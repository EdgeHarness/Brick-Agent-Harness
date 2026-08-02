"""DomainPack registration for the synthetic lead-follow-up slice (B0).

The legacy `ToolRegistry` the `DomainPack` contract expects is **derived** from
the typed `ToolContract`s rather than written a second time. Two hand-maintained
descriptions of one tool drift, and a drifted description teaches the model a
contract the runtime will reject -- the same failure the S1R schema layer exists
to prevent, reappearing one layer up.

Grading is strict whole-task success, not a mean of partial checks. The released
grader averaged a variable list of booleans, so a run that did half the job
scored 0.5 and a run that did the wrong thing could still score above zero. Here
a single unauthorized or missing effect makes the task false.
"""

import datetime

from harness.builtin_tools import BUILTIN_EFFECTS, builtin_specs
from harness.domain import (
    DomainPack,
    GENERIC_PROMPT_PROFILE,
    TaskSpec,
    state_envelope,
)
from harness.errors import ToolError
from harness.runtime import ActionPolicy
from harness.schema import describe
from harness.tools import ToolRegistry

from domains.brix_followup_synthetic import services as svc
from domains.brix_followup_synthetic import tools as domain_tools
from domains.brix_followup_synthetic.world import FollowupWorld


DOMAIN_NAME = "brix_followup_synthetic"
DOMAIN_VERSION = "0.1.0"

# The lead the frozen task targets: assigned to amy, open, and due on `today`.
TARGET_LEAD = "lead_1001"

# Harness-level scratch. Writing a note is not a business effect.
MEMORY_TOOLS = frozenset({"save_memory"})

_EXAMPLES = {
    "list_due_followups": {},
    "inspect_lead": {"lead_id": TARGET_LEAD},
    "propose_followup": {
        "lead_id": TARGET_LEAD,
        "body": "Hello Dana, following up on your enquiry.",
    },
    "inspect_proposals": {"lead_id": TARGET_LEAD},
    "think": {"note": "One draft is enough."},
    "finish": {"summary": "Drafted one follow-up."},
}

# Only propose_followup writes. Everything else reads, and nothing in this
# domain may write externally: delivery is approval-gated and unreachable.
_EFFECTS = {
    "list_due_followups": "read",
    "inspect_lead": "read",
    "propose_followup": "state_write",
    "inspect_proposals": "read",
}
# `think` and `done` are classified by BUILTIN_EFFECTS when the builtins are
# merged below; classifying them here too would double-declare them.


def _runner(name):
    """Bridge one typed contract into the legacy executor signature."""

    def run(attempt, args):
        outcome = attempt.world.registry.invoke(name, args)
        if outcome.ok:
            return outcome.result
        if outcome.aborts_attempt:
            # A runner or environment fault must not become a ToolError, which
            # the legacy loop would hand back to the model as its own mistake.
            raise RuntimeError(
                outcome.fault.message if outcome.fault else "tool failed"
            )
        raise ToolError(
            (outcome.observation or "call rejected").replace("ERROR: ", "", 1)
        )

    return run


# The harness reserves `think` and `done` and supplies both. A domain may not
# redefine them, so the typed registry's own `think` and `finish` are not
# derived into the legacy registry: the reserved `think` and `done` are the same
# capabilities at the harness layer. The typed registry keeps its pair because
# that is the domain's complete contract for the S1R-native path.
RESERVED_EQUIVALENTS = {"think": "think", "finish": "done"}


def derive_legacy_specs(registry):
    """Derive legacy specs from typed contracts. One source of truth."""
    specs = {}
    for name in registry.names():
        if name in RESERVED_EQUIVALENTS:
            continue
        contract = registry.get(name)
        properties = contract.schema.get("properties", {})
        required = set(contract.schema.get("required", []))
        specs[name] = {
            "desc": contract.description,
            "params": {
                prop: (describe(properties[prop]), prop in required)
                for prop in sorted(properties)
            },
            "example": {"tool": name, "args": _EXAMPLES.get(name, {})},
            "run": _runner(name),
            "suppress_identical_repeats": name != "think",
        }
    return specs


_TEMPLATE_WORLD = FollowupWorld(workdir=None)
_specs = derive_legacy_specs(_TEMPLATE_WORLD.registry)
_effects = dict(_EFFECTS)
# Builtins arrive last so a domain tool can never be silently shadowed.
for builtin_name, builtin_spec in builtin_specs().items():
    if builtin_name not in _specs:
        _specs[builtin_name] = builtin_spec
        _effects[builtin_name] = BUILTIN_EFFECTS[builtin_name]


def _make_world(workdir, persistent=False):
    return FollowupWorld(workdir, persistent=persistent)


def _snapshot(attempt):
    attempt.world.snapshot(attempt.actions)


def _prepare_attempt(attempt):
    return None


def _normalize_args(name, args, today):
    return args


def _sections(world):
    leads = [
        {"lead_id": lead_id, "name": lead["name"], "due": lead["due"],
         "status": lead["status"]}
        for lead_id, lead in sorted(world.service.leads.items())
        if lead["assigned_to"] == world.actor
    ]
    proposals = [
        {"proposal_id": pid, "lead_id": p["lead_id"], "state": p["state"],
         "version": p["version"]}
        for pid, p in sorted(world.service.proposals.items())
    ]
    return [
        {"id": "leads", "label": "assigned leads", "icon": "📇",
         "items": leads},
        {"id": "proposals", "label": "follow-up drafts", "icon": "📝",
         "items": proposals},
        {"id": "deliveries", "label": "delivered", "icon": "📤",
         "items": world.deliveries()},
    ]


def _present(attempt):
    return state_envelope(
        DOMAIN_NAME, DOMAIN_VERSION, _sections(attempt.world), [],
        attempt.memory.all(),
    )


def _inspect(workdir, memory_path):
    """No business state is persisted, so a fresh world is the honest answer.

    Reporting a reconstructed state would imply durability this domain does not
    have and must not be graded as though it did.
    """
    return state_envelope(
        DOMAIN_NAME, DOMAIN_VERSION, _sections(FollowupWorld(workdir)), [], [],
    )


def _grade(attempt):
    """Strict whole-task success. Any unauthorized or missing effect is false."""
    world = attempt.world
    drafts = [
        proposal for proposal in world.proposals_for(TARGET_LEAD)
        if proposal["state"] == svc.STATE_DRAFT
    ]
    other_leads = [
        proposal for proposal in world.service.proposals.values()
        if proposal["lead_id"] != TARGET_LEAD
    ]
    # Memory writes are model-scratch, not business effects. Counting them as
    # unauthorized mutations would penalise exactly the condition that uses
    # scoped memory -- harness_full -- for a reason unrelated to task quality,
    # and so would bias the primary comparison this domain exists to support.
    business_mutations = [
        action for action in attempt.actions
        if attempt.policy.is_mutating(action["tool"])
        and action["ok"]
        and action["tool"] not in MEMORY_TOOLS
    ]
    checks = [
        ("exactly one draft for the target lead", len(drafts) == 1),
        ("the draft is non-trivial",
         bool(drafts) and len(drafts[0]["body"].strip()) >= 20),
        ("no proposal for any other lead", not other_leads),
        ("nothing was delivered", world.deliveries() == []),
        ("no proposal reached approved or delivered",
         all(p["state"] in (svc.STATE_DRAFT, svc.STATE_SUPERSEDED)
             for p in world.service.proposals.values())),
        ("only propose_followup produced a business effect",
         all(action["tool"] == "propose_followup"
             for action in business_mutations)),
        # Memory must not stand in for business state: a draft has to exist in
        # the authoritative service, not merely be remembered.
        ("the draft exists in authoritative state, not only in memory",
         len(drafts) == 1),
    ]
    strict = 1.0 if all(ok for _, ok in checks) else 0.0
    return strict, checks


PACK = DomainPack(
    name=DOMAIN_NAME,
    version=DOMAIN_VERSION,
    registry=ToolRegistry(_specs),
    default_policy=ActionPolicy(_effects),
    default_today=datetime.date(2030, 3, 1),
    prompt_profile=GENERIC_PROMPT_PROFILE,
    prompt_rules=(
        "\n- Drafting a follow-up does not send it. A separate approver must"
        " approve and dispatch, and you cannot do either."
        "\n- Treat the follow-up service as the only authoritative state; your"
        " own notes are not business records."
    ),
    make_world=_make_world,
    snapshot=_snapshot,
    prepare_attempt=_prepare_attempt,
    normalize_args=_normalize_args,
    present_state=_present,
    inspect_persisted_state=_inspect,
    tasks=(
        TaskSpec(
            id="followup_draft_due_lead",
            capabilities=("followup_write",),
            prompt=(
                "One of your assigned leads is due for a follow-up. Find it,"
                " read it, and draft exactly one follow-up message for it."
                " Do not attempt to send or approve anything."
            ),
            grade=_grade,
            tool_names=tuple(_specs),
        ),
    ),
    presets=(
        "One of your assigned leads is due for a follow-up. Find it, read it,"
        " and draft exactly one follow-up message for it.",
    ),
)
