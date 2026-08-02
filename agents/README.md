# Per-model development launchers

These folders are thin legacy launch configurations over
[`_shared/run_agent.py`](_shared/run_agent.py). They are not separate agent
implementations, production assistants, retained benchmark conditions, or
performance claims.

| Folder | Configured development tag | Family |
|---|---|---|
| `1b/` | `llama3.2:1b` | Llama |
| `3b/` | `llama3.2:3b` | Llama |
| `8b/` | `llama3.1:8b` | Llama |
| `14b/` | `qwen2.5:14b` | Qwen |
| `32b/` | `qwen2.5:32b` | Qwen |

The folders mix families and Llama generations and do not form a size curve.
None participates in the retained protocol. The confirmatory candidate is
Qwen3.5 4B, resolved by immutable digest after Lenovo F0. Qwen3.5 2B and 9B are
descriptive system replications only.

The latest release is `v0.6.0` (S1R repaired runtime), preceded by `v0.5.0` (S4 evidence store) and `v0.4.0` (F0/Q0 feasibility). The native Lenovo F0 feasibility gate passed;
that records host feasibility only and is not a benchmark result. Annotated tags
and bound evidence are release-authoritative; see the `C`/`R`/`D` lifecycle in
[`../PROJECT_SETUP.md`](../PROJECT_SETUP.md).

## What the development launchers run

Each launcher loads its configured synthetic domain unless `--domain NAME`
selects another installed pack:

- `office_demo@0.1.0`: fixture inbox/calendar/messaging/reminder state plus real
  `.pptx` and `.xlsx` files inside the agent workspace;
- `counter_demo@0.1.0`: a structural wiring fixture.

No real email is sent, reminder delivered, calendar reserved, or Brix system
contacted. Generated Office files are real local artifacts.

## Requirements and launch

The released runtime supports Python 3.9–3.13. A local Ollama server at
`127.0.0.1:11434` and the requested development tag are required.

From the repository root:

```bash
python agents/8b/run_agent.py "List my simulated Wednesday meetings"
```

The per-agent `run.ps1` files discover `python` or the Windows `py` launcher and
honor the `PYTHON` override.

## Supported flags

The development CLI supports domain selection, routing diagnostics and a
positive call ceiling. Run `--help` for the exact current set. Unknown flags,
missing values and non-positive call limits fail before model construction.

Q0, released in `v0.4.0`, rejects legacy:

- `--root`;
- `--shell`;
- `--yolo`;
- `--with-domain`; and
- `--with-office`.

They fail before output creation, model access, network access or mutation.
There is no supported general filesystem or PowerShell overlay. Domain-owned
Office artifact generation remains confined to synthetic workspaces.

## Harness and audit limits

The released development harness still has key-only validation, lenient parsing
and fuzzy repair, a model-authored plan, a fail-open verifier, incomplete
transcripts, untrusted keyword memory and limited context handling. These are
current defects scheduled for S1R, not safety controls.

An accepted `done` means the loop stopped; it does not mean the task was
correct. Logs, state, tool arguments and memory may contain sensitive text and
are plaintext. Use synthetic data only.

## Router and adapter status

The legacy router maps fixed roles to tags. Its `deep` role is not dispatched,
and adapter values are telemetry rather than applied Ollama adapters. The
retained primary prohibits role routing: the same pinned 4B model serves every
driver, planning and completion call, and all calls consume one opportunity
ledger.

## Persistent development files

`office_demo` preserves legacy per-agent paths:

- `workspace/state.json` and `workspace/files/`;
- `memory/memory.jsonl`;
- `logs/run_NNN.json`; and
- `logs/model_calls.jsonl` in tier mode.

Other domains use:

```text
agents/<size>/runtime/<domain>/<version>/{workspace,memory,logs}/
```

These files are development state, not immutable retained evidence. Writes are
not uniformly transactional or concurrency-safe. S4 introduces a separate
marker-last evidence store for benchmark attempts.
