"""Prospective fixed-panel Llama 3.1 8B product-system comparison.

This module is intentionally isolated from the completed v0.13.6 Qwen study.
It compares a pinned Sharvin balanced orchestration adapter with a matched
minimal native-tool loop on the same Llama model, Brick task state, typed tool
executor, opportunity budget, strict graders, and marker-last evidence store.

The public CLI is score-blind until all 120 authorized cells have sealed.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import datetime as dt
from fractions import Fraction
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import socket
import subprocess
import sys
import tempfile
import time

import requests

from bench import focused_followup as _focused
from bench import next_study_live as _live
from bench.next_study_program import (
    BenchmarkLease,
    HOST_FINGERPRINT_SCHEMA,
    RUNTIME_FINGERPRINT_SCHEMA,
    build_fingerprint,
)
from bench.next_study_review import review_packet
from bench.next_study_validated_outcomes import (
    DEFAULT_PATH as VALIDATED_OUTCOMES_PATH,
    load_manifests,
    validate_validated_outcomes,
)
from domains.office_demo.contracts import build_registry
from domains.office_demo.generators_v2 import (
    GENERATOR_VERSION,
    SPLIT_ORDINALS,
    validate_office_instance_v2,
)
from domains.office_demo.reviewed_grader_v2 import (
    GRADER_VERSION,
    build_grader,
    task_id_for,
)
from harness.evidence import (
    ACTIONS_SCHEMA,
    GRADE_SCHEMA,
    RESULT_SCHEMA,
    STATE_SCHEMA,
    AttemptKey,
    EvidenceStore,
    canonical_json_bytes,
    validate_committed,
)
from harness.experiment import AttemptMemory, ConditionSpec, ExecutionContext, OllamaTransport, transcript_markdown
from harness.grading import GradingEvidence
from harness.instances import load_canonical_json, replace_canonical_json, sha256_bytes


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "bench" / "llama8_product_validation_protocol.json"
MANIFEST_DIRECTORY = ROOT / "bench" / "manifests" / "office-v2"
RUNS_ROOT = ROOT / "results-next-study" / "llama8-product-validation-v0138"
RUN_ID = "v0138-llama8-product-validation-r1"
AUTHORIZATION_PATH = RUNS_ROOT / "authorization.json"
PREFLIGHT_PATH = RUNS_ROOT / "preflight.json"
SCHEDULE_PATH = RUNS_ROOT / "schedule.json"
SEAL_PATH = RUNS_ROOT / "seal.json"
GATE_SEAL_PATH = RUNS_ROOT / "instrument-gate-seal.json"
ANALYSIS_PATH = RUNS_ROOT / "analysis.json"
REPORT_PATH = RUNS_ROOT / "report.json"
RECOVERY_DIRECTORY = RUNS_ROOT / "recovery-attestations"

PROTOCOL_SCHEMA = "brick.llama8-product-validation.protocol/1"
SCHEDULE_SCHEMA = "brick.llama8-product-validation.schedule/1"
PREFLIGHT_SCHEMA = "brick.llama8-product-validation.preflight/1"
AUTHORIZATION_SCHEMA = "brick.llama8-product-validation.authorization/1"
RUN_METADATA_SCHEMA = "brick.llama8-product-validation.run-metadata/1"
ATTEMPT_RECORD_SCHEMA = "brick.llama8-product-validation.attempt-record/1"
RECOVERY_SCHEMA = "brick.llama8-product-validation.recovery-attestation/1"
SEAL_SCHEMA = "brick.llama8-product-validation.seal/1"
GATE_SEAL_SCHEMA = "brick.llama8-product-validation.instrument-gate-seal/1"
ANALYSIS_SCHEMA = "brick.llama8-product-validation.analysis/1"
REPORT_SCHEMA = "brick.llama8-product-validation.report/1"

MODEL_TAG = "llama3.1:8b"
MODEL_DIGEST = "46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e"
OLLAMA_VERSION = "0.32.5"
FOLLOWUP_TAG = "v0.13.8"
SHARVIN_COMMIT = "7efc9b9dc2c54684f88c372de3a5d620e5497a23"
SHARVIN_TREE = "76800c58e1d24b941cad3374cc6d11edaf004053"
CONDITIONS = ("native_tools", "sharvin_balanced_adapter")
FAMILIES = ("cal_freeslot", "pptx_basic", "remind_msg")
NON_CALIBRATION_SPLITS = ("development", "validation", "sentinel", "retained", "adversarial")
SELECTED_ORDINALS = (1, 6, 8, 9, 10, 14, 15, 16, 19, 22, 23, 24, 27, 28, 32, 33, 37, 39, 45, 46)
SELECTOR_DIGEST = "00007ae49f345f9f3184f6caf094464ba461aab9a7881f8b55e2f4e3844a2432"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")

_SHARVIN_SOURCE_DIGESTS = {
    "standalone/agents/8b/config.json": "cddc3c0db88dd1c4b2da77f0681aee19c113e98c21bc91b43a93d457f2c8d3a2",
    "standalone/harness/agent.py": "c3037a6636e9fe789007b9becc62f1514800dc572f3e7bb4e04d1d322736a393",
    "standalone/harness/profiles.py": "43cfc00d08f6f75b767b6d063d9ebf41891b7652c9e5bd3e362b09ac23e87ae1",
    "standalone/harness/tools.py": "d9bd8c65e43d8c5ca9edaf11f1ee86e8b9a4a7f3d2fbe00969b72925bd2e795b",
}

_SOURCE_PATHS = (
    "bench/llama8_product_validation.py",
    "bench/llama8_product_validation_verifier.py",
    "bench/llama8_product_validation_protocol.json",
    "bench/focused_followup.py",
    "bench/next_study_live.py",
    "bench/next_study_program.py",
    "domains/office_demo/sharvin_adapter.py",
    "scripts/run-llama8-product-validation.ps1",
    "harness/evidence.py",
    "harness/experiment.py",
    "harness/typed_executor.py",
    "harness/grading.py",
    "harness/instances.py",
    "domains/office_demo/world.py",
    "domains/office_demo/contracts.py",
    "domains/office_demo/office_files.py",
    "domains/office_demo/strict_graders.py",
    "domains/office_demo/reviewed_grader_v2.py",
    "domains/office_demo/generators_v2.py",
    "domains/office_demo/outcome_oracle_v2.py",
    "bench/next_study_review.py",
    "bench/next_study_validated_outcomes.py",
    "evidence/next-study/office-v2-validated-outcomes.json",
    "bench/manifests/office-v2/manifest-lock.json",
    "bench/manifests/office-v2/development.json",
    "bench/manifests/office-v2/calibration.json",
    "bench/manifests/office-v2/validation.json",
    "bench/manifests/office-v2/sentinel.json",
    "bench/manifests/office-v2/retained.json",
    "bench/manifests/office-v2/adversarial.json",
)


class Llama8ProductValidationError(ValueError):
    """The product-validation protocol, evidence, or environment is invalid."""


def _digest(value, *, allow_float=False):
    return sha256_bytes(canonical_json_bytes(value, allow_float=allow_float))


def _file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _require_sha256(value, label):
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise Llama8ProductValidationError(f"{label} must be lowercase SHA-256")
    return value


def _require_sha1(value, label):
    if not isinstance(value, str) or _SHA1.fullmatch(value) is None:
        raise Llama8ProductValidationError(f"{label} must be lowercase Git SHA-1")
    return value


def _timestamp(value, label):
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise Llama8ProductValidationError(f"{label} must be ISO-8601") from exc
    if parsed.utcoffset() is None:
        raise Llama8ProductValidationError(f"{label} must include a timezone")
    return parsed


def _utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _git(*args, cwd=ROOT, text=True):
    try:
        result = subprocess.run(
            ["git", *args], cwd=str(cwd), check=True, capture_output=True,
            text=text, timeout=60,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise Llama8ProductValidationError("Git identity lookup failed") from exc
    return result.stdout.strip() if text else result.stdout


def _annotated_tag(tag, expected_commit=None):
    object_type = _git("cat-file", "-t", "refs/tags/" + tag)
    object_sha = _git("rev-parse", "refs/tags/" + tag)
    commit = _git("rev-parse", "refs/tags/%s^{}" % tag)
    if object_type != "tag":
        raise Llama8ProductValidationError("product-validation tag must be annotated")
    _require_sha1(object_sha, "tag object")
    _require_sha1(commit, "tag commit")
    if expected_commit is not None and commit != expected_commit:
        raise Llama8ProductValidationError("tag does not peel to the bound commit")
    return {"tag": tag, "tag_object_sha": object_sha, "commit_sha": commit}


def _publish_marker_last(path, document):
    path = Path(path)
    marker = path.with_name(path.name + ".complete")
    if path.exists() or marker.exists():
        raise Llama8ProductValidationError("refusing to replace marker-last evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(document, newline=True, allow_float=False)
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    with marker.open("xb") as handle:
        handle.flush()
        os.fsync(handle.fileno())
    return path


def _load_published(path, label):
    path = Path(path)
    marker = path.with_name(path.name + ".complete")
    if not path.is_file() or not marker.is_file() or marker.stat().st_size != 0:
        raise Llama8ProductValidationError(f"{label} marker-last artifact is missing")
    try:
        return load_canonical_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise Llama8ProductValidationError(f"{label} is not canonical JSON") from exc


def _publish_or_recover_marker_last(path, document, label):
    """Idempotently publish exact canonical JSON with an empty last marker.

    A crash after the JSON fsync but before marker creation is recoverable only
    when the JSON revalidates byte-for-byte as the freshly rederived document.
    Marker-only, nonempty-marker, or conflicting JSON states fail closed.
    """

    path = Path(path)
    marker = path.with_name(path.name + ".complete")
    if not path.exists() and not marker.exists():
        _publish_marker_last(path, document)
        return document
    if marker.exists() and (not path.is_file() or marker.stat().st_size != 0):
        raise Llama8ProductValidationError(f"{label} has an unsafe marker state")
    if path.is_file():
        try:
            actual = load_canonical_json(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise Llama8ProductValidationError(f"{label} JSON is unreadable") from exc
        if actual != document:
            raise Llama8ProductValidationError(f"{label} JSON differs from exact rederivation")
        if marker.exists():
            return actual
        with marker.open("xb") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        return actual
    raise Llama8ProductValidationError(f"{label} marker exists without JSON")


def load_protocol(path=PROTOCOL_PATH):
    try:
        return validate_protocol(load_canonical_json(path))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise Llama8ProductValidationError("Llama 8B protocol is unreadable") from exc


def validate_protocol(protocol):
    expected = {
        "schema_version", "version", "status", "classification", "source_freeze",
        "model", "opportunity_budget", "conditions", "panel", "sampling",
        "analysis", "execution", "reporting",
    }
    if not isinstance(protocol, dict) or set(protocol) != expected:
        raise Llama8ProductValidationError("protocol keys drifted")
    if (
        protocol["schema_version"] != PROTOCOL_SCHEMA
        or protocol["version"] != "1.0.0"
        or protocol["status"] != "frozen_before_llama8_product_validation_execution"
        or protocol["classification"] != "prospective_exploratory_fixed_panel_cross_model_product_validation"
    ):
        raise Llama8ProductValidationError("protocol identity drifted")
    source = protocol["source_freeze"]
    if (
        source.get("selected_commit") != SHARVIN_COMMIT
        or source.get("selected_tree") != SHARVIN_TREE
        or source.get("selected_files") != _SHARVIN_SOURCE_DIGESTS
        or source.get("all_remote_branches_audited") != {
            "main": SHARVIN_COMMIT,
            "real-accounts-and-app-shell": "0af900a28e0745dfa2848967b41ce06c7189b13f",
        }
        or source.get("no_license") is not True
    ):
        raise Llama8ProductValidationError("Sharvin source freeze drifted")
    model = protocol["model"]
    if (
        model.get("tag") != MODEL_TAG
        or model.get("digest") != MODEL_DIGEST
        or model.get("ollama_version") != OLLAMA_VERSION
        or model.get("quantization") != "Q4_K_M"
        or model.get("parameter_size") != "8.0B"
        or model.get("architecture") != "llama"
        or model.get("capabilities") != ["completion", "tools"]
        or model.get("show_sha256") != "9523af33146d8be2253c60a6b20cd0391171b84df9ae6714d5f9d4ef7a974bd7"
        or model.get("template_sha256") != "948af2743fc78a328dcb3b0f5a31b3d75f415840fdb699e8b1235978392ecf85"
        or model.get("parameters_sha256") != "2801e61a8848e505a6e20beeaea63cca1600200f6720e5f916ba7d6da5c3ba39"
        or model.get("modelfile_sha256") != "947bea9f1207d7ab6c85029349a914b9ec4b37e933c85a8dad239d5ace107aa7"
    ):
        raise Llama8ProductValidationError("model freeze drifted")
    budget = protocol["opportunity_budget"]
    if any(budget.get(k) != v for k, v in {
        "model_calls": 18,
        "generated_tokens": 6144,
        "generated_tokens_per_request": 700,
        "shared_across_planner_driver_verifier_and_subepisodes": True,
    }.items()):
        raise Llama8ProductValidationError("opportunity budget drifted")
    if set(protocol["conditions"]) != set(CONDITIONS):
        raise Llama8ProductValidationError("condition set drifted")
    panel = protocol["panel"]
    if (
        panel.get("families") != list(FAMILIES)
        or panel.get("generator_version") != GENERATOR_VERSION
        or panel.get("selected_ordinals") != list(SELECTED_ORDINALS)
        or panel.get("selection", {}).get("subset_sha256") != SELECTOR_DIGEST
    ):
        raise Llama8ProductValidationError("panel freeze drifted")
    selector = {
        "schema_version": panel["selection"]["schema"],
        "ordinals": panel["selected_ordinals"],
    }
    if _digest(selector) != SELECTOR_DIGEST:
        raise Llama8ProductValidationError("selector digest is not reproducible")
    sampling = protocol["sampling"]
    if (
        sampling.get("temperature") != 0
        or sampling.get("num_ctx") != 8192
        or sampling.get("transport") != {
            "endpoint": "http://127.0.0.1:11434", "keep_alive": "30m",
            "stream": False, "timeout_seconds": 900,
        }
    ):
        raise Llama8ProductValidationError("sampling contract drifted")
    execution = protocol["execution"]
    if (
        execution.get("run_id") != RUN_ID
        or execution.get("runs_root") != "results-next-study/llama8-product-validation-v0138"
        or execution.get("maximum_physical_attempts") != 252
        or execution.get("instrument_retry_limit") != 1
        or execution.get("score_masked_console") is not True
    ):
        raise Llama8ProductValidationError("execution contract drifted")
    analysis = protocol["analysis"]
    if (
        analysis.get("bootstrap_replicates") != 50000
        or analysis.get("claim_rule", {}).get("minimum_absolute_effect") != "0.12"
        or analysis.get("claim_rule", {}).get("direction") != "sharvin_balanced_adapter minus native_tools"
    ):
        raise Llama8ProductValidationError("analysis contract drifted")
    return protocol


def protocol_sha256(protocol=None):
    return _digest(validate_protocol(load_protocol() if protocol is None else protocol))


def _validated_instances(protocol=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    manifests = load_manifests(ROOT)
    validated = load_canonical_json(VALIDATED_OUTCOMES_PATH)
    validate_validated_outcomes(validated, manifests)
    candidates = {family: {} for family in FAMILIES}
    for manifest in manifests:
        split = manifest["split"]
        for instance in manifest["instances"]:
            validate_office_instance_v2(instance)
            content = instance["content"]
            family = content["family"]
            if split not in NON_CALIBRATION_SPLITS or family not in candidates:
                continue
            try:
                index = int(content["id"].rsplit(".", 1)[1])
                ordinal = SPLIT_ORDINALS[split][index]
            except (IndexError, TypeError, ValueError) as exc:
                raise Llama8ProductValidationError("instance ordinal cannot be reconstructed") from exc
            if ordinal in candidates[family]:
                raise Llama8ProductValidationError("duplicate family ordinal")
            structure = content["structure"]
            if (
                structure["workload"] != 3 + ordinal % 4
                or structure["distractor_count"] != (ordinal // 4) % 4
                or structure["decision_policy"] is None
            ):
                raise Llama8ProductValidationError("instance factorial axes drifted")
            if content["initial_state"]["memory"] or content["initial_state"]["artifacts"]:
                raise Llama8ProductValidationError("fixed-panel candidates must start without memory or artifacts")
            candidates[family][ordinal] = copy.deepcopy(instance)
    expected_noncal = set(range(48)) - set(SPLIT_ORDINALS["calibration"])
    if any(set(values) != expected_noncal for values in candidates.values()):
        raise Llama8ProductValidationError("non-calibration panel is incomplete")
    return candidates


def _validate_selected_panel(protocol, candidates):
    selected = {family: [candidates[family][o] for o in SELECTED_ORDINALS] for family in FAMILIES}
    split_target = {"development": 4, "validation": 2, "sentinel": 2, "retained": 10, "adversarial": 2}
    for family, instances in selected.items():
        if Counter(item["content"]["split"] for item in instances) != split_target:
            raise Llama8ProductValidationError("selected split balance drifted")
        if Counter(item["content"]["structure"]["workload"] for item in instances) != {3: 5, 4: 5, 5: 5, 6: 5}:
            raise Llama8ProductValidationError("selected workload balance drifted")
        if Counter(item["content"]["structure"]["distractor_count"] for item in instances) != {0: 5, 1: 5, 2: 5, 3: 5}:
            raise Llama8ProductValidationError("selected distractor balance drifted")
        policy_counts = sorted(Counter(item["content"]["structure"]["decision_policy"] for item in instances).values(), reverse=True)
        if policy_counts != [7, 7, 6]:
            raise Llama8ProductValidationError("selected policy balance drifted")
        if any(item["content"]["opportunity_budget"] != {
            "model_calls": 18, "generated_tokens": 6144,
            "generated_tokens_per_request": 700, "shared_across_subepisodes": True,
        } for item in instances):
            raise Llama8ProductValidationError("selected instance budget drifted")
    return selected


def _condition_order(protocol, family, instances):
    digest = protocol_sha256(protocol)
    ranked = sorted(instances, key=lambda item: _digest({
        "schema_version": "brick.llama8-product-validation.condition-order/1",
        "protocol_sha256": digest,
        "family": family,
        "instance_id": item["content"]["id"],
        "content_sha256": item["content_sha256"],
    }))
    return {item["content"]["id"]: ("AB" if index < 10 else "BA") for index, item in enumerate(ranked)}


def _trial_seed(protocol, instance_id):
    material = "\0".join((
        "brick.llama8.product-validation.seed/1",
        protocol_sha256(protocol), instance_id, MODEL_DIGEST,
    )).encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest(), "big") & ((1 << 63) - 1)


def build_schedule(protocol=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    candidates = _validated_instances(protocol)
    selected = _validate_selected_panel(protocol, candidates)
    gate, primary = [], []
    # Ordinal 3 is a non-calibration validation case excluded from the primary
    # selector in every family.  It exercises both request paths without
    # grading, efficacy inspection, or overlap with the final 60 clusters.
    for family_index, family in enumerate(FAMILIES):
        instance = candidates[family][3]
        content = instance["content"]
        stratum = "AB" if family_index % 2 == 0 else "BA"
        ordered = CONDITIONS if stratum == "AB" else tuple(reversed(CONDITIONS))
        seed = _trial_seed(protocol, content["id"])
        for position, condition in enumerate(ordered):
            identity = {
                "schema_version": "brick.llama8-product-validation.cell/1",
                "phase": "instrument_gate", "instance_id": content["id"],
                "content_sha256": instance["content_sha256"], "condition": condition,
                "trial_seed": seed,
            }
            gate.append({
                "logical_cell_id": _digest(identity), "phase": "instrument_gate",
                "instance_id": content["id"], "content_sha256": instance["content_sha256"],
                "family": family, "source_split": content["split"], "condition": condition,
                "trial_index": 0, "order_stratum": stratum, "order_position": position,
                "trial_seed": seed, "opening_gate": True,
            })
    for family in FAMILIES:
        instances = selected[family]
        order = _condition_order(protocol, family, instances)
        for instance in sorted(instances, key=lambda item: item["content"]["id"]):
            content = instance["content"]
            stratum = order[content["id"]]
            ordered = CONDITIONS if stratum == "AB" else tuple(reversed(CONDITIONS))
            seed = _trial_seed(protocol, content["id"])
            for position, condition in enumerate(ordered):
                identity = {
                    "schema_version": "brick.llama8-product-validation.cell/1",
                    "phase": "primary",
                    "instance_id": content["id"], "content_sha256": instance["content_sha256"],
                    "condition": condition, "trial_seed": seed,
                }
                primary.append({
                    "logical_cell_id": _digest(identity), "phase": "primary",
                    "instance_id": content["id"], "content_sha256": instance["content_sha256"],
                    "family": family, "source_split": content["split"], "condition": condition,
                    "trial_index": 0, "order_stratum": stratum, "order_position": position,
                    "trial_seed": seed, "opening_gate": False,
                })
    records = gate + primary
    document = {
        "schema_version": SCHEDULE_SCHEMA, "protocol_version": protocol["version"],
        "protocol_sha256": protocol_sha256(protocol), "generator_version": GENERATOR_VERSION,
        "model_tag": MODEL_TAG, "model_sha256": MODEL_DIGEST,
        "phase": "llama8_product_validation", "logical_cell_count": 126,
        "paired_cluster_count": 63, "opening_gate_cell_count": 6,
        "maximum_physical_attempts": 252, "same_seed_retry_limit": 1,
        "records": records,
    }
    return validate_schedule(document, protocol)


def validate_schedule(schedule, protocol=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    expected = {
        "schema_version", "protocol_version", "protocol_sha256", "generator_version",
        "model_tag", "model_sha256", "phase", "logical_cell_count", "paired_cluster_count",
        "opening_gate_cell_count", "maximum_physical_attempts", "same_seed_retry_limit", "records",
    }
    if not isinstance(schedule, dict) or set(schedule) != expected:
        raise Llama8ProductValidationError("schedule keys drifted")
    if (
        schedule["schema_version"] != SCHEDULE_SCHEMA
        or schedule["protocol_version"] != protocol["version"]
        or schedule["protocol_sha256"] != protocol_sha256(protocol)
        or schedule["generator_version"] != GENERATOR_VERSION
        or schedule["model_tag"] != MODEL_TAG
        or schedule["model_sha256"] != MODEL_DIGEST
        or schedule["phase"] != "llama8_product_validation"
        or schedule["logical_cell_count"] != 126
        or schedule["paired_cluster_count"] != 63
        or schedule["opening_gate_cell_count"] != 6
        or schedule["maximum_physical_attempts"] != 252
        or schedule["same_seed_retry_limit"] != 1
        or not isinstance(schedule["records"], list)
        or len(schedule["records"]) != 126
    ):
        raise Llama8ProductValidationError("schedule header drifted")
    cells = schedule["records"]
    required = {
        "logical_cell_id", "phase", "instance_id", "content_sha256", "family",
        "source_split", "condition", "trial_index", "order_stratum", "order_position",
        "trial_seed", "opening_gate",
    }
    if any(not isinstance(cell, dict) or set(cell) != required for cell in cells):
        raise Llama8ProductValidationError("schedule cell keys drifted")
    if len({cell["logical_cell_id"] for cell in cells}) != 126:
        raise Llama8ProductValidationError("schedule logical identities are not unique")
    if Counter(cell["family"] for cell in cells) != {family: 42 for family in FAMILIES}:
        raise Llama8ProductValidationError("schedule family cells drifted")
    if Counter(cell["condition"] for cell in cells) != {condition: 63 for condition in CONDITIONS}:
        raise Llama8ProductValidationError("schedule condition cells drifted")
    if Counter(cell["order_stratum"] for cell in cells) != {"AB": 64, "BA": 62}:
        raise Llama8ProductValidationError("schedule order strata drifted")
    if sum(cell["opening_gate"] for cell in cells) != 6 or not all(cell["opening_gate"] for cell in cells[:6]):
        raise Llama8ProductValidationError("opening gate ordering drifted")
    by_instance = defaultdict(list)
    for cell in cells:
        _require_sha256(cell["logical_cell_id"], "logical cell")
        _require_sha256(cell["content_sha256"], "content")
        if cell["family"] not in FAMILIES or cell["condition"] not in CONDITIONS:
            raise Llama8ProductValidationError("schedule cell label drifted")
        by_instance[cell["instance_id"]].append(cell)
    if len(by_instance) != 63:
        raise Llama8ProductValidationError("schedule cluster count drifted")
    for records in by_instance.values():
        if (
            {item["condition"] for item in records} != set(CONDITIONS)
            or len({item["trial_seed"] for item in records}) != 1
            or sorted(item["order_position"] for item in records) != [0, 1]
        ):
            raise Llama8ProductValidationError("schedule pairing drifted")
    return schedule


def _source_digests():
    paths = {}
    for relative in _SOURCE_PATHS:
        path = ROOT / relative
        if not path.is_file():
            raise Llama8ProductValidationError("bound source is missing: " + relative)
        paths[relative] = _file_digest(path)
    return paths


def _external_source_binding(checkout):
    checkout = Path(checkout).resolve()
    if not checkout.is_dir():
        raise Llama8ProductValidationError("Sharvin checkout is missing")
    if _git("status", "--porcelain=v1", cwd=checkout) != "":
        raise Llama8ProductValidationError("Sharvin checkout must be clean")
    commit = _git("rev-parse", "HEAD", cwd=checkout)
    tree = _git("rev-parse", "HEAD^{tree}", cwd=checkout)
    if commit != SHARVIN_COMMIT or tree != SHARVIN_TREE:
        raise Llama8ProductValidationError("Sharvin checkout identity drifted")
    source_digests = {}
    blob_ids = {}
    for relative, expected in sorted(_SHARVIN_SOURCE_DIGESTS.items()):
        payload = _git("show", f"{SHARVIN_COMMIT}:{relative}", cwd=checkout, text=False)
        # subprocess text=False returns the exact blob bytes; .strip is never applied.
        digest = hashlib.sha256(payload).hexdigest()
        if digest != expected:
            raise Llama8ProductValidationError("Sharvin canonical source digest drifted: " + relative)
        source_digests[relative] = digest
        blob_ids[relative] = _git("rev-parse", f"{SHARVIN_COMMIT}:{relative}", cwd=checkout)
    return {
        "resolved_checkout": str(checkout),
        "repository": "https://github.com/SMalshe/Final-Agent-8B",
        "commit_sha": commit,
        "tree_sha": tree,
        "source_sha256": source_digests,
        "git_blob_sha1": blob_ids,
        "adapter_binding": {
            "schema_version": "brick.sharvin-source-binding/1",
            "repository": "SMalshe/Final-Agent-8B",
            "remote": "https://github.com/SMalshe/Final-Agent-8B.git",
            "commit_sha": SHARVIN_COMMIT,
            "model_tag": MODEL_TAG,
            "files": dict(sorted(source_digests.items())),
        },
        "git_clean": True,
        "dynamic_load_only": True,
        "committed_memory_loaded": False,
    }


def _ollama_inventory():
    session = requests.Session()
    session.trust_env = False
    version_response = session.get("http://127.0.0.1:11434/api/version", timeout=(5, 30))
    tags_response = session.get("http://127.0.0.1:11434/api/tags", timeout=(5, 30))
    show_response = session.post(
        "http://127.0.0.1:11434/api/show", json={"model": MODEL_TAG}, timeout=(5, 30)
    )
    version_response.raise_for_status()
    tags_response.raise_for_status()
    show_response.raise_for_status()
    version = version_response.json().get("version")
    models = tags_response.json().get("models")
    if version != OLLAMA_VERSION or not isinstance(models, list):
        raise Llama8ProductValidationError("Ollama inventory identity drifted")
    matches = [item for item in models if item.get("name", item.get("model")) == MODEL_TAG]
    if len(matches) != 1:
        raise Llama8ProductValidationError("pinned Llama model is missing or duplicated")
    model = matches[0]
    show = show_response.json()
    details = model.get("details")
    if (
        model.get("digest") != MODEL_DIGEST
        or not isinstance(details, dict)
        or details.get("family") != "llama"
        or details.get("parameter_size") != "8.0B"
        or details.get("quantization_level") != "Q4_K_M"
        or details.get("context_length") != 131072
        or sorted(model.get("capabilities", [])) != ["completion", "tools"]
    ):
        raise Llama8ProductValidationError("pinned Llama model metadata drifted")
    show_sha256 = _digest(show, allow_float=True)
    if (
        show_sha256 != "9523af33146d8be2253c60a6b20cd0391171b84df9ae6714d5f9d4ef7a974bd7"
        or hashlib.sha256(str(show.get("template")).encode("utf-8")).hexdigest() != "948af2743fc78a328dcb3b0f5a31b3d75f415840fdb699e8b1235978392ecf85"
        or hashlib.sha256(str(show.get("parameters")).encode("utf-8")).hexdigest() != "2801e61a8848e505a6e20beeaea63cca1600200f6720e5f916ba7d6da5c3ba39"
        or hashlib.sha256(str(show.get("modelfile")).encode("utf-8")).hexdigest() != "947bea9f1207d7ab6c85029349a914b9ec4b37e933c85a8dad239d5ace107aa7"
    ):
        raise Llama8ProductValidationError("Ollama show/template/parameter binding drifted")
    return {
        "ollama_version": version,
        "model_tag": MODEL_TAG,
        "model_digest": MODEL_DIGEST,
        "model_details": copy.deepcopy(details),
        "capabilities": list(model["capabilities"]),
        "show_sha256": show_sha256,
        "template_sha256": "948af2743fc78a328dcb3b0f5a31b3d75f415840fdb699e8b1235978392ecf85",
        "parameters_sha256": "2801e61a8848e505a6e20beeaea63cca1600200f6720e5f916ba7d6da5c3ba39",
        "modelfile_sha256": "947bea9f1207d7ab6c85029349a914b9ec4b37e933c85a8dad239d5ace107aa7",
    }


def collect_preflight(sharvin_checkout, *, require_clean=True):
    if os.name != "nt" or platform.machine().casefold() not in {"arm64", "aarch64"}:
        raise Llama8ProductValidationError("live product validation requires native Windows ARM64")
    if not ((3, 9) <= sys.version_info[:2] < (3, 14)):
        raise Llama8ProductValidationError("Python must satisfy >=3.9,<3.14")
    clean = _git("status", "--porcelain=v1") == ""
    if require_clean and not clean:
        raise Llama8ProductValidationError("preflight requires a clean Brick worktree")
    commit = _git("rev-parse", "HEAD")
    tag = _annotated_tag(FOLLOWUP_TAG, commit)
    protocol = load_protocol()
    schedule = build_schedule(protocol)
    manifests = load_manifests(ROOT)
    validate_validated_outcomes(load_canonical_json(VALIDATED_OUTCOMES_PATH), manifests)
    registry = build_registry(alias_recovery=True)
    if registry.native_schemas() != build_registry(alias_recovery=False).native_schemas():
        raise Llama8ProductValidationError("tool schemas differ across alias mode")
    inventory = _ollama_inventory()
    external = _external_source_binding(sharvin_checkout)
    source_digests = _source_digests()
    tool_schema_sha256 = _digest(registry.native_schemas())
    host = build_fingerprint(HOST_FINGERPRINT_SCHEMA, {
        "hostname": socket.gethostname(), "os": platform.platform(),
        "architecture": platform.machine(), "python": platform.python_version(),
        "python_executable_sha256": _file_digest(sys.executable),
    })
    runtime = build_fingerprint(RUNTIME_FINGERPRINT_SCHEMA, {
        "ollama": inventory, "tool_schema_sha256": tool_schema_sha256,
        "protocol_sha256": protocol_sha256(protocol), "schedule_sha256": _digest(schedule),
        "source_digests": source_digests, "external_source": external,
        "packages": {
            package: metadata.version(package)
            for package in ("requests", "openpyxl", "python-pptx")
        },
    })
    document = {
        "schema_version": PREFLIGHT_SCHEMA, "status": "passed", "passed": True,
        "require_clean": bool(require_clean), "git_clean": clean,
        "commit_sha": commit, "tag": tag["tag"], "tag_object_sha": tag["tag_object_sha"],
        "protocol_sha256": protocol_sha256(protocol), "schedule_sha256": _digest(schedule),
        "host_fingerprint": host, "runtime_fingerprint": runtime,
        "model": inventory, "tool_schema_sha256": tool_schema_sha256,
        "validated_outcomes_sha256": _file_digest(VALIDATED_OUTCOMES_PATH),
        "source_digests": source_digests, "external_source": external,
        "live_model_calls": 0,
    }
    document["preflight_sha256"] = _digest(document)
    return validate_preflight(document, protocol)


def validate_preflight(document, protocol=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    expected = {
        "schema_version", "status", "passed", "require_clean", "git_clean", "commit_sha",
        "tag", "tag_object_sha", "protocol_sha256", "schedule_sha256", "host_fingerprint",
        "runtime_fingerprint", "model", "tool_schema_sha256", "validated_outcomes_sha256",
        "source_digests", "external_source", "live_model_calls", "preflight_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise Llama8ProductValidationError("preflight keys drifted")
    unsigned = dict(document)
    supplied = unsigned.pop("preflight_sha256")
    if supplied != _digest(unsigned):
        raise Llama8ProductValidationError("preflight digest drifted")
    if (
        document["schema_version"] != PREFLIGHT_SCHEMA
        or document["status"] != "passed" or document["passed"] is not True
        or document["require_clean"] is not True or document["git_clean"] is not True
        or document["tag"] != FOLLOWUP_TAG or document["protocol_sha256"] != protocol_sha256(protocol)
        or document["schedule_sha256"] != _digest(build_schedule(protocol))
        or document["live_model_calls"] != 0
        or document["source_digests"] != _source_digests()
        or document["model"]["model_digest"] != MODEL_DIGEST
        or document["model"]["model_tag"] != MODEL_TAG
        or document["model"]["ollama_version"] != OLLAMA_VERSION
    ):
        raise Llama8ProductValidationError("preflight semantics drifted")
    _require_sha1(document["commit_sha"], "preflight commit")
    _require_sha1(document["tag_object_sha"], "preflight tag object")
    for key in ("protocol_sha256", "schedule_sha256", "tool_schema_sha256", "validated_outcomes_sha256"):
        _require_sha256(document[key], key)
    external = document["external_source"]
    if (
        external.get("commit_sha") != SHARVIN_COMMIT
        or external.get("tree_sha") != SHARVIN_TREE
        or external.get("source_sha256") != _SHARVIN_SOURCE_DIGESTS
        or external.get("adapter_binding", {}).get("files") != dict(sorted(_SHARVIN_SOURCE_DIGESTS.items()))
        or external.get("git_clean") is not True
        or external.get("dynamic_load_only") is not True
        or external.get("committed_memory_loaded") is not False
    ):
        raise Llama8ProductValidationError("external source preflight drifted")
    return document


def _condition_identity(name, preflight):
    mechanisms = (
        ["native_ollama_tool_channel", "typed_closed_executor", "model_visible_typed_feedback"]
        if name == "native_tools" else
        load_protocol()["conditions"]["sharvin_balanced_adapter"]["mechanisms"]
    )
    document = {
        "schema_version": "brick.llama8-product-validation.condition/1",
        "name": name, "version": "llama8-product-validation/1",
        "mechanisms": mechanisms, "model": MODEL_TAG,
        "tool_schema_sha256": preflight["tool_schema_sha256"],
        "implementation_sha256": preflight["runtime_fingerprint"]["fingerprint_sha256"],
    }
    return {
        "name": name, "version": "llama8-product-validation/1",
        "runner": name, "mechanisms": mechanisms, "mechanism_sha256": _digest(document),
    }


def build_authorization(preflight, *, issued_at=None):
    protocol = load_protocol()
    validate_preflight(preflight, protocol)
    if preflight != collect_preflight(preflight["external_source"]["resolved_checkout"], require_clean=True):
        raise Llama8ProductValidationError("current environment differs from supplied preflight")
    schedule = build_schedule(protocol)
    conditions = {name: _condition_identity(name, preflight) for name in CONDITIONS}
    document = {
        "schema_version": AUTHORIZATION_SCHEMA, "status": "authorized_score_masked_execution",
        "execution_context": "authorized_research", "issued_at": issued_at or _utcnow(),
        "tag": FOLLOWUP_TAG, "tag_object_sha": preflight["tag_object_sha"],
        "commit_sha": preflight["commit_sha"], "protocol_sha256": protocol_sha256(protocol),
        "schedule_sha256": _digest(schedule), "run_id": RUN_ID,
        "runs_root": "results-next-study/llama8-product-validation-v0138",
        "logical_cell_ceiling": 126, "physical_attempt_ceiling": 252,
        "model": copy.deepcopy(preflight["model"]), "conditions": conditions,
        "preflight_sha256": preflight["preflight_sha256"],
        "host_fingerprint": preflight["host_fingerprint"],
        "runtime_fingerprint": preflight["runtime_fingerprint"],
        "tool_schema_sha256": preflight["tool_schema_sha256"],
        "validated_outcomes_sha256": preflight["validated_outcomes_sha256"],
        "source_digests": copy.deepcopy(preflight["source_digests"]),
        "external_source": copy.deepcopy(preflight["external_source"]),
        "score_embargo": True,
    }
    document["authorization_sha256"] = _digest(document)
    return validate_authorization(document, protocol)


def validate_authorization(document, protocol=None, *, validate_repository=False):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    expected = {
        "schema_version", "status", "execution_context", "issued_at", "tag", "tag_object_sha",
        "commit_sha", "protocol_sha256", "schedule_sha256", "run_id", "runs_root",
        "logical_cell_ceiling", "physical_attempt_ceiling", "model", "conditions",
        "preflight_sha256", "host_fingerprint", "runtime_fingerprint", "tool_schema_sha256",
        "validated_outcomes_sha256", "source_digests", "external_source", "score_embargo",
        "authorization_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise Llama8ProductValidationError("authorization keys drifted")
    unsigned = dict(document)
    supplied = unsigned.pop("authorization_sha256")
    if supplied != _digest(unsigned):
        raise Llama8ProductValidationError("authorization digest drifted")
    if (
        document["schema_version"] != AUTHORIZATION_SCHEMA
        or document["status"] != "authorized_score_masked_execution"
        or document["execution_context"] != "authorized_research"
        or document["tag"] != FOLLOWUP_TAG
        or document["protocol_sha256"] != protocol_sha256(protocol)
        or document["schedule_sha256"] != _digest(build_schedule(protocol))
        or document["run_id"] != RUN_ID
        or document["runs_root"] != "results-next-study/llama8-product-validation-v0138"
        or document["logical_cell_ceiling"] != 126
        or document["physical_attempt_ceiling"] != 252
        or document["score_embargo"] is not True
        or set(document["conditions"]) != set(CONDITIONS)
        or document["model"]["model_digest"] != MODEL_DIGEST
        or document["external_source"]["commit_sha"] != SHARVIN_COMMIT
    ):
        raise Llama8ProductValidationError("authorization semantics drifted")
    _timestamp(document["issued_at"], "authorization issue time")
    _require_sha1(document["commit_sha"], "authorization commit")
    _require_sha1(document["tag_object_sha"], "authorization tag object")
    for key in ("authorization_sha256", "protocol_sha256", "schedule_sha256", "preflight_sha256", "tool_schema_sha256", "validated_outcomes_sha256"):
        _require_sha256(document[key], key)
    for name, condition in document["conditions"].items():
        if condition != _condition_identity(name, {
            "tool_schema_sha256": document["tool_schema_sha256"],
            "runtime_fingerprint": document["runtime_fingerprint"],
        }):
            raise Llama8ProductValidationError("condition identity drifted")
    if validate_repository:
        if _git("status", "--porcelain=v1") != "" or _git("rev-parse", "HEAD") != document["commit_sha"]:
            raise Llama8ProductValidationError("current Brick checkout differs from authorization")
        if _annotated_tag(FOLLOWUP_TAG, document["commit_sha"])["tag_object_sha"] != document["tag_object_sha"]:
            raise Llama8ProductValidationError("current tag differs from authorization")
        if _source_digests() != document["source_digests"]:
            raise Llama8ProductValidationError("current source bytes differ from authorization")
        if _external_source_binding(document["external_source"]["resolved_checkout"]) != document["external_source"]:
            raise Llama8ProductValidationError("current Sharvin checkout differs from authorization")
    return document


def _fresh_environment(authorization):
    validate_authorization(authorization, validate_repository=True)
    current = collect_preflight(authorization["external_source"]["resolved_checkout"], require_clean=True)
    for key in (
        "preflight_sha256", "host_fingerprint", "runtime_fingerprint", "model",
        "tool_schema_sha256", "validated_outcomes_sha256", "source_digests", "external_source",
    ):
        if current[key] != authorization[key if key != "model" else "model"]:
            raise Llama8ProductValidationError("fresh environment differs from authorization: " + key)
    return current


def publish_authorization(preflight, output=AUTHORIZATION_PATH):
    if Path(output).exists() or Path(output).with_name(Path(output).name + ".complete").exists():
        return load_authorization(output, validate_repository=True)
    authorization = build_authorization(preflight)
    schedule = build_schedule()
    _publish_or_recover_marker_last(SCHEDULE_PATH, schedule, "schedule")
    _publish_or_recover_marker_last(output, authorization, "authorization")
    return authorization


def load_authorization(path=AUTHORIZATION_PATH, *, validate_repository=False):
    return validate_authorization(
        _load_published(path, "authorization"),
        validate_repository=validate_repository,
    )


def _schedule_by_id(schedule):
    validate_schedule(schedule)
    return {cell["logical_cell_id"]: cell for cell in schedule["records"]}


def _instances_by_id(protocol=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    candidates = _validated_instances(protocol)
    selected = _validate_selected_panel(protocol, candidates)
    result = {item["content"]["id"]: item for values in selected.values() for item in values}
    result.update({candidates[family][3]["content"]["id"]: candidates[family][3] for family in FAMILIES})
    return result


def _condition_spec(authorization, name):
    raw = authorization["conditions"][name]
    return ConditionSpec(
        name=raw["name"], version=raw["version"], runner=raw["runner"],
        mechanisms=tuple(raw["mechanisms"]), mechanism_sha256=raw["mechanism_sha256"],
    )


def _prompt_sha256(authorization, condition, content):
    return _digest({
        "schema_version": "brick.llama8-product-validation.prompt-identity/1",
        "protocol_sha256": authorization["protocol_sha256"],
        "condition": condition.name, "condition_version": condition.version,
        "today": content["today"], "episodes": _live._episodes(content),
        "role": "You are a careful office assistant.",
        "sharvin_commit": SHARVIN_COMMIT if condition.name == "sharvin_balanced_adapter" else None,
    })


def _attempt_key(authorization, instance, cell, repeat):
    content = instance["content"]
    condition = _condition_spec(authorization, cell["condition"])
    return AttemptKey(
        domain_name=content["domain"], domain_version=content["domain_version"],
        domain_content_sha256=authorization["runtime_fingerprint"]["fingerprint_sha256"],
        task_family=content["family"], task_version=content["family_version"],
        generator_version=content["generator_version"], grader_version=GRADER_VERSION,
        model_tag=MODEL_TAG, model_digest="sha256:" + MODEL_DIGEST,
        condition_name=condition.name, condition_version=condition.version,
        mechanism_sha256=condition.mechanism_sha256,
        instance_id=content["id"], instance_content_sha256=instance["content_sha256"],
        ordered_subepisodes=[item["id"] for item in content["ordered_subepisodes"]],
        repeat=repeat,
        sampling={
            "seed": cell["trial_seed"], "request_seed": cell["trial_seed"] & 0x7FFFFFFF,
            "trial_index": 0, "request_policy": "reuse_paired_trial_seed_low31",
            "temperature": 0, "num_ctx": 8192,
        },
        opportunity_budget={
            "model_calls": 18, "generated_tokens": 6144,
            "generated_tokens_per_request": 700, "shared_across_subepisodes": 1,
        },
        prompt_sha256=_prompt_sha256(authorization, condition, content),
        tool_schema_sha256=authorization["tool_schema_sha256"],
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


def _producer(authorization, instance, outcome_record, cell, transport, authorized_source):
    content = instance["content"]
    packet = review_packet(instance)
    grader = None if cell["phase"] == "instrument_gate" else build_grader(packet, outcome_record)
    condition = _condition_spec(authorization, cell["condition"])

    def produce(writer):
        # Imported lazily so schedule/preflight operations never load or mutate
        # the external controller's process-global state.
        from domains.office_demo.sharvin_adapter import (
            run_native_llama_attempt,
            run_sharvin_attempt,
        )

        with tempfile.TemporaryDirectory(prefix="brick-llama8-product-") as temporary:
            workdir = Path(temporary)
            world = _live._world_from_initial(workdir, content["initial_state"])
            memory = AttemptMemory(
                content["initial_state"]["memory"],
                visible_initial=content["initial_state"]["memory"],
                bridge_enabled=True,
            )
            context = ExecutionContext(world, memory, world.files_dir)
            kwargs = {
                "model": MODEL_TAG,
                "transport": transport,
                "context": context,
                "episodes": _live._episodes(content),
                "today": content["today"],
                "seed": cell["trial_seed"] & 0x7FFFFFFF,
            }
            if condition.name == "native_tools":
                runtime = run_native_llama_attempt(**kwargs)
            else:
                runtime = run_sharvin_attempt(source=authorized_source, **kwargs)
            final_state = _live._business_state(world)
            artifact_paths = [path for path in sorted(Path(world.files_dir).iterdir()) if path.is_file()]
            evidence = GradingEvidence.from_values(
                domain=content["domain"], domain_version=content["domain_version"],
                task_id=task_id_for(packet, outcome_record), state=final_state,
                actions=context.actions, memory=memory.all(),
                artifacts=[(path.name, path.read_bytes()) for path in artifact_paths],
            )
            if grader is None:
                grade_document = {
                    "schema_version": GRADE_SCHEMA, "grader_status": "not_run",
                    "candidate_decision": None,
                    "diagnostics": {"reason": "score_free_instrument_compatibility_gate"},
                }
            else:
                grade = grader.grade_evidence(evidence)
                grade_document = _grade_document(grade)
            if grader is not None and grade.grader_status != "graded":
                runtime["execution_status"] = "runner_error"
                runtime["failure_origin"] = "runner"
                runtime["failure"] = {"type": "grader_error", "message": grade.error}
            elif grader is not None and runtime["failure_origin"] == "model" and grade.candidate_decision:
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
            writer.write_json("actions.json", {"schema_version": ACTIONS_SCHEMA, "actions": context.actions})
            writer.write_json("result.json", {
                "schema_version": RESULT_SCHEMA,
                "execution_status": runtime["execution_status"],
                "tool_status": "had_errors" if any(not item["ok"] for item in context.actions) else "clean",
                "failure_origin": runtime["failure_origin"], "failure": runtime["failure"],
                "metrics": runtime["metrics"],
                "diagnostics": {
                    "condition": condition.name, "ledger": runtime["ledger"],
                    "requests": runtime["requests"], "subepisodes": runtime["subepisodes"],
                    "verifier_unverified_count": runtime.get("diagnostics", {}).get("unverified_completions", 0),
                    "repair_count": len(runtime.get("diagnostics", {}).get("repairs", [])),
                    "source_binding": (
                        authorization["external_source"]["adapter_binding"]
                        if condition.name == "sharvin_balanced_adapter" else None
                    ),
                },
            })
            writer.write_json("grade.json", grade_document)
            writer.write_bytes("memory-delta.jsonl", b"".join(
                canonical_json_bytes({"index": index, "fact": fact}, newline=True)
                for index, fact in enumerate(memory.delta(), start=1)
            ))
            writer.write_bytes("transcript.md", transcript_markdown(runtime["transcript"]))
            for path in artifact_paths:
                writer.write_bytes("artifacts/" + path.name, path.read_bytes())

    return produce


def _run_metadata(authorization):
    return {
        "schema_version": RUN_METADATA_SCHEMA, "run_id": RUN_ID,
        "runs_root": authorization["runs_root"],
        "authorization_sha256": authorization["authorization_sha256"],
        "protocol_sha256": authorization["protocol_sha256"],
        "schedule_sha256": authorization["schedule_sha256"],
        "preflight_sha256": authorization["preflight_sha256"],
        "model_digest": MODEL_DIGEST, "score_masked_console": True,
    }


def _open_store(authorization, *, runs_root=RUNS_ROOT):
    if Path(runs_root).resolve() != RUNS_ROOT.resolve():
        raise Llama8ProductValidationError("alternate runs root is forbidden")
    store = EvidenceStore.create_run(runs_root, RUN_ID, _run_metadata(authorization))
    if store.run_document["metadata"] != _run_metadata(authorization):
        raise Llama8ProductValidationError("EvidenceStore metadata drifted")
    return store


def _resource_metrics(result, actions):
    diagnostics = result.get("diagnostics") if isinstance(result, dict) else None
    ledger = diagnostics.get("ledger") if isinstance(diagnostics, dict) else None
    metrics = result.get("metrics") if isinstance(result, dict) else None
    if not isinstance(ledger, dict) or not isinstance(metrics, dict):
        raise Llama8ProductValidationError("result resource telemetry is missing")
    exact = ledger.get("generated_tokens_exact")
    if type(exact) is not bool:
        raise Llama8ProductValidationError("generated-token exactness is invalid")
    return {
        "model_calls": ledger["model_calls"],
        "generated_tokens_exact": exact,
        "generated_tokens": ledger.get("generated_tokens"),
        "generated_tokens_lower_bound": ledger["generated_tokens_lower_bound"],
        "generated_tokens_upper_bound": ledger["generated_tokens_upper_bound"],
        "successful_actions": sum(bool(item.get("ok")) for item in actions),
        "action_count": len(actions),
        "verifier_unverified_count": diagnostics.get("verifier_unverified_count", 0),
        "repair_count": diagnostics.get("repair_count", 0),
    }


def _physical_candidate_count(store):
    count = 0
    if not store.attempts_dir.is_dir():
        raise Llama8ProductValidationError("attempt directory is missing")
    for logical in store.attempts_dir.iterdir():
        if not logical.is_dir() or logical.is_symlink():
            raise Llama8ProductValidationError("attempt root contains an irregular member")
        for candidate in logical.iterdir():
            if not candidate.is_dir() or candidate.is_symlink():
                raise Llama8ProductValidationError("logical attempt directory contains an irregular member")
            count += 1
    if count > 252:
        raise Llama8ProductValidationError("physical-attempt candidate ceiling exceeded")
    return count


def extract_attempts(store, schedule, authorization):
    validate_authorization(authorization)
    cells = _schedule_by_id(schedule)
    instances = _instances_by_id()
    _physical_candidate_count(store)
    projection = store.read_committed()
    if projection.get("schema_version") != "brick.evidence-results/1" or not isinstance(projection.get("records"), list):
        raise Llama8ProductValidationError("evidence projection drifted")
    records = []
    seen = set()
    for committed in projection["records"]:
        key = committed.get("attempt_key")
        if not isinstance(key, dict):
            raise Llama8ProductValidationError("committed attempt key is missing")
        matches = [cell for cell in schedule["records"] if (
            cell["instance_id"] == key.get("instance", {}).get("id")
            and cell["condition"] == key.get("condition", {}).get("name")
            and cell["trial_seed"] == key.get("sampling", {}).get("seed")
        )]
        if len(matches) != 1:
            raise Llama8ProductValidationError("committed attempt is unscheduled")
        cell = matches[0]
        repeat = key.get("repeat")
        if (cell["logical_cell_id"], repeat) in seen:
            raise Llama8ProductValidationError("duplicate physical attempt")
        seen.add((cell["logical_cell_id"], repeat))
        expected_key = _attempt_key(authorization, instances[cell["instance_id"]], cell, repeat)
        if key != expected_key.to_dict():
            raise Llama8ProductValidationError("full committed AttemptKey drifted")
        candidate = store.attempts_dir / committed["logical_hash"] / committed["physical_uuid"]
        validated = validate_committed(
            candidate, expected_key=expected_key,
            expected_run={"run_id": store.run_id, "run_sha256": store.run_sha256},
        )
        semantic = validated["semantic"]
        if semantic["key"].to_dict() != key:
            raise Llama8ProductValidationError("candidate and projection keys differ")
        result = semantic["result"]
        grade = semantic["grade"]
        origin = result.get("failure_origin")
        gate_ungraded = cell["phase"] == "instrument_gate" and grade.get("grader_status") == "not_run"
        if origin in ("runner", "operator") or (grade.get("grader_status") != "graded" and not gate_ungraded):
            normalized_origin = "instrument"
        elif origin in ("none", "model", "environment"):
            normalized_origin = origin
        else:
            raise Llama8ProductValidationError("failure origin is unsupported")
        strict = grade.get("candidate_decision")
        if normalized_origin in ("environment", "instrument") or gate_ungraded:
            strict = None
        failure = result.get("failure")
        record = {
            "schema_version": ATTEMPT_RECORD_SCHEMA,
            "logical_cell_id": cell["logical_cell_id"], "repeat": repeat,
            "trial_seed": cell["trial_seed"], "failure_origin": normalized_origin,
            "strict_success": strict,
            "opportunity_budget_exhausted": bool(
                isinstance(failure, dict) and failure.get("type") == "opportunity_budget_exhausted"
            ),
            "evidence_sha256": _digest(committed, allow_float=True),
            "grade_record_sha256": _digest(grade, allow_float=True),
            "marker_last_verified": True,
            **_resource_metrics(result, semantic["actions"]["actions"]),
        }
        records.append(record)
    if len(records) > 252:
        raise Llama8ProductValidationError("physical-attempt ceiling exceeded")
    return sorted(records, key=lambda item: (item["logical_cell_id"], item["repeat"]))


def _final_attempts(schedule, attempts):
    cells = _schedule_by_id(schedule)
    by_cell = defaultdict(dict)
    for attempt in attempts:
        logical_id = attempt["logical_cell_id"]
        if logical_id not in cells or attempt["repeat"] not in (0, 1):
            raise Llama8ProductValidationError("attempt topology drifted")
        if attempt["repeat"] in by_cell[logical_id]:
            raise Llama8ProductValidationError("attempt repeat is duplicated")
        by_cell[logical_id][attempt["repeat"]] = attempt
    final, pending_retry = {}, []
    for logical_id in cells:
        attempts_for_cell = by_cell.get(logical_id, {})
        first = attempts_for_cell.get(0)
        second = attempts_for_cell.get(1)
        if first is None:
            if second is not None:
                raise Llama8ProductValidationError("repeat one exists without repeat zero")
            continue
        if first["failure_origin"] == "environment":
            if second is None:
                pending_retry.append(logical_id)
                continue
            final[logical_id] = second
        else:
            if second is not None:
                raise Llama8ProductValidationError("ineligible repeat one exists")
            final[logical_id] = first
    missing = [logical_id for logical_id in cells if logical_id not in final and logical_id not in pending_retry]
    invalid = [logical_id for logical_id, item in final.items() if item["failure_origin"] in ("environment", "instrument")]
    return final, missing, pending_retry, invalid


def _recovery_path(authorization, logical_cell_id):
    return RECOVERY_DIRECTORY / authorization["authorization_sha256"] / (logical_cell_id + ".json")


def _build_recovery_attestation(authorization, attempt, *, attested_at=None):
    if attempt["repeat"] != 0 or attempt["failure_origin"] != "environment":
        raise Llama8ProductValidationError("recovery attestation requires repeat-zero environment evidence")
    document = {
        "schema_version": RECOVERY_SCHEMA,
        "logical_cell_id": attempt["logical_cell_id"], "repeat": 0,
        "evidence_sha256": attempt["evidence_sha256"],
        "authorization_sha256": authorization["authorization_sha256"],
        "same_seed_retry": True, "health_revalidated": True,
        "attested_at": attested_at or _utcnow(),
    }
    document["attestation_sha256"] = _digest(document)
    return validate_recovery_attestation(document, authorization, attempt)


def validate_recovery_attestation(document, authorization, attempt=None):
    expected = {
        "schema_version", "logical_cell_id", "repeat", "evidence_sha256",
        "authorization_sha256", "same_seed_retry", "health_revalidated",
        "attested_at", "attestation_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise Llama8ProductValidationError("recovery attestation keys drifted")
    unsigned = dict(document)
    supplied = unsigned.pop("attestation_sha256")
    if supplied != _digest(unsigned):
        raise Llama8ProductValidationError("recovery attestation digest drifted")
    if (
        document["schema_version"] != RECOVERY_SCHEMA
        or document["repeat"] != 0
        or document["authorization_sha256"] != authorization["authorization_sha256"]
        or document["same_seed_retry"] is not True
        or document["health_revalidated"] is not True
    ):
        raise Llama8ProductValidationError("recovery attestation semantics drifted")
    _require_sha256(document["logical_cell_id"], "recovery logical cell")
    _require_sha256(document["evidence_sha256"], "recovery evidence")
    _timestamp(document["attested_at"], "recovery time")
    if attempt is not None and (
        attempt["logical_cell_id"] != document["logical_cell_id"]
        or attempt["repeat"] != 0
        or attempt["failure_origin"] != "environment"
        or attempt["evidence_sha256"] != document["evidence_sha256"]
    ):
        raise Llama8ProductValidationError("recovery evidence binding drifted")
    return document


def _load_or_publish_recovery(authorization, attempt):
    path = _recovery_path(authorization, attempt["logical_cell_id"])
    if path.exists() or path.with_name(path.name + ".complete").exists():
        document = _load_published(path, "recovery attestation")
        return validate_recovery_attestation(document, authorization, attempt)
    _fresh_environment(authorization)
    document = _build_recovery_attestation(authorization, attempt)
    _publish_or_recover_marker_last(path, document, "recovery attestation")
    return document


def _build_seal(authorization, store, schedule, *, status, reason, sealed_at=None):
    attempts = extract_attempts(store, schedule, authorization)
    final, missing, pending_retry, invalid = _final_attempts(schedule, attempts)
    complete_valid = len(final) == 126 and not missing and not pending_retry and not invalid
    if status == "sealed_complete_valid" and not complete_valid:
        raise Llama8ProductValidationError("complete seal requires 126 valid final cells")
    if status == "terminated_incomplete_instrument" and complete_valid:
        raise Llama8ProductValidationError("incomplete seal cannot cover complete valid evidence")
    if status not in {"sealed_complete_valid", "terminated_incomplete_instrument"}:
        raise Llama8ProductValidationError("unsupported terminal seal status")
    gate_seal_sha256 = None
    if GATE_SEAL_PATH.exists() or GATE_SEAL_PATH.with_name(GATE_SEAL_PATH.name + ".complete").exists():
        gate_seal_sha256 = load_gate_seal(authorization, store=store, schedule=schedule)["gate_seal_sha256"]
    if status == "sealed_complete_valid" and gate_seal_sha256 is None:
        raise Llama8ProductValidationError("complete seal requires the score-free gate seal")
    score_free_ledger = [
        {
            "logical_cell_id": item["logical_cell_id"], "repeat": item["repeat"],
            "evidence_sha256": item["evidence_sha256"], "marker_last_verified": True,
        }
        for item in sorted(final.values(), key=lambda value: value["logical_cell_id"])
    ]
    document = {
        "schema_version": SEAL_SCHEMA, "status": status, "reason": reason,
        "authorization_sha256": authorization["authorization_sha256"],
        "schedule_sha256": authorization["schedule_sha256"],
        "run_id": store.run_id, "run_sha256": store.run_sha256,
        "expected_logical_cells": 126, "complete_final_cells": len(final),
        "missing_cells": len(missing), "pending_retry_cells": len(pending_retry),
        "invalid_final_cells": len(invalid), "physical_attempts": _physical_candidate_count(store),
        "attempt_ledger_sha256": _digest(score_free_ledger),
        "gate_seal_sha256": gate_seal_sha256,
        "postflight_preflight_sha256": authorization["preflight_sha256"],
        "sealed_at": sealed_at or _utcnow(),
    }
    document["seal_sha256"] = _digest(document)
    return validate_seal(document, authorization)


def _build_gate_seal(authorization, store, schedule, *, sealed_at=None):
    attempts = extract_attempts(store, schedule, authorization)
    final, _missing, pending, invalid = _final_attempts(schedule, attempts)
    gate_ids = [cell["logical_cell_id"] for cell in schedule["records"] if cell["phase"] == "instrument_gate"]
    if len(gate_ids) != 6 or any(logical_id not in final for logical_id in gate_ids):
        raise Llama8ProductValidationError("instrument gate is incomplete")
    if any(logical_id in pending for logical_id in gate_ids) or any(logical_id in invalid for logical_id in gate_ids):
        raise Llama8ProductValidationError("instrument gate is not valid")
    gate_attempts = [final[logical_id] for logical_id in gate_ids]
    document = {
        "schema_version": GATE_SEAL_SCHEMA, "status": "sealed_instrument_valid_score_free",
        "authorization_sha256": authorization["authorization_sha256"],
        "schedule_sha256": authorization["schedule_sha256"],
        "run_id": store.run_id, "run_sha256": store.run_sha256,
        "gate_cells": 6,
        "attempt_ledger_sha256": _digest([
            {"logical_cell_id": item["logical_cell_id"], "repeat": item["repeat"], "evidence_sha256": item["evidence_sha256"]}
            for item in sorted(gate_attempts, key=lambda value: value["logical_cell_id"])
        ]),
        "sealed_at": sealed_at or _utcnow(),
    }
    document["gate_seal_sha256"] = _digest(document)
    return validate_gate_seal(document, authorization)


def validate_gate_seal(document, authorization, *, store=None, schedule=None):
    expected = {
        "schema_version", "status", "authorization_sha256", "schedule_sha256",
        "run_id", "run_sha256", "gate_cells", "attempt_ledger_sha256", "sealed_at",
        "gate_seal_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise Llama8ProductValidationError("gate seal keys drifted")
    unsigned = dict(document)
    supplied = unsigned.pop("gate_seal_sha256")
    if supplied != _digest(unsigned):
        raise Llama8ProductValidationError("gate seal digest drifted")
    if (
        document["schema_version"] != GATE_SEAL_SCHEMA
        or document["status"] != "sealed_instrument_valid_score_free"
        or document["authorization_sha256"] != authorization["authorization_sha256"]
        or document["schedule_sha256"] != authorization["schedule_sha256"]
        or document["run_id"] != RUN_ID
        or document["gate_cells"] != 6
    ):
        raise Llama8ProductValidationError("gate seal semantics drifted")
    _timestamp(document["sealed_at"], "gate seal time")
    for key in ("run_sha256", "attempt_ledger_sha256", "gate_seal_sha256"):
        _require_sha256(document[key], key)
    if store is not None:
        schedule = build_schedule() if schedule is None else validate_schedule(schedule)
        if _build_gate_seal(authorization, store, schedule, sealed_at=document["sealed_at"]) != document:
            raise Llama8ProductValidationError("gate seal differs from evidence rederivation")
    return document


def load_gate_seal(authorization, *, store=None, schedule=None):
    return validate_gate_seal(
        _load_published(GATE_SEAL_PATH, "instrument gate seal"),
        authorization, store=store, schedule=schedule,
    )


def validate_seal(document, authorization, *, store=None, schedule=None):
    validate_authorization(authorization)
    expected = {
        "schema_version", "status", "reason", "authorization_sha256", "schedule_sha256",
        "run_id", "run_sha256", "expected_logical_cells", "complete_final_cells",
        "missing_cells", "pending_retry_cells", "invalid_final_cells", "physical_attempts",
        "attempt_ledger_sha256", "gate_seal_sha256", "postflight_preflight_sha256", "sealed_at", "seal_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise Llama8ProductValidationError("seal keys drifted")
    unsigned = dict(document)
    supplied = unsigned.pop("seal_sha256")
    if supplied != _digest(unsigned):
        raise Llama8ProductValidationError("seal digest drifted")
    if (
        document["schema_version"] != SEAL_SCHEMA
        or document["status"] not in {"sealed_complete_valid", "terminated_incomplete_instrument"}
        or document["authorization_sha256"] != authorization["authorization_sha256"]
        or document["schedule_sha256"] != authorization["schedule_sha256"]
        or document["run_id"] != RUN_ID
        or document["expected_logical_cells"] != 126
        or document["postflight_preflight_sha256"] != authorization["preflight_sha256"]
    ):
        raise Llama8ProductValidationError("seal semantics drifted")
    _timestamp(document["sealed_at"], "seal time")
    for key in ("run_sha256", "attempt_ledger_sha256", "seal_sha256"):
        _require_sha256(document[key], key)
    if document["gate_seal_sha256"] is not None:
        _require_sha256(document["gate_seal_sha256"], "gate seal")
    if document["status"] == "sealed_complete_valid" and document["gate_seal_sha256"] is None:
        raise Llama8ProductValidationError("complete seal lacks gate binding")
    for key in ("complete_final_cells", "missing_cells", "pending_retry_cells", "invalid_final_cells", "physical_attempts"):
        if type(document[key]) is not int or document[key] < 0:
            raise Llama8ProductValidationError("seal count is invalid")
    if store is not None:
        schedule = build_schedule() if schedule is None else validate_schedule(schedule)
        rebuilt = _build_seal(
            authorization, store, schedule, status=document["status"], reason=document["reason"],
            sealed_at=document["sealed_at"],
        )
        if rebuilt != document:
            raise Llama8ProductValidationError("seal differs from evidence rederivation")
    return document


def load_seal(authorization, *, store=None, schedule=None):
    document = _load_published(SEAL_PATH, "product-validation seal")
    return validate_seal(document, authorization, store=store, schedule=schedule)


def _outcome_records():
    validated = load_canonical_json(VALIDATED_OUTCOMES_PATH)
    manifests = load_manifests(ROOT)
    validate_validated_outcomes(validated, manifests)
    records = validated.get("records")
    if not isinstance(records, list):
        raise Llama8ProductValidationError("validated outcomes have no records")
    return {record["instance_id"]: record for record in records}


def run_study(authorization, *, transport=None, lease_path=None):
    protocol = load_protocol()
    validate_authorization(authorization, protocol, validate_repository=True)
    schedule = validate_schedule(_load_published(SCHEDULE_PATH, "schedule"), protocol)
    if schedule != build_schedule(protocol):
        raise Llama8ProductValidationError("published schedule differs from exact rebuild")
    if ANALYSIS_PATH.exists() or ANALYSIS_PATH.with_name(ANALYSIS_PATH.name + ".complete").exists():
        raise Llama8ProductValidationError("analysis publication permanently closes inference")
    if SEAL_PATH.exists() or SEAL_PATH.with_name(SEAL_PATH.name + ".complete").exists():
        return load_seal(authorization)
    lease = BenchmarkLease(path=lease_path)
    lease.acquire(authorization["authorization_sha256"])
    try:
        _fresh_environment(authorization)
        store = _open_store(authorization)
        instances = _instances_by_id(protocol)
        outcomes = _outcome_records()
        client = transport or OllamaTransport("http://127.0.0.1:11434", 900)
        from domains.office_demo.sharvin_adapter import load_authorized_source
        authorized_source = load_authorized_source(
            authorization["external_source"]["resolved_checkout"],
            authorization["external_source"]["adapter_binding"],
        )
        initial_attempts = extract_attempts(store, schedule, authorization)
        initial_final, _initial_missing, _initial_pending, initial_invalid = _final_attempts(schedule, initial_attempts)
        gate_ids = {cell["logical_cell_id"] for cell in schedule["records"][:6]}
        primary_started = any(cell["phase"] == "primary" and cell["logical_cell_id"] in initial_final for cell in schedule["records"])
        gate_marker_exists = GATE_SEAL_PATH.exists() or GATE_SEAL_PATH.with_name(GATE_SEAL_PATH.name + ".complete").exists()
        if gate_marker_exists:
            load_gate_seal(authorization, store=store, schedule=schedule)
        elif gate_ids.issubset(initial_final) and not (gate_ids & set(initial_invalid)):
            _publish_or_recover_marker_last(
                GATE_SEAL_PATH, _build_gate_seal(authorization, store, schedule),
                "instrument gate seal",
            )
        elif primary_started:
            raise Llama8ProductValidationError("primary evidence exists without the score-free gate seal")
        for index, cell in enumerate(schedule["records"]):
            if index >= 6:
                load_gate_seal(authorization, store=store, schedule=schedule)
            attempts = extract_attempts(store, schedule, authorization)
            final, _missing, pending_retry, invalid = _final_attempts(schedule, attempts)
            if invalid:
                seal = _build_seal(
                    authorization, store, schedule,
                    status="terminated_incomplete_instrument",
                    reason="terminal_environment_or_instrument_failure",
                )
                _publish_or_recover_marker_last(SEAL_PATH, seal, "terminal seal")
                return seal
            logical_id = cell["logical_cell_id"]
            if logical_id in final:
                continue
            repeat = 1 if logical_id in pending_retry else 0
            if _physical_candidate_count(store) >= 252:
                raise Llama8ProductValidationError("no authorized physical-attempt capacity remains")
            if repeat == 1:
                first = next(item for item in attempts if item["logical_cell_id"] == logical_id and item["repeat"] == 0)
                _load_or_publish_recovery(authorization, first)
            key = _attempt_key(authorization, instances[cell["instance_id"]], cell, repeat)
            resolution = store.execute_or_resume(
                key,
                _producer(
                    authorization, instances[cell["instance_id"]],
                    outcomes[cell["instance_id"]], cell, client, authorized_source,
                ),
            )
            if resolution.state not in {"committed", "publish_blocked"}:
                raise Llama8ProductValidationError("attempt did not reach marker-last state")
            attempts = extract_attempts(store, schedule, authorization)
            final, _missing, pending_retry, invalid = _final_attempts(schedule, attempts)
            current = final.get(logical_id)
            if logical_id in pending_retry:
                # Re-enter the same schedule cell immediately; the next loop
                # iteration is not relied on for same-seed recovery.
                first = next(item for item in attempts if item["logical_cell_id"] == logical_id and item["repeat"] == 0)
                _load_or_publish_recovery(authorization, first)
                retry_key = _attempt_key(authorization, instances[cell["instance_id"]], cell, 1)
                retry = store.execute_or_resume(
                    retry_key,
                    _producer(
                        authorization, instances[cell["instance_id"]],
                        outcomes[cell["instance_id"]], cell, client, authorized_source,
                    ),
                )
                if retry.state not in {"committed", "publish_blocked"}:
                    raise Llama8ProductValidationError("same-seed retry did not publish")
                attempts = extract_attempts(store, schedule, authorization)
                final, _missing, pending_retry, invalid = _final_attempts(schedule, attempts)
                current = final.get(logical_id)
            if current is None:
                raise Llama8ProductValidationError("logical cell has no terminal attempt")
            print(json.dumps({
                "logical_cell_id": logical_id, "family": cell["family"],
                "condition": cell["condition"],
                "instrument_valid": current["failure_origin"] not in ("environment", "instrument"),
                "completed_cells": len(final), "expected_cells": 126,
            }, sort_keys=True), flush=True)
            if invalid:
                seal = _build_seal(
                    authorization, store, schedule,
                    status="terminated_incomplete_instrument",
                    reason="terminal_environment_or_instrument_failure",
                )
                _publish_or_recover_marker_last(SEAL_PATH, seal, "terminal seal")
                return seal
            if index == 5:
                gate_ids = {item["logical_cell_id"] for item in schedule["records"][:6]}
                if not gate_ids.issubset(final):
                    raise Llama8ProductValidationError("opening compatibility gate is incomplete")
                if GATE_SEAL_PATH.exists() or GATE_SEAL_PATH.with_name(GATE_SEAL_PATH.name + ".complete").exists():
                    load_gate_seal(authorization, store=store, schedule=schedule)
                else:
                    _publish_or_recover_marker_last(
                        GATE_SEAL_PATH, _build_gate_seal(authorization, store, schedule),
                        "instrument gate seal",
                    )
        _fresh_environment(authorization)
        seal = _build_seal(
            authorization, store, schedule,
            status="sealed_complete_valid", reason="all_authorized_cells_complete_and_valid",
        )
        _publish_or_recover_marker_last(SEAL_PATH, seal, "terminal seal")
        return seal
    finally:
        lease.release()


def _fraction_record(value):
    value = Fraction(value)
    return {
        "fraction": f"{value.numerator}/{value.denominator}",
        "decimal": format(float(value), ".12f"),
    }


def _condition_resource_report(records):
    exact_total = sum(item["generated_tokens_lower_bound"] for item in records)
    upper_total = sum(item["generated_tokens_upper_bound"] for item in records)
    return {
        "attempts": len(records),
        "model_calls": sum(item["model_calls"] for item in records),
        "generated_tokens_lower_bound": exact_total,
        "generated_tokens_upper_bound": upper_total,
        "all_generated_token_counts_exact": all(item["generated_tokens_exact"] for item in records),
        "successful_actions": sum(item["successful_actions"] for item in records),
        "actions": sum(item["action_count"] for item in records),
        "verifier_unverified_count": sum(item["verifier_unverified_count"] for item in records),
        "argument_repair_count": sum(item["repair_count"] for item in records),
        "opportunity_budget_exhausted_attempts": sum(item["opportunity_budget_exhausted"] for item in records),
    }


def _operational_attempt_report(attempts, schedule):
    """Summarize physical retries and instrument-invalid evidence by study phase."""

    cells = _schedule_by_id(schedule)
    scoped = {
        "all_authorized": list(attempts),
        "instrument_gate": [
            item for item in attempts
            if cells[item["logical_cell_id"]]["phase"] == "instrument_gate"
        ],
        "primary": [
            item for item in attempts
            if cells[item["logical_cell_id"]]["phase"] == "primary"
        ],
    }

    def summarize(records):
        return {
            "physical_attempts": len(records),
            "repeat_1_same_seed_retries": sum(item["repeat"] == 1 for item in records),
            "environment_invalid_physical_attempts": sum(
                item["failure_origin"] == "environment" for item in records
            ),
            "instrument_invalid_physical_attempts": sum(
                item["failure_origin"] == "instrument" for item in records
            ),
        }

    return {scope: summarize(records) for scope, records in scoped.items()}


def _derive_analysis(authorization, store, schedule, seal, *, analyzed_at=None):
    validate_seal(seal, authorization, store=store, schedule=schedule)
    if seal["status"] != "sealed_complete_valid":
        raise Llama8ProductValidationError("incomplete evidence cannot be analyzed")
    attempts = extract_attempts(store, schedule, authorization)
    final, missing, pending, invalid = _final_attempts(schedule, attempts)
    if len(final) != 126 or missing or pending or invalid:
        raise Llama8ProductValidationError("analysis requires 126 valid final attempts including the gate")
    cells = _schedule_by_id(schedule)
    by_cluster = defaultdict(dict)
    by_condition = {name: [] for name in CONDITIONS}
    for logical_id, record in final.items():
        cell = cells[logical_id]
        if cell["phase"] == "instrument_gate":
            if record["failure_origin"] not in ("none", "model") or record["strict_success"] is not None:
                raise Llama8ProductValidationError("instrument gate evidence is not score-free and valid")
            continue
        if record["failure_origin"] not in ("none", "model") or type(record["strict_success"]) is not bool:
            raise Llama8ProductValidationError("analysis contains a non-efficacy final attempt")
        key = (cell["family"], cell["instance_id"])
        if cell["condition"] in by_cluster[key]:
            raise Llama8ProductValidationError("analysis cluster condition is duplicated")
        by_cluster[key][cell["condition"]] = record
        by_condition[cell["condition"]].append(record)
    if len(by_cluster) != 60 or any(set(values) != set(CONDITIONS) for values in by_cluster.values()):
        raise Llama8ProductValidationError("analysis pairing drifted")
    family_differences = defaultdict(list)
    family_counts = defaultdict(lambda: {name: 0 for name in CONDITIONS})
    cap_patterns = Counter()
    for (family, _instance_id), values in sorted(by_cluster.items()):
        native = int(values["native_tools"]["strict_success"])
        treatment = int(values["sharvin_balanced_adapter"]["strict_success"])
        family_differences[family].append(Fraction(treatment - native, 1))
        family_counts[family]["native_tools"] += native
        family_counts[family]["sharvin_balanced_adapter"] += treatment
        cap_patterns[(
            values["sharvin_balanced_adapter"]["opportunity_budget_exhausted"],
            values["native_tools"]["opportunity_budget_exhausted"],
        )] += 1
    if set(family_differences) != set(FAMILIES) or any(len(values) != 20 for values in family_differences.values()):
        raise Llama8ProductValidationError("analysis family cluster counts drifted")
    family_effects = {
        family: sum(values, Fraction(0, 1)) / len(values)
        for family, values in family_differences.items()
    }
    delta = sum(family_effects.values(), Fraction(0, 1)) / len(FAMILIES)
    bootstrap = _focused._bootstrap_interval(
        family_differences, protocol_sha256(), "llama8_product_primary", 50000,
    )
    lower, upper = bootstrap["lower"], bootstrap["upper"]
    threshold = Fraction(12, 100)
    if delta >= threshold and lower > 0:
        disposition = "sharvin_balanced_adapter_superiority"
    elif delta <= -threshold and upper < 0:
        disposition = "native_tools_superiority"
    else:
        disposition = "no_directional_superiority_claim"
    lofo = []
    for family in FAMILIES:
        remaining = [family_effects[item] for item in FAMILIES if item != family]
        effect = sum(remaining, Fraction(0, 1)) / len(remaining)
        lofo.append({
            "excluded_family": family, "clusters": 40,
            "effect": _fraction_record(effect),
            "shift_from_all_family": _fraction_record(effect - delta),
            "descriptive_only": True,
        })
    sign_flip = _focused._sign_flip(
        [value for family in FAMILIES for value in family_differences[family]]
    )
    variance = _focused._variance_records(family_differences)
    operational_attempts = _operational_attempt_report(attempts, schedule)
    if operational_attempts["all_authorized"]["physical_attempts"] != seal["physical_attempts"]:
        raise Llama8ProductValidationError("analysis physical-attempt count differs from seal")
    document = {
        "schema_version": ANALYSIS_SCHEMA, "status": "sealed_complete_analysis",
        "classification": load_protocol()["classification"],
        "authorization_sha256": authorization["authorization_sha256"],
        "schedule_sha256": authorization["schedule_sha256"],
        "seal_sha256": seal["seal_sha256"], "analyzed_at": analyzed_at or _utcnow(),
        "estimand": "equal-family mean of paired strict-success differences; sharvin_balanced_adapter minus native_tools",
        "paired_clusters": 60, "clusters_per_family": 20,
        "condition_results": {
            condition: {
                "successes": sum(int(item["strict_success"]) for item in by_condition[condition]),
                "attempts": len(by_condition[condition]),
                "success_rate": _fraction_record(Fraction(
                    sum(int(item["strict_success"]) for item in by_condition[condition]),
                    len(by_condition[condition]),
                )),
                "resources": _condition_resource_report(by_condition[condition]),
            }
            for condition in CONDITIONS
        },
        "family_results": {
            family: {
                "paired_clusters": 20,
                "native_tools_successes": family_counts[family]["native_tools"],
                "sharvin_balanced_adapter_successes": family_counts[family]["sharvin_balanced_adapter"],
                "paired_effect": _fraction_record(family_effects[family]),
            }
            for family in FAMILIES
        },
        "paired_effect": _fraction_record(delta),
        "bootstrap_95_percent_interval": {
            "lower": _fraction_record(lower), "upper": _fraction_record(upper),
            "replicates": bootstrap["replicates"], "sampling": bootstrap["sampling"],
            "interval": bootstrap["interval"],
            "first_100_index_vectors_sha256": bootstrap["first_100_index_vectors_sha256"],
        },
        "claim_rule": {
            "minimum_absolute_effect": "0.12", "requires_interval_excluding_zero": True,
            "disposition": disposition,
        },
        "exact_sign_flip_diagnostic": {
            "method": sign_flip["method"], "nonzero_clusters": sign_flip["nonzero_clusters"],
            "two_sided_p": _fraction_record(sign_flip["two_sided_p"]), "claim_gating": False,
        },
        "variance_diagnostic": {key: _fraction_record(value) for key, value in variance.items()},
        "leave_one_family_out": lofo,
        "budget_exhaustion_patterns": {
            "neither": cap_patterns[(False, False)],
            "treatment_only": cap_patterns[(True, False)],
            "native_only": cap_patterns[(False, True)],
            "both": cap_patterns[(True, True)],
        },
        "operational_attempts": operational_attempts,
        "limitations": list(load_protocol()["reporting"]["limitations"]),
        "never_claim": list(load_protocol()["reporting"]["never_claim"]),
    }
    document["analysis_sha256"] = _digest(document)
    return document


def validate_analysis(document, authorization, *, store, schedule, seal):
    expected = {
        "schema_version", "status", "classification", "authorization_sha256",
        "schedule_sha256", "seal_sha256", "analyzed_at", "estimand", "paired_clusters",
        "clusters_per_family", "condition_results", "family_results", "paired_effect",
        "bootstrap_95_percent_interval", "claim_rule", "exact_sign_flip_diagnostic",
        "variance_diagnostic", "leave_one_family_out", "budget_exhaustion_patterns",
        "operational_attempts", "limitations", "never_claim", "analysis_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise Llama8ProductValidationError("analysis keys drifted")
    unsigned = dict(document)
    supplied = unsigned.pop("analysis_sha256")
    if supplied != _digest(unsigned):
        raise Llama8ProductValidationError("analysis digest drifted")
    rebuilt = _derive_analysis(
        authorization, store, schedule, seal, analyzed_at=document["analyzed_at"],
    )
    if rebuilt != document:
        raise Llama8ProductValidationError("analysis differs from evidence rederivation")
    return document


def publish_analysis(authorization):
    validate_authorization(authorization, validate_repository=True)
    schedule = validate_schedule(_load_published(SCHEDULE_PATH, "schedule"))
    store = _open_store(authorization)
    seal = load_seal(authorization, store=store, schedule=schedule)
    if ANALYSIS_PATH.exists() or ANALYSIS_PATH.with_name(ANALYSIS_PATH.name + ".complete").exists():
        return validate_analysis(
            _load_published(ANALYSIS_PATH, "analysis"), authorization,
            store=store, schedule=schedule, seal=seal,
        )
    document = _derive_analysis(authorization, store, schedule, seal)
    _publish_or_recover_marker_last(ANALYSIS_PATH, document, "analysis")
    return document


def _derive_report(authorization, analysis, *, reported_at=None):
    protocol = load_protocol()
    document = {
        "schema_version": REPORT_SCHEMA, "status": "final_verified_product_validation_report",
        "study_label": "v0.13.8 Llama 3.1 8B fixed-panel product-system validation",
        "reported_at": reported_at or _utcnow(),
        "authorization_sha256": authorization["authorization_sha256"],
        "analysis_sha256": analysis["analysis_sha256"],
        "research_question": "On controlled local office tasks where data remains on-device, does the pinned Sharvin balanced orchestration adapter outperform a matched minimal native-tools baseline on the same Llama 3.1 8B model?",
        "answer": {
            "disposition": analysis["claim_rule"]["disposition"],
            "paired_effect": analysis["paired_effect"],
            "bootstrap_95_percent_interval": analysis["bootstrap_95_percent_interval"],
            "condition_results": analysis["condition_results"],
        },
        "panel": {
            "families": list(FAMILIES), "paired_clusters": 60, "cells": 120,
            "selected_ordinals": list(SELECTED_ORDINALS),
            "selection_sha256": SELECTOR_DIGEST,
        },
        "system_contrast": {
            "treatment": "Sharvin balanced orchestration adapter over Brick typed executor",
            "control": "minimal native Ollama tools over the same Brick typed executor",
            "model": MODEL_TAG, "model_digest": MODEL_DIGEST,
            "local_data_boundary": "loopback Ollama and local synthetic office state; no external account connectors",
        },
        "family_results": analysis["family_results"],
        "leave_one_family_out": analysis["leave_one_family_out"],
        "budget_exhaustion_patterns": analysis["budget_exhaustion_patterns"],
        "operational_attempts": analysis["operational_attempts"],
        "exact_sign_flip_diagnostic": analysis["exact_sign_flip_diagnostic"],
        "limitations": list(protocol["reporting"]["limitations"]),
        "never_claim": list(protocol["reporting"]["never_claim"]),
    }
    document["report_sha256"] = _digest(document)
    return document


def validate_report(document, authorization, analysis):
    expected = {
        "schema_version", "status", "study_label", "reported_at", "authorization_sha256",
        "analysis_sha256", "research_question", "answer", "panel", "system_contrast",
        "family_results", "leave_one_family_out", "budget_exhaustion_patterns",
        "operational_attempts", "exact_sign_flip_diagnostic", "limitations", "never_claim",
        "report_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise Llama8ProductValidationError("report keys drifted")
    unsigned = dict(document)
    supplied = unsigned.pop("report_sha256")
    if supplied != _digest(unsigned):
        raise Llama8ProductValidationError("report digest drifted")
    rebuilt = _derive_report(authorization, analysis, reported_at=document["reported_at"])
    if rebuilt != document:
        raise Llama8ProductValidationError("report differs from analysis rederivation")
    return document


def publish_report(authorization):
    validate_authorization(authorization, validate_repository=True)
    schedule = validate_schedule(_load_published(SCHEDULE_PATH, "schedule"))
    store = _open_store(authorization)
    seal = load_seal(authorization, store=store, schedule=schedule)
    analysis = validate_analysis(
        _load_published(ANALYSIS_PATH, "analysis"), authorization,
        store=store, schedule=schedule, seal=seal,
    )
    if REPORT_PATH.exists() or REPORT_PATH.with_name(REPORT_PATH.name + ".complete").exists():
        return validate_report(_load_published(REPORT_PATH, "report"), authorization, analysis)
    document = _derive_report(authorization, analysis)
    _publish_or_recover_marker_last(REPORT_PATH, document, "report")
    return document


def seal_complete_after_resume(authorization, *, lease_path=None):
    validate_authorization(authorization, validate_repository=True)
    lease = BenchmarkLease(path=lease_path)
    lease.acquire(authorization["authorization_sha256"])
    try:
        _fresh_environment(authorization)
        schedule = validate_schedule(_load_published(SCHEDULE_PATH, "schedule"))
        store = _open_store(authorization)
        if SEAL_PATH.exists() or SEAL_PATH.with_name(SEAL_PATH.name + ".complete").exists():
            return load_seal(authorization, store=store, schedule=schedule)
        seal = _build_seal(
            authorization, store, schedule,
            status="sealed_complete_valid", reason="all_authorized_cells_complete_and_valid",
        )
        _publish_or_recover_marker_last(SEAL_PATH, seal, "terminal seal")
        return seal
    finally:
        lease.release()


def validate_lifecycle(authorization):
    validate_authorization(authorization, validate_repository=True)
    schedule = validate_schedule(_load_published(SCHEDULE_PATH, "schedule"))
    if schedule != build_schedule():
        raise Llama8ProductValidationError("published schedule does not rebuild exactly")
    store = _open_store(authorization)
    gate = load_gate_seal(authorization, store=store, schedule=schedule)
    seal = load_seal(authorization, store=store, schedule=schedule)
    result = {"gate_seal_sha256": gate["gate_seal_sha256"], "seal_sha256": seal["seal_sha256"]}
    if ANALYSIS_PATH.exists() or ANALYSIS_PATH.with_name(ANALYSIS_PATH.name + ".complete").exists():
        analysis = validate_analysis(
            _load_published(ANALYSIS_PATH, "analysis"), authorization,
            store=store, schedule=schedule, seal=seal,
        )
        result["analysis_sha256"] = analysis["analysis_sha256"]
        if REPORT_PATH.exists() or REPORT_PATH.with_name(REPORT_PATH.name + ".complete").exists():
            report = validate_report(_load_published(REPORT_PATH, "report"), authorization, analysis)
            result["report_sha256"] = report["report_sha256"]
    return result


def _cli_preflight(args):
    document = collect_preflight(args.sharvin_checkout, require_clean=True)
    _publish_or_recover_marker_last(PREFLIGHT_PATH, document, "preflight")
    print(json.dumps({"status": document["status"], "preflight_sha256": document["preflight_sha256"], "live_model_calls": 0}, sort_keys=True))
    return 0


def _cli_authorize(args):
    preflight = validate_preflight(_load_published(PREFLIGHT_PATH, "preflight"))
    authorization = publish_authorization(preflight)
    print(json.dumps({"status": authorization["status"], "authorization_sha256": authorization["authorization_sha256"], "logical_cells": 126}, sort_keys=True))
    return 0


def _cli_run(args):
    authorization = load_authorization(validate_repository=True)
    seal = run_study(authorization, lease_path=args.lease_path)
    print(json.dumps({
        "status": seal["status"], "complete_final_cells": seal["complete_final_cells"],
        "expected_logical_cells": seal["expected_logical_cells"], "seal_sha256": seal["seal_sha256"],
    }, sort_keys=True))
    return 0 if seal["status"] == "sealed_complete_valid" else 2


def _cli_seal(args):
    authorization = load_authorization(validate_repository=True)
    seal = seal_complete_after_resume(authorization, lease_path=args.lease_path)
    print(json.dumps({"status": seal["status"], "seal_sha256": seal["seal_sha256"]}, sort_keys=True))
    return 0


def _cli_analyze(_args):
    authorization = load_authorization(validate_repository=True)
    analysis = publish_analysis(authorization)
    print(json.dumps({"status": analysis["status"], "analysis_sha256": analysis["analysis_sha256"]}, sort_keys=True))
    return 0


def _cli_report(_args):
    authorization = load_authorization(validate_repository=True)
    report = publish_report(authorization)
    print(json.dumps({"status": report["status"], "report_sha256": report["report_sha256"], "path": str(REPORT_PATH)}, sort_keys=True))
    return 0


def _cli_validate(args):
    protocol = load_protocol()
    schedule = build_schedule(protocol)
    result = {"protocol_sha256": protocol_sha256(protocol), "schedule_sha256": _digest(schedule), "logical_cells": 126, "benchmark_cells": 120}
    if args.kind == "protocol":
        pass
    elif args.kind == "authorization":
        authorization = load_authorization(validate_repository=True)
        result["authorization_sha256"] = authorization["authorization_sha256"]
    elif args.kind == "lifecycle":
        authorization = load_authorization(validate_repository=True)
        result.update(validate_lifecycle(authorization))
    else:
        raise Llama8ProductValidationError("unknown validation kind")
    print(json.dumps(result, sort_keys=True))
    return 0


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--sharvin-checkout", required=True)
    preflight.set_defaults(func=_cli_preflight)
    authorize = subparsers.add_parser("authorize")
    authorize.set_defaults(func=_cli_authorize)
    run = subparsers.add_parser("run")
    run.add_argument("--lease-path")
    run.set_defaults(func=_cli_run)
    seal = subparsers.add_parser("seal")
    seal.add_argument("--lease-path")
    seal.set_defaults(func=_cli_seal)
    analyze = subparsers.add_parser("analyze")
    analyze.set_defaults(func=_cli_analyze)
    report = subparsers.add_parser("report")
    report.set_defaults(func=_cli_report)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--kind", choices=("protocol", "authorization", "lifecycle"), required=True)
    validate.set_defaults(func=_cli_validate)
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        return args.func(args)
    except Llama8ProductValidationError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
