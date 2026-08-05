"""Advisory human-agent content-validity protocol for office-v2.

This protocol never fabricates a judgment and never authorizes model execution.
It separates human interpretation evidence from agent-assisted triage and from
external, real-task validity.
"""

import argparse
from collections import Counter
import json
from pathlib import Path

from domains.office_demo.generators_v2 import FAMILIES, GENERATOR_VERSION
from harness.evidence import canonical_json_bytes
from harness.instances import (
    load_canonical_json, replace_canonical_json, sha256_bytes,
    validate_manifest,
)


PROTOCOL_SCHEMA = "brick.next-study.hybrid-validation-protocol/1"
PROTOCOL_VERSION = "office-hybrid-content-validation/1.1.0"
CHALLENGE_SCHEMA = "brick.next-study.hybrid-challenge-blueprint/1"
RESULT_SCHEMA = "brick.next-study.hybrid-validation-result/1"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROTOCOL = ROOT / "bench" / "next_study_hybrid_validation_protocol.json"
DEFAULT_BLUEPRINT = (
    ROOT / "evidence" / "next-study" / "office-v2-hybrid-challenge-blueprint.json"
)
DEFAULT_RESULT = (
    ROOT / "evidence" / "next-study" / "office-v2-hybrid-validation-result.json"
)

SPLIT_CHALLENGES = {
    "development": ("canonical_control", True),
    "calibration": ("record_order_control", True),
    "validation": ("irrelevant_state_control", True),
    "sentinel": ("alternate_policy_outcome", False),
    "retained": ("required_fact_omission", False),
    "adversarial": ("business_fact_corruption", False),
}


class HybridValidationError(ValueError):
    pass


def _digest(value):
    return sha256_bytes(canonical_json_bytes(value, allow_float=False))


def _all_instances(manifests):
    if not isinstance(manifests, (list, tuple)) or len(manifests) != 6:
        raise HybridValidationError("hybrid validation requires six manifests")
    for manifest in manifests:
        validate_manifest(manifest)
    if {item["split"] for item in manifests} != set(SPLIT_CHALLENGES):
        raise HybridValidationError("hybrid validation split set drifted")
    instances = [case for manifest in manifests for case in manifest["instances"]]
    if len(instances) != 528:
        raise HybridValidationError("hybrid validation requires 528 cases")
    return instances


def build_challenge_blueprint(manifests):
    """Select one outcome-blind base per family and split for 66 challenges."""

    instances = _all_instances(manifests)
    records = []
    for family in sorted(FAMILIES):
        for split, (challenge_type, expected_valid) in SPLIT_CHALLENGES.items():
            candidates = [
                item for item in instances
                if item["content"]["family"] == family
                and item["content"]["split"] == split
            ]
            if not candidates:
                raise HybridValidationError("challenge stratum is empty")
            base = min(
                candidates,
                key=lambda item: _digest({
                    "namespace": "brick.next-study.hybrid-challenge/1",
                    "family": family,
                    "split": split,
                    "instance_id": item["content"]["id"],
                    "content_sha256": item["content_sha256"],
                }),
            )
            identity = {
                "namespace": "brick.next-study.hybrid-challenge-id/1",
                "base_content_sha256": base["content_sha256"],
                "challenge_type": challenge_type,
            }
            records.append({
                "challenge_id": _digest(identity),
                "family": family,
                "source_split": split,
                "base_instance_id": base["content"]["id"],
                "base_content_sha256": base["content_sha256"],
                "challenge_type": challenge_type,
                "expected_valid": expected_valid,
                "materialized_packet_sha256": None,
                "sealed_answer_sha256": None,
                "status": "pending_family_specific_materialization",
            })
    document = {
        "schema_version": CHALLENGE_SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "status": "pending_materialization",
        "case_count": 66,
        "valid_controls": 33,
        "invalid_challenges": 33,
        "records": records,
    }
    document["blueprint_sha256"] = _digest(document)
    return validate_challenge_blueprint(document, manifests)


def validate_challenge_blueprint(document, manifests):
    expected = {
        "schema_version", "generator_version", "status", "case_count",
        "valid_controls", "invalid_challenges", "records",
        "blueprint_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise HybridValidationError("challenge blueprint has unexpected keys")
    unsigned = dict(document)
    supplied = unsigned.pop("blueprint_sha256")
    if supplied != _digest(unsigned):
        raise HybridValidationError("challenge blueprint digest drifted")
    if (
        document["schema_version"] != CHALLENGE_SCHEMA
        or document["generator_version"] != GENERATOR_VERSION
        or document["status"] != "pending_materialization"
        or document["case_count"] != 66
        or document["valid_controls"] != 33
        or document["invalid_challenges"] != 33
    ):
        raise HybridValidationError("challenge blueprint header drifted")
    instances = {
        item["content"]["id"]: item for item in _all_instances(manifests)
    }
    records = document["records"]
    if len(records) != 66 or len({item.get("challenge_id") for item in records}) != 66:
        raise HybridValidationError("challenge blueprint is not unique and complete")
    counts = Counter((item.get("family"), item.get("source_split")) for item in records)
    if set(counts.values()) != {1} or len(counts) != 66:
        raise HybridValidationError("challenge family/split balance drifted")
    for item in records:
        expected_keys = {
            "challenge_id", "family", "source_split", "base_instance_id",
            "base_content_sha256", "challenge_type", "expected_valid",
            "materialized_packet_sha256", "sealed_answer_sha256", "status",
        }
        if set(item) != expected_keys:
            raise HybridValidationError("challenge record has unexpected keys")
        base = instances.get(item["base_instance_id"])
        challenge = SPLIT_CHALLENGES.get(item["source_split"])
        if (
            base is None
            or base["content"]["family"] != item["family"]
            or base["content_sha256"] != item["base_content_sha256"]
            or challenge != (item["challenge_type"], item["expected_valid"])
            or item["materialized_packet_sha256"] is not None
            or item["sealed_answer_sha256"] is not None
            or item["status"] != "pending_family_specific_materialization"
        ):
            raise HybridValidationError("challenge record binding drifted")
    if document != _build_challenge_blueprint_unchecked(manifests):
        raise HybridValidationError("challenge selection is not deterministic")
    return document


def _build_challenge_blueprint_unchecked(manifests):
    # Avoid recursive validation while retaining one canonical constructor.
    instances = _all_instances(manifests)
    records = []
    for family in sorted(FAMILIES):
        for split, (challenge_type, expected_valid) in SPLIT_CHALLENGES.items():
            candidates = [
                item for item in instances
                if item["content"]["family"] == family
                and item["content"]["split"] == split
            ]
            base = min(candidates, key=lambda item: _digest({
                "namespace": "brick.next-study.hybrid-challenge/1",
                "family": family,
                "split": split,
                "instance_id": item["content"]["id"],
                "content_sha256": item["content_sha256"],
            }))
            records.append({
                "challenge_id": _digest({
                    "namespace": "brick.next-study.hybrid-challenge-id/1",
                    "base_content_sha256": base["content_sha256"],
                    "challenge_type": challenge_type,
                }),
                "family": family,
                "source_split": split,
                "base_instance_id": base["content"]["id"],
                "base_content_sha256": base["content_sha256"],
                "challenge_type": challenge_type,
                "expected_valid": expected_valid,
                "materialized_packet_sha256": None,
                "sealed_answer_sha256": None,
                "status": "pending_family_specific_materialization",
            })
    result = {
        "schema_version": CHALLENGE_SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "status": "pending_materialization",
        "case_count": 66,
        "valid_controls": 33,
        "invalid_challenges": 33,
        "records": records,
    }
    result["blueprint_sha256"] = _digest(result)
    return result


def build_protocol(review_selection_sha256, challenge_blueprint_sha256):
    for value, label in (
        (review_selection_sha256, "review selection"),
        (challenge_blueprint_sha256, "challenge blueprint"),
    ):
        if not isinstance(value, str) or len(value) != 64:
            raise HybridValidationError("%s digest is invalid" % label)
    return {
        "schema_version": PROTOCOL_SCHEMA,
        "version": PROTOCOL_VERSION,
        "generator_version": GENERATOR_VERSION,
        "status": "advisory_reviewer_a_packet_ready",
        "authorization_gate": False,
        "review_selection_sha256": review_selection_sha256,
        "challenge_blueprint_sha256": challenge_blueprint_sha256,
        "objectives": [
            "human interpretability and content validity of an outcome-blind audited sample",
            "agent reproduction of sealed human consensus on the audited sample",
            "agent sensitivity to balanced blinded valid and invalid challenge packets",
        ],
        "claims_permitted": [
            "human-reviewed clarity and outcome agreement for the audited fixed-suite sample",
            "agent reproduced human consensus on the audited sample if every frozen acceptance rule passes",
        ],
        "claims_prohibited": [
            "real-world utility or ecological validity",
            "generalized benchmark accuracy",
            "human-equivalent intelligence or universal annotator replacement",
            "a population defect-rate bound from the coverage-optimized sample",
        ],
        "human_design": {
            "minimum_real_humans_for_initial_content_audit": 1,
            "initial_audit_is_reliability_estimate": False,
            "second_independent_reviewer_required_for_agreement_claim": True,
            "independent_adjudicator_required_for_consensus_claim": True,
            "generative_ai_use_prohibited": True,
            "initial_single_review_cases": 44,
            "expanded_double_review_cases": 88,
            "full_claim_bearing_scope_cases": 308,
            "challenge_primary_cases": 66,
            "challenge_fixed_secondary_cases": 22,
            "initial_human_judgments": 44,
            "minimum_judgments_for_two_coder_agreement": 88,
        },
        "agent_design": {
            "minimum_distinct_model_lineages": 2,
            "evaluated_qwen_model_lineage_prohibited": True,
            "public_packet_only": True,
            "generator_oracle_grader_access_prohibited": True,
            "model_prompt_runtime_and_output_hashes_required": True,
            "claim_bearing_cases_reviewed": 308,
            "challenge_cases_reviewed": 66,
        },
        "acceptance": {
            "human_disagreement_requires_independent_adjudication": True,
            "confirmed_original_prompt_or_outcome_defects_allowed": 0,
            "agent_original_sample_exact_matches_required": 44,
            "agent_original_sample_exact_matches_denominator": 44,
            "agent_valid_challenge_controls_required": 33,
            "agent_invalid_challenges_detected_required": 33,
            "challenge_success_lower_95_bound_if_all_66_pass": "0.955624827",
            "invalid_sensitivity_lower_95_bound_if_all_33_pass": "0.913218811",
            "krippendorff_alpha": "descriptive with confidence interval when estimable; never a sole gate",
            "tost_equivalence": "prohibited unless a separate power analysis, equivalence margin, and coder-group design are frozen before judgments",
        },
        "adaptive_rule": {
            "zero_original_reliability_events": "stop human original review after the 44-case pilot",
            "one_original_reliability_event": "expand independent double review to the frozen 88-case sample",
            "two_or_more_original_reliability_events": "expand primary review to all 308 claim-bearing cases and secondary review to every mismatch",
            "confirmed_internal_defect": "convert to a deterministic counterexample and existing construct-gate test; pause live execution",
            "agent_only_flag": "advisory until reproduced deterministically or confirmed by a blinded human",
        },
        "external_validity": {
            "established": False,
            "required_separate_study": "provenance-bound probability sample of real target workflows with qualified end-user outcome assessment",
        },
    }


def build_pending_result(protocol, blueprint):
    if protocol.get("schema_version") != PROTOCOL_SCHEMA:
        raise HybridValidationError("pending result protocol is invalid")
    validate_challenge_blueprint(blueprint, _manifests())
    result = {
        "schema_version": RESULT_SCHEMA,
        "protocol_sha256": _digest(protocol),
        "challenge_blueprint_sha256": blueprint["blueprint_sha256"],
        "status": "pending_real_humans_and_challenge_materialization",
        "human_original_judgments": 0,
        "human_challenge_judgments": 0,
        "agent_judgments": 0,
        "confirmed_internal_defects": 0,
        "agent_substitution_supported": False,
        "external_validity_established": False,
        "execution_authorized": False,
        "claims_enabled": [],
    }
    result["result_sha256"] = _digest(result)
    return validate_pending_result(result, protocol, blueprint)


def validate_pending_result(result, protocol, blueprint):
    expected = {
        "schema_version", "protocol_sha256", "challenge_blueprint_sha256",
        "status", "human_original_judgments", "human_challenge_judgments",
        "agent_judgments", "confirmed_internal_defects",
        "agent_substitution_supported", "external_validity_established",
        "execution_authorized", "claims_enabled", "result_sha256",
    }
    if not isinstance(result, dict) or set(result) != expected:
        raise HybridValidationError("hybrid validation result has unexpected keys")
    unsigned = dict(result)
    supplied = unsigned.pop("result_sha256")
    if supplied != _digest(unsigned):
        raise HybridValidationError("hybrid validation result digest drifted")
    if (
        result["schema_version"] != RESULT_SCHEMA
        or result["protocol_sha256"] != _digest(protocol)
        or result["challenge_blueprint_sha256"] != blueprint["blueprint_sha256"]
        or result["status"] != "pending_real_humans_and_challenge_materialization"
        or any(result[field] != 0 for field in (
            "human_original_judgments", "human_challenge_judgments",
            "agent_judgments", "confirmed_internal_defects",
        ))
        or result["agent_substitution_supported"] is not False
        or result["external_validity_established"] is not False
        or result["execution_authorized"] is not False
        or result["claims_enabled"] != []
    ):
        raise HybridValidationError("pending hybrid result overclaims evidence")
    return result


def _manifests():
    directory = ROOT / "bench" / "manifests" / "office-v2"
    return [
        load_canonical_json(directory / (split + ".json"))
        for split in SPLIT_CHALLENGES
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    manifests = _manifests()
    selection = load_canonical_json(
        ROOT / "evidence" / "next-study" / "office-v2-review-selection.json"
    )
    blueprint = build_challenge_blueprint(manifests)
    protocol = build_protocol(
        selection["selection_sha256"], blueprint["blueprint_sha256"]
    )
    result = build_pending_result(protocol, blueprint)
    if args.write:
        replace_canonical_json(DEFAULT_BLUEPRINT, blueprint)
        replace_canonical_json(DEFAULT_PROTOCOL, protocol)
        replace_canonical_json(DEFAULT_RESULT, result)
    else:
        if load_canonical_json(DEFAULT_BLUEPRINT) != blueprint:
            raise HybridValidationError("challenge blueprint artifact drifted")
        if load_canonical_json(DEFAULT_PROTOCOL) != protocol:
            raise HybridValidationError("hybrid validation protocol drifted")
        validate_pending_result(
            load_canonical_json(DEFAULT_RESULT), protocol, blueprint
        )
    print(json.dumps({
        "status": protocol["status"],
        "human_pilot_cases": protocol["human_design"]["initial_single_review_cases"],
        "initial_human_judgments": protocol["human_design"]["initial_human_judgments"],
        "challenge_cases": blueprint["case_count"],
        "authorization_gate": protocol["authorization_gate"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CHALLENGE_SCHEMA", "DEFAULT_BLUEPRINT", "DEFAULT_PROTOCOL",
    "DEFAULT_RESULT",
    "HybridValidationError", "PROTOCOL_SCHEMA",
    "PROTOCOL_VERSION", "RESULT_SCHEMA", "SPLIT_CHALLENGES",
    "build_challenge_blueprint", "build_pending_result", "build_protocol",
    "main", "validate_challenge_blueprint", "validate_pending_result",
]
