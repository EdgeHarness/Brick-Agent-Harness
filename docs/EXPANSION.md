# Expansion plan

Written 2026-08-25, after the first first-party connector shipped and after a
survey of comparable harnesses. It says what to build next, in what order, and
one thing that has to change about how the central claim gets measured.

`docs/ROADMAP.md` remains the as-is analysis. This is the forward plan and
supersedes its "to-be" section where the two disagree.

## The three layers

| layer | what it is | state |
|---|---|---|
| `brick-agent-harness` | the engine. Domain-free loop, tool registry, effect policy, guards, profiles, memory, evidence, MCP connector layer | phases 1 to 5 done |
| connectors | MCP servers, ours and third-party, each adding a capability without touching the engine | one first-party server, `ms365-mcp`, feature complete |
| `brix-coworking` | the product repository, holding the client's specific features and consuming the other two | not created |

The layering is the point. A connector is a subprocess speaking JSON-RPC over
stdio, so it shares no dependency and need not even share a language with the
engine. That is what makes "add a lot of connectors" a plan rather than a
growing pile of coupling.

## What to build, in order

### 1. Finish proving the first connector, then copy it

`ms365-mcp` is feature complete and has never authenticated. Until it has, we
know the code works and not that the design does. Blocked on an Azure app
registration; the steps and the two ways a university tenant can refuse are in
the daily note and in that repository's README.

`docs/CONNECTOR-PATTERN.md` records what transfers. The next connector is a
copy-and-delete, not a rewrite.

### 2. The next connector: GitHub

It earns the slot over the alternatives because it needs no OAuth dance, its
read surface is immediately useful, and it has a natural draft equivalent in an
unposted comment, so the draft-first design carries over unchanged. Its hard
part is the twenty-tool budget: the API is enormous and choosing what to leave
out is the entire design problem, which is exactly the muscle worth building.

Deliberately not next: anything backed by local files. Both an Obsidian and a
documents connector run into hard rule 9, which forbids general filesystem
capability on a supported surface. That is a rule change to argue for on its
own merits, not something to slip in behind a connector.

### 3. `brix-coworking`

Waiting on the client's feature list. It should consume both layers and
contain no engine code. When the list arrives, the first question to ask of
every feature is which layer it belongs in, because the temptation will be to
put engine work in the product repository where it is invisible to the tests.

## Benchmarking, and the thing that has to change

The project's thesis is that the harness makes a small local model materially
better at multi-step tool use. No committed number establishes it. The
sanctioned route is the sealed v0.13.6 lane, 24 B1b cells plus the 240-cell B2
schedule.

A survey of comparable work turned up three findings that bear on that
measurement, and one of them is a problem.

**The problem: prompt format can dwarf architecture.** There is a documented
case of applying the correct chat template to a 7B model moving its score by
around 39 percent, on its own, with no other change. That is larger than most
scaffolding interventions could plausibly produce. If the harness-versus-native
comparison does not hold prompt and chat-template formatting constant across
both conditions, a positive result is uninterpretable: it may be measuring that
the harness condition happens to format its prompt correctly and the baseline
does not. **This is the single most important thing to get right before the
lane runs**, because it cannot be fixed afterwards without running it again.
The native condition must use the model's own correct chat template, and the
protocol should record the template used in both conditions.

**The counter-thesis worth taking seriously.** `mini-swe-agent` is roughly a
hundred lines, gives the model only a bash shell with no structured tool
interface at all, and outperforms the heavily-scaffolded `SWE-agent` it
descends from. Its stated argument is that scaffolding was a product of weaker
models and that its value shrinks as models improve. That is evidence of a
harness's value going negative, and it is the closest thing to a direct
refutation of this project's premise that the survey found.

It is not fatal. Its evidence is about capability rising over time, not about
small models specifically, and a 1B model is not a frontier model in 2023
clothing. But it does mean "more harness is better" cannot be assumed, and it
suggests a cheap and valuable control condition: run the same small models
through a bare loop with no registry, no guards and no profiles, as a third arm
alongside harness and native. If the bare loop matches the harness, that is the
most useful negative result this project could produce, and far better found by
us than by a reviewer.

**Support for a decision already made.** Several independent sources agree that
tool-catalogue size drives selection failure regardless of model size, with one
study reporting accuracy falling from roughly 78 percent at 10 tools to
roughly 14 percent past 100. That is direct support for the fourteen-tool
ceiling in `ms365-mcp` against the reference server's 326. It also raises a
question about our own registry: the literature rewards a small *visible* tool
set per step, and an immutable registry is only helping if it is small, not
merely fixed.

### An offline suite worth adding

BFCL, the Berkeley Function-Calling Leaderboard, is the best fit: it evaluates
tool-call correctness by AST rather than string match, has multi-turn and
agentic tracks, publishes small-model results, and runs locally against an
Ollama-served model with no paid API. It measures a narrower thing than our own
office tasks do, which is the point. A second, external, standard instrument
that anyone can reproduce is worth more to the central claim than another
in-house task pack.

Tau-2-bench is the better fit for multi-step stateful policy-following, but its
simulated user is normally another model, so running it fully offline means
substituting a local one. Real, but a cost.

## Ideas from other harnesses worth adopting

Ranked by risk, safest first.

1. **Per-model output-format routing.** Aider selects its edit format per model
   based on which one that model is empirically reliable at, and separately
   splits planning from formatting for exactly the reason we split driver from
   verifier. Our profiles already tune plan, verify and budget by model size;
   output format is the same kind of knob and there is public evidence it
   matters more than most.
2. **Check our parser against real local model output.** Cline's issue tracker
   documents Ollama-served small models emitting well-formed tool-call JSON
   that the harness's own parser rejected, producing infinite retry loops. That
   is a harness-side failure masquerading as a model failure, which is exactly
   what hard rule 5 forbids. Worth an afternoon against three real models
   before believing any number.
3. **Validate-then-reprompt as a measured alternative to our repair loop.**
   Pydantic AI builds this into its core. Worth comparing head to head on 1B to
   8B rather than assuming ours is better.
4. **The bare-loop control arm**, described above.
5. **An event-stream state model** for evidence, as OpenHands uses. Highest
   cost by far, and only worth it if the current evidence substrate proves
   insufficient. Watch, do not build.

## What this plan does not do

It does not add features to the engine speculatively. Phases 1 to 5 closed the
gaps that were identified against a reference; the next engine change should
come from a measurement, not from a survey. Everything above is either a
connector, a product, or an instrument for finding out whether the thesis is
true.
