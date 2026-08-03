"""Write or verify the frozen S6G office split manifests.

Usage from the repository root:

    python -m bench.generate_manifests --verify
    python -m bench.generate_manifests --write
"""
import argparse
import json
from pathlib import Path

from domains.office_demo.generators import (
    GENERATOR_VERSION,
    SUITE,
    generate_all_manifests,
)
from harness.instances import (
    LOCK_SCHEMA,
    SPLITS,
    InstanceContractError,
    canonical_file_bytes,
    load_canonical_json,
    replace_canonical_json,
    review_development_exposure,
    review_split_overlap,
    sha256_bytes,
    validate_manifest,
)


HERE = Path(__file__).resolve().parent
DEFAULT_DIRECTORY = HERE / "manifests" / "office-v1"
LOCK_NAME = "manifest-lock.json"
EXPOSURE_NAME = "development-exposure-v0.11.0.json"
EXPOSURE_SHA256 = "46ef00414006ac29ca64e137c2fae8ba843887f7c78470edfdff612346ab327e"


def _manifest_name(split):
    return "%s.json" % split


def _lock(manifests, digests, review):
    return {
        "schema_version": LOCK_SCHEMA,
        "suite": SUITE,
        "generator_version": GENERATOR_VERSION,
        "manifests": [
            {
                "split": manifest["split"],
                "path": _manifest_name(manifest["split"]),
                "sha256": digests[manifest["split"]],
                "instances": len(manifest["instances"]),
            }
            for manifest in manifests
        ],
        "overlap_review": review,
    }


def _validate_lock(lock):
    expected = {
        "schema_version", "suite", "generator_version", "manifests",
        "overlap_review",
    }
    if not isinstance(lock, dict) or set(lock) != expected:
        raise InstanceContractError("manifest lock has unexpected keys")
    if lock["schema_version"] != LOCK_SCHEMA:
        raise InstanceContractError("unsupported manifest-lock schema")
    if lock["suite"] != SUITE or lock["generator_version"] != GENERATOR_VERSION:
        raise InstanceContractError("manifest lock suite/version mismatch")
    entries = lock["manifests"]
    if not isinstance(entries, list) or len(entries) != len(SPLITS):
        raise InstanceContractError("manifest lock must bind all five splits")
    seen = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"split", "path", "sha256", "instances"}:
            raise InstanceContractError("invalid manifest-lock entry")
        if entry["split"] not in SPLITS or entry["path"] != _manifest_name(entry["split"]):
            raise InstanceContractError("manifest-lock path/split mismatch")
        if (
            not isinstance(entry["sha256"], str)
            or len(entry["sha256"]) != 64
            or any(character not in "0123456789abcdef" for character in entry["sha256"])
        ):
            raise InstanceContractError("invalid manifest-lock digest")
        if isinstance(entry["instances"], bool) or not isinstance(entry["instances"], int) or entry["instances"] <= 0:
            raise InstanceContractError("invalid manifest-lock instance count")
        seen.append(entry["split"])
    if seen != list(SPLITS):
        raise InstanceContractError("manifest-lock splits are not in canonical order")
    return lock


def build():
    manifests = generate_all_manifests()
    review = review_split_overlap(manifests)
    digests = {
        manifest["split"]: sha256_bytes(canonical_file_bytes(manifest))
        for manifest in manifests
    }
    lock = _validate_lock(_lock(manifests, digests, review))
    return manifests, lock


def write(directory=DEFAULT_DIRECTORY):
    directory = Path(directory)
    manifests, lock = build()
    for manifest in manifests:
        replace_canonical_json(directory / _manifest_name(manifest["split"]), manifest)
    replace_canonical_json(directory / LOCK_NAME, lock)
    return lock


def verify_exposure(directory=DEFAULT_DIRECTORY, development_manifest=None):
    directory = Path(directory)
    path = directory / EXPOSURE_NAME
    payload = path.read_bytes()
    if sha256_bytes(payload) != EXPOSURE_SHA256:
        raise InstanceContractError("development exposure ledger digest drifted")
    exposure = load_canonical_json(path)
    development = development_manifest or load_canonical_json(
        directory / "development.json"
    )
    return review_development_exposure(exposure, development)


def verify(directory=DEFAULT_DIRECTORY):
    directory = Path(directory)
    expected_manifests, expected_lock = build()
    actual_manifests = []
    for expected in expected_manifests:
        path = directory / _manifest_name(expected["split"])
        actual = load_canonical_json(path)
        validate_manifest(actual)
        if canonical_file_bytes(actual) != canonical_file_bytes(expected):
            raise InstanceContractError("%s does not replay from its generator" % path)
        actual_manifests.append(actual)
    review = review_split_overlap(actual_manifests)
    if review != expected_lock["overlap_review"]:
        raise InstanceContractError("committed overlap review does not reproduce")
    actual_lock = _validate_lock(load_canonical_json(directory / LOCK_NAME))
    if canonical_file_bytes(actual_lock) != canonical_file_bytes(expected_lock):
        raise InstanceContractError("manifest lock does not bind generated bytes")
    development = next(
        manifest for manifest in actual_manifests
        if manifest["split"] == "development"
    )
    verify_exposure(directory, development)
    return actual_lock


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    args = parser.parse_args(argv)
    lock = write(args.directory) if args.write else verify(args.directory)
    print(json.dumps({
        "status": "written" if args.write else "verified",
        "directory": str(args.directory),
        "instances": sum(item["instances"] for item in lock["manifests"]),
        "overlap_review": lock["overlap_review"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
