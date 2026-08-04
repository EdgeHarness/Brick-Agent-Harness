"""Fail-closed contract for the frozen D0/S7 protocol."""

import hashlib
import copy
import json
from pathlib import Path

from harness.evidence import canonical_json_bytes
from harness.experiment import protocol_sha256


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_PROTOCOL = HERE / "s7_protocol.json"


class S7ContractError(RuntimeError):
    """The D0/S7 protocol or its frozen binding is invalid."""


def _exact(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise S7ContractError("%s has unexpected keys" % label)
    return value


def _positive_int(value, label):
    if type(value) is not int or value < 1:
        raise S7ContractError("%s must be a positive integer" % label)
    return value


def load_protocol(path=DEFAULT_PROTOCOL):
    path = Path(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise S7ContractError("cannot load the S7 protocol") from exc
    return validate_protocol(value)


def validate_protocol(value):
    _exact(
        value,
        {
            "schema_version", "protocol_version", "base_protocol_path",
            "base_protocol_sha256", "d0", "analysis",
            "equal_action_sensitivity", "retained_execution_enabled",
            "predecessor_protocol_path", "predecessor_protocol_sha256",
            "instrument_audit_path", "instrument_audit_sha256",
            "environment_recovery",
        },
        "S7 protocol",
    )
    if value["schema_version"] != "brick.s7.protocol/1":
        raise S7ContractError("unsupported S7 protocol schema")
    if value["protocol_version"] != "1.0.1":
        raise S7ContractError("unsupported S7 protocol version")
    if value["base_protocol_path"] != "bench/s6_protocol.json":
        raise S7ContractError("S7 must bind the frozen S6 protocol path")
    if value["retained_execution_enabled"] is not False:
        raise S7ContractError("S7 must keep retained execution disabled")

    if value["predecessor_protocol_path"] != "bench/s7_protocol_v1.0.0.json":
        raise S7ContractError("S7 predecessor protocol path differs")
    predecessor_path = ROOT / value["predecessor_protocol_path"]
    try:
        predecessor = json.loads(predecessor_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise S7ContractError("cannot load the predecessor S7 protocol") from exc
    predecessor_sha = hashlib.sha256(canonical_json_bytes(predecessor)).hexdigest()
    if (
        value["predecessor_protocol_sha256"]
        != "cd1ebf1f101e6357a8fd3bcc00f9e63114b19032fbeda32dff1e3bcbf4515bd1"
        or predecessor_sha != value["predecessor_protocol_sha256"]
        or predecessor.get("protocol_version") != "1.0.0"
    ):
        raise S7ContractError("S7 predecessor protocol binding differs")

    if value["instrument_audit_path"] != "evidence/s7/d0a-instrument-audit.json":
        raise S7ContractError("S7 instrument-audit path differs")
    audit_path = ROOT / value["instrument_audit_path"]
    try:
        audit_bytes = audit_path.read_bytes()
        audit = json.loads(audit_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise S7ContractError("cannot load the D0-A instrument audit") from exc
    if (
        hashlib.sha256(audit_bytes).hexdigest()
        != value["instrument_audit_sha256"]
        or value["instrument_audit_sha256"]
        != "dd6f15321c87f53e6e220df0ab12147f7f6222e3273c83dff993d4797734aa72"
        or audit.get("schema_version") != "brick.s7.instrument-audit/1"
        or audit.get("instrument_valid") is not False
        or audit.get("logical_cells") != 88
        or audit.get("physical_attempts") != 91
        or len(audit.get("instrument_invalid_cells", [])) != 3
        or audit.get("runtime_decision_created") is not False
        or audit.get("grading_performed") is not False
        or audit.get("efficacy_fields_read") is not False
    ):
        raise S7ContractError("D0-A instrument-audit binding differs")

    base_path = ROOT / value["base_protocol_path"]
    try:
        base = json.loads(base_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise S7ContractError("cannot load the bound S6 protocol") from exc
    if protocol_sha256(base) != value["base_protocol_sha256"]:
        raise S7ContractError("bound S6 protocol digest differs")
    if base.get("retained_execution_enabled") is not False:
        raise S7ContractError("bound S6 protocol enables retained execution")

    d0 = _exact(
        value["d0"],
        {
            "initial_cohort", "correction_cohort", "families",
            "pairs_per_family", "pairs_per_cohort",
            "primary_attempts_per_cohort", "conditions", "grading_mode",
            "operator_projection_excludes", "runtime_decision",
            "floor_ceiling_audit",
            "active_cohort", "correction_reason",
        },
        "D0 protocol",
    )
    if d0["initial_cohort"] != "d0a" or d0["correction_cohort"] != "d0b":
        raise S7ContractError("D0 cohort order differs")
    if (
        d0["active_cohort"] != "d0b"
        or d0["correction_reason"]
        != "unresolved_ollama_http_500_environment_failures"
    ):
        raise S7ContractError("D0 correction authorization differs")
    if (
        d0["families"] != 11
        or d0["pairs_per_family"] != 4
        or d0["pairs_per_cohort"] != 44
        or d0["primary_attempts_per_cohort"] != 88
    ):
        raise S7ContractError("D0 allocation differs")
    if d0["conditions"] != ["native_tools", "harness_full"]:
        raise S7ContractError("D0 primary conditions differ")
    if d0["grading_mode"] != "deferred":
        raise S7ContractError("D0 grading must be deferred")
    excluded = d0["operator_projection_excludes"]
    required_exclusions = {
        "candidate_decision", "checks", "condition_success",
        "directional_discordance", "family_effect", "strict_success",
    }
    if not isinstance(excluded, list) or set(excluded) != required_exclusions:
        raise S7ContractError("D0 score exclusions differ")

    decision = _exact(
        d0["runtime_decision"],
        {
            "valid_failure_origins", "statistic",
            "retained_primary_attempts", "safety_factor_numerator",
            "safety_factor_denominator", "threshold_seconds",
            "default_cases_per_family", "fallback_cases_per_family",
        },
        "runtime decision",
    )
    if decision["valid_failure_origins"] != ["none", "model"]:
        raise S7ContractError("runtime-valid failure origins differ")
    if decision["statistic"] != "median_valid_attempt_wall_seconds":
        raise S7ContractError("runtime statistic differs")
    for key in (
        "retained_primary_attempts", "safety_factor_numerator",
        "safety_factor_denominator", "threshold_seconds",
        "default_cases_per_family", "fallback_cases_per_family",
    ):
        _positive_int(decision[key], "runtime decision %s" % key)
    if decision != {
        "valid_failure_origins": ["none", "model"],
        "statistic": "median_valid_attempt_wall_seconds",
        "retained_primary_attempts": 440,
        "safety_factor_numerator": 5,
        "safety_factor_denominator": 4,
        "threshold_seconds": 172800,
        "default_cases_per_family": 20,
        "fallback_cases_per_family": 12,
    }:
        raise S7ContractError("runtime-only decision rule differs")

    audit = _exact(
        d0["floor_ceiling_audit"],
        {
            "combined_outcomes_per_family", "floor_maximum_successes",
            "ceiling_minimum_successes", "correction_limit",
            "direction_blind",
        },
        "floor/ceiling audit",
    )
    if audit != {
        "combined_outcomes_per_family": 8,
        "floor_maximum_successes": 1,
        "ceiling_minimum_successes": 7,
        "correction_limit": 1,
        "direction_blind": True,
    }:
        raise S7ContractError("floor/ceiling rule differs")

    recovery = _exact(
        value["environment_recovery"],
        {
            "eligible_failure_origin", "eligible_failure_type",
            "eligible_http_status", "cooldown_seconds",
            "verify_loopback_version_and_model_digest",
            "full_attempt_retry_limit",
        },
        "environment recovery",
    )
    if recovery != {
        "eligible_failure_origin": "environment",
        "eligible_failure_type": "HTTPError",
        "eligible_http_status": 500,
        "cooldown_seconds": 60,
        "verify_loopback_version_and_model_digest": True,
        "full_attempt_retry_limit": 1,
    }:
        raise S7ContractError("environment recovery rule differs")
    if recovery["full_attempt_retry_limit"] != base.get(
        "instrument_retry_limit"
    ):
        raise S7ContractError(
            "environment recovery retry limit differs from the base protocol"
        )

    analysis = _exact(
        value["analysis"],
        {
            "python_minor", "numpy_version", "bit_generator", "seed",
            "bootstrap_draws", "quantiles", "quantile_method",
            "hyndman_fan_type", "ordering",
        },
        "analysis protocol",
    )
    if analysis != {
        "python_minor": "3.13",
        "numpy_version": "2.5.1",
        "bit_generator": "PCG64",
        "seed": 20260729,
        "bootstrap_draws": 20000,
        "quantiles": ["0.025", "0.975"],
        "quantile_method": "linear",
        "hyndman_fan_type": 7,
        "ordering": "draw-major-family-major-instance-id",
    }:
        raise S7ContractError("analysis protocol differs")

    sensitivity = _exact(
        value["equal_action_sensitivity"],
        {"driver", "overhead_per_subepisode"},
        "equal-action sensitivity",
    )
    if sensitivity != {
        "driver": {
            "model_calls": 14,
            "generated_tokens": 4096,
            "generated_tokens_per_request": 700,
        },
        "overhead_per_subepisode": {
            "plan_calls": 1,
            "completion_calls": 1,
            "generated_tokens_per_request": 700,
        },
    }:
        raise S7ContractError("role-aware sensitivity budget differs")
    return value


def s7_protocol_sha256(value):
    validate_protocol(value)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def equal_action_protocol(base_protocol, condition_name, subepisode_count,
                          s7_protocol=None):
    """Return an S6 protocol whose non-transferable role caps implement S7."""

    if s7_protocol is None:
        s7_protocol = load_protocol()
    else:
        validate_protocol(s7_protocol)
    if condition_name not in {"native_tools", "harness_full"}:
        raise S7ContractError("equal-action sensitivity is primary-condition only")
    _positive_int(subepisode_count, "subepisode count")
    changed = copy.deepcopy(base_protocol)
    driver = copy.deepcopy(s7_protocol["equal_action_sensitivity"]["driver"])
    roles = {"driver": driver}
    if condition_name == "harness_full":
        overhead = s7_protocol["equal_action_sensitivity"][
            "overhead_per_subepisode"
        ]
        per_request = overhead["generated_tokens_per_request"]
        roles["plan"] = {
            "model_calls": overhead["plan_calls"] * subepisode_count,
            "generated_tokens": per_request * subepisode_count,
            "generated_tokens_per_request": per_request,
        }
        roles["completion"] = {
            "model_calls": overhead["completion_calls"] * subepisode_count,
            "generated_tokens": per_request * subepisode_count,
            "generated_tokens_per_request": per_request,
        }
    changed["opportunity_budget"] = {
        "model_calls": sum(value["model_calls"] for value in roles.values()),
        "generated_tokens": sum(
            value["generated_tokens"] for value in roles.values()
        ),
        "generated_tokens_per_request": max(
            value["generated_tokens_per_request"] for value in roles.values()
        ),
        "shared_across_subepisodes": True,
        "role_budgets": roles,
    }
    # Import validation lazily to keep this contract's module boundary small.
    from harness.experiment import validate_protocol as validate_s6_protocol
    validate_s6_protocol(changed)
    return changed


__all__ = [
    "DEFAULT_PROTOCOL", "S7ContractError", "load_protocol",
    "equal_action_protocol", "s7_protocol_sha256", "validate_protocol",
]
