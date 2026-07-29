# Agent 32B — intended experimental configuration

This folder configures the research harness to request `qwen2.5:32b` from
Ollama.

```json
{
  "name": "Agent 32B",
  "model": "qwen2.5:32b",
  "num_ctx": 8192,
  "domain": "office_demo"
}
```

This is a Qwen condition, whereas the 1B–8B folders use Llama. Differences
cannot be attributed to parameter count alone. No committed repeated results
establish its accuracy, latency, reliability, hardware fit, or repair behavior.

## Run

From the project root:

```bash
python agents/32b/run_agent.py "List my simulated Wednesday meetings"
```

On the original Windows lab setup:

```powershell
cd agents\32b
.\run.ps1 "List my simulated Wednesday meetings"
```

`run_agent.py` is a thin shim over the shared runner. `run.ps1` hardcodes the
original lab Python path. Direct invocation uses the root package manifest and
pinned requirements; the transitive lock has no hashes and installation may
need network/cache access. Ollama, sufficient local resources, and the
configured model tag are prerequisites the runner does not validate in advance.

## Scope and safety

The default `office_demo@0.1.0` world is simulated. Email, calendar, chat, and reminder calls
only mutate local state. Generated PowerPoint and Excel files are real and live
under this agent's `workspace/files/`.

`--domain` can select another installed pack; `counter_demo@0.1.0` is only a
structural fixture. Real-file and shell flags inherit the serious limitations in
[`../README.md`](../README.md). The file boundary is not an OS sandbox,
PowerShell is not confined to the root, and confirmations can be disabled.
Never use real Brix or member data.

The LLM verifier fails open and does not certify outcomes. Logs are incomplete
and may retain sensitive content.

Runtime memory is local and ignored by Git; no memory file is shipped.

The default router calls its unused `deep` role `qwen2.5:14b`, which is smaller
than this base configuration. No code dispatches that role. Passing `--deep`
still enables tier/router mode and its telemetry, but the selected deep model is
never called. Adapter fields are recorded but not applied by Ollama.

## Hypothesis, not result

The intended hypothesis is that this configuration can serve as a higher-capacity
Qwen reference condition. That hypothesis requires an exact model digest,
runtime provenance, repeated trials, and explicit treatment of the family
confound; the folder alone supports none of those conclusions.
