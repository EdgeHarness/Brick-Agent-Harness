"""S1R fail-closed completion.

The released loop read a model verifier's self-assessment with
``verdict.get("complete", True)``. Every degenerate case therefore resolved to
*complete*: a malformed verdict, a missing key, a timed-out verifier, a verifier
that ran out of budget. The situation where a task is most likely unfinished --
the verifier could not answer -- was scored as finished.

These tests pin the inversion: authoritative postconditions decide, a model
verifier may only explain, and every degenerate path yields UNKNOWN rather than
COMPLETE.
"""

import pytest

from harness import completion as c


def sat(missing=(), detail=None):
    return c.PostconditionResult(True, missing, detail)


def unsat(missing=("draft not created",)):
    return c.PostconditionResult(False, missing)


def unavailable(detail="state unreadable"):
    return c.PostconditionResult(None, (), detail)


# --- the released fail-open behaviour is gone -------------------------------


@pytest.mark.parametrize(
    "verdict",
    [
        None,
        {},
        {"complete": "yes"},
        {"complete": None},
        {"complete": 1},
        {"missing": "something"},
        "not a mapping",
        [],
    ],
)
def test_a_degenerate_verdict_never_establishes_completion(verdict):
    """`verdict.get("complete", True)` turned every one of these into done."""
    assert c.decide(unsat(), verdict).status == c.INCOMPLETE
    assert c.decide(None, verdict).status == c.UNKNOWN


def test_a_verifier_cannot_authorize_completion_the_state_does_not_support():
    decision = c.decide(unsat(), {"complete": True})
    assert decision.status == c.INCOMPLETE
    assert decision.verifier_contradicted is True
    assert decision.missing == ("draft not created",)


def test_state_is_authoritative_when_the_verifier_disagrees_downward():
    """An unreliable verifier must not veto real evidence and manufacture a
    false negative."""
    decision = c.decide(sat(), {"complete": False, "missing": "unsure"})
    assert decision.status == c.COMPLETE
    assert decision.verifier_contradicted is True
    assert decision.verifier_note == "unsure"


def test_satisfied_postconditions_complete_without_any_verifier():
    decision = c.decide(sat())
    assert decision.status == c.COMPLETE
    assert decision.reason == c.REASON_POSTCONDITIONS_SATISFIED
    assert decision.verifier_contradicted is False


# --- UNKNOWN is distinct from INCOMPLETE ------------------------------------


def test_absent_postconditions_are_unknown_not_complete_and_not_incomplete():
    decision = c.decide(None)
    assert decision.status == c.UNKNOWN
    assert decision.reason == c.REASON_POSTCONDITIONS_UNAVAILABLE
    assert decision.is_complete is False


def test_unreadable_state_is_unknown():
    decision = c.decide(unavailable())
    assert decision.status == c.UNKNOWN
    assert decision.reason == c.REASON_POSTCONDITIONS_UNAVAILABLE


def test_malformed_postcondition_object_is_unknown():
    decision = c.decide({"satisfied": True})
    assert decision.status == c.UNKNOWN
    assert decision.reason == c.REASON_POSTCONDITION_MALFORMED


def test_unknown_is_never_treated_as_done():
    for decision in (
        c.decide(None),
        c.decide(unavailable()),
        c.decide({"satisfied": True}),
    ):
        assert decision.is_complete is False


def test_unknown_is_not_silently_folded_into_incomplete():
    """Keeping the axes separate is what stops an instrument failure from being
    recorded as a model failure."""
    assert c.decide(None).status != c.INCOMPLETE
    assert c.decide(unsat()).status == c.INCOMPLETE


# --- a broken checker is an instrument fault, not a model outcome -----------


def test_a_raising_postcondition_check_yields_unknown_not_a_crash():
    def boom():
        raise RuntimeError("state store offline")

    decision = c.evaluate(boom)
    assert decision.status == c.UNKNOWN
    assert decision.reason == c.REASON_POSTCONDITION_ERROR
    assert "state store offline" in decision.verifier_note


def test_a_check_returning_the_wrong_type_yields_unknown():
    assert c.evaluate(lambda: True).status == c.UNKNOWN
    assert c.evaluate(lambda: None).status == c.UNKNOWN


def test_absent_check_yields_unknown():
    assert c.evaluate(None).status == c.UNKNOWN


def test_evaluate_passes_through_a_satisfied_result():
    assert c.evaluate(lambda: sat()).status == c.COMPLETE


def test_a_raising_check_still_records_a_contradicting_verifier():
    def boom():
        raise RuntimeError("offline")

    assert c.evaluate(boom, {"complete": True}).verifier_contradicted is True


# --- the timed-out and budget-starved verifier cases ------------------------


def test_timed_out_verifier_over_unsatisfied_state_is_incomplete():
    """A timeout produces no verdict at all; state still decides."""
    assert c.decide(unsat(), None).status == c.INCOMPLETE


def test_timed_out_verifier_with_no_state_check_is_unknown():
    assert c.decide(None, None).status == c.UNKNOWN


def test_budget_starved_verifier_cannot_complete_an_unfinished_task():
    """No verdict because the ledger was exhausted mid-attempt."""
    decision = c.decide(unsat(missing=("no draft", "no approval")), None)
    assert decision.status == c.INCOMPLETE
    assert decision.missing == ("no draft", "no approval")


# --- verdict interpretation --------------------------------------------------


@pytest.mark.parametrize(
    "verdict,expected",
    [
        ({"complete": True}, True),
        ({"complete": False}, False),
        ({"complete": "true"}, None),
        ({}, None),
        (None, None),
        ("nope", None),
    ],
)
def test_read_verifier_claim_is_tri_state(verdict, expected):
    assert c.read_verifier_claim(verdict)[0] is expected


def test_blank_verifier_note_is_dropped():
    assert c.read_verifier_claim({"complete": False, "missing": "   "})[1] is None


# --- record shape ------------------------------------------------------------


def test_decision_record_is_serializable_and_complete():
    record = c.decide(unsat(), {"complete": True}).as_record()
    assert record["schema_version"] == c.COMPLETION_VERSION
    assert record["status"] == c.INCOMPLETE
    assert record["missing"] == ["draft not created"]
    assert record["verifier_contradicted"] is True


def test_postcondition_result_validates_its_own_arguments():
    with pytest.raises(TypeError):
        c.PostconditionResult("yes")
    with pytest.raises(TypeError):
        c.PostconditionResult(True, "not a sequence")
    with pytest.raises(TypeError):
        c.PostconditionResult(True, [""])


def test_unsupported_status_is_refused():
    with pytest.raises(ValueError):
        c.CompletionDecision("finished", "reason")


def test_version_is_pinned():
    assert c.COMPLETION_VERSION == "brick.completion/1"
