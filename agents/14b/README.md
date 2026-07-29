# Agent 14B — intended experimental configuration

This folder configures the research harness to request `qwen2.5:14b` from
Ollama.

```json
{
  "name": "Agent 14B",
  "model": "qwen2.5:14b",
  "num_ctx": 8192,
  "domain": "office_demo"
}
```

This changes model family as well as parameter count relative to the Llama
folders. Architecture, training data, and tokenizer are inherent confounds, so
it is not a clean size-only comparison. Exact quantization, model digest, and
serving runtime must additionally be pinned as controlled provenance.

No repeated, versioned results are committed that establish accuracy, latency,
reliability, memory fit, or repair behavior.

## Run

From the project root:

```bash
python agents/14b/run_agent.py "List my simulated Wednesday meetings"
```

On the original Windows lab setup:

```powershell
cd agents\14b
.\run.ps1 "List my simulated Wednesday meetings"
```

`run_agent.py` is a thin shim over the shared runner. `run.ps1` hardcodes the
original lab Python path. Direct invocation uses the root package manifest and
pinned requirements; the transitive lock has no hashes and installation may
need network/cache access. Ollama and this model tag must be available locally.

## Scope and safety

Default `office_demo@0.1.0` email, calendar, messaging, and reminders are simulated. They do not
contact real systems. PowerPoint and Excel files are real but are created only
under this agent's `workspace/files/`.

`--domain` can select another installed pack; `counter_demo@0.1.0` is only a
structural fixture. `--root`, `--shell`, and `--yolo` inherit the unsafe experimental behavior
documented in [`../README.md`](../README.md): lexical rather than OS-enforced
containment, symlink/junction gaps, unrestricted PowerShell, and optional removal
of confirmations. Do not use real business data.

The verifier is fail-open; logs are incomplete and may contain sensitive text.
The configured `deep` role defaults to the same tag here but is never invoked.
Adapter fields are not applied by Ollama.

Runtime memory is local and ignored by Git; no memory file is shipped.

## Hypothesis, not result

The intended hypothesis is that this configuration provides a higher-capacity
non-Llama comparison. It cannot establish a size trend by itself. Any evaluation
must report the family change and pin the exact model digest and runtime.
