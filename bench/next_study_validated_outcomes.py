"""Compile and validate public-packet outcomes for the 2.1.0 instrument.

The legacy-named ``outcome_oracle_v2`` module is the independent compiler: it
parses only prompt text, visible initial state, date, and subepisode prompts.
It imports neither the generator nor the grader.  This module binds its output
to every public packet and compares it with the generator's independently
constructed hidden outcome before publication.
"""

import copy
from pathlib import Path

from domains.office_demo.outcome_oracle_v2 import ORACLE_VERSION, derive_outcome
from harness.evidence import canonical_json_bytes
from harness.instances import load_canonical_json, sha256_bytes

from .next_study_review import digest_review_artifact, review_packet


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "evidence" / "next-study" / "office-v2-validated-outcomes.json"
SCHEMA_VERSION = "brick.next-study.validated-outcomes/1"
_SPLITS = (
    "development", "calibration", "validation", "sentinel", "retained",
    "adversarial",
)


class ValidatedOutcomeError(ValueError):
    pass


def _digest(value):
    return sha256_bytes(canonical_json_bytes(value, allow_float=False))


def build_validated_outcomes(manifests):
    records = []
    for manifest in manifests:
        for instance in manifest["instances"]:
            packet = review_packet(instance)
            outcome = derive_outcome(
                packet["family"], packet["prompt"], packet["subepisode_prompts"],
                packet["initial_state"], packet["today"],
            )
            if outcome != instance["content"]["required_effects"]:
                raise ValidatedOutcomeError(
                    "independent outcome mismatch for %s" % instance["content"]["id"]
                )
            records.append({
                "instance_id": instance["content"]["id"],
                "content_sha256": instance["content_sha256"],
                "review_packet_sha256": digest_review_artifact(packet),
                "prompt_valid": True,
                "outcome": copy.deepcopy(outcome),
                "accepted_alternatives": [],
                "review_resolution": "independent_public_packet_compilation",
            })
    document = {
        "schema_version": SCHEMA_VERSION,
        "compiler_version": ORACLE_VERSION,
        "case_count": len(records),
        "records": sorted(records, key=lambda item: item["instance_id"]),
        "live_model_calls": 0,
    }
    document["records_sha256"] = _digest(document["records"])
    return validate_validated_outcomes(document, manifests)


def validate_validated_outcomes(document, manifests):
    if not isinstance(document, dict) or set(document) != {
        "schema_version", "compiler_version", "case_count", "records",
        "records_sha256", "live_model_calls",
    }:
        raise ValidatedOutcomeError("validated-outcome artifact has unexpected keys")
    if document["schema_version"] != SCHEMA_VERSION:
        raise ValidatedOutcomeError("validated-outcome schema drifted")
    if document["compiler_version"] != ORACLE_VERSION:
        raise ValidatedOutcomeError("validated-outcome compiler drifted")
    if document["case_count"] != 528 or len(document["records"]) != 528:
        raise ValidatedOutcomeError("validated outcomes must cover all 528 cases")
    if document["records_sha256"] != _digest(document["records"]):
        raise ValidatedOutcomeError("validated-outcome record digest drifted")
    # Cross-bind every record without recursively rebuilding this document.
    instances = {
        item["content"]["id"]: item
        for manifest in manifests for item in manifest["instances"]
    }
    if set(instances) != {item["instance_id"] for item in document["records"]}:
        raise ValidatedOutcomeError("validated-outcome coverage drifted")
    for record in document["records"]:
        instance = instances[record["instance_id"]]
        packet = review_packet(instance)
        if (
            record["content_sha256"] != instance["content_sha256"]
            or record["review_packet_sha256"] != digest_review_artifact(packet)
            or record["prompt_valid"] is not True
            or record["accepted_alternatives"] != []
            or record["outcome"] != derive_outcome(
                packet["family"], packet["prompt"], packet["subepisode_prompts"],
                packet["initial_state"], packet["today"],
            )
        ):
            raise ValidatedOutcomeError("validated outcome binding drifted")
    if document["live_model_calls"] != 0:
        raise ValidatedOutcomeError("outcome compilation must remain model-free")
    return document


def load_manifests(root=ROOT):
    return [
        load_canonical_json(root / "bench" / "manifests" / "office-v2" / (split + ".json"))
        for split in _SPLITS
    ]


__all__ = [
    "DEFAULT_PATH", "SCHEMA_VERSION", "ValidatedOutcomeError",
    "build_validated_outcomes", "load_manifests", "validate_validated_outcomes",
]
