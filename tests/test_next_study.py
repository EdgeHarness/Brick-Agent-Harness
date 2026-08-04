import copy
import hashlib
from pathlib import Path

import pytest

from bench.next_study_contract import (
    NextStudyDesignError,
    execution_allowed,
    load_design,
    validate_design,
)
from bench.next_study_quality import audit_all
from bench.s7_postmortem import build_postmortem
from harness.evidence import canonical_json_bytes
from harness.instances import load_canonical_json


ROOT = Path(__file__).resolve().parents[1]
POSTMORTEM = ROOT / "evidence" / "s7" / "d0b-direction-blind-postmortem.json"
MUTATION_AUDIT = (
    ROOT / "evidence" / "s7" / "office-v1-grader-mutation-audit.json"
)


def test_direction_blind_postmortem_is_exact_reproducible_and_terminal():
    tracked = POSTMORTEM.read_bytes()
    rebuilt = canonical_json_bytes(build_postmortem(), newline=True)
    document = load_canonical_json(POSTMORTEM)
    assert tracked == rebuilt
    assert hashlib.sha256(tracked).hexdigest() == (
        "9b5b0f87340877b0fdcaada3ca2a4a40fc6bc557407debeed9b01f20cfe23805"
    )
    assert document["condition_scores_read"] is False
    assert document["directional_effects_computed"] is False
    assert document["raw_attempt_evidence_read"] is False
    assert document["current_study_terminal"] is True
    assert document["next_study_execution_allowed"] is False
    assert len(document["families"]) == 11
    assert sum(item["combined_outcomes"] for item in document["families"]) == 88

    by_family = {item["family"]: item for item in document["families"]}
    assert by_family["cal_brief"]["floor_ceiling_flag"] == "ceiling"
    assert by_family["email_reply"]["floor_ceiling_flag"] == "ceiling"
    assert by_family["pptx_from_email"]["floor_ceiling_flag"] == "ceiling"
    assert by_family["xlsx_from_email"]["floor_ceiling_flag"] == "floor"
    assert by_family["cal_brief"]["minimum_agent_tool_calls"] == [2, 2, 2, 2]
    assert by_family["email_reply"]["minimum_agent_tool_calls"] == [3, 3, 3, 3]
    assert by_family["pptx_from_email"]["minimum_agent_tool_calls"] == [3, 3, 3, 3]
    assert by_family["xlsx_from_email"]["minimum_agent_tool_calls"] == [5, 6, 7, 8]


def test_retired_suite_grader_mutation_audit_replays_all_applicable_checks():
    expected = load_canonical_json(MUTATION_AUDIT)
    assert hashlib.sha256(MUTATION_AUDIT.read_bytes()).hexdigest() == (
        "30e99c6d1d82e5520ce42202847e0a38fdc2c0539a5e69f9b3d9a186d112ac49"
    )
    assert audit_all() == expected
    assert expected == {
        "schema_version": "brick.next-study.grader-mutation-audit/1",
        "generator_version": "office-generators/1.1.0",
        "case_count": 352,
        "probe_count": 1984,
        "check_probe_counts": {
            "exact_artifacts": 352,
            "exact_business_effects": 352,
            "no_unauthorized_effects": 352,
            "no_unrequested_state": 352,
            "required_outcome": 352,
            "source_observed": 224,
        },
        "all_applicable_mutations_rejected": True,
        "live_model_calls": 0,
        "retained_model_execution": False,
    }


def test_next_study_design_is_exact_counted_and_fail_closed():
    design = load_design()
    assert design["status"] == "offline_instrument_build"
    assert design["version"] == "0.2.0"
    assert design["fresh_suite"]["generator_version"] == (
        design["fresh_suite"]["seed_namespace"]
    )
    assert design["fresh_suite"]["total_cases"] == 528
    assert design["calibration"]["combined_outcomes_per_family"] == 32
    assert design["calibration"]["model_attempts"] == 352
    assert design["primary_design"]["instance_clusters"] == 220
    assert design["primary_design"]["model_attempts"] == 880
    assert design["sentinel"]["primary_condition_cells"] == 88
    assert design["execution_gates"] == {
        "calibration_protocol_frozen": True,
        "fresh_generator_complete": True,
        "grader_mutation_matrix_complete": False,
        "independent_oracle_complete": True,
        "live_execution_authorized": False,
        "power_and_cluster_analysis_frozen": True,
        "prompt_ground_truth_review_complete": False,
        "sentinel_protocol_frozen": True,
    }
    assert design["live_model_execution_enabled"] is False
    assert design["retained_execution_enabled"] is False
    assert execution_allowed(design) is False


def test_next_study_canonical_json_is_lf_only_on_windows_checkout():
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "bench/next_study_design.json text eol=lf" in attributes.splitlines()
    assert (ROOT / "bench" / "next_study_design.json").read_bytes().endswith(
        b"\n"
    )
    assert b"\r\n" not in (
        ROOT / "bench" / "next_study_design.json"
    ).read_bytes()


@pytest.mark.parametrize(
    "mutation",
    (
        lambda value: value.__setitem__("live_model_execution_enabled", True),
        lambda value: value["execution_gates"].__setitem__(
            "live_execution_authorized", True
        ),
        lambda value: value["predecessor"].__setitem__(
            "runtime_decision_sha256", "0" * 64
        ),
        lambda value: value["fresh_suite"].__setitem__(
            "generator_version", "office-generators/1.1.0"
        ),
        lambda value: value["calibration"].__setitem__("model_attempts", 351),
        lambda value: value["predecessor"].__setitem__(
            "postmortem_path", "evidence/s7/missing.json"
        ),
        lambda value: value["calibration"].__setitem__(
            "acceptable_combined_successes_minimum", 9
        ),
        lambda value: value["sentinel"].__setitem__(
            "primary_condition_cells", 87
        ),
        lambda value: value["required_controls"].__setitem__(
            "old_suite_model_reuse_allowed", True
        ),
        lambda value: value["execution_gates"].pop(
            "independent_oracle_complete"
        ),
        lambda value: value["successor_artifacts"].__setitem__(
            "oracle_audit_sha256", "0" * 64
        ),
        lambda value: value["primary_design"].__setitem__(
            "minimum_relevant_absolute_effect", "0.10"
        ),
    ),
)
def test_next_study_design_tampering_fails_closed(mutation):
    design = copy.deepcopy(load_design())
    mutation(design)
    with pytest.raises(NextStudyDesignError):
        validate_design(design)
