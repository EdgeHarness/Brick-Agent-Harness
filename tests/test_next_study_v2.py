"""Offline gates for office-generators/2.0.0 and its frozen protocols."""

import copy
import inspect
import tempfile
from pathlib import Path

import pytest

from bench import generate_next_study
from bench.next_study_review import (
    ReviewLedgerError,
    refresh_status,
    review_complete,
    review_packet,
    validate_ledger,
)
from bench.next_study_statistics import (
    NextStudyStatisticsError,
    analyze_primary,
    build_protocol,
    load_protocol,
)
from domains.office_demo.generated_grader import build_grader
from domains.office_demo.generators_v2 import (
    FAMILIES,
    GENERATOR_VERSION,
    NEXT_SPLITS,
    SPLIT_SIZES,
    generate_all_manifests,
    validate_office_instance_v2,
)
from domains.office_demo.outcome_oracle_v2 import derive_outcome
from domains.office_demo.rules_reference import execute as execute_rules
from harness.instances import (
    envelope_instance,
    load_canonical_json,
    review_split_overlap,
)


def _committed_manifests():
    return [
        load_canonical_json(
            generate_next_study.DEFAULT_DIRECTORY / (split + ".json")
        )
        for split in NEXT_SPLITS
    ]


def test_successor_manifests_replay_all_528_fresh_balanced_cases():
    lock, audit, ledger = generate_next_study.verify()
    assert [item["split"] for item in lock["manifests"]] == list(NEXT_SPLITS)
    assert [item["instances"] for item in lock["manifests"]] == [
        88, 88, 44, 44, 220, 44,
    ]
    assert sum(item["instances"] for item in lock["manifests"]) == 528
    assert audit["case_count"] == 528
    assert audit["prompt_to_hidden_outcome_exact_matches"] == 528
    assert audit["family_counts"] == {family: 48 for family in sorted(FAMILIES)}
    assert ledger["status"] == "pending_human_review"
    assert ledger["completed_cases"] == 0


def test_successor_generation_is_deterministic_and_semantically_disjoint():
    first = generate_all_manifests()
    second = generate_all_manifests()
    assert first == second
    assert [item["split"] for item in first] == list(NEXT_SPLITS)
    for manifest in first:
        assert len(manifest["instances"]) == len(FAMILIES) * SPLIT_SIZES[
            manifest["split"]
        ]
    review = review_split_overlap(first, NEXT_SPLITS)
    assert review == {
        "schema_version": "brick.split-overlap-review/1",
        "passed": True,
        "splits": list(NEXT_SPLITS),
        "instances": 528,
        "structures": 528,
        "entity_keys": 1272,
        "entity_surfaces": 2256,
    }


def test_successor_lock_records_complete_balance_and_zero_predecessor_reuse():
    lock = load_canonical_json(
        generate_next_study.DEFAULT_DIRECTORY / generate_next_study.LOCK_NAME
    )
    assert lock["generator_version"] == GENERATOR_VERSION
    assert lock["predecessor_reuse_review"]["overlap_counts"] == {
        "content_sha256": 0,
        "entity_key": 0,
        "entity_surface": 0,
        "instance_id": 0,
        "structure_sha256": 0,
    }
    records = lock["balance_review"]["split_records"]
    assert [item["workload_3_through_6_counts"] for item in records] == [
        [2, 2, 2, 2], [2, 2, 2, 2], [1, 1, 1, 1],
        [1, 1, 1, 1], [5, 5, 5, 5], [1, 1, 1, 1],
    ]
    assert [item["distractor_0_through_3_counts"] for item in records] == [
        [2, 2, 2, 2], [2, 2, 2, 2], [1, 1, 1, 1],
        [1, 1, 1, 1], [5, 5, 5, 5], [1, 1, 1, 1],
    ]
    assert lock["balance_review"]["minimum_model_facing_tool_calls_by_family"] == {
        "cal_add": {"minimum": 2, "maximum": 2},
        "cal_brief": {"minimum": 2, "maximum": 2},
        "cal_freeslot": {"minimum": 2, "maximum": 2},
        "email_reply": {"minimum": 4, "maximum": 4},
        "multi_offsite": {"minimum": 5, "maximum": 5},
        "pptx_basic": {"minimum": 1, "maximum": 1},
        "pptx_from_email": {"minimum": 5, "maximum": 8},
        "preference_learning": {"minimum": 2, "maximum": 2},
        "remind_msg": {"minimum": 2, "maximum": 2},
        "xlsx_basic": {"minimum": 1, "maximum": 1},
        "xlsx_from_email": {"minimum": 3, "maximum": 3},
    }


def test_independent_oracle_api_cannot_accept_hidden_effects_or_grader_output():
    assert list(inspect.signature(derive_outcome).parameters) == [
        "family", "prompt", "subepisode_prompts", "initial_state", "today",
    ]
    instance = _committed_manifests()[0]["instances"][0]
    packet = review_packet(instance)
    assert "required_effects" not in packet
    assert "grader" not in packet
    assert set(packet) == {
        "schema_version", "instance_id", "family", "today", "prompt",
        "subepisode_prompts", "initial_state", "available_tools",
    }


def test_hidden_outcome_or_prompt_tampering_is_rejected_by_independent_oracle():
    source = next(
        item for item in _committed_manifests()[0]["instances"]
        if item["content"]["family"] == "pptx_basic"
    )
    instance = copy.deepcopy(source)
    instance["content"]["required_effects"][0]["filename"] = "wrong.pptx"
    changed = envelope_instance(instance["content"])
    with pytest.raises(ValueError, match="independent prompt oracle disagrees"):
        validate_office_instance_v2(changed)

    instance = copy.deepcopy(source)
    instance["content"]["prompt"] = instance["content"]["prompt"].replace(
        "Use exactly", "Use approximately",
    )
    changed = envelope_instance(instance["content"])
    with pytest.raises(ValueError):
        validate_office_instance_v2(changed)


def test_two_distinct_human_reviews_are_required_and_ledger_remains_open():
    manifests = _committed_manifests()
    ledger = load_canonical_json(
        generate_next_study.EVIDENCE_DIRECTORY
        / generate_next_study.REVIEW_LEDGER_NAME
    )
    validate_ledger(ledger, manifests)
    assert review_complete(ledger, manifests) is False

    instance = sorted(
        [item for manifest in manifests for item in manifest["instances"]],
        key=lambda item: item["content"]["id"],
    )[0]
    content = instance["content"]
    outcome = derive_outcome(
        content["family"], content["prompt"],
        [episode["prompt"] for episode in content["ordered_subepisodes"]],
        content["initial_state"], content["today"],
    )
    changed = copy.deepcopy(ledger)
    for slot, reviewer in (("reviewer_a", "human-001"), ("reviewer_b", "human-002")):
        changed["entries"][0]["reviews"][slot] = {
            "reviewer_id": reviewer,
            "prompt_valid": True,
            "outcome": outcome,
            "accepted_alternatives": [],
            "rationale": "Independently derived prompt and authoritative outcome.",
        }
    changed = refresh_status(changed, manifests)
    assert changed["entries"][0]["status"] == "agreed"
    assert changed["completed_cases"] == 1
    assert changed["status"] == "pending_human_review"

    duplicate = copy.deepcopy(ledger)
    for slot in ("reviewer_a", "reviewer_b"):
        duplicate["entries"][0]["reviews"][slot] = {
            "reviewer_id": "same-human",
            "prompt_valid": True,
            "outcome": outcome,
            "accepted_alternatives": [],
            "rationale": "This must fail the independence rule.",
        }
    with pytest.raises(ReviewLedgerError, match="same reviewer"):
        refresh_status(duplicate, manifests)


def test_frozen_repeat_aware_protocol_reconciles_and_stays_fail_closed():
    protocol = load_protocol()
    assert protocol == build_protocol()
    assert protocol["calibration"]["model_attempts"] == 352
    assert protocol["primary"]["instance_clusters"] == 220
    assert protocol["primary"]["model_attempts"] == 880
    assert protocol["power"]["minimum_clusters_for_target_power"] == 205
    assert protocol["power"]["normal_approximation_power_at_relevant_effect"] == (
        "0.828074238908"
    )
    assert protocol["sentinel"]["condition_cells"] == 88
    assert protocol["execution_controls"]["live_model_execution_enabled"] is False
    assert protocol["execution_controls"]["retained_execution_enabled"] is False
    changed = copy.deepcopy(protocol)
    changed["primary"]["model_attempts"] = 879
    with pytest.raises(NextStudyStatisticsError):
        analyze_primary([], _committed_manifests()[4], changed)


def test_existing_rules_reference_strictly_passes_all_successor_cases():
    count = 0
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for manifest in _committed_manifests():
            for instance in manifest["instances"]:
                outcome = build_grader(instance).grade_evidence(
                    execute_rules(instance, root / str(count))
                )
                assert outcome.strict_success is True, instance["content"]["id"]
                count += 1
    assert count == 528
