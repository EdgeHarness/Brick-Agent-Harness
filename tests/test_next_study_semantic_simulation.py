from bench.next_study_semantic_simulation import (
    DEFAULT_OUTPUT,
    audit_all,
    validate_report,
)
from harness.instances import load_canonical_json


def test_semantic_simulation_is_reproducible_and_fail_closed():
    report = validate_report(load_canonical_json(DEFAULT_OUTPUT))

    assert report == audit_all()
    assert report["status"] == "passed"
    assert report["artifact_is_execution_authorization"] is False
    assert report["assessment"] == {
        "executable_correctness": "pass",
        "prompt_to_outcome_internal_consistency": "pass",
        "construct_validity": "pass_for_fixed_synthetic_suite",
        "external_real_world_validity": "not_established",
        "confirmatory_execution_recommended": True,
        "exploratory_execution_recommended": True,
        "reason": (
            "All frozen internal-validity gates pass. External validity remains "
            "unestablished and is explicitly outside the claim."
        ),
    }


def test_semantic_simulation_covers_every_case_and_real_tool_contract():
    report = load_canonical_json(DEFAULT_OUTPUT)

    assert report["scope"]["case_count"] == 528
    assert report["scope"]["claim_bearing_cases"] == 308
    assert report["scope"]["unique_prompt_surfaces"] == 528
    assert report["scope"]["unique_structure_hashes"] == 528
    assert report["simulation"] == {
        "initial_record_order_invariance_passes": 528,
        "irrelevant_state_invariance_passes": 528,
        "live_model_calls": 0,
        "memory_use_dependency_failures": 0,
        "public_prompt_outcome_exact_matches": 528,
        "relevant_input_dependency_passes": 528,
        "relevant_input_dependency_probes": 528,
        "typed_positive_workflows_executed": 1056,
        "typed_positive_workflows_strict_successes": 1056,
        "typed_tool_actions_executed": 3312,
    }


def test_semantic_simulation_has_no_internal_construct_blockers():
    report = load_canonical_json(DEFAULT_OUTPUT)
    assert report["finding_severity_counts"] == {}
    assert report["findings"] == []
    assert report["assessment"]["external_real_world_validity"] == "not_established"


def test_all_eleven_families_have_three_outcome_distinct_policies():
    report = load_canonical_json(DEFAULT_OUTPUT)
    sensitive = {
        family for family, record in report["constraint_profile_sensitivity"].items()
        if record["distinct_policy_outcomes"] == 16
    }

    assert len(sensitive) == 11
