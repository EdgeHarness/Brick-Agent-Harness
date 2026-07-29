# Agent Lab — unauthenticated loopback research console

Agent Lab is a local browser interface for observing the experimental agents in
[`../agents/`](../agents/). It is a development console, not a production
service, security boundary, multi-user application, or Brix deployment.

The server binds to `127.0.0.1` and normally chooses the first available port
from 8765 through 8784. Loopback binding reduces network exposure, but it does
not provide authentication or protect against other local processes, hostile
browser origins, DNS-rebinding-style access, or a user who exposes the port
through a proxy, tunnel, container mapping, or remote desktop environment.

Never expose this server to a LAN or the internet. Do not use it with real
member, employee, agreement, payment, email, access-control, or other sensitive
Brix data.

## What it actually shows

The console starts one `webui.runner` subprocess at a time and displays:

- streamed chunks from local Ollama calls;
- harness notes, tool calls, arguments, and observations;
- the selected agent's local workspace, fixture inbox/calendar, memory, and
  generated files;
- PowerPoint and spreadsheet previews;
- local run metadata and saved transcript files.

The default office is simulated. “Sent” email and chat, calendar events, and
reminders are local JSON records. No email is delivered, no reminder fires, and
no external room or calendar is reserved. PowerPoint and Excel outputs are real
files under the selected agent's `workspace/files/`.

The UI currently displays hardcoded qualitative speed/reliability blurbs for
model cards. Those strings are not measurements and should be ignored. No
committed repeated benchmark establishes a model ranking.

## Start

From the project root:

```bash
python -m webui.server
```

Then open the printed loopback URL. It is usually:

```text
http://127.0.0.1:8765
```

`Agent Lab.command` on macOS and `Agent Lab.bat` on Windows are convenience
launchers. Both may install unpinned `requests`, `python-pptx`, and `openpyxl`
packages into the selected Python environment, potentially outside an isolated
virtual environment. The macOS launcher also attempts
to start Ollama if its health check fails; the Windows launcher does not start
Ollama. There is no root runtime dependency manifest, virtual-environment setup,
or lock file.

Model downloads initiated by **Get it** call Ollama's pull endpoint and may cause
network downloads. `--shell` can also execute network-capable commands. Therefore
“nothing leaves the machine” is not a valid general security guarantee.

## No authentication, origin check, or CSRF defense

The HTTP API has:

- no user authentication or authorization;
- no session or per-run ownership;
- no CSRF token;
- no `Origin`, `Referer`, or trusted-`Host` validation;
- no meaningful request-size or rate limits.

A malicious web page or another local process may be able to trigger state
changes against the loopback server. Responses being blocked by browser CORS
does not prevent all cross-origin requests from being sent.

Sensitive and destructive endpoints include:

- `POST /api/run` — can start an agent with real-root, shell, and
  skip-confirmation options;
- `POST /api/confirm` — answers the current run's destructive-action prompt
  without tying the answer to an authenticated browser session;
- `POST /api/reset` — deletes selected state, memory, generated files, or logs
  without an independent server-side confirmation;
- `POST /api/reveal` — accepts an unchecked `sub` path; `..` components can
  escape the selected agent folder and ask the operating system to reveal
  another existing path;
- `GET /api/pull` — performs a state-changing, potentially large model download;
- workspace, log, preview, download, status, and event endpoints — expose local
  agent data to any caller that can reach the server.

Close the server when not actively testing it. Browser confirmation buttons are
not a substitute for API authentication.

## Real-file and shell warnings

The options drawer exposes the same unsafe research flags as the CLI:

- real-root containment is a lexical in-process path check, not an OS sandbox;
- symlinks and Windows junctions can escape that check;
- the configured root itself can be selected for deletion;
- the write deny-list is tied to one Windows installation;
- shell commands receive the root only as their working directory and can access
  other paths or networks;
- skip-confirmations removes the interactive protection around destructive file
  and shell operations.

Use only a disposable test directory with independent backups. Keeping the
server on loopback does not make filesystem or shell execution safe.

## Process and Stop behavior

Only one runner subprocess is accepted at a time. This isolates the harness's
process-global registry and hooks, but it does **not** guarantee one model in RAM:
Ollama controls model residency, uses keep-alive settings, and tier mode may use
more than one tag.

**Stop** calls `terminate()` on the runner process. It does not manage an OS
process group, so shell-created child processes may survive. Real-file side
effects already performed are not rolled back. A terminated runner may not
write its final state snapshot or saved transcript, so the absence of a final log
does not imply that nothing changed.

Run events and captured stderr are retained in server memory without a durable
bounded audit design. A long or noisy run can consume increasing memory.

## Logging and privacy limits

The live stream exposes model tokens, tool arguments, results, workspace state,
and memory without redaction. Saved `run_NNN.json` files contain the harness
episode transcript, but they are not complete raw model transcripts:

- the original planner reply is reduced to a filtered plan;
- the original verifier reply or verifier exception is not retained;
- stopping or crashing before log creation can leave no saved run record.

Logs and state are plaintext and have no application-level access controls,
encryption, retention policy, or automatic secret/PII removal. A tool can also
copy content read under a real root into logs and agent state outside that root.

## Harness limitations remain

The UI invokes the same harness as the CLI; it does not add correctness:

- tool validation checks keys, not all documented types or semantic values;
- fuzzy repair can silently change or drop arguments;
- the completion verifier fails open and does not inspect generated artifacts;
- an accepted `done` means the loop stopped, not that the task succeeded;
- the router's `deep` role is not dispatched;
- adapter fields are recorded but not applied by Ollama.

Use the console to inspect and debug these behaviors. Do not use its visual
presentation as evidence that an action was correct, safe, delivered, or
production-ready.
