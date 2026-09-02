"""Process-level vLLM APC matrix for one HTCondor-assigned GPU."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import signal
import statistics
import subprocess
import sys
import time
from typing import Optional

from perf.brickkv.run_matrix import (
    coefficient_of_variation,
    correctness_mismatches,
    needs_extra_repetitions,
    percentile,
    write_json_exclusive,
    write_integrity_manifest,
)
from perf.brickkv.source_bundle import (
    source_bundle_digest,
    source_bundle_manifest,
)
from perf.brickkv.gpu_prefix_study import (
    ENDPOINT_BINDING,
    PROCESS_CONTAINMENT,
    valid_container_image,
)


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
    "container_digest", "container_image", "vllm_version", "gpu",
}
GPU_FIELDS = {
    "name", "uuid_hash", "memory_mb", "driver_version",
    "cuda_visible_devices_hash",
}
CONFIGURATION_FIELDS = {
    "context", "max_tokens", "append_turns", "prefix_caching",
    "prefix_hash_algorithm", "served_model_digest", "endpoint_binding",
    "process_containment",
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
        "container_digest", "container_image",
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
        "process_containment": PROCESS_CONTAINMENT,
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
        if not expected_cancel and (
            record["prompt_tokens"] <= 0 or record["generated_tokens"] <= 0
        ):
            raise ValueError("completed GPU record has no measured tokens")
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
    expected_sequence = [
        (trace, step)
        for trace, count in expected_steps.items()
        for step in range(count)
    ]
    actual_sequence = [(record["trace"], record["step"]) for record in records]
    if actual_sequence != expected_sequence:
        raise ValueError("GPU evidence records are not in canonical trace-step order")
    total_queries = sum(float(record["prefix_queries"]) for record in records)
    total_hits = sum(float(record["prefix_hits"]) for record in records)
    append_hits = sum(
        float(record["prefix_hits"])
        for record in records if record["trace"] == "append_only"
    )
    if mode == "off" and total_hits != 0:
        raise ValueError("APC-off evidence contains prefix-cache hits")
    if mode == "on" and total_queries <= 0:
        raise ValueError("APC-on evidence has no positive prefix-query activity")
    if mode == "on" and append_hits <= 0:
        raise ValueError("APC-on append-only evidence has no reusable-prefix hit")


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


def apc_activity_checks(observations):
    off = [item for item in observations if item["mode"] == "off"]
    on = [item for item in observations if item["mode"] == "on"]

    def total(item, field):
        return sum(
            float(metrics[field]) for metrics in item["metrics"].values()
        )

    return {
        "off_mode_zero_hits": bool(off) and all(
            total(item, "prefix_hits") == 0 for item in off
        ),
        "on_mode_positive_queries": bool(on) and all(
            total(item, "prefix_queries") > 0 for item in on
        ),
        "append_only_on_positive_hits": bool(on) and all(
            float(item["metrics"]["append_only"]["prefix_hits"]) > 0
            for item in on
        ),
    }


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


def process_group_alive(process_group: int) -> bool:
    if os.name == "nt":
        return False
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def signal_process_group(process_group: int, signal_number: int) -> bool:
    """Signal an existing POSIX group; report a concurrent clean exit."""
    try:
        os.killpg(process_group, signal_number)
    except ProcessLookupError:
        return False
    return True


def enable_linux_child_subreaper() -> None:
    """Adopt daemonized study descendants so they cannot escape cleanup."""
    if sys.platform != "linux":
        raise RuntimeError("GPU process containment requires Linux")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    value = ctypes.c_int()
    if libc.prctl(37, ctypes.byref(value), 0, 0, 0) != 0:  # PR_GET_CHILD_SUBREAPER
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    if value.value != 1:
        raise RuntimeError("Linux refused the child-subreaper containment state")


def linux_descendants(parent: int) -> set[int]:
    """Return the live /proc descendant closure for one Linux process."""
    if sys.platform != "linux":
        return set()
    parents = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "stat").read_text(
                encoding="utf-8", errors="replace"
            )
            end = raw.rfind(")")
            if end < 0:
                continue
            fields = raw[end + 2:].split()
            if len(fields) < 2:
                continue
            parents[int(entry.name)] = int(fields[1])
        except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError):
            continue
    descendants = set()
    frontier = {parent}
    while frontier:
        children = {
            pid for pid, process_parent in parents.items()
            if process_parent in frontier and pid not in descendants
        }
        descendants.update(children)
        frontier = children
    return descendants


def reap_adopted_children() -> None:
    while True:
        try:
            pid, _status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return


def signal_linux_descendants(
    supervisor: int, signal_number: int
) -> list[BaseException]:
    """Signal every current descendant through stable Linux pidfds.

    One inaccessible process must not prevent the remaining stable handles from
    being signalled. The caller receives every non-race failure and reports it
    only after the full cleanup sweep has run.
    """
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise RuntimeError("GPU containment requires Linux pidfd support")
    failures: list[BaseException] = []
    for pid in linux_descendants(supervisor):
        try:
            descriptor = os.pidfd_open(pid, 0)
        except ProcessLookupError:
            continue
        except (PermissionError, OSError) as exc:
            failures.append(exc)
            continue
        try:
            # Recheck lineage after opening the stable process handle. This
            # prevents PID reuse between /proc enumeration and signaling from
            # targeting a process that is no longer in this study tree.
            if pid in linux_descendants(supervisor):
                signal.pidfd_send_signal(descriptor, signal_number)
        except ProcessLookupError:
            pass
        except (PermissionError, OSError) as exc:
            failures.append(exc)
        finally:
            try:
                os.close(descriptor)
            except OSError as exc:
                failures.append(exc)
    return failures


def cleanup_process_group(process_group: int, grace: float) -> bool:
    residual = process_group_alive(process_group)
    if not residual:
        return False
    deadline = time.monotonic() + grace
    while process_group_alive(process_group) and time.monotonic() < deadline:
        signal_process_group(process_group, signal.SIGTERM)
        reap_adopted_children()
        time.sleep(0.05)
    deadline = time.monotonic() + 10.0
    while process_group_alive(process_group) and time.monotonic() < deadline:
        signal_process_group(process_group, signal.SIGKILL)
        reap_adopted_children()
        time.sleep(0.05)
    if process_group_alive(process_group):
        raise RuntimeError("GPU study process-group containment did not empty")
    return True


def cleanup_linux_descendants(supervisor: int, grace: float) -> bool:
    """Terminate every descendant, including workers that changed sessions."""
    descendants = linux_descendants(supervisor)
    if not descendants:
        reap_adopted_children()
        return False
    failures: list[BaseException] = []
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        failures.extend(signal_linux_descendants(supervisor, signal.SIGTERM))
        reap_adopted_children()
        if not linux_descendants(supervisor):
            break
        time.sleep(0.05)
    if linux_descendants(supervisor):
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            failures.extend(signal_linux_descendants(supervisor, signal.SIGKILL))
            reap_adopted_children()
            if not linux_descendants(supervisor):
                break
            time.sleep(0.05)
    survivors = linux_descendants(supervisor)
    if survivors or failures:
        message = (
            "GPU study descendant containment did not empty"
            if survivors else
            f"GPU study descendant containment had {len(failures)} signal failure(s)"
        )
        error = RuntimeError(message)
        if failures:
            raise error from failures[0]
        raise error
    return True


def communicate_contained(process, timeout: float, grace: float = 60.0,
                          supervisor: Optional[int] = None):
    """Collect one study and leave no process or daemonized descendant."""
    if sys.platform == "linux" and supervisor is None:
        raise RuntimeError("Linux containment requires an explicit subreaper PID")
    stdout = ""
    stderr = ""
    timed_out = False
    primary_error = None
    cleanup_errors: list[BaseException] = []
    try:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == "nt":
                process.terminate()
            else:
                signal_process_group(process.pid, signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=grace)
            except subprocess.TimeoutExpired:
                # Cleanup is centralized in finally so even decode errors,
                # interrupts, and OS failures take the same containment path.
                pass
    except BaseException as exc:
        primary_error = exc
    finally:
        residual_group = False
        residual_descendants = False
        try:
            if os.name != "nt":
                residual_group = process_group_alive(process.pid)
        except BaseException as exc:
            residual_group = True
            cleanup_errors.append(exc)
        try:
            if sys.platform == "linux":
                residual_descendants = bool(linux_descendants(supervisor))
        except BaseException as exc:
            residual_descendants = True
            cleanup_errors.append(exc)
        try:
            if process.poll() is None:
                if os.name == "nt":
                    process.terminate()
                else:
                    signal_process_group(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=grace)
                except subprocess.TimeoutExpired:
                    if os.name == "nt":
                        process.kill()
                    else:
                        signal_process_group(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
        except BaseException as exc:
            cleanup_errors.append(exc)
        # Captured pipes may still be held by a daemonized descendant. The
        # evidence is already a failed run, so close the readers before sweeping
        # instead of allowing inherited descriptors to hang us.
        if primary_error is not None or timed_out:
            for stream in (process.stdout, process.stderr):
                if stream is None:
                    continue
                try:
                    stream.close()
                except BaseException as exc:
                    cleanup_errors.append(exc)
            stdout, stderr = "", ""
        # These cleanup domains are deliberately independent. A failed group
        # operation must never skip the Linux descendant sweep.
        if os.name != "nt":
            try:
                residual_group = cleanup_process_group(
                    process.pid, grace
                ) or residual_group
            except BaseException as exc:
                residual_group = True
                cleanup_errors.append(exc)
        if sys.platform == "linux":
            try:
                residual_descendants = cleanup_linux_descendants(
                    supervisor, grace
                ) or residual_descendants
            except BaseException as exc:
                residual_descendants = True
                cleanup_errors.append(exc)
    if cleanup_errors:
        cleanup_error = RuntimeError(
            f"GPU study containment had {len(cleanup_errors)} cleanup failure(s)"
        )
        if primary_error is not None:
            raise cleanup_error from primary_error
        raise cleanup_error from cleanup_errors[0]
    if primary_error is not None:
        raise primary_error
    return (
        stdout, stderr, timed_out, residual_group, residual_descendants
    )


def run_one(args, root, phase, block, mode, environment):
    repository_root = Path(__file__).resolve().parents[2]
    if sys.platform == "linux" and linux_descendants(os.getpid()):
        raise RuntimeError("GPU matrix has a residual descendant before a run")
    if source_bundle_digest(
        repository_root, args.source_revision
    ) != args.source_bundle_digest:
        raise RuntimeError("GPU study source bundle changed before a process run")
    destination = root / "raw" / phase / f"block-{block:03d}" / f"{mode}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise RuntimeError(f"refusing to overwrite {destination}")
    command = [
        sys.executable, str(args.study), "--model", str(args.model),
        "--model-archive-digest", args.model_archive_digest,
        "--container-digest", args.container_digest,
        "--container-image", args.container_image,
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
        start_new_session=(os.name != "nt"),
    )
    stdout, stderr, timed_out, residual_group, residual_descendants = \
        communicate_contained(
            process, args.process_timeout, supervisor=os.getpid()
        )
    if process.returncode or timed_out or residual_group or residual_descendants:
        stdout_bytes = stdout.encode("utf-8", errors="replace")
        stderr_bytes = stderr.encode("utf-8", errors="replace")
        failure = {
            "phase": phase, "block": block, "mode": mode,
            "returncode": process.returncode,
            "timed_out": timed_out,
            "residual_process_group": residual_group,
            "residual_descendants": residual_descendants,
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
    if source_bundle_digest(
        repository_root, args.source_revision
    ) != args.source_bundle_digest:
        raise RuntimeError("GPU study source bundle changed during a process run")
    raw = destination.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    expected = {
        "source_revision": args.source_revision,
        "source_bundle_digest": args.source_bundle_digest,
        "model_archive_digest": args.model_archive_digest,
        "container_digest": args.container_digest,
        "container_image": args.container_image,
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
    parser.add_argument("--container-image", required=True)
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
    if not valid_container_image(args.container_image, args.container_digest):
        parser.error(
            "--container-image must be a credential-free docker:// reference "
            "pinned to --container-digest"
        )
    return args


def main(argv=None):
    args = parse_args(argv)
    if not args.execute:
        raise SystemExit("refusing an expensive GPU run without --execute")
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite {args.output}")
    enable_linux_child_subreaper()
    if linux_descendants(os.getpid()):
        raise SystemExit("GPU matrix started with an unexpected child process")
    for path in (args.study, args.model):
        if not path.exists():
            raise SystemExit(f"required path does not exist: {path}")
    repository_root = Path(__file__).resolve().parents[2]
    source_manifest = source_bundle_manifest(
        repository_root, args.source_revision
    )
    if source_manifest["source_bundle_digest"] != args.source_bundle_digest:
        raise SystemExit("transferred GPU study source bundle does not match")
    args.output.mkdir(parents=True)
    environment = os.environ.copy()
    environment["VLLM_LOGGING_LEVEL"] = "INFO"
    environment["BRICKKV_PROCESS_CONTAINMENT"] = PROCESS_CONTAINMENT
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
    activity = apc_activity_checks(measured)
    activity_passed = all(activity.values())
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
            "container_image": args.container_image,
            "source_manifest": source_manifest,
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
        "apc_activity": {
            "passed": activity_passed,
            "requirements": activity,
        },
        "publication_gate": {
            "passed": not mismatches and not unstable and activity_passed,
            "requirements": {
                "paired_output_digests_match": not mismatches,
                "p95_ttft_cv_at_or_below_threshold": not unstable,
                "apc_activity_demonstrated": activity_passed,
            },
        },
        "observations": warmups + measured,
    }
    if source_bundle_manifest(
        repository_root, args.source_revision
    ) != source_manifest:
        raise RuntimeError("GPU study source bundle changed before publication")
    write_json_exclusive(args.output / "report.json", report)
    write_integrity_manifest(args.output)
    print(f"complete: {args.output / 'report.json'}")


if __name__ == "__main__":
    main()
