"""Attempt-local state for Brick's transactional GenieX cache protocol.

This module contains no transport or model code.  It only creates independent
128-bit session identifiers for each reasoning role and advances a role's
parent revision after the server proves that generation committed.  Prompt
contents never enter its diagnostics.
"""
from dataclasses import dataclass
import re
import secrets


CACHE_OFF = "off"
CACHE_MANAGED = "managed"
CACHE_LEGACY_TEST = "legacy-test"
CACHE_MODES = (CACHE_OFF, CACHE_MANAGED, CACHE_LEGACY_TEST)
PRODUCTION_CACHE_MODES = (CACHE_OFF, CACHE_MANAGED)

_SESSION = re.compile(r"^[0-9a-f]{32}$")
_REVISION = re.compile(r"^sha256:[0-9a-f]{64}$")
_STATUSES = frozenset(("cold", "reused", "reset"))
_REASONS = frozenset((
    "first_request",
    "exact_extension",
    "branch",
    "session_switch",
    "parent_mismatch",
))


class CacheConfigurationError(ValueError):
    """A caller requested an unsafe or unknown cache mode."""


class ManagedCacheProtocolError(RuntimeError):
    """The local transport did not satisfy the managed-cache contract."""


def validate_cache_mode(value, allow_legacy_test=False):
    if value not in CACHE_MODES:
        raise CacheConfigurationError(
            "cache_mode must be one of " + ", ".join(CACHE_MODES)
        )
    if value == CACHE_LEGACY_TEST and not allow_legacy_test:
        raise CacheConfigurationError(
            "legacy-test is restricted to the synthetic BrickKV runner"
        )
    return value


def validate_managed_request(value):
    if not isinstance(value, dict) \
            or set(value) != {"mode", "session", "parent"}:
        raise ManagedCacheProtocolError("invalid managed cache request")
    if value.get("mode") != CACHE_MANAGED:
        raise ManagedCacheProtocolError("managed cache mode is not declared")
    if not isinstance(value.get("session"), str) \
            or not _SESSION.fullmatch(value["session"]):
        raise ManagedCacheProtocolError("invalid managed cache session")
    if not isinstance(value.get("parent"), str) \
            or (value["parent"] and not _REVISION.fullmatch(value["parent"])):
        raise ManagedCacheProtocolError("invalid managed cache parent")
    return value


def validate_managed_metadata(metadata):
    """Validate one final server commit record without mutating lineage state."""
    if not isinstance(metadata, dict):
        raise ManagedCacheProtocolError(
            "managed cache response is missing final metadata"
        )
    required = {"mode", "status", "revision", "reason"}
    if set(metadata) != required:
        raise ManagedCacheProtocolError(
            "managed cache metadata must contain exactly "
            + ", ".join(sorted(required))
        )
    if metadata["mode"] != CACHE_MANAGED:
        raise ManagedCacheProtocolError("managed cache mode was not acknowledged")
    if metadata["status"] not in _STATUSES:
        raise ManagedCacheProtocolError("unknown managed cache status")
    if metadata["reason"] not in _REASONS:
        raise ManagedCacheProtocolError("unknown managed cache reason")
    if not isinstance(metadata["revision"], str) \
            or not _REVISION.fullmatch(metadata["revision"]):
        raise ManagedCacheProtocolError("invalid managed cache revision")
    if metadata["status"] == "cold" \
            and metadata["reason"] != "first_request":
        raise ManagedCacheProtocolError("cold cache response has invalid reason")
    if metadata["status"] == "reused" \
            and metadata["reason"] != "exact_extension":
        raise ManagedCacheProtocolError("cache hit has invalid reason")
    if metadata["status"] == "reset" \
            and metadata["reason"] in ("first_request", "exact_extension"):
        raise ManagedCacheProtocolError("cache reset has invalid reason")
    return metadata


@dataclass
class _Lineage:
    session: str
    parent: str = ""


class CacheCoordinator:
    """One attempt's independent driver/router/verifier cache lineages."""

    def __init__(self):
        self.attempt_session = secrets.token_hex(16)
        self._lineages = {}
        self._events = []

    @staticmethod
    def _role(role):
        return role or "driver"

    def request(self, role=None):
        role = self._role(role)
        lineage = self._lineages.get(role)
        if lineage is None:
            lineage = _Lineage(session=secrets.token_hex(16))
            self._lineages[role] = lineage
        return {
            "mode": CACHE_MANAGED,
            "session": lineage.session,
            "parent": lineage.parent,
        }

    def commit(self, metadata, role=None):
        role = self._role(role)
        validate_managed_metadata(metadata)

        lineage = self._lineages.get(role)
        if lineage is None:
            raise ManagedCacheProtocolError(
                "managed cache response has no matching role request"
            )
        lineage.parent = metadata["revision"]
        self._events.append({
            "role": role,
            "status": metadata["status"],
            "reason": metadata["reason"],
            "revision": metadata["revision"],
        })

    def diagnostics(self):
        return {
            "mode": CACHE_MANAGED,
            "attempt_session": self.attempt_session,
            "roles": {
                role: {"session": value.session, "parent": value.parent}
                for role, value in sorted(self._lineages.items())
            },
            "events": list(self._events),
        }
