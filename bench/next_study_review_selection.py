"""Outcome-blind human-review scope and reliability-sample selection.

The research claim is calibrated on the calibration and retained cohorts, so
those 308 cases form the human-validity scope.  A factor-balanced 88-case
subset is independently double reviewed, and its 44-case pilot is nested in
that subset.  The other generated cohorts remain machine-conformance evidence.
"""

from itertools import combinations

from domains.office_demo.generators_v2 import FAMILIES, GENERATOR_VERSION
from harness.evidence import canonical_json_bytes
from harness.instances import sha256_bytes, validate_manifest


SELECTION_SCHEMA = "brick.next-study.review-selection/1"
SELECTION_POLICY = "office-tiered-human-validation-selection/1.0.0"
HUMAN_REVIEW_SPLITS = ("calibration", "retained")


class ReviewSelectionError(ValueError):
    pass


def _digest(value):
    return sha256_bytes(canonical_json_bytes(value, allow_float=False))


def _all_instances(manifests):
    if not isinstance(manifests, (list, tuple)) or len(manifests) != 6:
        raise ReviewSelectionError("selection requires all six frozen manifests")
    expected = {
        "development", "calibration", "validation", "sentinel",
        "retained", "adversarial",
    }
    for manifest in manifests:
        validate_manifest(manifest)
    if {item["split"] for item in manifests} != expected:
        raise ReviewSelectionError("selection manifests have missing or duplicate splits")
    instances = [case for manifest in manifests for case in manifest["instances"]]
    if len(instances) != 528:
        raise ReviewSelectionError("selection source must contain 528 cases")
    return instances


def _priority(instance, purpose):
    content = instance["content"]
    return _digest({
        "namespace": "brick.next-study.review-selection/1",
        "purpose": purpose,
        "family": content["family"],
        "split": content["split"],
        "instance_id": content["id"],
        "structure_sha256": content["structure_sha256"],
    })


def _coverage_key(cases, priorities):
    axes = [
        (
            item["content"]["structure"].get(
                "decision_policy",
                item["content"]["structure"].get("constraint_profile"),
            ),
            item["content"]["structure"]["workload"],
            item["content"]["structure"]["distractor_count"],
        )
        for item in cases
    ]
    constraints = {item[0] for item in axes}
    workloads = {item[1] for item in axes}
    distractors = {item[2] for item in axes}
    pair_coverage = (
        len({(item[0], item[1]) for item in axes})
        + len({(item[0], item[2]) for item in axes})
        + len({(item[1], item[2]) for item in axes})
    )
    # min() selects this key: negate coverage, then use a stable hash priority.
    return (
        -len(constraints), -len(workloads), -len(distractors), -pair_coverage,
        tuple(sorted(priorities[item["content"]["id"]] for item in cases)),
    )


def _choose(candidates, count, purpose):
    if len(candidates) < count:
        raise ReviewSelectionError("review stratum is smaller than its quota")
    priorities = {
        item["content"]["id"]: _priority(item, purpose) for item in candidates
    }
    return min(
        combinations(candidates, count),
        key=lambda value: _coverage_key(value, priorities),
    )


def _build_review_selection(manifests):
    instances = _all_instances(manifests)
    scoped = [
        item for item in instances
        if item["content"]["split"] in HUMAN_REVIEW_SPLITS
    ]
    if len(scoped) != 308:
        raise ReviewSelectionError("human-validity scope must contain 308 cases")

    fixed_ids, pilot_ids = set(), set()
    for family in sorted(FAMILIES):
        for split in HUMAN_REVIEW_SPLITS:
            stratum = [
                item for item in scoped
                if item["content"]["family"] == family
                and item["content"]["split"] == split
            ]
            expected = 8 if split == "calibration" else 20
            if len(stratum) != expected:
                raise ReviewSelectionError("human-review family/split stratum drifted")
            fixed = _choose(stratum, 4, "fixed-double")
            fixed_ids.update(item["content"]["id"] for item in fixed)
            pilot = _choose(fixed, 2, "pilot")
            pilot_ids.update(item["content"]["id"] for item in pilot)

    records = []
    for instance in sorted(scoped, key=lambda item: item["content"]["id"]):
        content = instance["content"]
        structure = content["structure"]
        records.append({
            "instance_id": content["id"],
            "content_sha256": instance["content_sha256"],
            "family": content["family"],
            "source_split": content["split"],
            "decision_policy": structure.get(
                "decision_policy", structure.get("constraint_profile")
            ),
            "workload": structure["workload"],
            "distractor_count": structure["distractor_count"],
            "fixed_double_review": content["id"] in fixed_ids,
            "pilot": content["id"] in pilot_ids,
        })
    document = {
        "schema_version": SELECTION_SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "selection_policy": SELECTION_POLICY,
        "scope_splits": list(HUMAN_REVIEW_SPLITS),
        "case_count": 308,
        "planned_primary_judgments": 308,
        "fixed_double_review_cases": 88,
        "planned_secondary_judgments": 88,
        "planned_judgments": 396,
        "maximum_secondary_judgments": 308,
        "expanded_judgments": 616,
        "pilot_cases": 44,
        "pilot_judgments": 88,
        "global_escalation_event_threshold": 2,
        "records": records,
    }
    document["selection_sha256"] = _digest(document)
    return document


def validate_review_selection(document, manifests):
    expected_keys = {
        "schema_version", "generator_version", "selection_policy",
        "scope_splits", "case_count", "planned_primary_judgments",
        "fixed_double_review_cases", "planned_secondary_judgments",
        "planned_judgments", "maximum_secondary_judgments",
        "expanded_judgments", "pilot_cases", "pilot_judgments",
        "global_escalation_event_threshold", "records", "selection_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected_keys:
        raise ReviewSelectionError("review selection has unexpected keys")
    unsigned = dict(document)
    supplied = unsigned.pop("selection_sha256")
    if supplied != _digest(unsigned):
        raise ReviewSelectionError("review selection digest drifted")
    if document["schema_version"] != SELECTION_SCHEMA:
        raise ReviewSelectionError("review selection schema drifted")
    if document["generator_version"] != GENERATOR_VERSION:
        raise ReviewSelectionError("review selection generator drifted")
    if document["selection_policy"] != SELECTION_POLICY:
        raise ReviewSelectionError("review selection policy drifted")
    if document != _build_review_selection(manifests):
        raise ReviewSelectionError("review selection is not the deterministic selection")
    return document


def build_review_selection(manifests):
    return validate_review_selection(_build_review_selection(manifests), manifests)


__all__ = [
    "HUMAN_REVIEW_SPLITS", "SELECTION_POLICY", "SELECTION_SCHEMA",
    "ReviewSelectionError", "build_review_selection", "validate_review_selection",
]
