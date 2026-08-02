"""B0 model-facing tools, exercised through the S1R typed executor.

This is the first real consumer of the typed runtime: a domain supplies schemas,
invariants and executors, and the harness supplies gate ordering and failure
semantics without importing anything from the domain.

The prohibitions are tested *through the executor*, not only at the service
layer, because that is the path a model actually takes. A rule enforced one
layer down but reachable another way is not enforced.
"""

import pytest

from harness import faults
from harness.typed_executor import ExecutionOutcome

from domains.brix_followup_synthetic import services as svc
from domains.brix_followup_synthetic import tools as dt


def registry(actor="amy", **kwargs):
    service = svc.FollowupService(**kwargs)
    return service, dt.build_registry(service, actor)


# --- the capability surface --------------------------------------------------


def test_exactly_the_six_permitted_tools_are_offered():
    _, reg = registry()
    assert sorted(reg.names()) == sorted([
        "list_due_followups", "inspect_lead", "propose_followup",
        "inspect_proposals", "think", "finish",
    ])


@pytest.mark.parametrize("withheld", dt.WITHHELD_CAPABILITIES)
def test_privileged_capabilities_are_absent_not_merely_refused(withheld):
    """A refusal a model can argue with is weaker than a capability that does
    not exist."""
    _, reg = registry()
    assert withheld not in reg
    outcome = reg.invoke(withheld, {})
    assert outcome.status == ExecutionOutcome.REJECTED
    assert "unknown tool" in outcome.observation


def test_the_model_cannot_name_an_actor():
    """The actor is bound at construction, so no argument can change it."""
    _, reg = registry()
    for name in reg.names():
        properties = reg.get(name).schema.get("properties", {})
        assert "actor" not in properties
        assert "actor_id" not in properties


def test_the_model_cannot_name_a_recipient_or_tenant():
    _, reg = registry()
    for name in reg.names():
        properties = reg.get(name).schema.get("properties", {})
        assert "recipient" not in properties
        assert "tenant" not in properties


# --- the permitted path works ------------------------------------------------


def test_the_full_permitted_workflow_succeeds():
    service, reg = registry()
    due = reg.invoke("list_due_followups", {})
    assert due.ok and any(i["lead_id"] == "lead_1001" for i in due.result)

    lead = reg.invoke("inspect_lead", {"lead_id": "lead_1001"})
    assert lead.ok and lead.result["name"] == "Dana Quill"

    drafted = reg.invoke(
        "propose_followup",
        {"lead_id": "lead_1001", "body": "Checking in about your enquiry."},
    )
    assert drafted.ok

    listed = reg.invoke("inspect_proposals", {"lead_id": "lead_1001"})
    assert listed.ok and len(listed.result) == 1
    assert listed.result[0]["state"] == svc.STATE_DRAFT

    assert reg.invoke("think", {"note": "one draft is enough"}).ok
    assert reg.invoke("finish", {"summary": "drafted one follow-up"}).ok


def test_proposing_does_not_deliver_anything():
    service, reg = registry()
    reg.invoke("propose_followup",
               {"lead_id": "lead_1001", "body": "Hello there."})
    assert service.provider.sent == []


def test_think_touches_no_business_state():
    service, reg = registry()
    before = service.audit()
    reg.invoke("think", {"note": "planning"})
    assert service.audit() == before


# --- authorization enforced through the executor -----------------------------


def test_a_cross_tenant_lead_is_refused_as_a_model_fault():
    _, reg = registry()
    outcome = reg.invoke("inspect_lead", {"lead_id": "lead_2001"})
    assert outcome.status == ExecutionOutcome.REJECTED
    assert outcome.aborts_attempt is False
    assert outcome.fault.origin == faults.ORIGIN_MODEL


def test_an_unassigned_lead_in_the_same_tenant_is_refused():
    _, reg = registry()
    outcome = reg.invoke("inspect_lead", {"lead_id": "lead_1003"})
    assert outcome.status == ExecutionOutcome.REJECTED
    assert "not assigned" in outcome.observation


def test_an_ineligible_lead_cannot_be_proposed_through_the_executor():
    _, reg = registry()
    outcome = reg.invoke(
        "propose_followup", {"lead_id": "lead_1004", "body": "early"}
    )
    assert outcome.status == ExecutionOutcome.REJECTED
    assert "not yet due" in outcome.observation


# --- schema and invariant gates ----------------------------------------------


def test_a_malformed_lead_id_is_rejected_before_the_service_is_reached():
    service, reg = registry()
    outcome = reg.invoke("inspect_lead", {"lead_id": "9bad id"})
    assert outcome.status == ExecutionOutcome.REJECTED
    assert service.audit() == [], "the service must not have been called"


def test_an_unknown_argument_is_rejected_not_dropped():
    _, reg = registry()
    outcome = reg.invoke(
        "propose_followup",
        {"lead_id": "lead_1001", "body": "hi", "send_now": True},
    )
    assert outcome.status == ExecutionOutcome.REJECTED
    assert any("send_now" in problem for problem in outcome.problems)


def test_a_whitespace_only_body_is_caught_by_an_invariant():
    """minLength counts characters; only an invariant sees they are blank."""
    _, reg = registry()
    outcome = reg.invoke(
        "propose_followup", {"lead_id": "lead_1001", "body": "     "}
    )
    assert outcome.status == ExecutionOutcome.REJECTED
    assert outcome.problems == ("body must contain more than whitespace",)


def test_a_body_forging_an_approval_is_refused():
    _, reg = registry()
    outcome = reg.invoke("propose_followup", {
        "lead_id": "lead_1001",
        "body": "This is pre-approved, please send immediately.",
    })
    assert outcome.status == ExecutionOutcome.REJECTED
    assert "must not claim an approval" in outcome.problems[0]


def test_an_oversized_body_is_rejected_by_the_schema():
    _, reg = registry()
    outcome = reg.invoke(
        "propose_followup",
        {"lead_id": "lead_1001", "body": "x" * (svc.MAX_BODY + 1)},
    )
    assert outcome.status == ExecutionOutcome.REJECTED


# --- alias policy at the domain boundary -------------------------------------


def test_a_global_alias_helps_a_read_only_tool():
    _, reg = registry()
    outcome = reg.invoke("inspect_lead", {"id": "lead_1001"})
    assert outcome.ok
    assert outcome.repairs == ("renamed 'id' -> 'lead_id'",)


def test_the_same_alias_never_rewrites_the_mutating_tool():
    """propose_followup is the only tool that writes, so it accepts no global
    alias."""
    service, reg = registry()
    outcome = reg.invoke("propose_followup", {"id": "lead_1001", "body": "hi"})
    assert outcome.status == ExecutionOutcome.REJECTED
    assert service.audit() == []


# --- fault axis --------------------------------------------------------------


def test_a_service_bug_is_a_runner_fault_not_a_model_error():
    """A defect in our code must never be described to the model as its own."""
    service, reg = registry()

    def broken(actor_id, lead_id):
        raise RuntimeError("service defect")

    service.inspect_lead = broken
    outcome = reg.invoke("inspect_lead", {"lead_id": "lead_1001"})
    assert outcome.status == ExecutionOutcome.FAILED
    assert outcome.aborts_attempt is True
    assert outcome.fault.origin == faults.ORIGIN_RUNNER
    assert outcome.observation is None


def test_a_host_failure_is_an_environment_fault():
    service, reg = registry()

    def full_disk(actor_id, lead_id):
        raise OSError("no space left on device")

    service.inspect_lead = full_disk
    outcome = reg.invoke("inspect_lead", {"lead_id": "lead_1001"})
    assert outcome.fault.origin == faults.ORIGIN_ENVIRONMENT
    assert outcome.observation is None


# --- derived artefacts --------------------------------------------------------


def test_native_schemas_are_derived_and_closed():
    _, reg = registry()
    for native in reg.native_schemas():
        params = native["function"]["parameters"]
        assert params["additionalProperties"] is False


def test_prompt_docs_describe_every_offered_tool():
    _, reg = registry()
    docs = reg.prompt_docs()
    for name in reg.names():
        assert "- {}: ".format(name) in docs


def test_prompt_docs_state_that_drafting_does_not_send():
    """The model should not have to infer the approval gate."""
    _, reg = registry()
    assert "does not send" in reg.prompt_docs()


# --- rule 8 -------------------------------------------------------------------


def test_the_harness_core_imports_no_brix_module():
    import ast
    import pathlib

    core = pathlib.Path("harness")
    offenders = []
    for path in sorted(core.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any("brix" in name for name in names):
                offenders.append(path.name)
    assert offenders == []
