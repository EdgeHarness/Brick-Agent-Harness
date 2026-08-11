import copy

import pytest

from bench import llama8_product_validation as study
from bench import llama8_product_validation_verifier as verifier
from tests.test_llama8_product_validation import _analysis_for, _auth


def _self(document, field):
    document[field] = study._digest(document)
    return document


def _artifacts(monkeypatch):
    analysis = _analysis_for(monkeypatch, False, True)
    authorization = _self({"schema_version": study.AUTHORIZATION_SCHEMA}, "authorization_sha256")
    gate = _self({
        "gate_cells": 6,
    }, "gate_seal_sha256")
    seal = _self({
        "status": "sealed_complete_valid", "complete_final_cells": 126,
        "invalid_final_cells": 0, "physical_attempts": 126,
        "gate_seal_sha256": gate["gate_seal_sha256"],
    }, "seal_sha256")
    report = study._derive_report(_auth(), analysis, reported_at="2026-08-11T07:00:00+00:00")
    schedule = study.build_schedule()
    mapping = {
        str(study.SCHEDULE_PATH): schedule,
        str(study.AUTHORIZATION_PATH): authorization,
        str(study.GATE_SEAL_PATH): gate,
        str(study.SEAL_PATH): seal,
        str(study.ANALYSIS_PATH): analysis,
        str(study.REPORT_PATH): report,
    }
    monkeypatch.setattr(verifier, "_published", lambda path, _label: copy.deepcopy(mapping[str(path)]))
    monkeypatch.setattr(study, "validate_schedule", lambda document, protocol=None: document)
    monkeypatch.setattr(study, "validate_authorization", lambda document, protocol=None, validate_repository=False: document)
    monkeypatch.setattr(study, "validate_lifecycle", lambda _authorization: {"report_sha256": mapping[str(study.REPORT_PATH)]["report_sha256"]})
    return mapping


def test_separate_verifier_recomputes_headline_and_claim(monkeypatch):
    _artifacts(monkeypatch)
    document = verifier.verify(verified_at="2026-08-11T08:00:00+00:00")
    assert document["status"] == "verified_complete"
    assert document["headline_effect"]["fraction"] == "1/1"
    assert document["claim_rule_disposition"] == "sharvin_balanced_adapter_superiority"
    assert document["live_model_calls"] == 0


def test_separate_verifier_rejects_resigned_report_headline_tamper(monkeypatch):
    mapping = _artifacts(monkeypatch)
    report = mapping[str(study.REPORT_PATH)]
    report["answer"]["paired_effect"] = {"fraction": "0/1", "decimal": "0.000000000000"}
    report["report_sha256"] = study._digest({k: v for k, v in report.items() if k != "report_sha256"})
    with pytest.raises(verifier.VerificationError, match="headline"):
        verifier.verify(verified_at="2026-08-11T08:00:00+00:00")


def test_separate_verifier_rejects_resigned_operational_count_tamper(monkeypatch):
    mapping = _artifacts(monkeypatch)
    analysis = mapping[str(study.ANALYSIS_PATH)]
    report = mapping[str(study.REPORT_PATH)]
    analysis["operational_attempts"]["all_authorized"]["physical_attempts"] = 125
    analysis["operational_attempts"]["primary"]["physical_attempts"] = 119
    analysis["analysis_sha256"] = study._digest({
        key: value for key, value in analysis.items() if key != "analysis_sha256"
    })
    report["analysis_sha256"] = analysis["analysis_sha256"]
    report["operational_attempts"] = copy.deepcopy(analysis["operational_attempts"])
    report["report_sha256"] = study._digest({
        key: value for key, value in report.items() if key != "report_sha256"
    })
    with pytest.raises(verifier.VerificationError, match="operational-attempt"):
        verifier.verify(verified_at="2026-08-11T08:00:00+00:00")
