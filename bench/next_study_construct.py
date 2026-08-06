"""Frozen construct contract for office-generators/2.1.1."""

from pathlib import Path

from domains.office_demo.generators_v2 import FAMILIES, GENERATOR_VERSION
from harness.instances import load_canonical_json


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "bench" / "next_study_construct_contract.json"
SCHEMA_VERSION = "brick.next-study.construct-contract/1"
VERSION = "office-construct/1.1.0"

POLICIES = {
    "pptx_basic": ["brief_sequence", "risk_descending", "owner_alphabetical"],
    "pptx_from_email": ["sequence_ascending", "revenue_descending", "region_alphabetical"],
    "xlsx_basic": ["source_order", "cost_descending", "item_alphabetical"],
    "xlsx_from_email": ["date_ascending", "amount_descending", "vendor_alphabetical"],
    "email_reply": ["latest_request", "highest_priority", "decision_key_match"],
    "cal_add": ["earliest_feasible", "highest_priority_feasible", "shortest_duration_feasible"],
    "cal_freeslot": ["earliest_free", "latest_free", "closest_to_preferred"],
    "cal_brief": ["chronological", "severity_descending", "owner_alphabetical"],
    "remind_msg": ["due_date_ascending", "priority_descending", "dependency_order"],
    "preference_learning": ["most_recent", "highest_priority", "most_specific_scope"],
    "multi_offsite": ["latest_issued", "highest_approval_rank", "consensus_supported"],
}


class ConstructContractError(ValueError):
    pass


def build_contract():
    return {
        "schema_version": SCHEMA_VERSION,
        "version": VERSION,
        "generator_version": GENERATOR_VERSION,
        "scope": "fixed_synthetic_benchmark_only",
        "families": sorted(FAMILIES),
        "policies": {key: POLICIES[key] for key in sorted(POLICIES)},
        "matched_triplets": 176,
        "required_case_count": 528,
        "acceptance": {
            "policy_outcomes_distinct_within_every_matched_triplet": True,
            "equal_non_policy_burden_within_every_matched_triplet": True,
            "public_packet_outcome_independently_reconstructible": True,
            "both_primary_conditions_have_legal_within_budget_positive_trace": True,
            "placeholder_presentations_rejected": True,
            "stored_preference_required_by_use_subepisode": True,
            "ordinary_case_scratch_memory_is_grading_neutral": True,
            "email_discovery_is_enforced_when_prompt_requires_listing": True,
            "every_graded_presentation_fact_is_mutation_tested": True,
            "semantic_negation_and_numeric_superstrings_are_rejected": True,
            "critical_high_medium_internal_validity_findings_allowed": 0,
        },
        "external_validity": {
            "real_work_sampling_frame_present": False,
            "generalized_real_world_claim_allowed": False,
            "mandatory_report_limitation": True,
        },
        "termination": {
            "this_is_final_remediation_version": True,
            "unresolved_deterministic_construct_blocker": "construct_gate_failed",
            "automatic_family_removal_allowed": False,
            "automatic_2_3_0_allowed": False,
        },
    }


def validate_contract(document):
    if document != build_contract():
        raise ConstructContractError("construct contract drifted")
    return document


def load_contract(path=CONTRACT_PATH):
    return validate_contract(load_canonical_json(path))


__all__ = [
    "CONTRACT_PATH", "POLICIES", "SCHEMA_VERSION", "VERSION",
    "ConstructContractError", "build_contract", "load_contract", "validate_contract",
]
