"""Run and analyze process-level BrickKV measurements.

This is intentionally separate from ``bench/``. It invokes the native
``brickkv-replay`` program once per mode and repetition, randomizes mode order
within each hardware block, and stores only synthetic, content-free evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import stat
import statistics
import subprocess
import sys
from typing import Iterable


MODES = ("reset", "legacy-test", "managed")
EXPECTED_SCHEMA = "brickkv.replay/3"
TRACE_ORDER = (
    "append_only", "planning_removed", "invalid_deleted", "context_pruning",
    "verifier_detour", "cancellation_decode",
)
TRACE_NAMES = frozenset(TRACE_ORDER)
ATTESTATION_FIELDS = frozenset({
    "source_revision", "sdk_version", "plugin", "plugin_version",
    "model_digest", "tokenizer_digest", "requested_device",
    "resolved_device", "device_warning", "hardware_label",
    "process_architecture", "host_processor", "system_product_name",
})
CONFIGURATION_FIELDS = frozenset({
    "context", "runtime_n_ctx", "max_tokens", "append_turns",
    "cancel_after_tokens",
})
RECORD_FIELDS = frozenset({
    "trace", "mode", "role", "step", "cache_status", "cache_reason",
    "revision", "result_code", "stop_reason", "callback_cancelled",
    "reusable",
    "ttft_us", "prompt_us", "decode_us", "wall_us", "prompt_tokens",
    "generated_tokens", "working_set_bytes", "output_digest",
})
FORBIDDEN_EVIDENCE_KEYS = frozenset(
    {"prompt", "messages", "content", "full_text", "generated_text"}
)
SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
REVISION_PATTERN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def mode_order(seed: int, phase: str, block: int) -> tuple[str, ...]:
    """Return a stable randomized order without depending on hash randomization."""
    material = f"brickkv-order/1\0{seed}\0{phase}\0{block}".encode()
    local_seed = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    values = list(MODES)
    random.Random(local_seed).shuffle(values)
    return tuple(values)


def percentile(values: Iterable[float], quantile: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("cannot calculate a percentile of an empty sample")
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be between zero and one")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def coefficient_of_variation(values: Iterable[float]) -> float | None:
    sample = [float(value) for value in values]
    if len(sample) < 2:
        return None
    mean = statistics.fmean(sample)
    if mean == 0.0:
        return None
    return statistics.stdev(sample) / mean


def _reject_content_keys(value, path="$"):
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_EVIDENCE_KEYS:
                raise ValueError(f"evidence contains forbidden key {path}.{key}")
            _reject_content_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_content_keys(child, f"{path}[{index}]")


def _require_exact_fields(value: dict, expected: frozenset[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(
            f"{label} fields do not match schema; missing={missing}, extra={extra}"
        )


def _require_attested_text(attestation: dict, key: str) -> str:
    value = attestation.get(key)
    if (not isinstance(value, str) or not value.strip() or
            value.strip().lower() == "unknown"):
        raise ValueError(f"attestation field {key!r} is not a verified value")
    return value


def _expected_cache_decision(
    mode: str, trace: str, step: int, prior_reusable: bool = True
) -> tuple[str, str]:
    if trace == "cancellation_decode" and step == 1:
        return "aborted", "callback_cancellation"
    if mode == "reset":
        return "reset", "reset_each_call"
    if mode == "legacy-test":
        return "legacy-test", "raw_keep_cache"
    if step == 0:
        return "cold", "first_request"
    if trace in {"planning_removed", "invalid_deleted", "context_pruning"} \
            and step == 2:
        return "reset", "branch"
    if trace == "verifier_detour" and step in {1, 2}:
        return "reset", "session_switch"
    if trace == "cancellation_decode" and step == 2:
        return "reset", "parent_mismatch"
    if not prior_reusable:
        return "reset", "previous_not_reusable"
    return "reused", "exact_extension"


def validate_evidence(
    payload: dict,
    expected_mode: str,
    *,
    expected_attestation: dict[str, str] | None = None,
    expected_traces: frozenset[str] | None = None,
) -> None:
    if not isinstance(payload, dict) or payload.get("schema_version") != EXPECTED_SCHEMA:
        raise ValueError("replay output has an unknown schema")
    _reject_content_keys(payload)
    _require_exact_fields(
        payload,
        frozenset({
            "schema_version", "status", "created_at", "attestation",
            "configuration", "records",
        }),
        "replay output",
    )
    if payload.get("status") != "complete":
        raise ValueError("replay output is not complete")
    if not isinstance(payload.get("created_at"), str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", payload["created_at"]
    ):
        raise ValueError("replay output has an invalid UTC creation time")

    attestation = payload.get("attestation")
    if not isinstance(attestation, dict):
        raise ValueError("replay output has no attestation")
    _require_exact_fields(attestation, ATTESTATION_FIELDS, "attestation")
    source_revision = _require_attested_text(attestation, "source_revision")
    if not REVISION_PATTERN.fullmatch(source_revision):
        raise ValueError("attestation source revision is not a full lowercase object ID")
    for key in (
        "sdk_version", "plugin_version", "hardware_label",
        "process_architecture", "host_processor", "system_product_name",
    ):
        _require_attested_text(attestation, key)
    if attestation["plugin"] not in {"qairt", "llama_cpp"}:
        raise ValueError("attestation contains an unsupported plugin")
    if attestation["requested_device"] not in {"cpu", "gpu", "npu", "hybrid"}:
        raise ValueError("attestation contains an unsupported requested device")
    if attestation["process_architecture"] not in {"arm64", "x86_64"}:
        raise ValueError("attestation contains an unsupported process architecture")
    if not SHA256_PATTERN.fullmatch(str(attestation["model_digest"])):
        raise ValueError("attestation contains an invalid model digest")
    tokenizer_digest = attestation["tokenizer_digest"]
    if tokenizer_digest != "none" and not SHA256_PATTERN.fullmatch(
        str(tokenizer_digest)
    ):
        raise ValueError("attestation contains an invalid tokenizer digest")
    if attestation["device_warning"] not in {"none", "present"}:
        raise ValueError("attestation device warning must be none or present")
    requested = attestation["requested_device"]
    resolved = attestation["resolved_device"]
    if attestation["plugin"] == "qairt":
        if resolved != "NPU":
            raise ValueError("QAIRT evidence did not resolve to the NPU")
        if requested == "npu" and attestation["device_warning"] != "none":
            raise ValueError("QAIRT NPU evidence contains an unexpected coercion warning")
        if requested != "npu" and attestation["device_warning"] != "present":
            raise ValueError("QAIRT device coercion has no warning evidence")
    else:
        expected_resolved = {
            "cpu": "", "gpu": "GPUOpenCL", "npu": "HTP0", "hybrid": "",
        }[requested]
        if resolved != expected_resolved:
            raise ValueError("llama.cpp evidence contains an unexpected resolved device")
        if attestation["device_warning"] != "none":
            raise ValueError("llama.cpp evidence contains an unexpected device warning")
    for key, value in (expected_attestation or {}).items():
        if key not in ATTESTATION_FIELDS:
            raise ValueError(f"caller requested an unknown attestation field {key!r}")
        if attestation[key] != value:
            raise ValueError(
                f"attestation mismatch for {key!r}: expected {value!r}, "
                f"got {attestation[key]!r}"
            )

    configuration = payload.get("configuration")
    if not isinstance(configuration, dict):
        raise ValueError("replay output has no configuration")
    _require_exact_fields(configuration, CONFIGURATION_FIELDS, "configuration")
    for key in CONFIGURATION_FIELDS - {"runtime_n_ctx"}:
        value = configuration[key]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"configuration field {key!r} must be a positive integer")
    runtime_n_ctx = configuration["runtime_n_ctx"]
    if isinstance(runtime_n_ctx, bool) or not isinstance(runtime_n_ctx, int):
        raise ValueError("configuration field 'runtime_n_ctx' must be an integer")
    if attestation["plugin"] == "qairt":
        if runtime_n_ctx != 0:
            raise ValueError("QAIRT evidence must leave runtime_n_ctx model-defined")
    elif runtime_n_ctx != configuration["context"]:
        raise ValueError("llama.cpp runtime_n_ctx must match the requested context")

    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("replay output has no measurement records")
    seen_steps: set[tuple[str, int]] = set()
    observed_traces: set[str] = set()
    reusable_by_role: dict[str, bool] = {}
    active_trace = None
    for record in records:
        if not isinstance(record, dict) or record.get("mode") != expected_mode:
            raise ValueError("replay output contains an unexpected cache mode")
        _require_exact_fields(record, RECORD_FIELDS, "measurement record")
        trace = record["trace"]
        if trace not in TRACE_NAMES:
            raise ValueError("measurement record contains an unknown trace")
        observed_traces.add(trace)
        if trace != active_trace:
            active_trace = trace
            reusable_by_role = {"driver": True, "verifier": True}
        step = record["step"]
        if isinstance(step, bool) or not isinstance(step, int) or step < 0:
            raise ValueError("measurement record contains an invalid step")
        step_key = (trace, step)
        if step_key in seen_steps:
            raise ValueError("measurement record contains a duplicate trace step")
        seen_steps.add(step_key)
        expected_role = "verifier" \
            if trace == "verifier_detour" and step == 1 else "driver"
        if record["role"] != expected_role:
            raise ValueError("measurement record has an invalid trace role")
        expected_cancel = trace == "cancellation_decode" and step == 1
        if record["callback_cancelled"] != expected_cancel:
            raise ValueError("measurement record has invalid cancellation placement")
        prior_reusable = reusable_by_role[expected_role]
        expected_decision = _expected_cache_decision(
            expected_mode, trace, step, prior_reusable
        )
        if (record["cache_status"], record["cache_reason"]) != expected_decision:
            raise ValueError("measurement record has an invalid cache decision")
        if expected_cancel and (
            record["stop_reason"] != "callback_cancelled"
            or record["revision"] != ""
        ):
            raise ValueError("measurement record has invalid cancellation outcome")
        if not expected_cancel and (
            record["stop_reason"] == "callback_cancelled"
        ):
            raise ValueError("measurement record has an unexpected cancellation outcome")
        for key in (
            "ttft_us", "prompt_us", "decode_us", "wall_us", "prompt_tokens",
            "generated_tokens", "working_set_bytes",
        ):
            value = record[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"measurement field {key!r} must be non-negative")
        if isinstance(record["result_code"], bool) or not isinstance(
            record["result_code"], int
        ):
            raise ValueError("measurement result code must be an integer")
        if not expected_cancel and record["result_code"] != 0:
            raise ValueError("completed measurement has a failed result code")
        if not isinstance(record["callback_cancelled"], bool):
            raise ValueError("measurement cancellation flag must be boolean")
        if not isinstance(record["reusable"], bool):
            raise ValueError("measurement reusable flag must be boolean")
        for key in ("cache_reason", "stop_reason"):
            if not isinstance(record[key], str) or not record[key]:
                raise ValueError(f"measurement field {key!r} must be non-empty text")
        allowed_status = {
            "reset": {"reset", "aborted"},
            "legacy-test": {"legacy-test", "aborted"},
            "managed": {"cold", "reused", "reset", "aborted"},
        }[expected_mode]
        if record["cache_status"] not in allowed_status:
            raise ValueError("measurement record contains an invalid cache status")
        allowed_stop_reasons = {
            "eos", "length", "user", "stop_sequence", "context_length", "other",
        }
        if not expected_cancel and record["stop_reason"] not in allowed_stop_reasons:
            raise ValueError("completed measurement has an invalid stop reason")
        expected_reusable = (
            not expected_cancel
            and (
                expected_mode == "legacy-test"
                or (
                    expected_mode == "managed"
                    and record["stop_reason"] == "eos"
                )
            )
        )
        if record["reusable"] is not expected_reusable:
            raise ValueError("measurement has an invalid reusable decision")
        for key in (
            "ttft_us", "prompt_us", "decode_us", "wall_us", "prompt_tokens",
            "generated_tokens", "working_set_bytes",
        ):
            if record[key] <= 0:
                raise ValueError(f"completed measurement field {key!r} must be positive")
        if record["wall_us"] < record["ttft_us"]:
            raise ValueError("measurement wall time is smaller than TTFT")
        if expected_cancel and (
            record["generated_tokens"] < configuration["cancel_after_tokens"]
        ):
            raise ValueError("cancelled measurement stopped before its callback count")
        revision = record["revision"]
        if expected_mode == "managed" and record["cache_status"] != "aborted":
            if not SHA256_PATTERN.fullmatch(str(revision)):
                raise ValueError("managed measurement has no committed revision")
        elif revision != "":
            raise ValueError("non-committed measurement contains a revision")
        if not SHA256_PATTERN.fullmatch(str(record["output_digest"])):
            raise ValueError("measurement record contains an invalid output digest")
        if expected_mode == "managed" and not expected_cancel:
            reusable_by_role[expected_role] = record["reusable"]
    if expected_traces is not None and observed_traces != set(expected_traces):
        raise ValueError(
            "replay output trace set does not match the requested experiment"
        )
    expected_counts = {
        "append_only": configuration["append_turns"],
        "planning_removed": 4,
        "invalid_deleted": 4,
        "context_pruning": 4,
        "verifier_detour": 3,
        "cancellation_decode": 4,
    }
    for trace in observed_traces:
        actual = sum(record["trace"] == trace for record in records)
        if actual != expected_counts[trace]:
            raise ValueError(
                f"trace {trace!r} has {actual} records; expected {expected_counts[trace]}"
            )
    expected_steps = {
        (trace, step)
        for trace in observed_traces
        for step in range(expected_counts[trace])
    }
    if seen_steps != expected_steps:
        raise ValueError("replay output does not contain the exact trace-step sequence")
    expected_sequence = [
        (trace, step)
        for trace in TRACE_ORDER if trace in observed_traces
        for step in range(expected_counts[trace])
    ]
    actual_sequence = [(record["trace"], record["step"]) for record in records]
    if actual_sequence != expected_sequence:
        raise ValueError("replay output records are not in canonical trace-step order")


def process_metrics(payload: dict) -> dict[str, dict[str, float]]:
    """Reduce one process to one observation per trace.

    Calls inside a process are not treated as independent samples. Their p95
    TTFT and total wall time become that process's trace-level observation.
    """
    grouped: dict[str, list[dict]] = {}
    for record in payload["records"]:
        grouped.setdefault(record["trace"], []).append(record)
    reduced = {}
    for trace, records in grouped.items():
        ttft = [float(item["ttft_us"]) for item in records]
        generated = sum(float(item["generated_tokens"]) for item in records)
        decode_us = sum(float(item.get("decode_us", 0)) for item in records)
        reduced[trace] = {
            "p95_ttft_us": percentile(ttft, 0.95),
            "median_ttft_us": statistics.median(ttft),
            "total_wall_us": sum(float(item["wall_us"]) for item in records),
            "prompt_tokens": sum(float(item["prompt_tokens"]) for item in records),
            "generated_tokens": generated,
            "decode_tokens_per_s": (
                generated / (decode_us / 1_000_000.0) if decode_us > 0 else 0.0
            ),
            "cache_hits": sum(item["cache_status"] == "reused" for item in records),
            "cache_resets": sum(item["cache_status"] == "reset" for item in records),
            "errors": sum(int(item.get("result_code", 0)) != 0 for item in records),
            "output_digests": [item["output_digest"] for item in records],
        }
    return reduced


def summarize_observations(observations: list[dict]) -> dict:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for observation in observations:
        for trace, metrics in observation["metrics"].items():
            grouped.setdefault((observation["mode"], trace), []).append(metrics)
    result = {}
    for (mode, trace), rows in sorted(grouped.items()):
        p95_values = [row["p95_ttft_us"] for row in rows]
        wall_values = [row["total_wall_us"] for row in rows]
        result.setdefault(mode, {})[trace] = {
            "process_runs": len(rows),
            "p95_ttft_us_median": statistics.median(p95_values),
            "p95_ttft_us_p95": percentile(p95_values, 0.95),
            "p95_ttft_run_cv": coefficient_of_variation(p95_values),
            "total_wall_us_median": statistics.median(wall_values),
            "total_wall_us_p95": percentile(wall_values, 0.95),
            "prompt_tokens_median": statistics.median(
                row["prompt_tokens"] for row in rows
            ),
            "decode_tokens_per_s_median": statistics.median(
                row["decode_tokens_per_s"] for row in rows
            ),
            "errors": sum(row["errors"] for row in rows),
        }
    return result


def paired_bootstrap_improvement(
    observations: list[dict], trace: str, *, samples: int = 5000, seed: int = 42
) -> dict | None:
    by_block: dict[int, dict[str, dict]] = {}
    for item in observations:
        metrics = item["metrics"].get(trace)
        if metrics is not None:
            by_block.setdefault(item["block"], {})[item["mode"]] = metrics
    pairs = [
        (row["reset"], row["managed"])
        for _, row in sorted(by_block.items())
        if "reset" in row and "managed" in row
    ]
    if not pairs:
        return None
    point_reset = statistics.median(pair[0]["p95_ttft_us"] for pair in pairs)
    point_managed = statistics.median(pair[1]["p95_ttft_us"] for pair in pairs)
    point = 100.0 * (point_reset - point_managed) / point_reset
    prompt_differences = [
        pair[0]["prompt_tokens"] - pair[1]["prompt_tokens"] for pair in pairs
    ]
    rng = random.Random(seed)
    estimates = []
    prompt_estimates = []
    for _ in range(samples):
        sample = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        reset = statistics.median(pair[0]["p95_ttft_us"] for pair in sample)
        managed = statistics.median(pair[1]["p95_ttft_us"] for pair in sample)
        if reset != 0:
            estimates.append(100.0 * (reset - managed) / reset)
        prompt_estimates.append(statistics.median(
            pair[0]["prompt_tokens"] - pair[1]["prompt_tokens"]
            for pair in sample
        ))
    return {
        "paired_process_blocks": len(pairs),
        "median_improvement_percent": point,
        "bootstrap_95_ci_percent": [
            percentile(estimates, 0.025), percentile(estimates, 0.975)
        ],
        "prompt_tokens_avoided_median": statistics.median(prompt_differences),
        "prompt_tokens_avoided_bootstrap_95_ci": [
            percentile(prompt_estimates, 0.025),
            percentile(prompt_estimates, 0.975),
        ],
    }


def correctness_mismatches(observations: list[dict], baseline: str,
                           candidate: str) -> list[dict]:
    """Compare deterministic output sequences at the process-block boundary."""
    grouped: dict[tuple[int, str], dict[str, dict]] = {}
    for item in observations:
        for trace, metrics in item["metrics"].items():
            grouped.setdefault((item["block"], trace), {})[
                item["mode"]
            ] = metrics
    mismatches = []
    for (block, trace), modes in sorted(grouped.items()):
        if baseline not in modes or candidate not in modes:
            mismatches.append({
                "block": block,
                "trace": trace,
                "reason": "missing paired mode",
            })
            continue
        left = modes[baseline]
        right = modes[candidate]
        if left["output_digests"] != right["output_digests"]:
            mismatches.append({
                "block": block,
                "trace": trace,
                "reason": "output digest sequence differs",
            })
        if left["errors"] != right["errors"]:
            mismatches.append({
                "block": block,
                "trace": trace,
                "reason": "result-code count differs",
            })
    return mismatches


def needs_extra_repetitions(summary: dict, threshold: float) -> list[dict]:
    unstable = []
    for mode, traces in summary.items():
        for trace, metrics in traces.items():
            value = metrics["p95_ttft_run_cv"]
            if value is not None and value > threshold:
                unstable.append({"mode": mode, "trace": trace, "cv": value})
    return unstable


def sha256_file(path: Path) -> str:
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RuntimeError(f"evidence entry is not a regular file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.lstat()
    if (
        stat.S_ISLNK(after.st_mode)
        or not stat.S_ISREG(after.st_mode)
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise RuntimeError(f"evidence entry changed while hashing: {path}")
    return digest.hexdigest()


def write_json_exclusive(path: Path, payload: dict) -> None:
    """Durably publish JSON without following or replacing an existing path."""
    temporary = path.with_name(path.name + ".tmp")
    if path.exists() or path.is_symlink():
        raise RuntimeError(f"refusing to overwrite evidence: {path}")
    if temporary.exists() or temporary.is_symlink():
        raise RuntimeError(f"refusing to overwrite partial evidence: {temporary}")
    encoded = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
    with temporary.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(temporary, path)
    except OSError:
        # Keep the exclusive temporary as a failure receipt. A later run must
        # not silently reuse or overwrite it.
        raise
    temporary.unlink()


def write_integrity_manifest(root: Path) -> None:
    entries = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if relative == Path("integrity.json"):
            continue
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise RuntimeError(f"evidence tree contains a symbolic link: {relative}")
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(f"evidence tree contains a special file: {relative}")
        entries.append(
            {
                "path": relative.as_posix(),
                "bytes": metadata.st_size,
                "sha256": sha256_file(path),
            }
        )
    write_json_exclusive(root / "integrity.json", {"files": entries})


def _run_one(args, root: Path, phase: str, block: int, mode: str,
             environment: dict[str, str]) -> dict:
    destination = root / "raw" / phase / f"block-{block:03d}" / f"{mode}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise RuntimeError(f"refusing to overwrite existing evidence: {destination}")
    command = [
        str(args.replay), "--model", str(args.model), "--plugin", args.plugin,
        "--device", args.device, "--mode", mode, "--trace", "all",
        "--output", str(destination), "--context", str(args.context),
        "--max-tokens", str(args.max_tokens), "--append-turns",
        str(args.append_turns), "--cancel-after-tokens",
        str(args.cancel_after_tokens), "--hardware-label", args.hardware_label,
        "--source-revision", args.source_revision,
    ]
    if args.tokenizer:
        command.extend(("--tokenizer", str(args.tokenizer)))
    try:
        completed = subprocess.run(
            command,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=args.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        if isinstance(stdout, str):
            stdout = stdout.encode("utf-8", errors="replace")
        if isinstance(stderr, str):
            stderr = stderr.encode("utf-8", errors="replace")
        write_json_exclusive(root / "failure.json", {
            "phase": phase,
            "block": block,
            "mode": mode,
            "timed_out": True,
            "stdout_bytes": len(stdout),
            "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "stderr_bytes": len(stderr),
            "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        })
        raise RuntimeError(
            f"brickkv-replay timed out in {phase} block {block}, mode {mode}"
        ) from exc
    if completed.returncode != 0:
        stderr_bytes = completed.stderr.encode("utf-8", errors="replace")
        stdout_bytes = completed.stdout.encode("utf-8", errors="replace")
        failure = {
            "phase": phase,
            "block": block,
            "mode": mode,
            "returncode": completed.returncode,
            "stderr_bytes": len(stderr_bytes),
            "stderr_sha256": hashlib.sha256(stderr_bytes).hexdigest(),
            "stdout_bytes": len(stdout_bytes),
            "stdout_sha256": hashlib.sha256(stdout_bytes).hexdigest(),
        }
        write_json_exclusive(root / "failure.json", failure)
        raise RuntimeError(
            f"brickkv-replay failed in {phase} block {block}, mode {mode}"
        )
    payload = json.loads(destination.read_text(encoding="utf-8"))
    expected_attestation = {
        "source_revision": args.source_revision,
        "plugin": args.plugin,
        "requested_device": args.device,
        "hardware_label": args.hardware_label,
        "process_architecture": args.expected_process_architecture,
    }
    validate_evidence(
        payload,
        mode,
        expected_attestation=expected_attestation,
        expected_traces=TRACE_NAMES,
    )
    attestation_json = json.dumps(
        payload["attestation"], sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "phase": phase,
        "block": block,
        "mode": mode,
        "path": destination.relative_to(root).as_posix(),
        "attestation_digest": "sha256:" + hashlib.sha256(attestation_json).hexdigest(),
        "metrics": process_metrics(payload),
    }


def _run_blocks(args, root: Path, phase: str, start: int, count: int,
                environment: dict[str, str]) -> list[dict]:
    observations = []
    for block in range(start, start + count):
        order = mode_order(args.seed, phase, block)
        print(f"{phase} block {block}: {', '.join(order)}", flush=True)
        for mode in order:
            observations.append(
                _run_one(args, root, phase, block, mode, environment)
            )
    return observations


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path)
    parser.add_argument("--plugin", choices=("qairt", "llama_cpp"), required=True)
    parser.add_argument("--plugin-path", type=Path, required=True)
    parser.add_argument("--sdk-lib", type=Path, required=True)
    parser.add_argument(
        "--device", choices=("cpu", "gpu", "npu", "hybrid"), default="npu"
    )
    parser.add_argument("--hardware-label", required=True)
    parser.add_argument(
        "--expected-process-architecture",
        choices=("arm64", "x86_64"),
        required=True,
    )
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--context", type=int, default=8192)
    parser.add_argument("--max-tokens", type=int, default=32)
    parser.add_argument("--append-turns", type=int, default=12)
    parser.add_argument("--cancel-after-tokens", type=int, default=1)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--extra-repetitions", type=int, default=10)
    parser.add_argument("--cv-threshold", type=float, default=0.08)
    parser.add_argument("--bootstrap-samples", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260830)
    parser.add_argument("--timeout", type=int, default=7200)
    args = parser.parse_args(argv)
    for name in (
        "context", "max_tokens", "append_turns", "cancel_after_tokens",
        "warmups", "repetitions", "extra_repetitions", "timeout",
        "bootstrap_samples",
    ):
        if getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    if not 0 < args.cv_threshold < 1:
        parser.error("--cv-threshold must be between zero and one")
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", args.source_revision):
        parser.error("--source-revision must be a full lowercase Git object ID")
    return args


def main(argv=None):
    args = parse_args(argv)
    if not args.execute:
        raise SystemExit("refusing an expensive hardware run without --execute")
    for path, label in (
        (args.replay, "replay executable"), (args.model, "model artifact"),
        (args.plugin_path, "plugin path"), (args.sdk_lib, "SDK library path"),
    ):
        if not path.exists():
            raise SystemExit(f"{label} does not exist: {path}")
    if args.tokenizer and not args.tokenizer.exists():
        raise SystemExit(f"tokenizer artifact does not exist: {args.tokenizer}")
    args.output.mkdir(parents=True, exist_ok=False)

    environment = os.environ.copy()
    environment["GENIEX_PLUGIN_PATH"] = str(args.plugin_path)
    environment["PATH"] = str(args.sdk_lib) + os.pathsep + environment.get("PATH", "")
    observations = []
    observations.extend(
        _run_blocks(args, args.output, "warmup", 0, args.warmups, environment)
    )
    measured = _run_blocks(
        args, args.output, "measure", 0, args.repetitions, environment
    )
    observations.extend(measured)
    summary = summarize_observations(measured)
    unstable = needs_extra_repetitions(summary, args.cv_threshold)
    if unstable:
        extra = _run_blocks(
            args, args.output, "measure",
            args.repetitions, args.extra_repetitions, environment,
        )
        observations.extend(extra)
        measured.extend(extra)
        summary = summarize_observations(measured)
        unstable = needs_extra_repetitions(summary, args.cv_threshold)

    improvements = {
        trace: paired_bootstrap_improvement(
            measured, trace, samples=args.bootstrap_samples,
            seed=args.seed + index,
        )
        for index, trace in enumerate(sorted({
            trace for item in measured for trace in item["metrics"]
        }))
    }
    mismatches = correctness_mismatches(measured, "reset", "managed")
    report = {
        "schema_version": "brickkv.matrix/1",
        "statistical_unit": "one brickkv-replay process",
        "warmup_blocks": args.warmups,
        "measurement_blocks": len({item["block"] for item in measured}),
        "mode_order_seed": args.seed,
        "cv_threshold": args.cv_threshold,
        "remaining_unstable_cells": unstable,
        "summary": summary,
        "managed_vs_reset": improvements,
        "managed_correctness": {
            "passed": not mismatches,
            "mismatches": mismatches,
        },
        "observations": observations,
    }
    write_json_exclusive(args.output / "report.json", report)
    write_integrity_manifest(args.output)
    print(f"complete: {args.output / 'report.json'}")


if __name__ == "__main__":
    main()
