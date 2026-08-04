"""Canonical, domain-neutral task-instance and split-manifest contracts.

S6G treats generated cases as versioned research inputs, not as convenient
prompt strings.  Every instance is a content-addressed envelope; every manifest
is canonical JSON; and overlap review is computed from semantic structure and
declared fictional-entity identities rather than trusting labels alone.
"""
import hashlib
import json
import os
import re
import stat
import tempfile
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from .evidence import canonical_json_bytes


INSTANCE_SCHEMA = "brick.task-instance/1"
MANIFEST_SCHEMA = "brick.task-manifest/1"
LOCK_SCHEMA = "brick.manifest-lock/1"
EXPOSURE_SCHEMA = "brick.development-exposure/1"
# ``SPLITS`` is the released office-generators/1.x split contract.  Keep it
# stable so the retired suite continues to replay byte-for-byte.  Successor
# studies may additionally use an isolated calibration split.
SPLITS = ("development", "validation", "sentinel", "retained", "adversarial")
SUPPORTED_SPLITS = (
    "development",
    "calibration",
    "validation",
    "sentinel",
    "retained",
    "adversarial",
)
MAX_CANONICAL_FILE_BYTES = 64 * 1024 * 1024

_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_INSTANCE_KEYS = frozenset({"schema_version", "content_sha256", "content"})
_CONTENT_KEYS = frozenset(
    {
        "id",
        "domain",
        "domain_version",
        "family",
        "family_version",
        "generator_version",
        "split",
        "seed",
        "structural_template",
        "structure_sha256",
        "structure",
        "policy_family",
        "today",
        "prompt",
        "ordered_subepisodes",
        "opportunity_budget",
        "tool_names",
        "initial_state",
        "required_effects",
        "forbidden_effects",
        "entities",
        "entity_keys",
    }
)
_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "suite",
        "generator_version",
        "split",
        "family_counts",
        "instances",
    }
)


class InstanceContractError(ValueError):
    """A generated input or manifest violates its frozen contract."""


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def _exact_keys(value, expected, label):
    if not isinstance(value, dict):
        raise InstanceContractError("%s must be an object" % label)
    actual = set(value)
    if actual != set(expected):
        missing = sorted(set(expected) - actual)
        extra = sorted(actual - set(expected))
        raise InstanceContractError(
            "%s keys differ (missing=%r, extra=%r)" % (label, missing, extra)
        )


def _text(value, label, identifier=False):
    if not isinstance(value, str) or not value:
        raise InstanceContractError("%s must be a nonempty string" % label)
    if unicodedata.normalize("NFC", value) != value:
        raise InstanceContractError("%s must already be NFC-normalized" % label)
    if any(ord(character) < 0x20 for character in value):
        raise InstanceContractError("%s contains a control character" % label)
    if identifier and not _ID.fullmatch(value):
        raise InstanceContractError("%s is not a portable identifier" % label)
    return value


def _string_list(value, label, *, nonempty=False, identifiers=False):
    if not isinstance(value, list):
        raise InstanceContractError("%s must be a list" % label)
    if nonempty and not value:
        raise InstanceContractError("%s cannot be empty" % label)
    checked = [
        _text(item, "%s[%d]" % (label, index), identifier=identifiers)
        for index, item in enumerate(value)
    ]
    if len(set(checked)) != len(checked):
        raise InstanceContractError("%s contains duplicates" % label)
    return checked


def _json_value(value, label):
    try:
        # Canonicalization rejects unsupported and non-finite JSON values.
        canonical_json_bytes(value, allow_float=False)
    except (TypeError, ValueError) as exc:
        raise InstanceContractError("%s is not canonical integer JSON" % label) from exc
    return value


def structure_sha256(structure):
    if not isinstance(structure, dict) or not structure:
        raise InstanceContractError("structure must be a nonempty object")
    return sha256_bytes(canonical_json_bytes(structure, allow_float=False))


def content_sha256(content):
    return sha256_bytes(canonical_json_bytes(content, allow_float=False))


def envelope_instance(content):
    """Validate content and bind it to its canonical SHA-256 digest."""
    envelope = {
        "schema_version": INSTANCE_SCHEMA,
        "content_sha256": content_sha256(content),
        "content": content,
    }
    return validate_instance(envelope)


def validate_instance(instance):
    _exact_keys(instance, _INSTANCE_KEYS, "instance")
    if instance["schema_version"] != INSTANCE_SCHEMA:
        raise InstanceContractError("unsupported instance schema")
    digest = instance["content_sha256"]
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise InstanceContractError("instance content_sha256 is invalid")
    content = instance["content"]
    _exact_keys(content, _CONTENT_KEYS, "instance content")
    for field in (
        "id",
        "domain",
        "family",
        "split",
        "structural_template",
        "policy_family",
    ):
        _text(content[field], field, identifier=True)
    for field in ("domain_version", "family_version", "generator_version", "today"):
        _text(content[field], field)
    if content["split"] not in SUPPORTED_SPLITS:
        raise InstanceContractError("unknown instance split")
    seed = content["seed"]
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2 ** 63:
        raise InstanceContractError("seed must be an unsigned 63-bit integer")
    structure = content["structure"]
    _json_value(structure, "structure")
    expected_structure = structure_sha256(structure)
    if content["structure_sha256"] != expected_structure:
        raise InstanceContractError("structure_sha256 does not match structure")
    if not content["structural_template"].endswith(expected_structure[:16]):
        raise InstanceContractError(
            "structural_template must be derived from the semantic structure hash"
        )

    prompt = content["prompt"]
    subepisodes = content["ordered_subepisodes"]
    if not isinstance(subepisodes, list):
        raise InstanceContractError("ordered_subepisodes must be a list")
    if subepisodes:
        if prompt is not None:
            raise InstanceContractError("multi-episode instances must have prompt=null")
        if len(subepisodes) != 2:
            raise InstanceContractError("learning instances require exactly two subepisodes")
        ids = []
        for index, episode in enumerate(subepisodes):
            _exact_keys(episode, {"id", "prompt", "required_effects"}, "subepisode")
            ids.append(_text(episode["id"], "subepisode id", identifier=True))
            _text(episode["prompt"], "subepisode prompt")
            if not isinstance(episode["required_effects"], list) or not episode["required_effects"]:
                raise InstanceContractError("subepisode required_effects cannot be empty")
            _json_value(episode["required_effects"], "subepisode required_effects")
        if len(set(ids)) != len(ids):
            raise InstanceContractError("subepisode ids must be unique")
    else:
        _text(prompt, "prompt")

    budget = content["opportunity_budget"]
    _exact_keys(
        budget,
        {"model_calls", "generated_tokens", "shared_across_subepisodes"},
        "opportunity_budget",
    )
    for field in ("model_calls", "generated_tokens"):
        value = budget[field]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise InstanceContractError("opportunity_budget.%s must be positive" % field)
    if type(budget["shared_across_subepisodes"]) is not bool:
        raise InstanceContractError(
            "opportunity_budget.shared_across_subepisodes must be boolean"
        )
    if budget["shared_across_subepisodes"] != bool(subepisodes):
        raise InstanceContractError("opportunity budget sharing disagrees with episode shape")

    _string_list(content["tool_names"], "tool_names", nonempty=True, identifiers=True)
    _string_list(content["entity_keys"], "entity_keys", nonempty=True, identifiers=True)
    if content["entity_keys"] != sorted(content["entity_keys"]):
        raise InstanceContractError("entity_keys must be sorted")
    entities = content["entities"]
    if not isinstance(entities, dict) or not entities:
        raise InstanceContractError("entities must be a nonempty object")
    if sorted(entities) != content["entity_keys"]:
        raise InstanceContractError("entities keys must exactly match entity_keys")
    _json_value(entities, "entities")
    if not isinstance(content["initial_state"], dict):
        raise InstanceContractError("initial_state must be an object")
    _json_value(content["initial_state"], "initial_state")
    effects = content["required_effects"]
    if not isinstance(effects, list) or not effects:
        raise InstanceContractError("required_effects must be a nonempty list")
    if not all(isinstance(effect, dict) and effect for effect in effects):
        raise InstanceContractError("required_effects entries must be nonempty objects")
    _json_value(effects, "required_effects")
    _string_list(content["forbidden_effects"], "forbidden_effects", nonempty=True)

    actual_digest = content_sha256(content)
    if digest != actual_digest:
        raise InstanceContractError("instance content_sha256 does not match content")
    return instance


def make_manifest(suite, generator_version, split, instances):
    if split not in SUPPORTED_SPLITS:
        raise InstanceContractError("unknown manifest split")
    ordered = sorted(instances, key=lambda item: item["content"]["id"])
    counts = Counter(item["content"]["family"] for item in ordered)
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "suite": suite,
        "generator_version": generator_version,
        "split": split,
        "family_counts": dict(sorted(counts.items())),
        "instances": ordered,
    }
    return validate_manifest(manifest)


def validate_manifest(manifest):
    _exact_keys(manifest, _MANIFEST_KEYS, "manifest")
    if manifest["schema_version"] != MANIFEST_SCHEMA:
        raise InstanceContractError("unsupported manifest schema")
    _text(manifest["suite"], "manifest suite", identifier=True)
    _text(manifest["generator_version"], "manifest generator_version")
    if manifest["split"] not in SUPPORTED_SPLITS:
        raise InstanceContractError("unknown manifest split")
    if not isinstance(manifest["instances"], list) or not manifest["instances"]:
        raise InstanceContractError("manifest instances cannot be empty")
    ids = []
    digests = []
    counts = Counter()
    for instance in manifest["instances"]:
        validate_instance(instance)
        content = instance["content"]
        if content["split"] != manifest["split"]:
            raise InstanceContractError("manifest contains an instance from another split")
        if content["generator_version"] != manifest["generator_version"]:
            raise InstanceContractError("manifest generator version mismatch")
        ids.append(content["id"])
        digests.append(instance["content_sha256"])
        counts[content["family"]] += 1
    if ids != sorted(ids) or len(set(ids)) != len(ids):
        raise InstanceContractError("manifest instance ids must be sorted and unique")
    if len(set(digests)) != len(digests):
        raise InstanceContractError("manifest contains duplicate instance content")
    expected_counts = dict(sorted(counts.items()))
    if manifest["family_counts"] != expected_counts:
        raise InstanceContractError("manifest family_counts do not match instances")
    return manifest


def review_split_overlap(manifests, required_splits=SPLITS):
    """Fail if splits reuse semantic templates or declared fictional entities."""
    required_splits = tuple(required_splits)
    if (
        not required_splits
        or len(set(required_splits)) != len(required_splits)
        or any(split not in SUPPORTED_SPLITS for split in required_splits)
    ):
        raise InstanceContractError("required split set is invalid")
    by_split = {}
    structures = {}
    templates = {}
    entities = defaultdict(set)
    surfaces = defaultdict(set)
    entity_owners = {}
    surface_owners = {}
    all_ids = set()
    for manifest in manifests:
        validate_manifest(manifest)
        split = manifest["split"]
        if split in by_split:
            raise InstanceContractError("duplicate manifest for split %s" % split)
        by_split[split] = manifest
        for instance in manifest["instances"]:
            content = instance["content"]
            instance_id = content["id"]
            if instance_id in all_ids:
                raise InstanceContractError("instance id reused across manifests")
            all_ids.add(instance_id)
            for registry, value, label in (
                (structures, content["structure_sha256"], "semantic structure"),
                (templates, content["structural_template"], "structural template"),
            ):
                previous = registry.get(value)
                if previous is not None:
                    raise InstanceContractError(
                        "%s reused by %s and %s" % (label, previous, instance_id)
                    )
                registry[value] = instance_id
            for key in content["entity_keys"]:
                folded_key = key.casefold()
                previous_key = entity_owners.get(folded_key)
                if previous_key is not None:
                    raise InstanceContractError(
                        "entity key reused by %s and %s" % (previous_key, instance_id)
                    )
                entity_owners[folded_key] = instance_id
                entities[split].add(folded_key)
                entity = content["entities"][key]
                if not isinstance(entity, dict) or not entity:
                    raise InstanceContractError("entity records must be nonempty objects")
                for value in entity.values():
                    if isinstance(value, str) and value:
                        folded_surface = unicodedata.normalize("NFC", value).casefold()
                        previous_surface = surface_owners.get(folded_surface)
                        if previous_surface is not None:
                            raise InstanceContractError(
                                "entity surface reused by %s and %s"
                                % (previous_surface, instance_id)
                            )
                        surface_owners[folded_surface] = instance_id
                        surfaces[split].add(folded_surface)
    if set(by_split) != set(required_splits):
        raise InstanceContractError(
            "overlap review requires exactly: %s"
            % ", ".join(required_splits)
        )
    for left_index, left in enumerate(required_splits):
        for right in required_splits[left_index + 1:]:
            shared = entities[left] & entities[right]
            if shared:
                raise InstanceContractError(
                    "splits %s and %s share entity keys: %r"
                    % (left, right, sorted(shared)[:5])
                )
            shared_surfaces = surfaces[left] & surfaces[right]
            if shared_surfaces:
                raise InstanceContractError(
                    "splits %s and %s share entity surfaces: %r"
                    % (left, right, sorted(shared_surfaces)[:5])
                )
    return {
        "schema_version": "brick.split-overlap-review/1",
        "passed": True,
        "splits": list(required_splits),
        "instances": len(all_ids),
        "structures": len(structures),
        "entity_keys": sum(len(value) for value in entities.values()),
        "entity_surfaces": sum(len(value) for value in surfaces.values()),
    }


def validate_development_exposure(value):
    """Validate the immutable record of score-visible S6C development cases."""

    _exact_keys(
        value,
        {"schema_version", "source_release", "source_commit", "runs", "instances"},
        "development exposure",
    )
    if value["schema_version"] != EXPOSURE_SCHEMA:
        raise InstanceContractError("unsupported development-exposure schema")
    if value["source_release"] != "v0.11.0":
        raise InstanceContractError("development exposure must bind v0.11.0")
    if value["source_commit"] != "9740ffa7e8e7104b74797a035d7d21eda8dfec0d":
        raise InstanceContractError("development exposure source commit differs")
    runs = value["runs"]
    instances = value["instances"]
    if not isinstance(runs, list) or len(runs) != 10:
        raise InstanceContractError("development exposure must record ten live runs")
    if not isinstance(instances, list) or len(instances) != 4:
        raise InstanceContractError("development exposure must record four unique cases")

    run_ids = []
    referenced = []
    for index, run in enumerate(runs):
        _exact_keys(run, {"run_id", "instance_id"}, "exposure run")
        run_ids.append(_text(run["run_id"], "run_id", identifier=True))
        referenced.append(_text(run["instance_id"], "instance_id", identifier=True))
    if run_ids != sorted(run_ids) or len(set(run_ids)) != len(run_ids):
        raise InstanceContractError("exposure run ids must be sorted and unique")

    instance_ids = []
    for index, record in enumerate(instances):
        _exact_keys(
            record,
            {
                "instance_id", "content_sha256", "structure_sha256",
                "entity_keys", "entity_surfaces",
            },
            "exposure instance",
        )
        instance_ids.append(
            _text(record["instance_id"], "instance_id", identifier=True)
        )
        for field in ("content_sha256", "structure_sha256"):
            if not isinstance(record[field], str) or not _SHA256.fullmatch(record[field]):
                raise InstanceContractError("exposure %s is invalid" % field)
        keys = _string_list(record["entity_keys"], "entity_keys", nonempty=True)
        surfaces = _string_list(
            record["entity_surfaces"], "entity_surfaces", nonempty=True,
        )
        if keys != sorted(keys) or any(key != key.casefold() for key in keys):
            raise InstanceContractError("exposure entity keys must be sorted and folded")
        if surfaces != sorted(surfaces) or any(
            surface != surface.casefold() for surface in surfaces
        ):
            raise InstanceContractError(
                "exposure entity surfaces must be sorted and folded"
            )
    if instance_ids != sorted(instance_ids) or len(set(instance_ids)) != len(instance_ids):
        raise InstanceContractError("exposure instance ids must be sorted and unique")
    if set(referenced) != set(instance_ids):
        raise InstanceContractError("exposure runs and instances do not agree")
    return value


def review_development_exposure(exposure, development_manifest):
    """Reject any D0 input that reuses score-visible development material."""

    validate_development_exposure(exposure)
    validate_manifest(development_manifest)
    if development_manifest["split"] != "development":
        raise InstanceContractError("exposure review requires the development manifest")
    exposed_ids = {item["instance_id"] for item in exposure["instances"]}
    exposed_contents = {item["content_sha256"] for item in exposure["instances"]}
    exposed_structures = {item["structure_sha256"] for item in exposure["instances"]}
    exposed_keys = {
        key for item in exposure["instances"] for key in item["entity_keys"]
    }
    exposed_surfaces = {
        surface
        for item in exposure["instances"]
        for surface in item["entity_surfaces"]
    }
    for instance in development_manifest["instances"]:
        content = instance["content"]
        comparisons = (
            (content["id"] in exposed_ids, "instance id"),
            (instance["content_sha256"] in exposed_contents, "content digest"),
            (content["structure_sha256"] in exposed_structures, "structure digest"),
            (
                bool({key.casefold() for key in content["entity_keys"]} & exposed_keys),
                "entity key",
            ),
            (
                bool(
                    {
                        unicodedata.normalize("NFC", surface).casefold()
                        for entity in content["entities"].values()
                        for surface in entity.values()
                        if isinstance(surface, str) and surface
                    }
                    & exposed_surfaces
                ),
                "entity surface",
            ),
        )
        for reused, label in comparisons:
            if reused:
                raise InstanceContractError(
                    "D0 development input reuses exposed %s: %s"
                    % (label, content["id"])
                )
    return {
        "schema_version": "brick.development-exposure-review/1",
        "passed": True,
        "source_release": exposure["source_release"],
        "exposed_runs": len(exposure["runs"]),
        "exposed_instances": len(exposure["instances"]),
        "development_instances": len(development_manifest["instances"]),
    }


def canonical_file_bytes(value):
    return canonical_json_bytes(value, allow_float=False, newline=True)


def load_canonical_json(path):
    path = Path(path)
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise InstanceContractError("cannot inspect canonical JSON file %s" % path) from exc
    reparse = bool(
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink() or reparse:
        raise InstanceContractError("%s must be a regular non-linked file" % path)
    if metadata.st_size > MAX_CANONICAL_FILE_BYTES:
        raise InstanceContractError(
            "%s exceeds the %d-byte canonical JSON limit"
            % (path, MAX_CANONICAL_FILE_BYTES)
        )
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise InstanceContractError("cannot read canonical JSON file %s" % path) from exc
    if len(payload) > MAX_CANONICAL_FILE_BYTES:
        raise InstanceContractError(
            "%s exceeds the %d-byte canonical JSON limit"
            % (path, MAX_CANONICAL_FILE_BYTES)
        )
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InstanceContractError("invalid UTF-8 JSON in %s" % path) from exc
    if payload != canonical_file_bytes(value):
        raise InstanceContractError("%s is not canonical JSON" % path)
    return value


def replace_canonical_json(path, value):
    """Atomically replace one generated canonical JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_file_bytes(value)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return sha256_bytes(payload)


__all__ = [
    "INSTANCE_SCHEMA",
    "MANIFEST_SCHEMA",
    "LOCK_SCHEMA",
    "EXPOSURE_SCHEMA",
    "MAX_CANONICAL_FILE_BYTES",
    "SPLITS",
    "SUPPORTED_SPLITS",
    "InstanceContractError",
    "canonical_file_bytes",
    "content_sha256",
    "envelope_instance",
    "load_canonical_json",
    "make_manifest",
    "replace_canonical_json",
    "review_development_exposure",
    "review_split_overlap",
    "sha256_bytes",
    "structure_sha256",
    "validate_instance",
    "validate_development_exposure",
    "validate_manifest",
]
