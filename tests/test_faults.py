"""S1R fault classification and explicit context outcomes.

The released executor caught every exception and handed it to the model as
``ERROR: ...``. A disk-full ``OSError``, a ``MemoryError``, a broken install, or
a bug in the harness all arrived as though the model had done something wrong,
and the model retried against them. That is the conversion hard rule 5 forbids,
it wastes the opportunity budget on something no model can fix, and it can turn
one infrastructure fault into a failed attempt a grader scores as a genuine
model loss.
"""

import pytest

from harness import faults as f


# --- the released misattribution is gone ------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        OSError("no space left on device"),
        MemoryError(),
        ImportError("no module named openpyxl"),
    ],
)
def test_host_failures_are_environment_not_model(exc):
    result = f.classify(exc)
    assert result.origin == f.ORIGIN_ENVIRONMENT
    assert result.is_model_fault is False
    assert result.aborts_attempt is True


@pytest.mark.parametrize(
    "exc",
    [
        AttributeError("'NoneType' object has no attribute 'id'"),
        TypeError("unsupported operand"),
        KeyError("lead_id"),
        ZeroDivisionError(),
        RuntimeError("harness bug"),
    ],
)
def test_programming_defects_are_runner_not_model(exc):
    """A KeyError from any dict access inside a tool body was reported to the
    model as its own missing parameter."""
    result = f.classify(exc)
    assert result.origin == f.ORIGIN_RUNNER
    assert result.is_model_fault is False


def test_an_unrecognised_exception_defaults_to_runner():
    """Conservative in one direction on purpose: misattributing an unknown
    defect to the model silently corrupts the measured outcome, while
    attributing it to the runner produces a visible failure someone
    investigates."""
    class Exotic(Exception):
        pass

    assert f.classify(Exotic("?")).origin == f.ORIGIN_RUNNER


def test_no_non_model_fault_is_ever_shown_to_the_model():
    """The safety property. Anything else invites a retry that cannot
    succeed."""
    for exc in (
        OSError("disk"), MemoryError(), RuntimeError("bug"),
        TimeoutError("slow"), KeyError("k"),
    ):
        assert f.observation_for(f.classify(exc)) is None


# --- model faults remain the model's -----------------------------------------


def test_a_model_input_fault_is_reported_back():
    result = f.classify(f.ModelInputFault("lead_id must be an identifier"))
    assert result.origin == f.ORIGIN_MODEL
    assert result.aborts_attempt is False
    assert f.observation_for(result) == (
        "ERROR: lead_id must be an identifier"
    )


def test_only_a_model_fault_lets_the_attempt_continue():
    assert f.classify(f.ModelInputFault("bad")).aborts_attempt is False
    for exc in (f.RunnerFault("x"), f.EnvironmentFault("x"),
                f.ModelTimeout("x")):
        assert f.classify(exc).aborts_attempt is True


def test_budget_exhaustion_is_a_model_outcome_but_not_shown():
    """Spending the budget is part of the task, but there is no turn left in
    which to say so."""
    result = f.classify(f.BudgetExhausted("14 calls used"))
    assert result.origin == f.ORIGIN_MODEL
    assert result.execution_status == f.STATUS_BUDGET_EXHAUSTED
    assert f.observation_for(result) is None


# --- timeout ------------------------------------------------------------------


def test_timeout_is_runner_origin_not_model():
    """A model cannot choose to be faster; recording a timeout against it would
    let a slow host depress a measured score."""
    result = f.classify(TimeoutError("deadline exceeded"))
    assert result.origin == f.ORIGIN_RUNNER
    assert result.execution_status == f.STATUS_TIMEOUT


def test_timeout_is_classified_before_oserror():
    """TimeoutError subclasses OSError, so ordering decides the answer."""
    assert f.classify(TimeoutError()).execution_status == f.STATUS_TIMEOUT
    assert f.classify(OSError()).execution_status == (
        f.STATUS_ENVIRONMENT_UNSTABLE
    )


def test_brick_model_timeout_matches_builtin_classification():
    assert (
        f.classify(f.ModelTimeout("x")).execution_status
        == f.classify(TimeoutError("x")).execution_status
    )


def test_interrupt_is_aborted_not_a_model_error():
    assert f.classify(KeyboardInterrupt()).execution_status == f.STATUS_ABORTED
    assert f.classify(SystemExit()).origin == f.ORIGIN_RUNNER


# --- statuses map onto the S4 evidence vocabulary ----------------------------


def test_statuses_match_the_evidence_store_vocabulary():
    """A classified fault must map onto retained evidence without a second
    translation table."""
    from harness import evidence

    source = evidence.__file__
    with open(source, "r", encoding="utf-8") as handle:
        text = handle.read()
    for status in (
        f.STATUS_DONE, f.STATUS_BUDGET_EXHAUSTED, f.STATUS_MODEL_ERROR,
        f.STATUS_RUNNER_ERROR, f.STATUS_TIMEOUT, f.STATUS_ABORTED,
        f.STATUS_ENVIRONMENT_UNSTABLE,
    ):
        assert '"{}"'.format(status) in text


def test_origins_match_the_evidence_failure_origin_vocabulary():
    from harness import evidence

    with open(evidence.__file__, "r", encoding="utf-8") as handle:
        text = handle.read()
    for origin in (f.ORIGIN_MODEL, f.ORIGIN_RUNNER, f.ORIGIN_ENVIRONMENT):
        assert '"{}"'.format(origin) in text


def test_classification_record_is_serializable():
    record = f.classify(OSError("disk")).as_record()
    assert record["origin"] == f.ORIGIN_ENVIRONMENT
    assert record["exception_type"] == "OSError"
    assert record["model_visible"] is False


# --- explicit context outcomes ------------------------------------------------


def test_short_observation_is_untouched_and_recorded_complete():
    text, outcome = f.truncate_observation("short", 100)
    assert text == "short"
    assert outcome.status == f.CONTEXT_COMPLETE
    assert outcome.was_truncated is False


def test_truncation_tells_the_model_in_band_and_records_it():
    """Silently shortening an observation changes the input without a trace, so
    a reader cannot tell an ignored fact from one never delivered."""
    text, outcome = f.truncate_observation("x" * 500, 100)
    assert text.startswith("x" * 100)
    assert "truncated: 100 of 500 characters" in text
    assert outcome.status == f.CONTEXT_OBSERVATION_TRUNCATED
    assert outcome.original_length == 500
    assert outcome.delivered_length == 100
    assert outcome.was_truncated is True


def test_truncation_boundary_is_exact():
    _, exact = f.truncate_observation("x" * 100, 100)
    _, over = f.truncate_observation("x" * 101, 100)
    assert exact.status == f.CONTEXT_COMPLETE
    assert over.status == f.CONTEXT_OBSERVATION_TRUNCATED


def test_truncation_coerces_non_string_observations():
    text, outcome = f.truncate_observation(12345, 3)
    assert text.startswith("123")
    assert outcome.original_length == 5


@pytest.mark.parametrize("limit", [0, -1, 1.5, "10"])
def test_invalid_truncation_limit_is_refused(limit):
    with pytest.raises(ValueError):
        f.truncate_observation("x", limit)


def test_dropping_history_records_how_many_turns_went():
    kept, outcome = f.drop_history(list(range(10)), 3)
    assert kept == [7, 8, 9]
    assert outcome.status == f.CONTEXT_HISTORY_DROPPED
    assert outcome.dropped_turns == 7
    assert outcome.original_length == 10


def test_history_within_budget_is_complete():
    kept, outcome = f.drop_history([1, 2], 5)
    assert kept == [1, 2]
    assert outcome.status == f.CONTEXT_COMPLETE
    assert outcome.dropped_turns == 0


def test_keeping_zero_turns_is_still_recorded():
    kept, outcome = f.drop_history([1, 2], 0)
    assert kept == []
    assert outcome.dropped_turns == 2


def test_history_arguments_are_validated():
    with pytest.raises(TypeError):
        f.drop_history("abc", 1)
    with pytest.raises(ValueError):
        f.drop_history([1], -1)


def test_unsupported_context_status_is_refused():
    with pytest.raises(ValueError):
        f.ContextOutcome("shrunk", 1, 1)


def test_version_is_pinned():
    assert f.FAULTS_VERSION == "brick.fault-classification/1"
