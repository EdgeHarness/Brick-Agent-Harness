"""Frozen repeat-aware protocol and analysis for the successor study.

The module is inert until handed a complete retained result set.  It contains
no runner and cannot authorize model execution.
"""

from collections import Counter, defaultdict
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import math
from pathlib import Path
from statistics import NormalDist

from domains.office_demo.generators_v2 import FAMILIES, GENERATOR_VERSION
from harness.instances import load_canonical_json, replace_canonical_json, validate_manifest


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "bench" / "next_study_protocol.json"
PROTOCOL_SCHEMA = "brick.next-study.protocol/1"
PROTOCOL_VERSION = "1.0.0"
CONDITIONS = ("native_tools", "harness_full")


class NextStudyStatisticsError(ValueError):
    pass


def _power_record():
    return {
        "alpha_two_sided": "0.05",
        "target_power": "0.80",
        "minimum_relevant_absolute_effect": "0.12",
        "retained_instance_clusters": 220,
        "independent_trials_per_condition": 2,
        "conservative_bernoulli_variance_per_trial": "0.25",
        "intra_condition_repeat_correlation_upper_assumption": "0.50",
        "cross_condition_correlation_lower_assumption": "0.00",
        "paired_cluster_difference_variance_bound": "0.375",
        "standard_error_bound": "0.041286141192",
        "normal_approximation_power_at_relevant_effect": "0.828074238908",
        "minimum_clusters_for_target_power": 205,
        "interpretation": (
            "The 220-cluster design is powered for a 12 percentage-point paired "
            "effect under the stated conservative correlation envelope; smaller "
            "effects remain estimable but are not a powered confirmatory claim."
        ),
    }


def build_protocol():
    return {
        "schema_version": PROTOCOL_SCHEMA,
        "version": PROTOCOL_VERSION,
        "status": "frozen_offline_no_execution_authorization",
        "generator_version": GENERATOR_VERSION,
        "conditions": list(CONDITIONS),
        "opportunity_budget": {
            "model_calls": 18,
            "generated_tokens": 6144,
            "identical_across_conditions": True,
            "rationale": (
                "The retired 14-call/4096-token D0 instrument exhausted its budget "
                "in 12 of 88 cells symmetrically; the successor raises both ceilings "
                "before calibration and freezes them for both conditions."
            ),
        },
        "trial_seeding": {
            "independent_trials_per_cell": 2,
            "paired_seed_across_conditions": True,
            "seed_formula": (
                "sha256(protocol_version|generator_version|instance_id|trial_index|"
                "model_digest), low unsigned 63 bits"
            ),
            "trial_indices": [0, 1],
            "seed_or_trajectory_reuse_from_office_generators_1_x": False,
        },
        "calibration": {
            "split": "calibration",
            "cases_per_family": 8,
            "families": 11,
            "conditions": list(CONDITIONS),
            "trials_per_cell": 2,
            "model_attempts": 352,
            "direction_blind": True,
            "combined_outcomes_per_family": 32,
            "acceptable_combined_successes_inclusive": [10, 22],
            "decision_rule": (
                "Every family must have 10 through 22 strict successes among its 32 "
                "condition-combined outcomes. Any family outside the band retires "
                "the complete generator version; no family is dropped post hoc."
            ),
            "per_condition_counts_or_directions_may_be_read": False,
            "calibration_attempts_reused_in_primary": False,
            "model_origin_terminal_failure_is_strict_failure": True,
            "instrument_or_environment_failure_invalidates_calibration": True,
        },
        "primary": {
            "split": "retained",
            "cases_per_family": 20,
            "families": 11,
            "instance_clusters": 220,
            "conditions": list(CONDITIONS),
            "trials_per_cell": 2,
            "model_attempts": 880,
            "estimand": (
                "mean over 220 instances of (harness_full two-trial strict-success "
                "mean minus native_tools two-trial strict-success mean)"
            ),
            "confirmatory_claim_rule": (
                "A directional superiority claim requires the two-sided 95% "
                "stratified cluster-bootstrap interval to exclude zero in that "
                "direction and an absolute point estimate of at least 0.12."
            ),
            "smaller_or_inconclusive_effects": "report estimate and interval descriptively",
            "family_level_inference": "descriptive only; no family-specific efficacy claims",
        },
        "analysis": {
            "cluster_unit": "instance_id",
            "repeat_handling": "average the two binary trials within condition and instance",
            "bootstrap": {
                "replicates": 50000,
                "stratified_by": "family",
                "sampling": "20 instance clusters with replacement within each family",
                "index_generator": (
                    "unsigned sha256(protocol_version|bootstrap|replicate|family|draw) "
                    "integer modulo 20"
                ),
                "interval": "two-sided percentile, nearest-rank 0.025 and 0.975",
            },
            "paired_diagnostic": (
                "exact two-sided cluster sign-flip distribution over nonzero absolute "
                "two-trial instance differences"
            ),
            "reliability_metrics": [
                "two-trial mean strict success",
                "pass_at_2_any_trial_success",
                "pass_pow_2_both_trials_success",
            ],
            "missing_data": (
                "No imputation. Any missing, duplicate, unscheduled, instrument-origin, "
                "or environment-origin primary cell invalidates analysis. A model-origin "
                "terminal failure is a strict failure."
            ),
            "family_weighting": "equal because every family contributes exactly 20 clusters",
            "condition_labels_unmasked_only_after": (
                "all 880 attempts, artifacts, grader records, and marker-last evidence "
                "are committed and verified"
            ),
        },
        "power": _power_record(),
        "sentinel": {
            "split": "sentinel",
            "cases_per_family": 4,
            "families": 11,
            "conditions": list(CONDITIONS),
            "trials_per_cell": 1,
            "condition_cells": 88,
            "instrument_invalid_cells_allowed": 0,
            "efficacy_fields_read": False,
            "zero_invalid_iid_binomial_upper_95_bound": "0.03346948891663748",
            "bound_interpretation": (
                "diagnostic only; the iid Bernoulli assumption is not used for an "
                "efficacy or deployment-reliability claim"
            ),
        },
        "execution_controls": {
            "live_model_execution_enabled": False,
            "retained_execution_enabled": False,
            "explicit_new_authorization_required": True,
            "required_before_any_model_call": [
                "fresh_generator_complete",
                "independent_oracle_complete",
                "prompt_ground_truth_review_complete",
                "grader_mutation_matrix_complete",
                "calibration_protocol_frozen",
                "power_and_cluster_analysis_frozen",
                "sentinel_protocol_frozen",
            ],
        },
    }


def validate_protocol(protocol):
    if protocol != build_protocol():
        raise NextStudyStatisticsError("next-study protocol differs from frozen 1.0.0")
    power = protocol["power"]
    variance_bound = 0.375
    standard_error = math.sqrt(variance_bound / 220)
    standardized = 0.12 / standard_error
    normal = NormalDist()
    critical = normal.inv_cdf(0.975)
    calculated_power = normal.cdf(-critical - standardized) + 1 - normal.cdf(
        critical - standardized
    )
    calculated_minimum = math.ceil(
        variance_bound
        * (critical + normal.inv_cdf(0.80)) ** 2
        / 0.12 ** 2
    )
    if abs(
        calculated_power
        - float(power["normal_approximation_power_at_relevant_effect"])
    ) > 5e-13:
        raise NextStudyStatisticsError("frozen power calculation drifted")
    if abs(standard_error - float(power["standard_error_bound"])) > 5e-13:
        raise NextStudyStatisticsError("frozen standard-error calculation drifted")
    if calculated_minimum != power["minimum_clusters_for_target_power"]:
        raise NextStudyStatisticsError("minimum powered cluster count drifted")
    if power["minimum_clusters_for_target_power"] != 205:
        raise NextStudyStatisticsError("power cluster requirement drifted")
    if power["retained_instance_clusters"] < power["minimum_clusters_for_target_power"]:
        raise NextStudyStatisticsError("retained design is underpowered for its claim")
    calibration = protocol["calibration"]
    if calibration["model_attempts"] != (
        calibration["cases_per_family"]
        * calibration["families"]
        * len(calibration["conditions"])
        * calibration["trials_per_cell"]
    ):
        raise NextStudyStatisticsError("calibration attempt count drifted")
    primary = protocol["primary"]
    if primary["model_attempts"] != (
        primary["instance_clusters"]
        * len(primary["conditions"])
        * primary["trials_per_cell"]
    ):
        raise NextStudyStatisticsError("primary attempt count drifted")
    sentinel = protocol["sentinel"]
    if sentinel["condition_cells"] != (
        sentinel["cases_per_family"]
        * sentinel["families"]
        * len(sentinel["conditions"])
        * sentinel["trials_per_cell"]
    ):
        raise NextStudyStatisticsError("sentinel cell count drifted")
    if protocol["execution_controls"]["live_model_execution_enabled"] is not False:
        raise NextStudyStatisticsError("live execution must remain disabled")
    if protocol["execution_controls"]["retained_execution_enabled"] is not False:
        raise NextStudyStatisticsError("retained execution must remain disabled")
    return protocol


def load_protocol(path=PROTOCOL_PATH):
    return validate_protocol(load_canonical_json(path))


def write_protocol(path=PROTOCOL_PATH):
    return replace_canonical_json(path, validate_protocol(build_protocol()))


def _decimal(value):
    with localcontext() as context:
        context.prec = 40
        result = Decimal(value.numerator) / Decimal(value.denominator)
        return format(result.quantize(Decimal("0.000000000000001")), "f")


def _hash_index(label, *parts, size):
    payload = "|".join([PROTOCOL_VERSION, label] + [str(part) for part in parts])
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest(), "big") % size


def _exact_sign_flip_pvalue(differences):
    magnitudes = [abs(value * 2) for value in differences if value]
    if not magnitudes:
        return Fraction(1, 1)
    observed = abs(sum(value * 2 for value in differences))
    distribution = Counter({0: 1})
    for magnitude in magnitudes:
        updated = Counter()
        for total, count in distribution.items():
            updated[total + magnitude] += count
            updated[total - magnitude] += count
        distribution = updated
    extreme = sum(count for total, count in distribution.items() if abs(total) >= observed)
    return Fraction(extreme, 2 ** len(magnitudes))


def analyze_primary(records, retained_manifest, protocol=None):
    """Analyze a complete primary result set under the frozen protocol.

    This function has no access to run directories and performs no execution.
    Its strict input contract intentionally refuses missing or non-boolean cells.
    """

    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    validate_manifest(retained_manifest)
    if retained_manifest["split"] != "retained":
        raise NextStudyStatisticsError("primary analysis requires the retained split")
    instances = retained_manifest["instances"]
    expected_ids = {item["content"]["id"] for item in instances}
    if len(instances) != 220 or len(expected_ids) != 220:
        raise NextStudyStatisticsError("primary retained manifest must have 220 cases")
    expected_keys = {"instance_id", "family", "condition", "trial", "strict_success"}
    cells = {}
    family_by_id = {
        item["content"]["id"]: item["content"]["family"] for item in instances
    }
    for record in records:
        if not isinstance(record, dict) or set(record) != expected_keys:
            raise NextStudyStatisticsError("primary record has unexpected keys")
        instance_id = record["instance_id"]
        if instance_id not in expected_ids or record["family"] != family_by_id[instance_id]:
            raise NextStudyStatisticsError("primary record identity is unscheduled")
        if record["condition"] not in CONDITIONS or record["trial"] not in (0, 1):
            raise NextStudyStatisticsError("primary cell coordinates are invalid")
        if type(record["strict_success"]) is not bool:
            raise NextStudyStatisticsError("primary strict_success must be boolean")
        key = (instance_id, record["condition"], record["trial"])
        if key in cells:
            raise NextStudyStatisticsError("duplicate primary cell")
        cells[key] = record["strict_success"]
    expected_cell_count = 220 * 2 * 2
    if len(cells) != expected_cell_count:
        raise NextStudyStatisticsError("primary result set is incomplete")

    differences = {}
    by_family = defaultdict(list)
    reliability = {condition: {"any": 0, "both": 0, "successes": 0} for condition in CONDITIONS}
    for instance_id in sorted(expected_ids):
        values = {}
        for condition in CONDITIONS:
            trials = [cells[(instance_id, condition, trial)] for trial in (0, 1)]
            values[condition] = Fraction(sum(trials), 2)
            reliability[condition]["successes"] += sum(trials)
            reliability[condition]["any"] += int(any(trials))
            reliability[condition]["both"] += int(all(trials))
        difference = values["harness_full"] - values["native_tools"]
        differences[instance_id] = difference
        by_family[family_by_id[instance_id]].append((instance_id, difference))
    if set(by_family) != set(FAMILIES) or any(len(items) != 20 for items in by_family.values()):
        raise NextStudyStatisticsError("primary family clusters are unbalanced")

    estimate = sum(differences.values(), Fraction(0, 1)) / 220
    replicates = []
    bootstrap_count = protocol["analysis"]["bootstrap"]["replicates"]
    for replicate in range(bootstrap_count):
        total = Fraction(0, 1)
        draws = 0
        for family in sorted(FAMILIES):
            items = by_family[family]
            for draw in range(20):
                index = _hash_index(
                    "bootstrap", replicate, family, draw, size=len(items)
                )
                total += items[index][1]
                draws += 1
        replicates.append(total / draws)
    replicates.sort()
    lower = replicates[math.ceil(0.025 * bootstrap_count) - 1]
    upper = replicates[math.ceil(0.975 * bootstrap_count) - 1]
    sign_flip = _exact_sign_flip_pvalue(list(differences.values()))
    return {
        "schema_version": "brick.next-study.primary-analysis/1",
        "protocol_version": PROTOCOL_VERSION,
        "instance_clusters": 220,
        "model_attempts": 880,
        "paired_effect": _decimal(estimate),
        "cluster_bootstrap_95_interval": [_decimal(lower), _decimal(upper)],
        "exact_cluster_sign_flip_p_value": _decimal(sign_flip),
        "exact_cluster_sign_flip_p_value_fraction": "%d/%d" % (
            sign_flip.numerator, sign_flip.denominator,
        ),
        "family_effects": {
            family: _decimal(
                sum((value for _identifier, value in by_family[family]), Fraction(0, 1))
                / len(by_family[family])
            )
            for family in sorted(FAMILIES)
        },
        "reliability": {
            condition: {
                "two_trial_mean_strict_success": _decimal(
                    Fraction(values["successes"], 440)
                ),
                "pass_at_2_any_trial_success": _decimal(
                    Fraction(values["any"], 220)
                ),
                "pass_pow_2_both_trials_success": _decimal(
                    Fraction(values["both"], 220)
                ),
            }
            for condition, values in sorted(reliability.items())
        },
    }


__all__ = [
    "CONDITIONS",
    "PROTOCOL_PATH",
    "PROTOCOL_VERSION",
    "NextStudyStatisticsError",
    "analyze_primary",
    "build_protocol",
    "load_protocol",
    "validate_protocol",
    "write_protocol",
]
