"""Synthetic vLLM prefix-cache study for one process and one GPU.

The server mode is always explicit because current vLLM releases may enable
automatic prefix caching by default. Prompts and generated text stay in memory;
the evidence contains timings, token counts, cache counters, and SHA-256 output
digests only.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

from perf.brickkv.run_matrix import write_json_exclusive


SCHEMA = "brickkv.vllm/1"
COUNTERS = (
    "vllm:prefix_cache_queries_total",
    "vllm:prefix_cache_hits_total",
    "vllm:gpu_prefix_cache_queries_total",
    "vllm:gpu_prefix_cache_hits_total",
)


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_prometheus(text: str) -> dict[str, float]:
    totals = {name: 0.0 for name in COUNTERS}
    found = set()
    for raw in text.splitlines():
        if not raw or raw.startswith("#"):
            continue
        match = re.match(r"^([^\s{]+)(?:\{[^}]*\})?\s+(\S+)$", raw)
        if not match or match.group(1) not in totals:
            continue
        try:
            value = float(match.group(2))
        except ValueError as exc:
            raise RuntimeError("vLLM prefix-cache counter is not numeric") from exc
        if not math.isfinite(value) or value < 0:
            raise RuntimeError(
                "vLLM prefix-cache counters must be finite and nonnegative"
            )
        totals[match.group(1)] += value
        found.add(match.group(1))
    modern_names = {
        "vllm:prefix_cache_queries_total", "vllm:prefix_cache_hits_total"
    }
    legacy_names = {
        "vllm:gpu_prefix_cache_queries_total",
        "vllm:gpu_prefix_cache_hits_total",
    }
    if found & modern_names:
        if not modern_names <= found:
            raise RuntimeError(
                "vLLM exposed only part of the current prefix-counter pair"
            )
        counters = {
            "queries": totals["vllm:prefix_cache_queries_total"],
            "hits": totals["vllm:prefix_cache_hits_total"],
        }
    else:
        if not legacy_names <= found:
            raise RuntimeError("vLLM prefix-cache counter pair is unavailable")
        counters = {
            "queries": totals["vllm:gpu_prefix_cache_queries_total"],
            "hits": totals["vllm:gpu_prefix_cache_hits_total"],
        }
    if counters["hits"] > counters["queries"]:
        raise RuntimeError("vLLM prefix-cache hits exceed queries")
    return counters


def parse_sse(lines, started_ns: int, cancel_after_first=False):
    parts = []
    usage = {}
    first_token_ns = None
    cancelled = False
    done = False
    finished = False
    usage_seen = False
    for raw in lines:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        value = line[5:].strip()
        if value == "[DONE]":
            done = True
            break
        chunk = json.loads(value)
        if chunk.get("error"):
            raise RuntimeError(f"vLLM stream error: {chunk['error']}")
        if chunk.get("usage"):
            usage = chunk["usage"]
            usage_seen = True
        choices = chunk.get("choices") or []
        if any(choice.get("finish_reason") is not None for choice in choices):
            finished = True
        piece = choices[0].get("delta", {}).get("content", "") if choices else ""
        if piece:
            if first_token_ns is None:
                first_token_ns = time.perf_counter_ns()
            parts.append(piece)
            if cancel_after_first:
                cancelled = True
                break
    if not cancelled:
        if not done or not finished or not usage_seen:
            raise RuntimeError(
                "vLLM stream ended without finish, usage, and [DONE] evidence"
            )
        if first_token_ns is None:
            raise RuntimeError("vLLM completed without a generated token")
        for key in ("prompt_tokens", "completion_tokens"):
            if type(usage.get(key)) is not int or usage[key] < 0:
                raise RuntimeError("vLLM stream usage is missing or invalid")
    ended_ns = time.perf_counter_ns()
    return {
        "text": "".join(parts),
        "ttft_us": (
            (first_token_ns - started_ns) // 1000
            if first_token_ns is not None else None
        ),
        "wall_us": (ended_ns - started_ns) // 1000,
        "prompt_tokens": int(usage.get("prompt_tokens", 0)),
        "generated_tokens": int(usage.get("completion_tokens", 0)),
        "cancelled": cancelled,
    }


def request_headers(api_key: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def open_request(request, timeout: float):
    # Proxy environment variables must not redirect loopback model traffic
    # outside the assigned experiment container.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return opener.open(request, timeout=timeout)


def http_text(url: str, timeout: float, api_key: str | None = None) -> str:
    request = urllib.request.Request(url, headers=request_headers(api_key))
    with open_request(request, timeout) as response:
        return response.read().decode("utf-8", "replace")


def stream_chat(base_url: str, model: str, messages: list[dict], cache_salt: str,
                max_tokens: int, timeout: float, api_key: str,
                cancel_after_first=False):
    body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0,
        "seed": 42,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
        "cache_salt": cache_salt,
    }).encode()
    request = urllib.request.Request(
        base_url + "/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json",
                 **request_headers(api_key)},
    )
    started = time.perf_counter_ns()
    with open_request(request, timeout) as response:
        result = parse_sse(response, started, cancel_after_first)
    return result


def random_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


def terminate_study(_signum, _frame):
    # Raising through the active Server context guarantees its process-group
    # teardown runs when the outer matrix terminates a timed-out study.
    raise SystemExit("GPU study terminated")


def gpu_attestation(expected: str) -> dict:
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "").strip()
    if not visible or "," in visible:
        raise RuntimeError("exactly one HTCondor-assigned CUDA_VISIBLE_DEVICES entry is required")
    command = [
        "nvidia-smi", "-i", visible,
        "--query-gpu=name,uuid,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ]
    completed = subprocess.run(
        command, capture_output=True, text=True, check=False, timeout=30
    )
    if completed.returncode != 0:
        raise RuntimeError("nvidia-smi could not attest the assigned GPU")
    rows = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if len(rows) != 1:
        raise RuntimeError(f"expected one assigned GPU, got {len(rows)}")
    fields = [field.strip() for field in rows[0].split(",")]
    if len(fields) != 4:
        raise RuntimeError("unexpected nvidia-smi attestation shape")
    name, uuid, memory_mb, driver = fields
    if name != expected:
        raise RuntimeError(f"assigned GPU {name!r} does not match {expected!r}")
    return {
        "name": name,
        "uuid_hash": sha256_text(uuid),
        "memory_mb": int(memory_mb),
        "driver_version": driver,
        "cuda_visible_devices_hash": sha256_text(visible),
    }


class Server:
    def __init__(self, args, log_path: Path):
        self.args = args
        self.log_path = log_path
        self.process = None
        self._log = None
        self.port = random_loopback_port()
        self.api_key = secrets.token_urlsafe(32)

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self):
        command = [
            "vllm", "serve", str(self.args.model),
            "--host", "127.0.0.1", "--port", str(self.port),
            "--served-model-name", self.args.served_model,
            "--dtype", "bfloat16", "--max-model-len", str(self.args.context),
            "--gpu-memory-utilization", str(self.args.gpu_memory_utilization),
            "--generation-config", "vllm",
            "--no-enable-log-requests", "--no-enable-log-outputs",
        ]
        if self.args.mode == "on":
            command.extend(("--enable-prefix-caching",
                            "--prefix-caching-hash-algo", "sha256"))
        else:
            command.append("--no-enable-prefix-caching")
        self._log = self.log_path.open("xb")
        environment = os.environ.copy()
        environment["VLLM_API_KEY"] = self.api_key
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=self._log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=environment,
        )
        try:
            deadline = time.monotonic() + self.args.server_timeout
            health = self.base_url + "/health"
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError(
                        f"vLLM exited during startup with {self.process.returncode}"
                    )
                try:
                    http_text(health, 2.0)
                    # vLLM intentionally leaves /health unauthenticated. A
                    # successful keyed /v1 call binds readiness to this run.
                    http_text(
                        self.base_url + "/v1/models", 2.0, self.api_key
                    )
                    return self
                except (OSError, urllib.error.URLError):
                    time.sleep(1.0)
            raise RuntimeError(
                "vLLM server did not become healthy before the timeout"
            )
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        if self.process is not None and self.process.poll() is None:
            if os.name == "nt":
                self.process.terminate()
            else:
                os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    self.process.kill()
                else:
                    os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=10)
        if self._log is not None:
            self._log.close()


def initial(trace):
    return [
        {"role": "system", "content": "Use only synthetic facts."},
        {"role": "user", "content": f"Summarize synthetic request 1 for {trace}."},
    ]


def traces(append_turns):
    return {
        "append_only": append_turns,
        "planning_removed": 4,
        "invalid_deleted": 4,
        "context_pruning": 4,
        "verifier_detour": 3,
        "cancellation_decode": 4,
    }


def run_workload(args, base_url, api_key):
    records = []
    for trace, steps in traces(args.append_turns).items():
        driver = initial(trace)
        verifier = [
            {"role": "system", "content": "Check only synthetic evidence."},
            {"role": "user", "content": "Verify the synthetic draft."},
        ]
        salts = {"driver": secrets.token_hex(16), "verifier": secrets.token_hex(16)}
        for step in range(steps):
            role = "verifier" if trace == "verifier_detour" and step == 1 else "driver"
            messages = verifier if role == "verifier" else driver
            if trace in ("planning_removed", "invalid_deleted") and step == 2 \
                    and len(messages) >= 6:
                del messages[3:5]
            elif trace == "context_pruning" and step == 2:
                messages[:] = [
                    {"role": "system", "content": "Use the approved synthetic summary."},
                    {"role": "user", "content": "Continue after context pruning."},
                ]
            cancel = trace == "cancellation_decode" and step == 1
            before = parse_prometheus(
                http_text(base_url + "/metrics", 10, api_key)
            )
            result = stream_chat(
                base_url, args.served_model, messages, salts[role],
                args.max_tokens, args.request_timeout, api_key, cancel,
            )
            after = parse_prometheus(
                http_text(base_url + "/metrics", 10, api_key)
            )
            query_delta = after["queries"] - before["queries"]
            hit_delta = after["hits"] - before["hits"]
            if query_delta < 0 or hit_delta < 0 or hit_delta > query_delta:
                raise RuntimeError("vLLM prefix-cache counters were not monotonic")
            text = result.pop("text")
            record = {
                "trace": trace,
                "step": step,
                "role": role,
                "mode": args.mode,
                **result,
                "output_digest": sha256_text(text),
                "prefix_queries": query_delta,
                "prefix_hits": hit_delta,
            }
            records.append(record)
            if record["cancelled"]:
                messages[-1]["content"] = "Retry the interrupted synthetic task."
                continue
            messages.append({"role": "assistant", "content": text})
            if not (trace == "verifier_detour" and role == "verifier"):
                messages.append({
                    "role": "user",
                    "content": f"Continue synthetic trace {trace} at step {step + 1}.",
                })
    return records


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--served-model", default="brickkv-llama-3.1-8b")
    parser.add_argument("--model-archive-digest", required=True)
    parser.add_argument("--container-digest", required=True)
    parser.add_argument("--expected-gpu", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--source-bundle-digest", required=True)
    parser.add_argument("--mode", choices=("off", "on"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--context", type=int, default=8192)
    parser.add_argument("--max-tokens", type=int, default=32)
    parser.add_argument("--append-turns", type=int, default=12)
    parser.add_argument("--server-timeout", type=int, default=1200)
    parser.add_argument("--request-timeout", type=int, default=600)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.9)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.model_archive_digest):
        parser.error("--model-archive-digest must be sha256:<64 lowercase hex>")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.container_digest):
        parser.error("--container-digest must be sha256:<64 lowercase hex>")
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", args.source_revision):
        parser.error("--source-revision must be a full lowercase Git object ID")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.source_bundle_digest):
        parser.error("--source-bundle-digest must be sha256:<64 lowercase hex>")
    if not args.model.exists():
        parser.error(f"model path does not exist: {args.model}")
    if args.output.exists():
        parser.error(f"refusing to overwrite {args.output}")
    if not re.fullmatch(r"[A-Za-z0-9._/-]{1,128}", args.served_model):
        parser.error("--served-model must be a bounded model identifier")
    for name in (
        "context", "max_tokens", "append_turns", "server_timeout",
        "request_timeout",
    ):
        if getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    if not 0.0 < args.gpu_memory_utilization <= 1.0:
        parser.error("--gpu-memory-utilization must be greater than zero and at most one")
    return args


def main(argv=None):
    args = parse_args(argv)
    signal.signal(signal.SIGTERM, terminate_study)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    gpu = gpu_attestation(args.expected_gpu)
    try:
        vllm_version = importlib.metadata.version("vllm")
    except importlib.metadata.PackageNotFoundError as exc:
        raise SystemExit("vLLM is not installed in this container") from exc
    server_log = args.output.with_suffix(".server.log")
    with Server(args, server_log) as server:
        base_url = server.base_url
        models = json.loads(http_text(
            base_url + "/v1/models", 10, server.api_key
        ))
        available = [item.get("id") for item in models.get("data", [])]
        if available != [args.served_model]:
            raise RuntimeError(
                "vLLM did not advertise exactly the reviewed model ID"
            )
        records = run_workload(args, base_url, server.api_key)
    evidence = {
        "schema_version": SCHEMA,
        "status": "complete",
        "mode": args.mode,
        "attestation": {
            "source_revision": args.source_revision,
            "source_bundle_digest": args.source_bundle_digest,
            "model_archive_digest": args.model_archive_digest,
            "container_digest": args.container_digest,
            "vllm_version": vllm_version,
            "gpu": gpu,
        },
        "configuration": {
            "context": args.context,
            "max_tokens": args.max_tokens,
            "append_turns": args.append_turns,
            "prefix_caching": args.mode == "on",
            "prefix_hash_algorithm": "sha256" if args.mode == "on" else None,
            "served_model_digest": sha256_text(args.served_model),
            "endpoint_binding": "random_loopback_authenticated_v1",
            "gpu_memory_utilization": args.gpu_memory_utilization,
            "server_timeout_s": args.server_timeout,
            "request_timeout_s": args.request_timeout,
            "dtype": "bfloat16",
            "generation_config": "vllm",
            "temperature": 0,
            "seed": 42,
            "workload_version": "brickkv.synthetic-agent-traces/1",
        },
        "records": records,
    }
    write_json_exclusive(args.output, evidence)
    print(f"wrote {len(records)} records to {args.output}")


if __name__ == "__main__":
    main()
