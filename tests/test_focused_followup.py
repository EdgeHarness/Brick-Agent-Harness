"""Model-free integrity tests for the deadline-focused follow-up.

These tests deliberately construct schedules and synthetic analysis rows only.
They never open Ollama, execute an agent, or write outside pytest's ``tmp_path``.
"""

from __future__ import annotations

import copy
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

import pytest

from bench import focused_followup as focused
import harness.evidence as evidence_module
from harness.evidence import AttemptKey
from harness.instances import load_canonical_json
from bench.next_study_schedule import (
    build_development_shakeout_schedule,
    build_phase_schedule,
)


MODEL_DIGEST = "2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd"
SHA256_A = "a" * 64
SHA256_B = "b" * 64
SHA256_C = "c" * 64
SHA1_A = "a" * 40
SHA1_B = "b" * 40
RUN_ID = "v0134-focused-followup-r1"
PUBLIC_COMBINED_CALIBRATION_TOTALS = {
    "cal_add": 25,
    "cal_brief": 8,
    "cal_freeslot": 18,
    "email_reply": 27,
    "multi_offsite": 3,
    "pptx_basic": 17,
    "pptx_from_email": 23,
    "preference_learning": 2,
    "remind_msg": 17,
    "xlsx_basic": 8,
    "xlsx_from_email": 1,
}
PUBLIC_SHAKEOUT_BINDINGS = {
    "schedule_file_sha256": "2b90035f6b9e257e6b84d17e4920e6bcb53be3dfbb5d9b4cf8d2610574660753",
    "authorization_file_sha256": "1708eb5667ccb786bd0b5b01c33bf7ecf3b3fba4856071a443ba0108f060f8de",
    "decision_file_sha256": "d6ad146d78b8b6b2380e83115dfadeb6b64b86c0c1e249602fbd0a967dd4ddc3",
    "authorization_sha256": "d31c4f483387183ba8d5f077ab7606495fc71dfdc1095ef82833d9c655d295dd",
    "decision_sha256": "cd41a00e2ce52afb3093957fff3d2435ff870436807086d2ed835460f297a794",
    "B1_shakeout_context_overlap_clusters": 6,
    "B2_repeats_B1a_clusters": 120,
    "full_seed_overlap": 0,
    "request_seed_low31_overlap": 0,
}


@pytest.fixture(scope="module")
def protocol():
    return focused.load_protocol()


def _authorization(protocol, model_digest=MODEL_DIGEST):
    """Build a fully self-consistent, model-free authorization fixture."""

    schedules = focused.build_schedules(model_digest, protocol)
    source = {
        "implementation_sha256": SHA256_A,
        "supervisor_path": "scripts/run-focused-followup.ps1",
        "generator": SHA256_B,
        "outcome_oracle_implementation": SHA256_B,
        "validated_outcomes": SHA256_B,
        "tool_contracts": SHA256_B,
        "reviewed_grader": SHA256_B,
        "strict_graders": SHA256_B,
        "office_files": SHA256_B,
        "world": SHA256_B,
        "validated_outcomes_compiler": SHA256_B,
        "focused_protocol": SHA256_B,
        "focused_analyzer": SHA256_B,
        "focused_supervisor": SHA256_B,
        "manifest_lock": SHA256_B,
        "exploratory_plan": SHA256_B,
        "pptx_basic_static_validity_audit": SHA256_B,
        "combined_calibration": SHA256_B,
    }
    document = {
        "schema_version": focused.AUTHORIZATION_SCHEMA,
        "status": "authorized",
        "execution_context": {
            "schema_version": focused.EXECUTION_CONTEXT_SCHEMA,
            "value": "focused_followup_exploratory",
        },
        "protocol_sha256": focused.protocol_sha256(protocol),
        "base_tag": "v0.13.3",
        "base_tag_object_sha": SHA1_A,
        "base_commit_sha": SHA1_B,
        "base_program_authorization_sha256": SHA256_A,
        "followup_tag": "v0.13.4",
        "followup_tag_object_sha": SHA1_B,
        "followup_commit_sha": SHA1_A,
        "issued_at": "2026-08-08T12:00:00-05:00",
        "issuer": "focused-followup-test",
        "preflight_sha256": SHA256_A,
        "run_id": RUN_ID,
        "runs_root": focused.FOCUSED_RUNS_ROOT_RELATIVE,
        "host_fingerprint": {"host": "test-host"},
        "runtime_fingerprint": {
            "runtime": "test-runtime", "fingerprint_sha256": SHA256_C,
        },
        "model_digests": {"2b": SHA256_A, "4b": model_digest, "9b": SHA256_C},
        "validated_outcomes_sha256": SHA256_A,
        "tool_schema_sha256": SHA256_A,
        "combined_calibration_sha256": protocol["selection"]["combined_calibration_artifact_sha256"],
        "shakeout_bindings": copy.deepcopy(PUBLIC_SHAKEOUT_BINDINGS),
        "source_digests": source,
        "schedule_digests": {
            block: focused._digest(schedule) for block, schedule in schedules.items()
        },
        "maximum_logical_cells": 720,
        "maximum_physical_attempts": 1440,
        "same_seed_retry_limit": 1,
        "cutoffs": copy.deepcopy(protocol["execution"]),
    }
    document["authorization_sha256"] = focused._digest(document)
    return focused.validate_authorization(document, protocol)


@pytest.fixture
def authorization(protocol, monkeypatch):
    # CI deliberately has no ignored host evidence. Tests below reconstruct
    # the tracked schedule and assert the public provenance contract; this
    # fixture isolates authorization schema/binding behavior.
    monkeypatch.setattr(
        focused,
        "_assert_focused_seed_nonreuse",
        lambda _schedules: copy.deepcopy(PUBLIC_SHAKEOUT_BINDINGS),
    )
    return _authorization(protocol)


def _resign(document):
    document["authorization_sha256"] = focused._digest({
        key: value for key, value in document.items() if key != "authorization_sha256"
    })
    return document


def _record(success, calls=4):
    return {
        "failure_origin": "none",
        "strict_success": success,
        "model_calls": calls,
        "successful_reads": 1,
        "successful_mutations": 1,
        "generated_tokens_exact": 512,
        "generated_tokens_lower_bound": None,
        "generated_tokens_upper_bound": None,
        "model_time_ms": 0,
        "wall_time_ms": 0,
    }


def _valid_attempt_record(cell, *, repeat=0, failure_origin="none", retryable=False, success=True):
    """A complete extracted-record fixture accepted by retry/seal validation."""

    return {
        "schema_version": focused.ATTEMPT_RECORD_SCHEMA,
        "logical_cell_id": cell["logical_cell_id"],
        "repeat": repeat,
        "trial_seed": cell["trial_seed"],
        "failure_origin": failure_origin,
        "retryable": retryable,
        "strict_success": success if failure_origin in ("none", "model") else None,
        "evidence_sha256": SHA256_A,
        "grade_record_sha256": SHA256_B,
        "marker_last_verified": True,
        "model_calls": 4,
        "successful_reads": 1,
        "successful_mutations": 1,
        "generated_tokens_exact": 512,
        "generated_tokens_lower_bound": None,
        "generated_tokens_upper_bound": None,
        "model_time_ms": 0,
        "wall_time_ms": 0,
    }


def _key_for_real_schedule_cell(instance, cell, authorization, repeat=0):
    """Build exactly the frozen producer key, not a coordinate lookalike."""

    expected = focused._expected_attempt_key(instance, cell, authorization, repeat)
    return AttemptKey.from_dict(expected)


def _write_real_committed_success(writer):
    """Write the minimal valid marker-last evidence payload without a model call."""

    writer.write_json("initial-state.json", {
        "schema_version": "brick.evidence-state/1",
        "state_kind": "initial",
        "payload": {},
    })
    writer.write_json("final-state.json", {
        "schema_version": "brick.evidence-state/1",
        "state_kind": "final",
        "payload": {},
    })
    writer.write_json("result.json", {
        "schema_version": "brick.evidence-result/1",
        "execution_status": "done",
        "tool_status": "clean",
        "failure_origin": "none",
        "failure": None,
        "metrics": {"model_calls": 1, "generated_tokens": 1},
        "diagnostics": {"ledger": {"generated_tokens_exact": True}},
    })
    writer.write_json("grade.json", {
        "schema_version": "brick.evidence-grade/1",
        "grader_status": "graded",
        "candidate_decision": True,
        "diagnostics": [],
    })
    writer.write_json("actions.json", {
        "schema_version": "brick.evidence-actions/1",
        "actions": [],
    })
    writer.write_bytes("transcript.md", b"# focused model-free test\n")
    writer.write_bytes(
        "memory-delta.jsonl",
        b'{"delta":[],"schema_version":"brick.memory-delta/1"}\n',
    )


def _populate_real_block(store, schedule, authorization):
    """Commit every scheduled B1a cell using real EvidenceStore transactions."""

    instances = focused._instances_by_id()
    for cell in schedule["records"]:
        resolution = store.execute_or_resume(
            _key_for_real_schedule_cell(instances[cell["instance_id"]], cell, authorization),
            _write_real_committed_success,
        )
        assert resolution.state == "committed"


def _analysis_rows(values, trial_index=0):
    """Return minimal paired rows accepted by the pure analyzer."""

    rows = []
    for family, pairs in values.items():
        for index, (native, harness) in enumerate(pairs):
            instance_id = "%s-%02d" % (family, index)
            for condition, success in (("native_tools", native), ("harness_full", harness)):
                rows.append((
                    _record(success, calls=18 if condition == "harness_full" and index == 0 else 4),
                    {
                        "family": family,
                        "instance_id": instance_id,
                        "condition": condition,
                        "trial_index": trial_index,
                    },
                ))
    return rows


def _write_complete(path, payload=b"{}\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    path.with_name(path.name + ".complete").write_bytes(b"")


def _fake_block_data(block, trial_index):
    records = []
    final = {}
    for condition, success in (("native_tools", False), ("harness_full", True)):
        logical_id = "%s-%s" % (block, condition)
        cell = {
            "logical_cell_id": logical_id,
            "family": "cal_freeslot" if block != "B1b" else "pptx_from_email",
            "instance_id": "instance-" + block,
            "condition": condition,
            "trial_index": trial_index,
        }
        records.append(cell)
        final[logical_id] = _record(success)
    return ({"records": records}, [], final, {"seal_sha256": SHA256_A})


def _install_analysis_stubs(monkeypatch, authorization, runs_root, blocks):
    """Install score-free evidence-store facsimiles for analysis-control tests."""

    class Store:
        pass

    data = {
        "B1a": _fake_block_data("B1a", 0),
        "B1b": _fake_block_data("B1b", 0),
        "B2": _fake_block_data("B2", 1),
    }
    for block in blocks:
        _write_complete(focused._block_artifact_path(runs_root, authorization, block))
    monkeypatch.setattr(focused.EvidenceStore, "open_run", staticmethod(lambda *_args: Store()))
    monkeypatch.setattr(focused, "_validate_store_metadata", lambda store, _auth: store)
    monkeypatch.setattr(focused, "validate_authorized_run_union", lambda *_args: None)
    monkeypatch.setattr(
        focused,
        "load_block_seal",
        lambda auth, _root, run_id, block, _protocol=None: (
            data[block][3]
            if auth == authorization and run_id == RUN_ID and block in blocks
            else (_ for _ in ()).throw(AssertionError("unexpected block-seal lookup"))
        ),
    )
    monkeypatch.setattr(
        focused,
        "_records_for_blocks",
        lambda _store, _auth, _root, _run, requested, _protocol: {
            block: data[block] for block in requested
        },
    )
    return data


def _install_recovered_calibration_stub(monkeypatch):
    """Bind analysis tests to a score-free recovered-calibration digest."""

    document = {
        "recovered_calibration_sha256": SHA256_C,
        "analysis": {
            "interpretation": {"claim_applicable": False},
            "label": "recovered_calibration_all_11",
        },
    }
    monkeypatch.setattr(
        focused,
        "_validate_recovered_calibration",
        lambda supplied: document if supplied == document else (_ for _ in ()).throw(
            AssertionError("unexpected recovered-calibration document")
        ),
    )
    return document


def test_protocol_is_canonical_and_direction_blind(protocol):
    focused.validate_protocol(protocol)
    assert focused.protocol_sha256(protocol) == "00ad7f376d4ed0219473844a4c66d3567c1bdacecd7f1278594b97004631ea7b"
    assert protocol["selection"]["comparative_calibration_outcomes_known_when_frozen"] is True
    assert protocol["planning"]["calibration_variance_is_empirical_not_guaranteed"] is True
    assert {
        "B1_approximate_normal_zero_exclusion_probability_at_true_0_12",
        "B1a_approximate_normal_zero_exclusion_probability_at_true_0_12",
        "B2_approximate_normal_zero_exclusion_probability_at_true_0_12",
    } <= set(protocol["planning"])

    totals = PUBLIC_COMBINED_CALIBRATION_TOTALS
    ranked = sorted(
        totals,
        key=lambda family: (-(totals[family] * (32 - totals[family])), family),
    )
    assert tuple(ranked[:6]) == tuple(protocol["selection"]["ranked_selected_families"])
    assert tuple(protocol["selection"]["B1a_families"]) == (
        "cal_freeslot", "pptx_basic", "remind_msg",
    )
    assert tuple(protocol["selection"]["B1b_families"]) == (
        "pptx_from_email", "cal_brief", "xlsx_basic",
    )

    bad = copy.deepcopy(protocol)
    bad["selection"]["ranked_selected_families"][0] = "cal_add"
    with pytest.raises(focused.FocusedFollowupError):
        focused.validate_protocol(bad)


def test_exact_schedules_are_fresh_paired_balanced_and_reverse_b2(protocol):
    schedules = focused.build_schedules(MODEL_DIGEST, protocol)
    assert {block: focused._digest(schedule) for block, schedule in schedules.items()} == {
        "B1a": "d55a76eb042918e13dadb4ed7d4d3059d404f33e146d597d9abb11935924dacf",
        "B1b": "be4cb28ceef223d54e846abdfa9cc719ea151c84eca4f5f6e2df2c5389ed1d78",
        "B2": "3bceef7d51f986093ea4ce5587ecc844de7a0fe28324fe3f7043a9e2c283eb71",
    }
    assert set(schedules) == set(focused.BLOCKS)
    assert sum(schedule["logical_cell_count"] for schedule in schedules.values()) == 720
    assert all(schedule["logical_cell_count"] == 240 for schedule in schedules.values())
    assert all(schedule["maximum_physical_attempts"] == 480 for schedule in schedules.values())

    calibration_manifest = load_canonical_json(focused.CALIBRATION_MANIFEST_PATH)
    calibration_ids = {item["content"]["id"] for item in calibration_manifest["instances"]}
    calibration_schedule = build_phase_schedule(
        calibration_manifest, "calibration", MODEL_DIGEST,
    )
    development_manifest = load_canonical_json(focused._manifest_path("development"))
    shakeout_schedule = build_development_shakeout_schedule(
        development_manifest, MODEL_DIGEST,
    )
    baseline_records = calibration_schedule["records"] + shakeout_schedule["records"]
    calibration_seeds = {item["trial_seed"] for item in calibration_schedule["records"]}
    baseline_seeds = {item["trial_seed"] for item in baseline_records}
    baseline_low31 = {item["trial_seed"] & 0x7FFFFFFF for item in baseline_records}
    focused_ids = set()
    focused_seeds = set()
    for block, schedule in schedules.items():
        assert focused.validate_schedule(schedule, protocol) == schedule
        assert {cell["source_split"] for cell in schedule["records"]} <= set(focused.NON_CALIBRATION_SPLITS)
        assert not ({cell["instance_id"] for cell in schedule["records"]} & calibration_ids)
        assert not ({cell["trial_seed"] for cell in schedule["records"]} & calibration_seeds)
        focused_ids.update(cell["logical_cell_id"] for cell in schedule["records"])
        focused_seeds.update(cell["trial_seed"] for cell in schedule["records"])

        by_cluster = defaultdict(list)
        for cell in schedule["records"]:
            by_cluster[(cell["family"], cell["instance_id"])].append(cell)
        assert len(by_cluster) == 120
        for cells in by_cluster.values():
            assert len(cells) == 2
            assert {cell["condition"] for cell in cells} == set(focused.CONDITIONS)
            assert len({cell["trial_seed"] for cell in cells}) == 1
            assert {cell["order_position"] for cell in cells} == {0, 1}
            ordered = [cell["condition"] for cell in sorted(cells, key=lambda item: item["order_position"])]
            expected = (
                focused.CONDITIONS
                if cells[0]["order_stratum"] == "AB"
                else tuple(reversed(focused.CONDITIONS))
            )
            assert tuple(ordered) == expected

        for family in {cell["family"] for cell in schedule["records"]}:
            family_cells = [cell for cell in schedule["records"] if cell["family"] == family]
            assert Counter(cell["order_stratum"] for cell in family_cells) == {"AB": 40, "BA": 40}
            assert Counter(cell["source_split"] for cell in family_cells) == {
                "development": 16, "validation": 8, "sentinel": 8, "retained": 40, "adversarial": 8,
            }

    assert len(focused_ids) == 720
    assert focused_seeds.isdisjoint(calibration_seeds)
    assert focused_seeds.isdisjoint(baseline_seeds)
    assert {seed & 0x7FFFFFFF for seed in focused_seeds}.isdisjoint(baseline_low31)

    b1a = schedules["B1a"]
    b2 = schedules["B2"]
    b1a_orders = {
        (cell["family"], cell["instance_id"]): cell["order_stratum"]
        for cell in b1a["records"] if cell["condition"] == "native_tools"
    }
    b2_orders = {
        (cell["family"], cell["instance_id"]): cell["order_stratum"]
        for cell in b2["records"] if cell["condition"] == "native_tools"
    }
    assert b1a_orders.keys() == b2_orders.keys()
    assert all(b2_orders[key] != b1a_orders[key] for key in b1a_orders)
    b1_ids = {
        cell["instance_id"] for block in ("B1a", "B1b")
        for cell in schedules[block]["records"]
    }
    shakeout_ids = {cell["instance_id"] for cell in shakeout_schedule["records"]}
    assert len(b1_ids & shakeout_ids) == PUBLIC_SHAKEOUT_BINDINGS["B1_shakeout_context_overlap_clusters"]
    assert {
        (cell["family"], cell["instance_id"]): cell["trial_seed"]
        for cell in b1a["records"] if cell["condition"] == "native_tools"
    }.items().isdisjoint({
        (cell["family"], cell["instance_id"]): cell["trial_seed"]
        for cell in b2["records"] if cell["condition"] == "native_tools"
    }.items())


@pytest.mark.parametrize("field, replacement", [
    ("content_sha256", SHA256_A),
    ("trial_seed", 1),
    ("model_sha256", SHA256_A),
])
def test_schedule_tampering_fails_exact_reconstruction(protocol, field, replacement):
    schedule = copy.deepcopy(focused.build_schedule("B1a", MODEL_DIGEST, protocol))
    target = schedule if field == "model_sha256" else schedule["records"][0]
    target[field] = replacement
    with pytest.raises(focused.FocusedFollowupError, match="schedule"):
        focused.validate_schedule(schedule, protocol)


def test_authorization_digest_and_base_tag_tampering_fail_closed(protocol, authorization):
    tampered = copy.deepcopy(authorization)
    tampered["model_digests"]["4b"] = SHA256_A
    with pytest.raises(focused.FocusedFollowupError, match="digest"):
        focused.validate_authorization(tampered, protocol)

    tampered = copy.deepcopy(authorization)
    tampered["source_digests"]["implementation_sha256"] = SHA256_C
    with pytest.raises(focused.FocusedFollowupError, match="digest"):
        focused.validate_authorization(tampered, protocol)

    # Re-signing must not let an operator move the frozen tags, run identity,
    # or evidence root into a second execution universe.
    for field, replacement in (
        ("base_tag", "v0.13.2"),
        ("followup_tag", "v0.13.5"),
        ("run_id", "v0134-focused-followup-r2"),
        ("runs_root", "results-next-study/focused-v0134-focused-followup-r2"),
    ):
        tampered = copy.deepcopy(authorization)
        tampered[field] = replacement
        _resign(tampered)
        with pytest.raises(focused.FocusedFollowupError, match="authorization contract drifted"):
            focused.validate_authorization(tampered, protocol)


def test_cli_root_binding_rejects_alternate_evidence_universe(tmp_path, authorization):
    expected = focused.authorized_runs_root(authorization)
    assert focused.require_authorized_runs_root(authorization, expected) == expected
    with pytest.raises(focused.FocusedFollowupError, match="runs root differs"):
        focused.require_authorized_runs_root(authorization, tmp_path / "alternate")
    with pytest.raises(focused.FocusedFollowupError, match="sole authorization-bound run id"):
        focused.require_authorized_run_id(authorization, "v0134-focused-followup-r2")


def test_current_environment_rejects_frozen_runtime_hash_drift(monkeypatch, protocol, authorization):
    preflight = {
        "preflight_sha256": authorization["preflight_sha256"],
        "host_fingerprint": authorization["host_fingerprint"],
        "runtime_fingerprint": authorization["runtime_fingerprint"],
        "model_digests": authorization["model_digests"],
        "validated_outcomes_sha256": authorization["validated_outcomes_sha256"],
        "tool_schema_sha256": authorization["tool_schema_sha256"],
        "commit_sha": authorization["followup_commit_sha"],
    }
    monkeypatch.setattr(focused, "_validate_preflight_for_authorization", lambda value: value)
    def tag_binding(tag, _commit):
        if tag == "v0.13.3":
            return {
                "tag": tag,
                "tag_object_sha": authorization["base_tag_object_sha"],
                "commit_sha": authorization["base_commit_sha"],
            }
        return {
            "tag": tag,
            "tag_object_sha": authorization["followup_tag_object_sha"],
            "commit_sha": authorization["followup_commit_sha"],
        }
    monkeypatch.setattr(focused, "_annotated_tag_binding", tag_binding)
    def git_command(*args):
        if args == ("rev-parse", "HEAD"):
            return authorization["followup_commit_sha"]
        if args == ("status", "--porcelain", "--untracked-files=all"):
            return ""
        raise AssertionError("unexpected git command: %r" % (args,))
    monkeypatch.setattr(focused, "_git", git_command)
    monkeypatch.setattr(
        focused,
        "_load_base_program_authorization",
        lambda: {
            "authorization_sha256": authorization["base_program_authorization_sha256"],
            "tag": authorization["base_tag"],
            "tag_object_sha": authorization["base_tag_object_sha"],
            "commit_sha": authorization["base_commit_sha"],
            "model_digests": authorization["model_digests"],
            "runtime_fingerprint": authorization["runtime_fingerprint"],
        },
    )
    drifted_source = dict(authorization["source_digests"])
    drifted_source["implementation_sha256"] = SHA256_C
    monkeypatch.setattr(focused, "_source_digests", lambda _path: drifted_source)
    with pytest.raises(focused.FocusedFollowupError, match="source binding drifted"):
        focused.validate_current_environment(
            authorization,
            preflight=preflight,
            supervisor_path="ignored",
            protocol=protocol,
            preflight_provider=lambda: preflight,
        )


def test_block_seal_binds_authorization_schedule_and_run(protocol, authorization):
    schedule = focused.build_schedule("B1a", authorization["model_digests"]["4b"], protocol)
    document = {
        "schema_version": focused.BLOCK_SEAL_SCHEMA,
        "status": "sealed_complete_valid",
        "authorization_sha256": authorization["authorization_sha256"],
        "schedule_sha256": focused._digest(schedule),
        "run_id": RUN_ID,
        "run_sha256": SHA256_A,
        "block": "B1a",
        "logical_cells_expected": 240,
        "logical_cells_complete": 240,
        "physical_attempts": 240,
        "instrument_invalid_cells": 0,
        "scores_exposed": False,
        "block_started_at": "2026-08-08T12:00:00-05:00",
        "block_finished_at": "2026-08-08T12:01:00-05:00",
        "block_elapsed_ms": 60_000,
        "attempt_records_sha256": SHA256_B,
    }
    document["seal_sha256"] = focused._digest(document)
    assert focused._validate_block_seal(document, authorization, schedule, RUN_ID) == document

    for field, value in (
        ("authorization_sha256", SHA256_C),
        ("schedule_sha256", SHA256_C),
        ("run_id", "wrong-run"),
    ):
        tampered = copy.deepcopy(document)
        tampered[field] = value
        tampered["seal_sha256"] = focused._digest({key: item for key, item in tampered.items() if key != "seal_sha256"})
        with pytest.raises(focused.FocusedFollowupError):
            focused._validate_block_seal(tampered, authorization, schedule, RUN_ID)


def test_real_marker_last_block_lifecycle_and_re_signed_seal_tampering(tmp_path, protocol, authorization):
    """Exercise real store commit/resume/extract/seal/reload without inference."""

    runs_root = tmp_path / "r"
    store = focused._open_or_create_store(runs_root, RUN_ID, authorization)
    schedule = focused.build_schedule("B1a", MODEL_DIGEST, protocol)
    _populate_real_block(store, schedule, authorization)

    # A second execution must reuse the immutable committed record.
    first_cell = schedule["records"][0]
    instance = focused._instances_by_id()[first_cell["instance_id"]]
    resumed = store.execute_or_resume(
        _key_for_real_schedule_cell(instance, first_cell, authorization),
        lambda _writer: (_ for _ in ()).throw(AssertionError("producer reran")),
    )
    assert resumed.state == "committed"
    assert resumed.producer_called is False

    extracted = focused.extract_block_attempts(store, schedule, authorization)
    assert len(extracted) == 240
    assert focused.validate_authorized_run_union(store, authorization, protocol) == 240
    focused._load_or_publish_block_start(
        authorization, runs_root, RUN_ID, "B1a", "2026-08-08T12:00:00-05:00", protocol,
    )

    seal = focused.seal_block(
        authorization, runs_root, RUN_ID, "B1a", protocol=protocol,
    )
    reloaded = focused.load_block_seal(authorization, runs_root, RUN_ID, "B1a", protocol)
    assert reloaded == seal

    # Re-signing an edited seal cannot defeat re-extraction from committed evidence.
    forged = copy.deepcopy(seal)
    forged["physical_attempts"] = 241
    forged["seal_sha256"] = focused._digest({
        key: value for key, value in forged.items() if key != "seal_sha256"
    })
    path = focused._block_artifact_path(runs_root, authorization, "B1a")
    path.write_bytes(focused.canonical_json_bytes(forged, newline=True, allow_float=False))
    with pytest.raises(focused.FocusedFollowupError, match="physical-attempt count drifted"):
        focused.load_block_seal(authorization, runs_root, RUN_ID, "B1a", protocol)


@pytest.mark.parametrize("mutate", [
    lambda key: key.__setitem__("grader_version", "office-strict-grader/3.0.1"),
    lambda key: key["condition"].__setitem__("mechanism_sha256", SHA256_A),
    lambda key: key.__setitem__("tool_schema_sha256", SHA256_B),
    lambda key: key["opportunity_budget"].__setitem__("model_calls", 17),
    lambda key: key["model"].__setitem__("tag", "alternate-local-model"),
    lambda key: key["domain"].__setitem__("content_sha256", SHA256_A),
])
def test_full_attempt_key_identity_rejects_coordinate_lookalikes(
    monkeypatch, protocol, authorization, mutate,
):
    """Every model-facing AttemptKey field is provenance, not decoration."""

    schedule = focused.build_schedule("B1a", MODEL_DIGEST, protocol)
    cell = schedule["records"][0]
    instance = focused._instances_by_id()[cell["instance_id"]]
    expected = focused._expected_attempt_key(instance, cell, authorization, 0)
    lookalike = copy.deepcopy(expected)
    mutate(lookalike)
    semantic = {
        "key": AttemptKey.from_dict(lookalike),
        "result": {
            "failure_origin": "none", "failure": None,
            "metrics": {"model_calls": 0, "generated_tokens": 0},
            "diagnostics": {"ledger": {"generated_tokens_exact": True}},
        },
        "grade": {"grader_status": "graded", "candidate_decision": True},
        "actions": {"actions": []},
    }
    monkeypatch.setattr(focused, "validate_committed", lambda *_args, **_kwargs: {"semantic": semantic})
    store = type("Store", (), {
        "attempts_dir": Path("."), "run_id": RUN_ID, "run_sha256": SHA256_A,
    })()
    committed = {
        "attempt_key": lookalike,
        "logical_hash": SHA256_A,
        "physical_uuid": "00000000-0000-4000-8000-000000000000",
        "grade": {},
    }
    coordinate = (cell["instance_id"], cell["condition"], cell["trial_seed"], cell["trial_index"])
    with pytest.raises(focused.FocusedFollowupError, match="AttemptKey differs"):
        focused._attempt_record_from_committed(
            committed, store, {coordinate: cell}, {cell["logical_cell_id"]: cell},
            authorization, {cell["instance_id"]: instance},
        )


def test_full_model_free_lifecycle_rehearses_all_blocks_analysis_report_and_closure(
    monkeypatch, tmp_path, protocol, authorization,
):
    """Exercise the actual score-masked follow-up lifecycle without a model call.

    The rehearsal uses real marker-last attempt evidence for all 720 scheduled
    logical cells, then performs the actual 50,000-replicate analysis, B2
    two-trial join, canonical publication, report rebuild, and post-analysis
    execution closure.  Every synthetic committed outcome is a strict success;
    the asserted result is pipeline integrity, not an efficacy fixture.
    """

    # Evidence attempt directories intentionally include two cryptographic
    # identifiers. Prefix the pytest-owned root only on Windows so this
    # end-to-end rehearsal works under a long user profile and Linux CI alike.
    runs_root = tmp_path / "runs"
    if focused.os.name == "nt":
        runs_root = Path("\\\\?\\" + str(runs_root.resolve()))
    # The smaller real marker-last test separately exercises durable fsync and
    # parent-directory synchronization. This 720-cell rehearsal keeps the
    # same EvidenceStore files, complete markers, reopen/validation path, and
    # analysis pipeline, but avoids thousands of Windows durability flushes
    # that otherwise make clean CI time out before semantic verification.
    monkeypatch.setattr(evidence_module.os, "fsync", lambda _descriptor: None)
    monkeypatch.setattr(evidence_module, "_sync_parent", lambda _path: None)
    # ``execute_or_resume`` normally rebuilds the whole generated projection
    # after every committed physical attempt.  That is deliberately durable
    # production behaviour, and the smaller marker-last lifecycle test covers
    # it directly.  Rebuilding after every one of 720 synthetic commits would
    # scan 1 + 2 + ... + 720 attempt directories here, however, making this
    # otherwise model-free rehearsal exceed the CI time limit.  Keep the
    # complete real resolve/begin/write/marker-last transaction for each cell,
    # then restore the genuine projector before a full 720-record reopen.
    raw_rebuild_results = evidence_module.RunSession.rebuild_results

    def deferred_projection(self, deadline_seconds=30.0):
        self._require_active()
        return self.store.run_dir / evidence_module.RESULTS

    monkeypatch.setattr(
        evidence_module.RunSession, "rebuild_results", deferred_projection,
    )
    # Re-deriving analysis and report legitimately revisits the same immutable
    # 720 marker-last directories. Validate each unique candidate/run binding
    # once with the real verifier, then return a deep copy on later visits.
    # The extractor still exact-compares the returned semantic AttemptKey to
    # the freshly reconstructed schedule key on every visit, so a cached
    # candidate cannot cross a different expected identity or run binding.
    # The focused extractor imports the validator, while EvidenceStore uses
    # its module-local reference.  Patch both to one cache.  A generic
    # EvidenceStore projection has no caller-provided expected key, so it may
    # reuse a candidate only after that same path/run has been validated once
    # with an exact reconstructed AttemptKey.  A bound call may reuse only a
    # matching semantic-key digest; a mismatch returns to the real validator.
    # Thus the test avoids repeated byte-identical validations without ever
    # allowing an unbound scan to establish an identity for a later bound one.
    raw_validate_committed = evidence_module.validate_committed
    committed_validation_cache = {}
    real_validation_keys = []
    unbound_first_calls = []

    def cached_validate_committed(candidate, *args, **kwargs):
        expected_run = kwargs.get("expected_run")
        expected_key = kwargs.get("expected_key")
        if not isinstance(expected_run, dict):
            return raw_validate_committed(candidate, *args, **kwargs)
        cache_key = (
            str(Path(candidate).resolve()),
            focused._digest(expected_run),
        )
        if expected_key is None:
            cached = committed_validation_cache.get(cache_key)
            if cached is not None:
                return copy.deepcopy(cached["validated"])
            # An unbound first read is still fully validated by the original
            # function, but it is deliberately not cache-seeding evidence for
            # a later expected AttemptKey.
            unbound_first_calls.append(cache_key)
            return raw_validate_committed(candidate, *args, **kwargs)
        if not isinstance(expected_key, AttemptKey):
            return raw_validate_committed(candidate, *args, **kwargs)
        expected_key_digest = focused._digest(expected_key.to_dict())
        cached = committed_validation_cache.get(cache_key)
        if cached is not None and cached["semantic_key_sha256"] == expected_key_digest:
            return copy.deepcopy(cached["validated"])
        validated = raw_validate_committed(candidate, *args, **kwargs)
        # Cache only a successful exact-key validation.  A failed mismatch
        # propagates before this point and never alters the cache.
        committed_validation_cache[cache_key] = {
            "semantic_key_sha256": expected_key_digest,
            "validated": copy.deepcopy(validated),
        }
        if cached is None:
            real_validation_keys.append(cache_key)
        return copy.deepcopy(validated)

    monkeypatch.setattr(focused, "validate_committed", cached_validate_committed)
    monkeypatch.setattr(
        evidence_module, "validate_committed", cached_validate_committed,
    )
    # ``validate_analysis`` and ``validate_report`` intentionally rebuild the
    # same deterministic 50,000-draw B1/B2 intervals. Memoize only within
    # this end-to-end rehearsal: each distinct production label/shape still
    # executes the real bootstrap once, while later evidence rederivations
    # receive a deep copy of that exact result rather than burning CI time on
    # byte-for-byte identical calculations.
    raw_bootstrap = focused._bootstrap_interval
    bootstrap_cache = {}

    def cached_bootstrap(family_differences, protocol_digest_value, analysis_label, replicates=50000):
        cache_key = (
            tuple((family, tuple(values)) for family, values in sorted(family_differences.items())),
            protocol_digest_value, analysis_label, replicates,
        )
        if cache_key not in bootstrap_cache:
            bootstrap_cache[cache_key] = raw_bootstrap(
                family_differences, protocol_digest_value, analysis_label, replicates,
            )
        return copy.deepcopy(bootstrap_cache[cache_key])

    monkeypatch.setattr(focused, "_bootstrap_interval", cached_bootstrap)
    store = focused._open_or_create_store(runs_root, RUN_ID, authorization)
    schedules = {
        block: focused.build_schedule(block, MODEL_DIGEST, protocol)
        for block in focused.BLOCKS
    }
    starts = {
        "B1a": "2026-08-08T12:00:00-05:00",
        "B1b": "2026-08-08T12:30:00-05:00",
        "B2": "2026-08-08T13:00:00-05:00",
    }
    finish_times = iter((
        "2026-08-08T12:10:00-05:00",
        "2026-08-08T12:40:00-05:00",
        "2026-08-08T13:10:00-05:00",
    ))
    monkeypatch.setattr(focused, "_utcnow", lambda: next(finish_times))
    seals = {}
    for block in focused.BLOCKS:
        focused._load_or_publish_block_start(
            authorization, runs_root, RUN_ID, block, starts[block], protocol,
        )
        _populate_real_block(store, schedules[block], authorization)
        # Restore the real projector before every marker-last block seal.  In
        # particular, the final B2 reopen proves that all 720 committed
        # directories can be recovered into one genuine projection.
        monkeypatch.setattr(
            evidence_module.RunSession, "rebuild_results", raw_rebuild_results,
        )
        if block == "B2":
            assert len(store.read_committed()["records"]) == 720
        seals[block] = focused.seal_block(
            authorization, runs_root, RUN_ID, block, protocol=protocol,
        )
        assert focused.validate_block_seal(
            authorization, runs_root, RUN_ID, block, protocol,
        ) == seals[block]
        if block != "B2":
            monkeypatch.setattr(
                evidence_module.RunSession, "rebuild_results", deferred_projection,
            )

    assert focused.validate_authorized_run_union(store, authorization, protocol) == 720
    # The full calibration archive is intentionally ignored in clean CI. A
    # separate real-evidence golden validates it locally; here we bind a
    # canonical nonclaiming context so the entire focused lifecycle remains
    # reproducible from this test's temporary EvidenceStore alone.
    recovered = _install_recovered_calibration_stub(monkeypatch)
    analysis = focused.analyze_followup(
        authorization, runs_root, RUN_ID, analyzed_at="2026-08-08T15:31:00-05:00",
        protocol=protocol, recovered_calibration=recovered,
    )
    assert analysis["status"] == "sealed_complete"
    assert analysis["terminal_disposition"] == {
        "B1": "sealed_complete", "B2": "sealed_complete_secondary_only",
    }
    assert analysis["secondary_B2"]["status"] == "sealed_complete_secondary_only"
    assert analysis["primary"]["claim"] == "no_directional_superiority_claim"
    assert {key[2] for key in bootstrap_cache} == {
        "B1", "B2_two_trial", "B2_trial_0_descriptive", "B2_trial_1_descriptive",
    }
    assert {key[3] for key in bootstrap_cache} == {50_000}
    assert focused.validate_analysis(
        authorization, analysis, runs_root, RUN_ID, recovered, protocol,
    ) == analysis
    focused._publish_canonical_analysis(authorization, runs_root, analysis)

    report = focused.build_report(
        authorization, analysis, runs_root, RUN_ID, recovered,
        reported_at="2026-08-08T15:32:00-05:00", protocol=protocol,
    )
    focused._publish_canonical_report(authorization, runs_root, report)
    assert focused.validate_report(
        authorization, report, analysis, runs_root, RUN_ID, recovered, protocol,
    ) == report
    assert len(committed_validation_cache) == 720
    assert len(real_validation_keys) == 720
    assert not unbound_first_calls
    assert focused._analysis_artifact_path(runs_root, authorization).with_name(
        "analysis.json.complete"
    ).is_file()
    assert focused._report_artifact_path(runs_root, authorization).with_name(
        "study-report.json.complete"
    ).is_file()

    with pytest.raises(focused.FocusedFollowupError, match="already published"):
        focused.run_block(
            authorization, runs_root, RUN_ID, "B1a", "scripts/run-focused-followup.ps1",
            now="2026-08-08T15:33:00-05:00", protocol=protocol,
        )


def test_authorized_union_rejects_foreign_duplicate_and_over_ceiling_evidence(monkeypatch, protocol, authorization):
    """A run may contain only unique physical attempts from the 720-cell union."""

    class ProjectionStore:
        run_id = RUN_ID
        run_document = {"metadata": focused._run_metadata(authorization)}

        def __init__(self, records):
            self._records = records

        def read_committed(self):
            return {"records": self._records}

    foreign = ProjectionStore([{}])
    monkeypatch.setattr(focused, "_attempt_record_from_committed", lambda *_args: None)
    with pytest.raises(focused.FocusedFollowupError, match="foreign attempt"):
        focused.validate_authorized_run_union(foreign, authorization, protocol)

    over_ceiling = ProjectionStore([{}] * (authorization["maximum_physical_attempts"] + 1))
    with pytest.raises(focused.FocusedFollowupError, match="physical ceiling"):
        focused.validate_authorized_run_union(over_ceiling, authorization, protocol)

    cell = focused.build_schedule("B1a", MODEL_DIGEST, protocol)["records"][0]
    duplicate = ProjectionStore([{}, {}])
    monkeypatch.setattr(
        focused,
        "_attempt_record_from_committed",
        lambda *_args: _valid_attempt_record(cell),
    )
    with pytest.raises(focused.FocusedFollowupError, match="physical attempt is duplicated"):
        focused.validate_authorized_run_union(duplicate, authorization, protocol)


def test_authorization_allows_exactly_its_bound_run_id(tmp_path, authorization):
    runs_root = tmp_path / "r"
    with pytest.raises(focused.FocusedFollowupError, match="run id differs"):
        focused._open_or_create_store(runs_root, "second-focused-run", authorization)
    assert not runs_root.exists()


def test_retry_requires_one_eligible_environment_first_attempt_and_attestation(tmp_path, protocol, authorization):
    """A physical retry is a same-seed recovery, never a second model draw."""

    schedule = focused.build_schedule("B1a", MODEL_DIGEST, protocol)
    cell = schedule["records"][0]
    model_first = _valid_attempt_record(cell, failure_origin="model", retryable=False)
    model_second = _valid_attempt_record(cell, repeat=1, failure_origin="none", retryable=False)
    with pytest.raises(focused.FocusedFollowupError, match="ineligible retry"):
        focused._final_attempts(schedule, [model_first, model_second])

    environment_first = _valid_attempt_record(
        cell, failure_origin="environment", retryable=True,
    )
    final, missing, invalid = focused._final_attempts(
        schedule, [environment_first, model_second],
    )
    assert final[cell["logical_cell_id"]] == model_second
    assert cell["logical_cell_id"] not in invalid
    assert len(missing) == schedule["logical_cell_count"] - 1

    runs_root = tmp_path / "r"
    with pytest.raises(focused.FocusedFollowupError, match="recovery attestation marker-last artifact is missing"):
        focused._final_attempts(
            schedule, [environment_first, model_second], authorization, runs_root, RUN_ID,
        )
    attestation = focused._recovery_document(
        authorization, environment_first, "2026-08-08T12:00:00-05:00",
    )
    attestation_path = focused._recovery_artifact_path(
        runs_root, authorization, RUN_ID, cell["logical_cell_id"],
    )
    attestation_path.parent.mkdir(parents=True, exist_ok=True)
    focused._publish_marker_last(attestation_path, attestation)
    final, _missing, invalid = focused._final_attempts(
        schedule, [environment_first, model_second], authorization, runs_root, RUN_ID,
    )
    assert final[cell["logical_cell_id"]] == model_second
    assert not invalid


def test_claim_boundaries_sign_reversal_bootstrap_digest_and_order_invariance(protocol):
    assert focused._claim(Fraction(12, 100), Fraction(1, 100), Fraction(1, 4), protocol) == "harness_superiority"
    assert focused._claim(Fraction(12, 100), Fraction(0, 1), Fraction(1, 4), protocol) == "no_directional_superiority_claim"
    assert focused._claim(Fraction(11, 100), Fraction(1, 100), Fraction(1, 4), protocol) == "no_directional_superiority_claim"
    assert focused._claim(Fraction(-12, 100), Fraction(-1, 4), Fraction(-1, 100), protocol) == "native_superiority"
    assert focused._claim(Fraction(0, 1), Fraction(-1, 10), Fraction(1, 10), protocol) == "no_directional_superiority_claim"

    signs = [Fraction(1), Fraction(1), Fraction(-1), Fraction(0)]
    assert focused._sign_flip(signs)["two_sided_p"] == focused._sign_flip([-value for value in signs])["two_sided_p"]

    differences = {
        "alpha": [Fraction(-1), Fraction(0), Fraction(1)],
        "beta": [Fraction(1), Fraction(1), Fraction(-1)],
    }
    bootstrap = focused._bootstrap_interval(
        differences, focused.protocol_sha256(protocol), "golden", replicates=100,
    )
    reversed_bootstrap = focused._bootstrap_interval(
        dict(reversed(tuple(differences.items()))), focused.protocol_sha256(protocol), "golden", replicates=100,
    )
    assert bootstrap == reversed_bootstrap
    assert bootstrap["first_100_index_vectors_sha256"] == "fcbc1fb2db8cac50f8c03597fe64f8545a8d8af2a99ec8ade201087b7f08240d"

    # Production labels and population shapes are independently frozen. The
    # index vectors do not depend on outcomes, so this catches accidental
    # label/population drift before the 50,000-draw headline analysis runs.
    b1_differences = {
        family: [Fraction(((family_index * 3 + index) % 5) - 2, 2) for index in range(40)]
        for family_index, family in enumerate(protocol["selection"]["ranked_selected_families"])
    }
    b2_differences = {
        family: [Fraction(((family_index * 2 + index) % 5) - 2, 2) for index in range(40)]
        for family_index, family in enumerate(protocol["selection"]["B1a_families"])
    }
    b1_bootstrap = focused._bootstrap_interval(
        b1_differences, focused.protocol_sha256(protocol), "B1", replicates=100,
    )
    b2_bootstrap = focused._bootstrap_interval(
        b2_differences, focused.protocol_sha256(protocol), "B2_two_trial", replicates=100,
    )
    assert b1_bootstrap["first_100_index_vectors_sha256"] == (
        "dd7b1dc702beada0f5548f22bf8f74648990feb134551207f3a5cc2de8f38ebd"
    )
    assert b2_bootstrap["first_100_index_vectors_sha256"] == (
        "70fcd0e2e6668e9021ecfc8b64c0d9d45f09235f8dea14b8a82d0da3c31041c2"
    )
    b2_sign_reversed = focused._bootstrap_interval(
        {family: [-value for value in values] for family, values in b2_differences.items()},
        focused.protocol_sha256(protocol), "B2_two_trial", replicates=100,
    )
    assert b2_sign_reversed["lower"] == -b2_bootstrap["upper"]
    assert b2_sign_reversed["upper"] == -b2_bootstrap["lower"]
    assert b2_sign_reversed["first_100_index_vectors_sha256"] == b2_bootstrap["first_100_index_vectors_sha256"]

    rows = _analysis_rows({
        "alpha": [(False, True), (True, True)],
        "beta": [(True, False), (False, True)],
    })
    forward = focused._analyze_paired_records(rows, "order-invariance", protocol, (0,))
    reverse = focused._analyze_paired_records(list(reversed(rows)), "order-invariance", protocol, (0,))
    assert forward == reverse


def test_constant_stratified_bootstrap_shortcut_is_exact_and_auditable(monkeypatch, protocol):
    """The degenerate fast path must equal the original draw-by-draw algorithm."""

    def slow_reference(family_differences, label, replicates):
        families = sorted(family_differences)
        first_hundred = []
        values = []
        for replicate in range(replicates):
            family_means = []
            vector = []
            for family in families:
                differences = family_differences[family]
                selected = [
                    focused._seed_index(
                        focused.protocol_sha256(protocol), label, replicate, family, draw, len(differences),
                    )
                    for draw in range(len(differences))
                ]
                if replicate < 100:
                    vector.append({"family": family, "indices": selected})
                family_means.append(sum(
                    (differences[index] for index in selected), Fraction(0, 1),
                ) / len(selected))
            if replicate < 100:
                first_hundred.append(vector)
            values.append(sum(family_means, Fraction(0, 1)) / len(family_means))
        values.sort()
        return {
            "replicates": replicates,
            "sampling": "exact-uniform SHA-256 rejection sampling",
            "interval": "two-sided percentile nearest-rank 0.025 and 0.975",
            "lower": values[(25 * replicates + 999) // 1000 - 1],
            "upper": values[(975 * replicates + 999) // 1000 - 1],
            "first_100_index_vectors_sha256": focused._digest(first_hundred),
        }

    constant = {
        "alpha": [Fraction(1, 3)] * 4,
        "beta": [Fraction(-1, 4)] * 3,
        "gamma": [Fraction(7, 10)] * 5,
    }
    for replicates in (1, 99, 100, 101):
        actual = focused._bootstrap_interval(
            constant, focused.protocol_sha256(protocol), "constant-fixture", replicates,
        )
        assert actual == slow_reference(constant, "constant-fixture", replicates)

    reversed_constant = {family: [-value for value in values] for family, values in constant.items()}
    forward = focused._bootstrap_interval(
        constant, focused.protocol_sha256(protocol), "constant-fixture", 101,
    )
    reverse = focused._bootstrap_interval(
        reversed_constant, focused.protocol_sha256(protocol), "constant-fixture", 101,
    )
    assert reverse["lower"] == -forward["upper"]
    assert reverse["upper"] == -forward["lower"]
    assert reverse["first_100_index_vectors_sha256"] == forward["first_100_index_vectors_sha256"]

    calls = []
    raw_seed_index = focused._seed_index
    monkeypatch.setattr(
        focused, "_seed_index",
        lambda *args: (calls.append(args), raw_seed_index(*args))[1],
    )
    focused._bootstrap_interval(
        constant, focused.protocol_sha256(protocol), "constant-call-count", 101,
    )
    assert len(calls) == 100 * sum(len(values) for values in constant.values())
    with pytest.raises(focused.FocusedFollowupError, match="family has no clusters"):
        focused._bootstrap_interval(
            {"empty": []}, focused.protocol_sha256(protocol), "empty", 1,
        )


def test_full_analyzer_derives_claims_from_records_and_intervals(protocol):
    """Headline claims are derived by the full analyzer, not a caller boolean."""

    def fixed_interval(lower, upper):
        return lambda _families: {
            "replicates": 1,
            "sampling": "test fixed interval",
            "interval": "test interval",
            "lower": lower,
            "upper": upper,
            "first_100_index_vectors_sha256": SHA256_A,
        }

    positive = focused._analyze_paired_records(
        _analysis_rows({"alpha": [(False, True)], "beta": [(False, True)]}),
        "positive", protocol, (0,),
        bootstrap_builder=fixed_interval(Fraction(1, 4), Fraction(1, 1)),
    )
    assert positive["condition_success"] == {
        "native_tools": Fraction(0, 1), "harness_full": Fraction(1, 1),
    }
    assert positive["paired_effect"] == Fraction(1, 1)
    assert positive["interval"]["lower"] == Fraction(1, 4)
    assert positive["claim"] == "harness_superiority"

    negative = focused._analyze_paired_records(
        _analysis_rows({"alpha": [(True, False)], "beta": [(True, False)]}),
        "negative", protocol, (0,),
        bootstrap_builder=fixed_interval(Fraction(-1, 1), Fraction(-1, 4)),
    )
    assert negative["condition_success"] == {
        "native_tools": Fraction(1, 1), "harness_full": Fraction(0, 1),
    }
    assert negative["paired_effect"] == Fraction(-1, 1)
    assert negative["interval"]["upper"] == Fraction(-1, 4)
    assert negative["claim"] == "native_superiority"
    assert negative["sign_flip"]["two_sided_p"] == positive["sign_flip"]["two_sided_p"]

    null = focused._analyze_paired_records(
        _analysis_rows({"alpha": [(False, False)], "beta": [(True, True)]}),
        "null", protocol, (0,),
        bootstrap_builder=fixed_interval(Fraction(0, 1), Fraction(0, 1)),
    )
    assert null["paired_effect"] == Fraction(0, 1)
    assert null["interval"]["lower"] == Fraction(0, 1)
    assert null["claim"] == "no_directional_superiority_claim"

    # The threshold is inclusive, but an interval touching/crossing zero still
    # cannot issue the directional result.  Three of 25 clusters gives 0.12.
    threshold_rows = _analysis_rows({
        "alpha": [(False, True)] * 3 + [(False, False)] * 22,
    })
    threshold = focused._analyze_paired_records(
        threshold_rows, "threshold", protocol, (0,),
        bootstrap_builder=fixed_interval(Fraction(-1, 100), Fraction(1, 4)),
    )
    assert threshold["paired_effect"] == Fraction(12, 100)
    assert threshold["condition_success"]["harness_full"] == Fraction(12, 100)
    assert threshold["interval"]["lower"] == Fraction(-1, 100)
    assert threshold["claim"] == "no_directional_superiority_claim"


def test_b2_uses_b1a_and_b2_trials_not_trial_one_alone(monkeypatch, tmp_path, protocol, authorization):
    runs_root = tmp_path / "r"
    _install_analysis_stubs(monkeypatch, authorization, runs_root, ("B1a", "B1b", "B2"))
    recovered = _install_recovered_calibration_stub(monkeypatch)
    calls = []

    def fake_analyze(rows, label, _protocol, repeats):
        calls.append((label, tuple(repeats), {cell["trial_index"] for _record, cell in rows}))
        return {"label": label, "claim": "no_directional_superiority_claim"}

    monkeypatch.setattr(focused, "_analyze_paired_records", fake_analyze)
    document = focused.analyze_followup(
        authorization, runs_root, RUN_ID, protocol=protocol,
        recovered_calibration=recovered,
    )
    assert document["primary"]["label"] == "B1"
    assert document["secondary_B2"]["two_trial"]["label"] == "B2_two_trial"
    assert document["secondary_B2"]["trial_0_descriptive"]["label"] == "B2_trial_0_descriptive"
    assert document["secondary_B2"]["trial_1_descriptive"]["label"] == "B2_trial_1_descriptive"
    assert ("B2_two_trial", (0, 1), {0, 1}) in calls
    assert ("B2_trial_0_descriptive", (0,), {0}) in calls
    assert ("B2_trial_1_descriptive", (1,), {1}) in calls


def test_incomplete_primary_fallback_and_deadline_fail_closed(monkeypatch, tmp_path, protocol, authorization):
    runs_root = tmp_path / "r"
    _install_analysis_stubs(monkeypatch, authorization, runs_root, ("B1a",))
    recovered = _install_recovered_calibration_stub(monkeypatch)
    monkeypatch.setattr(
        focused,
        "_analyze_paired_records",
        lambda _rows, label, _protocol, _repeats: {"label": label},
    )
    with pytest.raises(focused.FocusedFollowupError, match="primary requires"):
        focused.analyze_followup(
            authorization, runs_root, RUN_ID, protocol=protocol,
            recovered_calibration=recovered,
        )
    with pytest.raises(focused.FocusedFollowupError, match="fallback reason is invalid"):
        focused.analyze_followup(
            authorization, runs_root, RUN_ID, allow_fallback=True,
            fallback_reason="instrument_failure", protocol=protocol,
            recovered_calibration=recovered,
        )
    _write_complete(focused._termination_artifact_path(runs_root, authorization, "B1b"))
    monkeypatch.setattr(
        focused,
        "load_termination",
        lambda *_args, **_kwargs: {"reason": "deadline", "termination_sha256": SHA256_A},
    )
    fallback = focused.analyze_followup(
        authorization, runs_root, RUN_ID, allow_fallback=True,
        fallback_reason="deadline", protocol=protocol,
        recovered_calibration=recovered,
    )
    assert fallback["primary"] is None
    assert fallback["fallback"]["used"] is True
    assert fallback["fallback"]["reason"] == "deadline"
    assert fallback["termination_artifacts"] == {"B1b": SHA256_A}
    assert fallback["terminal_disposition"]["B2"] == "not_eligible_after_B1a_fallback"


@pytest.mark.parametrize("block", ["B1b", "B2"])
def test_later_blocks_require_predecessor_seals_before_runtime(monkeypatch, tmp_path, protocol, authorization, block):
    """A missing predecessor must reject before any environment or model call."""

    def fail_if_reached(*_args, **_kwargs):
        raise AssertionError("runtime reached before sequence validation")

    monkeypatch.setattr(focused, "validate_current_environment", fail_if_reached)
    with pytest.raises(focused.FocusedFollowupError, match="marker-last artifact is missing"):
        focused.run_block(
            authorization, tmp_path / "r", RUN_ID, block,
            "scripts/run-focused-followup.ps1", now="2026-08-09T01:00:00-05:00", protocol=protocol,
        )


def test_deadline_prevents_runtime_before_block_start(monkeypatch, tmp_path, protocol, authorization):
    monkeypatch.setattr(
        focused,
        "validate_current_environment",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("runtime reached after hard stop")),
    )
    with pytest.raises(focused.FocusedFollowupError, match="hard stop"):
        focused.run_block(
            authorization, tmp_path / "r", RUN_ID, "B1a",
            "scripts/run-focused-followup.ps1", now="2026-08-10T20:00:00-05:00", protocol=protocol,
        )


def test_b2_eligibility_is_bound_to_b1b_seal_time_not_dispatch_time(monkeypatch, tmp_path, protocol, authorization):
    """A timely B1b makes B2 mandatory even if dispatch begins after 03:00."""

    monkeypatch.setattr(focused, "_require_prior_block_seals", lambda *_args: None)
    monkeypatch.setattr(
        focused,
        "load_block_seal",
        lambda *_args, **_kwargs: {"block_finished_at": "2026-08-10T03:00:00-05:00"},
    )
    monkeypatch.setattr(
        focused,
        "validate_current_environment",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("runtime reached")),
    )
    with pytest.raises(AssertionError, match="runtime reached"):
        focused.run_block(
            authorization, tmp_path / "r", RUN_ID, "B2",
            "scripts/run-focused-followup.ps1", now="2026-08-10T02:59:59-05:00", protocol=protocol,
        )
    with pytest.raises(AssertionError, match="runtime reached"):
        focused.run_block(
            authorization, tmp_path / "r", RUN_ID, "B2",
            "scripts/run-focused-followup.ps1", now="2026-08-10T03:00:01-05:00", protocol=protocol,
        )
    monkeypatch.setattr(
        focused,
        "load_block_seal",
        lambda *_args, **_kwargs: {"block_finished_at": "2026-08-10T03:00:01-05:00"},
    )
    with pytest.raises(focused.FocusedFollowupError, match="ineligible"):
        focused.run_block(
            authorization, tmp_path / "r", RUN_ID, "B2",
            "scripts/run-focused-followup.ps1", now="2026-08-10T03:00:01-05:00", protocol=protocol,
        )


def test_late_b1b_permits_only_core_derived_zero_attempt_b2_cutoff_termination(
    monkeypatch, tmp_path, protocol, authorization,
):
    """A late B1b, not the operator's dispatch clock, permits B2 omission."""

    class Store:
        run_sha256 = SHA256_A

    monkeypatch.setattr(focused.EvidenceStore, "open_run", staticmethod(lambda *_args: Store()))
    monkeypatch.setattr(focused, "_validate_store_metadata", lambda store, _auth: store)
    monkeypatch.setattr(focused, "validate_authorized_run_union", lambda *_args: None)
    monkeypatch.setattr(focused, "extract_block_attempts", lambda *_args: [])
    monkeypatch.setattr(
        focused,
        "_final_attempts",
        lambda schedule, *_args: ({}, set(range(schedule["logical_cell_count"])), []),
    )
    monkeypatch.setattr(
        focused,
        "load_block_seal",
        lambda *_args, **_kwargs: {"block_finished_at": "2026-08-10T03:00:01-05:00"},
    )

    document = focused.terminate_block(
        authorization, tmp_path / "late", RUN_ID, "B2", "B2_start_cutoff",
        terminated_at="2026-08-10T03:00:01-05:00", protocol=protocol,
    )
    assert document["reason"] == "B2_start_cutoff"
    assert document["logical_cells_complete"] == 0
    assert document["missing_cells"] == 240

    monkeypatch.setattr(
        focused,
        "load_block_seal",
        lambda *_args, **_kwargs: {"block_finished_at": "2026-08-10T03:00:00-05:00"},
    )
    with pytest.raises(focused.FocusedFollowupError, match="timely B1 sealing"):
        focused.terminate_block(
            authorization, tmp_path / "timely", RUN_ID, "B2", "B2_start_cutoff",
            terminated_at="2026-08-10T03:00:01-05:00", protocol=protocol,
        )


def test_public_cli_exposes_no_deadline_model_or_score_mutators():
    parser = focused.build_parser()
    base = [
        "run-block", "--authorization", "auth.json", "--runs-root", "runs",
        "--run-id", RUN_ID, "--block", "B1a", "--supervisor-path", "scripts/run-focused-followup.ps1",
    ]
    for forbidden in ("--cutoff", "--hard-stop", "--now", "--model", "--claim", "--score"):
        with pytest.raises(SystemExit):
            parser.parse_args(base + [forbidden, "operator-value"])
    with pytest.raises(SystemExit):
        parser.parse_args([
            "seal-block", "--authorization", "auth.json", "--runs-root", "runs",
            "--run-id", RUN_ID, "--block", "B1a",
        ])


def test_seal_only_cli_requires_fresh_environment_under_lease(monkeypatch, tmp_path, authorization):
    """Crash recovery cannot turn postflight runtime drift into a valid seal."""

    events = []

    class Lease:
        def acquire(self, digest):
            events.append(("acquire", digest))

        def release(self):
            events.append(("release",))

    args = type("Args", (), {
        "authorization": "authorization.json",
        "runs_root": str(tmp_path / "runs"),
        "run_id": RUN_ID,
        "block": "B1a",
        "supervisor_path": "scripts/run-focused-followup.ps1",
    })()
    monkeypatch.setattr(focused, "_load_published", lambda *_args: authorization)
    monkeypatch.setattr(focused, "require_authorized_runs_root", lambda _auth, root: Path(root))
    monkeypatch.setattr(focused, "BenchmarkLease", lambda: Lease())
    sealed = []
    monkeypatch.setattr(focused, "seal_block", lambda *_args, **_kwargs: sealed.append(True))
    monkeypatch.setattr(
        focused, "validate_current_environment",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            focused.FocusedFollowupError("recollected runtime drift")
        ),
    )
    with pytest.raises(focused.FocusedFollowupError, match="runtime drift"):
        focused._cli_run(args, seal_only=True)
    assert sealed == []
    assert events == [("acquire", authorization["authorization_sha256"]), ("release",)]

    events.clear()
    monkeypatch.setattr(
        focused, "validate_current_environment",
        lambda auth, preflight=None, supervisor_path=None: (
            events.append(("preflight", auth["authorization_sha256"], preflight, supervisor_path))
            or {"preflight_sha256": SHA256_A}
        ),
    )
    document = {
        "status": "sealed_complete_valid", "block": "B1a",
        "logical_cells_complete": 240, "instrument_invalid_cells": 0,
    }
    monkeypatch.setattr(focused, "seal_block", lambda *_args, **_kwargs: document)
    focused._cli_run(args, seal_only=True)
    assert events == [
        ("acquire", authorization["authorization_sha256"]),
        ("preflight", authorization["authorization_sha256"], None, "scripts/run-focused-followup.ps1"),
        ("release",),
    ]


def test_cli_rejects_alternate_root_before_environment_or_evidence(monkeypatch, tmp_path, authorization):
    args = type("Args", (), {
        "authorization": "authorization.json",
        "runs_root": str(tmp_path / "alternate-runs"),
        "run_id": RUN_ID,
        "block": "B1a",
        "supervisor_path": "scripts/run-focused-followup.ps1",
        "preflight": None,
    })()
    monkeypatch.setattr(focused, "_load_published", lambda *_args: authorization)
    monkeypatch.setattr(
        focused, "validate_current_environment",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("environment reached")),
    )
    with pytest.raises(focused.FocusedFollowupError, match="runs root differs"):
        focused._cli_run(args)


def test_analysis_cannot_expose_b1_while_b2_is_pending(monkeypatch, tmp_path, protocol, authorization):
    runs_root = tmp_path / "r"
    _install_analysis_stubs(monkeypatch, authorization, runs_root, ("B1a", "B1b"))
    recovered = _install_recovered_calibration_stub(monkeypatch)
    monkeypatch.setattr(
        focused,
        "_analyze_paired_records",
        lambda _rows, label, _protocol, _repeats: {"label": label, "claim": "harness_superiority"},
    )
    with pytest.raises(focused.FocusedFollowupError, match="sealed B2 result or terminal B2 disposition"):
        focused.analyze_followup(
            authorization, runs_root, RUN_ID, protocol=protocol,
            recovered_calibration=recovered,
        )


def test_b2_terminal_disposition_allows_primary_without_secondary_claim(monkeypatch, tmp_path, protocol, authorization):
    runs_root = tmp_path / "r"
    _install_analysis_stubs(monkeypatch, authorization, runs_root, ("B1a", "B1b"))
    recovered = _install_recovered_calibration_stub(monkeypatch)
    _write_complete(focused._termination_artifact_path(runs_root, authorization, "B2"))
    monkeypatch.setattr(
        focused,
        "load_termination",
        lambda *_args, **_kwargs: {
            "reason": "B2_start_cutoff", "termination_sha256": SHA256_A,
        },
    )
    monkeypatch.setattr(
        focused,
        "_analyze_paired_records",
        lambda _rows, label, _protocol, _repeats: {"label": label, "claim": "harness_superiority"},
    )
    document = focused.analyze_followup(
        authorization, runs_root, RUN_ID, protocol=protocol,
        recovered_calibration=recovered,
    )
    assert document["primary"]["claim"] == "harness_superiority"
    assert document["secondary_B2"] == {
        "status": "terminated_incomplete_secondary_only",
        "reason": "B2_start_cutoff",
        "may_not_issue_or_alter_primary_claim": True,
    }
    assert document["terminal_disposition"]["B2"] == "terminated_B2_start_cutoff"


def test_deadline_termination_cannot_be_operator_declared_early(monkeypatch, tmp_path, protocol, authorization):
    """A deadline termination is valid only at the authorization's hard stop."""

    class Store:
        run_sha256 = SHA256_A

    monkeypatch.setattr(focused.EvidenceStore, "open_run", staticmethod(lambda *_args: Store()))
    monkeypatch.setattr(focused, "_validate_store_metadata", lambda store, _auth: store)
    monkeypatch.setattr(focused, "validate_authorized_run_union", lambda *_args: None)
    monkeypatch.setattr(focused, "_require_prior_block_seals", lambda *_args: None)
    monkeypatch.setattr(focused, "extract_block_attempts", lambda *_args: [])
    monkeypatch.setattr(
        focused,
        "_final_attempts",
        lambda schedule, *_args: ({}, set(range(schedule["logical_cell_count"])), []),
    )
    with pytest.raises(focused.FocusedFollowupError, match="cannot precede"):
        focused.terminate_block(
            authorization, tmp_path / "r", RUN_ID, "B1b", "deadline",
            terminated_at="2026-08-10T19:59:59-05:00", protocol=protocol,
        )


def test_hard_stop_before_b1a_creates_only_authorized_empty_evidence(monkeypatch, tmp_path, protocol, authorization):
    """A never-started B1a can still seal a recovered-only deadline disposition.

    This is deliberately the sole no-evidence termination path. It creates an
    immutable run descriptor after the frozen hard stop, but no attempt record
    and therefore no prospective outcome or claim.
    """

    runs_root = tmp_path / "r"
    deadline = authorization["cutoffs"]["hard_stop"]
    document = focused.terminate_block(
        authorization, runs_root, RUN_ID, "B1a", "deadline",
        terminated_at=deadline, protocol=protocol,
    )
    assert document["reason"] == "deadline"
    assert document["logical_cells_complete"] == 0
    assert document["missing_cells"] == 240
    assert document["instrument_invalid_cells"] == 0
    assert (runs_root / RUN_ID / "run.json").is_file()
    assert focused.load_termination(
        authorization, runs_root, RUN_ID, "B1a", protocol,
    )["termination_sha256"] == document["termination_sha256"]

    with pytest.raises(Exception):
        focused.terminate_block(
            authorization, tmp_path / "other-r", RUN_ID, "B1a", "environment_failure",
            terminated_at=deadline, protocol=protocol,
        )


def test_report_has_no_caller_claim_parameter(monkeypatch, tmp_path, protocol, authorization):
    recovered = _install_recovered_calibration_stub(monkeypatch)
    analysis = {
        "schema_version": focused.ANALYSIS_SCHEMA,
        "status": "sealed_complete",
        "authorization_sha256": authorization["authorization_sha256"],
        "protocol_sha256": focused.protocol_sha256(protocol),
        "run_id": RUN_ID,
        "recovered_calibration_sha256": recovered["recovered_calibration_sha256"],
        "block_seals": {},
        "termination_artifacts": {},
        "primary": {"claim": "harness_superiority"},
        "fallback": {"used": False, "reason": None, "analysis": None},
        "secondary_B2": None,
        "terminal_disposition": {"B1": "sealed_complete", "B2": "terminated_B2_start_cutoff"},
        "limitations": [],
        "analyzed_at": "2026-08-10T20:01:00-05:00",
    }
    analysis["analysis_sha256"] = focused._digest(analysis)
    with pytest.raises(TypeError):
        focused.build_report(authorization, analysis, claim="harness_superiority", protocol=protocol)
    monkeypatch.setattr(focused, "analyze_followup", lambda *_args, **_kwargs: analysis)
    report = focused.build_report(
        authorization, analysis, tmp_path / "r", RUN_ID, recovered,
        protocol=protocol,
    )
    assert report["primary"] == analysis["primary"]
    assert report["analysis_sha256"] == analysis["analysis_sha256"]


def test_recovered_legacy_bootstrap_generator_has_a_clean_checkout_golden():
    """Keep the v2.3 recovery sampler pinned without ignored run evidence."""

    differences = {
        "alpha": [Fraction(index, 8) for index in range(8)],
        "beta": [Fraction((index % 3) - 1, 2) for index in range(8)],
    }
    interval = focused._recovered_calibration_bootstrap_interval(differences, replicates=100)
    assert interval == {
        "replicates": 100,
        "sampling": "exact-uniform SHA-256 modulo 8",
        "interval": "two-sided percentile nearest-rank 0.025 and 0.975",
        "lower": Fraction(1, 128),
        "upper": Fraction(45, 128),
        "first_100_index_vectors_sha256": "5daac3ca83d37ccbb19b5243e594d8f6079af0a509502450455699020679c2d3",
    }


def test_recovered_calibration_is_evidence_rederived_and_never_claiming(protocol):
    """Local integration golden: completed calibration is re-extracted, never trusted."""

    run_document = focused.CALIBRATION_RUNS_ROOT / focused.CALIBRATION_RUN_ID / "run.json"
    if not run_document.is_file():
        pytest.skip("ignored sealed v0.13.3 calibration evidence is unavailable in clean CI")

    recovered = focused.recover_calibration("2026-08-08T12:00:00-05:00", protocol)
    assert recovered["status"] == "sealed_complete_retrospective_exploratory"
    assert recovered["exploratory_plan_sha256"] == focused._file_digest(focused.EXPLORATORY_PLAN_PATH)
    assert "claim" not in recovered["analysis"]
    assert recovered["analysis"]["interpretation"]["claim_applicable"] is False
    assert set(recovered["analysis"]["reliability_metrics"]) == set(focused.CONDITIONS)
    assert recovered["analysis"]["in_band_subset"]["families"] == [
        "cal_freeslot", "pptx_basic", "remind_msg",
    ]
    assert recovered["analysis"]["interval"]["sampling"] == "exact-uniform SHA-256 modulo 8"
    assert recovered["analysis"]["paired_effect"] == {
        "fraction": "25/176", "decimal": "0.142045454545",
    }
    assert recovered["analysis"]["condition_success"] == {
        "native_tools": {"fraction": "31/88", "decimal": "0.352272727273"},
        "harness_full": {"fraction": "87/176", "decimal": "0.494318181818"},
    }
    assert recovered["analysis"]["interval"]["lower"] == {
        "fraction": "3/44", "decimal": "0.068181818182",
    }
    assert recovered["analysis"]["interval"]["upper"] == {
        "fraction": "19/88", "decimal": "0.215909090909",
    }
    assert recovered["analysis"]["interval"]["first_100_index_vectors_sha256"] == (
        "c7795602453d0135e11ca455756dfec3cbf7769126ae1738c857af3e505de07b"
    )
    assert recovered["analysis"]["sign_flip"]["two_sided_p"] == {
        "fraction": "1548288520721/281474976710656", "decimal": "0.005500625806",
    }
    assert {
        "generated_tokens_exact_total_for_exact_attempts",
        "generated_tokens_lower_bound_total_for_bound_only_attempts",
        "generated_tokens_upper_bound_total_for_bound_only_attempts",
    } <= set(recovered["analysis"]["resource_report"]["native_tools"])

    forged = copy.deepcopy(recovered)
    forged["analysis"]["paired_effect"] = {"fraction": "0/1", "decimal": "0.000000000000"}
    forged["recovered_calibration_sha256"] = focused._digest({
        key: value for key, value in forged.items() if key != "recovered_calibration_sha256"
    })
    with pytest.raises(focused.FocusedFollowupError, match="differs from re-extracted evidence"):
        focused._validate_recovered_calibration(forged, protocol)


def test_seal_and_termination_cannot_bypass_phase_predecessors(tmp_path, protocol, authorization):
    """Crash recovery may seal a prior run, but cannot reorder phase state."""

    with pytest.raises(focused.FocusedFollowupError, match="marker-last artifact is missing"):
        focused.seal_block(authorization, tmp_path / "r", RUN_ID, "B1b", protocol)
    with pytest.raises(focused.FocusedFollowupError, match="marker-last artifact is missing"):
        focused.terminate_block(
            authorization, tmp_path / "r", RUN_ID, "B1b", "deadline",
            terminated_at="2026-08-10T20:00:00-05:00", protocol=protocol,
        )
