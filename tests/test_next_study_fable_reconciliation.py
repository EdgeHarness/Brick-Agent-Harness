import copy

import pytest

from bench.next_study_fable_reconciliation import (
    FableReconciliationError,
    build_pending,
    load_reconciliation,
    validate_reconciliation,
)
from harness.evidence import canonical_json_bytes
from harness.instances import sha256_bytes


def _reseal(document):
    document = copy.deepcopy(document)
    document.pop("reconciliation_sha256", None)
    document["reconciliation_sha256"] = sha256_bytes(
        canonical_json_bytes(document, allow_float=False)
    )
    return document


def _report(index, findings=0):
    return {
        "report_id": "fable-%d" % index,
        "model": "Fable 5",
        "source_content_sha256": ("%064x" % index),
        "reviewed_generator_version": "office-generators/2.1.0",
        "reviewed_case_count": 308,
        "findings_reported": findings,
    }


def test_pending_fable_reconciliation_is_valid_but_blocks_authorization():
    pending = load_reconciliation()
    assert pending["status"] == "pending_reports"
    assert pending["generator_version"] == "office-generators/2.1.2"
    assert len(pending["reports_received"]) == 1
    assert pending["reports_received"][0]["report_id"] == (
        "sunnycho100-consolidated-20260806"
    )
    assert pending["reports_received"][0]["findings_reported"] == 11
    assert len(pending["findings"]) == 11
    assert pending["unresolved_report_count"] == 2
    with pytest.raises(FableReconciliationError, match="remain unreconciled"):
        validate_reconciliation(pending, require_complete=True)


def test_three_fully_accounted_reports_close_only_the_advisory_qa_hold():
    complete = build_pending()
    complete["reports_received"] = [_report(index) for index in range(1, 4)]
    complete["unresolved_report_count"] = 0
    complete["status"] = "passed"
    complete["authorization_gate_passed"] = True
    complete = _reseal(complete)
    assert validate_reconciliation(complete, require_complete=True) == complete
    assert complete["advisory_reports_may_supply_outcomes"] is False
    assert complete["absence_of_flags_can_establish_validity"] is False


def test_reported_fable_finding_cannot_be_omitted_from_reconciliation():
    forged = build_pending()
    forged["reports_received"] = [
        _report(1, findings=1), _report(2), _report(3)
    ]
    forged["unresolved_report_count"] = 0
    forged["status"] = "passed"
    forged["authorization_gate_passed"] = True
    forged = _reseal(forged)
    with pytest.raises(FableReconciliationError, match="fully reconciled"):
        validate_reconciliation(forged, require_complete=True)


def test_duplicate_report_content_cannot_count_as_multiple_sessions():
    forged = build_pending()
    reports = [_report(index) for index in range(1, 4)]
    reports[2]["source_content_sha256"] = reports[1]["source_content_sha256"]
    forged["reports_received"] = reports
    forged["unresolved_report_count"] = 0
    forged["status"] = "passed"
    forged["authorization_gate_passed"] = True
    forged = _reseal(forged)
    with pytest.raises(FableReconciliationError, match="report record is invalid"):
        validate_reconciliation(forged, require_complete=True)
