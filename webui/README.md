# Agent Lab — local research console

Agent Lab is a loopback browser interface for observing Brick's synthetic
development agents. It is not a production service, security boundary,
multi-user application, Brix deployment, or retained benchmark scheduler.

The latest release is `v0.9.0` (S5W control-plane hardening), preceded by
`v0.8.0` (S5), `v0.7.0` (B0), `v0.6.0` (S1R), `v0.5.0` (S4), and `v0.4.0`
(F0/Q0).
Annotated tags and bound evidence are release-authoritative; see the
`C`/`R`/`D` lifecycle in [`../PROJECT_SETUP.md`](../PROJECT_SETUP.md).

The server binds to `127.0.0.1` and normally selects a port from 8765 through
8784. It generates a new 256-bit capability on every start. Exact Host,
capability, and mutation-Origin checks protect the API; loopback itself is not
treated as authentication. A same-user process that can read the launch URL or
browser memory has the same authority as the operator.

Never expose Agent Lab to a LAN or the internet. Use synthetic data only.

## What it shows

Agent Lab starts one `webui.runner` subprocess and displays:

- streamed local Ollama output;
- harness notes, tool calls, arguments and observations;
- fixture workspace, inbox/calendar, memory and generated files;
- PowerPoint and spreadsheet previews; and
- local run metadata and saved development logs.

Email, chat, calendar and reminder effects are simulated. PowerPoint and Excel
outputs are real files inside the selected synthetic workspace. Model-card tier
hints are not measurements, and no retained model ranking exists.

## Start

From the repository root:

```bash
python -m webui.server
```

Use the exact URL printed and opened at startup. It has this shape:

```text
http://127.0.0.1:8765/#capability=<per-start secret>
```

The fragment is not sent in HTTP requests. Client code holds it in memory and
sends it to API routes as an `Authorization: Bearer` header. Restart the server
to revoke the capability. Do not paste or record the launch URL.

The macOS and Windows convenience launchers may install checked-in dependencies.
Model pulls initiated through the interface may download weights. Brick as a
repository is therefore not inherently offline or air-gapped.

## Q0 capability quarantine

Q0, released in `v0.4.0`, removes real-root, general filesystem, PowerShell and
skip-confirmation choices from Agent Lab. `/api/run`, its request schema, runner
arguments and static UI reject or omit every equivalent of:

- `--root`;
- `--shell`;
- `--yolo`;
- `--with-domain`; and
- `--with-office`.

Rejection occurs before output creation, model construction, network access or
mutation. Domain-specific synthetic Office tools may still create declared
artifacts inside the agent workspace. That is not general host access.

## S5W control-plane boundary

S5W does not turn the console into a production service. It makes the supported
single-user local workflow fail closed across its declared boundary:

- all API reads and streams require the startup bearer capability;
- every request has an exact `127.0.0.1:<bound-port>` Host;
- every mutation is an exact-origin, JSON-only POST with a 64 KiB maximum and
  a closed typed schema;
- events, subscribers, stderr, previews, downloads, logs, archive expansion,
  and retained log count/bytes are bounded;
- file and log access accepts one portable regular-file leaf and rejects links,
  reparse points, irregular files, traversal, and untrusted runtime roots;
- reset is serialized with run creation, while stop and confirmation bind to
  the current unguessable run identifier; and
- external-write or shell-classified effects require one operator decision
  bound to `(run_id, confirmation_id, nonce)` through a narrow JSONL pipe.

Sensitive state-changing or data-exposing operations include:

- starting a synthetic run;
- resetting selected synthetic state, memory, files or logs;
- revealing an allowlisted runtime path;
- pulling a model; and
- reading workspace, log, preview, status or event data.

The channel never forwards arbitrary stdin. Missing, malformed, stale,
mismatched, replayed, timed-out, or explicitly denied decisions refuse the
effect. Current released domain packs expose no external-write or shell tools,
so this is a fail-closed platform seam rather than evidence of a real provider
integration.

## Process and stop behavior

Only one runner subprocess is accepted at a time. The process boundary gives
limited lifecycle and crash containment; Ollama controls model residency.

On POSIX, the runner owns a new session/process group; on Windows, it is assigned
to a kill-on-close Job Object. Stop terminates and waits for the owned tree, and
normal server/run teardown also closes the owner so a descendant cannot outlive
its run. Already performed synthetic effects are not rolled back. A force-stopped
run may lack a final state snapshot or saved log.

The retained research matrix does not run through Agent Lab. A standalone Python
or PowerShell scheduler owns its queue, evidence commits, heartbeat and resume.

## Logging and privacy

The authenticated live stream exposes model tokens, tool arguments,
observations, state, memory, and one-time confirmation details to its operator.
Its in-memory replay is bounded. Saved run logs recursively redact common secret
keys and bearer values, cap string/list/depth and total-file size, use exclusive
temporary creation plus fsync/atomic replacement, and retain at most 100 run logs
within 50 MiB. This is defense in depth, not a PII detector. Logs and state remain
plaintext without production encryption or access policy. Never place real Brix
or other private data in Agent Lab.

## Harness limitations

Agent Lab invokes the repaired S1R development harness, but its visual display
and saved development log are not immutable benchmark evidence. It does not run
the S5 strict grader, paired conditions, opportunity ledger, retained scheduler,
or score-masked analysis. Accepted `done` and a plausible UI state therefore do
not establish strict task success or a harness effect. Those claims remain S6G
through S9 work.

## Design references

The control design follows mature local-compute and web-security practice:

- [Jupyter Server security](https://jupyter-server.readthedocs.io/en/latest/operators/security.html)
  uses generated startup tokens because local code-execution services require
  authentication even when commonly bound to loopback.
- [OWASP CSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
  recommends authentication plus Origin/Fetch Metadata checks and non-simple
  content types; Agent Lab enforces all three for mutations.
- [Python subprocess documentation](https://docs.python.org/3/library/subprocess.html)
  documents `start_new_session` as the thread-safe POSIX session mechanism.
- [Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
  define process-tree inheritance and kill-on-close ownership used on Windows.
- [Inspect evaluation logs](https://inspect.aisi.org.uk/eval-logs.html) and the
  [SWE-bench harness](https://github.com/princeton-nlp/SWE-bench/blob/main/swebench/harness/run_evaluation.py)
  reinforce that development UI logs are distinct from structured evaluation
  records and that evaluation processes need explicit timeouts/cleanup. Brick's
  retained evidence continues to use the separate S4/S6C path.
