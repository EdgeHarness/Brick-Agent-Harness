"""Fail-closed receipt-v1 agent loop.

This module is opt-in.  The legacy loops remain untouched for frozen research
comparisons.  Receipt-v1 adds durable lifecycle evidence, deterministic route
preflight, an execution-receipt ledger, cooperative cancellation, and
authoritative completion over domain state.
"""

import difflib
import hashlib
import json

from . import guards as _guards
from .agent import (
    Episode,
    HARNESS_SYSTEM,
    PLAN_PROMPT,
    SHAPE,
    _AttemptLLM,
    _obs,
    _shrink_context,
    build_harness_system,
    parse_lenient,
    repair_args,
)
from .completion import PostconditionResult, evaluate
from .lifecycle import (
    JournalWriteError,
    LifecycleJournal,
    digest_value,
    journal_path,
    read_and_verify,
)
from .receipts import TaskLedger
from .router_contract import CapabilityError, preflight_backend
from .runtime_recipe import build_runtime_recipe
from .tool_pipeline import ToolPipeline


RUNTIME_PROTOCOL = "receipt_v1"
_SAFE_CALL_GUARDS = (
    ("wrong_date", _guards.guard_wrong_date),
    ("unread_file", _guards.guard_unread_file),
    ("read_before_write", _guards.guard_read_before_write),
)
_REPLAN_PROMPT = (
    'TASK: {task}\n\nThe accepted plan was:\n{plan}\n\n'
    'A result now suggests another mutating tool may be necessary. Add only '
    'the remaining tools justified by the task and results. Reply with one '
    'JSON object: {{"steps": [{{"tool": "<tool name>", "what": '
    '"<5 words>"}}]}}.'
)


class _Cancelled(RuntimeError):
    pass


def _task_postconditions(attempt):
    if attempt.completion_checker is not None:
        return attempt.completion_checker(attempt)
    if attempt.authoritative_task_id is None:
        return None
    task = next(
        (
            item
            for item in attempt.domain.tasks
            if item.id == attempt.authoritative_task_id
        ),
        None,
    )
    if task is None:
        return PostconditionResult(
            None, detail="authoritative task definition is unavailable"
        )
    outcome = task.grader.grade_attempt(attempt, task.id)
    if outcome.strict_success is None:
        return PostconditionResult(
            None, detail="authoritative grader is unavailable"
        )
    missing = tuple(
        description
        for _check_id, description, passed in outcome.checks
        if not passed
    )
    return PostconditionResult(bool(outcome.strict_success), missing=missing)


def _extract_steps(reply, registry, max_steps):
    parsed, _ = parse_lenient(reply)
    steps = []
    if isinstance(parsed, dict) and isinstance(parsed.get("steps"), list):
        for candidate in parsed["steps"][:max_steps]:
            if not isinstance(candidate, dict):
                continue
            tool = candidate.get("tool")
            if tool not in registry or tool == "done":
                continue
            steps.append(
                {"tool": tool, "what": str(candidate.get("what", ""))[:60]}
            )
    return steps


def _render_plan(steps):
    return "\n".join(
        "{}. {} - {}".format(index + 1, step["tool"], step["what"])
        for index, step in enumerate(steps)
    )


def _completion_record(attempt, verdict):
    return evaluate(
        lambda: _task_postconditions(attempt), verdict=verdict
    )


def run_receipt_v1(llm, task_text, attempt):
    if attempt.config.runtime_protocol != RUNTIME_PROTOCOL:
        raise ValueError("run_receipt_v1 requires runtime_protocol=receipt_v1")
    episode = Episode(attempt.hooks.on_note)
    episode.runtime_protocol = RUNTIME_PROTOCOL
    config = attempt.config
    profile = config.profile
    delegate = llm
    metered = _AttemptLLM(delegate, config.max_calls)
    journal = None
    terminal_written = False

    def terminal(event, payload):
        nonlocal terminal_written
        journal.append(event, payload)
        terminal_written = True

    def finish_cancelled(reason):
        episode.finished = False
        episode.terminal_status = "cancelled"
        episode.note("terminal", "cancelled")
        if journal is not None and not terminal_written:
            terminal(
                "run.cancelled",
                {"status": "cancelled", "reason": reason},
            )

    try:
        path = journal_path(attempt.workdir, attempt.attempt_id)
        episode.lifecycle_path = str(path)
        journal = LifecycleJournal(path)
        recipe, recipe_digest = build_runtime_recipe(attempt, delegate)
        router_digest = recipe["router_digest"]
        task_ref = attempt.authoritative_task_id or "interactive"
        journal.append(
            "run.started",
            {
                "protocol": RUNTIME_PROTOCOL,
                "domain": "{}@{}".format(
                    attempt.domain.name, attempt.domain.version
                ),
                "recipe_digest": recipe_digest,
                "router_digest": router_digest,
                "task_ref": task_ref,
            },
        )

        request_counter = {"value": 0}

        def model_call(messages, *, role, num_predict, force_json=True):
            if attempt.cancelled():
                raise _Cancelled("cancelled_before_model")
            decision = preflight_backend(
                delegate,
                role,
                required=("chat", "json_object"),
                min_context=max(
                    1,
                    sum(
                        len(str(item.get("content", "")))
                        for item in messages
                    )
                    // 4
                    + num_predict,
                ),
            )
            input_digest = digest_value(messages)
            request_id = hashlib.sha256(
                json.dumps(
                    {
                        "attempt": attempt.attempt_id,
                        "sequence": request_counter["value"],
                        "role": role,
                        "input_digest": input_digest,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            request_counter["value"] += 1
            journal.append(
                "model.requested",
                {
                    "request_id": request_id,
                    "role": role,
                    "message_count": len(messages),
                    "input_digest": input_digest,
                    "route_digest": decision.decision_digest,
                },
            )
            try:
                reply = metered.chat(
                    messages,
                    force_json=force_json,
                    role=role,
                    num_predict=num_predict,
                )
            except Exception as exc:
                journal.append(
                    "model.failed",
                    {
                        "request_id": request_id,
                        "failure_class": type(exc).__name__,
                    },
                )
                raise
            parsed, _ = parse_lenient(reply)
            journal.append(
                "model.returned",
                {
                    "request_id": request_id,
                    "output_digest": digest_value(reply),
                    "parsed": isinstance(parsed, dict),
                },
            )
            if attempt.cancelled():
                raise _Cancelled("cancelled_after_model")
            return reply

        memories = attempt.memory.search(task_text, k=profile.memory_k)
        memory_block = ""
        if memories:
            memory_block = (
                "\n\nTHINGS YOU HAVE LEARNED PREVIOUSLY "
                "(apply them when relevant):\n"
                + "\n".join("- {}".format(item) for item in memories)
            )
        managed_rules = (
            "\n- This run uses an accepted execution plan. A mutating tool "
            "outside that plan is rejected.\n- A done claim is accepted only "
            "when authoritative state and signed execution receipts agree."
        )
        system = build_harness_system(
            attempt.tools,
            config.today_human,
            attempt.resolved_prompt_profile,
            memory_block=memory_block,
            extra_rules=(
                attempt.resolved_prompt_rules
                + config.prompt_rules
                + managed_rules
            ),
        )
        messages = [{"role": "system", "content": system}]
        episode.note("system", system)
        episode.note("task", task_text)

        plan_request = {
            "role": "user",
            "content": "TASK: {}\n\n{}".format(task_text, PLAN_PROMPT),
        }
        plan_reply = model_call(
            messages + [plan_request],
            role="router",
            num_predict=250,
        )
        steps = _extract_steps(
            plan_reply, attempt.tools, profile.plan_max_steps
        )
        plan = _render_plan(steps)
        episode.note(
            "plan", plan or "(no executable steps in plan reply)"
        )
        journal.append(
            "plan.accepted",
            {
                "plan_digest": digest_value(steps),
                "step_count": len(steps),
            },
        )
        ledger = TaskLedger(attempt.attempt_id, steps)
        pipeline = ToolPipeline(attempt, journal, ledger)
        episode.ledger = ledger.summary()

        act = "TASK: {}\n\n".format(task_text)
        if plan:
            act += (
                "Accepted tool sequence (results may justify a reviewed "
                "extension):\n{}\n\n".format(plan)
            )
        act += (
            "Make the first tool call now. Reply with exactly one JSON "
            "object: {}".format(SHAPE)
        )
        messages.append({"role": "user", "content": act})

        guard_state = None
        if config.guards:
            write_tools = frozenset(
                name
                for name in attempt.tools.names()
                if attempt.policy.is_mutating(name)
            )
            guard_state = _guards.GuardState(
                metered,
                episode,
                messages,
                task_text,
                registry=attempt.tools,
                write_tools=write_tools,
                plan=plan,
                artifact_dir=attempt.artifact_dir,
                today=config.today,
                history=config.history,
            )

        invalid_streak = 0
        last_reply = None
        seen_calls = set()
        verifier_count = 0

        def feedback(text, reply):
            nonlocal last_reply
            if (
                reply == last_reply
                and len(messages) >= 3
                and messages[-3]["role"] == "assistant"
                and messages[-3]["content"] == reply
            ):
                del messages[-3:-1]
                text = "Repeated invalid reply. " + text
            messages.append({"role": "user", "content": text})
            episode.note("feedback", text)
            last_reply = reply

        def extend_plan():
            nonlocal plan
            if metered.calls >= config.max_calls:
                return False
            ask = _REPLAN_PROMPT.format(task=task_text, plan=plan or "(none)")
            reply = model_call(
                messages + [{"role": "user", "content": ask}],
                role="router",
                num_predict=250,
            )
            additions = _extract_steps(
                reply, attempt.tools, profile.plan_max_steps
            )
            # Do not append duplicate pending work; a repeated plan is not new
            # authorization for a second side effect.
            pending_tools = {
                entry.tool for entry in ledger.entries
                if entry.grounded_by is None
            }
            additions = [
                item for item in additions if item["tool"] not in pending_tools
            ]
            if not additions:
                return False
            ledger.extend(additions)
            rendered = _render_plan(additions)
            plan = "{}\n{}".format(plan, rendered).strip()
            journal.append(
                "plan.accepted",
                {
                    "plan_digest": digest_value(additions),
                    "step_count": len(additions),
                },
            )
            episode.note("replan", rendered)
            if guard_state is not None:
                guard_state.plan = plan
                guard_state.planned = _guards.planned_tools(
                    plan, attempt.tools
                )
                guard_state.planned_set = set(guard_state.planned)
            return True

        while metered.calls < config.max_calls:
            if attempt.cancelled():
                raise _Cancelled("cancelled_between_steps")
            if profile.prune_context:
                _shrink_context(messages, profile.num_ctx, episode)
            if (
                profile.invalid_streak_break
                and invalid_streak >= profile.invalid_streak_break
            ):
                episode.note("stuck", "invalid-call streak limit reached")
                break
            reply = model_call(
                messages,
                role="driver",
                num_predict=profile.num_predict,
            )
            invalid_streak += 1
            messages.append({"role": "assistant", "content": reply})
            episode.note("model", reply)
            obj, error = parse_lenient(reply)
            if obj is None:
                episode.parse_failures += 1
                feedback(
                    "FORMAT ERROR: {}. Reply with exactly one JSON object: {}".format(
                        error, SHAPE
                    ),
                    reply,
                )
                continue
            name = str(obj.get("tool") or obj.get("name") or "").strip()
            args = obj.get("args") if isinstance(obj.get("args"), dict) else {}
            if not args:
                args = {
                    key: value
                    for key, value in obj.items()
                    if key not in {"tool", "name", "thought", "args"}
                }

            if name == "done":
                if guard_state is not None:
                    guard_state.summary = str(args.get("summary", ""))
                    questioned = _guards.run_guards(
                        guard_state, _guards.DONE_GUARDS
                    )
                    if questioned:
                        guard_name, message = questioned
                        episode.note("guard", guard_name)
                        feedback(message, reply)
                        continue

                verdict = None
                if (
                    verifier_count < config.verifier_rounds
                    and metered.calls < config.max_calls
                ):
                    verifier_count += 1
                    verifier_prompt = [
                        {
                            "role": "system",
                            "content": (
                                "Explain whether the task appears complete. "
                                "Your answer is advisory; state checks decide."
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "task": task_text,
                                    "actions": [
                                        {
                                            "tool": item["tool"],
                                            "ok": item["ok"],
                                        }
                                        for item in attempt.actions
                                    ],
                                    "shape": {
                                        "complete": True,
                                        "missing": "short explanation",
                                    },
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ]
                    verifier_reply = model_call(
                        verifier_prompt,
                        role="verifier",
                        num_predict=200,
                    )
                    verdict, _ = parse_lenient(verifier_reply)
                    episode.note("verify", verifier_reply)

                attempt.snapshot()
                decision = _completion_record(attempt, verdict)
                episode.completion = decision.as_record()
                episode.ledger = ledger.summary()
                journal.append(
                    "completion.checked",
                    {
                        "status": decision.status,
                        "reason": decision.reason,
                        "ledger_complete": ledger.completion_ready,
                    },
                )
                if decision.is_complete and ledger.completion_ready:
                    episode.done_summary = str(args.get("summary", ""))
                    episode.finished = True
                    episode.terminal_status = "completed"
                    episode.note("done", episode.done_summary)
                    terminal(
                        "run.completed",
                        {
                            "status": "completed",
                            "completion_status": decision.status,
                        },
                    )
                    break
                if decision.status == "unknown":
                    episode.terminal_status = "incomplete"
                    terminal(
                        "run.incomplete",
                        {
                            "status": "incomplete",
                            "completion_status": "unknown",
                            "reason": "authoritative_check_unavailable",
                        },
                    )
                    break
                missing = "; ".join(decision.missing) or (
                    "accepted plan entries remain ungrounded"
                )
                feedback(
                    "COMPLETION CHECK: task is not proven complete. Missing: "
                    + missing,
                    reply,
                )
                continue

            args, fixes = repair_args(name, args, attempt.tools)
            if fixes:
                episode.note("repair", "; ".join(fixes))
            args = attempt.domain.normalize_args(name, args, config.today)
            problems = attempt.tools.validate(name, args)
            if problems:
                episode.invalid_calls += 1
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
                        hint = " Did you mean {!r}?".format(close[0])
                feedback(
                    "INVALID CALL: {}.{}".format(
                        "; ".join(problems), hint
                    ),
                    reply,
                )
                continue
            last_reply = reply

            if guard_state is not None:
                guard_state.name, guard_state.args = name, args
                questioned = _guards.run_guards(
                    guard_state, _SAFE_CALL_GUARDS
                )
                if questioned:
                    guard_name, message = questioned
                    episode.note("guard", guard_name)
                    feedback(message, reply)
                    continue

            if (
                attempt.policy.is_mutating(name)
                and ledger.pending_entry_for(name) is None
            ):
                if extend_plan() and ledger.pending_entry_for(name) is not None:
                    feedback(
                        "The accepted plan was extended. Repeat the tool call "
                        "if it is still required.",
                        reply,
                    )
                    continue

            signature = digest_value({"tool": name, "args": args})
            if (
                profile.loop_break
                and signature in seen_calls
                and attempt.tools.suppresses_identical_repeats(name)
                and ledger.pending_entry_for(name) is None
            ):
                feedback(
                    "That exact call already ran. Use its result, take the "
                    "next step, or call done.",
                    reply,
                )
                continue

            result = pipeline.execute(name, args)
            # A blocking executor can complete after cancellation was
            # requested. Preserve the real receipt and grounding first, then
            # terminate explicitly instead of falling through to budget-based
            # completion with stale cancellation state.
            episode.ledger = ledger.summary()
            invalid_streak = 0
            seen_calls.add(signature)
            if result.status == "cancelled":
                raise _Cancelled("cancelled_at_tool_boundary")
            if attempt.cancelled():
                raise _Cancelled("cancelled_after_tool")
            if not result.ok:
                episode.tool_errors += 1
            if guard_state is not None and result.ok:
                if name not in guard_state.write_tools and name != "think":
                    guard_state.looked = True
                    filename_pattern = _guards.filename_re(attempt.tools)
                    if filename_pattern:
                        guard_state.mentioned_files.update(
                            filename_pattern.findall(result.observation)
                        )
                if attempt.tools[name].get("opens"):
                    guard_state.opened_files.add(
                        str(args.get("filename", ""))
                    )
            observation = _obs(
                result.observation,
                config.observation_limit,
                profile.observation_keep_tail,
            )
            messages.append(
                {"role": "user", "content": "OBSERVATION: " + observation}
            )
            episode.note("observation", observation)
            episode.ledger = ledger.summary()

        if not terminal_written:
            attempt.snapshot()
            decision = _completion_record(attempt, None)
            episode.completion = decision.as_record()
            episode.ledger = ledger.summary()
            journal.append(
                "completion.checked",
                {
                    "status": decision.status,
                    "reason": decision.reason,
                    "ledger_complete": ledger.completion_ready,
                },
            )
            if decision.is_complete and ledger.completion_ready:
                episode.finished = True
                episode.terminal_status = "completed"
                terminal(
                    "run.completed",
                    {
                        "status": "completed",
                        "completion_status": "complete",
                    },
                )
            else:
                episode.finished = False
                episode.terminal_status = "incomplete"
                terminal(
                    "run.incomplete",
                    {
                        "status": "incomplete",
                        "completion_status": decision.status,
                        "reason": "budget_or_requirements_remaining",
                    },
                )

    except _Cancelled as exc:
        try:
            attempt.snapshot()
        finally:
            finish_cancelled(str(exc))
    except (CapabilityError, JournalWriteError) as exc:
        episode.finished = False
        episode.terminal_status = "failed"
        episode.note("instrument_fault", type(exc).__name__)
        if journal is not None and not terminal_written:
            try:
                terminal(
                    "run.failed",
                    {"status": "failed", "reason": type(exc).__name__},
                )
            except JournalWriteError:
                pass
    except Exception as exc:
        episode.finished = False
        episode.terminal_status = "failed"
        episode.note("instrument_fault", type(exc).__name__)
        if journal is not None and not terminal_written:
            try:
                terminal(
                    "run.failed",
                    {"status": "failed", "reason": type(exc).__name__},
                )
            except JournalWriteError:
                pass
    finally:
        if journal is not None:
            journal.close()

    if terminal_written:
        try:
            read_and_verify(episode.lifecycle_path)
        except Exception as exc:
            episode.finished = False
            episode.terminal_status = "failed"
            episode.note("instrument_fault", type(exc).__name__)
    return episode


__all__ = ["RUNTIME_PROTOCOL", "run_receipt_v1"]
