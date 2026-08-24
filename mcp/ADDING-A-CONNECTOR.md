# Adding an audited MCP subprocess

This registry is for off-the-shelf stdio MCP servers such as Gmail, Google
Calendar, and Microsoft 365. HubSpot and Optix use the stricter normalized layer
in [`../connectors/README.md`](../connectors/README.md).

Adding an entry does not make its dynamic catalog safe. Discover the actual
server surface and narrow it before use. Exact `tool_policies` are preferred;
when a generic server cannot supply them, the conservative classifier and the
Agent Lab inspection view make every assumption visible.

## Required registry entry

```json
"slack": {
  "summary": "Slack sandbox reads and reviewed drafts.",
  "command": "npx",
  "args": ["-y", "@reviewed/slack-mcp-server"],
  "prefix": "slack_",
  "allow": ["list_channels", "read_messages", "create_draft"],
  "tool_policies": {
    "list_channels": {
      "effect": "read",
      "transmits": false,
      "invites": false
    },
    "read_messages": {
      "effect": "read",
      "transmits": false,
      "invites": false
    },
    "create_draft": {
      "effect": "external_write",
      "transmits": false,
      "invites": false
    }
  },
  "setup": ["Complete OAuth outside the model run."],
  "docs": "https://provider.example/docs"
}
```

When `tool_policies` is present, there is no name-based fallback: an absent
allow list, missing policy, unknown field, or policy outside the allow list
prevents launch. Generic entries without `tool_policies` retain the separately
audited annotation/name classifier described below. Normalized HubSpot tools do
not use this generic fallback.

## Execution fields

| field | rule |
|---|---|
| `command`, `args` | fixed registry-owned launcher, no shell |
| `env`, `cwd` | fixed registry-owned values; agent configs cannot replace them |
| `prefix` | stable Brick prefix for discovered tool names |
| `allow` | reviewed provider tool list; required with `tool_policies` |
| `drop` | additional registry-owned removals |
| `tool_policies` | optional strict path: exact `effect`, `transmits`, and `invites` for every allowed tool |
| `arg_hints`, `hide_params` | reviewed rendering adjustments for a small local model |
| `mode` | optional fixed `read_only`, `draft`, or `live` restriction |

Agent configuration may only narrow `allow`, add names to `drop`, or choose a
valid mode. It cannot change a command, executable arguments, environment,
working directory, policy, prefix, or schema hint.

The child receives a small platform environment needed to start (`PATH`, temp,
home, and Windows system variables) plus exactly the values declared by its
registry entry. Credential-shaped variables from the parent shell are not
inherited accidentally.

## Policy classification

`enable()` returns an effect per tool alongside the specs, and `ActionPolicy`
is what reads it. An MCP tool gets one of two of this harness's four classes:
`read`, or `external_write` (assumed to reach another party).

`classify()` decides, in falling order of authority:

| order | source | shown in `--mcp-list` as |
|---|---|---|
| 1 | exact `tool_policies` entry | `policy` |
| 2 | `read_tools` / `write_tools` override | `override` |
| 3 | server MCP annotations (`readOnlyHint`, `destructiveHint`) | `declared` |
| 4 | a read verb leading the name (`list_`, `get_`, `search_`, ...) | `read verb` |
| 5 | a write verb anywhere in the name | `write verb` |
| 6 | nothing matched | `unclassified`, **treated as a write** |

The final step is the important one. A name with no verb this harness recognises
(`upsert_contact`, `merge_records`, `execute_workflow`) is a write until you
say otherwise, and the run prints those names so you can confirm them. It used
to fall through to `read`, which published them with no confirmation.

An entry that supplies `tool_policies` opts into the stricter path. Every
allowed tool then declares:

- `effect`: `read` or `external_write`;
- `transmits`: whether it can put content in front of another person or system;
- `invites`: whether it can create or change an invitation.

`read_only` exposes only `read`. `draft` removes every `transmits` or `invites`
tool even if an agent config asks for it. `live` may expose a reviewed write,
but `ActionPolicy` still requires one explicit operator confirmation. Missing or
declined confirmation denies the call.

A calendar operation with attendees is both transmitting and invitation-capable.
A draft stored in a provider is still an external write even if it does not send.

## Catalog and result safety

The bridge adapts only allowed names. An MCP
`notifications/tools/list_changed` event marks the catalog stale and blocks all
later writes until a fresh connection is reviewed. Structured MCP results stay
structured and are bounded/redacted before entering an observation.

Transport and subprocess failures are environment failures. A provider's
explicit tool-result error remains model-visible so the model can correct bad
arguments. Credentials and credential-shaped diagnostics are redacted before
stderr, browser events, transcripts, or logs.

## 4. Your one manual job: resolve the `unclassified` list

Run `--mcp-list` and look at the parenthesised source next to each tool. Every
tool marked `unclassified` is the safe default speaking, not the server, and
resolving those is the whole of your classification work:

```
    write  hs_upsert_contact    (unclassified)
  ! hubspot: 1 tool(s) have no write/read verb and no server annotation, so
    they are treated as writes and will ask for confirmation: hs_upsert_contact.
```

For each one, ask: *does this change anything on the real account?*

```json
"write_tools": ["hs_upsert_contact"],
"read_tools":  ["hs_recent_activity"]
```

Both answers are one line. Leaving it unresolved is safe but noisy: the tool
keeps asking for confirmation on every call, which costs a small model a turn.

Two conveniences worth knowing:

- A server that ships MCP annotations classifies itself and you write nothing.
  Prefer such servers when you have a choice.
- `read_tools` is still needed for a false positive from a write verb inside a
  longer word, though the leading-read-verb rule now catches the common shape
  (`get-mailbox-settings` reads as `get`, not `set`).

Write a `notes` entry saying why each override exists. Future you needs the
reason, not the list.

## Tool limits

One run may expose at most 8 external connector tools and 25 tools total,
including the domain registry. This is a hard refusal, not a warning. Use the
server's own preset and then a narrow `allow` list. Do not expose a broad dynamic
catalog to a small model.

When two reviewed accounts provide the same prefixed capability, the bridge
uses one brokered tool with a required `account` argument. There is no default
account.

## Simulated tools

By default, attaching a real account drops domain tools that declare
`simulates`, avoiding a fake inbox beside a real one. `--keep-office-tools`
keeps them only when the operator intentionally wants both.

Real-account runs use run-only memory and do not persist their task, transcript,
observations, answer, or normal chat turn.

## Verification order

1. Discover the real server catalog outside a model run.
2. Add the smallest reviewed allow list and exact policies.
3. List the adapted surface with no inference:

   ```powershell
   python agents\8b\run_agent.py --mcp selftest --mcp-list
   ```

4. Run offline boundary tests:

   ```powershell
   python -m pytest -q tests/test_mcp_bridge.py tests/test_connectors.py
   ```

Measured, not guessed: the ms365 server returns **69 tools** even with
`--preset mail,calendar`. That is why its reviewed entry has a narrow `allow`
list.

Use the server's own preset flag first, then `allow` to cut the rest. Derive the
list from real `--mcp-list` output, never from the upstream docs.

---

## 6. What happens to the simulated tools

A domain tool that declares `"simulates": "<surface>"` is dropped when any
connector is attached, so the model is not offered a fake inbox beside a real
one: two list-mail tools is a coin flip for a small model. Pass
`--keep-office-tools` to keep both.

This is a drop-list derived from what each tool declares, never an allow-list of
survivors, so a tool added to a domain later survives unless it opts in. If your
connector replaces a surface no domain tool declares yet, add the declaration to
that tool rather than a list here.

---

## 7. Verify it, in this order

**a. List the tools without running an agent.** Either open the Agent Lab, go
to run options, Real accounts, and press **Check** under your connector, or
use the CLI:

```bash
python3 agents/8b/run_agent.py --mcp slack --mcp-list
```

Both start the server, report what it exposes after filtering with each
tool's effect class and the reason for it, and stop the server again. No
model call either way.

Check three things: the names are prefixed, the count is under budget, and every
transmitting tool is absent in draft mode.

**b. Confirm the safety guarantees still hold.** This uses the fake mailbox, no
credentials and no network:

```bash
python3 -m pytest tests/test_mcp_bridge.py -q
```

**c. Run the suite.**

```bash
python3 -m pytest -q
```

**d. Look at it in the run panel.** Start the lab, open the run options, and
confirm your connector appears with its summary and setup notes.

```bash
python3 -m webui.server
```

Then run one task with it selected. The banner grows a panel per connector
showing every tool it exposed, whether that tool can change something, and how
that was decided, plus any warning. It is the same audit as `--mcp-list`, so
you can do the whole classification pass in the console without the CLI.

---

## 8. Two accounts of the same service

If you add a second entry for the same provider (a work and a personal mailbox),
they will collide on every tool name. That is handled: the second provider joins
the first behind one tool name, and the tool gains a required `account`
argument naming which one to use.

You do not configure this. It happens on collision. Just be aware that the model
must then name an account on every call, because two mailboxes behind one name
have no safe default.

---

## 9. When you actually do need code

Only two cases:

**You are writing the server itself.** Use
[selftest_server.py](selftest_server.py) as the template. It is a complete MCP
server in one stdlib file, speaks JSON-RPC 2.0 over stdio, and needs no
dependencies. Point a registry entry at it with `"command": "python3"` and
`"args": ["-m", "mcp.your_server"]`.

**The server's argument shapes defeat the model.** Some servers take a whole
API entity under one `body` argument with 25 top-level keys. `arg_hints` and
`hide_params` exist for that, and the ms365 entry is the worked example. Read
the shapes off a live `--mcp-list`, not the vendor docs, because they disagree.

---

## Checklist

- [ ] entry added to `servers.json` with `summary`, `command`, `args`, `prefix`
- [ ] `setup` steps written, including any OAuth dance
- [ ] nonempty allow list derived from authenticated discovery when exact
      `tool_policies` are used
- [ ] every exact-policy tool declares effect, transmission, and invitation
- [ ] otherwise, no tool is left `unclassified`; resolve each into
      `read_tools` or `write_tools` and explain the override in `notes`
- [ ] at most 8 external tools and 25 total tools in an actual agent run
- [ ] `--mcp-list` shows no transmitting tools in draft mode
- [ ] structured result and catalog-change behavior tested
- [ ] credentials remain outside the repository and model context
- [ ] `python3 -m pytest tests/test_mcp_bridge.py -q` passes
- [ ] `python3 -m pytest -q` passes
- [ ] connector visible in the Agent Lab run options panel
- [ ] no write enabled before sandbox confirmation

The self-test server at [`selftest_server.py`](selftest_server.py) is the offline
protocol fixture. The production adapter is
[`../harness/mcp_bridge.py`](../harness/mcp_bridge.py).
