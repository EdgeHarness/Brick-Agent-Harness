# Changelog

All notable changes to this repository are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions use
`MAJOR.MINOR.PATCH`.

While the major version is `0`, a minor bump may contain breaking changes to
internal Python interfaces. Nothing in this repository is a stable public API.

**A released version is not gate acceptance.** Versions record repository
changes only. The canonical acceptance gates in
[`PROJECT_SETUP.md`](PROJECT_SETUP.md) are evaluated separately, and `G0` and
`R1` remain partial and unpassed. No entry below should be read as evidence that
the research instrument is valid or that any measured effect exists.

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
