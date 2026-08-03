"""Frozen paired-outcome analysis for S7 and the retained experiment."""

from collections import Counter, defaultdict
from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path
import sys

from bench.s7_artifacts import commit_artifact, verify_artifact
from bench.s7_contract import DEFAULT_PROTOCOL, load_protocol, s7_protocol_sha256
from harness.evidence import canonical_json_bytes


OUTCOME_SCHEMA = "brick.s7.paired-outcomes/1"
ANALYSIS_SCHEMA = "brick.s7.paired-analysis/1"


class S7AnalysisError(RuntimeError):
    """An analysis input or runtime differs from the frozen contract."""


def _numpy(protocol):
    try:
        import numpy as np
    except ImportError as exc:
        raise S7AnalysisError("the pinned NumPy analysis environment is absent") from exc
    expected_minor = tuple(int(value) for value in protocol["analysis"]["python_minor"].split("."))
    if sys.version_info[:2] != expected_minor:
        raise S7AnalysisError("Python minor version differs from the analysis contract")
    if np.__version__ != protocol["analysis"]["numpy_version"]:
        raise S7AnalysisError("NumPy version differs from the analysis contract")
    return np


def _decimal_ratio(numerator, denominator):
    with localcontext() as context:
        context.prec = 50
        return format(Decimal(numerator) / Decimal(denominator), "f")


def _float_string(value):
    value = float(value)
    if not math.isfinite(value):
        raise S7AnalysisError("analysis produced a non-finite value")
    return format(value, ".17g")


def validate_outcomes(document, protocol):
    if not isinstance(document, dict) or set(document) != {
        "schema_version", "s7_protocol_sha256", "cases_per_family", "pairs",
    }:
        raise S7AnalysisError("paired-outcome document keys differ")
    if document["schema_version"] != OUTCOME_SCHEMA:
        raise S7AnalysisError("paired-outcome schema differs")
    if document["s7_protocol_sha256"] != s7_protocol_sha256(protocol):
        raise S7AnalysisError("paired outcomes bind a different S7 protocol")
    n = document["cases_per_family"]
    allowed = protocol["d0"]["runtime_decision"]
    if n not in {
        allowed["default_cases_per_family"],
        allowed["fallback_cases_per_family"],
    }:
        raise S7AnalysisError("retained sample size differs from the runtime rule")
    pairs = document["pairs"]
    if not isinstance(pairs, list):
        raise S7AnalysisError("paired outcomes must be a list")
    normalized = []
    identifiers = set()
    counts = Counter()
    for item in pairs:
        if not isinstance(item, dict) or set(item) != {
            "instance_id", "family", "native_tools", "harness_full",
        }:
            raise S7AnalysisError("paired outcome keys differ")
        if (
            not isinstance(item["instance_id"], str)
            or not item["instance_id"]
            or not isinstance(item["family"], str)
            or not item["family"]
            or type(item["native_tools"]) is not bool
            or type(item["harness_full"]) is not bool
        ):
            raise S7AnalysisError("paired outcome value is invalid")
        if item["instance_id"] in identifiers:
            raise S7AnalysisError("paired instance identifiers must be unique")
        identifiers.add(item["instance_id"])
        counts[item["family"]] += 1
        normalized.append(dict(item))
    if len(counts) != protocol["d0"]["families"]:
        raise S7AnalysisError("paired outcomes do not cover eleven families")
    if any(value != n for value in counts.values()):
        raise S7AnalysisError("paired outcomes are not balanced by family")
    normalized.sort(key=lambda item: (item["family"], item["instance_id"]))
    return normalized


def exact_sign_flip(positive, negative):
    """Two-sided randomization probability for the paired signed sum."""

    if min(positive, negative) < 0:
        raise ValueError("discordance counts cannot be negative")
    discordant = positive + negative
    if discordant == 0:
        return 1, 1
    observed = abs(positive - negative)
    numerator = sum(
        math.comb(discordant, successes)
        for successes in range(discordant + 1)
        if abs(2 * successes - discordant) >= observed
    )
    denominator = 2 ** discordant
    divisor = math.gcd(numerator, denominator)
    return numerator // divisor, denominator // divisor


def bootstrap_index_vectors(families, n, protocol, draws=None):
    """Generate the explicitly ordered PCG64 resampling stream."""

    np = _numpy(protocol)
    total = protocol["analysis"]["bootstrap_draws"] if draws is None else draws
    if type(total) is not int or total < 1:
        raise S7AnalysisError("bootstrap draw count must be positive")
    rng = np.random.Generator(np.random.PCG64(protocol["analysis"]["seed"]))
    for _draw in range(total):
        yield [
            rng.integers(0, n, size=n, dtype=np.int64).tolist()
            for _family in families
        ]


def analyze(document, protocol_path=DEFAULT_PROTOCOL):
    protocol = load_protocol(protocol_path)
    np = _numpy(protocol)
    pairs = validate_outcomes(document, protocol)
    grouped = defaultdict(list)
    native_successes = 0
    harness_successes = 0
    positive = 0
    negative = 0
    for item in pairs:
        native = int(item["native_tools"])
        harness = int(item["harness_full"])
        difference = harness - native
        grouped[item["family"]].append(difference)
        native_successes += native
        harness_successes += harness
        positive += int(difference == 1)
        negative += int(difference == -1)
    families = sorted(grouped)
    n = document["cases_per_family"]
    total = len(pairs)
    signed_sum = harness_successes - native_successes
    p_numerator, p_denominator = exact_sign_flip(positive, negative)

    first_hundred = []
    bootstrap = np.empty(protocol["analysis"]["bootstrap_draws"], dtype=np.float64)
    for draw, indices_by_family in enumerate(
        bootstrap_index_vectors(families, n, protocol)
    ):
        if draw < 100:
            first_hundred.append(indices_by_family)
        family_means = []
        for family, indices in zip(families, indices_by_family):
            values = grouped[family]
            family_means.append(sum(values[index] for index in indices) / n)
        bootstrap[draw] = sum(family_means) / len(families)
    lower, upper = np.quantile(
        bootstrap,
        [float(value) for value in protocol["analysis"]["quantiles"]],
        method=protocol["analysis"]["quantile_method"],
    )
    claim_checks = {
        "equal_family_delta_positive": signed_sum > 0,
        "exact_sign_flip_p_below_0_05": p_numerator * 20 < p_denominator,
        "bootstrap_lower_bound_positive": float(lower) > 0,
    }
    leave_one_out = []
    family_effects = []
    pair_map = defaultdict(list)
    for item in pairs:
        pair_map[item["family"]].append(item)
    for family in families:
        native_family = sum(item["native_tools"] for item in pair_map[family])
        harness_family = sum(item["harness_full"] for item in pair_map[family])
        family_effects.append({
            "family": family,
            "pairs": n,
            "native_tools_successes": native_family,
            "harness_full_successes": harness_family,
            "delta": _decimal_ratio(harness_family - native_family, n),
        })
    for excluded in families:
        numerator = sum(
            sum(grouped[family]) for family in families if family != excluded
        )
        denominator = n * (len(families) - 1)
        leave_one_out.append({
            "excluded_family": excluded,
            "delta": _decimal_ratio(numerator, denominator),
        })
    vector_bytes = canonical_json_bytes(first_hundred)
    return {
        "schema_version": ANALYSIS_SCHEMA,
        "s7_protocol_sha256": s7_protocol_sha256(protocol),
        "cases_per_family": n,
        "families": families,
        "pairs": total,
        "condition_successes": {
            "native_tools": native_successes,
            "harness_full": harness_successes,
        },
        "strict_success_rates": {
            "native_tools": _decimal_ratio(native_successes, total),
            "harness_full": _decimal_ratio(harness_successes, total),
        },
        "equal_family_delta": _decimal_ratio(signed_sum, total),
        "family_effects": family_effects,
        "discordance": {
            "harness_only_success": positive,
            "native_only_success": negative,
            "exact_sign_flip_p_numerator": p_numerator,
            "exact_sign_flip_p_denominator": p_denominator,
            "exact_sign_flip_p": _decimal_ratio(p_numerator, p_denominator),
        },
        "bootstrap": {
            "draws": protocol["analysis"]["bootstrap_draws"],
            "seed": protocol["analysis"]["seed"],
            "bit_generator": protocol["analysis"]["bit_generator"],
            "ordering": protocol["analysis"]["ordering"],
            "quantile_method": protocol["analysis"]["quantile_method"],
            "hyndman_fan_type": protocol["analysis"]["hyndman_fan_type"],
            "confidence_interval": [_float_string(lower), _float_string(upper)],
            "first_100_index_vectors_sha256": hashlib.sha256(vector_bytes).hexdigest(),
        },
        "positive_claim_gate": {
            "checks": claim_checks,
            "passed": all(claim_checks.values()),
        },
        "leave_one_family_out": leave_one_out,
    }


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("outcomes", type=Path)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.outcomes.is_dir():
            document = verify_artifact(args.outcomes, OUTCOME_SCHEMA)["document"]
        else:
            outcome_bytes = args.outcomes.read_bytes()
            document = json.loads(outcome_bytes.decode("utf-8"))
            if canonical_json_bytes(document, newline=True) != outcome_bytes:
                raise S7AnalysisError("paired outcomes are not canonical JSON")
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise S7AnalysisError("cannot load paired outcomes") from exc
    result = analyze(document, args.protocol)
    payload = canonical_json_bytes(result, newline=True)
    if args.output is None:
        sys.stdout.buffer.write(payload)
    else:
        sealed = commit_artifact(args.output, result)
        sys.stdout.buffer.write(canonical_json_bytes(sealed, newline=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
