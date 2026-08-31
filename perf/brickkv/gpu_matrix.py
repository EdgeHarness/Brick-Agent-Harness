"""Process-level vLLM APC matrix for one HTCondor-assigned GPU."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import statistics
import subprocess
import sys

from perf.brickkv.run_matrix import (
    coefficient_of_variation,
    correctness_mismatches,
    needs_extra_repetitions,
    percentile,
    write_json_exclusive,
    write_integrity_manifest,
)
from perf.brickkv.source_bundle import source_bundle_digest
from perf.brickkv.gpu_prefix_study import ENDPOINT_BINDING


MODES = ("off", "on")
TRACES = {
    "append_only": None,
    "planning_removed": 4,
    "invalid_deleted": 4,
    "context_pruning": 4,
    "verifier_detour": 3,
    "cancellation_decode": 4,
}
ROOT_FIELDS = {
    "schema_version", "status", "mode", "attestation", "configuration",
    "records",
}
ATTESTATION_FIELDS = {
    "source_revision", "source_bundle_digest", "model_archive_digest",
    "container_digest", "vllm_version", "gpu",
}
GPU_FIELDS = {
    "name", "uuid_hash", "memory_mb", "driver_version",
    "cuda_visible_devices_hash",
}
CONFIGURATION_FIELDS = {
    "context", "max_tokens", "append_turns", "prefix_caching",
    "prefix_hash_algorithm", "served_model_digest", "endpoint_binding",
    "gpu_memory_utilization", "server_timeout_s", "request_timeout_s",
    "dtype", "generation_config", "temperature", "seed",
    "workload_version",
}
RECORD_FIELDS = {
    "trace", "step", "role", "mode", "ttft_us", "wall_us",
    "prompt_tokens", "generated_tokens", "cancelled", "output_digest",
    "prefix_queries", "prefix_hits",
}


def gpu_mode_order(seed: int, phase: str, block: int) -> tuple[str, ...]:
    material = f"brickkv-gpu-order/1\0{seed}\0{phase}\0{block}".encode()
    local_seed = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    values = list(MODES)
    random.Random(local_seed).shuffle(values)
    return tuple(values)


def _exact_object(value, fields, label):
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"GPU evidence {label} has an invalid field set")
    return value


def _digest(value, label):
    if not isinstance(value, str) \
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise ValueError(f"GPU evidence {label} is not a SHA-256 digest")


def _nonnegative_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or value < 0:
        raise ValueError(f"GPU evidence {label} must be finite and nonnegative")


def validate_gpu_evidence(payload: dict, mode: str, expected: dict):
    _exact_object(payload, ROOT_FIELDS, "root")
    if payload["schema_version"] != "brickkv.vllm/1" \
            or payload["status"] != "complete" or payload["mode"] != mode:
        raise ValueError("GPU evidence has an invalid envelope")
    attestation = _exact_object(
        payload["attestation"], ATTESTATION_FIELDS, "attestation"
    )
    for field in (
        "source_revision", "source_bundle_digest", "model_archive_digest",
        "container_digest",
    ):
        if attestation[field] != expected[field]:
            raise ValueError(f"GPU evidence {field} does not match the run")
    if not isinstance(attestation["vllm_version"], str) \
            or not re.fullmatch(r"[ -~]{1,128}", attestation["vllm_version"]):
        raise ValueError("GPU evidence has an invalid vLLM version")
    gpu = _exact_object(attestation["gpu"], GPU_FIELDS, "GPU attestation")
    if not isinstance(gpu["name"], str) or expected["expected_gpu"] not in gpu["name"]:
        raise ValueError("GPU evidence does not match the requested GPU")
    for field in ("uuid_hash", "cuda_visible_devices_hash"):
        _digest(gpu[field], field)
    if type(gpu["memory_mb"]) is not int or gpu["memory_mb"] <= 0:
        raise ValueError("GPU evidence has invalid device memory")
    if not isinstance(gpu["driver_version"], str) \
            or not re.fullmatch(r"[ -~]{1,128}", gpu["driver_version"]):
        raise ValueError("GPU evidence has an invalid driver version")

    configuration = _exact_object(
        payload["configuration"], CONFIGURATION_FIELDS, "configuration"
    )
    expected_configuration = {
        "context": expected["context"],
        "max_tokens": expected["max_tokens"],
        "append_turns": expected["append_turns"],
        "prefix_caching": mode == "on",
        "prefix_hash_algorithm": "sha256" if mode == "on" else None,
        "served_model_digest": expected["served_model_digest"],
        "endpoint_binding": ENDPOINT_BINDING,
        "gpu_memory_utilization": expected["gpu_memory_utilization"],
        "server_timeout_s": expected["server_timeout"],
        "request_timeout_s": expected["request_timeout"],
        "dtype": "bfloat16",
        "generation_config": "vllm",
        "temperature": 0,
        "seed": 42,
        "workload_version": "brickkv.synthetic-agent-traces/1",
    }
    if configuration != expected_configuration:
        raise ValueError("GPU evidence configuration does not match the run")

    records = payload["records"]
    expected_steps = dict(TRACES)
    expected_steps["append_only"] = expected["append_turns"]
    expected_count = sum(expected_steps.values())
    if not isinstance(records, list) or len(records) != expected_count:
        raise ValueError("GPU evidence has the wrong record count")
    forbidden = {"messages", "content", "full_text", "generated_text", "prompt"}

    def visit(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower() in forbidden:
                    raise ValueError(f"GPU evidence contains forbidden key {key!r}")
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    seen = set()
    for record in records:
        _exact_object(record, RECORD_FIELDS, "record")
        trace = record["trace"]
        step = record["step"]
        if trace not in expected_steps or type(step) is not int \
                or not 0 <= step < expected_steps[trace] \
                or (trace, step) in seen:
            raise ValueError("GPU record has an invalid or duplicate trace step")
        seen.add((trace, step))
        expected_role = "verifier" \
            if trace == "verifier_detour" and step == 1 else "driver"
        if record["mode"] != mode or record["role"] != expected_role:
            raise ValueError("GPU record has the wrong mode or role")
        expected_cancel = trace == "cancellation_decode" and step == 1
        if type(record["cancelled"]) is not bool \
                or record["cancelled"] != expected_cancel:
            raise ValueError("GPU record has invalid cancellation evidence")
        for field in ("ttft_us", "wall_us", "prompt_tokens", "generated_tokens"):
            if type(record[field]) is not int or record[field] < 0:
                raise ValueError(f"GPU record has invalid {field}")
        if record["ttft_us"] <= 0 or record["wall_us"] < record["ttft_us"]:
            raise ValueError("GPU record has invalid timing order")
        for field in ("prefix_queries", "prefix_hits"):
            _nonnegative_number(record[field], field)
        if record["prefix_hits"] > record["prefix_queries"]:
            raise ValueError("GPU record has more prefix hits than queries")
        _digest(record["output_digest"], "output digest")
    expected_pairs = {
        (trace, step)
        for trace, count in expected_steps.items()
        for step in range(count)
    }
    if seen != expected_pairs:
        raise ValueError("GPU evidence is missing required trace steps")


def gpu_process_metrics(payload: dict) -> dict[str, dict[str, float]]:
    grouped = {}
    for record in payload["records"]:
        grouped.setdefault(record["trace"], []).append(record)
    result = {}
    for trace, rows in grouped.items():
        ttft = [float(row["ttft_us"]) for row in rows]
        wall = sum(float(row["wall_us"]) for row in rows)
        generated = sum(float(row["generated_tokens"]) for row in rows)
        decode_us = sum(max(
            0.0, float(row["wall_us"]) - float(row["ttft_us"])
        ) for row in rows if row["ttft_us"] is not None)
        queries = sum(float(row["prefix_queries"]) for row in rows)
        hits = sum(float(row["prefix_hits"]) for row in rows)
        result[trace] = {
            "p95_ttft_us": percentile(ttft, 0.95),
            "median_ttft_us": statistics.median(ttft),
            "total_wall_us": wall,
            "prompt_tokens": sum(float(row["prompt_tokens"]) for row in rows),
            "generated_tokens": generated,
            "decode_tokens_per_s": (
                generated / (decode_us / 1_000_000.0) if decode_us > 0 else 0.0
            ),
            "prefix_queries": queries,
            "prefix_hits": hits,
            "prefix_hit_rate": hits / queries if queries > 0 else None,
            "errors": 0,
            "output_digests": [row["output_digest"] for row in rows],
        }
    return result


def summarize(observations):
    grouped = {}
    for observation in observations:
        for trace, metrics in observation["metrics"].items():
            grouped.setdefault((observation["mode"], trace), []).append(metrics)
    summary = {}
    for (mode, trace), rows in sorted(grouped.items()):
        p95 = [row["p95_ttft_us"] for row in rows]
        summary.setdefault(mode, {})[trace] = {
            "process_runs": len(rows),
            "p95_ttft_us_median": statistics.median(p95),
            "p95_ttft_us_p95": percentile(p95, 0.95),
            "p95_ttft_run_cv": coefficient_of_variation(p95),
            "total_wall_us_median": statistics.median(
                row["total_wall_us"] for row in rows
            ),
            "prompt_tokens_median": statistics.median(
                row["prompt_tokens"] for row in rows
            ),
            "prefix_hit_rate_median": statistics.median(
                row["prefix_hit_rate"]
                for row in rows if row["prefix_hit_rate"] is not None
            ) if any(row["prefix_hit_rate"] is not None for row in rows) else None,
            "errors": 0,
        }
    return summary


def paired_apc_improvement(observations, trace, samples=5000, seed=42):
    by_block = {}
    for item in observations:
        if trace in item["metrics"]:
            by_block.setdefault(item["block"], {})[item["mode"]] = \
                item["metrics"][trace]["p95_ttft_us"]
    pairs = [(row["off"], row["on"]) for _, row in sorted(by_block.items())
             if "off" in row and "on" in row]
    if not pairs:
        return None
    baseline = statistics.median(row[0] for row in pairs)
    enabled = statistics.median(row[1] for row in pairs)
    point = 100.0 * (baseline - enabled) / baseline
    rng = random.Random(seed)
    estimates = []
    for _ in range(samples):
        sample = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        off = statistics.median(row[0] for row in sample)
        on = statistics.median(row[1] for row in sample)
        if off:
            estimates.append(100.0 * (off - on) / off)
    return {
        "paired_process_blocks": len(pairs),
        "median_improvement_percent": point,
        "bootstrap_95_ci_percent": [
            percentile(estimates, 0.025), percentile(estimates, 0.975)
        ],
    }


def run_one(args, root, phase, block, mode, environment):
    repository_root = Path(__file__).resolve().parents[2]
    if source_bundle_digest(repository_root) != args.source_bundle_digest:
        raise RuntimeError("GPU study source bundle changed before a process run")
    destination = root / "raw" / phase / f"block-{block:03d}" / f"{mode}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise RuntimeError(f"refusing to overwrite {destination}")
    command = [
        sys.executable, str(args.study), "--model", str(args.model),
        "--model-archive-digest", args.model_archive_digest,
        "--container-digest", args.container_digest,
        "--expected-gpu", args.expected_gpu,
        "--source-revision", args.source_revision,
        "--source-bundle-digest", args.source_bundle_digest,
        "--served-model", args.served_model,
        "--mode", mode, "--output", str(destination),
        "--context", str(args.context), "--max-tokens", str(args.max_tokens),
        "--append-turns", str(args.append_turns),
        "--server-timeout", str(args.server_timeout),
        "--request-timeout", str(args.request_timeout),
        "--gpu-memory-utilization", str(args.gpu_memory_utilization),
    ]
    process = subprocess.Popen(
        command, env=environment, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=args.process_timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
    if process.returncode or timed_out:
        stdout_bytes = stdout.encode("utf-8", errors="replace")
        stderr_bytes = stderr.encode("utf-8", errors="replace")
        failure = {
            "phase": phase, "block": block, "mode": mode,
            "returncode": process.returncode,
            "timed_out": timed_out,
            "stdout": {
                "bytes": len(stdout_bytes),
                "sha256": "sha256:" + hashlib.sha256(stdout_bytes).hexdigest(),
            },
            "stderr": {
                "bytes": len(stderr_bytes),
                "sha256": "sha256:" + hashlib.sha256(stderr_bytes).hexdigest(),
            },
        }
        write_json_exclusive(root / "failure.json", failure)
        raise RuntimeError(f"GPU study failed in {phase} block {block}, mode {mode}")
    if source_bundle_digest(repository_root) != args.source_bundle_digest:
        raise RuntimeError("GPU study source bundle changed during a process run")
    raw = destination.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    expected = {
        "source_revision": args.source_revision,
        "source_bundle_digest": args.source_bundle_digest,
        "model_archive_digest": args.model_archive_digest,
        "container_digest": args.container_digest,
        "expected_gpu": args.expected_gpu,
        "context": args.context,
        "max_tokens": args.max_tokens,
        "append_turns": args.append_turns,
        "served_model_digest": "sha256:" + hashlib.sha256(
            args.served_model.encode("utf-8")
        ).hexdigest(),
        "gpu_memory_utilization": args.gpu_memory_utilization,
        "server_timeout": args.server_timeout,
        "request_timeout": args.request_timeout,
    }
    validate_gpu_evidence(payload, mode, expected)
    attestation_digest = "sha256:" + hashlib.sha256(
        json.dumps(
            payload["attestation"], sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    return {
        "phase": phase, "block": block, "mode": mode,
        "path": destination.relative_to(root).as_posix(),
        "evidence_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "attestation_sha256": attestation_digest,
        "metrics": gpu_process_metrics(payload),
    }


def run_blocks(args, root, phase, start, count, environment):
    observations = []
    for block in range(start, start + count):
        order = gpu_mode_order(args.seed, phase, block)
        print(f"{phase} block {block}: {', '.join(order)}", flush=True)
        for mode in order:
            observations.append(
                run_one(args, root, phase, block, mode, environment)
            )
    return observations


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--model-archive-digest", required=True)
    parser.add_argument("--container-digest", required=True)
    parser.add_argument("--expected-gpu", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--source-bundle-digest", required=True)
    parser.add_argument("--served-model", default="brickkv-llama-3.1-8b")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--context", type=int, default=8192)
    parser.add_argument("--max-tokens", type=int, default=32)
    parser.add_argument("--append-turns", type=int, default=12)
    parser.add_argument("--server-timeout", type=int, default=1200)
    parser.add_argument("--request-timeout", type=int, default=600)
    parser.add_argument("--process-timeout", type=int, default=3600)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--extra-repetitions", type=int, default=10)
    parser.add_argument("--cv-threshold", type=float, default=0.08)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.9)
    parser.add_argument("--bootstrap-samples", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260830)
    args = parser.parse_args(argv)
    for name in (
        "context", "max_tokens", "append_turns", "server_timeout",
        "request_timeout", "process_timeout", "warmups", "repetitions",
        "extra_repetitions", "bootstrap_samples",
    ):
        if getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    if not 0.0 < args.cv_threshold < 1.0:
        parser.error("--cv-threshold must be between zero and one")
    if not 0.0 < args.gpu_memory_utilization <= 1.0:
        parser.error("--gpu-memory-utilization must be in (0, 1]")
    if not re.fullmatch(r"[A-Za-z0-9._/-]{1,128}", args.served_model):
        parser.error("--served-model must be a bounded model identifier")
    for value, label in (
        (args.model_archive_digest, "--model-archive-digest"),
        (args.container_digest, "--container-digest"),
        (args.source_bundle_digest, "--source-bundle-digest"),
    ):
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
            parser.error(f"{label} must be sha256:<64 lowercase hex>")
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", args.source_revision):
        parser.error("--source-revision must be a full lowercase Git object ID")
    return args


def main(argv=None):
    args = parse_args(argv)
    if not args.execute:
        raise SystemExit("refusing an expensive GPU run without --execute")
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite {args.output}")
    for path in (args.study, args.model):
        if not path.exists():
            raise SystemExit(f"required path does not exist: {path}")
    repository_root = Path(__file__).resolve().parents[2]
    if source_bundle_digest(repository_root) != args.source_bundle_digest:
        raise SystemExit("transferred GPU study source bundle does not match")
    args.output.mkdir(parents=True)
    environment = os.environ.copy()
    environment["VLLM_LOGGING_LEVEL"] = "INFO"
    warmups = run_blocks(
        args, args.output, "warmup", 0, args.warmups, environment
    )
    measured = run_blocks(
        args, args.output, "measure", 0, args.repetitions, environment
    )
    summary = summarize(measured)
    unstable = needs_extra_repetitions(summary, args.cv_threshold)
    if unstable:
        extra = run_blocks(
            args, args.output, "measure", args.repetitions,
            args.extra_repetitions, environment,
        )
        measured.extend(extra)
        summary = summarize(measured)
        unstable = needs_extra_repetitions(summary, args.cv_threshold)
    all_traces = sorted({trace for item in measured for trace in item["metrics"]})
    mismatches = correctness_mismatches(measured, "off", "on")
    report = {
        "schema_version": "brickkv.gpu-matrix/1",
        "statistical_unit": "one vLLM server process",
        "warmup_blocks": args.warmups,
        "measurement_blocks": len({item["block"] for item in measured}),
        "mode_order_seed": args.seed,
        "experiment_binding": {
            "source_revision": args.source_revision,
            "source_bundle_digest": args.source_bundle_digest,
            "model_archive_digest": args.model_archive_digest,
            "container_digest": args.container_digest,
            "expected_gpu": args.expected_gpu,
            "served_model_digest": "sha256:" + hashlib.sha256(
                args.served_model.encode("utf-8")
            ).hexdigest(),
            "context": args.context,
            "max_tokens": args.max_tokens,
            "append_turns": args.append_turns,
            "gpu_memory_utilization": args.gpu_memory_utilization,
        },
        "remaining_unstable_cells": unstable,
        "summary": summary,
        "apc_on_vs_off": {
            trace: paired_apc_improvement(
                measured, trace, args.bootstrap_samples, args.seed + index
            ) for index, trace in enumerate(all_traces)
        },
        "apc_correctness": {
            "passed": not mismatches,
            "mismatches": mismatches,
        },
        "publication_gate": {
            "passed": not mismatches and not unstable,
            "requirements": {
                "paired_output_digests_match": not mismatches,
                "p95_ttft_cv_at_or_below_threshold": not unstable,
            },
        },
        "observations": warmups + measured,
    }
    if source_bundle_digest(repository_root) != args.source_bundle_digest:
        raise RuntimeError("GPU study source bundle changed before publication")
    write_json_exclusive(args.output / "report.json", report)
    write_integrity_manifest(args.output)
    print(f"complete: {args.output / 'report.json'}")


if __name__ == "__main__":
    main()
