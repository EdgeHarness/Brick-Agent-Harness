"""Fault classification and explicit context outcomes (S1R).

The released executor ended with::

    except Exception as error:  # keep-the-episode-alive
        attempt.record_action(name, args, False, repr(error))
        ok, obs = False, f"ERROR: {type(error).__name__}: {error}"

so *every* exception became a tool error handed back to the model. A disk-full
``OSError``, a ``MemoryError``, an ``ImportError`` from a broken install, or an
outright bug in the harness all arrived at the model as ``ERROR: ...``, which it
then retried against. That is the conversion hard rule 5 forbids: a runner or
environment failure recorded as a model failure. It also wastes the opportunity
budget retrying something no model could fix, and can turn one infrastructure
fault into a whole failed attempt that a grader scores as a genuine model loss.

A narrower instance sat just above it: a bare ``except KeyError`` reported
"missing required parameter", but a ``KeyError`` from any dict access inside a
tool body produced the same message, so a bug in the tool was described to the
model as its own bad argument.

This module classifies a fault onto the origin axis S4 already records
(``model``, ``runner``, ``environment``) and decides, per origin, whether the
attempt may continue:

* **model** -- the model sent something invalid. Feed the message back, charge
  the turn, continue. This is the only origin the model can act on.
* **runner** -- our code or a tool implementation broke. Abort. Never describe
  it to the model as its own error.
* **environment** -- the host, disk, or memory failed. Abort.

Classification is conservative in one direction: an exception we do not
recognise is a **runner** fault, not a model fault. Misattributing an unknown
defect to the model silently corrupts the outcome being measured; misattributing
it to the runner produces a loud, visible instrument failure that someone
investigates.

Context outcomes are explicit for the same reason. Silently dropping an
observation or a history turn changes what the model saw without leaving a
record, so a later reader cannot tell whether the model ignored information or
never received it.
"""

from collections.abc import Sequence


FAULTS_VERSION = "brick.fault-classification/1"

ORIGIN_MODEL = "model"
ORIGIN_RUNNER = "runner"
ORIGIN_ENVIRONMENT = "environment"

# Mirrors harness/evidence.py's execution_status vocabulary so a classified
# fault maps onto retained evidence without a second translation table.
STATUS_DONE = "done"
STATUS_BUDGET_EXHAUSTED = "budget_exhausted"
STATUS_MODEL_ERROR = "model_error"
STATUS_RUNNER_ERROR = "runner_error"
STATUS_TIMEOUT = "timeout"
STATUS_ABORTED = "aborted"
STATUS_ENVIRONMENT_UNSTABLE = "environment_unstable"


class BrickFault(Exception):
    """Base for faults Brick raises deliberately."""

    origin = ORIGIN_RUNNER
    execution_status = STATUS_RUNNER_ERROR
    # Whether the message may be shown to the model. Only model-origin faults
    # may be, because anything else invites a retry that cannot succeed.
    model_visible = False


class ModelInputFault(BrickFault):
    """The model supplied something invalid. Safe to report back to it."""

    origin = ORIGIN_MODEL
    execution_status = STATUS_MODEL_ERROR
    model_visible = True


class RunnerFault(BrickFault):
    """Brick's own code, or a tool implementation, failed."""


class EnvironmentFault(BrickFault):
    """The host failed: disk, memory, a missing dependency."""

    origin = ORIGIN_ENVIRONMENT
    execution_status = STATUS_ENVIRONMENT_UNSTABLE


class ModelTimeout(BrickFault):
    """The model call exceeded its deadline.

    Runner origin, not model: a model cannot choose to be faster, and recording
    a timeout as a model error would let a slow host depress a measured score.
    """

    origin = ORIGIN_RUNNER
    execution_status = STATUS_TIMEOUT


class BudgetExhausted(BrickFault):
    """The opportunity ledger ran out.

    Model origin: the budget is part of the task, and spending it is a model
    outcome rather than an instrument failure. It is not model_visible, since
    there is no turn left in which to tell it.
    """

    origin = ORIGIN_MODEL
    execution_status = STATUS_BUDGET_EXHAUSTED


# Exceptions that always indicate the host rather than our logic.
_ENVIRONMENT_TYPES = (MemoryError, OSError)
# Exceptions that indicate a broken install or interpreter state.
_ENVIRONMENT_NAMES = ("ImportError", "ModuleNotFoundError")


class FaultClassification:
    """An immutable classification result."""

    __slots__ = ("origin", "execution_status", "model_visible", "message",
                 "exception_type")

    def __init__(self, origin, execution_status, model_visible, message,
                 exception_type):
        self.origin = origin
        self.execution_status = execution_status
        self.model_visible = model_visible
        self.message = message
        self.exception_type = exception_type

    @property
    def is_model_fault(self):
        return self.origin == ORIGIN_MODEL

    @property
    def aborts_attempt(self):
        """Only a model fault lets the attempt continue."""
        return self.origin != ORIGIN_MODEL

    def as_record(self):
        return {
            "schema_version": FAULTS_VERSION,
            "origin": self.origin,
            "execution_status": self.execution_status,
            "model_visible": self.model_visible,
            "exception_type": self.exception_type,
            "message": self.message,
        }

    def __repr__(self):
        return "FaultClassification({!r}, {!r})".format(
            self.origin, self.execution_status
        )


def classify(exc):
    """Classify an exception onto the origin axis.

    An unrecognised exception is a **runner** fault. Misattributing an unknown
    defect to the model silently corrupts the measured outcome; attributing it
    to the runner produces a visible instrument failure someone investigates.
    """
    name = type(exc).__name__
    message = str(exc) or name

    if isinstance(exc, BrickFault):
        return FaultClassification(
            exc.origin, exc.execution_status, exc.model_visible, message, name
        )
    # TimeoutError is a subclass of OSError, so it must be tested first.
    if isinstance(exc, TimeoutError):
        return FaultClassification(
            ORIGIN_RUNNER, STATUS_TIMEOUT, False, message, name
        )
    if isinstance(exc, _ENVIRONMENT_TYPES) or name in _ENVIRONMENT_NAMES:
        return FaultClassification(
            ORIGIN_ENVIRONMENT, STATUS_ENVIRONMENT_UNSTABLE, False, message,
            name,
        )
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        return FaultClassification(
            ORIGIN_RUNNER, STATUS_ABORTED, False, message, name
        )
    return FaultClassification(
        ORIGIN_RUNNER, STATUS_RUNNER_ERROR, False, message, name
    )


def observation_for(classification):
    """The text the model may see, or None.

    Returning None is the safety property: a runner or environment fault must
    never reach the model as though it were something the model did.
    """
    if not classification.model_visible:
        return None
    return "ERROR: {}".format(classification.message)


# --- explicit context outcomes ----------------------------------------------

CONTEXT_COMPLETE = "complete"
CONTEXT_OBSERVATION_TRUNCATED = "observation_truncated"
CONTEXT_HISTORY_DROPPED = "history_dropped"


class ContextOutcome:
    """What the model actually saw, recorded rather than assumed.

    Silently shortening an observation or dropping a turn changes the input
    without leaving a trace, so a later reader cannot distinguish a model that
    ignored information from one that never received it.
    """

    __slots__ = ("status", "original_length", "delivered_length",
                 "dropped_turns")

    def __init__(self, status, original_length, delivered_length,
                 dropped_turns=0):
        if status not in (
            CONTEXT_COMPLETE,
            CONTEXT_OBSERVATION_TRUNCATED,
            CONTEXT_HISTORY_DROPPED,
        ):
            raise ValueError("unsupported context status: {!r}".format(status))
        self.status = status
        self.original_length = original_length
        self.delivered_length = delivered_length
        self.dropped_turns = dropped_turns

    @property
    def was_truncated(self):
        return self.status != CONTEXT_COMPLETE

    def as_record(self):
        return {
            "schema_version": FAULTS_VERSION,
            "status": self.status,
            "original_length": self.original_length,
            "delivered_length": self.delivered_length,
            "dropped_turns": self.dropped_turns,
        }

    def __repr__(self):
        return "ContextOutcome({!r}, {}/{})".format(
            self.status, self.delivered_length, self.original_length
        )


TRUNCATION_NOTICE = "\n[truncated: {} of {} characters shown]"


def truncate_observation(text, limit):
    """Shorten an observation and say so, in-band and in the record.

    The notice is appended to the delivered text as well as recorded, so the
    model is told its input was cut rather than being left to infer it from a
    sentence ending mid-word.
    """
    if not isinstance(text, str):
        text = str(text)
    if type(limit) is not int or limit <= 0:
        raise ValueError("limit must be a positive integer")
    if len(text) <= limit:
        return text, ContextOutcome(CONTEXT_COMPLETE, len(text), len(text))
    notice = TRUNCATION_NOTICE.format(limit, len(text))
    delivered = text[:limit] + notice
    return delivered, ContextOutcome(
        CONTEXT_OBSERVATION_TRUNCATED, len(text), limit
    )


def drop_history(turns, keep):
    """Keep the most recent ``keep`` turns and record what was dropped."""
    if not isinstance(turns, Sequence) or isinstance(turns, (str, bytes)):
        raise TypeError("turns must be a sequence")
    if type(keep) is not int or keep < 0:
        raise ValueError("keep must be a nonnegative integer")
    total = len(turns)
    if total <= keep:
        return list(turns), ContextOutcome(CONTEXT_COMPLETE, total, total)
    kept = list(turns[total - keep:]) if keep else []
    return kept, ContextOutcome(
        CONTEXT_HISTORY_DROPPED, total, len(kept), total - len(kept)
    )
