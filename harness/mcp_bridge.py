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

Schema rendering is kept in step with the upstream bridge: local $refs are
dereferenced (ms365 hides every recipient behind $defs), nested shapes and
enums render inline rather than as a bare "object", registry `arg_hints` give
a measured working example in place of a generated one, and `hide_params`
drops server plumbing that costs context and is never model-set.

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
# A read verb LEADING the name. Anchored, unlike _WRITE_RE, because the first
# word of an MCP tool name is its action: "get-mailbox-settings" is a read that
# only looks like a write because "set" hides inside "settings". Deliberately
# excludes download and export, which put a file on disk.
_READ_RE = re.compile(
    r"^(list|get|read|search|find|fetch|query|show|describe|check|count|view)\b"
    r"|^(list|get|read|search|find|fetch|query|show|describe|check|count|view)[_\-]",
    re.I)


# Credential-shaped environment variables never reach an MCP child process
# unless the server's own config names them. Hard rule 9 says provider
# credentials live with the third-party server, not here - so an unrelated
# API key sitting in the user's shell must not leak into every connector
# spawned. Everything else (PATH, HOME, locale) passes through, because
# npx-style launchers need a working environment.
_SENSITIVE_ENV_RE = re.compile(
    r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH)", re.I)


def _child_env(extra):
    """The environment for one MCP child: the parent's, minus anything
    credential-shaped, plus exactly what the server config declares."""
    env = {k: v for k, v in os.environ.items()
           if not _SENSITIVE_ENV_RE.search(k)}
    env.update(extra or {})
    return env


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
        full_env = _child_env(env)
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


# Read-only / derived fields every Graph entity carries. Rendering them wastes
# the context an 8B does not have, and no model should ever set them.
_SCHEMA_NOISE = {"id", "createdDateTime", "lastModifiedDateTime", "changeKey",
                 "etag", "@odata.etag", "@odata.type", "categories"}
_TYPE_DESC_CLIP = 300


def _deref(node, root, seen=()):
    """Follow a local $ref, e.g. '#/$defs/def1'.

    Not optional: ms-365-mcp-server puts every recipient and every start/end
    behind $defs, so without this `toRecipients` and `start` render as bare
    'array'/'any' and the model invents a shape. Measured upstream, not
    guessed - that is where the create-draft-email failures came from."""
    for _ in range(8):
        if not isinstance(node, dict):
            return {}
        ref = node.get("$ref")
        if not isinstance(ref, str) or not ref.startswith("#/"):
            return node
        if ref in seen:
            return {}                      # cyclic $ref - stop rather than recurse
        seen = (*seen, ref)
        target = root
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            target = (target or {}).get(part) if isinstance(target, dict) else None
            if target is None:
                return {}
        node = target
    return node if isinstance(node, dict) else {}


def _type_desc(node, root, depth=0, max_depth=2, max_keys=6):
    """Compact one-line type: enum values and nested keys, not just 'object'.

    A bare 'object' tells the model nothing, so it guesses the nesting and the
    server rejects it. Depth and key count are capped because this lands in the
    system prompt of a model with an 8k context."""
    node = _deref(node, root)
    for branch in (node.get("anyOf") or node.get("oneOf") or []):
        b = _deref(branch, root)
        if b.get("type") != "null":
            return _type_desc(b, root, depth, max_depth, max_keys)
    if node.get("enum"):
        return "|".join(json.dumps(v, ensure_ascii=False) for v in node["enum"][:6])
    t = node.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), "any")
    if not t:
        t = "object" if node.get("properties") else "any"
    if t == "object" and depth < max_depth:
        props = {k: v for k, v in (node.get("properties") or {}).items()
                 if k not in _SCHEMA_NOISE}
        keys = list(props)[:max_keys]
        if keys:
            inner = ", ".join(f"{k}: {_type_desc(props[k], root, depth + 1, max_depth, max_keys)}"
                              for k in keys)
            return "{" + inner + (", ..." if len(props) > len(keys) else "") + "}"
    if t == "array":
        # The array wrapper does NOT consume a depth level: charging one made
        # `toRecipients` render as '[object]', hiding the very shape the model
        # gets wrong. It is a container, not a level of nesting.
        return "[" + _type_desc(node.get("items"), root, depth, max_depth, max_keys) + "]"
    return t


def _placeholder(schema, root=None, depth=0):
    node = _deref(schema, root if root is not None else {})
    for branch in (node.get("anyOf") or node.get("oneOf") or []):
        b = _deref(branch, root or {})
        if b.get("type") != "null":
            node = b
            break
    if node.get("enum"):
        return node["enum"][0]
    t = node.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), None)
    if not t:
        t = "object" if node.get("properties") else None
    if t == "object" and depth < 2:
        props = {k: v for k, v in (node.get("properties") or {}).items()
                 if k not in _SCHEMA_NOISE}
        return {k: _placeholder(props[k], root, depth + 1) for k in list(props)[:3]}
    if t == "array" and depth < 2:
        item = _placeholder(node.get("items"), root, depth + 1)
        return [item] if item != "..." else []
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


def _params_from_schema(schema, root=None, hint=None, hide=()):
    """MCP inputSchema (JSON Schema) -> registry params {name: (type_desc, required)}.

    Every character here lands in the system prompt of a model with an 8k
    context, so a parameter already demonstrated by the example renders as a
    pointer instead of a second, longer copy of the same shape.

    Parameter names are sanitized like tool names (the registry validates them
    with the same pattern); the returned back-map restores the wire names."""
    root = schema if root is None else root
    props = (schema or {}).get("properties") or {}
    required = set((schema or {}).get("required") or [])
    hinted = set(hint or ())
    hidden = {h.lower() for h in hide}
    out, back = {}, {}
    for pname, pschema in props.items():
        if pname.lower() in hidden and pname not in required:
            continue          # server plumbing: costs context, never set by a model
        pschema = pschema or {}
        if pname in hinted:
            t = "object - use the shape in the example exactly"
        else:
            t = _type_desc(pschema, root)
            if len(t) > _TYPE_DESC_CLIP:
                t = t[:_TYPE_DESC_CLIP - 3] + "..."
        desc = str(pschema.get("description", "")).strip().replace("\n", " ")
        if len(desc) > 120:
            desc = desc[:117] + "..."
        tdesc = f"{t}" + (f" - {desc}" if desc else "")
        safe = sanitize_name(pname)
        out[safe] = (tdesc, pname in required)
        back[safe] = pname
    return out, back


def _example_for(harness_name, schema, back, hint=None):
    """A correct call the model can copy.

    A registry `arg_hints` entry wins over anything derived from the schema:
    these servers expose the whole Graph entity (25 top-level keys on a draft),
    so a generated example picks the first few keys, not the ones a human
    actually needs. The hint is the measured, working shape.

    Hint keys are wire names, so they are sanitized to match the params."""
    fwd = {v: k for k, v in back.items()}
    if hint:
        return {"tool": harness_name,
                "args": {fwd.get(k, sanitize_name(k)): v for k, v in hint.items()}}
    props = (schema or {}).get("properties") or {}
    required = (schema or {}).get("required") or list(props)[:2]
    args = {fwd.get(r, sanitize_name(r)): _placeholder(props.get(r), schema)
            for r in list(required)[:3]}
    return {"tool": harness_name, "args": args}


def classify(name, server_cfg, tool=None):
    """Is this MCP tool a write? Returns (is_write, why).

    Resolved in falling order of authority, because guessing from a name is
    the weakest evidence available and used to be the only evidence used:

      1. the registry entry's explicit read_tools / write_tools override
      2. the server's own MCP annotations (readOnlyHint, destructiveHint) -
         the protocol carries the answer and we were throwing it away
      3. a read verb leading the name (list_, get_, search_, ...)
      4. a write verb anywhere in the name (_WRITE_RE)
      5. UNKNOWN, which counts as a write

    Step 5 is the change that matters. This used to fall through to "read",
    so a tool whose name held no verb the regex knew - upsert_contact,
    merge_records, execute_workflow - was published read-only and ran against
    a real account with no confirmation. Absence of a recognised write verb is
    not evidence that nothing is written, and this is the one classification
    in the bridge that fails on a real person's data. It now fails closed,
    matching ActionPolicy's deny-by-default posture everywhere else.

    The cost of the safe default is a confirmation prompt on a tool that only
    reads. `why` exists so `--mcp-list` can show which tools were guessed at,
    making that a two-second fix in the registry rather than a mystery.
    """
    n = name.lower()
    if n in {k.lower() for k in server_cfg.get("write_tools", [])}:
        return True, "override"
    if n in {k.lower() for k in server_cfg.get("read_tools", [])}:
        return False, "override"

    ann = (tool or {}).get("annotations") or {}
    if isinstance(ann, dict):
        # destructiveHint is only meaningful for a non-read-only tool, so a
        # server that sets it at all is declaring a write.
        if ann.get("destructiveHint") is True:
            return True, "declared"
        if ann.get("readOnlyHint") is True:
            return False, "declared"
        if ann.get("readOnlyHint") is False:
            return True, "declared"

    if _READ_RE.match(name):
        return False, "read verb"
    if _WRITE_RE.search(name):
        return True, "write verb"
    return True, "unclassified"


def _is_write(name, server_cfg, tool=None):
    return classify(name, server_cfg, tool)[0]


def _transmits(name, tool=None):
    """Would this tool put something in front of another person?

    Draft mode drops these, so a run cannot reach anyone. The test is the
    tool's name, because most servers say nothing about it, and a name is all
    we have.

    A name is a blunt instrument though: "reply_draft" writes a draft reply
    and transmits nothing, but it contains "reply". So a tool that explicitly
    declares itself non-destructive is believed, on the same rule the effect
    classifier uses - a declaration beats a guess about a name.

    Only an explicit `destructiveHint: false` rescues a tool. A missing
    annotation is not a claim, so it keeps the conservative drop; that way a
    server that says nothing can never talk its way out of draft mode.
    """
    if not _TRANSMIT_RE.search(name):
        return False
    ann = (tool or {}).get("annotations") or {}
    if isinstance(ann, dict) and ann.get("destructiveHint") is False:
        return False
    return True


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


def _make_broker_executor(providers):
    """Dispatch one call to whichever connected account the caller named.

    Several providers of one capability coexist behind a single name and the
    broker routes each request, instead of each provider claiming a name of its
    own. Reuses _make_executor so the wire path is byte for byte the one a
    single-provider tool gets; a broker must not become a second place where
    argument mapping is written down."""
    def run(attempt, args):
        by_id = {a: (c, n, b) for a, c, n, b, _ in providers}
        account = (args or {}).get("account")
        if account not in by_id:
            raise ToolError(
                "'account' must be one of %s; got %r. More than one account is "
                "connected, so there is no default."
                % (", ".join(sorted(by_id)), account))
        client, mcp_name, back = by_id[account]
        rest = {k: v for k, v in (args or {}).items() if k != "account"}
        return _make_executor(client, mcp_name, back)(attempt, rest)
    return run


def _to_broker(spec, providers):
    """Rewrite an adapted spec so it serves every provider under its name.

    Idempotent: a third provider rebuilds the same way a second did."""
    accounts = sorted(a for a, _, _, _, _ in providers)
    spec = dict(spec)

    # The account list is named ONCE, on the parameter, which is where the model
    # looks for allowed values. Repeating it in the description too cost real
    # context for no information: measured, it ate most of what brokering saved.
    params = dict(spec["params"])
    params["account"] = ("string, one of: " + ", ".join(accounts), True)
    spec["params"] = params

    example = dict(spec.get("example") or {})
    ex_args = dict(example.get("args") or {})
    ex_args["account"] = accounts[0]
    example["args"] = ex_args
    spec["example"] = example

    spec["run"] = _make_broker_executor(providers)
    return spec


def _adapt(client, tool, server_cfg, prefix, draft_only, seen):
    """One MCP tool -> (harness_name, spec, effect, provider, why) or None.

    `why` is how the effect was decided (see classify); enable() carries it
    into the summary so a developer can audit a new connector's classes.

    `seen` is the names THIS server has already claimed. A name already taken by
    an EARLIER server is not a clash, it is a second provider of the same
    capability, and enable() brokers it. Only a collision inside one server
    gets qualified away."""
    mcp_name = tool.get("name")
    if not mcp_name:
        return None
    is_write, why = classify(mcp_name, server_cfg, tool)
    if draft_only and is_write and _transmits(mcp_name, tool) \
            and mcp_name.lower() not in {k.lower() for k in server_cfg.get("write_tools", [])}:
        return None  # draft mode: never expose a tool that transmits to a person
    if mcp_name.lower() in {d.lower() for d in server_cfg.get("drop", [])}:
        return None
    allow = server_cfg.get("allow")
    if allow and mcp_name.lower() not in {a.lower() for a in allow}:
        return None

    harness_name = sanitize_name(f"{prefix}{mcp_name}" if prefix else mcp_name)
    if harness_name in seen:
        harness_name = sanitize_name(f"{client.id}_{mcp_name}")  # a real clash: qualify with server id
    schema = tool.get("inputSchema") or {}
    desc = str(tool.get("description", "")).strip().replace("\n", " ")
    tag = "[real, needs confirmation] " if is_write else "[real, read-only] "
    hint = (server_cfg.get("arg_hints") or {}).get(mcp_name)
    params, back = _params_from_schema(
        schema, hint=hint, hide=server_cfg.get("hide_params") or ())
    spec = {
        "desc": tag + (desc or mcp_name),
        "params": params,
        "example": _example_for(harness_name, schema, back, hint),
        "run": _make_executor(client, mcp_name, back),
    }
    provider = (client.id, client, mcp_name, back, is_write)
    return harness_name, spec, ("external_write" if is_write else "read"), provider, why


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
    providers = {}          # tool name -> [(account, client, mcp_name, back, is_write)]
    for cfg in servers:
        sid = cfg.get("id") or cfg.get("command", "mcp")
        server_mode = cfg.get("mode", mode)
        draft_only = server_mode == "draft"
        read_only = server_mode == "read_only"
        client = MCPClient(sid, cfg["command"], cfg.get("args"), cfg.get("env"), cfg.get("cwd"))
        _CLIENTS.append(client)
        prefix = cfg.get("prefix", "")
        added, writes, seen = [], [], set()
        classes = {}
        for tool in client.list_tools():
            if read_only and _is_write(tool.get("name", ""), cfg, tool):
                continue
            adapted = _adapt(client, tool, cfg, prefix, draft_only, seen)
            if not adapted:
                continue
            name, spec, effect, provider, why = adapted
            classes[name] = why
            providers.setdefault(name, []).append(provider)
            if name in specs:
                # A SECOND PROVIDER of the same capability, not a name clash.
                # ms365 and ms365-personal share the outlook_ prefix and an
                # identical allow list, so a work and a personal mailbox used to
                # yield twenty tools for ten operations, the second set named
                # asymmetrically after its server. One broker instead.
                spec = _to_broker(specs[name], providers[name])
                # The most dangerous provider sets the class. Two servers behind
                # one name should agree, but if they ever disagree the policy
                # must follow the worse one.
                if effect == "external_write":
                    effects[name] = "external_write"
            else:
                effects[name] = effect
            specs[name] = spec
            seen.add(name)
            added.append(name)
            if effects[name] == "external_write":
                writes.append(name)
        summary.append({"id": sid, "mode": server_mode, "tools": added,
                        "writes": writes, "classified_by": classes})
    return specs, effects, summary


def without_simulated(registry, keep=()):
    """The domain registry minus the tools a real account replaces.

    A spec declares itself a stand-in with "simulates": the surface it fakes.
    Offering list_emails beside a real Gmail list tool is a coin flip for a
    small model, so the fake goes when the real one arrives.

    A DROP-list derived from what each tool declares, never an allow-list of
    survivors: an allow-list silently deletes every tool added afterwards. The
    upstream bridge learned that by watching a model be told "unknown tool
    list_files" in a real run. `keep` spares named tools anyway."""
    keep = set(keep)
    return registry.selected([
        name for name in registry.names()
        if name in keep or not (registry.get(name) or {}).get("simulates")
    ])


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
