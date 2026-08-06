"""Descriptive-only eligibility, controls, and resource-frontier reporting."""

from collections import defaultdict
import copy
from fractions import Fraction
import re

from harness.evidence import canonical_json_bytes
from harness.instances import sha256_bytes
from .next_study_statistics import GRADE_LEDGER_SCHEMA, PRIMARY_ANALYSIS_SCHEMA


REPORT_SCHEMA = "brick.next-study.descriptive-report/3"
EVIDENCE_SCHEMA = "brick.next-study.descriptive-evidence/1"
ELIGIBILITY_SCHEMA = "brick.next-study.descriptive-eligibility/1"
CONTROLS_SCHEMA = "brick.next-study.descriptive-controls/1"


class NextStudyDescriptiveError(ValueError):
    pass


def _digest(value):
    return sha256_bytes(canonical_json_bytes(value, allow_float=False))


def _sha256(value, label):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise NextStudyDescriptiveError("%s must be lowercase SHA-256 hex" % label)
    return value


def seal_descriptive_eligibility(primary_analysis, grade_ledger, schedule):
    if (
        not isinstance(primary_analysis, dict)
        or primary_analysis.get("schema_version") != PRIMARY_ANALYSIS_SCHEMA
        or not isinstance(grade_ledger, dict)
        or grade_ledger.get("schema_version") != GRADE_LEDGER_SCHEMA
        or grade_ledger.get("status") != "sealed_complete"
        or not isinstance(schedule, dict)
        or schedule.get("blocked_until") != "sealed_primary_analysis"
        or schedule.get("logical_cell_count") != 222
    ):
        raise NextStudyDescriptiveError("descriptive eligibility requires sealed primary inputs")
    if primary_analysis.get("protocol_version") != grade_ledger.get("protocol_version"):
        raise NextStudyDescriptiveError("primary analysis protocol binding drifted")
    if primary_analysis.get("primary_grade_ledger_sha256") != _digest(grade_ledger):
        raise NextStudyDescriptiveError("primary analysis grade-ledger binding drifted")
    if primary_analysis.get("primary_schedule_sha256") != grade_ledger.get("schedule_sha256"):
        raise NextStudyDescriptiveError("primary analysis schedule binding drifted")
    if primary_analysis.get("execution_context") != grade_ledger.get("execution_context"):
        raise NextStudyDescriptiveError("primary execution context binding drifted")
    document = {
        "schema_version": ELIGIBILITY_SCHEMA,
        "execution_context": copy.deepcopy(primary_analysis["execution_context"]),
        "status": "sealed_primary_analysis",
        "protocol_version": primary_analysis["protocol_version"],
        "primary_analysis_sha256": _digest(primary_analysis),
        "primary_grade_ledger_sha256": _digest(grade_ledger),
        "descriptive_selection_sha256": schedule["selection_sha256"],
        "descriptives_may_run": True,
    }
    document["eligibility_sha256"] = _digest(document)
    return document


def _validate_eligibility(binding, schedule):
    expected = {
        "schema_version", "status", "protocol_version",
        "primary_analysis_sha256", "primary_grade_ledger_sha256",
        "descriptive_selection_sha256", "descriptives_may_run",
        "eligibility_sha256", "execution_context",
    }
    if not isinstance(binding, dict) or set(binding) != expected:
        raise NextStudyDescriptiveError("descriptive eligibility has unexpected keys")
    unsigned = dict(binding)
    supplied = unsigned.pop("eligibility_sha256")
    _sha256(supplied, "descriptive eligibility digest")
    if supplied != _digest(unsigned):
        raise NextStudyDescriptiveError("descriptive eligibility digest drifted")
    for field in (
        "primary_analysis_sha256", "primary_grade_ledger_sha256",
        "descriptive_selection_sha256",
    ):
        _sha256(binding[field], field)
    if (
        binding["schema_version"] != ELIGIBILITY_SCHEMA
        or binding["status"] != "sealed_primary_analysis"
        or binding["descriptives_may_run"] is not True
        or binding["protocol_version"] != schedule.get("protocol_version")
        or binding["descriptive_selection_sha256"] != schedule.get("selection_sha256")
    ):
        raise NextStudyDescriptiveError("descriptive eligibility binding drifted")
    return binding


def extract_descriptive_results(eligible, attempts):
    """Project resource rows solely from sealed attempt-record/2 evidence."""

    scheduled = {item["logical_cell_id"]: item for item in eligible.get("records", [])}
    if len(scheduled) != eligible.get("eligible_cells"):
        raise NextStudyDescriptiveError("eligible schedule contains duplicate cells")
    by_cell = defaultdict(list)
    for attempt in attempts:
        if attempt.get("schema_version") != "brick.next-study.attempt-record/2":
            raise NextStudyDescriptiveError("descriptive input is not attempt-record/2")
        logical_id = attempt.get("logical_cell_id")
        if logical_id not in scheduled:
            raise NextStudyDescriptiveError("descriptive attempt is unscheduled")
        by_cell[logical_id].append(attempt)
    rows = []
    for logical_id, values in sorted(by_cell.items()):
        values = sorted(values, key=lambda item: item["repeat"])
        if len(values) > 2 or [item["repeat"] for item in values] not in ([0], [0, 1]):
            raise NextStudyDescriptiveError("descriptive recovery sequence is invalid")
        final = values[-1]
        if final["failure_origin"] in ("environment", "instrument"):
            continue
        rows.append({
            "logical_cell_id": logical_id,
            "status": "complete" if final["failure_origin"] == "none" else "failed",
            "strict_success": final["strict_success"],
            "model_calls": final["model_calls"],
            "successful_reads": final["successful_reads"],
            "successful_mutations": final["successful_mutations"],
            "generated_tokens_exact": final["generated_tokens_exact"],
            "generated_tokens_lower_bound": final["generated_tokens_lower_bound"],
            "generated_tokens_upper_bound": final["generated_tokens_upper_bound"],
            "model_time_ms": final["model_time_ms"],
            "wall_time_ms": final["wall_time_ms"],
        })
    document = {
        "schema_version": EVIDENCE_SCHEMA,
        "eligibility_sha256": eligible["eligibility_sha256"],
        "scheduled_cells": len(scheduled),
        "completed_cells": len(rows),
        "records": rows,
    }
    document["evidence_sha256"] = _digest(document)
    return document


def eligible_schedule(schedule, model_preflight, primary_analysis_binding):
    if (
        not isinstance(schedule, dict) or schedule.get("logical_cell_count") != 222
        or schedule.get("blocked_until") != "sealed_primary_analysis"
        or not isinstance(schedule.get("records"), list)
        or len(schedule["records"]) != 222
    ):
        raise NextStudyDescriptiveError("descriptive schedule is invalid")
    _validate_eligibility(primary_analysis_binding, schedule)
    if set(model_preflight) != {"2b", "4b", "9b"} or any(
        type(value) is not bool for value in model_preflight.values()
    ):
        raise NextStudyDescriptiveError("descriptive preflight must name boolean 2b/4b/9b")
    if model_preflight["4b"] is not True:
        raise NextStudyDescriptiveError("primary 4B model drift terminates authorization")
    removed = []
    records = []
    for record in schedule["records"]:
        if record["model_role"] in ("2b", "9b") and not model_preflight[record["model_role"]]:
            removed.append(record["block"])
            continue
        records.append(copy.deepcopy(record))
    document = {
        "status": "eligible_after_sealed_primary_analysis",
        "phase": "descriptives",
        "execution_context": copy.deepcopy(
            primary_analysis_binding["execution_context"]
        ),
        "eligibility_sha256": primary_analysis_binding["eligibility_sha256"],
        "authorized_schedule_sha256": _digest(schedule),
        "selection_sha256": schedule["selection_sha256"],
        "planned_cells": schedule["logical_cell_count"],
        "eligible_cells": len(records),
        "logical_cell_count": len(records),
        "maximum_physical_attempts": len(records) * 2,
        "removed_blocks": sorted(set(removed)),
        "substitute_models": [],
        "records": records,
    }
    return validate_eligible_schedule(document, schedule)


def validate_eligible_schedule(document, authorized_schedule):
    expected_keys = {
        "status", "phase", "execution_context", "eligibility_sha256",
        "authorized_schedule_sha256", "selection_sha256", "planned_cells",
        "eligible_cells", "logical_cell_count", "maximum_physical_attempts",
        "removed_blocks", "substitute_models", "records",
    }
    if (
        not isinstance(document, dict)
        or set(document) != expected_keys
        or document.get("status") != "eligible_after_sealed_primary_analysis"
        or document.get("phase") != "descriptives"
        or document.get("authorized_schedule_sha256") != _digest(authorized_schedule)
        or document.get("selection_sha256")
        != authorized_schedule.get("selection_sha256")
        or document.get("planned_cells") != 222
        or document.get("eligible_cells")
        not in (134, 178, 222)
        or document.get("logical_cell_count") != document.get("eligible_cells")
        or document.get("maximum_physical_attempts")
        != document.get("eligible_cells") * 2
        or not isinstance(document.get("records"), list)
        or len(document["records"]) != document["eligible_cells"]
        or document.get("substitute_models") != []
        or not isinstance(document.get("eligibility_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", document["eligibility_sha256"]) is None
        or document.get("execution_context", {}).get("schema_version")
        != "brick.next-study.execution-context/1"
        or document.get("execution_context", {}).get("value")
        not in ("authorized_research", "synthetic_rehearsal")
    ):
        raise NextStudyDescriptiveError("eligible descriptive schedule drifted")
    authorized = {
        record["logical_cell_id"]: record
        for record in authorized_schedule.get("records", [])
    }
    selected = {record.get("logical_cell_id"): record for record in document["records"]}
    if (
        len(authorized) != 222 or len(selected) != document["eligible_cells"]
        or any(authorized.get(key) != value for key, value in selected.items())
    ):
        raise NextStudyDescriptiveError("eligible cells are not an authorized subset")
    removed_roles = {
        authorized[key]["model_role"] for key in set(authorized) - set(selected)
    }
    if removed_roles - {"2b", "9b"}:
        raise NextStudyDescriptiveError("mandatory 4B descriptive cell was removed")
    for role in ("2b", "9b"):
        authorized_role_ids = {
            key for key, value in authorized.items() if value["model_role"] == role
        }
        selected_role_ids = authorized_role_ids & set(selected)
        if selected_role_ids not in (set(), authorized_role_ids):
            raise NextStudyDescriptiveError(
                "optional descriptive model block was only partially removed"
            )
    expected_blocks = sorted({
        authorized[key]["block"] for key in set(authorized) - set(selected)
    })
    if document.get("removed_blocks") != expected_blocks:
        raise NextStudyDescriptiveError("removed descriptive blocks drifted")
    expected_count = 222 - sum(
        len({
            key for key, value in authorized.items()
            if value["model_role"] == role
        })
        for role in removed_roles
    )
    if document["eligible_cells"] != expected_count:
        raise NextStudyDescriptiveError("eligible descriptive block count drifted")
    return document


def extract_primary_trial_0_controls(grade_ledger, descriptive_schedule):
    if (
        not isinstance(grade_ledger, dict)
        or grade_ledger.get("schema_version") != GRADE_LEDGER_SCHEMA
        or grade_ledger.get("status") != "sealed_complete"
        or grade_ledger.get("cell_count") != 880
    ):
        raise NextStudyDescriptiveError("controls require a sealed primary grade ledger")
    selected = {item["instance_id"] for item in descriptive_schedule["records"]}
    if len(selected) != 22:
        raise NextStudyDescriptiveError("descriptive selection must contain 22 instances")
    records = []
    seen = set()
    for record in grade_ledger["records"]:
        key = (record.get("instance_id"), record.get("condition"), record.get("trial_index"))
        if record.get("instance_id") not in selected or record.get("trial_index") != 0:
            continue
        if key in seen or record.get("condition") not in ("native_tools", "harness_full"):
            raise NextStudyDescriptiveError("primary control coordinates are duplicate or invalid")
        if type(record.get("strict_success")) is not bool:
            raise NextStudyDescriptiveError("primary control success is invalid")
        seen.add(key)
        records.append({
            "instance_id": record["instance_id"],
            "condition": record["condition"],
            "strict_success": record["strict_success"],
            "evidence_sha256": record["evidence_sha256"],
            "grade_record_sha256": record["grade_record_sha256"],
        })
    if len(records) != 44:
        raise NextStudyDescriptiveError("primary controls must contain 44 trial-0 cells")
    document = {
        "schema_version": CONTROLS_SCHEMA,
        "primary_grade_ledger_sha256": _digest(grade_ledger),
        "selection_sha256": descriptive_schedule["selection_sha256"],
        "record_count": 44,
        "records": sorted(records, key=lambda item: (item["instance_id"], item["condition"])),
    }
    document["controls_sha256"] = _digest(document)
    return document


def _validate_controls(controls, eligible):
    expected = {
        "schema_version", "primary_grade_ledger_sha256", "selection_sha256",
        "record_count", "records", "controls_sha256",
    }
    if not isinstance(controls, dict) or set(controls) != expected:
        raise NextStudyDescriptiveError("primary controls have unexpected keys")
    unsigned = dict(controls)
    supplied = unsigned.pop("controls_sha256")
    _sha256(supplied, "primary controls digest")
    if supplied != _digest(unsigned):
        raise NextStudyDescriptiveError("primary controls digest drifted")
    if (
        controls["schema_version"] != CONTROLS_SCHEMA
        or controls["selection_sha256"] != eligible["selection_sha256"]
        or controls["record_count"] != 44
        or not isinstance(controls["records"], list)
        or len(controls["records"]) != 44
    ):
        raise NextStudyDescriptiveError("primary control binding drifted")
    selected = {item["instance_id"] for item in eligible["records"]}
    coordinates = set()
    values = {}
    for record in controls["records"]:
        if set(record) != {
            "instance_id", "condition", "strict_success", "evidence_sha256",
            "grade_record_sha256",
        }:
            raise NextStudyDescriptiveError("primary control record drifted")
        key = (record["instance_id"], record["condition"])
        if (
            record["instance_id"] not in selected
            or record["condition"] not in ("native_tools", "harness_full")
            or key in coordinates or type(record["strict_success"]) is not bool
        ):
            raise NextStudyDescriptiveError("primary control coordinate is invalid")
        _sha256(record["evidence_sha256"], "control evidence digest")
        _sha256(record["grade_record_sha256"], "control grade digest")
        coordinates.add(key)
        values[key] = int(record["strict_success"])
    if len(coordinates) != 44:
        raise NextStudyDescriptiveError("primary controls are incomplete")
    return values


def _rate(successes, count):
    return "%d/%d" % (successes, count)


def _fraction(value, count):
    result = Fraction(value, count)
    return "%d/%d" % (result.numerator, result.denominator)


def build_report(eligible, descriptive_evidence, primary_trial_0_controls):
    if eligible.get("status") != "eligible_after_sealed_primary_analysis":
        raise NextStudyDescriptiveError("descriptive report is not eligible")
    controls = _validate_controls(primary_trial_0_controls, eligible)
    if (
        not isinstance(descriptive_evidence, dict)
        or set(descriptive_evidence) != {
            "schema_version", "eligibility_sha256", "scheduled_cells",
            "completed_cells", "records", "evidence_sha256",
        }
        or descriptive_evidence["schema_version"] != EVIDENCE_SCHEMA
        or descriptive_evidence["eligibility_sha256"] != eligible["eligibility_sha256"]
        or descriptive_evidence["evidence_sha256"] != _digest({
            key: value for key, value in descriptive_evidence.items()
            if key != "evidence_sha256"
        })
    ):
        raise NextStudyDescriptiveError("descriptive evidence binding drifted")
    results = descriptive_evidence["records"]
    scheduled = {item["logical_cell_id"]: item for item in eligible["records"]}
    if len(scheduled) != eligible.get("eligible_cells"):
        raise NextStudyDescriptiveError("eligible schedule contains duplicate cells")
    expected_fields = {
        "logical_cell_id", "status", "strict_success", "model_calls",
        "successful_reads", "successful_mutations", "generated_tokens_exact",
        "generated_tokens_lower_bound", "generated_tokens_upper_bound",
        "model_time_ms", "wall_time_ms",
    }
    by_condition = defaultdict(list)
    result_by_coordinate = {}
    seen = set()
    for result in results:
        if not isinstance(result, dict) or set(result) != expected_fields:
            raise NextStudyDescriptiveError("descriptive result has unexpected keys")
        cell = scheduled.get(result["logical_cell_id"])
        if cell is None or result["logical_cell_id"] in seen:
            raise NextStudyDescriptiveError("descriptive result is duplicate or unscheduled")
        seen.add(result["logical_cell_id"])
        if result["status"] not in ("complete", "failed"):
            raise NextStudyDescriptiveError("descriptive status is invalid")
        if type(result["strict_success"]) is not bool or (
            result["status"] == "failed" and result["strict_success"]
        ):
            raise NextStudyDescriptiveError("descriptive success is inconsistent")
        for key in (
            "model_calls", "successful_reads", "successful_mutations",
            "model_time_ms", "wall_time_ms",
        ):
            if isinstance(result[key], bool) or not isinstance(result[key], int) or result[key] < 0:
                raise NextStudyDescriptiveError("descriptive resource field is invalid")
        exact = result["generated_tokens_exact"]
        lower, upper = result["generated_tokens_lower_bound"], result["generated_tokens_upper_bound"]
        if exact is None:
            if (
                isinstance(lower, bool) or not isinstance(lower, int) or lower < 0
                or upper is not None and (
                    isinstance(upper, bool) or not isinstance(upper, int) or upper < lower
                )
            ):
                raise NextStudyDescriptiveError("token bounds are invalid")
        elif (
            isinstance(exact, bool) or not isinstance(exact, int) or exact < 0
            or lower is not None or upper is not None
        ):
            raise NextStudyDescriptiveError("exact tokens cannot be mixed with bounds")
        key = "%s|%s" % (cell["block"], cell["condition"])
        by_condition[key].append((cell, result))
        result_by_coordinate[(cell["block"], cell["instance_id"], cell["condition"])] = result

    summaries = {}
    for key, items in sorted(by_condition.items()):
        successes = sum(result["strict_success"] for _cell, result in items)
        exact_values = [result["generated_tokens_exact"] for _cell, result in items]
        lowers = [
            result["generated_tokens_exact"] if result["generated_tokens_exact"] is not None
            else result["generated_tokens_lower_bound"]
            for _cell, result in items
        ]
        uppers = [
            result["generated_tokens_exact"] if result["generated_tokens_exact"] is not None
            else result["generated_tokens_upper_bound"]
            for _cell, result in items
        ]
        summaries[key] = {
            "completed_cells": len(items),
            "absolute_strict_success": _rate(successes, len(items)),
            "actual_model_calls": sum(result["model_calls"] for _cell, result in items),
            "successful_reads": sum(result["successful_reads"] for _cell, result in items),
            "successful_mutations": sum(result["successful_mutations"] for _cell, result in items),
            "generated_tokens_exact_total": (
                sum(exact_values) if all(value is not None for value in exact_values) else None
            ),
            "generated_tokens_lower_bound_total": sum(lowers),
            "generated_tokens_upper_bound_total": (
                sum(uppers) if all(value is not None for value in uppers) else None
            ),
            "model_time_ms": sum(result["model_time_ms"] for _cell, result in items),
            "wall_time_ms": sum(result["wall_time_ms"] for _cell, result in items),
        }

    comparison_specs = {
        "2b_native_minus_4b_native": ("native_tools", "native_tools", "2b_native_full"),
        "2b_full_minus_4b_full": ("harness_full", "harness_full", "2b_native_full"),
        "9b_native_minus_4b_native": ("native_tools", "native_tools", "9b_native_full"),
        "9b_full_minus_4b_full": ("harness_full", "harness_full", "9b_native_full"),
        "raw_json_minus_4b_native": ("raw_json", "native_tools", "4b_raw_json"),
        "no_plan_minus_4b_full": ("harness_no_plan", "harness_full", "4b_three_harness_ablations"),
        "no_recovery_minus_4b_full": ("harness_no_recovery", "harness_full", "4b_three_harness_ablations"),
        "no_completion_guard_minus_4b_full": ("harness_no_completion_guard", "harness_full", "4b_three_harness_ablations"),
        "no_memory_minus_4b_full": ("harness_no_memory", "harness_full", "4b_no_memory_learning"),
    }
    paired = []
    for comparison, (condition, control_condition, block) in sorted(comparison_specs.items()):
        cells = [item for item in eligible["records"] if item["block"] == block and item["condition"] == condition]
        available = [
            (
                item,
                result_by_coordinate.get((block, item["instance_id"], condition)),
            )
            for item in cells
        ]
        available = [(item, result) for item, result in available if result is not None]
        if available:
            difference = sum(
                int(result["strict_success"]) - controls[(item["instance_id"], control_condition)]
                for item, result in available
            )
            paired.append({
                "comparison": comparison,
                "paired_cells": len(available),
                "paired_strict_success_difference": _fraction(difference, len(available)),
            })
    equal_pairs = []
    for instance_id in sorted({item["instance_id"] for item in eligible["records"]}):
        native = result_by_coordinate.get((
            "4b_role_aware_equal_action_native_full", instance_id,
            "native_equal_action",
        ))
        full = result_by_coordinate.get((
            "4b_role_aware_equal_action_native_full", instance_id,
            "harness_full_equal_action",
        ))
        if native is not None and full is not None:
            equal_pairs.append(int(full["strict_success"]) - int(native["strict_success"]))
    if equal_pairs:
        paired.append({
            "comparison": "equal_action_full_minus_native",
            "paired_cells": len(equal_pairs),
            "paired_strict_success_difference": _fraction(sum(equal_pairs), len(equal_pairs)),
        })

    complete = len(results) == len(scheduled)
    document = {
        "schema_version": REPORT_SCHEMA,
        "execution_context": copy.deepcopy(eligible["execution_context"]),
        "status": "complete" if complete else "partial_descriptive",
        "planned_cells": eligible["planned_cells"],
        "eligible_cells": len(scheduled),
        "completed_cells": len(results),
        "removed_blocks": eligible["removed_blocks"],
        "eligibility_sha256": eligible["eligibility_sha256"],
        "descriptive_evidence_sha256": descriptive_evidence["evidence_sha256"],
        "primary_grade_ledger_sha256": primary_trial_0_controls[
            "primary_grade_ledger_sha256"
        ],
        "selection_sha256": eligible["selection_sha256"],
        "condition_summaries": summaries,
        "paired_descriptive_differences": paired,
        "primary_trial_0_controls_sha256": primary_trial_0_controls["controls_sha256"],
        "primary_claim_affected": False,
        "p_values": None,
        "intervals": None,
        "causal_mechanism_claims": [],
        "no_effect_claims": [],
        "model_size_curve_claim": False,
        "unknown_tokens_imputed": False,
        "synthetic_resource_score": None,
        "rules_reference_classification": (
            "answer-key-backed grader/conformance evidence; not a resource competitor"
        ),
    }
    document["descriptive_report_sha256"] = _digest(document)
    return document


__all__ = [
    "CONTROLS_SCHEMA", "ELIGIBILITY_SCHEMA", "EVIDENCE_SCHEMA", "REPORT_SCHEMA",
    "NextStudyDescriptiveError", "build_report", "eligible_schedule",
    "extract_descriptive_results", "extract_primary_trial_0_controls",
    "seal_descriptive_eligibility", "validate_eligible_schedule",
]
