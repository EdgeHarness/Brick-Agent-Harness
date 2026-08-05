import copy
from pathlib import Path

import pytest

from bench.next_study_live import (
    NextStudyLiveError, _attempt_key, _condition, _producer, build_execution_protocol,
    build_shakeout_authorization, validate_native_preflight,
    validate_shakeout_authorization,
)
from bench.next_study_program import (
    HOST_FINGERPRINT_SCHEMA, REQUIRED_ARTIFACT_DIGESTS,
    RUNTIME_FINGERPRINT_SCHEMA, build_authorization, build_fingerprint,
)
from bench.next_study_runtime import extract_attempt_records
from bench.next_study_schedule import (
    build_descriptive_schedule, build_development_shakeout_schedule,
    build_phase_schedule,
)
from harness.instances import load_canonical_json
from harness.evidence import EvidenceStore


ROOT = Path(__file__).resolve().parents[1]


def _preflight(model_digest="4" * 64):
    document = {
        "schema_version": "brick.next-study.native-preflight/1",
        "status": "passed", "passed": True, "require_clean": True,
        "git_clean": True, "commit_sha": "b" * 40,
        "host_fingerprint": build_fingerprint(HOST_FINGERPRINT_SCHEMA, {"host": "test"}),
        "runtime_fingerprint": build_fingerprint(RUNTIME_FINGERPRINT_SCHEMA, {"runtime": "test"}),
        "model_digests": {"2b": "2" * 64, "4b": model_digest, "9b": "9" * 64},
        "tool_schema_sha256": "c" * 64, "research_catalog_closed": True,
        "plugin_entry_points_enumerated": False,
        "validated_outcomes_sha256": "d" * 64, "live_model_calls": 0,
    }
    from harness.evidence import canonical_json_bytes
    from harness.instances import sha256_bytes
    document["preflight_sha256"] = sha256_bytes(canonical_json_bytes(document))
    return validate_native_preflight(document)


def test_successor_execution_protocol_has_exact_budget_and_runtime_role_names():
    regular = build_execution_protocol()
    assert regular["opportunity_budget"] == {
        "model_calls": 18, "generated_tokens": 6144,
        "generated_tokens_per_request": 700, "shared_across_subepisodes": True,
    }
    equal = build_execution_protocol(equal_action=True)
    roles = equal["opportunity_budget"]["role_budgets"]
    assert set(roles) == {"driver", "plan", "completion"}
    assert sum(item["model_calls"] for item in roles.values()) == 18
    assert sum(item["generated_tokens"] for item in roles.values()) == 6144


def test_shakeout_authorization_is_exact_and_cannot_authorize_research():
    preflight = _preflight()
    manifest = load_canonical_json(
        ROOT / "bench" / "manifests" / "office-v2" / "development.json"
    )
    schedule = build_development_shakeout_schedule(manifest, "4" * 64)
    authorization = build_shakeout_authorization(
        preflight, schedule, issued_at="2026-08-05T10:00:00Z", issuer="tester",
    )
    assert authorization["research_phase_allowed"] is False
    assert authorization["maximum_logical_cells"] == 22
    changed = copy.deepcopy(authorization)
    changed["research_phase_allowed"] = True
    with pytest.raises(NextStudyLiveError, match="digest drifted"):
        validate_shakeout_authorization(changed)


def test_attempt_identity_binds_trial_seed_but_uses_provider_low31_seed():
    manifest = load_canonical_json(
        ROOT / "bench" / "manifests" / "office-v2" / "development.json"
    )
    schedule = build_development_shakeout_schedule(manifest, "4" * 64)
    cell = schedule["records"][0]
    instance = next(
        item for item in manifest["instances"] if item["content"]["id"] == cell["instance_id"]
    )
    condition, protocol = _condition("native_tools", "a" * 64)
    key = _attempt_key(
        instance, cell, condition, protocol, protocol["primary_model"], "4" * 64,
        0, _preflight(),
    ).to_dict()
    assert key["sampling"]["seed"] == cell["trial_seed"]
    assert key["sampling"]["request_seed"] == cell["trial_seed"] & 0x7FFFFFFF
    assert key["sampling"]["trial_index"] == 0


def test_live_producer_executes_and_grades_v2_packet_through_native_tools(tmp_path):
    manifest = load_canonical_json(
        ROOT / "bench" / "manifests" / "office-v2" / "development.json"
    )
    schedule = build_development_shakeout_schedule(manifest, "4" * 64)
    cell = next(item for item in schedule["records"] if item["family"] == "cal_add" and item["condition"] == "native_tools")
    instance = next(item for item in manifest["instances"] if item["content"]["id"] == cell["instance_id"])
    validated = load_canonical_json(
        ROOT / "evidence" / "next-study" / "office-v2-validated-outcomes.json"
    )
    outcome_record = next(item for item in validated["records"] if item["instance_id"] == cell["instance_id"])
    event = next(item for item in outcome_record["outcome"] if item["type"] == "event_created")
    calls = [
        ("list_events", {"date": event["date"]}),
        (
            "add_event",
            {
                "title": event["title"],
                "date": event["date"],
                "start_time": event["start"],
                "end_time": event["end"],
                "location": event["location"],
                "attendees": event["attendees"],
            },
        ),
        ("done", {"summary": "calendar task complete"}),
    ]

    class Transport:
        def chat(self, payload):
            name, arguments = calls.pop(0)
            return {
                "model": payload["model"], "done": True,
                "message": {"role": "assistant", "content": "", "thinking": "", "tool_calls": [{"function": {"name": name, "arguments": arguments}}]},
                "total_duration": 1, "load_duration": 0,
                "prompt_eval_count": 1, "prompt_eval_duration": 1,
                "eval_count": 1, "eval_duration": 1, "done_reason": "stop",
            }

    condition, protocol = _condition("native_tools", "a" * 64)
    preflight = _preflight()
    key = _attempt_key(
        instance, cell, condition, protocol, protocol["primary_model"], "4" * 64,
        0, preflight,
    )
    store = EvidenceStore.create_run(tmp_path / "runs", "adapter-test", {"kind": "test"})
    resolution = store.execute_or_resume(
        key, _producer(instance, outcome_record, cell, condition, protocol, Transport())
    )
    assert resolution.state == "committed"
    assert resolution.record["strict_success"] is True
    assert resolution.record["grader_status"] == "graded"
    assert calls == []


def test_sentinel_live_producer_never_constructs_or_invokes_a_grader(
    tmp_path, monkeypatch,
):
    manifest = load_canonical_json(
        ROOT / "bench" / "manifests" / "office-v2" / "sentinel.json"
    )
    schedule = build_phase_schedule(manifest, "sentinel", "4" * 64)
    cell = next(
        item for item in schedule["records"]
        if item["family"] == "cal_add" and item["condition"] == "native_tools"
    )
    instance = next(
        item for item in manifest["instances"]
        if item["content"]["id"] == cell["instance_id"]
    )
    validated = load_canonical_json(
        ROOT / "evidence" / "next-study" / "office-v2-validated-outcomes.json"
    )
    outcome_record = next(
        item for item in validated["records"]
        if item["instance_id"] == cell["instance_id"]
    )
    event = next(
        item for item in outcome_record["outcome"] if item["type"] == "event_created"
    )
    calls = [
        ("list_events", {"date": event["date"]}),
        ("add_event", {
            "title": event["title"], "date": event["date"],
            "start_time": event["start"], "end_time": event["end"],
            "location": event["location"], "attendees": event["attendees"],
        }),
        ("done", {"summary": "sentinel complete"}),
    ]

    class Transport:
        def chat(self, payload):
            name, arguments = calls.pop(0)
            return {
                "model": payload["model"], "done": True,
                "message": {"role": "assistant", "content": "", "thinking": "", "tool_calls": [{"function": {"name": name, "arguments": arguments}}]},
                "total_duration": 1, "load_duration": 0,
                "prompt_eval_count": 1, "prompt_eval_duration": 1,
                "eval_count": 1, "eval_duration": 1, "done_reason": "stop",
            }

    monkeypatch.setattr(
        "bench.next_study_live.build_grader",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("grader invoked")),
    )
    condition, protocol = _condition("native_tools", "a" * 64)
    key = _attempt_key(
        instance, cell, condition, protocol, protocol["primary_model"], "4" * 64,
        0, _preflight(),
    )
    store = EvidenceStore.create_run(
        tmp_path / "runs", "sentinel-adapter-test", {"kind": "test"}
    )
    resolution = store.execute_or_resume(
        key, _producer(instance, outcome_record, cell, condition, protocol, Transport())
    )
    assert resolution.state == "committed"
    assert resolution.record["grader_status"] == "not_run"
    assert resolution.record["strict_success"] is None
    extracted = extract_attempt_records(store, {
        **schedule,
        "records": [cell],
        "logical_cell_count": 1,
        "maximum_physical_attempts": 2,
    })
    assert extracted[0]["failure_origin"] == "none"
    assert extracted[0]["strict_success"] is None
    assert calls == []


def test_research_executor_requires_authorization_bound_program_state(tmp_path):
    manifests = {
        name: load_canonical_json(
            ROOT / "bench" / "manifests" / "office-v2" / (name + ".json")
        )
        for name in ("calibration", "sentinel", "retained")
    }
    model_digests = {"2b": "2" * 64, "4b": "4" * 64, "9b": "9" * 64}
    schedules = {
        "calibration": build_phase_schedule(
            manifests["calibration"], "calibration", model_digests["4b"]
        ),
        "sentinel": build_phase_schedule(
            manifests["sentinel"], "sentinel", model_digests["4b"]
        ),
        "primary": build_phase_schedule(
            manifests["retained"], "primary", model_digests["4b"]
        ),
        "descriptives": build_descriptive_schedule(
            manifests["retained"], model_digests
        ),
    }
    from harness.evidence import canonical_json_bytes
    from harness.instances import sha256_bytes
    authorization = build_authorization(
        tag="v0.13.0", tag_object_sha="8" * 40, commit_sha="b" * 40,
        artifact_digests={name: "a" * 64 for name in REQUIRED_ARTIFACT_DIGESTS},
        host_fingerprint=_preflight()["host_fingerprint"],
        runtime_fingerprint=_preflight()["runtime_fingerprint"],
        schedule_digests={
            name: sha256_bytes(canonical_json_bytes(value, allow_float=False))
            for name, value in schedules.items()
        },
        model_digests=model_digests,
        descriptive_selection_sha256=schedules["descriptives"]["selection_sha256"],
        issued_at="2026-08-05T10:00:00Z", issuer="tester",
    )
    from bench.next_study_live import execute_schedule
    with pytest.raises(NextStudyLiveError, match="sealed program state"):
        execute_schedule(
            schedule=schedules["calibration"], manifest=manifests["calibration"],
            authorization=authorization, preflight=_preflight(),
            runs_root=tmp_path / "runs", run_id="must-not-start",
        )
    assert not (tmp_path / "runs").exists()
