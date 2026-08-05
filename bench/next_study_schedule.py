"""Deterministic logical schedules for the authorized successor program.

This module is model-free.  It can build and validate schedules, but it cannot
authorize or execute them.
"""

from collections import Counter, defaultdict
import argparse
import hashlib
import json
from functools import lru_cache
from pathlib import Path

from domains.office_demo.generators_v2 import FAMILIES, GENERATOR_VERSION
from harness.evidence import canonical_json_bytes
from harness.instances import (
    load_canonical_json, replace_canonical_json, sha256_bytes, validate_manifest,
)

from .next_study_statistics import CONDITIONS, PROTOCOL_VERSION, build_protocol


SCHEDULE_SCHEMA = "brick.next-study.schedule/1"
DESCRIPTIVE_SELECTION_SCHEMA = "brick.next-study.descriptive-selection/1"
DESCRIPTIVE_SCHEDULE_SCHEMA = "brick.next-study.descriptive-schedule/1"
ROOT = Path(__file__).resolve().parents[1]
RETAINED_MANIFEST_PATH = ROOT / "bench" / "manifests" / "office-v2" / "retained.json"
DESCRIPTIVE_SELECTION_PATH = ROOT / "bench" / "next_study_descriptive_selection.json"


class NextStudyScheduleError(ValueError):
    pass


def _digest(value):
    return sha256_bytes(canonical_json_bytes(value, allow_float=False))


def _validate_sha256(value, label):
    if (
        not isinstance(value, str) or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise NextStudyScheduleError("%s must be lowercase SHA-256 hex" % label)
    return value


@lru_cache(maxsize=1)
def protocol_digest():
    return _digest(build_protocol())


def trial_seed(instance_id, trial_index, model_digest):
    if trial_index not in (0, 1):
        raise NextStudyScheduleError("trial_index must be zero or one")
    payload = "|".join((
        PROTOCOL_VERSION, GENERATOR_VERSION, instance_id,
        str(trial_index), model_digest,
    ))
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest(), "big") & (
        (1 << 63) - 1
    )


def _family_order_strata(manifest, trial_index):
    """Counterbalance once, then reverse every instance on trial one.

    Including ``trial_index`` in the ranking silently re-randomizes cases and
    does not guarantee the declared within-instance reversal.
    """

    if trial_index not in (0, 1):
        raise NextStudyScheduleError("trial_index must be zero or one")
    by_family = defaultdict(list)
    for instance in manifest["instances"]:
        by_family[instance["content"]["family"]].append(instance)
    result = {}
    for family in sorted(FAMILIES):
        items = sorted(
            by_family[family],
            key=lambda item: _digest({
                "protocol_digest": protocol_digest(),
                "namespace": "primary-order",
                "family": family,
                "instance_id": item["content"]["id"],
            }),
        )
        midpoint = len(items) // 2
        for index, instance in enumerate(items):
            first = "AB" if index < midpoint else "BA"
            if trial_index == 1:
                first = "BA" if first == "AB" else "AB"
            result[instance["content"]["id"]] = first
    return result


def build_phase_schedule(manifest, phase, model_digest):
    validate_manifest(manifest)
    expected = {
        "calibration": ("calibration", 2, 352),
        "sentinel": ("sentinel", 1, 88),
        "primary": ("retained", 2, 880),
    }
    if phase not in expected:
        raise NextStudyScheduleError("unknown successor phase")
    split, trials, expected_count = expected[phase]
    if manifest["split"] != split:
        raise NextStudyScheduleError("phase manifest split drifted")
    _validate_sha256(model_digest, "model digest")
    records = []
    for trial_index in range(trials):
        strata = _family_order_strata(manifest, trial_index)
        for instance in sorted(
            manifest["instances"], key=lambda item: item["content"]["id"]
        ):
            instance_id = instance["content"]["id"]
            order = strata[instance_id]
            ordered_conditions = CONDITIONS if order == "AB" else tuple(reversed(CONDITIONS))
            for order_position, condition in enumerate(ordered_conditions):
                records.append({
                    "logical_cell_id": _digest({
                        "phase": phase,
                        "instance_id": instance_id,
                        "condition": condition,
                        "trial_index": trial_index,
                    }),
                    "phase": phase,
                    "instance_id": instance_id,
                    "content_sha256": instance["content_sha256"],
                    "family": instance["content"]["family"],
                    "condition": condition,
                    "trial_index": trial_index,
                    "order_stratum": order,
                    "order_position": order_position,
                    "trial_seed": trial_seed(instance_id, trial_index, model_digest),
                })
    if len(records) != expected_count:
        raise NextStudyScheduleError("phase schedule cell count drifted")
    logical_ids = [item["logical_cell_id"] for item in records]
    if len(logical_ids) != len(set(logical_ids)):
        raise NextStudyScheduleError("phase schedule contains duplicate logical cells")
    return {
        "schema_version": SCHEDULE_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "protocol_sha256": protocol_digest(),
        "generator_version": GENERATOR_VERSION,
        "model_sha256": model_digest,
        "phase": phase,
        "split": split,
        "logical_cell_count": len(records),
        "maximum_physical_attempts": len(records) * 2,
        "same_seed_retry_limit": 1,
        "records": records,
    }


def build_development_shakeout_schedule(manifest, model_digest):
    """Freeze one outcome-blind development case per family and condition."""

    validate_manifest(manifest)
    if manifest["split"] != "development":
        raise NextStudyScheduleError("development shakeout requires development cases")
    _validate_sha256(model_digest, "model digest")
    records = []
    for family_index, family in enumerate(sorted(FAMILIES)):
        candidates = [
            item for item in manifest["instances"]
            if item["content"]["family"] == family
        ]
        if len(candidates) != 8:
            raise NextStudyScheduleError("development family allocation drifted")
        instance = min(candidates, key=lambda item: _digest({
            "namespace": "brick.next-study.development-shakeout/1",
            "protocol_sha256": protocol_digest(),
            "family": family,
            "instance_id": item["content"]["id"],
            "content_sha256": item["content_sha256"],
        }))
        order = "AB" if family_index % 2 == 0 else "BA"
        conditions = CONDITIONS if order == "AB" else tuple(reversed(CONDITIONS))
        seed = trial_seed(instance["content"]["id"], 0, model_digest)
        for order_position, condition in enumerate(conditions):
            records.append({
                "logical_cell_id": _digest({
                    "phase": "development_shakeout",
                    "instance_id": instance["content"]["id"],
                    "condition": condition,
                }),
                "phase": "development_shakeout",
                "instance_id": instance["content"]["id"],
                "content_sha256": instance["content_sha256"],
                "family": family,
                "condition": condition,
                "trial_index": 0,
                "order_stratum": order,
                "order_position": order_position,
                "trial_seed": seed,
            })
    if len(records) != 22 or len({item["logical_cell_id"] for item in records}) != 22:
        raise NextStudyScheduleError("development shakeout must contain 22 unique cells")
    return {
        "schema_version": SCHEDULE_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "protocol_sha256": protocol_digest(),
        "generator_version": GENERATOR_VERSION,
        "model_sha256": model_digest,
        "phase": "development_shakeout",
        "split": "development",
        "logical_cell_count": 22,
        "maximum_physical_attempts": 44,
        "same_seed_retry_limit": 1,
        "records": records,
    }


def validate_development_shakeout_schedule(schedule, manifest):
    if not isinstance(schedule, dict):
        raise NextStudyScheduleError("development shakeout schedule must be an object")
    expected = build_development_shakeout_schedule(
        manifest, schedule.get("model_sha256")
    )
    if schedule != expected:
        raise NextStudyScheduleError("development shakeout schedule drifted")
    return schedule


def validate_phase_schedule(schedule, manifest):
    """Rebuild a phase schedule and require byte-semantic equality."""

    if not isinstance(schedule, dict):
        raise NextStudyScheduleError("phase schedule must be an object")
    expected_keys = {
        "schema_version", "protocol_version", "protocol_sha256",
        "generator_version", "model_sha256", "phase", "split",
        "logical_cell_count", "maximum_physical_attempts",
        "same_seed_retry_limit", "records",
    }
    if set(schedule) != expected_keys or schedule.get("schema_version") != SCHEDULE_SCHEMA:
        raise NextStudyScheduleError("phase schedule schema drifted")
    expected = build_phase_schedule(manifest, schedule["phase"], schedule["model_sha256"])
    if schedule != expected:
        raise NextStudyScheduleError("phase schedule content drifted")
    return schedule


def select_descriptive_cases(retained_manifest):
    validate_manifest(retained_manifest)
    if retained_manifest["split"] != "retained":
        raise NextStudyScheduleError("descriptive selection requires retained cases")
    strata = _family_order_strata(retained_manifest, 0)
    selected = []
    for family in sorted(FAMILIES):
        for order_stratum in ("AB", "BA"):
            candidates = [
                item for item in retained_manifest["instances"]
                if item["content"]["family"] == family
                and strata[item["content"]["id"]] == order_stratum
            ]
            candidates.sort(key=lambda item: hashlib.sha256(
                "|".join((
                    protocol_digest(), "descriptive", family, order_stratum,
                    item["content"]["id"],
                )).encode("utf-8")
            ).hexdigest())
            chosen = candidates[0]
            selected.append({
                "family": family,
                "order_stratum": order_stratum,
                "instance_id": chosen["content"]["id"],
                "content_sha256": chosen["content_sha256"],
            })
    document = {
        "schema_version": DESCRIPTIVE_SELECTION_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "protocol_sha256": protocol_digest(),
        "generator_version": GENERATOR_VERSION,
        "selection_count": len(selected),
        "records": selected,
    }
    document["selection_sha256"] = _digest(document)
    return document


def build_descriptive_schedule(retained_manifest, model_digests):
    required_models = {"2b", "4b", "9b"}
    if not isinstance(model_digests, dict) or set(model_digests) != required_models:
        raise NextStudyScheduleError("descriptive schedule requires 2b/4b/9b digests")
    for role, value in model_digests.items():
        _validate_sha256(value, "descriptive model digest %s" % role)
    selection = select_descriptive_cases(retained_manifest)
    records = []

    def add(block, selected, conditions, model):
        for item in selected:
            for condition in conditions:
                records.append({
                    "logical_cell_id": _digest({
                        "block": block,
                        "instance_id": item["instance_id"],
                        "condition": condition,
                        "model": model,
                    }),
                    "block": block,
                    "instance_id": item["instance_id"],
                    "content_sha256": item["content_sha256"],
                    "family": item["family"],
                    "condition": condition,
                    "model_role": model,
                    "model_sha256": model_digests[model],
                    "trial_index": 0,
                    "trial_seed": trial_seed(item["instance_id"], 0, model_digests[model]),
                })

    chosen = selection["records"]
    add("2b_native_full", chosen, CONDITIONS, "2b")
    add("9b_native_full", chosen, CONDITIONS, "9b")
    add("4b_raw_json", chosen, ("raw_json",), "4b")
    add(
        "4b_three_harness_ablations", chosen,
        ("harness_no_plan", "harness_no_recovery", "harness_no_completion_guard"),
        "4b",
    )
    learning = [item for item in chosen if item["family"] == "preference_learning"]
    add("4b_no_memory_learning", learning, ("harness_no_memory",), "4b")
    add(
        "4b_role_aware_equal_action_native_full", chosen,
        ("native_equal_action", "harness_full_equal_action"), "4b",
    )
    counts = Counter(item["block"] for item in records)
    expected_counts = {
        "2b_native_full": 44,
        "9b_native_full": 44,
        "4b_raw_json": 22,
        "4b_three_harness_ablations": 66,
        "4b_no_memory_learning": 2,
        "4b_role_aware_equal_action_native_full": 44,
    }
    if dict(counts) != expected_counts or len(records) != 222:
        raise NextStudyScheduleError("descriptive matrix does not contain 222 cells")
    ids = [item["logical_cell_id"] for item in records]
    if len(ids) != len(set(ids)):
        raise NextStudyScheduleError("descriptive logical cells are not unique")
    return {
        "schema_version": DESCRIPTIVE_SCHEDULE_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "protocol_sha256": protocol_digest(),
        "generator_version": GENERATOR_VERSION,
        "selection_sha256": selection["selection_sha256"],
        "logical_cell_count": 222,
        "maximum_physical_attempts": 444,
        "blocked_until": "sealed_primary_analysis",
        "block_counts": expected_counts,
        "model_digests": dict(sorted(model_digests.items())),
        "records": records,
    }


def validate_descriptive_schedule(schedule, retained_manifest):
    if not isinstance(schedule, dict):
        raise NextStudyScheduleError("descriptive schedule must be an object")
    expected = build_descriptive_schedule(
        retained_manifest, schedule.get("model_digests")
    )
    if schedule != expected:
        raise NextStudyScheduleError("descriptive schedule content drifted")
    return schedule


def write_descriptive_selection(
    retained_manifest_path=RETAINED_MANIFEST_PATH,
    output_path=DESCRIPTIVE_SELECTION_PATH,
):
    document = select_descriptive_cases(load_canonical_json(retained_manifest_path))
    replace_canonical_json(output_path, document)
    return document


def verify_descriptive_selection(
    retained_manifest_path=RETAINED_MANIFEST_PATH,
    output_path=DESCRIPTIVE_SELECTION_PATH,
):
    expected = select_descriptive_cases(load_canonical_json(retained_manifest_path))
    actual = load_canonical_json(output_path)
    if actual != expected:
        raise NextStudyScheduleError("frozen descriptive selection drifted")
    return actual


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    document = (
        write_descriptive_selection() if args.write
        else verify_descriptive_selection()
    )
    print(json.dumps({
        "status": "written" if args.write else "verified",
        "selection_count": document["selection_count"],
        "selection_sha256": document["selection_sha256"],
        "live_model_calls": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    main()


__all__ = [
    "DESCRIPTIVE_SCHEDULE_SCHEMA",
    "DESCRIPTIVE_SELECTION_SCHEMA",
    "SCHEDULE_SCHEMA",
    "NextStudyScheduleError",
    "build_descriptive_schedule",
    "build_development_shakeout_schedule",
    "build_phase_schedule",
    "protocol_digest",
    "select_descriptive_cases",
    "trial_seed",
    "validate_descriptive_schedule",
    "validate_development_shakeout_schedule",
    "validate_phase_schedule",
    "verify_descriptive_selection",
    "write_descriptive_selection",
]
