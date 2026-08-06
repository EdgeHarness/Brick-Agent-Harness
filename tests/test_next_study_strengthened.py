import ast
import copy
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import tempfile

import pytest

from bench import generate_next_study
from bench.next_study_grader_audit import audit_all, audit_machine_conformance
from bench.next_study_descriptive import (
    build_report, eligible_schedule, extract_descriptive_results,
    extract_primary_trial_0_controls,
    seal_descriptive_eligibility,
    validate_eligible_schedule,
)
from bench.next_study_program import (
    BenchmarkLease, calibration_decision, research_catalog, retry_decision,
    sentinel_decision,
)
from bench.next_study_review import (
    REVIEW_PROTOCOL_VERSION, build_assignments, build_pilot,
    build_staffing_template, materialize_ledger, review_packet,
    export_review_packets, seal_submission, staffing_ready, validate_pilot_result,
    validate_staffing, STAFFING_SCHEMA,
)
from bench.next_study_runtime import (
    ATTEMPT_RECORD_SCHEMA, build_masked_grade_ledger, resume_queue,
    unmask_primary,
)
from bench.next_study_review_training import verify_artifacts as verify_review_training
from bench.next_study_review_selection import build_review_selection
from bench.next_study_schedule import (
    build_descriptive_schedule, build_phase_schedule, select_descriptive_cases,
)
from bench.next_study_statistics import (
    _claim_disposition, analyze_primary, load_protocol,
)
from domains.office_demo.generators_v2 import FAMILIES, GENERATOR_VERSION
from domains.office_demo.outcome_oracle_v2 import derive_outcome
from domains.office_demo.reviewed_grader_v2 import build_grader
from harness.evidence import canonical_json_bytes
from harness.instances import load_canonical_json, sha256_bytes


ROOT = Path(__file__).resolve().parents[1]


def _manifests():
    return [
        load_canonical_json(generate_next_study.DEFAULT_DIRECTORY / (split + ".json"))
        for split in (
            "development", "calibration", "validation", "sentinel",
            "retained", "adversarial",
        )
    ]


def _qualification(identifier):
    protocol = verify_review_training()
    return {
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
        "case_results_sha256": "0" * 64,
        "qualification_result_sha256": "2" * 64,
        "qualified": True,
    }


def _reviewer(identifier):
    return {
        "reviewer_id": identifier,
        "name": "Test Human " + identifier,
        "identity_attested": True,
        "conflicts_attested": True,
        "availability_attested": True,
        "access_ready": True,
        "compensation_arranged": True,
        "confidentiality_attested": True,
        "no_generative_ai_attested": True,
        "no_source_access_attested": True,
        "qualification": _qualification(identifier),
    }


def _staffing(count):
    return {
        "schema_version": STAFFING_SCHEMA,
        "review_protocol_version": REVIEW_PROTOCOL_VERSION,
        "status": "ready",
        "active_reviewers": [_reviewer("human-%d" % index) for index in range(count)],
        "backup_reviewers": [],
    }


def _review_response(identifier, outcome):
    return {
        "reviewer_id": identifier,
        "prompt_valid": True,
        "outcome": copy.deepcopy(outcome),
        "accepted_alternatives": [],
        "rationale": "Independent test-fixture derivation.",
    }


def _review_attestations():
    return {
        "identity_confirmed": True,
        "no_source_access": True,
        "no_generative_ai": True,
        "no_case_discussion": True,
        "independent_response": True,
    }


def _outcome(instance):
    content = instance["content"]
    return derive_outcome(
        content["family"], content["prompt"],
        [item["prompt"] for item in content["ordered_subepisodes"]],
        content["initial_state"], content["today"],
    )


def _synthetic_outcomes_for_grader_test(manifests):
    selection = build_review_selection(manifests)
    selected = {item["instance_id"] for item in selection["records"]}
    records = []
    for manifest in manifests:
        for instance in manifest["instances"]:
            if instance["content"]["id"] not in selected:
                continue
            packet = review_packet(instance)
            records.append({
                "instance_id": instance["content"]["id"],
                "content_sha256": instance["content_sha256"],
                "review_packet_sha256": __import__(
                    "bench.next_study_review", fromlist=["_digest"]
                )._digest(packet),
                "prompt_valid": True,
                "outcome": _outcome(instance),
                "accepted_alternatives": [],
                "review_resolution": "agreed",
            })
    return {
        "schema_version": "brick.next-study.adjudicated-outcomes/2",
        "generator_version": GENERATOR_VERSION,
        "review_protocol_version": REVIEW_PROTOCOL_VERSION,
        "review_selection_sha256": selection["selection_sha256"],
        "review_ledger_sha256": "0" * 64,
        "case_count": 308,
        "records": records,
    }


def test_staffing_is_real_prerequisite_and_pair_loads_are_exact():
    template = build_staffing_template()
    assert staffing_ready(template) is False
    manifests = _manifests()
    three = build_assignments(manifests, validate_staffing(_staffing(3)))
    assert max(three["pair_counts"].values()) - min(three["pair_counts"].values()) == 1
    assert set(three["reviewer_planned_judgment_counts"].values()) == {132}
    assert set(three["reviewer_expanded_judgment_counts"].values()) == {205, 206}
    four = build_assignments(manifests, validate_staffing(_staffing(4)))
    assert max(four["pair_counts"].values()) - min(four["pair_counts"].values()) == 1
    assert set(four["reviewer_planned_judgment_counts"].values()) == {99}
    assert set(four["reviewer_expanded_judgment_counts"].values()) == {154}
    with tempfile.TemporaryDirectory() as directory, pytest.raises(ValueError):
        export_review_packets(directory, manifests, template, four, "0" * 64)


def test_pilot_is_44_cases_and_counts_only_when_bindings_do_not_change():
    manifests = _manifests()
    assignments = build_assignments(manifests, _staffing(4))
    bindings = {"generator": "1" * 64, "handbook": "2" * 64, "packet": "3" * 64}
    pilot = build_pilot(assignments, manifests, bindings)
    assert pilot["case_count"] == 44 and pilot["judgment_count"] == 88
    assert max(pilot["pair_counts"].values()) - min(pilot["pair_counts"].values()) <= 2
    assert set(pilot["reviewer_judgment_counts"].values()) == {22}
    counts = {}
    by_id = {item["content"]["id"]: item for manifest in manifests for item in manifest["instances"]}
    for record in pilot["records"]:
        family = by_id[record["instance_id"]]["content"]["family"]
        counts[family] = counts.get(family, 0) + 1
    assert set(counts.values()) == {4}
    result = {
        "schema_version": "brick.next-study.review-pilot-result/2",
        "pilot_sha256": __import__(
            "bench.next_study_review", fromlist=["_digest"]
        )._digest(pilot),
        "status": "complete_counted_toward_full_review",
        "case_count": 44,
        "judgment_count": 88,
        "median_review_seconds": 240,
        "p90_review_seconds": 360,
        "entry_errors": 0,
        "exact_agreements": 42,
        "disputes": 2,
        "adjudications": 2,
        "median_adjudication_seconds": 180,
        "protocol_changed": False,
        "prompt_or_oracle_defects": 0,
        "reliability_events": 2,
        "global_escalation_triggered": True,
    }
    assert validate_pilot_result(pilot, result, bindings) == result
    with pytest.raises(ValueError):
        validate_pilot_result(pilot, result, {**bindings, "handbook": "4" * 64})


def test_sealed_submissions_materialize_only_assigned_independent_reviews():
    manifests = _manifests()
    staffing = _staffing(3)
    assignments = build_assignments(manifests, staffing)
    assignment = assignments["records"][0]
    by_id = {item["content"]["id"]: item for manifest in manifests for item in manifest["instances"]}
    instance = by_id[assignment["instance_id"]]
    packet, outcome = review_packet(instance), _outcome(instance)
    submissions = []
    for role in ("primary", "secondary"):
        reviewer = assignment[role]
        submissions.append(seal_submission(
            packet, reviewer, role, _review_response(reviewer, outcome),
            "2026-08-04T11:56:00Z", "2026-08-04T12:00:00Z",
            _review_attestations(),
        ))
    pending = load_canonical_json(
        generate_next_study.EVIDENCE_DIRECTORY / generate_next_study.REVIEW_LEDGER_NAME
    )
    materialized = materialize_ledger(pending, manifests, assignments, submissions)
    assert materialized["completed_cases"] == 1


def test_independent_grader_import_boundary_and_full_mutation_matrix():
    tree = ast.parse((
        ROOT / "domains" / "office_demo" / "reviewed_grader_v2.py"
    ).read_text(encoding="utf-8"))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not any(
        name.endswith(("generators_v2", "outcome_oracle_v2", "generated_grader"))
        for name in imports
    )
    manifests = _manifests()
    synthetic = _synthetic_outcomes_for_grader_test(manifests)
    human = audit_all(manifests, synthetic)
    assert human["targeted_mutations"] == 2394
    assert human["benign_non_rejection_controls"] == 1092
    assert human["may_satisfy_human_ground_truth_gate"] is True
    audit = audit_machine_conformance(manifests)
    assert audit["targeted_mutations"] == 4104
    assert audit["benign_control_counts"] == {
        "equivalent_serialization": 528, "failed_unauthorized_call": 528,
        "repeated_safe_read": 336, "nonbusiness_scratch_memory": 480,
    }
    assert audit["may_satisfy_human_ground_truth_gate"] is False
    assert audit["passed"] is True


def test_schedules_descriptives_and_closed_research_catalog_are_exact(monkeypatch):
    retained = _manifests()[4]
    primary = build_phase_schedule(retained, "primary", "a" * 64)
    assert primary["logical_cell_count"] == 880
    assert primary["maximum_physical_attempts"] == 1760
    selection = select_descriptive_cases(retained)
    assert selection["selection_count"] == 22
    matrix = build_descriptive_schedule(
        retained, {"2b": "b" * 64, "4b": "c" * 64, "9b": "d" * 64}
    )
    assert matrix["logical_cell_count"] == 222
    assert len({item["logical_cell_id"] for item in matrix["records"]}) == 222
    selected = {item["instance_id"] for item in matrix["records"]}
    grade_ledger = {
        "schema_version": "brick.next-study.grade-ledger/2",
        "execution_context": {"schema_version": "brick.next-study.execution-context/1", "value": "synthetic_rehearsal"},
        "protocol_version": load_protocol()["version"],
        "status": "sealed_complete",
        "cell_count": 880,
        "schedule_sha256": sha256_bytes(canonical_json_bytes(primary)),
        "records": [
            {
                "instance_id": cell["instance_id"],
                "condition": cell["condition"],
                "trial_index": 0,
                "strict_success": cell["condition"] == "harness_full",
                "evidence_sha256": "1" * 64,
                "grade_record_sha256": "2" * 64,
            }
            for cell in primary["records"]
            if cell["trial_index"] == 0 and cell["instance_id"] in selected
        ],
    }
    primary_analysis = {
        "schema_version": "brick.next-study.primary-analysis/3",
        "execution_context": {"schema_version": "brick.next-study.execution-context/1", "value": "synthetic_rehearsal"},
        "protocol_version": load_protocol()["version"],
        "primary_grade_ledger_sha256": sha256_bytes(
            canonical_json_bytes(grade_ledger)
        ),
        "primary_schedule_sha256": grade_ledger["schedule_sha256"],
    }
    binding = seal_descriptive_eligibility(primary_analysis, grade_ledger, matrix)
    eligible = eligible_schedule(
        matrix, {"2b": False, "4b": True, "9b": True}, binding,
    )
    assert eligible["eligible_cells"] == 178
    assert eligible["removed_blocks"] == ["2b_native_full"]
    full = eligible_schedule(
        matrix, {"2b": True, "4b": True, "9b": True}, binding,
    )
    forged = copy.deepcopy(full)
    remove = {
        item["logical_cell_id"]
        for role in ("2b", "9b")
        for item in [
            value for value in full["records"] if value["model_role"] == role
        ][:22]
    }
    forged["records"] = [
        item for item in forged["records"]
        if item["logical_cell_id"] not in remove
    ]
    forged["eligible_cells"] = forged["logical_cell_count"] = 178
    forged["maximum_physical_attempts"] = 356
    forged["removed_blocks"] = ["2b_native_full", "9b_native_full"]
    with pytest.raises(ValueError, match="partially removed"):
        validate_eligible_schedule(forged, matrix)
    first = eligible["records"][0]
    controls = extract_primary_trial_0_controls(grade_ledger, matrix)
    evidence = extract_descriptive_results(eligible, [{
        "schema_version": ATTEMPT_RECORD_SCHEMA,
        "logical_cell_id": first["logical_cell_id"],
        "repeat": 0, "trial_seed": first["trial_seed"],
        "failure_origin": "none", "retryable": False,
        "strict_success": True,
        "evidence_sha256": "1" * 64, "grade_record_sha256": "2" * 64,
        "marker_last_verified": True,
        "model_calls": 7,
        "successful_reads": 2,
        "successful_mutations": 1,
        "generated_tokens_exact": None,
        "generated_tokens_lower_bound": 300,
        "generated_tokens_upper_bound": 420,
        "model_time_ms": 1200,
        "wall_time_ms": 1400,
    }])
    report = build_report(eligible, evidence, primary_trial_0_controls=controls)
    assert report["status"] == "partial_descriptive"
    assert report["primary_claim_affected"] is False
    assert report["unknown_tokens_imputed"] is False
    assert report["p_values"] is None and report["synthetic_resource_score"] is None
    monkeypatch.setattr(
        "importlib.metadata.entry_points",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("enumerated")),
    )
    catalog = research_catalog()
    assert catalog["external_entry_point_discovery"] is False
    assert catalog["domains"] == ["office_demo"]


@pytest.mark.parametrize("successes,expected", ((9, "retire_generator"), (10, "sealed_pass"), (22, "sealed_pass"), (23, "retire_generator")))
def test_calibration_boundaries_and_sentinel_zero_one(successes, expected):
    manifests = _manifests()
    calibration_schedule = build_phase_schedule(
        manifests[1], "calibration", "a" * 64
    )
    records = []
    seen = {family: 0 for family in FAMILIES}
    for cell in calibration_schedule["records"]:
        index = seen[cell["family"]]
        seen[cell["family"]] += 1
        records.append({
            "logical_cell_id": cell["logical_cell_id"],
            "instrument_valid": True, "strict_success": index < successes,
        })
    assert calibration_decision(records, calibration_schedule)["status"] == expected
    sentinel_schedule = build_phase_schedule(manifests[3], "sentinel", "a" * 64)
    valid = [
        {"logical_cell_id": cell["logical_cell_id"], "instrument_valid": True}
        for cell in sentinel_schedule["records"]
    ]
    assert sentinel_decision(valid, sentinel_schedule)["status"] == "sealed_pass"
    invalid = copy.deepcopy(valid)
    invalid[-1]["instrument_valid"] = False
    assert sentinel_decision(invalid, sentinel_schedule)["status"] == "retire_instrument"


def test_environment_only_retry_and_machine_wide_lease():
    eligible = retry_decision({
        "repeat": 0, "failure_origin": "environment", "retryable": True,
        "same_seed_available": True,
    })
    assert eligible == {
        "eligible": True, "next_repeat": 1, "same_seed_required": True,
        "known_parser_rejection_is_model_failure": True,
    }
    assert retry_decision({
        "repeat": 0, "failure_origin": "model", "retryable": False,
        "same_seed_available": True,
    })["eligible"] is False
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "machine.lease"
        first, second = BenchmarkLease(path), BenchmarkLease(path)
        first.acquire("e" * 64)
        with pytest.raises(ValueError):
            second.acquire("e" * 64)
        first.release()


def test_masked_primary_must_be_complete_before_unmask_and_analysis():
    retained = _manifests()[4]
    schedule = build_phase_schedule(retained, "primary", "f" * 64)
    attempts = []
    instance_order = {
        identifier: index
        for index, identifier in enumerate(sorted({
            item["instance_id"] for item in schedule["records"]
        }))
    }
    for cell in schedule["records"]:
        instance_index = instance_order[cell["instance_id"]]
        attempts.append({
            "schema_version": ATTEMPT_RECORD_SCHEMA,
            "logical_cell_id": cell["logical_cell_id"],
            "repeat": 0,
            "trial_seed": cell["trial_seed"],
            "failure_origin": "none",
            "retryable": False,
            "strict_success": (
                instance_index % 5 != 0
                if cell["condition"] == "harness_full"
                else instance_index % 3 != 0
            ),
            "evidence_sha256": "1" * 64,
            "grade_record_sha256": "2" * 64,
            "marker_last_verified": True,
            "model_calls": 1, "successful_reads": 0,
            "successful_mutations": 0, "generated_tokens_exact": 1,
            "generated_tokens_lower_bound": None,
            "generated_tokens_upper_bound": None,
            "model_time_ms": 1, "wall_time_ms": 1,
        })
    assert resume_queue(schedule, attempts) == []
    key = "7" * 64
    masked = build_masked_grade_ledger(
        schedule, attempts, retained, "2026-08-04T13:00:00Z", key
    )
    assert masked["status"] == "sealed_complete_masked"
    assert "condition" not in masked["records"][0]
    grade_ledger = unmask_primary(
        masked, schedule, retained, attempts, key, "2026-08-04T13:01:00Z"
    )
    analysis = analyze_primary(grade_ledger, retained, schedule, load_protocol())
    assert analysis == load_canonical_json(
        ROOT / "tests" / "fixtures" / "next_study_analysis_golden.json"
    )
    assert analysis["instance_clusters"] == 220
    assert len(analysis["leave_one_family_out"]["records"]) == 11
    assert analysis["bootstrap_first_100_index_vectors_sha256"] == (
        load_protocol()["analysis"]["bootstrap"]["first_100_index_vectors_sha256"]
    )
    reordered = copy.deepcopy(grade_ledger)
    reordered["records"].reverse()
    reordered_analysis = analyze_primary(
        reordered, retained, schedule, load_protocol()
    )
    assert reordered_analysis["primary_grade_ledger_sha256"] != analysis[
        "primary_grade_ledger_sha256"
    ]
    assert {
        key: value for key, value in reordered_analysis.items()
        if key != "primary_grade_ledger_sha256"
    } == {
        key: value for key, value in analysis.items()
        if key != "primary_grade_ledger_sha256"
    }

    reversed_labels = copy.deepcopy(grade_ledger)
    values = {
        (record["instance_id"], record["condition"], record["trial_index"]): record["strict_success"]
        for record in grade_ledger["records"]
    }
    for record in reversed_labels["records"]:
        other = "native_tools" if record["condition"] == "harness_full" else "harness_full"
        record["strict_success"] = values[(record["instance_id"], other, record["trial_index"])]
    reversed_analysis = analyze_primary(
        reversed_labels, retained, schedule, load_protocol()
    )
    assert Decimal(reversed_analysis["paired_effect"]) == -Decimal(analysis["paired_effect"])
    assert [Decimal(item) for item in reversed_analysis["cluster_bootstrap_95_interval"]] == [
        -Decimal(analysis["cluster_bootstrap_95_interval"][1]),
        -Decimal(analysis["cluster_bootstrap_95_interval"][0]),
    ]
    assert reversed_analysis["reliability"]["native_tools"] == analysis["reliability"]["harness_full"]
    assert reversed_analysis["reliability"]["harness_full"] == analysis["reliability"]["native_tools"]


def test_claim_boundaries_are_symmetric_and_effect_threshold_is_inclusive():
    assert _claim_disposition(Fraction(12, 100), Fraction(1, 100), Fraction(2, 10)) == (
        "harness_full_directional_superiority"
    )
    assert _claim_disposition(Fraction(119, 1000), Fraction(1, 100), Fraction(2, 10)) == (
        "no_directional_superiority_claim"
    )
    assert _claim_disposition(Fraction(-12, 100), Fraction(-2, 10), Fraction(-1, 100)) == (
        "native_tools_directional_superiority"
    )
    assert _claim_disposition(Fraction(-12, 100), Fraction(-2, 10), Fraction(0, 1)) == (
        "no_directional_superiority_claim"
    )
