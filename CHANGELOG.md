# Changelog

All notable changes to this repository are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions use
`MAJOR.MINOR.PATCH`.

While the major version is `0`, a minor bump may contain breaking changes to
internal Python interfaces. Nothing in this repository is a stable public API.

**A released version is not gate acceptance.** Versions record repository
changes only. The active gates and current status live in
[`PROJECT_SETUP.md`](PROJECT_SETUP.md). No entry below should be read as evidence
that the research instrument is valid or that any measured effect exists.

## [Unreleased]

B0 is in progress. It is not released and no gate has passed.

### Added

- `domains/brix_followup_synthetic/services.py`, the deterministic services for
  the fictional lead-follow-up slice. Every record is fictional, every address is
  a reserved `.example` domain that cannot resolve, and the module imports nothing
  capable of reaching a network — a test walks its import graph to assert that
  rather than trusting the claim.
- The division of labour is the substance of the stage. The model may list due
  follow-ups, inspect an assigned lead, propose a follow-up and inspect its
  proposals. It may not approve, dispatch, cross a tenant boundary, choose a
  recipient, or bypass a policy. Those live in deterministic code, so a model that
  asks for them is refused by the instrument rather than trusted not to ask. That
  matters for the benchmark specifically: if a model could dispatch, a harness
  that merely asked more persuasively would score higher, and the measured effect
  would be persuasion rather than task completion.
- **Approval binds a payload hash, not a proposal id.** Approving "proposal 3"
  and then dispatching whatever proposal 3 now says would let a revision slip
  through an approval granted for different content, so approval names the exact
  bytes and dispatch revalidates the hash still matches. A revision supersedes an
  earlier draft rather than editing it.
- **An ambiguous provider timeout is not a failure.** It enters
  `delivery_unknown`, which must be reconciled before any retry, because retrying
  a send whose outcome is unknown is precisely how a duplicate delivery happens —
  two messages to one client. Reconciliation asks the provider what actually
  occurred and either marks delivery or returns the proposal to approved without
  resending.
- Cross-tenant refusals are deliberately indistinguishable from
  unknown-record refusals: revealing that a lead exists in another tenant is
  itself a cross-tenant leak.
- Recipients derive from authoritative lead state, never from model input, so a
  model cannot redirect a message by asking. Dispatch is idempotent under
  concurrency: eight racing dispatches deliver exactly once, and eight racing
  approvals grant once. The audit log is append-only and its accessor returns
  copies, so history cannot be edited through it.

## [0.6.0] — 2026-08-02

S1R, the repaired typed runtime. Every item in the stage's exit gate has passing
tests, measured item by item rather than asserted: parser 33, schema 50,
semantic-value 6, memory 36, completion 35, truncation 7, timeout 3, executor 31.
Offline suite 680 passed, 3 skipped on native Windows ARM64, with required Linux
Python 3.9–3.13 and Windows x64 CI green.

S1R needs no native attestation. Unlike S4, its exit gate is that the named tests
fail closed, which the offline suite and required CI establish.

This release records instrument behaviour only. It is not a benchmark result, no
measured effect exists, and B0 through S9 are unstarted.

### Added

- `harness/schema.py`, executable tool-argument schemas. The released registry
  described parameters as prose -- `{"name": ("a date string", True)}` -- and
  validated only that required keys were present, so `{"count": "seven"}` and
  `{"count": true}` both reached the executor. The resulting type error surfaced
  as an executor exception, which is recorded on a different status axis than a
  model error, so a malformed argument could be misattributed as an instrument
  fault. One `ToolSchema` now yields, by derivation rather than duplication:
  validation of an argument mapping, the Ollama native function-call schema, and
  the prompt documentation. Deriving all three from one object is the point:
  prompt text that disagrees with the validator teaches a contract the runtime
  will reject, and a native schema that disagrees with it lets the server accept
  what Brick refuses.
- Validation is closed by construction. Unknown properties are rejected because
  `additionalProperties` defaults to false; `bool` never satisfies `integer` or
  `number` despite Python's `bool` subclassing `int`; `int` satisfies `number`
  but a float never satisfies `integer`; non-finite numbers are refused; string
  patterns are anchored so a prefix cannot pass; and a string is never treated as
  an array of characters. Every constraint failure is reported rather than only
  the first, so one exchange conveys the whole contract, and problems are emitted
  in a deterministic order because they become immutable attempt evidence.
- Supported constraints are a deliberate JSON Schema subset: enums, object
  properties/required/additionalProperties, array items with bounds and
  uniqueness, string length/pattern/format, and numeric
  minimum/maximum/exclusive bounds/multipleOf. Formats are `date`, `time`,
  `date-time`, `email` and `identifier`. Accepting arbitrary JSON Schema would
  mean shipping a general validator whose behaviour cannot be enumerated in
  tests.
- A malformed schema raises `SchemaError` at definition rather than at call
  time, since a schema defect is a developer error, not a model error.
- `harness/parsing.py`, conservative tool-call parsing. Two released defects,
  both silent. The brace matcher was not string-aware, so a closing brace inside
  a JSON string terminated the object early: a valid tool call whose body reads
  `Hi {name}, bye}` was **rejected**, consuming a turn of the opportunity budget
  and recording a spurious model error. Extraction now tracks string literals and
  backslash escapes, and reports an unterminated string rather than mis-parsing.
  It deliberately no longer repairs trailing commas; the released parser did,
  which taught the model that invalid output is acceptable and made the
  transcript disagree with what was executed.
- Argument repair is limited to an explicit, versioned alias table. The released
  `repair_args` used `difflib.get_close_matches(cutoff=0.5)` and then fell back to
  substring matching, so `{"id": ...}` was renamed to `lead_id` on a delete tool
  — inference on a mutation argument, where the model said one thing and the
  runtime executed another against authoritative state. Similarity and substring
  matching are gone entirely. A mutating tool accepts only aliases declared for
  that specific tool; a global alias never rewrites an argument that reaches
  authoritative state. Chained aliases are refused because resolving `a`→`b`→`c`
  would make the applied rename depend on iteration order.
- Unknown parameters are reported, never dropped. The released repair deleted
  them silently, so a model sending `confirm: false` had its safety intent
  discarded with no record. Refusing to repair is the safe outcome: a rejected
  call costs one turn, a wrongly repaired one produces a wrong effect the grader
  may score as a genuine model failure.
- `harness/completion.py`, fail-closed completion. The released loop asked a
  model to verify its own work and read the answer with
  `verdict.get("complete", True)`, so every degenerate case resolved to
  *complete*: a malformed verdict, a missing key, a non-boolean value, a
  timed-out verifier, a verifier that exhausted its budget. The one situation
  where a task is most likely unfinished — the verifier could not answer — was
  scored as finished.
- Completion is now decided by authoritative postconditions over real state; a
  model verifier may only explain, never establish. Unsatisfied postconditions
  plus a verifier claiming completion yields `incomplete`. Satisfied
  postconditions plus a verifier claiming otherwise yields `complete`, because
  state is authoritative and letting an unreliable verifier veto real evidence
  would manufacture false negatives; the disagreement is recorded rather than
  obeyed. Every unavailable, malformed, or raising postcondition check yields
  `unknown`.
- `unknown` is a first-class outcome, not a synonym for incomplete. Keeping the
  axes separate is what stops an instrument failure from being recorded as a
  model failure, which hard rule 5 forbids. A postcondition check that raises is
  caught and reported as `unknown` rather than propagating.
- The harness core owns the precedence rule and never imports a domain. A domain
  pack supplies one opaque callable reporting whether the required effects exist
  in authoritative state, so the contract is fixed now while B0 and S6G remain
  unbuilt.
- `harness/scoped_memory.py`, scoped and untrusted memory. The released store
  appended `{"fact": "..."}` to one shared JSONL file and loaded it with
  `json.loads(line)["fact"]` inside `__init__`, so a single malformed line raised
  and made the entire store unreadable — a recoverable defect ended the run.
  A malformed record is now quarantined with its line number, reason and raw
  text, and loading continues. Quarantine rather than discard is deliberate: a
  silently dropped memory and a correctly absent one are indistinguishable
  afterwards, which would make a memory failure look like a model that never
  learned.
- Every record carries tenant/subject/attempt scope, provenance, schema version
  and optional expiry. Reads never cross a scope boundary; an attempt-scoped
  record is private to that attempt while a subject-scoped record is shared, and
  nothing widens a scope. The released single shared file let a preference leak
  across tasks, tenants and subjects — which for the learning family, where the
  whole measurement is whether a stored preference is used later, does not add
  noise but fabricates the effect being measured.
- Memory is treated as untrusted model-authored input, not configuration.
  Control markers such as `<|im_start|>` and NUL are refused, content is length
  bounded, and rendering quotes records as inert, clearly attributed data with
  newlines flattened so a record cannot forge turn boundaries in the assembled
  prompt.
- `write_policy` is explicit. `read_only` refuses writes at the store, so the
  no-memory ablation is enforced by the instrument rather than by a caller
  remembering not to write. Expiry hides a record without deleting it, and an
  expiry that cannot be evaluated counts as expired.
- `harness/faults.py`, fault classification and explicit context outcomes. The
  released executor ended with a bare `except Exception` that handed every
  failure to the model as `ERROR: ...`. A disk-full `OSError`, a `MemoryError`, a
  broken install, and outright harness bugs all arrived as though the model had
  erred, and it retried against them — the conversion hard rule 5 forbids. It
  also spent the opportunity budget on something no model can fix and could turn
  one infrastructure fault into a failed attempt a grader scores as a genuine
  model loss. A narrower instance sat above it: a bare `except KeyError`
  reported "missing required parameter", so a `KeyError` from any dict access
  inside a tool body was described to the model as its own bad argument.
- Faults are classified onto the `model` / `runner` / `environment` origin axis
  the S4 evidence store already records, with a test asserting the status and
  origin vocabularies match so no second translation table can drift. Only a
  model-origin fault is shown to the model or allows the attempt to continue;
  a runner or environment fault aborts and is never described to the model.
- Classification is deliberately conservative in one direction: an unrecognised
  exception is a **runner** fault. Misattributing an unknown defect to the model
  silently corrupts the outcome being measured, while attributing it to the
  runner produces a visible instrument failure someone investigates. Timeout is
  runner origin, not model, because a model cannot choose to be faster and a slow
  host must not depress a measured score; `TimeoutError` is matched before
  `OSError`, which it subclasses. Budget exhaustion is a model outcome but is not
  shown, since no turn remains in which to say so.
- Context outcomes are explicit. Truncating an observation appends an in-band
  notice and records the original and delivered lengths; dropping history records
  how many turns went. Silently shortening input changes what the model saw
  without leaving a trace, so a reader could not distinguish a model that ignored
  information from one that never received it.
- `harness/typed_executor.py`, the typed tool contract and its fail-closed
  executor, where the S1R pieces compose into one admission path: unknown-tool
  check, alias repair, schema validation, deterministic semantic invariants, then
  execution with origin-classified faults.
- Semantic invariants close the "deterministic domain invariants" requirement
  that JSON Schema cannot express — an end after its start, a due date not
  already past. Structural validity is not semantic validity, and a
  structurally perfect call can still be nonsense. Invariants run **only after**
  the schema passes, so they may assume shape and check meaning; a test asserts
  an invariant never sees an unvalidated value. A raising or wrongly-typed
  invariant is a runner fault, not a model rejection, because telling the model
  to fix a harness bug would charge a model failure for our defect.
- The failure asymmetry is enforced end to end. A model fault yields a message
  and costs a turn; a runner or environment fault aborts the attempt and its
  observation is `None`, so it can never reach the model. Arguments are
  deep-copied before execution, so a tool cannot mutate the caller's record of
  what was requested.
- The registry holds no domain knowledge: a domain pack supplies schemas,
  invariant callables and executors, while the core supplies the gate ordering
  and the failure semantics.

### Changed

- **The estimand decision is made and locked: all 11 families, as written.**
  Recorded 2 August 2026, when the only releases were `v0.4.0` (F0 feasibility)
  and `v0.5.0` (S4 evidence store). No generator, grader, condition, or attempt
  outcome existed, so the choice provably could not have been influenced by
  observed results — which is the whole reason `EXECUTION.md` requires it before
  D0 rather than at D0. The rejected alternative, a preregistered structural
  subset, offers better power on a sharper question at equal run cost; it is
  rejected because a harness that helps only on the subset selected for it is a
  weaker result than a smaller effect across the full frozen distribution.
  Dilution is accepted as an honest cost and managed by a preregistered floor and
  ceiling audit: with eight development outcomes per family, 0–1 successes flags
  `<15%` and 7–8 flags `>85%`; a flag blocks the S7 freeze and permits exactly one
  versioned, direction-blind correction plus a disjoint 44-pair D0 rerun; a
  repeated flag stops the work before S8. No family is ever silently removed,
  reweighted, or excluded.
- `.gitignore` now excludes `.tmp-*/`. Multiple agents work in this tree and a
  harness-created scratch directory must never be stageable as project content.

The next stage is S1R.

## [0.5.0] — 2026-08-02

S4, the production marker-last immutable attempt evidence store. **The native
Windows ARM64 S4 gate passed** from candidate `0b8f77d`, with `overall_status`
`pass`, 461 passed, 0 failed, 3 skipped and **`s4_skipped` 0** against a
collected inventory of 464. The three remaining skips are two POSIX filesystem
fixtures and one non-Windows behaviour case, none of which is resolvable on
Windows; every required S4 symlink and junction case executed. The JUnit report
is `df2d8d1f3565f815148139ef1f91954a1b890deef1f02413cc12851952ba54aa`, attached
to the release and bound by the annotated tag alongside the candidate commit and
attestation blob.

Developer Mode was enabled on the benchmark host with explicit machine-owner
approval so the three required symlink cases execute rather than skip. Windows
long-path support was deliberately not enabled: the S4 exit gate must hold on a
default path regime, because validating Windows filesystem behaviour is its
purpose.

This release records instrument behaviour only. It is not a benchmark result, no
measured effect exists, and S1R onward is unstarted.

### Added

- `harness/evidence.py`, the production S4 marker-last evidence store:
  canonical logical attempt identity, hash-bound immutable run metadata,
  never-reused UUID candidates, persistent `flock`/`LockFileEx` run locking,
  strict versioned evidence envelopes, validated `PREPARED.json`, exclusive
  empty `COMMITTED` publication, fail-closed recovery, derived outcomes, and
  deterministic committed-only `results.json` rebuilding.
- `bench/s4_attest.py`, the strict native S4 runner attestor and verifier,
  binding the clean pushed candidate, source and executable identities, native
  Windows environment, JUnit record, required test inventory, and zero
  platform-applicable S4 skips.
- Offline S4 tests for canonical identity and envelopes, crash recovery at
  every publication boundary, corruption and stale-artifact rejection,
  duplicate and logical-collision handling, cross-process locking, Windows
  sharing/access retry, real Office artifacts, projection recovery, and
  attestation tampering.

### Fixed

- The Windows S4 platform tests inherited pytest's deep default root, so the
  real-junction case built a 250-character path and failed `CreateDirectoryW`,
  whose limit is `MAX_PATH - 12 = 248` rather than 260 because Windows reserves
  twelve characters for an 8.3 name inside the new directory. The failure was not
  constant: the path moved with the pytest counter (`pytest-99` to `pytest-100`
  adds a character) and with the operator's user name, so the S4 gate could pass
  or fail depending on how often the suite had been run. A release gate must not
  depend on either. The S4 test root is now bounded explicitly, the bound is
  asserted at fixture setup so a regression fails loudly instead of returning as
  an intermittent result, and `tests/test_s4_path_contract.py` pins the
  derivation against the real modules. Long-path support is deliberately not
  relied upon: this host has `LongPathsEnabled=0`, and the S4 exit gate must hold
  on a default Windows configuration because validating Windows filesystem
  behaviour is its purpose.
- The bound covers every S4 module that creates evidence runs, not only the
  platform tests. `tests/test_evidence_store.py` contains a symlink case that
  only begins executing once Developer Mode is enabled; under the old root it
  would have started running at 245 characters, reintroducing the same fragility
  inside the native gate it is meant to satisfy.
- The attestor's native report-directory rule asserted a flat maximum of 120
  characters that was tied to no documented limit and neither proved nor
  explained the bound it imposed. It is replaced by a derived preflight: the
  worst S4 path is computed from the report directory and must clear the 248
  directory limit by at least the 32-character margin, failing before the report
  directory is consumed so a too-long path is refused at preflight rather than
  surfacing as a mid-run `WinError 206` inside a required case. The attestor also
  supplies the bounded root through `BRICK_S4_PLATFORM_ROOT` and never inherits
  an operator's value, since a bound is only meaningful for the root it verified.
- A strict post-release audit found that `option-recognition-v2` recorded
  key-specific and type-specific error fields but gated only on a non-2xx
  response. A generic error could therefore have been mislabeled as proof of
  recognition. Eligibility now requires a 4xx/5xx response whose body names the
  real key and states its declared type. Unknown-name acceptance or rejection is
  diagnostic only, matching the canonical protocol.
- `verify_report` now reconstructs every recognition request, recomputes each
  result from the raw response, and recomputes inference-runner identity and
  process-set stability from raw memory samples. The immutable `v0.4.0` original
  and extracted bundles both pass these stronger checks without changing any
  evidence byte; their recorded archive, manifest, and summary hashes remain
  unchanged.
- Runner attestation now fails when the sampled runner process set changes
  during one model probe, including a PID replacement that the prior per-PID
  identity check could miss. Parent PIDs are retained in the attestation.
- Failed-report verification now accepts and verifies early prerequisite
  failures, classifies late run-level exceptions, requires exact model-summary
  equality, and recomputes the structured failure-code list from on-disk
  components. A well-formed but invented failure domain/code is no longer enough.
- The research/product repository boundary is now explicit. The moving
  `SMalshe/Brick` prototype is not a retained benchmark dependency; future
  convergence requires a pinned product commit, versioned adapter, schema
  digests, and conformance evidence while B0 remains fictional and no-network.

### Changed

- Froze and documented the production S4 evidence contract:
  `harness/evidence.py`, strict canonical `brick.attempt-key/1` identity,
  hash-bound immutable run metadata, strict versioned evidence envelopes,
  persistent cross-platform OS run locking, reader-derived status and strict
  outcome, deterministic committed-only projection rebuilding, the
  cooperative-local-writer threat boundary, and the required native Windows
  ARM64 `v0.5.0` attestation.
- Removed the obsolete schedule escape that allowed concurrent-writer locking to
  be replaced by an operator assertion. Locking and the cross-process test are
  mandatory evidence-integrity requirements of S4.

At the candidate state recorded by this entry, commit `f12dd71`, the independent
F0 verifier correction, is pushed to `main` and required CI is green. Runnable
S4 cases pass locally on Windows. Three required symlink cases remain blocked
because Windows Developer Mode is disabled. Candidate freeze and CI, the
zero-S4-skip native Windows ARM64 run, and the candidate-bound attestation remain
release requirements rather than claimed results. The regular attestation file
must be the only change in release descendant `R`; the tag and bound evidence
authoritatively record whether they passed. S1R has not started and no benchmark
result exists.

## [0.4.0] — 2026-08-01

F0/Q0. **The native Windows 11 ARM64 Lenovo F0 gate passed** from candidate
`6402bf5`, run `f0-20260801T164210Z-07054bec`, archive SHA-256
`edf6f06fc06332e1e6cef4322dd583c4656f034c68c7d9f758571292dffc3220`. All three
models are eligible: `qwen3.5:4b-q4_K_M` at a median 22.26 output tokens/second
against a 5 tok/s floor, `qwen3.5:2b-q4_K_M` at 45.02, and `qwen3.5:9b-q4_K_M` at
12.37 against a 3 tok/s floor. Peak process memory reached 9.61 GiB against a
28 GiB ceiling. Native tool calls round-tripped 3/3 for every model, all nine
frozen sampling options were individually recognized, and each probe ran in a
native ARM64 `llama-server.exe` with a stable hashed identity. The 200-cycle
marker-last storage spike committed 200/200 with zero invalid bundles and zero
directory renames under live Defender real-time protection and Windows Search.

This release records feasibility only. It establishes that the benchmark host can
run the designed experiment; it is not a benchmark result, no measured effect
exists, and every stage from S4 onward is unstarted.

Three earlier runs are superseded and retained. **The first failed** from
candidate `e4dd167`: run `f0-20260801T020325Z-5f948e97`, archive SHA-256
`9FEDF657AF259578E5C03B45610D4E3188D009F1CE194B8591C3A60E8BE6D7F5`. The
environment, the 200-cycle marker-last storage spike, all three model pulls, 4B
metadata and digest stability, 4B native tool conformance (3/3), 4B warm
throughput (median 23.00 tok/s against a 5 tok/s floor) and 4B process memory
(6.45 GiB against a 28 GiB ceiling) all passed. The sole failure was protocol
v1's requirement that Ollama reject an unknown option name with a 4xx client
error. Ollama does not promise that and 0.32.5 returned 200, so the gate failed
on correct server behavior rather than on any defect in the machine, the model or
the research design. That bundle stays immutable and failed; the gate was
corrected and versioned instead of repaired or waived.

The two other superseded runs passed but could not back this release: run
`f0-20260801T034453Z-94b29703` tested behavior tree `557b5ad8`, invalidated when
the version-pin test fix changed the tree, and run
`f0-20260801T162806Z-e6ca4f26` tested tree `abf609c0` at commit `1beb3da`,
invalidated when the structural allowlist fix changed the candidate commit. That
third run shares its behavior tree with the released run; a shared tree does not
make a different commit's bundle usable, and `evidence/f0/v0.4.0.json` asserts
both tree and commit. Neither was reused and no subresult was carried forward.

### Fixed (release procedure)

- The `C`-to-`R` release allowlist enumerated permitted files by name, and that
  list had rotted: `CLAUDE.md` and `EXECUTION.md` were added to the repository
  after it was written, so promoting their release status — the first two files an
  agent reads — was an allowlist violation requiring a full gate rerun. An audit of
  all 19 tracked Markdown files confirmed those were the only two gaps
  (`BRIX_DISCOVERY.md` carries no status claims). The rule is now structural:
  status-only prose in **any** tracked `*.md` file, which cannot drift as files are
  added and is safe by construction because the canonical digest excludes every
  `.md` path. The mandatory diff review is unchanged.
- The `C`-to-`R` release allowlist was internally inconsistent and made the
  documented `v0.4.0` procedure impossible to execute. It permits bumping the
  `[project].version` scalar, and the canonical digest normalizes that line so the
  bump is digest-neutral — but `tests/test_offline_foundation.py` pinned the
  version to the literal `0.3.1`. Satisfying that pin required editing a test;
  tests are inside the behavior tree; so the edit would change the digest and void
  the F0 evidence the release depends on. The test now asserts a well-formed
  `MAJOR.MINOR.PATCH` version instead of a literal, and `PROJECT_SETUP.md` records
  the general rule: assert the *shape* of an allowlisted file, never its released
  value. Discovered while executing the release, before any tag existed.

### Added

- F0 protocol v2 (`brick.f0.protocol/2`) with an explicit `option_contract`
  declaring the exact permitted option names and value types, a named
  `option-recognition-v2` suite, and a recorded unknown-option sentinel.
- Per-key option recognition replacing unknown-name rejection as the eligibility
  rule. Each frozen option name is sent with a deliberately invalid value type
  and must be rejected, while the same invalid value under an unknown name must
  be accepted. Only that contrast separates a parsed key from an ignored one, and
  unlike a generated-output differential it discriminates at the frozen values —
  including the neutral `top_p=1.0`, `min_p=0` and `repeat_penalty=1.0`, where
  changing a no-op cannot change any output. Both 4xx and 5xx are accepted for the
  invalid probe and the exact status, body, offending key and expected type are
  recorded, followed by a valid request proving the server stayed healthy.
- Brick-owned fail-closed chat-request validation (`validate_chat_request`)
  enforcing exact top-level and option keys, exact types with booleans rejected
  as integers, finite numbers, the exact frozen sampling values, `think=false`,
  `stream=false`, and a reproducible seed range, all before any HTTP request.
- Inference-runner attestation. Every observed Ollama model-runner descendant is
  now identified by full executable path, SHA-256 and PE architecture, must be
  native ARM64, and must keep a stable identity for the duration of a model
  probe. Attesting only the listener could not distinguish a native runner from
  an x64 runner under emulation, which is the exact claim the gate exists to
  establish. Executable identities are cached per path so hashing does not repeat
  on every 0.25-second sample.
- Structured, domain-attributed failure codes (`environment`, `storage`,
  `instrument`, `protocol_contract`, `model_runtime`) recorded on every summary
  with evidence paths, so a protocol-contract or runner fault is never recorded
  as a statement about a model.
- Semantic verification of *failed* reports. Identity recomputes, component
  statuses must agree with their underlying records, every failing model must
  record a substantiating cause, and every structured failure code must be
  well-formed and attributed to a known domain.
- Backward verification of protocol v1 bundles for hash integrity and identity
  only, so the immutable failed v1 evidence stays verifiable while never being
  able to establish a passing gate.
- `tests/test_f0_protocol_v2.py` covering the request contract, per-key
  recognition, the diagnostic-only status of unknown-name acceptance, runner
  attestation including emulated-x64 and identity-change rejection, failure
  attribution, and both verification paths.

### Fixed

- `option-validation/summary.json` emitted a static interpretation string
  asserting that the server rejects unknown option names regardless of outcome.
  Alongside `passed: false` it stated the opposite of what happened, so any
  reader taking the prose without the boolean drew the inverted conclusion.
  Interpretation text is now conditional on the result and names the offending
  options.
- `verify_report` recomputed eligibility only for passing reports and returned
  the stored summary for failed ones, so a failed bundle was echoed rather than
  verified.

### Changed

- Replaced the superseded S0–S18/G0–P4 execution taxonomy with the audited
  F0/Q0-through-S9 release plan.
- Defined the 4B native-tools versus full-harness confirmatory contract, bounded
  descriptive matrix, runtime-only sample-size fallback, standalone scheduler,
  incomplete-run rule, fixed-family claim boundary, ordered two-subepisode
  learning case, and exact attempt accounting.
- Defined marker-last publication using never-reused physical directories,
  `PREPARED.json`, and exclusive `COMMITTED` marker creation. Only the disposable
  F0 primitive is implemented in this worktree; the production S4 store remains
  pending.
- Reframed the exact sign-flip/McNemar result as a sharp
  pairwise-exchangeability diagnostic and made the fully specified within-family
  percentile bootstrap the inferential gate for the equal-family estimand.
- Reordered the synthetic Brix layer after the repaired typed runtime and
  clarified that it is a fictional architecture fixture, not a selected or
  approved Brix production workflow.
- Changed missing `ActionPolicy` confirmation callbacks from historical
  permissive compatibility to fail-closed denial.
- Made every disposable F0 candidate—including normal and recovered
  replacements—publish through the same bounded retry path. F0 report
  publication now re-reads its prepared manifest before and after exclusive
  marker creation, and `verify` recomputes pass eligibility from the committed
  protocol, host, storage, pull, model, runtime, and memory records instead of
  trusting `summary.json`.

### Added

- `EXECUTION.md`, the operational handbook that `PROJECT_SETUP.md` deliberately
  does not cover: read order for a new session, dated repository and benchmark-host
  state, the immediate next action, honest timeline ranges, a zero-buffer
  two-week schedule, hard checkpoints with pre-decided consequences, the cut
  order when behind and the six things that must never be cut, the
  eleven-family versus preregistered-structural-subset estimand decision that
  must be made before D0, the development-set floor and ceiling check, the
  per-session protocol, and status wording that does not conflate a written F0
  implementation with a passed F0 gate. It defers to `PROJECT_SETUP.md` and
  `PROJECT_GUIDE.md`, and to `git log` and `CHANGELOG.md` for state.
- `CLAUDE.md`, a short always-loaded orientation for coding agents and new
  contributors: the hard rules (clean worktree during an evidence gate, report a
  failing gate rather than repairing it, live-model work only on the native
  Lenovo, one stage at a time, no domain imports in the core), current release
  position, the F0 gate and its consequences, the remaining stage sequence, the
  primary contrast and claim gate, what completing the plan produces, the four
  valid conclusions, and the claims that must never be made. It defers to
  `PROJECT_SETUP.md` and `PROJECT_GUIDE.md` on any disagreement.
- A first-time Lenovo host setup section in `bench/README.md` covering native
  ARM64 shell/Python/Ollama verification, server start, power mode, required
  Defender and Windows Search state, pre-pull free space, output-path rules,
  candidate-commit resolution, expected duration, and a failure-triage table
  mapping each fail-closed check to its likely cause. `PROJECT_SETUP.md` and
  `README.md` link to it. The plan previously stated these conditions only as
  acceptance criteria, so an operator could not satisfy them from the documents
  alone.
- `bench/f0_protocol.json`, `bench/f0_probe.py`, `bench/f0_windows.py`, and
  `bench/f0_storage.py` for the reproducible native-Windows ARM64 environment,
  model, native-tool, option-validation, memory, throughput, and disposable
  marker-last storage gate.
- Offline F0 tests covering protocol validation, environment/report fail-closed
  behavior, native-tool and option-validation records, every disposable storage
  write boundary, process-exit recovery, collision, tamper, unexpected-member,
  deadline/non-retryable handling, semantic report verification, and retry
  behavior. Windows x64 additionally runs live ctypes/current-process and real
  Office held-handle smoke tests. Full Lenovo held-handle evidence remains
  pending.
- Native host gates for fixed local NTFS storage, Lenovo/Snapdragon X Elite
  identity, AC power, Defender and indexing state, stable ARM64 listener
  identity, measured Ollama runner descendants, post-pull free space, model
  family/size/tool metadata, raw runtime responses, and processor placement.
- Required Windows x64 CI alongside the Linux matrix. The hosted
  `windows-11-arm` job is manual and advisory; local Lenovo evidence is
  authoritative.
- A clean candidate-commit to metadata-only release-descendant attestation
  contract, reproducible behavior-tree fingerprint command, and exact Lenovo
  run/verify handoff. No Lenovo evidence is claimed yet.

### Security

- Removed `harness/fs_tools.py` and every supported general-filesystem,
  PowerShell, broad-root, skip-confirmation, and overlay-composition activation
  path from the CLI, Agent Lab, and configuration surfaces.
- Legacy `--root`, `--shell`, `--yolo`, `--with-domain`, and `--with-office`
  forms now fail before output creation, model access, network access, or
  mutation.
- Removed Agent Lab's unbound browser/stdin confirmation channel. Its replacement
  is the new run/nonce-bound protocol scheduled for S5W.

### Pending before `v0.4.0`

- Run and retain the full F0 evidence bundle on the native Windows 11 ARM64
  Lenovo.
- Reconcile any accepted-option, template, context, thinking, or backend
  difference found by that gate.
- Tag and release only after the offline suite, required CI, and Lenovo gates
  all pass.

## [0.3.1] — 2026-07-29

Corrective release after an independent audit of `0.3.0`. It tightens the S2/S3
contracts and reconciles documentation with the code. It does not complete S4,
S5, S5F, G0, or R1.

### Fixed

- Domain packs must explicitly classify every registered tool in
  `ActionPolicy`; missing or extra classifications now fail pack construction
  instead of silently treating an omitted mutating tool as read-only. Attempt
  contexts also reject a policy missing any tool on their active surface.
- Benchmark result metadata records the canonical `ToolRegistry` order actually
  rendered to the model, not a pack author's possibly reordered selection.
- The report rejects missing domain/version identity, unknown conditions,
  incomplete or impossible metrics, invalid tool/capability/check lists, and
  duplicate records. It escapes untrusted table labels and no longer invents
  `office_demo@unversioned` provenance for incomplete rows.
- The shared agent CLI uses a real argument parser. `--help`, misspelled flags,
  missing flag values, and non-positive call budgets now stop before any model
  request.
- Windows launchers discover Python or honor `PYTHON`; Agent Lab launchers
  install from the checked-in lock rather than unpinned package names.
- Agent Lab resolves child components beneath trusted canonical roots and
  rejects direct, same-prefix, and child-symlink escapes observed at lookup
  time. This is not root-integrity enforcement, race-free containment,
  authentication, CSRF protection, or an OS sandbox.
- Publication tests cover additional runtime/key paths and selected
  high-confidence credential formats. They remain a narrow automated check,
  not proof that arbitrary secrets or private data are absent.
- Both training generators' serving prompts are now checked against the live
  office harness prompt.

### Documentation

- Reconciled the benchmark, Agent Lab, training, agent, architecture,
  remediation, project-guide, setup, security, and release documents with the
  implemented S0–S3 state.
- Clarified that S4 is incomplete rather than literally untouched, `0.2.0` was
  not a standalone tagged release, the interleaving test proves reentrancy
  rather than thread safety, and generated training corpora are ignored local
  artifacts rather than shipped data.
- Recorded unresolved publication governance: the EdgeHarness repository is
  canonical, but license selection, branch protection, and cleanup of a
  divergent legacy public repository require owner action.

## [0.3.0] — 2026-07-28

Implements packages **S2** (explicit runtime contracts) and **S3** (domain-pack
extraction and a second portability pack). Scope was limited to those packages;
S4 remains incomplete. Limited path namespacing, resume-key, and report
groundwork landed while migrating S3 callers, but none of S4's transactional,
crash-recovery, stale-artifact, or concurrent-writer exit checks passed.

The office demo's behavior is preserved deliberately: both office system prompts
are byte-identical to the pre-extraction baseline (`d4278c7`), verified by SHA-256
in `tests/test_runtime_architecture.py`.

### Added

- `harness/runtime.py` — `RunConfig`, `RunHooks`, `ActionPolicy`, and
  `AttemptContext`. All execution settings, the simulation clock, the call
  budget, observation limits, effect classification, and observation hooks are
  now constructor arguments validated at the boundary.
- `harness/domain.py` — the `DomainPack`, `TaskSpec`, and `PromptProfile`
  contracts, the generic UI state envelope with its validator, and
  `load_domain()`, which imports `domains.<name>.PACK` by convention. Pack
  construction validates SemVer, callback signatures, reserved `think`/`done`
  tool contracts, task/tool references, and identifier safety.
- `harness/builtin_tools.py` — domain-independent `think`, `save_memory`,
  `recall_memories`, and `done` specifications, returned as a fresh mapping so
  composition never shares mutable dictionaries between packs.
- `harness/errors.py` — `ToolError`, so worlds and registries no longer import an
  error type from the office demo.
- `harness/storage.py` — `agent_runtime_paths()`, selecting the legacy office
  layout or a `runtime/<domain>/<version>/` namespace per pack.
- `domains/office_demo/` — the existing fictional office as a versioned pack
  (`office_demo@0.1.0`): world, tools, normalization, office-file helpers, 12
  tasks, and graders.
- `domains/counter_demo/` — `counter_demo@0.1.0`, a minimal read/increment pack
  used only as a structural portability fixture. It is not generalization or
  performance evidence.
- `--domain` selection for the benchmark runner, the shared agent CLI, and the
  Agent Lab runner; a domain selector in the Agent Lab UI that locks once a run
  starts.
- `tests/test_runtime_architecture.py` and `tests/test_domain_callers.py` — 53
  tests covering contract validation, registry immutability, prompt-byte parity,
  cross-domain isolation, overlay composition, path-component safety, report
  separation, and every caller surface.
- Two acceptance tests that make the S2/S3 exit criteria executable rather than
  asserted: `test_no_core_module_outside_the_named_shims_imports_a_domain` and
  `test_two_domains_interleave_in_one_process_without_leakage`, the latter
  running a complete `counter_demo` attempt from inside a suspended
  `office_demo` model call.
- `S5F` package and a package-status table in `PROJECT_SETUP.md`. Gate `R1.6`
  (filesystem and process safety) previously mapped to no package, which would
  have allowed an `R1` review to pass with that subsection unbuilt.

### Changed

- Both agent loops now take one `AttemptContext`; `run(llm, task_text, attempt)`
  resolves the condition. Neither loop reads module-level state.
- Tool executors take `(attempt, args)` instead of `(world, memory, args)`.
  Signatures are checked when a registry is constructed.
- `ToolRegistry` replaces the mutable `TOOLS` dictionary. Stored specifications
  are recursively frozen and public accessors return defensive copies, so
  neither an ingress dictionary nor an exported copy can mutate a pack.
- `harness/fs_tools.py` returns a composable, per-attempt `FileOverlay` from
  `build_overlay()` rather than injecting tools into a shared registry.
  `compose()` merges tools, effects, confirmer, and prompt rules atomically.
- Prompt templates are parameterized by a domain-owned `PromptProfile`, and the
  generic profile carries no office vocabulary.
- Benchmark artifacts and result records are namespaced by domain and version
  (`<outdir>/<domain>/<version>/<model>/<condition>/<task>`); resume matching
  includes domain and version.
- `bench/report.py` groups by `domain@version` and never pools scores across
  packs; it rejects duplicate result identities and withholds raw-versus-harness
  deltas when task sets or recorded tool/call-budget surfaces are incompatible.
- The office CLI keeps its historic `workspace/`, `memory/`, and `logs/` layout
  so existing local runtime state is neither moved nor deleted; other packs are
  namespaced.
- `finetune/gen_toolcall_data.py` builds its system prompt from the same
  serving-path builder as the harness rather than a duplicated string.
- `README.md`, `ARCHITECTURE.md`, `PROJECT_SETUP.md`, and the agent
  documentation describe the implemented contracts and preserved office
  layout. Benchmark, Agent Lab, training, and remediation documentation was
  subsequently reconciled in `0.3.1`.

### Removed

- The process-global `TOOLS` registry, the `SIM_TODAY` module clock used as a
  runtime date, the module-level event/tool/stream hooks, the global call
  ceiling, and global extra-rule strings.
- `fs_tools.enable()` and `fs_tools.restrict_to_files()`, which mutated a shared
  registry in place.
- `agents/_shared/run.ps1`, an unreachable launcher; each `agents/<size>/run.ps1`
  invokes its own shim.

`harness/world.py`, `harness/office.py`, `bench/tasks.py`, and `bench/grade.py`
remain as deprecated re-exports of `office_demo` for pre-refactor import paths.
They are the only modules in `harness/` permitted to import a domain, which is
enforced by test.

### Fixed

- The call budget is metered per attempt by `_AttemptLLM`. It previously read a
  delegate's cumulative counter, so a reused client silently reduced the budget
  of every later attempt.
- Nested mutable values inside a tool specification could be mutated after
  registration through a retained reference or an exported copy. Freezing and
  thawing are now recursive; executors keep their identity and are not copied.
- Duplicate-call suppression is a per-tool policy
  (`suppress_identical_repeats`). Suppression was unconditional, which made a
  legitimately repeated action — such as the counter pack's second increment —
  unrepresentable.
- Observation hooks can no longer alter evidence: hook arguments are deep-copied
  and hook exceptions are contained, so an observer cannot change a tool result
  or the recorded action log.
- Observation truncation limits are attempt-local rather than a module default.
- Office world fixtures are deep-copied per world, so mutating one attempt's
  state no longer poisons the module fixture or a later world.
- Benchmark path components pass through `slug()`, which rejects traversal
  sequences, normalizes unsafe characters with a content digest, refuses
  reserved Windows device names, and rejects model labels that collide after
  cross-platform normalization. Invalid options are rejected before any output
  directory is created.
- Agent-folder resolution in the Agent Lab rejects traversal.
- Overlay composition raises rather than silently choosing one of two different
  confirmation callbacks.
- `ModelRouter` freezes role configuration, isolates one client per role, and
  rejects unknown roles. Keep-alive values are described as backend hints, not
  residency claims.

### Security

- `ActionPolicy` classifies every tool as `read`, `state_write`,
  `external_write`, or `shell`. This is an execution-policy seam for classifying
  and gating calls; it is not authentication, authorization, or an OS sandbox.
- A missing confirmation callback still approves, preserving the historical
  default. Changing that default to deny is `S5F` work and is deliberately not
  bundled into this release.

### Known limitations

Unchanged and still open after this release:

- `results.json` is rewritten non-atomically; attempts reuse task directories,
  so a stale generated file can influence a later score. (`S4`)
- Graders remain permissive: substring file lookup, loose value/row association,
  conditional denominators, and limited penalties for unrequested actions.
  A grader exception is still recorded as a zero score rather than an invalid
  attempt. (`S5`)
- Filesystem containment is lexical: symlinks and junctions are not resolved,
  overly broad roots are accepted, and the write deny-list is hard-coded to one
  Windows installation, so it protects neither this repository's code nor its
  results directory in any other checkout. (`S5F`)
- The Agent Lab server is an unauthenticated loopback development interface with
  no CSRF or Origin protection.
- Provenance is partial: model digest, quantization, dependency and code hashes,
  hardware, and OS are not stamped into result records. (`S7`)
- Benchmark outputs are exploratory. They must not be published, compared across
  code revisions, or reused from a development output directory.

## [0.2.0] — 2026-07-28

Implements packages **S0** (offline test and CI foundation) and **S1**
(behavior characterization). This was never tagged as a standalone release; the
commit first became publicly reachable as an ancestor of `v0.3.0`.

### Added

- `pyproject.toml` with PEP 621 metadata, pinned direct runtime dependencies,
  a `test` extra, and pytest configuration declaring strict markers.
- `requirements.txt`, `requirements-lock.txt`, and `requirements-test.txt`. The
  lock pins transitive versions but carries no package hashes, so installation
  is not a cryptographically reproducible supply-chain boundary.
- `.github/workflows/ci.yml` running the offline suite on Python 3.9 through
  3.13 with no Ollama service and no network-dependent tests.
- `tests/conftest.py` with an autouse network guard: a test that reaches
  `requests` or `urllib` fails instead of silently contacting a local model
  server.
- 62 characterization tests across parsing and normalization, tool validation
  and execution, world and memory behavior, agent-loop boundaries, and every
  existing grader. Tests that encode behavior documented as defective are
  marked, so a later fix must change a test deliberately rather than silently.
- A tracked-path policy test for runtime memory, workspaces, logs, generated
  training corpora, model artifacts, and common sensitive filenames. The
  narrower high-confidence content scan was added in `0.3.1`; neither replaces
  publication review or a dedicated secret scanner.
- `SECURITY.md` describing the supported scope, reporting expectations, and the
  controls this repository does not implement.

### Changed

- `.gitignore` excludes local agent/editor configuration, runtime memory,
  workspaces, logs, benchmark outputs, generated office documents, unreviewed
  training corpora, and model artifacts.

## [0.1.0] — 2026-07-28

Initial sanitized public baseline, published as a history-free snapshot to a new
organization repository.

### Added

- The pre-existing research scaffold: raw and harness agent loops, the simulated
  office world and tools, the benchmark runner and report, per-model agent
  configurations, the Agent Lab console, and the experimental training package.
- `BRIX_DISCOVERY.md`, a sanitized discovery summary containing no client
  records.
- `PROJECT_GUIDE.md` and `PROJECT_SETUP.md`, the evidence standards and the
  gated implementation plan with its `S0`–`S18` session packages.
- `FIXES.md`, the code-level defect register mapped to the canonical gates.

### Removed

Excluded from the published snapshot: local editor and permission settings,
agent runtime memory, generated training corpora with unresolved provenance,
benchmark outputs, model artifacts, credentials, and the original client contact
address.

[0.3.1]: https://github.com/EdgeHarness/Brick-Agent-Harness/releases/tag/v0.3.1
[0.3.0]: https://github.com/EdgeHarness/Brick-Agent-Harness/releases/tag/v0.3.0
[0.2.0]: https://github.com/EdgeHarness/Brick-Agent-Harness/commit/d8cbd7a
[0.1.0]: https://github.com/EdgeHarness/Brick-Agent-Harness/releases/tag/v0.1.0
