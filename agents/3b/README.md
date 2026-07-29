# Agent 3B — intended experimental configuration

This folder configures the research harness to request `llama3.2:3b` from
Ollama. It is an intended comparison point, not a measured recommendation.

```json
{
  "name": "Agent 3B",
  "model": "llama3.2:3b",
  "num_ctx": 8192,
  "domain": "office_demo"
}
```

No repeated, versioned results are committed that establish this
configuration's accuracy, latency, reliability, or repair behavior.

## Run

From the project root:

```bash
python agents/3b/run_agent.py "List my simulated Wednesday meetings"
```

On the original Windows lab setup:

```powershell
cd agents\3b
.\run.ps1 "List my simulated Wednesday meetings"
```

`run_agent.py` is a thin shim over the shared runner. `run.ps1` discovers
`python`/`py` and honors the `PYTHON` environment variable. Install from the
root pinned requirements first; the transitive lock has no hashes and
installation may need network/cache access. Ollama must be running locally and
the configured tag must be installed.

## Scope and safety

Default `office_demo@0.1.0` email, calendar, messaging, and reminders are simulated local records,
not integrations. PowerPoint and Excel creation produces real files only under
this agent's `workspace/files/`.

`--domain` can select another installed pack; `counter_demo@0.1.0` is only a
structural fixture. `--root` exposes experimental file writes, moves, and deletion through an
in-process path check, not an OS sandbox. Symlinks/junctions can defeat the
boundary. `--shell` is unrestricted PowerShell, and `--yolo` removes
confirmations. Use only disposable data. See [`../README.md`](../README.md).

The LLM verifier is fail-open and cannot certify correctness. Logs omit original
planner/verifier output and can retain sensitive task and file text.

Runtime memory is local and ignored by Git; no memory file is shipped.

`--small` changes the model used for planning and verification; it does not make
those calls correct. `--deep` is currently unreachable, and adapter fields are
not applied by Ollama.

## Hypothesis, not result

The intended hypothesis is that scaffolding effects may differ between the 1B
and 3B same-generation Llama 3.2 configurations. The 8B folder uses Llama 3.1,
so a 3B-to-8B difference cannot be attributed to size alone. No
speed-to-capability or production-suitability claim has been established.
