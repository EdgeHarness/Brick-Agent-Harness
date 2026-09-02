"""The MCP bridge, registry-native: real stdio against the selftest server.

The selftest server is a genuine MCP server (initialize / tools/list /
tools/call over newline JSON-RPC); only its mailbox is fake. Its tool names are
chosen to hit every branch of the write classifier, so these tests exercise the
same code path a real Gmail/Outlook server would - minus credentials.
"""
from pathlib import Path

import pytest

from harness import mcp_bridge, mcp_config
from harness.runtime import ActionPolicy
from harness.tools import ToolRegistry


class _StubAttempt:
    """Just enough attempt for ToolRegistry.execute: an action log and hooks."""

    class _Hooks:
        on_tool = None

    def __init__(self):
        self.actions = []
        self.hooks = self._Hooks()

    def record_action(self, tool, args, ok, result_preview):
        self.actions.append({"tool": tool, "args": args, "ok": ok,
                             "result": str(result_preview)[:300]})


@pytest.fixture(scope="module")
def draft():
    servers = mcp_config.names_to_servers(["selftest"])
    specs, effects, summary = mcp_bridge.enable(servers, mode="draft")
    yield specs, effects, summary
    mcp_bridge.shutdown()


def test_draft_mode_never_exposes_a_transmit_tool(draft):
    specs, _, _ = draft
    assert "mail_send_mail" not in specs
    assert "mail_reply_mail" not in specs
    assert "mail_login" not in specs            # per-server drop list
    assert {"mail_list_mail", "mail_read_mail",
            "mail_draft_mail", "mail_modify_mail"} <= set(specs)


def test_effects_come_classified_for_the_action_policy(draft):
    specs, effects, _ = draft
    assert set(effects) == set(specs)           # exactly the exposed tools
    assert effects["mail_list_mail"] == "read"
    assert effects["mail_draft_mail"] == "external_write"
    # modify_mail has no write verb the classifier knows; only the registry's
    # write_tools override classifies it. If this fails, the override is dead.
    assert effects["mail_modify_mail"] == "external_write"


def test_specs_survive_registry_validation_and_merge(draft):
    specs, effects, _ = draft
    merged = ToolRegistry(specs)                # construction IS the validation
    policy = ActionPolicy().with_effects(effects)
    policy.validate_registry(merged.names())    # exactly one effect per tool
    assert not policy.is_mutating("mail_read_mail")
    assert policy.is_mutating("mail_draft_mail")


def test_an_unconfirmed_write_is_denied_not_allowed(draft):
    _, effects, _ = draft
    policy = ActionPolicy().with_effects(effects)
    # No confirmer configured: absence of a decision channel is denial.
    assert policy.confirm("mail_draft_mail", "detail") is False


def test_the_executor_round_trips_over_real_stdio(draft):
    specs, _, _ = draft
    registry = ToolRegistry(specs)
    attempt = _StubAttempt()
    ok, obs = registry.execute("mail_list_mail", {}, attempt)
    assert ok, obs
    assert attempt.actions and attempt.actions[0]["tool"] == "mail_list_mail"
    ok, obs = registry.execute("mail_read_mail", {"id": "m1"}, attempt)
    assert ok, obs


def test_a_tool_error_comes_back_as_an_observation_not_a_crash(draft):
    specs, _, _ = draft
    registry = ToolRegistry(specs)
    ok, obs = registry.execute("mail_read_mail", {"id": "nope"}, _StubAttempt())
    assert not ok
    assert obs.startswith("ERROR:")


def test_live_mode_exposes_send_and_read_only_drops_every_write():
    servers = mcp_config.names_to_servers(["selftest"])
    specs, effects, _ = mcp_bridge.enable(servers, mode="live")
    try:
        assert "mail_send_mail" in specs
        assert effects["mail_send_mail"] == "external_write"
    finally:
        mcp_bridge.shutdown()
    specs, effects, _ = mcp_bridge.enable(
        mcp_config.names_to_servers(["selftest"]), mode="read_only")
    try:
        assert set(effects.values()) == {"read"}
        assert "mail_draft_mail" not in specs
    finally:
        mcp_bridge.shutdown()


def test_server_published_names_are_sanitized_to_registry_law():
    # ms365 publishes hyphenated names; the registry rejects them un-sanitized.
    assert mcp_bridge.sanitize_name("list-mail-messages") == "list_mail_messages"
    assert mcp_bridge.sanitize_name("getMailTips") == "getmailtips"
    assert mcp_bridge.sanitize_name("3d-render") == "t_3d_render"
    for name in ("list-mail-messages", "getMailTips", "3d-render"):
        ToolRegistry({mcp_bridge.sanitize_name(name): {
            "desc": "x", "params": {},
            "example": {"tool": mcp_bridge.sanitize_name(name), "args": {}},
            "run": lambda attempt, args: "ok"}})


def test_registry_path_is_this_repo_not_the_upstream_one():
    assert Path(mcp_config.REGISTRY_PATH).exists()
    assert "final-agent-8b" not in mcp_config.REGISTRY_PATH


def test_selftest_uses_a_direct_script_not_an_importable_mcp_package():
    server = mcp_config.names_to_servers(["selftest"])[0]
    assert len(server["args"]) == 1
    script = Path(server["args"][0])
    assert script == Path(mcp_config.ROOT) / "mcp" / "selftest_server.py"
    assert script.is_file()


# --- schema rendering, kept in step with the upstream bridge -----------------

_MS365_ISH = {
    "type": "object",
    "$defs": {
        "recipient": {"type": "object", "properties": {
            "emailAddress": {"type": "object", "properties": {
                "address": {"type": "string"}, "name": {"type": "string"}}}}},
        "when": {"type": "object", "properties": {
            "dateTime": {"type": "string"}, "timeZone": {"type": "string"}}},
    },
    "properties": {
        "subject": {"type": "string"},
        "toRecipients": {"type": "array", "items": {"$ref": "#/$defs/recipient"}},
        "start": {"$ref": "#/$defs/when"},
        "importance": {"enum": ["low", "normal", "high"]},
        "id": {"type": "string"},
        "confirm": {"type": "boolean"},
    },
    "required": ["subject", "toRecipients"],
}


def test_a_ref_is_dereferenced_rather_than_rendered_as_a_bare_type():
    params, _ = mcp_bridge._params_from_schema(_MS365_ISH)
    # Without $ref following these are 'array' and 'any', and the model invents
    # a shape the server rejects. This is the create-draft-email failure.
    assert "emailAddress" in params["torecipients"][0]
    assert "address" in params["torecipients"][0]
    assert "dateTime" in params["start"][0]


def test_an_array_wrapper_does_not_hide_the_item_shape():
    params, _ = mcp_bridge._params_from_schema(_MS365_ISH)
    assert not params["torecipients"][0].startswith("[object]")
    assert params["torecipients"][0].startswith("[{")


def test_enums_render_as_their_values():
    params, _ = mcp_bridge._params_from_schema(_MS365_ISH)
    assert '"low"' in params["importance"][0]


def test_derived_graph_fields_are_dropped_from_nested_shapes():
    """_SCHEMA_NOISE prunes NESTED keys, where a Graph entity would otherwise
    spend most of an 8k context on read-only fields. Top-level parameters are
    left alone (a server that requires 'id' means it); hide_params is the knob
    for those. Matches the upstream bridge exactly."""
    noisy = {"type": "object", "properties": {"item": {"type": "object", "properties": {
        "subject": {"type": "string"}, "changeKey": {"type": "string"},
        "lastModifiedDateTime": {"type": "string"}}}}}
    params, _ = mcp_bridge._params_from_schema(noisy)
    assert "subject" in params["item"][0]
    assert "changeKey" not in params["item"][0]
    assert "lastModifiedDateTime" not in params["item"][0]


def test_hide_params_drops_optional_server_plumbing_only():
    params, _ = mcp_bridge._params_from_schema(
        _MS365_ISH, hide=("confirm", "subject"))
    assert "confirm" not in params     # optional: dropped
    assert "subject" in params         # required: kept even when hidden


def test_an_arg_hint_replaces_the_generated_example_and_shortens_the_params():
    hint = {"subject": "Q3", "toRecipients": [{"emailAddress": {"address": "a@b.c"}}]}
    params, back = mcp_bridge._params_from_schema(_MS365_ISH, hint=hint)
    example = mcp_bridge._example_for("ms365_create_draft_email",
                                      _MS365_ISH, back, hint)
    assert "use the shape in the example exactly" in params["torecipients"][0]
    assert example["args"]["torecipients"] == hint["toRecipients"]
    # hint keys are wire names; the example must use the sanitized param names
    assert set(example["args"]) <= set(params)


def test_the_registry_carries_the_measured_ms365_hints():
    reg = mcp_config.load_registry()
    hints = reg["ms365"].get("arg_hints") or {}
    assert "create-draft-email" in hints
    assert reg["ms365"].get("hide_params")


# ------------------------------------------------------- the service broker --
#
# Several providers of one capability behind a single name. ms365 and
# ms365-personal ship the same outlook_ prefix and an identical allow list, so
# connecting a work and a personal mailbox used to register twenty tools for ten
# operations, the second set named after its server (mail_list_mail beside
# personal_list_mail). Two selftest servers reproduce that exactly, over real
# stdio, without credentials.


@pytest.fixture(scope="module")
def two_mailboxes():
    base = mcp_config.names_to_servers(["selftest"])[0]
    servers = [dict(base, id="work"), dict(base, id="personal")]
    specs, effects, summary = mcp_bridge.enable(servers, mode="draft")
    yield specs, effects, summary
    mcp_bridge.shutdown()


def test_a_second_provider_shares_the_name_instead_of_claiming_its_own(two_mailboxes):
    specs, _, summary = two_mailboxes
    assert "mail_list_mail" in specs
    assert "personal_list_mail" not in specs
    # Both servers report the same names, so the tool count is one server's.
    assert summary[0]["tools"] == summary[1]["tools"]
    assert len(specs) == len(summary[0]["tools"])


def test_the_account_argument_is_required_and_names_both(two_mailboxes):
    specs, _, _ = two_mailboxes
    kind, required = specs["mail_list_mail"]["params"]["account"]
    assert required, "two mailboxes have no safe default"
    assert "work" in kind and "personal" in kind
    assert specs["mail_list_mail"]["example"]["args"]["account"] == "personal"


def test_either_account_is_reachable_over_real_stdio(two_mailboxes):
    """Both names resolve and both round-trip. The two selftest servers hold
    identical mailboxes, so which one answered is checked below with clients
    that can be told apart."""
    specs, _, _ = two_mailboxes
    run = specs["mail_list_mail"]["run"]
    for account in ("work", "personal"):
        assert "jordan@example.com" in run(_StubAttempt(), {"account": account})


def test_the_call_reaches_the_account_that_was_named():
    """Two clients that answer differently, so routing is observable."""
    class _Fake:
        def __init__(self, cid, reply):
            self.id, self._reply, self.calls = cid, reply, []

        def call_tool(self, name, args):
            self.calls.append((name, args))
            return False, self._reply

    work, personal = _Fake("work", "WORK INBOX"), _Fake("personal", "PERSONAL INBOX")
    tool = {"name": "list_mail"}
    providers = [mcp_bridge._adapt(c, tool, {}, "outlook_", True, set())[3]
                 for c in (work, personal)]
    run = mcp_bridge._to_broker(
        mcp_bridge._adapt(work, tool, {}, "outlook_", True, set())[1],
        providers)["run"]

    assert run(_StubAttempt(), {"account": "personal"}) == "PERSONAL INBOX"
    assert work.calls == [], "the other mailbox was touched"
    assert run(_StubAttempt(), {"account": "work"}) == "WORK INBOX"
    assert work.calls == [("list_mail", {})]


def test_an_omitted_account_refuses_rather_than_picking_one(two_mailboxes):
    """The whole safety argument for the broker. Silently choosing a mailbox is
    merely confusing for a read and wrong for anything that leaves the machine."""
    from harness.errors import ToolError

    specs, _, _ = two_mailboxes
    run = specs["mail_draft_mail"]["run"]
    for args in ({}, {"account": "nonesuch"}):
        with pytest.raises(ToolError) as caught:
            run(_StubAttempt(), args)
        assert "work" in str(caught.value) and "personal" in str(caught.value)


def test_the_broker_keeps_the_effect_class_of_the_worst_provider(two_mailboxes):
    specs, effects, _ = two_mailboxes
    assert effects["mail_list_mail"] == "read"
    assert effects["mail_draft_mail"] == "external_write"
    assert effects["mail_modify_mail"] == "external_write"
    assert set(effects) == set(specs)


def test_a_clash_inside_one_server_still_qualifies_rather_than_brokering():
    """Two tools of ONE server sanitizing to the same name are different
    capabilities that happen to collide, not two accounts. Only a name an
    EARLIER server already claimed may broker."""
    class _Fake:
        id = "srv"

        def call_tool(self, name, args):
            return False, name

    fake = _Fake()
    seen = set()
    first = mcp_bridge._adapt(fake, {"name": "list-mail"}, {}, "", True, seen)
    seen.add(first[0])
    second = mcp_bridge._adapt(fake, {"name": "list_mail"}, {}, "", True, seen)
    assert first[0] == "list_mail"
    assert second[0] == "srv_list_mail"
    assert "account" not in second[1]["params"]
