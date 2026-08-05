import copy
import json
from pathlib import Path

import pytest

from bench import generate_next_study
from bench.next_study_review import (
    REVIEW_PROTOCOL_VERSION, build_assignments, build_pending_ledger,
    build_pilot, compile_adjudicated_outcomes, export_adjudication_packet,
    export_review_packets,
    digest_review_artifact, materialize_ledger, review_packet, seal_submission,
    validate_staffing, STAFFING_SCHEMA,
)
from bench.next_study_review_ops import build_progress, frozen_review_bindings, main
from bench.next_study_review_training import (
    ANSWER_KEY_PATH, HANDBOOK_PATH, PRACTICE_PATH, qualification_roster_record,
    score_qualification, seal_qualification_submission, verify_artifacts,
)
from bench.next_study_review_selection import build_review_selection
from domains.office_demo.generators_v2 import FAMILIES
from domains.office_demo.outcome_oracle_v2 import derive_outcome
from harness.instances import load_canonical_json, replace_canonical_json


def _manifests():
    return [
        load_canonical_json(generate_next_study.DEFAULT_DIRECTORY / (split + ".json"))
        for split in (
            "development", "calibration", "validation", "sentinel",
            "retained", "adversarial",
        )
    ]


def _mark_published(path):
    Path(str(path) + ".complete").write_bytes(b"")


def _perfect_responses():
    key = load_canonical_json(ANSWER_KEY_PATH)
    return [
        {
            "practice_id": answer["practice_id"],
            "prompt_valid": answer["prompt_valid"],
            "outcome": copy.deepcopy(answer["outcome"]),
            "accepted_alternatives": copy.deepcopy(answer["accepted_alternatives"]),
            "rationale": "Independent qualification response.",
        }
        for answer in key["answers"]
    ]


def _qualification_result(reviewer_id):
    submission = seal_qualification_submission(
        reviewer_id, _perfect_responses(), "2026-08-05T10:00:00Z",
        {
            "identity_confirmed": True,
            "no_source_access": True,
            "no_generative_ai": True,
            "independent_response": True,
        },
    )
    return score_qualification(submission)


def _reviewer(identifier):
    return {
        "reviewer_id": identifier,
        "name": "Synthetic Test Human " + identifier,
        "identity_attested": True,
        "conflicts_attested": True,
        "availability_attested": True,
        "access_ready": True,
        "compensation_arranged": True,
        "confidentiality_attested": True,
        "no_generative_ai_attested": True,
        "no_source_access_attested": True,
        "qualification": qualification_roster_record(
            _qualification_result(identifier)
        ),
    }


def _staffing():
    return {
        "schema_version": STAFFING_SCHEMA,
        "review_protocol_version": REVIEW_PROTOCOL_VERSION,
        "status": "ready",
        "active_reviewers": [_reviewer("human-%d" % index) for index in range(3)],
        "backup_reviewers": [],
    }


def _outcome(instance):
    content = instance["content"]
    return derive_outcome(
        content["family"], content["prompt"],
        [item["prompt"] for item in content["ordered_subepisodes"]],
        content["initial_state"], content["today"],
    )


def _response(identifier, outcome, *, adjudicator=False):
    return {
        "adjudicator_id" if adjudicator else "reviewer_id": identifier,
        "prompt_valid": True,
        "outcome": copy.deepcopy(outcome),
        "accepted_alternatives": [],
        "rationale": "Synthetic workflow fixture.",
    }


def _attestations(adjudicator=False):
    result = {
        "identity_confirmed": True,
        "no_source_access": True,
        "no_generative_ai": True,
        "no_case_discussion": True,
        "independent_response": True,
    }
    if adjudicator:
        result.update({
            "reviews_unseen_before_seal": True,
            "oracle_unseen": True,
        })
    return result


def test_frozen_qualification_covers_all_families_and_seeded_controls():
    protocol = verify_artifacts()
    practice = load_canonical_json(PRACTICE_PATH)
    assert protocol["practice_version"] == "office-review-practice/1.0.0"
    assert protocol["minimum_score"] == 12
    assert practice["case_count"] == 13
    families = {item["family"] for item in practice["packets"]}
    assert set(FAMILIES) <= families
    assert {"seeded_ambiguity", "seeded_alternative"} <= families
    assert protocol["handbook_sha256"] == __import__(
        "harness.instances", fromlist=["sha256_bytes"]
    ).sha256_bytes(HANDBOOK_PATH.read_bytes())


def test_qualification_threshold_allows_one_family_error_but_not_control_error():
    perfect = _qualification_result("human-perfect")
    assert perfect["qualified"] is True and perfect["score_numerator"] == 13

    one_error = _perfect_responses()
    one_error[0]["outcome"] = []
    result = score_qualification(seal_qualification_submission(
        "human-one-error", one_error, "2026-08-05T10:00:00Z",
        {"identity_confirmed": True, "no_source_access": True,
         "no_generative_ai": True, "independent_response": True},
    ))
    assert result["qualified"] is True and result["score_numerator"] == 12

    control_error = _perfect_responses()
    control = next(
        item for item in control_error
        if item["practice_id"] == "practice-seeded-ambiguity"
    )
    control["prompt_valid"] = True
    result = score_qualification(seal_qualification_submission(
        "human-control-error", control_error, "2026-08-05T10:00:00Z",
        {"identity_confirmed": True, "no_source_access": True,
         "no_generative_ai": True, "independent_response": True},
    ))
    assert result["score_numerator"] == 12
    assert result["qualified"] is False


def test_end_to_end_review_dry_run_is_blind_sealed_and_adjudicated(tmp_path):
    manifests = _manifests()
    staffing = validate_staffing(_staffing())
    assignments = build_assignments(manifests, staffing)
    pilot = build_pilot(assignments, manifests, frozen_review_bindings())
    included = {item["packet_id"] for item in pilot["records"]}
    bundles = export_review_packets(
        tmp_path / "pilot", manifests, staffing, assignments,
        frozen_review_bindings()["handbook_sha256"], included,
    )
    assert sum(load_canonical_json(path)["case_count"] for path in bundles) == 88
    assert all("instance_id" not in path.read_text(encoding="utf-8") for path in bundles)
    staffing_path = tmp_path / "staffing.json"
    assignments_path = tmp_path / "assignments.json"
    pilot_path = tmp_path / "pilot.json"
    result_path = tmp_path / "pilot-result.json"
    replace_canonical_json(staffing_path, staffing)
    replace_canonical_json(assignments_path, assignments)
    replace_canonical_json(pilot_path, pilot)
    replace_canonical_json(result_path, {
        "schema_version": "brick.next-study.review-pilot-result/2",
        "pilot_sha256": digest_review_artifact(pilot),
        "status": "complete_counted_toward_full_review",
        "case_count": 44,
        "judgment_count": 88,
        "median_review_seconds": 240,
        "p90_review_seconds": 360,
        "entry_errors": 0,
        "exact_agreements": 44,
        "disputes": 0,
        "adjudications": 0,
        "median_adjudication_seconds": 0,
        "protocol_changed": False,
        "prompt_or_oracle_defects": 0,
        "reliability_events": 0,
        "global_escalation_triggered": False,
    })
    remaining_dir = tmp_path / "remaining"
    main([
        "export-full", "--staffing", str(staffing_path),
        "--assignments", str(assignments_path), "--pilot", str(pilot_path),
        "--pilot-result", str(result_path), "--output-dir", str(remaining_dir),
    ])
    assert sum(
        load_canonical_json(path)["case_count"]
        for path in remaining_dir.glob("*.json")
    ) == 308

    assignment = pilot["records"][0]
    instance_by_id = {
        item["content"]["id"]: item
        for manifest in manifests for item in manifest["instances"]
    }
    instance = instance_by_id[assignment["instance_id"]]
    packet, outcome = review_packet(instance), _outcome(instance)
    first_id, second_id = assignment["primary"], assignment["secondary"]
    first = seal_submission(
        packet, first_id, "primary", _response(first_id, outcome),
        "2026-08-05T11:00:00Z", "2026-08-05T11:04:00Z",
        _attestations(),
    )
    wrong = copy.deepcopy(outcome)
    wrong[-1] = {"type": "message_sent", "to": "Wrong", "exact_count": 1}
    second = seal_submission(
        packet, second_id, "secondary", _response(second_id, wrong),
        "2026-08-05T11:01:00Z", "2026-08-05T11:06:00Z",
        _attestations(),
    )

    adjudication_path = export_adjudication_packet(
        tmp_path / "adjudication.json", manifests, staffing, assignments,
        assignment["packet_id"], frozen_review_bindings()["handbook_sha256"],
    )
    adjudication_bundle = load_canonical_json(adjudication_path)
    assert "reviews" not in adjudication_path.read_text(encoding="utf-8")
    adjudicator_id = assignment["adjudicator"]
    assert adjudication_bundle["reviewer_id"] == adjudicator_id
    adjudication = seal_submission(
        packet, adjudicator_id, "adjudicator",
        _response(adjudicator_id, outcome, adjudicator=True),
        "2026-08-05T11:07:00Z", "2026-08-05T11:10:00Z",
        _attestations(adjudicator=True),
    )
    ledger = materialize_ledger(
        build_pending_ledger(manifests), manifests, assignments,
        [first, second], [adjudication],
    )
    assert ledger["completed_cases"] == 1
    assert next(
        item for item in ledger["entries"]
        if item["instance_id"] == assignment["instance_id"]
    )["status"] == "adjudicated"
    progress = build_progress(assignments, [first, second, adjudication])
    assert progress["disputes"] == 1
    assert progress["resolved_disputes"] == 1
    assert progress["median_review_seconds"] == 240
    assert progress["p90_review_seconds"] == 300

    tampered = copy.deepcopy(first)
    tampered["review_duration_seconds"] = 1
    with pytest.raises(ValueError):
        build_progress(assignments, [tampered])


def test_review_selection_is_outcome_blind_balanced_and_pilot_nested():
    selection = build_review_selection(_manifests())
    assert selection["case_count"] == 308
    assert selection["planned_judgments"] == 396
    assert selection["expanded_judgments"] == 616
    assert set(selection["scope_splits"]) == {"calibration", "retained"}
    for family in FAMILIES:
        family_records = [item for item in selection["records"] if item["family"] == family]
        assert len(family_records) == 28
        assert sum(item["fixed_double_review"] for item in family_records) == 8
        assert sum(item["pilot"] for item in family_records) == 4
        assert all(item["fixed_double_review"] for item in family_records if item["pilot"])
        for split in ("calibration", "retained"):
            fixed = [
                item for item in family_records
                if item["source_split"] == split and item["fixed_double_review"]
            ]
            assert len(fixed) == 4
            assert sum(item["pilot"] for item in fixed) == 2
            assert len({item["decision_policy"] for item in fixed}) == 3
            assert len({item["workload"] for item in fixed}) == 4
            assert len({item["distractor_count"] for item in fixed}) == 4


def test_two_reliability_events_expand_secondary_review_to_all_308():
    manifests = _manifests()
    assignments = build_assignments(manifests, validate_staffing(_staffing()))
    instances = {
        item["content"]["id"]: item
        for manifest in manifests for item in manifest["instances"]
    }
    adaptive = [item for item in assignments["records"] if not item["fixed_double_review"]][:2]
    submissions = []
    for assignment in adaptive:
        instance = instances[assignment["instance_id"]]
        packet, wrong = review_packet(instance), copy.deepcopy(_outcome(instance))
        wrong[-1] = {"type": "message_sent", "to": "Wrong", "exact_count": 1}
        reviewer = assignment["primary"]
        submissions.append(seal_submission(
            packet, reviewer, "primary", _response(reviewer, wrong),
            "2026-08-05T16:00:00Z", "2026-08-05T16:04:00Z",
            _attestations(),
        ))
    first = materialize_ledger(
        build_pending_ledger(manifests), manifests, assignments, submissions[:1],
    )
    assert first["global_escalation"] is False
    assert first["required_secondary_judgments"] == 89
    second = materialize_ledger(
        build_pending_ledger(manifests), manifests, assignments, submissions,
    )
    assert second["global_escalation"] is True
    assert len(second["reliability_event_cases"]) == 2
    assert second["required_secondary_judgments"] == 308
    assert all(item["secondary_required"] for item in second["entries"])


def test_operator_status_is_honestly_pending_and_assignment_init_fails(capsys):
    main(["status"])
    status = json.loads(capsys.readouterr().out)
    assert status["staffing_ready"] is False
    assert status["active_reviewers"] == 0
    assert status["completed_cases"] == 0
    with pytest.raises(ValueError):
        main(["init-assignments"])


def test_synthetic_planned_ledger_compiles_all_308_human_outcomes():
    manifests = _manifests()
    assignments = build_assignments(manifests, validate_staffing(_staffing()))
    instances = {
        item["content"]["id"]: item
        for manifest in manifests for item in manifest["instances"]
    }
    submissions = []
    for assignment in assignments["records"]:
        instance = instances[assignment["instance_id"]]
        packet, outcome = review_packet(instance), _outcome(instance)
        roles = ("primary", "secondary") if assignment["fixed_double_review"] else ("primary",)
        for role in roles:
            reviewer = assignment[role]
            submissions.append(seal_submission(
                packet, reviewer, role, _response(reviewer, outcome),
                "2026-08-05T13:00:00Z", "2026-08-05T13:04:00Z",
                _attestations(),
            ))
    ledger = materialize_ledger(
        build_pending_ledger(manifests), manifests, assignments, submissions,
    )
    assert ledger["status"] == "complete"
    assert ledger["completed_cases"] == 308
    compiled = compile_adjudicated_outcomes(ledger, manifests)
    assert compiled["case_count"] == 308
    assert {item["review_resolution"] for item in compiled["records"]} == {
        "accepted_single", "agreed",
    }


def test_operator_qualification_commands_require_explicit_attestation(tmp_path, capsys):
    template = tmp_path / "qualification-responses.json"
    main(["qualification-template", "--output", str(template)])
    capsys.readouterr()
    replace_canonical_json(template, _perfect_responses())
    sealed = tmp_path / "sealed-qualification.json"
    command = [
        "seal-qualification", "--reviewer-id", "human-cli",
        "--responses", str(template), "--sealed-at", "2026-08-05T12:00:00Z",
        "--output", str(sealed),
    ]
    with pytest.raises(ValueError):
        main(command)
    main(command + ["--attest"])
    capsys.readouterr()
    result = tmp_path / "qualification-result.json"
    roster = tmp_path / "qualification-roster-record.json"
    main([
        "score-qualification", "--submission", str(sealed),
        "--output", str(result), "--roster-record", str(roster),
    ])
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "qualified"
    assert load_canonical_json(result)["score_numerator"] == 13
    assert set(load_canonical_json(roster)) == {
        "reviewer_id", "submission_sha256", "sealed_at",
        "practice_set_version", "practice_set_sha256", "answer_key_sha256",
        "families", "seeded_ambiguity_passed", "accepted_alternatives_passed",
        "score_numerator", "score_denominator", "minimum_score",
        "case_results_sha256", "qualification_result_sha256", "qualified",
    }


def test_operator_assembles_only_three_or_four_attested_qualified_reviewers(tmp_path, capsys):
    active = tmp_path / "active"
    active.mkdir()
    for index in range(3):
        reviewer_id = "human-roster-%d" % index
        result_path = tmp_path / (reviewer_id + "-qualification.json")
        replace_canonical_json(result_path, _qualification_result(reviewer_id))
        _mark_published(result_path)
        command = [
            "reviewer-record", "--reviewer-id", reviewer_id,
            "--name", "Roster Human %d" % index,
            "--qualification-result", str(result_path),
            "--output", str(active / (reviewer_id + ".json")),
        ]
        if index == 0:
            with pytest.raises(ValueError):
                main(command)
        main(command + ["--attest-all-roster-requirements"])
        capsys.readouterr()
    staffing_path = tmp_path / "staffing.json"
    main([
        "assemble-staffing", "--active-dir", str(active),
        "--output", str(staffing_path),
    ])
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "ready"
    assert output["active_reviewers"] == 3
    assert validate_staffing(load_canonical_json(staffing_path))["status"] == "ready"


def test_progress_rejects_wrong_signer_and_premature_adjudication():
    manifests = _manifests()
    staffing = validate_staffing(_staffing())
    assignments = build_assignments(manifests, staffing)
    assignment = assignments["records"][0]
    instance = next(
        item for manifest in manifests for item in manifest["instances"]
        if item["content"]["id"] == assignment["instance_id"]
    )
    packet, outcome = review_packet(instance), _outcome(instance)
    wrong_id = assignment["adjudicator"]
    wrong = seal_submission(
        packet, wrong_id, "primary", _response(wrong_id, outcome),
        "2026-08-05T14:00:00Z", "2026-08-05T14:04:00Z",
        _attestations(),
    )
    with pytest.raises(ValueError, match="signer is not assigned"):
        build_progress(assignments, [wrong], manifests=manifests, staffing=staffing)
    adjudication = seal_submission(
        packet, wrong_id, "adjudicator",
        _response(wrong_id, outcome, adjudicator=True),
        "2026-08-05T14:00:00Z", "2026-08-05T14:04:00Z",
        _attestations(adjudicator=True),
    )
    with pytest.raises(ValueError, match="cannot precede"):
        build_progress(
            assignments, [adjudication], manifests=manifests, staffing=staffing,
        )


def test_marker_last_intake_preserves_pristine_and_existing_seals(tmp_path, capsys):
    manifests = _manifests()
    staffing = validate_staffing(_staffing())
    assignments = build_assignments(manifests, staffing)
    assignment = assignments["records"][0]
    instance = next(
        item for manifest in manifests for item in manifest["instances"]
        if item["content"]["id"] == assignment["instance_id"]
    )
    packet, outcome = review_packet(instance), _outcome(instance)
    reviewer = assignment["primary"]
    submission = seal_submission(
        packet, reviewer, "primary", _response(reviewer, outcome),
        "2026-08-05T15:00:00Z", "2026-08-05T15:04:00Z",
        _attestations(),
    )
    assignments_path = tmp_path / "assignments.json"
    replace_canonical_json(assignments_path, assignments)
    directory = tmp_path / "submissions"
    directory.mkdir()
    submission_path = directory / "one.json"
    receipts = tmp_path / "receipts"
    replace_canonical_json(submission_path, submission)
    with pytest.raises(ValueError, match="invalid files"):
        main([
            "intake", "--assignments", str(assignments_path),
            "--submissions", str(directory), "--receipt-dir", str(receipts),
            "--output", str(tmp_path / "ledger.json"),
        ])
    _mark_published(submission_path)
    with pytest.raises(ValueError, match="pristine pending ledger"):
        main([
            "intake", "--assignments", str(assignments_path),
            "--submissions", str(directory), "--receipt-dir", str(receipts), "--output",
            str(generate_next_study.EVIDENCE_DIRECTORY / generate_next_study.REVIEW_LEDGER_NAME),
        ])
    derived = tmp_path / "ledger.json"
    main([
        "intake", "--assignments", str(assignments_path),
        "--submissions", str(directory), "--receipt-dir", str(receipts),
        "--output", str(derived),
    ])
    capsys.readouterr()
    assert not derived.exists()
    changed_response = _response(reviewer, outcome)
    changed_response["rationale"] = "Changed after the first sealed intake."
    changed = seal_submission(
        packet, reviewer, "primary", changed_response,
        "2026-08-05T15:00:00Z", "2026-08-05T15:04:00Z",
        _attestations(),
    )
    replace_canonical_json(submission_path, changed)
    with pytest.raises(ValueError, match="replace sealed review work"):
        main([
            "intake", "--assignments", str(assignments_path),
            "--submissions", str(directory), "--receipt-dir", str(receipts),
            "--output", str(derived),
        ])
