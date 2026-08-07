"""Terminal construct-gate evidence for the frozen office-v2.1.2 candidate."""

from pathlib import Path

from harness.evidence import canonical_json_bytes
from harness.instances import load_canonical_json, replace_canonical_json, sha256_bytes

from .next_study_fable_reconciliation import load_reconciliation


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "evidence" / "next-study" / "office-v2.1.2-construct-gate-failure.json"
SCHEMA_VERSION = "brick.next-study.construct-gate-failure/1"


class ConstructGateFailureError(ValueError):
    pass


def _digest(value):
    return sha256_bytes(canonical_json_bytes(value, allow_float=False))


def build_failure():
    reconciliation = load_reconciliation()
    blocking = [
        item["finding_id"] for item in reconciliation["findings"]
        if item["blocks_authorization"]
    ]
    document = {
        "schema_version": SCHEMA_VERSION,
        "status": "construct_gate_failed",
        "generator_version": "office-generators/2.1.2",
        "protocol_version": "1.4.0",
        "audited_commit_sha": "614ef9b4f20b39addf081f8b95bf3213f4f9ee04",
        "reconciliation_sha256": reconciliation["reconciliation_sha256"],
        "confirmed_authorization_blockers": blocking,
        "confirmed_authorization_blocker_count": len(blocking),
        "live_study_cells_run": 0,
        "effectiveness_data_inspected": False,
        "development_shakeout_allowed": False,
        "calibration_allowed": False,
        "instrument_tag_allowed": False,
        "automatic_2_1_3_allowed": False,
        "automatic_family_removal_allowed": False,
        "required_disposition": "terminate_current_11_family_program",
        "future_remediation_requirement": (
            "explicitly authorize a new protocol and independently versioned generator; "
            "do not mutate or relabel office-generators/2.1.2"
        ),
    }
    document["failure_sha256"] = _digest(document)
    return document


def validate_failure(document):
    expected = {
        "schema_version", "status", "generator_version", "protocol_version",
        "audited_commit_sha", "reconciliation_sha256",
        "confirmed_authorization_blockers",
        "confirmed_authorization_blocker_count", "live_study_cells_run",
        "effectiveness_data_inspected", "development_shakeout_allowed",
        "calibration_allowed", "instrument_tag_allowed",
        "automatic_2_1_3_allowed", "automatic_family_removal_allowed",
        "required_disposition", "future_remediation_requirement",
        "failure_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise ConstructGateFailureError("construct failure has unexpected keys")
    unsigned = dict(document)
    supplied = unsigned.pop("failure_sha256")
    if supplied != _digest(unsigned):
        raise ConstructGateFailureError("construct failure digest drifted")
    reconciliation = load_reconciliation()
    blockers = [
        item["finding_id"] for item in reconciliation["findings"]
        if item["blocks_authorization"]
    ]
    if (
        document["schema_version"] != SCHEMA_VERSION
        or document["status"] != "construct_gate_failed"
        or document["generator_version"] != "office-generators/2.1.2"
        or document["protocol_version"] != "1.4.0"
        or document["reconciliation_sha256"] != reconciliation["reconciliation_sha256"]
        or document["confirmed_authorization_blockers"] != blockers
        or document["confirmed_authorization_blocker_count"] != len(blockers)
        or len(blockers) == 0
        or document["live_study_cells_run"] != 0
        or document["effectiveness_data_inspected"] is not False
        or document["development_shakeout_allowed"] is not False
        or document["calibration_allowed"] is not False
        or document["instrument_tag_allowed"] is not False
        or document["automatic_2_1_3_allowed"] is not False
        or document["automatic_family_removal_allowed"] is not False
        or document["required_disposition"] != "terminate_current_11_family_program"
    ):
        raise ConstructGateFailureError("construct failure semantics drifted")
    return document


def load_failure(path=DEFAULT_PATH):
    return validate_failure(load_canonical_json(path))


def write_failure(path=DEFAULT_PATH):
    document = build_failure()
    validate_failure(document)
    replace_canonical_json(path, document)
    return document


if __name__ == "__main__":
    write_failure()


__all__ = [
    "ConstructGateFailureError", "DEFAULT_PATH", "SCHEMA_VERSION",
    "build_failure", "load_failure", "validate_failure", "write_failure",
]
