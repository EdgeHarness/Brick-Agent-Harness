"""Durable, privacy-preserving lifecycle evidence for receipt-v1 runs.

The journal is deliberately smaller than a conversation transcript.  It
records control-flow facts and hashes, never prompts, tool arguments, tool
observations, or provider errors.  A tool is not dispatched until its
``tool.dispatch_committed`` record has been flushed and fsynced.

The format borrows the useful invariant shared by append-only agent runtimes:
events are immutable, each event commits to its predecessor, and terminal
state is explicit.  It is not a resumable conversation log and makes no claim
that a hash chain protects a host an attacker already controls.
"""

import hashlib
import json
import os
from pathlib import Path
import re


LIFECYCLE_VERSION = "brick.lifecycle/1"
GENESIS_HASH = "0" * 64
TERMINAL_EVENTS = frozenset(
    {"run.completed", "run.incomplete", "run.failed", "run.cancelled"}
)


class LifecycleError(RuntimeError):
    """Base class for lifecycle contract failures."""


class JournalWriteError(LifecycleError):
    """A durable append did not complete; no dependent effect may start."""


class JournalValidationError(LifecycleError):
    """A journal is malformed, tampered with, or relationally impossible."""


_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_KEY = re.compile(r"^[a-z][a-z0-9_]*$")
_FORBIDDEN_KEYS = frozenset(
    {
        "args",
        "arguments",
        "content",
        "credential",
        "email",
        "error",
        "message",
        "observation",
        "password",
        "prompt",
        "result",
        "secret",
        "token",
    }
)

# Each event has a closed payload schema.  Values still receive a conservative
# scalar/length check below.  Digest fields are verified as SHA-256 hex.
_EVENT_FIELDS = {
    "run.started": frozenset(
        {"protocol", "domain", "recipe_digest", "router_digest", "task_ref"}
    ),
    "model.requested": frozenset(
        {"request_id", "role", "message_count", "input_digest", "route_digest"}
    ),
    "model.returned": frozenset(
        {"request_id", "output_digest", "parsed"}
    ),
    "model.failed": frozenset({"request_id", "failure_class"}),
    "plan.accepted": frozenset({"plan_digest", "step_count"}),
    "tool.proposed": frozenset(
        {"call_id", "tool", "args_digest", "ledger_entry"}
    ),
    "tool.rejected": frozenset({"call_id", "tool", "reason_code"}),
    "tool.dispatch_committed": frozenset({"call_id", "tool", "effect"}),
    "tool.succeeded": frozenset({"call_id", "tool", "result_digest"}),
    "tool.failed": frozenset({"call_id", "tool", "failure_class"}),
    "receipt.issued": frozenset(
        {"call_id", "receipt_id", "tool", "issuer"}
    ),
    "ledger.grounded": frozenset({"receipt_id", "ledger_entry"}),
    "ledger.unmatched": frozenset({"receipt_id", "tool"}),
    "completion.checked": frozenset(
        {"status", "reason", "ledger_complete"}
    ),
    "run.completed": frozenset({"status", "completion_status"}),
    "run.incomplete": frozenset({"status", "completion_status", "reason"}),
    "run.failed": frozenset({"status", "reason"}),
    "run.cancelled": frozenset({"status", "reason"}),
}

_DIGEST_FIELDS = frozenset(
    {
        "args_digest",
        "input_digest",
        "output_digest",
        "plan_digest",
        "recipe_digest",
        "result_digest",
        "route_digest",
        "router_digest",
    }
)


def canonical_json_bytes(value):
    """Return the one byte representation used by lifecycle hashes."""
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest_value(value):
    """Hash sensitive model/tool data without putting it in the journal."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _validate_payload(event_type, payload):
    expected = _EVENT_FIELDS.get(event_type)
    if expected is None:
        raise JournalValidationError(
            "unknown lifecycle event {!r}".format(event_type)
        )
    if not isinstance(payload, dict) or set(payload) != set(expected):
        raise JournalValidationError(
            "{} payload fields must be exactly: {}".format(
                event_type, ", ".join(sorted(expected))
            )
        )
    for key, value in payload.items():
        if not _SAFE_KEY.fullmatch(key) or key in _FORBIDDEN_KEYS:
            raise JournalValidationError(
                "unsafe lifecycle payload key {!r}".format(key)
            )
        if key in _DIGEST_FIELDS:
            if not isinstance(value, str) or not _HEX_64.fullmatch(value):
                raise JournalValidationError(
                    "{} must be a SHA-256 hex digest".format(key)
                )
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and value >= 0:
            continue
        if not isinstance(value, str) or not value or len(value) > 256:
            raise JournalValidationError(
                "{} must be a nonempty bounded scalar".format(key)
            )
    if event_type == "completion.checked" and payload["status"] not in {
        "complete", "incomplete", "unknown"
    }:
        raise JournalValidationError("completion status is invalid")
    terminal_status = {
        "run.completed": "completed",
        "run.incomplete": "incomplete",
        "run.failed": "failed",
        "run.cancelled": "cancelled",
    }.get(event_type)
    if terminal_status is not None and payload["status"] != terminal_status:
        raise JournalValidationError("terminal status does not match event")
    if event_type in {"run.completed", "run.incomplete"} and payload[
        "completion_status"
    ] not in {"complete", "incomplete", "unknown"}:
        raise JournalValidationError("terminal completion status is invalid")


def journal_path(workdir, attempt_id):
    """Choose a private runtime path that strict artifact graders ignore."""
    name = hashlib.sha256(attempt_id.encode("utf-8")).hexdigest() + ".jsonl"
    return Path(workdir, ".brick-runtime", name)


class LifecycleJournal:
    """Exclusive append-only JSONL journal with a SHA-256 hash chain."""

    def __init__(self, path, fsync=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fsync = os.fsync if fsync is None else fsync
        self._records = []
        self._last_hash = GENESIS_HASH
        self._terminal = False
        try:
            self._stream = open(self.path, "x+b")
        except OSError as exc:
            raise JournalWriteError(
                "cannot create lifecycle journal: {}".format(type(exc).__name__)
            ) from exc

    @property
    def records(self):
        return tuple(json.loads(json.dumps(item)) for item in self._records)

    @property
    def terminal(self):
        return self._terminal

    def append(self, event_type, payload):
        if self._terminal:
            raise JournalValidationError("terminal lifecycle state is immutable")
        _validate_payload(event_type, payload)
        core = {
            "schema_version": LIFECYCLE_VERSION,
            "sequence": len(self._records),
            "event_type": event_type,
            "payload": dict(payload),
            "previous_hash": self._last_hash,
        }
        event_hash = hashlib.sha256(canonical_json_bytes(core)).hexdigest()
        record = dict(core, event_hash=event_hash)
        encoded = canonical_json_bytes(record) + b"\n"
        try:
            self._stream.write(encoded)
            self._stream.flush()
            self._fsync(self._stream.fileno())
        except Exception as exc:
            # Internal state does not advance.  A caller must treat this as a
            # hard stop because the file may contain a partial final line.
            raise JournalWriteError(
                "lifecycle append was not durable: {}".format(type(exc).__name__)
            ) from exc
        self._records.append(record)
        self._last_hash = event_hash
        if event_type in TERMINAL_EVENTS:
            self._terminal = True
        return json.loads(json.dumps(record))

    def close(self):
        stream = getattr(self, "_stream", None)
        if stream is not None and not stream.closed:
            stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
        return False


def _verify_record(record, sequence, previous_hash):
    required = {
        "schema_version",
        "sequence",
        "event_type",
        "payload",
        "previous_hash",
        "event_hash",
    }
    if not isinstance(record, dict) or set(record) != required:
        raise JournalValidationError("lifecycle record fields are invalid")
    if record["schema_version"] != LIFECYCLE_VERSION:
        raise JournalValidationError("unsupported lifecycle schema")
    if record["sequence"] != sequence:
        raise JournalValidationError("lifecycle sequence is not contiguous")
    if record["previous_hash"] != previous_hash:
        raise JournalValidationError("lifecycle predecessor hash is invalid")
    _validate_payload(record["event_type"], record["payload"])
    core = {key: record[key] for key in required - {"event_hash"}}
    expected = hashlib.sha256(canonical_json_bytes(core)).hexdigest()
    if record["event_hash"] != expected:
        raise JournalValidationError("lifecycle event hash is invalid")
    return expected


def verify_records(records, require_terminal=True):
    """Verify hashes plus request, dispatch, receipt, and terminal relations."""
    if not isinstance(records, (list, tuple)) or not records:
        raise JournalValidationError("lifecycle journal is empty")
    previous = GENESIS_HASH
    pending_models = set()
    tool_states = {}
    tool_names = {}
    succeeded = set()
    receipts = set()
    receipted_calls = set()
    consumed_receipts = set()
    completion = None
    terminal_seen = False

    for index, record in enumerate(records):
        previous = _verify_record(record, index, previous)
        event = record["event_type"]
        payload = record["payload"]
        if index == 0 and event != "run.started":
            raise JournalValidationError("run.started must be the first event")
        if index > 0 and event == "run.started":
            raise JournalValidationError("run.started may occur only once")
        if terminal_seen:
            raise JournalValidationError("event follows terminal state")

        if event == "model.requested":
            request_id = payload["request_id"]
            if pending_models:
                raise JournalValidationError("model requests are not serialized")
            pending_models.add(request_id)
        elif event in {"model.returned", "model.failed"}:
            request_id = payload["request_id"]
            if request_id not in pending_models:
                raise JournalValidationError("model result has no request")
            pending_models.remove(request_id)
        elif event == "tool.proposed":
            call_id = payload["call_id"]
            if call_id in tool_states:
                raise JournalValidationError("duplicate tool call id")
            tool_states[call_id] = "proposed"
            tool_names[call_id] = payload["tool"]
        elif event == "tool.rejected":
            call_id = payload["call_id"]
            if tool_states.get(call_id) != "proposed":
                raise JournalValidationError("tool rejection has no proposal")
            if tool_names[call_id] != payload["tool"]:
                raise JournalValidationError("tool rejection name changed")
            tool_states[call_id] = "rejected"
        elif event == "tool.dispatch_committed":
            call_id = payload["call_id"]
            if tool_states.get(call_id) != "proposed":
                raise JournalValidationError("tool dispatch has no proposal")
            if tool_names[call_id] != payload["tool"]:
                raise JournalValidationError("tool dispatch name changed")
            tool_states[call_id] = "dispatched"
        elif event in {"tool.succeeded", "tool.failed"}:
            call_id = payload["call_id"]
            if tool_states.get(call_id) != "dispatched":
                raise JournalValidationError("tool result has no dispatch")
            if tool_names[call_id] != payload["tool"]:
                raise JournalValidationError("tool result name changed")
            tool_states[call_id] = "succeeded" if event == "tool.succeeded" else "failed"
            if event == "tool.succeeded":
                succeeded.add(call_id)
        elif event == "receipt.issued":
            if payload["call_id"] not in succeeded:
                raise JournalValidationError("receipt has no successful call")
            if payload["call_id"] in receipted_calls:
                raise JournalValidationError("successful call has two receipts")
            if tool_names[payload["call_id"]] != payload["tool"]:
                raise JournalValidationError("receipt tool name changed")
            if payload["receipt_id"] in receipts:
                raise JournalValidationError("duplicate receipt id")
            receipts.add(payload["receipt_id"])
            receipted_calls.add(payload["call_id"])
        elif event in {"ledger.grounded", "ledger.unmatched"}:
            if payload["receipt_id"] not in receipts:
                raise JournalValidationError("ledger event has no receipt")
            if payload["receipt_id"] in consumed_receipts:
                raise JournalValidationError("receipt was consumed twice")
            consumed_receipts.add(payload["receipt_id"])
        elif event == "completion.checked":
            completion = payload
        elif event in TERMINAL_EVENTS:
            terminal_seen = True
            if pending_models:
                raise JournalValidationError("terminal state has a pending model request")
            if any(state in {"proposed", "dispatched"} for state in tool_states.values()):
                raise JournalValidationError("terminal state has a pending tool call")
            if event == "run.completed" and (
                completion is None
                or completion["status"] != "complete"
                or completion["ledger_complete"] is not True
                or succeeded != receipted_calls
                or receipts != consumed_receipts
            ):
                raise JournalValidationError(
                    "completed run lacks authoritative grounded completion"
                )

    if require_terminal and not terminal_seen:
        raise JournalValidationError("lifecycle journal has no terminal state")
    return tuple(json.loads(json.dumps(item)) for item in records)


def read_and_verify(path, require_terminal=True):
    records = []
    try:
        with open(path, "rb") as stream:
            for line in stream:
                if not line.endswith(b"\n"):
                    raise JournalValidationError("partial lifecycle record")
                try:
                    records.append(json.loads(line.decode("utf-8")))
                except (UnicodeDecodeError, ValueError) as exc:
                    raise JournalValidationError("invalid lifecycle JSON") from exc
    except OSError as exc:
        raise JournalValidationError("cannot read lifecycle journal") from exc
    return verify_records(records, require_terminal=require_terminal)


__all__ = [
    "GENESIS_HASH",
    "LIFECYCLE_VERSION",
    "LifecycleError",
    "LifecycleJournal",
    "JournalValidationError",
    "JournalWriteError",
    "TERMINAL_EVENTS",
    "canonical_json_bytes",
    "digest_value",
    "journal_path",
    "read_and_verify",
    "verify_records",
]
