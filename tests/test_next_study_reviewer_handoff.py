import copy
import csv
from pathlib import Path

import pytest

from bench.next_study_reviewer_handoff import (
    CHALLENGE_KEY_PATH, CHALLENGE_SET_PATH, ReviewerHandoffError,
    export_handoff, materialize_challenges, validate_challenges,
    validate_handoff, validate_submission,
)
from harness.instances import load_canonical_json


def test_materialized_challenges_are_balanced_bound_and_reproducible():
    challenge_set, key = materialize_challenges()
    assert challenge_set == load_canonical_json(CHALLENGE_SET_PATH)
    assert key == load_canonical_json(CHALLENGE_KEY_PATH)
    validate_challenges(challenge_set, key)
    assert challenge_set["case_count"] == 66
    assert key["valid_controls"] == 33
    assert key["invalid_challenges"] == 33
    assert len({item["challenge_packet_sha256"] for item in challenge_set["records"]}) == 66
    assert all("expected_valid" not in item for item in challenge_set["records"])
    assert all("source_split" not in item for item in challenge_set["records"])


def test_challenge_truth_or_packet_tampering_fails_closed():
    challenge_set, key = materialize_challenges()
    changed = copy.deepcopy(challenge_set)
    changed["records"][0]["candidate_outcome"] = []
    with pytest.raises(ReviewerHandoffError, match="drifted"):
        validate_challenges(changed, key)
    changed_key = copy.deepcopy(key)
    changed_key["records"][0]["expected_valid"] = not changed_key["records"][0]["expected_valid"]
    with pytest.raises(ReviewerHandoffError, match="drifted"):
        validate_challenges(challenge_set, changed_key)


def test_reviewer_a_handoff_is_blind_complete_and_reproducible(tmp_path):
    directory, archive = export_handoff(tmp_path / "brick-office-v2-reviewer-a")
    manifest = validate_handoff(directory)
    assert archive.is_file()
    assert manifest["packet_count"] == 44
    assert manifest["authorization_gate"] is False
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in directory.iterdir() if path.is_file()
    ).casefold()
    for prohibited in (
        "required_effects", "expected_valid", "source_split", "oracle_outcome",
        "condition_name", "strict_success",
    ):
        assert prohibited not in combined


def test_submission_validation_requires_every_answer(tmp_path):
    directory, _archive = export_handoff(tmp_path / "brick-office-v2-reviewer-a")
    response = directory / "RESPONSES.csv"
    with response.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
        fields = tuple(rows[0])
    for row in rows:
        row["prompt_clear"] = "yes"
        row["enough_information"] = "yes"
        row["single_reasonable_outcome"] = "yes"
        row["expected_actions_and_exact_details"] = "Exact expected actions recorded."
        row["reasonable_alternatives"] = "none"
        row["defect_or_ambiguity"] = "none"
        row["rationale"] = "The result follows from the visible packet."
        row["minutes_spent"] = "4"
    completed = tmp_path / "completed.csv"
    with completed.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    receipt = validate_submission(completed, directory)
    assert receipt["packet_count"] == 44
    assert receipt["flagged_packets"] == 0
    rows[0]["prompt_clear"] = "maybe"
    with completed.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    with pytest.raises(ReviewerHandoffError, match="yes or no"):
        validate_submission(completed, directory)
