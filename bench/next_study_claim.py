"""Single machine-readable claim contract for the Brick successor study."""

from pathlib import Path

from harness.instances import load_canonical_json, replace_canonical_json


ROOT = Path(__file__).resolve().parents[1]
CLAIM_CONTRACT_PATH = ROOT / "bench" / "next_study_claim_contract.json"
CLAIM_SCHEMA = "brick.next-study.claim-contract/1"
CLAIM_VERSION = "1.0.0"


class NextStudyClaimError(ValueError):
    pass


def build_claim_contract():
    return {
        "schema_version": CLAIM_SCHEMA,
        "version": CLAIM_VERSION,
        "estimand": (
            "equal-family mean over 220 fixed instance clusters of harness_full "
            "two-trial strict-success mean minus native_tools two-trial "
            "strict-success mean"
        ),
        "families": 11,
        "clusters_per_family": 20,
        "instance_clusters": 220,
        "interval": {
            "confidence": "0.95",
            "kind": "two-sided stratified cluster percentile bootstrap",
            "replicates": 50000,
            "endpoint_rule": "nearest-rank",
        },
        "minimum_claim_absolute_effect": "0.12",
        "threshold_inclusive": True,
        "directional_dispositions": {
            "harness_superiority": (
                "paired_effect >= 0.12 and bootstrap lower endpoint > 0"
            ),
            "native_superiority": (
                "paired_effect <= -0.12 and bootstrap upper endpoint < 0"
            ),
            "otherwise": "no_directional_superiority_claim",
        },
        "sign_flip": {
            "role": "diagnostic_only",
            "may_change_claim": False,
        },
        "family_level_inference": "descriptive_only",
        "scope": "the fixed eleven-family synthetic Brick benchmark only",
        "external_generalization_claim": False,
    }


def validate_claim_contract(document):
    if document != build_claim_contract():
        raise NextStudyClaimError("claim contract differs from the frozen contract")
    return document


def load_claim_contract(path=CLAIM_CONTRACT_PATH):
    return validate_claim_contract(load_canonical_json(path))


def write_claim_contract(path=CLAIM_CONTRACT_PATH):
    return replace_canonical_json(path, validate_claim_contract(build_claim_contract()))


__all__ = [
    "CLAIM_CONTRACT_PATH", "CLAIM_SCHEMA", "CLAIM_VERSION",
    "NextStudyClaimError", "build_claim_contract", "load_claim_contract",
    "validate_claim_contract", "write_claim_contract",
]
