"""Advisory-report reconciliation gate for the replacement freeze.

Advisory reports never supply outcomes or certify validity.  This artifact
proves that every promised report was received and every reported concern was
either converted into deterministic evidence or refuted reproducibly.  A
confirmed prompt/grader blocker closes the reconciliation but fails the
construct gate; report completeness must never be confused with a pass.
"""

import hashlib
from pathlib import Path
import re

from harness.evidence import canonical_json_bytes
from harness.instances import load_canonical_json, replace_canonical_json, sha256_bytes


SCHEMA_VERSION = "brick.next-study.fable-reconciliation/3"
DEFAULT_PATH = "evidence/next-study/office-v2-fable-reconciliation.json"
GENERATOR_VERSION = "office-generators/2.1.2"
SEED_NAMESPACE = "office-generators/2.1.0"
ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = Path("evidence/next-study/advisory-audits")


class FableReconciliationError(ValueError):
    pass


def _digest(value):
    return sha256_bytes(canonical_json_bytes(value, allow_float=False))


def _canonical_text_digest(path):
    payload = Path(path).read_bytes()
    try:
        payload = payload.decode("utf-8").replace("\r\n", "\n").encode("utf-8")
    except UnicodeDecodeError:
        pass
    return hashlib.sha256(payload).hexdigest()


def build_pending():
    document = {
        "schema_version": SCHEMA_VERSION,
        "status": "pending_reports",
        "generator_version": GENERATOR_VERSION,
        "seed_namespace": SEED_NAMESPACE,
        "invalidated_instrument_tag": "v0.13.0",
        "minimum_reports_required": 3,
        "reports_received": [],
        "findings": [],
        "unresolved_report_count": 3,
        "confirmed_authorization_blocker_count": 0,
        "authorization_gate_passed": False,
        "advisory_reports_may_supply_outcomes": False,
        "absence_of_flags_can_establish_validity": False,
        "live_model_calls": 0,
    }
    document["reconciliation_sha256"] = _digest(document)
    return document


def validate_reconciliation(document, require_complete=False):
    expected = {
        "schema_version", "status", "generator_version", "seed_namespace",
        "invalidated_instrument_tag", "minimum_reports_required",
        "reports_received", "findings", "unresolved_report_count",
        "confirmed_authorization_blocker_count", "authorization_gate_passed",
        "advisory_reports_may_supply_outcomes",
        "absence_of_flags_can_establish_validity", "live_model_calls",
        "reconciliation_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise FableReconciliationError("Fable reconciliation has unexpected keys")
    unsigned = dict(document)
    supplied = unsigned.pop("reconciliation_sha256")
    if supplied != _digest(unsigned):
        raise FableReconciliationError("Fable reconciliation digest drifted")
    reports = document["reports_received"]
    findings = document["findings"]
    if (
        document["schema_version"] != SCHEMA_VERSION
        or document["generator_version"] != GENERATOR_VERSION
        or document["seed_namespace"] != SEED_NAMESPACE
        or document["invalidated_instrument_tag"] != "v0.13.0"
        or document["minimum_reports_required"] != 3
        or not isinstance(reports, list)
        or not isinstance(findings, list)
        or type(document["unresolved_report_count"]) is not int
        or document["unresolved_report_count"] < 0
        or type(document["confirmed_authorization_blocker_count"]) is not int
        or document["confirmed_authorization_blocker_count"] < 0
        or document["advisory_reports_may_supply_outcomes"] is not False
        or document["absence_of_flags_can_establish_validity"] is not False
        or document["live_model_calls"] != 0
    ):
        raise FableReconciliationError("Fable reconciliation semantics drifted")
    report_ids = set()
    source_hashes = set()
    for report in reports:
        if (
            not isinstance(report, dict)
            or set(report) != {
                "report_id", "model", "source_path", "source_content_sha256",
                "reviewed_generator_version", "reviewed_case_count",
                "findings_reported",
            }
            or not isinstance(report["report_id"], str)
            or not report["report_id"].strip()
            or report["report_id"] in report_ids
            or not isinstance(report["model"], str)
            or not report["model"].strip()
            or not isinstance(report["source_path"], str)
            or Path(report["source_path"]).parent != REPORT_ROOT
            or re.fullmatch(r"[0-9a-f]{64}", report["source_content_sha256"] or "")
            is None
            or report["source_content_sha256"] in source_hashes
            or report["reviewed_generator_version"]
            not in (
                "office-generators/2.1.0", "office-generators/2.1.1",
                GENERATOR_VERSION,
            )
            or type(report["reviewed_case_count"]) is not int
            or report["reviewed_case_count"] < 1
            or type(report["findings_reported"]) is not int
            or report["findings_reported"] < 0
        ):
            raise FableReconciliationError("Fable report record is invalid")
        source = ROOT / report["source_path"]
        if not source.is_file() or _canonical_text_digest(source) != report["source_content_sha256"]:
            raise FableReconciliationError("Fable report source binding drifted")
        report_ids.add(report["report_id"])
        source_hashes.add(report["source_content_sha256"])
    finding_ids = set()
    for finding in findings:
        if (
            not isinstance(finding, dict)
            or set(finding) != {
                "finding_id", "report_ids", "case_ids", "severity",
                "blocks_authorization", "disposition",
                "deterministic_reproduction", "regression_test", "notes",
            }
            or not isinstance(finding["finding_id"], str)
            or not finding["finding_id"].strip()
            or finding["finding_id"] in finding_ids
            or not isinstance(finding["report_ids"], list)
            or not finding["report_ids"]
            or not set(finding["report_ids"]) <= report_ids
            or not isinstance(finding["case_ids"], list)
            or not all(isinstance(value, str) and value for value in finding["case_ids"])
            or finding["severity"] not in ("high", "medium", "low")
            or type(finding["blocks_authorization"]) is not bool
            or finding["disposition"] not in (
                "confirmed_with_regression", "refuted_with_reproduction"
            )
            or not isinstance(finding["deterministic_reproduction"], str)
            or not finding["deterministic_reproduction"].strip()
            or not isinstance(finding["notes"], str)
        ):
            raise FableReconciliationError("Fable finding record is invalid")
        if finding["blocks_authorization"] and finding["disposition"] != "confirmed_with_regression":
            raise FableReconciliationError("only confirmed findings may block authorization")
        if (
            finding["disposition"] == "confirmed_with_regression"
            and (
                not isinstance(finding["regression_test"], str)
                or not finding["regression_test"].strip()
            )
        ):
            raise FableReconciliationError("confirmed Fable finding lacks a regression")
        if (
            finding["disposition"] == "refuted_with_reproduction"
            and finding["regression_test"] is not None
        ):
            raise FableReconciliationError("refuted Fable finding names a regression")
        finding_ids.add(finding["finding_id"])
    for report in reports:
        mapped = sum(report["report_id"] in finding["report_ids"] for finding in findings)
        if mapped != report["findings_reported"]:
            raise FableReconciliationError("Fable report finding count is not fully reconciled")
    blockers = sum(finding["blocks_authorization"] for finding in findings)
    if blockers != document["confirmed_authorization_blocker_count"]:
        raise FableReconciliationError("Fable blocker count drifted")
    complete = (
        len(reports) >= document["minimum_reports_required"]
        and document["unresolved_report_count"] == 0
    )
    expected_status = (
        "construct_gate_failed" if complete and blockers
        else "passed" if complete
        else "pending_reports"
    )
    if document["status"] != expected_status:
        raise FableReconciliationError("Fable reconciliation status drifted")
    passed = complete and blockers == 0
    if document["authorization_gate_passed"] is not passed:
        raise FableReconciliationError("Fable authorization gate drifted")
    if require_complete and not complete:
        raise FableReconciliationError("Fable reports remain unreconciled")
    if require_complete and blockers:
        raise FableReconciliationError("Fable reconciliation construct gate failed")
    return document


def load_reconciliation(path=DEFAULT_PATH, require_complete=False):
    return validate_reconciliation(
        load_canonical_json(path), require_complete=require_complete
    )


def write_reconciliation(document, path=DEFAULT_PATH):
    unsigned = dict(document)
    unsigned.pop("reconciliation_sha256", None)
    unsigned["reconciliation_sha256"] = _digest(unsigned)
    validate_reconciliation(unsigned)
    replace_canonical_json(path, unsigned)
    return unsigned


__all__ = [
    "DEFAULT_PATH", "FableReconciliationError", "GENERATOR_VERSION",
    "SCHEMA_VERSION", "SEED_NAMESPACE", "build_pending",
    "load_reconciliation", "validate_reconciliation", "write_reconciliation",
]
