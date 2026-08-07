"""Write or verify the offline office-generators/2.2.0 artifacts.

This command performs no model calls.  It regenerates 528 cases, validates the
independent prompt oracle, checks all old/new identity-reuse channels, and
freezes the machine-qualified instrument artifacts. Human-review utilities are
advisory only.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
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

from .next_study_review import (
    build_pending_ledger, build_staffing_template, validate_ledger,
    validate_staffing,
)
from .next_study_review_selection import (
    build_review_selection, validate_review_selection,
)
from .next_study_validated_outcomes import (
    DEFAULT_PATH as VALIDATED_OUTCOMES_PATH,
    build_validated_outcomes,
    validate_validated_outcomes,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIRECTORY = ROOT / "bench" / "manifests" / "office-v2"
PREDECESSOR_DIRECTORY = ROOT / "bench" / "manifests" / "office-v1"
EVIDENCE_DIRECTORY = ROOT / "evidence" / "next-study"
LOCK_NAME = "manifest-lock.json"
ORACLE_AUDIT_NAME = "office-v2-oracle-audit.json"
REVIEW_LEDGER_NAME = "office-v2-review-ledger.json"
STAFFING_NAME = "office-v2-review-staffing.json"
REVIEW_SELECTION_NAME = "office-v2-review-selection.json"
LOCK_SCHEMA = "brick.next-study.manifest-lock/1"
ORACLE_AUDIT_SCHEMA = "brick.next-study.oracle-audit/1"
LEAKAGE_REVIEW_SCHEMA = "brick.next-study.split-leakage-review/1"

_FORBIDDEN_SPLIT_TERMS = tuple(NEXT_SPLITS)
_FORBIDDEN_SPLIT_STEMS = (
    "devora", "calvera", "valnora", "sentryn", "retnora", "adverra",
)
_FORBIDDEN_SPLIT_MARKERS = tuple(
    marker
    for split in NEXT_SPLITS
    for marker in (
        "v2-%s" % split,
        "v2_%s" % split,
        "v2-%s" % split[:3],
        "v2_%s" % split[:3],
    )
)


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


def _walk_strings(value, path="$"):
    if isinstance(value, str):
        yield path, unicodedata.normalize("NFC", value).casefold()
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_strings(item, "%s[%d]" % (path, index))
    elif isinstance(value, dict):
        for key, item in sorted(value.items()):
            yield from _walk_strings(item, "%s.%s" % (path, key))


def _visible_surface(content):
    """Return every model/reviewer-visible semantic surface.

    Manifest envelopes, split mappings, random seeds, and hidden structural
    metadata are intentionally excluded.  Required outcomes are scanned because
    their addresses, identifiers, and filenames mirror agent-visible surfaces.
    """

    return {
        "prompt": content["prompt"],
        "ordered_subepisodes": content["ordered_subepisodes"],
        "initial_state": content["initial_state"],
        "required_effects": content["required_effects"],
        "entities": content["entities"],
    }


def _split_leakage_review(manifests):
    findings = []
    scanned_strings = 0
    term_patterns = {
        term: re.compile(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(term))
        for term in _FORBIDDEN_SPLIT_TERMS
    }
    for manifest in manifests:
        for instance in manifest["instances"]:
            content = instance["content"]
            for path, value in _walk_strings(_visible_surface(content)):
                scanned_strings += 1
                matches = [
                    "split:%s" % term
                    for term, pattern in term_patterns.items()
                    if pattern.search(value)
                ]
                matches.extend(
                    "stem:%s" % stem
                    for stem in _FORBIDDEN_SPLIT_STEMS if stem in value
                )
                matches.extend(
                    "marker:%s" % marker
                    for marker in _FORBIDDEN_SPLIT_MARKERS if marker in value
                )
                if matches:
                    findings.append({
                        "instance_id": content["id"],
                        "path": path,
                        "matches": sorted(set(matches)),
                    })
    if findings:
        raise ValueError("successor split leakage detected: %r" % findings[:5])
    return {
        "schema_version": LEAKAGE_REVIEW_SCHEMA,
        "passed": True,
        "case_count": sum(len(item["instances"]) for item in manifests),
        "scanned_strings": scanned_strings,
        "forbidden_split_terms": list(_FORBIDDEN_SPLIT_TERMS),
        "forbidden_split_stems": list(_FORBIDDEN_SPLIT_STEMS),
        "forbidden_split_markers": list(_FORBIDDEN_SPLIT_MARKERS),
        "finding_count": 0,
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
        # Counts above contain eleven identical family allocations.
        workload_counts = [workloads[value] // len(FAMILIES) for value in range(3, 7)]
        distractor_counts = [
            distractors[value] // len(FAMILIES) for value in range(4)
        ]
        policy_counts_by_family = {}
        for family in FAMILIES:
            counts = Counter(
                item["decision_policy"]
                for item in structures if item["family"] == family
            )
            if len(counts) != 3 or max(counts.values()) - min(counts.values()) > 1:
                raise ValueError("successor decision policies are not balanced")
            policy_counts_by_family[family] = dict(sorted(counts.items()))
        if (
            sum(workload_counts) != per_family
            or sum(distractor_counts) != per_family
            or max(workload_counts) - min(workload_counts) > 0
            or max(distractor_counts) - min(distractor_counts) > 0
        ):
            raise ValueError("successor split axes are not balanced")
        records.append({
            "split": split,
            "cases_per_family": per_family,
            "workload_3_through_6_counts": workload_counts,
            "distractor_0_through_3_counts": distractor_counts,
            "decision_policy_counts_by_family": policy_counts_by_family,
        })
    if set(value for values in SPLIT_ORDINALS.values() for value in values) != set(range(48)):
        raise ValueError("successor ordinal allocation is not a partition of 0..47")
    all_instances = [
        instance for manifest in manifests for instance in manifest["instances"]
    ]
    triplets = {}
    for instance in all_instances:
        content = instance["content"]
        structure = content["structure"]
        key = (
            content["family"], structure["workload"],
            structure["distractor_count"],
        )
        triplets.setdefault(key, []).append(instance)
    if len(triplets) != 176 or any(len(items) != 3 for items in triplets.values()):
        raise ValueError("successor policy triplets are incomplete")
    for key, items in triplets.items():
        outcomes = {
            sha256_bytes(canonical_file_bytes(item["content"]["required_effects"]))
            for item in items
        }
        burdens = {
            canonical_file_bytes(item["content"]["structure"]["difficulty"])
            for item in items
        }
        if len(outcomes) != 3 or len(burdens) != 1:
            raise ValueError("policy triplet is not outcome-distinct and burden-matched: %r" % (key,))
    burden = {}
    for family in FAMILIES:
        business_calls, native_calls, harness_calls = [], [], []
        for instance in all_instances:
            if instance["content"]["family"] != family:
                continue
            difficulty = instance["content"]["structure"]["difficulty"]
            business = (
                difficulty["minimum_discovery_calls"]
                + difficulty["minimum_source_reads"]
                + difficulty["minimum_mutating_calls"]
            )
            subepisodes = difficulty["subepisodes"]
            memory_reads = 1 if family == "preference_learning" else 0
            business_calls.append(business)
            native_calls.append(business + memory_reads + subepisodes)
            harness_calls.append(business + 4 * subepisodes)
        business_minimum, business_maximum = min(business_calls), max(business_calls)
        native_minimum, native_maximum = min(native_calls), max(native_calls)
        harness_minimum, harness_maximum = min(harness_calls), max(harness_calls)
        burden[family] = {
            "business_calls": {
                "minimum": business_minimum, "maximum": business_maximum,
            },
            "native_requests": {
                "minimum": native_minimum,
                "maximum": native_maximum,
                "minimum_budget_fraction": "%d/18" % native_minimum,
                "maximum_budget_fraction": "%d/18" % native_maximum,
                "minimum_absolute_slack": 18 - native_maximum,
            },
            "harness_requests": {
                "minimum": harness_minimum,
                "maximum": harness_maximum,
                "minimum_budget_fraction": "%d/18" % harness_minimum,
                "maximum_budget_fraction": "%d/18" % harness_maximum,
                "minimum_absolute_slack": 18 - harness_maximum,
            },
        }
    if max(value["native_requests"]["maximum"] for value in burden.values()) > 9:
        raise ValueError("native request lower bound exceeds 9")
    if max(value["harness_requests"]["maximum"] for value in burden.values()) > 12:
        raise ValueError("harness request lower bound exceeds 12")
    expected_corrections = {
        "cal_brief": (3, 3),
        "email_reply": (6, 6),
        "pptx_from_email": (5, 8),
        "xlsx_from_email": (5, 8),
        "preference_learning": (2, 2),
    }
    actual_corrections = {
        family: (
            burden[family]["business_calls"]["minimum"],
            burden[family]["business_calls"]["maximum"],
        )
        for family in expected_corrections
    }
    if actual_corrections != expected_corrections:
        raise ValueError("direction-blind burden corrections drifted")
    return {
        "schema_version": "brick.next-study.balance-review/2",
        "passed": True,
        "factorial_shapes_per_family": 48,
        "matched_policy_triplets": 176,
        "distinct_policy_triplets": 176,
        "split_records": records,
        "request_cap": 18,
        "native_per_subepisode_requests": {"done": 1},
        "harness_per_subepisode_requests": {
            "planning": 1,
            "rejected_first_done": 1,
            "completion_review": 1,
            "final_done": 1,
        },
        "preference_learning_minimum_requests": {
            "native_tools": 5, "harness_full": 10,
        },
        "condition_aware_lower_bounds_by_family": burden,
        "direction_blind_corrections": {
            family: {"minimum": values[0], "maximum": values[1]}
            for family, values in sorted(actual_corrections.items())
        },
        "maximum_expected_native_requests": max(
            value["native_requests"]["maximum"] for value in burden.values()
        ),
        "maximum_expected_harness_requests": max(
            value["harness_requests"]["maximum"] for value in burden.values()
        ),
        "normalized_two_x_headroom_claimed": False,
    }


def _lock(manifests, overlap, predecessor_review, leakage, balance):
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
        "split_leakage_review": leakage,
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
    leakage = _split_leakage_review(manifests)
    balance = _balance_review(manifests)
    lock = _lock(manifests, overlap, predecessor_review, leakage, balance)
    audit = _oracle_audit(manifests, lock)
    selection = build_review_selection(manifests)
    ledger = build_pending_ledger(manifests, selection)
    return manifests, lock, audit, ledger


def write(directory=DEFAULT_DIRECTORY, evidence_directory=EVIDENCE_DIRECTORY):
    directory = Path(directory)
    evidence_directory = Path(evidence_directory)
    manifests, lock, audit, ledger = build()
    for manifest in manifests:
        replace_canonical_json(directory / _manifest_name(manifest["split"]), manifest)
    replace_canonical_json(directory / LOCK_NAME, lock)
    replace_canonical_json(evidence_directory / ORACLE_AUDIT_NAME, audit)
    replace_canonical_json(
        evidence_directory / VALIDATED_OUTCOMES_PATH.name,
        build_validated_outcomes(manifests),
    )
    replace_canonical_json(
        evidence_directory / REVIEW_SELECTION_NAME,
        build_review_selection(manifests),
    )
    # Advisory review fixtures are retained for optional later external-validity
    # work. They are not authorization artifacts and must not overwrite human work.
    ledger_path = evidence_directory / REVIEW_LEDGER_NAME
    if ledger_path.exists():
        existing = load_canonical_json(ledger_path)
        pristine = (
            existing.get("status") == "pending_human_review"
            and existing.get("completed_cases") == 0
            and all(
                entry.get("adjudication") is None
                and all(value is None for value in entry.get("reviews", {}).values())
                for entry in existing.get("entries", [])
            )
        )
        if canonical_file_bytes(existing) != canonical_file_bytes(ledger) and not pristine:
            raise ValueError("refusing to overwrite a non-pending review ledger")
    replace_canonical_json(ledger_path, ledger)
    staffing_path = evidence_directory / STAFFING_NAME
    staffing_template = build_staffing_template()
    if staffing_path.exists():
        existing_staffing = load_canonical_json(staffing_path)
        pristine_staffing = (
            existing_staffing.get("status") == "pending_real_human_roster"
            and existing_staffing.get("active_reviewers") == []
            and existing_staffing.get("backup_reviewers") == []
        )
        if (
            canonical_file_bytes(existing_staffing)
            != canonical_file_bytes(staffing_template)
            and not pristine_staffing
        ):
            raise ValueError("refusing to overwrite a populated reviewer roster")
    replace_canonical_json(staffing_path, staffing_template)
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
            raise ValueError("%s does not replay from office-generators/2.2.0" % path)
        actual_manifests.append(actual)
    actual_lock = load_canonical_json(directory / LOCK_NAME)
    if canonical_file_bytes(actual_lock) != canonical_file_bytes(expected_lock):
        raise ValueError("successor manifest lock drifted")
    actual_audit = load_canonical_json(evidence_directory / ORACLE_AUDIT_NAME)
    if canonical_file_bytes(actual_audit) != canonical_file_bytes(expected_audit):
        raise ValueError("independent oracle audit drifted")
    validate_validated_outcomes(
        load_canonical_json(evidence_directory / VALIDATED_OUTCOMES_PATH.name),
        actual_manifests,
    )
    selection = load_canonical_json(evidence_directory / REVIEW_SELECTION_NAME)
    validate_review_selection(selection, actual_manifests)
    ledger = load_canonical_json(evidence_directory / REVIEW_LEDGER_NAME)
    validate_ledger(ledger, actual_manifests, selection)
    staffing = load_canonical_json(evidence_directory / STAFFING_NAME)
    validate_staffing(staffing, require_ready=False)
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
        ledger_status = "advisory_pending"
    else:
        lock, _audit, ledger = verify(args.directory, args.evidence_directory)
        status = "verified"
        ledger_status = (
            "advisory_pending_not_authoritative"
            if ledger["status"] == "pending_human_review"
            else "advisory_completed_not_authoritative"
        )
    from bench.next_study_fable_reconciliation import load_reconciliation
    from bench.next_study_successor import load_closure
    historical_construct_gate_status = load_reconciliation()["status"]
    successor_closure_status = load_closure()["status"]
    print(json.dumps({
        "status": status,
        "generator_version": GENERATOR_VERSION,
        "instances": sum(item["instances"] for item in lock["manifests"]),
        "advisory_review_status": ledger_status,
        "historical_2_1_2_construct_gate_status": historical_construct_gate_status,
        "successor_remediation_closure_status": successor_closure_status,
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
    "REVIEW_SELECTION_NAME",
    "STAFFING_NAME",
    "build",
    "verify",
    "write",
]
