# Brick Replacement Plan

## Status and authority

This is the canonical implementation and research plan for Brick. It supersedes
the former `S0`–`S18`, `G0`–`G1`, `R1`–`R5`, and `P0`–`P4` execution taxonomy.
Those names may remain in released changelog entries as historical descriptions,
but they no longer authorize or order current work.

The latest released version is `v0.11.1`. The native-Windows Lenovo F0 gate
passed, so `v0.4.0` records feasibility, and the native Windows ARM64 S4 gate
passed from candidate `0b8f77d` with `overall_status` pass, 461 passed, 0 failed
and `s4_skipped` 0, so `v0.5.0` records the production evidence store. Both
record instrument behaviour only. S1R is released as `v0.6.0`: parser, schema,
semantic-value, memory, completion, truncation, timeout and executor tests all
fail closed. B0 is released as `v0.7.0`: the fictional lead-follow-up slice
passes tenant, approval, concurrency, expiry, idempotency, ambiguous-delivery,
audit and no-network tests, and no generic package imports a Brix module.
S5 is released as `v0.8.0`. Its acceptance matrix covers every released
scenario and every required fixture class; candidate and tag CI are green.
S5W is released as `v0.9.0`: its 17-test adversarial matrix covers the startup
capability, Host/Origin, JSON/body, run/confirmation/reset, path/retention, and
real process-tree gates. S6G is released as `v0.10.0`; S6C is released as
`v0.11.0` with the shared native transport,
typed office contracts, compiled generated grader, mechanism-digested condition
registry, opportunity ledger, restartable disposable scheduler, raw-JSON lower
bound, descriptive ablations, telemetry, strict F0/runtime binding, and
model-free rules reference. The `v0.11.1` pre-D0 integrity repair versions the
generator as `office-generators/1.1.0`, reproducing 352 canonical fictional
instances with 352 distinct semantic structures and no repeated entity key or
surface. It provides fresh, balanced D0-A and D0-B cohorts of 44 paired cases
each, binds the ten disposable runs/four exposed instances in a canonical
ledger, and corrects the Brix domain/grader to `0.1.1`/`1.0.1`. D0/S7 through
S9 are unstarted, retained
execution is mechanically disabled, and no confirmatory effect estimate exists.

Release identity is authoritative in annotated Git tags and their bound
evidence, not in mutable current-status prose. S4 uses three commits/states:
tested candidate `C`; direct attestation-only release descendant `R`, tagged
`v0.5.0`; and an immediate docs-only descendant `D` that promotes changelog and
current-status wording after the tag exists. `D` is not part of `v0.5.0` and
does not alter its code or evidence. Consequently the tagged `R` intentionally
retains `C`'s candidate-scoped wording; the tag and
`evidence/s4/v0.5.0.json` are authoritative for whether S4 passed. They record
that it did.

The program targets three outputs, and they must not be conflated:

1. a reusable generic harness instrument; S4, S1R, S5, and S6C provide
   the evidence, typed execution, grading, condition, accounting, and scheduler
   components, while retained health policy and analysis remain later-stage work;
2. a replaceable, entirely synthetic Brix lead-follow-up demonstration; B0
   implements and tests the service layer plus a model-facing draft task, while
   an end-to-end operator demonstration remains unfinished; and
3. a valid, narrowly scoped same-model research result, which does not exist
   until the retained S9 experiment passes every preceding gate.

The Mac is limited to source work and offline tests. All live-model feasibility,
sentinel, development-timing, and retained measurements run on the Lenovo Yoga
with Snapdragon X Elite, 32 GB RAM, and native Windows 11 ARM64.

## Execution rules

1. Work on one release stage at a time.
2. Treat all current model scores as exploratory until S9 is sealed.
3. Never convert a runner, store, grader, or analysis failure into a model
   failure.
4. Never tune from retained outcomes.
5. Keep the generic harness free of Brix-specific imports and branches.
6. Use only fictional records and fake providers in the synthetic Brix layer.
7. Do not expose a general filesystem, shell, or skip-confirmation capability
   through a supported surface.
8. Commit evidence only through the marker-last protocol defined below.
9. A release version records implemented behavior; it does not waive an
   acceptance gate.
10. Each stage ends with tests, documentation reconciliation, an exact
    `CHANGELOG.md` entry, commit, SemVer tag, push, required green CI, and a stop
    for review. A tag is created only after that stage's mandatory evidence
    exists. For S4, substantive documentation and the pending changelog entry
    are frozen in `C`; `R` adds only the attestation; the tag makes the release
    authoritative; and docs-only `D` immediately promotes the pending prose.

## Release sequence

| Stage | Planned release | Deliverable | Mandatory exit gate |
|---|---:|---|---|
| F0/Q0 | `v0.4.0` | Quarantine unsafe capabilities and add reproducible Lenovo model, runtime, resource, and Windows storage probes. | All legacy escape paths fail before side effects, offline tests pass, and the native Lenovo F0 evidence satisfies every requirement below. |
| S4 | `v0.5.0` | Marker-last immutable attempt evidence, writer locking, exact resume, recovery, projection rebuilding, and failure taxonomy. | Crash-boundary, stale-artifact, corruption, duplicate, concurrent-writer, held-handle, and recovery tests pass on POSIX and native Windows ARM64. |
| S1R | `v0.6.0` | Typed tool schemas, conservative parsing, fail-closed completion, explicit context outcomes, scoped untrusted memory, and correct exception classification. | Parser, schema, semantic-value, memory, completion, truncation, timeout, and executor tests fail closed. |
| B0 | `v0.7.0` | Replaceable synthetic Brix lead-follow-up vertical slice with fake records and fake delivery. | Tenant, approval, concurrency, expiry, idempotency, ambiguous-delivery, audit, and no-network tests pass; generic packages import no Brix module. |
| S5 | `v0.8.0` | Strict, independently versioned outcome graders. | Positive, minimally wrong, harmful, stale, missing, extra, and corrupt fixtures pass for every scenario; grader failures yield `strict_success=null`. |
| S5W | `v0.9.0` | Harden the local Agent Lab control plane. | Token, origin, content-type, body-limit, run-bound confirmation, reset, path, stop, and orphan-process tests pass on Windows and POSIX. |
| S6G | `v0.10.0` | Independent versioned generators and split manifests. | Development, validation, sentinel, retained, and adversarial instances replay exactly and pass structural-overlap review. |
| S6C | `v0.11.0` | Shared native-tool transport, condition registry, opportunity ledger, standalone scheduler, telemetry, rules reference, and descriptive ablations. | Primary conditions share the exact model transport, schemas, validators, tasks, and budgets; every condition has an immutable mechanism digest. |
| Pre-D0 | `v0.11.1` | Fresh balanced D0 cohorts, immutable exposure accounting, and corrected Brix grading. | Each D0 cohort has 44 pairs/88 primary attempts with matched marginals and disjoint structures; all exposed-material reuse channels fail closed; all 352 rules-reference cases pass strictly. |
| D0/S7 | `v0.12.0` | Score-masked development timing run and frozen protocol, manifests, exclusions, order, analysis, and sample size. | Only instrumentation and resource fields were visible during D0; all retained inputs hash-match the tag before retained outcomes are inspected. |
| S8 | `v0.13.x` | Disposable sentinel across every retained condition. | There are zero instrument-invalid sentinel cells. Any instrument change creates a patch release and requires a complete sentinel rerun. |
| S9 | `v0.14.0` | Sealed primary experiment, bounded descriptive work, immutable evidence bundle, final report, and reproduction command. | A clean checkout reproduces all reported records, tables, intervals, and conclusions from validated committed bundles. |

## F0/Q0 — feasibility and quarantine

### Q0 capability boundary

Supported CLI, web, and configuration surfaces must reject all legacy forms of:

- `--root`;
- `--shell`;
- `--yolo`;
- `--with-domain`;
- `--with-office`;
- Agent Lab real-root, shell, and skip-confirmation options; and
- configuration or composition paths that expose the general filesystem/shell
  overlay.

Rejection occurs before output creation, model access, network access, or
mutation. Brick may still create attempt-owned Office artifacts through
domain-specific tools. Those artifact writers are not a general filesystem
capability.

The runnable legacy overlay source is deleted rather than relocated to another
importable package. Released history may describe it, but no supported module,
launcher, API, UI, or configuration may import or activate it. Tests enumerate
every former entry path and prove fail-before-side-effect behavior.

### Lenovo model feasibility

F0 runs only on the native Windows 11 ARM64 Lenovo. Record:

- exact Lenovo model, CPU, RAM, storage device and free space;
- Windows build, BIOS, Qualcomm driver, power mode, and execution backend;
- Python and Ollama architecture, version, executable path, and SHA-256 digest;
- the full model metadata and served digest for:
  - `qwen3.5:2b-q4_K_M`;
  - `qwen3.5:4b-q4_K_M`; and
  - `qwen3.5:9b-q4_K_M`;
- effective chat template, tool transport, loaded context, exact requested
  sampling-option payloads, process memory, latency, and warm throughput.

The exact ARM64 Ollama build is selected by this gate; it is not hard-coded in
advance. Pulling a tag is insufficient: the full digest and metadata must be
captured.

For each model, run three non-business native-tool conformance cases. Verify that
native tool calls and tool results round-trip without prompt-JSON emulation. Save
the exact accepted request payloads, returned native tool-call objects, tool
results, model metadata, effective chat template, loaded context, and
`think=false` responses.

### Option recognition (protocol v2)

Protocol v1 gated eligibility on the server rejecting the unknown option
`brick_f0_unknown_option` with a client error naming it. That tested an
assumption Ollama never made: its chat API defines `options` as a runtime
options object and does not promise strict unknown-key rejection. Ollama 0.32.5
logs a warning and continues, so the v1 gate failed on correct server behavior.
That candidate's bundle remains immutable and failed; the gate was corrected and
versioned rather than waived.

Protocol v2 proves recognition positively, per key. For every option name in the
frozen `option_contract`, the probe sends the complete valid production map with
only that key's value replaced by a deliberately invalid type. Recognition
requires a 4xx or 5xx response whose body names the key and states its declared
type. The exact status and body are recorded; Ollama 0.32.5 answers 500 with the
key and `float32` or `integer`. A complete valid request is required before and
after the invalid probes to prove both production-map acceptance and continued
server health.

The same invalid value is also sent under the unknown sentinel. Whether the
runtime accepts or rejects that unknown name is diagnostic only: the pinned
0.32.5 build accepts it, while another conforming build may reject unknown keys
globally. A key-specific, type-specific error for every real name is the
eligibility evidence. Unlike a generated-output differential, that check holds
at the frozen values — including the neutral `top_p=1.0`, `min_p=0` and
`repeat_penalty=1.0`, where changing a no-op cannot change any output.

This establishes per-key recognition and the declared value type for the exact
production option map. It does **not** prove the numerical behavioral semantics
of any sampler, and Brick makes no stronger claim. Output-differential
comparisons are retained only as descriptive diagnostics and never as acceptance
evidence.

Unknown-name behavior is recorded, and acceptance is reported as a typo hazard;
neither outcome gates the run. Brick therefore owns the request contract itself:
every chat request is validated before it reaches the network against exact
allowed keys, exact types (rejecting booleans masquerading as integers), finite
values, the exact frozen sampling values, `think=false`, `stream=false`, and no
missing or additional keys. A request Brick has not fully specified fails closed
instead of reaching the model.

If a candidate option is rejected, thinking cannot be disabled, or a frozen
option name is not recognized, revise and version the candidate protocol and
rerun all of F0 before D0.

F0 requires:

- a Lenovo-manufacturer host whose processor identifies as Snapdragon X Elite,
  running on AC power;
- the Windows AC overlay set to Best Performance, or an active High/Ultimate
  Performance scheme, with its GUID retained in the environment record;
- native ARM64 Python and Ollama processes;
- an unchanged, hash-matched Ollama listener plus at least one measured Ollama
  model-runner descendant during inference, each attested by full executable
  path, SHA-256 and PE architecture, native ARM64, and stable in identity for
  the duration of that model's probe. Attesting the listener alone is
  insufficient: an x64 runner under emulation beneath an ARM64 listener would
  otherwise satisfy the gate whose purpose is to establish native inference;
- a fixed local NTFS output volume outside OneDrive, with Microsoft Defender
  real-time protection and the Windows Search service running;
- at least 30 GiB free after model pulls;
- no out-of-memory failure, server crash, or request longer than ten minutes;
- peak committed memory no greater than 28 GiB;
- median warm throughput of at least 5 output tokens/second for 4B;
- median warm throughput of at least 3 output tokens/second for 9B; and
- a recorded backend classification rather than an assumption of GPU or NPU
  acceleration.

Failure of the 4B model stops the research design. Failure of 2B or 9B removes
only that descriptive system replication; no substitute model is introduced.
The three releases are not described as a controlled parameter-size series.

### Windows storage feasibility

F0 includes a disposable standalone implementation of the marker-last primitive.
It validates Windows behavior before the production S4 store is built; it is not
itself retained evidence or an S4 implementation.

Run the probe on a short local NTFS path such as `C:\BrickRuns`, outside OneDrive,
with Defender and indexing left enabled. It must complete:

- 200 prepare/commit/validate cycles using real `.pptx` and `.xlsx` fixtures;
- 50 injected process exits distributed across write boundaries;
- 10 held-handle cycles, alternating real `.pptx` and `.xlsx` files and exercising
  bounded Windows sharing/access retry; and
- zero invalid committed bundles.

The 50 exit cycles and 10 held-handle cycles are included in the 200-cycle total.
Q0 offline tests separately cover every disposable-probe write boundary,
prepared-bundle adoption, incomplete-bundle preservation, physical-directory
collision, tampering, unexpected members, and simulated retryable access errors.
The production-only concurrent-writer, duplicate-valid-candidate,
logical-collision, projection-rebuild, and full corruption matrix belongs to S4;
F0 does not claim to implement or validate that production store.

Hosted `windows-11-arm` CI is advisory because the runner is a preview service.
Required automation is Linux and Windows x64 CI plus the locally generated,
hash-pinned Lenovo ARM64 evidence bundle. The Windows x64 job must exercise the
live Win32 memory/filesystem signatures, current-process tree sampling, and one
real Office held-handle publication; it is supporting portability evidence, not
a substitute for the Lenovo gate.

### Lenovo command and `v0.4.0` attestation

Run F0 from a clean, pushed candidate commit `C`. Use native ARM64 Python, start
the native ARM64 Ollama server, connect AC power, select the recorded performance
power mode, and leave Defender and indexing enabled. First-time host setup steps
that satisfy these conditions, plus a failure-triage table, are in
[`bench/README.md`](bench/README.md#preparing-the-lenovo-host). From an ARM64
PowerShell in the repository root:

```powershell
git switch --detach <C>
git status --short
python -m pip install -r requirements-test.txt
python -m pytest -q
python -m bench.f0_probe fingerprint
python -m bench.f0_probe run --outdir C:\BrickRuns\f0 --pull
```

`git status --short` must print nothing. The final command must exit zero and
print `F0 PASS run=<RUN_DIR>`. Copy that exact printed path and independently
verify the committed bundle:

```powershell
python -m bench.f0_probe verify "<RUN_DIR>"
```

Verification must exit zero and print a summary whose `overall_status` is
`pass`. A failed 2B or 9B descriptive model remains explicitly `ineligible` in
that passing summary; it is not silently omitted or substituted. Do not rename,
edit, or reuse `<RUN_DIR>`. Verification re-hashes every manifested member and
recomputes pass eligibility from the protocol, repository, environment, storage,
pull, model, runtime, and memory records; it does not trust the summary status
alone.

A **failed** report is verified semantically too, not merely echoed back. Its
identity must recompute, its component statuses must agree with the underlying
records, every failing model must record a substantiating cause, and its
structured failure-code list must be recomputed from the on-disk component
records rather than accepted by shape. Early prerequisite failures and late
run-level exceptions remain committed, classifiable, and independently
verifiable. Every structured failure code is attributed to one of the domains
`environment`, `storage`, `instrument`, `protocol_contract`, or `model_runtime`.
Separating a protocol-contract fault from a model/runtime fault is what stops a
runner or transport defect from being recorded as a statement about a model.
Bundles written under protocol v1 remain verifiable for hash integrity and
identity only, and can never establish a passing gate.

Retain two copies of the exact bundle: the original short-path NTFS directory and
a release archive. Record the archive SHA-256, committed manifest SHA-256,
protocol SHA-256, run ID, candidate commit, model digests, and summary status in
`evidence/f0/v0.4.0.json`. Extract the archive into a fresh directory and run the
same `verify` command against the extracted run before release. Attach the
hash-matched archive to the `v0.4.0` GitHub release; do not commit the bulky raw
bundle into Git.

Use this PowerShell sequence without changing the committed run directory:

```powershell
$runDir = "<RUN_DIR>"
$archive = "$runDir.zip"
$extractRoot = "$runDir-extracted"
Compress-Archive -LiteralPath $runDir -DestinationPath $archive -CompressionLevel Optimal
Get-FileHash -Algorithm SHA256 $archive
Get-FileHash -Algorithm SHA256 (Join-Path $runDir "PREPARED.json")
Get-FileHash -Algorithm SHA256 (Join-Path $runDir "summary.json")
Expand-Archive -LiteralPath $archive -DestinationPath $extractRoot
$extractedRun = Join-Path $extractRoot (Split-Path $runDir -Leaf)
python -m bench.f0_probe verify $extractedRun
```

The archive path must not already exist, and `$extractRoot` must be a new empty
path. Retain the exact `Get-FileHash` output in the release preparation record.

The release tag may point to a metadata-only direct descendant `R` of tested
commit `C`, under this exact rule:

1. Run `python -m bench.f0_probe fingerprint` at `C` and record its commit and
   `behavior_tree_sha256`; the F0 bundle independently records the same values.
2. Between `C` and `R`, permit only:
   - creation of the release attestation under `evidence/<stage>/`;
   - promotion of the pending changelog entry and status-only release wording in
     **any tracked `*.md` file**; and
   - changing only the `[project].version` scalar in `pyproject.toml`.
3. Run the same `fingerprint` command at `R` and require byte equality with the
   behavior-tree digest recorded for `C`.
4. Mechanically review the complete `C..R` diff against the allowlist. Any other
   changed byte—including code, tests, workflow, dependency, task, prompt,
   protocol, or probe behavior—creates a new candidate commit and requires a full
   Lenovo F0 rerun.

5. Run required CI on `R`, then create an annotated `v0.4.0` tag that points to
   `R` and records `C`, the attestation-file Git blob ID, archive SHA-256, and
   behavior-tree SHA-256. Push the commit and tag. The tracked attestation must
   not claim to contain `R`'s commit hash: embedding a commit's own hash in one of
   its files is circular. The tag target supplies the authoritative `R` identity.

**The allowlist is stated structurally, never as a list of filenames.** An
enumerated file list rots: files added after it was written are silently outside
it, so a routine status update becomes an allowlist violation that demands a full
gate rerun. Two such gaps were found while executing `v0.4.0`. Because the
canonical digest excludes every `.md` path, no Markdown change can alter tested
behavior, so "any tracked `*.md` file" is safe by construction and cannot drift.
This does not relax the review: step 4 still requires confirming that the `.md`
changes are status-only prose, and that nothing outside `*.md`,
`evidence/<stage>/`, and the single `pyproject.toml` version scalar moved. A prose
assertion that the diff is "documentation only" remains insufficient.

**No test may pin the project version to a literal.** The allowlist permits
bumping the `[project].version` scalar between `C` and `R`, and the canonical
digest normalizes that line specifically so the bump is digest-neutral. A test
asserting a literal version would make the permitted change impossible: the only
way to satisfy it is to edit a test, tests are inside the behavior tree, and that
edit breaks the byte-equality requirement in step 3 and voids the F0 evidence. The
version is therefore asserted as well-formed `MAJOR.MINOR.PATCH` only. Release
identity is governed by the annotated tag, `CHANGELOG.md`, and this diff review —
never by a literal in a test. The same rule applies to any future assertion over
an allowlisted file: assert its *shape*, not the released value.

`evidence/f0/v0.4.0.json` must contain exactly the versioned release-attestation
schema, candidate commit `C`, candidate behavior-tree SHA-256, run ID, protocol
SHA-256, F0 `PREPARED.json` SHA-256, `summary.json` SHA-256 and status, archive
name/size/SHA-256, primary tag/digest/status, both descriptive tag/digest/status
records (with a null digest and explicit reason when a descriptive pull failed),
extracted-copy verification status, and verification timestamp. It must not
contain a guessed release commit, mutable URL, raw transcript, or machine-local
path. The annotated tag and GitHub release bind that tracked record to `R` and
the external archive.

The implemented canonical digest enumerates `git ls-files -z`, sorts the UTF-8
path bytes, excludes all `.md` paths and `evidence/f0/**`, and hashes every other
tracked path as: eight-byte big-endian path length, path bytes, eight-byte
big-endian content length, then content bytes. A symlink contributes its UTF-8
link target. Before hashing `pyproject.toml`, the single project-version line is
normalized to `version = "<release-metadata>"`; any missing or duplicate version
line fails. Because this digest deliberately excludes release prose, the separate
`C..R` diff allowlist remains mandatory. A prose assertion that the diff is
“documentation only” is insufficient.

## S4 — marker-last evidence store

### Layout

```text
runs/<run-id>/
  run.json
  run.lock
  attempts/<logical-hash>/<physical-uuid>/
    attempt.json
    initial-state.json
    final-state.json
    result.json
    grade.json
    actions.json
    transcript.md
    memory-delta.jsonl
    artifacts/
    PREPARED.json
    COMMITTED
  results.json
```

The production implementation lives in `harness/evidence.py`. The disposable F0
storage probe remains separate and is not imported as the production store.
The benchmark-facing operation encapsulates lock acquisition, recovery
classification, physical-candidate creation, producer invocation, publication,
and projection rebuilding; it never returns a "call the model" decision that a
caller could execute outside the lock.

`run.json` is an immutable `brick.evidence-run/1` document with exactly
`schema_version`, `run_id`, and `metadata`. `metadata` is a canonical JSON
object owned by the versioned run protocol. The file is created exclusively,
never rewritten, and its SHA-256 is recorded in every `attempt.json`.
`run.lock` is a persistent regular lock file: Brick never deletes or replaces
it. `run_id` is a portable ASCII path component: traversal, separators, control
characters, Windows device names, and trailing dots are rejected.

### Attempt identity and canonical JSON

`AttemptKey` is the strict `brick.attempt-key/1` object with exactly these keys
and nested keys:

```text
schema_version: "brick.attempt-key/1"
domain:
  name: string
  version: string
  content_sha256: lowercase 64-hex string
task:
  family: string
  version: string
generator_version: string
grader_version: string
model:
  tag: string
  digest: "sha256:" followed by lowercase 64-hex
condition:
  name: string
  version: string
  mechanism_sha256: lowercase 64-hex string
instance:
  id: string
  content_sha256: lowercase 64-hex string
ordered_subepisodes: list[string]
repeat: integer
sampling: object
opportunity_budget: object
prompt_sha256: lowercase 64-hex string
tool_schema_sha256: lowercase 64-hex string
```

Every string is nonempty, contains no U+0000–U+001F control character, and is
normalized to Unicode NFC before serialization. Object keys are normalized too,
and a collision after normalization is rejected.
`ordered_subepisodes` contains unique nonempty IDs in execution order and is
empty for an atomic attempt. `repeat` is a nonnegative integer; a boolean is not
an integer. `sampling` is a nonempty object and contains no JSON float at any
depth. `opportunity_budget` is a nonempty object whose values are nonnegative
integers; booleans are not integers. S4 preserves both maps exactly after NFC
normalization and never inserts defaults. The later versioned benchmark
protocol owns their exact key sets, ranges, and canonical decimal-string
grammar and must validate those before constructing the key. Fractional
sampling values are therefore stored as protocol-validated decimal strings,
not binary floats. Unsupported, missing, or additional fixed envelope keys,
duplicate or normalization-colliding JSON object keys, non-finite numbers, and
wrong structural types fail closed.

Canonical JSON bytes are UTF-8 with NFC strings, keys sorted lexicographically
after normalization, compact `,` and `:` separators, `ensure_ascii=false`, and
no trailing newline. The logical hash is the lowercase SHA-256 of those exact
`AttemptKey` bytes. Golden tests pin both bytes and digest across supported
Python versions and operating systems.

### Evidence envelopes

Every S4 JSON evidence file is decoded with duplicate-key rejection, must use
the same canonical encoding followed by exactly one LF byte, and has an exact
versioned envelope:

- `attempt.json` is `brick.evidence-attempt/1` with exactly
  `schema_version`, `run_id`, `run_sha256`, `logical_hash`, `physical_uuid`, and
  `attempt_key`;
- both state files are `brick.evidence-state/1` with exactly
  `schema_version`, `state_kind` (`initial | final`), and `payload`;
- `result.json` is `brick.evidence-result/1` with exactly `schema_version`,
  `execution_status`, `tool_status`, `failure_origin`, `failure`, `metrics`, and
  `diagnostics`;
- `grade.json` is `brick.evidence-grade/1` with exactly `schema_version`,
  `grader_status`, `candidate_decision`, and `diagnostics`; and
- `actions.json` is `brick.evidence-actions/1` with exactly `schema_version` and
  `actions`.

State payloads, action entries, failure details, and diagnostics remain opaque
canonical JSON at S4; `metrics` is an opaque canonical JSON object. Later
domain/runtime stages own their semantic schemas. `failure_origin` is `none |
model | runner | environment | operator`.
It disambiguates, in particular, a model-request timeout from a runner timeout
and an operator abort from a runner abort. `candidate_decision` is boolean only
when `grader_status=graded` and is otherwise null. It is deliberately not named
`strict_success`: strict success is derived only after committed-bundle
validation.

Status/origin compatibility is exact: `done` uses `none`;
`budget_exhausted` and `model_error` use `model`; `runner_error` uses `runner`;
`environment_unstable` uses `environment`; `timeout` uses `model` or `runner`
according to the timed operation; and `aborted` uses `operator` or `runner`
according to who terminated it. `failure` is null exactly when the origin is
`none` and is otherwise an object. A graded model-origin failure must have
`candidate_decision=false`.

An empty `memory-delta.jsonl` is allowed; otherwise every record is canonical
JSON terminated by one LF byte. CR, CRLF, a missing final LF, and blank records
are rejected, while Unicode line-separator characters inside a JSON string
remain string data. `transcript.md` is UTF-8. Artifact paths are normalized to
NFC before creation and use relative forward-slash form; validation rejects a
non-NFC member already present on disk. Absolute paths, empty or dot components,
`..`, backslashes, duplicate or case-insensitively colliding paths, and Windows
reserved device components are rejected. Every recursive artifact file is
declared in the prepared manifest.

`PREPARED.json` is `brick.evidence-prepared/1` with exactly `schema_version`,
`run_id`, `run_sha256`, `logical_hash`, `physical_uuid`, and `files`. `files` is
sorted by normalized path and every entry has exactly `path`, nonnegative
integer `size`, and lowercase 64-hex `sha256`. It declares every regular
candidate file except itself and `COMMITTED`.

### Commit protocol

1. Open the persistent `run.lock` and acquire its exclusive OS lock before
   recovery scanning, candidate creation, or model access. Use `flock` on POSIX
   and `LockFileEx` on Windows. Hold the same lock through producer execution,
   publication, and projection rebuilding. Process termination releases the OS
   lock; the lock file remains and is never deleted.
2. Create a never-reused UUID directory directly in its final physical location.
   An impossible-in-normal-operation UUID collision aborts fail closed; it never
   reuses or overwrites the existing candidate.
3. Execute only in that directory.
4. Write, flush, close, and hash every required evidence file.
5. Reject symlinks, junctions, reparse points, and unexpected files.
6. Write and flush `PREPARED.json`, then re-read it and verify every declared
   size and hash.
7. Publish by exclusively creating the empty regular file `COMMITTED`.
8. Re-open and validate the complete bundle before exposing it to readers.

No directory is renamed or replaced. A committed directory is immutable.
`results.json` is only a disposable projection rebuilt from valid committed
bundles.

### Recovery rules

- No physical directory means the attempt was not started.
- A directory without valid `PREPARED.json` is preserved as abandoned; resume
  creates a new physical attempt. Consequently, the no-rerun guarantee begins
  only at a complete, valid `PREPARED.json`; a process exit or write failure
  before that boundary may execute the producer again in a new UUID directory.
- A valid prepared bundle without `COMMITTED` is adopted by validation and marker
  creation. The model is not called again.
- A marker-present bundle with valid hashes is committed.
- A marker-present bundle with a missing or mismatched file is
  `instrument_invalid` and halts the run.
- More than one valid prepared or committed candidate for one logical key is an
  integrity violation and halts the run.
- A logical-hash collision halts the run.
- A missing or corrupt projection is rebuilt and never changes source evidence.

Retry only idempotent inventory reads, validation, and marker creation. Each
recovery/adoption operation and each commit/publication operation uses one
30-second monotonic deadline with delays `0, 50, 100, 200, 400, 800, 1600`
milliseconds and then two-second delays; one projection rebuild shares one
deadline across its complete candidate scan. Model execution is not charged to
a filesystem-publication deadline. Retry Windows access, sharing, and lock
violations. Existing-file errors require state inspection, not blind overwrite.
Exhaustion produces `publish_blocked` (or aborts a projection rebuild before
replacement) and never re-executes the model.

The durability claim is fail-closed recovery after process termination. Brick
does not claim lossless persistence through sudden power or storage-device
failure.

The S4 threat model coordinates cooperative Brick writer processes on one local
host. Brick never mutates a committed candidate and every reader revalidates its
manifest, sizes, hashes, file types, and identities. S4 does not provide digital
signatures, defend against an administrator or hostile local process rewriting
an entire internally consistent bundle, or claim protection against a
hard-link adversary.

### Status model

Keep instrument and model outcomes orthogonal:

- `record_status`: `prepared | committed | abandoned | invalid`;
- `execution_status`: `done | budget_exhausted | model_error | runner_error | timeout | aborted | environment_unstable`;
- `grader_status`: `graded | grader_error | not_run`;
- `tool_status`: `clean | had_errors`;
- `publish_status`: `committed | publish_blocked | corrupt`;
- `strict_success`: `true | false | null`.

These are reader-derived statuses, not fields that are mutated after
`PREPARED.json` is written. When no physical directory exists, there is no
record. An incomplete or invalid uncommitted candidate is `abandoned` with null
publication status; a valid marker-free candidate is `prepared`, with null
publication status until a current publication attempt exhausts its deadline
and derives `publish_blocked`; a valid marker-present candidate is
`committed/committed`; and a marker-present invalid candidate is
`invalid/corrupt` and halts the run. Status fields are nullable when no
enumerated state applies. Execution, grader, and tool status are available only
when their strict envelope validates.

`failure_origin=model` is an instrument-valid model/task failure and may be
graded false. `runner`, `environment`, and `operator` origins are
instrument-invalid and force derived strict success to null. A grader error or
not-run grader also forces null. `tool_status=had_errors` remains orthogonal
because a later recovery may still produce a correct final state. Only a fully
committed, currently validated, instrument-valid, graded record can have
non-null strict success.

### Projection

`results.json` is the canonical JSON `brick.evidence-results/1` object with
exactly `schema_version`, `run_id`, `run_sha256`, and `records`. Each record has
exactly `logical_hash`, `physical_uuid`, `attempt_key`, `record_status`,
`execution_status`, `grader_status`, `tool_status`, `publish_status`,
`failure_origin`, `strict_success`, `result`, and `grade`.

The projection contains only currently valid committed candidates, so its record
and publication statuses are always `committed`. Rows sort by logical hash and
then physical UUID. It contains no rebuild timestamp or other nondeterministic
field. A rebuild validates the complete candidate set first and halts without
publishing a partial projection on a corrupt committed candidate, duplicate
valid candidate, or logical collision. Missing, malformed, or stale projections
are replaced atomically from source evidence while the run lock is held.
`RunSession.inspect(key)` reports the aggregate `not_started`, `abandoned`,
`prepared`, `committed`, or `publish_blocked` recovery classification without
adopting a prepared candidate. Abandoned physical directories remain unchanged
on disk for forensic inspection. Invalid committed evidence raises and halts
instead of being returned as an ordinary record. None of these uncommitted or
invalid candidates enters `results.json`; the projection is never consulted to
decide resume.

### Native Windows ARM64 attestation

S4 cannot be released from hosted CI alone. From a clean, pushed candidate commit
on the native Windows ARM64 Lenovo, use a new short NTFS directory outside
OneDrive, leave Defender real-time protection and Windows Search enabled, and
run `bench/s4_attest.py run`. This is the only release-producing path: after a
passing preflight, the tool creates a previously absent
`s4-<candidate-prefix>-<unique-token>` report directory, owns the exact
complete-suite pytest invocation, removes `PYTEST_ADDOPTS`,
`PYTEST_PLUGINS`, and `PYTHONPATH`, disables third-party pytest-plugin autoload,
sets `BRICK_S4_NATIVE_REQUIRED=1`, and places both `pytest-tmp` and the JUnit
report under that short directory. It requires a clean candidate contained by a
remote-tracking ref before and after pytest, and exact-matches the JUnit
inventory to a second clean-environment collection from that candidate. Native
host, interpreter, volume, Defender, Search, and Developer Mode facts are
sampled before and after pytest and must remain identical and passing.
Symlink, junction/reparse, real Office held-handle, cross-process lock,
hard-process-exit recovery, duplicate/collision, corruption, stale-artifact, and
projection-rebuild cases must execute without a platform skip. Windows
Developer Mode must be enabled so the symlink fixtures execute.

Retain the raw JUnit report outside Git and commit
`evidence/s4/v0.5.0.json` as a strict `brick.s4-attestation/1` object with
exactly `schema_version`, `candidate_commit`, `command`, `report`, `host`,
`python`, `volume`, `services`, `tests`, `overall_status`, and
`verification_timestamp_utc`. Its nested objects have exactly:

- `report`: `name`, nonnegative integer `size`, and lowercase 64-hex `sha256`;
- `host`: `manufacturer`, `model`, `processor`, `os_build`, and
  `os_architecture`;
- `python`: `version`, `architecture`, and `executable_sha256`;
- `volume`: `root`, `filesystem`, `volume_id`, and boolean
  `outside_onedrive`;
- `services`: boolean `defender_realtime_enabled`,
  `windows_search_running`, and `developer_mode_enabled`; and
- `tests`: sorted `inventory`, nonnegative integer `passed`, `failed`, `skipped`,
  and `s4_skipped`.

`command` is the exact frozen ten-argument list emitted and executed by the
attestor, `candidate_commit` is lowercase 40-hex, and `overall_status=pass`
requires zero failed tests and `s4_skipped=0`. The attestor exclusively writes
only `evidence/s4/v0.5.0.json`; that write is the first intended worktree change
after the candidate run. Attach the hash-matched JUnit report to the `v0.5.0`
GitHub release. The annotated tag binds the tracked attestation to the release
commit. `bench/s4_attest.py verify` re-hashes the report and exact-matches its
inventory against the checked-out candidate. For S4, all version and protocol
metadata, staged changelog content, and candidate-scoped status prose must
already be present at candidate `C`; release commit `R` must be a pushed, clean
direct child whose complete `C..R` name-status diff is exactly the addition of
the regular file `evidence/s4/v0.5.0.json`. The verifier enforces that release
binding. It also requires annotated tag `v0.5.0` to point to `R` and to contain
exact `candidate_commit=`, `attestation_blob=`, and
`junit_sha256=` binding lines. Any other change after the tested candidate
requires a new native S4 run; an S4 platform skip leaves the gate pending.

Immediately after the annotated tag and GitHub release are verified, create
docs-only descendant `D` from `R`. `D` promotes the staged changelog entry to
`[0.5.0]` with the actual release date and updates current-status prose to
record the tag-authoritative result. Its complete `R..D` diff may modify only
already-tracked `*.md` files and must be reviewed as status-only prose. Do not
move the tag to `D`: `v0.5.0` remains bound to attestation-only `R`. Any code,
test, workflow, dependency, protocol, task, prompt, or evidence change belongs
to a later candidate rather than `D`.

## S1R and B0 — repaired runtime and replaceable layer

S1R introduces executable `ToolSpec` JSON schemas from which prompt documentation
and Ollama native schemas are derived. It validates primitive and nested types,
formats, ranges, additional properties, dates, times, and deterministic domain
invariants.

Parsing uses the native tool-call object for primary conditions. Any legacy JSON
extraction uses a string-aware decoder. Automatic argument repair is limited to
an explicit versioned alias table. It may not infer or fuzzy-rename a mutation
argument.

`CompletionStatus` is `complete | incomplete | unknown`. A malformed, timed-out,
contradictory, or budget-starved model verifier cannot establish completion.
Authoritative state and artifact postconditions decide whether required work
exists. Model verification may explain missing work but cannot authorize an
effect.

Memory is untrusted scoped input with provenance, tenant/subject scope, version,
expiry, validation, and explicit write policy. A malformed record is quarantined
rather than silently accepted or allowed to poison all loading.

After S1R, B0 adds `domains/brix_followup_synthetic`. It uses fictional actors,
tenants, leads, policies, addresses, and providers. The model may list due
follow-ups, inspect an assigned lead, propose a follow-up, inspect its proposals,
think, and finish. It may not approve, dispatch, choose another tenant, supply an
arbitrary recipient, bypass policy, or use model memory as business state.

Deterministic services own:

- actor and tenant authorization;
- due-date and eligibility rules;
- proposal versions, payload hashes, expiry, and revision;
- approval and dispatch revalidation;
- idempotency and concurrency;
- fake-provider delivery and reconciliation; and
- immutable audit records.

Delivery remains fake and approval-gated. An ambiguous fake-provider timeout
enters `delivery_unknown` and must reconcile before retry. Passing this slice
will demonstrate only the tested replaceable layering; it will not make the
workflow Brix-approved or deployed.

## S5 through S6C — valid tasks and conditions

### Graders

Every scenario has a fixed, versioned rubric over immutable attempt evidence.
Strict whole-task success is primary. A harmful, unauthorized, stale, missing,
extra, or incorrect effect makes strict success false. Grader exceptions,
unreadable evidence, or inconsistent manifests produce `strict_success=null`.

Fixtures must include a correct case and minimally wrong variants for every
check, including exact file identity, row/column association, slide structure,
required source reads, unintended actions, corrupted files, and stale artifacts.
Partial checks remain diagnostics with fixed denominators.

### Task generators

Use 11 fixed scenario-family generator distributions, combining the dependent
memory write/use episodes into one family. Instances vary task structure,
policies, state, valid action sequences, wording, entities, dates, conflicts, and
distractors. Renaming entities or changing only a seed inside one template is not
an independent instance.

One learning-family case is one logical attempt containing exactly two ordered
subepisodes: first store a generated preference, then solve a later task that
requires using it. The two subepisodes share one isolated memory scope and one
14-call/4096-generated-token ledger; neither budget resets between subepisodes.
Their prompts, state boundaries, actions, memory delta, and completion statuses
remain separately identifiable inside the one immutable attempt bundle. Both
subepisodes must strictly succeed for the case to succeed. A valid model failure
or budget exhaustion in either makes the case false; an instrument failure in
either makes the entire case null. No memory crosses case or condition
boundaries. Consequently each learning case remains one model attempt in the
440-primary and 662-default-maximum counts.

Each instance records its generator version, structural template, policy family,
seed, initial state, required and forbidden effects, and content digest.
Development, validation, sentinel, retained, and adversarial manifests do not
share entities or structural templates. Held-out retained manifests remain
unavailable during prompt and grader tuning.

### Shared native transport

`native_tools` and `harness_full` use the same:

- Qwen3.5 4B digest;
- Ollama native function-call endpoint and chat template;
- tool names, schemas, ordering, and structured tool-result transport;
- deterministic business validators and state transitions;
- initial state, task instance, and hidden grader; and
- safety and authorization rules.

`native_tools` receives ordinary typed validation and structured error feedback.
`harness_full` adds only versioned planning, scoped untrusted memory,
known-alias recovery, duplicate suppression, observation management, and
completion guarding. Hidden grader logic is unavailable to both.

The primary opportunity ledger counts all driver, planning, and completion calls.
Both conditions receive:

- context `8192`;
- `think=false`;
- temperature `1.0`;
- `top_p=1.0`;
- `top_k=20`;
- `min_p=0`;
- presence penalty `2.0`;
- repeat penalty `1.0`;
- maximum 700 generated tokens per request;
- maximum 4096 generated tokens per attempt; and
- maximum 14 total model calls per attempt.

A deterministic base seed is derived from the frozen protocol digest and
instance ID and reused for the paired conditions. Each physical request records
the effective seed and sampling options.

The primary interpretation is deliberately conservative: does the full harness
pay for its own planning and verification overhead under the same end-to-end
opportunity limits? Equal calls are not described as equal FLOPs, tokens,
latency, or energy. Reports show the success/call/token/model-time/wall-time
frontier.

`raw_json` is a descriptive lower bound. `rules_reference` consumes structured
instances and is reported separately as an architecture-selection reference. If
rules are more accurate and cheaper for a family, the conclusion recommends a
deterministic workflow for that family.

## D0/S7 — frozen research protocol

The current source contains the pre-run S7 enforcement layer: deferred D0
grading, a score-masked operator summary, exact reconstruction of every attempt
identity, a marker-last runtime-only sample decision, a direction-blind
floor/ceiling audit, role-aware equal-action accounting, and pinned analysis.
This implementation is not evidence that D0 passed. D0 remains unexecuted until
the exact clean candidate receives required CI, and retained execution remains
disabled.

### Primary question and estimand

> For the 11 fixed synthetic Brick task-family generator distributions, does
> `harness_full` improve strict whole-task success over a competent
> `native_tools` implementation on the pinned Qwen3.5 4B system under the same
> end-to-end opportunity budget?

The estimand is:

```text
Delta = (1 / 11) * sum(family_mean(harness_success - native_success))
```

The 11 families are fixed strata. Conclusions apply only to their frozen
generator distributions. They do not establish performance over all office work,
unseen workflow families, frontier models, production Brix operations, or a
causal parameter-size law.

### Sample-size rule

D0 runs 44 development pairs on 4B with efficacy fields masked. Operators may
inspect instrumentation validity, resource use, calls, tokens, and elapsed time,
but not strict success, component scores, directional discordance, or
family-level effects.

Choose the retained sample using runtime only:

- if `median valid attempt wall time * 440 * 1.25 <= 48 hours`, freeze 20
  instances per family: 220 pairs and 440 model attempts;
- otherwise freeze the preregistered fallback of 12 instances per family: 132
  pairs and 264 model attempts.

The default is designed for approximately 81.5% power for the sharp
pairwise-exchangeability diagnostic described below, for a 20-point paired effect
at worst-case discordance `q=1`. The fallback provides approximately 81.6% power
for that diagnostic at a 25-point effect and `q=1`. These are not power claims for
the weak-null equal-family estimand, the bootstrap interval, or the joint positive
claim gate. Publish the complete sensitivity curve.

No observed efficacy outcome may influence the sample-size choice.

### Primary analysis

- outcome: strict whole-task success;
- contrast: 4B `harness_full` minus 4B `native_tools`;
- diagnostic: two-sided exact paired sign-flip test at `alpha=0.05` under the
  sharp pairwise-exchangeability null;
- estimand interval: predeclared 95% within-family percentile bootstrap using
  20,000 draws and seed `20260729`;
- reporting: pooled equal-family-weight effect, all 11 family effects, and
  leave-one-family-out sensitivity.

A positive claim requires all three:

1. `Delta > 0`;
2. sharp-null diagnostic `p < 0.05`; and
3. the bootstrap 95% lower bound is greater than zero.

For the diagnostic, retain each observed nonzero paired difference and enumerate
its independent sign reversals; the two-sided p-value is the probability of an
absolute signed sum at least as large as observed. With complete equal family
allocation this calculation is numerically equivalent to exact McNemar. It is
exact only for the sharp pairwise-exchangeability null. Independence of generated
cases and equal allocation do not make it an exact test of the weaker null
`Delta=0` when family-specific effects differ. AB/BA execution order does not
randomize condition identity. The diagnostic is therefore an additional
predeclared hurdle, not the inferential justification for the equal-family
estimand.

The interval is the inferential gate for `Delta`. For every bootstrap draw,
process families in frozen family-ID order; within each family, sample that
family's `N` paired case differences with replacement, compute its sampled mean,
then average the 11 sampled family means. Use
`numpy.random.Generator(numpy.random.PCG64(20260729))`, generate indices
draw-major then family-major from cases sorted by instance ID, and pin the NumPy
version in the D0/S7 analysis environment. The endpoints are the 0.025 and 0.975
Hyndman–Fan type-7 quantiles of the 20,000 `Delta` draws. A constant or otherwise
degenerate family remains in every draw and is neither dropped, jittered, nor
reweighted; a point-mass distribution produces equal endpoints.

Golden tests must pin the sorted input fixture, first 100 generated index vectors,
exact diagnostic p-values, all-family and leave-one-family-out point estimates,
and final type-7 endpoints. A clean checkout must reproduce their byte-identical
serialized values with the pinned analysis environment.

### Bounded descriptive matrix

Run these only after the primary is complete and sealed:

| Analysis | Cases | Conditions | Model attempts |
|---|---:|---:|---:|
| 2B system replication | 2 per family | native/full | 44 |
| 9B system replication | 2 per family | native/full | 44 |
| `raw_json` lower bound | 2 per family | raw only | 22 |
| Three harness ablations | 2 per family | one per ablation | 66 |
| No-memory learning ablation | 2 learning-family cases | one | 2 |
| Equal-action-opportunity sensitivity | 2 per family | native/full | 44 |

The default retained maximum is 662 model attempts: 440 primary plus 222
descriptive attempts. A failed F0 secondary model removes its 44 attempts.
`rules_reference` is model-free and runs on applicable primary cases.
Each no-memory ablation case still contains both ordered subepisodes in one
logical attempt; only the scoped memory bridge is disabled, so its two listed
cases remain two model attempts.

All secondary results are descriptive. They receive no confirmatory p-values,
Holm tests, or “mechanism does not matter” conclusion. There is one stochastic
draw per retained cell, so this milestone makes no within-instance repeatability
or pass-at-\(k\) claim. It reports the success distribution across independently
generated cases under the frozen sampling policy.

## S8/S9 — sentinel and retained execution

A plain Python or PowerShell command owns the queue, run lock, heartbeat, health
checks, evidence commits, logs, and resume. Execution does not depend on an
active Codex session.

The primary runs in `N` balanced waves, where D0 freezes `N` to 20 or 12. Each
wave contains one instance from all 11 families under both conditions. Paired
conditions run contiguously. AB/BA order is counterbalanced across families and
waves.

Reboots are allowed after a fixed warm-up only when code, configuration, tasks,
graders, model digests, Ollama binary, OS build, driver, backend, and power-mode
fingerprints remain identical. Any fingerprint change ends the run. Results from
different environment strata are never pooled.

Record per request and attempt:

- prompt, output, and other exposed token counts;
- model and wall time;
- calls by role, retries, repairs, approvals, and action opportunities;
- model load/backend state and warm throughput;
- process memory and other available resource telemetry; and
- all environment and protocol digests.

Three consecutive requests below 70% of the F0 warm-throughput baseline trigger
a cooldown and warm-up check. Persistent degradation stops the scheduler as
`environment_unstable`. This decision uses performance telemetry only, never
task outcome.

One logical cell receives at most one preregistered retry for an instrument
failure. A valid task failure is never rerun. Both physical records remain
auditable.

### Incomplete-run rule

- If any required primary pair remains invalid or missing, the primary is
  `INCOMPLETE/DESCRIPTIVE`.
- An incomplete primary reports planned/completed coverage and failure reasons,
  but no confirmatory p-value, interval claim, or selected subset.
- Honest publication of that status does not complete the research milestone or
  answer the primary question.
- A fingerprint change during an incomplete primary requires a new complete run;
  strata are not combined.
- A sealed complete primary remains reportable if a later descriptive phase is
  interrupted.
- No post-hoc subset can replace the frozen primary.

## Manual boundary and future work

The user must only provide Lenovo access, approve required installer/UAC
prompts, authenticate GitHub if credentials are absent, keep the machine on AC
power, and free disk space if required. Agents can prepare and launch the
standalone commands, but the commands—not an interactive agent session—own long
runs.

Real Brix discovery, provider integration, approved-data shadow evaluation,
pilot deployment, external-benchmark integration, and model fine-tuning are
outside this milestone. They may be considered after `v0.14.0`; none is needed
to manufacture a positive internal result. Broader claims require independently
developed domains or a suitable pinned external benchmark.

## Stop conditions

Stop the affected stage if:

- the 4B model fails F0;
- a supported path can activate general filesystem, shell, or skip-confirmation
  behavior;
- a committed bundle fails manifest or hash validation;
- more than one valid candidate exists for a logical attempt;
- an attempt can inherit state, memory, or artifacts;
- a grader failure can become a model score;
- primary conditions differ in native transport, schemas, validators, hidden
  information, or opportunity budgets;
- generator splits share a retained structural template;
- a sentinel produces any instrument-invalid cell;
- environment identity changes during a retained run;
- a protocol or instrument change is proposed after retained outcome inspection
  without a new version and complete rerun; or
- a partial primary is proposed as confirmatory evidence.

A null result, a rules-dominant result, or omission of an incompatible secondary
model still completes the research honestly. Manufacturing a positive result
does not.
