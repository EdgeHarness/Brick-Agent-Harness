"""The bridge fixture must coexist with the official SDK named ``mcp``."""

from harness import mcp_config


def test_selftest_uses_brick_namespace_not_official_sdk_namespace():
    server = mcp_config.names_to_servers(["selftest"])[0]
    assert server["args"] == ["-m", "harness.mcp_selftest_server"]
    assert "mcp.selftest_server" not in server["args"]
