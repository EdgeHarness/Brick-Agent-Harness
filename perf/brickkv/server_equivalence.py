"""Fail-closed reset-versus-managed comparison for GenieX server replays.

The comparator consumes only the secret-free evidence emitted by
``geniex_server_replay``. It never reads prompts or generated text. A passing
result proves one development replay produced identical completed outputs while
actually reducing prompt work on at least one managed cache hit. It does not
authorize a latency claim or complete the final benchmark.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import stat

from perf.brickkv.geniex_managed_smoke import (
    REVISION_PATTERN,
    SHA256_PATTERN,
    loopback_target,
)
from perf.brickkv.geniex_server_replay import (
    FORBIDDEN_EVIDENCE_KEYS,
    SCHEMA as REPLAY_SCHEMA,
    SMOKE_SOURCE_FILES,
    TRACE_ORDER,
    _trace_steps,
    expected_cache_decision,
)
from perf.brickkv.run_matrix import sha256_file, write_json_exclusive
from perf.brickkv.source_bundle import source_bundle_manifest, verify_git_revision


SCHEMA = "brickkv.server-equivalence/1"
MAX_EVIDENCE_BYTES = 32 * 1024 * 1024
TOP_FIELDS = frozenset({
    "schema_version", "status", "created_at", "claim_scope", "attestation",
    "configuration", "records",
})
CLAIM_FIELDS = frozenset({
    "kind", "model_role", "performance_claim_authorized",
    "final_benchmark_complete",
})
ATTESTATION_FIELDS = frozenset({
    "source_revision", "source_bundle_digest", "source_file_count",
    "geniex_revision", "operator_asserted_runtime_version",
    "operator_asserted_hardware_label", "process_architecture", "model",
    "model_artifact", "model_artifact_binding", "cli_sha256",
    "loaded_runtime_modules", "server_pid", "server_creation_time_100ns",
    "listener_identity_checks", "runtime_module_checks", "server_origin",
})
STABLE_ATTESTATION_FIELDS = tuple(sorted(ATTESTATION_FIELDS - {
    "server_pid", "server_creation_time_100ns", "listener_identity_checks",
    "runtime_module_checks", "server_origin",
}))
CONFIGURATION_FIELDS = frozenset({
    "mode", "traces", "append_turns", "max_completion_tokens",
    "cancel_after_stream_chunks", "streaming",
    "single_bound_server_process", "fresh_process_launch_attested",
})
STABLE_CONFIGURATION_FIELDS = tuple(sorted(CONFIGURATION_FIELDS - {"mode"}))
RECORD_FIELDS = frozenset({
    "trace", "mode", "role", "step", "cancelled", "cache_status",
    "cache_reason", "revision", "reusable", "ttft_us", "decode_stream_us",
    "wall_us", "prompt_tokens", "generated_tokens",
    "observed_output_chunks", "working_set_bytes", "finish_reason",
    "output_digest", "stream_bytes",
})
PAIR_RESULT_FIELDS = ("output_digest", "finish_reason", "generated_tokens")
UTC_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


def _exact_fields(value: object, expected: frozenset[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} has unknown or missing fields")
    return value


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _reject_forbidden_keys(value: object, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_EVIDENCE_KEYS:
                raise ValueError(f"evidence contains forbidden key {path}.{key}")
            _reject_forbidden_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_keys(child, f"{path}[{index}]")


def _read_evidence(path: Path) -> tuple[dict, str]:
    resolved = path.resolve(strict=True)
    metadata = resolved.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"evidence path is not one regular non-link file: {path}")
    if metadata.st_size <= 0 or metadata.st_size > MAX_EVIDENCE_BYTES:
        raise ValueError(f"evidence file size is outside the accepted bound: {path}")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"evidence is not bounded UTF-8 JSON: {path}") from error
    return payload, "sha256:" + sha256_file(resolved)


def _validate_manifest(value: object, label: str) -> None:
    manifest = _exact_fields(
        value, frozenset({"kind", "files", "bytes", "sha256"}), label
    )
    if manifest["kind"] != "directory":
        raise ValueError(f"{label} is not a directory manifest")
    _positive_integer(manifest["files"], f"{label}.files")
    _positive_integer(manifest["bytes"], f"{label}.bytes")
    if not SHA256_PATTERN.fullmatch(str(manifest["sha256"])):
        raise ValueError(f"{label} has an invalid digest")


def _validate_runtime_modules(value: object) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError("attestation has no loaded runtime modules")
    names = set()
    for index, item in enumerate(value):
        module = _exact_fields(
            item, frozenset({"name", "bytes", "sha256"}),
            f"loaded_runtime_modules[{index}]",
        )
        name = module["name"]
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("loaded runtime module names must be unique text")
        names.add(name)
        _positive_integer(module["bytes"], f"loaded_runtime_modules[{index}].bytes")
        if not SHA256_PATTERN.fullmatch(str(module["sha256"])):
            raise ValueError("loaded runtime module has an invalid digest")


def _validate_records(payload: dict, expected_mode: str) -> dict[tuple[str, str, int], dict]:
    configuration = payload["configuration"]
    traces = configuration["traces"]
    expected_sequence = [
        (trace, "verifier" if trace == "verifier_detour" and step == 1 else "driver", step)
        for trace in traces
        for step in range(_trace_steps(trace, configuration["append_turns"]))
    ]
    records = payload["records"]
    if not isinstance(records, list) or len(records) != len(expected_sequence):
        raise ValueError("replay does not contain the exact expected record count")

    reusable_by_role = {"driver": True, "verifier": True}
    active_trace = None
    indexed = {}
    for expected, raw in zip(expected_sequence, records):
        record = _exact_fields(raw, RECORD_FIELDS, "measurement record")
        trace, role, step = expected
        if trace != active_trace:
            active_trace = trace
            reusable_by_role = {"driver": True, "verifier": True}
        if (record["trace"], record["role"], record["step"]) != expected:
            raise ValueError("measurement records are not in canonical trace order")
        if record["mode"] != expected_mode:
            raise ValueError("measurement record contains the wrong cache mode")
        cancelled = trace == "cancellation_decode" and step == 1
        if record["cancelled"] is not cancelled:
            raise ValueError("measurement record has invalid cancellation placement")
        prior_reusable = reusable_by_role[role]
        decision = expected_cache_decision(
            expected_mode, trace, step, prior_reusable
        )
        if (record["cache_status"], record["cache_reason"]) != decision:
            raise ValueError("measurement record has an invalid cache decision")
        if not isinstance(record["reusable"], bool):
            raise ValueError("measurement reusable state must be boolean")
        expected_reusable = (
            not cancelled
            and (
                expected_mode == "legacy-test"
                or (expected_mode == "managed" and record["finish_reason"] == "stop")
            )
        )
        if record["reusable"] is not expected_reusable:
            raise ValueError("measurement record has an invalid reusable state")
        if cancelled:
            if (
                record["finish_reason"] != "client_disconnect"
                or record["prompt_tokens"] != 0
                or record["generated_tokens"] != 0
                or record["revision"] != ""
            ):
                raise ValueError("cancelled measurement has an invalid terminal state")
        else:
            if record["finish_reason"] not in {"stop", "length"}:
                raise ValueError("completed measurement has an invalid finish reason")
            _positive_integer(record["prompt_tokens"], "record.prompt_tokens")
            _positive_integer(record["generated_tokens"], "record.generated_tokens")
            if expected_mode == "managed":
                if not SHA256_PATTERN.fullmatch(str(record["revision"])):
                    raise ValueError("managed measurement has an invalid revision")
            elif record["revision"] != "":
                raise ValueError("unmanaged measurement contains a revision")
        for field in (
            "ttft_us", "decode_stream_us", "wall_us", "observed_output_chunks",
            "working_set_bytes", "stream_bytes",
        ):
            _positive_integer(record[field], f"record.{field}")
        if record["wall_us"] < record["ttft_us"]:
            raise ValueError("measurement wall time is smaller than TTFT")
        if not SHA256_PATTERN.fullmatch(str(record["output_digest"])):
            raise ValueError("measurement record has an invalid output digest")
        if expected_mode == "managed" and not cancelled:
            reusable_by_role[role] = record["reusable"]
        indexed[(trace, role, step)] = record
    return indexed


def validate_replay(payload: object, expected_mode: str) -> dict[tuple[str, str, int], dict]:
    replay = _exact_fields(payload, TOP_FIELDS, "replay")
    _reject_forbidden_keys(replay)
    if replay["schema_version"] != REPLAY_SCHEMA or replay["status"] != "complete":
        raise ValueError("replay is not one complete supported evidence file")
    if not isinstance(replay["created_at"], str) or not UTC_PATTERN.fullmatch(
        replay["created_at"]
    ):
        raise ValueError("replay has an invalid UTC creation time")
    claim = _exact_fields(replay["claim_scope"], CLAIM_FIELDS, "claim_scope")
    if (
        claim["kind"] != "attested_production_path_development_replay"
        or claim["model_role"] not in {"smoke", "final-study"}
        or claim["performance_claim_authorized"] is not False
        or claim["final_benchmark_complete"] is not False
    ):
        raise ValueError("replay claim scope exceeds the development boundary")

    attestation = _exact_fields(
        replay["attestation"], ATTESTATION_FIELDS, "attestation"
    )
    if not REVISION_PATTERN.fullmatch(str(attestation["source_revision"])):
        raise ValueError("attestation has an invalid source revision")
    if not REVISION_PATTERN.fullmatch(str(attestation["geniex_revision"])):
        raise ValueError("attestation has an invalid GenieX revision")
    for field in ("source_bundle_digest", "cli_sha256"):
        if not SHA256_PATTERN.fullmatch(str(attestation[field])):
            raise ValueError(f"attestation has an invalid {field}")
    _positive_integer(attestation["source_file_count"], "source_file_count")
    _positive_integer(attestation["server_pid"], "server_pid")
    _positive_integer(
        attestation["server_creation_time_100ns"], "server_creation_time_100ns"
    )
    _positive_integer(attestation["listener_identity_checks"], "listener checks")
    _positive_integer(attestation["runtime_module_checks"], "runtime checks")
    loopback_target(attestation["server_origin"])
    _validate_manifest(attestation["model_artifact"], "model_artifact")
    _validate_runtime_modules(attestation["loaded_runtime_modules"])

    configuration = _exact_fields(
        replay["configuration"], CONFIGURATION_FIELDS, "configuration"
    )
    if configuration["mode"] != expected_mode:
        raise ValueError("configuration contains the wrong cache mode")
    traces = configuration["traces"]
    if (
        not isinstance(traces, list)
        or not traces
        or len(set(traces)) != len(traces)
        or traces != [trace for trace in TRACE_ORDER if trace in traces]
    ):
        raise ValueError("configuration traces are not a canonical non-empty subset")
    append_turns = _positive_integer(configuration["append_turns"], "append_turns")
    max_tokens = _positive_integer(
        configuration["max_completion_tokens"], "max_completion_tokens"
    )
    cancel_chunks = _positive_integer(
        configuration["cancel_after_stream_chunks"], "cancel_after_stream_chunks"
    )
    if not 2 <= append_turns <= 64:
        raise ValueError("append_turns is outside the replay bound")
    if not 1 <= max_tokens <= 2048:
        raise ValueError("max_completion_tokens is outside the replay bound")
    if cancel_chunks > max_tokens:
        raise ValueError("cancel_after_stream_chunks exceeds the token limit")
    if (
        configuration["streaming"] is not True
        or configuration["single_bound_server_process"] is not True
        or configuration["fresh_process_launch_attested"] is not False
    ):
        raise ValueError("configuration exceeds the supported server-replay boundary")
    return _validate_records(replay, expected_mode)


def compare_replays(reset: dict, managed: dict) -> dict:
    reset_records = validate_replay(reset, "reset")
    managed_records = validate_replay(managed, "managed")
    if reset["claim_scope"]["model_role"] != managed["claim_scope"]["model_role"]:
        raise ValueError("paired replays use different model roles")
    for field in STABLE_ATTESTATION_FIELDS:
        if reset["attestation"][field] != managed["attestation"][field]:
            raise ValueError(f"paired replay attestation differs at {field}")
    for field in STABLE_CONFIGURATION_FIELDS:
        if reset["configuration"][field] != managed["configuration"][field]:
            raise ValueError(f"paired replay configuration differs at {field}")
    if set(reset_records) != set(managed_records):
        raise ValueError("paired replay record identities differ")

    mismatches = []
    compared = 0
    cancelled = 0
    prompt_reductions = 0
    managed_hits = 0
    for key in reset_records:
        left = reset_records[key]
        right = managed_records[key]
        if left["cancelled"]:
            cancelled += 1
            continue
        compared += 1
        for field in PAIR_RESULT_FIELDS:
            if left[field] != right[field]:
                mismatches.append({
                    "trace": key[0],
                    "role": key[1],
                    "step": key[2],
                    "field": field,
                })
        if right["cache_status"] == "reused":
            managed_hits += 1
            if right["prompt_tokens"] < left["prompt_tokens"]:
                prompt_reductions += 1

    equivalent = not mismatches
    reuse_observed = managed_hits > 0
    prompt_reduction_observed = prompt_reductions > 0
    return {
        "completed_records_compared": compared,
        "cancelled_records_excluded": cancelled,
        "managed_cache_hits": managed_hits,
        "managed_hits_with_lower_prompt_tokens": prompt_reductions,
        "output_equivalent": equivalent,
        "managed_reuse_observed": reuse_observed,
        "prompt_reduction_observed": prompt_reduction_observed,
        "mismatches": mismatches,
        "development_npu_gate_passed": (
            equivalent and reuse_observed and prompt_reduction_observed
        ),
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--reset", type=Path, required=True)
    parser.add_argument("--managed", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.execute:
        parser.error("refusing an evidence comparison without --execute")
    if not REVISION_PATTERN.fullmatch(args.source_revision):
        parser.error("--source-revision must be a full lowercase object ID")
    try:
        if args.reset.resolve(strict=True) == args.managed.resolve(strict=True):
            parser.error("--reset and --managed must be different files")
    except OSError as error:
        parser.error(f"input evidence does not exist: {error}")
    if args.output.exists() or Path(str(args.output) + ".tmp").exists():
        parser.error("refusing to overwrite comparison evidence")
    return args


def main(argv=None) -> None:
    args = parse_args(argv)
    source_root = Path(__file__).resolve().parents[2]
    verify_git_revision(source_root, args.source_revision, SMOKE_SOURCE_FILES)
    source_manifest = source_bundle_manifest(
        source_root, args.source_revision, SMOKE_SOURCE_FILES
    )
    reset, reset_digest = _read_evidence(args.reset)
    managed, managed_digest = _read_evidence(args.managed)
    for payload in (reset, managed):
        attestation = payload.get("attestation", {})
        if attestation.get("source_revision") != args.source_revision:
            raise ValueError("input replay source revision does not match the comparator")
        if attestation.get("source_bundle_digest") != source_manifest[
            "source_bundle_digest"
        ]:
            raise ValueError("input replay source bundle does not match the comparator")
        if attestation.get("source_file_count") != len(source_manifest["files"]):
            raise ValueError("input replay source-file count does not match")
    comparison = compare_replays(reset, managed)
    payload = {
        "schema_version": SCHEMA,
        "status": "passed" if comparison["development_npu_gate_passed"] else "failed",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        ),
        "claim_scope": {
            "kind": "paired_production_path_development_equivalence",
            "performance_claim_authorized": False,
            "final_benchmark_complete": False,
        },
        "attestation": {
            "source_revision": args.source_revision,
            "source_bundle_digest": source_manifest["source_bundle_digest"],
            "source_file_count": len(source_manifest["files"]),
            "geniex_revision": reset["attestation"]["geniex_revision"],
            "model": reset["attestation"]["model"],
            "model_artifact": reset["attestation"]["model_artifact"],
            "reset_evidence_sha256": reset_digest,
            "managed_evidence_sha256": managed_digest,
            "comparator_sha256": "sha256:" + sha256_file(Path(__file__)),
        },
        "comparison": comparison,
    }
    _reject_forbidden_keys(payload)
    write_json_exclusive(args.output, payload)
    if not comparison["development_npu_gate_passed"]:
        raise SystemExit(
            "managed replay failed reset equivalence or did not prove prompt reuse"
        )
    print(
        f"paired {comparison['completed_records_compared']} completed records; "
        f"observed {comparison['managed_cache_hits']} managed cache hits"
    )


if __name__ == "__main__":
    main()
