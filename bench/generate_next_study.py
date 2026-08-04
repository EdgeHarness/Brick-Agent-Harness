"""Write or verify the offline office-generators/2.0.0 artifacts.

This command performs no model calls.  It regenerates 528 cases, validates the
independent prompt oracle, checks all old/new identity-reuse channels, and
maintains a deliberately pending two-reviewer ledger.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import unicodedata

from domains.office_demo.generators_v2 import (
    FAMILIES,
    GENERATOR_VERSION,
    NEXT_SPLITS,
    SPLIT_ORDINALS,
    SPLIT_SIZES,
    SUITE,
    generate_all_manifests,
    validate_office_instance_v2,
)
from domains.office_demo.outcome_oracle_v2 import ORACLE_VERSION, derive_outcome
from harness.instances import (
    canonical_file_bytes,
    load_canonical_json,
    replace_canonical_json,
    review_split_overlap,
    sha256_bytes,
    validate_manifest,
)

from .next_study_review import build_pending_ledger, validate_ledger


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIRECTORY = ROOT / "bench" / "manifests" / "office-v2"
PREDECESSOR_DIRECTORY = ROOT / "bench" / "manifests" / "office-v1"
EVIDENCE_DIRECTORY = ROOT / "evidence" / "next-study"
LOCK_NAME = "manifest-lock.json"
ORACLE_AUDIT_NAME = "office-v2-oracle-audit.json"
REVIEW_LEDGER_NAME = "office-v2-review-ledger.json"
LOCK_SCHEMA = "brick.next-study.manifest-lock/1"
ORACLE_AUDIT_SCHEMA = "brick.next-study.oracle-audit/1"


def _manifest_name(split):
    return "%s.json" % split


def _source_sha256(module_name):
    path = ROOT / "domains" / "office_demo" / module_name
    return sha256_bytes(path.read_bytes())


def _entity_surfaces(content):
    return {
        unicodedata.normalize("NFC", value).casefold()
        for entity in content["entities"].values()
        for value in entity.values()
        if isinstance(value, str) and value
    }


def _predecessor_manifests():
    manifests = []
    for split in ("development", "validation", "sentinel", "retained", "adversarial"):
        manifest = load_canonical_json(PREDECESSOR_DIRECTORY / _manifest_name(split))
        validate_manifest(manifest)
        manifests.append(manifest)
    return manifests


def _identity_reuse_review(manifests):
    predecessor = [
        instance
        for manifest in _predecessor_manifests()
        for instance in manifest["instances"]
    ]
    successor = [
        instance for manifest in manifests for instance in manifest["instances"]
    ]

    def channels(instances):
        return {
            "instance_id": {item["content"]["id"] for item in instances},
            "content_sha256": {item["content_sha256"] for item in instances},
            "structure_sha256": {
                item["content"]["structure_sha256"] for item in instances
            },
            "entity_key": {
                key.casefold()
                for item in instances for key in item["content"]["entity_keys"]
            },
            "entity_surface": {
                surface
                for item in instances
                for surface in _entity_surfaces(item["content"])
            },
        }

    old, new = channels(predecessor), channels(successor)
    overlaps = {name: sorted(old[name] & new[name]) for name in old}
    if any(overlaps.values()):
        failed = [name for name, values in overlaps.items() if values]
        raise ValueError("successor reuses predecessor identity channels: %r" % failed)
    return {
        "schema_version": "brick.next-study.predecessor-reuse-review/1",
        "passed": True,
        "predecessor_generator_version": "office-generators/1.1.0",
        "successor_generator_version": GENERATOR_VERSION,
        "predecessor_cases": len(predecessor),
        "successor_cases": len(successor),
        "overlap_counts": {name: len(values) for name, values in overlaps.items()},
    }


def _balance_review(manifests):
    records = []
    for manifest in manifests:
        split = manifest["split"]
        structures = [item["content"]["structure"] for item in manifest["instances"]]
        per_family = SPLIT_SIZES[split]
        workloads = Counter(item["workload"] for item in structures)
        distractors = Counter(item["distractor_count"] for item in structures)
        constraints = Counter(item["constraint_profile"] for item in structures)
        # Counts above contain eleven identical family allocations.
        workload_counts = [workloads[value] // len(FAMILIES) for value in range(3, 7)]
        distractor_counts = [
            distractors[value] // len(FAMILIES) for value in range(4)
        ]
        constraint_counts = [
            constraints[value] // len(FAMILIES)
            for value in ("listed", "ranked", "cross_check")
        ]
        if (
            sum(workload_counts) != per_family
            or sum(distractor_counts) != per_family
            or sum(constraint_counts) != per_family
            or max(workload_counts) - min(workload_counts) > 0
            or max(distractor_counts) - min(distractor_counts) > 0
            or max(constraint_counts) - min(constraint_counts) > 1
        ):
            raise ValueError("successor split axes are not balanced")
        records.append({
            "split": split,
            "cases_per_family": per_family,
            "workload_3_through_6_counts": workload_counts,
            "distractor_0_through_3_counts": distractor_counts,
            "constraint_listed_ranked_cross_check_counts": constraint_counts,
        })
    if set(value for values in SPLIT_ORDINALS.values() for value in values) != set(range(48)):
        raise ValueError("successor ordinal allocation is not a partition of 0..47")
    all_instances = [
        instance for manifest in manifests for instance in manifest["instances"]
    ]
    burden = {}
    for family in FAMILIES:
        calls = []
        for instance in all_instances:
            if instance["content"]["family"] != family:
                continue
            difficulty = instance["content"]["structure"]["difficulty"]
            calls.append(
                difficulty["minimum_discovery_calls"]
                + difficulty["minimum_source_reads"]
                + difficulty["minimum_mutating_calls"]
            )
        burden[family] = {"minimum": min(calls), "maximum": max(calls)}
    return {
        "schema_version": "brick.next-study.balance-review/1",
        "passed": True,
        "factorial_shapes_per_family": 48,
        "split_records": records,
        "minimum_model_facing_tool_calls_by_family": burden,
    }


def _lock(manifests, overlap, predecessor_review, balance):
    entries = []
    for manifest in manifests:
        entries.append({
            "split": manifest["split"],
            "path": _manifest_name(manifest["split"]),
            "sha256": sha256_bytes(canonical_file_bytes(manifest)),
            "instances": len(manifest["instances"]),
        })
    return {
        "schema_version": LOCK_SCHEMA,
        "suite": SUITE,
        "generator_version": GENERATOR_VERSION,
        "oracle_version": ORACLE_VERSION,
        "generator_source_sha256": _source_sha256("generators_v2.py"),
        "oracle_source_sha256": _source_sha256("outcome_oracle_v2.py"),
        "manifests": entries,
        "overlap_review": overlap,
        "predecessor_reuse_review": predecessor_review,
        "balance_review": balance,
    }


def _oracle_audit(manifests, lock):
    family_counts = Counter()
    comparisons = 0
    for manifest in manifests:
        for instance in manifest["instances"]:
            validate_office_instance_v2(instance)
            content = instance["content"]
            prompts = [
                episode["prompt"] for episode in content["ordered_subepisodes"]
            ]
            derived = derive_outcome(
                content["family"], content["prompt"], prompts,
                content["initial_state"], content["today"],
            )
            if derived != content["required_effects"]:
                raise ValueError("oracle mismatch for %s" % content["id"])
            comparisons += 1
            family_counts[content["family"]] += 1
    return {
        "schema_version": ORACLE_AUDIT_SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "oracle_version": ORACLE_VERSION,
        "manifest_lock_sha256": sha256_bytes(canonical_file_bytes(lock)),
        "oracle_source_sha256": lock["oracle_source_sha256"],
        "case_count": comparisons,
        "family_counts": dict(sorted(family_counts.items())),
        "prompt_to_hidden_outcome_exact_matches": comparisons,
        "all_exact_matches": True,
        "oracle_accepts_required_effects_parameter": False,
        "required_effects_consumed_by_oracle": False,
        "grader_output_consumed_by_oracle": False,
        "live_model_calls": 0,
    }


def build():
    manifests = generate_all_manifests()
    overlap = review_split_overlap(manifests, NEXT_SPLITS)
    predecessor_review = _identity_reuse_review(manifests)
    balance = _balance_review(manifests)
    lock = _lock(manifests, overlap, predecessor_review, balance)
    audit = _oracle_audit(manifests, lock)
    ledger = build_pending_ledger(manifests)
    return manifests, lock, audit, ledger


def write(directory=DEFAULT_DIRECTORY, evidence_directory=EVIDENCE_DIRECTORY):
    directory = Path(directory)
    evidence_directory = Path(evidence_directory)
    manifests, lock, audit, ledger = build()
    for manifest in manifests:
        replace_canonical_json(directory / _manifest_name(manifest["split"]), manifest)
    replace_canonical_json(directory / LOCK_NAME, lock)
    replace_canonical_json(evidence_directory / ORACLE_AUDIT_NAME, audit)
    # Do not overwrite human work.  A write is permitted only when no ledger
    # exists or when it is still byte-identical to the generated pending form.
    ledger_path = evidence_directory / REVIEW_LEDGER_NAME
    if ledger_path.exists():
        existing = load_canonical_json(ledger_path)
        if canonical_file_bytes(existing) != canonical_file_bytes(ledger):
            raise ValueError("refusing to overwrite a non-pending review ledger")
    replace_canonical_json(ledger_path, ledger)
    return lock


def verify(directory=DEFAULT_DIRECTORY, evidence_directory=EVIDENCE_DIRECTORY):
    directory = Path(directory)
    evidence_directory = Path(evidence_directory)
    expected_manifests, expected_lock, expected_audit, _pending = build()
    actual_manifests = []
    for expected in expected_manifests:
        path = directory / _manifest_name(expected["split"])
        actual = load_canonical_json(path)
        validate_manifest(actual)
        if canonical_file_bytes(actual) != canonical_file_bytes(expected):
            raise ValueError("%s does not replay from office-generators/2.0.0" % path)
        actual_manifests.append(actual)
    actual_lock = load_canonical_json(directory / LOCK_NAME)
    if canonical_file_bytes(actual_lock) != canonical_file_bytes(expected_lock):
        raise ValueError("successor manifest lock drifted")
    actual_audit = load_canonical_json(evidence_directory / ORACLE_AUDIT_NAME)
    if canonical_file_bytes(actual_audit) != canonical_file_bytes(expected_audit):
        raise ValueError("independent oracle audit drifted")
    ledger = load_canonical_json(evidence_directory / REVIEW_LEDGER_NAME)
    validate_ledger(ledger, actual_manifests)
    return actual_lock, actual_audit, ledger


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    parser.add_argument(
        "--evidence-directory", type=Path, default=EVIDENCE_DIRECTORY,
    )
    args = parser.parse_args(argv)
    if args.write:
        lock = write(args.directory, args.evidence_directory)
        status = "written"
        ledger_status = "pending_human_review"
    else:
        lock, _audit, ledger = verify(args.directory, args.evidence_directory)
        status = "verified"
        ledger_status = ledger["status"]
    print(json.dumps({
        "status": status,
        "generator_version": GENERATOR_VERSION,
        "instances": sum(item["instances"] for item in lock["manifests"]),
        "review_ledger_status": ledger_status,
        "live_model_calls": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    main()


__all__ = [
    "DEFAULT_DIRECTORY",
    "EVIDENCE_DIRECTORY",
    "LOCK_NAME",
    "ORACLE_AUDIT_NAME",
    "REVIEW_LEDGER_NAME",
    "build",
    "verify",
    "write",
]
