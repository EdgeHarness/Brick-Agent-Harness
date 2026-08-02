"""S1R typed contracts and the fail-closed executor.

This is where the S1R pieces compose. The gate ordering is load-bearing:
semantic invariants run only after schema validation, so an invariant may assume
shape and check meaning. The failure asymmetry is the point -- a model fault
costs a turn, while a runner or environment fault aborts and is never shown to
the model, because the released executor showed them and a model retrying a
disk-full error burns budget on something it cannot fix.
"""

import pytest

from harness import faults
from harness.typed_executor import (
    ContractError,
    ExecutionOutcome,
    ToolContract,
    TypedToolRegistry,
)


BOOKING = {
    "type": "object",
    "properties": {
        "start": {"type": "string", "format": "time"},
        "end": {"type": "string", "format": "time"},
        "lead_id": {"type": "string", "format": "identifier"},
    },
    "required": ["start", "end", "lead_id"],
}


def end_after_start(args):
    """A deterministic cross-field rule JSON Schema cannot express."""
    if args["end"] <= args["start"]:
        return ["end must be later than start"]
    return []


def make_registry(executor=None, invariants=(end_after_start,),
                  mutating=True, alias_table=None):
    calls = []

    def default(context, args):
        calls.append(args)
        return "booked"

    contract = ToolContract(
        "book_slot", "Book a slot.", BOOKING, executor or default,
        mutating=mutating, invariants=invariants,
    )
    registry = TypedToolRegistry([contract], alias_table=alias_table)
    return registry, calls


GOOD = {"start": "09:00", "end": "10:00", "lead_id": "lead_1"}


# --- the happy path ----------------------------------------------------------


def test_a_valid_call_executes():
    registry, calls = make_registry()
    outcome = registry.invoke("book_slot", GOOD)
    assert outcome.ok
    assert outcome.result == "booked"
    assert calls == [GOOD]


def test_the_executor_cannot_mutate_the_caller_arguments():
    def mutator(context, args):
        args["start"] = "tampered"
        return "ok"

    registry, _ = make_registry(executor=mutator)
    original = dict(GOOD)
    registry.invoke("book_slot", original)
    assert original == GOOD


# --- gate 1: unknown tool ----------------------------------------------------


def test_an_unknown_tool_is_a_model_fault_that_does_not_abort():
    registry, _ = make_registry()
    outcome = registry.invoke("nope", {})
    assert outcome.status == ExecutionOutcome.REJECTED
    assert outcome.aborts_attempt is False
    assert "unknown tool" in outcome.observation


# --- gate 2: alias repair, never inference -----------------------------------

def test_a_global_alias_never_repairs_a_mutating_argument():
    registry, calls = make_registry(
        alias_table={parsingscope(): {"id": "lead_id"}}
    )
    outcome = registry.invoke(
        "book_slot", {"start": "09:00", "end": "10:00", "id": "lead_1"}
    )
    assert outcome.status == ExecutionOutcome.REJECTED
    assert calls == []


def parsingscope():
    from harness import parsing

    return parsing.GLOBAL_SCOPE


def test_a_tool_scoped_alias_is_applied():
    registry, calls = make_registry(
        alias_table={"book_slot": {"id": "lead_id"}}
    )
    outcome = registry.invoke(
        "book_slot", {"start": "09:00", "end": "10:00", "id": "lead_1"}
    )
    assert outcome.ok
    assert outcome.repairs == ("renamed 'id' -> 'lead_id'",)


# --- gate 3: schema validation ------------------------------------------------


def test_a_structurally_invalid_call_is_rejected_before_execution():
    registry, calls = make_registry()
    outcome = registry.invoke(
        "book_slot", {"start": "09:00", "end": "25:00", "lead_id": "lead_1"}
    )
    assert outcome.status == ExecutionOutcome.REJECTED
    assert calls == []
    assert any("ISO-8601 time" in problem for problem in outcome.problems)


def test_every_schema_problem_is_reported_in_one_exchange():
    registry, _ = make_registry()
    outcome = registry.invoke("book_slot", {"start": 9, "end": "25:00"})
    assert len(outcome.problems) >= 3


def test_an_unknown_argument_is_rejected_not_dropped():
    registry, calls = make_registry()
    outcome = registry.invoke("book_slot", dict(GOOD, confirm=False))
    assert outcome.status == ExecutionOutcome.REJECTED
    assert calls == []


# --- gate 4: semantic invariants ---------------------------------------------


def test_a_structurally_valid_but_semantically_wrong_call_is_rejected():
    """Structural validity is not semantic validity."""
    registry, calls = make_registry()
    outcome = registry.invoke(
        "book_slot", {"start": "10:00", "end": "09:00", "lead_id": "lead_1"}
    )
    assert outcome.status == ExecutionOutcome.REJECTED
    assert outcome.problems == ("end must be later than start",)
    assert calls == []


def test_invariants_run_only_after_the_schema_passes():
    """An invariant may assume shape, so it must never see a malformed value."""
    seen = []

    def fragile(args):
        seen.append(args)
        return [] if args["end"] > args["start"] else ["bad order"]

    registry, _ = make_registry(invariants=(fragile,))
    registry.invoke("book_slot", {"start": 9})  # missing keys, wrong type
    assert seen == [], "invariant ran against an unvalidated value"


def test_multiple_invariants_all_report():
    registry, _ = make_registry(
        invariants=(lambda a: ["first"], lambda a: ["second"])
    )
    outcome = registry.invoke("book_slot", GOOD)
    assert outcome.problems == ("first", "second")


def test_an_invariant_may_return_a_bare_string():
    registry, _ = make_registry(invariants=(lambda a: "single problem",))
    assert registry.invoke("book_slot", GOOD).problems == ("single problem",)


def test_an_invariant_returning_none_passes():
    registry, _ = make_registry(invariants=(lambda a: None,))
    assert registry.invoke("book_slot", GOOD).ok


def test_a_raising_invariant_is_a_runner_fault_not_a_model_rejection():
    """A broken invariant is our defect. Telling the model to fix it would
    charge a model failure for a harness bug."""
    def broken(args):
        raise ZeroDivisionError("bad rule")

    registry, calls = make_registry(invariants=(broken,))
    outcome = registry.invoke("book_slot", GOOD)
    assert outcome.status == ExecutionOutcome.FAILED
    assert outcome.aborts_attempt is True
    assert outcome.fault.origin == faults.ORIGIN_RUNNER
    assert outcome.observation is None
    assert calls == []


def test_an_invariant_returning_the_wrong_type_is_a_runner_fault():
    registry, _ = make_registry(invariants=(lambda a: 42,))
    outcome = registry.invoke("book_slot", GOOD)
    assert outcome.status == ExecutionOutcome.FAILED
    assert outcome.fault.origin == faults.ORIGIN_RUNNER


# --- gate 5: execution faults keep their axis --------------------------------


@pytest.mark.parametrize(
    "exc,origin",
    [
        (OSError("no space left on device"), faults.ORIGIN_ENVIRONMENT),
        (MemoryError(), faults.ORIGIN_ENVIRONMENT),
        (RuntimeError("harness bug"), faults.ORIGIN_RUNNER),
        (KeyError("internal"), faults.ORIGIN_RUNNER),
        (TimeoutError("slow"), faults.ORIGIN_RUNNER),
    ],
)
def test_a_non_model_fault_aborts_and_is_never_shown_to_the_model(exc, origin):
    """The released executor handed all of these to the model as ERROR: ...,
    which it then retried."""
    def failing(context, args):
        raise exc

    registry, _ = make_registry(executor=failing)
    outcome = registry.invoke("book_slot", GOOD)
    assert outcome.status == ExecutionOutcome.FAILED
    assert outcome.aborts_attempt is True
    assert outcome.fault.origin == origin
    assert outcome.observation is None


def test_a_tool_raising_a_model_input_fault_is_reported_and_continues():
    def refusing(context, args):
        raise faults.ModelInputFault("that slot is already taken")

    registry, _ = make_registry(executor=refusing)
    outcome = registry.invoke("book_slot", GOOD)
    assert outcome.status == ExecutionOutcome.REJECTED
    assert outcome.aborts_attempt is False
    assert "already taken" in outcome.observation


def test_outcome_record_is_serializable():
    registry, _ = make_registry()
    record = registry.invoke("book_slot", {"start": "10:00", "end": "09:00",
                                           "lead_id": "lead_1"}).as_record()
    assert record["status"] == ExecutionOutcome.REJECTED
    assert record["problems"] == ["end must be later than start"]
    assert record["fault"]["origin"] == faults.ORIGIN_MODEL


# --- derivation and contract validation --------------------------------------


def test_native_schemas_and_prompt_docs_derive_from_the_contracts():
    registry, _ = make_registry()
    native = registry.native_schemas()
    assert native[0]["function"]["name"] == "book_slot"
    assert native[0]["function"]["parameters"]["additionalProperties"] is False
    assert "book_slot (" not in registry.prompt_docs()
    assert "- book_slot: Book a slot." in registry.prompt_docs()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": ""},
        {"description": ""},
        {"schema": {"type": "string"}},
        {"executor": "not callable"},
        {"mutating": "yes"},
        {"invariants": ("not callable",)},
    ],
)
def test_a_malformed_contract_fails_loudly(kwargs):
    base = dict(
        name="t", description="d", schema=BOOKING,
        executor=lambda c, a: None, mutating=False, invariants=(),
    )
    base.update(kwargs)
    with pytest.raises((ContractError, Exception)):
        ToolContract(**base)


def test_duplicate_registration_is_refused():
    registry, _ = make_registry()
    duplicate = ToolContract(
        "book_slot", "d", BOOKING, lambda c, a: None
    )
    with pytest.raises(ContractError):
        registry.register(duplicate)


def test_a_malformed_alias_table_is_refused_at_construction():
    from harness import parsing

    with pytest.raises(parsing.AliasTableError):
        TypedToolRegistry([], alias_table={"t": {"a": "a"}})
