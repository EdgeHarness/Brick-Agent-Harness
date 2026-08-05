"""Frozen repeat-aware protocol and analysis for the successor study.

The module is inert until handed a complete retained result set.  It contains
no runner and cannot authorize model execution.
"""

from collections import Counter, defaultdict
import datetime
from decimal import Decimal, localcontext
from fractions import Fraction
from functools import lru_cache
import hashlib
import math
from pathlib import Path
from statistics import NormalDist

from domains.office_demo.generators_v2 import FAMILIES, GENERATOR_VERSION
from harness.evidence import canonical_json_bytes
from harness.instances import (
    load_canonical_json, replace_canonical_json, sha256_bytes, validate_manifest,
)

from .next_study_claim import load_claim_contract


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "bench" / "next_study_protocol.json"
PROTOCOL_SCHEMA = "brick.next-study.protocol/2"
PROTOCOL_VERSION = "1.3.0"
CONDITIONS = ("native_tools", "harness_full")
GRADE_LEDGER_SCHEMA = "brick.next-study.grade-ledger/2"
PRIMARY_ANALYSIS_SCHEMA = "brick.next-study.primary-analysis/2"


class NextStudyStatisticsError(ValueError):
    pass


def _digest(value):
    return sha256_bytes(canonical_json_bytes(value, allow_float=False))


def _power_record():
    return {
        "alpha_two_sided": "0.05",
        "target_power": "0.80",
        "minimum_claim_absolute_effect": "0.12",
        "retained_instance_clusters": 220,
        "independent_trials_per_condition": 2,
        "conservative_bernoulli_variance_per_trial": "0.25",
        "intra_condition_repeat_correlation_upper_assumption": "0.50",
        "cross_condition_correlation_lower_assumption": "0.00",
        "paired_cluster_difference_variance_bound": "0.375",
        "standard_error_bound": "0.041286141192",
        "normal_approximation_zero_exclusion_probability_at_true_0_12": "0.828074238908",
        "normal_approximation_joint_claim_probability_at_true_0_12": "0.500000000000",
        "normal_approximation_true_effect_for_80_percent_joint_claim": "0.154747293080",
        "minimum_clusters_for_target_power": 205,
        "planning_sensitivity": [
            {
                "paired_variance_bound": "0.375",
                "zero_exclusion_probability_at_true_0_12": "0.828074238908",
                "joint_claim_probability_at_true_0_12": "0.500000000000",
                "true_effect_for_80_percent_joint_claim": "0.154747293080",
                "approximate_clusters_for_80_percent": 205,
            },
            {
                "paired_variance_bound": "0.500",
                "zero_exclusion_probability_at_true_0_12": "0.711300617614",
                "joint_claim_probability_at_true_0_12": "0.500000000000",
                "true_effect_for_80_percent_joint_claim": "0.160122718026",
                "approximate_clusters_for_80_percent": 273,
            },
            {
                "paired_variance_bound": "0.750",
                "zero_exclusion_probability_at_true_0_12": "0.537980794137",
                "joint_claim_probability_at_true_0_12": "0.500000000000",
                "true_effect_for_80_percent_joint_claim": "0.169140093129",
                "approximate_clusters_for_80_percent": 409,
            },
            {
                "paired_variance_bound": "1.000",
                "zero_exclusion_probability_at_true_0_12": "0.428638379910",
                "joint_claim_probability_at_true_0_12": "0.428546315454",
                "true_effect_for_80_percent_joint_claim": "0.188882836873",
                "approximate_clusters_for_80_percent": 546,
            },
        ],
        "interpretation": (
            "The zero-exclusion and joint-decision figures are normal approximations "
            "conditional on the stated variance and correlation assumptions. The "
            "0.828 figure is not power for the joint claim rule: at a true effect of "
            "0.12, the observed-effect threshold is crossed about half the time."
        ),
    }


def build_protocol():
    claim = load_claim_contract()
    return {
        "schema_version": PROTOCOL_SCHEMA,
        "version": PROTOCOL_VERSION,
        "status": "frozen_offline_no_execution_authorization",
        "generator_version": GENERATOR_VERSION,
        "claim_contract_version": claim["version"],
        "conditions": list(CONDITIONS),
        "opportunity_budget": {
            "model_calls": 18,
            "generated_tokens": 6144,
            "generated_tokens_per_request": 700,
            "shared_across_subepisodes": True,
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
            "estimand": claim["estimand"],
            "confirmatory_claim_rule": claim["directional_dispositions"],
            "minimum_claim_absolute_effect": claim["minimum_claim_absolute_effect"],
            "threshold_inclusive": claim["threshold_inclusive"],
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
                    "unsigned sha256(protocol_version|bootstrap|replicate|family|draw|"
                    "rejection_counter), rejecting values outside the largest exact "
                    "multiple of 20 below 2^256"
                ),
                "interval": "two-sided percentile, nearest-rank 0.025 and 0.975",
                "first_100_index_vectors_sha256": _first_100_index_vectors_sha256(),
            },
            "leave_one_family_out": {
                "descriptive_only": True,
                "formula": "Delta_-f = (11*Delta - Delta_f)/10",
                "records": 11,
                "clusters_per_record": 200,
                "may_alter_claim": False,
                "may_justify_family_exclusion": False,
                "may_support_ten_family_superiority": False,
            },
            "observed_paired_variance": (
                "sample variance across the 220 instance-level paired differences, "
                "reported after sealed primary analysis"
            ),
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
        "descriptive_matrix": {
            "runs_only_after_sealed_primary_analysis": True,
            "selection": (
                "two retained cases per family, one from each trial-0 AB/BA order "
                "stratum, smallest sha256(protocol_digest|descriptive|family|"
                "order_stratum|instance_id)"
            ),
            "selected_instances": 22,
            "maximum_logical_cells": 222,
            "blocks": {
                "2b_native_full": 44,
                "9b_native_full": 44,
                "4b_raw_json": 22,
                "4b_three_harness_ablations": 66,
                "4b_no_memory_learning": 2,
                "4b_role_aware_equal_action_native_full": 44,
            },
            "primary_trial_0_controls_reused": True,
            "reference_reruns": 0,
            "equal_action_role_budgets": {
                "driver": {
                    "model_calls": 15,
                    "generated_tokens": 4800,
                    "available_to": [
                        "native_equal_action", "harness_full_equal_action",
                    ],
                },
                "planning": {
                    "model_calls": 1,
                    "generated_tokens": 672,
                    "available_to": ["harness_full_equal_action"],
                },
                "completion": {
                    "model_calls": 2,
                    "generated_tokens": 672,
                    "available_to": ["harness_full_equal_action"],
                },
                "unused_allowance_transferable": False,
            },
            "inferential_statistics_prohibited": True,
            "may_alter_primary_claim": False,
        },
        "execution_controls": {
            "live_model_execution_enabled": False,
            "retained_execution_enabled": False,
            "explicit_new_authorization_required": True,
            "required_before_any_model_call": [
                "fresh_generator_complete",
                "independent_oracle_complete",
                "semantic_internal_validity_complete",
                "independent_validated_outcomes_complete",
                "construct_contract_complete",
                "grader_mutation_matrix_complete",
                "calibration_protocol_frozen",
                "power_and_cluster_analysis_frozen",
                "sentinel_protocol_frozen",
            ],
        },
    }


def validate_protocol(protocol):
    if protocol != build_protocol():
        raise NextStudyStatisticsError("next-study protocol differs from frozen 1.3.0")
    power = protocol["power"]
    variance_bound = 0.375
    standard_error = math.sqrt(variance_bound / 220)
    normal = NormalDist()
    critical = normal.inv_cdf(0.975)
    for record in power["planning_sensitivity"]:
        variance = float(record["paired_variance_bound"])
        standardized = 0.12 / math.sqrt(variance / 220)
        calculated_power = normal.cdf(-critical - standardized) + 1 - normal.cdf(
            critical - standardized
        )
        calculated_minimum = math.ceil(
            variance * (critical + normal.inv_cdf(0.80)) ** 2 / 0.12 ** 2
        )
        if abs(
            calculated_power
            - float(record["zero_exclusion_probability_at_true_0_12"])
        ) > 5e-13:
            raise NextStudyStatisticsError("power sensitivity calculation drifted")
        if calculated_minimum != record["approximate_clusters_for_80_percent"]:
            raise NextStudyStatisticsError("power sensitivity cluster count drifted")
        standard_error_for_record = math.sqrt(variance / 220)
        interval_threshold = critical * standard_error_for_record
        decision_threshold = max(0.12, interval_threshold)
        joint_at_boundary = 1 - normal.cdf(
            (decision_threshold - 0.12) / standard_error_for_record
        )
        effect_for_eighty = (
            decision_threshold + normal.inv_cdf(0.80) * standard_error_for_record
        )
        if abs(
            joint_at_boundary
            - float(record["joint_claim_probability_at_true_0_12"])
        ) > 5e-13:
            raise NextStudyStatisticsError("joint claim probability drifted")
        if abs(
            effect_for_eighty
            - float(record["true_effect_for_80_percent_joint_claim"])
        ) > 5e-13:
            raise NextStudyStatisticsError("joint claim 80 percent effect drifted")
    if abs(standard_error - float(power["standard_error_bound"])) > 5e-13:
        raise NextStudyStatisticsError("frozen standard-error calculation drifted")
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
    """Return an exact-uniform deterministic index using rejection sampling."""

    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise NextStudyStatisticsError("hash index size must be a positive integer")
    domain = 1 << 256
    limit = domain - (domain % size)
    counter = 0
    while True:
        payload = "|".join(
            [PROTOCOL_VERSION, label]
            + [str(part) for part in parts]
            + [str(counter)]
        )
        value = int.from_bytes(
            hashlib.sha256(payload.encode("utf-8")).digest(), "big"
        )
        if value < limit:
            return value % size
        counter += 1


def _first_100_index_vectors():
    return [
        [
            _hash_index("bootstrap", replicate, family, draw, size=20)
            for family in sorted(FAMILIES)
            for draw in range(20)
        ]
        for replicate in range(100)
    ]


@lru_cache(maxsize=1)
def _first_100_index_vectors_sha256():
    return sha256_bytes(
        canonical_json_bytes(_first_100_index_vectors(), allow_float=False)
    )


@lru_cache(maxsize=1)
def _bootstrap_index_vectors():
    """Cache the frozen 50,000x220 byte index matrix for invariant tests."""

    return tuple(
        bytes(
            _hash_index("bootstrap", replicate, family, draw, size=20)
            for family in sorted(FAMILIES)
            for draw in range(20)
        )
        for replicate in range(50000)
    )


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


def _claim_disposition(estimate, lower, upper):
    claim = load_claim_contract()
    threshold = Fraction(claim["minimum_claim_absolute_effect"])
    if not claim["threshold_inclusive"]:
        raise NextStudyStatisticsError("successor threshold must remain inclusive")
    if claim["sign_flip"]["may_change_claim"] is not False:
        raise NextStudyStatisticsError("sign-flip diagnostic cannot alter the claim")
    if estimate >= threshold and lower > 0:
        return "harness_full_directional_superiority"
    if estimate <= -threshold and upper < 0:
        return "native_tools_directional_superiority"
    return "no_directional_superiority_claim"


def _sealed_primary_records(grade_ledger):
    expected = {
        "schema_version", "generator_version", "protocol_version", "split",
        "status", "cell_count", "schedule_sha256", "sealed_at", "records",
        "execution_context",
    }
    if not isinstance(grade_ledger, dict) or set(grade_ledger) != expected:
        raise NextStudyStatisticsError("primary analysis requires a sealed grade ledger")
    if grade_ledger["schema_version"] != GRADE_LEDGER_SCHEMA:
        raise NextStudyStatisticsError("grade ledger schema drifted")
    if grade_ledger["generator_version"] != GENERATOR_VERSION:
        raise NextStudyStatisticsError("grade ledger generator version drifted")
    if grade_ledger["protocol_version"] != PROTOCOL_VERSION:
        raise NextStudyStatisticsError("grade ledger protocol version drifted")
    if grade_ledger["split"] != "retained" or grade_ledger["status"] != "sealed_complete":
        raise NextStudyStatisticsError("primary grade ledger is not sealed complete")
    if grade_ledger["cell_count"] != 880:
        raise NextStudyStatisticsError("primary grade ledger cell count drifted")
    context = grade_ledger["execution_context"]
    if (
        not isinstance(context, dict)
        or set(context) != {"schema_version", "value"}
        or context.get("schema_version") != "brick.next-study.execution-context/1"
        or context.get("value") not in ("authorized_research", "synthetic_rehearsal")
    ):
        raise NextStudyStatisticsError("grade ledger execution context drifted")
    for field in ("schedule_sha256",):
        value = grade_ledger[field]
        if (
            not isinstance(value, str) or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise NextStudyStatisticsError("grade ledger digest is invalid")
    try:
        sealed = datetime.datetime.fromisoformat(
            grade_ledger["sealed_at"].replace("Z", "+00:00")
        )
    except (AttributeError, ValueError):
        raise NextStudyStatisticsError("grade ledger seal timestamp is invalid")
    if sealed.utcoffset() is None:
        raise NextStudyStatisticsError("grade ledger seal timestamp requires a timezone")
    if not isinstance(grade_ledger["records"], list):
        raise NextStudyStatisticsError("grade ledger records must be a list")
    return grade_ledger["records"]


def analyze_primary(grade_ledger, retained_manifest, primary_schedule, protocol=None):
    """Analyze a complete primary result set under the frozen protocol.

    This function has no access to run directories and performs no execution.
    It accepts only a complete sealed, evidence-derived grade ledger.
    """

    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    validate_manifest(retained_manifest)
    if retained_manifest["split"] != "retained":
        raise NextStudyStatisticsError("primary analysis requires the retained split")
    instances = retained_manifest["instances"]
    expected_ids = {item["content"]["id"] for item in instances}
    if len(instances) != 220 or len(expected_ids) != 220:
        raise NextStudyStatisticsError("primary retained manifest must have 220 cases")
    try:
        from .next_study_schedule import validate_phase_schedule
        validate_phase_schedule(primary_schedule, retained_manifest)
    except ValueError as exc:
        raise NextStudyStatisticsError(str(exc))
    records = _sealed_primary_records(grade_ledger)
    if grade_ledger["schedule_sha256"] != _digest(primary_schedule):
        raise NextStudyStatisticsError("grade ledger schedule binding drifted")
    scheduled = {
        (item["instance_id"], item["condition"], item["trial_index"]): item
        for item in primary_schedule["records"]
    }
    expected_keys = {
        "instance_id", "content_sha256", "family", "condition", "trial_index",
        "trial_seed", "attempt_key", "evidence_sha256", "grade_record_sha256",
        "outcome_origin", "strict_success",
    }
    cells = {}
    family_by_id = {
        item["content"]["id"]: item["content"]["family"] for item in instances
    }
    for record in records:
        if not isinstance(record, dict) or set(record) != expected_keys:
            raise NextStudyStatisticsError("primary record has unexpected keys")
        instance_id = record["instance_id"]
        instance = next(
            item for item in instances if item["content"]["id"] == instance_id
        ) if instance_id in expected_ids else None
        if (
            instance is None
            or record["family"] != family_by_id[instance_id]
            or record["content_sha256"] != instance["content_sha256"]
        ):
            raise NextStudyStatisticsError("primary record identity is unscheduled")
        scheduled_cell = scheduled.get(
            (instance_id, record["condition"], record["trial_index"])
        )
        if scheduled_cell is None or record["trial_seed"] != scheduled_cell["trial_seed"]:
            raise NextStudyStatisticsError("primary record schedule or seed drifted")
        if record["condition"] not in CONDITIONS or record["trial_index"] not in (0, 1):
            raise NextStudyStatisticsError("primary cell coordinates are invalid")
        if (
            isinstance(record["trial_seed"], bool)
            or not isinstance(record["trial_seed"], int)
            or record["trial_seed"] < 0
        ):
            raise NextStudyStatisticsError("primary trial seed is invalid")
        if type(record["strict_success"]) is not bool:
            raise NextStudyStatisticsError("primary strict_success must be boolean")
        attempt_key = record["attempt_key"]
        if not isinstance(attempt_key, dict) or attempt_key != {
            "instance_id": instance_id,
            "condition": record["condition"],
            "trial_index": record["trial_index"],
            "repeat": attempt_key.get("repeat") if isinstance(attempt_key, dict) else None,
        }:
            raise NextStudyStatisticsError("primary attempt key is invalid")
        if type(attempt_key["repeat"]) is not int or attempt_key["repeat"] not in (0, 1):
            raise NextStudyStatisticsError("physical recovery repeat is invalid")
        for field in ("evidence_sha256", "grade_record_sha256"):
            if (
                not isinstance(record[field], str) or len(record[field]) != 64
                or any(character not in "0123456789abcdef" for character in record[field])
            ):
                raise NextStudyStatisticsError("primary evidence digest is invalid")
        if record["outcome_origin"] not in ("completed", "model_terminal_failure"):
            raise NextStudyStatisticsError("non-model invalid cell cannot enter analysis")
        if record["outcome_origin"] == "model_terminal_failure" and record["strict_success"]:
            raise NextStudyStatisticsError("model terminal failure cannot be successful")
        key = (instance_id, record["condition"], record["trial_index"])
        if key in cells:
            raise NextStudyStatisticsError("duplicate primary cell")
        cells[key] = record["strict_success"]
    expected_cell_count = 220 * 2 * 2
    if len(cells) != expected_cell_count:
        raise NextStudyStatisticsError("primary result set is incomplete")
    for instance_id in expected_ids:
        for trial_index in (0, 1):
            paired = {
                scheduled[(instance_id, condition, trial_index)]["trial_seed"]
                for condition in CONDITIONS
            }
            if len(paired) != 1:
                raise NextStudyStatisticsError("condition seeds are not paired")
        if (
            scheduled[(instance_id, CONDITIONS[0], 0)]["trial_seed"]
            == scheduled[(instance_id, CONDITIONS[0], 1)]["trial_seed"]
        ):
            raise NextStudyStatisticsError("independent trials reused a seed")

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
    index_vectors = _bootstrap_index_vectors()
    if len(index_vectors) != bootstrap_count:
        raise NextStudyStatisticsError("bootstrap index matrix count drifted")
    for replicate, indices in enumerate(index_vectors):
        total = Fraction(0, 1)
        draws = 0
        for family_index, family in enumerate(sorted(FAMILIES)):
            items = by_family[family]
            for draw in range(20):
                index = indices[family_index * 20 + draw]
                total += items[index][1]
                draws += 1
        replicates.append(total / draws)
    replicates.sort()
    lower = replicates[math.ceil(0.025 * bootstrap_count) - 1]
    upper = replicates[math.ceil(0.975 * bootstrap_count) - 1]
    sign_flip = _exact_sign_flip_pvalue(list(differences.values()))
    family_effects = {
        family: (
            sum((value for _identifier, value in by_family[family]), Fraction(0, 1))
            / len(by_family[family])
        )
        for family in sorted(FAMILIES)
    }
    lofo = []
    for family in sorted(FAMILIES):
        excluded = (11 * estimate - family_effects[family]) / 10
        lofo.append({
            "excluded_family": family,
            "instance_clusters": 200,
            "paired_effect": _decimal(excluded),
            "shift_from_all_family_estimate": _decimal(excluded - estimate),
            "sign_consistent_with_all_family": (
                excluded == 0 if estimate == 0 else excluded * estimate > 0
            ),
        })
    lofo_values = [Fraction(item["paired_effect"]) for item in lofo]
    paired_variance = sum(
        ((value - estimate) ** 2 for value in differences.values()),
        Fraction(0, 1),
    ) / 219
    claim = _claim_disposition(estimate, lower, upper)
    return {
        "schema_version": PRIMARY_ANALYSIS_SCHEMA,
        "execution_context": grade_ledger["execution_context"],
        "protocol_version": PROTOCOL_VERSION,
        "instance_clusters": 220,
        "model_attempts": 880,
        "paired_effect": _decimal(estimate),
        "cluster_bootstrap_95_interval": [_decimal(lower), _decimal(upper)],
        "bootstrap_first_100_index_vectors_sha256": (
            _first_100_index_vectors_sha256()
        ),
        "exact_cluster_sign_flip_p_value": _decimal(sign_flip),
        "exact_cluster_sign_flip_p_value_fraction": "%d/%d" % (
            sign_flip.numerator, sign_flip.denominator,
        ),
        "family_effects": {
            family: _decimal(value) for family, value in family_effects.items()
        },
        "leave_one_family_out": {
            "descriptive_only": True,
            "records": lofo,
            "paired_effect_range": [
                _decimal(min(lofo_values)), _decimal(max(lofo_values)),
            ],
            "all_signs_consistent": all(
                item["sign_consistent_with_all_family"] for item in lofo
            ),
            "may_alter_claim": False,
        },
        "observed_paired_difference_sample_variance": _decimal(paired_variance),
        "claim_disposition": claim,
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
    "PRIMARY_ANALYSIS_SCHEMA",
    "NextStudyStatisticsError",
    "analyze_primary",
    "build_protocol",
    "load_protocol",
    "validate_protocol",
    "write_protocol",
]
