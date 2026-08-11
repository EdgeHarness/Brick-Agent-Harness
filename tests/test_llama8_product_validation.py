from collections import Counter
import copy
from pathlib import Path

import pytest

from bench import llama8_product_validation as study
from domains.office_demo.sharvin_adapter import inspect_pinned_source
from harness.instances import load_canonical_json


EXTERNAL = Path(r"C:\bft-final-agent-8b-audit-7efc9b9")


def _auth():
    conditions = {}
    for name in study.CONDITIONS:
        conditions[name] = {
            "name": name,
            "version": "llama8-product-validation/1",
            "runner": name,
            "mechanisms": [],
            "mechanism_sha256": ("1" if name == "native_tools" else "2") * 64,
        }
    return {
        "authorization_sha256": "a" * 64,
        "schedule_sha256": "b" * 64,
        "protocol_sha256": study.protocol_sha256(),
        "tool_schema_sha256": "c" * 64,
        "runtime_fingerprint": {"fingerprint_sha256": "d" * 64},
        "conditions": conditions,
        "external_source": {
            "resolved_checkout": str(EXTERNAL),
            "adapter_binding": {
                "schema_version": "brick.sharvin-source-binding/1",
                "repository": "SMalshe/Final-Agent-8B",
                "remote": "https://github.com/SMalshe/Final-Agent-8B.git",
                "commit_sha": study.SHARVIN_COMMIT,
                "model_tag": study.MODEL_TAG,
                "files": dict(sorted(study._SHARVIN_SOURCE_DIGESTS.items())),
            },
        },
    }


def _real_auth():
    """Return a structurally valid authorization for model-free evidence tests."""

    schedule = study.build_schedule()
    runtime = {"fingerprint_sha256": "d" * 64}
    tool_schema = "c" * 64
    document = {
        "schema_version": study.AUTHORIZATION_SCHEMA,
        "status": "authorized_score_masked_execution",
        "execution_context": "authorized_research",
        "issued_at": "2026-08-11T06:00:00+00:00",
        "tag": study.FOLLOWUP_TAG,
        "tag_object_sha": "1" * 40,
        "commit_sha": "2" * 40,
        "protocol_sha256": study.protocol_sha256(),
        "schedule_sha256": study._digest(schedule),
        "run_id": study.RUN_ID,
        "runs_root": "results-next-study/llama8-product-validation-v0138",
        "logical_cell_ceiling": 126,
        "physical_attempt_ceiling": 252,
        "model": {"model_digest": study.MODEL_DIGEST},
        "conditions": {
            name: study._condition_identity(name, {
                "tool_schema_sha256": tool_schema,
                "runtime_fingerprint": runtime,
            })
            for name in study.CONDITIONS
        },
        "preflight_sha256": "3" * 64,
        "host_fingerprint": {},
        "runtime_fingerprint": runtime,
        "tool_schema_sha256": tool_schema,
        "validated_outcomes_sha256": "4" * 64,
        "source_digests": {},
        "external_source": {"commit_sha": study.SHARVIN_COMMIT},
        "score_embargo": True,
    }
    document["authorization_sha256"] = study._digest(document)
    return study.validate_authorization(document)


def _write_model_free_attempt(writer, *, gate, success):
    """Write a minimal fully valid marker-last transaction without inference."""

    writer.write_json("initial-state.json", {
        "schema_version": study.STATE_SCHEMA,
        "state_kind": "initial",
        "payload": {},
    })
    writer.write_json("final-state.json", {
        "schema_version": study.STATE_SCHEMA,
        "state_kind": "final",
        "payload": {},
    })
    writer.write_json("actions.json", {
        "schema_version": study.ACTIONS_SCHEMA,
        "actions": [],
    })
    writer.write_json("result.json", {
        "schema_version": study.RESULT_SCHEMA,
        "execution_status": "done",
        "tool_status": "clean",
        "failure_origin": "none",
        "failure": None,
        "metrics": {"model_calls": 1, "generated_tokens": 1},
        "diagnostics": {
            "condition": "model_free_lifecycle",
            "ledger": {
                "model_calls": 1,
                "generated_tokens_exact": True,
                "generated_tokens": 1,
                "generated_tokens_lower_bound": 1,
                "generated_tokens_upper_bound": 1,
            },
            "requests": [],
            "subepisodes": [],
            "verifier_unverified_count": 0,
            "repair_count": 0,
            "source_binding": None,
        },
    })
    writer.write_json("grade.json", {
        "schema_version": study.GRADE_SCHEMA,
        "grader_status": "not_run" if gate else "graded",
        "candidate_decision": None if gate else bool(success),
        "diagnostics": ({"reason": "score_free_instrument_compatibility_gate"} if gate else []),
    })
    writer.write_bytes("memory-delta.jsonl", b'{"delta":[],"schema_version":"brick.memory-delta/1"}\n')
    writer.write_bytes("transcript.md", b"# llama8 model-free lifecycle\n")


def _attempt(logical_id, success, *, condition, gate=False):
    return {
        "schema_version": study.ATTEMPT_RECORD_SCHEMA,
        "logical_cell_id": logical_id,
        "repeat": 0,
        "trial_seed": 1,
        "failure_origin": "none",
        "strict_success": None if gate else bool(success),
        "opportunity_budget_exhausted": False,
        "evidence_sha256": logical_id,
        "grade_record_sha256": "e" * 64,
        "marker_last_verified": True,
        "model_calls": 3,
        "generated_tokens_exact": True,
        "generated_tokens": 30,
        "generated_tokens_lower_bound": 30,
        "generated_tokens_upper_bound": 30,
        "successful_actions": 2,
        "action_count": 3,
        "verifier_unverified_count": int(condition == "sharvin_balanced_adapter" and not gate),
        "repair_count": int(condition == "sharvin_balanced_adapter" and not gate),
    }


def _analysis_for(monkeypatch, native_success, treatment_success):
    schedule = study.build_schedule()
    final = {}
    for cell in schedule["records"]:
        gate = cell["phase"] == "instrument_gate"
        success = native_success if cell["condition"] == "native_tools" else treatment_success
        final[cell["logical_cell_id"]] = _attempt(
            cell["logical_cell_id"], success, condition=cell["condition"], gate=gate,
        )
    monkeypatch.setattr(study, "validate_seal", lambda *args, **kwargs: args[0])
    monkeypatch.setattr(study, "extract_attempts", lambda *args, **kwargs: list(final.values()))
    monkeypatch.setattr(study, "_final_attempts", lambda *args, **kwargs: (final, [], [], []))
    return study._derive_analysis(
        _auth(), object(), schedule,
        {
            "status": "sealed_complete_valid", "seal_sha256": "f" * 64,
            "physical_attempts": 126,
        },
        analyzed_at="2026-08-11T06:00:00+00:00",
    )


def test_protocol_is_canonical_and_exactly_frozen():
    protocol = load_canonical_json(study.PROTOCOL_PATH)
    assert study.validate_protocol(protocol) == protocol
    assert protocol["panel"]["selected_ordinals"] == list(study.SELECTED_ORDINALS)
    assert protocol["panel"]["selection"]["subset_sha256"] == study.SELECTOR_DIGEST
    assert protocol["model"]["digest"] == study.MODEL_DIGEST
    assert protocol["source_freeze"]["selected_commit"] == study.SHARVIN_COMMIT


def test_preflight_uses_only_shared_validated_fingerprint_schemas():
    host = study.build_fingerprint(study.HOST_FINGERPRINT_SCHEMA, {"host": "test"})
    runtime = study.build_fingerprint(study.RUNTIME_FINGERPRINT_SCHEMA, {"runtime": "test"})
    assert host["schema_version"] == study.HOST_FINGERPRINT_SCHEMA
    assert runtime["schema_version"] == study.RUNTIME_FINGERPRINT_SCHEMA


def test_schedule_is_paired_balanced_unique_and_reproducible():
    first = study.build_schedule()
    second = study.build_schedule()
    assert first == second
    assert len(first["records"]) == 126
    assert sum(cell["phase"] == "instrument_gate" for cell in first["records"]) == 6
    assert sum(cell["phase"] == "primary" for cell in first["records"]) == 120
    assert all(cell["opening_gate"] for cell in first["records"][:6])
    assert not any(cell["opening_gate"] for cell in first["records"][6:])
    primary = [cell for cell in first["records"] if cell["phase"] == "primary"]
    assert Counter(cell["family"] for cell in primary) == {family: 40 for family in study.FAMILIES}
    assert Counter(cell["condition"] for cell in primary) == {condition: 60 for condition in study.CONDITIONS}
    for family in study.FAMILIES:
        family_cells = [cell for cell in primary if cell["family"] == family]
        assert Counter(cell["order_stratum"] for cell in family_cells) == {"AB": 20, "BA": 20}
    by_instance = {}
    for cell in first["records"]:
        by_instance.setdefault(cell["instance_id"], []).append(cell)
    assert len(by_instance) == 63
    request_seeds = set()
    for pair in by_instance.values():
        assert len(pair) == 2
        assert {cell["condition"] for cell in pair} == set(study.CONDITIONS)
        assert len({cell["trial_seed"] for cell in pair}) == 1
        request_seed = pair[0]["trial_seed"] & 0x7FFFFFFF
        assert request_seed not in request_seeds
        request_seeds.add(request_seed)


def test_selected_panel_reconstructs_all_frozen_margins():
    selected = study._validate_selected_panel(study.load_protocol(), study._validated_instances())
    for family, instances in selected.items():
        assert len(instances) == 20
        assert not any(item["content"]["initial_state"]["memory"] for item in instances)
        assert not any(item["content"]["initial_state"]["artifacts"] for item in instances)
        assert Counter(item["content"]["split"] for item in instances) == {
            "development": 4, "validation": 2, "sentinel": 2,
            "retained": 10, "adversarial": 2,
        }
        assert sorted(Counter(item["content"]["structure"]["decision_policy"] for item in instances).values()) == [6, 7, 7]


def test_full_attempt_key_binds_model_condition_sampling_budget_and_source():
    schedule = study.build_schedule()
    cell = schedule["records"][6]
    instance = study._instances_by_id()[cell["instance_id"]]
    key = study._attempt_key(_auth(), instance, cell, 0).to_dict()
    assert key["model"] == {"tag": study.MODEL_TAG, "digest": "sha256:" + study.MODEL_DIGEST}
    assert key["condition"]["name"] == cell["condition"]
    assert key["sampling"]["seed"] == cell["trial_seed"]
    assert key["sampling"]["request_seed"] == cell["trial_seed"] & 0x7FFFFFFF
    assert key["sampling"]["temperature"] == 0
    assert key["sampling"]["num_ctx"] == 8192
    assert key["opportunity_budget"] == {
        "model_calls": 18, "generated_tokens": 6144,
        "generated_tokens_per_request": 700, "shared_across_subepisodes": 1,
    }


def test_operational_attempt_report_counts_retries_and_invalid_origins_by_phase():
    schedule = study.build_schedule()
    gate_cell = schedule["records"][0]
    primary_cell = schedule["records"][6]
    first = _attempt(gate_cell["logical_cell_id"], False, condition=gate_cell["condition"], gate=True)
    first["failure_origin"] = "environment"
    retry = copy.deepcopy(first)
    retry["repeat"] = 1
    retry["failure_origin"] = "none"
    instrument = _attempt(
        primary_cell["logical_cell_id"], False,
        condition=primary_cell["condition"], gate=False,
    )
    instrument["failure_origin"] = "instrument"
    report = study._operational_attempt_report([first, retry, instrument], schedule)
    assert report == {
        "all_authorized": {
            "physical_attempts": 3,
            "repeat_1_same_seed_retries": 1,
            "environment_invalid_physical_attempts": 1,
            "instrument_invalid_physical_attempts": 1,
        },
        "instrument_gate": {
            "physical_attempts": 2,
            "repeat_1_same_seed_retries": 1,
            "environment_invalid_physical_attempts": 1,
            "instrument_invalid_physical_attempts": 0,
        },
        "primary": {
            "physical_attempts": 1,
            "repeat_1_same_seed_retries": 0,
            "environment_invalid_physical_attempts": 0,
            "instrument_invalid_physical_attempts": 1,
        },
    }


def test_positive_negative_and_null_analyzer_goldens(monkeypatch):
    positive = _analysis_for(monkeypatch, False, True)
    assert positive["paired_effect"]["fraction"] == "1/1"
    assert positive["claim_rule"]["disposition"] == "sharvin_balanced_adapter_superiority"
    assert positive["bootstrap_95_percent_interval"]["lower"]["fraction"] == "1/1"
    negative = _analysis_for(monkeypatch, True, False)
    assert negative["paired_effect"]["fraction"] == "-1/1"
    assert negative["claim_rule"]["disposition"] == "native_tools_superiority"
    null = _analysis_for(monkeypatch, False, False)
    assert null["paired_effect"]["fraction"] == "0/1"
    assert null["claim_rule"]["disposition"] == "no_directional_superiority_claim"
    assert positive["bootstrap_95_percent_interval"]["first_100_index_vectors_sha256"] == negative["bootstrap_95_percent_interval"]["first_100_index_vectors_sha256"]


def test_marker_last_requires_empty_completion_marker(tmp_path):
    path = tmp_path / "artifact.json"
    document = {"schema_version": "example/1", "value": 1}
    study._publish_marker_last(path, document)
    assert study._load_published(path, "test") == document
    path.with_name(path.name + ".complete").write_text("not-empty", encoding="utf-8")
    with pytest.raises(study.Llama8ProductValidationError, match="marker-last"):
        study._load_published(path, "test")


def test_json_only_marker_recovery_is_exact_and_marker_only_fails(tmp_path):
    document = {"schema_version": "example/1", "value": 2}
    path = tmp_path / "json-only.json"
    path.write_bytes(study.canonical_json_bytes(document, newline=True))
    assert study._publish_or_recover_marker_last(path, document, "test") == document
    assert path.with_name(path.name + ".complete").read_bytes() == b""
    changed = {"schema_version": "example/1", "value": 3}
    with pytest.raises(study.Llama8ProductValidationError, match="differs"):
        study._publish_or_recover_marker_last(path, changed, "test")
    marker_only = tmp_path / "marker-only.json"
    marker_only.with_name(marker_only.name + ".complete").write_bytes(b"")
    with pytest.raises(study.Llama8ProductValidationError, match="unsafe marker"):
        study._publish_or_recover_marker_last(marker_only, document, "test")


@pytest.mark.skipif(not EXTERNAL.is_dir(), reason="private pinned checkout is unavailable")
def test_private_external_source_binding_matches_protocol_and_never_uses_branch():
    binding = inspect_pinned_source(EXTERNAL)
    assert binding["commit_sha"] == study.SHARVIN_COMMIT
    assert binding["files"] == dict(sorted(study._SHARVIN_SOURCE_DIGESTS.items()))
    external = study._external_source_binding(EXTERNAL)
    assert external["adapter_binding"] == binding
    assert external["tree_sha"] == study.SHARVIN_TREE


def test_authorization_tamper_rejects_after_resigning(monkeypatch):
    protocol = study.load_protocol()
    schedule = study.build_schedule(protocol)
    runtime = {"fingerprint_sha256": "d" * 64}
    preflight = {
        "tool_schema_sha256": "c" * 64,
        "runtime_fingerprint": runtime,
    }
    conditions = {name: study._condition_identity(name, preflight) for name in study.CONDITIONS}
    document = {
        "schema_version": study.AUTHORIZATION_SCHEMA,
        "status": "authorized_score_masked_execution", "execution_context": "authorized_research",
        "issued_at": "2026-08-11T06:00:00+00:00", "tag": study.FOLLOWUP_TAG,
        "tag_object_sha": "1" * 40, "commit_sha": "2" * 40,
        "protocol_sha256": study.protocol_sha256(protocol), "schedule_sha256": study._digest(schedule),
        "run_id": study.RUN_ID, "runs_root": "results-next-study/llama8-product-validation-v0138",
        "logical_cell_ceiling": 126, "physical_attempt_ceiling": 252,
        "model": {"model_digest": study.MODEL_DIGEST}, "conditions": conditions,
        "preflight_sha256": "3" * 64, "host_fingerprint": {}, "runtime_fingerprint": runtime,
        "tool_schema_sha256": "c" * 64, "validated_outcomes_sha256": "4" * 64,
        "source_digests": {}, "external_source": {"commit_sha": study.SHARVIN_COMMIT},
        "score_embargo": True,
    }
    document["authorization_sha256"] = study._digest(document)
    assert study.validate_authorization(document, protocol) == document
    changed = copy.deepcopy(document)
    changed["run_id"] = "alternate-run"
    changed["authorization_sha256"] = study._digest({k: v for k, v in changed.items() if k != "authorization_sha256"})
    with pytest.raises(study.Llama8ProductValidationError, match="semantics"):
        study.validate_authorization(changed, protocol)


def test_full_model_free_marker_last_lifecycle_rederives_report(tmp_path, monkeypatch):
    """Exercise all 126 real transactions, seals, analysis, and report offline."""

    runs_root = tmp_path / "runs"
    gate_path = tmp_path / "instrument-gate-seal.json"
    seal_path = tmp_path / "seal.json"
    monkeypatch.setattr(study, "RUNS_ROOT", runs_root)
    monkeypatch.setattr(study, "GATE_SEAL_PATH", gate_path)
    monkeypatch.setattr(study, "SEAL_PATH", seal_path)

    authorization = _real_auth()
    schedule = study.build_schedule()
    store = study._open_store(authorization, runs_root=runs_root)
    instances = study._instances_by_id()

    for cell in schedule["records"]:
        gate = cell["phase"] == "instrument_gate"
        success = cell["condition"] == "sharvin_balanced_adapter"
        key = study._attempt_key(
            authorization, instances[cell["instance_id"]], cell, 0,
        )

        def producer(writer, *, gate=gate, success=success):
            _write_model_free_attempt(writer, gate=gate, success=success)

        resolution = store.execute_or_resume(key, producer)
        assert resolution.state == "committed"

    projection = store.read_committed()
    assert len(projection["records"]) == 126
    attempts = study.extract_attempts(store, schedule, authorization)
    assert len(attempts) == 126
    final, missing, pending, invalid = study._final_attempts(schedule, attempts)
    assert len(final) == 126
    assert not missing and not pending and not invalid

    gate_seal = study._build_gate_seal(
        authorization, store, schedule, sealed_at="2026-08-11T06:10:00+00:00",
    )
    study._publish_marker_last(gate_path, gate_seal)
    assert study.validate_gate_seal(
        gate_seal, authorization, store=store, schedule=schedule,
    ) == gate_seal

    seal = study._build_seal(
        authorization, store, schedule,
        status="sealed_complete_valid",
        reason="all_authorized_cells_complete_and_valid",
        sealed_at="2026-08-11T06:20:00+00:00",
    )
    study._publish_marker_last(seal_path, seal)
    assert study.validate_seal(
        seal, authorization, store=store, schedule=schedule,
    ) == seal

    analysis = study._derive_analysis(
        authorization, store, schedule, seal,
        analyzed_at="2026-08-11T06:30:00+00:00",
    )
    assert analysis["paired_clusters"] == 60
    assert analysis["paired_effect"]["fraction"] == "1/1"
    assert analysis["claim_rule"]["disposition"] == "sharvin_balanced_adapter_superiority"
    assert analysis["operational_attempts"]["all_authorized"] == {
        "physical_attempts": 126,
        "repeat_1_same_seed_retries": 0,
        "environment_invalid_physical_attempts": 0,
        "instrument_invalid_physical_attempts": 0,
    }
    assert study.validate_analysis(
        analysis, authorization, store=store, schedule=schedule, seal=seal,
    ) == analysis

    report = study._derive_report(
        authorization, analysis, reported_at="2026-08-11T06:40:00+00:00",
    )
    assert report["answer"]["disposition"] == "sharvin_balanced_adapter_superiority"
    assert report["operational_attempts"] == analysis["operational_attempts"]
    assert study.validate_report(report, authorization, analysis) == report

    forged = copy.deepcopy(seal)
    forged["physical_attempts"] = 125
    forged["seal_sha256"] = study._digest({
        key: value for key, value in forged.items() if key != "seal_sha256"
    })
    with pytest.raises(study.Llama8ProductValidationError, match="rederivation"):
        study.validate_seal(
            forged, authorization, store=store, schedule=schedule,
        )
