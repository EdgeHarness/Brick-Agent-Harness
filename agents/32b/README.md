# Agent 32B — legacy development launcher

This folder requests `qwen2.5:32b` from Ollama:

```json
{
  "name": "Agent 32B",
  "model": "qwen2.5:32b",
  "num_ctx": 8192,
  "domain": "office_demo"
}
```

It is not part of the confirmatory or descriptive retained matrix and supports
no size, quality, latency, fit, safety or reliability claim. Qwen2.5 is not the
Qwen3.5 family used by the candidate protocol. The retained candidates are
resolved by immutable digest after Lenovo F0.

## Run for synthetic development

From the repository root:

```bash
python agents/32b/run_agent.py "List my simulated Wednesday meetings"
```

On Windows:

```powershell
cd agents\32b
.\run.ps1 "List my simulated Wednesday meetings"
```

Ollama must be local and the configured tag installed. The launcher is a thin
shim over the shared development runner.

## Scope and safety

`office_demo@0.1.0` uses fixture state. Email, chat, calendar and reminder
effects are simulated. PowerPoint and Excel tools create real files inside this
agent's synthetic workspace.

Q0, released in `v0.4.0`, rejects legacy `--root`, `--shell`, `--yolo`,
`--with-domain` and `--with-office` forms before side effects. There is no
supported general filesystem or PowerShell capability. Use synthetic data only.

The released verifier is fail-open, logs are incomplete, and model-authored
memory is untrusted. The `deep` role is unused and adapter fields are not applied
by Ollama. See [`../README.md`](../README.md).
