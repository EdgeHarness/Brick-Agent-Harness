# Agent 1B — intended experimental configuration

This folder configures the research harness to request `llama3.2:1b` from
Ollama. It is one condition in a proposed size comparison, not evidence that a
1B model is adequate for unattended work.

```json
{
  "name": "Agent 1B",
  "model": "llama3.2:1b",
  "num_ctx": 8192
}
```

No repeated, versioned benchmark results are committed that establish this
configuration's accuracy, latency, repair rate, or safety.

## Run

From the project root:

```bash
python agents/1b/run_agent.py "List my simulated Wednesday meetings"
```

On the original Windows lab setup:

```powershell
cd agents\1b
.\run.ps1 "List my simulated Wednesday meetings"
```

`run.ps1` hardcodes the original lab Python path. Direct invocation requires
Python, `requests`, `python-pptx`, and `openpyxl`; no root runtime dependency
manifest or lock file currently exists. Ollama must be running locally and the
configured tag must be installed.

## Scope and safety

Default mode uses fixture email/calendar data. Email, chat, calendar, and
reminder actions only update local simulated state; they do not contact real
services or people. PowerPoint and Excel creation writes real files inside this
agent's `workspace/files/`.

`--root` enables experimental real-file tools, including deletion. Its path
check is not an OS sandbox and is vulnerable to symlink/junction escapes.
`--shell` runs unrestricted PowerShell, and `--yolo` removes confirmations.
Use only a disposable directory and never real Brix or member data. See
[`../README.md`](../README.md) for the shared runtime and safety limitations.

The LLM verifier is fail-open and does not prove task completion. Logs omit the
original planner and verifier replies, and may store sensitive prompts, tool
arguments, and observations.

`--deep` configures a role that is never invoked. Adapter fields are logged but
not applied by the Ollama backend.

## Hypothesis, not result

The intended hypothesis is that a smaller model may exhibit more formatting,
tool-selection, and task-completion failures, leaving more room for scaffolding
to change its score. That claim must be tested with repeated, versioned runs and
must not be inferred from the folder name or documentation.
