"""Bounded, dependency-free redaction for connector and UI boundaries.

This module deliberately lives in the domain-independent harness layer so a
provider response can be scrubbed before it reaches an action record, browser
event, transcript, or log.  It is not a data-loss-prevention system; callers
must still avoid logging customer payloads in the first place.
"""
import re


_SECRET_KEY = re.compile(
    r"(?:^|[_-])(?:authorization|api[_-]?key|password|secret|token|"
    r"access[_-]?token|refresh[_-]?token|capability|nonce|"
    r"client[_-]?secret)(?:$|[_-])",
    re.I,
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/]+=*")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)([\"']?(?:authorization|api[_-]?key|password|secret|token|"
    r"access[_-]?token|refresh[_-]?token|capability|nonce|"
    r"client[_-]?secret)[\"']?\s*[:=]\s*)"
    r"([\"']?)([^\s,}\"']+)([\"']?)"
)


def redact(value, *, depth=0):
    """Return a bounded JSON-compatible copy with likely secrets removed."""
    if depth > 20:
        return "[truncated]"
    if isinstance(value, dict):
        out = {}
        for key, item in list(value.items())[:1_000]:
            label = str(key)[:256]
            out[label] = (
                "[redacted]"
                if _SECRET_KEY.search(label)
                else redact(item, depth=depth + 1)
            )
        return out
    if isinstance(value, (list, tuple)):
        return [redact(item, depth=depth + 1) for item in value[:2_000]]
    if isinstance(value, str):
        bounded = _BEARER.sub("Bearer [redacted]", value[:32_768])
        return _SECRET_ASSIGNMENT.sub(r"\1\2[redacted]\4", bounded)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact(str(value)[:32_768], depth=depth + 1)


def redact_text(value, *, limit=32_768):
    """Redact one diagnostic and return text with a deterministic bound."""
    clean = redact(str(value)[:limit])
    return clean if isinstance(clean, str) else str(clean)[:limit]
