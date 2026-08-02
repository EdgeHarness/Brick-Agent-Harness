# Agent Lab — local research console

Agent Lab is a loopback browser interface for observing Brick's synthetic
development agents. It is not a production service, security boundary,
multi-user application, Brix deployment, or retained benchmark scheduler.

The latest release is `v0.7.0` (B0 synthetic lead-follow-up slice), preceded by `v0.6.0` (S1R repaired runtime), `v0.5.0` (S4 evidence store) and `v0.4.0` (F0/Q0 feasibility).
Annotated tags and bound evidence are release-authoritative; see the
`C`/`R`/`D` lifecycle in [`../PROJECT_SETUP.md`](../PROJECT_SETUP.md).

The server binds to `127.0.0.1` and normally selects a port from 8765 through
8784. Loopback reduces network exposure but does not authenticate a user or
protect against another local process, hostile browser origin, proxy, tunnel,
container mapping or remote-desktop environment.

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

Open the printed loopback URL, normally:

```text
http://127.0.0.1:8765
```

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

## Remaining control-plane defects

Q0 does not harden the rest of Agent Lab. The released Q0 implementation lacks
production authentication or authorization, session ownership, a CSRF token,
trusted Origin/Host policy, and comprehensive request limits. Q0 additionally
has no browser/stdin action-confirmation channel: that old unbound mechanism and
its skip-confirmation mode were removed together.

Sensitive state-changing or data-exposing operations include:

- starting a synthetic run;
- resetting selected synthetic state, memory, files or logs;
- revealing an allowlisted runtime path;
- pulling a model; and
- reading workspace, log, preview, status or event data.

Loopback and browser CORS behavior do not make these safe against all local or
browser-driven requests. Close the server when not testing it.

S5W must add a high-entropy startup capability, trusted Host/Origin handling,
JSON-only state-changing POSTs, typed and bounded request bodies, reset
serialization, bounded/redacted logs and verified process-tree termination. S5W
also introduces a new operator-confirmation capability bound to a specific
`(run_id, confirmation_id, nonce)`; it must not restore the removed generic stdin
protocol.

## Process and stop behavior

Only one runner subprocess is accepted at a time. The process boundary gives
limited lifecycle and crash containment; Ollama controls model residency.

The released Stop path terminates the runner wrapper but does not prove that
every descendant or in-flight Ollama operation has stopped. Already performed
synthetic effects are not rolled back. A terminated run may lack a final state
snapshot or saved log. S5W owns the process-group and teardown remediation.

The retained research matrix does not run through Agent Lab. A standalone Python
or PowerShell scheduler owns its queue, evidence commits, heartbeat and resume.

## Logging and privacy

The live stream can expose model tokens, tool arguments, observations, state and
memory without redaction. Released saved logs are incomplete: planner and
verifier source output may be reduced or absent, and a crash can occur before
final log creation.

Logs and state are plaintext and have no production access control, encryption,
retention policy or automatic PII removal. Never place real Brix or other private
data in Agent Lab.

## Harness limitations

Agent Lab invokes the same released development harness as the CLI. It does not
add correctness:

- validation does not yet enforce every advertised type and semantic value;
- fuzzy repair can change or drop arguments;
- completion verification can fail open;
- accepted `done` does not prove success;
- the router's `deep` role is not dispatched; and
- adapter metadata is not applied by Ollama.

These defects are addressed by S1R and later benchmark stages. Visual
presentation is never evidence that an action was correct, safe, delivered or
production-ready.
