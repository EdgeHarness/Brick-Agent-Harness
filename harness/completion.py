"""Fail-closed completion decisions (S1R).

The released loop asked a model to verify its own work and then read the answer
with ``verdict.get("complete", True)``. Every degenerate case therefore resolved
to *complete*: a malformed verdict, a missing key, a timed-out verifier, a
verifier that ran out of budget. The one situation where a task is most likely
unfinished -- the verifier could not answer -- was scored as finished.

This module inverts that. Completion is decided by **authoritative
postconditions over real state**, and a model verifier may only explain, never
establish. Its precedence rule is:

===================  ==================  ==========
Postconditions       Model verifier      Result
===================  ==================  ==========
unsatisfied          says complete       incomplete
satisfied            says incomplete     complete
unavailable/raised   anything            unknown
satisfied            malformed/absent    complete
===================  ==================  ==========

Two consequences are deliberate. A verifier that contradicts satisfied
postconditions does not block completion -- state is authoritative, and letting
an unreliable verifier veto real evidence would manufacture false negatives.
A verifier that claims completion the postconditions do not support is ignored
entirely, because that is the direction with consequences.

``UNKNOWN`` is a first-class outcome, not a synonym for incomplete. It says the
instrument could not determine the answer. Keeping it distinct is what stops an
instrument failure from being recorded as a model failure, which hard rule 5
forbids.

The core owns the precedence and never imports a domain. A domain pack supplies
one opaque callable that reports whether the required effects exist in
authoritative state.
"""

from collections.abc import Mapping, Sequence


COMPLETION_VERSION = "brick.completion/1"

COMPLETE = "complete"
INCOMPLETE = "incomplete"
UNKNOWN = "unknown"

_STATUSES = (COMPLETE, INCOMPLETE, UNKNOWN)

# Why a decision came out the way it did. Recorded in attempt evidence so a
# reader can separate "the model did not finish" from "we could not tell".
REASON_POSTCONDITIONS_SATISFIED = "postconditions_satisfied"
REASON_POSTCONDITIONS_UNSATISFIED = "postconditions_unsatisfied"
REASON_POSTCONDITIONS_UNAVAILABLE = "postconditions_unavailable"
REASON_POSTCONDITION_ERROR = "postcondition_error"
REASON_POSTCONDITION_MALFORMED = "postcondition_malformed"


class PostconditionResult:
    """What authoritative state says about the required effects.

    ``satisfied`` is a tri-state. ``None`` means the check could not be
    performed -- unreadable state, an unavailable service -- and must never be
    read as either finished or unfinished.
    """

    __slots__ = ("satisfied", "missing", "detail")

    def __init__(self, satisfied, missing=(), detail=None):
        if satisfied is not None and type(satisfied) is not bool:
            raise TypeError("satisfied must be True, False or None")
        if isinstance(missing, (str, bytes)) or not isinstance(
            missing, Sequence
        ):
            raise TypeError("missing must be a sequence of strings")
        for item in missing:
            if not isinstance(item, str) or not item:
                raise TypeError("missing entries must be nonempty strings")
        if detail is not None and not isinstance(detail, str):
            raise TypeError("detail must be a string or None")
        self.satisfied = satisfied
        self.missing = tuple(missing)
        self.detail = detail

    def __repr__(self):
        return "PostconditionResult(satisfied={!r}, missing={!r})".format(
            self.satisfied, list(self.missing)
        )


class CompletionDecision:
    """An immutable completion outcome with its justification."""

    __slots__ = ("status", "reason", "missing", "verifier_note",
                 "verifier_contradicted")

    def __init__(
        self,
        status,
        reason,
        missing=(),
        verifier_note=None,
        verifier_contradicted=False,
    ):
        if status not in _STATUSES:
            raise ValueError("unsupported completion status: {!r}".format(status))
        self.status = status
        self.reason = reason
        self.missing = tuple(missing)
        self.verifier_note = verifier_note
        self.verifier_contradicted = bool(verifier_contradicted)

    @property
    def is_complete(self):
        """True only for COMPLETE. UNKNOWN is never treated as done."""
        return self.status == COMPLETE

    def as_record(self):
        return {
            "schema_version": COMPLETION_VERSION,
            "status": self.status,
            "reason": self.reason,
            "missing": list(self.missing),
            "verifier_note": self.verifier_note,
            "verifier_contradicted": self.verifier_contradicted,
        }

    def __repr__(self):
        return "CompletionDecision({!r}, {!r})".format(self.status, self.reason)


def read_verifier_claim(verdict):
    """Interpret a model verifier's reply. Returns ``(claim, note)``.

    ``claim`` is ``True``, ``False`` or ``None``. ``None`` covers every
    degenerate reply -- absent, malformed, wrong type, non-boolean ``complete``
    -- and is the value the released code turned into ``True``.
    """
    if not isinstance(verdict, Mapping):
        return None, None
    claim = verdict.get("complete")
    if type(claim) is not bool:
        claim = None
    note = verdict.get("missing")
    if not isinstance(note, str) or not note.strip():
        note = None
    return claim, note


def decide(postconditions, verdict=None):
    """Decide completion. Authoritative state wins; the verifier only explains.

    ``postconditions`` is a ``PostconditionResult``, or ``None`` when no
    authoritative check was available at all. A model verdict can never move the
    result toward COMPLETE.
    """
    claim, note = read_verifier_claim(verdict)

    if postconditions is None:
        return CompletionDecision(
            UNKNOWN,
            REASON_POSTCONDITIONS_UNAVAILABLE,
            verifier_note=note,
            # A verifier claiming completion with no authoritative check is the
            # exact fail-open path being removed; record that it disagreed.
            verifier_contradicted=claim is True,
        )
    if not isinstance(postconditions, PostconditionResult):
        return CompletionDecision(
            UNKNOWN,
            REASON_POSTCONDITION_MALFORMED,
            verifier_note=note,
            verifier_contradicted=claim is True,
        )
    if postconditions.satisfied is None:
        return CompletionDecision(
            UNKNOWN,
            REASON_POSTCONDITIONS_UNAVAILABLE,
            missing=postconditions.missing,
            verifier_note=note or postconditions.detail,
            verifier_contradicted=claim is True,
        )
    if postconditions.satisfied:
        return CompletionDecision(
            COMPLETE,
            REASON_POSTCONDITIONS_SATISFIED,
            verifier_note=note,
            # State is authoritative. A verifier saying "not done" over
            # satisfied postconditions does not veto real evidence; recording
            # the disagreement is enough.
            verifier_contradicted=claim is False,
        )
    return CompletionDecision(
        INCOMPLETE,
        REASON_POSTCONDITIONS_UNSATISFIED,
        missing=postconditions.missing,
        verifier_note=note,
        verifier_contradicted=claim is True,
    )


def evaluate(check, verdict=None):
    """Run a domain-supplied postcondition callable and decide from its result.

    ``check`` takes no arguments and returns a ``PostconditionResult``. Any
    exception, or any non-conforming return, yields UNKNOWN rather than
    propagating: a broken postcondition check is an instrument fault and must
    not be recorded as a model outcome.
    """
    if check is None:
        return decide(None, verdict)
    try:
        result = check()
    except Exception as exc:  # noqa: BLE001 - deliberately total
        claim, note = read_verifier_claim(verdict)
        return CompletionDecision(
            UNKNOWN,
            REASON_POSTCONDITION_ERROR,
            verifier_note=note or "{}: {}".format(type(exc).__name__, exc),
            verifier_contradicted=claim is True,
        )
    return decide(result, verdict)
