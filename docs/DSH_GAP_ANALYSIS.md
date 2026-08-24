# DeepSeek Harness gap analysis, second pass

Written 2026-08-23. The first pass (recorded in the phase 2 design and the
integration notes) took the effect classes, monotonic guards, and the guard
defaults from DeepSeek Harness `@99f6f02` (dsh). This pass swept the three
areas that reading never opened: the MCP/tool layer, the loop's context
management, and the composition system. Concepts only, never code; dsh is
432k lines of TypeScript and we do not compete on surface area.

## Already covered, previously believed missing

The first pass listed four repeat-reminder mechanisms as unadopted. Two of
them turn out to be already present in Brick by construction:

- **Canonical argument keys.** dsh deep-sorts JSON keys before comparing
  calls. Brick's signature is `json.dumps(args, sort_keys=True)`, which sorts
  recursively; identical semantics.
- **Denied calls count as repeats.** dsh counts a policy deny toward the
  repeat chain. Brick's denied confirmation returns `ok=False` into the same
  `seen_calls` bookkeeping, and a failed call's repeat budget is already
  clamped to 1.

Two remain genuinely unadopted and stay deliberate:

- **Bookkeeping tools transparent to the chain.** dsh needs this because
  `todo_write` interleaves with real work. Brick counts per world version,
  not consecutively, so an interleaved read cannot launder a loop; the
  mechanism is unnecessary here.
- **Escalating thresholds [3, 5, 8].** Recorded in `docs/PHASE2_GUARDS.md`
  for the `wrong_date` guard, still deferred until it proves noisy live.

## Adopted in this change

Each is bench-invisible: default-off, or in a path `bench/` never runs.

1. **MCP child environment scrubbing** (`harness/mcp_bridge.py`). dsh spawns
   MCP servers with credential-shaped variables dropped from the parent env.
   Brick passed `os.environ` verbatim, so every API key in the user's shell
   reached every third-party connector process. Now anything matching
   KEY/TOKEN/SECRET/PASSWORD/CREDENTIAL/AUTH is dropped unless the server's
   own config names it. This is hard rule 9's spirit applied to the process
   boundary.
2. **Transport retries with backoff** (`harness/llm.py`). dsh retries
   EMPTY/RATE_LIMIT/SERVER/TIMEOUT/TRANSPORT with exponential backoff and
   jitter. Brick had none, and the D0 history records a local Ollama
   returning 500s that cleared on their own. `LLM(retries=N)` retries
   connection failures, timeouts, and 5xx; never 4xx, never a reply that
   already streamed tokens (the viewer would see it twice). Default 0, so
   the bench arm is byte-identical; interactive callers pass 2.
3. **Head-and-tail observation clipping** (`_obs`, profile knob
   `observation_keep_tail`). dsh's tool-result pruner keeps head and tail.
   Brick clipped head-only, which feeds the model everything except the part
   it usually needs: totals and verdicts live at the end of a result.
   Default 0 keeps the original clip; every named profile keeps 300 tail
   characters.
4. **Context pressure valve** (`_shrink_context`, profile knob
   `prune_context`). dsh compacts at 80% of the window using a chars/4
   estimate, prunes tool results middle-out first, and never spends a model
   call to do it. Brick had nothing, and the failure mode is nasty: at
   overflow Ollama truncates silently from the FRONT, which eats the system
   prompt first. Brick now estimates chars/4 before each driver call and,
   past 80% of `num_ctx`, middle-prunes observations older than the last six
   messages. Deterministic, no model call, off in DEFAULT.

## Worth adopting later, with the trigger that makes it worth it

- **Reconnect generations** (dsh `mcp-client/connection.ts`): fresh client
  per attempt, generation counter making stale callbacks no-ops, backoff
  budget that a stability window resets, teardown that never starts attempt
  N+1 before N's process is observed dead. Adopt when a long-lived Agent Lab
  session with real connectors starts seeing mid-run server deaths; today a
  dead server just errors every call, which is survivable for one run.
- **Spill-to-file** (dsh spill-policy): oversized results written to a
  session artifact, model sees head/tail plus the path, `read` exempted to
  avoid read-spill-read loops. Adopt when MCP mail listings routinely exceed
  the observation limit; needs a read-file tool in the loop first.
- **Fixed-template compaction summary** (dsh compaction-basic): the
  same-prefix summarizer is KV-cache-friendly and free with local models.
  Adopt if chat threads grow past what the pressure valve handles; the
  valve should buy a long time at 50 calls.
- **Config as id-addressed rows** (dsh cordis.patch.yml): per-surface bundle
  layers flattened last-write-wins over an empty root, whole-config
  replacement, a name assertion so a drifted pack fails instead of
  half-applying. This is the right shape for phase 5's per-company pack
  overrides; adopt when the second real customer pack exists.
- **Prompt fragments with order bands** (dsh system-prompt): registrations
  with integer order and reserved bands instead of string concatenation.
  Adopt with the same phase 5 trigger; today two callers concatenating
  `prompt_rules` is manageable.
- **Synthetic closers with idempotency wording** (dsh session repair): on
  crash resume, a dangling tool call gets a paired synthetic result telling
  the model to retry only idempotent work. Adopt if Agent Lab ever resumes
  interrupted runs rather than starting fresh.
- **Corrective routing in errors** (dsh: a bare "unknown tool" makes the
  model conclude the deployment is broken). Brick already does "did you
  mean"; keep the principle in mind for MCP-side errors.

## Not adopting, and why

- **Image and audio tool results.** The supported surfaces are text tools;
  admitting media means model-capability negotiation we have no consumer
  for.
- **A per-run token budget.** dsh itself has none; the call budget is the
  right unit for this harness and it is already enforced.
- **Two-phase tool-list resync with a mutex.** Brick composes the registry
  once per attempt and it is immutable; there is nothing to resync.
- **Subagent orchestration.** No delegation exists or is planned before
  phase 5; the parent-join and policy-stamping ideas are recorded above for
  when it does.
