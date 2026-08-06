"""Evidence-bound study report generation for the successor program."""

import copy

from harness.evidence import canonical_json_bytes
from harness.instances import sha256_bytes

from .next_study_claim import load_claim_contract
from .next_study_descriptive import REPORT_SCHEMA as DESCRIPTIVE_REPORT_SCHEMA
from .next_study_program import validate_authorization, validate_program_state
from .next_study_statistics import (
    GRADE_LEDGER_SCHEMA, PRIMARY_ANALYSIS_SCHEMA,
)


STUDY_REPORT_SCHEMA = "brick.next-study.study-report/1"
FAILURE_TAXONOMY_SCHEMA = "brick.next-study.failure-taxonomy/1"
RESOURCE_REPORT_SCHEMA = "brick.next-study.resource-report/1"
PROGRAM_BINDINGS_SCHEMA = "brick.next-study.report-program-bindings/1"


class NextStudyReportError(ValueError):
    pass


def _digest(value):
    return sha256_bytes(canonical_json_bytes(value, allow_float=False))


def _artifact_digest(value):
    return sha256_bytes(
        canonical_json_bytes(value, allow_float=False, newline=True)
    )


def build_failure_taxonomy(grade_ledger):
    if (
        not isinstance(grade_ledger, dict)
        or grade_ledger.get("schema_version") != GRADE_LEDGER_SCHEMA
        or grade_ledger.get("status") != "sealed_complete"
        or grade_ledger.get("cell_count") != 880
        or not isinstance(grade_ledger.get("records"), list)
        or len(grade_ledger["records"]) != 880
    ):
        raise NextStudyReportError("failure taxonomy requires the sealed primary ledger")
    categories = {
        "strict_success": 0,
        "completed_execution_strict_failure": 0,
        "model_terminal_failure": 0,
    }
    by_family = {}
    by_condition = {}
    for record in grade_ledger["records"]:
        if (
            record.get("condition") not in ("native_tools", "harness_full")
            or record.get("outcome_origin") not in (
                "completed", "model_terminal_failure",
            )
            or type(record.get("strict_success")) is not bool
            or not isinstance(record.get("family"), str)
        ):
            raise NextStudyReportError("failure taxonomy input record is invalid")
        if record["strict_success"]:
            if record["outcome_origin"] != "completed":
                raise NextStudyReportError("terminal model failure cannot be successful")
            category = "strict_success"
        elif record["outcome_origin"] == "model_terminal_failure":
            category = "model_terminal_failure"
        else:
            category = "completed_execution_strict_failure"
        categories[category] += 1
        for mapping, key in (
            (by_family, record["family"]),
            (by_condition, record["condition"]),
        ):
            counts = mapping.setdefault(key, {name: 0 for name in categories})
            counts[category] += 1
    document = {
        "schema_version": FAILURE_TAXONOMY_SCHEMA,
        "primary_grade_ledger_sha256": _digest(grade_ledger),
        "cell_count": 880,
        "categories": categories,
        "by_family": dict(sorted(by_family.items())),
        "by_condition": dict(sorted(by_condition.items())),
        "interpretation": (
            "Execution-origin categories only; they do not infer a causal failure mechanism."
        ),
    }
    document["failure_taxonomy_sha256"] = _digest(document)
    return document


def build_resource_report(descriptive_report):
    if (
        not isinstance(descriptive_report, dict)
        or descriptive_report.get("schema_version") != DESCRIPTIVE_REPORT_SCHEMA
        or descriptive_report.get("status") != "complete"
    ):
        raise NextStudyReportError("resource report requires complete descriptives")
    unsigned = dict(descriptive_report)
    supplied = unsigned.pop("descriptive_report_sha256", None)
    if supplied != _digest(unsigned):
        raise NextStudyReportError("descriptive report digest drifted")
    document = {
        "schema_version": RESOURCE_REPORT_SCHEMA,
        "descriptive_report_sha256": supplied,
        "eligible_cells": descriptive_report["eligible_cells"],
        "completed_cells": descriptive_report["completed_cells"],
        "removed_blocks": copy.deepcopy(descriptive_report["removed_blocks"]),
        "condition_summaries": copy.deepcopy(
            descriptive_report["condition_summaries"]
        ),
        "unknown_tokens_imputed": descriptive_report["unknown_tokens_imputed"],
        "synthetic_resource_score": descriptive_report["synthetic_resource_score"],
    }
    document["resource_report_sha256"] = _digest(document)
    return document


def build_program_bindings(
    authorization, program_state, primary_analysis, descriptive_report,
):
    validate_authorization(authorization)
    validate_program_state(program_state)
    if (
        program_state["authorization_sha256"]
        != authorization["authorization_sha256"]
        or program_state["current_phase"] != "release"
        or program_state["completed_phases"] != [
            "calibration", "sentinel", "primary", "primary_analysis",
            "descriptives",
        ]
    ):
        raise NextStudyReportError("program bindings require the release-ready state")
    gates = {gate["phase"]: gate for gate in program_state["sealed_phase_gates"]}
    if (
        gates["primary_analysis"]["sealed_artifact_sha256"]
        != _digest(primary_analysis)
        or gates["descriptives"]["sealed_artifact_sha256"]
        != _digest(descriptive_report)
    ):
        raise NextStudyReportError("report inputs differ from sealed phase gates")
    document = {
        "schema_version": PROGRAM_BINDINGS_SCHEMA,
        "authorization_sha256": authorization["authorization_sha256"],
        "execution_context": copy.deepcopy(authorization["execution_context"]),
        "schedule_digests": copy.deepcopy(authorization["schedule_digests"]),
        "primary_analysis_gate_sha256": gates["primary_analysis"][
            "sealed_artifact_sha256"
        ],
        "descriptives_gate_sha256": gates["descriptives"][
            "sealed_artifact_sha256"
        ],
        "phase_gate_history_sha256": _digest(program_state["sealed_phase_gates"]),
    }
    document["program_bindings_sha256"] = _digest(document)
    return document


def build_study_report(
    primary_analysis, descriptive_report, manifest_lock, grade_ledger,
    authorization, program_state, limitations,
):
    """Build the report without accepting a caller-supplied claim."""

    claim_contract = load_claim_contract()
    if primary_analysis.get("schema_version") != PRIMARY_ANALYSIS_SCHEMA:
        raise NextStudyReportError("study report requires primary-analysis/3")
    if descriptive_report.get("schema_version") != DESCRIPTIVE_REPORT_SCHEMA:
        raise NextStudyReportError("study report requires descriptive-report/3")
    if primary_analysis.get("execution_context") != descriptive_report.get("execution_context"):
        raise NextStudyReportError("study report execution contexts disagree")
    if (
        not isinstance(manifest_lock, dict)
        or manifest_lock.get("balance_review", {}).get("passed") is not True
        or _artifact_digest(manifest_lock)
        != authorization.get("artifact_digests", {}).get("manifest_lock")
    ):
        raise NextStudyReportError("study report requires a passed burden audit")
    burden_audit = manifest_lock["balance_review"]
    if primary_analysis.get("primary_grade_ledger_sha256") != _digest(grade_ledger):
        raise NextStudyReportError("study report primary-ledger binding drifted")
    if (
        primary_analysis.get("execution_context")
        != authorization.get("execution_context")
    ):
        raise NextStudyReportError("study report execution context is unauthorized")
    if not isinstance(limitations, list) or not all(
        isinstance(item, str) and item.strip() for item in limitations
    ):
        raise NextStudyReportError("limitations must be nonempty strings")
    mandatory = (
        "This result is limited to the fixed eleven-family synthetic benchmark; "
        "generalized real-world performance was not established."
    )
    burden_limitation = (
        "Condition opportunity slack is asymmetric by task family; in "
        "preference_learning the executable lower bounds are 5 native requests "
        "and 10 harness requests under the shared cap of 18."
    )
    merged_limitations = list(limitations)
    for value in (mandatory, burden_limitation):
        if value not in merged_limitations:
            merged_limitations.append(value)
    failure_taxonomy = build_failure_taxonomy(grade_ledger)
    resource_report = build_resource_report(descriptive_report)
    program_bindings = build_program_bindings(
        authorization, program_state, primary_analysis, descriptive_report,
    )
    document = {
        "schema_version": STUDY_REPORT_SCHEMA,
        "execution_context": copy.deepcopy(primary_analysis["execution_context"]),
        "scope": claim_contract["scope"],
        "claim_disposition": primary_analysis["claim_disposition"],
        "paired_effect": primary_analysis["paired_effect"],
        "cluster_bootstrap_95_interval": copy.deepcopy(
            primary_analysis["cluster_bootstrap_95_interval"]
        ),
        "sign_flip_role": "diagnostic_only",
        "primary_analysis_sha256": _digest(primary_analysis),
        "descriptive_report_sha256": _digest(descriptive_report),
        "burden_audit_sha256": _digest(burden_audit),
        "manifest_lock_sha256": _artifact_digest(manifest_lock),
        "resource_report_sha256": resource_report["resource_report_sha256"],
        "failure_taxonomy": copy.deepcopy(failure_taxonomy),
        "limitations": merged_limitations,
        "program_bindings": copy.deepcopy(program_bindings),
        "descriptives_may_alter_primary_claim": False,
    }
    document["study_report_sha256"] = _digest(document)
    return document, resource_report, failure_taxonomy, program_bindings


def validate_study_report(document):
    expected = {
        "schema_version", "execution_context", "scope", "claim_disposition",
        "paired_effect", "cluster_bootstrap_95_interval", "sign_flip_role",
        "primary_analysis_sha256", "descriptive_report_sha256",
        "burden_audit_sha256", "manifest_lock_sha256",
        "resource_report_sha256", "failure_taxonomy", "limitations",
        "program_bindings", "descriptives_may_alter_primary_claim",
        "study_report_sha256",
    }
    if (
        not isinstance(document, dict)
        or set(document) != expected
        or document.get("schema_version") != STUDY_REPORT_SCHEMA
    ):
        raise NextStudyReportError("study report schema drifted")
    unsigned = dict(document)
    supplied = unsigned.pop("study_report_sha256", None)
    if supplied != _digest(unsigned):
        raise NextStudyReportError("study report digest drifted")
    if document.get("sign_flip_role") != "diagnostic_only":
        raise NextStudyReportError("study report promoted sign flip into the claim")
    if document.get("descriptives_may_alter_primary_claim") is not False:
        raise NextStudyReportError("descriptives altered the primary claim")
    taxonomy = document.get("failure_taxonomy")
    taxonomy_unsigned = dict(taxonomy) if isinstance(taxonomy, dict) else {}
    taxonomy_digest = taxonomy_unsigned.pop("failure_taxonomy_sha256", None)
    bindings = document.get("program_bindings")
    bindings_unsigned = dict(bindings) if isinstance(bindings, dict) else {}
    bindings_digest = bindings_unsigned.pop("program_bindings_sha256", None)
    if (
        taxonomy_digest != _digest(taxonomy_unsigned)
        or bindings_digest != _digest(bindings_unsigned)
        or not isinstance(document.get("limitations"), list)
        or not all(
            isinstance(item, str) and item.strip()
            for item in document["limitations"]
        )
    ):
        raise NextStudyReportError("study report support bindings drifted")
    return document


__all__ = [
    "FAILURE_TAXONOMY_SCHEMA", "PROGRAM_BINDINGS_SCHEMA",
    "RESOURCE_REPORT_SCHEMA", "STUDY_REPORT_SCHEMA", "NextStudyReportError",
    "build_failure_taxonomy", "build_program_bindings", "build_resource_report",
    "build_study_report", "validate_study_report",
]
