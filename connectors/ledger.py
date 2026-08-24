"""Minimal append-only operation ledger for non-idempotent provider writes."""
import hashlib
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import threading
import time

from .errors import AmbiguousWrite, ConnectorConfigError, ConnectorUnavailable


LEDGER_SCHEMA = "brick.connector-operation/1"
_RECORD_KEYS = frozenset(
    (
        "schema_version", "ts_unix_ms", "provider", "operation",
        "client_key", "confirmed", "status", "object_sha256",
    )
)
_STATUSES = frozenset(("prepared", "done", "rejected", "unknown", "verified"))
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@contextmanager
def _process_lock(handle):
    """One-byte cross-process lock guarding append/replay decisions."""
    handle.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _validate_record(record):
    if not isinstance(record, dict) or set(record) != _RECORD_KEYS:
        raise ConnectorUnavailable("connector operation ledger is corrupt")
    if record["schema_version"] != LEDGER_SCHEMA:
        raise ConnectorUnavailable("connector operation ledger schema is unsupported")
    if type(record["ts_unix_ms"]) is not int or record["ts_unix_ms"] < 0:
        raise ConnectorUnavailable("connector operation ledger timestamp is invalid")
    if any(
        not isinstance(record[field], str) or not record[field]
        for field in ("provider", "operation", "client_key")
    ):
        raise ConnectorUnavailable("connector operation ledger identity is invalid")
    if not _SHA256.fullmatch(record["client_key"]):
        raise ConnectorUnavailable("connector operation ledger key is invalid")
    if record["status"] not in _STATUSES:
        raise ConnectorUnavailable("connector operation ledger status is invalid")
    if record["confirmed"] is not True:
        raise ConnectorUnavailable("connector operation ledger confirmation is invalid")
    object_digest = record["object_sha256"]
    if object_digest is not None and (
        not isinstance(object_digest, str) or not _SHA256.fullmatch(object_digest)
    ):
        raise ConnectorUnavailable("connector operation ledger object digest is invalid")
    return record


def default_ledger_path():
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".brick"
    return root / "Brick" / "connectors" / "operation-ledger.jsonl"


def client_key(account_scope, tool_name, args):
    payload = json.dumps(
        {"account_scope": account_scope, "tool": tool_name, "args": args},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class OperationLedger:
    def __init__(self, path=None, project_root=None):
        self.path = Path(path or default_ledger_path()).resolve()
        if project_root is not None:
            project = Path(project_root).resolve()
            try:
                self.path.relative_to(project)
            except ValueError:
                pass
            else:
                raise ConnectorConfigError("connector ledger must stay outside the repository")
        self._lock = threading.Lock()

    def _append(self, record):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(
            record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ) + "\n"
        with self._lock:
            with open(self.path, "a+", encoding="utf-8", newline="\n") as handle:
                with _process_lock(handle):
                    handle.seek(0, os.SEEK_END)
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())

    def reserve(self, *, provider, operation, key, object_id=None):
        """Atomically refuse a prior uncertain/done write or record PREPARED."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        object_hash = (
            hashlib.sha256(str(object_id).encode("utf-8")).hexdigest()
            if object_id not in (None, "")
            else None
        )
        record = {
            "schema_version": LEDGER_SCHEMA,
            "ts_unix_ms": int(time.time() * 1000),
            "provider": provider,
            "operation": operation,
            "client_key": key,
            "confirmed": True,
            "status": "prepared",
            "object_sha256": object_hash,
        }
        _validate_record(record)
        encoded = json.dumps(
            record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ) + "\n"
        with self._lock:
            with open(self.path, "a+", encoding="utf-8", newline="\n") as handle:
                with _process_lock(handle):
                    handle.seek(0)
                    latest = None
                    for line in handle:
                        try:
                            existing = json.loads(line)
                        except ValueError as exc:
                            raise ConnectorUnavailable(
                                "connector operation ledger is corrupt"
                            ) from exc
                        _validate_record(existing)
                        if existing["client_key"] == key:
                            latest = existing
                    if latest and latest["status"] in (
                        "prepared", "done", "unknown", "verified"
                    ):
                        raise AmbiguousWrite(
                            "this write already started for the bound account; "
                            "reconcile it instead of retrying"
                        )
                    handle.seek(0, os.SEEK_END)
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
        return record

    def record(self, *, provider, operation, key, status, object_id=None):
        if status not in _STATUSES:
            raise ValueError("invalid connector ledger status")
        object_hash = (
            hashlib.sha256(str(object_id).encode("utf-8")).hexdigest()
            if object_id not in (None, "")
            else None
        )
        record = {
                "schema_version": LEDGER_SCHEMA,
                "ts_unix_ms": int(time.time() * 1000),
                "provider": provider,
                "operation": operation,
                "client_key": key,
                "confirmed": True,
                "status": status,
                "object_sha256": object_hash,
            }
        _validate_record(record)
        self._append(record)

    def latest(self, key):
        if not self.path.is_file():
            return None
        latest = None
        with self._lock:
            with open(self.path, "r+", encoding="utf-8") as handle:
                with _process_lock(handle):
                    handle.seek(0)
                    for line in handle:
                        try:
                            record = json.loads(line)
                        except ValueError as exc:
                            raise ConnectorUnavailable(
                                "connector operation ledger is corrupt"
                            ) from exc
                        _validate_record(record)
                        if record["client_key"] == key:
                            latest = record
        return latest
