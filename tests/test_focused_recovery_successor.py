import copy
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import pytest

from bench import focused_recovery_successor as recovery


@pytest.fixture(scope="module")
def private_old_state():
    if not (recovery.OLD_ROOT / "authorization.json").is_file():
        pytest.skip("private immutable v0.13.5 evidence is absent in clean CI")
    return recovery._old_efficacy_state(recovery._old_topology_state())


def test_canonical_protocol_freezes_two_nonclaiming_lanes_and_exact_ceilings():
    protocol = recovery.load_protocol()
    assert protocol["execution"]["maximum_logical_cells"] == 264
    assert protocol["execution"]["maximum_physical_attempts"] == 528
    assert protocol["execution"]["hard_stop"] == "2026-08-11T11:00:00-05:00"
    assert protocol["analysis"]["pooling_headline_allowed"] is False
    assert set(protocol["execution"]["blocks"]) == set(recovery.BLOCKS)
    assert all(
        output["claim_applicable"] is False
        and output["may_issue_or_alter_claim"] is False
        for output in protocol["analysis"]["outputs"].values()
    )


def test_protocol_mutation_is_rejected():
    forged = copy.deepcopy(recovery.load_protocol())
    forged["analysis"]["pooling_headline_allowed"] = True
    with pytest.raises(recovery.FocusedRecoveryError, match="canonical freeze"):
        recovery.validate_protocol(forged)


def test_current_classifier_matches_only_exact_observed_incident_contract():
    binding = recovery._validate_classifier_semantics()
    assert binding == {
        "classifier_version": recovery.CLASSIFIER_VERSION,
        "classifier_source_sha256": recovery._file_digest(recovery.CLASSIFIER_SOURCE_PATH),
        "observed_signature_recognized": True,
        "failure_origin": "model",
        "retryable": False,
        "strict_success": False,
    }
    audit = recovery.load_canonical_json(recovery.PARSER_INCIDENT_PATH)
    assert recovery._file_digest(recovery.PARSER_INCIDENT_PATH) == (
        "a3e60793e16a8e0afc06c258ed81f0965b104601c5e801c6739bf6a6d1384195"
    )
    assert audit["schema_version"] == (
        "brick.next-study.focused-followup-b1b-parser-incident-audit/1"
    )
    assert audit["status"] == "source_proven_prospective_classifier_fix_only"
    assert audit["classifier"]["symmetric_signature_added"] == (
        "element <parameter> closed by </function>"
    )
    assert audit["classifier"]["prospective_outcome"] == {
        "failure_origin": "model",
        "failure_type": "model_output_tool_syntax_rejected",
        "retryable": False,
        "strict_success": False,
    }
    assert audit["classifier"]["implementation"]["canonical_lf_sha256"] == (
        hashlib.sha256(
            recovery.CLASSIFIER_SOURCE_PATH.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
    )


def test_private_parser_incident_attempt_result_request_join_is_exact():
    if not (recovery.OLD_ROOT / "authorization.json").is_file():
        pytest.skip("private immutable v0.13.5 evidence is absent in clean CI")
    audit = recovery._load_parser_incident()
    records = sorted(
        audit["incident_records"], key=lambda item: item["attempt_key"]["repeat"],
    )
    assert [item["attempt_key"]["repeat"] for item in records] == [0, 1]
    assert [item["attempt_key"]["instance_id"] for item in records] == [
        "v2.retained.xlsx-basic.15", "v2.retained.xlsx-basic.15",
    ]


def test_transitive_model_and_analysis_sources_are_directly_bound(monkeypatch):
    supervisor = recovery.ROOT / "scripts" / "run-focused-recovery-successor.ps1"
    expected = recovery._source_digests(supervisor)
    required = {
        "focused_followup", "focused_protocol", "generator", "strict_graders",
        "office_files", "validated_outcomes_validator", "validated_outcomes",
        "manifest_lock", "manifest_calibration", "manifest_development",
        "manifest_validation", "manifest_sentinel", "manifest_retained",
        "manifest_adversarial",
    }
    assert required <= set(expected["transitive_source_digests"])
    forged = copy.deepcopy(expected)
    forged["transitive_source_digests"]["strict_graders"] = "0" * 64
    with pytest.raises(recovery.FocusedRecoveryError, match="source binding drifted"):
        recovery._validate_source_bindings(forged, supervisor)


def test_old_root_write_guard_rejects_every_descendant(tmp_path):
    with pytest.raises(recovery.FocusedRecoveryError, match="strictly read-only"):
        recovery._assert_not_old_path(recovery.OLD_ROOT / "new.json")
    assert recovery._assert_not_old_path(tmp_path / "new.json") == (tmp_path / "new.json").resolve()


def test_public_cli_has_no_root_run_id_deadline_or_score_mutators():
    parser = recovery.build_parser()
    base = [
        "run-block", "--block", "B1b_recovery", "--supervisor-path",
        "scripts/run-focused-recovery-successor.ps1",
    ]
    for option in ("--runs-root", "--run-id", "--hard-stop", "--score", "--claim"):
        with pytest.raises(SystemExit):
            parser.parse_args(base + [option, "forged"])
    parsed = parser.parse_args(["validate", "--kind", "block", "--block", "B2_repeatability"])
    assert parsed.block == "B2_repeatability"


def test_hard_stop_boundary_is_fixed_and_checked_only_before_next_cell():
    assert recovery._hard_stop_reached("2026-08-11T10:59:59.999999-05:00") is False
    assert recovery._hard_stop_reached("2026-08-11T11:00:00-05:00") is True
    assert recovery._hard_stop_reached("2026-08-11T16:00:00Z") is True


def test_repeatability_summary_is_exact_same_context_description_only():
    rows0 = []
    rows1 = []
    outcomes = {
        ("one", "native_tools"): (False, True),
        ("one", "harness_full"): (True, True),
        ("two", "native_tools"): (True, False),
        ("two", "harness_full"): (False, False),
    }
    for instance_id in ("one", "two"):
        for condition in recovery._focused.CONDITIONS:
            before, after = outcomes[(instance_id, condition)]
            cell0 = {"family": "cal_freeslot", "instance_id": instance_id,
                     "condition": condition, "trial_index": 0}
            cell1 = dict(cell0, trial_index=1)
            rows0.append(({"strict_success": before}, cell0))
            rows1.append(({"strict_success": after}, cell1))
    summary = recovery._repeatability_summary(rows0, rows1)
    assert summary["clusters"] == 2
    assert summary["condition_transitions"]["native_tools"] == {
        "fail_to_fail": 0, "fail_to_success": 1,
        "success_to_fail": 1, "success_to_success": 0,
    }
    assert summary["exact_joint_outcome_signature_matches"] == 0
    assert summary["interpretation"].endswith("not independent replication")


def test_b2_schedule_is_byte_identical_old_object_and_recovery_is_exact_missing_subset(private_old_state):
    state = private_old_state
    b1 = recovery.build_schedule("B1b_recovery", old_state=state)
    b2 = recovery.build_schedule("B2_repeatability", old_state=state)
    assert b1["logical_cell_count"] == 24
    assert len({item["instance_id"] for item in b1["records"]}) == 12
    assert set(Counter(item["instance_id"] for item in b1["records"]).values()) == {2}
    assert {item["family"] for item in b1["records"]} == {"xlsx_basic"}
    assert b2 == state["schedules"]["B2"]
    assert recovery._digest(b2) == "3bceef7d51f986093ea4ce5587ecc844de7a0fe28324fe3f7043a9e2c283eb71"


def test_old_private_topology_is_exact_215_plus_parser_plus_24(private_old_state):
    state = private_old_state
    assert len(state["b1b_valid"]) == 215
    assert len(state["b1b_missing"]) == 24
    assert [item["repeat"] for item in state["parser_attempts"]] == [0, 1]
    assert state["parser_derived"]["failure_origin"] == "model"
    assert state["parser_derived"]["strict_success"] is False
    assert state["parser_derived"]["retryable"] is False


def test_private_old_validation_is_byte_and_mtime_read_only(monkeypatch):
    if not (recovery.OLD_ROOT / "authorization.json").is_file():
        pytest.skip("private immutable v0.13.5 evidence is absent in clean CI")
    projection = (
        recovery.OLD_ROOT / "v0135-focused-followup-r1" / "results.json"
    )
    before_tree = recovery._old_tree_manifest()
    before_bytes = projection.read_bytes()
    before_mtime = projection.stat().st_mtime_ns
    monkeypatch.setattr(
        recovery.EvidenceStore, "read_committed",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("old read_committed forbidden")),
    )
    monkeypatch.setattr(
        recovery._evidence.RunSession, "rebuild_results",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("old rebuild forbidden")),
    )
    topology = recovery._old_topology_state()
    recovery._old_efficacy_state(topology)
    assert recovery._old_tree_manifest() == before_tree
    assert projection.read_bytes() == before_bytes
    assert projection.stat().st_mtime_ns == before_mtime


def test_resume_disposition_never_skips_authorized_repeat_one_after_hard_stop():
    cell_id = "a" * 64
    retryable = [{
        "logical_cell_id": cell_id, "repeat": 0,
        "failure_origin": "environment", "retryable": True,
    }]
    assert recovery._cell_resume_disposition(retryable, cell_id) == (
        "resume_authorized_retry", None,
    )
    invalid = [dict(retryable[0], retryable=False)]
    assert recovery._cell_resume_disposition(invalid, cell_id) == (
        "terminal_invalid", "environment_failure",
    )
    assert recovery._cell_resume_disposition([], cell_id) == ("never_started", None)
    assert recovery._must_check_hard_stop_before_cell("never_started", False) is True
    assert recovery._must_check_hard_stop_before_cell("never_started", True) is False
    assert recovery._must_check_hard_stop_before_cell("resume_authorized_retry", True) is False


def test_marker_last_recovers_exact_json_only_and_rejects_marker_only(tmp_path):
    path = tmp_path / "artifact.json"
    document = {"schema_version": "fixture/1", "value": 1}
    path.write_bytes(recovery.canonical_json_bytes(document, newline=True, allow_float=False))
    recovery._publish_marker_last(path, document, validator=lambda value: value == document)
    assert path.with_name("artifact.json.complete").read_bytes() == b""
    marker_only = tmp_path / "marker-only.json"
    marker_only.with_name("marker-only.json.complete").write_bytes(b"")
    with pytest.raises(recovery.FocusedRecoveryError, match="invalid existing"):
        recovery._publish_marker_last(marker_only, document)


def test_stale_lease_recovery_is_fixed_audited_and_race_safe(monkeypatch, tmp_path):
    canonical = tmp_path / "machine" / "benchmark.lease"
    monkeypatch.setattr(recovery, "SUCCESSOR_ROOT", tmp_path / "successor")
    real_lease = recovery.BenchmarkLease
    monkeypatch.setattr(recovery, "BenchmarkLease", lambda path=None: real_lease(canonical))
    authorization = {"authorization_sha256": "a" * 64}
    assert recovery.recover_stale_lease(authorization)["status"] == "lease_absent_noop"
    lease = real_lease(canonical); lease.acquire(authorization["authorization_sha256"])
    with pytest.raises(recovery.FocusedRecoveryError, match="live or not definitively dead"):
        recovery.recover_stale_lease(authorization, dead_pid_checker=lambda _pid: False)
    document = recovery.recover_stale_lease(
        authorization, recovered_at="2026-08-10T12:00:00-05:00",
        dead_pid_checker=lambda _pid: True,
    )
    assert document["audit_published_before_unlink"] is True
    assert not canonical.exists()
    lease = real_lease(canonical); lease.acquire(authorization["authorization_sha256"])
    with pytest.raises(recovery.FocusedRecoveryError, match="corrupt or foreign"):
        recovery.recover_stale_lease(
            {"authorization_sha256": "b" * 64}, dead_pid_checker=lambda _pid: True,
        )
    lease.release()
    lease = real_lease(canonical); lease.acquire(authorization["authorization_sha256"])
    original = canonical.read_bytes()
    def race():
        canonical.write_bytes(original + b" ")
    with pytest.raises(recovery.FocusedRecoveryError, match="changed"):
        recovery.recover_stale_lease(
            authorization, recovered_at="2026-08-10T12:01:00-05:00",
            dead_pid_checker=lambda _pid: True, before_unlink=race,
        )
    assert canonical.exists()


def test_candidate_topology_counts_abandoned_prepared_and_committed_against_ceiling(monkeypatch, tmp_path):
    attempts = tmp_path / "attempts"; attempts.mkdir()
    for logical, states in (("0" * 64, ("abandoned", "committed")),
                            ("1" * 64, ("prepared",))):
        logical_dir = attempts / logical; logical_dir.mkdir()
        for index, state in enumerate(states):
            candidate = logical_dir / ("00000000-0000-0000-0000-%012d" % index)
            candidate.mkdir(); (candidate / "attempt.json").write_text("{}", encoding="utf-8")
            if state == "committed": (candidate / "COMMITTED").write_bytes(b"")
            if state == "prepared": (candidate / "PREPARED.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(recovery._focused, "_instances_by_id", lambda: {"i": {}})
    monkeypatch.setattr(
        recovery._focused, "_expected_attempt_key",
        lambda _instance, _cell, _authorization, repeat: {"repeat": repeat},
    )
    monkeypatch.setattr(
        recovery.AttemptKey, "from_dict",
        lambda value: type("Key", (), {"logical_hash": str(value["repeat"]) * 64})(),
    )
    schedule = {
        "maximum_physical_attempts": 4,
        "records": [{"logical_cell_id": "a" * 64, "instance_id": "i"}],
    }
    store = type("Store", (), {"attempts_dir": attempts})()
    with pytest.raises(recovery.FocusedRecoveryError, match="two physical candidates"):
        recovery._physical_candidate_state(store, schedule, {})


def test_terminal_inventory_requires_cell_starts_and_disposes_uncommitted_candidates(monkeypatch):
    cell = "a" * 64
    monkeypatch.setattr(recovery, "_open_store", lambda *_args: object())
    monkeypatch.setattr(recovery, "_physical_candidate_state", lambda *_args: {
        "physical_candidates": 1, "by_cell": {cell: [{"state": "abandoned"}]},
        "records": [], "candidate_records_sha256": "1" * 64,
        "state_counts": {"abandoned": 1},
    })
    monkeypatch.setattr(recovery, "_cell_start_inventory", lambda *_args: {
        "logical_cells_started": 1,
        "records": [{"logical_cell_id": cell}],
        "cell_start_records_sha256": "2" * 64,
    })
    with pytest.raises(recovery.FocusedRecoveryError, match="uncommitted candidates"):
        recovery._validate_execution_inventory({}, "B1b_recovery", {}, {}, None)
    physical, starts = recovery._validate_execution_inventory(
        {}, "B1b_recovery", {}, {}, "instrument_failure",
    )
    assert physical["state_counts"] == {"abandoned": 1}
    assert starts["logical_cells_started"] == 1


def test_bootstrap_index_vector_goldens_are_pinned_to_correct_protocol_lanes():
    dummy = {
        family: [Fraction(0, 1)] * 40
        for family in ("cal_brief", "pptx_from_email", "xlsx_basic")
    }
    generated = recovery._focused._bootstrap_interval(
        dummy, recovery.protocol_sha256(), "recovered_B1b", replicates=100,
    )["first_100_index_vectors_sha256"]
    assert generated == recovery.BOOTSTRAP_INDEX_GOLDENS["recovered_B1b"]
    assert recovery.BOOTSTRAP_INDEX_GOLDENS["B1"] == "dd7b1dc702beada0f5548f22bf8f74648990feb134551207f3a5cc2de8f38ebd"
    assert recovery.BOOTSTRAP_INDEX_GOLDENS["B2_two_trial"] == "70fcd0e2e6668e9021ecfc8b64c0d9d45f09235f8dea14b8a82d0da3c31041c2"
    assert recovery.BOOTSTRAP_INDEX_GOLDENS["B2_trial_1_descriptive"] == "e36449e15f2bf537d3c5482788e4334b02edd3d7c5da7716f85c03649b18e4d1"


def test_terminal_embargo_rejects_until_both_blocks_terminal(monkeypatch):
    protocol = recovery.load_protocol()
    authorization = {"authorization_sha256": "a" * 64}
    monkeypatch.setattr(recovery, "validate_authorization", lambda *_args, **_kwargs: authorization)
    monkeypatch.setattr(recovery, "_validate_repository_bindings", lambda *_args, **_kwargs: authorization)
    monkeypatch.setattr(recovery, "_old_topology_state", lambda *_args: {})
    monkeypatch.setattr(recovery, "_terminal", lambda *_args: (None, None))
    with pytest.raises(recovery.FocusedRecoveryError, match="both successor blocks"):
        recovery.analyze(authorization, protocol=protocol)


def test_mixed_terminal_state_reports_complete_b2_lane_only(monkeypatch):
    protocol = recovery.load_protocol()
    authorization = {
        "authorization_sha256": "a" * 64,
        "projection_rewrite_incident_sha256":
            "7df3c07b14e65c732337c11216579accffbfc105f8b0dbd4b298b3995d70d63d",
    }
    old_state = {
        "b1a_final": {}, "schedules": {"B1a": {"records": []}},
        "old": {
            "report": {"report_sha256": "b" * 64, "status": "focused_followup_complete"},
            "closed_analysis": {"analysis_sha256": "c" * 64},
        },
    }
    terminals = {
        "B1b_recovery": ("terminated", {
            "termination_sha256": "d" * 64, "status": "terminated_incomplete",
            "reason": "deadline", "logical_cells_expected": 24,
            "logical_cells_complete": 20, "missing_cells": 4,
            "instrument_invalid_cells": 0, "physical_attempts": 20,
            "candidate_state_counts": {"committed": 20}, "logical_cells_started": 20,
            "terminated_at": "2026-08-11T11:00:00-05:00",
        }),
        "B2_repeatability": ("sealed", {
            "seal_sha256": "e" * 64, "status": "sealed_complete_valid",
            "logical_cells_expected": 240, "logical_cells_complete": 240,
            "instrument_invalid_cells": 0, "physical_attempts": 240,
            "candidate_state_counts": {"committed": 240}, "logical_cells_started": 240,
            "block_finished_at": "2026-08-11T11:00:30-05:00",
        }),
    }
    monkeypatch.setattr(recovery, "validate_authorization", lambda *_args, **_kwargs: authorization)
    monkeypatch.setattr(recovery, "_validate_repository_bindings", lambda *_args, **_kwargs: authorization)
    monkeypatch.setattr(recovery, "_terminal_marker_present", lambda *_args: True)
    monkeypatch.setattr(recovery, "_old_topology_state", lambda *_args: old_state)
    monkeypatch.setattr(recovery, "_old_efficacy_state", lambda *_args: old_state)
    monkeypatch.setattr(recovery, "_terminal", lambda _a, block, *_args: terminals[block])
    monkeypatch.setattr(recovery, "build_schedule", lambda *_args, **_kwargs: {"records": []})
    monkeypatch.setattr(recovery, "_open_store", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(recovery, "_new_final", lambda *_args, **_kwargs: ([], {}, [], []))
    monkeypatch.setattr(recovery, "_rows", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        recovery, "_analyze",
        lambda _rows, label, *_args, **_kwargs: {
            "label": label,
            **({"claim": "no_directional_superiority_claim"}
               if label == "B2_trial_1_descriptive" else {}),
        },
    )
    monkeypatch.setattr(recovery, "_repeatability_summary", lambda *_args: {"clusters": 120})
    document = recovery.analyze(
        authorization, analyzed_at="2026-08-11T11:01:00-05:00", protocol=protocol,
    )
    assert document["status"] == "mixed_terminal_recovery_incomplete_repeatability_complete"
    assert document["recovered_B1b"] is None
    assert document["recovered_six_family_sensitivity"] is None
    assert document["standalone_repeatability"]["label"] == "B2_trial_1_descriptive"
    assert document["standalone_repeatability"]["claim"] is None
    assert document["standalone_repeatability"]["standalone_repeatability_criterion_result"] == "no_directional_superiority_claim"
    assert document["b1a_two_trial_secondary"]["label"] == "B2_two_trial"
    assert document["old_fallback_reference"]["unchanged"] is True


def test_b2_start_requires_any_validated_b1_terminal_before_lease(monkeypatch):
    protocol = recovery.load_protocol()
    authorization = {"authorization_sha256": "a" * 64}
    monkeypatch.setattr(recovery, "validate_authorization", lambda *_args, **_kwargs: authorization)
    monkeypatch.setattr(recovery, "_old_topology_state", lambda *_args: {})
    monkeypatch.setattr(recovery, "_terminal", lambda *_args: (None, None))
    monkeypatch.setattr(
        recovery, "BenchmarkLease",
        lambda *_args: (_ for _ in ()).throw(AssertionError("lease reached before predecessor")),
    )
    with pytest.raises(recovery.FocusedRecoveryError, match="terminal B1b recovery"):
        recovery.run_block(
            authorization, "B2_repeatability", "scripts/run-focused-recovery-successor.ps1",
            protocol=protocol,
        )


def test_termination_validator_rederives_counts_and_rejects_tamper(monkeypatch, tmp_path):
    authorization = {"authorization_sha256": "a" * 64}
    schedule = {"logical_cell_count": 2, "maximum_physical_attempts": 4, "records": []}
    store = type("Store", (), {"run_id": "run", "run_sha256": "b" * 64})()
    attempts = [{"logical_cell_id": "c" * 64}]
    final = {"c" * 64: {"failure_origin": "environment"}}
    document = {
        "schema_version": recovery.TERMINATION_SCHEMA, "status": "terminated_incomplete",
        "authorization_sha256": "a" * 64, "block": "B1b_recovery", "run_id": "run",
        "run_sha256": "b" * 64, "schedule_sha256": recovery._digest(schedule),
        "reason": "environment_failure", "logical_cells_expected": 2,
        "logical_cells_complete": 1, "missing_cells": 1, "instrument_invalid_cells": 1,
        "physical_attempts": 1, "attempt_records_sha256": recovery._digest(attempts),
        "candidate_records_sha256": "1" * 64,
        "candidate_state_counts": {"committed": 1},
        "logical_cells_started": 1, "cell_start_records_sha256": "2" * 64,
        "block_start_sha256": "f" * 64,
        "block_started_at": "2026-08-10T00:00:00-05:00",
        "terminated_at": "2026-08-10T00:01:00-05:00", "block_elapsed_ms": 60000,
        "scores_exposed": False,
    }
    document["termination_sha256"] = recovery._digest(document)
    monkeypatch.setattr(recovery, "validate_protocol", lambda value: value)
    monkeypatch.setattr(recovery, "build_schedule", lambda *_args, **_kwargs: schedule)
    monkeypatch.setattr(recovery, "_open_store", lambda *_args, **_kwargs: store)
    monkeypatch.setattr(recovery, "load_block_start", lambda *_args, **_kwargs: {
        "start_sha256": "f" * 64, "started_at": "2026-08-10T00:00:00-05:00",
    })
    monkeypatch.setattr(recovery, "_validate_execution_inventory", lambda *_args, **_kwargs: (
        {"physical_candidates": 1, "candidate_records_sha256": "1" * 64,
         "state_counts": {"committed": 1}, "by_cell": {"c" * 64: [{}]}},
        {"logical_cells_started": 1, "cell_start_records_sha256": "2" * 64},
    ))
    monkeypatch.setattr(
        recovery, "_new_final",
        lambda *_args, **_kwargs: (attempts, final, ["d" * 64], ["c" * 64]),
    )
    monkeypatch.setattr(recovery, "_artifact_path", lambda *_args: tmp_path / "termination.json")
    recovery._publish_marker_last(tmp_path / "termination.json", document)
    assert recovery.load_termination(
        authorization, "B1b_recovery", protocol={}, old_state={},
    )["logical_cells_complete"] == 1
    forged = json.loads((tmp_path / "termination.json").read_text(encoding="utf-8"))
    forged["missing_cells"] = 0
    forged["termination_sha256"] = recovery._digest({
        key: value for key, value in forged.items() if key != "termination_sha256"
    })
    (tmp_path / "termination.json").write_bytes(
        recovery.canonical_json_bytes(forged, newline=True, allow_float=False)
    )
    with pytest.raises(recovery.FocusedRecoveryError, match="exact evidence"):
        recovery.load_termination(
            authorization, "B1b_recovery", protocol={}, old_state={},
        )
