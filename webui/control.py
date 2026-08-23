"""Security and lifecycle primitives for the local Agent Lab control plane.

The web console is loopback-only, but loopback is a routing property rather
than an authorization boundary.  This module keeps the security-sensitive
pieces small enough to test without starting Ollama or a browser.
"""
from collections import deque
import ctypes
import json
import os
from pathlib import Path
import queue
import re
import secrets
import signal
import stat
import subprocess
import threading
import time
import shutil


CAPABILITY_BYTES = 32
MAX_BODY_BYTES = 64 * 1024
MAX_EVENT_BYTES = 256 * 1024
MAX_EVENTS = 2_000
MAX_SUBSCRIBERS = 8
SUBSCRIBER_QUEUE = 256
MAX_STDERR_LINES = 100
MAX_STDERR_LINE = 4_096
MAX_LOG_FILES = 100
MAX_LOG_BYTES = 50 * 1024 * 1024
MAX_LOG_FILE_BYTES = 4 * 1024 * 1024
MAX_ARTIFACT_BYTES = 20 * 1024 * 1024
MAX_PREVIEW_BYTES = 10 * 1024 * 1024
MAX_ARCHIVE_EXPANDED_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 2_000
MAX_WORKSPACE_MEMBERS = 5_000
MAX_WORKSPACE_BYTES = 100 * 1024 * 1024
CONFIRMATION_TIMEOUT_SECONDS = 120

_SECRET_KEY = re.compile(
    r"^(?:authorization|api[_-]?key|password|secret|token|"
    r"access[_-]?token|refresh[_-]?token|capability|nonce)$",
    re.I,
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/]+=*")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)([\"']?(?:authorization|api[_-]?key|password|secret|token|"
    r"access[_-]?token|refresh[_-]?token|capability|nonce)[\"']?\s*[:=]\s*)"
    r"([\"']?)([^\s,}\"']+)([\"']?)"
)


class RequestError(ValueError):
    """A deliberately user-visible request rejection."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = int(status)


def new_capability():
    """Return at least 256 bits of unguessable startup authority."""
    return secrets.token_urlsafe(CAPABILITY_BYTES)


def validate_host(headers, expected_host):
    values = headers.get_all("Host", [])
    if len(values) != 1 or values[0] != expected_host:
        raise RequestError(421, "untrusted Host header")


def validate_capability(headers, capability):
    values = headers.get_all("Authorization", [])
    expected = "Bearer " + capability
    if (
        len(values) != 1
        or not secrets.compare_digest(values[0], expected)
    ):
        raise RequestError(401, "missing or invalid Agent Lab capability")


def validate_mutation_origin(headers, expected_origin):
    origins = headers.get_all("Origin", [])
    if len(origins) != 1 or origins[0] != expected_origin:
        raise RequestError(403, "untrusted request origin")
    fetch_site = headers.get("Sec-Fetch-Site")
    if fetch_site is not None and fetch_site != "same-origin":
        raise RequestError(403, "cross-origin request refused")


def read_json_object(handler):
    """Read one bounded, non-simple JSON request with an exact length."""
    if handler.headers.get("Transfer-Encoding") is not None:
        raise RequestError(400, "Transfer-Encoding is not supported")
    lengths = handler.headers.get_all("Content-Length", [])
    if len(lengths) != 1:
        raise RequestError(411, "one Content-Length header is required")
    try:
        length = int(lengths[0], 10)
    except (TypeError, ValueError):
        raise RequestError(400, "invalid Content-Length")
    if length <= 0:
        raise RequestError(400, "a JSON request body is required")
    if length > MAX_BODY_BYTES:
        handler.close_connection = True
        raise RequestError(413, "request body is too large")
    if handler.headers.get_content_type() != "application/json":
        raise RequestError(415, "Content-Type must be application/json")
    try:
        raw = handler.rfile.read(length)
        if len(raw) != length:
            raise RequestError(400, "request body ended early")
        value = json.loads(raw.decode("utf-8"))
    except RequestError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RequestError(400, "request body is not valid UTF-8 JSON")
    if not isinstance(value, dict):
        raise RequestError(400, "request body must be a JSON object")
    return value


def exact_object(value, *, required=(), optional=()):
    """Reject missing and unknown keys; return the original detached mapping."""
    if not isinstance(value, dict):
        raise RequestError(400, "request body must be a JSON object")
    required = set(required)
    allowed = required | set(optional)
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        raise RequestError(400, "missing fields: " + ", ".join(missing))
    if unknown:
        raise RequestError(400, "unknown fields: " + ", ".join(unknown))
    return dict(value)


def require_string(value, field, *, minimum=1, maximum=8_192):
    if not isinstance(value, str) or not (minimum <= len(value) <= maximum):
        raise RequestError(
            400, f"{field} must be a string of {minimum}..{maximum} characters"
        )
    return value


def require_optional_string(value, field, *, maximum=200):
    if value is None:
        return None
    return require_string(value, field, maximum=maximum)


def require_bool(value, field):
    if not isinstance(value, bool):
        raise RequestError(400, f"{field} must be a boolean")
    return value


def require_int(value, field, *, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int):
        raise RequestError(400, f"{field} must be an integer")
    if not minimum <= value <= maximum:
        raise RequestError(400, f"{field} must be between {minimum} and {maximum}")
    return value


def portable_leaf(value, field="name"):
    value = require_string(value, field, maximum=255)
    if value in (".", "..") or value != os.path.basename(value):
        raise RequestError(400, f"{field} must be one portable file name")
    if "/" in value or "\\" in value or "\x00" in value:
        raise RequestError(400, f"{field} must be one portable file name")
    if (
        any(ord(character) < 32 or ord(character) == 127 for character in value)
        or any(character in '<>:"|?*' for character in value)
        or value.endswith((".", " "))
        or value.split(".", 1)[0].upper() in {
            "CON", "PRN", "AUX", "NUL",
            *(f"COM{number}" for number in range(1, 10)),
            *(f"LPT{number}" for number in range(1, 10)),
        }
    ):
        raise RequestError(400, f"{field} is not portable across supported hosts")
    return value


def _is_reparse(info):
    attributes = getattr(info, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse)


def regular_path_under(root, leaf, *, maximum_bytes=None):
    """Resolve one leaf below a trusted root and reject links/reparse points."""
    leaf = portable_leaf(leaf)
    root = os.path.abspath(os.fspath(root))
    trusted_directory_under(root, root)
    path = os.path.abspath(os.path.join(root, leaf))
    try:
        if os.path.commonpath((root, path)) != root:
            raise RequestError(400, "requested path is outside its allowed root")
    except ValueError:
        raise RequestError(400, "requested path is outside its allowed root")
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        raise RequestError(404, "file not found")
    if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
        raise RequestError(400, "linked or reparse-point files are not allowed")
    if not stat.S_ISREG(info.st_mode):
        raise RequestError(400, "requested path is not a regular file")
    if maximum_bytes is not None and info.st_size > maximum_bytes:
        raise RequestError(413, "file is too large")
    return path


def trusted_directory_under(root, target, *, must_exist=True):
    """Validate an existing directory and every descendant path component."""
    root = os.path.abspath(os.fspath(root))
    target = os.path.abspath(os.fspath(target))
    try:
        root_info = os.lstat(root)
    except FileNotFoundError:
        raise RequestError(400, "trusted root does not exist")
    if stat.S_ISLNK(root_info.st_mode) or _is_reparse(root_info):
        raise RequestError(400, "linked or reparse-point roots are not allowed")
    if not stat.S_ISDIR(root_info.st_mode):
        raise RequestError(400, "trusted root is not a directory")
    try:
        relative = os.path.relpath(target, root)
        if relative == os.pardir or relative.startswith(os.pardir + os.sep):
            raise RequestError(400, "directory is outside its allowed root")
    except ValueError:
        raise RequestError(400, "directory is outside its allowed root")
    current = root
    for component in (() if relative == "." else relative.split(os.sep)):
        current = os.path.join(current, component)
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            if must_exist:
                raise RequestError(400, "directory does not exist")
            break
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise RequestError(400, "linked or reparse-point directories are not allowed")
        if not stat.S_ISDIR(info.st_mode):
            raise RequestError(400, "path component is not a directory")
    return target


def validate_regular_tree_under(
    root,
    target,
    *,
    must_exist=True,
    maximum_members=MAX_WORKSPACE_MEMBERS,
    maximum_bytes=MAX_WORKSPACE_BYTES,
):
    """Reject links, reparse points, irregular files, and oversized read trees.

    Agent Lab domain inspectors are legacy callbacks that receive paths rather
    than already-open file handles.  Validate the complete tree immediately
    before invoking one so a linked state, memory, or artifact cannot redirect
    an authenticated browser read outside the configured-agent directory.
    """
    target = trusted_directory_under(root, target, must_exist=must_exist)
    if not os.path.exists(target):
        return target
    members = 0
    total_bytes = 0
    pending = [target]
    while pending:
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise RequestError(400, "workspace tree cannot be inspected") from exc
        for entry in entries:
            members += 1
            if members > maximum_members:
                raise RequestError(413, "workspace tree has too many members")
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise RequestError(400, "workspace member cannot be inspected") from exc
            if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
                raise RequestError(400, "linked or reparse-point workspace members are not allowed")
            if stat.S_ISDIR(info.st_mode):
                pending.append(entry.path)
            elif stat.S_ISREG(info.st_mode):
                total_bytes += info.st_size
                if total_bytes > maximum_bytes:
                    raise RequestError(413, "workspace tree is too large")
            else:
                raise RequestError(400, "irregular workspace members are not allowed")
    return target


def regular_entries_under(root, *, prefix="", suffix="", limit=MAX_LOG_FILES):
    """Return newest regular direct children without following directory links."""
    trusted_directory_under(root, root)
    entries = []
    try:
        children = os.scandir(root)
    except OSError as exc:
        raise RequestError(400, "directory cannot be inspected") from exc
    with children:
        for entry in children:
            if prefix and not entry.name.startswith(prefix):
                continue
            if suffix and not entry.name.endswith(suffix):
                continue
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if (
                stat.S_ISREG(info.st_mode)
                and not stat.S_ISLNK(info.st_mode)
                and not _is_reparse(info)
            ):
                entries.append((info.st_mtime_ns, entry.name, info.st_size))
    entries.sort(reverse=True)
    return entries[:limit]


def reset_directory(root, target):
    target = trusted_directory_under(root, target)
    shutil.rmtree(target)
    os.makedirs(target, exist_ok=False)


def redact(value, *, depth=0):
    """Return a bounded JSON-compatible copy with likely credentials removed."""
    if depth > 20:
        return "[truncated]"
    if isinstance(value, dict):
        out = {}
        for key, item in list(value.items())[:1_000]:
            label = str(key)[:256]
            out[label] = "[redacted]" if _SECRET_KEY.search(label) else redact(
                item, depth=depth + 1
            )
        return out
    if isinstance(value, (list, tuple)):
        return [redact(item, depth=depth + 1) for item in value[:2_000]]
    if isinstance(value, str):
        bounded = _BEARER.sub("Bearer [redacted]", value[:32_768])
        return _SECRET_ASSIGNMENT.sub(r"\1\2[redacted]\4", bounded)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:32_768]


def prune_logs(log_dir):
    """Keep the newest bounded regular JSON logs within count and byte caps."""
    root = Path(log_dir)
    if not root.is_dir():
        return
    entries = []
    for path in root.iterdir():
        try:
            info = path.lstat()
        except OSError:
            continue
        if (
            path.name.startswith("run_")
            and path.suffix == ".json"
            and stat.S_ISREG(info.st_mode)
            and not stat.S_ISLNK(info.st_mode)
            and not _is_reparse(info)
        ):
            entries.append((info.st_mtime_ns, path, info.st_size))
    entries.sort(reverse=True)
    kept_bytes = 0
    for index, (_, path, size) in enumerate(entries):
        kept_bytes += size
        if index >= MAX_LOG_FILES or kept_bytes > MAX_LOG_BYTES:
            try:
                path.unlink()
            except OSError:
                pass


class EventJournal:
    """Bounded replay plus bounded subscribers for one run."""

    def __init__(self):
        self._events = deque(maxlen=MAX_EVENTS)
        self._next = 0
        self._subscribers = []
        self._lock = threading.Lock()

    def add(self, event):
        safe = redact(event)
        # The one-time nonce is the browser's response secret. It must survive
        # authenticated replay until the decision is consumed; it is never
        # written to the retained run transcript.
        if isinstance(event, dict) and event.get("t") == "confirmation":
            safe["nonce"] = event.get("nonce")
        if len(json.dumps(safe, ensure_ascii=False, default=str).encode("utf-8")) > MAX_EVENT_BYTES:
            safe = {"t": "error", "message": "runner event exceeded the retention limit"}
        with self._lock:
            item = (self._next, safe)
            self._next += 1
            self._events.append(item)
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(item)
            except queue.Full:
                with self._lock:
                    if subscriber in self._subscribers:
                        self._subscribers.remove(subscriber)
                try:
                    subscriber.get_nowait()
                    subscriber.put_nowait(
                        (self._next, {"t": "closed", "status": "subscriber_overflow"})
                    )
                except queue.Empty:
                    pass
        return item

    def subscribe(self, after=-1):
        subscriber = queue.Queue(maxsize=SUBSCRIBER_QUEUE)
        with self._lock:
            if len(self._subscribers) >= MAX_SUBSCRIBERS:
                raise RequestError(429, "too many event subscribers")
            backlog = [item for item in self._events if item[0] > after]
            self._subscribers.append(subscriber)
        return subscriber, backlog

    def unsubscribe(self, subscriber):
        with self._lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)

    def snapshot(self):
        with self._lock:
            return list(self._events)


class ConfirmationLedger:
    """One-shot decisions bound to a run, confirmation id, and nonce."""

    def __init__(self, run_id):
        self.run_id = run_id
        self._pending = {}
        self._lock = threading.RLock()

    def register(self, confirmation_id, nonce):
        require_string(confirmation_id, "confirmation_id", maximum=128)
        require_string(nonce, "nonce", minimum=32, maximum=256)
        with self._lock:
            if confirmation_id in self._pending:
                raise ValueError("duplicate confirmation id")
            self._pending[confirmation_id] = nonce

    def decide(self, run_id, confirmation_id, nonce, decision):
        if run_id != self.run_id:
            raise RequestError(409, "confirmation belongs to another run")
        if not isinstance(decision, bool):
            raise RequestError(400, "decision must be a boolean")
        with self._lock:
            expected = self._pending.get(confirmation_id)
            if expected is None:
                raise RequestError(409, "confirmation is stale or unknown")
            if not secrets.compare_digest(expected, nonce):
                raise RequestError(409, "confirmation nonce does not match")
            del self._pending[confirmation_id]
        return {
            "run_id": run_id,
            "confirmation_id": confirmation_id,
            "nonce": nonce,
            "decision": decision,
        }

    def clear(self):
        with self._lock:
            self._pending.clear()


class ConfirmationChannel:
    """Runner-side, exact JSONL confirmation channel (never generic stdin)."""

    def __init__(self, input_stream, emit, run_id, timeout=CONFIRMATION_TIMEOUT_SECONDS):
        self._input = input_stream
        self._emit = emit
        self._run_id = require_string(run_id, "run_id", maximum=128)
        self._timeout = timeout
        self._responses = queue.Queue(maxsize=1)
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self):
        while True:
            line = self._input.readline()
            if not line:
                self._responses.put(None)
                return
            try:
                value = json.loads(line)
            except (TypeError, json.JSONDecodeError):
                value = None
            self._responses.put(value)

    def confirm(self, action, detail, real=None, mode=None):
        """Ask the operator. `real` names the connected account when the call
        reaches one, and `mode` says whether that account can transmit.

        Named fields rather than an open bag: this event is the security
        prompt, and a call that empties a real mailbox must not look identical
        to one that writes a scratch file."""
        confirmation_id = secrets.token_urlsafe(18)
        nonce = secrets.token_urlsafe(32)
        extra = {}
        if real:
            extra["real"] = str(real)[:64]
            extra["mode"] = str(mode or "draft")[:32]
        self._emit(
            "confirmation",
            run_id=self._run_id,
            confirmation_id=confirmation_id,
            nonce=nonce,
            action=str(action)[:256],
            detail=str(detail)[:4_096],
            **extra,
        )
        try:
            value = self._responses.get(timeout=self._timeout)
        except queue.Empty:
            return False
        if not isinstance(value, dict) or set(value) != {
            "run_id", "confirmation_id", "nonce", "decision"
        }:
            return False
        return bool(
            value["run_id"] == self._run_id
            and value["confirmation_id"] == confirmation_id
            and secrets.compare_digest(str(value["nonce"]), nonce)
            and value["decision"] is True
        )


class _WindowsJob:
    """A kill-on-close Windows Job Object for a subprocess tree."""

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class _BASIC_LIMIT(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", ctypes.c_ulong),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_ulong),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_ulong),
            ("SchedulingClass", ctypes.c_ulong),
        ]

    class _EXTENDED_LIMIT(ctypes.Structure):
        pass

    _EXTENDED_LIMIT._fields_ = [
        ("BasicLimitInformation", _BASIC_LIMIT),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]

    def __init__(self, proc):
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = ctypes.c_void_p
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        kernel32.SetInformationJobObject.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong
        ]
        kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        kernel32.TerminateJobObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        self._kernel32 = kernel32
        self._handle = kernel32.CreateJobObjectW(None, None)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = self._EXTENDED_LIMIT()
        limits.BasicLimitInformation.LimitFlags = self.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            self._handle,
            self.JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())
        process_handle = ctypes.c_void_p(int(proc._handle))
        if not kernel32.AssignProcessToJobObject(self._handle, process_handle):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())

    def terminate(self):
        if self._handle and not self._kernel32.TerminateJobObject(self._handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


class ProcessTree:
    """A subprocess whose complete descendant tree is owned by the caller."""

    def __init__(self, proc, job=None):
        self.proc = proc
        self._job = job
        self._lock = threading.RLock()
        self._closed = False

    @classmethod
    def start(cls, command, **kwargs):
        platform = os.name
        if platform == "nt":
            kwargs["creationflags"] = (
                kwargs.get("creationflags", 0) | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(command, **kwargs)
        try:
            job = _WindowsJob(proc) if platform == "nt" else None
        except Exception:
            proc.terminate()
            proc.wait(timeout=5)
            raise
        return cls(proc, job)

    def terminate(self, grace_seconds=3.0):
        with self._lock:
            if self.proc.poll() is not None:
                self.close()
                return
            if os.name == "nt":
                self._job.terminate()
            else:
                try:
                    os.killpg(self.proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    self.proc.wait(timeout=grace_seconds)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(self.proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            try:
                self.proc.wait(timeout=max(grace_seconds, 0.1))
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
            self.close()

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._job is not None:
                self._job.close()
                self._job = None
            elif os.name != "nt":
                # The leader may have exited while a descendant remains.
                try:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
