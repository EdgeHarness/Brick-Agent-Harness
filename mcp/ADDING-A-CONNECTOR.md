# Adding a connector

How to give the agent a new real-account capability (Slack, Notion, Jira, a
first-party server you wrote) so it appears in the Agent Lab run panel and its
tools land in a task's registry.

**The short version: you add one JSON object to `servers.json`. No harness code.**

The registry is data, not code. `webui/server.py` builds the connector picker
from `mcp_config.available()`, which reads this file, so a new entry shows up in
the picker on the next restart with nothing else touched.

---

## 1. The minimal entry

Open [servers.json](servers.json) and add a key. This is the smallest thing
that works:

```json
"slack": {
  "summary": "Slack, read channels and post messages.",
  "command": "npx",
  "args": ["-y", "@some/slack-mcp-server"],
  "prefix": "slack_"
}
```

That is enough to launch, list, and adapt. Everything below is refinement.

`prefix` is not optional in practice. Without it, a server whose tool is called
`search` claims the bare name `search` in a registry it shares with the domain's
own tools. Prefix everything.

---

## 2. What each field does

**Fields the bridge acts on** (anything else is documentation and is stripped
before launch, see `_BRIDGE_KEYS` in [../harness/mcp_config.py](../harness/mcp_config.py)):

| field | purpose |
|---|---|
| `command`, `args` | how to launch the server. Run with `subprocess.Popen`, no shell |
| `env`, `cwd` | passed through. `~` and `${VARS}` are expanded, so credential paths are not machine specific. `${ROOT}` is this repository |
| `prefix` | prepended to every tool name. Use it |
| `allow` | whitelist of MCP tool names to expose. Everything else is dropped |
| `drop` | blacklist, for when a whitelist is overkill |
| `read_tools`, `write_tools` | override the write classifier. **Read section 4** |
| `arg_hints`, `hide_params` | reshape a tool's parameters for a small model |
| `mode` | `draft` / `live` / `read_only`, overriding the run's mode for this server only |

**Documentation-only fields**, which the UI does surface to the user:

| field | purpose |
|---|---|
| `summary` | one line, shown next to the checkbox in the run panel |
| `setup` | list of strings, shown as setup steps. Put the OAuth dance here |
| `docs` | upstream URL |
| `notes` | why any override above exists. Future you will need this |

---

## 3. Effect classes are assigned for you, safe side first

`enable()` returns an effect per tool alongside the specs, and `ActionPolicy`
is what reads it. An MCP tool gets one of two of this harness's four classes:
`read`, or `external_write` (assumed to reach another party).

`classify()` decides, in falling order of authority:

| order | source | shown in `--mcp-list` as |
|---|---|---|
| 1 | your `read_tools` / `write_tools` in this file | `override` |
| 2 | the server's MCP annotations (`readOnlyHint`, `destructiveHint`) | `declared` |
| 3 | a read verb leading the name (`list_`, `get_`, `search_`, ...) | `read verb` |
| 4 | a write verb anywhere in the name | `write verb` |
| 5 | nothing matched | `unclassified`, **treated as a write** |

Step 5 is the important one. A name with no verb this harness recognises
(`upsert_contact`, `merge_records`, `execute_workflow`) is a write until you
say otherwise, and the run prints those names so you can confirm them. It used
to fall through to `read`, which published them with no confirmation.

Note what is missing: an MCP tool is **never** classified `state_write`. From a
name alone we cannot tell whether a write reaches another person, and a calendar
invite does. Guessing the recoverable class would be guessing in the one
direction that costs something.

In `draft` mode, any tool whose name matches send / forward / reply is dropped
entirely and never reaches the model.

Confirmation is not configured here and is not implemented in the executor. The
loop confirms every mutating call through `ActionPolicy`, deny-by-default: with
no confirmer wired, an `external_write` is refused rather than run. Classifying
the tool correctly is the whole of your job.

---

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

---

## 5. Watch the tool count

A small model at `num_ctx 8192` carries the entire tool list in its system
prompt. A server that injects 60 tools does not fail loudly, it quietly makes
the agent stupid, because the model starts picking tools at random.

`TOOL_BUDGET_WARN` is 25 and `count_warnings()` flags a run before it starts.

Measured, not guessed: the ms365 server returns **69 tools** even with
`--preset mail,calendar`. That is why its entry has a ten-name `allow` list.

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
- [ ] tool count under 25 after `allow`, verified with `--mcp-list`
- [ ] no tool left `unclassified` in `--mcp-list`, each resolved into
      `read_tools` or `write_tools`
- [ ] `notes` explaining each override
- [ ] `--mcp-list` shows no transmitting tools in draft mode
- [ ] `python3 -m pytest tests/test_mcp_bridge.py -q` passes
- [ ] `python3 -m pytest -q` passes
- [ ] connector visible in the Agent Lab run options panel

## Related

- [../harness/mcp_bridge.py](../harness/mcp_bridge.py), whose module docstring
  records what this port deliberately does not do and why.
