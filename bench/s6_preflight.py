"""Read-only S6C host, model, protocol, and manifest preflight.

This command never starts an experiment and never changes Ollama or the
worktree.  It emits one JSON document suitable for binding into run metadata.
"""

import argparse
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

import requests

from bench.generate_manifests import (
    EXPOSURE_NAME,
    EXPOSURE_SHA256,
    verify as verify_manifests,
)
from domains.office_demo.contracts import build_registry
from harness.evidence import canonical_json_bytes
from harness.experiment import protocol_sha256
from harness.instances import load_canonical_json


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_PROTOCOL = HERE / "s6_protocol.json"
_MODEL_DIGEST = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")

IMPLEMENTATION_PATHS = (
    "harness/experiment.py",
    "harness/evidence.py",
    "harness/faults.py",
    "harness/errors.py",
    "harness/schema.py",
    "harness/typed_executor.py",
    "harness/parsing.py",
    "harness/grading.py",
    "harness/instances.py",
    "harness/builtin_tools.py",
    "harness/domain.py",
    "bench/generate_manifests.py",
    "bench/s6_run.py",
    "bench/s6_preflight.py",
    "bench/s6_rules_reference.py",
    "bench/s7_analysis.py",
    "bench/s7_artifacts.py",
    "bench/s7_contract.py",
    "bench/s7_decision.py",
    "bench/s7_floor_audit.py",
    "bench/s7_preflight.py",
    "bench/s7_protocol.json",
    "bench/s7_protocol_v1.0.0.json",
    "bench/s7_protocol_v1.0.1.json",
    "bench/s7_run.py",
    "evidence/s7/d0a-instrument-audit.json",
    "evidence/s7/d0a-ollama-parser-audit.json",
    "requirements-analysis.txt",
    "bench/manifests/office-v1/" + EXPOSURE_NAME,
)

DOMAIN_PATHS = (
    "domains/office_demo/generators.py",
    "domains/office_demo/world.py",
    "domains/office_demo/office_files.py",
    "domains/office_demo/tools.py",
    "domains/office_demo/contracts.py",
    "domains/office_demo/generated_grader.py",
    "domains/office_demo/strict_graders.py",
    "domains/office_demo/rules_reference.py",
)


def _git(*args):
    return subprocess.run(
        ["git", *args],
        cwd=str(ROOT),
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()


def _sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _verify_f0_binding(protocol):
    binding = protocol["f0_binding"]
    attestation = ROOT / binding["attestation_path"]
    if attestation.resolve().parent != (ROOT / "evidence" / "f0").resolve():
        raise RuntimeError("F0 attestation path escaped evidence/f0")
    if _sha256_file(attestation) != binding["attestation_sha256"]:
        raise RuntimeError("F0 release attestation digest drifted")
    document = json.loads(attestation.read_text(encoding="utf-8"))
    primary = document.get("primary_model")
    expected_digest = binding["primary_model_digest"].removeprefix("sha256:")
    if (
        document.get("schema_version") != "brick.f0.release-attestation/1"
        or document.get("release") != binding["release"]
        or document.get("run_id") != binding["run_id"]
        or document.get("ollama_version") != binding["ollama_version"]
        or not isinstance(primary, dict)
        or primary.get("tag") != protocol["primary_model"]
        or primary.get("digest") != expected_digest
        or primary.get("status") != "eligible"
        or primary.get("native_tools_passed") is not True
        or primary.get("option_recognition_passed") is not True
        or primary.get("median_eval_tps") != binding["median_eval_tps"]
        or document.get("environment_status") != "pass"
        or document.get("storage_status") != "pass"
        or document.get("summary_status") != "pass"
    ):
        raise RuntimeError("S6 protocol does not match the passed F0 attestation")
    return document


def implementation_sha256():
    paths = tuple(ROOT / path for path in IMPLEMENTATION_PATHS)
    document = {
        path.relative_to(ROOT).as_posix(): _sha256_file(path) for path in paths
    }
    return hashlib.sha256(canonical_json_bytes(document)).hexdigest()


def domain_sha256():
    paths = tuple(ROOT / path for path in DOMAIN_PATHS)
    document = {
        path.relative_to(ROOT).as_posix(): _sha256_file(path) for path in paths
    }
    return hashlib.sha256(canonical_json_bytes(document)).hexdigest()


def _ollama(protocol):
    endpoint = protocol["transport"]["endpoint"]
    session = requests.Session()
    session.trust_env = False
    version_response = session.get(endpoint + "/api/version", timeout=(5, 30))
    version_response.raise_for_status()
    tags_response = session.get(endpoint + "/api/tags", timeout=(5, 30))
    tags_response.raise_for_status()
    version = version_response.json()
    tags = tags_response.json()
    matches = [
        item
        for item in tags.get("models", [])
        if item.get("name", item.get("model")) == protocol["primary_model"]
    ]
    if len(matches) != 1 or not _MODEL_DIGEST.fullmatch(
        str(matches[0].get("digest", ""))
    ):
        raise RuntimeError("the exact primary model and immutable digest are absent")
    digest = str(matches[0]["digest"])
    if not digest.startswith("sha256:"):
        digest = "sha256:" + digest
    if version.get("version") != protocol["f0_binding"]["ollama_version"]:
        raise RuntimeError("the live Ollama version differs from the F0 binding")
    if digest != protocol["f0_binding"]["primary_model_digest"]:
        raise RuntimeError("the live model digest differs from the F0 binding")
    return {
        "version": version.get("version"),
        "primary_model": protocol["primary_model"],
        "model_digest": digest,
    }


def collect(protocol_path=DEFAULT_PROTOCOL, require_clean=False):
    protocol = json.loads(Path(protocol_path).read_text(encoding="utf-8"))
    protocol_sha256(protocol)
    _verify_f0_binding(protocol)
    manifest_lock = verify_manifests()
    native = build_registry(alias_recovery=False)
    harness = build_registry(alias_recovery=True)
    if native.native_schemas() != harness.native_schemas():
        raise RuntimeError("primary conditions expose different native schemas")
    names = native.names()
    if names != harness.names():
        raise RuntimeError("primary condition tool ordering differs")
    manifests_root = HERE / "manifests" / "office-v1"
    for split in ("development", "validation", "sentinel", "retained", "adversarial"):
        manifest = load_canonical_json(manifests_root / (split + ".json"))
        for instance in manifest["instances"]:
            content = instance["content"]
            if content["tool_names"] != names:
                raise RuntimeError("manifest tool ordering drifted for " + content["id"])
            if content["opportunity_budget"]["model_calls"] != protocol["opportunity_budget"]["model_calls"]:
                raise RuntimeError("manifest model-call budget drifted")
            if content["opportunity_budget"]["generated_tokens"] != protocol["opportunity_budget"]["generated_tokens"]:
                raise RuntimeError("manifest generated-token budget drifted")
    clean = _git("status", "--porcelain=v1") == ""
    if require_clean and not clean:
        raise RuntimeError("a gate preflight requires a clean worktree")
    if os.name != "nt" or platform.machine().casefold() not in {"arm64", "aarch64"}:
        raise RuntimeError("live S6 execution is supported only on native Windows ARM64")
    if not ((3, 9) <= sys.version_info[:2] < (3, 14)):
        raise RuntimeError("Python must satisfy >=3.9,<3.14")
    ollama = _ollama(protocol)
    packages = {}
    for package in ("requests", "openpyxl", "python-pptx"):
        packages[package] = metadata.version(package)
    schema_bytes = canonical_json_bytes(native.native_schemas())
    fingerprint = {
        "schema_version": "brick.s6.environment/1",
        "os": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "packages": packages,
        "ollama": ollama,
        "git_commit": _git("rev-parse", "HEAD"),
        "git_clean": clean,
        "protocol_sha256": protocol_sha256(protocol),
        "implementation_sha256": implementation_sha256(),
        "domain_sha256": domain_sha256(),
        "tool_schema_sha256": hashlib.sha256(schema_bytes).hexdigest(),
        "manifest_lock_sha256": hashlib.sha256(
            canonical_json_bytes(manifest_lock)
        ).hexdigest(),
        "development_exposure_sha256": EXPOSURE_SHA256,
        "f0_attestation_sha256": protocol["f0_binding"]["attestation_sha256"],
    }
    return {
        "schema_version": "brick.s6.preflight/1",
        "passed": True,
        "require_clean": bool(require_clean),
        "environment": fingerprint,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--require-clean", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = collect(args.protocol, require_clean=args.require_clean)
    except Exception as exc:
        result = {
            "schema_version": "brick.s6.preflight/1",
            "passed": False,
            "error": "%s: %s" % (type(exc).__name__, exc),
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
