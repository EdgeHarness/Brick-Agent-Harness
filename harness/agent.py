"""Two agent loops over the SAME tools and the SAME LLM-call budget.

raw     - what you get wiring a model to tools naively: tool list in the
          prompt, strict JSON parsing, errors fed back verbatim, no other help.

harness - the scaffolding under test:
          1. few-shot example per tool in the docs
          2. grammar-constrained decoding (Ollama format=json)
          3. lenient JSON extraction + repair feedback
          4. deterministic call repair (rename near-miss params, drop unknowns,
             lift top-level args) before rejecting anything
          5. schema validation with corrective, example-bearing feedback
          6. domain-supplied argument normalization (the office demo resolves
             date/time expressions against its configured clock)
          7. a tool-grounded plan step (JSON list of tool names, not free prose)
          8. loop-breaking: repeated identical calls are not re-executed; the
             duplicated exchanges are removed from context (they act as
             attractors for small models) and the task is restated
          9. a verifier pass before accepting done()
         10. auto-injection of relevant long-term memories

Both loops stop after the configured total LLM invocations, so the harness pays
for its plan/verify/repair calls out of the same budget.
"""
import copy
import difflib
import json
import re

from . import guards as _guards

# Abstract on purpose: concrete example content in an instruction becomes an
# attractor that 1B models copy verbatim. Real examples live per-tool in docs.
SHAPE = '{"thought": "<why>", "tool": "<tool_name>", "args": { ... }}'


# ---------------------------------------------------------------- parsing ----

def strip_fences(text):
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return m.group(1).strip() if m else text.strip()


def parse_strict(text):
    """Raw condition: fence-strip + json.loads, nothing else."""
    try:
        obj = json.loads(strip_fences(text))
        if isinstance(obj, dict):
            return obj, None
        return None, "response was not a JSON object"
    except Exception as e:
        return None, f"response was not valid JSON ({e})"


def parse_lenient(text):
    """Harness condition: also brace-match the first object and repair
    trailing commas."""
    obj, err = parse_strict(text)
    if obj is not None:
        return obj, None
    text = strip_fences(text)
    start = text.find("{")
    if start == -1:
        return None, "no JSON object found in response"
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                cand = text[start:i + 1]
                for fix in (cand, re.sub(r",\s*([}\]])", r"\1", cand)):
                    try:
                        obj = json.loads(fix)
                        if isinstance(obj, dict):
                            return obj, None
                    except Exception:
                        pass
                return None, "found a {...} block but it is not valid JSON"
    return None, "unbalanced braces in response"


def repair_args(name, args, registry):
    """Deterministic near-miss repair: rename close-match parameter names to
    the missing required ones, then drop unknown parameters. Returns
    (fixed_args, [notes])."""
    spec = registry.get(name)
    if not spec or not isinstance(args, dict):
        return args, []
    valid = spec["params"]
    out = dict(args)
    notes = []
    unknown = [k for k in out if k not in valid]
    missing = [p for p, (_, req) in valid.items() if req and out.get(p) in (None, "")]
    for miss in missing:
        cand = difflib.get_close_matches(miss, unknown, n=1, cutoff=0.5)
        if not cand:
            cand = [u for u in unknown if u in miss or miss in u]
        if cand:
            out[miss] = out.pop(cand[0])
            unknown.remove(cand[0])
            notes.append(f"renamed '{cand[0]}' -> '{miss}'")
    for u in unknown:
        out.pop(u)
        notes.append(f"dropped unknown parameter '{u}'")
    return out, notes


# ------------------------------------------------------------- transcripts ----

class Episode:
    def __init__(self, note_hook=None):
        self.transcript = []   # readable log of everything
        self.parse_failures = 0
        self.invalid_calls = 0
        self.tool_errors = 0
        self.done_summary = None
        self.finished = False
        self._note_hook = note_hook

    def note(self, kind, content):
        self.transcript.append({"kind": kind, "content": content})
        if self._note_hook:
            try:
                self._note_hook(kind, copy.deepcopy(content))
            except Exception:
                # Observers are best-effort and must not abort an attempt.
                pass


def _obs(text, limit=2000):
    text = str(text)
    return text if len(text) <= limit else text[:limit] + " ...[truncated]"


def _execute_with_policy(attempt, name, args):
    """Require an explicit one-shot decision for host/external effects."""
    effect = attempt.policy.effect(name)
    if effect in ("external_write", "shell"):
        detail = json.dumps(
            {"tool": name, "args": args}, sort_keys=True,
            ensure_ascii=False, default=str,
        )[:4_096]
        if not attempt.policy.confirm(name, detail):
            observation = "ERROR: operator confirmation was denied or unavailable"
            attempt.record_action(name, args, False, observation)
            if attempt.hooks.on_tool:
                try:
                    attempt.hooks.on_tool(name, args, False, observation)
                except Exception:
                    pass
            return False, observation
    return attempt.tools.execute(name, args, attempt)


class _AttemptLLM:
    """Attempt-local call meter around an LLM or ModelRouter.

    This isolates only call budgeting when a delegate is reused. Delegate
    counters, caches, logs, and stream hooks are not concurrency-safe;
    first-party callers use one delegate per active attempt.
    """

    def __init__(self, delegate, max_calls):
        self.delegate = delegate
        self.max_calls = max_calls
        self.calls = 0

    def chat(self, *args, **kwargs):
        if self.calls >= self.max_calls:
            raise RuntimeError("attempt LLM-call budget exhausted")
        result = self.delegate.chat(*args, **kwargs)
        self.calls += 1
        return result


# ------------------------------------------------------------------- RAW ----

RAW_SYSTEM = """{role} Today is {today}.

Available tools:
{docs}{extra_rules}

Respond with a single JSON object of the form {{"tool": "<tool name>", "args": {{...}}}}. \
Call the done tool when the task is finished."""


def build_raw_system(
    registry, today_human, prompt_profile, extra_rules=""
):
    return RAW_SYSTEM.format(
        role=prompt_profile.raw_role,
        today=today_human,
        docs=registry.docs(with_examples=False),
        extra_rules=extra_rules,
    )


def run_raw(llm, task_text, attempt):
    ep = Episode(attempt.hooks.on_note)
    config = attempt.config
    llm = _AttemptLLM(llm, config.max_calls)
    profile = attempt.resolved_prompt_profile
    system = build_raw_system(
        attempt.tools,
        config.today_human,
        profile,
        extra_rules=(
            attempt.resolved_prompt_rules + config.prompt_rules
        ),
    )
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": task_text}]
    ep.note("system", system)
    ep.note("task", task_text)

    while llm.calls < config.max_calls:
        reply = llm.chat(messages, force_json=False)
        messages.append({"role": "assistant", "content": reply})
        ep.note("model", reply)
        obj, err = parse_strict(reply)
        if obj is None:
            ep.parse_failures += 1
            fb = f"ERROR: {err}. Respond with a single JSON object: {{\"tool\": ..., \"args\": {{...}}}}"
            messages.append({"role": "user", "content": fb})
            ep.note("feedback", fb)
            continue
        name = obj.get("tool") or obj.get("name") or ""
        args = obj.get("args") if isinstance(obj.get("args"), dict) else {}
        if name == "done":
            ep.done_summary = str(args.get("summary", ""))
            ep.finished = True
            ep.note("done", ep.done_summary)
            break
        ok, obs = _execute_with_policy(attempt, name, args)
        if not ok:
            ep.tool_errors += 1
        obs = _obs(obs, config.observation_limit)
        messages.append({"role": "user", "content": f"OBSERVATION: {obs}"})
        ep.note("observation", obs)
    attempt.snapshot()
    return ep


# --------------------------------------------------------------- HARNESS ----

HARNESS_SYSTEM = """{role} Today is {today}.
{scope}

RESPONSE FORMAT - every reply must be exactly one JSON object:
{shape}

Rules:
- ONE tool call per reply. No text outside the JSON object.
- Only do what the task requires - nothing extra.
- Look before you act: {look_before_act}
{format_rule}
- If a tool returns an ERROR, fix the arguments and try again.
- When every part of the task is complete, call done with a short summary.

TOOLS:
{docs}{memory_block}{extra_rules}"""

PLAN_PROMPT = ('Which tools will you need to call to complete this task, in order? '
               'Reply with one JSON object: {"steps": [{"tool": "<tool_name>", "what": "<5 words>"}, ...]}. '
               'Most tasks need only 1-4 calls. Do not include tools the task does not need.')


def plan_step(llm, messages, ep, registry, max_steps=6):
    """Ask for a tool-grounded plan; return it as short text (or ''). Invalid
    tool names are dropped - free prose never enters the context."""
    reply = llm.chat(messages, force_json=True, num_predict=250, role="router")
    obj, _ = parse_lenient(reply)
    steps = []
    if isinstance(obj, dict) and isinstance(obj.get("steps"), list):
        for s in obj["steps"][:max_steps]:
            if isinstance(s, dict) and s.get("tool") in registry:
                what = str(s.get("what", ""))[:60]
                steps.append(f"{len(steps) + 1}. {s['tool']} - {what}")
    plan = "\n".join(steps)
    ep.note("plan", plan or f"(unusable plan reply: {reply[:200]})")
    return plan


def build_harness_system(
    registry,
    today_human,
    prompt_profile,
    memory_block="",
    extra_rules="",
):
    return HARNESS_SYSTEM.format(
        role=prompt_profile.harness_role,
        today=today_human,
        scope=prompt_profile.scope,
        look_before_act=prompt_profile.look_before_act,
        format_rule=prompt_profile.format_rule,
        shape=SHAPE,
        docs=registry.docs(with_examples=True),
        memory_block=memory_block,
        extra_rules=extra_rules,
    )


def run_harness(llm, task_text, attempt):
    ep = Episode(attempt.hooks.on_note)
    config = attempt.config
    llm = _AttemptLLM(llm, config.max_calls)
    profile = config.profile
    memories = attempt.memory.search(
        task_text, k=profile.memory_k
    )  # inject only matches, never a recency fallback
    memory_block = ""
    if memories:
        memory_block = ("\n\nTHINGS YOU HAVE LEARNED PREVIOUSLY (apply them when relevant):\n"
                        + "\n".join(f"- {f}" for f in memories))
    system = build_harness_system(
        attempt.tools,
        config.today_human,
        attempt.resolved_prompt_profile,
        memory_block=memory_block,
        extra_rules=attempt.resolved_prompt_rules + config.prompt_rules,
    )
    messages = [{"role": "system", "content": system}]
    ep.note("system", system)
    ep.note("task", task_text)

    plan = ""
    if profile.plan:
        messages.append(
            {"role": "user", "content": f"TASK: {task_text}\n\n{PLAN_PROMPT}"}
        )
        plan = plan_step(llm, messages, ep, attempt.tools,
                         max_steps=profile.plan_max_steps)
        messages.pop()  # the plan request leaves the context; the plan re-enters as user guidance
    act = f"TASK: {task_text}\n\n"
    if plan:
        act += f"Suggested tool sequence (adapt if the results demand it):\n{plan}\n\n"
    act += f"Make the first tool call now. Reply with exactly one JSON object: {SHAPE}"
    messages.append({"role": "user", "content": act})

    g = None
    if config.guards:
        write_tools = frozenset(
            n for n in attempt.tools.names() if attempt.policy.is_mutating(n)
        )
        g = _guards.GuardState(
            llm, ep, messages, task_text,
            registry=attempt.tools, write_tools=write_tools, plan=plan,
            artifact_dir=attempt.artifact_dir, today=config.today,
            history=config.history,
        )

    verify_rounds = 0
    seen_calls = {}      # signature -> (world_version, repeats, last_ok)
    world_version = 0    # bumped on successful writes; repeated reads are only
                         # suppressed while the world is unchanged
    last_reply = None
    think_streak = 0

    def give_feedback(fb, reply):
        """Append corrective feedback; a verbatim-repeated bad reply gets its
        older copy deleted from context (repetition is an attractor)."""
        nonlocal last_reply
        if reply == last_reply and len(messages) >= 3 \
                and messages[-3]["role"] == "assistant" and messages[-3]["content"] == reply:
            del messages[-3:-1]
            fb = "You repeated the same invalid reply. It is still invalid. " + fb
        messages.append({"role": "user", "content": fb})
        ep.note("feedback", fb)
        last_reply = reply

    while llm.calls < config.max_calls:
        reply = llm.chat(messages, force_json=True, role="driver",
                         num_predict=profile.num_predict)
        messages.append({"role": "assistant", "content": reply})
        ep.note("model", reply)
        obj, err = parse_lenient(reply)
        if obj is None:
            ep.parse_failures += 1
            give_feedback(f"FORMAT ERROR: {err}. Reply with exactly one JSON object: {SHAPE}", reply)
            continue
        name = str(obj.get("tool") or obj.get("name") or "").strip()
        args = obj.get("args") if isinstance(obj.get("args"), dict) else {}
        if not args:
            # repair: models sometimes put args at the top level next to "tool"
            args = {k: v for k, v in obj.items() if k not in ("tool", "name", "thought", "args")}

        if name == "done":
            if (
                verify_rounds < config.verifier_rounds
                and llm.calls < config.max_calls
            ):
                verify_rounds += 1
                verdict = _verify(llm, task_text, attempt)
                ep.note("verify", json.dumps(verdict, ensure_ascii=False))
                if not verdict.get("complete", True):
                    give_feedback("VERIFIER: the task is NOT finished yet. Missing: "
                                  f"{verdict.get('missing', 'unknown')}. Continue with the next tool call.",
                                  reply)
                    continue
            if g is not None:
                g.summary = str(args.get("summary", ""))
                questioned = _guards.run_guards(g, _guards.DONE_GUARDS)
                if questioned:
                    guard_name, message = questioned
                    ep.note("guard", guard_name)
                    give_feedback(message, reply)
                    continue
            ep.done_summary = str(args.get("summary", ""))
            ep.finished = True
            ep.note("done", ep.done_summary)
            break

        args, fixes = repair_args(name, args, attempt.tools)
        if fixes:
            ep.note("repair", "; ".join(fixes))
        args = attempt.domain.normalize_args(name, args, config.today)

        problems = attempt.tools.validate(name, args)
        if problems:
            ep.invalid_calls += 1
            hint = ""
            if name in attempt.tools:
                hint = " Correct shape: " + json.dumps(
                    attempt.tools[name]["example"], ensure_ascii=False
                )
            else:
                close = difflib.get_close_matches(
                    name, attempt.tools.keys(), n=1
                )
                if close:
                    hint = (f" Did you mean '{close[0]}'? Correct shape: "
                            + json.dumps(
                                attempt.tools[close[0]]["example"],
                                ensure_ascii=False,
                            ))
            give_feedback("INVALID CALL: " + "; ".join(problems) + "." + hint
                          + " Reply with one corrected JSON object.", reply)
            continue
        last_reply = reply

        if g is not None:
            # The cross-checks. First guard to speak wins and nothing after
            # it runs, so a question cannot be reversed downstream.
            g.name, g.args = name, args
            questioned = _guards.run_guards(g)
            if questioned:
                guard_name, message = questioned
                ep.note("guard", guard_name)
                give_feedback(message, reply)
                continue

        sig = json.dumps({"t": name, "a": args}, sort_keys=True, default=str)
        # A call may repeat up to its profile budget while the world is
        # unchanged; any successful write moves world_version and hands out a
        # fresh budget, because the same call can now legitimately return
        # something new. At the default limits of 1 this is exactly the
        # original one-execution rule.
        last_version, repeats, last_ok = seen_calls.get(sig, (None, 0, True))
        if last_version != world_version:
            repeats = 0
        limit = (profile.repeat_limit_write if attempt.policy.is_mutating(name)
                 else profile.repeat_limit)
        if not last_ok:
            # A repeat budget exists so a model can look at something twice.
            # That reasoning only holds for a call that WORKED: an identical
            # call that errored against an unchanged world will produce the
            # identical error, so a budget above one buys copies of the same
            # failure.
            limit = 1
        if (
            profile.loop_break
            and name != "think"
            and attempt.tools.suppresses_identical_repeats(name)
            and repeats >= limit
        ):
            # Identical call, unchanged world, budget spent: do not
            # re-execute. If it is a verbatim repeat of the previous exchange,
            # delete the older copy (repetition in context is an attractor for
            # small models).
            if len(messages) >= 3 and messages[-3]["role"] == "assistant" \
                    and messages[-3]["content"] == reply:
                del messages[-3:-1]
            if not last_ok:
                fb = (f"{name} with exactly those arguments already failed, and nothing has "
                      f"changed since, so it will fail the same way. Its error is above - fix "
                      f"the arguments or use a different tool. The task is: \"{task_text}\"")
            elif limit == 1:
                # byte-identical to the phrasing the benchmark runs on
                fb = (f"You already called {name} with exactly those arguments; its result is above "
                      f"and has not changed. Do the NEXT step of the task: \"{task_text}\" "
                      f"If everything is complete, call done.")
            else:
                fb = (f"You have called {name} with exactly those arguments {repeats} times now; "
                      f"its result is above and has not changed. Do the NEXT step of the task: "
                      f"\"{task_text}\" If everything is complete, call done.")
            messages.append({"role": "user", "content": fb})
            ep.note("feedback", fb)
            continue
        think_streak = think_streak + 1 if name == "think" else 0

        ok, obs = _execute_with_policy(attempt, name, args)
        if g is not None and ok:
            if name not in g.write_tools and name != "think":
                g.looked = True
                # A filename the run was told about, from the result rather
                # than from the model's own words: a model that writes "I'll
                # check data.xlsx" has not been told anything.
                fre = _guards.filename_re(attempt.tools)
                if fre:
                    g.mentioned_files.update(fre.findall(str(obs)))
            if attempt.tools[name].get("opens"):
                g.opened_files.add(str(args.get("filename", "")))
        if ok and attempt.policy.is_mutating(name):
            world_version += 1
        # recorded against the world version AFTER any bump, so an identical
        # write stacked on its own result still counts as a repeat
        seen_calls[sig] = (world_version, repeats + 1, ok)
        if not ok:
            ep.tool_errors += 1
        obs = _obs(obs, config.observation_limit)
        if think_streak >= profile.think_streak_cap:
            obs += " NOTE: stop thinking and take a concrete action now."
        messages.append({"role": "user", "content": f"OBSERVATION: {obs}"})
        ep.note("observation", obs)
    attempt.snapshot()
    return ep


def _verify(llm, task_text, attempt):
    acts = [a for a in attempt.actions if a["tool"] != "think"]
    lines = []
    for a in acts:
        status = "ok" if a["ok"] else "FAILED"
        lines.append(f"- {a['tool']}({json.dumps(a['args'], ensure_ascii=False, default=str)[:200]}) -> {status}")
    prompt = (f"TASK GIVEN TO AN ASSISTANT:\n{task_text}\n\n"
              f"ACTIONS THE ASSISTANT TOOK:\n" + "\n".join(lines or ["(none)"])
              + "\n\nCheck the task requirements one by one against the actions. "
                'Respond with one JSON object: {"complete": true or false, "missing": "<what has not been done>"}')
    msgs = [{"role": "system", "content": "You are a strict task-completion verifier. Today is "
             + attempt.config.today_human + "."},
            {"role": "user", "content": prompt}]
    try:
        reply = llm.chat(msgs, force_json=True, num_predict=200, role="verifier")
        obj, _ = parse_lenient(reply)
        if isinstance(obj, dict) and isinstance(obj.get("complete"), bool):
            return obj
    except Exception:
        pass
    return {"complete": True, "missing": ""}


def run(llm, task_text, attempt):
    """Execute the condition resolved on one explicit AttemptContext."""
    if attempt.config.condition == "harness":
        return run_harness(llm, task_text, attempt)
    return run_raw(llm, task_text, attempt)
