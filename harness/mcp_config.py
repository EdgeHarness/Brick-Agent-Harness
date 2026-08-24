"""Resolve named MCP servers from the registry into configs mcp_bridge can launch.

mcp_bridge already knows how to speak to an MCP server; it just had no way to
be told *which* servers to start. This module is that missing half:

    names_to_servers(["gmail", "ms365"])  ->  [{...}, {...}]  for mcp_bridge.enable()

The registry itself is data, not code - mcp/servers.json. An agent folder may
only narrow a reviewed allow list, add drops, or select a valid mode through a
"mcp" block in its config.json:

    "mcp": {
      "enable": ["gmail", "ms365"],
      "mode": "draft",
      "servers": {
        "gmail": {"allow": ["search_emails", "read_email", "draft_email"]}
      }
    }

Three things this does that a plain json.load would not:

  - Command resolution. mcp_bridge does subprocess.Popen([command, ...]) with no
    shell. On Windows "npx" is npx.cmd and that Popen raises FileNotFoundError,
    which is exactly the box this repo targets. shutil.which() finds the real
    executable via PATHEXT, so the same registry entry works on both platforms.
  - Expansion. ~ and ${VARS} in env values and cwd, so credential paths in the
    registry are not machine-specific.
  - A tool-count guard. An 8B at num_ctx 8192 has the whole tool list in its
    system prompt; actual runs additionally enforce the normalized connector
    layer's eight-external/25-total boundary.
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REGISTRY_PATH = os.path.join(ROOT, "mcp", "servers.json")

# Substituted into registry paths before ${ENV} expansion, so an entry can point
# at a server that ships in this repo without hard-coding anyone's checkout.
_VARS = {"${ROOT}": ROOT}

# Above this many injected tools, a small model's system prompt is mostly tool
# specification. Generic catalog inspection may reach this ceiling; actual
# runs have the stricter eight-external limit in connectors.runtime.
TOOL_BUDGET_WARN = 25
MAX_MCP_SERVERS = 8
MCP_MODES = frozenset(("draft", "live", "read_only"))
MCP_EFFECTS = frozenset(("read", "external_write"))

# Keys mcp_bridge.enable() understands. Everything else in a registry entry is
# documentation and is stripped before launch.
_BRIDGE_KEYS = {
    "id", "command", "args", "env", "cwd", "prefix", "allow", "drop",
    "read_tools", "write_tools", "mode", "arg_hints", "hide_params",
    "tool_policies",
}
_AGENT_OVERRIDE_KEYS = frozenset(("allow", "drop", "mode"))
_TOOL_POLICY_KEYS = frozenset(("effect", "transmits", "invites"))


class ConfigError(Exception):
    pass


def load_registry(path=None):
    with open(path or REGISTRY_PATH, encoding="utf-8-sig") as f:
        reg = json.load(f)
    return {k: v for k, v in reg.items() if not k.startswith("_")}


def available(path=None):
    """[(name, summary)] for --mcp-help and the webui's server picker."""
    reg = load_registry(path)
    return [(name, cfg.get("summary", "")) for name, cfg in sorted(reg.items())]


def _expand(value):
    if isinstance(value, str):
        for token, target in _VARS.items():
            value = value.replace(token, target)
        return os.path.expanduser(os.path.expandvars(value))
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


def _resolve_command(command, server_id):
    """Absolute path to the executable, so Popen works without a shell.

    On Windows this is what turns 'npx' into '...\\npx.cmd'; without it every
    npx-based server dies with FileNotFoundError on the Snapdragon box.

    A Python server always runs under the interpreter the harness is running
    under, never a stray system python - that is what keeps a first-party server
    in mcp/servers/ inside the same virtualenv as everything else."""
    if command in ("python", "python3"):
        return sys.executable
    found = shutil.which(command)
    if found:
        return found
    raise ConfigError(
        f"MCP server {server_id!r} needs {command!r}, which is not on PATH.\n"
        f"    npx-based servers need Node.js installed: https://nodejs.org")


def _merge(base, override):
    """Apply only narrowing, non-executable per-agent overrides."""
    out = dict(base)
    override = override or {}
    if not isinstance(override, dict):
        raise ConfigError("MCP server override must be an object")
    unknown = set(override) - _AGENT_OVERRIDE_KEYS
    if unknown:
        raise ConfigError(
            "MCP server override cannot change: " + ", ".join(sorted(unknown))
        )
    if "allow" in override:
        asked = override["allow"]
        if not isinstance(asked, list) or any(not isinstance(x, str) for x in asked):
            raise ConfigError("MCP allow override must be a string list")
        declared = set(base.get("allow") or ())
        if not set(asked) <= declared:
            raise ConfigError("MCP allow override may only narrow the audited allow list")
        out["allow"] = list(asked)
    if "drop" in override:
        dropped = override["drop"]
        if not isinstance(dropped, list) or any(not isinstance(x, str) for x in dropped):
            raise ConfigError("MCP drop override must be a string list")
        out["drop"] = sorted(set(base.get("drop") or ()) | set(dropped))
    if "mode" in override:
        out["mode"] = override["mode"]
    return out


def require_mode(mode):
    if mode not in MCP_MODES:
        raise ConfigError(
            "MCP mode must be one of " + ", ".join(sorted(MCP_MODES))
        )
    return mode


def _validate_tool_policies(cfg, server_id):
    allow = cfg.get("allow")
    policies = cfg.get("tool_policies")
    # Generic MCP servers retain the conservative annotation/name classifier.
    # Supplying tool_policies opts the entry into the exact reviewed boundary.
    if policies is None:
        return
    if not isinstance(allow, list) or not allow or any(
        not isinstance(name, str) or not name for name in allow
    ):
        raise ConfigError(
            f"MCP server {server_id!r} has no audited nonempty allow list"
        )
    if len(allow) != len(set(name.casefold() for name in allow)):
        raise ConfigError(f"MCP server {server_id!r} allow list contains duplicates")
    if not isinstance(policies, dict):
        raise ConfigError(
            f"MCP server {server_id!r} has no explicit tool_policies"
        )
    for name in allow:
        policy = policies.get(name)
        if not isinstance(policy, dict) or set(policy) != _TOOL_POLICY_KEYS:
            raise ConfigError(
                f"MCP tool {server_id}.{name} must declare exactly "
                "effect, transmits, and invites"
            )
        if policy["effect"] not in MCP_EFFECTS:
            raise ConfigError(
                f"MCP tool {server_id}.{name} has invalid effect"
            )
        if type(policy["transmits"]) is not bool or type(policy["invites"]) is not bool:
            raise ConfigError(
                f"MCP tool {server_id}.{name} transmit/invite flags must be bool"
            )
        if policy["effect"] == "read" and (
            policy["transmits"] or policy["invites"]
        ):
            raise ConfigError(
                f"MCP tool {server_id}.{name} cannot transmit while classified read"
            )
    undeclared = set(policies) - set(allow)
    if undeclared:
        raise ConfigError(
            f"MCP server {server_id!r} policies are outside its allow list: "
            + ", ".join(sorted(undeclared))
        )


def names_to_servers(names, agent_cfg=None, mode=None, registry_path=None):
    """Resolve server names into configs ready for mcp_bridge.enable().

    names       list of registry keys, e.g. ["gmail", "ms365"]
    agent_cfg   the agent's config.json "mcp" block, for per-agent overrides
    mode        "draft" | "live" | "read_only", applied to servers that do not
                pin their own mode

    Raises ConfigError on an unknown name or a missing executable - both are
    worth failing loudly at startup rather than half-way through a run.
    """
    if not isinstance(names, (list, tuple)) or not names:
        raise ConfigError("MCP server names must be a nonempty list")
    if len(names) > MAX_MCP_SERVERS:
        raise ConfigError(f"at most {MAX_MCP_SERVERS} MCP servers may be enabled")
    if any(not isinstance(name, str) or not name for name in names):
        raise ConfigError("MCP server names must be nonempty strings")
    if len(names) != len(set(names)):
        raise ConfigError("MCP server names must be unique")
    if mode is not None:
        require_mode(mode)
    reg = load_registry(registry_path)
    agent_cfg = agent_cfg or {}
    if not isinstance(agent_cfg, dict):
        raise ConfigError("MCP agent config must be an object")
    overrides = agent_cfg.get("servers", {})
    if not isinstance(overrides, dict):
        raise ConfigError("MCP agent server overrides must be an object")
    unknown_overrides = set(overrides) - set(names)
    if unknown_overrides:
        raise ConfigError(
            "MCP overrides name servers that are not enabled: "
            + ", ".join(sorted(unknown_overrides))
        )
    out = []
    for name in names:
        if name not in reg:
            raise ConfigError(
                f"unknown MCP server {name!r}. Known: {', '.join(sorted(reg))}")
        cfg = _merge(reg[name], overrides.get(name))
        cfg = {k: v for k, v in cfg.items() if k in _BRIDGE_KEYS}
        cfg["id"] = cfg.get("id", name)
        _validate_tool_policies(cfg, name)
        cfg["command"] = _resolve_command(_expand(cfg["command"]), name)
        for key in ("args", "env", "cwd"):
            if key in cfg:
                cfg[key] = _expand(cfg[key])
        if "mode" not in cfg and mode is not None:
            cfg["mode"] = mode
        if "mode" in cfg:
            require_mode(cfg["mode"])
        out.append(cfg)
    return out


def enforce_tool_budget(summary, budget=TOOL_BUDGET_WARN):
    total = sum(len(item.get("tools") or ()) for item in summary)
    if total > budget:
        raise ConfigError(
            f"{total} MCP tools exceed the hard limit of {budget}; narrow the allow lists"
        )
    return total


def setup_notes(name, registry_path=None):
    """The human setup steps for one server - printed by --mcp-help."""
    reg = load_registry(registry_path)
    if name not in reg:
        raise ConfigError(f"unknown MCP server {name!r}")
    cfg = reg[name]
    lines = [f"{name} - {cfg.get('summary', '')}"]
    for step in cfg.get("setup", []):
        lines.append(f"    {step}")
    for note in cfg.get("notes", []):
        lines.append(f"    ! {note}")
    if cfg.get("docs"):
        lines.append(f"    docs: {cfg['docs']}")
    return "\n".join(lines)


def classification_warnings(summary):
    """Name the tools whose effect class was a safe guess, not a fact.

    An unclassified tool is treated as a write, so nothing runs unconfirmed;
    the cost is a confirmation prompt on a tool that may only read. Both
    outcomes are fixed the same way, by one line in the registry entry, so
    the run says which tools are waiting on that line."""
    warnings = []
    for server in summary:
        guessed = sorted(
            name for name, why in (server.get("classified_by") or {}).items()
            if why == "unclassified"
        )
        if guessed:
            warnings.append(
                f"{server['id']}: {len(guessed)} tool(s) have no write/read verb "
                f"and no server annotation, so they are treated as writes and "
                f"will ask for confirmation: {', '.join(guessed)}. Confirm each "
                f"in mcp/servers.json under 'read_tools' or 'write_tools'.")
    return warnings


def count_warnings(summary, budget=TOOL_BUDGET_WARN):
    """Warn when a server injected more tools than a small model can hold.

    summary is what mcp_bridge.enable() returns."""
    warnings = []
    total = sum(len(s["tools"]) for s in summary)
    for s in summary:
        if len(s["tools"]) > budget:
            warnings.append(
                f"{s['id']} injected {len(s['tools'])} tools (> {budget}). A small "
                f"model reads all of them in its system prompt - narrow it with the "
                f"server's own preset flag or an 'allow' list in mcp/servers.json.")
    if total > budget and not warnings:
        warnings.append(
            f"{total} MCP tools injected in total (> {budget}); expect the model to "
            f"spend calls choosing between them.")
    return warnings
