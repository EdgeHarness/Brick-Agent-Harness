"""S6G gates for canonical replay, independence, and office semantics."""
import copy

import pytest

import harness.instances as instance_contracts
from bench import generate_manifests as manifest_cli
from domains.office_demo.generators import (
    FAMILIES,
    GENERATOR_VERSION,
    SPLIT_SIZES,
    generate_all_manifests,
    generate_instance,
    validate_office_instance,
)
from harness.instances import (
    InstanceContractError,
    SPLITS,
    canonical_file_bytes,
    envelope_instance,
    make_manifest,
    review_split_overlap,
    validate_instance,
)


def test_all_split_manifests_have_frozen_family_counts_and_exact_replay():
    first = generate_all_manifests()
    second = generate_all_manifests()
    assert [canonical_file_bytes(item) for item in first] == [
        canonical_file_bytes(item) for item in second
    ]
    assert [item["split"] for item in first] == list(SPLITS)
    for manifest in first:
        expected = SPLIT_SIZES[manifest["split"]]
        assert manifest["family_counts"] == {
            family: expected for family in sorted(FAMILIES)
        }
        assert len(manifest["instances"]) == len(FAMILIES) * expected


def test_committed_manifests_replay_and_lock_exact_bytes():
    lock = manifest_cli.verify()
    assert lock["generator_version"] == GENERATOR_VERSION
    assert sum(item["instances"] for item in lock["manifests"]) == 341
    assert lock["overlap_review"]["passed"] is True
    assert lock["overlap_review"]["structures"] == 341


def test_every_instance_has_complete_semantics_and_shared_learning_budget():
    instances = [
        instance
        for manifest in generate_all_manifests()
        for instance in manifest["instances"]
    ]
    assert len(instances) == 341
    for instance in instances:
        validate_instance(instance)
        validate_office_instance(instance)
        content = instance["content"]
        assert content["opportunity_budget"]["model_calls"] == 14
        assert content["opportunity_budget"]["generated_tokens"] == 4096
        learning = content["family"] == "preference_learning"
        assert content["opportunity_budget"]["shared_across_subepisodes"] is learning
        assert len(content["ordered_subepisodes"]) == (2 if learning else 0)


def test_overlap_review_proves_no_seed_only_or_entity_renaming_cases():
    review = review_split_overlap(generate_all_manifests())
    assert review == {
        "schema_version": "brick.split-overlap-review/1",
        "passed": True,
        "splits": list(SPLITS),
        "instances": 341,
        "structures": 341,
        "entity_keys": 786,
        "entity_surfaces": 1417,
    }


def test_reseeded_copy_with_same_semantic_structure_is_rejected():
    manifests = generate_all_manifests()
    duplicate = copy.deepcopy(manifests[1]["instances"][0])
    content = duplicate["content"]
    content["id"] = "validation.synthetic-copy.99"
    content["seed"] += 1
    duplicate = envelope_instance(content)
    manifests[1] = make_manifest(
        manifests[1]["suite"], manifests[1]["generator_version"],
        manifests[1]["split"], manifests[1]["instances"] + [duplicate],
    )
    with pytest.raises(InstanceContractError, match="semantic structure reused"):
        review_split_overlap(manifests)


def test_cross_split_entity_surface_reuse_is_rejected_even_with_new_keys():
    manifests = generate_all_manifests()
    source = manifests[0]["instances"][0]["content"]
    target_envelope = copy.deepcopy(manifests[1]["instances"][0])
    target = target_envelope["content"]
    source_entity = next(iter(source["entities"].values()))
    target_key = next(iter(target["entities"]))
    target["entities"][target_key] = copy.deepcopy(source_entity)
    target_envelope = envelope_instance(target)
    replacements = [target_envelope] + manifests[1]["instances"][1:]
    manifests[1] = make_manifest(
        manifests[1]["suite"], manifests[1]["generator_version"],
        manifests[1]["split"], replacements,
    )
    with pytest.raises(InstanceContractError, match="entity surface reused"):
        review_split_overlap(manifests)


def test_content_and_structure_tampering_fail_closed():
    instance = generate_instance("development", "cal_add", 0)
    changed = copy.deepcopy(instance)
    changed["content"]["seed"] += 1
    with pytest.raises(InstanceContractError, match="content_sha256"):
        validate_instance(changed)

    changed = copy.deepcopy(instance)
    changed["content"]["structure"]["workload"] += 1
    with pytest.raises(InstanceContractError, match="structure_sha256"):
        envelope_instance(changed["content"])

    changed = copy.deepcopy(instance)
    changed["content"]["seed"] += 1
    with pytest.raises(InstanceContractError, match="content_sha256"):
        validate_office_instance(changed)


def test_noncanonical_manifest_bytes_are_rejected(tmp_path):
    path = tmp_path / "development.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(InstanceContractError, match="canonical JSON"):
        manifest_cli.verify(tmp_path)


def test_canonical_loader_rejects_irregular_and_oversized_leaves(tmp_path, monkeypatch):
    irregular = tmp_path / "directory.json"
    irregular.mkdir()
    with pytest.raises(InstanceContractError, match="regular non-linked file"):
        instance_contracts.load_canonical_json(irregular)

    ordinary = tmp_path / "ordinary.json"
    ordinary.write_bytes(canonical_file_bytes({"ok": True}))
    monkeypatch.setattr(instance_contracts, "MAX_CANONICAL_FILE_BYTES", 1)
    with pytest.raises(InstanceContractError, match="exceeds the 1-byte"):
        instance_contracts.load_canonical_json(ordinary)


def test_retained_fallback_is_a_frozen_prefix_not_a_regeneration():
    retained = next(
        manifest for manifest in generate_all_manifests()
        if manifest["split"] == "retained"
    )
    by_family = {
        family: [
            item["content"]["id"] for item in retained["instances"]
            if item["content"]["family"] == family
        ]
        for family in FAMILIES
    }
    assert all(len(ids) == 20 for ids in by_family.values())
    assert by_family == {
        family: [
            "retained.%s.%02d" % (family.replace("_", "-"), index)
            for index in range(20)
        ]
        for family in FAMILIES
    }
