"""Verify the managed GenieX cache protocol against a loopback server.

This is a hardware and protocol readiness check, not a latency benchmark. It
retains no prompt or generated text.
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
import platform
import re
import socket
import subprocess
import time
from urllib.parse import urlsplit

from perf.brickkv.run_matrix import sha256_file, write_json_exclusive
from perf.brickkv.source_bundle import source_bundle_manifest, verify_git_revision


SCHEMA = "brickkv.geniex-managed-smoke/1"
CHAT_PATH = "/v1/chat/completions"
MAX_RESPONSE_BYTES = 1024 * 1024
REVISION_PATTERN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
MODEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}")
VERSION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}")
HARDWARE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._()+-]{0,127}")
CACHE_FIELDS = frozenset({"mode", "status", "revision", "reason"})
REQUIRED_RUNTIME_MODULES = frozenset({
    "geniex.dll",
    "geniex_core.dll",
    "geniex_plugin.dll",
})
SMOKE_SOURCE_FILES = tuple(sorted((
    "perf/brickkv/geniex_managed_smoke.py",
    "perf/brickkv/run_matrix.py",
    "perf/brickkv/source_bundle.py",
)))
DECISIONS = {
    "cold": ("cold", "first_request"),
    "extension": ("reused", "exact_extension"),
    "branch": ("reset", "branch"),
    "session_switch": ("reset", "session_switch"),
    "parent_mismatch": ("reset", "parent_mismatch"),
    "post_disconnect": ("cold", "first_request"),
}
SESSION_A = "0123456789abcdef0123456789abcdef"
SESSION_B = "fedcba9876543210fedcba9876543210"
SESSION_C = "33333333333333333333333333333333"
BOGUS_PARENT = "sha256:" + "0" * 64


def loopback_target(value: str) -> tuple[str, int]:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("server must be an uncredentialed http://127.0.0.1:PORT origin")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("server has an invalid port") from error
    if port is None or not 1 <= port <= 65535:
        raise ValueError("server must include a valid explicit port")
    return "127.0.0.1", port


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def model_parts(value: str) -> tuple[str, ...]:
    if not MODEL_PATTERN.fullmatch(value):
        raise ValueError("model must be a bounded catalogue name")
    parts = tuple(value.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("model catalogue components must be explicit names")
    return parts


def resolve_bound_model_artifact(
    data_dir: Path, model: str, model_artifact: Path
) -> tuple[Path, Path]:
    resolved_data = data_dir.resolve(strict=True)
    resolved_artifact = model_artifact.resolve(strict=True)
    expected = resolved_data.joinpath(
        "models", *model_parts(model)
    ).resolve(strict=True)
    if os.path.normcase(str(resolved_artifact)) != os.path.normcase(str(expected)):
        raise RuntimeError(
            "model artifact must be the selected model directory inside GenieX data"
        )
    return resolved_data, resolved_artifact


def _frame(digest, label: bytes, value: bytes) -> None:
    digest.update(len(label).to_bytes(4, "big"))
    digest.update(label)
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def artifact_manifest(path: Path) -> dict:
    """Hash one regular file or an immutable view of one regular-file tree."""
    if path.is_symlink():
        raise RuntimeError("model artifact must not be a symbolic link")
    resolved = path.resolve(strict=True)
    if resolved.is_file():
        return {
            "kind": "file",
            "files": 1,
            "bytes": resolved.stat().st_size,
            "sha256": "sha256:" + sha256_file(resolved),
        }
    if not resolved.is_dir():
        raise RuntimeError("model artifact must be a regular file or directory")

    def inventory() -> list[tuple[str, Path]]:
        rows = []
        for root, directories, files in os.walk(resolved, followlinks=False):
            directories.sort()
            files.sort()
            root_path = Path(root)
            for name in directories:
                candidate = root_path / name
                if candidate.is_symlink() or not candidate.is_dir():
                    raise RuntimeError(
                        f"model artifact tree contains an unsafe directory: {candidate}"
                    )
            for name in files:
                candidate = root_path / name
                if candidate.is_symlink() or not candidate.is_file():
                    raise RuntimeError(
                        f"model artifact tree contains a non-regular file: {candidate}"
                    )
                rows.append((candidate.relative_to(resolved).as_posix(), candidate))
        return rows

    before = inventory()
    digest = hashlib.sha256()
    _frame(digest, b"format", b"brickkv-artifact-tree/1")
    total_bytes = 0
    entries = []
    for relative, candidate in before:
        size = candidate.stat().st_size
        file_digest = sha256_file(candidate)
        _frame(digest, b"path", relative.encode("utf-8"))
        _frame(digest, b"sha256", file_digest.encode("ascii"))
        _frame(digest, b"bytes", str(size).encode("ascii"))
        total_bytes += size
        entries.append((relative, candidate))
    after = inventory()
    if [row[0] for row in entries] != [row[0] for row in after]:
        raise RuntimeError("model artifact tree changed while hashing")
    return {
        "kind": "directory",
        "files": len(entries),
        "bytes": total_bytes,
        "sha256": "sha256:" + digest.hexdigest(),
    }


def _windows_process_image(pid: int) -> Path:
    if os.name != "nt":
        raise RuntimeError("server process attestation requires Windows")
    process_query_limited_information = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    )
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        raise RuntimeError(f"cannot inspect GenieX server process {pid}")
    try:
        capacity = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(capacity.value)
        if not kernel32.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(capacity)
        ):
            raise RuntimeError(f"cannot read GenieX server process image for {pid}")
        return Path(buffer.value).resolve(strict=True)
    finally:
        kernel32.CloseHandle(handle)


def _windows_command_line_argv(command_line: str) -> list[str]:
    if os.name != "nt":
        raise RuntimeError("Windows command-line parsing requires Windows")
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32.CommandLineToArgvW.argtypes = (
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_int),
    )
    shell32.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel32.LocalFree.argtypes = (wintypes.HLOCAL,)
    kernel32.LocalFree.restype = wintypes.HLOCAL
    count = ctypes.c_int(0)
    pointer = shell32.CommandLineToArgvW(command_line, ctypes.byref(count))
    if not pointer or count.value <= 0:
        raise RuntimeError("cannot parse the GenieX process command line")
    try:
        return [pointer[index] for index in range(count.value)]
    finally:
        kernel32.LocalFree(ctypes.cast(pointer, wintypes.HLOCAL))


def _windows_process_argv(pid: int) -> list[str]:
    if os.name != "nt":
        raise RuntimeError("server command-line attestation requires Windows")
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows")).resolve()
    powershell = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not powershell.is_file():
        raise RuntimeError("cannot locate the Windows PowerShell system binary")
    script = (
        "$ErrorActionPreference='Stop';"
        f"$p=Get-CimInstance -ClassName Win32_Process -Filter 'ProcessId = {pid}';"
        "if($null -eq $p){throw 'process not found'};"
        "[Console]::Out.Write(($p.CommandLine | ConvertTo-Json -Compress))"
    )
    completed = subprocess.run(
        [
            str(powershell),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        cwd=system_root / "System32",
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=20,
    )
    if completed.returncode != 0 or len(completed.stdout) > 128 * 1024:
        raise RuntimeError(f"cannot read GenieX server process command line for {pid}")
    try:
        command_line = json.loads(completed.stdout.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Windows returned an invalid process command line") from error
    if not isinstance(command_line, str) or not command_line:
        raise RuntimeError("Windows returned an empty process command line")
    return _windows_command_line_argv(command_line)


def _one_flag_value(arguments: list[str], name: str) -> str:
    values = []
    for index, argument in enumerate(arguments):
        if argument == name:
            if index + 1 >= len(arguments) or arguments[index + 1].startswith("-"):
                raise RuntimeError(f"GenieX process has an incomplete {name} flag")
            values.append(arguments[index + 1])
        elif argument.startswith(name + "="):
            values.append(argument[len(name) + 1:])
    if len(values) != 1:
        raise RuntimeError(f"GenieX process must declare exactly one {name} flag")
    return values[0]


def _verify_geniex_argv(
    arguments: list[str], executable: Path, data_dir: Path, host: str, port: int
) -> None:
    if not arguments:
        raise RuntimeError("GenieX process has an empty command line")
    process_image = Path(arguments[0]).resolve(strict=True)
    if os.path.normcase(str(process_image)) != os.path.normcase(str(executable)):
        raise RuntimeError("GenieX command line names a different executable")
    if arguments.count("serve") != 1:
        raise RuntimeError("GenieX process is not one explicit serve command")
    declared_data = Path(_one_flag_value(arguments, "--data-dir")).resolve(strict=True)
    if os.path.normcase(str(declared_data)) != os.path.normcase(str(data_dir)):
        raise RuntimeError("GenieX process uses a different data directory")
    if _one_flag_value(arguments, "--host") != f"{host}:{port}":
        raise RuntimeError("GenieX process uses a different listener address")
    if _one_flag_value(arguments, "--compute") != "npu":
        raise RuntimeError("GenieX process is not explicitly configured for NPU compute")


def _windows_listener_pids(host: str, port: int) -> set[int]:
    if os.name != "nt":
        raise RuntimeError("TCP listener attestation requires Windows")
    if host != "127.0.0.1":
        raise RuntimeError("listener attestation supports exact IPv4 loopback only")

    class TcpRowOwnerPid(ctypes.Structure):
        _fields_ = [
            ("state", wintypes.DWORD),
            ("local_address", wintypes.DWORD),
            ("local_port", wintypes.DWORD),
            ("remote_address", wintypes.DWORD),
            ("remote_port", wintypes.DWORD),
            ("owning_pid", wintypes.DWORD),
        ]

    af_inet = 2
    owner_pid_listener = 3
    insufficient_buffer = 122
    iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)
    get_table = iphlpapi.GetExtendedTcpTable
    get_table.argtypes = (
        wintypes.LPVOID,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.BOOL,
        wintypes.ULONG,
        ctypes.c_int,
        wintypes.ULONG,
    )
    get_table.restype = wintypes.DWORD
    size = wintypes.DWORD(0)
    result = get_table(None, ctypes.byref(size), False, af_inet, owner_pid_listener, 0)
    if result not in {0, insufficient_buffer} or size.value < 4:
        raise RuntimeError(f"cannot size the Windows TCP listener table: {result}")
    buffer = ctypes.create_string_buffer(size.value)
    result = get_table(buffer, ctypes.byref(size), False, af_inet, owner_pid_listener, 0)
    if result != 0:
        raise RuntimeError(f"cannot read the Windows TCP listener table: {result}")
    count = wintypes.DWORD.from_buffer_copy(buffer.raw[:4]).value
    row_size = ctypes.sizeof(TcpRowOwnerPid)
    if 4 + count * row_size > len(buffer):
        raise RuntimeError("Windows returned a malformed TCP listener table")
    expected_address = int.from_bytes(socket.inet_aton(host), "little")
    matches = set()
    for index in range(count):
        start = 4 + index * row_size
        row = TcpRowOwnerPid.from_buffer_copy(buffer.raw[start:start + row_size])
        if (
            row.local_address == expected_address
            and socket.ntohs(row.local_port & 0xFFFF) == port
        ):
            matches.add(int(row.owning_pid))
    return matches


def _windows_process_modules(pid: int) -> tuple[Path, ...]:
    if os.name != "nt":
        raise RuntimeError("runtime module attestation requires Windows")

    class ModuleEntry32W(ctypes.Structure):
        _fields_ = [
            ("size", wintypes.DWORD),
            ("module_id", wintypes.DWORD),
            ("process_id", wintypes.DWORD),
            ("global_usage", wintypes.DWORD),
            ("process_usage", wintypes.DWORD),
            ("base_address", ctypes.POINTER(wintypes.BYTE)),
            ("base_size", wintypes.DWORD),
            ("module_handle", wintypes.HMODULE),
            ("module_name", wintypes.WCHAR * 256),
            ("executable_path", wintypes.WCHAR * 260),
        ]

    snapshot_modules = 0x00000008 | 0x00000010
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Module32FirstW.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(ModuleEntry32W),
    )
    kernel32.Module32FirstW.restype = wintypes.BOOL
    kernel32.Module32NextW.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(ModuleEntry32W),
    )
    kernel32.Module32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.CreateToolhelp32Snapshot(snapshot_modules, pid)
    if handle == wintypes.HANDLE(-1).value:
        raise RuntimeError(f"cannot inspect loaded modules for process {pid}")
    try:
        entry = ModuleEntry32W()
        entry.size = ctypes.sizeof(ModuleEntry32W)
        if not kernel32.Module32FirstW(handle, ctypes.byref(entry)):
            raise RuntimeError(f"cannot read loaded modules for process {pid}")
        paths = []
        while True:
            if entry.executable_path:
                paths.append(Path(entry.executable_path).resolve(strict=True))
            entry.size = ctypes.sizeof(ModuleEntry32W)
            if not kernel32.Module32NextW(handle, ctypes.byref(entry)):
                error = ctypes.get_last_error()
                if error != 18:  # ERROR_NO_MORE_FILES
                    raise RuntimeError(
                        f"cannot continue loaded-module inspection for process {pid}"
                    )
                break
        return tuple(paths)
    finally:
        kernel32.CloseHandle(handle)


class WindowsServerBinding:
    """Bind every response to one exact listener process and executable."""

    def __init__(
        self,
        host: str,
        port: int,
        pid: int,
        executable: Path,
        data_dir: Path,
        runtime_artifacts: list[Path],
    ):
        if isinstance(pid, bool) or not isinstance(pid, int) or not 1 <= pid <= 0xFFFFFFFF:
            raise ValueError("server PID must be a positive Windows process ID")
        self.host = host
        self.port = port
        self.pid = pid
        if executable.is_symlink():
            raise RuntimeError("GenieX CLI must not be a symbolic link")
        self.executable = executable.resolve(strict=True)
        if not self.executable.is_file():
            raise RuntimeError("GenieX CLI must be one regular executable file")
        if data_dir.is_symlink():
            raise RuntimeError("GenieX data directory must not be a symbolic link")
        self.data_dir = data_dir.resolve(strict=True)
        if not self.data_dir.is_dir():
            raise RuntimeError("GenieX data directory must be one directory")
        _verify_geniex_argv(
            _windows_process_argv(pid),
            self.executable,
            self.data_dir,
            host,
            port,
        )
        self.runtime_artifacts = []
        seen_paths = set()
        for artifact in runtime_artifacts:
            if artifact.is_symlink():
                raise RuntimeError("runtime artifacts must not be symbolic links")
            resolved_artifact = artifact.resolve(strict=True)
            if not resolved_artifact.is_file():
                raise RuntimeError("runtime artifacts must be regular files")
            normalized = os.path.normcase(str(resolved_artifact))
            if normalized in seen_paths:
                raise RuntimeError("runtime artifacts must not contain duplicates")
            seen_paths.add(normalized)
            self.runtime_artifacts.append({
                "path": resolved_artifact,
                "name": resolved_artifact.name,
                "bytes": resolved_artifact.stat().st_size,
                "sha256": "sha256:" + sha256_file(resolved_artifact),
            })
        runtime_names = {row["name"].lower() for row in self.runtime_artifacts}
        if not REQUIRED_RUNTIME_MODULES.issubset(runtime_names):
            missing = sorted(REQUIRED_RUNTIME_MODULES - runtime_names)
            raise RuntimeError(f"required runtime artifacts are missing: {missing}")
        self.executable_sha256 = "sha256:" + sha256_file(self.executable)
        self.checks = 0
        self.runtime_checks = 0
        self.runtime_verified = False
        self.verify()

    def verify(self) -> None:
        actual_image = _windows_process_image(self.pid)
        if os.path.normcase(str(actual_image)) != os.path.normcase(str(self.executable)):
            raise RuntimeError("the selected process is not the attested GenieX executable")
        owners = _windows_listener_pids(self.host, self.port)
        if owners != {self.pid}:
            raise RuntimeError(
                f"loopback listener ownership changed: expected {self.pid}, found {sorted(owners)}"
            )
        self.checks += 1
        if self.runtime_verified:
            self._verify_runtime_modules()

    def _verify_runtime_modules(self) -> None:
        loaded = {
            os.path.normcase(str(path)) for path in _windows_process_modules(self.pid)
        }
        for artifact in self.runtime_artifacts:
            path = artifact["path"]
            if os.path.normcase(str(path)) not in loaded:
                raise RuntimeError(f"attested runtime module is not loaded: {path.name}")
            if "sha256:" + sha256_file(path) != artifact["sha256"]:
                raise RuntimeError(f"loaded runtime module changed: {path.name}")
        self.runtime_checks += 1

    def verify_runtime(self) -> None:
        self._verify_runtime_modules()
        self.runtime_verified = True

    def runtime_manifest(self) -> list[dict]:
        return [
            {
                "name": row["name"],
                "bytes": row["bytes"],
                "sha256": row["sha256"],
            }
            for row in self.runtime_artifacts
        ]


def validate_cache_metadata(value: object, expected_step: str) -> dict:
    if not isinstance(value, dict) or set(value) != CACHE_FIELDS:
        raise RuntimeError(f"{expected_step} returned an invalid cache record shape")
    status, reason = DECISIONS[expected_step]
    if value.get("mode") != "managed":
        raise RuntimeError(f"{expected_step} did not report managed mode")
    if value.get("status") != status or value.get("reason") != reason:
        raise RuntimeError(
            f"{expected_step} returned {value.get('status')}/{value.get('reason')}; "
            f"expected {status}/{reason}"
        )
    revision = value.get("revision")
    if not isinstance(revision, str) or not SHA256_PATTERN.fullmatch(revision):
        raise RuntimeError(f"{expected_step} returned an invalid revision")
    return {
        "mode": "managed",
        "status": status,
        "reason": reason,
        "revision": revision,
    }


def response_record(response: dict, step: str) -> tuple[dict, str]:
    cache = validate_cache_metadata(response.get("geniex_cache"), step)
    try:
        content = response["choices"][0]["message"]["content"]
        usage = response["usage"]
        prompt_tokens = usage["prompt_tokens"]
        completion_tokens = usage["completion_tokens"]
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError(f"{step} returned an invalid OpenAI response") from error
    if not isinstance(content, str):
        raise RuntimeError(f"{step} returned non-text content")
    for label, value in (
        ("prompt_tokens", prompt_tokens),
        ("completion_tokens", completion_tokens),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise RuntimeError(f"{step} returned invalid {label}")
    return {
        "step": step,
        "cache": cache,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "output_bytes": len(content.encode("utf-8")),
        "output_sha256": sha256_text(content),
    }, content


class GenieXLoopbackClient:
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

    def _payload(self, messages: list[dict], *, max_tokens: int, stream: bool) -> bytes:
        return json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "max_completion_tokens": max_tokens,
                "temperature": 0,
                "seed": 42,
                "enable_think": False,
                "compute": "npu",
                "stream": stream,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def _post(self, payload: bytes, headers: dict[str, str]) -> object:
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
                    **headers,
                },
            )
            response = connection.getresponse()
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise RuntimeError("GenieX response exceeded the one MiB ceiling")
            if response.status != 200:
                raise RuntimeError(f"GenieX returned HTTP {response.status}")
            media_type = response.getheader("Content-Type", "").split(";", 1)[0]
            if media_type != "application/json":
                raise RuntimeError("GenieX returned a non-JSON response")
            result = json.loads(raw.decode("utf-8"))
            self.server_binding.verify_runtime()
            return result
        finally:
            connection.close()

    def clear_lineage(self) -> None:
        payload = self._payload(
            [{"role": "system", "content": "Synthetic cache smoke warm-up."}],
            max_tokens=1,
            stream=False,
        )
        self._post(payload, {})

    def managed(
        self, messages: list[dict], session: str, parent: str = ""
    ) -> dict:
        headers = {"GenieX-Cache-Session": session}
        if parent:
            headers["GenieX-Cache-Parent"] = parent
        result = self._post(
            self._payload(messages, max_tokens=8, stream=False), headers
        )
        if not isinstance(result, dict):
            raise RuntimeError("GenieX returned a non-object managed response")
        return result

    def force_disconnect(self) -> dict:
        self.server_binding.verify()
        long_input = ("TOKEN " * 1200).strip()
        body = self._payload(
            [
                {"role": "system", "content": "Read the synthetic request."},
                {
                    "role": "user",
                    "content": "Summarize this synthetic sequence: " + long_input,
                },
            ],
            max_tokens=256,
            stream=True,
        )
        request = (
            f"POST {CHAT_PATH} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"GenieX-Cache-Session: {SESSION_C}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii") + body
        with socket.create_connection((self.host, self.port), self.timeout) as client:
            client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            client.sendall(request)
            time.sleep(0.1)
        # Give the loopback server time to observe the closed socket, abort the
        # transaction and reset the one mutable model handle.
        time.sleep(1.5)
        self.server_binding.verify()
        return {
            "request_bytes": len(body),
            "disconnect_after_send_ms": 100,
            "recovery_wait_ms": 1500,
            "response_bytes_read": 0,
        }


def run_protocol(client: GenieXLoopbackClient) -> tuple[list[dict], dict]:
    client.clear_lineage()
    first_messages = [
        {"role": "system", "content": "Answer briefly and exactly."},
        {"role": "user", "content": "Reply with CACHE_ONE."},
    ]
    first, answer_one = response_record(
        client.managed(first_messages, SESSION_A), "cold"
    )

    extension_messages = first_messages + [
        {"role": "assistant", "content": answer_one},
        {"role": "user", "content": "Reply with CACHE_TWO."},
    ]
    extension, _ = response_record(
        client.managed(
            extension_messages, SESSION_A, first["cache"]["revision"]
        ),
        "extension",
    )

    branch_messages = [
        {"role": "system", "content": "Answer briefly and exactly."},
        {"role": "user", "content": "This edit creates a synthetic branch."},
    ]
    branch, _ = response_record(
        client.managed(branch_messages, SESSION_A, extension["cache"]["revision"]),
        "branch",
    )

    second_messages = [
        {"role": "system", "content": "Answer briefly."},
        {"role": "user", "content": "Reply SESSION_TWO."},
    ]
    switched, answer_two = response_record(
        client.managed(second_messages, SESSION_B, branch["cache"]["revision"]),
        "session_switch",
    )
    mismatch_messages = second_messages + [
        {"role": "assistant", "content": answer_two},
        {"role": "user", "content": "Reply PARENT_CHECK."},
    ]
    mismatch, _ = response_record(
        client.managed(mismatch_messages, SESSION_B, BOGUS_PARENT),
        "parent_mismatch",
    )

    disconnect = client.force_disconnect()
    post_disconnect_messages = [
        {"role": "system", "content": "Answer briefly."},
        {"role": "user", "content": "Reply AFTER_DISCONNECT."},
    ]
    recovered, _ = response_record(
        client.managed(post_disconnect_messages, SESSION_C), "post_disconnect"
    )
    return [first, extension, branch, switched, mismatch, recovered], disconnect


def _architecture() -> str:
    value = platform.machine().lower()
    return {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "arm64",
            "aarch64": "arm64"}.get(value, value)


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--server", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-role", choices=("smoke", "final-study"), required=True)
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
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)
    if not args.execute:
        parser.error("refusing a hardware request without --execute")
    loopback_target(args.server)
    for label in ("source_revision", "geniex_revision"):
        if not REVISION_PATTERN.fullmatch(getattr(args, label)):
            parser.error(f"--{label.replace('_', '-')} must be a full lowercase object ID")
    try:
        model_parts(args.model)
    except ValueError as error:
        parser.error(str(error))
    if not VERSION_PATTERN.fullmatch(args.runtime_version):
        parser.error("--runtime-version contains unsupported characters or is too long")
    if not HARDWARE_PATTERN.fullmatch(args.hardware_label):
        parser.error("--hardware-label contains unsupported characters or is too long")
    if args.server_pid <= 0 or args.server_pid > 0xFFFFFFFF:
        parser.error("--server-pid must be a positive Windows process ID")
    if not math.isfinite(args.timeout) or args.timeout <= 0 or args.timeout > 300:
        parser.error("--timeout must be finite and between 0 and 300 seconds")
    for label in ("model_artifact", "geniex_cli", "geniex_data_dir"):
        value = getattr(args, label)
        try:
            value.resolve(strict=True)
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
    model_manifest = artifact_manifest(args.model_artifact)
    host, port = loopback_target(args.server)
    server_binding = WindowsServerBinding(
        host,
        port,
        args.server_pid,
        args.geniex_cli,
        args.geniex_data_dir,
        args.runtime_artifact,
    )
    client = GenieXLoopbackClient(
        args.server, args.model, args.timeout, server_binding
    )
    records, disconnect = run_protocol(client)
    server_binding.verify()
    if artifact_manifest(args.model_artifact) != model_manifest:
        raise RuntimeError("model artifact changed during the smoke run")
    verify_git_revision(source_root, args.source_revision, SMOKE_SOURCE_FILES)
    if source_bundle_manifest(
        source_root, args.source_revision, SMOKE_SOURCE_FILES
    ) != source_manifest:
        raise RuntimeError("smoke runner source changed during execution")
    if "sha256:" + sha256_file(server_binding.executable) != server_binding.executable_sha256:
        raise RuntimeError("GenieX executable changed during the smoke run")
    payload = {
        "schema_version": SCHEMA,
        "status": "passed",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        ),
        "claim_scope": {
            "kind": "managed_cache_protocol_and_npu_smoke",
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
            "listener_identity_checks": 0,
            "runtime_module_checks": 0,
            "server_origin": args.server.rstrip("/"),
        },
        "records": records,
        "forced_disconnect": disconnect,
    }
    server_binding.verify()
    payload["attestation"]["listener_identity_checks"] = server_binding.checks
    payload["attestation"]["runtime_module_checks"] = server_binding.runtime_checks
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    for forbidden in ("messages", "generated_text", "prompt", "full_text", "content"):
        if f'"{forbidden}"' in serialized:
            raise RuntimeError(f"evidence unexpectedly contains forbidden key {forbidden!r}")
    write_json_exclusive(args.output, payload)
    print(f"wrote {len(records)} secret-free protocol records to {args.output}")


if __name__ == "__main__":
    main()
