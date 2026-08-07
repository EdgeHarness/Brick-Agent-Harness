"""Native execution surface for the successor development and research program.

This module does not weaken authorization.  Development calls require a
clean-commit, host-bound shakeout authorization.  Research phases require the
replacement v0.13.3 program authorization. Console output never contains task
scores; all evidence is marker-last and resumable.
"""

import argparse
import copy
import datetime
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import requests

from bench.next_study_program import (
    BenchmarkLease, HOST_FINGERPRINT_SCHEMA, RUNTIME_FINGERPRINT_SCHEMA,
    REQUIRED_ARTIFACT_DIGESTS, SEALED_GATE_SCHEMA, advance_program,
    build_authorization, build_fingerprint, calibration_decision,
    execution_allowed, initial_program_state, sentinel_decision,
    primary_mask_key_commitment, validate_authorization, validate_program_state,
)
from bench.next_study_fable_reconciliation import (
    DEFAULT_PATH as FABLE_RECONCILIATION_PATH,
)
from bench.next_study_successor import (
    AUTHORIZATION_PATH as SUCCESSOR_AUTHORIZATION_PATH,
    CLOSURE_PATH as SUCCESSOR_CLOSURE_PATH,
    load_closure,
)
from bench.next_study_review import review_packet
from bench.next_study_report import build_study_report
from bench.next_study_descriptive import (
    build_report as build_descriptive_report, eligible_schedule,
    extract_descriptive_results, extract_primary_trial_0_controls,
    seal_descriptive_eligibility, validate_eligible_schedule,
)
from bench.next_study_schedule import (
    build_development_shakeout_schedule, build_descriptive_schedule,
    build_phase_schedule, validate_development_shakeout_schedule,
    validate_descriptive_schedule, validate_phase_schedule,
)
from bench.next_study_statistics import build_protocol as build_analysis_protocol
from bench.next_study_runtime import (
    build_masked_grade_ledger, build_release_archive_manifest,
    extract_attempt_records, resume_queue, seal_recovery_attestation,
    unmask_primary, verify_release,
)
from bench.next_study_statistics import analyze_primary
from bench.next_study_validated_outcomes import (
    DEFAULT_PATH as VALIDATED_OUTCOMES_PATH, load_manifests,
    validate_validated_outcomes,
)
from domains.office_demo.contracts import build_registry
from domains.office_demo.generators_v2 import validate_office_instance_v2
from domains.office_demo.reviewed_grader_v2 import (
    GRADER_VERSION, build_grader, task_id_for,
)
from domains.office_demo.world import World
from harness.evidence import (
    ACTIONS_SCHEMA, GRADE_SCHEMA, RESULT_SCHEMA, STATE_SCHEMA, AttemptKey,
    EvidenceStore, canonical_json_bytes, validate_committed,
)
from harness.experiment import (
    EXPERIMENT_VERSION, AttemptMemory, ConditionSpec, ExecutionContext, OllamaTransport,
    condition_registry, protocol_sha256, run_attempt, run_raw_json_attempt,
    transcript_markdown, validate_protocol as validate_execution_protocol,
)
from harness.grading import GradingEvidence
from harness.instances import load_canonical_json, sha256_bytes


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIRECTORY = ROOT / "bench" / "manifests" / "office-v2"
BASE_EXECUTION_PROTOCOL = ROOT / "bench" / "s6_protocol.json"
DESIGN_PATH = ROOT / "bench" / "next_study_design.json"
DEFAULT_RUNS_ROOT = ROOT / "results-next-study"

PREFLIGHT_SCHEMA = "brick.next-study.native-preflight/1"
SHAKEOUT_AUTHORIZATION_SCHEMA = "brick.next-study.shakeout-authorization/1"
SHAKEOUT_DECISION_SCHEMA = "brick.next-study.shakeout-decision/1"
RUN_METADATA_SCHEMA = "brick.next-study.live-run-metadata/1"
CLEAN_CHECKOUT_SCHEMA = "brick.next-study.clean-checkout-reproduction/2"
CLEAN_CHECKOUT_TEST_COMMAND = [
    "-m", "pytest", "-q", "-p", "no:cacheprovider",
    "--basetemp", "<temporary>",
]
LINUX_CI_SCHEMA = "brick.next-study.linux-ci-reproduction/1"
DESCRIPTIVE_MODEL_PREFLIGHT_SCHEMA = (
    "brick.next-study.descriptive-model-preflight/1"
)
GITHUB_API_VERSION = "2026-03-10"
GITHUB_REPOSITORY = "EdgeHarness/Brick-Agent-Harness"
LINUX_CI_JOB_NAMES = tuple("Python " + version for version in (
    "3.9", "3.10", "3.11", "3.12", "3.13",
))
MODEL_TAGS = {
    "2b": "qwen3.5:2b-q4_K_M",
    "4b": "qwen3.5:4b-q4_K_M",
    "9b": "qwen3.5:9b-q4_K_M",
}
_DIGEST = re.compile(r"(?:sha256:)?([0-9a-f]{64})\Z")
_LIVE_IMPLEMENTATION_PATHS = (
    "harness/experiment.py", "harness/evidence.py", "harness/typed_executor.py",
    "harness/parsing.py", "harness/grading.py", "domains/office_demo/world.py",
    "domains/office_demo/contracts.py", "domains/office_demo/reviewed_grader_v2.py",
    "bench/next_study_live.py", "bench/next_study_runtime.py",
    "bench/next_study_program.py", "bench/next_study_schedule.py",
    "bench/next_study_fable_reconciliation.py",
    "bench/next_study_successor.py", "bench/next_study_220_failure.py",
    "bench/next_study_protocol.json",
)
_AUTHORIZATION_ARTIFACT_PATHS = {
    "design": "bench/next_study_design.json",
    "protocol": "bench/next_study_protocol.json",
    "manifest_lock": "bench/manifests/office-v2/manifest-lock.json",
    "claim_contract": "bench/next_study_claim_contract.json",
    "construct_contract": "bench/next_study_construct_contract.json",
    "semantic_simulation": "evidence/next-study/office-v2-semantic-simulation.json",
    "validated_outcomes": "evidence/next-study/office-v2-validated-outcomes.json",
    "grader_implementation": "domains/office_demo/reviewed_grader_v2.py",
    "grader_mutation_audit": "evidence/next-study/office-v2-grader-machine-conformance.json",
    "grader_machine_conformance": "evidence/next-study/office-v2-grader-machine-conformance.json",
    "runtime_implementation": "bench/next_study_runtime.py",
    "schedule_implementation": "bench/next_study_schedule.py",
    "descriptive_selection": "bench/next_study_descriptive_selection.json",
    "fable_reconciliation": FABLE_RECONCILIATION_PATH,
    "successor_authorization": SUCCESSOR_AUTHORIZATION_PATH,
    "successor_closure": SUCCESSOR_CLOSURE_PATH,
}


class NextStudyLiveError(ValueError):
    pass


def _digest(value, allow_float=False):
    return sha256_bytes(canonical_json_bytes(value, allow_float=allow_float))


def _file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_mask_key(path):
    try:
        value = Path(path).read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        raise NextStudyLiveError("primary mask-key file is unreadable")
    if re.fullmatch(r"[0-9a-f]{64}", value or "") is None:
        raise NextStudyLiveError(
            "primary mask-key file must contain 32-byte lowercase hex"
        )
    return value


def _git(*args):
    completed = subprocess.run(
        ["git", *args], cwd=str(ROOT), check=True, capture_output=True,
        text=True, timeout=30,
    )
    return completed.stdout.strip()


def _annotated_tag_binding(tag, commit_sha):
    """Resolve an annotated tag object and require that it peels to commit."""

    try:
        object_type = _git("cat-file", "-t", "refs/tags/" + tag)
        tag_object_sha = _git("rev-parse", "refs/tags/" + tag)
        peeled_commit = _git("rev-parse", "refs/tags/%s^{}" % tag)
    except subprocess.CalledProcessError as error:
        raise NextStudyLiveError("required annotated tag is missing") from error
    if object_type != "tag":
        raise NextStudyLiveError("instrument tag must be annotated, not lightweight")
    if (
        re.fullmatch(r"[0-9a-f]{40}", tag_object_sha) is None
        or peeled_commit != commit_sha
    ):
        raise NextStudyLiveError("instrument tag does not peel to the authorized commit")
    return tag_object_sha


def _timestamp(value, label):
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise NextStudyLiveError("%s must be timezone-qualified ISO-8601" % label)
    if parsed.utcoffset() is None:
        raise NextStudyLiveError("%s must include a timezone" % label)
    return parsed


def _sha256(value, label):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise NextStudyLiveError("%s must be lowercase SHA-256" % label)
    return value


def _publish_marker_last(path, document):
    path = Path(path)
    marker = path.with_name(path.name + ".complete")
    if path.exists() or marker.exists():
        raise NextStudyLiveError("refusing to replace published live evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(document, newline=True, allow_float=False)
    with path.open("xb") as target:
        target.write(payload); target.flush(); os.fsync(target.fileno())
    with marker.open("xb") as target:
        target.flush(); os.fsync(target.fileno())


def _load_published(path):
    path = Path(path)
    marker = path.with_name(path.name + ".complete")
    if not path.is_file() or not marker.is_file() or marker.stat().st_size != 0:
        raise NextStudyLiveError("published evidence or completion marker is missing")
    return load_canonical_json(path)


def build_execution_protocol(model_role="4b", equal_action=False):
    if model_role not in MODEL_TAGS:
        raise NextStudyLiveError("unknown model role")
    protocol = json.loads(BASE_EXECUTION_PROTOCOL.read_text(encoding="utf-8"))
    protocol["primary_model"] = MODEL_TAGS[model_role]
    protocol["opportunity_budget"] = {
        "model_calls": 18,
        "generated_tokens": 6144,
        "generated_tokens_per_request": 700,
        "shared_across_subepisodes": True,
    }
    if equal_action:
        protocol["opportunity_budget"]["role_budgets"] = {
            "driver": {
                "model_calls": 15, "generated_tokens": 4800,
                "generated_tokens_per_request": 320,
            },
            "plan": {
                "model_calls": 1, "generated_tokens": 672,
                "generated_tokens_per_request": 672,
            },
            "completion": {
                "model_calls": 2, "generated_tokens": 672,
                "generated_tokens_per_request": 336,
            },
        }
    validate_execution_protocol(protocol)
    return protocol


def _implementation_sha256():
    document = {
        relative: _file_digest(ROOT / relative)
        for relative in _LIVE_IMPLEMENTATION_PATHS
    }
    return _digest(document)


def _model_inventory(endpoint="http://127.0.0.1:11434"):
    session = requests.Session(); session.trust_env = False
    version_response = session.get(endpoint + "/api/version", timeout=(5, 30))
    tags_response = session.get(endpoint + "/api/tags", timeout=(5, 30))
    version_response.raise_for_status(); tags_response.raise_for_status()
    version = version_response.json().get("version")
    records = tags_response.json().get("models")
    if not isinstance(version, str) or not isinstance(records, list):
        raise NextStudyLiveError("Ollama inventory response is malformed")
    result = {}
    for role, tag in MODEL_TAGS.items():
        matches = [item for item in records if item.get("name", item.get("model")) == tag]
        if len(matches) != 1:
            raise NextStudyLiveError("exact model tag is missing or duplicated: " + tag)
        match = _DIGEST.fullmatch(str(matches[0].get("digest", "")))
        if match is None:
            raise NextStudyLiveError("model digest is not immutable SHA-256: " + tag)
        result[role] = match.group(1)
    return version, result


def collect_native_preflight(*, require_clean=True, inventory=None):
    if os.name != "nt" or platform.machine().casefold() not in {"arm64", "aarch64"}:
        raise NextStudyLiveError("live successor execution requires native Windows ARM64")
    if not ((3, 9) <= sys.version_info[:2] < (3, 14)):
        raise NextStudyLiveError("Python must satisfy >=3.9,<3.14")
    clean = _git("status", "--porcelain=v1") == ""
    if require_clean and not clean:
        raise NextStudyLiveError("native gate requires a clean worktree")
    protocol = build_execution_protocol()
    registry = build_registry(alias_recovery=False)
    if registry.native_schemas() != build_registry(alias_recovery=True).native_schemas():
        raise NextStudyLiveError("primary conditions expose unequal schemas")
    version, model_digests = _model_inventory() if inventory is None else inventory
    if version != protocol["f0_binding"]["ollama_version"]:
        raise NextStudyLiveError("Ollama version differs from the qualified runtime")
    manifests = load_manifests(ROOT)
    validated = load_canonical_json(VALIDATED_OUTCOMES_PATH)
    validate_validated_outcomes(validated, manifests)
    names = registry.names()
    for manifest in manifests:
        for instance in manifest["instances"]:
            content = instance["content"]
            if content["tool_names"] != names:
                raise NextStudyLiveError("manifest tool catalog drifted")
            expected = build_analysis_protocol()["opportunity_budget"]
            executable_budget = {
                key: expected[key] for key in (
                    "model_calls", "generated_tokens", "generated_tokens_per_request",
                    "shared_across_subepisodes",
                )
            }
            if content["opportunity_budget"] != executable_budget:
                raise NextStudyLiveError("manifest opportunity budget drifted")
    tool_schema_sha256 = _digest(registry.native_schemas())
    host = build_fingerprint(HOST_FINGERPRINT_SCHEMA, {
        "hostname": socket.gethostname(), "os": platform.platform(),
        "architecture": platform.machine(), "python": platform.python_version(),
        "python_executable_sha256": _file_digest(sys.executable),
    })
    packages = {
        package: metadata.version(package)
        for package in ("requests", "openpyxl", "python-pptx")
    }
    runtime = build_fingerprint(RUNTIME_FINGERPRINT_SCHEMA, {
        "ollama_version": version, "model_tags": MODEL_TAGS,
        "model_digests": model_digests, "packages": packages,
        "implementation_sha256": _implementation_sha256(),
        "tool_schema_sha256": tool_schema_sha256,
        "execution_protocol_sha256": protocol_sha256(protocol),
    })
    document = {
        "schema_version": PREFLIGHT_SCHEMA,
        "status": "passed",
        "passed": True,
        "require_clean": bool(require_clean),
        "git_clean": clean,
        "commit_sha": _git("rev-parse", "HEAD"),
        "host_fingerprint": host,
        "runtime_fingerprint": runtime,
        "model_digests": model_digests,
        "tool_schema_sha256": tool_schema_sha256,
        "research_catalog_closed": True,
        "plugin_entry_points_enumerated": False,
        "validated_outcomes_sha256": _file_digest(VALIDATED_OUTCOMES_PATH),
        "live_model_calls": 0,
    }
    document["preflight_sha256"] = _digest(document)
    return validate_native_preflight(document)


def validate_native_preflight(document):
    expected = {
        "schema_version", "status", "passed", "require_clean", "git_clean",
        "commit_sha", "host_fingerprint", "runtime_fingerprint", "model_digests",
        "tool_schema_sha256", "research_catalog_closed",
        "plugin_entry_points_enumerated", "validated_outcomes_sha256",
        "live_model_calls", "preflight_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise NextStudyLiveError("native preflight has unexpected keys")
    unsigned = dict(document); supplied = unsigned.pop("preflight_sha256")
    if supplied != _digest(unsigned):
        raise NextStudyLiveError("native preflight digest drifted")
    if (
        document["schema_version"] != PREFLIGHT_SCHEMA
        or document["status"] != "passed" or document["passed"] is not True
        or type(document["require_clean"]) is not bool
        or type(document["git_clean"]) is not bool
        or document["require_clean"] and not document["git_clean"]
        or document["research_catalog_closed"] is not True
        or document["plugin_entry_points_enumerated"] is not False
        or document["live_model_calls"] != 0
        or set(document["model_digests"]) != set(MODEL_TAGS)
        or re.fullmatch(r"[0-9a-f]{40}", document["commit_sha"]) is None
    ):
        raise NextStudyLiveError("native preflight does not represent a pass")
    for name, digest in document["model_digests"].items():
        _sha256(digest, "model %s" % name)
    _sha256(document["tool_schema_sha256"], "tool schema")
    _sha256(document["validated_outcomes_sha256"], "validated outcomes")
    # The program module owns exact fingerprint validation.
    build = {
        "host_fingerprint": build_fingerprint(
            HOST_FINGERPRINT_SCHEMA, document["host_fingerprint"]["details"]
        ),
        "runtime_fingerprint": build_fingerprint(
            RUNTIME_FINGERPRINT_SCHEMA, document["runtime_fingerprint"]["details"]
        ),
    }
    if build["host_fingerprint"] != document["host_fingerprint"] or build[
        "runtime_fingerprint"
    ] != document["runtime_fingerprint"]:
        raise NextStudyLiveError("native preflight fingerprint drifted")
    return document


def _assert_current_native_preflight(bound_preflight):
    """Recollect launch state and require byte-for-byte preflight identity."""

    validate_native_preflight(bound_preflight)
    current = collect_native_preflight(require_clean=True)
    if current != bound_preflight:
        raise NextStudyLiveError(
            "current native environment differs from the bound preflight"
        )
    return current


def collect_descriptive_model_preflight(
    authorization, endpoint="http://127.0.0.1:11434", session=None,
):
    """Recheck pinned models; only unavailable 2B/9B blocks may be removed."""

    validate_authorization(authorization)
    client = session or requests.Session()
    if session is None:
        client.trust_env = False
    try:
        version_response = client.get(endpoint + "/api/version", timeout=(5, 30))
        tags_response = client.get(endpoint + "/api/tags", timeout=(5, 30))
        version_response.raise_for_status(); tags_response.raise_for_status()
        version = version_response.json().get("version")
        records = tags_response.json().get("models")
    except (requests.RequestException, ValueError, AttributeError):
        raise NextStudyLiveError("descriptive model inventory is unavailable")
    if not isinstance(version, str) or not isinstance(records, list):
        raise NextStudyLiveError("descriptive model inventory is malformed")
    expected_version = authorization["runtime_fingerprint"]["details"].get(
        "ollama_version"
    )
    if version != expected_version:
        raise NextStudyLiveError("descriptive runtime version drifted")
    availability = {}
    for role, tag in MODEL_TAGS.items():
        expected = authorization["model_digests"][role]
        matches = [
            item for item in records
            if item.get("name", item.get("model")) == tag
            and str(item.get("digest", "")) == expected
        ]
        availability[role] = len(matches) == 1
    document = {
        "schema_version": DESCRIPTIVE_MODEL_PREFLIGHT_SCHEMA,
        "status": "passed" if availability["4b"] else "terminate_authorization",
        "authorization_sha256": authorization["authorization_sha256"],
        "ollama_version": version,
        "model_digests": copy.deepcopy(authorization["model_digests"]),
        "availability": availability,
        "optional_failed_roles": sorted(
            role for role in ("2b", "9b") if not availability[role]
        ),
        "substitute_models": [],
        "live_model_calls": 0,
    }
    document["descriptive_model_preflight_sha256"] = _digest(document)
    return validate_descriptive_model_preflight(document, authorization)


def validate_descriptive_model_preflight(document, authorization):
    validate_authorization(authorization)
    expected = {
        "schema_version", "status", "authorization_sha256", "ollama_version",
        "model_digests", "availability", "optional_failed_roles",
        "substitute_models", "live_model_calls",
        "descriptive_model_preflight_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise NextStudyLiveError("descriptive model preflight has unexpected keys")
    unsigned = dict(document)
    supplied = unsigned.pop("descriptive_model_preflight_sha256")
    if supplied != _digest(unsigned):
        raise NextStudyLiveError("descriptive model preflight digest drifted")
    availability = document["availability"]
    if (
        document["schema_version"] != DESCRIPTIVE_MODEL_PREFLIGHT_SCHEMA
        or document["authorization_sha256"]
        != authorization["authorization_sha256"]
        or document["model_digests"] != authorization["model_digests"]
        or document["ollama_version"]
        != authorization["runtime_fingerprint"]["details"].get("ollama_version")
        or not isinstance(availability, dict)
        or set(availability) != {"2b", "4b", "9b"}
        or any(type(value) is not bool for value in availability.values())
        or document["optional_failed_roles"] != sorted(
            role for role in ("2b", "9b") if not availability[role]
        )
        or document["substitute_models"] != []
        or document["live_model_calls"] != 0
        or document["status"]
        != ("passed" if availability["4b"] else "terminate_authorization")
    ):
        raise NextStudyLiveError("descriptive model preflight semantics drifted")
    return document


def _prepare_clean_checkout(commit_sha, directory, source=ROOT):
    """Clone only committed material and detach at the preflight-bound commit."""

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    checkout = directory / "checkout"
    clone = subprocess.run(
        [
            "git", "clone", "--quiet", "--no-hardlinks", "--no-checkout",
            str(source), str(checkout),
        ],
        capture_output=True, text=True,
    )
    if clone.returncode != 0:
        raise NextStudyLiveError("clean-checkout clone failed")
    detached = subprocess.run(
        ["git", "-C", str(checkout), "checkout", "--quiet", "--detach", commit_sha],
        capture_output=True, text=True,
    )
    if detached.returncode != 0:
        raise NextStudyLiveError("clean-checkout detached checkout failed")
    head = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "-C", str(checkout), "status", "--porcelain=v1"],
        capture_output=True, text=True, check=True,
    ).stdout
    if head != commit_sha or status != "":
        raise NextStudyLiveError("detached clean checkout identity drifted")
    return checkout


def collect_clean_checkout_reproduction(preflight):
    """Run the complete suite from a detached clone of the bound commit."""

    validate_native_preflight(preflight)
    if preflight["require_clean"] is not True or preflight["git_clean"] is not True:
        raise NextStudyLiveError("clean-checkout reproduction requires a clean preflight")
    if _git("status", "--porcelain=v1") != "":
        raise NextStudyLiveError("worktree changed after native preflight")
    temporary = Path(tempfile.mkdtemp(prefix=".qualification-tmp-", dir=ROOT))
    started = datetime.datetime.now(datetime.timezone.utc)
    try:
        checkout = _prepare_clean_checkout(preflight["commit_sha"], temporary)
        command = [
            sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
            "--basetemp", str(temporary / "pytest"),
        ]
        completed = subprocess.run(
            command, cwd=checkout, capture_output=True, text=True, timeout=1800,
        )
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    finished = datetime.datetime.now(datetime.timezone.utc)
    if _git("status", "--porcelain=v1") != "":
        raise NextStudyLiveError("qualification run changed the clean worktree")
    combined = (completed.stdout + "\n" + completed.stderr).encode("utf-8")
    document = {
        "schema_version": CLEAN_CHECKOUT_SCHEMA,
        "status": "passed" if completed.returncode == 0 else "failed",
        "passed": completed.returncode == 0,
        "commit_sha": preflight["commit_sha"],
        "preflight_sha256": preflight["preflight_sha256"],
        "platform": "windows-arm64",
        "checkout_method": "local_no_hardlink_clone_detached_commit",
        "checkout_commit_sha": preflight["commit_sha"],
        "test_command": CLEAN_CHECKOUT_TEST_COMMAND,
        "return_code": completed.returncode,
        "output_sha256": hashlib.sha256(combined).hexdigest(),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "live_model_calls": 0,
    }
    document["reproduction_sha256"] = _digest(document)
    return validate_clean_checkout_reproduction(document, preflight)


def validate_clean_checkout_reproduction(document, preflight):
    validate_native_preflight(preflight)
    expected = {
        "schema_version", "status", "passed", "commit_sha", "preflight_sha256",
        "platform", "checkout_method", "checkout_commit_sha", "test_command",
        "return_code", "output_sha256", "started_at",
        "finished_at", "live_model_calls", "reproduction_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise NextStudyLiveError("clean-checkout reproduction has unexpected keys")
    unsigned = dict(document); supplied = unsigned.pop("reproduction_sha256")
    if supplied != _digest(unsigned):
        raise NextStudyLiveError("clean-checkout reproduction digest drifted")
    if (
        document["schema_version"] != CLEAN_CHECKOUT_SCHEMA
        or document["status"] != "passed" or document["passed"] is not True
        or document["return_code"] != 0 or document["live_model_calls"] != 0
        or document["platform"] != "windows-arm64"
        or document["checkout_method"] != "local_no_hardlink_clone_detached_commit"
        or document["checkout_commit_sha"] != preflight["commit_sha"]
        or document["commit_sha"] != preflight["commit_sha"]
        or document["preflight_sha256"] != preflight["preflight_sha256"]
        or document["test_command"] != CLEAN_CHECKOUT_TEST_COMMAND
    ):
        raise NextStudyLiveError("clean-checkout reproduction does not represent a pass")
    _sha256(document["output_sha256"], "qualification output")
    _timestamp(document["started_at"], "qualification start")
    _timestamp(document["finished_at"], "qualification finish")
    return document


def _github_json(session, url):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": "brick-next-study-linux-ci-verifier",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    response = session.get(url, headers=headers, timeout=(10, 60))
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise NextStudyLiveError("GitHub Actions returned a non-object payload")
    return payload


def _normalize_linux_ci_api(run, jobs):
    if not isinstance(run, dict) or not isinstance(jobs, list):
        raise NextStudyLiveError("GitHub Actions evidence is malformed")
    run_id = run.get("id")
    attempt = run.get("run_attempt")
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id <= 0:
        raise NextStudyLiveError("GitHub Actions run id is invalid")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt <= 0:
        raise NextStudyLiveError("GitHub Actions run attempt is invalid")
    normalized_jobs = []
    for expected_name in LINUX_CI_JOB_NAMES:
        matches = [item for item in jobs if item.get("name") == expected_name]
        if len(matches) != 1:
            raise NextStudyLiveError(
                "Linux CI must contain exactly one successful %s job" % expected_name
            )
        job = matches[0]
        steps = [
            step for step in job.get("steps", [])
            if step.get("name") == "Run offline tests"
        ]
        if len(steps) != 1:
            raise NextStudyLiveError(expected_name + " lacks the offline-test step")
        step = steps[0]
        if (
            job.get("status") != "completed" or job.get("conclusion") != "success"
            or job.get("head_sha") != run.get("head_sha")
            or "ubuntu-latest" not in job.get("labels", [])
            or step.get("status") != "completed" or step.get("conclusion") != "success"
        ):
            raise NextStudyLiveError(expected_name + " did not pass on ubuntu-latest")
        normalized_jobs.append({
            "id": job.get("id"), "name": job.get("name"),
            "head_sha": job.get("head_sha"), "status": job.get("status"),
            "conclusion": job.get("conclusion"),
            "labels": sorted(job.get("labels", [])),
            "started_at": job.get("started_at"),
            "completed_at": job.get("completed_at"),
            "offline_test_step": {
                "number": step.get("number"), "name": step.get("name"),
                "status": step.get("status"), "conclusion": step.get("conclusion"),
            },
        })
    workflow = {"name": run.get("name"), "path": run.get("path")}
    normalized_run = {
        "id": run_id, "attempt": attempt, "event": run.get("event"),
        "status": run.get("status"), "conclusion": run.get("conclusion"),
        "head_sha": run.get("head_sha"), "html_url": run.get("html_url"),
        "updated_at": run.get("updated_at"),
    }
    if (
        workflow != {"name": "Offline test suite", "path": ".github/workflows/ci.yml"}
        or normalized_run["status"] != "completed"
        or normalized_run["conclusion"] != "success"
        or normalized_run["event"] not in {"push", "workflow_dispatch"}
        or not isinstance(normalized_run["head_sha"], str)
        or re.fullmatch(r"[0-9a-f]{40}", normalized_run["head_sha"]) is None
        or normalized_run["html_url"] != (
            "https://github.com/%s/actions/runs/%s" % (GITHUB_REPOSITORY, run_id)
        )
    ):
        raise NextStudyLiveError("GitHub Actions run is not the required Linux CI pass")
    _timestamp(normalized_run["updated_at"], "GitHub Actions update")
    for job in normalized_jobs:
        if isinstance(job["id"], bool) or not isinstance(job["id"], int) or job["id"] <= 0:
            raise NextStudyLiveError("GitHub Actions job id is invalid")
        _timestamp(job["started_at"], job["name"] + " start")
        _timestamp(job["completed_at"], job["name"] + " completion")
    return {"workflow": workflow, "run": normalized_run, "linux_jobs": normalized_jobs}


def collect_linux_ci_reproduction(
    preflight, run_id, *, session=None, collected_at=None,
):
    """Collect an exact-commit Linux matrix pass from the GitHub Actions API."""

    validate_native_preflight(preflight)
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id <= 0:
        raise NextStudyLiveError("GitHub Actions run id must be a positive integer")
    session = session or requests.Session()
    base = "https://api.github.com/repos/%s/actions/runs/%s" % (
        GITHUB_REPOSITORY, run_id,
    )
    run = _github_json(session, base)
    attempt = run.get("run_attempt")
    jobs_payload = _github_json(
        session, base + "/attempts/%s/jobs?per_page=100" % attempt,
    )
    jobs = jobs_payload.get("jobs")
    if (
        not isinstance(jobs, list)
        or jobs_payload.get("total_count") != len(jobs)
        or len(jobs) > 100
    ):
        raise NextStudyLiveError("GitHub Actions job list is incomplete")
    evidence = _normalize_linux_ci_api(run, jobs)
    if evidence["run"]["id"] != run_id:
        raise NextStudyLiveError("GitHub Actions returned the wrong run")
    if evidence["run"]["head_sha"] != preflight["commit_sha"]:
        raise NextStudyLiveError("Linux CI commit does not match native preflight")
    collected = collected_at or datetime.datetime.now(datetime.timezone.utc).isoformat()
    _timestamp(collected, "Linux CI collection")
    document = {
        "schema_version": LINUX_CI_SCHEMA,
        "status": "passed", "passed": True, "provider": "github_actions",
        "repository": GITHUB_REPOSITORY, "api_version": GITHUB_API_VERSION,
        **evidence, "api_evidence_sha256": _digest(evidence),
        "collected_at": collected, "live_model_calls": 0,
    }
    document["attestation_sha256"] = _digest(document)
    return validate_linux_ci_reproduction(document, preflight)


def validate_linux_ci_reproduction(document, preflight):
    """Validate fetched, exact-commit Linux CI evidence; absence fails closed."""

    validate_native_preflight(preflight)
    expected = {
        "schema_version", "status", "passed", "provider", "repository",
        "api_version", "workflow", "run", "linux_jobs", "api_evidence_sha256",
        "collected_at", "live_model_calls", "attestation_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise NextStudyLiveError("Linux CI reproduction has unexpected keys")
    unsigned = dict(document); supplied = unsigned.pop("attestation_sha256")
    if supplied != _digest(unsigned):
        raise NextStudyLiveError("Linux CI reproduction digest drifted")
    reconstructed_run = {
        **document["run"], "name": document["workflow"].get("name"),
        "path": document["workflow"].get("path"),
        "run_attempt": document["run"].get("attempt"),
    }
    reconstructed_jobs = [
        {**job, "steps": [job.get("offline_test_step", {})]}
        for job in document["linux_jobs"]
    ] if isinstance(document["linux_jobs"], list) else document["linux_jobs"]
    evidence = _normalize_linux_ci_api(reconstructed_run, reconstructed_jobs)
    if (
        document["schema_version"] != LINUX_CI_SCHEMA
        or document["status"] != "passed" or document["passed"] is not True
        or document["provider"] != "github_actions"
        or document["repository"] != GITHUB_REPOSITORY
        or document["api_version"] != GITHUB_API_VERSION
        or evidence != {
            "workflow": document["workflow"], "run": document["run"],
            "linux_jobs": document["linux_jobs"],
        }
        or document["api_evidence_sha256"] != _digest(evidence)
        or document["run"]["head_sha"] != preflight["commit_sha"]
        or document["live_model_calls"] != 0
    ):
        raise NextStudyLiveError("Linux CI reproduction does not represent a pass")
    _timestamp(document["collected_at"], "Linux CI collection")
    _sha256(document["api_evidence_sha256"], "Linux CI API evidence")
    return document


def verify_linux_ci_reproduction(document, preflight, *, session=None):
    """Refetch the run before authorization so self-authored JSON cannot pass."""

    validated = validate_linux_ci_reproduction(document, preflight)
    refreshed = collect_linux_ci_reproduction(
        preflight, validated["run"]["id"], session=session,
        collected_at=validated["collected_at"],
    )
    if refreshed != validated:
        raise NextStudyLiveError("published Linux CI evidence differs from GitHub")
    return validated


def build_research_authorization(
    preflight, clean_checkout, linux_ci, schedules, shakeout_authorization,
    shakeout_decision, *, native_preflight_artifact_sha256,
    clean_checkout_artifact_sha256, linux_ci_artifact_sha256,
    issued_at, issuer, primary_mask_key_commitment_sha256,
    github_session=None,
):
    """Build the marker-last v0.13.3 authorization after all external gates."""

    validate_native_preflight(preflight)
    validate_clean_checkout_reproduction(clean_checkout, preflight)
    verify_linux_ci_reproduction(linux_ci, preflight, session=github_session)
    load_closure(ROOT / SUCCESSOR_CLOSURE_PATH)
    validate_shakeout_authorization(shakeout_authorization)
    validate_shakeout_decision(shakeout_decision)
    if (
        shakeout_decision["status"] != "passed"
        or shakeout_decision["authorization_sha256"]
        != shakeout_authorization["authorization_sha256"]
        or shakeout_decision["schedule_sha256"]
        != shakeout_authorization["schedule_sha256"]
        or shakeout_authorization["native_preflight_sha256"]
        != preflight["preflight_sha256"]
        or shakeout_authorization["commit_sha"] != preflight["commit_sha"]
    ):
        raise NextStudyLiveError("research authorization requires a passed shakeout")
    if set(schedules) != {"calibration", "sentinel", "primary", "descriptives"}:
        raise NextStudyLiveError("research authorization requires four exact schedules")
    manifests = {item["split"]: item for item in load_manifests(ROOT)}
    validate_phase_schedule(schedules["calibration"], manifests["calibration"])
    validate_phase_schedule(schedules["sentinel"], manifests["sentinel"])
    validate_phase_schedule(schedules["primary"], manifests["retained"])
    validate_descriptive_schedule(schedules["descriptives"], manifests["retained"])
    schedule_digests = {name: _digest(value) for name, value in schedules.items()}
    if any(
        schedules[name]["model_sha256"] != preflight["model_digests"]["4b"]
        for name in ("calibration", "sentinel", "primary")
    ):
        raise NextStudyLiveError("primary schedule model binding drifted")
    artifact_digests = {
        name: _file_digest(ROOT / relative)
        for name, relative in _AUTHORIZATION_ARTIFACT_PATHS.items()
    }
    artifact_digests["native_preflight"] = _sha256(
        native_preflight_artifact_sha256, "native preflight artifact"
    )
    artifact_digests["clean_checkout_reproduction"] = _sha256(
        clean_checkout_artifact_sha256, "clean checkout artifact"
    )
    artifact_digests["linux_ci_reproduction"] = _sha256(
        linux_ci_artifact_sha256, "Linux CI artifact"
    )
    if set(artifact_digests) != REQUIRED_ARTIFACT_DIGESTS:
        raise NextStudyLiveError("authorization artifact inventory drifted")
    tag_object_sha = _annotated_tag_binding("v0.13.3", preflight["commit_sha"])
    return build_authorization(
        tag="v0.13.3", tag_object_sha=tag_object_sha,
        commit_sha=preflight["commit_sha"], artifact_digests=artifact_digests,
        host_fingerprint=preflight["host_fingerprint"],
        runtime_fingerprint=preflight["runtime_fingerprint"],
        schedule_digests=schedule_digests,
        model_digests=preflight["model_digests"],
        descriptive_selection_sha256=schedules["descriptives"]["selection_sha256"],
        primary_mask_key_commitment_sha256=primary_mask_key_commitment_sha256,
        issued_at=issued_at, issuer=issuer,
    )


def build_shakeout_authorization(preflight, schedule, *, issued_at, issuer):
    validate_native_preflight(preflight)
    manifest = load_canonical_json(MANIFEST_DIRECTORY / "development.json")
    validate_development_shakeout_schedule(schedule, manifest)
    if preflight["git_clean"] is not True or preflight["require_clean"] is not True:
        raise NextStudyLiveError("shakeout authorization requires a clean native preflight")
    if schedule["model_sha256"] != preflight["model_digests"]["4b"]:
        raise NextStudyLiveError("shakeout model binding drifted")
    _timestamp(issued_at, "shakeout issue time")
    if not isinstance(issuer, str) or not issuer.strip():
        raise NextStudyLiveError("shakeout issuer is empty")
    document = {
        "schema_version": SHAKEOUT_AUTHORIZATION_SCHEMA,
        "status": "authorized_score_masked_development_only",
        "authorization_gate": "development_shakeout_only",
        "commit_sha": preflight["commit_sha"],
        "design_sha256": _file_digest(DESIGN_PATH),
        "analysis_protocol_sha256": _digest(build_analysis_protocol()),
        "native_preflight_sha256": preflight["preflight_sha256"],
        "host_fingerprint": copy.deepcopy(preflight["host_fingerprint"]),
        "runtime_fingerprint": copy.deepcopy(preflight["runtime_fingerprint"]),
        "model_sha256": preflight["model_digests"]["4b"],
        "schedule_sha256": _digest(schedule),
        "maximum_logical_cells": 22,
        "maximum_physical_attempts": 44,
        "same_seed_retry_limit": 1,
        "score_masked": True,
        "research_phase_allowed": False,
        "issued_at": issued_at,
        "issuer": issuer,
    }
    document["authorization_sha256"] = _digest(document)
    return validate_shakeout_authorization(document)


def validate_shakeout_authorization(document):
    expected = {
        "schema_version", "status", "authorization_gate", "commit_sha",
        "design_sha256", "analysis_protocol_sha256", "native_preflight_sha256",
        "host_fingerprint", "runtime_fingerprint", "model_sha256",
        "schedule_sha256", "maximum_logical_cells", "maximum_physical_attempts",
        "same_seed_retry_limit", "score_masked", "research_phase_allowed",
        "issued_at", "issuer", "authorization_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise NextStudyLiveError("shakeout authorization has unexpected keys")
    unsigned = dict(document); supplied = unsigned.pop("authorization_sha256")
    if supplied != _digest(unsigned):
        raise NextStudyLiveError("shakeout authorization digest drifted")
    if (
        document["schema_version"] != SHAKEOUT_AUTHORIZATION_SCHEMA
        or document["status"] != "authorized_score_masked_development_only"
        or document["authorization_gate"] != "development_shakeout_only"
        or document["maximum_logical_cells"] != 22
        or document["maximum_physical_attempts"] != 44
        or document["same_seed_retry_limit"] != 1
        or document["score_masked"] is not True
        or document["research_phase_allowed"] is not False
    ):
        raise NextStudyLiveError("shakeout authorization scope drifted")
    if re.fullmatch(r"[0-9a-f]{40}", document["commit_sha"]) is None:
        raise NextStudyLiveError("shakeout commit is invalid")
    for field in (
        "design_sha256", "analysis_protocol_sha256", "native_preflight_sha256",
        "model_sha256", "schedule_sha256",
    ):
        _sha256(document[field], field)
    _timestamp(document["issued_at"], "shakeout issue time")
    if not isinstance(document["issuer"], str) or not document["issuer"].strip():
        raise NextStudyLiveError("shakeout issuer is empty")
    return document


def _condition(name, implementation_sha256):
    protocol = build_execution_protocol(equal_action=name.endswith("_equal_action"))
    regular = condition_registry(protocol, implementation_sha256)
    if name in regular:
        return regular[name], protocol
    mapping = {
        "native_equal_action": "native_tools",
        "harness_full_equal_action": "harness_full",
    }
    base_name = mapping.get(name)
    if base_name is None:
        raise NextStudyLiveError("unsupported live condition")
    base = regular[base_name]
    identity = {
        "schema_version": "brick.condition-mechanism/1",
        "name": name, "version": "1.0.0", "runner": base.runner,
        "mechanisms": list(base.mechanisms) + ["nontransferable_equal_action_budget"],
        "implementation_sha256": implementation_sha256,
        "runtime_version": EXPERIMENT_VERSION,
    }
    return ConditionSpec(
        name, "1.0.0", base.runner, tuple(identity["mechanisms"]), _digest(identity)
    ), protocol


def _world_from_initial(workdir, initial):
    if initial["artifacts"]:
        raise NextStudyLiveError("successor live runner does not accept preexisting artifacts")
    world = World(str(workdir), persistent=False)
    world.emails = copy.deepcopy(initial["emails"])
    world.events = copy.deepcopy(initial["events"])
    world.sent_emails = copy.deepcopy(initial["sent_emails"])
    world.messages = copy.deepcopy(initial["messages"])
    world.reminders = copy.deepcopy(initial["reminders"])
    world.actions = []
    return world


def _business_state(world):
    return {
        "emails": copy.deepcopy(world.emails), "events": copy.deepcopy(world.events),
        "sent_emails": copy.deepcopy(world.sent_emails),
        "messages": copy.deepcopy(world.messages),
        "reminders": copy.deepcopy(world.reminders),
    }


def _episodes(content):
    return (
        [{"id": item["id"], "prompt": item["prompt"]} for item in content["ordered_subepisodes"]]
        if content["ordered_subepisodes"] else [{"id": "main", "prompt": content["prompt"]}]
    )


def _grade_document(outcome):
    return {
        "schema_version": GRADE_SCHEMA,
        "grader_status": outcome.grader_status,
        "candidate_decision": outcome.candidate_decision,
        "diagnostics": {
            "checks": [
                {"id": key, "description": description, "passed": passed}
                for key, description, passed in outcome.checks
            ],
            "error": outcome.error,
            "diagnostic_fraction": outcome.diagnostic_fraction,
        },
    }


def _prompt_sha256(condition, content):
    return _digest({
        "schema_version": "brick.next-study.prompt-identity/1",
        "condition": condition.name, "condition_version": condition.version,
        "today": content["today"], "episodes": _episodes(content),
        "role": "You are a careful office assistant.",
    })


def _attempt_key(instance, cell, condition, protocol, model_tag, model_digest, repeat, environment):
    content = instance["content"]
    request_seed = cell["trial_seed"] & 0x7FFFFFFF
    return AttemptKey(
        domain_name=content["domain"], domain_version=content["domain_version"],
        domain_content_sha256=environment["runtime_fingerprint"]["fingerprint_sha256"],
        task_family=content["family"], task_version=content["family_version"],
        generator_version=content["generator_version"], grader_version=GRADER_VERSION,
        model_tag=model_tag, model_digest="sha256:" + model_digest,
        condition_name=condition.name, condition_version=condition.version,
        mechanism_sha256=condition.mechanism_sha256,
        instance_id=content["id"], instance_content_sha256=instance["content_sha256"],
        ordered_subepisodes=[item["id"] for item in content["ordered_subepisodes"]],
        repeat=repeat,
        sampling={
            "seed": cell["trial_seed"], "request_seed": request_seed,
            "trial_index": cell["trial_index"], "request_policy": "reuse_trial_seed_low31",
        },
        opportunity_budget={
            "model_calls": protocol["opportunity_budget"]["model_calls"],
            "generated_tokens": protocol["opportunity_budget"]["generated_tokens"],
            "generated_tokens_per_request": protocol["opportunity_budget"]["generated_tokens_per_request"],
            "shared_across_subepisodes": 1,
            **({"role_budgets": protocol["opportunity_budget"]["role_budgets"]}
               if "role_budgets" in protocol["opportunity_budget"] else {}),
        },
        prompt_sha256=_prompt_sha256(condition, content),
        tool_schema_sha256=environment["tool_schema_sha256"],
    )


def _producer(instance, outcome_record, cell, condition, protocol, transport):
    content = instance["content"]
    packet = review_packet(instance)
    grader = None if cell["phase"] == "sentinel" else build_grader(
        packet, outcome_record
    )

    def produce(writer):
        with tempfile.TemporaryDirectory(prefix="brick-next-live-") as temporary:
            workdir = Path(temporary)
            world = _world_from_initial(workdir, content["initial_state"])
            memory = AttemptMemory(
                content["initial_state"]["memory"],
                visible_initial=content["initial_state"]["memory"],
                bridge_enabled=not condition.has("attempt_scoped_memory_bridge_disabled"),
            )
            registry = build_registry(alias_recovery=condition.has("known_alias_recovery"))
            context = ExecutionContext(world, memory, world.files_dir)
            run_loop = run_raw_json_attempt if condition.runner == "raw_json_loop" else run_attempt
            request_seed = cell["trial_seed"] & 0x7FFFFFFF
            runtime = run_loop(
                protocol=protocol, condition=condition, model=protocol["primary_model"],
                registry=registry, transport=transport, context=context,
                episodes=_episodes(content), today=content["today"], seed=request_seed,
            )
            final_state = _business_state(world)
            artifact_paths = [
                path for path in sorted(Path(world.files_dir).iterdir()) if path.is_file()
            ]
            evidence = GradingEvidence.from_values(
                domain=content["domain"], domain_version=content["domain_version"],
                task_id=task_id_for(packet, outcome_record), state=final_state,
                actions=context.actions, memory=memory.all(),
                artifacts=[(path.name, path.read_bytes()) for path in artifact_paths],
            )
            if grader is None:
                grade_document = {
                    "schema_version": GRADE_SCHEMA,
                    "grader_status": "not_run", "candidate_decision": None,
                    "diagnostics": {"reason": "sentinel_instrument_only"},
                }
            else:
                grade = grader.grade_evidence(evidence)
                if grade.grader_status != "graded":
                    runtime["execution_status"] = "runner_error"
                    runtime["failure_origin"] = "runner"
                    runtime["failure"] = {"type": "grader_error", "message": grade.error}
                elif runtime["failure_origin"] == "model" and grade.candidate_decision:
                    grade = type(grade)(
                        grade.grader_id, grade.grader_version, grade.grader_status,
                        False, grade.checks, grade.error,
                    )
                grade_document = _grade_document(grade)
            writer.write_json("initial-state.json", {
                "schema_version": STATE_SCHEMA, "state_kind": "initial",
                "payload": {
                    "business": {key: copy.deepcopy(content["initial_state"][key]) for key in (
                        "emails", "events", "sent_emails", "messages", "reminders",
                    )},
                    "memory": copy.deepcopy(content["initial_state"]["memory"]),
                    "artifacts": copy.deepcopy(content["initial_state"]["artifacts"]),
                },
            })
            writer.write_json("final-state.json", {
                "schema_version": STATE_SCHEMA, "state_kind": "final",
                "payload": {
                    "business": final_state, "memory": memory.all(),
                    "artifacts": [path.name for path in artifact_paths],
                    "subepisodes": runtime["subepisodes"],
                },
            })
            writer.write_json("actions.json", {
                "schema_version": ACTIONS_SCHEMA, "actions": context.actions,
            })
            writer.write_json("result.json", {
                "schema_version": RESULT_SCHEMA,
                "execution_status": runtime["execution_status"],
                "tool_status": "had_errors" if any(not item["ok"] for item in context.actions) else "clean",
                "failure_origin": runtime["failure_origin"], "failure": runtime["failure"],
                "metrics": runtime["metrics"],
                "diagnostics": {
                    "condition": condition.name, "ledger": runtime["ledger"],
                    "requests": runtime["requests"], "subepisodes": runtime["subepisodes"],
                },
            })
            writer.write_json("grade.json", grade_document)
            memory_delta = b"".join(
                canonical_json_bytes({"index": index, "fact": fact}, newline=True)
                for index, fact in enumerate(memory.delta(), start=1)
            )
            writer.write_bytes("memory-delta.jsonl", memory_delta)
            writer.write_bytes("transcript.md", transcript_markdown(runtime["transcript"]))
            for path in artifact_paths:
                writer.write_bytes("artifacts/" + path.name, path.read_bytes())

    return produce


def _model_for_cell(cell, model_digests):
    role = cell.get("model_role", "4b")
    if role not in MODEL_TAGS or role not in model_digests:
        raise NextStudyLiveError("scheduled model role is unavailable")
    return role, MODEL_TAGS[role], model_digests[role]


def execute_schedule(
    *, schedule, manifest, authorization, preflight, runs_root, run_id,
    lease_path=None, program_state=None, eligible_descriptive_schedule=None,
):
    validate_native_preflight(preflight)
    _assert_current_native_preflight(preflight)
    is_shakeout = schedule.get("phase") == "development_shakeout"
    if is_shakeout:
        validate_shakeout_authorization(authorization)
        validate_development_shakeout_schedule(schedule, manifest)
        if (
            authorization["commit_sha"] != preflight["commit_sha"]
            or authorization["native_preflight_sha256"] != preflight["preflight_sha256"]
            or authorization["schedule_sha256"] != _digest(schedule)
            or authorization["model_sha256"] != preflight["model_digests"]["4b"]
        ):
            raise NextStudyLiveError("current shakeout environment is unauthorized")
        authorization_sha256 = authorization["authorization_sha256"]
    else:
        validate_authorization(authorization)
        if program_state is None:
            raise NextStudyLiveError("research execution requires sealed program state")
        validate_program_state(program_state)
        if (
            program_state["authorization_sha256"] != authorization["authorization_sha256"]
            or program_state["status"] != "ready"
            or program_state["current_phase"] != schedule.get("phase")
        ):
            raise NextStudyLiveError("program state does not authorize this phase")
        if schedule.get("schema_version") == "brick.next-study.descriptive-schedule/1":
            validate_descriptive_schedule(schedule, manifest)
        else:
            validate_phase_schedule(schedule, manifest)
        current = {
            "host_fingerprint": preflight["host_fingerprint"],
            "runtime_fingerprint": preflight["runtime_fingerprint"],
            "commit_sha": preflight["commit_sha"], "tag": authorization["tag"],
            "tag_object_sha": _annotated_tag_binding(
                authorization["tag"], preflight["commit_sha"]
            ),
            "artifact_digests": authorization["artifact_digests"],
            "model_digests": preflight["model_digests"],
            "descriptive_selection_sha256": authorization["descriptive_selection_sha256"],
        }
        if not execution_allowed(authorization, current, authorization["schedule_digests"]):
            raise NextStudyLiveError("current research environment is unauthorized")
        phase_key = schedule["phase"]
        if phase_key not in authorization["schedule_digests"]:
            raise NextStudyLiveError("schedule phase is not directly executable")
        if _digest(schedule) != authorization["schedule_digests"][phase_key]:
            raise NextStudyLiveError("loaded schedule differs from authorization binding")
        authorization_sha256 = authorization["authorization_sha256"]
    execution_schedule = schedule
    if schedule.get("phase") == "descriptives":
        if eligible_descriptive_schedule is None:
            raise NextStudyLiveError(
                "descriptive execution requires sealed model eligibility"
            )
        try:
            execution_schedule = validate_eligible_schedule(
                eligible_descriptive_schedule, schedule,
            )
        except ValueError as exc:
            raise NextStudyLiveError(str(exc))
    elif eligible_descriptive_schedule is not None:
        raise NextStudyLiveError("eligible descriptive schedule used outside descriptives")
    by_id = {item["content"]["id"]: item for item in manifest["instances"]}
    validated_document = load_canonical_json(VALIDATED_OUTCOMES_PATH)
    all_manifests = load_manifests(ROOT)
    validate_validated_outcomes(validated_document, all_manifests)
    outcomes = {item["instance_id"]: item for item in validated_document["records"]}
    metadata_document = {
        "schema_version": RUN_METADATA_SCHEMA,
        "run_id": run_id, "phase": schedule["phase"],
        "authorization_sha256": authorization_sha256,
        "schedule_sha256": _digest(schedule),
        "execution_schedule_sha256": _digest(execution_schedule),
        "preflight_sha256": preflight["preflight_sha256"],
        "score_masked_console": True,
        "model_digests": copy.deepcopy(preflight["model_digests"]),
    }
    store = EvidenceStore.create_run(runs_root, run_id, metadata_document)
    lease = BenchmarkLease(lease_path)
    lease.acquire(authorization_sha256)
    emitted = []
    try:
        for cell in execution_schedule["records"]:
            instance = by_id.get(cell["instance_id"])
            if instance is None or instance["content_sha256"] != cell["content_sha256"]:
                raise NextStudyLiveError("scheduled instance binding drifted")
            validate_office_instance_v2(instance)
            model_role, model_tag, model_digest = _model_for_cell(
                cell, preflight["model_digests"]
            )
            condition, protocol = _condition(cell["condition"], _implementation_sha256())
            protocol["primary_model"] = model_tag
            validate_execution_protocol(protocol)
            transport = OllamaTransport(
                protocol["transport"]["endpoint"],
                protocol["transport"]["request_timeout_seconds"],
            )
            final = None
            for repeat in range(2):
                key = _attempt_key(
                    instance, cell, condition, protocol, model_tag, model_digest,
                    repeat, preflight,
                )
                resolution = store.execute_or_resume(
                    key, _producer(instance, outcomes[cell["instance_id"]], cell, condition, protocol, transport)
                )
                if resolution.state != "committed":
                    raise NextStudyLiveError("attempt publication did not commit")
                final = resolution.record
                if final["failure_origin"] != "environment":
                    break
                failure = final["result"].get("failure")
                retryable = isinstance(failure, dict) and failure.get("retryable") is True
                if not retryable or repeat == 1:
                    break
                time.sleep(1)
                transport.verify_health(protocol, {
                    "ollama": {"version": protocol["f0_binding"]["ollama_version"],
                               "model_digest": "sha256:" + model_digest},
                })
                attestation = seal_recovery_attestation(
                    cell["logical_cell_id"],
                    sha256_bytes(canonical_json_bytes(final, allow_float=True)),
                    authorization_sha256, 1,
                    datetime.datetime.now(datetime.timezone.utc).isoformat(),
                )
                recovery_path = (
                    Path(runs_root) / "recovery-attestations" / run_id
                    / (cell["logical_cell_id"] + ".json")
                )
                _publish_marker_last(recovery_path, attestation)
            instrument_valid = final["failure_origin"] in {"none", "model"}
            event = {
                "event": "cell_complete", "phase": schedule["phase"],
                "logical_cell_id": cell["logical_cell_id"],
                "family": cell["family"], "instrument_valid": instrument_valid,
            }
            emitted.append(event)
            print(json.dumps(event, sort_keys=True), flush=True)
    finally:
        lease.release()
    if len(emitted) != schedule["logical_cell_count"]:
        raise NextStudyLiveError("live executor did not emit the complete schedule")
    store.read_committed()
    summary = {
        "schema_version": "brick.next-study.live-run-summary/1",
        "run_id": run_id, "phase": schedule["phase"],
        "logical_cells": len(emitted),
        "instrument_invalid_cells": sum(not item["instrument_valid"] for item in emitted),
        "scores_exposed": False,
    }
    print(json.dumps(summary, sort_keys=True), flush=True)
    return summary


def build_shakeout_decision(store, schedule, authorization, decided_at):
    validate_shakeout_authorization(authorization)
    manifest = load_canonical_json(MANIFEST_DIRECTORY / "development.json")
    validate_development_shakeout_schedule(schedule, manifest)
    _timestamp(decided_at, "shakeout decision time")
    projection = store.read_committed()
    by_coordinate = {
        (item["instance_id"], item["condition"]): item for item in schedule["records"]
    }
    final = {}
    for record in projection["records"]:
        validated = validate_committed(
            store.attempts_dir / record["logical_hash"] / record["physical_uuid"],
            expected_run={"run_id": store.run_id, "run_sha256": store.run_sha256},
        )["semantic"]
        key = validated["key"].to_dict()
        coordinate = (key["instance"]["id"], key["condition"]["name"])
        cell = by_coordinate.get(coordinate)
        if cell is None or key["sampling"].get("seed") != cell["trial_seed"]:
            raise NextStudyLiveError("shakeout evidence is unscheduled")
        repeat = key["repeat"]
        if coordinate in final and repeat <= final[coordinate][0]:
            raise NextStudyLiveError("shakeout evidence repeat order is invalid")
        final[coordinate] = (repeat, validated["result"]["failure_origin"])
    missing = set(by_coordinate) - set(final)
    invalid = [coordinate for coordinate, (_repeat, origin) in final.items() if origin not in {"none", "model"}]
    passed = not missing and not invalid and len(final) == 22
    document = {
        "schema_version": SHAKEOUT_DECISION_SCHEMA,
        "status": "passed" if passed else "failed",
        "authorization_sha256": authorization["authorization_sha256"],
        "schedule_sha256": _digest(schedule),
        "run_id": store.run_id,
        "logical_cells_expected": 22,
        "logical_cells_complete": len(final),
        "instrument_invalid_cells": len(invalid),
        "missing_cells": len(missing),
        "scores_read": False,
        "condition_scores_read": False,
        "strict_successes_reported": False,
        "next_transition": (
            "eligible_to_freeze_v0.13.3_candidate" if passed
            else "terminate_office_generators_2.3.0_candidate"
        ),
        "decided_at": decided_at,
    }
    document["decision_sha256"] = _digest(document)
    return validate_shakeout_decision(document)


def validate_shakeout_decision(document):
    expected = {
        "schema_version", "status", "authorization_sha256", "schedule_sha256",
        "run_id", "logical_cells_expected", "logical_cells_complete",
        "instrument_invalid_cells", "missing_cells", "scores_read",
        "condition_scores_read", "strict_successes_reported", "next_transition",
        "decided_at", "decision_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise NextStudyLiveError("shakeout decision has unexpected keys")
    unsigned = dict(document); supplied = unsigned.pop("decision_sha256")
    if supplied != _digest(unsigned):
        raise NextStudyLiveError("shakeout decision digest drifted")
    passed = document["status"] == "passed"
    if (
        document["schema_version"] != SHAKEOUT_DECISION_SCHEMA
        or document["status"] not in {"passed", "failed"}
        or document["logical_cells_expected"] != 22
        or type(document["logical_cells_complete"]) is not int
        or type(document["instrument_invalid_cells"]) is not int
        or type(document["missing_cells"]) is not int
        or not 0 <= document["logical_cells_complete"] <= 22
        or min(document["instrument_invalid_cells"], document["missing_cells"]) < 0
        or document["scores_read"] is not False
        or document["condition_scores_read"] is not False
        or document["strict_successes_reported"] is not False
        or passed != (
            document["logical_cells_complete"] == 22
            and document["instrument_invalid_cells"] == 0
            and document["missing_cells"] == 0
        )
        or document["next_transition"] != (
            "eligible_to_freeze_v0.13.3_candidate" if passed
            else "terminate_office_generators_2.3.0_candidate"
        )
    ):
        raise NextStudyLiveError("shakeout decision state is inconsistent")
    _sha256(document["authorization_sha256"], "shakeout authorization")
    _sha256(document["schedule_sha256"], "shakeout schedule")
    _timestamp(document["decided_at"], "shakeout decision time")
    if not isinstance(document["run_id"], str) or not document["run_id"]:
        raise NextStudyLiveError("shakeout run id is invalid")
    return document


def _recovery_attestations(runs_root, run_id):
    directory = Path(runs_root) / "recovery-attestations" / run_id
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise NextStudyLiveError("recovery attestation path is not a directory")
    return [_load_published(path) for path in sorted(directory.glob("*.json"))]


def _sealed_gate(state, phase, artifact, logical_cells, physical_attempts):
    return {
        "schema_version": SEALED_GATE_SCHEMA,
        "authorization_sha256": state["authorization_sha256"],
        "phase": phase, "status": "sealed_pass",
        "logical_cells_completed": logical_cells,
        "physical_attempts_completed": physical_attempts,
        "sealed_artifact_sha256": _digest(artifact),
    }


def seal_execution_phase(
    *, store, schedule, manifest, authorization, program_state,
    recovery_attestations=(), sealed_at, masking_key=None,
):
    """Seal calibration, sentinel, or primary without exposing masked scores."""

    validate_authorization(authorization)
    validate_program_state(program_state)
    phase = schedule.get("phase")
    if phase not in {"calibration", "sentinel", "primary"}:
        raise NextStudyLiveError("only executed primary phases can use this sealer")
    if (
        program_state["authorization_sha256"] != authorization["authorization_sha256"]
        or program_state["current_phase"] != phase
        or _digest(schedule) != authorization["schedule_digests"][phase]
    ):
        raise NextStudyLiveError("phase sealer inputs are not authorization-bound")
    validate_phase_schedule(schedule, manifest)
    _timestamp(sealed_at, "phase seal time")
    attempts = extract_attempt_records(
        store, schedule, recovery_attestations,
        authorization["authorization_sha256"],
    )
    if resume_queue(schedule, attempts):
        raise NextStudyLiveError("phase cannot seal while logical cells remain")
    by_cell = {}
    for attempt in attempts:
        by_cell.setdefault(attempt["logical_cell_id"], []).append(attempt)
    final = {
        logical_id: max(records, key=lambda item: item["repeat"])
        for logical_id, records in by_cell.items()
    }
    if phase == "calibration":
        if any(item["failure_origin"] not in {"none", "model"} for item in final.values()):
            return {"status": "retire_generator", "reason": "instrument_invalid"}, program_state
        records = [{
            "logical_cell_id": logical_id,
            "instrument_valid": item["failure_origin"] in {"none", "model"},
            "strict_success": item["strict_success"],
        } for logical_id, item in sorted(final.items())]
        artifact = calibration_decision(records, schedule)
        if artifact.get("status") != "sealed_pass":
            return artifact, program_state
    elif phase == "sentinel":
        records = [{
            "logical_cell_id": logical_id,
            "instrument_valid": item["failure_origin"] in {"none", "model"},
        } for logical_id, item in sorted(final.items())]
        artifact = sentinel_decision(records, schedule)
        if artifact.get("status") != "sealed_pass":
            return artifact, program_state
    else:
        if masking_key is None:
            raise NextStudyLiveError("primary sealing requires the committed mask key")
        artifact = build_masked_grade_ledger(
            schedule, attempts, manifest, sealed_at, masking_key,
            expected_mask_key_commitment=authorization[
                "primary_mask_key_commitment"
            ],
        )
    gate = _sealed_gate(
        program_state, phase, artifact, schedule["logical_cell_count"], len(attempts),
    )
    return artifact, advance_program(program_state, gate)


def seal_primary_analysis(
    *, masked_ledger, schedule, retained_manifest, authorization,
    program_state, attempts, masking_key, sealed_at,
):
    """Unmask once, compute the frozen analysis, and advance to descriptives."""

    validate_authorization(authorization)
    validate_program_state(program_state)
    if (
        program_state["authorization_sha256"] != authorization["authorization_sha256"]
        or program_state["current_phase"] != "primary_analysis"
        or _digest(schedule) != authorization["schedule_digests"]["primary"]
        or primary_mask_key_commitment(masking_key)
        != authorization["primary_mask_key_commitment"]
    ):
        raise NextStudyLiveError("primary analysis inputs are not authorization-bound")
    grade_ledger = unmask_primary(
        masked_ledger, schedule, retained_manifest, attempts, masking_key,
        sealed_at,
    )
    analysis = analyze_primary(grade_ledger, retained_manifest, schedule)
    gate = _sealed_gate(program_state, "primary_analysis", analysis, 0, 0)
    return grade_ledger, analysis, advance_program(program_state, gate)


def seal_descriptives(
    *, store, schedule, authorization, program_state, primary_analysis,
    grade_ledger, recovery_attestations=(), model_preflight,
):
    """Extract and seal the descriptive matrix without altering the claim."""

    validate_authorization(authorization)
    validate_program_state(program_state)
    if (
        program_state["authorization_sha256"] != authorization["authorization_sha256"]
        or program_state["current_phase"] != "descriptives"
        or _digest(schedule) != authorization["schedule_digests"]["descriptives"]
    ):
        raise NextStudyLiveError("descriptive seal inputs are not authorization-bound")
    primary_gates = [
        gate for gate in program_state["sealed_phase_gates"]
        if gate["phase"] == "primary_analysis"
    ]
    if (
        len(primary_gates) != 1
        or primary_gates[0]["sealed_artifact_sha256"] != _digest(primary_analysis)
    ):
        raise NextStudyLiveError(
            "descriptives require the exact sealed primary-analysis artifact"
        )
    retained = load_canonical_json(MANIFEST_DIRECTORY / "retained.json")
    validate_descriptive_schedule(schedule, retained)
    binding = seal_descriptive_eligibility(primary_analysis, grade_ledger, schedule)
    eligible = eligible_schedule(schedule, model_preflight, binding)
    attempts = extract_attempt_records(
        store, eligible, recovery_attestations,
        authorization["authorization_sha256"],
    )
    if resume_queue(eligible, attempts):
        raise NextStudyLiveError("descriptives cannot seal while cells remain")
    evidence = extract_descriptive_results(eligible, attempts)
    controls = extract_primary_trial_0_controls(grade_ledger, schedule)
    report = build_descriptive_report(eligible, evidence, controls)
    if report["status"] != "complete":
        raise NextStudyLiveError("complete eligible descriptives are required to advance")
    gate = _sealed_gate(
        program_state, "descriptives", report,
        eligible["eligible_cells"], len(attempts),
    )
    return binding, evidence, controls, report, advance_program(program_state, gate)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("native-preflight")
    preflight.add_argument("--allow-dirty", action="store_true")
    preflight.add_argument("--output", type=Path)
    descriptive_preflight = commands.add_parser("descriptive-model-preflight")
    descriptive_preflight.add_argument("--authorization", type=Path, required=True)
    descriptive_preflight.add_argument("--output", type=Path, required=True)
    qualify = commands.add_parser("qualify-clean-checkout")
    qualify.add_argument("--preflight", type=Path, required=True)
    qualify.add_argument("--output", type=Path, required=True)
    schedules = commands.add_parser("build-schedules")
    schedules.add_argument("--preflight", type=Path, required=True)
    schedules.add_argument("--output-dir", type=Path, required=True)
    authorize = commands.add_parser("authorize-shakeout")
    authorize.add_argument("--preflight", type=Path, required=True)
    authorize.add_argument("--schedule", type=Path, required=True)
    authorize.add_argument("--issuer", required=True)
    authorize.add_argument("--issued-at")
    authorize.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run-shakeout")
    run.add_argument("--preflight", type=Path, required=True)
    run.add_argument("--schedule", type=Path, required=True)
    run.add_argument("--authorization", type=Path, required=True)
    run.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    run.add_argument("--run-id", required=True)
    run.add_argument("--lease", type=Path)
    decide = commands.add_parser("seal-shakeout")
    decide.add_argument("--schedule", type=Path, required=True)
    decide.add_argument("--authorization", type=Path, required=True)
    decide.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    decide.add_argument("--run-id", required=True)
    decide.add_argument("--decided-at")
    decide.add_argument("--output", type=Path, required=True)
    linux = commands.add_parser("collect-linux-ci")
    linux.add_argument("--preflight", type=Path, required=True)
    linux.add_argument("--run-id", type=int, required=True)
    linux.add_argument("--collected-at")
    linux.add_argument("--output", type=Path, required=True)
    research = commands.add_parser("authorize-research")
    research.add_argument("--preflight", type=Path, required=True)
    research.add_argument("--clean-checkout", type=Path, required=True)
    research.add_argument("--linux-ci", type=Path, required=True)
    research.add_argument("--schedules-dir", type=Path, required=True)
    research.add_argument("--shakeout-authorization", type=Path, required=True)
    research.add_argument("--shakeout-decision", type=Path, required=True)
    research.add_argument("--issuer", required=True)
    research.add_argument("--mask-key-file", type=Path, required=True)
    research.add_argument("--issued-at")
    research.add_argument("--output", type=Path, required=True)
    research.add_argument("--state-output", type=Path, required=True)
    phase = commands.add_parser("run-phase")
    phase.add_argument("--preflight", type=Path, required=True)
    phase.add_argument("--schedule", type=Path, required=True)
    phase.add_argument("--authorization", type=Path, required=True)
    phase.add_argument("--program-state", type=Path, required=True)
    phase.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    phase.add_argument("--run-id", required=True)
    phase.add_argument("--lease", type=Path)
    phase.add_argument("--descriptive-preflight", type=Path)
    phase.add_argument("--primary-analysis", type=Path)
    phase.add_argument("--grade-ledger", type=Path)
    seal = commands.add_parser("seal-phase")
    seal.add_argument("--schedule", type=Path, required=True)
    seal.add_argument("--authorization", type=Path, required=True)
    seal.add_argument("--program-state", type=Path, required=True)
    seal.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    seal.add_argument("--run-id", required=True)
    seal.add_argument("--sealed-at")
    seal.add_argument("--mask-key-file", type=Path)
    seal.add_argument("--output", type=Path, required=True)
    seal.add_argument("--state-output", type=Path, required=True)
    analyze = commands.add_parser("analyze-primary")
    analyze.add_argument("--masked-ledger", type=Path, required=True)
    analyze.add_argument("--schedule", type=Path, required=True)
    analyze.add_argument("--authorization", type=Path, required=True)
    analyze.add_argument("--program-state", type=Path, required=True)
    analyze.add_argument("--sealed-at")
    analyze.add_argument("--mask-key-file", type=Path, required=True)
    analyze.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    analyze.add_argument("--run-id", required=True)
    analyze.add_argument("--grade-ledger-output", type=Path, required=True)
    analyze.add_argument("--analysis-output", type=Path, required=True)
    analyze.add_argument("--state-output", type=Path, required=True)
    descriptives = commands.add_parser("seal-descriptives")
    descriptives.add_argument("--preflight", type=Path, required=True)
    descriptives.add_argument("--descriptive-preflight", type=Path, required=True)
    descriptives.add_argument("--schedule", type=Path, required=True)
    descriptives.add_argument("--authorization", type=Path, required=True)
    descriptives.add_argument("--program-state", type=Path, required=True)
    descriptives.add_argument("--primary-analysis", type=Path, required=True)
    descriptives.add_argument("--grade-ledger", type=Path, required=True)
    descriptives.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    descriptives.add_argument("--run-id", required=True)
    descriptives.add_argument("--output-dir", type=Path, required=True)
    descriptives.add_argument("--state-output", type=Path, required=True)
    report = commands.add_parser("build-report")
    report.add_argument("--authorization", type=Path, required=True)
    report.add_argument("--program-state", type=Path, required=True)
    report.add_argument("--primary-analysis", type=Path, required=True)
    report.add_argument("--grade-ledger", type=Path, required=True)
    report.add_argument("--descriptive-report", type=Path, required=True)
    report.add_argument("--burden-audit", type=Path, required=True)
    report.add_argument("--limitation", action="append", default=[])
    report.add_argument("--output-dir", type=Path, required=True)
    archive = commands.add_parser("build-release-archive")
    archive.add_argument("--authorization", type=Path, required=True)
    archive.add_argument("--archived-commit", required=True)
    for name in (
        "calibration", "sentinel", "masked-primary-ledger",
        "primary-grade-ledger", "primary-analysis", "descriptives",
        "resource-report", "failure-taxonomy", "program-bindings",
        "study-report", "program-state",
    ):
        archive.add_argument("--" + name, type=Path, required=True)
    archive.add_argument("--output", type=Path, required=True)
    release = commands.add_parser("verify-release")
    release.add_argument("--authorization", type=Path, required=True)
    release.add_argument("--program-state", type=Path, required=True)
    release.add_argument("--archive-manifest", type=Path, required=True)
    release.add_argument("--tag", default="v0.14.0")
    release.add_argument("--output", type=Path, required=True)
    release.add_argument("--state-output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "native-preflight":
        document = collect_native_preflight(require_clean=not args.allow_dirty)
        if args.output:
            _publish_marker_last(args.output, document)
        result = document
    elif args.command == "descriptive-model-preflight":
        authorization = validate_authorization(_load_published(args.authorization))
        document = collect_descriptive_model_preflight(authorization)
        _publish_marker_last(args.output, document)
        result = document
    elif args.command == "qualify-clean-checkout":
        preflight_document = validate_native_preflight(_load_published(args.preflight))
        document = collect_clean_checkout_reproduction(preflight_document)
        _publish_marker_last(args.output, document); result = document
    elif args.command == "build-schedules":
        preflight_document = validate_native_preflight(_load_published(args.preflight))
        manifests = {item["split"]: item for item in load_manifests(ROOT)}
        model_digests = preflight_document["model_digests"]
        documents = {
            "development-shakeout": build_development_shakeout_schedule(
                manifests["development"], model_digests["4b"]
            ),
            "calibration": build_phase_schedule(manifests["calibration"], "calibration", model_digests["4b"]),
            "sentinel": build_phase_schedule(manifests["sentinel"], "sentinel", model_digests["4b"]),
            "primary": build_phase_schedule(manifests["retained"], "primary", model_digests["4b"]),
            "descriptives": build_descriptive_schedule(manifests["retained"], model_digests),
        }
        args.output_dir.mkdir(parents=True, exist_ok=False)
        for name, document in documents.items():
            (args.output_dir / (name + ".json")).write_bytes(
                canonical_json_bytes(document, newline=True)
            )
        result = {"status": "written", "schedules": {name: _digest(value) for name, value in documents.items()}, "live_model_calls": 0}
    elif args.command == "authorize-shakeout":
        preflight_document = validate_native_preflight(_load_published(args.preflight))
        schedule = load_canonical_json(args.schedule)
        issued = args.issued_at or datetime.datetime.now(datetime.timezone.utc).isoformat()
        document = build_shakeout_authorization(
            preflight_document, schedule, issued_at=issued, issuer=args.issuer,
        )
        _publish_marker_last(args.output, document); result = document
    elif args.command == "run-shakeout":
        preflight_document = validate_native_preflight(_load_published(args.preflight))
        schedule = load_canonical_json(args.schedule)
        authorization = validate_shakeout_authorization(_load_published(args.authorization))
        manifest = load_canonical_json(MANIFEST_DIRECTORY / "development.json")
        result = execute_schedule(
            schedule=schedule, manifest=manifest, authorization=authorization,
            preflight=preflight_document, runs_root=args.runs_root,
            run_id=args.run_id, lease_path=args.lease,
        )
    elif args.command == "seal-shakeout":
        schedule = load_canonical_json(args.schedule)
        authorization = validate_shakeout_authorization(_load_published(args.authorization))
        store = EvidenceStore.open_run(args.runs_root, args.run_id)
        decided = args.decided_at or datetime.datetime.now(datetime.timezone.utc).isoformat()
        document = build_shakeout_decision(store, schedule, authorization, decided)
        _publish_marker_last(args.output, document); result = document
    elif args.command == "collect-linux-ci":
        preflight_document = validate_native_preflight(_load_published(args.preflight))
        document = collect_linux_ci_reproduction(
            preflight_document, args.run_id, collected_at=args.collected_at,
        )
        _publish_marker_last(args.output, document); result = document
    elif args.command == "authorize-research":
        preflight_document = validate_native_preflight(_load_published(args.preflight))
        clean = validate_clean_checkout_reproduction(
            _load_published(args.clean_checkout), preflight_document,
        )
        linux_ci = validate_linux_ci_reproduction(
            _load_published(args.linux_ci), preflight_document,
        )
        schedules_documents = {
            name: load_canonical_json(args.schedules_dir / (name + ".json"))
            for name in ("calibration", "sentinel", "primary", "descriptives")
        }
        issued = args.issued_at or datetime.datetime.now(datetime.timezone.utc).isoformat()
        document = build_research_authorization(
            preflight_document, clean, linux_ci, schedules_documents,
            validate_shakeout_authorization(_load_published(args.shakeout_authorization)),
            validate_shakeout_decision(_load_published(args.shakeout_decision)),
            native_preflight_artifact_sha256=_file_digest(args.preflight),
            clean_checkout_artifact_sha256=_file_digest(args.clean_checkout),
            linux_ci_artifact_sha256=_file_digest(args.linux_ci),
            primary_mask_key_commitment_sha256=primary_mask_key_commitment(
                _load_mask_key(args.mask_key_file)
            ),
            issued_at=issued, issuer=args.issuer,
        )
        _publish_marker_last(args.output, document)
        _publish_marker_last(
            args.state_output, initial_program_state(document["authorization_sha256"])
        )
        result = document
    elif args.command == "run-phase":
        preflight_document = validate_native_preflight(_load_published(args.preflight))
        schedule = load_canonical_json(args.schedule)
        authorization = validate_authorization(_load_published(args.authorization))
        state = validate_program_state(_load_published(args.program_state))
        split = {
            "calibration": "calibration", "sentinel": "sentinel",
            "primary": "retained", "descriptives": "retained",
        }.get(schedule.get("phase"))
        if split is None:
            raise NextStudyLiveError("run-phase schedule is not executable")
        manifest = load_canonical_json(MANIFEST_DIRECTORY / (split + ".json"))
        eligible = None
        if schedule.get("phase") == "descriptives":
            if any(
                value is None for value in (
                    args.descriptive_preflight, args.primary_analysis,
                    args.grade_ledger,
                )
            ):
                raise NextStudyLiveError(
                    "descriptive execution requires preflight and sealed primary inputs"
                )
            descriptive_model = validate_descriptive_model_preflight(
                _load_published(args.descriptive_preflight), authorization,
            )
            if descriptive_model["status"] != "passed":
                raise NextStudyLiveError("mandatory 4B descriptive preflight failed")
            primary_analysis = _load_published(args.primary_analysis)
            grade_ledger = _load_published(args.grade_ledger)
            binding = seal_descriptive_eligibility(
                primary_analysis, grade_ledger, schedule,
            )
            eligible = eligible_schedule(
                schedule, descriptive_model["availability"], binding,
            )
        elif any(
            value is not None for value in (
                args.descriptive_preflight, args.primary_analysis,
                args.grade_ledger,
            )
        ):
            raise NextStudyLiveError(
                "descriptive-only inputs were supplied to another phase"
            )
        result = execute_schedule(
            schedule=schedule, manifest=manifest, authorization=authorization,
            preflight=preflight_document, program_state=state,
            runs_root=args.runs_root, run_id=args.run_id, lease_path=args.lease,
            eligible_descriptive_schedule=eligible,
        )
    elif args.command == "seal-phase":
        schedule = load_canonical_json(args.schedule)
        authorization = validate_authorization(_load_published(args.authorization))
        state = validate_program_state(_load_published(args.program_state))
        split = {
            "calibration": "calibration", "sentinel": "sentinel",
            "primary": "retained",
        }.get(schedule.get("phase"))
        if split is None:
            raise NextStudyLiveError("seal-phase schedule is not sealable")
        manifest = load_canonical_json(MANIFEST_DIRECTORY / (split + ".json"))
        store = EvidenceStore.open_run(args.runs_root, args.run_id)
        sealed_at = args.sealed_at or datetime.datetime.now(datetime.timezone.utc).isoformat()
        artifact, updated = seal_execution_phase(
            store=store, schedule=schedule, manifest=manifest,
            authorization=authorization, program_state=state,
            recovery_attestations=_recovery_attestations(args.runs_root, args.run_id),
            sealed_at=sealed_at,
            masking_key=(
                _load_mask_key(args.mask_key_file)
                if args.mask_key_file is not None else None
            ),
        )
        _publish_marker_last(args.output, artifact)
        if updated != state:
            _publish_marker_last(args.state_output, updated)
        result = {"phase": schedule["phase"], "status": artifact["status"], "advanced": updated != state}
    elif args.command == "analyze-primary":
        authorization = validate_authorization(_load_published(args.authorization))
        state = validate_program_state(_load_published(args.program_state))
        schedule = load_canonical_json(args.schedule)
        retained = load_canonical_json(MANIFEST_DIRECTORY / "retained.json")
        store = EvidenceStore.open_run(args.runs_root, args.run_id)
        attempts = extract_attempt_records(
            store, schedule,
            _recovery_attestations(args.runs_root, args.run_id),
            authorization["authorization_sha256"],
        )
        sealed_at = args.sealed_at or datetime.datetime.now(datetime.timezone.utc).isoformat()
        grade, analysis_document, updated = seal_primary_analysis(
            masked_ledger=_load_published(args.masked_ledger), schedule=schedule,
            retained_manifest=retained, authorization=authorization,
            program_state=state, attempts=attempts,
            masking_key=_load_mask_key(args.mask_key_file), sealed_at=sealed_at,
        )
        _publish_marker_last(args.grade_ledger_output, grade)
        _publish_marker_last(args.analysis_output, analysis_document)
        _publish_marker_last(args.state_output, updated)
        result = {
            "status": "sealed", "claim_disposition": analysis_document["claim_disposition"],
            "next_phase": updated["current_phase"],
        }
    elif args.command == "seal-descriptives":
        preflight_document = validate_native_preflight(_load_published(args.preflight))
        authorization = validate_authorization(_load_published(args.authorization))
        state = validate_program_state(_load_published(args.program_state))
        schedule = load_canonical_json(args.schedule)
        descriptive_model = validate_descriptive_model_preflight(
            _load_published(args.descriptive_preflight), authorization,
        )
        if descriptive_model["status"] != "passed":
            raise NextStudyLiveError("mandatory 4B descriptive preflight failed")
        store = EvidenceStore.open_run(args.runs_root, args.run_id)
        documents = seal_descriptives(
            store=store, schedule=schedule, authorization=authorization,
            program_state=state,
            primary_analysis=_load_published(args.primary_analysis),
            grade_ledger=_load_published(args.grade_ledger),
            recovery_attestations=_recovery_attestations(args.runs_root, args.run_id),
            model_preflight=descriptive_model["availability"],
        )
        binding, evidence, controls, report, updated = documents
        args.output_dir.mkdir(parents=True, exist_ok=False)
        for name, document in (
            ("eligibility", binding), ("evidence", evidence),
            ("controls", controls), ("report", report),
        ):
            _publish_marker_last(args.output_dir / (name + ".json"), document)
        _publish_marker_last(args.state_output, updated)
        result = {"status": report["status"], "next_phase": updated["current_phase"]}
    elif args.command == "build-report":
        authorization = validate_authorization(_load_published(args.authorization))
        state = validate_program_state(_load_published(args.program_state))
        manifest_lock = load_canonical_json(args.burden_audit)
        study, resource, taxonomy, bindings = build_study_report(
            _load_published(args.primary_analysis),
            _load_published(args.descriptive_report),
            manifest_lock,
            _load_published(args.grade_ledger),
            authorization, state, args.limitation,
        )
        args.output_dir.mkdir(parents=True, exist_ok=False)
        for name, document in (
            ("resource-report", resource),
            ("failure-taxonomy", taxonomy),
            ("program-bindings", bindings),
            ("study-report", study),
        ):
            _publish_marker_last(args.output_dir / (name + ".json"), document)
        result = {
            "status": "report_built",
            "claim_disposition": study["claim_disposition"],
            "study_report_sha256": study["study_report_sha256"],
        }
    elif args.command == "build-release-archive":
        authorization = validate_authorization(_load_published(args.authorization))
        paths = {
            "authorization": args.authorization,
            "calibration": args.calibration,
            "sentinel": args.sentinel,
            "masked_primary_ledger": args.masked_primary_ledger,
            "primary_grade_ledger": args.primary_grade_ledger,
            "primary_analysis": args.primary_analysis,
            "descriptives": args.descriptives,
            "resource_report": args.resource_report,
            "failure_taxonomy": args.failure_taxonomy,
            "program_bindings": args.program_bindings,
            "study_report": args.study_report,
            "program_state": args.program_state,
        }
        document = build_release_archive_manifest(
            ROOT, authorization, args.archived_commit,
            {name: path.resolve().relative_to(ROOT.resolve()) for name, path in paths.items()},
        )
        _publish_marker_last(args.output, document)
        result = {"status": "archive_built", "archive_sha256": document["archive_sha256"]}
    elif args.command == "verify-release":
        authorization = validate_authorization(_load_published(args.authorization))
        state = validate_program_state(_load_published(args.program_state))
        attestation = verify_release(
            ROOT, authorization, state,
            _load_published(args.archive_manifest), annotated_tag=args.tag,
        )
        updated = advance_program(
            state, _sealed_gate(state, "release", attestation, 0, 0)
        )
        _publish_marker_last(args.output, attestation)
        _publish_marker_last(args.state_output, updated)
        result = {
            "status": attestation["status"],
            "program_status": updated["status"],
            "annotated_tag": attestation["annotated_tag"],
        }
    else:
        raise NextStudyLiveError("unsupported command")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "MODEL_TAGS", "NextStudyLiveError", "build_execution_protocol",
    "build_research_authorization", "build_shakeout_authorization",
    "build_shakeout_decision", "collect_clean_checkout_reproduction",
    "collect_linux_ci_reproduction", "collect_native_preflight", "execute_schedule",
    "seal_descriptives", "seal_execution_phase", "seal_primary_analysis",
    "validate_clean_checkout_reproduction", "validate_native_preflight",
    "validate_linux_ci_reproduction", "validate_shakeout_authorization",
    "validate_shakeout_decision", "verify_linux_ci_reproduction",
]
