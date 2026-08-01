# Agent 3B — legacy development launcher

This folder requests `llama3.2:3b` from Ollama:

```json
{
  "name": "Agent 3B",
  "model": "llama3.2:3b",
  "num_ctx": 8192,
  "domain": "office_demo"
}
```

It is not part of the confirmatory or descriptive retained matrix and supports
no size, quality, latency, fit, safety or reliability claim. The retained
protocol resolves its Qwen3.5 candidates by immutable digest after Lenovo F0.

## Run for synthetic development

From the repository root:

```bash
python agents/3b/run_agent.py "List my simulated Wednesday meetings"
```

On Windows:

```powershell
cd agents\3b
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
memory is untrusted. `--small` changes development router roles but is prohibited
in the retained primary. `--deep` is unused and adapter fields are not applied.
See [`../README.md`](../README.md).
