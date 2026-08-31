"""Execution receipts and a plan-grounded task ledger.

Models may propose work, but they cannot manufacture evidence that it ran.
Only :class:`ReceiptIssuer`, held by the tool pipeline, can sign a receipt.
The ledger accepts a signed successful receipt only for the earliest matching
pending plan entry.  An unplanned success is preserved as unmatched evidence;
it never creates a new plan entry after the fact.
"""

from dataclasses import dataclass, replace
import hashlib
import hmac
import os
import re

from .lifecycle import canonical_json_bytes, digest_value


RECEIPT_VERSION = "brick.tool-receipt/1"
LEDGER_VERSION = "brick.task-ledger/1"
DEFAULT_ISSUER = "brick.tool-pipeline/1"
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class ReceiptError(ValueError):
    """Receipt authenticity or shape is invalid."""


@dataclass(frozen=True)
class ToolReceipt:
    schema_version: str
    receipt_id: str
    issuer: str
    call_id: str
    tool: str
    effect: str
    args_digest: str
    result_digest: str
    signature: str

    def unsigned_record(self):
        return {
            "schema_version": self.schema_version,
            "issuer": self.issuer,
            "call_id": self.call_id,
            "tool": self.tool,
            "effect": self.effect,
            "args_digest": self.args_digest,
            "result_digest": self.result_digest,
        }


class ReceiptIssuer:
    """Attempt-local HMAC authority unavailable to model output."""

    def __init__(self, secret=None, issuer=DEFAULT_ISSUER):
        secret = os.urandom(32) if secret is None else secret
        if not isinstance(secret, bytes) or len(secret) < 16:
            raise ValueError("receipt issuer secret must be at least 16 bytes")
        if not isinstance(issuer, str) or not issuer:
            raise ValueError("receipt issuer id must be nonempty")
        self._secret = bytes(secret)
        self.issuer = issuer

    def issue(
        self,
        *,
        call_id,
        tool,
        effect,
        args_digest,
        result_digest,
    ):
        values = (call_id, tool, effect, args_digest, result_digest)
        if not all(isinstance(value, str) and value for value in values):
            raise ReceiptError("receipt fields must be nonempty strings")
        if not _HEX_64.fullmatch(args_digest) or not _HEX_64.fullmatch(
            result_digest
        ):
            raise ReceiptError("receipt arguments and result require SHA-256 digests")
        unsigned = {
            "schema_version": RECEIPT_VERSION,
            "issuer": self.issuer,
            "call_id": call_id,
            "tool": tool,
            "effect": effect,
            "args_digest": args_digest,
            "result_digest": result_digest,
        }
        payload = canonical_json_bytes(unsigned)
        receipt_id = hashlib.sha256(payload).hexdigest()
        signature = hmac.new(
            self._secret, payload + receipt_id.encode("ascii"), hashlib.sha256
        ).hexdigest()
        return ToolReceipt(
            receipt_id=receipt_id,
            signature=signature,
            **unsigned,
        )

    def verify(self, receipt):
        if not isinstance(receipt, ToolReceipt):
            return False
        if receipt.schema_version != RECEIPT_VERSION:
            return False
        if receipt.issuer != self.issuer:
            return False
        if not _HEX_64.fullmatch(receipt.args_digest) or not _HEX_64.fullmatch(
            receipt.result_digest
        ):
            return False
        payload = canonical_json_bytes(receipt.unsigned_record())
        receipt_id = hashlib.sha256(payload).hexdigest()
        expected = hmac.new(
            self._secret, payload + receipt_id.encode("ascii"), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(receipt.receipt_id, receipt_id) and hmac.compare_digest(
            receipt.signature, expected
        )


@dataclass(frozen=True)
class LedgerEntry:
    entry_id: str
    index: int
    tool: str
    intent_digest: str
    grounded_by: object = None


@dataclass(frozen=True)
class GroundingResult:
    status: str
    receipt_id: str
    entry_id: object = None


class TaskLedger:
    """Mutable attempt-local ledger whose entries are immutable values."""

    def __init__(self, run_id, steps):
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("run_id must be nonempty")
        if not isinstance(steps, (list, tuple)):
            raise TypeError("steps must be a sequence")
        self._run_id = run_id
        self._entries = []
        self._unmatched = []
        self.extend(steps)

    def extend(self, steps):
        """Append a newly accepted plan; existing evidence is never rewritten."""
        if not isinstance(steps, (list, tuple)):
            raise TypeError("steps must be a sequence")
        added = []
        start = len(self._entries)
        for offset, step in enumerate(steps):
            index = start + offset
            if not isinstance(step, dict) or set(step) != {"tool", "what"}:
                raise ValueError("ledger steps require exactly tool and what")
            tool = step["tool"]
            what = step["what"]
            if not isinstance(tool, str) or not tool:
                raise ValueError("ledger tool must be nonempty")
            if not isinstance(what, str):
                raise TypeError("ledger intent must be a string")
            entry_id = hashlib.sha256(
                canonical_json_bytes(
                    {
                        "schema_version": LEDGER_VERSION,
                        "run_id": self._run_id,
                        "index": index,
                        "tool": tool,
                        "intent_digest": digest_value(what),
                    }
                )
            ).hexdigest()
            added.append(
                LedgerEntry(
                    entry_id=entry_id,
                    index=index,
                    tool=tool,
                    intent_digest=digest_value(what),
                )
            )
        self._entries.extend(added)
        return tuple(added)

    @property
    def entries(self):
        return tuple(self._entries)

    @property
    def unmatched_receipts(self):
        return tuple(self._unmatched)

    @property
    def nonempty(self):
        return bool(self._entries)

    @property
    def all_grounded(self):
        return self.nonempty and all(
            entry.grounded_by is not None for entry in self._entries
        )

    @property
    def completion_ready(self):
        return self.all_grounded and not self._unmatched

    def pending_entry_for(self, tool):
        for entry in self._entries:
            if entry.tool == tool and entry.grounded_by is None:
                return entry
        return None

    def ground(self, receipt, issuer):
        if not isinstance(issuer, ReceiptIssuer):
            raise TypeError("issuer must be a ReceiptIssuer")
        if not issuer.verify(receipt):
            raise ReceiptError("receipt signature or issuer is invalid")
        entry = self.pending_entry_for(receipt.tool)
        if entry is None:
            self._unmatched.append(receipt.receipt_id)
            return GroundingResult("unmatched", receipt.receipt_id)
        updated = replace(entry, grounded_by=receipt.receipt_id)
        self._entries[entry.index] = updated
        return GroundingResult(
            "grounded", receipt.receipt_id, entry_id=entry.entry_id
        )

    def summary(self):
        return {
            "schema_version": LEDGER_VERSION,
            "entries": len(self._entries),
            "grounded": sum(
                entry.grounded_by is not None for entry in self._entries
            ),
            "unmatched": len(self._unmatched),
            "completion_ready": self.completion_ready,
        }


__all__ = [
    "DEFAULT_ISSUER",
    "GroundingResult",
    "LEDGER_VERSION",
    "LedgerEntry",
    "RECEIPT_VERSION",
    "ReceiptError",
    "ReceiptIssuer",
    "TaskLedger",
    "ToolReceipt",
]
