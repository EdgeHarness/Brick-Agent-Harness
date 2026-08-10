"""Strict v0.13.6 recovery successor for the terminated v0.13.5 follow-up.

This program does not restart or alter the old run.  It binds and validates the
old evidence read-only, executes only the 24 never-started B1b cells in one new
EvidenceStore run, and executes the already-frozen 240-cell B2 schedule in a
second new EvidenceStore run.  Results remain score-masked until both runs have
an immutable terminal artifact.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import datetime as _datetime
from fractions import Fraction
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import socket
import subprocess

from harness.evidence import AttemptKey, EvidenceStore, canonical_json_bytes, validate_committed
from harness import evidence as _evidence
from harness.instances import load_canonical_json, sha256_bytes
from harness import experiment as _experiment

from . import focused_followup as _focused
from . import next_study_live as _live
from .next_study_program import BenchmarkLease, validate_lease


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "bench" / "focused_recovery_successor_protocol.json"
OLD_PROTOCOL_PATH = ROOT / "bench" / "focused_followup_protocol.json"
OLD_ROOT = ROOT / "results-next-study" / "focused-v0135-focused-followup-r1"
SUCCESSOR_ROOT = ROOT / "results-next-study" / "focused-recovery-v0136"
AUTHORIZATION_PATH = SUCCESSOR_ROOT / "authorization.json"
PARSER_INCIDENT_PATH = (
    ROOT / "evidence" / "next-study"
    / "office-v2.3.0-focused-followup-b1b-parser-incident-audit.json"
)
PROJECTION_REWRITE_PATH = (
    ROOT / "evidence" / "next-study"
    / "office-v2.3.0-focused-followup-preauthorization-projection-rewrite.json"
)
CLASSIFIER_SOURCE_PATH = ROOT / "harness" / "experiment.py"
RELEASE_VERIFIER_PATH = ROOT / "bench" / "focused_recovery_release_verifier.py"

BLOCKS = ("B1b_recovery", "B2_repeatability")
RUN_SPECS = {
    "B1b_recovery": {
        "runs_root": SUCCESSOR_ROOT / "b1b-recovery",
        "runs_root_relative": "results-next-study/focused-recovery-v0136/b1b-recovery",
        "run_id": "v0136-b1b-recovery-r1",
        "logical_cells": 24,
        "maximum_physical_attempts": 48,
    },
    "B2_repeatability": {
        "runs_root": SUCCESSOR_ROOT / "b2-repeatability",
        "runs_root_relative": "results-next-study/focused-recovery-v0136/b2-repeatability",
        "run_id": "v0136-b2-repeatability-r1",
        "logical_cells": 240,
        "maximum_physical_attempts": 480,
    },
}

PROTOCOL_SCHEMA = "brick.focused-recovery-successor.protocol/1"
AUTHORIZATION_SCHEMA = "brick.focused-recovery-successor.authorization/1"
SCHEDULE_SCHEMA = "brick.focused-recovery-successor.schedule/1"
RUN_METADATA_SCHEMA = "brick.focused-recovery-successor.run-metadata/1"
BLOCK_START_SCHEMA = "brick.focused-recovery-successor.block-start/1"
CELL_START_SCHEMA = "brick.focused-recovery-successor.logical-cell-start/1"
BLOCK_SEAL_SCHEMA = "brick.focused-recovery-successor.block-seal/1"
TERMINATION_SCHEMA = "brick.focused-recovery-successor.block-termination/1"
ANALYSIS_SCHEMA = "brick.focused-recovery-successor.analysis/1"
REPORT_SCHEMA = "brick.focused-recovery-successor.report/1"
RELEASE_ARCHIVE_SCHEMA = "brick.focused-recovery-successor.release-archive/1"
RELEASE_MANIFEST_SCHEMA = "brick.focused-recovery-successor.release-manifest/1"
VERIFICATION_SCHEMA = "brick.focused-recovery-successor.independent-verification/1"
LEASE_RECOVERY_SCHEMA = "brick.focused-recovery-successor.stale-lease-recovery/1"
CLASSIFIER_VERSION = "qwen35-tool-syntax-rejection/2"
OBSERVED_PARSER_ERROR = (
    "XML syntax error on line 11: element <parameter> closed by </function>"
)
PARSER_LOG_TIMESTAMPS = (
    "2026-08-09T22:49:29.870-05:00",
    "2026-08-09T22:54:51.632-05:00",
)
PARSER_CELL_ID = "ee2cf0875ec6b5afb7cf2831e0229637ffc8be2380cb2332ff550e7ad88de25d"
PARSER_REPEAT_EVIDENCE = {
    0: "51ec36cbda3eed4ea3a131746170498fda2fb16f29d64f73136a90a9e22485eb",
    1: "348b449fad8e6e9cd0cd0b9203726a0333d2d5503831f9f0e966ec1bd88ce9db",
}
PARSER_REQUEST_SHA256 = {
    0: "71d482d2762a1be64701e19149680785ea4108a2fb176fc231cf49cfd542badf",
    1: "1539019e846f065b4a07a7c9a2357ad9a5696ddb223cf3092e77f06c5f1e2998",
}
BOOTSTRAP_INDEX_GOLDENS = {
    "recovered_B1b": "2bedf0bcdbfb8afe21e82d452ebf0a36c9fd20ae50d9cb4a04383c59d6f7b331",
    "B1": "dd7b1dc702beada0f5548f22bf8f74648990feb134551207f3a5cc2de8f38ebd",
    "B2_two_trial": "70fcd0e2e6668e9021ecfc8b64c0d9d45f09235f8dea14b8a82d0da3c31041c2",
    "B2_trial_1_descriptive": "e36449e15f2bf537d3c5482788e4334b02edd3d7c5da7716f85c03649b18e4d1",
}
_PROTOCOL_DIGEST = "bd22a171b390f01f8d401bbeb497b4ed0a3723a2f779a83e3476df6783f8b482"
HARD_STOP = "2026-08-11T11:00:00-05:00"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")


class FocusedRecoveryError(ValueError):
    """Recovery authorization, evidence, or state is invalid."""


def _digest(value):
    return sha256_bytes(canonical_json_bytes(value, allow_float=False))


def _file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _timestamp(value, label):
    try:
        parsed = _datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise FocusedRecoveryError(label + " must be ISO-8601 with timezone") from exc
    if parsed.utcoffset() is None:
        raise FocusedRecoveryError(label + " must include a timezone")
    return parsed


def _utcnow():
    return _datetime.datetime.now(_datetime.timezone.utc).isoformat()


def _hard_stop_reached(value):
    """Return the frozen stop decision, called only between logical cells."""

    return _timestamp(value, "current time") >= _timestamp(HARD_STOP, "hard stop")


def _require_sha256(value, label):
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise FocusedRecoveryError(label + " must be lowercase SHA-256")
    return value


def _require_sha1(value, label):
    if not isinstance(value, str) or _SHA1.fullmatch(value) is None:
        raise FocusedRecoveryError(label + " must be lowercase Git SHA-1")
    return value


def _git(*args):
    try:
        return subprocess.run(
            ["git", *args], cwd=str(ROOT), check=True, capture_output=True,
            text=True, timeout=30,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise FocusedRecoveryError("git repository binding failed") from exc


def _git_blob_bytes(revision, relative):
    try:
        return subprocess.run(
            ["git", "cat-file", "blob", "%s:%s" % (revision, relative)],
            cwd=str(ROOT), check=True, capture_output=True, timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise FocusedRecoveryError("git blob binding failed") from exc


def _publish_marker_last(path, document, validator=None):
    path = Path(path)
    _assert_not_old_path(path)
    marker = path.with_name(path.name + ".complete")
    if marker.exists():
        if not path.is_file() or not marker.is_file() or marker.stat().st_size != 0:
            raise FocusedRecoveryError("invalid existing marker-last evidence")
        existing = _load_published(path, "existing marker-last evidence")
        if existing != document:
            raise FocusedRecoveryError("existing marker-last evidence differs")
        if validator is not None:
            validator(existing)
        return path
    if path.exists():
        if not path.is_file():
            raise FocusedRecoveryError("partial marker-last evidence is not a file")
        existing = _load_document(path, "partial marker-last evidence")
        if existing != document:
            raise FocusedRecoveryError("partial marker-last evidence differs")
        if validator is not None:
            validator(existing)
        with marker.open("xb") as handle:
            handle.flush(); os.fsync(handle.fileno())
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(document, newline=True, allow_float=False)
    with path.open("xb") as handle:
        handle.write(payload); handle.flush(); os.fsync(handle.fileno())
    with marker.open("xb") as handle:
        handle.flush(); os.fsync(handle.fileno())
    return path


def _load_published(path, label):
    path = Path(path)
    marker = path.with_name(path.name + ".complete")
    if not path.is_file() or not marker.is_file() or marker.stat().st_size != 0:
        raise FocusedRecoveryError(label + " marker-last artifact is missing")
    try:
        return load_canonical_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise FocusedRecoveryError(label + " is unreadable") from exc


def _assert_not_old_path(path):
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(OLD_ROOT.resolve())
    except ValueError:
        return resolved
    raise FocusedRecoveryError("old v0.13.5 evidence root is strictly read-only")


def _old_tree_manifest():
    """Hash every old file without opening any old path for writing."""

    if not OLD_ROOT.is_dir():
        raise FocusedRecoveryError("old v0.13.5 evidence root is missing")
    records = []
    for path in sorted(OLD_ROOT.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink() or not path.is_file():
            if path.is_symlink():
                raise FocusedRecoveryError("old evidence contains a symlink")
            continue
        relative = path.relative_to(OLD_ROOT).as_posix()
        records.append({
            "path": relative, "size": path.stat().st_size,
            "sha256": _file_digest(path),
        })
    return {"files": len(records), "tree_sha256": _digest(records)}


def load_protocol(path=PROTOCOL_PATH):
    try:
        document = load_canonical_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise FocusedRecoveryError("recovery protocol is unreadable") from exc
    return validate_protocol(document)


def validate_protocol(document):
    if not isinstance(document, dict) or _digest(document) != _PROTOCOL_DIGEST:
        raise FocusedRecoveryError("recovery protocol differs from the canonical freeze")
    if (
        document.get("schema_version") != PROTOCOL_SCHEMA
        or document.get("version") != "1.0.0"
        or document.get("status") != "frozen_before_successor_execution"
        or tuple(document["base_instrument"]["conditions"]) != _focused.CONDITIONS
        or document["execution"]["maximum_logical_cells"] != 264
        or document["execution"]["maximum_physical_attempts"] != 528
        or document["execution"]["hard_stop"] != HARD_STOP
        or set(document["execution"]["blocks"]) != set(BLOCKS)
        or document["parser_incident"]["classifier_version"] != CLASSIFIER_VERSION
        or document["parser_incident"]["observed_error"] != OBSERVED_PARSER_ERROR
        or document["analysis"]["pooling_headline_allowed"] is not False
    ):
        raise FocusedRecoveryError("recovery protocol identity drifted")
    for block, spec in RUN_SPECS.items():
        frozen = document["execution"]["blocks"][block]
        if frozen != {
            "logical_cells": spec["logical_cells"],
            "maximum_physical_attempts": spec["maximum_physical_attempts"],
            "run_id": spec["run_id"], "runs_root": spec["runs_root_relative"],
            "schedule_sha256": (
                "f35767d3f927c9f921ee7b02f52af7b6464e5763e84b7eb8e7cedba32d1efb85"
                if block == "B1b_recovery" else
                "3bceef7d51f986093ea4ce5587ecc844de7a0fe28324fe3f7043a9e2c283eb71"
            ),
        }:
            raise FocusedRecoveryError("recovery block freeze drifted")
    return document


def protocol_sha256(protocol=None):
    return _digest(load_protocol() if protocol is None else validate_protocol(protocol))


def _old_path(binding):
    path = (ROOT / binding["path"]).resolve()
    try:
        path.relative_to(OLD_ROOT.resolve())
    except ValueError as exc:
        raise FocusedRecoveryError("old binding escapes the immutable root") from exc
    return path


def _bound_source_path(binding):
    path = (ROOT / binding["path"]).resolve()
    if path != OLD_PROTOCOL_PATH.resolve():
        return _old_path(binding)
    return path


def _validate_old_bindings(protocol):
    bindings = protocol["old_bindings"]
    file_labels = (
        "authorization", "protocol", "run", "results_projection", "b1a_start",
        "b1a_seal", "b1b_start", "b1b_termination", "closed_analysis", "report",
    )
    for label in file_labels:
        binding = bindings[label]
        path = _bound_source_path(binding)
        if _file_digest(path) != binding["file_sha256"]:
            raise FocusedRecoveryError("old %s file digest drifted" % label)
        marker = path.with_name(path.name + ".complete")
        if label not in ("run", "results_projection", "protocol") and (
            not marker.is_file() or marker.stat().st_size != 0
        ):
            raise FocusedRecoveryError("old %s marker-last binding is missing" % label)
    authorization = _load_published(_old_path(bindings["authorization"]), "old authorization")
    run = load_canonical_json(_old_path(bindings["run"]))
    b1a = _load_published(_old_path(bindings["b1a_seal"]), "old B1a seal")
    b1a_start = _load_published(_old_path(bindings["b1a_start"]), "old B1a start")
    b1b_start = _load_published(_old_path(bindings["b1b_start"]), "old B1b start")
    termination = _load_published(_old_path(bindings["b1b_termination"]), "old B1b termination")
    analysis = _load_published(_old_path(bindings["closed_analysis"]), "old closed analysis")
    report = _load_published(_old_path(bindings["report"]), "old report")
    old_protocol = load_canonical_json(_bound_source_path(bindings["protocol"]))
    if authorization.get("authorization_sha256") != bindings["authorization"]["authorization_sha256"]:
        raise FocusedRecoveryError("old authorization semantic digest drifted")
    if (
        run.get("run_id") != bindings["run"]["run_id"]
        or _file_digest(_old_path(bindings["run"])) != bindings["run"]["run_sha256"]
        or b1a.get("seal_sha256") != bindings["b1a_seal"]["seal_sha256"]
        or b1a.get("attempt_records_sha256") != bindings["b1a_seal"]["attempt_records_sha256"]
        or b1a_start.get("start_sha256") != bindings["b1a_start"]["start_sha256"]
        or b1b_start.get("start_sha256") != bindings["b1b_start"]["start_sha256"]
        or termination.get("termination_sha256") != bindings["b1b_termination"]["termination_sha256"]
        or termination.get("attempt_records_sha256") != bindings["b1b_termination"]["attempt_records_sha256"]
        or analysis.get("analysis_sha256") != bindings["closed_analysis"]["analysis_sha256"]
        or report.get("report_sha256") != bindings["report"]["report_sha256"]
        or _focused.protocol_sha256(old_protocol) != bindings["protocol"]["protocol_sha256"]
        or authorization.get("schedule_digests") != bindings["schedules"]
        or termination.get("logical_cells_complete") != 216
        or termination.get("missing_cells") != 24
        or termination.get("instrument_invalid_cells") != 1
    ):
        raise FocusedRecoveryError("old semantic artifact binding drifted")
    return {
        "authorization": authorization, "run": run, "b1a_seal": b1a,
        "b1b_termination": termination, "closed_analysis": analysis, "report": report,
    }


class _ProbeResponse:
    status_code = 500

    def json(self):
        return {"error": OBSERVED_PARSER_ERROR}


def _validate_classifier_semantics():
    payload = {"model": "qwen3.5:4b-q4_K_M", "tools": [{"type": "function"}]}
    recognized = _experiment._recognized_qwen35_tool_syntax_rejection(
        payload, _ProbeResponse(),
    )
    if recognized != OBSERVED_PARSER_ERROR:
        raise FocusedRecoveryError("current classifier does not recognize the exact incident signature")
    error = _experiment.ModelOutputProtocolError(OBSERVED_PARSER_ERROR, 500)
    result = _experiment._model_output_protocol_failure(
        error,
        type("Ledger", (), {"calls": 18, "finish_request_unknown": lambda self, *_: None})(),
        700, "driver", payload, 972074874, 0,
    )
    if result.get("retryable") is not False or result.get("type") != "model_output_tool_syntax_rejected":
        raise FocusedRecoveryError("current classifier parser disposition drifted")
    return {
        "classifier_version": CLASSIFIER_VERSION,
        "classifier_source_sha256": _file_digest(CLASSIFIER_SOURCE_PATH),
        "observed_signature_recognized": True,
        "failure_origin": "model", "retryable": False, "strict_success": False,
    }


def _load_parser_incident():
    try:
        document = load_canonical_json(PARSER_INCIDENT_PATH)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise FocusedRecoveryError("parser incident audit is unreadable") from exc
    if _file_digest(PARSER_INCIDENT_PATH) != "a3e60793e16a8e0afc06c258ed81f0965b104601c5e801c6739bf6a6d1384195":
        raise FocusedRecoveryError("parser incident audit file digest drifted")
    try:
        records = sorted(document["incident_records"], key=lambda item: item["attempt_key"]["repeat"])
        outcome = document["classifier"]["prospective_outcome"]
        excerpt = "\n".join(item["text"] for item in document["local_server_log"]["excerpt"]["lines"])
    except (KeyError, TypeError) as exc:
        raise FocusedRecoveryError("parser incident audit is incomplete") from exc
    if (
        document.get("schema_version") != "brick.next-study.focused-followup-b1b-parser-incident-audit/1"
        or document.get("status") != "source_proven_prospective_classifier_fix_only"
        or [item["attempt_key"]["repeat"] for item in records] != [0, 1]
        or any(item["attempt_key"]["instance_id"] != "v2.retained.xlsx-basic.15" for item in records)
        or [item["server_log"]["event_timestamp"] for item in records] != list(PARSER_LOG_TIMESTAMPS)
        or OBSERVED_PARSER_ERROR not in excerpt
        or outcome != {
            "failure_origin": "model", "failure_type": "model_output_tool_syntax_rejected",
            "retryable": False, "strict_success": False,
        }
        or document["classifier"]["implementation"]["canonical_lf_sha256"]
        != hashlib.sha256(CLASSIFIER_SOURCE_PATH.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    ):
        raise FocusedRecoveryError("parser incident audit lacks the exact consumed adjudication")
    for item in records:
        repeat = item["attempt_key"]["repeat"]
        evidence = item["attempt_evidence"]
        attempt_path = (ROOT / evidence["attempt_path"]).resolve()
        result_path = (ROOT / evidence["result_path"]).resolve()
        try:
            attempt_path.relative_to(OLD_ROOT.resolve()); result_path.relative_to(OLD_ROOT.resolve())
            attempt = json.loads(attempt_path.read_bytes())
            result = json.loads(result_path.read_bytes())
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            raise FocusedRecoveryError("parser incident evidence join is unreadable") from exc
        compact = item["attempt_key"]
        key = attempt["attempt_key"]
        requests = result.get("diagnostics", {}).get("requests")
        if (
            _file_digest(attempt_path) != evidence["attempt_sha256"]
            or _file_digest(result_path) != evidence["result_sha256"]
            or attempt.get("logical_hash") != evidence["logical_hash"]
            or attempt.get("physical_uuid") != evidence["physical_uuid"]
            or key["repeat"] != repeat or key["instance"]["id"] != compact["instance_id"]
            or key["instance"]["content_sha256"] != compact["instance_content_sha256"]
            or key["condition"]["name"] != compact["condition"]
            or key["condition"]["mechanism_sha256"] != compact["condition_mechanism_sha256"]
            or key["sampling"]["seed"] != compact["seed"]
            or key["sampling"]["request_seed"] != compact["request_seed"]
            or key["sampling"]["trial_index"] != 0
            or not isinstance(requests, list) or len(requests) != 17
            or requests[-1].get("request_sha256") != PARSER_REQUEST_SHA256[repeat]
            or result.get("failure_origin") != "environment"
            or result.get("failure", {}).get("http_status") != 500
        ):
            raise FocusedRecoveryError("parser incident exact attempt/result/request join drifted")
    return document


def _load_projection_rewrite_incident(protocol):
    try:
        document = load_canonical_json(PROJECTION_REWRITE_PATH)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise FocusedRecoveryError("projection rewrite incident audit is unreadable") from exc
    frozen = protocol["projection_rewrite_incident"]
    if (
        _file_digest(PROJECTION_REWRITE_PATH) != frozen["audit_file_sha256"]
        or document.get("schema_version") != frozen["audit_schema"]
        or document.get("status") != frozen["audit_status"]
        or document["authorization_status"]["occurred_before_v0.13.6_authorization"] is not True
        or document["derived_projection"]["before_sha256"] != frozen["results_file_sha256_before_and_after"]
        or document["derived_projection"]["after_sha256"] != frozen["results_file_sha256_before_and_after"]
        or document["derived_projection"]["byte_content_changed"] is not False
        or document["immutable_bindings"]["old_run_file_sha256"] != frozen["run_sha256"]
        or document["scope"]["attempt_or_marker_write_observed"] is not False
        or document["corrective_action"]["status"] != "implemented_and_verified"
    ):
        raise FocusedRecoveryError("projection rewrite incident audit drifted")
    return document


def _old_authorization_and_schedules(protocol):
    old = _validate_old_bindings(protocol)
    old_protocol = _focused.load_protocol()
    old_authorization = old["authorization"]
    schedules = {
        block: _focused.build_schedule(block, old_authorization["model_digests"]["4b"], old_protocol)
        for block in ("B1a", "B1b", "B2")
    }
    for block, schedule in schedules.items():
        if _digest(schedule) != old_authorization["schedule_digests"][block]:
            raise FocusedRecoveryError("old %s schedule reconstruction drifted" % block)
    return old, old_authorization, schedules


def _old_projection_binding(protocol):
    """Verify the derived projection as bytes without decoding efficacy fields."""

    path = _old_path(protocol["old_bindings"]["results_projection"])
    if _file_digest(path) != protocol["old_bindings"]["results_projection"]["file_sha256"]:
        raise FocusedRecoveryError("old results projection digest drifted")
    return {"path": path, "size": path.stat().st_size, "sha256": _file_digest(path)}


def _old_topology_state(protocol=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    old, authorization, schedules = _old_authorization_and_schedules(protocol)
    projection = _old_projection_binding(protocol)
    old_run_sha256 = protocol["old_bindings"]["run"].get("run_sha256")
    _require_sha256(old_run_sha256, "old bound run digest")
    if old_run_sha256 != _file_digest(_old_path(protocol["old_bindings"]["run"])):
        raise FocusedRecoveryError("old bound run digest differs from validated run bytes")
    expected_logical = {}
    cells = {}
    instances = _focused._instances_by_id()
    for block, schedule in schedules.items():
        for cell in schedule["records"]:
            coordinate = (cell["instance_id"], cell["condition"], cell["trial_seed"], cell["trial_index"])
            if coordinate in cells:
                raise FocusedRecoveryError("old union schedule coordinate is duplicated")
            cells[coordinate] = (block, cell)
            for repeat in (0, 1):
                key = _focused._expected_attempt_key(
                    instances[cell["instance_id"]], cell, authorization, repeat,
                )
                logical = AttemptKey.from_dict(key).logical_hash
                if logical in expected_logical:
                    raise FocusedRecoveryError("old expected attempt logical hash collides")
                expected_logical[logical] = (block, cell, repeat, key)
    attempts_dir = OLD_ROOT / authorization["run_id"] / "attempts"
    logical_dirs = sorted(attempts_dir.iterdir(), key=lambda item: item.name)
    if len(logical_dirs) != 457:
        raise FocusedRecoveryError("old score-free attempt directory count drifted")
    by_block = defaultdict(list); seen = set()
    for logical_dir in logical_dirs:
        if logical_dir.is_symlink() or not logical_dir.is_dir():
            raise FocusedRecoveryError("old attempt topology contains an irregular logical directory")
        matched = expected_logical.get(logical_dir.name)
        if matched is None:
            raise FocusedRecoveryError("old attempt topology contains a foreign logical hash")
        block, cell, repeat, expected_key = matched
        candidates = list(logical_dir.iterdir())
        if len(candidates) != 1 or candidates[0].is_symlink() or not candidates[0].is_dir():
            raise FocusedRecoveryError("old attempt topology lacks exactly one physical candidate")
        candidate = candidates[0]
        marker = candidate / "COMMITTED"; prepared = candidate / "PREPARED.json"
        attempt_path = candidate / "attempt.json"
        if (
            not marker.is_file() or marker.stat().st_size != 0
            or not prepared.is_file() or not attempt_path.is_file()
        ):
            raise FocusedRecoveryError("old attempt topology is not marker-last committed")
        try:
            attempt = json.loads(attempt_path.read_bytes())
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise FocusedRecoveryError("old score-free attempt identity is unreadable") from exc
        if (
            attempt.get("attempt_key") != expected_key
            or attempt.get("logical_hash") != logical_dir.name
            or attempt.get("physical_uuid") != candidate.name
            or attempt.get("run_id") != authorization["run_id"]
            or attempt.get("run_sha256") != old_run_sha256
        ):
            raise FocusedRecoveryError("old score-free attempt identity drifted")
        try:
            # Full PREPARED inventory/hash, run, key, and COMMITTED integrity is
            # checked preauthorization.  The semantic result is deliberately
            # discarded here; no efficacy field is inspected or retained.
            validate_committed(
                candidate, expected_key=AttemptKey.from_dict(expected_key),
                expected_run={"run_id": authorization["run_id"], "run_sha256": old_run_sha256},
            )
        except Exception as exc:
            raise FocusedRecoveryError("old committed candidate integrity drifted") from exc
        identity = (cell["logical_cell_id"], repeat)
        if identity in seen:
            raise FocusedRecoveryError("old score-free attempt is duplicated")
        seen.add(identity)
        by_block[block].append({
            "logical_hash": logical_dir.name, "physical_uuid": candidate.name,
            "attempt_key": expected_key, "candidate_path": candidate,
        })
    if len(by_block["B1a"]) != 240 or len(by_block["B1b"]) != 217 or by_block["B2"]:
        raise FocusedRecoveryError("old block physical topology drifted")
    b1b_started = defaultdict(set)
    for committed in by_block["B1b"]:
        key = committed["attempt_key"]
        coordinate = (
            key["instance"]["id"], key["condition"]["name"],
            key["sampling"]["seed"], key["sampling"]["trial_index"],
        )
        _block, cell = cells[coordinate]
        b1b_started[cell["logical_cell_id"]].add(key["repeat"])
    b1a_started = defaultdict(set)
    for committed in by_block["B1a"]:
        key = committed["attempt_key"]
        coordinate = (
            key["instance"]["id"], key["condition"]["name"],
            key["sampling"]["seed"], key["sampling"]["trial_index"],
        )
        _block, cell = cells[coordinate]
        b1a_started[cell["logical_cell_id"]].add(key["repeat"])
    missing = {
        cell["logical_cell_id"] for cell in schedules["B1b"]["records"]
        if cell["logical_cell_id"] not in b1b_started
    }
    parser_cell = next(cell for cell in schedules["B1b"]["records"] if cell["logical_cell_id"] == PARSER_CELL_ID)
    if (
        len(b1a_started) != 240 or any(repeats != {0} for repeats in b1a_started.values())
        or len(b1b_started) != 216 or len(missing) != 24
        or b1b_started.get(PARSER_CELL_ID) != {0, 1}
        or any(
            repeats != {0} for cell_id, repeats in b1b_started.items()
            if cell_id != PARSER_CELL_ID
        )
        or parser_cell["instance_id"] != "v2.retained.xlsx-basic.15"
        or parser_cell["condition"] != "native_tools"
    ):
        raise FocusedRecoveryError("old 215+parser+24 score-free topology drifted")
    _load_parser_incident()
    _load_projection_rewrite_incident(protocol)
    _validate_classifier_semantics()
    return {
        "old": old, "authorization": authorization, "schedules": schedules,
        "projection_binding": projection, "committed_by_block": dict(by_block),
        "b1b_missing": missing,
    }


def _extract_old_attempts_read_only(store, schedule, authorization, committed_descriptors):
    schedule_by_cell = {cell["logical_cell_id"]: cell for cell in schedule["records"]}
    schedule_by_coordinate = {
        (cell["instance_id"], cell["condition"], cell["trial_seed"], cell["trial_index"]): cell
        for cell in schedule["records"]
    }
    instances = _focused._instances_by_id(); result = []; seen = set()
    for descriptor in committed_descriptors:
        expected_key = AttemptKey.from_dict(descriptor["attempt_key"])
        try:
            validated = validate_committed(
                descriptor["candidate_path"], expected_key=expected_key,
                expected_run={"run_id": store.run_id, "run_sha256": store.run_sha256},
            )
            committed = _evidence._record_from_validated(validated)
        except Exception as exc:
            raise FocusedRecoveryError("old committed candidate failed pure read-only validation") from exc
        record = _focused._attempt_record_from_committed(
            committed, store, schedule_by_coordinate, schedule_by_cell, authorization, instances,
        )
        if record is None:
            raise FocusedRecoveryError("old read-only extraction contains a foreign attempt")
        identity = (record["logical_cell_id"], record["repeat"])
        if identity in seen:
            raise FocusedRecoveryError("old read-only extraction contains a duplicate attempt")
        seen.add(identity); result.append(record)
    return sorted(result, key=lambda item: (item["logical_cell_id"], item["repeat"]))


def _old_efficacy_state(topology):
    authorization = topology["authorization"]; schedules = topology["schedules"]
    store = EvidenceStore.open_run(OLD_ROOT, authorization["run_id"])
    _focused._validate_store_metadata(store, authorization)
    b1a_attempts = _extract_old_attempts_read_only(
        store, schedules["B1a"], authorization, topology["committed_by_block"]["B1a"],
    )
    b1b_attempts = _extract_old_attempts_read_only(
        store, schedules["B1b"], authorization, topology["committed_by_block"]["B1b"],
    )
    b1a_final, b1a_missing, b1a_invalid = _focused._final_attempts(
        schedules["B1a"], b1a_attempts, authorization, OLD_ROOT, authorization["run_id"],
    )
    b1b_final, b1b_missing, b1b_invalid = _focused._final_attempts(
        schedules["B1b"], b1b_attempts, authorization, OLD_ROOT, authorization["run_id"],
    )
    if len(b1a_final) != 240 or b1a_missing or b1a_invalid:
        raise FocusedRecoveryError("old B1a evidence is not exactly sealed-valid")
    valid_b1b = {
        cell_id: record for cell_id, record in b1b_final.items()
        if record["failure_origin"] in ("none", "model")
    }
    if (
        len(b1b_attempts) != 217 or len(b1b_final) != 216
        or len(valid_b1b) != 215 or len(b1b_missing) != 24
        or b1b_invalid != [PARSER_CELL_ID]
        or topology["old"]["b1b_termination"]["attempt_records_sha256"] != _digest(b1b_attempts)
        or set(b1b_missing) != topology["b1b_missing"]
    ):
        raise FocusedRecoveryError("old B1b 215+parser+24 topology drifted")
    parser_attempts = sorted(
        (record for record in b1b_attempts if record["logical_cell_id"] == PARSER_CELL_ID),
        key=lambda item: item["repeat"],
    )
    if (
        [item["repeat"] for item in parser_attempts] != [0, 1]
        or any(item["failure_origin"] != "environment" for item in parser_attempts)
        or any(item["evidence_sha256"] != PARSER_REPEAT_EVIDENCE[item["repeat"]] for item in parser_attempts)
    ):
        raise FocusedRecoveryError("old parser retry provenance drifted")
    incident = _load_parser_incident()
    _validate_classifier_semantics()
    derived = copy.deepcopy(parser_attempts[0])
    derived.update({"failure_origin": "model", "retryable": False, "strict_success": False})
    return {
        **topology,
        "store": store, "b1a_attempts": b1a_attempts, "b1a_final": b1a_final,
        "b1b_attempts": b1b_attempts, "b1b_valid": valid_b1b,
        "b1b_missing": set(b1b_missing), "parser_attempts": parser_attempts,
        "parser_derived": derived, "parser_incident": incident,
    }


def build_schedule(block, protocol=None, old_state=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    if block not in BLOCKS:
        raise FocusedRecoveryError("unknown recovery block")
    state = old_state if old_state is not None else _old_topology_state(protocol)
    source = state["schedules"]["B1b" if block == "B1b_recovery" else "B2"]
    if block == "B1b_recovery":
        records = [
            copy.deepcopy(cell) for cell in source["records"]
            if cell["logical_cell_id"] in state["b1b_missing"]
        ]
        if len(records) != 24 or {cell["family"] for cell in records} != {"xlsx_basic"}:
            raise FocusedRecoveryError("recovery schedule is not exactly the 24 never-started cells")
        clusters = Counter(cell["instance_id"] for cell in records)
        if len(clusters) != 12 or set(clusters.values()) != {2}:
            raise FocusedRecoveryError("recovery schedule lacks 12 complete paired clusters")
    else:
        records = copy.deepcopy(source["records"])
        if len(records) != 240 or {cell["trial_index"] for cell in records} != {1}:
            raise FocusedRecoveryError("repeatability schedule differs from frozen B2")
        if _digest(source) != protocol["old_bindings"]["schedules"]["B2"]:
            raise FocusedRecoveryError("frozen old B2 schedule byte identity drifted")
        # REP-1 freezes this exact old schedule object and its digest.  The new
        # EvidenceStore/run identity lives in authorization and run metadata;
        # it must not be smuggled into a rewritten schedule.
        return _focused.validate_schedule(source, _focused.load_protocol())
    spec = RUN_SPECS[block]
    document = {
        "schema_version": SCHEDULE_SCHEMA,
        "block": block, "source_old_schedule_sha256": _digest(source),
        "run_id": spec["run_id"], "runs_root": spec["runs_root_relative"],
        "logical_cell_count": len(records),
        "maximum_physical_attempts": spec["maximum_physical_attempts"],
        "same_seed_retry_limit": 1, "records": records,
    }
    return validate_schedule(document, protocol, old_state=state)


def validate_schedule(document, protocol=None, old_state=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    if isinstance(document, dict) and document.get("schema_version") == _focused.SCHEDULE_SCHEMA:
        validated = _focused.validate_schedule(document, _focused.load_protocol())
        if (
            validated.get("phase") != "focused_B2"
            or _digest(validated) != protocol["old_bindings"]["schedules"]["B2"]
            or old_state is not None and validated != old_state["schedules"]["B2"]
        ):
            raise FocusedRecoveryError("repeatability schedule is not exact frozen old B2")
        return validated
    expected = {
        "schema_version", "block", "source_old_schedule_sha256",
        "run_id", "runs_root", "logical_cell_count", "maximum_physical_attempts",
        "same_seed_retry_limit", "records",
    }
    if not isinstance(document, dict) or set(document) != expected or document.get("block") not in BLOCKS:
        raise FocusedRecoveryError("recovery schedule schema drifted")
    block = document["block"]; spec = RUN_SPECS[block]
    if (
        document["schema_version"] != SCHEDULE_SCHEMA
        or document["run_id"] != spec["run_id"]
        or document["runs_root"] != spec["runs_root_relative"]
        or document["logical_cell_count"] != spec["logical_cells"]
        or len(document["records"]) != spec["logical_cells"]
        or document["maximum_physical_attempts"] != spec["maximum_physical_attempts"]
        or document["same_seed_retry_limit"] != 1
        or len({item.get("logical_cell_id") for item in document["records"]}) != len(document["records"])
    ):
        raise FocusedRecoveryError("recovery schedule contract drifted")
    if old_state is not None:
        source = old_state["schedules"]["B1b" if block == "B1b_recovery" else "B2"]
        expected_ids = (
            old_state["b1b_missing"] if block == "B1b_recovery"
            else {item["logical_cell_id"] for item in source["records"]}
        )
        if (
            document["source_old_schedule_sha256"] != _digest(source)
            or {item["logical_cell_id"] for item in document["records"]} != set(expected_ids)
        ):
            raise FocusedRecoveryError("recovery schedule old binding drifted")
    return document


def _source_digests(supervisor_path):
    supervisor = Path(supervisor_path).resolve()
    expected = (ROOT / "scripts" / "run-focused-recovery-successor.ps1").resolve()
    if supervisor != expected or not supervisor.is_file():
        raise FocusedRecoveryError("recovery supervisor path is not canonical")
    live_delta = _validate_live_implementation_delta()
    return {
        "implementation_sha256": _live._implementation_sha256(),
        "live_implementation_delta": live_delta,
        "transitive_source_digests": _transitive_source_digests(),
        "recovery_module": _file_digest(Path(__file__)),
        "recovery_protocol": _file_digest(PROTOCOL_PATH),
        "supervisor": _file_digest(supervisor),
        "supervisor_path": "scripts/run-focused-recovery-successor.ps1",
        "classifier_source": _file_digest(CLASSIFIER_SOURCE_PATH),
        "classifier_source_path": "harness/experiment.py",
        "parser_incident": _file_digest(PARSER_INCIDENT_PATH),
        "parser_incident_path": PARSER_INCIDENT_PATH.relative_to(ROOT).as_posix(),
        "projection_rewrite_incident": _file_digest(PROJECTION_REWRITE_PATH),
        "projection_rewrite_incident_path": PROJECTION_REWRITE_PATH.relative_to(ROOT).as_posix(),
        "release_verifier": _file_digest(RELEASE_VERIFIER_PATH),
        "release_verifier_path": RELEASE_VERIFIER_PATH.relative_to(ROOT).as_posix(),
    }


def _transitive_source_digests():
    paths = {
        "focused_followup": ROOT / "bench" / "focused_followup.py",
        "focused_protocol": OLD_PROTOCOL_PATH,
        "generator": ROOT / "domains" / "office_demo" / "generators_v2.py",
        "strict_graders": ROOT / "domains" / "office_demo" / "strict_graders.py",
        "office_files": ROOT / "domains" / "office_demo" / "office_files.py",
        "world": ROOT / "domains" / "office_demo" / "world.py",
        "contracts": ROOT / "domains" / "office_demo" / "contracts.py",
        "reviewed_grader": ROOT / "domains" / "office_demo" / "reviewed_grader_v2.py",
        "validated_outcomes_validator": ROOT / "bench" / "next_study_validated_outcomes.py",
        "validated_outcomes": _focused.VALIDATED_OUTCOMES_PATH,
        "manifest_lock": _focused.MANIFEST_DIRECTORY / "manifest-lock.json",
    }
    for split in ("calibration",) + _focused.NON_CALIBRATION_SPLITS:
        paths["manifest_" + split] = _focused.MANIFEST_DIRECTORY / (split + ".json")
    if any(not path.is_file() for path in paths.values()):
        raise FocusedRecoveryError("a transitive recovery source is missing")
    return {label: _file_digest(path) for label, path in sorted(paths.items())}


def _validate_live_implementation_delta():
    paths = tuple(_live._LIVE_IMPLEMENTATION_PATHS)
    old = {
        relative: hashlib.sha256(_git_blob_bytes("v0.13.5", relative)).hexdigest()
        for relative in paths
    }
    current = {
        relative: hashlib.sha256(
            (ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        for relative in paths
    }
    changed = sorted(relative for relative in paths if current[relative] != old[relative])
    if changed != ["harness/experiment.py"]:
        raise FocusedRecoveryError("live implementation delta is not classifier-source-only")
    _validate_classifier_semantics()
    return {
        "base_tag": "v0.13.5", "changed_paths": changed,
        "normalization": "compare Git blob LF bytes to working bytes with CRLF normalized to LF",
        "old_path_digests": old, "current_path_digests": current,
        "current_implementation_sha256": _live._implementation_sha256(),
    }


def _validate_source_bindings(expected, supervisor_path):
    current = _source_digests(supervisor_path)
    if current != expected:
        raise FocusedRecoveryError("recovery source binding drifted")
    return current


def _authorization_repo_snapshot(commit_sha, supervisor_path):
    if _git("rev-parse", "HEAD") != commit_sha:
        raise FocusedRecoveryError("authorization HEAD differs from fresh preflight")
    if _git("status", "--porcelain", "--untracked-files=all"):
        raise FocusedRecoveryError("authorization requires a clean worktree")
    tag = _focused._annotated_tag_binding("v0.13.6", commit_sha)
    return {"head": commit_sha, "tag_object_sha": tag["tag_object_sha"],
            "source_digests": _source_digests(supervisor_path)}


def build_authorization(preflight, issued_at, issuer, supervisor_path, protocol=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    _timestamp(issued_at, "authorization issue time")
    if not isinstance(issuer, str) or not issuer.strip():
        raise FocusedRecoveryError("authorization issuer is empty")
    preflight = _focused._validate_preflight_for_authorization(preflight)
    snapshot_before = _authorization_repo_snapshot(preflight["commit_sha"], supervisor_path)
    # Authorization is score-blind: only exact attempt topology is materialized.
    old_state = _old_topology_state(protocol)
    old_authorization = old_state["authorization"]
    for field in (
        "host_fingerprint", "model_digests", "validated_outcomes_sha256", "tool_schema_sha256",
    ):
        if preflight[field] != old_authorization[field]:
            raise FocusedRecoveryError("fresh preflight differs from old frozen runtime: " + field)
    old_runtime = old_authorization["runtime_fingerprint"]["details"]
    current_runtime = preflight["runtime_fingerprint"]["details"]
    expected_runtime = dict(old_runtime)
    expected_runtime["implementation_sha256"] = _live._implementation_sha256()
    if current_runtime != expected_runtime:
        raise FocusedRecoveryError("fresh runtime differs beyond the authorized classifier-only delta")
    current = preflight["commit_sha"]
    tag = {"tag_object_sha": snapshot_before["tag_object_sha"]}
    schedules = {block: build_schedule(block, protocol, old_state) for block in BLOCKS}
    classifier = _validate_classifier_semantics()
    tree = _old_tree_manifest()
    document = {
        "schema_version": AUTHORIZATION_SCHEMA, "status": "authorized",
        "protocol_sha256": protocol_sha256(protocol), "tag": "v0.13.6",
        "tag_object_sha": tag["tag_object_sha"], "commit_sha": current,
        "issued_at": issued_at, "issuer": issuer.strip(),
        "preflight_sha256": preflight["preflight_sha256"],
        "host_fingerprint": preflight["host_fingerprint"],
        "runtime_fingerprint": preflight["runtime_fingerprint"],
        "model_digests": preflight["model_digests"],
        "validated_outcomes_sha256": preflight["validated_outcomes_sha256"],
        "tool_schema_sha256": preflight["tool_schema_sha256"],
        "old_bindings": copy.deepcopy(protocol["old_bindings"]),
        "old_tree_manifest": tree,
        "classifier_binding": classifier,
        "parser_incident_sha256": _file_digest(PARSER_INCIDENT_PATH),
        "projection_rewrite_incident_sha256": _file_digest(PROJECTION_REWRITE_PATH),
        "source_digests": snapshot_before["source_digests"],
        "schedule_digests": {block: _digest(schedule) for block, schedule in schedules.items()},
        "run_specs": {
            block: {
                "run_id": spec["run_id"], "runs_root": spec["runs_root_relative"],
                "logical_cells": spec["logical_cells"],
                "maximum_physical_attempts": spec["maximum_physical_attempts"],
            }
            for block, spec in RUN_SPECS.items()
        },
        "maximum_logical_cells": 264, "maximum_physical_attempts": 528,
        "same_seed_retry_limit": 1, "analysis_embargo": "both_blocks_terminal",
    }
    document["authorization_sha256"] = _digest(document)
    validated = validate_authorization(document, protocol, old_state=old_state)
    if _authorization_repo_snapshot(current, supervisor_path) != snapshot_before:
        raise FocusedRecoveryError("repository changed during authorization construction")
    return validated


def validate_authorization(document, protocol=None, old_state=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    expected = {
        "schema_version", "status", "protocol_sha256", "tag", "tag_object_sha",
        "commit_sha", "issued_at", "issuer", "preflight_sha256", "host_fingerprint",
        "runtime_fingerprint", "model_digests", "validated_outcomes_sha256",
        "tool_schema_sha256", "old_bindings", "old_tree_manifest", "classifier_binding",
        "parser_incident_sha256", "projection_rewrite_incident_sha256", "source_digests", "schedule_digests", "run_specs",
        "maximum_logical_cells", "maximum_physical_attempts", "same_seed_retry_limit",
        "analysis_embargo", "authorization_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise FocusedRecoveryError("recovery authorization schema drifted")
    unsigned = dict(document); supplied = unsigned.pop("authorization_sha256")
    if supplied != _digest(unsigned):
        raise FocusedRecoveryError("recovery authorization digest drifted")
    if (
        document["schema_version"] != AUTHORIZATION_SCHEMA or document["status"] != "authorized"
        or document["protocol_sha256"] != protocol_sha256(protocol)
        or document["tag"] != "v0.13.6" or document["old_bindings"] != protocol["old_bindings"]
        or document["maximum_logical_cells"] != 264
        or document["maximum_physical_attempts"] != 528
        or document["same_seed_retry_limit"] != 1
        or document["analysis_embargo"] != "both_blocks_terminal"
        or set(document["schedule_digests"]) != set(BLOCKS)
        or document["schedule_digests"] != {
            block: protocol["execution"]["blocks"][block]["schedule_sha256"]
            for block in BLOCKS
        }
    ):
        raise FocusedRecoveryError("recovery authorization contract drifted")
    _require_sha1(document["tag_object_sha"], "tag object")
    _require_sha1(document["commit_sha"], "commit")
    _timestamp(document["issued_at"], "authorization issue time")
    for field in ("preflight_sha256", "validated_outcomes_sha256", "tool_schema_sha256", "parser_incident_sha256", "projection_rewrite_incident_sha256"):
        _require_sha256(document[field], field)
    tree = document["old_tree_manifest"]
    if (
        not isinstance(tree, dict) or set(tree) != {"files", "tree_sha256"}
        or type(tree["files"]) is not int or tree["files"] < 1
    ):
        raise FocusedRecoveryError("old evidence tree manifest schema drifted")
    _require_sha256(tree["tree_sha256"], "old evidence tree")
    if document["classifier_binding"] != {
        "classifier_version": CLASSIFIER_VERSION,
        "classifier_source_sha256": document["source_digests"]["classifier_source"],
        "observed_signature_recognized": True,
        "failure_origin": "model", "retryable": False, "strict_success": False,
    }:
        raise FocusedRecoveryError("recovery classifier binding drifted")
    source_keys = {
        "implementation_sha256", "live_implementation_delta", "transitive_source_digests", "recovery_module",
        "recovery_protocol", "supervisor", "supervisor_path", "classifier_source",
        "classifier_source_path", "parser_incident", "parser_incident_path",
        "projection_rewrite_incident", "projection_rewrite_incident_path",
        "release_verifier", "release_verifier_path",
    }
    if not isinstance(document["source_digests"], dict) or set(document["source_digests"]) != source_keys:
        raise FocusedRecoveryError("recovery source digest schema drifted")
    for key in (
        "implementation_sha256", "recovery_module", "recovery_protocol", "supervisor",
        "classifier_source", "parser_incident", "projection_rewrite_incident",
        "release_verifier",
    ):
        _require_sha256(document["source_digests"][key], "source " + key)
    transitive = document["source_digests"]["transitive_source_digests"]
    if not isinstance(transitive, dict) or set(transitive) != set(_transitive_source_digests()):
        raise FocusedRecoveryError("transitive source digest schema drifted")
    for label, digest in transitive.items():
        _require_sha256(digest, "transitive source " + label)
    if document["parser_incident_sha256"] != document["source_digests"]["parser_incident"]:
        raise FocusedRecoveryError("parser incident authorization bindings disagree")
    if document["projection_rewrite_incident_sha256"] != document["source_digests"]["projection_rewrite_incident"]:
        raise FocusedRecoveryError("projection incident authorization bindings disagree")
    expected_specs = {
        block: {
            "run_id": spec["run_id"], "runs_root": spec["runs_root_relative"],
            "logical_cells": spec["logical_cells"],
            "maximum_physical_attempts": spec["maximum_physical_attempts"],
        }
        for block, spec in RUN_SPECS.items()
    }
    if document["run_specs"] != expected_specs:
        raise FocusedRecoveryError("recovery fixed run specs drifted")
    if old_state is not None:
        for block in BLOCKS:
            if document["schedule_digests"][block] != _digest(build_schedule(block, protocol, old_state)):
                raise FocusedRecoveryError("authorized recovery schedule drifted")
    return document


def _validate_repository_bindings(authorization, supervisor_path=None):
    validate_authorization(authorization)
    _validate_old_bindings(load_protocol())
    if _old_tree_manifest() != authorization["old_tree_manifest"]:
        raise FocusedRecoveryError("old evidence tree changed after authorization")
    tag = _focused._annotated_tag_binding("v0.13.6", authorization["commit_sha"])
    if tag["tag_object_sha"] != authorization["tag_object_sha"] or _git("rev-parse", "HEAD") != authorization["commit_sha"]:
        raise FocusedRecoveryError("recovery tag or HEAD binding drifted")
    if _git("status", "--porcelain", "--untracked-files=all"):
        raise FocusedRecoveryError("recovery execution requires a clean worktree")
    if supervisor_path is None:
        supervisor_path = ROOT / authorization["source_digests"]["supervisor_path"]
    _validate_source_bindings(authorization["source_digests"], supervisor_path)
    if _validate_classifier_semantics() != authorization["classifier_binding"]:
        raise FocusedRecoveryError("current classifier differs from authorization")
    if _file_digest(PARSER_INCIDENT_PATH) != authorization["parser_incident_sha256"]:
        raise FocusedRecoveryError("parser incident artifact differs from authorization")
    if _file_digest(PROJECTION_REWRITE_PATH) != authorization["projection_rewrite_incident_sha256"]:
        raise FocusedRecoveryError("projection incident artifact differs from authorization")
    return authorization


def validate_current_environment(authorization, preflight=None, supervisor_path=None, preflight_provider=None):
    _validate_repository_bindings(authorization, supervisor_path)
    provider = preflight_provider or (lambda: _live.collect_native_preflight(require_clean=True))
    current = _focused._validate_preflight_for_authorization(provider())
    if preflight is not None and preflight != current:
        raise FocusedRecoveryError("caller preflight differs from fresh preflight")
    for field in (
        "preflight_sha256", "host_fingerprint", "runtime_fingerprint", "model_digests",
        "validated_outcomes_sha256", "tool_schema_sha256",
    ):
        if current[field] != authorization[field]:
            raise FocusedRecoveryError("fresh environment differs from authorization: " + field)
    if current["commit_sha"] != authorization["commit_sha"]:
        raise FocusedRecoveryError("fresh environment commit differs from authorization")
    return current


def _artifact_path(block, authorization, kind):
    if block not in BLOCKS or kind not in ("starts", "seals", "terminations"):
        raise FocusedRecoveryError("unknown recovery artifact coordinate")
    return (
        RUN_SPECS[block]["runs_root"] / ("focused-recovery-" + kind)
        / authorization["authorization_sha256"] / (block + ".json")
    )


def _cell_start_path(block, authorization, logical_cell_id):
    _require_sha256(logical_cell_id, "logical cell id")
    return (
        RUN_SPECS[block]["runs_root"] / "focused-recovery-cell-starts"
        / authorization["authorization_sha256"] / block / (logical_cell_id + ".json")
    )


def _analysis_path(authorization):
    return SUCCESSOR_ROOT / "analysis" / authorization["authorization_sha256"] / "analysis.json"


def _report_path(authorization):
    return SUCCESSOR_ROOT / "reports" / authorization["authorization_sha256"] / "report.json"


def _release_paths(authorization):
    root = SUCCESSOR_ROOT / "release" / authorization["authorization_sha256"]
    return {
        "archive": root / "archive.json",
        "manifest": root / "manifest.json",
        "verification": root / "independent-verification.json",
    }


def _run_metadata(authorization, block):
    spec = RUN_SPECS[block]
    return {
        "schema_version": RUN_METADATA_SCHEMA, "block": block,
        "run_id": spec["run_id"], "runs_root": spec["runs_root_relative"],
        "authorization_sha256": authorization["authorization_sha256"],
        "protocol_sha256": authorization["protocol_sha256"],
        "schedule_sha256": authorization["schedule_digests"][block],
        "commit_sha": authorization["commit_sha"], "preflight_sha256": authorization["preflight_sha256"],
        "score_masked_console": True,
    }


def _open_or_create_store(authorization, block):
    spec = RUN_SPECS[block]
    _assert_not_old_path(spec["runs_root"])
    return EvidenceStore.create_run(spec["runs_root"], spec["run_id"], _run_metadata(authorization, block))


def _open_store(authorization, block):
    spec = RUN_SPECS[block]
    store = EvidenceStore.open_run(spec["runs_root"], spec["run_id"])
    if store.run_document.get("metadata") != _run_metadata(authorization, block):
        raise FocusedRecoveryError("recovery EvidenceStore metadata drifted")
    return store


def load_block_start(authorization, block, schedule, _document=None):
    document = (_load_published(_artifact_path(block, authorization, "starts"), "recovery block start")
                if _document is None else _document)
    unsigned = dict(document); supplied = unsigned.pop("start_sha256", None)
    store = _open_store(authorization, block)
    expected = {
        "schema_version", "authorization_sha256", "block", "run_id", "run_sha256",
        "schedule_sha256", "logical_cells_expected", "maximum_physical_attempts",
        "started_at", "scores_exposed", "start_sha256",
    }
    if (
        set(document) != expected
        or supplied != _digest(unsigned) or document.get("schema_version") != BLOCK_START_SCHEMA
        or document.get("authorization_sha256") != authorization["authorization_sha256"]
        or document.get("block") != block or document.get("run_id") != store.run_id
        or document.get("run_sha256") != store.run_sha256
        or document.get("schedule_sha256") != _digest(schedule)
        or document.get("logical_cells_expected") != schedule["logical_cell_count"]
        or document.get("maximum_physical_attempts") != schedule["maximum_physical_attempts"]
        or document.get("scores_exposed") is not False
    ):
        raise FocusedRecoveryError("recovery block start differs from exact run binding")
    _timestamp(document.get("started_at"), "block start time")
    if _timestamp(document["started_at"], "block start time") < _timestamp(authorization["issued_at"], "authorization time"):
        raise FocusedRecoveryError("block start predates authorization")
    if block == "B2_repeatability":
        predecessor = None
        for kind, field in (("seals", "block_finished_at"), ("terminations", "terminated_at")):
            path = _artifact_path("B1b_recovery", authorization, kind)
            marker = path.with_name(path.name + ".complete")
            if path.is_file() and marker.is_file() and marker.stat().st_size == 0:
                if predecessor is not None:
                    raise FocusedRecoveryError("B1b recovery has conflicting terminals")
                predecessor = _load_published(path, "B1b predecessor terminal").get(field)
        if predecessor is None or _timestamp(document["started_at"], "B2 start") < _timestamp(predecessor, "B1 terminal"):
            raise FocusedRecoveryError("B2 start predates B1b terminal disposition")
    return document


def load_cell_start(authorization, block, schedule, cell, _document=None):
    path = _cell_start_path(block, authorization, cell["logical_cell_id"])
    document = (_load_published(path, "logical cell start") if _document is None else _document)
    unsigned = dict(document); supplied = unsigned.pop("cell_start_sha256", None)
    start = load_block_start(authorization, block, schedule)
    expected = {
        "schema_version", "authorization_sha256", "block", "run_id", "run_sha256",
        "schedule_sha256", "block_start_sha256", "logical_cell_id", "instance_id",
        "condition", "trial_index", "trial_seed", "started_at", "scores_exposed",
        "cell_start_sha256",
    }
    store = _open_store(authorization, block)
    if (
        not isinstance(document, dict) or set(document) != expected
        or supplied != _digest(unsigned)
        or document["schema_version"] != CELL_START_SCHEMA
        or document["authorization_sha256"] != authorization["authorization_sha256"]
        or document["block"] != block or document["run_id"] != store.run_id
        or document["run_sha256"] != store.run_sha256
        or document["schedule_sha256"] != _digest(schedule)
        or document["block_start_sha256"] != start["start_sha256"]
        or document["logical_cell_id"] != cell["logical_cell_id"]
        or document["instance_id"] != cell["instance_id"]
        or document["condition"] != cell["condition"]
        or document["trial_index"] != cell["trial_index"]
        or document["trial_seed"] != cell["trial_seed"]
        or document["scores_exposed"] is not False
    ):
        raise FocusedRecoveryError("logical cell start differs from exact schedule binding")
    if _timestamp(document["started_at"], "logical cell start time") < _timestamp(start["started_at"], "block start time"):
        raise FocusedRecoveryError("logical cell start precedes block start")
    return document


def _publish_or_recover_cell_start(authorization, block, schedule, cell, started_at):
    path = _cell_start_path(block, authorization, cell["logical_cell_id"])
    marker = path.with_name(path.name + ".complete")
    if marker.exists() and not path.is_file():
        raise FocusedRecoveryError("logical-cell marker exists without JSON")
    if path.is_file():
        document = _load_document(path, "logical cell start")
        load_cell_start(authorization, block, schedule, cell, document)
    else:
        store = _open_store(authorization, block)
        block_start = load_block_start(authorization, block, schedule)
        document = {
            "schema_version": CELL_START_SCHEMA,
            "authorization_sha256": authorization["authorization_sha256"],
            "block": block, "run_id": store.run_id, "run_sha256": store.run_sha256,
            "schedule_sha256": _digest(schedule), "block_start_sha256": block_start["start_sha256"],
            "logical_cell_id": cell["logical_cell_id"], "instance_id": cell["instance_id"],
            "condition": cell["condition"], "trial_index": cell["trial_index"],
            "trial_seed": cell["trial_seed"], "started_at": started_at,
            "scores_exposed": False,
        }
        document["cell_start_sha256"] = _digest(document)
    _publish_marker_last(
        path, document,
        validator=lambda item: load_cell_start(authorization, block, schedule, cell, item),
    )
    return document


def _cell_start_inventory(authorization, block, schedule):
    cells = {cell["logical_cell_id"]: cell for cell in schedule["records"]}
    root = (
        RUN_SPECS[block]["runs_root"] / "focused-recovery-cell-starts"
        / authorization["authorization_sha256"] / block
    )
    records = []
    if root.exists():
        if root.is_symlink() or not root.is_dir():
            raise FocusedRecoveryError("logical-cell start root is irregular")
        for path in sorted(root.iterdir(), key=lambda item: item.name):
            if path.name.endswith(".json.complete"):
                json_path = path.with_name(path.name[:-9])
                if not json_path.is_file() or not path.is_file() or path.stat().st_size != 0:
                    raise FocusedRecoveryError("orphan or invalid logical-cell start marker")
                continue
            if path.suffix != ".json" or path.stem not in cells:
                raise FocusedRecoveryError("foreign logical-cell start artifact exists")
            document = load_cell_start(authorization, block, schedule, cells[path.stem])
            records.append({
                "logical_cell_id": path.stem,
                "cell_start_sha256": document["cell_start_sha256"],
                "file_sha256": _file_digest(path),
            })
    return {
        "logical_cells_started": len(records), "records": records,
        "cell_start_records_sha256": _digest(records),
    }


def _validate_execution_inventory(authorization, block, schedule, final, terminal_reason=None):
    store = _open_store(authorization, block)
    physical = _physical_candidate_state(store, schedule, authorization)
    starts = _cell_start_inventory(authorization, block, schedule)
    attempted_cells = set(physical["by_cell"]) | set(final)
    started_cells = {item["logical_cell_id"] for item in starts["records"]}
    if not attempted_cells <= started_cells:
        raise FocusedRecoveryError("attempt evidence lacks its logical-cell start")
    if started_cells != attempted_cells and terminal_reason != "instrument_failure":
        raise FocusedRecoveryError("orphan logical-cell start requires instrument-failure disposition")
    incomplete_states = set(physical["state_counts"]) - {"committed"}
    if terminal_reason is None and incomplete_states:
        raise FocusedRecoveryError("complete-valid block contains uncommitted candidates")
    if incomplete_states and terminal_reason != "instrument_failure":
        raise FocusedRecoveryError("uncommitted candidates require instrument-failure disposition")
    return physical, starts


def _extract_new_attempts(store, schedule, authorization):
    schedule_by_cell = {cell["logical_cell_id"]: cell for cell in schedule["records"]}
    schedule_by_coordinate = {
        (cell["instance_id"], cell["condition"], cell["trial_seed"], cell["trial_index"]): cell
        for cell in schedule["records"]
    }
    records = []
    seen = set()
    instances = _focused._instances_by_id()
    candidates = _physical_candidate_state(store, schedule, authorization)
    projection = store.read_committed()
    for committed in projection.get("records", []):
        record = _focused._attempt_record_from_committed(
            committed, store, schedule_by_coordinate, schedule_by_cell, authorization, instances,
        )
        if record is None:
            raise FocusedRecoveryError("new recovery run contains a foreign attempt")
        identity = (record["logical_cell_id"], record["repeat"])
        if identity in seen:
            raise FocusedRecoveryError("new recovery run contains a duplicate attempt")
        seen.add(identity); records.append(record)
    if len(records) > schedule["maximum_physical_attempts"]:
        raise FocusedRecoveryError("new recovery physical-attempt ceiling exceeded")
    if len(records) > candidates["physical_candidates"]:
        raise FocusedRecoveryError("committed projection exceeds physical candidate topology")
    return sorted(records, key=lambda item: (item["logical_cell_id"], item["repeat"]))


def _new_final(store, schedule, authorization):
    attempts = _extract_new_attempts(store, schedule, authorization)
    final, missing, invalid = _focused._final_attempts(
        schedule, attempts, authorization, store.runs_root, store.run_id,
    )
    return attempts, final, missing, invalid


def _cell_resume_disposition(attempts, logical_cell_id):
    records = sorted(
        (item for item in attempts if item["logical_cell_id"] == logical_cell_id),
        key=lambda item: item["repeat"],
    )
    if not records:
        return "never_started", None
    last = records[-1]
    if last["failure_origin"] in ("none", "model"):
        return "complete_valid", None
    if len(records) == 1 and last["repeat"] == 0 and last["retryable"]:
        return "resume_authorized_retry", None
    reason = "instrument_failure" if last["failure_origin"] == "instrument" else "environment_failure"
    return "terminal_invalid", reason


def _must_check_hard_stop_before_cell(disposition, has_valid_cell_start):
    return disposition == "never_started" and not has_valid_cell_start


def _physical_candidate_state(store, schedule, authorization):
    instances = _focused._instances_by_id(); expected = {}; cells = defaultdict(list)
    for cell in schedule["records"]:
        for repeat in (0, 1):
            key = _focused._expected_attempt_key(
                instances[cell["instance_id"]], cell, authorization, repeat,
            )
            logical = AttemptKey.from_dict(key).logical_hash
            expected[logical] = (cell["logical_cell_id"], repeat)
    total = 0; details = defaultdict(list)
    for logical_dir in store.attempts_dir.iterdir():
        if logical_dir.is_symlink() or not logical_dir.is_dir() or logical_dir.name not in expected:
            raise FocusedRecoveryError("recovery run contains a foreign or irregular logical directory")
        cell_id, repeat = expected[logical_dir.name]
        for candidate in logical_dir.iterdir():
            if candidate.is_symlink() or not candidate.is_dir():
                raise FocusedRecoveryError("recovery run contains an irregular physical candidate")
            total += 1
            committed = (candidate / "COMMITTED").is_file()
            prepared = (candidate / "PREPARED.json").is_file()
            state = "committed" if committed else "prepared" if prepared else "abandoned"
            members = []
            for member in sorted(candidate.rglob("*"), key=lambda item: item.relative_to(candidate).as_posix()):
                if member.is_symlink():
                    raise FocusedRecoveryError("recovery candidate contains a symlink")
                if member.is_file():
                    members.append({
                        "path": member.relative_to(candidate).as_posix(),
                        "size": member.stat().st_size, "sha256": _file_digest(member),
                    })
            details[cell_id].append({
                "logical_hash": logical_dir.name, "physical_uuid": candidate.name,
                "repeat": repeat, "state": state, "candidate_tree_sha256": _digest(members),
            })
    if total > schedule["maximum_physical_attempts"]:
        raise FocusedRecoveryError("recovery physical candidate ceiling exceeded")
    if any(len(records) > 2 for records in details.values()):
        raise FocusedRecoveryError("recovery logical cell exceeds two physical candidates")
    records = [
        {"logical_cell_id": cell_id, **record}
        for cell_id in sorted(details)
        for record in sorted(details[cell_id], key=lambda item: (item["repeat"], item["physical_uuid"]))
    ]
    return {
        "physical_candidates": total, "by_cell": dict(details), "records": records,
        "candidate_records_sha256": _digest(records),
        "state_counts": dict(sorted(Counter(item["state"] for item in records).items())),
    }


def _seal_block(authorization, block, schedule, started_at, finished_at=None):
    store = _open_store(authorization, block)
    attempts, final, missing, invalid = _new_final(store, schedule, authorization)
    physical_inventory, start_inventory = _validate_execution_inventory(
        authorization, block, schedule, final,
    )
    physical = physical_inventory["physical_candidates"]
    if missing or invalid or len(final) != schedule["logical_cell_count"]:
        raise FocusedRecoveryError("recovery block cannot seal incomplete or invalid evidence")
    finished_at = finished_at or _utcnow()
    elapsed = int((_timestamp(finished_at, "finish") - _timestamp(started_at, "start")).total_seconds() * 1000)
    if elapsed < 0:
        raise FocusedRecoveryError("block finish precedes block start")
    start = load_block_start(authorization, block, schedule)
    if start["started_at"] != started_at:
        raise FocusedRecoveryError("block start timestamp linkage drifted")
    document = {
        "schema_version": BLOCK_SEAL_SCHEMA, "status": "sealed_complete_valid",
        "authorization_sha256": authorization["authorization_sha256"], "block": block,
        "run_id": store.run_id, "run_sha256": store.run_sha256,
        "schedule_sha256": _digest(schedule), "logical_cells_expected": schedule["logical_cell_count"],
        "logical_cells_complete": len(final), "instrument_invalid_cells": 0,
        "physical_attempts": physical, "attempt_records_sha256": _digest(attempts),
        "candidate_records_sha256": physical_inventory["candidate_records_sha256"],
        "candidate_state_counts": physical_inventory["state_counts"],
        "logical_cells_started": start_inventory["logical_cells_started"],
        "cell_start_records_sha256": start_inventory["cell_start_records_sha256"],
        "block_start_sha256": start["start_sha256"],
        "block_started_at": started_at, "block_finished_at": finished_at,
        "block_elapsed_ms": elapsed, "scores_exposed": False,
    }
    document["seal_sha256"] = _digest(document)
    _publish_marker_last(_artifact_path(block, authorization, "seals"), document)
    return document


def _terminate_block(authorization, block, schedule, reason, started_at, terminated_at=None):
    if reason not in ("environment_failure", "instrument_failure", "deadline"):
        raise FocusedRecoveryError("invalid recovery termination reason")
    store = _open_store(authorization, block)
    attempts, final, missing, invalid = _new_final(store, schedule, authorization)
    physical_inventory, start_inventory = _validate_execution_inventory(
        authorization, block, schedule, final, terminal_reason=reason,
    )
    physical = physical_inventory["physical_candidates"]
    terminated_at = terminated_at or _utcnow()
    if reason == "deadline" and (
        not missing or _timestamp(terminated_at, "termination time") < _timestamp(HARD_STOP, "hard stop")
    ):
        raise FocusedRecoveryError("deadline termination requires missing cells at/after hard stop")
    start = load_block_start(authorization, block, schedule)
    if start["started_at"] != started_at:
        raise FocusedRecoveryError("block start timestamp linkage drifted")
    elapsed = int((_timestamp(terminated_at, "termination time") - _timestamp(started_at, "start")).total_seconds() * 1000)
    if elapsed < 0:
        raise FocusedRecoveryError("termination precedes block start")
    document = {
        "schema_version": TERMINATION_SCHEMA, "status": "terminated_incomplete",
        "authorization_sha256": authorization["authorization_sha256"], "block": block,
        "run_id": store.run_id, "run_sha256": store.run_sha256,
        "schedule_sha256": _digest(schedule), "reason": reason,
        "logical_cells_expected": schedule["logical_cell_count"],
        "logical_cells_complete": len(final), "missing_cells": len(missing),
        "instrument_invalid_cells": len(invalid), "physical_attempts": physical,
        "attempt_records_sha256": _digest(attempts),
        "candidate_records_sha256": physical_inventory["candidate_records_sha256"],
        "candidate_state_counts": physical_inventory["state_counts"],
        "logical_cells_started": start_inventory["logical_cells_started"],
        "cell_start_records_sha256": start_inventory["cell_start_records_sha256"],
        "block_start_sha256": start["start_sha256"], "block_started_at": started_at,
        "terminated_at": terminated_at, "block_elapsed_ms": elapsed, "scores_exposed": False,
    }
    document["termination_sha256"] = _digest(document)
    _publish_marker_last(_artifact_path(block, authorization, "terminations"), document)
    return document


def load_block_seal(authorization, block, protocol=None, old_state=None, _document=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    validate_authorization(authorization, protocol, old_state=old_state)
    document = (_load_published(_artifact_path(block, authorization, "seals"), "recovery block seal")
                if _document is None else _document)
    unsigned = dict(document); supplied = unsigned.pop("seal_sha256", None)
    state = old_state if old_state is not None else _old_topology_state(protocol)
    schedule = build_schedule(block, protocol, state)
    store = _open_store(authorization, block)
    attempts, final, missing, invalid = _new_final(store, schedule, authorization)
    physical_inventory, start_inventory = _validate_execution_inventory(
        authorization, block, schedule, final,
    )
    physical = physical_inventory["physical_candidates"]
    start = load_block_start(authorization, block, schedule)
    expected = {
        "schema_version", "status", "authorization_sha256", "block", "run_id",
        "run_sha256", "schedule_sha256", "logical_cells_expected",
        "logical_cells_complete", "instrument_invalid_cells", "physical_attempts",
        "attempt_records_sha256", "candidate_records_sha256", "candidate_state_counts",
        "logical_cells_started", "cell_start_records_sha256",
        "block_start_sha256", "block_started_at",
        "block_finished_at", "block_elapsed_ms", "scores_exposed", "seal_sha256",
    }
    elapsed = int((_timestamp(document.get("block_finished_at"), "block finish") -
                   _timestamp(document.get("block_started_at"), "block start")).total_seconds() * 1000)
    if (
        set(document) != expected
        or supplied != _digest(unsigned) or document.get("schema_version") != BLOCK_SEAL_SCHEMA
        or document.get("status") != "sealed_complete_valid"
        or document.get("authorization_sha256") != authorization["authorization_sha256"]
        or document.get("block") != block or document.get("run_id") != store.run_id
        or document.get("run_sha256") != store.run_sha256
        or document.get("schedule_sha256") != _digest(schedule)
        or document.get("logical_cells_expected") != schedule["logical_cell_count"]
        or document.get("logical_cells_complete") != schedule["logical_cell_count"]
        or document.get("instrument_invalid_cells") != 0
        or document.get("physical_attempts") != physical
        or missing or invalid or len(final) != schedule["logical_cell_count"]
        or document.get("attempt_records_sha256") != _digest(attempts)
        or document.get("candidate_records_sha256") != physical_inventory["candidate_records_sha256"]
        or document.get("candidate_state_counts") != physical_inventory["state_counts"]
        or document.get("logical_cells_started") != start_inventory["logical_cells_started"]
        or document.get("cell_start_records_sha256") != start_inventory["cell_start_records_sha256"]
        or document.get("block_start_sha256") != start["start_sha256"]
        or document.get("block_started_at") != start["started_at"]
        or elapsed < 0 or document.get("block_elapsed_ms") != elapsed
        or document.get("scores_exposed") is not False
    ):
        raise FocusedRecoveryError("recovery block seal differs from exact evidence")
    return document


def _recover_partial_terminals(authorization, block, protocol, old_state):
    for kind in ("seals", "terminations"):
        path = _artifact_path(block, authorization, kind)
        marker = path.with_name(path.name + ".complete")
        if marker.exists() and not path.is_file():
            raise FocusedRecoveryError("terminal marker exists without its JSON artifact")
        if path.is_file() and not marker.exists():
            document = _load_document(path, "partial terminal artifact")
            validator = (
                lambda item: load_block_seal(authorization, block, protocol, old_state, item)
                if kind == "seals" else
                lambda item: load_termination(authorization, block, protocol, old_state, item)
            )
            _publish_marker_last(path, document, validator=validator)


def _terminal(authorization, block, protocol, old_state, recover_partial=False):
    if recover_partial:
        _recover_partial_terminals(authorization, block, protocol, old_state)
    seal_path = _artifact_path(block, authorization, "seals")
    term_path = _artifact_path(block, authorization, "terminations")
    seal_exists = seal_path.is_file() and seal_path.with_name(seal_path.name + ".complete").is_file()
    term_exists = term_path.is_file() and term_path.with_name(term_path.name + ".complete").is_file()
    if seal_exists and term_exists:
        raise FocusedRecoveryError("recovery block has conflicting terminal artifacts")
    if seal_exists:
        return "sealed", load_block_seal(authorization, block, protocol, old_state)
    if term_exists:
        return "terminated", load_termination(authorization, block, protocol, old_state)
    return None, None


def _terminal_marker_present(authorization, block):
    """Score-free marker check used to enforce the two-block analysis embargo."""

    states = []
    for kind in ("seals", "terminations"):
        path = _artifact_path(block, authorization, kind)
        marker = path.with_name(path.name + ".complete")
        if path.exists() != marker.exists():
            raise FocusedRecoveryError("recovery block has a partial terminal publication")
        if path.exists():
            if not path.is_file() or not marker.is_file() or marker.stat().st_size != 0:
                raise FocusedRecoveryError("recovery block has an invalid terminal marker")
            states.append(kind)
    if len(states) > 1:
        raise FocusedRecoveryError("recovery block has conflicting terminal markers")
    return bool(states)


def load_termination(authorization, block, protocol=None, old_state=None, _document=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    state = old_state if old_state is not None else _old_topology_state(protocol)
    schedule = build_schedule(block, protocol, state)
    document = (_load_published(_artifact_path(block, authorization, "terminations"), "recovery termination")
                if _document is None else _document)
    unsigned = dict(document); supplied = unsigned.pop("termination_sha256", None)
    store = _open_store(authorization, block)
    attempts, final, missing, invalid = _new_final(store, schedule, authorization)
    reason = document.get("reason")
    physical_inventory, start_inventory = _validate_execution_inventory(
        authorization, block, schedule, final, terminal_reason=reason,
    )
    physical = physical_inventory["physical_candidates"]
    start = load_block_start(authorization, block, schedule)
    expected = {
        "schema_version", "status", "authorization_sha256", "block", "run_id",
        "run_sha256", "schedule_sha256", "reason", "logical_cells_expected",
        "logical_cells_complete", "missing_cells", "instrument_invalid_cells",
        "physical_attempts", "attempt_records_sha256", "block_start_sha256",
        "candidate_records_sha256", "candidate_state_counts", "logical_cells_started",
        "cell_start_records_sha256",
        "block_started_at", "terminated_at", "block_elapsed_ms", "scores_exposed",
        "termination_sha256",
    }
    elapsed = int((_timestamp(document.get("terminated_at"), "termination time") -
                   _timestamp(document.get("block_started_at"), "block start")).total_seconds() * 1000)
    if (
        set(document) != expected
        or supplied != _digest(unsigned) or document.get("schema_version") != TERMINATION_SCHEMA
        or document.get("status") != "terminated_incomplete"
        or document.get("authorization_sha256") != authorization["authorization_sha256"]
        or document.get("block") != block or document.get("run_id") != store.run_id
        or document.get("run_sha256") != store.run_sha256
        or document.get("schedule_sha256") != _digest(schedule)
        or document.get("logical_cells_expected") != schedule["logical_cell_count"]
        or document.get("logical_cells_complete") != len(final)
        or document.get("missing_cells") != len(missing)
        or document.get("instrument_invalid_cells") != len(invalid)
        or document.get("physical_attempts") != physical
        or document.get("attempt_records_sha256") != _digest(attempts)
        or document.get("candidate_records_sha256") != physical_inventory["candidate_records_sha256"]
        or document.get("candidate_state_counts") != physical_inventory["state_counts"]
        or document.get("logical_cells_started") != start_inventory["logical_cells_started"]
        or document.get("cell_start_records_sha256") != start_inventory["cell_start_records_sha256"]
        or document.get("block_start_sha256") != start["start_sha256"]
        or document.get("block_started_at") != start["started_at"]
        or elapsed < 0 or document.get("block_elapsed_ms") != elapsed
        or document.get("scores_exposed") is not False
    ):
        raise FocusedRecoveryError("recovery termination differs from exact evidence")
    _timestamp(document.get("terminated_at"), "termination time")
    if reason not in ("environment_failure", "instrument_failure", "deadline"):
        raise FocusedRecoveryError("recovery termination reason drifted")
    invalid_records = [final[item] for item in invalid]
    if reason == "environment_failure" and (
        len(invalid_records) != 1 or invalid_records[0]["failure_origin"] != "environment"
    ):
        raise FocusedRecoveryError("environment termination differs from terminal evidence")
    if reason == "instrument_failure" and not (
        any(item["failure_origin"] == "instrument" for item in invalid_records)
        or set(physical_inventory["state_counts"]) - {"committed"}
        or start_inventory["logical_cells_started"] > len(physical_inventory["by_cell"])
    ):
        raise FocusedRecoveryError("instrument termination differs from terminal evidence")
    if reason == "deadline" and (
        not missing or invalid
        or _timestamp(document["terminated_at"], "termination time") < _timestamp(HARD_STOP, "hard stop")
    ):
        raise FocusedRecoveryError("deadline termination evidence is inconsistent")
    return document


def run_block(
    authorization, block, supervisor_path, preflight=None, preflight_provider=None,
    lease_path=None, protocol=None, now_provider=None,
):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    validate_authorization(authorization, protocol)
    if block not in BLOCKS:
        raise FocusedRecoveryError("unknown recovery block")
    if _analysis_path(authorization).exists() or _analysis_path(authorization).with_name("analysis.json.complete").exists():
        raise FocusedRecoveryError("analysis is already sealed; execution is closed")
    old_state = _old_topology_state(protocol)
    if block == "B2_repeatability":
        predecessor_state, _predecessor = _terminal(
            authorization, "B1b_recovery", protocol, old_state,
        )
        if predecessor_state is None:
            raise FocusedRecoveryError("B2 repeatability requires a validated terminal B1b recovery disposition")
    state, artifact = _terminal(authorization, block, protocol, old_state)
    # Never act on this pre-lease observation.  It exists only to fail closed
    # on malformed terminal evidence; the authoritative check is under lease.
    before = _old_tree_manifest()
    if before != authorization["old_tree_manifest"]:
        raise FocusedRecoveryError("old evidence changed before recovery execution")
    now_fn = now_provider or _utcnow
    lease = BenchmarkLease(lease_path)
    lease.acquire(authorization["authorization_sha256"])
    try:
        # The pre-lease view is advisory.  A competing supervisor may have
        # completed while this process waited, so terminal state is rederived
        # under the machine-wide lease before any preflight or run mutation.
        state, artifact = _terminal(
            authorization, block, protocol, old_state, recover_partial=True,
        )
        if state is not None:
            return artifact
        if block == "B2_repeatability":
            predecessor_state, _predecessor = _terminal(
                authorization, "B1b_recovery", protocol, old_state, recover_partial=True,
            )
            if predecessor_state is None:
                raise FocusedRecoveryError("B2 repeatability requires a validated terminal B1b recovery disposition")
        current = validate_current_environment(
            authorization, preflight, supervisor_path, preflight_provider,
        )
        schedule = build_schedule(block, protocol, old_state)
        if _digest(schedule) != authorization["schedule_digests"][block]:
            raise FocusedRecoveryError("live recovery schedule differs from authorization")
        store = _open_or_create_store(authorization, block)
        started_at = now_fn()
        start = {
            "schema_version": BLOCK_START_SCHEMA,
            "authorization_sha256": authorization["authorization_sha256"],
            "block": block, "run_id": store.run_id, "run_sha256": store.run_sha256,
            "schedule_sha256": _digest(schedule),
            "logical_cells_expected": schedule["logical_cell_count"],
            "maximum_physical_attempts": schedule["maximum_physical_attempts"],
            "started_at": started_at,
            "scores_exposed": False,
        }
        start["start_sha256"] = _digest(start)
        start_path = _artifact_path(block, authorization, "starts")
        marker = start_path.with_name(start_path.name + ".complete")
        if not start_path.exists() and not marker.exists():
            _publish_marker_last(start_path, start, validator=lambda item: load_block_start(
                authorization, block, schedule, item,
            ))
        elif start_path.is_file() and not marker.exists():
            partial = _load_document(start_path, "partial block start")
            load_block_start(authorization, block, schedule, partial)
            _publish_marker_last(start_path, partial, validator=lambda item: load_block_start(
                authorization, block, schedule, item,
            ))
            started_at = partial["started_at"]
        else:
            started_at = load_block_start(authorization, block, schedule)["started_at"]
        _cell_start_inventory(authorization, block, schedule)
        instances = _focused._instances_by_id(); outcomes = _focused._validated_outcomes()
        for cell in schedule["records"]:
            attempts, _final, _missing, _invalid = _new_final(store, schedule, authorization)
            disposition, terminal_reason = _cell_resume_disposition(
                attempts, cell["logical_cell_id"],
            )
            cell_start_path = _cell_start_path(block, authorization, cell["logical_cell_id"])
            cell_start_marker = cell_start_path.with_name(cell_start_path.name + ".complete")
            has_cell_start = cell_start_path.exists() or cell_start_marker.exists()
            if has_cell_start:
                _publish_or_recover_cell_start(
                    authorization, block, schedule, cell, now_fn(),
                )
            elif disposition != "never_started":
                raise FocusedRecoveryError("attempt evidence exists without its authorization-bound logical-cell start")
            if disposition == "complete_valid":
                continue
            if disposition == "terminal_invalid":
                return _terminate_block(
                    authorization, block, schedule, terminal_reason, started_at,
                )
            if not _must_check_hard_stop_before_cell(disposition, has_cell_start):
                # The authorization-bound logical cell already started: finish
                # repeat zero and, if eligible, its sole retry even past cutoff.
                pass
            else:
                current_time = now_fn()
                if _hard_stop_reached(current_time):
                    return _terminate_block(
                        authorization, block, schedule, "deadline", started_at,
                        terminated_at=current_time,
                    )
                _publish_or_recover_cell_start(
                    authorization, block, schedule, cell, current_time,
                )
            physical = _physical_candidate_state(store, schedule, authorization)
            cell_candidates = physical["by_cell"].get(cell["logical_cell_id"], [])
            if any(item["state"] == "abandoned" for item in cell_candidates):
                return _terminate_block(
                    authorization, block, schedule, "instrument_failure", started_at,
                )
            if len(cell_candidates) >= 2 and disposition not in ("complete_valid", "terminal_invalid"):
                raise FocusedRecoveryError("logical cell has no remaining authorized physical-candidate capacity")
            instance = instances.get(cell["instance_id"]); outcome = outcomes.get(cell["instance_id"])
            if instance is None or outcome is None or instance["content_sha256"] != cell["content_sha256"]:
                raise FocusedRecoveryError("scheduled instance or outcome binding drifted")
            _focused._execute_cell(store, authorization, current, cell, instance, outcome)
            _physical_candidate_state(store, schedule, authorization)
            attempts, final, _missing, invalid = _new_final(store, schedule, authorization)
            record = final.get(cell["logical_cell_id"])
            event = {
                "event": "cell_complete", "block": block,
                "logical_cell_id": cell["logical_cell_id"], "family": cell["family"],
                "instrument_valid": bool(record and record["failure_origin"] in ("none", "model")),
                "scores_exposed": False,
            }
            print(json.dumps(event, sort_keys=True), flush=True)
            if cell["logical_cell_id"] in invalid:
                reason = "instrument_failure" if record["failure_origin"] == "instrument" else "environment_failure"
                return _terminate_block(authorization, block, schedule, reason, started_at)
        # A transient postflight failure does not create an immutable terminal
        # disposition.  Complete attempt evidence remains resumable and a later
        # invocation can revalidate the environment and seal without rerunning.
        validate_current_environment(authorization, None, supervisor_path, preflight_provider)
        return _seal_block(authorization, block, schedule, started_at)
    finally:
        lease.release()
        if _old_tree_manifest() != before:
            raise FocusedRecoveryError("old v0.13.5 evidence changed during successor execution")


def _rows(final, schedule):
    cells = {cell["logical_cell_id"]: cell for cell in schedule["records"]}
    return [(final[cell_id], cells[cell_id]) for cell_id in sorted(cells)]


def _analyze(rows, label, protocol, trials, claim, seed_protocol_sha256=None):
    seed_protocol_sha256 = seed_protocol_sha256 or protocol_sha256(protocol)
    raw = _focused._analyze_paired_records(
        rows, label, _focused.load_protocol(), trials,
        bootstrap_builder=lambda differences: _focused._bootstrap_interval(
            differences, seed_protocol_sha256, label,
        ),
        issue_directional_claim=claim,
    )
    rendered = _focused._jsonify_analysis(raw)
    golden = BOOTSTRAP_INDEX_GOLDENS.get(label)
    if golden is not None and rendered["interval"]["first_100_index_vectors_sha256"] != golden:
        raise FocusedRecoveryError("bootstrap index-vector binding drifted for " + label)
    return rendered


def _repeatability_summary(trial0_rows, trial1_rows):
    indexed = defaultdict(dict)
    for record, cell in trial0_rows + trial1_rows:
        indexed[(cell["family"], cell["instance_id"], cell["condition"])][cell["trial_index"]] = record
    transitions = {condition: Counter() for condition in _focused.CONDITIONS}
    joint = Counter(); exact_joint = 0
    by_cluster = defaultdict(dict)
    for (family, instance_id, condition), trials in indexed.items():
        if set(trials) != {0, 1}:
            raise FocusedRecoveryError("repeatability join lacks a trial")
        pair = (bool(trials[0]["strict_success"]), bool(trials[1]["strict_success"]))
        transitions[condition][pair] += 1
        by_cluster[(family, instance_id)][condition] = pair
    for key, conditions in sorted(by_cluster.items()):
        if set(conditions) != set(_focused.CONDITIONS):
            raise FocusedRecoveryError("repeatability joint signature lacks a condition")
        t0 = tuple(conditions[condition][0] for condition in _focused.CONDITIONS)
        t1 = tuple(conditions[condition][1] for condition in _focused.CONDITIONS)
        joint[(t0, t1)] += 1
        exact_joint += t0 == t1
    def rendered(counter):
        return {
            "fail_to_fail": counter[(False, False)], "fail_to_success": counter[(False, True)],
            "success_to_fail": counter[(True, False)], "success_to_success": counter[(True, True)],
        }
    return {
        "clusters": len(by_cluster),
        "condition_transitions": {condition: rendered(counter) for condition, counter in transitions.items()},
        "exact_joint_outcome_signature_matches": exact_joint,
        "exact_joint_outcome_signature_rate": _focused._jsonify_analysis(Fraction(exact_joint, len(by_cluster))),
        "joint_signature_counts": [
            {"trial_0": list(key[0]), "trial_1": list(key[1]), "clusters": count}
            for key, count in sorted(joint.items(), key=lambda item: str(item[0]))
        ],
        "interpretation": "same-context trial repeatability only; not independent replication",
    }


def analyze(authorization, analyzed_at=None, protocol=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    validate_authorization(authorization, protocol)
    _validate_repository_bindings(authorization)
    if not all(_terminal_marker_present(authorization, block) for block in BLOCKS):
        raise FocusedRecoveryError("efficacy embargo remains: both successor blocks must be terminal")
    topology = _old_topology_state(protocol)
    terminals = {block: _terminal(authorization, block, protocol, topology) for block in BLOCKS}
    if any(state is None for state, _artifact in terminals.values()):
        raise FocusedRecoveryError("efficacy embargo remains: both successor blocks must be terminal")
    # Only after both score-free terminal markers and their evidence-derived
    # terminal documents validate may old/new efficacy be materialized.
    old_state = _old_efficacy_state(topology)
    analyzed_at = analyzed_at or _utcnow(); analyzed_time = _timestamp(analyzed_at, "analysis time")
    for _block, (_state, artifact) in terminals.items():
        terminal_time = artifact.get("block_finished_at", artifact.get("terminated_at"))
        if analyzed_time < _timestamp(terminal_time, "terminal time"):
            raise FocusedRecoveryError("analysis predates a successor terminal disposition")
    terminal_bindings = {
        block: artifact.get("seal_sha256", artifact.get("termination_sha256"))
        for block, (_state, artifact) in terminals.items()
    }
    terminal_dispositions = {}
    for block, (lane_state, artifact) in terminals.items():
        terminal_dispositions[block] = {
            "disposition": lane_state,
            "status": artifact["status"],
            "reason": artifact.get("reason"),
            "logical_cells_expected": artifact["logical_cells_expected"],
            "logical_cells_complete": artifact["logical_cells_complete"],
            "missing_cells": artifact.get("missing_cells", 0),
            "instrument_invalid_cells": artifact["instrument_invalid_cells"],
            "physical_attempts": artifact["physical_attempts"],
            "candidate_state_counts": artifact["candidate_state_counts"],
            "logical_cells_started": artifact["logical_cells_started"],
            "terminal_sha256": terminal_bindings[block],
        }
    recovery_complete = terminals["B1b_recovery"][0] == "sealed"
    b2_complete = terminals["B2_repeatability"][0] == "sealed"
    if recovery_complete and b2_complete:
        status = "sealed_complete_both_lanes"
    elif recovery_complete:
        status = "mixed_terminal_recovery_complete_repeatability_incomplete"
    elif b2_complete:
        status = "mixed_terminal_recovery_incomplete_repeatability_complete"
    else:
        status = "terminal_incomplete_no_complete_lane"
    b1a_rows = _rows(old_state["b1a_final"], old_state["schedules"]["B1a"])
    recovered_b1b = six = parser_provenance = None
    if recovery_complete:
        recovery_schedule = build_schedule("B1b_recovery", protocol, old_state)
        _attempts, recovery_final, missing, invalid = _new_final(
            _open_store(authorization, "B1b_recovery"), recovery_schedule, authorization,
        )
        if missing or invalid:
            raise FocusedRecoveryError("sealed recovery lane is not complete-valid")
        complete_b1b = dict(old_state["b1b_valid"])
        complete_b1b[PARSER_CELL_ID] = old_state["parser_derived"]
        if set(complete_b1b) & set(recovery_final):
            raise FocusedRecoveryError("recovery executed a previously started cell")
        complete_b1b.update(recovery_final)
        if len(complete_b1b) != 240:
            raise FocusedRecoveryError("recovered B1b does not contain exactly 240 terminal cells")
        b1b_rows = _rows(complete_b1b, old_state["schedules"]["B1b"])
        recovered_b1b = _analyze(b1b_rows, "recovered_B1b", protocol, (0,), False)
        recovered_b1b.update({
            "claim": None, "claim_applicable": False, "may_issue_or_alter_claim": False,
            "classification": "recovered_component_sensitivity_with_fixed_incident_adjudication",
            "composition": {
                "old_complete_valid_cells": 215,
                "old_parser_repeat0_derived_strict_false_cells": 1,
                "new_never_started_cells": 24,
                "total_cells": 240,
            },
        })
        old_digest = _focused.protocol_sha256(_focused.load_protocol())
        six = _analyze(b1a_rows + b1b_rows, "B1", protocol, (0,), False, old_digest)
        six.update({"claim": None, "claim_applicable": False, "may_issue_or_alter_claim": False,
                    "classification": "post-outcome_nonconfirmatory_six_family_sensitivity"})
        parser0, parser1 = old_state["parser_attempts"]
        parser_provenance = {
            "logical_cell_id": PARSER_CELL_ID, "classifier_version": CLASSIFIER_VERSION,
            "observed_error": OBSERVED_PARSER_ERROR,
            "repeat_0": {
                "evidence_sha256": parser0["evidence_sha256"],
                "original_failure_origin": parser0["failure_origin"],
                "derived_failure_origin": "model", "derived_retryable": False,
                "derived_strict_success": False, "included_in_efficacy": True,
            },
            "repeat_1": {
                "evidence_sha256": parser1["evidence_sha256"], "included_in_efficacy": False,
                "use": "provenance_and_operational_cost_only", "model_calls": parser1["model_calls"],
                "successful_reads": parser1["successful_reads"],
                "successful_mutations": parser1["successful_mutations"],
                "generated_tokens_exact": parser1["generated_tokens_exact"],
                "generated_tokens_lower_bound": parser1["generated_tokens_lower_bound"],
                "generated_tokens_upper_bound": parser1["generated_tokens_upper_bound"],
                "model_time_ms": parser1["model_time_ms"], "wall_time_ms": parser1["wall_time_ms"],
                "opportunity_budget_exhausted": parser1["opportunity_budget_exhausted"],
            },
            "parser_incident_sha256": authorization["parser_incident_sha256"],
        }
        parser_provenance["adjudication_influence_sensitivity"] = {
            "strict_false_assignment": "included as failure",
            "strict_true_alternate": "included as success",
            "recovered_B1b_maximum_delta": _focused._jsonify_analysis(Fraction(1, 120)),
            "recovered_B1b_maximum_percentage_points": "0.8333333333333333",
            "six_family_B1_maximum_delta": _focused._jsonify_analysis(Fraction(1, 240)),
            "six_family_B1_maximum_percentage_points": "0.4166666666666667",
            "gating": False, "claiming": False,
            "interpretation": "post-adjudication influence bound; separate from leave-one-family-out",
        }
    standalone = two_trial = None
    if b2_complete:
        repeat_schedule = build_schedule("B2_repeatability", protocol, old_state)
        _attempts, b2_final, missing, invalid = _new_final(
            _open_store(authorization, "B2_repeatability"), repeat_schedule, authorization,
        )
        if missing or invalid:
            raise FocusedRecoveryError("sealed repeatability lane is not complete-valid")
        b2_rows = _rows(b2_final, repeat_schedule)
        old_digest = _focused.protocol_sha256(_focused.load_protocol())
        standalone = _analyze(
            b2_rows, "B2_trial_1_descriptive", protocol, (1,), True, old_digest,
        )
        criterion = standalone.pop("claim")
        standalone.update({"standalone_repeatability_criterion_result": criterion,
                           "claim": None, "claim_applicable": False, "may_issue_or_alter_claim": False,
                           "classification": "same_context_repeatability_not_replication"})
        two_trial = _analyze(
            b1a_rows + b2_rows, "B2_two_trial", protocol, (0, 1), False, old_digest,
        )
        two_trial.update({"claim": None, "claim_applicable": False, "may_issue_or_alter_claim": False,
                          "classification": "secondary_two_trial_same_context"})
        standalone["repeatability"] = _repeatability_summary(b1a_rows, b2_rows)
    document = {
        "schema_version": ANALYSIS_SCHEMA, "status": status,
        "authorization_sha256": authorization["authorization_sha256"],
        "protocol_sha256": protocol_sha256(protocol), "terminal_bindings": terminal_bindings,
        "terminal_dispositions": terminal_dispositions,
        "recovered_B1b": recovered_b1b, "recovered_six_family_sensitivity": six,
        "standalone_repeatability": standalone, "b1a_two_trial_secondary": two_trial,
        "parser_incident_provenance": parser_provenance,
        "old_fallback_reference": {
            "report_sha256": old_state["old"]["report"]["report_sha256"],
            "analysis_sha256": old_state["old"]["closed_analysis"]["analysis_sha256"],
            "status": old_state["old"]["report"]["status"],
            "unchanged": True,
        },
        "pooling_headline_allowed": False, "analyzed_at": analyzed_at,
        "claim": None, "may_issue_or_alter_claim": False,
        "projection_rewrite_incident": {
            "sha256": authorization["projection_rewrite_incident_sha256"],
            "occurred_before_authorization": True,
            "results_bytes_changed": False,
            "corrective_status": "implemented_and_verified",
        },
    }
    document["analysis_sha256"] = _digest(document)
    return document


def validate_analysis(authorization, document, protocol=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    if not isinstance(document, dict) or document.get("schema_version") != ANALYSIS_SCHEMA:
        raise FocusedRecoveryError("recovery analysis schema drifted")
    rebuilt = analyze(authorization, document.get("analyzed_at"), protocol)
    if document != rebuilt:
        raise FocusedRecoveryError("recovery analysis differs from exact evidence rederivation")
    return document


def build_report(authorization, analysis, reported_at=None, protocol=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    validate_analysis(authorization, analysis, protocol)
    reported_at = reported_at or _utcnow(); reported_time = _timestamp(reported_at, "report time")
    if reported_time < _timestamp(analysis["analyzed_at"], "analysis time"):
        raise FocusedRecoveryError("report predates analysis")
    document = {
        "schema_version": REPORT_SCHEMA,
        "status": analysis["status"],
        "display_label": "v0.13.6-recovery-successor",
        "classification": protocol["classification"],
        "authorization_sha256": authorization["authorization_sha256"],
        "analysis_sha256": analysis["analysis_sha256"],
        "terminal_dispositions": analysis["terminal_dispositions"],
        "recovered_B1b": analysis["recovered_B1b"],
        "recovered_six_family_sensitivity": analysis["recovered_six_family_sensitivity"],
        "standalone_repeatability": analysis["standalone_repeatability"],
        "b1a_two_trial_secondary": analysis["b1a_two_trial_secondary"],
        "parser_incident_provenance": analysis["parser_incident_provenance"],
        "old_fallback_reference": analysis["old_fallback_reference"],
        "parser_incident_sha256": authorization["parser_incident_sha256"],
        "projection_rewrite_incident_sha256": authorization["projection_rewrite_incident_sha256"],
        "pooling_headline_allowed": False,
        "claim": None, "may_issue_or_alter_claim": False,
        "projection_rewrite_incident": analysis["projection_rewrite_incident"],
        "limitations": [
            "The six-family result is post-outcome nonconfirmatory sensitivity only.",
            "B2 repeats frozen task contexts and is repeatability evidence, not independent replication.",
            "The repeat-1 parser attempt is excluded from efficacy and retained only for provenance and operational cost.",
            "The immutable old sealed B1a fallback is the only completed prospective directional lane; every successor output is nonclaiming.",
            "Fixed synthetic benchmark only; no mechanism attribution or production validation.",
        ],
        "reported_at": reported_at,
    }
    document["report_sha256"] = _digest(document)
    return document


def validate_report(authorization, report, analysis, protocol=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    rebuilt = build_report(authorization, analysis, report.get("reported_at") if isinstance(report, dict) else None, protocol)
    if report != rebuilt:
        raise FocusedRecoveryError("recovery report differs from exact rederivation")
    return report


def _artifact_inventory_entry(path, semantic_field):
    document = _load_published(path, "release input")
    value = document.get(semantic_field)
    _require_sha256(value, "release input " + semantic_field)
    return {
        "path": Path(path).relative_to(ROOT).as_posix(),
        "file_sha256": _file_digest(path),
        semantic_field: value,
        "marker_last_verified": True,
    }


def build_release_archive(authorization, analysis, report, archived_at=None, protocol=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    validate_report(authorization, report, analysis, protocol)
    archived_at = archived_at or _utcnow(); archived_time = _timestamp(archived_at, "archive time")
    if archived_time < _timestamp(report["reported_at"], "report time"):
        raise FocusedRecoveryError("release archive predates report")
    terminals = {}
    topology = _old_topology_state(protocol)
    schedules = {block: build_schedule(block, protocol, topology) for block in BLOCKS}
    for block in BLOCKS:
        state, artifact = _terminal(authorization, block, protocol, topology)
        if state is None:
            raise FocusedRecoveryError("release requires both validated terminal dispositions")
        kind = "seals" if state == "sealed" else "terminations"
        field = "seal_sha256" if state == "sealed" else "termination_sha256"
        terminals[block] = {
            "disposition": state,
            **_artifact_inventory_entry(_artifact_path(block, authorization, kind), field),
        }
    document = {
        "schema_version": RELEASE_ARCHIVE_SCHEMA, "status": report["status"],
        "authorization": _artifact_inventory_entry(AUTHORIZATION_PATH, "authorization_sha256"),
        "terminal_artifacts": terminals,
        "schedules": schedules,
        "analysis": _artifact_inventory_entry(_analysis_path(authorization), "analysis_sha256"),
        "report": _artifact_inventory_entry(_report_path(authorization), "report_sha256"),
        "protocol": {"path": PROTOCOL_PATH.relative_to(ROOT).as_posix(),
                     "file_sha256": _file_digest(PROTOCOL_PATH),
                     "protocol_sha256": protocol_sha256(protocol)},
        "old_bindings": copy.deepcopy(protocol["old_bindings"]),
        "source_digests": copy.deepcopy(authorization["source_digests"]),
        "incident_audits": {
            "parser": authorization["parser_incident_sha256"],
            "preauthorization_projection_rewrite": authorization["projection_rewrite_incident_sha256"],
        },
        "terminal_dispositions": copy.deepcopy(analysis["terminal_dispositions"]),
        "claim": None, "may_issue_or_alter_claim": False,
        "archived_at": archived_at,
    }
    document["archive_sha256"] = _digest(document)
    return document


def validate_release_archive(authorization, document, analysis, report, protocol=None):
    if not isinstance(document, dict) or document.get("schema_version") != RELEASE_ARCHIVE_SCHEMA:
        raise FocusedRecoveryError("release archive schema drifted")
    rebuilt = build_release_archive(
        authorization, analysis, report, document.get("archived_at"), protocol,
    )
    if document != rebuilt:
        raise FocusedRecoveryError("release archive differs from exact artifact inventory")
    return document


def build_release_manifest(authorization, archive, analysis, report, manifested_at=None, protocol=None):
    validate_release_archive(authorization, archive, analysis, report, protocol)
    manifested_at = manifested_at or _utcnow(); manifested_time = _timestamp(manifested_at, "manifest time")
    if manifested_time < _timestamp(archive["archived_at"], "archive time"):
        raise FocusedRecoveryError("release manifest predates archive")
    document = {
        "schema_version": RELEASE_MANIFEST_SCHEMA, "status": report["status"],
        "authorization_sha256": authorization["authorization_sha256"],
        "archive_sha256": archive["archive_sha256"],
        "archive_file_sha256": _file_digest(_release_paths(authorization)["archive"]),
        "analysis_sha256": analysis["analysis_sha256"], "report_sha256": report["report_sha256"],
        "terminal_dispositions": copy.deepcopy(analysis["terminal_dispositions"]),
        "release_interpretation": "complete lanes reported independently; no partial lane analysis; no pooled headline",
        "claim": None, "may_issue_or_alter_claim": False,
        "manifested_at": manifested_at,
    }
    document["manifest_sha256"] = _digest(document)
    return document


def validate_release_manifest(authorization, document, archive, analysis, report, protocol=None):
    if not isinstance(document, dict) or document.get("schema_version") != RELEASE_MANIFEST_SCHEMA:
        raise FocusedRecoveryError("release manifest schema drifted")
    rebuilt = build_release_manifest(
        authorization, archive, analysis, report, document.get("manifested_at"), protocol,
    )
    if document != rebuilt:
        raise FocusedRecoveryError("release manifest differs from exact archive binding")
    return document


def _pid_definitively_dead(pid):
    if type(pid) is not int or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            # ERROR_INVALID_PARAMETER is Windows' definitive nonexistent-PID result.
            return ctypes.windll.kernel32.GetLastError() == 87
        try:
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value != 259  # STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except (PermissionError, OSError):
        return False
    return False


def _lease_recovery_path(authorization, lease_document):
    return (
        SUCCESSOR_ROOT / "lease-recovery" / authorization["authorization_sha256"]
        / (lease_document["lease_sha256"] + ".json")
    )


def recover_stale_lease(authorization, recovered_at=None, lease_path=None,
                        dead_pid_checker=None, before_unlink=None):
    canonical = BenchmarkLease().path.resolve()
    target = canonical if lease_path is None else Path(lease_path).resolve()
    if target != canonical:
        raise FocusedRecoveryError("stale lease recovery is restricted to the canonical machine lease")
    if not target.exists():
        return {"status": "lease_absent_noop", "lease_path": str(canonical)}
    try:
        initial_bytes = target.read_bytes(); initial = json.loads(initial_bytes)
        validate_lease(initial, authorization["authorization_sha256"], require_current_host=True)
    except Exception as exc:
        raise FocusedRecoveryError("canonical machine lease is corrupt or foreign") from exc
    if initial["host"] != socket.gethostname():
        raise FocusedRecoveryError("canonical machine lease belongs to another host")
    dead = dead_pid_checker or _pid_definitively_dead
    if not dead(initial["pid"]):
        raise FocusedRecoveryError("canonical machine lease PID is live or not definitively dead")
    initial_stat = target.stat()
    audit_path = _lease_recovery_path(authorization, initial)
    audit_marker = audit_path.with_name(audit_path.name + ".complete")
    if audit_marker.exists() and not audit_path.is_file():
        raise FocusedRecoveryError("lease recovery audit marker exists without JSON")
    existing_audit = _load_document(audit_path, "lease recovery audit") if audit_path.is_file() else None
    recovered_at = (
        existing_audit.get("recovered_at") if existing_audit is not None
        else recovered_at or _utcnow()
    )
    _timestamp(recovered_at, "lease recovery time")
    document = {
        "schema_version": LEASE_RECOVERY_SCHEMA, "status": "authorized_dead_pid_lease_recovery",
        "authorization_sha256": authorization["authorization_sha256"],
        "lease_path": str(canonical), "lease_sha256": initial["lease_sha256"],
        "host": initial["host"], "dead_pid": initial["pid"],
        "lease_file_sha256": hashlib.sha256(initial_bytes).hexdigest(),
        "recovered_at": recovered_at, "audit_published_before_unlink": True,
    }
    document["recovery_sha256"] = _digest(document)
    if existing_audit is not None and existing_audit != document:
        raise FocusedRecoveryError("existing lease recovery audit differs from exact stale lease")
    _publish_marker_last(audit_path, document)
    if before_unlink is not None:
        before_unlink()
    try:
        current_bytes = target.read_bytes(); current = json.loads(current_bytes)
        current_stat = target.stat()
        validate_lease(current, authorization["authorization_sha256"], require_current_host=True)
    except Exception as exc:
        raise FocusedRecoveryError("canonical lease changed during audited recovery") from exc
    stat_identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    if (
        current_bytes != initial_bytes or current != initial
        or stat_identity(current_stat) != stat_identity(initial_stat)
        or not dead(current["pid"])
    ):
        raise FocusedRecoveryError("canonical lease changed or revived during audited recovery")
    target.unlink()
    return document


def _load_document(path, label):
    try:
        return load_canonical_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise FocusedRecoveryError(label + " is unreadable") from exc


def _publish_generated(path, builder, validator):
    path = Path(path); marker = path.with_name(path.name + ".complete")
    if marker.exists() and not path.is_file():
        raise FocusedRecoveryError("marker exists without generated JSON artifact")
    if path.is_file():
        document = _load_document(path, "existing generated artifact")
        validator(document)
    else:
        document = builder()
        validator(document)
    _publish_marker_last(path, document, validator=validator)
    return document


def _cli_authorize(args):
    if Path(args.output).resolve() != AUTHORIZATION_PATH.resolve():
        raise FocusedRecoveryError("authorization output must be the fixed canonical path")
    document = build_authorization(
        _load_document(args.preflight, "preflight"), args.issued_at, args.issuer,
        args.supervisor_path,
    )
    before = _authorization_repo_snapshot(document["commit_sha"], args.supervisor_path)
    _publish_marker_last(
        AUTHORIZATION_PATH, document,
        validator=lambda item: validate_authorization(item),
    )
    after = _authorization_repo_snapshot(document["commit_sha"], args.supervisor_path)
    if before != after or before["source_digests"] != document["source_digests"]:
        raise FocusedRecoveryError("repository changed during authorization publication")
    print(json.dumps({"status": "authorized", "authorization_sha256": document["authorization_sha256"], "scores_exposed": False}, sort_keys=True))


def _cli_run(args):
    authorization = _load_published(AUTHORIZATION_PATH, "recovery authorization")
    document = run_block(
        authorization, args.block, args.supervisor_path,
        preflight=_load_document(args.preflight, "preflight") if args.preflight else None,
    )
    print(json.dumps({"status": document["status"], "block": args.block, "scores_exposed": False}, sort_keys=True))


def _cli_recover_stale_lease(_args):
    authorization = _load_published(AUTHORIZATION_PATH, "recovery authorization")
    _validate_repository_bindings(authorization)
    document = recover_stale_lease(authorization)
    print(json.dumps({"status": document["status"], "scores_exposed": False}, sort_keys=True))


def _cli_analyze(args):
    authorization = _load_published(AUTHORIZATION_PATH, "recovery authorization")
    expected = _analysis_path(authorization)
    if Path(args.output).resolve() != expected.resolve():
        raise FocusedRecoveryError("analysis output must be the canonical authorization-bound path")
    document = _publish_generated(
        expected, lambda: analyze(authorization),
        lambda item: validate_analysis(authorization, item),
    )
    print(json.dumps({"status": document["status"], "analysis_sha256": document["analysis_sha256"]}, sort_keys=True))


def _cli_report(args):
    authorization = _load_published(AUTHORIZATION_PATH, "recovery authorization")
    analysis = _load_published(_analysis_path(authorization), "recovery analysis")
    expected = _report_path(authorization)
    if Path(args.output).resolve() != expected.resolve():
        raise FocusedRecoveryError("report output must be the canonical authorization-bound path")
    document = _publish_generated(
        expected, lambda: build_report(authorization, analysis),
        lambda item: validate_report(authorization, item, analysis),
    )
    print(json.dumps({"status": document["status"], "report_sha256": document["report_sha256"]}, sort_keys=True))


def _cli_release(_args):
    authorization = _load_published(AUTHORIZATION_PATH, "recovery authorization")
    analysis = _load_published(_analysis_path(authorization), "recovery analysis")
    report = _load_published(_report_path(authorization), "recovery report")
    paths = _release_paths(authorization)
    archive = _publish_generated(
        paths["archive"], lambda: build_release_archive(authorization, analysis, report),
        lambda item: validate_release_archive(authorization, item, analysis, report),
    )
    manifest = _publish_generated(
        paths["manifest"], lambda: build_release_manifest(authorization, archive, analysis, report),
        lambda item: validate_release_manifest(authorization, item, archive, analysis, report),
    )
    print(json.dumps({"status": "archive_and_manifest_sealed_pending_independent_verification",
                      "archive_sha256": archive["archive_sha256"],
                      "manifest_sha256": manifest["manifest_sha256"]}, sort_keys=True))


def _cli_validate(args):
    authorization = _load_published(AUTHORIZATION_PATH, "recovery authorization")
    _validate_repository_bindings(authorization)
    if args.kind == "authorization":
        validate_authorization(authorization)
    elif args.kind == "block":
        if args.block is None:
            raise FocusedRecoveryError("block validation requires --block")
        old_state = _old_topology_state()
        state, _artifact = _terminal(authorization, args.block, load_protocol(), old_state)
        if state is None:
            raise FocusedRecoveryError("block has no validated terminal artifact")
    elif args.kind == "analysis":
        validate_analysis(authorization, _load_published(_analysis_path(authorization), "analysis"))
    elif args.kind == "report":
        analysis = _load_published(_analysis_path(authorization), "analysis")
        validate_report(authorization, _load_published(_report_path(authorization), "report"), analysis)
    else:
        analysis = _load_published(_analysis_path(authorization), "analysis")
        report = _load_published(_report_path(authorization), "report")
        paths = _release_paths(authorization)
        archive = _load_published(paths["archive"], "release archive")
        manifest = _load_published(paths["manifest"], "release manifest")
        validate_release_manifest(authorization, manifest, archive, analysis, report)
    print(json.dumps({"status": "valid", "kind": args.kind}, sort_keys=True))


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    authorize = commands.add_parser("authorize")
    authorize.add_argument("--preflight", required=True); authorize.add_argument("--output", required=True)
    authorize.add_argument("--issued-at", required=True); authorize.add_argument("--issuer", required=True)
    authorize.add_argument("--supervisor-path", required=True); authorize.set_defaults(handler=_cli_authorize)
    run = commands.add_parser("run-block")
    run.add_argument("--block", choices=BLOCKS, required=True); run.add_argument("--preflight")
    run.add_argument("--supervisor-path", required=True); run.set_defaults(handler=_cli_run)
    recover_lease = commands.add_parser("recover-stale-lease")
    recover_lease.set_defaults(handler=_cli_recover_stale_lease)
    analyze_cmd = commands.add_parser("analyze"); analyze_cmd.add_argument("--output", required=True)
    analyze_cmd.set_defaults(handler=_cli_analyze)
    report_cmd = commands.add_parser("report"); report_cmd.add_argument("--output", required=True)
    report_cmd.set_defaults(handler=_cli_report)
    release_cmd = commands.add_parser("release"); release_cmd.set_defaults(handler=_cli_release)
    validate_cmd = commands.add_parser("validate")
    validate_cmd.add_argument("--kind", choices=("authorization", "block", "analysis", "report", "release"), required=True)
    validate_cmd.add_argument("--block", choices=BLOCKS)
    validate_cmd.set_defaults(handler=_cli_validate)
    return parser


def main(argv=None):
    parser = build_parser(); args = parser.parse_args(argv)
    try:
        args.handler(args)
    except FocusedRecoveryError as exc:
        parser.exit(2, "focused recovery error: %s\n" % exc)


if __name__ == "__main__":
    main()
