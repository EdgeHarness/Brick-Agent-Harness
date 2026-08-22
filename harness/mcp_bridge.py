"""MCP tool bridge - real MCP servers adapted into ToolRegistry specs.

Ported from the Final-Agent-8B connector layer and made registry-native. The
upstream bridge mutates a process-global TOOLS dict; here nothing is mutated:

    specs, effects, summary = enable(servers, mode="draft")
    registry = registry.merged(specs)
    policy   = policy.with_effects(effects, confirmer)

Two upstream responsibilities deliberately DROPPED, because Brick's core owns
them:

  - Confirmation. Upstream confirms writes inside each executor via a module
    global. Brick's loop confirms every mutating call through ActionPolicy,
    deny-by-default (no confirmer means no consent). MCP writes are therefore
    just classified "external_write" and the loop does the rest.
  - restrict_to_mcp(). Upstream prunes the global registry so the model never
    sees a fake inbox next to a real one. Brick composes registries per task
    (DomainPack.registry_for / ToolRegistry.selected), so there is no global
    to prune: build the task's registry from the specs you want.

SAFETY, unchanged from upstream:
  - mode="draft" (default) never exposes a tool that transmits to a person
    (send/forward/reply). The model composes; a human sends.
  - mode="read_only" drops every world-changing tool.
  - per-server allow/drop lists and read_tools/write_tools overrides correct
    the name-based classifier where a server's naming defeats it.

Tool names are sanitized to the registry's ^[a-z][a-z0-9_]*$ (ms365 publishes
"list-mail-messages"); the executor closure keeps the server's real name, so
the wire protocol never sees the sanitized one.
"""
import atexit
import itertools
import json
import os
import queue
import re
import subprocess
import threading
import time

from .errors import ToolError

PROTOCOL_VERSION = "2025-06-18"   # sent; we accept whatever the server negotiates back
CLIENT_INFO = {"name": "brick-harness", "version": "0.1"}
CALL_TIMEOUT = 120                # seconds to wait for one tools/call result
INIT_TIMEOUT = 60                 # seconds to wait for the initialize handshake
OBS_CLIP = 4000                   # clip a tool result before it enters the transcript

_CLIENTS = []                     # live MCPClient processes, terminated on shutdown

# A world-changing verb anywhere in the tool name. Heuristic; overridable per server.
_WRITE_RE = re.compile(
    r"(send|create|add|update|patch|delete|remove|trash|archive|move|reply|"
    r"forward|draft|schedule|accept|decline|cancel|mark|write|post|put|set)",
    re.I)
# Tools that actually TRANSMIT to another person. Dropped in draft mode.
_TRANSMIT_RE = re.compile(r"(send|forward|reply)", re.I)


# --------------------------------------------------------------- JSON-RPC ----

class MCPClient:
    """One MCP server subprocess, spoken to over stdio JSON-RPC 2.0.

    Synchronous: the harness loop issues one tool call at a time. A reader
    thread drains stdout into a queue so a request can wait for its matching id
    without blocking on interleaved notifications or log lines."""

    def __init__(self, server_id, command, args=None, env=None, cwd=None):
        self.id = server_id
        self.name = server_id
        self._ids = itertools.count(1)
        self._inbox = queue.Queue()
        self._write_lock = threading.Lock()
        full_env = dict(os.environ)
        full_env.update(env or {})
        try:
            self.proc = subprocess.Popen(
                [command, *(args or [])],
                cwd=cwd, env=full_env, text=True, encoding="utf-8",
                errors="replace", bufsize=1,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except FileNotFoundError:
            raise ToolError(f"MCP server {server_id!r}: command {command!r} not found. "
                            f"Is it installed / on PATH?")
        self._stderr_tail = []
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        self._initialize()

    def _read_stdout(self):
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._inbox.put(json.loads(line))
            except ValueError:
                pass  # non-JSON banner/log line on stdout - ignore, not our protocol
        self._inbox.put({"__eof__": True})

    def _drain_stderr(self):
        for line in self.proc.stderr:
            self._stderr_tail.append(line)
            del self._stderr_tail[:-40]  # keep only the last 40 lines for error context

    def _send(self, msg):
        with self._write_lock:
            if self.proc.poll() is not None:
                raise ToolError(f"MCP server {self.id!r} has exited "
                                f"({''.join(self._stderr_tail)[-400:].strip()})")
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()

    def _request(self, method, params, timeout):
        rid = next(self._ids)
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        end = time.time() + timeout
        while True:
            remaining = end - time.time()
            if remaining <= 0:
                raise ToolError(f"MCP server {self.id!r}: no response to {method} within {timeout}s")
            try:
                msg = self._inbox.get(timeout=remaining)
            except queue.Empty:
                raise ToolError(f"MCP server {self.id!r}: no response to {method} within {timeout}s")
            if msg.get("__eof__"):
                raise ToolError(f"MCP server {self.id!r} closed the connection "
                                f"({''.join(self._stderr_tail)[-400:].strip()})")
            if msg.get("id") != rid:
                continue  # a notification or an out-of-order reply - not ours
            if "error" in msg:
                err = msg["error"]
                raise ToolError(f"{method} failed: {err.get('message', err)}")
            return msg.get("result", {})

    def _notify(self, method, params=None):
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def _initialize(self):
        self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": CLIENT_INFO,
        }, timeout=INIT_TIMEOUT)
        self._notify("notifications/initialized")

    def list_tools(self):
        tools, cursor = [], None
        while True:
            params = {"cursor": cursor} if cursor else {}
            result = self._request("tools/list", params, timeout=INIT_TIMEOUT)
            tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            if not cursor:
                return tools

    def call_tool(self, name, arguments):
        """Return (is_error, text). Text is the joined text content blocks."""
        result = self._request("tools/call", {"name": name, "arguments": arguments or {}},
                               timeout=CALL_TIMEOUT)
        blocks = result.get("content", [])
        parts = []
        for b in blocks:
            if isinstance(b, dict):
                if b.get("type") == "text":
                    parts.append(b.get("text", ""))
                else:
                    parts.append(json.dumps(b, ensure_ascii=False, default=str))
        text = "\n".join(p for p in parts if p) or "(no content)"
        return bool(result.get("isError")), text

    def close(self):
        try:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
        except Exception:
            pass


# -------------------------------------------------------------- adapting ----

def _clip(text, limit=OBS_CLIP):
    text = str(text)
    return text if len(text) <= limit else text[:limit] + " ...[truncated]"


def _placeholder(schema):
    t = (schema or {}).get("type")
    return {"string": "...", "number": 0, "integer": 0,
            "boolean": True, "array": [], "object": {}}.get(t, "...")


_NAME_OK = re.compile(r"^[a-z][a-z0-9_]*$")


def sanitize_name(name):
    """A registry-legal tool name for an MCP tool name.

    The registry enforces ^[a-z][a-z0-9_]*$; real servers publish names like
    "list-mail-messages" and "getMailTips". Lowercase, then map every illegal
    character to "_". The MCP-side name survives in the executor closure, so
    the wire protocol always sees the original."""
    out = re.sub(r"[^a-z0-9_]", "_", str(name).lower()).strip("_")
    if not out or not out[0].isalpha():
        out = "t_" + out
    return out


def _params_from_schema(schema):
    """MCP inputSchema (JSON Schema) -> registry params {name: (type_desc, required)}.

    Parameter names are sanitized like tool names (the registry validates them
    with the same pattern); the executor maps them back before the wire call."""
    props = (schema or {}).get("properties") or {}
    required = set((schema or {}).get("required") or [])
    out, back = {}, {}
    for pname, pschema in props.items():
        pschema = pschema or {}
        t = pschema.get("type", "any")
        desc = str(pschema.get("description", "")).strip().replace("\n", " ")
        if len(desc) > 120:
            desc = desc[:117] + "..."
        tdesc = f"{t}" + (f" - {desc}" if desc else "")
        safe = sanitize_name(pname)
        out[safe] = (tdesc, pname in required)
        back[safe] = pname
    return out, back


def _example_for(harness_name, schema, back):
    props = (schema or {}).get("properties") or {}
    required = (schema or {}).get("required") or list(props)[:2]
    fwd = {v: k for k, v in back.items()}
    args = {fwd.get(r, sanitize_name(r)): _placeholder(props.get(r)) for r in list(required)[:3]}
    return {"tool": harness_name, "args": args}


def _is_write(name, server_cfg):
    keep_read = {k.lower() for k in server_cfg.get("read_tools", [])}
    force_write = {k.lower() for k in server_cfg.get("write_tools", [])}
    n = name.lower()
    if n in force_write:
        return True
    if n in keep_read:
        return False
    return bool(_WRITE_RE.search(name))


def _make_executor(client, mcp_name, back):
    """The registry 'run' callable: (attempt, args) -> observation text.

    No confirmation here. Brick's loop confirms every mutating call through
    ActionPolicy before execution, deny-by-default, so an executor that asked
    again would double-prompt the operator."""
    def run(attempt, args):
        wire_args = {back.get(k, k): v for k, v in (args or {}).items()}
        is_error, text = client.call_tool(mcp_name, wire_args)
        if is_error:
            raise ToolError(_clip(text))
        return _clip(text)
    return run


def _adapt(client, tool, server_cfg, prefix, draft_only, taken):
    """One MCP tool -> (harness_name, spec, effect) or None if filtered out."""
    mcp_name = tool.get("name")
    if not mcp_name:
        return None
    is_write = _is_write(mcp_name, server_cfg)
    if draft_only and is_write and _TRANSMIT_RE.search(mcp_name) \
            and mcp_name.lower() not in {k.lower() for k in server_cfg.get("write_tools", [])}:
        return None  # draft mode: never expose a tool that transmits to a person
    if mcp_name.lower() in {d.lower() for d in server_cfg.get("drop", [])}:
        return None
    allow = server_cfg.get("allow")
    if allow and mcp_name.lower() not in {a.lower() for a in allow}:
        return None

    harness_name = sanitize_name(f"{prefix}{mcp_name}" if prefix else mcp_name)
    if harness_name in taken:
        harness_name = sanitize_name(f"{client.id}_{mcp_name}")  # collision: qualify with server id
    schema = tool.get("inputSchema") or {}
    desc = str(tool.get("description", "")).strip().replace("\n", " ")
    tag = "[real, needs confirmation] " if is_write else "[real, read-only] "
    params, back = _params_from_schema(schema)
    spec = {
        "desc": tag + (desc or mcp_name),
        "params": params,
        "example": _example_for(harness_name, schema, back),
        "run": _make_executor(client, mcp_name, back),
    }
    return harness_name, spec, ("external_write" if is_write else "read")


# ---------------------------------------------------------------- enable ----

def enable(servers, mode="draft"):
    """Launch each MCP server and adapt its tools into registry specs.

    servers: list of dicts (see mcp_config.names_to_servers):
        {"id": "gmail", "command": "npx", "args": [...], "env": {...},
         "cwd": "...", "prefix": "gmail_",         # optional name prefix
         "allow": [...], "drop": [...],            # optional tool filters
         "read_tools": [...], "write_tools": [...],# override the write classifier
         "mode": "draft"|"live"|"read_only"}       # per-server, overrides the arg

    mode:
        "draft"     (default) real reads + draft/tentative writes; transmit tools dropped
        "live"      also expose send/forward/reply (still confirmed by the policy)
        "read_only" drop every world-changing tool

    Returns (specs, effects, summary):
        specs    {name: spec} for ToolRegistry.merged()
        effects  {name: "read"|"external_write"} for ActionPolicy.with_effects()
        summary  [{id, mode, tools, writes}] per server, for banners and warnings

    Nothing global is touched; the caller owns registry and policy composition.
    """
    specs, effects, summary = {}, {}, []
    for cfg in servers:
        sid = cfg.get("id") or cfg.get("command", "mcp")
        server_mode = cfg.get("mode", mode)
        draft_only = server_mode == "draft"
        read_only = server_mode == "read_only"
        client = MCPClient(sid, cfg["command"], cfg.get("args"), cfg.get("env"), cfg.get("cwd"))
        _CLIENTS.append(client)
        prefix = cfg.get("prefix", "")
        added, writes = [], []
        for tool in client.list_tools():
            if read_only and _is_write(tool.get("name", ""), cfg):
                continue
            adapted = _adapt(client, tool, cfg, prefix, draft_only, specs.keys())
            if not adapted:
                continue
            name, spec, effect = adapted
            specs[name] = spec
            effects[name] = effect
            added.append(name)
            if effect == "external_write":
                writes.append(name)
        summary.append({"id": sid, "mode": server_mode, "tools": added, "writes": writes})
    return specs, effects, summary


def mail_rules(mode="draft"):
    """Text for the system prompt (PromptProfile / prompt_rules) so the model
    treats the real tools correctly."""
    base = ("\n\nYou also have REAL tools that act on live email/calendar accounts. "
            "Tools tagged [real, ...] touch a real account.\n"
            "- Look before you write: list/read before you create or reply.\n"
            "- Use the exact addresses, dates and times the task gives you; never invent recipients.\n"
            "- A write tool asks the user to confirm. If a call is declined, do not retry it.")
    if mode == "draft":
        base += ("\n- You are in DRAFT mode: create email DRAFTS and TENTATIVE calendar events. "
                 "You cannot send mail or send invitations - a human reviews and sends. "
                 "Creating the draft/tentative event IS completing the task.")
    return base


def shutdown():
    for c in _CLIENTS:
        c.close()
    _CLIENTS.clear()


atexit.register(shutdown)
