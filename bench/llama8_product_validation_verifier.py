"""Separate read-only verifier for the Llama 8B product-validation release.

The verifier reopens every marker-last lifecycle artifact, asks the production
module to rederive evidence-bound semantics, and independently recomputes the
headline arithmetic and claim-rule disposition from the sealed analysis.  It
does not run models, mutate EvidenceStore candidates, or broaden any claim.
"""

from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import sys

from bench import llama8_product_validation as study
from harness.evidence import canonical_json_bytes
from harness.instances import load_canonical_json, sha256_bytes


SCHEMA = "brick.llama8-product-validation.separate-verification/1"
DEFAULT_OUTPUT = study.RUNS_ROOT / "verification.json"


class VerificationError(ValueError):
    pass


def _fraction(record, label):
    if not isinstance(record, dict) or set(record) != {"fraction", "decimal"}:
        raise VerificationError(label + " is not an exact fraction record")
    try:
        numerator, denominator = record["fraction"].split("/", 1)
        value = Fraction(int(numerator), int(denominator))
    except (AttributeError, ValueError, ZeroDivisionError) as exc:
        raise VerificationError(label + " fraction is invalid") from exc
    if format(float(value), ".12f") != record["decimal"]:
        raise VerificationError(label + " decimal differs from its fraction")
    return value


def _published(path, label):
    path = Path(path)
    marker = path.with_name(path.name + ".complete")
    if not path.is_file() or not marker.is_file() or marker.stat().st_size != 0:
        raise VerificationError(label + " is not marker-last complete")
    try:
        return load_canonical_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise VerificationError(label + " is not canonical JSON") from exc


def _self_digest(document, field, label):
    if not isinstance(document, dict) or field not in document:
        raise VerificationError(label + " lacks its self digest")
    unsigned = dict(document)
    supplied = unsigned.pop(field)
    if supplied != sha256_bytes(canonical_json_bytes(unsigned, allow_float=False)):
        raise VerificationError(label + " self digest drifted")
    return supplied


def verify(*, verified_at=None):
    protocol = study.load_protocol()
    schedule = _published(study.SCHEDULE_PATH, "schedule")
    authorization = _published(study.AUTHORIZATION_PATH, "authorization")
    gate = _published(study.GATE_SEAL_PATH, "gate seal")
    seal = _published(study.SEAL_PATH, "final seal")
    analysis = _published(study.ANALYSIS_PATH, "analysis")
    report = _published(study.REPORT_PATH, "report")

    study.validate_schedule(schedule, protocol)
    study.validate_authorization(authorization, protocol, validate_repository=True)
    lifecycle = study.validate_lifecycle(authorization)
    if lifecycle.get("report_sha256") != report.get("report_sha256"):
        raise VerificationError("lifecycle report binding drifted")

    for document, field, label in (
        (authorization, "authorization_sha256", "authorization"),
        (gate, "gate_seal_sha256", "gate seal"),
        (seal, "seal_sha256", "final seal"),
        (analysis, "analysis_sha256", "analysis"),
        (report, "report_sha256", "report"),
    ):
        _self_digest(document, field, label)

    if (
        len(schedule["records"]) != 126
        or sum(cell["phase"] == "instrument_gate" for cell in schedule["records"]) != 6
        or sum(cell["phase"] == "primary" for cell in schedule["records"]) != 120
        or gate["gate_cells"] != 6
        or seal["status"] != "sealed_complete_valid"
        or seal["complete_final_cells"] != 126
        or seal["invalid_final_cells"] != 0
        or seal["gate_seal_sha256"] != gate["gate_seal_sha256"]
    ):
        raise VerificationError("schedule or seal completeness drifted")

    family_results = analysis["family_results"]
    if set(family_results) != set(study.FAMILIES):
        raise VerificationError("analysis family set drifted")
    family_effects = []
    native_total = treatment_total = 0
    for family in study.FAMILIES:
        result = family_results[family]
        if result["paired_clusters"] != 20:
            raise VerificationError("family paired denominator drifted")
        native = result["native_tools_successes"]
        treatment = result["sharvin_balanced_adapter_successes"]
        if any(type(value) is not int or not 0 <= value <= 20 for value in (native, treatment)):
            raise VerificationError("family success count is invalid")
        expected_effect = Fraction(treatment - native, 20)
        if _fraction(result["paired_effect"], family + " effect") != expected_effect:
            raise VerificationError("family effect arithmetic drifted")
        family_effects.append(expected_effect)
        native_total += native
        treatment_total += treatment
    effect = sum(family_effects, Fraction(0, 1)) / 3
    if _fraction(analysis["paired_effect"], "paired effect") != effect:
        raise VerificationError("equal-family effect arithmetic drifted")
    if analysis["condition_results"]["native_tools"]["successes"] != native_total:
        raise VerificationError("native total differs from family results")
    if analysis["condition_results"]["sharvin_balanced_adapter"]["successes"] != treatment_total:
        raise VerificationError("treatment total differs from family results")
    lower = _fraction(analysis["bootstrap_95_percent_interval"]["lower"], "CI lower")
    upper = _fraction(analysis["bootstrap_95_percent_interval"]["upper"], "CI upper")
    if lower > upper:
        raise VerificationError("bootstrap interval is reversed")
    threshold = Fraction(12, 100)
    expected_disposition = (
        "sharvin_balanced_adapter_superiority"
        if effect >= threshold and lower > 0 else
        "native_tools_superiority"
        if effect <= -threshold and upper < 0 else
        "no_directional_superiority_claim"
    )
    if analysis["claim_rule"]["disposition"] != expected_disposition:
        raise VerificationError("claim-rule disposition arithmetic drifted")
    if report["answer"]["disposition"] != expected_disposition or report["answer"]["paired_effect"] != analysis["paired_effect"]:
        raise VerificationError("report headline differs from sealed analysis")
    operational = analysis["operational_attempts"]
    if set(operational) != {"all_authorized", "instrument_gate", "primary"}:
        raise VerificationError("operational-attempt scope drifted")
    metric_keys = {
        "physical_attempts", "repeat_1_same_seed_retries",
        "environment_invalid_physical_attempts",
        "instrument_invalid_physical_attempts",
    }
    for scope in operational.values():
        if set(scope) != metric_keys or any(type(value) is not int or value < 0 for value in scope.values()):
            raise VerificationError("operational-attempt metrics are invalid")
    for key in metric_keys:
        if operational["all_authorized"][key] != (
            operational["instrument_gate"][key] + operational["primary"][key]
        ):
            raise VerificationError("operational-attempt phase arithmetic drifted")
    if (
        operational["all_authorized"]["physical_attempts"] != seal["physical_attempts"]
        or operational["all_authorized"]["repeat_1_same_seed_retries"] != (
            operational["all_authorized"]["physical_attempts"] - 126
        )
        or operational["all_authorized"]["environment_invalid_physical_attempts"]
        != operational["all_authorized"]["repeat_1_same_seed_retries"]
        or operational["all_authorized"]["instrument_invalid_physical_attempts"] != 0
        or report["operational_attempts"] != operational
    ):
        raise VerificationError("operational-attempt evidence binding drifted")
    if report["never_claim"] != protocol["reporting"]["never_claim"]:
        raise VerificationError("report claim lock drifted")

    document = {
        "schema_version": SCHEMA,
        "status": "verified_complete",
        "verification_mode": "separate_entrypoint_read_only_rederivation",
        "verified_at": verified_at or study._utcnow(),
        "authorization_sha256": authorization["authorization_sha256"],
        "gate_seal_sha256": gate["gate_seal_sha256"],
        "seal_sha256": seal["seal_sha256"],
        "analysis_sha256": analysis["analysis_sha256"],
        "report_sha256": report["report_sha256"],
        "protocol_sha256": study.protocol_sha256(protocol),
        "schedule_sha256": study._digest(schedule),
        "headline_effect": analysis["paired_effect"],
        "claim_rule_disposition": expected_disposition,
        "live_model_calls": 0,
    }
    document["verification_sha256"] = sha256_bytes(canonical_json_bytes(document))
    return document


def publish(output=DEFAULT_OUTPUT):
    output = Path(output)
    if output.resolve() != DEFAULT_OUTPUT.resolve():
        raise VerificationError("verification output path is fixed")
    document = verify()
    study._publish_or_recover_marker_last(output, document, "separate verification")
    return document


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    try:
        document = publish(args.output)
    except (VerificationError, study.Llama8ProductValidationError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"status": document["status"], "verification_sha256": document["verification_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
