"""Brix's screen-only lead review and follow-up drafting profile.

The pack intentionally contains no CRM implementation.  HubSpot facts enter a
run only through the separately authenticated, reviewed connector registry.
"""
import datetime

from harness.builtin_tools import BUILTIN_EFFECTS, builtin_specs
from harness.domain import DomainPack, PromptProfile, state_envelope
from harness.runtime import ActionPolicy
from harness.tools import ToolRegistry

from .world import BrixHubSpotWorld


DOMAIN_NAME = "brix_hubspot_leads"
DOMAIN_VERSION = "0.1.0"

_BUILTINS = builtin_specs()
_SPECS = {name: _BUILTINS[name] for name in ("think", "done")}
_EFFECTS = {name: BUILTIN_EFFECTS[name] for name in _SPECS}


def _make_world(workdir, persistent=False):
    return BrixHubSpotWorld(workdir, persistent=persistent)


def _snapshot(attempt):
    return attempt.world.snapshot(attempt.actions)


def _prepare_attempt(attempt):
    return None


def _normalize_args(name, args, today):
    del name, today
    return args


def _state(memory):
    return state_envelope(
        DOMAIN_NAME,
        DOMAIN_VERSION,
        [],
        [],
        list(memory),
    )


def _present(attempt):
    return _state(attempt.memory.all())


def _inspect(workdir, memory_path):
    del workdir, memory_path
    return _state([])


def _capture_grading_state(attempt):
    del attempt
    return {}


PROMPT_RULES = (
    "\n- HubSpot is the only source of lead, owner, task, and activity facts."
    "\n- Find the contact, then read the selected contact and relevant recent"
    " activity before drafting a reply."
    "\n- If more than one contact matches, stop and ask the operator to choose;"
    " do not guess."
    "\n- If recent activity is unavailable, say that it is unavailable and do"
    " not fill the gap."
    "\n- Never invent names, dates, availability, ownership, status, or previous"
    " communication."
    "\n- Use exactly these output headings: Lead summary; HubSpot evidence;"
    " Recommended next step; Draft, not sent."
    "\n- The draft exists only in this browser run. Never claim that a note, task,"
    " message, or email was created or sent."
    "\n- Do not request or imply a HubSpot write tool."
)


PACK = DomainPack(
    name=DOMAIN_NAME,
    version=DOMAIN_VERSION,
    registry=ToolRegistry(_SPECS),
    default_policy=ActionPolicy(_EFFECTS),
    default_today=datetime.date.today(),
    prompt_profile=PromptProfile(
        raw_role="You review leads and prepare unsent follow-up drafts.",
        harness_role="You are a careful Brix lead follow-up assistant.",
        scope=(
            "Use only the tools exposed for this run. HubSpot connector results"
            " are the only business records."
        ),
        look_before_act=(
            "find the contact and inspect its record and recent activity before"
            " drafting."
        ),
        format_rule=(
            "End with four clearly labeled sections, including 'Draft, not sent'."
        ),
    ),
    prompt_rules=PROMPT_RULES,
    make_world=_make_world,
    snapshot=_snapshot,
    prepare_attempt=_prepare_attempt,
    normalize_args=_normalize_args,
    present_state=_present,
    inspect_persisted_state=_inspect,
    presets=(
        "Find Dana Reed in HubSpot, summarize her recent activity, identify the"
        " next follow-up, and draft a concise reply. Do not change HubSpot or"
        " send anything.",
    ),
    capture_grading_state=_capture_grading_state,
)
