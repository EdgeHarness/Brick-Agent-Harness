import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from bench import s6_run, s7_decision, s7_floor_audit, s7_run
from bench.s7_analysis import analyze, exact_sign_flip
from bench.s7_artifacts import S7ArtifactError, commit_artifact, verify_artifact
from bench.s7_contract import (
    S7ContractError,
    equal_action_protocol,
    load_protocol,
    s7_protocol_sha256,
    validate_protocol,
)
from harness.evidence import canonical_json_bytes
from harness.experiment import BudgetExhausted, OpportunityLedger
from harness.experiment import condition_registry, protocol_sha256
from harness.instances import load_canonical_json


ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / "bench" / "manifests" / "office-v1"
BASE_PROTOCOL = json.loads(
    (ROOT / "bench" / "s6_protocol.json").read_text(encoding="utf-8")
)


class _CaptureWriter:
    def __init__(self):
        self.json = {}
        self.bytes = {}

    def write_json(self, relative, value):
        self.json[relative] = copy.deepcopy(value)

    def write_bytes(self, relative, payload):
        self.bytes[relative] = bytes(payload)


class _DoneTransport:
    def chat(self, payload):
        return {
            "model": payload["model"],
            "created_at": "2026-08-03T00:00:00Z",
            "message": {
                "role": "assistant",
                "content": "",
                "thinking": None,
                "tool_calls": [{
                    "function": {
                        "name": "done",
                        "arguments": {"summary": "complete"},
                    }
                }],
            },
            "done": True,
            "done_reason": "stop",
            "total_duration": 10,
            "load_duration": 1,
            "prompt_eval_count": 5,
            "prompt_eval_duration": 2,
            "eval_count": 1,
            "eval_duration": 3,
        }


def test_s7_protocol_and_d0_schedule_are_exact_and_fail_closed(monkeypatch, tmp_path):
    protocol = load_protocol()
    changed = copy.deepcopy(protocol)
    changed["d0"]["pairs_per_cohort"] = 43
    with pytest.raises(S7ContractError, match="allocation"):
        validate_protocol(changed)

    manifest = load_canonical_json(MANIFESTS / "development.json")
    d0a = [
        item for item in manifest["instances"]
        if item["content"]["id"].startswith("development.d0a.")
    ]
    d0b = [
        item for item in manifest["instances"]
        if item["content"]["id"].startswith("development.d0b.")
    ]
    assert len(d0a) == len(d0b) == 44
    assert set(item["content"]["structure_sha256"] for item in d0a).isdisjoint(
        item["content"]["structure_sha256"] for item in d0b
    )
    assert {len(values) for values in (
        [item for item in d0a if item["content"]["family"] == family]
        for family in manifest["family_counts"]
    )} == {4}
    assert len(s6_run._waves(d0a)) * len(protocol["d0"]["conditions"]) == 88

    captured = {}
    def fake_run(args, policy, preflight=None):
        captured.update(args=args, policy=policy, preflight=preflight)
        return {"cells": [{} for _ in range(88)]}
    monkeypatch.setattr(s7_run.s6_run, "_run", fake_run)
    args = SimpleNamespace(
        protocol=ROOT / "bench" / "s7_protocol.json",
        cohort="d0a",
        instance_id=None,
        max_cases=None,
        run_id="test-d0a",
        manifests=MANIFESTS,
        runs_root=tmp_path,
    )
    summary = s7_run.run(args, preflight={"passed": True, "environment": {}})
    assert len(summary["cells"]) == 88
    assert captured["args"].split == "development"
    assert captured["policy"].grading_mode == "deferred"
    assert captured["policy"].score_masked is True
    assert captured["policy"].instance_prefix == "development.d0a."
    assert captured["policy"].required_conditions == (
        "native_tools", "harness_full"
    )


def test_deferred_producer_writes_no_candidate_decision():
    manifest = load_canonical_json(MANIFESTS / "validation.json")
    instance = manifest["instances"][0]
    condition = condition_registry(BASE_PROTOCOL, "1" * 64)["native_tools"]
    writer = _CaptureWriter()
    s6_run._producer(
        instance, condition, BASE_PROTOCOL, _DoneTransport(),
        grading_mode="deferred",
    )(writer)
    assert writer.json["grade.json"] == {
        "schema_version": "brick.evidence-grade/1",
        "grader_status": "not_run",
        "candidate_decision": None,
        "diagnostics": {"checks": [], "error": None},
    }


def test_equal_action_role_budgets_do_not_borrow_between_roles():
    s7 = load_protocol()
    changed = equal_action_protocol(BASE_PROTOCOL, "harness_full", 2, s7)
    budget = changed["opportunity_budget"]
    assert budget["model_calls"] == 18
    assert budget["generated_tokens"] == 6896
    ledger = OpportunityLedger(
        budget["model_calls"], budget["generated_tokens"],
        budget["generated_tokens_per_request"], budget["role_budgets"],
    )
    for _ in range(2):
        assert ledger.begin_request("plan") == 700
        ledger.finish_request(1, 700, "plan")
    with pytest.raises(BudgetExhausted, match="role"):
        ledger.begin_request("plan")
    assert ledger.begin_request("driver") == 700
    ledger.finish_request(2, 700, "driver")
    record = ledger.as_record()
    assert record["call_roles"] == {"driver": 1, "plan": 2}
    assert record["role_generated_tokens"] == {"driver": 2, "plan": 2}

    native = equal_action_protocol(BASE_PROTOCOL, "native_tools", 2, s7)
    assert native["opportunity_budget"]["role_budgets"] == {
        "driver": s7["equal_action_sensitivity"]["driver"]
    }


def test_marker_last_artifact_detects_tampering(tmp_path):
    target = tmp_path / "decision"
    document = {"schema_version": "test.decision/1", "selected": 12}
    committed = commit_artifact(target, document)
    assert commit_artifact(target, document) == committed
    with pytest.raises(S7ArtifactError, match="different content"):
        commit_artifact(
            target, {"schema_version": "test.decision/1", "selected": 20}
        )
    assert committed["document"] == document
    assert verify_artifact(target)["artifact_sha256"] == committed["artifact_sha256"]
    (target / "artifact.json").write_bytes(
        canonical_json_bytes(
            {"schema_version": "test.decision/1", "selected": 20}, newline=True
        )
    )
    with pytest.raises(S7ArtifactError, match="binding"):
        verify_artifact(target)


def _fake_d0(protocol, wall_seconds=1.0):
    implementation = "1" * 64
    environment = {
        "implementation_sha256": implementation,
        "domain_sha256": "2" * 64,
        "tool_schema_sha256": "3" * 64,
        "protocol_sha256": protocol_sha256(BASE_PROTOCOL),
        "ollama": {
            "model_digest": BASE_PROTOCOL["f0_binding"]["primary_model_digest"],
        },
        "s7_protocol_sha256": s7_protocol_sha256(protocol),
        "analysis_python_minor": protocol["analysis"]["python_minor"],
        "analysis_numpy_version": protocol["analysis"]["numpy_version"],
    }
    conditions = condition_registry(BASE_PROTOCOL, implementation)
    manifest = load_canonical_json(MANIFESTS / "development.json")
    instances = [
        item for item in manifest["instances"]
        if item["content"]["id"].startswith("development.d0a.")
    ]
    schedule = [
        {
            "wave": wave,
            "family": family,
            "instance_id": instance["content"]["id"],
            "condition_order": list(order),
        }
        for wave, family, instance, order in s6_run._waves(instances)
    ]
    records = []
    for _wave, _family, instance, _order in s6_run._waves(instances):
        for condition_name in protocol["d0"]["conditions"]:
            key = s6_run._attempt_key(
                instance, conditions[condition_name], environment,
                BASE_PROTOCOL, 0,
            )
            records.append({
                "attempt_key": key.to_dict(),
                "logical_hash": str(key.logical_hash),
                "physical_uuid": "00000000-0000-4000-8000-%012d" % len(records),
                "grader_status": "not_run",
                "strict_success": None,
                "grade": {"candidate_decision": None},
                "failure_origin": "none",
                "result": {"metrics": {"wall_seconds": wall_seconds}},
            })
    metadata = {
        "run_kind": "score_masked_d0",
        "split": "development",
        "retained": False,
        "grading_mode": "deferred",
        "score_masked": True,
        "cohort": "d0a",
        "protocol_binding": {
            "schema_version": protocol["schema_version"],
            "protocol_version": protocol["protocol_version"],
            "sha256": s7_protocol_sha256(protocol),
        },
        "schedule": schedule,
        "protocol": BASE_PROTOCOL,
        "environment": environment,
        "conditions": {
            name: {
                "version": spec.version,
                "mechanisms": list(spec.mechanisms),
                "mechanism_sha256": spec.mechanism_sha256,
            }
            for name, spec in conditions.items()
        },
    }
    projection = {"records": records}
    store = SimpleNamespace(
        run_document={"metadata": metadata},
        run_sha256="a" * 64,
        read_committed=lambda: projection,
    )
    return store, records


def test_runtime_decision_is_complete_masked_and_uses_only_wall_time(monkeypatch):
    protocol = load_protocol()
    store, records = _fake_d0(protocol, wall_seconds=1.0)
    monkeypatch.setattr(s7_decision.EvidenceStore, "open_run", lambda *_a: store)
    decision = s7_decision.build_decision("ignored", "d0-test")
    assert decision["valid_attempts"] == 88
    assert decision["selected_cases_per_family"] == 20
    assert decision["estimated_retained_wall_seconds"] == "550"
    assert decision["efficacy_fields_read"] is False

    records[0]["grader_status"] = "graded"
    records[0]["strict_success"] = True
    records[0]["grade"]["candidate_decision"] = True
    with pytest.raises(RuntimeError, match="efficacy score"):
        s7_decision.build_decision("ignored", "d0-test")

    store, records = _fake_d0(protocol, wall_seconds=1.0)
    monkeypatch.setattr(s7_decision.EvidenceStore, "open_run", lambda *_a: store)
    records[0]["attempt_key"]["instance"]["content_sha256"] = "f" * 64
    with pytest.raises(RuntimeError, match="identity differs"):
        s7_decision.build_decision("ignored", "d0-test")


def test_floor_ceiling_audit_is_direction_blind_and_blocks_flagged_family(
    monkeypatch, tmp_path
):
    protocol = load_protocol()
    store, records = _fake_d0(protocol, wall_seconds=1.0)
    monkeypatch.setattr(s7_decision.EvidenceStore, "open_run", lambda *_a: store)
    monkeypatch.setattr(s7_floor_audit.EvidenceStore, "open_run", lambda *_a: store)
    decision = s7_decision.build_decision("ignored", "d0-test")
    decision_dir = tmp_path / "decision"
    commit_artifact(decision_dir, decision)
    monkeypatch.setattr(
        s7_floor_audit,
        "_grade_record",
        lambda _store, record, _instance: (
            record["attempt_key"]["task"]["family"] != "cal_add"
            and record["attempt_key"]["condition"]["name"] == "native_tools"
        ),
    )
    audit = s7_floor_audit.build_audit(
        "ignored", "d0-test", decision_dir
    )
    assert audit["flags"] == [{"family": "cal_add", "flag": "floor"}]
    assert audit["protocol_freeze_allowed"] is False
    assert audit["condition_scores_emitted"] is False
    assert audit["directional_effects_computed"] is False
    assert all(
        set(item) == {"family", "combined_successes", "combined_outcomes"}
        for item in audit["family_combined_totals"]
    )


def _analysis_fixture():
    protocol = load_protocol()
    pairs = []
    for family_index in range(11):
        family = "family-%02d" % family_index
        for ordinal in range(12):
            pairs.append({
                "instance_id": "%s.%02d" % (family, ordinal),
                "family": family,
                "native_tools": ordinal % 3 == 0,
                "harness_full": ordinal % 2 == 0,
            })
    return {
        "schema_version": "brick.s7.paired-outcomes/1",
        "s7_protocol_sha256": s7_protocol_sha256(protocol),
        "cases_per_family": 12,
        "pairs": pairs,
    }


@pytest.mark.skipif(
    sys.version_info[:2] != (3, 13),
    reason="the frozen analysis environment is Python 3.13",
)
def test_frozen_analysis_has_exact_sign_flip_and_golden_random_stream():
    numerator, denominator = exact_sign_flip(44, 22)
    assert (numerator, denominator) == (84951773094493789, 9223372036854775808)
    result = analyze(_analysis_fixture())
    assert result["condition_successes"] == {
        "native_tools": 44, "harness_full": 66
    }
    assert result["equal_family_delta"] == (
        "0.16666666666666666666666666666666666666666666666667"
    )
    assert result["discordance"]["harness_only_success"] == 44
    assert result["discordance"]["native_only_success"] == 22
    assert result["bootstrap"]["confidence_interval"] == [
        "0.053030303030303025", "0.28030303030303033"
    ]
    assert result["bootstrap"]["first_100_index_vectors_sha256"] == (
        "2586e4a517d48b7a2296a8eed959689739098bb7bb246900e7b0d2e2e69dc525"
    )
    assert len(result["leave_one_family_out"]) == 11
    assert len(result["family_effects"]) == 11
    assert all(item["delta"] == result["equal_family_delta"] for item in result["family_effects"])


@pytest.mark.parametrize(
    "positive,negative,expected",
    [
        (0, 0, (1, 1)),
        (1, 0, (1, 1)),
        (2, 0, (1, 2)),
        (3, 0, (1, 4)),
        (4, 0, (1, 8)),
        (3, 1, (5, 8)),
    ],
)
def test_exact_sign_flip_small_enumerations(positive, negative, expected):
    assert exact_sign_flip(positive, negative) == expected
