# As-is analysis and to-be roadmap

Written 2026-08-23, after phase 2 (guards) landed as `b625087`. As-is facts are
cited to files in this tree; nothing here overrides `docs/PROJECT_SETUP.md` or
`docs/PROJECT_GUIDE.md`, and nothing here touches the immutable v0.13.5 root or
the sixteen digest-bound sources.

## As-is

### What is proven, and what is not

- **Host feasibility only.** The released F0 numbers (`evidence/f0/v0.4.0.json`)
  are 22.26 tok/s for the 4B against a 5.0 floor, 45.02 for the 2B, 12.37 for
  the 9B against a 3.0 floor, with peak memory 6.50/3.99/9.61 GiB against a
  28 GiB ceiling. At 22.26 tok/s a 4,096-token attempt is about 184 s of
  generation. These say the Lenovo can run the experiment, nothing more.
- **No harness efficacy number exists.** `bench/README.md` states it outright:
  no committed result establishes that the harness improves a model. The B1a
  fallback lane is sealed but score-embargoed, and D0/S7 closed without a
  freeze. Every claim below stays inside that boundary.
- **The instrument works.** 1,097 offline tests pass, the S4 evidence store
  passed its native gate (461/0/3), and the only path to a claimable number is
  already preauthorized: the 24 missing B1b cells plus the 240-cell B2
  schedule under `v0.13.6`, on the Lenovo.

### What the platform is today

- A domain-free harness core with three packs (`office_demo`, `counter_demo`,
  `brix_followup_synthetic`), an immutable per-attempt `ToolRegistry`,
  effect-classified `ActionPolicy` with one-shot confirmations, fail-closed
  completion, scoped memory, and immutable attempt evidence.
- The phase 1 and 2 ports are done: the Agent Lab console, the MCP connector
  layer with draft/live/read_only modes and a multi-account broker, chat
  threads, and the five advisory guards (on interactively, off in `bench/`).
- One backend: Ollama on 127.0.0.1:11434, hardcoded in `harness/llm.py`.
- A model router with driver/router/verifier/deep roles exists
  (`harness/model_router.py`), but no shipped agent config defines tiers, so
  every run is single-model unless launched with `--tiers`.

### Where run cost and reliability are currently fixed by literals

`harness/agent.py` hardcodes what final-agent-8b tunes per model in
`harness/profiles.py`:

| knob | brick today | f8b profile range |
|---|---|---|
| plan step | always on, 1 call | off for 1B, capped 3 to 6 steps |
| verifier rounds | 2 | 0 (1B) to 2 |
| driver num_predict | 700 | 350 (1B) to 1000 (32B) |
| repeat budget | 1, read and write alike | 1 to 3, read/write split |
| think streak cap | 2 | 1 to 3 |
| memory_k | 3 | 2 to 4 |
| num_ctx | 8192 | 8192 to 16384 |

The cost of the mismatch is visible in practice: today's live 1B run spent 12
of 12 calls with a mandatory plan call and feedback loops the 1B profile
upstream exists to prevent (plan off, num_predict 350, repeat budget 2).

### Smaller as-is gaps

- `harness/memory.py` uses exact word-set overlap, so "meeting" does not match
  "meetings"; f8b's version adds 4-char prefix matching, dedupe on save, and
  torn-line tolerance. Unbounded file growth in both.
- The Agent Lab emits `prompt_tokens` and `usage_by_role` on every run end but
  the UI never renders them; there is no tok/s figure anywhere.
- `guard_wrong_date` fires on first occurrence; the DeepSeek Harness reference
  escalates at thresholds instead (recorded in `docs/PHASE2_GUARDS.md`).
- `llm.py` pins `seed: 42` in every payload, right for the bench, debatable
  for interactive threads.

## To-be roadmap

Ordered by effect on performance per unit of risk. Nothing below changes
`bench/` behavior; the bench defaults stay byte-stable.

### 1. Phase 3: port `harness/profiles.py` (DONE 2026-08-23)

Per-model tuning is the largest interactive-performance lever available
without any new measurement. Port the `Profile` dataclass, the named profiles,
and the size-band resolution (`for_model`), then move the seven hardcoded
knobs in `run_harness` onto it. `RunConfig` keeps its current fields;
`DEFAULT = Profile()` must reproduce today's literals exactly so the bench
path is unchanged, and a test should assert that. Interactive callers resolve
the profile from the agent's model tag; a `harness` dict in `config.json`
overrides fields. Expected effect: the 1B and 3B agents stop burning their
budget on plan/verify calls they cannot use, and the 14B/32B tiers get room.

### 2. Quick wins alongside phase 3

- DONE: f8b's `memory.py` retrieval (prefix overlap, dedupe, torn-line
  tolerance).
- DONE: the Agent Lab end card renders `prompt_tokens`, tok/s, and per-role
  usage when more than one role ran.
- Deferred: a default `router` block in `agents/8b/config.json`. Turning
  tiering on by default breaks the agent when the small model is not
  installed, so it needs an installed-models check first.
- `wrong_date` escalation thresholds: **measured 2026-08-25, inconclusive, and
  probably unnecessary.** Two things came out of trying.

  First, reading the code: the recorded incident behind this item is "four
  corrections for four innocent `list_events` probes". `list_events` is a read
  and `guard_wrong_date` has been writes-only since it landed, so the incident
  describes behaviour that the current `is_write()` check already prevents. The
  writes-only restriction appears to BE the fix this item is asking for a
  second fix to. Nothing in `evidence/` or `CHANGELOG.md` records the guard
  being noisy after that change; the claim is asserted in prose in three places
  and demonstrated in none.

  Second, running it: four dated office tasks (`cal_add`, `cal_freeslot`,
  `cal_brief`, `remind_msg`) against `llama3.2:1b` with guards on produced zero
  guard firings. Guards run after argument validation, and on the runs that
  reached a valid write the date was correct, so there was nothing to question.

  So the item cannot be settled on this machine. `llama3.2:1b` is not a good
  probe for it: the guard is writes-only and the 1B reaches few writes. It
  needs `llama3.1:8b`, which will not fit while the disk is at 98 percent with
  11 GiB free. **Leaving this open rather than implementing thresholds against
  a claim the code appears to have already answered.** If it is picked up
  again, fix the docstring first: it reads as a live complaint about behaviour
  the same function no longer has.

### What the live 1B runs actually showed

A first pass at the measurement above was invalid and is worth recording,
because the mistake is easy to repeat. `webui/runner.py` passes `--task`
straight through to `run_harness` as the task TEXT. Passing a task *id* like
`cal_add` therefore tells the model its task is the string "cal_add", and it
duly produced eighteen calls with empty arguments. That was the measurement
being wrong, not the model and not the harness.

Re-run with the real prompt, three times, `llama3.2:1b` on `cal_add`:

| run | calls | invalid | finished | successful actions |
|---|---|---|---|---|
| 1 | 18 of 18 | 9 | no | 1, correct |
| 2 | 18 of 18 | 9 | no | 1, correct |
| 3 | 7 of 18 | 0 | yes | 5, of which 4 were never asked for |

**The 1B forms the tool call correctly and then cannot stop.** Every run
produced `add_event` with the right title, the right date, 2pm converted to
14:00, and both attendees. Two of three then spent the remaining seventeen
calls re-calling `add_event` with an unknown `id` parameter and no required
ones, never calling `done`, despite feedback each round saying "If everything
is complete, call done." The third stopped but had also sent a message and set
a reminder the task never mentioned.

That is a termination problem, not a tool-formation problem, and it is where
the next engine change should aim for small models. A separate check confirms
the formation half: the same model, same task, in a focused single-tool prompt
answered correctly six times out of six with the plain `format: "json"` the
harness already sends, and constrained decoding against a full JSON Schema was
also six out of six. So schema-constrained decoding is not the lever here; it
would be fixing something that is not broken.

### 3. Phase 4: hardware layer (DONE 2026-08-23)

Copy `npu/ollama_shim.py` (270 lines) and `llamacpp/ollama_shim.py` (186
lines), both stdlib-only, plus their operating notes. They impersonate Ollama
on 11434, so the harness needs zero code changes; backend choice is which
process is running. Two boundaries to respect:

- `llamacpp/openrouter_shim.py` is marked local-only upstream and stays out of
  this repository. Hard rule 9 allows third-party-held credentials for a
  throwaway account only; an OpenRouter key in an env var meets that, but the
  shim ships nowhere.
- The NPU shim does not forward `num_ctx` (GenieX serves what `--nctx` gave
  it), so the phase 3 profile for NPU models must document that ceiling.

### 4. The efficacy number itself

The roadmap's honest end state is a claimable harness-vs-native result, and
the only sanctioned route is the existing v0.13.6 preauthorization: run the 24
B1b cells and the mandatory 240-cell B2 schedule on the Lenovo, under the
frozen protocol, guards off. No interactive improvement above changes that
number; keeping the two worlds separate is what makes both trustworthy.

### 5. Phase 5: retire final-agent-8b to a shipping instance (DONE 2026-08-23)

After phases 3 and 4, everything generic lives here. f8b keeps packaging and
device-specific material and consumes brick as the base. Its `fs_tools.py`
(real filesystem tools with a root jail) does not move: hard rule 9 forbids
general filesystem capability on a supported surface, so real file access
stays MCP-mediated. Revisiting that is a rule change, not a port.

### Not doing

- No edits to the sixteen v0.13.5-bound sources; the office world merge stays
  blocked as recorded in `docs/PHASE2_GUARDS.md` §5.
- No new benchmark claims from interactive runs, ever.
- No embeddings/vector store for memory; the cheap retrieval is a deliberate
  same-for-every-model control.
