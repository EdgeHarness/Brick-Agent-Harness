"""S6G gates for canonical replay, independence, and office semantics."""
import copy
from collections import Counter

import pytest

import harness.instances as instance_contracts
from bench import generate_manifests as manifest_cli, s6_run
from domains.office_demo.generators import (
    D0_COHORT_ORDINALS,
    FAMILIES,
    GENERATOR_VERSION,
    SPLIT_ORDINALS,
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
    load_canonical_json,
    review_development_exposure,
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
    assert sum(item["instances"] for item in lock["manifests"]) == 352
    assert lock["overlap_review"]["passed"] is True
    assert lock["overlap_review"]["structures"] == 352


def test_every_instance_has_complete_semantics_and_shared_learning_budget():
    instances = [
        instance
        for manifest in generate_all_manifests()
        for instance in manifest["instances"]
    ]
    assert len(instances) == 352
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
        "instances": 352,
        "structures": 352,
        "entity_keys": 816,
        "entity_surfaces": 1472,
    }


def test_d0_cohorts_are_complete_balanced_and_semantically_disjoint():
    development = generate_all_manifests()[0]["instances"]
    cohorts = {
        name: [
            item for item in development
            if item["content"]["id"].startswith("development.%s." % name)
        ]
        for name in ("d0a", "d0b")
    }
    assert D0_COHORT_ORDINALS == {
        "d0a": (4, 9, 18, 31),
        "d0b": (7, 10, 17, 28),
    }
    assert SPLIT_ORDINALS == {
        "development": (4, 9, 18, 31, 7, 10, 17, 28),
        "validation": (0,),
        "sentinel": (16,),
        "retained": (
            1, 2, 3, 5, 11, 12, 20, 23, 24, 26, 29, 30,
            6, 13, 14, 15, 19, 21, 22, 25,
        ),
        "adversarial": (8, 27),
    }
    assert {
        ordinal for ordinals in SPLIT_ORDINALS.values() for ordinal in ordinals
    } == set(range(32))
    for cohort in cohorts.values():
        assert len(cohort) == 44
        schedule = s6_run._waves(cohort)
        assert len(schedule) == 44
        assert len(schedule) * 2 == 88
        assert Counter(order for _, _, _, order in schedule) == Counter({
            ("native_tools", "harness_full"): 22,
            ("harness_full", "native_tools"): 22,
        })
        assert Counter(item["content"]["family"] for item in cohort) == {
            family: 4 for family in FAMILIES
        }
    assert {
        item["content"]["structure_sha256"] for item in cohorts["d0a"]
    }.isdisjoint(
        item["content"]["structure_sha256"] for item in cohorts["d0b"]
    )
    for family in FAMILIES:
        profiles = []
        for cohort_name in ("d0a", "d0b"):
            family_cases = [
                item["content"]["structure"]
                for item in cohorts[cohort_name]
                if item["content"]["family"] == family
            ]
            marginal = {
                axis: Counter(item[axis] for item in family_cases)
                for axis in ("workload", "distractor_count", "constraint_profile")
            }
            assert marginal["workload"] == Counter({3: 1, 4: 1, 5: 1, 6: 1})
            assert marginal["distractor_count"] == Counter({0: 1, 1: 1, 2: 1, 3: 1})
            assert sorted(marginal["constraint_profile"].values()) == [2, 2]
            profiles.append(marginal)
        assert profiles[0] == profiles[1]


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
    for family in FAMILIES:
        prefix = [
            item["content"]["structure"]
            for item in retained["instances"]
            if item["content"]["family"] == family
        ][:12]
        assert Counter(item["workload"] for item in prefix) == Counter(
            {3: 3, 4: 3, 5: 3, 6: 3}
        )
        assert Counter(item["distractor_count"] for item in prefix) == Counter(
            {0: 3, 1: 3, 2: 3, 3: 3}
        )
        assert sorted(
            Counter(item["constraint_profile"] for item in prefix).values()
        ) == [6, 6]


def _exposure():
    return load_canonical_json(
        manifest_cli.DEFAULT_DIRECTORY / manifest_cli.EXPOSURE_NAME
    )


def _development():
    return generate_all_manifests()[0]


def test_exposure_ledger_is_digest_bound_and_reviews_all_fresh_d0_cases(tmp_path):
    review = manifest_cli.verify_exposure(
        development_manifest=_development()
    )
    assert review == {
        "schema_version": "brick.development-exposure-review/1",
        "passed": True,
        "source_release": "v0.11.0",
        "exposed_runs": 10,
        "exposed_instances": 4,
        "development_instances": 88,
    }
    ledger = manifest_cli.DEFAULT_DIRECTORY / manifest_cli.EXPOSURE_NAME
    changed = bytearray(ledger.read_bytes())
    changed[-2] = ord(" ")
    (tmp_path / manifest_cli.EXPOSURE_NAME).write_bytes(changed)
    with pytest.raises(InstanceContractError, match="ledger digest drifted"):
        manifest_cli.verify_exposure(tmp_path, _development())


@pytest.mark.parametrize(
    ("channel", "message"),
    (
        ("instance_id", "instance id"),
        ("content_sha256", "content digest"),
        ("structure_sha256", "structure digest"),
        ("entity_key", "entity key"),
        ("entity_surface", "entity surface"),
    ),
)
def test_exposure_review_rejects_every_identity_reuse_channel(channel, message):
    exposure = copy.deepcopy(_exposure())
    development = _development()
    target = development["instances"][0]
    content = target["content"]
    if channel == "instance_id":
        changed = copy.deepcopy(target)
        changed["content"]["id"] = exposure["instances"][0]["instance_id"]
        changed = envelope_instance(changed["content"])
        development = make_manifest(
            development["suite"], development["generator_version"],
            development["split"], [changed] + development["instances"][1:],
        )
    elif channel == "content_sha256":
        exposure["instances"][0]["content_sha256"] = target["content_sha256"]
    elif channel == "structure_sha256":
        exposure["instances"][0]["structure_sha256"] = content[
            "structure_sha256"
        ]
    elif channel == "entity_key":
        exposure["instances"][0]["entity_keys"] = [
            content["entity_keys"][0].casefold()
        ]
    else:
        surface = next(
            value
            for entity in content["entities"].values()
            for value in entity.values()
            if isinstance(value, str) and value
        )
        exposure["instances"][0]["entity_surfaces"] = [surface.casefold()]
    with pytest.raises(InstanceContractError, match=message):
        review_development_exposure(exposure, development)
