"""Receipt-v1 tool execution pipeline.

Order is fixed and monotonic:

proposal -> schema/policy/cancellation checks -> durable dispatch barrier ->
real executor -> normalized result -> signed receipt -> ledger grounding.

There is no automatic write retry.  If durability fails before dispatch, the
executor is never called.  If durability fails after an effect, the run fails
as an instrument fault and no receipt is minted for the uncommitted result.
"""

from dataclasses import dataclass
import hashlib
import json

from .lifecycle import canonical_json_bytes, digest_value
from .receipts import ReceiptIssuer, TaskLedger
from .runtime import MAX_CONFIRMATION_DETAIL_BYTES


TOOL_PIPELINE_VERSION = "brick.tool-pipeline/1"


@dataclass(frozen=True)
class PipelineResult:
    ok: bool
    status: str
    observation: str
    call_id: str
    receipt: object = None
    ledger_entry: object = None


class ToolPipeline:
    def __init__(
        self,
        attempt,
        journal,
        ledger,
        *,
        issuer=None,
    ):
        if not isinstance(ledger, TaskLedger):
            raise TypeError("ledger must be a TaskLedger")
        self.attempt = attempt
        self.journal = journal
        self.ledger = ledger
        self.issuer = ReceiptIssuer() if issuer is None else issuer
        if not isinstance(self.issuer, ReceiptIssuer):
            raise TypeError("issuer must be a ReceiptIssuer")
        self._counter = 0

    def _call_id(self, name, args_digest):
        value = {
            "schema_version": TOOL_PIPELINE_VERSION,
            "attempt_id": self.attempt.attempt_id,
            "sequence": self._counter,
            "tool": name,
            "args_digest": args_digest,
        }
        self._counter += 1
        return hashlib.sha256(canonical_json_bytes(value)).hexdigest()

    def _observe_rejection(self, name, args, observation):
        self.attempt.record_action(name, args, False, observation)
        hook = self.attempt.hooks.on_tool
        if hook:
            try:
                hook(name, args, False, observation)
            except Exception:
                pass

    def execute(self, name, args):
        args = args if isinstance(args, dict) else {}
        args_digest = digest_value(args)
        call_id = self._call_id(name, args_digest)
        pending = self.ledger.pending_entry_for(name)
        entry_id = pending.entry_id if pending is not None else "unplanned"
        self.journal.append(
            "tool.proposed",
            {
                "call_id": call_id,
                "tool": str(name) or "unknown",
                "args_digest": args_digest,
                "ledger_entry": entry_id,
            },
        )

        problems = self.attempt.tools.validate(name, args)
        if problems:
            self.journal.append(
                "tool.rejected",
                {
                    "call_id": call_id,
                    "tool": str(name) or "unknown",
                    "reason_code": "schema_rejected",
                },
            )
            observation = "ERROR: " + "; ".join(problems)
            self._observe_rejection(name, args, observation)
            return PipelineResult(
                False, "rejected", observation, call_id
            )

        effect = self.attempt.policy.effect(name)
        if effect != "read" and pending is None:
            self.journal.append(
                "tool.rejected",
                {
                    "call_id": call_id,
                    "tool": name,
                    "reason_code": "unplanned_effect",
                },
            )
            observation = "ERROR: mutating tool was not in the accepted plan"
            self._observe_rejection(name, args, observation)
            return PipelineResult(
                False, "rejected", observation, call_id
            )

        if self.attempt.cancelled():
            self.journal.append(
                "tool.rejected",
                {
                    "call_id": call_id,
                    "tool": name,
                    "reason_code": "cancelled_before_dispatch",
                },
            )
            observation = "ERROR: run cancelled before tool dispatch"
            self._observe_rejection(name, args, observation)
            return PipelineResult(
                False, "cancelled", observation, call_id
            )

        if effect in {"external_write", "shell"}:
            detail = json.dumps(
                {"tool": name, "args": args},
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            )
            if (
                len(detail.encode("utf-8"))
                > MAX_CONFIRMATION_DETAIL_BYTES
            ):
                self.journal.append(
                    "tool.rejected",
                    {
                        "call_id": call_id,
                        "tool": name,
                        "reason_code": "confirmation_payload_too_large",
                    },
                )
                observation = (
                    "ERROR: complete confirmation payload exceeds {} bytes; "
                    "shorten the request"
                ).format(MAX_CONFIRMATION_DETAIL_BYTES)
                self._observe_rejection(name, args, observation)
                return PipelineResult(
                    False, "rejected", observation, call_id
                )
            if not self.attempt.policy.confirm(name, detail):
                self.journal.append(
                    "tool.rejected",
                    {
                        "call_id": call_id,
                        "tool": name,
                        "reason_code": "policy_denied",
                    },
                )
                observation = (
                    "ERROR: operator confirmation was denied or unavailable"
                )
                self._observe_rejection(name, args, observation)
                return PipelineResult(
                    False, "denied", observation, call_id
                )

        # This fsynced event is the side-effect barrier.  An append exception
        # escapes and prevents the executor below from being entered.
        self.journal.append(
            "tool.dispatch_committed",
            {"call_id": call_id, "tool": name, "effect": effect},
        )

        # Cancellation can arrive after the barrier.  Close the dispatched
        # call explicitly, but do not invoke the executor.
        if self.attempt.cancelled():
            self.journal.append(
                "tool.failed",
                {
                    "call_id": call_id,
                    "tool": name,
                    "failure_class": "cancelled_before_effect",
                },
            )
            observation = "ERROR: run cancelled before tool effect"
            self._observe_rejection(name, args, observation)
            return PipelineResult(
                False, "cancelled", observation, call_id
            )

        ok, observation = self.attempt.tools.execute(
            name, args, self.attempt
        )
        observation = str(observation)
        if not ok:
            self.journal.append(
                "tool.failed",
                {
                    "call_id": call_id,
                    "tool": name,
                    "failure_class": "executor_rejected_or_failed",
                },
            )
            return PipelineResult(
                False, "failed", observation, call_id
            )

        result_digest = digest_value(observation)
        self.journal.append(
            "tool.succeeded",
            {
                "call_id": call_id,
                "tool": name,
                "result_digest": result_digest,
            },
        )
        receipt = self.issuer.issue(
            call_id=call_id,
            tool=name,
            effect=effect,
            args_digest=args_digest,
            result_digest=result_digest,
        )
        self.journal.append(
            "receipt.issued",
            {
                "call_id": call_id,
                "receipt_id": receipt.receipt_id,
                "tool": name,
                "issuer": receipt.issuer,
            },
        )
        grounding = self.ledger.ground(receipt, self.issuer)
        if grounding.status == "grounded":
            self.journal.append(
                "ledger.grounded",
                {
                    "receipt_id": receipt.receipt_id,
                    "ledger_entry": grounding.entry_id,
                },
            )
        else:
            self.journal.append(
                "ledger.unmatched",
                {"receipt_id": receipt.receipt_id, "tool": name},
            )
        return PipelineResult(
            True,
            "succeeded",
            observation,
            call_id,
            receipt=receipt,
            ledger_entry=grounding.entry_id,
        )


__all__ = ["PipelineResult", "TOOL_PIPELINE_VERSION", "ToolPipeline"]
