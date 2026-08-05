import copy
from pathlib import Path

import pytest

from bench.next_study_hybrid_validation import (
    DEFAULT_BLUEPRINT, DEFAULT_PROTOCOL, DEFAULT_RESULT, HybridValidationError,
    build_challenge_blueprint, build_pending_result, build_protocol,
    validate_challenge_blueprint, validate_pending_result,
)
from harness.instances import load_canonical_json


ROOT = Path(__file__).resolve().parents[1]


def _manifests():
    directory = ROOT / "bench" / "manifests" / "office-v2"
    return [
        load_canonical_json(directory / (split + ".json"))
        for split in (
            "development", "calibration", "validation", "sentinel",
            "retained", "adversarial",
        )
    ]


def test_hybrid_protocol_is_advisory_and_does_not_overclaim():
    blueprint = build_challenge_blueprint(_manifests())
    protocol = build_protocol("a" * 64, blueprint["blueprint_sha256"])
    assert protocol["authorization_gate"] is False
    assert protocol["human_design"]["minimum_real_humans"] == 3
    assert protocol["human_design"]["initial_double_review_cases"] == 44
    assert protocol["human_design"]["minimum_planned_human_judgments"] == 176
    assert protocol["agent_design"]["minimum_distinct_model_lineages"] == 2
    assert protocol["acceptance"]["agent_invalid_challenges_detected_required"] == 33
    assert protocol["acceptance"]["tost_equivalence"].startswith("prohibited")
    assert "real-world utility or ecological validity" in protocol["claims_prohibited"]


def test_challenge_blueprint_is_balanced_deterministic_and_unmaterialized():
    manifests = _manifests()
    blueprint = build_challenge_blueprint(manifests)
    assert blueprint == load_canonical_json(DEFAULT_BLUEPRINT)
    assert len(blueprint["records"]) == 66
    assert sum(item["expected_valid"] is True for item in blueprint["records"]) == 33
    assert sum(item["expected_valid"] is False for item in blueprint["records"]) == 33
    assert {
        (item["family"], item["source_split"])
        for item in blueprint["records"]
    } == {
        (family, split)
        for family in {item["family"] for item in blueprint["records"]}
        for split in {
            "development", "calibration", "validation", "sentinel",
            "retained", "adversarial",
        }
    }
    assert all(item["materialized_packet_sha256"] is None for item in blueprint["records"])
    tampered = copy.deepcopy(blueprint)
    tampered["records"][0]["expected_valid"] = not tampered["records"][0]["expected_valid"]
    with pytest.raises(HybridValidationError, match="digest drifted"):
        validate_challenge_blueprint(tampered, manifests)


def test_canonical_hybrid_protocol_matches_bound_blueprint_and_selection():
    protocol = load_canonical_json(DEFAULT_PROTOCOL)
    blueprint = load_canonical_json(DEFAULT_BLUEPRINT)
    selection = load_canonical_json(
        ROOT / "evidence" / "next-study" / "office-v2-review-selection.json"
    )
    assert protocol == build_protocol(
        selection["selection_sha256"], blueprint["blueprint_sha256"]
    )
    result = load_canonical_json(DEFAULT_RESULT)
    assert result == build_pending_result(protocol, blueprint)
    overclaim = copy.deepcopy(result)
    overclaim["execution_authorized"] = True
    unsigned = dict(overclaim)
    unsigned.pop("result_sha256")
    from harness.evidence import canonical_json_bytes
    from harness.instances import sha256_bytes
    overclaim["result_sha256"] = sha256_bytes(
        canonical_json_bytes(unsigned, allow_float=False)
    )
    with pytest.raises(HybridValidationError, match="overclaims"):
        validate_pending_result(overclaim, protocol, blueprint)
