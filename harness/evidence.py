"""Production marker-last attempt evidence store.

The store deliberately separates logical attempt identity from physical
execution.  A logical :class:`AttemptKey` hashes to one directory.  Every
execution receives a fresh UUID directory created directly in that final
location.  A candidate is visible to readers only after all evidence has been
closed, flushed, hashed into ``PREPARED.json``, and an empty ``COMMITTED``
marker has been created exclusively.

The durability claim is intentionally narrow: fail-closed recovery after
process termination on a cooperative local filesystem.  This module does not
claim sudden-power-loss durability or protection from a hostile local user who
can rewrite both evidence and manifests.
"""

import copy
import ctypes
from dataclasses import dataclass
import errno
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import threading
import time
import unicodedata
import uuid


ATTEMPT_KEY_SCHEMA = "brick.attempt-key/1"
RUN_SCHEMA = "brick.evidence-run/1"
ATTEMPT_SCHEMA = "brick.evidence-attempt/1"
STATE_SCHEMA = "brick.evidence-state/1"
RESULT_SCHEMA = "brick.evidence-result/1"
GRADE_SCHEMA = "brick.evidence-grade/1"
ACTIONS_SCHEMA = "brick.evidence-actions/1"
PREPARED_SCHEMA = "brick.evidence-prepared/1"
PROJECTION_SCHEMA = "brick.evidence-results/1"

PREPARED = "PREPARED.json"
COMMITTED = "COMMITTED"
RESULTS = "results.json"
RESULTS_TEMP = "results.json.tmp"

REQUIRED_EVIDENCE_FILES = frozenset(
    {
        "actions.json",
        "attempt.json",
        "final-state.json",
        "grade.json",
        "initial-state.json",
        "memory-delta.jsonl",
        "result.json",
        "transcript.md",
    }
)
_EXECUTION_STATUSES = frozenset(
    {
        "done",
        "budget_exhausted",
        "model_error",
        "runner_error",
        "timeout",
        "aborted",
        "environment_unstable",
    }
)
_GRADER_STATUSES = frozenset({"graded", "grader_error", "not_run"})
_TOOL_STATUSES = frozenset({"clean", "had_errors"})
_FAILURE_ORIGINS = frozenset(
    {"model", "runner", "environment", "operator"}
)
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {"com%d" % index for index in range(1, 10)}
    | {"lpt%d" % index for index in range(1, 10)}
)
_WINDOWS_FORBIDDEN = frozenset('<>:"\\|?*')
_RETRY_DELAYS = (0.0, 0.05, 0.1, 0.2, 0.4, 0.8, 1.6)
_RETRYABLE_WINERRORS = frozenset({5, 32, 33})
_LOCK_REGISTRY = set()
_LOCK_REGISTRY_GUARD = threading.Lock()


class EvidenceError(RuntimeError):
    """Base class for evidence-store failures."""


class EvidenceIntegrityError(EvidenceError):
    """Evidence or filesystem state cannot be trusted."""


class LogicalCollisionError(EvidenceIntegrityError):
    """One logical digest contains a different complete AttemptKey."""


class DuplicateCandidateError(EvidenceIntegrityError):
    """More than one valid candidate exists for one logical attempt."""


class RunLockedError(EvidenceError):
    """Another writer owns the persistent run lock."""


class CandidateStateError(EvidenceError):
    """The requested candidate operation is invalid for its current state."""


class SchemaError(EvidenceIntegrityError):
    """A versioned evidence document violates its frozen schema."""


def _sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_digest(value, label):
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError("%s must be a lowercase SHA-256 digest" % label)
    return value


def _require_model_digest(value):
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", value)
    ):
        raise ValueError(
            "model_digest must be an immutable sha256:<lowercase-hex> digest"
        )
    return value


def _require_text(value, label):
    if not isinstance(value, str) or not value:
        raise ValueError("%s must be a nonempty string" % label)
    normalized = unicodedata.normalize("NFC", value)
    if any(ord(character) < 0x20 for character in normalized):
        raise ValueError("%s cannot contain control characters" % label)
    return normalized


def _safe_component(value, label):
    if not isinstance(value, str) or not _COMPONENT.fullmatch(value):
        raise ValueError("%s is not a safe path component" % label)
    if value.endswith((" ", ".")):
        raise ValueError(
            "%s cannot end with a Windows-trimmed character" % label
        )
    if value.split(".", 1)[0].casefold() in _WINDOWS_RESERVED:
        raise ValueError("%s is a reserved Windows device name" % label)
    return value


def _logical_hash(value):
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise EvidenceIntegrityError(
            "logical directory must be a lowercase SHA-256 digest"
        )
    return value


def _physical_uuid(value):
    _safe_component(value, "physical id")
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise EvidenceIntegrityError(
            "physical directory must use a canonical UUID"
        ) from exc
    if str(parsed) != value:
        raise EvidenceIntegrityError(
            "physical directory must use a canonical UUID"
        )
    return value


def _normalize_json(value, label="$", allow_float=True):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not allow_float:
            raise ValueError(
                "%s cannot contain binary floats; use a canonical decimal "
                "string" % label
            )
        if not math.isfinite(value):
            raise ValueError("%s cannot contain NaN or infinity" % label)
        return value
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, (list, tuple)):
        return [
            _normalize_json(
                member,
                "%s[%d]" % (label, index),
                allow_float=allow_float,
            )
            for index, member in enumerate(value)
        ]
    if isinstance(value, dict):
        normalized = {}
        for key, member in value.items():
            if not isinstance(key, str):
                raise ValueError("%s object keys must be strings" % label)
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in normalized:
                raise ValueError(
                    "%s contains object keys that collide after NFC "
                    "normalization" % label
                )
            normalized[normalized_key] = _normalize_json(
                member,
                "%s.%s" % (label, normalized_key),
                allow_float=allow_float,
            )
        return normalized
    raise ValueError(
        "%s contains unsupported JSON type %s"
        % (label, type(value).__name__)
    )


def _normalize_identity_json(value, label="$"):
    """Normalize JSON embedded in an AttemptKey.

    Attempt identity is intentionally stricter than opaque evidence payloads:
    every string, including an object key, is nonempty, control-free NFC and
    binary floats are forbidden.  Keeping this policy separate lets later
    versioned evidence schemas own the semantics of their opaque payloads.
    """

    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise ValueError(
            "%s cannot contain binary floats; use a canonical decimal string"
            % label
        )
    if isinstance(value, str):
        return _require_text(value, label)
    if isinstance(value, (list, tuple)):
        return [
            _normalize_identity_json(
                member,
                "%s[%d]" % (label, index),
            )
            for index, member in enumerate(value)
        ]
    if isinstance(value, dict):
        normalized = {}
        for key, member in value.items():
            normalized_key = _require_text(key, label + " object key")
            if normalized_key in normalized:
                raise ValueError(
                    "%s contains object keys that collide after NFC "
                    "normalization" % label
                )
            normalized[normalized_key] = _normalize_identity_json(
                member,
                "%s.%s" % (label, normalized_key),
            )
        return normalized
    raise ValueError(
        "%s contains unsupported JSON type %s"
        % (label, type(value).__name__)
    )


def canonical_json_bytes(value, allow_float=True, newline=False):
    """Return versioned canonical UTF-8 JSON bytes.

    Mapping order never influences the result.  AttemptKey calls this with
    ``allow_float=False`` so fractional sampling values must be exact decimal
    strings rather than binary floats.
    """

    normalized = _normalize_json(value, allow_float=allow_float)
    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return payload + (b"\n" if newline else b"")


def _reject_duplicate_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SchemaError("duplicate JSON object key %r" % key)
        result[key] = value
    return result


class _CallableDigest(str):
    """Compatibility string that also returns itself when called."""

    def __call__(self):
        return str(self)


def _decode_json_bytes(payload, label):
    try:
        text = payload.decode("utf-8")
    except UnicodeError as exc:
        raise SchemaError("%s is not valid UTF-8" % label) from exc
    try:
        value = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except SchemaError:
        raise
    except (TypeError, ValueError) as exc:
        raise SchemaError("%s is not valid JSON: %s" % (label, exc)) from exc
    try:
        return _normalize_json(value)
    except ValueError as exc:
        raise SchemaError("%s is not canonical JSON data: %s" % (label, exc))


def _decode_canonical_json_bytes(payload, label, newline=True):
    value = _decode_json_bytes(payload, label)
    if payload != canonical_json_bytes(value, newline=newline):
        raise SchemaError("%s bytes are not canonical JSON" % label)
    return value


def _load_json(path, label=None):
    path = Path(path)
    try:
        payload = path.read_bytes()
    except OSError:
        raise
    return _decode_canonical_json_bytes(payload, label or path.name)


def _require_exact_keys(value, expected, label):
    if not isinstance(value, dict):
        raise SchemaError("%s must be an object" % label)
    missing = set(expected) - set(value)
    extra = set(value) - set(expected)
    if missing or extra:
        details = []
        if missing:
            details.append("missing " + ", ".join(sorted(missing)))
        if extra:
            details.append("unknown " + ", ".join(sorted(extra)))
        raise SchemaError("%s has %s" % (label, "; ".join(details)))


class AttemptKey:
    """Frozen, complete logical identity for one benchmark attempt."""

    __slots__ = ("_document", "_canonical", "_logical_hash")

    def __init__(
        self,
        *,
        domain_name,
        domain_version,
        domain_content_sha256,
        task_family,
        task_version,
        generator_version,
        grader_version,
        model_tag,
        model_digest,
        condition_name,
        condition_version,
        mechanism_sha256,
        instance_id,
        instance_content_sha256,
        ordered_subepisodes,
        repeat,
        sampling,
        opportunity_budget,
        prompt_sha256,
        tool_schema_sha256
    ):
        if isinstance(repeat, bool) or not isinstance(repeat, int) or repeat < 0:
            raise ValueError("repeat must be a nonnegative integer")
        if not isinstance(ordered_subepisodes, (list, tuple)):
            raise ValueError("ordered_subepisodes must be a list or tuple")
        subepisodes = [
            _require_text(value, "ordered_subepisodes")
            for value in ordered_subepisodes
        ]
        if len(set(subepisodes)) != len(subepisodes):
            raise ValueError("ordered_subepisodes cannot contain duplicates")
        if not isinstance(sampling, dict) or not sampling:
            raise ValueError("sampling must be a nonempty object")
        if not isinstance(opportunity_budget, dict) or not opportunity_budget:
            raise ValueError("opportunity_budget must be a nonempty object")
        normalized_sampling = _normalize_identity_json(
            sampling, "sampling"
        )
        normalized_budget = _normalize_identity_json(
            opportunity_budget, "opportunity_budget"
        )
        for budget_value in normalized_budget.values():
            if (
                isinstance(budget_value, bool)
                or not isinstance(budget_value, int)
                or budget_value < 0
            ):
                raise ValueError(
                    "opportunity_budget values must be nonnegative integers"
                )
        document = {
            "schema_version": ATTEMPT_KEY_SCHEMA,
            "domain": {
                "name": _require_text(domain_name, "domain_name"),
                "version": _require_text(domain_version, "domain_version"),
                "content_sha256": _require_digest(
                    domain_content_sha256, "domain_content_sha256"
                ),
            },
            "task": {
                "family": _require_text(task_family, "task_family"),
                "version": _require_text(task_version, "task_version"),
            },
            "generator_version": _require_text(
                generator_version, "generator_version"
            ),
            "grader_version": _require_text(
                grader_version, "grader_version"
            ),
            "model": {
                "tag": _require_text(model_tag, "model_tag"),
                "digest": _require_model_digest(model_digest),
            },
            "condition": {
                "name": _require_text(condition_name, "condition_name"),
                "version": _require_text(
                    condition_version, "condition_version"
                ),
                "mechanism_sha256": _require_digest(
                    mechanism_sha256, "mechanism_sha256"
                ),
            },
            "instance": {
                "id": _require_text(instance_id, "instance_id"),
                "content_sha256": _require_digest(
                    instance_content_sha256,
                    "instance_content_sha256",
                ),
            },
            "ordered_subepisodes": subepisodes,
            "repeat": repeat,
            "sampling": normalized_sampling,
            "opportunity_budget": normalized_budget,
            "prompt_sha256": _require_digest(
                prompt_sha256, "prompt_sha256"
            ),
            "tool_schema_sha256": _require_digest(
                tool_schema_sha256, "tool_schema_sha256"
            ),
        }
        canonical = canonical_json_bytes(document, allow_float=False)
        object.__setattr__(self, "_document", document)
        object.__setattr__(self, "_canonical", canonical)
        object.__setattr__(self, "_logical_hash", _sha256_bytes(canonical))

    @classmethod
    def from_dict(cls, document):
        _validate_attempt_key_document(document)
        return cls(
            domain_name=document["domain"]["name"],
            domain_version=document["domain"]["version"],
            domain_content_sha256=document["domain"]["content_sha256"],
            task_family=document["task"]["family"],
            task_version=document["task"]["version"],
            generator_version=document["generator_version"],
            grader_version=document["grader_version"],
            model_tag=document["model"]["tag"],
            model_digest=document["model"]["digest"],
            condition_name=document["condition"]["name"],
            condition_version=document["condition"]["version"],
            mechanism_sha256=document["condition"]["mechanism_sha256"],
            instance_id=document["instance"]["id"],
            instance_content_sha256=document["instance"]["content_sha256"],
            ordered_subepisodes=document["ordered_subepisodes"],
            repeat=document["repeat"],
            sampling=document["sampling"],
            opportunity_budget=document["opportunity_budget"],
            prompt_sha256=document["prompt_sha256"],
            tool_schema_sha256=document["tool_schema_sha256"],
        )

    def to_dict(self):
        return copy.deepcopy(self._document)

    def canonical_bytes(self):
        return self._canonical

    @property
    def logical_hash(self):
        return _CallableDigest(self._logical_hash)

    def __eq__(self, other):
        return (
            isinstance(other, AttemptKey)
            and self._canonical == other._canonical
        )

    def __hash__(self):
        return hash(self._canonical)


def _validate_attempt_key_document(document):
    expected = {
        "schema_version",
        "domain",
        "task",
        "generator_version",
        "grader_version",
        "model",
        "condition",
        "instance",
        "ordered_subepisodes",
        "repeat",
        "sampling",
        "opportunity_budget",
        "prompt_sha256",
        "tool_schema_sha256",
    }
    _require_exact_keys(document, expected, "AttemptKey")
    if document["schema_version"] != ATTEMPT_KEY_SCHEMA:
        raise SchemaError("unsupported AttemptKey schema")
    _require_exact_keys(
        document["domain"],
        {"name", "version", "content_sha256"},
        "AttemptKey.domain",
    )
    _require_exact_keys(
        document["task"], {"family", "version"}, "AttemptKey.task"
    )
    _require_exact_keys(
        document["model"], {"tag", "digest"}, "AttemptKey.model"
    )
    _require_exact_keys(
        document["condition"],
        {"name", "version", "mechanism_sha256"},
        "AttemptKey.condition",
    )
    _require_exact_keys(
        document["instance"],
        {"id", "content_sha256"},
        "AttemptKey.instance",
    )
    # The constructor performs all remaining type and canonical-value checks.


def _lexists(path):
    return os.path.lexists(str(path))


def _optional_lstat(path):
    """Return lstat data, distinguishing absence from every other failure."""

    try:
        return Path(path).lstat()
    except FileNotFoundError:
        return None


def _is_reparse_stat(file_stat):
    return bool(
        getattr(file_stat, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _lstat_regular(path, kind, missing_ok=False):
    path = Path(path)
    try:
        file_stat = path.lstat()
    except FileNotFoundError:
        if missing_ok:
            return None
        raise EvidenceIntegrityError("%s is absent" % kind)
    except OSError:
        raise
    if stat.S_ISLNK(file_stat.st_mode) or _is_reparse_stat(file_stat):
        raise EvidenceIntegrityError("%s is a symlink or reparse point" % kind)
    expected = stat.S_ISDIR if kind.endswith("directory") else stat.S_ISREG
    if not expected(file_stat.st_mode):
        raise EvidenceIntegrityError("%s has an irregular type" % kind)
    return file_stat


def _sync_parent(path):
    flags = getattr(os, "O_DIRECTORY", 0) | os.O_RDONLY
    try:
        descriptor = os.open(str(path), flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        # Directory fsync is not portable on Windows.  The store promises
        # fail-closed process recovery, not sudden-power-loss persistence.
        pass
    finally:
        os.close(descriptor)


def _write_bytes(path, payload, exclusive=True):
    if not isinstance(payload, bytes):
        raise TypeError("evidence payload must be bytes")
    path = Path(path)
    mode = "xb" if exclusive else "wb"
    with path.open(mode) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    _sync_parent(path.parent)


def _write_json(path, value, exclusive=True):
    _write_bytes(
        path,
        canonical_json_bytes(value, newline=True),
        exclusive=exclusive,
    )


def _flush_existing(path):
    descriptor = os.open(str(path), os.O_RDWR | getattr(os, "O_BINARY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _portable_relative(relative, require_normalized=False):
    if not isinstance(relative, str) or not relative:
        raise ValueError("evidence path must be a nonempty string")
    if "\\" in relative:
        raise ValueError("evidence paths must use forward slashes")
    raw = PurePosixPath(relative)
    if raw.is_absolute() or ".." in raw.parts or "." in raw.parts:
        raise ValueError("evidence path cannot traverse")
    if raw.as_posix() != relative:
        raise ValueError("evidence path is not canonical")
    normalized_parts = []
    for component in raw.parts:
        normalized_component = _require_text(
            component, "evidence path component"
        )
        if (
            normalized_component.endswith((" ", "."))
            or any(
                character in _WINDOWS_FORBIDDEN
                for character in normalized_component
            )
            or normalized_component.split(".", 1)[0].casefold()
            in _WINDOWS_RESERVED
        ):
            raise ValueError(
                "evidence path is not portable across supported hosts"
            )
        normalized_parts.append(normalized_component)
    normalized = PurePosixPath(*normalized_parts)
    if require_normalized and normalized.as_posix() != relative:
        raise ValueError("evidence path is not NFC-normalized")
    parsed = normalized
    return parsed


def _candidate_member_allowed(relative):
    if relative in REQUIRED_EVIDENCE_FILES:
        return True
    return relative.startswith("artifacts/") and len(
        PurePosixPath(relative).parts
    ) >= 2


def _walk_tree(root):
    """Return non-following regular files/directories below ``root``."""

    root = Path(root)
    _lstat_regular(root, "candidate directory")
    files = {}
    directories = set()

    def visit(directory, prefix):
        try:
            entries = list(os.scandir(str(directory)))
        except OSError:
            raise
        for entry in entries:
            relative = (
                entry.name
                if not prefix
                else prefix + "/" + entry.name
            )
            try:
                _portable_relative(relative, require_normalized=True)
            except ValueError as exc:
                raise EvidenceIntegrityError(str(exc)) from exc
            try:
                file_stat = entry.stat(follow_symlinks=False)
            except OSError:
                raise
            if (
                stat.S_ISLNK(file_stat.st_mode)
                or _is_reparse_stat(file_stat)
            ):
                raise EvidenceIntegrityError(
                    "candidate member %r is a symlink or reparse point"
                    % relative
                )
            if stat.S_ISDIR(file_stat.st_mode):
                directories.add(relative)
                visit(Path(entry.path), relative)
            elif stat.S_ISREG(file_stat.st_mode):
                files[relative] = Path(entry.path)
            else:
                raise EvidenceIntegrityError(
                    "candidate member %r is irregular" % relative
                )

    visit(root, "")
    folded = {}
    for relative in list(files) + list(directories):
        key = relative.casefold()
        if key in folded and folded[key] != relative:
            raise EvidenceIntegrityError(
                "candidate has cross-platform case-colliding members"
            )
        folded[key] = relative
    return files, directories


def _validate_state_document(value, key, label):
    _require_exact_keys(
        value, {"schema_version", "state_kind", "payload"}, label
    )
    if value["schema_version"] != STATE_SCHEMA:
        raise SchemaError("%s uses an unsupported schema" % label)
    expected_kind = "initial" if label.startswith("initial") else "final"
    if value["state_kind"] != expected_kind:
        raise SchemaError("%s state_kind is inconsistent" % label)
    _normalize_json(value["payload"], label + ".payload")


def _validate_failure(value, execution_status, failure_origin):
    allowed_by_status = {
        "done": {"none"},
        "budget_exhausted": {"model"},
        "model_error": {"model"},
        "runner_error": {"runner"},
        "timeout": {"model", "runner"},
        "aborted": {"operator", "runner"},
        "environment_unstable": {"environment"},
    }
    if failure_origin not in allowed_by_status[execution_status]:
        raise SchemaError(
            "failure_origin is incompatible with execution_status"
        )
    if failure_origin == "none":
        if value is not None:
            raise SchemaError("failure must be null when origin is none")
    else:
        if not isinstance(value, dict):
            raise SchemaError(
                "non-none failure origin requires a failure object"
            )
        _normalize_json(value, "result.failure")


def _validate_result_document(value):
    _require_exact_keys(
        value,
        {
            "schema_version",
            "execution_status",
            "tool_status",
            "failure_origin",
            "failure",
            "metrics",
            "diagnostics",
        },
        "result.json",
    )
    if value["schema_version"] != RESULT_SCHEMA:
        raise SchemaError("result.json uses an unsupported schema")
    if value["execution_status"] not in _EXECUTION_STATUSES:
        raise SchemaError("execution_status is unsupported")
    if value["tool_status"] not in _TOOL_STATUSES:
        raise SchemaError("tool_status is unsupported")
    if value["failure_origin"] not in _FAILURE_ORIGINS | {"none"}:
        raise SchemaError("failure_origin is unsupported")
    if not isinstance(value["metrics"], dict):
        raise SchemaError("result metrics must be an object")
    _normalize_json(value["metrics"], "result.metrics")
    _normalize_json(value["diagnostics"], "result.diagnostics")
    _validate_failure(
        value["failure"],
        value["execution_status"],
        value["failure_origin"],
    )


def _validate_grade_document(value):
    _require_exact_keys(
        value,
        {
            "schema_version",
            "grader_status",
            "candidate_decision",
            "diagnostics",
        },
        "grade.json",
    )
    if value["schema_version"] != GRADE_SCHEMA:
        raise SchemaError("grade.json uses an unsupported schema")
    status_value = value["grader_status"]
    if status_value not in _GRADER_STATUSES:
        raise SchemaError("grader_status is unsupported")
    decision = value["candidate_decision"]
    if status_value == "graded":
        if type(decision) is not bool:
            raise SchemaError("graded evidence requires a boolean decision")
    elif decision is not None:
        raise SchemaError(
            "ungraded evidence requires decision=null"
        )
    _normalize_json(value["diagnostics"], "grade.diagnostics")


def _validate_actions_document(value):
    _require_exact_keys(value, {"schema_version", "actions"}, "actions.json")
    if value["schema_version"] != ACTIONS_SCHEMA:
        raise SchemaError("actions.json uses an unsupported schema")
    if not isinstance(value["actions"], list):
        raise SchemaError("actions must be an ordered list")
    _normalize_json(value["actions"], "actions")


def _validate_memory_jsonl_bytes(payload):
    if not payload:
        return
    if b"\r" in payload:
        raise SchemaError(
            "memory-delta.jsonl must use LF record terminators"
        )
    if not payload.endswith(b"\n"):
        raise SchemaError(
            "memory-delta.jsonl must end every record with LF"
        )
    for number, line in enumerate(payload[:-1].split(b"\n"), 1):
        if not line.strip():
            raise SchemaError(
                "memory-delta.jsonl contains a blank record at line %d"
                % number
            )
        value = _decode_json_bytes(
            line,
            "memory-delta.jsonl line %d" % number,
        )
        _normalize_json(value, "memory delta record")
        if canonical_json_bytes(value) != line:
            raise SchemaError(
                "memory-delta.jsonl line %d is not canonical JSON" % number
            )


def _validate_memory_jsonl(path):
    _validate_memory_jsonl_bytes(Path(path).read_bytes())


def _validate_transcript_bytes(payload):
    try:
        payload.decode("utf-8")
    except UnicodeError as exc:
        raise SchemaError("transcript.md is not valid UTF-8") from exc


def _validate_transcript(path):
    _validate_transcript_bytes(Path(path).read_bytes())


def _validate_candidate_payloads(
    candidate,
    payloads,
    expected_key=None,
):
    candidate = Path(candidate)
    logical = _logical_hash(candidate.parent.name)
    physical = _physical_uuid(candidate.name)
    attempt = _decode_canonical_json_bytes(
        payloads["attempt.json"], "attempt.json"
    )
    _require_exact_keys(
        attempt,
        {
            "schema_version",
            "run_id",
            "run_sha256",
            "logical_hash",
            "physical_uuid",
            "attempt_key",
        },
        "attempt.json",
    )
    if attempt["schema_version"] != ATTEMPT_SCHEMA:
        raise SchemaError("attempt.json uses an unsupported schema")
    key = AttemptKey.from_dict(attempt["attempt_key"])
    if attempt["logical_hash"] != logical or key.logical_hash != logical:
        raise LogicalCollisionError(
            "AttemptKey digest does not match its logical directory"
        )
    if attempt["physical_uuid"] != physical:
        raise EvidenceIntegrityError(
            "attempt physical id does not match its directory"
        )
    _safe_component(attempt["run_id"], "attempt run id")
    _require_digest(attempt["run_sha256"], "attempt run_sha256")
    if expected_key is not None and key != expected_key:
        raise LogicalCollisionError(
            "different complete AttemptKeys occupy one logical digest"
        )
    initial = _decode_canonical_json_bytes(
        payloads["initial-state.json"], "initial-state.json"
    )
    final = _decode_canonical_json_bytes(
        payloads["final-state.json"], "final-state.json"
    )
    result = _decode_canonical_json_bytes(
        payloads["result.json"], "result.json"
    )
    grade = _decode_canonical_json_bytes(
        payloads["grade.json"], "grade.json"
    )
    actions = _decode_canonical_json_bytes(
        payloads["actions.json"], "actions.json"
    )
    _validate_state_document(initial, key, "initial-state.json")
    _validate_state_document(final, key, "final-state.json")
    _validate_result_document(result)
    _validate_grade_document(grade)
    _validate_actions_document(actions)
    if (
        result["failure_origin"] == "model"
        and grade["grader_status"] == "graded"
        and grade["candidate_decision"] is not False
    ):
        raise SchemaError(
            "a graded model-origin failure requires candidate_decision=false"
        )
    _validate_memory_jsonl_bytes(payloads["memory-delta.jsonl"])
    _validate_transcript_bytes(payloads["transcript.md"])
    return {
        "attempt": attempt,
        "key": key,
        "result": result,
        "grade": grade,
    }


def _validate_candidate_semantics(candidate, expected_key=None):
    candidate = Path(candidate)
    payloads = {
        name: (candidate / name).read_bytes()
        for name in REQUIRED_EVIDENCE_FILES
    }
    return _validate_candidate_payloads(
        candidate, payloads, expected_key=expected_key
    )


def _manifest_paths(files):
    return [entry.get("path") for entry in files if isinstance(entry, dict)]


def _validate_prepared_impl(candidate, expected_key=None, expected_run=None):
    candidate = Path(candidate)
    _lstat_regular(candidate, "candidate directory")
    logical = _logical_hash(candidate.parent.name)
    physical = _physical_uuid(candidate.name)
    files, directories = _walk_tree(candidate)
    if PREPARED not in files:
        raise EvidenceIntegrityError("PREPARED.json is absent")
    if COMMITTED in files:
        files_without_control = {
            name: path
            for name, path in files.items()
            if name not in {PREPARED, COMMITTED}
        }
    else:
        files_without_control = {
            name: path for name, path in files.items() if name != PREPARED
        }
    if "artifacts" not in directories:
        raise EvidenceIntegrityError("artifacts directory is absent")
    unexpected_directories = {
        name
        for name in directories
        if name != "artifacts" and not name.startswith("artifacts/")
    }
    if unexpected_directories:
        raise EvidenceIntegrityError(
            "candidate contains unexpected directories"
        )
    if not REQUIRED_EVIDENCE_FILES <= set(files_without_control):
        raise EvidenceIntegrityError(
            "candidate is missing required evidence files"
        )
    if any(
        not _candidate_member_allowed(name)
        for name in files_without_control
    ):
        raise EvidenceIntegrityError(
            "candidate contains unexpected evidence files"
        )
    manifest = _load_json(files[PREPARED])
    _require_exact_keys(
        manifest,
        {
            "schema_version",
            "run_id",
            "run_sha256",
            "logical_hash",
            "physical_uuid",
            "files",
        },
        PREPARED,
    )
    if manifest["schema_version"] != PREPARED_SCHEMA:
        raise SchemaError("PREPARED.json uses an unsupported schema")
    if manifest["logical_hash"] != logical:
        raise LogicalCollisionError(
            "prepared logical hash does not match its directory"
        )
    if manifest["physical_uuid"] != physical:
        raise EvidenceIntegrityError(
            "prepared physical id does not match its directory"
        )
    _safe_component(manifest["run_id"], "prepared run id")
    _require_digest(manifest["run_sha256"], "prepared run_sha256")
    if expected_run is not None:
        if (
            manifest["run_id"] != expected_run["run_id"]
            or manifest["run_sha256"] != expected_run["run_sha256"]
        ):
            raise EvidenceIntegrityError(
                "candidate belongs to a different immutable run"
            )
    entries = manifest["files"]
    if not isinstance(entries, list):
        raise SchemaError("prepared files must be a list")
    names = _manifest_paths(entries)
    if (
        len(names) != len(entries)
        or names != sorted(names)
        or len(set(names)) != len(names)
    ):
        raise SchemaError(
            "prepared file entries must be unique and canonically sorted"
        )
    if names != sorted(files_without_control):
        raise EvidenceIntegrityError(
            "prepared manifest does not match the complete member set"
        )
    for entry in entries:
        _require_exact_keys(
            entry, {"path", "size", "sha256"}, "prepared file entry"
        )
        try:
            relative = _portable_relative(
                entry["path"], require_normalized=True
            ).as_posix()
        except ValueError as exc:
            raise SchemaError(str(exc)) from exc
        if relative in {PREPARED, COMMITTED}:
            raise SchemaError("control files cannot be manifested")
        size = entry["size"]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise SchemaError("prepared file size is invalid")
        digest = entry["sha256"]
        try:
            _require_digest(digest, "prepared file sha256")
        except ValueError as exc:
            raise SchemaError(str(exc)) from exc
        path = files_without_control[relative]
        if path.stat().st_size != size:
            raise EvidenceIntegrityError(
                "size mismatch for %s" % relative
            )
        if _sha256_file(path) != digest:
            raise EvidenceIntegrityError(
                "hash mismatch for %s" % relative
            )
    semantic = _validate_candidate_semantics(candidate, expected_key)
    if (
        semantic["attempt"]["run_id"] != manifest["run_id"]
        or semantic["attempt"]["run_sha256"] != manifest["run_sha256"]
    ):
        raise EvidenceIntegrityError(
            "attempt and prepared run identities differ"
        )
    # Re-read the manifest bytes after hashing members.  A cooperative writer
    # should be excluded by run.lock; this check still detects accidental
    # replacement during validation.
    first_manifest_bytes = files[PREPARED].read_bytes()
    if _decode_json_bytes(first_manifest_bytes, PREPARED) != manifest:
        raise EvidenceIntegrityError("prepared manifest changed during read")
    return {
        "manifest": manifest,
        "semantic": semantic,
        "prepared_sha256": _sha256_bytes(first_manifest_bytes),
    }


def validate_prepared(candidate, expected_key=None, expected_run=None):
    """Validate and return a complete prepared candidate description.

    Values read from disk never leak constructor-oriented ``ValueError`` or
    ``TypeError`` exceptions.  Recovery needs one stable integrity-error
    boundary so invalid uncommitted evidence can be classified as abandoned
    while the same defect under a commit marker halts the run.
    """

    try:
        return _validate_prepared_impl(
            candidate,
            expected_key=expected_key,
            expected_run=expected_run,
        )
    except EvidenceIntegrityError:
        raise
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise SchemaError(
            "prepared evidence contains an invalid value: %s" % exc
        ) from exc


def validate_committed(candidate, expected_key=None, expected_run=None):
    prepared = validate_prepared(
        candidate, expected_key=expected_key, expected_run=expected_run
    )
    marker = Path(candidate) / COMMITTED
    marker_stat = _lstat_regular(marker, "commit marker")
    if marker_stat.st_size != 0:
        raise EvidenceIntegrityError("commit marker must be empty")
    return prepared


def _is_retryable_publication_error(exc):
    if os.name != "nt":
        return False
    winerror = getattr(exc, "winerror", None)
    if winerror is not None:
        return winerror in _RETRYABLE_WINERRORS
    return getattr(exc, "errno", None) in {errno.EACCES, errno.EBUSY}


def _deadline(seconds, clock):
    if isinstance(seconds, bool):
        raise ValueError("deadline_seconds must be finite and nonnegative")
    try:
        duration = float(seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "deadline_seconds must be finite and nonnegative"
        ) from exc
    if not math.isfinite(duration) or duration < 0:
        raise ValueError("deadline_seconds must be finite and nonnegative")
    return clock() + duration


def _wait_retry(attempt, deadline_at, clock, sleeper):
    remaining = deadline_at - clock()
    if remaining <= 0:
        return False
    delay = (
        _RETRY_DELAYS[attempt]
        if attempt < len(_RETRY_DELAYS)
        else 2.0
    )
    sleeper(min(delay, remaining))
    return True


def _retry_idempotent(operation, deadline_at, clock, sleeper):
    attempt = 0
    while True:
        try:
            return True, operation()
        except OSError as exc:
            if not _is_retryable_publication_error(exc):
                raise
            if not _wait_retry(
                attempt, deadline_at, clock, sleeper
            ):
                return False, None
            attempt += 1


def _create_commit_marker(candidate):
    marker = Path(candidate) / COMMITTED
    flags = (
        os.O_CREAT
        | os.O_EXCL
        | os.O_WRONLY
        | getattr(os, "O_BINARY", 0)
    )
    descriptor = os.open(str(marker), flags, 0o600)
    try:
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise EvidenceIntegrityError(
                "new commit marker is not a regular file"
            )
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _sync_parent(Path(candidate))


def _publish_prepared(
    candidate,
    expected_key,
    expected_run,
    *,
    deadline_at,
    clock,
    sleeper
):
    candidate = Path(candidate)

    def publish_once():
        validate_prepared(
            candidate,
            expected_key=expected_key,
            expected_run=expected_run,
        )
        try:
            _create_commit_marker(candidate)
        except FileExistsError:
            # Existing-file errors are state inspection, never blind success.
            validate_committed(
                candidate,
                expected_key=expected_key,
                expected_run=expected_run,
            )
        return validate_committed(
            candidate,
            expected_key=expected_key,
            expected_run=expected_run,
        )

    completed, value = _retry_idempotent(
        publish_once, deadline_at, clock, sleeper
    )
    return ("committed", value) if completed else ("publish_blocked", None)


def _record_from_validated(validated):
    manifest = validated["manifest"]
    semantic = validated["semantic"]
    result = semantic["result"]
    grade = semantic["grade"]
    strict_success = (
        grade["candidate_decision"]
        if (
            grade["grader_status"] == "graded"
            and result["failure_origin"] in {"none", "model"}
        )
        else None
    )
    return {
        "logical_hash": manifest["logical_hash"],
        "physical_uuid": manifest["physical_uuid"],
        "attempt_key": semantic["key"].to_dict(),
        "record_status": "committed",
        "execution_status": result["execution_status"],
        "grader_status": grade["grader_status"],
        "tool_status": result["tool_status"],
        "publish_status": "committed",
        "strict_success": strict_success,
        "failure_origin": result["failure_origin"],
        "result": copy.deepcopy(result),
        "grade": copy.deepcopy(grade),
    }


@dataclass(frozen=True)
class AttemptResolution:
    state: str
    record: object = None
    candidate_path: object = None
    producer_called: bool = False

    def __post_init__(self):
        if self.state not in {
            "not_started",
            "abandoned",
            "prepared",
            "committed",
            "publish_blocked",
        }:
            raise ValueError("unsupported attempt resolution state")
        if self.record is not None:
            object.__setattr__(self, "record", copy.deepcopy(self.record))
        if self.candidate_path is not None:
            object.__setattr__(
                self, "candidate_path", Path(self.candidate_path)
            )


class RunLock:
    """Persistent native file lock; the path is never deleted or replaced."""

    def __init__(self, path):
        self.path = Path(path)
        self._descriptor = None
        self._owner_pid = None
        self._overlapped = None
        self._registry_key = os.path.normcase(
            os.path.abspath(str(self.path))
        )

    @property
    def held(self):
        return (
            self._descriptor is not None
            and self._owner_pid == os.getpid()
        )

    def acquire(self):
        if self._descriptor is not None:
            raise RunLockedError("run lock is not reentrant")
        with _LOCK_REGISTRY_GUARD:
            if self._registry_key in _LOCK_REGISTRY:
                raise RunLockedError("run is already locked in this process")
            descriptor = os.open(
                str(self.path),
                os.O_RDWR
                | os.O_CREAT
                | getattr(os, "O_BINARY", 0)
                | getattr(os, "O_NOINHERIT", 0),
                0o600,
            )
            try:
                os.set_inheritable(descriptor, False)
                opened_stat = os.fstat(descriptor)
                if not stat.S_ISREG(opened_stat.st_mode):
                    raise EvidenceIntegrityError(
                        "run.lock is not a regular file"
                    )
                path_stat = self.path.lstat()
                if (
                    stat.S_ISLNK(path_stat.st_mode)
                    or _is_reparse_stat(path_stat)
                    or not stat.S_ISREG(path_stat.st_mode)
                ):
                    raise EvidenceIntegrityError(
                        "run.lock is a symlink, reparse point, or irregular"
                    )
                self._native_lock(descriptor)
            except BaseException:
                os.close(descriptor)
                raise
            _LOCK_REGISTRY.add(self._registry_key)
            self._descriptor = descriptor
            self._owner_pid = os.getpid()
        return self

    def _native_lock(self, descriptor):
        if os.name == "nt":
            import msvcrt

            class Overlapped(ctypes.Structure):
                _fields_ = [
                    ("Internal", ctypes.c_void_p),
                    ("InternalHigh", ctypes.c_void_p),
                    ("Offset", ctypes.c_uint32),
                    ("OffsetHigh", ctypes.c_uint32),
                    ("hEvent", ctypes.c_void_p),
                ]

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            lock_file = kernel32.LockFileEx
            lock_file.argtypes = (
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.c_uint32,
                ctypes.c_uint32,
                ctypes.c_uint32,
                ctypes.POINTER(Overlapped),
            )
            lock_file.restype = ctypes.c_int
            overlapped = Overlapped()
            handle = msvcrt.get_osfhandle(descriptor)
            if not lock_file(
                ctypes.c_void_p(handle),
                0x2 | 0x1,
                0,
                0xFFFFFFFF,
                0xFFFFFFFF,
                ctypes.byref(overlapped),
            ):
                error = ctypes.get_last_error()
                if error == 33:
                    raise RunLockedError("another process owns run.lock")
                raise ctypes.WinError(error)
            self._overlapped = overlapped
        else:
            import fcntl

            try:
                fcntl.flock(
                    descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB
                )
            except OSError as exc:
                if exc.errno in {errno.EACCES, errno.EAGAIN}:
                    raise RunLockedError(
                        "another process owns run.lock"
                    ) from exc
                raise

    def release(self):
        descriptor = self._descriptor
        if descriptor is None:
            return
        if self._owner_pid != os.getpid():
            raise RunLockedError(
                "run lock cannot be released by a different process"
            )
        try:
            if os.name == "nt":
                import msvcrt

                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                unlock_file = kernel32.UnlockFileEx
                unlock_file.argtypes = (
                    ctypes.c_void_p,
                    ctypes.c_uint32,
                    ctypes.c_uint32,
                    ctypes.c_uint32,
                    ctypes.POINTER(type(self._overlapped)),
                )
                unlock_file.restype = ctypes.c_int
                handle = msvcrt.get_osfhandle(descriptor)
                if not unlock_file(
                    ctypes.c_void_p(handle),
                    0,
                    0xFFFFFFFF,
                    0xFFFFFFFF,
                    ctypes.byref(self._overlapped),
                ):
                    raise ctypes.WinError(ctypes.get_last_error())
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
            with _LOCK_REGISTRY_GUARD:
                _LOCK_REGISTRY.discard(self._registry_key)
            self._descriptor = None
            self._owner_pid = None
            self._overlapped = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()
        return False


class CandidateWriter:
    """One physical attempt owned by a live locked RunSession."""

    def __init__(self, session, key, path, attempt_payload):
        self._session = session
        self.key = key
        self.path = Path(path)
        self.artifacts_dir = self.path / "artifacts"
        self._entries = {
            "attempt.json": {
                "path": "attempt.json",
                "size": len(attempt_payload),
                "sha256": _sha256_bytes(attempt_payload),
            }
        }
        self._semantic_payloads = {"attempt.json": attempt_payload}

    def _active(self):
        self._session._require_active()
        if (
            _optional_lstat(self.path / PREPARED) is not None
            or _optional_lstat(self.path / COMMITTED) is not None
        ):
            raise CandidateStateError(
                "prepared or committed candidates are immutable"
            )

    def write_bytes(self, relative, payload):
        self._active()
        parsed = _portable_relative(relative)
        normalized = parsed.as_posix()
        if normalized in {"attempt.json", PREPARED, COMMITTED}:
            raise CandidateStateError(
                "candidate identity and publication files are store-owned"
            )
        if not _candidate_member_allowed(normalized):
            raise ValueError("unsupported candidate evidence path")
        existing_files, existing_directories = _walk_tree(self.path)
        folded = normalized.casefold()
        for existing in list(existing_files) + list(existing_directories):
            if existing.casefold() == folded:
                raise ValueError(
                    "candidate evidence path already exists or case-collides"
                )
        path = self.path.joinpath(*parsed.parts)
        parent = path.parent
        if normalized.startswith("artifacts/"):
            parent.mkdir(parents=True, exist_ok=True)
            current = parent
            while current != self.path:
                _lstat_regular(current, "artifact directory")
                current = current.parent
        elif parent != self.path:
            raise ValueError("root evidence cannot use subdirectories")
        _write_bytes(path, payload, exclusive=True)
        self._entries[normalized] = {
            "path": normalized,
            "size": len(payload),
            "sha256": _sha256_bytes(payload),
        }
        if normalized in REQUIRED_EVIDENCE_FILES:
            self._semantic_payloads[normalized] = payload
        return path

    def write_json(self, relative, value):
        payload = canonical_json_bytes(value, newline=True)
        return self.write_bytes(relative, payload)

    def capture_artifact(self, relative):
        """Flush/hash a caller-generated artifact after its writer closes."""

        self._active()
        parsed = _portable_relative(relative)
        normalized = parsed.as_posix()
        if not normalized.startswith("artifacts/"):
            raise ValueError("capture_artifact accepts only artifact paths")
        path = self.path.joinpath(*parsed.parts)
        _lstat_regular(path, "artifact file")
        _flush_existing(path)
        self._entries[normalized] = {
            "path": normalized,
            "size": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        return path

    def commit(
        self,
        deadline_seconds=30.0,
        clock=time.monotonic,
        sleeper=time.sleep,
    ):
        self._session._require_active()
        deadline_at = _deadline(deadline_seconds, clock)
        completed, marker_stat = _retry_idempotent(
            lambda: _optional_lstat(self.path / COMMITTED),
            deadline_at,
            clock,
            sleeper,
        )
        if not completed:
            return AttemptResolution(
                "publish_blocked", candidate_path=self.path
            )
        if marker_stat is not None:
            completed, validated = _retry_idempotent(
                lambda: validate_committed(
                    self.path,
                    expected_key=self.key,
                    expected_run=self._session.run_identity,
                ),
                deadline_at,
                clock,
                sleeper,
            )
            if not completed:
                return AttemptResolution(
                    "publish_blocked", candidate_path=self.path
                )
            return AttemptResolution(
                "committed",
                record=_record_from_validated(validated),
                candidate_path=self.path,
            )
        completed, prepared_stat = _retry_idempotent(
            lambda: _optional_lstat(self.path / PREPARED),
            deadline_at,
            clock,
            sleeper,
        )
        if not completed:
            return AttemptResolution(
                "publish_blocked", candidate_path=self.path
            )
        if prepared_stat is None:
            self._prepare_manifest()

            def validate_new():
                return validate_prepared(
                    self.path,
                    expected_key=self.key,
                    expected_run=self._session.run_identity,
                )

            completed, _ = _retry_idempotent(
                validate_new, deadline_at, clock, sleeper
            )
            if not completed:
                return AttemptResolution(
                    "publish_blocked", candidate_path=self.path
                )
        state, validated = _publish_prepared(
            self.path,
            self.key,
            self._session.run_identity,
            deadline_at=deadline_at,
            clock=clock,
            sleeper=sleeper,
        )
        if state == "publish_blocked":
            return AttemptResolution(state, candidate_path=self.path)
        return AttemptResolution(
            "committed",
            record=_record_from_validated(validated),
            candidate_path=self.path,
        )

    def _prepare_manifest(self):
        self._active()
        files, directories = _walk_tree(self.path)
        if "artifacts" not in directories:
            raise EvidenceIntegrityError("artifacts directory is absent")
        if not REQUIRED_EVIDENCE_FILES <= set(files):
            missing = sorted(REQUIRED_EVIDENCE_FILES - set(files))
            raise EvidenceIntegrityError(
                "candidate is missing required evidence: "
                + ", ".join(missing)
            )
        if any(not _candidate_member_allowed(name) for name in files):
            raise EvidenceIntegrityError(
                "candidate contains unexpected evidence files"
            )
        unexpected_directories = {
            name
            for name in directories
            if name != "artifacts" and not name.startswith("artifacts/")
        }
        if unexpected_directories:
            raise EvidenceIntegrityError(
                "candidate contains unexpected directories"
            )
        if set(files) != set(self._entries):
            untracked = sorted(set(files) - set(self._entries))
            missing = sorted(set(self._entries) - set(files))
            details = []
            if untracked:
                details.append("uncaptured " + ", ".join(untracked))
            if missing:
                details.append("missing " + ", ".join(missing))
            raise EvidenceIntegrityError(
                "candidate file inventory differs from writer ledger: "
                + "; ".join(details)
            )
        try:
            semantic = _validate_candidate_payloads(
                self.path,
                self._semantic_payloads,
                expected_key=self.key,
            )
        except EvidenceIntegrityError:
            raise
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise SchemaError(
                "candidate evidence contains an invalid value: %s" % exc
            ) from exc
        if (
            semantic["attempt"]["run_id"]
            != self._session.run_identity["run_id"]
            or semantic["attempt"]["run_sha256"]
            != self._session.run_identity["run_sha256"]
        ):
            raise EvidenceIntegrityError(
                "candidate belongs to a different immutable run"
            )
        entries = [
            copy.deepcopy(self._entries[relative])
            for relative in sorted(self._entries)
        ]
        manifest = {
            "schema_version": PREPARED_SCHEMA,
            "run_id": self._session.run_identity["run_id"],
            "run_sha256": self._session.run_identity["run_sha256"],
            "logical_hash": self.key.logical_hash,
            "physical_uuid": self.path.name,
            "files": entries,
        }
        _write_json(self.path / PREPARED, manifest, exclusive=True)
        return manifest


class RunSession:
    """One exclusive recovery/execution/publication transaction."""

    def __init__(self, store):
        self.store = store
        self.lock = RunLock(store.run_dir / "run.lock")
        self.run_identity = {
            "run_id": store.run_id,
            "run_sha256": store.run_sha256,
        }
        self._active = False

    def __enter__(self):
        self.lock.acquire()
        self._active = True
        try:
            self.store._validate_layout()
        except BaseException:
            self._active = False
            self.lock.release()
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._active = False
        self.lock.release()
        return False

    def _require_active(self):
        if not self._active or not self.lock.held:
            raise RunLockedError(
                "operation requires the live exclusive run lock"
            )

    def _logical_directory(self, key):
        return self.store.attempts_dir / key.logical_hash

    def _candidate_key_if_present(self, candidate):
        attempt_path = Path(candidate) / "attempt.json"
        if _optional_lstat(attempt_path) is None:
            return None
        try:
            _lstat_regular(attempt_path, "attempt.json")
            value = _load_json(attempt_path)
            if not isinstance(value, dict) or "attempt_key" not in value:
                return None
            return AttemptKey.from_dict(value["attempt_key"])
        except (EvidenceIntegrityError, ValueError):
            return None

    def _scan(
        self,
        logical,
        expected_key=None,
        adopt=False,
        deadline_seconds=30.0,
        deadline_at=None,
    ):
        self._require_active()
        logical = _logical_hash(logical)
        if deadline_at is None:
            deadline_at = _deadline(deadline_seconds, time.monotonic)
        logical_dir = self.store.attempts_dir / logical
        completed, logical_stat = _retry_idempotent(
            lambda: _optional_lstat(logical_dir),
            deadline_at,
            time.monotonic,
            time.sleep,
        )
        if not completed:
            return AttemptResolution(
                "publish_blocked", candidate_path=logical_dir
            )
        if logical_stat is None:
            return AttemptResolution("not_started")
        if (
            stat.S_ISLNK(logical_stat.st_mode)
            or _is_reparse_stat(logical_stat)
            or not stat.S_ISDIR(logical_stat.st_mode)
        ):
            raise EvidenceIntegrityError(
                "logical directory has an irregular type"
            )
        valid = []
        abandoned = []
        completed, entries = _retry_idempotent(
            lambda: list(os.scandir(str(logical_dir))),
            deadline_at,
            time.monotonic,
            time.sleep,
        )
        if not completed:
            return AttemptResolution(
                "publish_blocked", candidate_path=logical_dir
            )
        for entry in entries:
            candidate = Path(entry.path)
            completed, file_stat = _retry_idempotent(
                lambda entry=entry: entry.stat(follow_symlinks=False),
                deadline_at,
                time.monotonic,
                time.sleep,
            )
            if not completed:
                return AttemptResolution(
                    "publish_blocked", candidate_path=candidate
                )
            if (
                stat.S_ISLNK(file_stat.st_mode)
                or _is_reparse_stat(file_stat)
                or not stat.S_ISDIR(file_stat.st_mode)
            ):
                raise EvidenceIntegrityError(
                    "logical directory contains an irregular candidate"
                )
            _physical_uuid(entry.name)
            completed, parsed_key = _retry_idempotent(
                lambda candidate=candidate: self._candidate_key_if_present(
                    candidate
                ),
                deadline_at,
                time.monotonic,
                time.sleep,
            )
            if not completed:
                return AttemptResolution(
                    "publish_blocked", candidate_path=candidate
                )
            if parsed_key is not None and parsed_key.logical_hash != logical:
                raise LogicalCollisionError(
                    "candidate AttemptKey collides with logical directory"
                )
            if (
                expected_key is not None
                and parsed_key is not None
                and parsed_key != expected_key
            ):
                raise LogicalCollisionError(
                    "different complete AttemptKeys occupy one logical digest"
                )
            completed, marker_stat = _retry_idempotent(
                lambda candidate=candidate: _optional_lstat(
                    candidate / COMMITTED
                ),
                deadline_at,
                time.monotonic,
                time.sleep,
            )
            if not completed:
                return AttemptResolution(
                    "publish_blocked", candidate_path=candidate
                )
            completed, prepared_stat = _retry_idempotent(
                lambda candidate=candidate: _optional_lstat(
                    candidate / PREPARED
                ),
                deadline_at,
                time.monotonic,
                time.sleep,
            )
            if not completed:
                return AttemptResolution(
                    "publish_blocked", candidate_path=candidate
                )
            marker_present = marker_stat is not None
            prepared_present = prepared_stat is not None
            if marker_present:
                try:
                    completed, validated = _retry_idempotent(
                        lambda: validate_committed(
                            candidate,
                            expected_key=expected_key,
                            expected_run=self.run_identity,
                        ),
                        deadline_at,
                        time.monotonic,
                        time.sleep,
                    )
                except EvidenceIntegrityError as exc:
                    raise EvidenceIntegrityError(
                        "invalid committed evidence at %s: %s"
                        % (candidate, exc)
                    ) from exc
                if not completed:
                    return AttemptResolution(
                        "publish_blocked", candidate_path=candidate
                    )
                valid.append(("committed", candidate, validated))
            elif prepared_present:
                try:
                    completed, validated = _retry_idempotent(
                        lambda: validate_prepared(
                            candidate,
                            expected_key=expected_key,
                            expected_run=self.run_identity,
                        ),
                        deadline_at,
                        time.monotonic,
                        time.sleep,
                    )
                except EvidenceIntegrityError:
                    abandoned.append(candidate)
                else:
                    if not completed:
                        return AttemptResolution(
                            "publish_blocked", candidate_path=candidate
                        )
                    valid.append(("prepared", candidate, validated))
            else:
                abandoned.append(candidate)
        if len(valid) > 1:
            raise DuplicateCandidateError(
                "multiple valid candidates exist for logical attempt %s"
                % logical
            )
        if not valid:
            return AttemptResolution(
                "abandoned" if abandoned else "not_started",
                candidate_path=abandoned[0] if len(abandoned) == 1 else None,
            )
        state, candidate, validated = valid[0]
        if state == "committed":
            return AttemptResolution(
                "committed",
                record=_record_from_validated(validated),
                candidate_path=candidate,
            )
        if not adopt:
            return AttemptResolution(
                "prepared", candidate_path=candidate
            )
        key = validated["semantic"]["key"]
        state, committed = _publish_prepared(
            candidate,
            key,
            self.run_identity,
            deadline_at=deadline_at,
            clock=time.monotonic,
            sleeper=time.sleep,
        )
        if state == "publish_blocked":
            return AttemptResolution(state, candidate_path=candidate)
        return AttemptResolution(
            "committed",
            record=_record_from_validated(committed),
            candidate_path=candidate,
        )

    def resolve(self, key, deadline_seconds=30.0):
        if not isinstance(key, AttemptKey):
            raise TypeError("key must be an AttemptKey")
        return self._scan(
            key.logical_hash,
            expected_key=key,
            adopt=True,
            deadline_seconds=deadline_seconds,
        )

    def inspect(self, key):
        """Classify one logical attempt without adopting prepared evidence."""

        if not isinstance(key, AttemptKey):
            raise TypeError("key must be an AttemptKey")
        return self._scan(
            key.logical_hash,
            expected_key=key,
            adopt=False,
        )

    def begin_attempt(self, key):
        self._require_active()
        if not isinstance(key, AttemptKey):
            raise TypeError("key must be an AttemptKey")
        existing = self._scan(
            key.logical_hash, expected_key=key, adopt=False
        )
        if existing.state not in {"not_started", "abandoned"}:
            raise CandidateStateError(
                "a valid prepared or committed candidate already exists"
            )
        logical_dir = self._logical_directory(key)
        if not _lexists(logical_dir):
            logical_dir.mkdir(parents=False, exist_ok=False)
            _sync_parent(logical_dir.parent)
        _lstat_regular(logical_dir, "logical directory")
        physical = str(uuid.uuid4())
        candidate = logical_dir / physical
        candidate.mkdir(exist_ok=False)
        _sync_parent(logical_dir)
        (candidate / "artifacts").mkdir(exist_ok=False)
        _sync_parent(candidate)
        attempt = {
            "schema_version": ATTEMPT_SCHEMA,
            "run_id": self.run_identity["run_id"],
            "run_sha256": self.run_identity["run_sha256"],
            "logical_hash": key.logical_hash,
            "physical_uuid": physical,
            "attempt_key": key.to_dict(),
        }
        attempt_payload = canonical_json_bytes(attempt, newline=True)
        _write_bytes(candidate / "attempt.json", attempt_payload)
        return CandidateWriter(
            self, key, candidate, attempt_payload=attempt_payload
        )

    def _all_logical_names(
        self,
        deadline_seconds=30.0,
        deadline_at=None,
    ):
        self._require_active()
        if deadline_at is None:
            deadline_at = _deadline(deadline_seconds, time.monotonic)
        names = []
        completed, entries = _retry_idempotent(
            lambda: list(os.scandir(str(self.store.attempts_dir))),
            deadline_at,
            time.monotonic,
            time.sleep,
        )
        if not completed:
            raise EvidenceError(
                "attempt inventory remained temporarily unreadable"
            )
        for entry in entries:
            completed, file_stat = _retry_idempotent(
                lambda entry=entry: entry.stat(follow_symlinks=False),
                deadline_at,
                time.monotonic,
                time.sleep,
            )
            if not completed:
                raise EvidenceError(
                    "attempt inventory remained temporarily unreadable"
                )
            if (
                stat.S_ISLNK(file_stat.st_mode)
                or _is_reparse_stat(file_stat)
                or not stat.S_ISDIR(file_stat.st_mode)
            ):
                raise EvidenceIntegrityError(
                    "attempts directory contains an irregular logical member"
                )
            names.append(_logical_hash(entry.name))
        return sorted(names)

    def recover_all(self, deadline_seconds=30.0):
        deadline_at = _deadline(deadline_seconds, time.monotonic)
        records = []
        for logical in self._all_logical_names(
            deadline_at=deadline_at
        ):
            resolution = self._scan(
                logical,
                adopt=True,
                deadline_at=deadline_at,
            )
            if resolution.state == "committed":
                records.append(resolution.record)
            elif resolution.state == "publish_blocked":
                raise EvidenceError(
                    "cannot rebuild projection while attempt evidence is "
                    "temporarily unreadable"
                )
        return records

    def rebuild_results(self, deadline_seconds=30.0):
        self._require_active()
        records = self.recover_all(deadline_seconds=deadline_seconds)
        records.sort(
            key=lambda value: (
                value["logical_hash"],
                value["physical_uuid"],
            )
        )
        projection = {
            "schema_version": PROJECTION_SCHEMA,
            "run_id": self.store.run_id,
            "run_sha256": self.store.run_sha256,
            "records": records,
        }
        payload = canonical_json_bytes(projection, newline=True)
        temp = self.store.run_dir / RESULTS_TEMP
        final = self.store.run_dir / RESULTS
        if _lexists(temp):
            _lstat_regular(temp, "projection temporary file")
        _write_bytes(temp, payload, exclusive=False)
        os.replace(str(temp), str(final))
        _sync_parent(self.store.run_dir)
        # Projection is not evidence, but immediately decode it so callers
        # never receive a partial or malformed generated view.
        if _load_json(final, RESULTS) != projection:
            raise EvidenceIntegrityError(
                "results projection failed post-write validation"
            )
        return final


class EvidenceStore:
    """One immutable run descriptor plus marker-last physical attempts."""

    def __init__(self, runs_root, run_id, run_document):
        self.runs_root = Path(runs_root)
        self.run_id = _safe_component(run_id, "run id")
        self.run_dir = self.runs_root / self.run_id
        self.attempts_dir = self.run_dir / "attempts"
        self.run_document = copy.deepcopy(run_document)
        self.run_bytes = canonical_json_bytes(run_document, newline=True)
        self.run_sha256 = _sha256_bytes(self.run_bytes)

    @classmethod
    def create_run(cls, runs_root, run_id, metadata):
        if not isinstance(metadata, dict):
            raise ValueError("run metadata must be an object")
        runs_root = Path(runs_root)
        if not _lexists(runs_root):
            runs_root.mkdir(parents=True, exist_ok=False)
        _lstat_regular(runs_root, "runs directory")
        run_id = _safe_component(run_id, "run id")
        run_dir = runs_root / run_id
        if not _lexists(run_dir):
            run_dir.mkdir(exist_ok=False)
            _sync_parent(runs_root)
        _lstat_regular(run_dir, "run directory")
        run_document = {
            "schema_version": RUN_SCHEMA,
            "run_id": run_id,
            "metadata": _normalize_json(metadata, "run metadata"),
        }
        store = cls(runs_root, run_id, run_document)
        lock = RunLock(run_dir / "run.lock")
        with lock:
            run_path = run_dir / "run.json"
            if _lexists(run_path):
                _lstat_regular(run_path, "run.json")
                existing = _load_json(run_path)
                if existing != run_document:
                    raise EvidenceIntegrityError(
                        "existing run.json does not match requested metadata"
                    )
            else:
                _write_bytes(run_path, store.run_bytes, exclusive=True)
            attempts = run_dir / "attempts"
            if not _lexists(attempts):
                attempts.mkdir(exist_ok=False)
                _sync_parent(run_dir)
            _lstat_regular(attempts, "attempts directory")
        store._validate_layout()
        return store

    @classmethod
    def open_run(cls, runs_root, run_id):
        runs_root = Path(runs_root)
        run_id = _safe_component(run_id, "run id")
        run_dir = runs_root / run_id
        _lstat_regular(runs_root, "runs directory")
        _lstat_regular(run_dir, "run directory")
        _lstat_regular(run_dir / "run.json", "run.json")
        run_document = _load_json(run_dir / "run.json")
        _require_exact_keys(
            run_document,
            {"schema_version", "run_id", "metadata"},
            "run.json",
        )
        if run_document["schema_version"] != RUN_SCHEMA:
            raise SchemaError("run.json uses an unsupported schema")
        if run_document["run_id"] != run_id:
            raise EvidenceIntegrityError(
                "run.json identity does not match its directory"
            )
        if not isinstance(run_document["metadata"], dict):
            raise SchemaError("run metadata must be an object")
        store = cls(runs_root, run_id, run_document)
        store._validate_layout()
        return store

    def _validate_layout(self):
        _lstat_regular(self.runs_root, "runs directory")
        _lstat_regular(self.run_dir, "run directory")
        _lstat_regular(self.run_dir / "run.json", "run.json")
        _lstat_regular(self.run_dir / "run.lock", "run.lock")
        _lstat_regular(self.attempts_dir, "attempts directory")
        actual_run = _load_json(self.run_dir / "run.json")
        if actual_run != self.run_document:
            raise EvidenceIntegrityError(
                "immutable run.json changed after open"
            )
        allowed = {
            "run.json",
            "run.lock",
            "attempts",
            RESULTS,
            RESULTS_TEMP,
        }
        for entry in os.scandir(str(self.run_dir)):
            if entry.name not in allowed:
                raise EvidenceIntegrityError(
                    "run directory contains unexpected member %r"
                    % entry.name
                )
            file_stat = entry.stat(follow_symlinks=False)
            if (
                stat.S_ISLNK(file_stat.st_mode)
                or _is_reparse_stat(file_stat)
            ):
                raise EvidenceIntegrityError(
                    "run member %r is a symlink or reparse point"
                    % entry.name
                )
        for optional in (RESULTS, RESULTS_TEMP):
            path = self.run_dir / optional
            if _lexists(path):
                _lstat_regular(path, "projection file")

    def locked(self):
        return RunSession(self)

    def execute_or_resume(
        self,
        key,
        producer,
        deadline_seconds=30.0,
    ):
        if not isinstance(key, AttemptKey):
            raise TypeError("key must be an AttemptKey")
        if not callable(producer):
            raise TypeError("producer must be callable")
        with self.locked() as session:
            recovered = session.resolve(
                key, deadline_seconds=deadline_seconds
            )
            if recovered.state == "publish_blocked":
                return AttemptResolution(
                    recovered.state,
                    record=recovered.record,
                    candidate_path=recovered.candidate_path,
                    producer_called=False,
                )
            if recovered.state == "committed":
                session.rebuild_results(
                    deadline_seconds=deadline_seconds
                )
                return AttemptResolution(
                    recovered.state,
                    record=recovered.record,
                    candidate_path=recovered.candidate_path,
                    producer_called=False,
                )
            writer = session.begin_attempt(key)
            producer(writer)
            published = writer.commit(
                deadline_seconds=deadline_seconds
            )
            if published.state == "publish_blocked":
                return AttemptResolution(
                    published.state,
                    record=published.record,
                    candidate_path=published.candidate_path,
                    producer_called=True,
                )
            session.rebuild_results(
                deadline_seconds=deadline_seconds
            )
            return AttemptResolution(
                published.state,
                record=published.record,
                candidate_path=published.candidate_path,
                producer_called=True,
            )

    def read_committed(self):
        """Validate/recover the run and return the committed-only projection."""

        with self.locked() as session:
            path = session.rebuild_results()
            projection = _load_json(path, RESULTS)
        return copy.deepcopy(projection)


__all__ = [
    "ACTIONS_SCHEMA",
    "ATTEMPT_KEY_SCHEMA",
    "ATTEMPT_SCHEMA",
    "AttemptKey",
    "AttemptResolution",
    "COMMITTED",
    "CandidateStateError",
    "DuplicateCandidateError",
    "EvidenceError",
    "EvidenceIntegrityError",
    "EvidenceStore",
    "GRADE_SCHEMA",
    "LogicalCollisionError",
    "PREPARED",
    "PREPARED_SCHEMA",
    "PROJECTION_SCHEMA",
    "RESULT_SCHEMA",
    "RunLockedError",
    "STATE_SCHEMA",
    "SchemaError",
    "canonical_json_bytes",
    "validate_committed",
    "validate_prepared",
]
