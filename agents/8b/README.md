# Agent 8B — intended experimental configuration

This folder configures the research harness to request `llama3.1:8b` from
Ollama. It is the largest Llama configuration currently declared here, not a
validated unattended assistant.

```json
{
  "name": "Agent 8B",
  "model": "llama3.1:8b",
  "num_ctx": 8192
}
```

No repeated, versioned benchmark results are committed that establish this
configuration's accuracy, latency, reliability, or repair behavior.

## Run

From the project root:

```bash
python agents/8b/run_agent.py "List my simulated Wednesday meetings"
```

On the original Windows lab setup:

```powershell
cd agents\8b
.\run.ps1 "List my simulated Wednesday meetings"
```

`run.ps1` hardcodes the original lab Python path. Direct invocation requires
Python, `requests`, `python-pptx`, and `openpyxl`; no root runtime dependency
manifest or lock file currently exists. Ollama must be running locally and the
configured tag must be installed.

## Scope and safety

Default office actions operate on fixture state. They do not send real email,
deliver reminders, message members, or reserve an external calendar. Generated
PowerPoint and Excel files are real and are written under
`workspace/files/`.

`--root` exposes experimental destructive file tools through a lexical path
check that is not an OS sandbox. `--shell` can act outside the root, and
`--yolo` removes confirmations. Use only disposable data and read the shared
[`../README.md`](../README.md) before enabling either option.

The LLM verifier is fail-open and does not inspect generated artifacts. Run logs
omit original planner/verifier replies and can retain file or task contents.

This folder ships with a tracked `memory/memory.jsonl` containing one demo fact.
That fact may be injected into matching tasks. Remove or isolate it before a
clean experiment, and do not store real private facts in tracked memory.

The router's `deep` role is never invoked. Adapter configuration is telemetry
only with the Ollama backend.

## Hypothesis, not result

One intended hypothesis is that this configuration may require less format and
call repair than the smaller configurations. However, it uses Llama 3.1 while
the 1B and 3B folders use Llama 3.2, so any difference is confounded with model
generation and cannot establish a size effect. The behavior remains untested
until a repeated, versioned benchmark is published.
