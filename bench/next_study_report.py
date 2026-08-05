"""Evidence-bound study report generation for the successor program."""

import copy

from harness.evidence import canonical_json_bytes
from harness.instances import sha256_bytes

from .next_study_claim import load_claim_contract
from .next_study_descriptive import REPORT_SCHEMA as DESCRIPTIVE_REPORT_SCHEMA
from .next_study_statistics import PRIMARY_ANALYSIS_SCHEMA


STUDY_REPORT_SCHEMA = "brick.next-study.study-report/1"


class NextStudyReportError(ValueError):
    pass


def _digest(value):
    return sha256_bytes(canonical_json_bytes(value, allow_float=False))


def build_study_report(
    primary_analysis, descriptive_report, burden_audit, failure_taxonomy,
    limitations, program_bindings,
):
    """Build the report without accepting a caller-supplied claim."""

    claim_contract = load_claim_contract()
    if primary_analysis.get("schema_version") != PRIMARY_ANALYSIS_SCHEMA:
        raise NextStudyReportError("study report requires primary-analysis/2")
    if descriptive_report.get("schema_version") != DESCRIPTIVE_REPORT_SCHEMA:
        raise NextStudyReportError("study report requires descriptive-report/2")
    if primary_analysis.get("execution_context") != descriptive_report.get("execution_context"):
        raise NextStudyReportError("study report execution contexts disagree")
    if not isinstance(burden_audit, dict) or burden_audit.get("passed") is not True:
        raise NextStudyReportError("study report requires a passed burden audit")
    if not isinstance(failure_taxonomy, dict):
        raise NextStudyReportError("failure taxonomy must be an object")
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
    if not isinstance(program_bindings, dict) or not program_bindings:
        raise NextStudyReportError("program bindings are empty")
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
        "failure_taxonomy": copy.deepcopy(failure_taxonomy),
        "limitations": merged_limitations,
        "program_bindings": copy.deepcopy(program_bindings),
        "descriptives_may_alter_primary_claim": False,
    }
    document["study_report_sha256"] = _digest(document)
    return document


def validate_study_report(document):
    if not isinstance(document, dict) or document.get("schema_version") != STUDY_REPORT_SCHEMA:
        raise NextStudyReportError("study report schema drifted")
    unsigned = dict(document)
    supplied = unsigned.pop("study_report_sha256", None)
    if supplied != _digest(unsigned):
        raise NextStudyReportError("study report digest drifted")
    if document.get("sign_flip_role") != "diagnostic_only":
        raise NextStudyReportError("study report promoted sign flip into the claim")
    if document.get("descriptives_may_alter_primary_claim") is not False:
        raise NextStudyReportError("descriptives altered the primary claim")
    return document


__all__ = [
    "STUDY_REPORT_SCHEMA", "NextStudyReportError", "build_study_report",
    "validate_study_report",
]
