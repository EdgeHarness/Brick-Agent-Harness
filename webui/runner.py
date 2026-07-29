"""Run one configured agent and emit a JSONL event stream."""
import argparse
import datetime
import json
import os
import re
import sys
import time
import traceback


HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

from harness.agent import run_harness  # noqa: E402
from harness.builtin_tools import BUILTIN_EFFECTS, builtin_specs  # noqa: E402
from harness.domain import GENERIC_PROMPT_PROFILE, load_domain  # noqa: E402
from harness.fs_tools import build_overlay  # noqa: E402
from harness.llm import LLM, OLLAMA_URL  # noqa: E402
from harness.memory import MemoryStore  # noqa: E402
from harness.model_router import (  # noqa: E402
    ModelRouter,
    adapters_note,
    default_roles,
)
from harness.runtime import (  # noqa: E402
    ActionPolicy,
    AttemptContext,
    RunConfig,
    RunHooks,
)
from harness.storage import agent_runtime_paths  # noqa: E402
from harness.tools import ToolRegistry  # noqa: E402


AGENTS_DIR = os.path.join(PROJECT, "agents")
MAX_TREE_ENTRIES = 400
_AGENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def emit(event, **fields):
    line = json.dumps(
        {"t": event, "ts": round(time.time(), 3), **fields},
        ensure_ascii=False,
        default=str,
    )
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def resolve_agent_folder(agent):
    if not isinstance(agent, str) or not _AGENT_ID.fullmatch(agent):
        raise ValueError(f"invalid configured-agent id {agent!r}")
    folder = os.path.abspath(os.path.join(AGENTS_DIR, agent))
    if os.path.dirname(folder) != os.path.abspath(AGENTS_DIR):
        raise ValueError(f"invalid configured-agent id {agent!r}")
    if not os.path.isfile(os.path.join(folder, "config.json")):
        raise ValueError(f"unknown configured agent {agent!r}")
    return folder


def list_tree(root):
    """Return a shallow best-effort display of a selected filesystem root."""
    out = []
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        depth = dirpath[len(root):].count(os.sep)
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not name.startswith(".") and name != "__pycache__"
        )
        if depth >= 3:
            dirnames[:] = []
        for name in dirnames:
            relative = os.path.relpath(os.path.join(dirpath, name), root)
            out.append({"name": relative, "dir": True})
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            full = os.path.join(dirpath, name)
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            out.append(
                {"name": os.path.relpath(full, root), "size": size}
            )
        if len(out) >= MAX_TREE_ENTRIES:
            return out[:MAX_TREE_ENTRIES]
    return out


def world_snapshot(domain, attempt, root=None):
    snapshot = domain.present(attempt)
    if root:
        snapshot["tree"] = list_tree(root)
    return snapshot


class Confirmer:
    """Obtain destructive-action decisions from the parent web server."""

    def __init__(self):
        self.n = 0

    def __call__(self, action, detail):
        self.n += 1
        confirmation_id = self.n
        emit(
            "confirm",
            id=confirmation_id,
            action=action,
            detail=detail,
        )
        while True:
            line = sys.stdin.readline()
            if not line:
                return False
            try:
                answer = json.loads(line)
            except ValueError:
                continue
            if answer.get("id") == confirmation_id:
                return bool(answer.get("allow"))


def build_llm(config, args, log_dir, stream_hook):
    use_router = args.tiers or bool(config.get("router"))
    if not use_router:
        return (
            LLM(
                config["model"],
                num_ctx=config.get("num_ctx", 8192),
                stream_hook=stream_hook,
            ),
            None,
        )
    router_config = config.get("router", {})
    roles = router_config.get("roles") or default_roles(
        base=router_config.get("base", config["model"]),
        small=args.small or router_config.get("small"),
        deep=args.deep or router_config.get("deep", "qwen2.5:14b"),
    )
    os.makedirs(log_dir, exist_ok=True)
    router = ModelRouter(
        roles=roles,
        num_ctx=config.get("num_ctx", 8192),
        log_path=os.path.join(log_dir, "model_calls.jsonl"),
        stream_hook=stream_hook,
    )
    return router, router


def _surface(domain, root, include_domain, allow_shell, confirmer):
    if not root:
        return (
            domain.registry,
            domain.default_policy,
            domain.prompt_profile,
            domain.prompt_rules,
            None,
        )
    overlay = build_overlay(
        root, allow_shell=allow_shell, confirmer=confirmer
    )
    if include_domain:
        registry = domain.registry
        policy = domain.default_policy
        profile = domain.prompt_profile
        rules = domain.prompt_rules
    else:
        registry = ToolRegistry(builtin_specs())
        policy = ActionPolicy(BUILTIN_EFFECTS)
        profile = GENERIC_PROMPT_PROFILE
        rules = ""
    composed = overlay.compose(registry, policy, prompt_rules=rules)
    return (
        composed.registry,
        composed.policy,
        profile,
        composed.prompt_rules,
        overlay.root,
    )


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True)
    parser.add_argument("--domain", default=None)
    parser.add_argument("--task", required=True)
    parser.add_argument("--root", default=None)
    parser.add_argument("--shell", action="store_true")
    parser.add_argument("--yolo", action="store_true")
    parser.add_argument("--max-calls", type=int, default=None)
    parser.add_argument("--tiers", action="store_true")
    parser.add_argument("--small", default=None)
    parser.add_argument("--deep", default=None)
    parser.add_argument(
        "--with-domain",
        "--with-office",
        dest="with_domain",
        action="store_true",
    )
    args = parser.parse_args(argv)

    try:
        folder = resolve_agent_folder(args.agent)
    except ValueError as exc:
        parser.error(str(exc))
    with open(
        os.path.join(folder, "config.json"), encoding="utf-8-sig"
    ) as handle:
        config_data = json.load(handle)
    assert (
        "127.0.0.1" in OLLAMA_URL or "localhost" in OLLAMA_URL
    ), "refusing non-local endpoint"

    domain = load_domain(
        args.domain or config_data.get("domain") or "office_demo"
    )
    paths = agent_runtime_paths(folder, domain)
    allow_shell = args.shell or bool(config_data.get("allow_shell"))
    confirmer = None if args.yolo else Confirmer()
    tools, policy, profile, prompt_rules, root = _surface(
        domain,
        args.root or config_data.get("root"),
        args.with_domain,
        allow_shell,
        confirmer,
    )
    max_calls = args.max_calls
    if max_calls is None:
        max_calls = config_data.get("max_calls")
    if max_calls is None:
        max_calls = 40 if root else 14
    today = datetime.date.today() if root else domain.default_today
    run_config = RunConfig(
        condition="harness", max_calls=max_calls, today=today
    )

    state = {"call": 0}

    def on_stream(event, payload):
        if event == "start":
            state["call"] += 1
            emit(
                "llm_start",
                call=state["call"],
                budget=run_config.max_calls,
                role=payload.get("role") or "driver",
                model=payload.get("model"),
            )
        elif event == "token":
            emit("token", text=payload.get("text", ""))
        else:
            emit(
                "llm_end",
                role=payload.get("role") or "driver",
                ms=payload.get("ms", 0),
                output_tokens=payload.get("output_tokens", 0),
            )

    workdir = paths.workspace
    world = domain.make_world(workdir, persistent=True)
    memory = MemoryStore(
        str(paths.memory)
    )
    attempt_holder = {}

    def on_note(kind, content):
        emit("note", kind=kind, content=content)

    def on_tool(name, tool_args, ok, observation):
        emit(
            "tool",
            name=name,
            args=tool_args,
            ok=ok,
            result=observation,
        )
        emit(
            "world",
            **world_snapshot(domain, attempt_holder["attempt"], root),
        )

    attempt = AttemptContext(
        attempt_id=f"web:{domain.name}:{args.agent}:{time.time_ns()}",
        config=run_config,
        domain=domain,
        tools=tools,
        policy=policy,
        world=world,
        memory=memory,
        workdir=workdir,
        artifact_dir=paths.artifacts,
        prompt_profile=profile,
        prompt_rules=prompt_rules,
        hooks=RunHooks(on_note=on_note, on_tool=on_tool),
    )
    attempt_holder["attempt"] = attempt
    log_dir = str(paths.logs)
    llm, router = build_llm(
        config_data, args, log_dir, stream_hook=on_stream
    )

    tiers = None
    if router:
        tiers = {
            "roles": {
                role: spec["model"]
                for role, spec in router.roles.items()
            },
            "retained_hints": router.retained_model_hints(),
            "note": adapters_note(),
        }
    emit(
        "banner",
        agent=args.agent,
        name=config_data["name"],
        model=config_data["model"],
        note=config_data.get("note", ""),
        domain=domain.name,
        domain_version=domain.version,
        budget=run_config.max_calls,
        task=args.task,
        endpoint=OLLAMA_URL,
        root=root,
        shell=allow_shell,
        yolo=bool(args.yolo),
        toolset=(
            "files only"
            if root and not args.with_domain
            else f"files + {domain.name}"
            if root
            else domain.name
        ),
        tiers=tiers,
        today=run_config.today_human,
        tools=list(tools.names()),
    )
    emit("world", **world_snapshot(domain, attempt, root))

    try:
        episode = run_harness(llm, args.task, attempt)
    except Exception as exc:
        emit(
            "error",
            message=f"{type(exc).__name__}: {exc}",
            trace=traceback.format_exc(),
        )
        raise SystemExit(1)

    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(
        log_dir, f"run_{len(os.listdir(log_dir)) + 1:03d}.json"
    )
    with open(log_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "task": args.task,
                "root": root,
                "agent": args.agent,
                "model": config_data["model"],
                "domain": domain.name,
                "domain_version": domain.version,
                "via": "webui",
                "transcript": episode.transcript,
                "finished": episode.finished,
                "summary": episode.done_summary,
            },
            handle,
            indent=1,
            ensure_ascii=False,
        )

    emit("world", **world_snapshot(domain, attempt, root))
    emit(
        "end",
        finished=episode.finished,
        summary=episode.done_summary,
        calls=llm.calls,
        budget=run_config.max_calls,
        output_tokens=llm.output_tokens,
        prompt_tokens=llm.prompt_tokens,
        wall=round(llm.wall, 1),
        parse_failures=episode.parse_failures,
        invalid_calls=episode.invalid_calls,
        tool_errors=episode.tool_errors,
        actions=[
            action
            for action in attempt.actions
            if action["tool"] != "think"
        ],
        usage_by_role=router.usage_by_role() if router else None,
        log=os.path.relpath(log_path, PROJECT),
    )


if __name__ == "__main__":
    main()
