"""Authorization and deterministic closure for the post-2.2.0 successor.

The tagged 2.2.0 failure remains immutable. This module records the explicitly
authorized 2.3.0 remediation and permits closure only after the new
manifest, semantic simulation, and full grader conformance evidence all pass.
"""

import hashlib
from pathlib import Path

from bench.next_study_220_failure import load_failure
from domains.office_demo.generators_v2 import GENERATOR_VERSION
from domains.office_demo.outcome_oracle_v2 import ORACLE_VERSION
from domains.office_demo.reviewed_grader_v2 import GRADER_VERSION
from harness.instances import load_canonical_json, replace_canonical_json


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION_PATH = (
    ROOT / "evidence" / "next-study" / "office-v2.3.0-successor-authorization.json"
)
CLOSURE_PATH = (
    ROOT / "evidence" / "next-study" / "office-v2.3.0-remediation-closure.json"
)
FAILURE_PATH = (
    ROOT / "evidence" / "next-study" / "office-v2.2.0-construct-gate-failure.json"
)
MANIFEST_LOCK_PATH = ROOT / "bench" / "manifests" / "office-v2" / "manifest-lock.json"
SEMANTIC_PATH = (
    ROOT / "evidence" / "next-study" / "office-v2-semantic-simulation.json"
)
CONFORMANCE_PATH = (
    ROOT / "evidence" / "next-study" / "office-v2-grader-machine-conformance.json"
)

AUTHORIZATION_SCHEMA = "brick.next-study.successor-authorization/1"
CLOSURE_SCHEMA = "brick.next-study.remediation-closure/1"
PROTOCOL_VERSION = "1.6.0"
CONSTRUCT_VERSION = "office-construct/1.4.0"
TARGET_TAG = "v0.13.3"

BLOCKER_CLOSURES = {
    "cal-add-calendar-feasibility-inert": (
        "an infeasible superlative decoy makes the visible calendar causal"
    ),
    "preference-policy-answer-printed": (
        "the selected memory values must be derived from bundles and policy"
    ),
}


class SuccessorAuthorizationError(ValueError):
    pass


def _canonical_text_sha256(path):
    payload = Path(path).read_bytes()
    try:
        payload = payload.decode("utf-8").replace("\r\n", "\n").encode("utf-8")
    except UnicodeDecodeError:
        pass
    return hashlib.sha256(payload).hexdigest()


def build_authorization():
    failure = load_failure(FAILURE_PATH)
    if failure["status"] != "construct_gate_failed":
        raise SuccessorAuthorizationError("2.2.0 must remain terminal before succession")
    blocker_ids = sorted(
        finding["blocker_id"] for finding in failure["confirmed_authorization_blockers"]
    )
    if blocker_ids != sorted(BLOCKER_CLOSURES):
        raise SuccessorAuthorizationError("authorized blocker set differs from terminal evidence")
    return {
        "schema_version": AUTHORIZATION_SCHEMA,
        "status": "authorized_pre_outcome_successor_remediation",
        "authorized_on": "2026-08-07",
        "authorization_basis": (
            "User explicitly instructed Codex to perform a final deep architecture "
            "audit, revise every change, fix validated gaps, and finalize the instrument."
        ),
        "from_generator_version": "office-generators/2.2.0",
        "to_generator_version": GENERATOR_VERSION,
        "seed_namespace": "office-generators/2.1.0",
        "protocol_version": PROTOCOL_VERSION,
        "construct_contract_version": CONSTRUCT_VERSION,
        "oracle_version": ORACLE_VERSION,
        "grader_version": GRADER_VERSION,
        "target_instrument_tag": TARGET_TAG,
        "live_study_cells_run": 0,
        "no_effectiveness_data_inspected": True,
        "families": 11,
        "retained_clusters": 220,
        "estimand_or_claim_rule_changed": False,
        "automatic_family_removal_allowed": False,
        "automatic_followup_generator_allowed": False,
        "terminal_failure_path": str(FAILURE_PATH.relative_to(ROOT)).replace("\\", "/"),
        "terminal_failure_sha256": _canonical_text_sha256(FAILURE_PATH),
        "authorized_blocker_ids": blocker_ids,
    }


def validate_authorization(document):
    if document != build_authorization():
        raise SuccessorAuthorizationError("2.3.0 successor authorization drifted")
    return document


def load_authorization(path=AUTHORIZATION_PATH):
    return validate_authorization(load_canonical_json(path))


def write_authorization(path=AUTHORIZATION_PATH):
    return replace_canonical_json(path, build_authorization())


def build_closure():
    authorization = load_authorization()
    lock = load_canonical_json(MANIFEST_LOCK_PATH)
    semantic = load_canonical_json(SEMANTIC_PATH)
    conformance = load_canonical_json(CONFORMANCE_PATH)
    marker = Path(str(CONFORMANCE_PATH) + ".complete")
    checks = {
        "authorization_valid": authorization["status"] == "authorized_pre_outcome_successor_remediation",
        "generator_version_exact": lock.get("generator_version") == GENERATOR_VERSION,
        "case_count_exact": sum(
            item.get("instances", 0) for item in lock.get("manifests", [])
        ) == 528,
        "leakage_scan_passed": lock.get("split_leakage_review", {}).get("passed") is True,
        "semantic_simulation_passed": semantic.get("status") == "passed",
        "semantic_case_count_exact": semantic.get("scope", {}).get("case_count") == 528,
        "typed_positive_workflows_exact": semantic.get("simulation", {}).get(
            "typed_positive_workflows_strict_successes"
        ) == 1056,
        "cal_add_calendar_dependency_exact": semantic.get("simulation", {}).get(
            "causal_dependency_passes_by_family", {}
        ).get("cal_add") == 48,
        "preference_policy_dependency_exact": semantic.get("simulation", {}).get(
            "causal_dependency_passes_by_family", {}
        ).get("preference_learning") == 48,
        "no_material_semantic_findings": all(
            semantic.get("finding_severity_counts", {}).get(level, 0) == 0
            for level in ("critical", "high", "medium")
        ),
        "grader_conformance_passed": conformance.get("passed") is True,
        "grader_case_count_exact": conformance.get("case_count") == 528,
        "grader_completion_marker_present": marker.is_file() and marker.read_bytes() == b"",
    }
    if not all(checks.values()):
        failed = sorted(name for name, passed in checks.items() if not passed)
        raise SuccessorAuthorizationError(
            "2.3.0 remediation evidence is incomplete: %s" % ", ".join(failed)
        )
    return {
        "schema_version": CLOSURE_SCHEMA,
        "status": "passed",
        "generator_version": GENERATOR_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "authorization_sha256": _canonical_text_sha256(AUTHORIZATION_PATH),
        "closed_blockers": [
            {"blocker_id": blocker_id, "closure": BLOCKER_CLOSURES[blocker_id]}
            for blocker_id in sorted(BLOCKER_CLOSURES)
        ],
        "checks": checks,
        "bound_artifacts": {
            "manifest_lock_sha256": _canonical_text_sha256(MANIFEST_LOCK_PATH),
            "semantic_simulation_sha256": _canonical_text_sha256(SEMANTIC_PATH),
            "grader_conformance_sha256": _canonical_text_sha256(CONFORMANCE_PATH),
        },
        "live_model_calls": 0,
        "effectiveness_data_inspected": False,
    }


def validate_closure(document):
    if document != build_closure():
        raise SuccessorAuthorizationError("2.3.0 remediation closure drifted")
    return document


def load_closure(path=CLOSURE_PATH):
    return validate_closure(load_canonical_json(path))


def write_closure(path=CLOSURE_PATH):
    return replace_canonical_json(path, build_closure())


__all__ = [
    "AUTHORIZATION_PATH", "CLOSURE_PATH", "BLOCKER_CLOSURES",
    "SuccessorAuthorizationError", "build_authorization", "build_closure",
    "load_authorization", "load_closure", "validate_authorization",
    "validate_closure", "write_authorization", "write_closure",
]
