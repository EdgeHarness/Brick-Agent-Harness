import copy

import pytest

from bench import generate_next_study
from bench.next_study_program import (
    AUTHORIZATION_SCHEMA, BenchmarkLease, HOST_FINGERPRINT_SCHEMA, PHASES,
    REQUIRED_ARTIFACT_DIGESTS, RUNTIME_FINGERPRINT_SCHEMA,
    SEALED_GATE_SCHEMA, advance_program, build_authorization,
    build_fingerprint, initial_program_state, validate_authorization,
    validate_program_state,
)
from bench.next_study_readiness import build_readiness_report
from bench.next_study_review import (
    REVIEW_PROTOCOL_VERSION, STAFFING_SCHEMA, build_assignments, build_pilot,
    validate_assignments, validate_pilot,
)
from bench.next_study_review_training import verify_artifacts
from bench.next_study_runtime import (
    ATTEMPT_RECORD_SCHEMA, build_masked_grade_ledger,
    extract_attempt_records, PREFLIGHT_GATE_ARTIFACTS, PREFLIGHT_GATE_SCHEMA,
    preflight, resume_queue, unmask_primary,
)
from bench.next_study_schedule import build_descriptive_schedule, build_phase_schedule
from domains.office_demo.generators_v2 import FAMILIES
from harness.evidence import AttemptKey, EvidenceStore, canonical_json_bytes
from harness.instances import load_canonical_json, sha256_bytes


def _manifests():
    return [
        load_canonical_json(generate_next_study.DEFAULT_DIRECTORY / (split + ".json"))
        for split in (
            "development", "calibration", "validation", "sentinel",
            "retained", "adversarial",
        )
    ]


def _resource_fields():
    return {
        "model_calls": 1, "successful_reads": 0, "successful_mutations": 0,
        "generated_tokens_exact": 1, "generated_tokens_lower_bound": None,
        "generated_tokens_upper_bound": None, "model_time_ms": 1,
        "wall_time_ms": 1,
    }


def _reviewer(identifier):
    protocol = verify_artifacts()
    return {
        "reviewer_id": identifier,
        "name": "Hardening Human " + identifier,
        "identity_attested": True,
        "conflicts_attested": True,
        "availability_attested": True,
        "access_ready": True,
        "compensation_arranged": True,
        "confidentiality_attested": True,
        "no_generative_ai_attested": True,
        "no_source_access_attested": True,
        "qualification": {
            "reviewer_id": identifier,
            "submission_sha256": "1" * 64,
            "sealed_at": "2026-08-04T10:00:00Z",
            "practice_set_version": protocol["practice_version"],
            "practice_set_sha256": protocol["practice_sha256"],
            "answer_key_sha256": protocol["practice_answer_key_sha256"],
            "families": list(FAMILIES),
            "seeded_ambiguity_passed": True,
            "accepted_alternatives_passed": True,
            "score_numerator": 13,
            "score_denominator": 13,
            "minimum_score": 12,
            "case_results_sha256": "2" * 64,
            "qualification_result_sha256": "3" * 64,
            "qualified": True,
        },
    }


def _staffing():
    return {
        "schema_version": STAFFING_SCHEMA,
        "review_protocol_version": REVIEW_PROTOCOL_VERSION,
        "status": "ready",
        "active_reviewers": [_reviewer("hard-%d" % index) for index in range(4)],
        "backup_reviewers": [],
    }


def test_every_case_reverses_condition_order_on_trial_one():
    retained = _manifests()[4]
    schedule = build_phase_schedule(retained, "primary", "a" * 64)
    by_case = {}
    for record in schedule["records"]:
        by_case.setdefault(record["instance_id"], {}).setdefault(
            record["trial_index"], []
        ).append(record)
    assert len(by_case) == 220
    for trials in by_case.values():
        first = [item["condition"] for item in sorted(trials[0], key=lambda x: x["order_position"])]
        second = [item["condition"] for item in sorted(trials[1], key=lambda x: x["order_position"])]
        assert second == list(reversed(first))


def test_assignment_and_pilot_tampering_fail_canonical_validation():
    manifests = _manifests()
    staffing = _staffing()
    assignments = build_assignments(manifests, staffing)
    assert validate_assignments(assignments, manifests, staffing) == assignments
    tampered = copy.deepcopy(assignments)
    tampered["records"][0]["primary"] = tampered["records"][0]["adjudicator"]
    with pytest.raises(ValueError):
        validate_assignments(tampered, manifests, staffing)
    bindings = {"generator": "1" * 64, "handbook": "2" * 64}
    pilot = build_pilot(assignments, manifests, bindings)
    assert validate_pilot(pilot, assignments, manifests, bindings) == pilot
    changed = copy.deepcopy(pilot)
    changed["records"].reverse()
    with pytest.raises(ValueError):
        validate_pilot(changed, assignments, manifests, bindings)


def test_authorization_and_program_state_are_exact_and_history_derived():
    host = build_fingerprint(HOST_FINGERPRINT_SCHEMA, {"host": "lenovo-test"})
    runtime = build_fingerprint(RUNTIME_FINGERPRINT_SCHEMA, {"ollama": "pinned"})
    authorization = build_authorization(
        tag="v0.13.0", tag_object_sha="9" * 40, commit_sha="a" * 40,
        artifact_digests={name: "b" * 64 for name in REQUIRED_ARTIFACT_DIGESTS},
        host_fingerprint=host, runtime_fingerprint=runtime,
        schedule_digests={name: "c" * 64 for name in (
            "calibration", "sentinel", "primary", "descriptives",
        )},
        model_digests={name: "d" * 64 for name in ("2b", "4b", "9b")},
        descriptive_selection_sha256="e" * 64,
        issued_at="2026-08-05T10:00:00Z", issuer="test issuer",
    )
    assert authorization["schema_version"] == AUTHORIZATION_SCHEMA
    assert validate_authorization(authorization) == authorization
    state = initial_program_state(authorization["authorization_sha256"])
    logical_counts = {
        "calibration": 352, "sentinel": 88, "primary": 880,
        "primary_analysis": 0, "descriptives": 222, "release": 0,
    }
    for phase in PHASES:
        logical = logical_counts[phase]
        state = advance_program(state, {
            "schema_version": SEALED_GATE_SCHEMA,
            "authorization_sha256": authorization["authorization_sha256"],
            "phase": phase,
            "status": "sealed_pass",
            "logical_cells_completed": logical,
            "physical_attempts_completed": logical,
            "sealed_artifact_sha256": "f" * 64,
        })
    assert state["status"] == "complete"
    changed = copy.deepcopy(state)
    changed["logical_cells_completed"] -= 1
    with pytest.raises(ValueError):
        validate_program_state(changed)

    partial = initial_program_state(authorization["authorization_sha256"])
    for phase in PHASES[:4]:
        logical = logical_counts[phase]
        partial = advance_program(partial, {
            "schema_version": SEALED_GATE_SCHEMA,
            "authorization_sha256": authorization["authorization_sha256"],
            "phase": phase, "status": "sealed_pass",
            "logical_cells_completed": logical,
            "physical_attempts_completed": logical,
            "sealed_artifact_sha256": "f" * 64,
        })
    with pytest.raises(ValueError, match="logical-cell count"):
        advance_program(partial, {
            "schema_version": SEALED_GATE_SCHEMA,
            "authorization_sha256": authorization["authorization_sha256"],
            "phase": "descriptives", "status": "sealed_pass",
            "logical_cells_completed": 0, "physical_attempts_completed": 0,
            "sealed_artifact_sha256": "f" * 64,
        })
    assert advance_program(partial, {
        "schema_version": SEALED_GATE_SCHEMA,
        "authorization_sha256": authorization["authorization_sha256"],
        "phase": "descriptives", "status": "sealed_pass",
        "logical_cells_completed": 134, "physical_attempts_completed": 134,
        "sealed_artifact_sha256": "f" * 64,
    })["current_phase"] == "release"


def test_orphan_retry_and_masked_identity_tampering_fail_closed():
    retained = _manifests()[4]
    schedule = build_phase_schedule(retained, "primary", "f" * 64)
    cell = schedule["records"][0]
    orphan = [{
        "schema_version": ATTEMPT_RECORD_SCHEMA,
        "logical_cell_id": cell["logical_cell_id"], "repeat": 1,
        "trial_seed": cell["trial_seed"], "failure_origin": "none",
        "retryable": False, "strict_success": True,
        "evidence_sha256": "1" * 64, "grade_record_sha256": "2" * 64,
        "marker_last_verified": True,
        **_resource_fields(),
    }]
    with pytest.raises(ValueError, match="without repeat zero"):
        resume_queue(schedule, orphan)

    attempts = [{
        "schema_version": ATTEMPT_RECORD_SCHEMA,
        "logical_cell_id": item["logical_cell_id"], "repeat": 0,
        "trial_seed": item["trial_seed"], "failure_origin": "none",
        "retryable": False, "strict_success": True,
        "evidence_sha256": "1" * 64, "grade_record_sha256": "2" * 64,
        "marker_last_verified": True,
        **_resource_fields(),
    } for item in schedule["records"]]
    masked = build_masked_grade_ledger(
        schedule, attempts, retained, "2026-08-05T10:00:00Z"
    )
    masked["records"][0]["family"] = "forged"
    with pytest.raises(ValueError, match="identity drifted"):
        unmask_primary(masked, schedule, retained, "2026-08-05T10:01:00Z")


def test_attempt_extractor_reads_committed_marker_last_evidence(tmp_path):
    retained = _manifests()[4]
    schedule = build_phase_schedule(retained, "primary", "f" * 64)
    cell = schedule["records"][0]

    def key_for(item, model_role, model_digest):
        return AttemptKey(
            domain_name="office_demo", domain_version="0.1.0",
            domain_content_sha256="a" * 64,
            task_family=item["family"], task_version="1.0.0",
            generator_version=generate_next_study.GENERATOR_VERSION,
            grader_version="1.0.0", model_tag="qwen3.5:%s" % model_role,
            model_digest="sha256:" + model_digest,
            condition_name=item["condition"], condition_version="1.0.0",
            mechanism_sha256="b" * 64, instance_id=item["instance_id"],
            instance_content_sha256=item["content_sha256"],
            ordered_subepisodes=(), repeat=0,
            sampling={"seed": item["trial_seed"], "temperature": "0"},
            opportunity_budget={"model_calls": 18, "generated_tokens": 6144},
            prompt_sha256="c" * 64, tool_schema_sha256="d" * 64,
        )

    key = key_for(cell, "4b", schedule["model_sha256"])
    store = EvidenceStore.create_run(
        tmp_path / "runs", "next-study-extractor", {"test": True}
    )

    def producer(writer):
        writer.write_json("initial-state.json", {
            "schema_version": "brick.evidence-state/1", "state_kind": "initial", "payload": {},
        })
        writer.write_json("final-state.json", {
            "schema_version": "brick.evidence-state/1", "state_kind": "final", "payload": {},
        })
        writer.write_json("result.json", {
            "schema_version": "brick.evidence-result/1", "execution_status": "done",
            "tool_status": "clean", "failure_origin": "none", "failure": None,
            "metrics": {}, "diagnostics": [],
        })
        writer.write_json("grade.json", {
            "schema_version": "brick.evidence-grade/1", "grader_status": "graded",
            "candidate_decision": True, "diagnostics": [],
        })
        writer.write_json("actions.json", {
            "schema_version": "brick.evidence-actions/1", "actions": [],
        })
        writer.write_bytes("transcript.md", b"# committed attempt\n")
        writer.write_bytes(
            "memory-delta.jsonl",
            b'{"delta":[],"schema_version":"brick.memory-delta/1"}\n',
        )

    store.execute_or_resume(key, producer)
    extracted = extract_attempt_records(store, schedule)
    assert len(extracted) == 1
    assert extracted[0]["logical_cell_id"] == cell["logical_cell_id"]
    assert extracted[0]["marker_last_verified"] is True

    model_digests = {"2b": "2" * 64, "4b": "4" * 64, "9b": "9" * 64}
    descriptive = build_descriptive_schedule(retained, model_digests)
    descriptive_cell = descriptive["records"][0]
    descriptive_store = EvidenceStore.create_run(
        tmp_path / "runs", "next-study-descriptive-extractor", {"test": True}
    )
    descriptive_store.execute_or_resume(
        key_for(
            descriptive_cell, descriptive_cell["model_role"],
            descriptive_cell["model_sha256"],
        ),
        producer,
    )
    descriptive_extracted = extract_attempt_records(
        descriptive_store, descriptive
    )
    assert descriptive_extracted[0]["logical_cell_id"] == descriptive_cell[
        "logical_cell_id"
    ]


def test_preflight_requires_the_actually_held_machine_lease(tmp_path):
    manifests = _manifests()
    model_digests = {"2b": "2" * 64, "4b": "4" * 64, "9b": "9" * 64}
    schedules = {
        "calibration": build_phase_schedule(manifests[1], "calibration", model_digests["4b"]),
        "sentinel": build_phase_schedule(manifests[3], "sentinel", model_digests["4b"]),
        "primary": build_phase_schedule(manifests[4], "primary", model_digests["4b"]),
        "descriptives": build_descriptive_schedule(manifests[4], model_digests),
    }
    schedule_digests = {
        name: sha256_bytes(canonical_json_bytes(value, allow_float=False))
        for name, value in schedules.items()
    }
    host = build_fingerprint(HOST_FINGERPRINT_SCHEMA, {"host": "lenovo-test"})
    runtime = build_fingerprint(RUNTIME_FINGERPRINT_SCHEMA, {"ollama": "pinned"})
    artifacts = {name: "a" * 64 for name in REQUIRED_ARTIFACT_DIGESTS}
    authorization = build_authorization(
        tag="v0.13.0", tag_object_sha="9" * 40, commit_sha="b" * 40,
        artifact_digests=artifacts, host_fingerprint=host,
        runtime_fingerprint=runtime, schedule_digests=schedule_digests,
        model_digests=model_digests,
        descriptive_selection_sha256=schedules["descriptives"]["selection_sha256"],
        issued_at="2026-08-05T10:00:00Z", issuer="test issuer",
    )
    current = {
        "host_fingerprint": host, "runtime_fingerprint": runtime,
        "commit_sha": "b" * 40, "tag": "v0.13.0", "tag_object_sha": "9" * 40,
        "artifact_digests": artifacts, "model_digests": model_digests,
        "descriptive_selection_sha256": schedules["descriptives"]["selection_sha256"],
    }
    gates = {
        gate: {
            "schema_version": PREFLIGHT_GATE_SCHEMA,
            "status": "sealed_pass", "artifact_name": artifact,
            "artifact_sha256": artifacts[artifact],
        }
        for gate, artifact in PREFLIGHT_GATE_ARTIFACTS.items()
    }
    lease = BenchmarkLease(tmp_path / "benchmark.lease")
    assert preflight(authorization, current, schedules, gates, lease)["passed"] is False
    lease.acquire(authorization["authorization_sha256"])
    assert preflight(authorization, current, schedules, gates, lease)["passed"] is True
    forged = copy.deepcopy(gates)
    forged["construct_contract_complete"]["artifact_sha256"] = "0" * 64
    forged_result = preflight(authorization, current, schedules, forged, lease)
    assert forged_result["passed"] is False
    assert forged_result["all_offline_gates_passed"] is False
    lease.release()
    assert preflight(authorization, current, schedules, gates, lease)["passed"] is False


def test_readiness_report_names_the_real_next_gate_without_overclaiming():
    report = build_readiness_report()
    assert report["current_activity"] == "instrument construction and qualification"
    assert report["benchmark_running_now"] is False
    assert report["experiment_running_now"] is False
    assert report["live_model_calls"] == 0
    assert report["authorization_buildable"] is False
    assert report["human_review_authorization_gate"] is False
    assert report["external_or_evidence_dependent_gates"][
        "score_masked_22_cell_development_shakeout"
    ] is False
    assert report["next_transition"].startswith("complete native")
