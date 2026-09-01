"""Measure BrickKV trace behavior through an attested loopback GenieX server.

This runner exists for Windows systems where application-control policy permits
the reviewed GenieX server but rejects an unsigned diagnostic executable. It
does not bypass that policy. Inputs are fixed synthetic text, and evidence
retains no prompt or generated content.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import secrets
import time

from perf.brickkv.geniex_managed_smoke import (
    CACHE_FIELDS,
    HARDWARE_PATTERN,
    MODEL_PATTERN,
    REVISION_PATTERN,
    SHA256_PATTERN,
    VERSION_PATTERN,
    WindowsServerBinding,
    _architecture,
    artifact_manifest,
    loopback_target,
    model_parts,
    resolve_bound_model_artifact,
)
from perf.brickkv.run_matrix import sha256_file, write_json_exclusive
from perf.brickkv.source_bundle import source_bundle_manifest, verify_git_revision


SCHEMA = "brickkv.server-replay/2"
CHAT_PATH = "/v1/chat/completions"
MAX_SSE_LINE_BYTES = 1024 * 1024
MAX_STREAM_BYTES = 8 * 1024 * 1024
TRACE_ORDER = (
    "append_only",
    "planning_removed",
    "invalid_deleted",
    "context_pruning",
    "verifier_detour",
    "cancellation_decode",
)
MODES = ("reset", "legacy-test", "managed")
SMOKE_SOURCE_FILES = tuple(sorted((
    "perf/brickkv/geniex_managed_smoke.py",
    "perf/brickkv/server_equivalence.py",
    "perf/brickkv/geniex_server_replay.py",
    "perf/brickkv/run_matrix.py",
    "perf/brickkv/source_bundle.py",
)))
FORBIDDEN_EVIDENCE_KEYS = frozenset({
    "content",
    "full_text",
    "generated_text",
    "messages",
    "prompt",
})


def expected_cache_decision(
    mode: str, trace: str, step: int, prior_reusable: bool = True
) -> tuple[str, str]:
    if trace == "cancellation_decode" and step == 1:
        return "aborted", "client_disconnect"
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


def validate_cache_record(
    value: object,
    mode: str,
    trace: str,
    step: int,
    *,
    prior_reusable: bool,
    expected_reusable: bool,
) -> dict:
    expected_status, expected_reason = expected_cache_decision(
        mode, trace, step, prior_reusable
    )
    if mode != "managed":
        if value is not None:
            raise RuntimeError("unmanaged streaming response exposed cache metadata")
        return {
            "status": expected_status,
            "reason": expected_reason,
            "revision": "",
            "reusable": mode == "legacy-test",
        }
    if not isinstance(value, dict) or set(value) != CACHE_FIELDS:
        raise RuntimeError("managed streaming response has an invalid cache record")
    if value.get("mode") != "managed":
        raise RuntimeError("managed streaming response has an invalid cache mode")
    if (
        value.get("status") != expected_status
        or value.get("reason") != expected_reason
    ):
        raise RuntimeError(
            f"unexpected cache decision for {trace} step {step}: "
            f"{value.get('status')}/{value.get('reason')}; expected "
            f"{expected_status}/{expected_reason}"
        )
    revision = value.get("revision")
    if not isinstance(revision, str) or not SHA256_PATTERN.fullmatch(revision):
        raise RuntimeError("managed streaming response has an invalid revision")
    if value.get("reusable") is not expected_reusable:
        raise RuntimeError("managed streaming response has invalid reusable state")
    return {
        "status": expected_status,
        "reason": expected_reason,
        "revision": revision,
        "reusable": expected_reusable,
    }


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RuntimeError(f"stream returned invalid {label}")
    return value


def _stream_usage(value: object) -> dict:
    if not isinstance(value, dict):
        raise RuntimeError("stream returned invalid usage")
    prompt_tokens = _positive_integer(value.get("prompt_tokens"), "prompt_tokens")
    completion_tokens = _positive_integer(
        value.get("completion_tokens"), "completion_tokens"
    )
    total_tokens = _positive_integer(value.get("total_tokens"), "total_tokens")
    if total_tokens != prompt_tokens + completion_tokens:
        raise RuntimeError("stream returned inconsistent token accounting")
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def consume_sse(
    response,
    *,
    mode: str,
    trace: str,
    step: int,
    started_ns: int,
    cancel_after_chunks: int,
    prior_reusable: bool = True,
    now_ns=time.perf_counter_ns,
) -> dict:
    """Consume one bounded GenieX SSE response without retaining it in evidence."""
    total_bytes = 0
    output_parts = []
    output_chunks = 0
    first_token_ns = None
    last_token_ns = None
    finish_reason = None
    cache_value = None
    usage = None
    done = False
    while True:
        line = response.readline(MAX_SSE_LINE_BYTES + 1)
        if not line:
            break
        total_bytes += len(line)
        if len(line) > MAX_SSE_LINE_BYTES:
            raise RuntimeError("GenieX SSE line exceeded the one MiB ceiling")
        if total_bytes > MAX_STREAM_BYTES:
            raise RuntimeError("GenieX stream exceeded the eight MiB ceiling")
        stripped = line.strip()
        if not stripped or stripped.startswith(b":"):
            continue
        if not stripped.startswith(b"data:"):
            raise RuntimeError("GenieX stream contained a non-data SSE field")
        data = stripped[5:].strip()
        if data == b"[DONE]":
            done = True
            break
        try:
            chunk = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("GenieX stream contained invalid JSON") from error
        if not isinstance(chunk, dict):
            raise RuntimeError("GenieX stream chunk was not an object")
        if "error" in chunk:
            raise RuntimeError("GenieX stream returned an error event")
        if not set(chunk).issubset({"object", "choices", "usage", "geniex_cache"}):
            raise RuntimeError("GenieX stream chunk contained unreviewed fields")
        choices = chunk.get("choices")
        if not isinstance(choices, list):
            raise RuntimeError("GenieX stream chunk has invalid choices")
        if chunk.get("usage") is not None:
            if usage is not None or choices:
                raise RuntimeError("GenieX stream has an invalid usage chunk")
            usage = _stream_usage(chunk["usage"])
        if chunk.get("geniex_cache") is not None:
            if cache_value is not None:
                raise RuntimeError("GenieX stream returned cache metadata twice")
            cache_value = chunk["geniex_cache"]
        for choice in choices:
            if not isinstance(choice, dict):
                raise RuntimeError("GenieX stream choice was not an object")
            reason = choice.get("finish_reason")
            if reason is not None:
                if finish_reason is not None or not isinstance(reason, str):
                    raise RuntimeError("GenieX stream has an invalid finish reason")
                finish_reason = reason
            delta = choice.get("delta", {})
            if not isinstance(delta, dict):
                raise RuntimeError("GenieX stream choice has an invalid delta")
            if not set(delta).issubset(
                {"role", "content", "reasoning_content", "tool_calls"}
            ):
                raise RuntimeError("GenieX stream delta contained unreviewed fields")
            if delta.get("role") not in {None, "", "assistant"}:
                raise RuntimeError("GenieX stream delta returned an unexpected role")
            if delta.get("tool_calls"):
                raise RuntimeError("synthetic replay unexpectedly produced a tool call")
            reasoning = delta.get("reasoning_content", "")
            if reasoning not in {None, ""}:
                raise RuntimeError("non-inline reasoning is outside replay version 1")
            piece = delta.get("content", "")
            if piece is None:
                piece = ""
            if not isinstance(piece, str):
                raise RuntimeError("GenieX stream returned non-text output")
            if piece:
                timestamp = now_ns()
                if first_token_ns is None:
                    first_token_ns = timestamp
                last_token_ns = timestamp
                output_parts.append(piece)
                output_chunks += 1
                if cancel_after_chunks and output_chunks >= cancel_after_chunks:
                    ended_ns = now_ns()
                    output = "".join(output_parts)
                    return {
                        "cancelled": True,
                        "ttft_us": max(1, (first_token_ns - started_ns) // 1000),
                        "decode_stream_us": max(
                            1, (last_token_ns - first_token_ns) // 1000
                        ),
                        "wall_us": max(1, (ended_ns - started_ns) // 1000),
                        "prompt_tokens": 0,
                        "generated_tokens": 0,
                        "observed_output_chunks": output_chunks,
                        "finish_reason": "client_disconnect",
                        "cache": {
                            "status": "aborted",
                            "reason": "client_disconnect",
                            "revision": "",
                            "reusable": False,
                        },
                        "output_digest": "sha256:" + hashlib.sha256(
                            output.encode("utf-8")
                        ).hexdigest(),
                        "stream_bytes": total_bytes,
                    }
    ended_ns = now_ns()
    if not done:
        raise RuntimeError("GenieX stream ended without [DONE]")
    if first_token_ns is None or last_token_ns is None:
        raise RuntimeError("GenieX stream completed without generated text")
    if finish_reason not in {"stop", "length"}:
        raise RuntimeError("GenieX stream returned an unsupported finish reason")
    if usage is None:
        raise RuntimeError("GenieX stream omitted usage")
    cache = validate_cache_record(
        cache_value,
        mode,
        trace,
        step,
        prior_reusable=prior_reusable,
        expected_reusable=finish_reason == "stop",
    )
    output = "".join(output_parts)
    return {
        "cancelled": False,
        "ttft_us": max(1, (first_token_ns - started_ns) // 1000),
        "decode_stream_us": max(1, (last_token_ns - first_token_ns) // 1000),
        "wall_us": max(1, (ended_ns - started_ns) // 1000),
        "prompt_tokens": usage["prompt_tokens"],
        "generated_tokens": usage["completion_tokens"],
        "observed_output_chunks": output_chunks,
        "finish_reason": finish_reason,
        "cache": cache,
        "output_digest": "sha256:" + hashlib.sha256(
            output.encode("utf-8")
        ).hexdigest(),
        "stream_bytes": total_bytes,
        "output": output,
    }


class GenieXStreamingClient:
    def __init__(
        self,
        origin: str,
        model: str,
        timeout: float,
        server_binding: WindowsServerBinding,
    ):
        self.host, self.port = loopback_target(origin)
        model_parts(model)
        self.model = model
        self.timeout = timeout
        self.server_binding = server_binding

    def reset_model(self) -> None:
        """Reset the one mutable server handle without generating output."""
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "system", "content": "Synthetic warm-up."}],
                "compute": "npu",
                "stream": False,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.server_binding.verify()
        connection = http.client.HTTPConnection(
            self.host, self.port, timeout=self.timeout
        )
        try:
            connection.request(
                "POST",
                CHAT_PATH,
                body=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            body = response.read(1025)
            if response.status != 200 or len(body) > 1024:
                raise RuntimeError(
                    "GenieX model reset did not return one bounded successful response"
                )
            if body.strip() not in {b"", b"null"}:
                raise RuntimeError("GenieX model reset returned an unexpected body")
        finally:
            connection.close()
        self.server_binding.verify_runtime()

    def stream(
        self,
        messages: list[dict],
        *,
        mode: str,
        trace: str,
        step: int,
        session: str,
        parent: str,
        max_tokens: int,
        cancel_after_chunks: int = 0,
        prior_reusable: bool = True,
    ) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Connection": "close",
        }
        if mode == "legacy-test":
            headers["GenieX-KeepCache"] = "true"
        elif mode == "managed":
            headers["GenieX-Cache-Session"] = session
            if parent:
                headers["GenieX-Cache-Parent"] = parent
        payload = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "max_completion_tokens": max_tokens,
                "temperature": 0,
                "seed": 42,
                "enable_think": False,
                "compute": "npu",
                "stream": True,
                "stream_options": {"include_usage": True},
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.server_binding.verify()
        connection = http.client.HTTPConnection(
            self.host, self.port, timeout=self.timeout
        )
        started_ns = time.perf_counter_ns()
        try:
            connection.request("POST", CHAT_PATH, body=payload, headers=headers)
            response = connection.getresponse()
            if mode == "managed" and response.getheader(
                "GenieX-Cache-Protocol"
            ) != "2":
                raise RuntimeError("GenieX did not prove managed-cache protocol 2")
            if response.status != 200:
                body = response.read(MAX_SSE_LINE_BYTES + 1)
                raise RuntimeError(
                    f"GenieX streaming request returned HTTP {response.status} "
                    f"with {len(body)} bounded response bytes"
                )
            media_type = response.getheader("Content-Type", "").split(";", 1)[0]
            if media_type != "text/event-stream":
                raise RuntimeError("GenieX streaming request returned another media type")
            result = consume_sse(
                response,
                mode=mode,
                trace=trace,
                step=step,
                started_ns=started_ns,
                cancel_after_chunks=cancel_after_chunks,
                prior_reusable=prior_reusable,
            )
        finally:
            connection.close()
        if result["cancelled"]:
            time.sleep(1.5)
            self.server_binding.verify()
        else:
            self.server_binding.verify_runtime()
        return result


def windows_process_working_set(pid: int) -> int:
    if os.name != "nt":
        raise RuntimeError("server working-set attestation requires Windows")

    class ProcessMemoryCountersEx(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("page_fault_count", wintypes.DWORD),
            ("peak_working_set_size", ctypes.c_size_t),
            ("working_set_size", ctypes.c_size_t),
            ("quota_peak_paged_pool_usage", ctypes.c_size_t),
            ("quota_paged_pool_usage", ctypes.c_size_t),
            ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
            ("quota_non_paged_pool_usage", ctypes.c_size_t),
            ("pagefile_usage", ctypes.c_size_t),
            ("peak_pagefile_usage", ctypes.c_size_t),
            ("private_usage", ctypes.c_size_t),
        ]

    process_query_information = 0x0400
    process_vm_read = 0x0010
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    psapi.GetProcessMemoryInfo.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(ProcessMemoryCountersEx),
        wintypes.DWORD,
    )
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(
        process_query_information | process_vm_read, False, pid
    )
    if not handle:
        raise RuntimeError(f"cannot inspect working set for process {pid}")
    try:
        counters = ProcessMemoryCountersEx()
        counters.cb = ctypes.sizeof(ProcessMemoryCountersEx)
        if not psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.cb
        ):
            raise RuntimeError(f"cannot read working set for process {pid}")
        if counters.working_set_size <= 0:
            raise RuntimeError("server process reported an empty working set")
        return int(counters.working_set_size)
    finally:
        kernel32.CloseHandle(handle)


def initial_messages(trace: str) -> list[dict]:
    if trace not in TRACE_ORDER:
        raise ValueError("unknown synthetic trace")
    return [
        {
            "role": "system",
            "content": "Reply with only the exact synthetic marker requested.",
        },
        {
            "role": "user",
            "content": f"Reply exactly with ACK_{trace}_1.",
        },
    ]


def next_user(trace: str, step: int) -> str:
    if trace not in TRACE_ORDER or isinstance(step, bool) or step < 0:
        raise ValueError("invalid synthetic trace step")
    return f"Reply exactly with ACK_{trace}_{step + 2}."


def _trace_steps(trace: str, append_turns: int) -> int:
    if trace == "append_only":
        return append_turns
    if trace == "verifier_detour":
        return 3
    return 4


def _record_result(
    result: dict,
    *,
    mode: str,
    trace: str,
    role: str,
    step: int,
    working_set_bytes: int,
    prior_reusable: bool,
) -> dict:
    expected_status, expected_reason = expected_cache_decision(
        mode, trace, step, prior_reusable
    )
    cache = result["cache"]
    if (cache["status"], cache["reason"]) != (expected_status, expected_reason):
        raise RuntimeError("stream result and trace cache decision disagree")
    for field in ("ttft_us", "decode_stream_us", "wall_us", "observed_output_chunks"):
        value = result[field]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise RuntimeError(f"stream returned invalid measurement {field}")
    prompt_tokens = result["prompt_tokens"]
    if result["cancelled"]:
        if (
            prompt_tokens != 0
            or result["generated_tokens"] != 0
            or result["finish_reason"] != "client_disconnect"
        ):
            raise RuntimeError("cancelled stream returned an invalid terminal state")
    else:
        for field in ("prompt_tokens", "generated_tokens"):
            value = result[field]
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise RuntimeError(
                    f"completed stream returned invalid {field} accounting"
                )
    if result["wall_us"] < result["ttft_us"]:
        raise RuntimeError("stream wall time is smaller than TTFT")
    if not SHA256_PATTERN.fullmatch(result["output_digest"]):
        raise RuntimeError("stream returned an invalid output digest")
    if working_set_bytes <= 0:
        raise RuntimeError("server process reported an invalid working set")
    return {
        "trace": trace,
        "mode": mode,
        "role": role,
        "step": step,
        "cancelled": result["cancelled"],
        "cache_status": cache["status"],
        "cache_reason": cache["reason"],
        "revision": cache["revision"],
        "reusable": cache["reusable"],
        "ttft_us": result["ttft_us"],
        "decode_stream_us": result["decode_stream_us"],
        "wall_us": result["wall_us"],
        "prompt_tokens": prompt_tokens,
        "generated_tokens": result["generated_tokens"],
        "observed_output_chunks": result["observed_output_chunks"],
        "working_set_bytes": working_set_bytes,
        "finish_reason": result["finish_reason"],
        "output_digest": result["output_digest"],
        "stream_bytes": result["stream_bytes"],
    }


def run_trace(
    client: GenieXStreamingClient,
    *,
    mode: str,
    trace: str,
    append_turns: int,
    max_tokens: int,
    cancel_after_chunks: int,
) -> list[dict]:
    """Run one fixed synthetic trace from a clean server cache state."""
    if mode not in MODES or trace not in TRACE_ORDER:
        raise ValueError("unsupported replay mode or trace")
    client.reset_model()
    sessions = {
        "driver": secrets.token_hex(16),
        "verifier": secrets.token_hex(16),
    }
    parents = {"driver": "", "verifier": ""}
    reusable = {"driver": True, "verifier": True}
    transcripts = {
        "driver": initial_messages(trace),
        "verifier": [
            {"role": "system", "content": "Reply with only the requested marker."},
            {
                "role": "user",
                "content": "Reply exactly with ACK_verifier.",
            },
        ],
    }
    records = []
    for step in range(_trace_steps(trace, append_turns)):
        role = "verifier" if trace == "verifier_detour" and step == 1 else "driver"
        messages = transcripts[role]
        if (
            trace in {"planning_removed", "invalid_deleted"}
            and step == 2
            and len(messages) >= 6
        ):
            del messages[3:5]
        elif trace == "context_pruning" and step == 2:
            messages[:] = [
                {
                    "role": "system",
                    "content": "Reply with only the exact synthetic marker requested.",
                },
                {
                    "role": "user",
                    "content": "Reply exactly with ACK_context_pruned.",
                },
            ]

        cancel = trace == "cancellation_decode" and step == 1
        if cancel:
            messages[-1]["content"] = (
                "Write the synthetic integers from one through sixty in words."
            )
        prior_reusable = reusable[role]
        result = client.stream(
            messages,
            mode=mode,
            trace=trace,
            step=step,
            session=sessions[role],
            parent=parents[role],
            max_tokens=max_tokens,
            cancel_after_chunks=cancel_after_chunks if cancel else 0,
            prior_reusable=prior_reusable,
        )
        output = result.pop("output", "")
        if result["cancelled"] != cancel:
            raise RuntimeError("cancellation trace did not exercise the disconnect path")
        records.append(
            _record_result(
                result,
                mode=mode,
                trace=trace,
                role=role,
                step=step,
                working_set_bytes=windows_process_working_set(
                    client.server_binding.pid
                ),
                prior_reusable=prior_reusable,
            )
        )

        if cancel:
            if mode == "legacy-test":
                # Raw KeepCache has no transaction abort. Reset it explicitly so
                # the comparison does not carry a partial decode into the retry.
                client.reset_model()
            messages[-1]["content"] = (
                "Reply exactly with ACK_cancellation_recovered."
            )
            continue

        if not output:
            raise RuntimeError("completed replay step produced empty output")
        if mode == "managed":
            parents[role] = result["cache"]["revision"]
            reusable[role] = result["cache"]["reusable"]
        messages.append({"role": "assistant", "content": output})
        if not (trace == "verifier_detour" and role == "verifier"):
            messages.append({"role": "user", "content": next_user(trace, step)})
    return records


def _reject_forbidden_evidence_keys(value: object, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_EVIDENCE_KEYS:
                raise RuntimeError(f"evidence contains forbidden key {path}.{key}")
            _reject_forbidden_evidence_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_evidence_keys(child, f"{path}[{index}]")


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--server", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-role", choices=("smoke", "final-study"), required=True)
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument("--trace", choices=TRACE_ORDER + ("all",), default="all")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--geniex-revision", required=True)
    parser.add_argument("--runtime-version", required=True)
    parser.add_argument("--hardware-label", required=True)
    parser.add_argument("--model-artifact", type=Path, required=True)
    parser.add_argument("--geniex-cli", type=Path, required=True)
    parser.add_argument("--geniex-data-dir", type=Path, required=True)
    parser.add_argument(
        "--runtime-artifact", type=Path, action="append", required=True
    )
    parser.add_argument("--server-pid", type=int, required=True)
    parser.add_argument("--append-turns", type=int, default=12)
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--cancel-after-chunks", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args(argv)
    if not args.execute:
        parser.error("refusing a hardware request without --execute")
    try:
        loopback_target(args.server)
        model_parts(args.model)
    except ValueError as error:
        parser.error(str(error))
    for label in ("source_revision", "geniex_revision"):
        if not REVISION_PATTERN.fullmatch(getattr(args, label)):
            parser.error(
                f"--{label.replace('_', '-')} must be a full lowercase object ID"
            )
    if not VERSION_PATTERN.fullmatch(args.runtime_version):
        parser.error("--runtime-version contains unsupported characters or is too long")
    if not HARDWARE_PATTERN.fullmatch(args.hardware_label):
        parser.error("--hardware-label contains unsupported characters or is too long")
    if args.server_pid <= 0 or args.server_pid > 0xFFFFFFFF:
        parser.error("--server-pid must be a positive Windows process ID")
    if not 2 <= args.append_turns <= 64:
        parser.error("--append-turns must be between 2 and 64")
    if not 1 <= args.max_tokens <= 2048:
        parser.error("--max-tokens must be between 1 and 2048")
    if not 1 <= args.cancel_after_chunks <= args.max_tokens:
        parser.error("--cancel-after-chunks must be between 1 and --max-tokens")
    if not math.isfinite(args.timeout) or not 1 <= args.timeout <= 900:
        parser.error("--timeout must be finite and between 1 and 900 seconds")
    for label in ("model_artifact", "geniex_cli", "geniex_data_dir"):
        try:
            getattr(args, label).resolve(strict=True)
        except OSError as error:
            parser.error(f"--{label.replace('_', '-')} does not exist: {error}")
    for artifact in args.runtime_artifact:
        try:
            artifact.resolve(strict=True)
        except OSError as error:
            parser.error(f"--runtime-artifact does not exist: {error}")
    if args.output.exists() or Path(str(args.output) + ".tmp").exists():
        parser.error("refusing to overwrite evidence or partial evidence")
    return args


def main(argv=None) -> None:
    args = parse_args(argv)
    source_root = Path(__file__).resolve().parents[2]
    verify_git_revision(source_root, args.source_revision, SMOKE_SOURCE_FILES)
    source_manifest = source_bundle_manifest(
        source_root, args.source_revision, SMOKE_SOURCE_FILES
    )
    data_dir, model_artifact = resolve_bound_model_artifact(
        args.geniex_data_dir, args.model, args.model_artifact
    )
    model_manifest = artifact_manifest(model_artifact)
    host, port = loopback_target(args.server)
    server_binding = WindowsServerBinding(
        host,
        port,
        args.server_pid,
        args.geniex_cli,
        data_dir,
        args.runtime_artifact,
    )
    client = GenieXStreamingClient(
        args.server, args.model, args.timeout, server_binding
    )
    selected_traces = TRACE_ORDER if args.trace == "all" else (args.trace,)
    records = []
    for trace in selected_traces:
        records.extend(
            run_trace(
                client,
                mode=args.mode,
                trace=trace,
                append_turns=args.append_turns,
                max_tokens=args.max_tokens,
                cancel_after_chunks=args.cancel_after_chunks,
            )
        )

    server_binding.verify()
    if artifact_manifest(model_artifact) != model_manifest:
        raise RuntimeError("model artifact changed during the replay")
    verify_git_revision(source_root, args.source_revision, SMOKE_SOURCE_FILES)
    if source_bundle_manifest(
        source_root, args.source_revision, SMOKE_SOURCE_FILES
    ) != source_manifest:
        raise RuntimeError("server replay source changed during execution")
    if "sha256:" + sha256_file(server_binding.executable) \
            != server_binding.executable_sha256:
        raise RuntimeError("GenieX executable changed during the replay")
    expected_records = sum(
        _trace_steps(trace, args.append_turns) for trace in selected_traces
    )
    if len(records) != expected_records:
        raise RuntimeError("server replay produced an incomplete trace set")
    payload = {
        "schema_version": SCHEMA,
        "status": "complete",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        ),
        "claim_scope": {
            "kind": "attested_production_path_development_replay",
            "model_role": args.model_role,
            "performance_claim_authorized": False,
            "final_benchmark_complete": False,
        },
        "attestation": {
            "source_revision": args.source_revision,
            "source_bundle_digest": source_manifest["source_bundle_digest"],
            "source_file_count": len(source_manifest["files"]),
            "geniex_revision": args.geniex_revision,
            "operator_asserted_runtime_version": args.runtime_version,
            "operator_asserted_hardware_label": args.hardware_label,
            "process_architecture": _architecture(),
            "model": args.model,
            "model_artifact": model_manifest,
            "model_artifact_binding": "geniex-data/models/<catalogue-name>",
            "cli_sha256": server_binding.executable_sha256,
            "loaded_runtime_modules": server_binding.runtime_manifest(),
            "server_pid": server_binding.pid,
            "server_creation_time_100ns": server_binding.creation_time_100ns,
            "listener_identity_checks": 0,
            "runtime_module_checks": 0,
            "server_origin": args.server.rstrip("/"),
        },
        "configuration": {
            "mode": args.mode,
            "traces": list(selected_traces),
            "append_turns": args.append_turns,
            "max_completion_tokens": args.max_tokens,
            "cancel_after_stream_chunks": args.cancel_after_chunks,
            "streaming": True,
            "single_bound_server_process": True,
            "fresh_process_launch_attested": False,
        },
        "records": records,
    }
    server_binding.verify()
    payload["attestation"]["listener_identity_checks"] = server_binding.checks
    payload["attestation"]["runtime_module_checks"] = server_binding.runtime_checks
    _reject_forbidden_evidence_keys(payload)
    write_json_exclusive(args.output, payload)
    print(
        f"wrote {len(records)} secret-free {args.mode} replay records to "
        f"{args.output}"
    )


if __name__ == "__main__":
    main()
