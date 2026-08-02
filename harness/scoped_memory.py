"""Scoped, untrusted memory (S1R).

The released store appended ``{"fact": "..."}`` to one shared JSONL file and
loaded it with ``json.loads(line)["fact"]`` inside the constructor. Three
consequences followed.

**One malformed line poisoned every load.** An unterminated write, a partial
flush, or a single corrupt record raised out of ``__init__``, so the whole store
became unreadable. A store that fails open on corruption is bad; one that fails
*totally* is worse, because a recoverable defect ends the run.

**There was no scope.** Every attempt shared one file, so a preference written
by one task could be retrieved by an unrelated one, and by a different tenant or
subject. For the learning family — where the whole measurement is whether a
stored preference is used later — cross-attempt bleed does not merely add noise,
it fabricates the effect being measured.

**Content was trusted.** A recalled string went into the system prompt verbatim.
Memory is model-authored text, so it is untrusted input, and treating it as
configuration is how prompt content becomes control flow.

This store therefore records provenance, scope, schema version and expiry on
every record; refuses cross-scope reads; and quarantines a malformed record
instead of discarding it or letting it stop the load. Quarantine is deliberate:
a silently dropped record and a correctly absent one are indistinguishable
afterwards, which would make a memory failure look like a model that never
learned.
"""

import datetime
import json
import os
import re
import tempfile
from collections.abc import Mapping


MEMORY_VERSION = "brick.memory-record/1"

_SCOPE_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_MAX_CONTENT = 2000
_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset({
    "the", "a", "an", "to", "of", "and", "or", "for", "with", "my", "me",
    "i", "is", "are", "in", "on", "at", "it", "that", "this", "be", "do",
})

# A memory record is model-authored text. It is quoted into a prompt, never
# interpreted, and these markers are refused so recalled content cannot forge
# turn boundaries or role headers in the assembled conversation.
_INJECTION_MARKERS = (
    "<|im_start|>", "<|im_end|>", "<|system|>", "<|user|>", "<|assistant|>",
    "\x00",
)


class MemoryScopeError(ValueError):
    """A scope is malformed. A developer defect, not untrusted input."""


class MemoryScope:
    """Where a record lives. Reads never cross a scope boundary."""

    __slots__ = ("tenant", "subject", "attempt")

    def __init__(self, tenant, subject, attempt=None):
        for name, value in (("tenant", tenant), ("subject", subject)):
            if not isinstance(value, str) or not _SCOPE_PART.fullmatch(value):
                raise MemoryScopeError(
                    "{} must match {}".format(name, _SCOPE_PART.pattern)
                )
        if attempt is not None and (
            not isinstance(attempt, str) or not _SCOPE_PART.fullmatch(attempt)
        ):
            raise MemoryScopeError(
                "attempt must match {}".format(_SCOPE_PART.pattern)
            )
        self.tenant = tenant
        self.subject = subject
        self.attempt = attempt

    def key(self):
        return (self.tenant, self.subject, self.attempt)

    def as_record(self):
        return {
            "tenant": self.tenant,
            "subject": self.subject,
            "attempt": self.attempt,
        }

    def permits(self, other):
        """True when a record in ``other`` is readable from this scope.

        Tenant and subject must match exactly. An attempt-scoped record is
        private to that attempt; a record with no attempt is shared across the
        subject. Nothing widens a scope.
        """
        if (self.tenant, self.subject) != (other.tenant, other.subject):
            return False
        if other.attempt is None:
            return True
        return other.attempt == self.attempt

    def __eq__(self, value):
        return isinstance(value, MemoryScope) and self.key() == value.key()

    def __hash__(self):
        return hash(self.key())

    def __repr__(self):
        return "MemoryScope({!r}, {!r}, {!r})".format(
            self.tenant, self.subject, self.attempt
        )


class MemoryRecord:
    """One untrusted, scoped, expiring memory."""

    __slots__ = ("content", "scope", "provenance", "created_at", "expires_at")

    def __init__(self, content, scope, provenance, created_at,
                 expires_at=None):
        self.content = content
        self.scope = scope
        self.provenance = provenance
        self.created_at = created_at
        self.expires_at = expires_at

    def is_expired(self, now):
        """True when this record must not be served.

        ``expires_at`` is stored as an ISO-8601 string, so it is parsed here
        rather than compared directly. An expiry that cannot be evaluated --
        unparseable, or naive against an aware clock -- counts as expired.
        Serving a record whose lifetime is unknown is the risk worth avoiding;
        hiding one costs only a recall.
        """
        if self.expires_at is None:
            return False
        expires = _parse_timestamp(self.expires_at)
        if expires is None:
            return True
        if (expires.tzinfo is None) != (now.tzinfo is None):
            return True
        return now >= expires

    def as_record(self):
        return {
            "schema_version": MEMORY_VERSION,
            "content": self.content,
            "scope": self.scope.as_record(),
            "provenance": self.provenance,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }

    def __repr__(self):
        return "MemoryRecord({!r}, {!r})".format(self.content, self.scope)


def _parse_timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except ValueError:
        return None


def validate_content(content):
    """Return a problem string, or None. Untrusted-input rules only."""
    if not isinstance(content, str):
        return "content must be a string"
    stripped = content.strip()
    if not stripped:
        return "content must not be blank"
    if len(content) > _MAX_CONTENT:
        return "content exceeds {} characters".format(_MAX_CONTENT)
    lowered = content.casefold()
    for marker in _INJECTION_MARKERS:
        if marker in lowered or marker in content:
            return "content contains a control marker: {!r}".format(marker)
    return None


class QuarantinedRecord:
    """A record that could not be loaded, retained with its reason.

    Retained rather than discarded because a silently dropped memory and a
    correctly absent one are indistinguishable afterwards, which would make a
    memory failure look like a model that never learned.
    """

    __slots__ = ("line_number", "reason", "raw")

    def __init__(self, line_number, reason, raw):
        self.line_number = line_number
        self.reason = reason
        self.raw = raw[:_MAX_CONTENT]

    def as_record(self):
        return {
            "line_number": self.line_number,
            "reason": self.reason,
            "raw": self.raw,
        }

    def __repr__(self):
        return "QuarantinedRecord({}, {!r})".format(
            self.line_number, self.reason
        )


class ScopedMemoryStore:
    """Append-only scoped memory with quarantine and expiry.

    ``write_policy`` is explicit: ``"append"`` permits writes, ``"read_only"``
    refuses them. The no-memory ablation and every read-only condition use
    ``"read_only"`` so a disabled bridge is enforced by the store rather than by
    a caller remembering not to write.
    """

    def __init__(self, path, scope, write_policy="append", now=None):
        if write_policy not in ("append", "read_only"):
            raise ValueError("write_policy must be 'append' or 'read_only'")
        if not isinstance(scope, MemoryScope):
            raise MemoryScopeError("scope must be a MemoryScope")
        self.path = str(path)
        self.scope = scope
        self.write_policy = write_policy
        self._now = now or (lambda: datetime.datetime.now(datetime.timezone.utc))
        self.records = []
        self.quarantined = []
        self._load()

    # -- loading -------------------------------------------------------------

    def _load(self):
        if not os.path.exists(self.path):
            return
        with open(self.path, "r", encoding="utf-8", errors="replace") as handle:
            for number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                record, reason = self._decode(line)
                if record is None:
                    # One bad line must never stop the load. The released store
                    # raised out of __init__ and made the whole store unreadable.
                    self.quarantined.append(
                        QuarantinedRecord(number, reason, line)
                    )
                else:
                    self.records.append(record)

    def _decode(self, line):
        try:
            raw = json.loads(line)
        except ValueError as exc:
            return None, "malformed JSON: {}".format(exc)
        if not isinstance(raw, Mapping):
            return None, "record is not an object"
        if raw.get("schema_version") != MEMORY_VERSION:
            return None, "unsupported schema_version: {!r}".format(
                raw.get("schema_version")
            )
        problem = validate_content(raw.get("content"))
        if problem:
            return None, problem
        scope_raw = raw.get("scope")
        if not isinstance(scope_raw, Mapping):
            return None, "scope is missing or not an object"
        try:
            scope = MemoryScope(
                scope_raw.get("tenant"),
                scope_raw.get("subject"),
                scope_raw.get("attempt"),
            )
        except MemoryScopeError as exc:
            return None, "invalid scope: {}".format(exc)
        provenance = raw.get("provenance")
        if not isinstance(provenance, str) or not provenance:
            return None, "provenance must be a nonempty string"
        created = _parse_timestamp(raw.get("created_at"))
        if created is None:
            return None, "created_at must be an ISO-8601 timestamp"
        expires = None
        if raw.get("expires_at") is not None:
            expires = _parse_timestamp(raw.get("expires_at"))
            if expires is None:
                return None, "expires_at must be an ISO-8601 timestamp"
        return (
            MemoryRecord(
                raw["content"], scope, provenance,
                raw["created_at"], raw.get("expires_at"),
            ),
            None,
        )

    # -- writing -------------------------------------------------------------

    def write(self, content, provenance, ttl_seconds=None, scope=None):
        """Append one record. Returns ``(record, problem)``.

        A refused write returns a problem rather than raising, because an
        invalid memory is a model error and must not be recorded on the
        instrument axis.
        """
        if self.write_policy != "append":
            return None, "memory is read-only for this condition"
        problem = validate_content(content)
        if problem:
            return None, problem
        if not isinstance(provenance, str) or not provenance:
            return None, "provenance must be a nonempty string"
        target = scope or self.scope
        if not isinstance(target, MemoryScope):
            return None, "scope must be a MemoryScope"
        if not self.scope.permits(target):
            return None, "refusing to write outside the current scope"
        now = self._now()
        expires = None
        if ttl_seconds is not None:
            if type(ttl_seconds) is not int or ttl_seconds <= 0:
                return None, "ttl_seconds must be a positive integer"
            expires = (
                now + datetime.timedelta(seconds=ttl_seconds)
            ).isoformat()
        record = MemoryRecord(
            content, target, provenance, now.isoformat(), expires
        )
        self._append(record)
        self.records.append(record)
        return record, None

    def _append(self, record):
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        line = json.dumps(
            record.as_record(), ensure_ascii=False, sort_keys=True
        )
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    # -- reading -------------------------------------------------------------

    def visible(self):
        """Records readable from this scope and not expired."""
        now = self._now()
        return [
            record
            for record in self.records
            if self.scope.permits(record.scope) and not record.is_expired(now)
        ]

    def search(self, query, limit=3):
        """Deterministic keyword overlap over visible records only."""
        tokens = _tokens(str(query))
        scored = []
        for index, record in enumerate(self.visible()):
            overlap = len(tokens & _tokens(record.content))
            if overlap:
                # index keeps ties in insertion order, so results are stable.
                scored.append((-overlap, index, record))
        scored.sort(key=lambda item: (item[0], item[1]))
        return [record for _, _, record in scored[:limit]]

    def quarantine_report(self):
        return [item.as_record() for item in self.quarantined]


def _tokens(text):
    return {word for word in _WORD.findall(text.lower()) if word not in _STOP}


def render_for_prompt(records, header="Remembered notes (untrusted):"):
    """Quote records for a prompt as inert, clearly-attributed data.

    Recalled text is model-authored and must be quoted, never interpreted. The
    header states that plainly so a later reader of the transcript can tell
    which text was instruction and which was recalled content.
    """
    if not records:
        return ""
    lines = [header]
    for record in records:
        flat = " ".join(record.content.split())
        lines.append("- [{}] {}".format(record.provenance, flat))
    return "\n".join(lines)
