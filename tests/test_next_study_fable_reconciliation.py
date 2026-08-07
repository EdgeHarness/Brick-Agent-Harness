import copy

import pytest

from bench.next_study_fable_reconciliation import (
    FableReconciliationError,
    load_reconciliation,
    validate_reconciliation,
)
from bench.next_study_construct_failure import load_failure
from harness.evidence import canonical_json_bytes
from harness.instances import sha256_bytes


def _reseal(document):
    document = copy.deepcopy(document)
    document.pop("reconciliation_sha256", None)
    document["reconciliation_sha256"] = sha256_bytes(
        canonical_json_bytes(document, allow_float=False)
    )
    return document


def test_three_reports_are_complete_but_terminally_block_authorization():
    document = load_reconciliation()
    assert document["status"] == "construct_gate_failed"
    assert document["generator_version"] == "office-generators/2.1.2"
    assert len(document["reports_received"]) == 4
    assert {item["findings_reported"] for item in document["reports_received"]} == {
        1, 10, 11, 16
    }
    assert len(document["findings"]) == 37
    assert document["unresolved_report_count"] == 0
    assert document["confirmed_authorization_blocker_count"] == 10
    assert document["authorization_gate_passed"] is False
    with pytest.raises(FableReconciliationError, match="construct gate failed"):
        validate_reconciliation(document, require_complete=True)


def test_complete_reports_pass_only_when_no_confirmed_blocker_exists():
    complete = load_reconciliation()
    for finding in complete["findings"]:
        finding["blocks_authorization"] = False
    complete["confirmed_authorization_blocker_count"] = 0
    complete["status"] = "passed"
    complete["authorization_gate_passed"] = True
    complete = _reseal(complete)
    assert validate_reconciliation(complete, require_complete=True) == complete
    assert complete["advisory_reports_may_supply_outcomes"] is False
    assert complete["absence_of_flags_can_establish_validity"] is False


def test_reported_finding_cannot_be_omitted_from_reconciliation():
    forged = load_reconciliation()
    forged["findings"].pop()
    forged = _reseal(forged)
    with pytest.raises(FableReconciliationError, match="fully reconciled"):
        validate_reconciliation(forged)


def test_duplicate_report_content_cannot_count_as_multiple_sessions():
    forged = load_reconciliation()
    forged["reports_received"][2]["source_content_sha256"] = (
        forged["reports_received"][1]["source_content_sha256"]
    )
    forged = _reseal(forged)
    with pytest.raises(FableReconciliationError, match="report record is invalid"):
        validate_reconciliation(forged)


def test_report_bytes_are_part_of_the_gate():
    forged = load_reconciliation()
    forged["reports_received"][1]["source_content_sha256"] = "0" * 64
    forged = _reseal(forged)
    with pytest.raises(FableReconciliationError, match="source binding drifted"):
        validate_reconciliation(forged)


def test_terminal_failure_binds_reconciliation_and_forbids_live_transitions():
    failure = load_failure()
    reconciliation = load_reconciliation()
    assert failure["reconciliation_sha256"] == reconciliation["reconciliation_sha256"]
    assert failure["confirmed_authorization_blocker_count"] == 10
    assert failure["development_shakeout_allowed"] is False
    assert failure["calibration_allowed"] is False
    assert failure["instrument_tag_allowed"] is False
    assert failure["automatic_2_1_3_allowed"] is False
    assert failure["required_disposition"] == "terminate_current_11_family_program"
