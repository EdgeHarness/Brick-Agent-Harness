# Focused recovery successor: v0.13.6 preauthorization record

## Status

`v0.13.6` is a pending successor, not an authorization, run, result, release,
or benchmark claim. It may be authorized only after its exact committed tree is
tagged, all preflight checks pass, and the marker-last authorization is created.
Until then, no command below is permission to execute model calls.

This document records the operational boundary for the successor implemented by
`bench.focused_recovery_successor` and
`scripts/run-focused-recovery-successor.ps1`. The canonical JSON protocol and
its eventual marker-last authorization are the machine-enforced authorities.

## Immutable v0.13.5 history

The v0.13.5 focused follow-up root is sealed historical evidence. It is
read-only and must never be resumed, repaired in place, renamed, copied into a
new run, or supplemented with late cells.

- The three-family B1a fallback lane sealed successfully. It is the only
  completed prospective directional lane from that program.
- B1b terminated after a source-proven Qwen tool-call parser event. It left
  exactly 24 scheduled cells never started.
- B2 never started.

The event was not a generic host outage or a deadline decision. The exact
observed Qwen/Ollama parser signature was:

```text
XML syntax error on line 11: element <parameter> closed by </function>
```

The v0.13.6 classifier recognizes that exact signature only. It does not
reclassify arbitrary HTTP 500s, arbitrary XML errors, or future parser changes
as model-origin failures.

## Frozen successor scope

One future marker-last authorization binds two separate score-masked evidence
stores and an analysis embargo:

1. `B1b_recovery` executes exactly the 24 v0.13.5 B1b cells that never started.
   It preserves their old logical-cell identities, conditions, trial index,
   seeds, order, and task content.
2. `B2_repeatability` executes the byte-identical 240-cell frozen v0.13.5 B2
   schedule. It is a same-context, fresh-seed repeatability lane, not an
   independent task replication.

B2 is mandatory after B1b reaches any validated terminal state, including an
incomplete terminal state. No efficacy field may be computed, printed, unmasked,
or reported until both lanes have independently validated terminal markers.
The supervisor owns no schedule, root, run identifier, label, Python override,
fallback selection, or outcome-based branch.

### Marker-last recovery boundary

A JSON file without its `.complete` marker is not published evidence. The fixed
core may complete that one state only when it re-derives the exact artifact,
validates its bound inputs, and confirms byte identity before writing an empty
marker. The supervisor never trusts JSON-only evidence directly. A marker with
no JSON, a nonempty marker, a non-file marker/path, conflicting terminal
artifacts, or JSON that differs from the exact rederivation fails closed.

The old B1b evidence is read only. The one parser-affected repeat-0 record is
handled only by the predeclared exact classifier; the old repeat-1 attempt is
kept for provenance and operational cost, not efficacy. No other old record is
rewritten.

## Interpretation boundary

The successor emits distinct, nonpooled outputs:

- recovered B1b is a recovery component sensitivity;
- the recovered six-family result is a post-outcome, nonconfirmatory
  sensitivity;
- B2 is same-context repeatability evidence, not an independent replication;
- B1a plus B2 is a secondary two-trial same-context summary.

None of those successor outputs may alter or extend the old B1a directional
lane. There is no pooled headline, new confirmatory claim, family removal,
outcome-triggered extension, or inference from a terminated lane.

The experiment remains a comparison of `harness_full` with the competent
`native_tools` baseline on the pinned Qwen3.5 4B system, native tools, fixed
synthetic Office tasks, and the shared opportunity budget. `native_tools` is
not a bare model. This does not evaluate Sharvin's Llama 8B Brix product,
llama.cpp backend, product web UI, fine-tuning, or production harness.

## Pending operational commands

These commands are stable interfaces but are **pending** the v0.13.6 freeze,
annotated tag, clean CI/preflight, and authorized issue metadata. Do not run
them early.

```powershell
# Pending: writes only the fixed-path preflight and authorization; starts no cell.
powershell -NoProfile -ExecutionPolicy Bypass -File `
  scripts/run-focused-recovery-successor.ps1 `
  -Mode Authorize `
  -IssuedAt "<ISO-8601 timestamp with offset>" `
  -Issuer "<authorized issuer>"

# Pending: validates the fixed authorization, then runs B1b recovery and B2.
powershell -NoProfile -ExecutionPolicy Bypass -File `
  scripts/run-focused-recovery-successor.ps1 `
  -Mode Run
```

The second command is resumable only through existing validated marker-last
artifacts. A JSON-only artifact can be completed only by its exact bound core
writer/validator; marker-only, nonempty-marker, mismatched, or nonterminal
failure states stop closed. It is not valid to pass alternate paths, schedules,
run IDs, model settings, labels, or fallback choices to the supervisor.
