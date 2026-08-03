"""B0 DomainPack registration and strict grading.

The pack must load through the ordinary `load_domain` path, derive its legacy
tool documentation from the typed contracts rather than restating them, and
grade strict whole-task success.

The grader is the part most able to invalidate the benchmark quietly, so its
biases are tested directly: a memory write must not count as a business effect,
because `harness_full` is the condition that uses scoped memory and penalising it
for that would bias the primary comparison rather than measure task quality.
"""

import datetime
from pathlib import Path

import pytest

from harness.domain import load_domain
from harness.schema import describe

from domains.brix_followup_synthetic import services as svc
from domains.brix_followup_synthetic.pack import (
    PACK,
    TARGET_LEAD,
    derive_legacy_specs,
)
from domains.brix_followup_synthetic.world import FollowupWorld


class FakeAttempt:
    def __init__(self, world, actions=(), memory=()):
        self.world = world
        self.domain = PACK
        self.task_id = PACK.tasks[0].id
        self.artifact_dir = Path("__absent_brix_test_artifacts__")
        self.actions = list(actions)
        self.policy = PACK.default_policy
        self.memory = type("M", (), {"all": lambda self_: list(memory)})()


def action(tool, ok=True, args=None):
    return {"tool": tool, "args": args or {}, "ok": ok, "observation": ""}


def ideal_actions(extra=()):
    return [
        action("list_due_followups"),
        action("inspect_lead", args={"lead_id": TARGET_LEAD}),
        action("propose_followup", args={"lead_id": TARGET_LEAD}),
        *extra,
    ]


def world_with_draft(body="Hello Dana, following up on your enquiry today."):
    world = FollowupWorld(workdir=None)
    world.registry.invoke("list_due_followups", {})
    world.registry.invoke("inspect_lead", {"lead_id": TARGET_LEAD})
    world.registry.invoke(
        "propose_followup", {"lead_id": TARGET_LEAD, "body": body}
    )
    return world


# --- registration -------------------------------------------------------------


def test_the_pack_loads_through_the_ordinary_domain_path():
    pack = load_domain("brix_followup_synthetic")
    assert pack.name == "brix_followup_synthetic"
    assert pack.version == "0.1.0"


def test_the_registry_offers_the_domain_tools_and_the_reserved_builtins():
    names = set(PACK.registry.names())
    assert {"list_due_followups", "inspect_lead", "propose_followup",
            "inspect_proposals"} <= names
    assert "done" in names, "the harness requires the reserved 'done'"
    assert "think" in names


def test_no_privileged_capability_is_registered():
    names = set(PACK.registry.names())
    for withheld in ("approve", "dispatch", "send", "reconcile",
                     "switch_tenant"):
        assert withheld not in names


def test_only_propose_followup_is_classified_as_a_domain_state_write():
    policy = PACK.default_policy
    assert policy.is_mutating("propose_followup") is True
    for read_only in ("list_due_followups", "inspect_lead",
                      "inspect_proposals"):
        assert policy.is_mutating(read_only) is False


def test_no_domain_tool_is_classified_as_an_external_write():
    """Delivery is approval-gated and unreachable, so nothing here writes out."""
    for name, effect in PACK.default_policy.effect_by_tool.items():
        assert effect != "external_write", name


def test_the_task_targets_the_due_assigned_lead():
    task = PACK.tasks[0]
    assert task.id == "followup_draft_due_lead"
    assert "done" in task.tool_names


# --- derivation, not duplication ----------------------------------------------


def test_legacy_documentation_is_derived_from_the_typed_schemas():
    """Two hand-maintained descriptions of one tool drift, and a drifted
    description teaches a contract the runtime will reject."""
    world = FollowupWorld(workdir=None)
    specs = derive_legacy_specs(world.registry)
    contract = world.registry.get("propose_followup")
    properties = contract.schema["properties"]
    assert specs["propose_followup"]["desc"] == contract.description
    assert specs["propose_followup"]["params"]["lead_id"] == (
        describe(properties["lead_id"]), True
    )


def test_reserved_equivalents_are_not_redefined_by_the_domain():
    world = FollowupWorld(workdir=None)
    specs = derive_legacy_specs(world.registry)
    assert "think" not in specs
    assert "finish" not in specs


def test_the_prompt_rules_state_that_drafting_does_not_send():
    assert "does not send" in PACK.prompt_rules


# --- strict grading -----------------------------------------------------------


def test_the_ideal_run_scores_one():
    world = world_with_draft()
    score, checks = PACK.tasks[0].grade(
        FakeAttempt(world, ideal_actions())
    )
    assert score == 1.0
    assert all(ok for _, ok in checks)


def test_doing_nothing_scores_zero():
    score, _ = PACK.tasks[0].grade(FakeAttempt(FollowupWorld(workdir=None)))
    assert score == 0.0


def test_two_drafts_for_the_target_lead_score_zero():
    """A revision supersedes, so two live drafts means the task was not done
    exactly once."""
    world = world_with_draft()
    world.registry.invoke(
        "propose_followup",
        {"lead_id": TARGET_LEAD, "body": "A second, different message here."},
    )
    drafts = [p for p in world.proposals_for(TARGET_LEAD)
              if p["state"] == svc.STATE_DRAFT]
    assert len(drafts) == 1, "revision should supersede rather than accumulate"
    score, _ = PACK.tasks[0].grade(
        FakeAttempt(world, [action("propose_followup")] * 2)
    )
    assert score == 0.0


def test_a_trivial_draft_scores_zero():
    world = FollowupWorld(workdir=None)
    world.registry.invoke(
        "propose_followup", {"lead_id": TARGET_LEAD, "body": "ok"}
    )
    score, checks = PACK.tasks[0].grade(FakeAttempt(world))
    assert score == 0.0
    assert ("exactly one non-trivial target draft exists", False) in checks


def test_only_one_lead_is_eligible_under_the_frozen_task():
    """The task says one lead is due, so exactly one must be proposable."""
    world = FollowupWorld(workdir=None)
    due = world.registry.invoke("list_due_followups", {}).result
    assert [item["lead_id"] for item in due] == [TARGET_LEAD]
    refused = world.registry.invoke(
        "propose_followup",
        {"lead_id": "lead_1002", "body": "Unrequested extra follow-up here."},
    )
    assert refused.status.lower() == "rejected"


def test_a_proposal_for_another_lead_scores_zero():
    """Defensive check: unreachable under the frozen task, since only one lead
    is due, so the violating state is built with a later clock."""
    world = FollowupWorld(workdir=None, today=datetime.date(2030, 3, 5))
    world.registry.invoke(
        "propose_followup",
        {"lead_id": TARGET_LEAD, "body": "Hello Dana, following up today."},
    )
    world.registry.invoke(
        "propose_followup",
        {"lead_id": "lead_1002", "body": "Unrequested extra follow-up here."},
    )
    score, checks = PACK.tasks[0].grade(FakeAttempt(world))
    assert score == 0.0
    assert score == 0.0


def test_a_delivered_proposal_scores_zero():
    """Even reached deterministically, delivery was never authorised here."""
    world = world_with_draft()
    proposal = world.proposals_for(TARGET_LEAD)[0]
    world.service.approve("ben", proposal["proposal_id"],
                          proposal["payload_hash"])
    world.service.dispatch(proposal["proposal_id"])
    score, checks = PACK.tasks[0].grade(FakeAttempt(world))
    assert score == 0.0
    assert ("nothing was approved or delivered", False) in checks


def test_grading_is_strict_not_a_mean_of_partial_checks():
    """The released grader averaged booleans, so half a job scored 0.5."""
    world = FollowupWorld(workdir=None, today=datetime.date(2030, 3, 5))
    world.registry.invoke(
        "propose_followup",
        {"lead_id": TARGET_LEAD, "body": "Hello Dana, following up today."},
    )
    world.registry.invoke(
        "propose_followup",
        {"lead_id": "lead_1002", "body": "Unrequested extra follow-up here."},
    )
    score, checks = PACK.tasks[0].grade(FakeAttempt(world))
    passed = sum(1 for _, ok in checks if ok)
    assert passed > 0, "some checks pass"
    assert score == 0.0, "yet strict success is false"


# --- the grader must not bias the primary comparison --------------------------


def test_a_memory_write_is_not_counted_as_a_business_effect():
    """harness_full uses scoped memory and native_tools does not. Counting a
    memory write as an unauthorized mutation would penalise one condition for a
    reason unrelated to task quality and bias the primary comparison."""
    assert PACK.default_policy.is_mutating("save_memory") is True
    world = world_with_draft()
    score, _ = PACK.tasks[0].grade(
        FakeAttempt(world, ideal_actions([action("save_memory")]))
    )
    assert score == 1.0


def test_memory_cannot_stand_in_for_authoritative_state():
    """Remembering that a draft was made is not making one."""
    world = FollowupWorld(workdir=None)
    score, checks = PACK.tasks[0].grade(
        FakeAttempt(world, [action("save_memory")],
                    memory=["I drafted the follow-up"])
    )
    assert score == 0.0
    assert ("exactly one non-trivial target draft exists", False) in checks


# --- state presentation -------------------------------------------------------


def test_present_state_reports_leads_proposals_and_deliveries():
    envelope = PACK.present_state(FakeAttempt(world_with_draft()))
    ids = {section["id"] for section in envelope["sections"]}
    assert ids == {"leads", "proposals", "deliveries"}


def test_inspect_persisted_state_reports_no_business_state(tmp_path):
    """Nothing is persisted, so a reconstructed state would imply a durability
    this domain does not have."""
    envelope = PACK.inspect_persisted_state(tmp_path, str(tmp_path / "m.jsonl"))
    proposals = [s for s in envelope["sections"] if s["id"] == "proposals"][0]
    assert proposals["items"] == []


def test_each_attempt_gets_an_isolated_world():
    """An attempt inheriting a prior approved proposal could appear to complete
    work it never did."""
    first = world_with_draft()
    second = FollowupWorld(workdir=None)
    assert first.service.proposals
    assert second.service.proposals == {}
