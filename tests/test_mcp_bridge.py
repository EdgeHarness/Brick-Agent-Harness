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
