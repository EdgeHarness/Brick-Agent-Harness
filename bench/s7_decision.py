"""Commit the preregistered runtime-only D0 sample-size decision."""

import argparse
from collections import defaultdict
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path

from bench import s6_run
from bench.s7_artifacts import commit_artifact
from bench.s7_contract import DEFAULT_PROTOCOL, load_protocol, s7_protocol_sha256
from harness.evidence import EvidenceStore, canonical_json_bytes
from harness.experiment import condition_registry, protocol_sha256
from harness.instances import load_canonical_json, validate_manifest


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFESTS = ROOT / "bench" / "manifests" / "office-v1"


def _final_records(store, protocol, manifests=DEFAULT_MANIFESTS):
    projection = store.read_committed()
    metadata = store.run_document["metadata"]
    d0 = protocol["d0"]
    binding = metadata.get("protocol_binding")
    expected_binding = {
        "schema_version": protocol["schema_version"],
        "protocol_version": protocol["protocol_version"],
        "sha256": s7_protocol_sha256(protocol),
    }
    if (
        metadata.get("run_kind") != "score_masked_d0"
        or metadata.get("split") != "development"
        or metadata.get("retained") is not False
        or metadata.get("grading_mode") != "deferred"
        or metadata.get("score_masked") is not True
        or metadata.get("cohort") != d0["initial_cohort"]
        or binding != expected_binding
    ):
        raise RuntimeError("run is not the frozen score-masked D0-A cohort")
    base = metadata.get("protocol")
    if not isinstance(base, dict) or protocol_sha256(base) != protocol["base_protocol_sha256"]:
        raise RuntimeError("D0 run embeds a different base protocol")
    environment = metadata.get("environment")
    if not isinstance(environment, dict):
        raise RuntimeError("D0 run has no environment binding")
    if (
        environment.get("s7_protocol_sha256") != expected_binding["sha256"]
        or environment.get("analysis_python_minor")
        != protocol["analysis"]["python_minor"]
        or environment.get("analysis_numpy_version")
        != protocol["analysis"]["numpy_version"]
    ):
        raise RuntimeError("D0 environment differs from the S7 analysis binding")
    try:
        conditions = condition_registry(base, environment["implementation_sha256"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("D0 condition binding is invalid") from exc
    expected_conditions = {
        name: {
            "version": spec.version,
            "mechanisms": list(spec.mechanisms),
            "mechanism_sha256": spec.mechanism_sha256,
        }
        for name, spec in conditions.items()
    }
    if metadata.get("conditions") != expected_conditions:
        raise RuntimeError("D0 run condition registry differs")
    manifest = load_canonical_json(Path(manifests) / "development.json")
    validate_manifest(manifest)
    instances = [
        item for item in manifest["instances"]
        if item["content"]["id"].startswith("development.d0a.")
    ]
    instance_map = {item["content"]["id"]: item for item in instances}
    expected_schedule = [
        {
            "wave": wave,
            "family": family,
            "instance_id": instance["content"]["id"],
            "condition_order": list(
                s6_run._condition_order(order, tuple(d0["conditions"]))
            ),
        }
        for wave, family, instance, order in s6_run._waves(instances)
    ]
    schedule = metadata.get("schedule")
    if schedule != expected_schedule or len(schedule) != d0["pairs_per_cohort"]:
        raise RuntimeError("D0 schedule differs from the locked 44-pair cohort")
    expected = set()
    for cell in schedule:
        if (
            not isinstance(cell, dict)
            or not cell.get("instance_id", "").startswith("development.d0a.")
            or cell.get("condition_order") not in (
                ["native_tools", "harness_full"],
                ["harness_full", "native_tools"],
            )
        ):
            raise RuntimeError("D0 schedule contains a noncanonical cell")
        for condition in d0["conditions"]:
            expected.add((cell["instance_id"], condition))
    if len(expected) != d0["primary_attempts_per_cohort"]:
        raise RuntimeError("D0 schedule does not define 88 unique primary cells")

    grouped = defaultdict(list)
    for record in projection["records"]:
        key = record["attempt_key"]
        try:
            instance_id = key["instance"]["id"]
            condition_name = key["condition"]["name"]
            repeat = key["repeat"]
        except (KeyError, TypeError) as exc:
            raise RuntimeError("D0 attempt identity is malformed") from exc
        logical = (instance_id, condition_name)
        if logical not in expected:
            raise RuntimeError("D0 evidence contains an unscheduled attempt")
        try:
            expected_key = s6_run._attempt_key(
                instance_map[instance_id], conditions[condition_name],
                environment, base, repeat,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("D0 attempt cannot be reconstructed") from exc
        if key != expected_key.to_dict() or record["logical_hash"] != str(
            expected_key.logical_hash
        ):
            raise RuntimeError("D0 attempt identity differs from frozen inputs")
        if (
            record["grader_status"] != "not_run"
            or record["strict_success"] is not None
            or record["grade"]["candidate_decision"] is not None
        ):
            raise RuntimeError("D0 evidence contains an efficacy score")
        grouped[logical].append(record)
    if set(grouped) != expected:
        raise RuntimeError("D0 evidence is incomplete")

    finals = []
    retry_limit = metadata["protocol"]["instrument_retry_limit"]
    for logical in sorted(grouped):
        records = sorted(
            grouped[logical], key=lambda item: item["attempt_key"]["repeat"]
        )
        repeats = [item["attempt_key"]["repeat"] for item in records]
        if repeats != list(range(len(repeats))) or repeats[-1] > retry_limit:
            raise RuntimeError("D0 retry sequence differs")
        if any(
            item["failure_origin"] not in {"runner", "environment"}
            for item in records[:-1]
        ):
            raise RuntimeError("D0 retried a valid model attempt")
        finals.append(records[-1])
    return projection, finals


def build_decision(
    runs_root, run_id, protocol_path=DEFAULT_PROTOCOL, manifests=DEFAULT_MANIFESTS
):
    protocol = load_protocol(protocol_path)
    store = EvidenceStore.open_run(runs_root, run_id)
    projection, finals = _final_records(store, protocol, manifests)
    allowed = set(protocol["d0"]["runtime_decision"]["valid_failure_origins"])
    if any(record["failure_origin"] not in allowed for record in finals):
        raise RuntimeError("D0 has an unresolved instrument-invalid cell")
    wall_values = []
    for record in finals:
        value = record["result"]["metrics"].get("wall_seconds")
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise RuntimeError("D0 wall-time telemetry is invalid")
        wall_values.append(Decimal.from_float(float(value)))
    wall_values.sort()
    middle = len(wall_values) // 2
    median = (wall_values[middle - 1] + wall_values[middle]) / Decimal(2)
    rule = protocol["d0"]["runtime_decision"]
    estimate = (
        median
        * Decimal(rule["retained_primary_attempts"])
        * Decimal(rule["safety_factor_numerator"])
        / Decimal(rule["safety_factor_denominator"])
    )
    selected = (
        rule["default_cases_per_family"]
        if estimate <= Decimal(rule["threshold_seconds"])
        else rule["fallback_cases_per_family"]
    )
    projection_sha = hashlib.sha256(
        canonical_json_bytes(projection, allow_float=True, newline=True)
    ).hexdigest()
    wall_sha = hashlib.sha256(
        canonical_json_bytes(
            [format(value, "f") for value in wall_values], newline=True
        )
    ).hexdigest()
    return {
        "schema_version": "brick.s7.runtime-decision/1",
        "run_id": run_id,
        "run_sha256": store.run_sha256,
        "results_projection_sha256": projection_sha,
        "s7_protocol_sha256": s7_protocol_sha256(protocol),
        "statistic": rule["statistic"],
        "valid_attempts": len(finals),
        "valid_attempt_wall_seconds_sha256": wall_sha,
        "median_valid_attempt_wall_seconds": format(median, "f"),
        "retained_primary_attempts": rule["retained_primary_attempts"],
        "safety_factor": "%d/%d" % (
            rule["safety_factor_numerator"], rule["safety_factor_denominator"]
        ),
        "estimated_retained_wall_seconds": format(estimate, "f"),
        "threshold_seconds": rule["threshold_seconds"],
        "selected_cases_per_family": selected,
        "decision_basis": "runtime_only",
        "efficacy_fields_read": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--manifests", type=Path, default=DEFAULT_MANIFESTS)
    args = parser.parse_args(argv)
    sealed = commit_artifact(
        args.output,
        build_decision(args.runs_root, args.run_id, args.protocol, args.manifests),
    )
    print(json.dumps(sealed, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
