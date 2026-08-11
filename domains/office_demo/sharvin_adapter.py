"""Isolated Llama 3.1 8B comparison adapter.

This module deliberately does not import Sharvin's package.  A caller supplies
an authorization-bound external checkout at one exact commit.  We read and
compile only ``agent.py``, ``profiles.py`` and ``tools.py`` under private module
names, removing their relative imports and injecting the narrow compatibility
surface below.  In particular, the upstream world, memory, office renderer,
filesystem, MCP, UI and launchers are never imported or executed.

Both comparison arms execute Brick's typed office contracts against Brick's
fresh per-attempt world.  They share one request/response implementation, one
paired seed, and the same 18-call / 6,144-token opportunity ledger.  The only
provider request-shape distinction is the intended treatment: native schemas
in ``tools`` for the baseline versus ``format=json`` for Sharvin's controller.
"""

import ast
import copy
import datetime
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
import threading
import time
from types import ModuleType

import requests

from domains.office_demo.contracts import build_registry
from domains.office_demo.world import World
from harness.evidence import canonical_json_bytes
from harness.experiment import (
    AttemptMemory,
    BudgetExhausted,
    ExecutionContext,
    ExperimentError,
    OpportunityLedger,
)
from harness.typed_executor import TypedToolRegistry


ADAPTER_VERSION = "brick.sharvin-balanced-adapter/1"
RUNTIME_SCHEMA = "brick.llama8-comparison-runtime/1"
SOURCE_BINDING_SCHEMA = "brick.sharvin-source-binding/1"
PINNED_COMMIT = "7efc9b9dc2c54684f88c372de3a5d620e5497a23"
PINNED_REMOTE = "https://github.com/SMalshe/Final-Agent-8B.git"
MODEL_TAG = "llama3.1:8b"
MAX_MODEL_CALLS = 18
MAX_GENERATED_TOKENS = 6144
MAX_TOKENS_PER_REQUEST = 700
NUM_CTX = 8192
KEEP_ALIVE = "30m"
OBS_LIMIT = 2000

_SOURCE_PATHS = (
    "standalone/harness/agent.py",
    "standalone/harness/profiles.py",
    "standalone/harness/tools.py",
    "standalone/agents/8b/config.json",
)
_BRICK_ROOT = Path(__file__).resolve().parents[2]
_WORD = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "a", "an", "to", "of", "and", "or", "for", "with", "my",
    "me", "i", "is", "are", "in", "on", "at", "it", "that", "this",
    "be", "do",
}


class SharvinAdapterError(RuntimeError):
    """The isolated adapter or its source binding is invalid."""


class _AttemptAbort(RuntimeError):
    """Private control-flow exception; the latched failure is authoritative."""


def _sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _git(checkout, *arguments):
    completed = subprocess.run(
        ["git", "-C", str(checkout)] + list(arguments),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode:
        raise SharvinAdapterError(
            "pinned source git check failed: " + completed.stderr.strip()
        )
    return completed.stdout.strip()


def _git_blob(checkout, relative):
    completed = subprocess.run(
        ["git", "-C", str(checkout), "show", PINNED_COMMIT + ":" + relative],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode:
        raise SharvinAdapterError("pinned source blob is unavailable: " + relative)
    return completed.stdout


def inspect_pinned_source(checkout):
    """Return the immutable source binding for one clean external checkout.

    This function never resolves a branch or fetches.  ``HEAD`` must already be
    the pinned object and the worktree (including untracked files) must be
    clean.  The returned document is intended to be copied into an independent
    authorization before :func:`load_authorized_source` is called.
    """

    checkout = Path(checkout).resolve()
    try:
        checkout.relative_to(_BRICK_ROOT.resolve())
    except ValueError:
        pass
    else:
        raise SharvinAdapterError("Sharvin source checkout must be external to Brick")
    if not (checkout / ".git").exists():
        raise SharvinAdapterError("Sharvin source is not a git checkout")
    if _git(checkout, "rev-parse", "HEAD") != PINNED_COMMIT:
        raise SharvinAdapterError("Sharvin source HEAD is not the pinned commit")
    if _git(checkout, "config", "--get", "remote.origin.url") != PINNED_REMOTE:
        raise SharvinAdapterError("Sharvin source remote differs from the pin")
    if _git(checkout, "status", "--porcelain=v1", "--untracked-files=all"):
        raise SharvinAdapterError("Sharvin source checkout is not clean")
    tracked = set(_git(checkout, "ls-files").splitlines())
    if not set(_SOURCE_PATHS).issubset(tracked):
        raise SharvinAdapterError("Sharvin source binding file is not tracked")
    files = {}
    for relative in _SOURCE_PATHS:
        path = checkout / Path(relative)
        if not path.is_file() or path.is_symlink():
            raise SharvinAdapterError("Sharvin source binding file is unavailable")
        # Bind and later execute the immutable Git blob bytes. A clean Windows
        # checkout may materialize CRLF while the committed blob is LF; hashing
        # the worktree would bind platform conversion instead of the source
        # object named by the authorization.
        files[relative] = _sha256_bytes(_git_blob(checkout, relative))
    try:
        config = json.loads(
            _git_blob(checkout, "standalone/agents/8b/config.json").decode(
                "utf-8-sig"
            )
        )
    except (OSError, ValueError) as exc:
        raise SharvinAdapterError("Sharvin 8B config is unreadable") from exc
    if not isinstance(config, dict) or config.get("model") != MODEL_TAG:
        raise SharvinAdapterError("Sharvin source does not bind llama3.1:8b")
    return {
        "schema_version": SOURCE_BINDING_SCHEMA,
        "repository": "SMalshe/Final-Agent-8B",
        "remote": PINNED_REMOTE,
        "commit_sha": PINNED_COMMIT,
        "model_tag": MODEL_TAG,
        "files": dict(sorted(files.items())),
    }


def _without_relative_imports(source, filename, expected):
    tree = ast.parse(source, filename=filename)
    found = []
    kept = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            signature = (
                node.module,
                tuple((item.name, item.asname) for item in node.names),
            )
            found.append(signature)
            continue
        kept.append(node)
    if tuple(found) != tuple(expected):
        raise SharvinAdapterError(
            "pinned upstream relative-import surface changed in " + filename
        )
    tree.body = kept
    return compile(ast.fix_missing_locations(tree), filename, "exec")


def _module_from_code(name, code, injected=None):
    module = ModuleType(name)
    module.__dict__.update(injected or {})
    exec(code, module.__dict__)  # noqa: S102 - exact, digest-bound local source
    return module


@dataclass
class AuthorizedSharvinSource:
    checkout: Path
    binding: dict
    agent: ModuleType
    profiles: ModuleType
    tools: ModuleType
    lock: object


def load_authorized_source(checkout, authorized_binding):
    """Load only the authorized upstream controller sources.

    ``authorized_binding`` must be a byte-semantic match for a fresh inspection;
    this function never creates its own authorization.
    """

    current = inspect_pinned_source(checkout)
    if not isinstance(authorized_binding, dict) or authorized_binding != current:
        raise SharvinAdapterError("current Sharvin source differs from authorization")
    checkout = Path(checkout).resolve()
    profiles_path = checkout / "standalone/harness/profiles.py"
    tools_path = checkout / "standalone/harness/tools.py"
    agent_path = checkout / "standalone/harness/agent.py"

    profiles_code = _without_relative_imports(
        _git_blob(checkout, "standalone/harness/profiles.py").decode("utf-8"),
        str(profiles_path), ()
    )
    profiles = _module_from_code("_brick_sharvin_profiles", profiles_code)

    tools_code = _without_relative_imports(
        _git_blob(checkout, "standalone/harness/tools.py").decode("utf-8"),
        str(tools_path),
        (
            (None, (("office", None),)),
            ("world", (("ToolError", None),)),
        ),
    )
    tools = _module_from_code("_brick_sharvin_tools", tools_code)

    # The injected execute function is replaced per attempt while holding the
    # source object's lock.  The placeholder makes accidental out-of-run use
    # fail closed.
    def unavailable_execute(*_args, **_kwargs):
        raise SharvinAdapterError("Sharvin execute adapter is not active")

    agent_code = _without_relative_imports(
        _git_blob(checkout, "standalone/harness/agent.py").decode("utf-8"),
        str(agent_path),
        (
            ("profiles", (("DEFAULT", "_DEFAULT_PROFILE"),)),
            (
                "tools",
                (
                    ("TOOLS", None), ("execute", None), ("tool_docs", None),
                    ("validate_call", None),
                ),
            ),
            (
                "world",
                (("SIM_TODAY", None), ("SIM_TODAY_HUMAN", None)),
            ),
        ),
    )
    agent = _module_from_code(
        "_brick_sharvin_agent",
        agent_code,
        {
            "_DEFAULT_PROFILE": profiles.DEFAULT,
            "TOOLS": tools.TOOLS,
            "execute": unavailable_execute,
            "tool_docs": tools.tool_docs,
            "validate_call": tools.validate_call,
            "SIM_TODAY": datetime.date(2000, 1, 1),
            "SIM_TODAY_HUMAN": "Saturday, January 1, 2000",
        },
    )
    profile = profiles.for_model(MODEL_TAG)
    expected_profile = {
        "label": "balanced", "plan": True, "plan_max_steps": 5,
        "verify_rounds": 2, "loop_break": True, "repeat_limit": 3,
        "repeat_limit_write": 1, "think_streak_cap": 2,
        "num_predict": 700, "memory_k": 3, "num_ctx": 8192,
        "max_calls": 20,
    }
    if any(getattr(profile, key, None) != value for key, value in expected_profile.items()):
        raise SharvinAdapterError("pinned Sharvin balanced profile changed")
    agent.set_profile(profile)
    agent.MAX_CALLS = MAX_MODEL_CALLS
    return AuthorizedSharvinSource(
        checkout, copy.deepcopy(current), agent, profiles, tools,
        threading.RLock(),
    )


def request_options(seed, num_predict):
    if type(seed) is not int or not 0 <= seed <= 0x7FFFFFFF:
        raise ValueError("paired request seed must be an unsigned 31-bit integer")
    if type(num_predict) is not int or not 1 <= num_predict <= MAX_TOKENS_PER_REQUEST:
        raise ValueError("request token limit is outside the frozen budget")
    return {
        "temperature": 0.0,
        "seed": seed,
        "num_ctx": NUM_CTX,
        "num_predict": num_predict,
    }


def _failure_from_exception(exc):
    failure = {
        "type": type(exc).__name__, "message": str(exc), "retryable": False,
    }
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if type(status) is int:
        failure["http_status"] = status
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        failure["category"] = "transport_connectivity"
        failure["retryable"] = True
        return "environment_unstable", "environment", failure
    if isinstance(exc, requests.HTTPError):
        if type(status) is int and 500 <= status <= 599:
            failure["category"] = "provider_server_error"
            failure["retryable"] = True
            return "environment_unstable", "environment", failure
        failure["category"] = "provider_request_rejected"
        return "runner_error", "runner", failure
    if isinstance(exc, OSError):
        failure["category"] = "unresolved_host_error"
        return "environment_unstable", "environment", failure
    failure["category"] = "adapter_or_response_error"
    return "runner_error", "runner", failure


def _validate_common_response(response, model, requested_limit):
    if not isinstance(response, dict):
        raise ExperimentError("Ollama response is not an object")
    if response.get("model") != model or response.get("done") is not True:
        raise ExperimentError("Ollama response identity or done marker is invalid")
    message = response.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise ExperimentError("Ollama response has no assistant message")
    if message.get("thinking") not in (None, ""):
        raise ExperimentError("unexpected thinking content appeared")
    for key in (
        "total_duration", "load_duration", "prompt_eval_count",
        "prompt_eval_duration", "eval_count", "eval_duration",
    ):
        if type(response.get(key)) is not int or response[key] < 0:
            raise ExperimentError("Ollama response telemetry is invalid: " + key)
    if response["eval_count"] > requested_limit:
        raise ExperimentError("Ollama generated more tokens than requested")
    return message


def _native_calls(message):
    raw = message.get("tool_calls", [])
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise ExperimentError("assistant tool_calls is not a list")
    result = []
    for item in raw:
        function = item.get("function") if isinstance(item, dict) else None
        if not isinstance(function, dict):
            raise ExperimentError("native tool call has no function object")
        name = function.get("name")
        arguments = function.get("arguments")
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise ExperimentError("native tool call name or arguments are malformed")
        result.append((name, arguments))
    return result


class _LedgeredClient:
    def __init__(self, model, transport, seed, treatment):
        if model != MODEL_TAG:
            raise ValueError("Llama comparison model tag differs")
        self.model = model
        self.transport = transport
        self.seed = seed
        self.treatment = treatment
        self.ledger = OpportunityLedger(
            MAX_MODEL_CALLS, MAX_GENERATED_TOKENS, MAX_TOKENS_PER_REQUEST
        )
        self.requests = []
        self.fatal = None
        self.prompt_tokens = 0
        self.output_tokens = 0
        self.wall = 0.0

    @property
    def calls(self):
        return self.ledger.calls

    def _latch(self, execution_status, origin, failure):
        if self.fatal is None:
            self.fatal = {
                "execution_status": execution_status,
                "failure_origin": origin,
                "failure": copy.deepcopy(failure),
            }

    def _close_unknown(self, requested, role):
        """Conservatively close a provider call with unusable telemetry."""

        try:
            self.ledger.finish_request_unknown(requested, role)
        except ExperimentError as exc:
            self._latch(
                "runner_error", "runner",
                {"type": type(exc).__name__, "message": str(exc),
                 "category": "opportunity_accounting"},
            )

    def chat(self, messages, force_json=False, num_predict=700, role=None,
             keep_alive=None):
        role = str(role or "driver")
        try:
            allowance = self.ledger.begin_request(role)
        except BudgetExhausted as exc:
            self._latch(
                "budget_exhausted", "model",
                {"type": "opportunity_budget_exhausted", "message": str(exc)},
            )
            raise _AttemptAbort("opportunity budget exhausted") from exc
        requested = min(allowance, int(num_predict))
        if requested < 1:
            self._latch(
                "budget_exhausted", "model",
                {"type": "opportunity_budget_exhausted"},
            )
            raise _AttemptAbort("opportunity budget exhausted")
        payload = {
            "model": self.model,
            "messages": copy.deepcopy(messages),
            "stream": False,
            "keep_alive": keep_alive or KEEP_ALIVE,
            "options": request_options(self.seed, requested),
        }
        if self.treatment:
            if not force_json:
                error = ExperimentError("Sharvin treatment requested unconstrained output")
                self.ledger.finish_request(0, requested, role)
                self._latch("runner_error", "runner", {
                    "type": type(error).__name__, "message": str(error),
                })
                raise _AttemptAbort(str(error))
            payload["format"] = "json"
        started = time.monotonic()
        try:
            response = self.transport.chat(payload)
        except Exception as exc:  # provider exception is classified, never leaked to model
            wall = time.monotonic() - started
            self._close_unknown(requested, role)
            status, origin, failure = _failure_from_exception(exc)
            self._latch(status, origin, failure)
            self.requests.append(self._failed_request(payload, role, requested, wall, failure))
            raise _AttemptAbort("provider request failed") from exc
        wall = time.monotonic() - started
        try:
            message = _validate_common_response(response, self.model, requested)
            if self.treatment:
                if _native_calls(message):
                    raise ExperimentError("JSON treatment returned native tool calls")
                content = message.get("content")
                if not isinstance(content, str):
                    raise ExperimentError("JSON treatment response content is not text")
            else:
                content = message.get("content", "")
                if not isinstance(content, str):
                    raise ExperimentError("native response content is not text")
            self.ledger.finish_request(response["eval_count"], requested, role)
        except Exception as exc:
            self._close_unknown(requested, role)
            self._latch(
                "runner_error", "runner",
                {"type": type(exc).__name__, "message": str(exc),
                 "category": "response_validation"},
            )
            self.requests.append(self._failed_request(
                payload, role, requested, wall, self.fatal["failure"], response
            ))
            raise _AttemptAbort("provider response validation failed") from exc
        self.wall += wall
        self.prompt_tokens += response["prompt_eval_count"]
        self.output_tokens += response["eval_count"]
        self.requests.append(self._successful_request(
            payload, response, role, requested, wall
        ))
        return content

    def native_chat(self, messages, tools):
        role = "driver"
        try:
            requested = self.ledger.begin_request(role)
        except BudgetExhausted as exc:
            self._latch(
                "budget_exhausted", "model",
                {"type": "opportunity_budget_exhausted", "message": str(exc)},
            )
            raise _AttemptAbort("opportunity budget exhausted") from exc
        payload = {
            "model": self.model,
            "messages": copy.deepcopy(messages),
            "tools": copy.deepcopy(tools),
            "stream": False,
            "keep_alive": KEEP_ALIVE,
            "options": request_options(self.seed, requested),
        }
        started = time.monotonic()
        try:
            response = self.transport.chat(payload)
        except Exception as exc:
            wall = time.monotonic() - started
            self._close_unknown(requested, role)
            status, origin, failure = _failure_from_exception(exc)
            self._latch(status, origin, failure)
            self.requests.append(self._failed_request(payload, role, requested, wall, failure))
            raise _AttemptAbort("provider request failed") from exc
        wall = time.monotonic() - started
        try:
            message = _validate_common_response(response, self.model, requested)
            calls = _native_calls(message)
            self.ledger.finish_request(response["eval_count"], requested, role)
        except Exception as exc:
            self._close_unknown(requested, role)
            self._latch(
                "runner_error", "runner",
                {"type": type(exc).__name__, "message": str(exc),
                 "category": "response_validation"},
            )
            self.requests.append(self._failed_request(
                payload, role, requested, wall, self.fatal["failure"], response
            ))
            raise _AttemptAbort("provider response validation failed") from exc
        self.wall += wall
        self.prompt_tokens += response["prompt_eval_count"]
        self.output_tokens += response["eval_count"]
        self.requests.append(self._successful_request(
            payload, response, role, requested, wall
        ))
        return copy.deepcopy(message), calls

    def _base_request(self, payload, role, requested, wall):
        return {
            "index": self.ledger.calls,
            "role": role,
            "seed": self.seed,
            "requested_num_predict": requested,
            "client_wall_seconds": wall,
            "request_sha256": _sha256_bytes(
                canonical_json_bytes(payload, allow_float=True)
            ),
            "request": copy.deepcopy(payload),
        }

    def _successful_request(self, payload, response, role, requested, wall):
        record = self._base_request(payload, role, requested, wall)
        record.update({
            "status": "ok",
            "prompt_eval_count": response["prompt_eval_count"],
            "eval_count": response["eval_count"],
            "total_duration": response["total_duration"],
            "load_duration": response["load_duration"],
            "prompt_eval_duration": response["prompt_eval_duration"],
            "eval_duration": response["eval_duration"],
            "done_reason": response.get("done_reason"),
            "response": copy.deepcopy(response),
        })
        return record

    def _failed_request(self, payload, role, requested, wall, failure, response=None):
        record = self._base_request(payload, role, requested, wall)
        record.update({
            "status": "failed", "failure": copy.deepcopy(failure),
            "response": copy.deepcopy(response),
        })
        return record


def _fresh_context(context):
    if not isinstance(context, ExecutionContext):
        raise TypeError("context must be an ExecutionContext")
    if not isinstance(context.world, World):
        raise TypeError("comparison attempts require Brick office World")
    if not isinstance(context.memory, AttemptMemory):
        raise TypeError("comparison attempts require AttemptMemory")
    if context.actions or context.memory.all():
        raise ValueError("comparison attempts require empty attempt-local state")
    if Path(context.artifact_dir).resolve() != Path(context.world.files_dir).resolve():
        raise ValueError("comparison artifacts must use the Brick world renderer directory")


def _today(value):
    if not isinstance(value, str):
        raise ValueError("today must be an ISO date")
    try:
        parsed = datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("today must be an ISO date") from exc
    human = "%s %d, %d" % (parsed.strftime("%A, %B"), parsed.day, parsed.year)
    return parsed, human


def _format_observation(value):
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _bounded_observation(value):
    text = _format_observation(value)
    return text if len(text) <= OBS_LIMIT else text[:OBS_LIMIT] + " ...[truncated]"


class _MemoryFacade:
    def __init__(self, memory):
        self.memory = memory

    def save(self, fact):
        return self.memory.save(fact)

    def search(self, query, k=3):
        wanted = {word for word in _WORD.findall(str(query).lower()) if word not in _STOP}
        scored = []
        for index, fact in enumerate(self.memory.all()):
            terms = {word for word in _WORD.findall(str(fact).lower()) if word not in _STOP}
            overlap = len(wanted & terms)
            if overlap:
                scored.append((-overlap, index, fact))
        scored.sort()
        return [fact for _score, _index, fact in scored[:k]]

    def all(self):
        return self.memory.all()


class _WorldFacade:
    def __init__(self, actions):
        self._actions = actions

    @property
    def actions(self):
        return copy.deepcopy(self._actions)

    def snapshot(self):
        return None


def _typed_execute(registry, context, verifier_actions, repair_queue, fatal_box):
    def execute(name, args, _world, _memory):
        outcome = registry.invoke(name, args, context)
        observation = outcome.result if outcome.ok else outcome.observation
        context.record(name, args, outcome, observation)
        if repair_queue:
            repair = repair_queue.pop(0)
            if repair["tool"] == name:
                context.actions[-1]["repairs"] = list(repair["notes"])
            else:
                repair_queue.insert(0, repair)
        if outcome.aborts_attempt:
            origin = outcome.fault.origin if outcome.fault else "runner"
            fatal_box["fatal"] = {
                "execution_status": (
                    "environment_unstable" if origin == "environment" else "runner_error"
                ),
                "failure_origin": origin,
                "failure": (
                    outcome.fault.as_record() if outcome.fault
                    else {"type": "typed_executor_abort"}
                ),
            }
            raise _AttemptAbort("typed executor aborted the attempt")
        # Upstream ``world.actions`` contains every call that reached tool
        # execution, including model-correctable tool failures.  Preserve that
        # semantic surface while excluding only pre-validation rejections that
        # never invoked the typed executor.
        verifier_actions.append({
            "tool": name, "args": copy.deepcopy(args), "ok": bool(outcome.ok),
            "result": copy.deepcopy(observation),
        })
        return outcome.ok, _format_observation(observation)
    return execute


def _base_result(client, context, transcript, subepisodes, started, unverified,
                 repairs, fatal=None):
    fatal = fatal or client.fatal
    if fatal is None:
        execution_status, origin, failure = "done", "none", None
    else:
        execution_status = fatal["execution_status"]
        origin = fatal["failure_origin"]
        failure = copy.deepcopy(fatal["failure"])
    model_seconds = sum(
        item.get("eval_duration", 0) / 1_000_000_000
        for item in client.requests if item.get("status") == "ok"
    )
    return {
        "schema_version": RUNTIME_SCHEMA,
        "execution_status": execution_status,
        "failure_origin": origin,
        "failure": failure,
        "ledger": client.ledger.as_record(),
        "requests": copy.deepcopy(client.requests),
        "subepisodes": copy.deepcopy(subepisodes),
        "transcript": copy.deepcopy(transcript),
        "diagnostics": {
            "unverified_completions": unverified,
            "repairs": copy.deepcopy(repairs),
            "adapter_version": ADAPTER_VERSION,
        },
        "metrics": {
            "model_calls": client.ledger.calls,
            "generated_tokens": (
                client.ledger.generated_tokens
                if client.ledger.generated_tokens_exact else None
            ),
            "model_eval_seconds": model_seconds,
            "wall_seconds": time.monotonic() - started,
            "successful_actions": sum(action["ok"] for action in context.actions),
            "action_count": len(context.actions),
        },
    }


def run_sharvin_attempt(*, source, model, transport, context, episodes, today, seed,
                        role="You are a careful office assistant."):
    """Run the pinned balanced controller over Brick's typed office surface."""

    del role  # upstream owns its exact system-role wording
    if not isinstance(source, AuthorizedSharvinSource):
        raise TypeError("source must be an AuthorizedSharvinSource")
    _fresh_context(context)
    day, human = _today(today)
    if not isinstance(episodes, list) or not episodes:
        raise ValueError("episodes must be a non-empty list")
    registry = build_registry(alias_recovery=False)
    if not isinstance(registry, TypedToolRegistry):
        raise SharvinAdapterError("Brick office registry is unavailable")
    client = _LedgeredClient(model, transport, seed, treatment=True)
    memory = _MemoryFacade(context.memory)
    transcript = []
    subepisodes = []
    repairs = []
    verifier_actions = []
    repair_queue = []
    fatal_box = {"fatal": None}
    terminal_fatal = None
    started = time.monotonic()

    with source.lock:
        agent = source.agent
        original_execute = agent.execute
        original_repair = agent.repair_args
        original_today = agent.SIM_TODAY
        original_human = agent.SIM_TODAY_HUMAN

        def repair_args(name, args):
            fixed, notes = original_repair(name, args)
            if notes:
                record = {
                    "tool": name, "before": copy.deepcopy(args),
                    "after": copy.deepcopy(fixed), "notes": list(notes),
                }
                repairs.append(record)
                repair_queue.append(record)
            return fixed, notes

        agent.execute = _typed_execute(
            registry, context, verifier_actions, repair_queue, fatal_box
        )
        agent.repair_args = repair_args
        agent.SIM_TODAY = day
        agent.SIM_TODAY_HUMAN = human
        agent.MAX_CALLS = MAX_MODEL_CALLS
        try:
            for episode in episodes:
                if not isinstance(episode, dict) or set(episode) != {"id", "prompt"}:
                    raise ValueError("episode shape is invalid")
                context.subepisode = episode["id"]
                episode_start = len(context.actions)
                facade = _WorldFacade(verifier_actions)
                try:
                    result = agent.run_harness(client, facade, memory, episode["prompt"])
                except _AttemptAbort:
                    result = None
                if result is not None:
                    transcript.append({"kind": "boundary", "subepisode": episode["id"]})
                    transcript.extend(copy.deepcopy(result.transcript))
                current_fatal = fatal_box["fatal"] or client.fatal
                if current_fatal is not None:
                    status = "instrument_failure" if current_fatal["failure_origin"] != "model" else "budget_exhausted"
                elif result is None or not result.finished:
                    current_fatal = {
                        "execution_status": "budget_exhausted",
                        "failure_origin": "model",
                        "failure": {"type": "opportunity_budget_exhausted"},
                    }
                    terminal_fatal = current_fatal
                    status = "budget_exhausted"
                else:
                    done_outcome = registry.invoke(
                        "done", {"summary": result.done_summary or "completed"}, context
                    )
                    context.record(
                        "done", {"summary": result.done_summary or "completed"},
                        done_outcome,
                        done_outcome.result if done_outcome.ok else done_outcome.observation,
                    )
                    if done_outcome.aborts_attempt:
                        origin = done_outcome.fault.origin if done_outcome.fault else "runner"
                        current_fatal = {
                            "execution_status": "runner_error",
                            "failure_origin": origin,
                            "failure": done_outcome.fault.as_record(),
                        }
                        terminal_fatal = current_fatal
                        status = "instrument_failure"
                    else:
                        status = "done"
                subepisodes.append({
                    "id": episode["id"], "status": status,
                    "action_start": episode_start,
                    "action_end": len(context.actions),
                })
                if status != "done":
                    terminal_fatal = current_fatal
                    break
        finally:
            agent.execute = original_execute
            agent.repair_args = original_repair
            agent.SIM_TODAY = original_today
            agent.SIM_TODAY_HUMAN = original_human

    unverified = 0
    for record in transcript:
        if record.get("kind") != "verify":
            continue
        try:
            verdict = json.loads(record.get("content", ""))
        except (TypeError, ValueError):
            continue
        if isinstance(verdict, dict) and verdict.get("unverified"):
            unverified += 1
    # At the exact call ceiling the upstream controller intentionally accepts
    # done without starting a verifier request. Preserve that behavior but make
    # the absent verification visible in evidence.
    completed = sum(item["status"] == "done" for item in subepisodes)
    verifier_records = sum(record.get("kind") == "verify" for record in transcript)
    if completed and verifier_records < completed and client.calls >= MAX_MODEL_CALLS:
        unverified += completed - verifier_records
    return _base_result(
        client, context, transcript, subepisodes, started, unverified, repairs,
        fatal_box["fatal"] or terminal_fatal,
    )


def _native_system(role, today):
    return (
        "%s Today is %s. Complete only the user's task using the offered "
        "native tools. Make exactly one native tool call per response. Inspect "
        "relevant source state before acting. Dates use YYYY-MM-DD and times "
        "use 24-hour HH:MM. Call done once the current task is complete."
    ) % (role, today)


def run_native_llama_attempt(*, model, transport, context, episodes, today, seed,
                             role="You are a careful office assistant."):
    """Run the matched minimal native-tool baseline on the Llama transport."""

    _fresh_context(context)
    _day, human = _today(today)
    if not isinstance(episodes, list) or not episodes:
        raise ValueError("episodes must be a non-empty list")
    registry = build_registry(alias_recovery=False)
    client = _LedgeredClient(model, transport, seed, treatment=False)
    schemas = registry.native_schemas()
    transcript = []
    subepisodes = []
    started = time.monotonic()
    fatal = None

    for episode in episodes:
        if not isinstance(episode, dict) or set(episode) != {"id", "prompt"}:
            raise ValueError("episode shape is invalid")
        context.subepisode = episode["id"]
        system = _native_system(role, human)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": episode["prompt"]},
        ]
        episode_start = len(context.actions)
        status = "running"
        transcript.extend([
            {"kind": "boundary", "subepisode": episode["id"]},
            {"kind": "system", "content": system},
            {"kind": "task", "content": episode["prompt"]},
        ])
        while status == "running":
            try:
                message, calls = client.native_chat(messages, schemas)
            except _AttemptAbort:
                fatal = client.fatal
                status = (
                    "budget_exhausted"
                    if fatal and fatal["failure_origin"] == "model"
                    else "instrument_failure"
                )
                break
            messages.append(copy.deepcopy(message))
            transcript.append({"kind": "assistant", "content": copy.deepcopy(message)})
            if len(calls) != 1:
                feedback = "ERROR: make exactly one native tool call; received %d." % len(calls)
                for name, args in calls:
                    context.record_rejection(name, args, "multiple_tool_calls", feedback)
                    messages.append({
                        "role": "tool", "tool_name": name, "content": feedback,
                    })
                if not calls:
                    messages.append({"role": "user", "content": feedback})
                transcript.append({"kind": "feedback", "content": feedback})
                continue
            name, args = calls[0]
            outcome = registry.invoke(name, args, context)
            observation = outcome.result if outcome.ok else outcome.observation
            context.record(name, args, outcome, observation)
            if outcome.aborts_attempt:
                origin = outcome.fault.origin if outcome.fault else "runner"
                fatal = {
                    "execution_status": (
                        "environment_unstable" if origin == "environment" else "runner_error"
                    ),
                    "failure_origin": origin,
                    "failure": (
                        outcome.fault.as_record() if outcome.fault
                        else {"type": "typed_executor_abort"}
                    ),
                }
                status = "instrument_failure"
                break
            if outcome.ok and name == "done":
                status = "done"
                transcript.append({"kind": "done", "content": args.get("summary", "")})
                break
            tool_message = {
                "role": "tool", "tool_name": name,
                "content": _bounded_observation(observation),
            }
            messages.append(tool_message)
            transcript.append({"kind": "observation", "content": tool_message["content"]})
        subepisodes.append({
            "id": episode["id"], "status": status,
            "action_start": episode_start, "action_end": len(context.actions),
        })
        if status != "done":
            break
    return _base_result(
        client, context, transcript, subepisodes, started, 0, [], fatal
    )


__all__ = [
    "ADAPTER_VERSION",
    "KEEP_ALIVE",
    "MAX_GENERATED_TOKENS",
    "MAX_MODEL_CALLS",
    "MAX_TOKENS_PER_REQUEST",
    "MODEL_TAG",
    "NUM_CTX",
    "PINNED_COMMIT",
    "PINNED_REMOTE",
    "AuthorizedSharvinSource",
    "SharvinAdapterError",
    "inspect_pinned_source",
    "load_authorized_source",
    "request_options",
    "run_native_llama_attempt",
    "run_sharvin_attempt",
]
