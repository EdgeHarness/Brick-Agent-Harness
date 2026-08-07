"""Terminal construct-gate evidence for the tagged office-v2.2.0 instrument."""

from pathlib import Path

from harness.evidence import canonical_json_bytes
from harness.instances import load_canonical_json, replace_canonical_json, sha256_bytes


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "evidence" / "next-study" / "office-v2.2.0-construct-gate-failure.json"
SCHEMA_VERSION = "brick.next-study.construct-gate-failure/2"

TAGGED_COMMIT = "d87e7fd05da604919f677fcc9563c773cf1a95db"
TAG_OBJECT = "3a5be0b9ae1903c485c7fa6e26b26fbba2d19104"
BLOCKERS = [
    {
        "blocker_id": "cal-add-calendar-feasibility-inert",
        "family": "cal_add",
        "affected_cases": 48,
        "finding": (
            "Every generated candidate is feasible, so calendar contents never alter "
            "the selected request even though a calendar read is required."
        ),
        "required_repair": (
            "Add a publicly visible infeasible candidate whose removal from the "
            "feasible set is necessary under every decision policy."
        ),
    },
    {
        "blocker_id": "preference-policy-answer-printed",
        "family": "preference_learning",
        "affected_cases": 48,
        "finding": (
            "Every store prompt prints the selected fact string, so the named policy "
            "need not be applied to the conflicting bundles."
        ),
        "required_repair": (
            "Expose the bundle records and policy semantics but require the selected "
            "memory fields to be derived rather than printing their values."
        ),
    },
]


class ConstructGateFailure220Error(ValueError):
    pass


def _digest(value):
    return sha256_bytes(canonical_json_bytes(value, allow_float=False))


def build_failure():
    document = {
        "schema_version": SCHEMA_VERSION,
        "status": "construct_gate_failed",
        "generator_version": "office-generators/2.2.0",
        "protocol_version": "1.5.0",
        "instrument_tag": "v0.13.2",
        "tag_object_sha": TAG_OBJECT,
        "audited_commit_sha": TAGGED_COMMIT,
        "audit_date": "2026-08-07",
        "audit_scope_cases": 528,
        "confirmed_authorization_blockers": BLOCKERS,
        "confirmed_authorization_blocker_count": len(BLOCKERS),
        "prior_shakeout_cells_run": 22,
        "calibration_cells_run": 0,
        "effectiveness_data_inspected": False,
        "calibration_allowed": False,
        "tag_must_remain_immutable": True,
        "automatic_2_2_1_allowed": False,
        "automatic_family_removal_allowed": False,
        "required_disposition": "retire_v0.13.2_before_calibration",
        "future_remediation_requirement": (
            "explicitly authorize a new protocol, generator, construct contract, "
            "instrument tag, and complete offline/live qualification"
        ),
    }
    document["failure_sha256"] = _digest(document)
    return document


def validate_failure(document):
    expected = build_failure()
    if document != expected:
        raise ConstructGateFailure220Error("2.2.0 construct failure drifted")
    return document


def load_failure(path=DEFAULT_PATH):
    return validate_failure(load_canonical_json(path))


def write_failure(path=DEFAULT_PATH):
    return replace_canonical_json(path, build_failure())


if __name__ == "__main__":
    write_failure()


__all__ = [
    "BLOCKERS", "ConstructGateFailure220Error", "DEFAULT_PATH", "SCHEMA_VERSION",
    "build_failure", "load_failure", "validate_failure", "write_failure",
]
