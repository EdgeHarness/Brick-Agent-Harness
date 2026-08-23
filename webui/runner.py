"""Run one configured agent and emit a JSONL event stream."""
import argparse
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

from agents._shared.run_agent import validate_config  # noqa: E402
from harness.agent import run_harness  # noqa: E402
from harness.domain import load_domain  # noqa: E402
from harness import chat  # noqa: E402
from harness import mcp_bridge, mcp_config  # noqa: E402
from harness.llm import LLM, OLLAMA_URL  # noqa: E402
from harness.memory import MemoryStore  # noqa: E402
from harness.model_router import (  # noqa: E402
    ModelRouter,
    adapters_note,
    default_roles,
)
from harness.runtime import (  # noqa: E402
    AttemptContext,
    RunConfig,
    RunHooks,
)
from harness.storage import agent_runtime_paths  # noqa: E402
from webui.control import ConfirmationChannel, prune_logs, redact  # noqa: E402


AGENTS_DIR = os.path.join(PROJECT, "agents")
_AGENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def emit(event, **fields):
    line = json.dumps(
        {"t": event, "ts": round(time.time(), 3), **fields},
        ensure_ascii=False,
        default=str,
    )
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def emit_run_failure():
    """Keep redacted diagnostics local and emit only a browser-safe failure."""
    detail = redact(traceback.format_exc())
    sys.stderr.write(str(detail) + ("" if str(detail).endswith("\n") else "\n"))
    sys.stderr.flush()
    emit("error", message="the agent run failed")


def resolve_agent_folder(agent):
    if not isinstance(agent, str) or not _AGENT_ID.fullmatch(agent):
        raise ValueError(f"invalid configured-agent id {agent!r}")
    folder = os.path.abspath(os.path.join(AGENTS_DIR, agent))
    if os.path.dirname(folder) != os.path.abspath(AGENTS_DIR):
        raise ValueError(f"invalid configured-agent id {agent!r}")
    if not os.path.isfile(os.path.join(folder, "config.json")):
        raise ValueError(f"unknown configured agent {agent!r}")
    return folder


def world_snapshot(domain, attempt):
    return domain.present(attempt)


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


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--domain", default=None)
    parser.add_argument("--task", required=True)
    parser.add_argument("--max-calls", type=int, default=None)
    parser.add_argument("--tiers", action="store_true")
    parser.add_argument("--small", default=None)
    parser.add_argument("--deep", default=None)
    parser.add_argument("--mcp", default=None)
    parser.add_argument(
        "--mcp-mode", default=None,
        choices=("draft", "live", "read_only"),
    )
    parser.add_argument("--keep-office-tools", action="store_true")
    parser.add_argument(
        "--thread", default=None,
        help="conversation this run belongs to; earlier turns are "
             "read into the prompt. The server writes the turns, the "
             "runner only reads them, so a CLI run without one behaves "
             "exactly as it always did",
    )
    parser.add_argument(
        "--model", default=None,
        help="override the tag in the agent's config.json",
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
    validate_config(config_data)
    if args.model:
        # The folder still owns the state paths; only the tag doing the work
        # changes, so the run lands in the same workspace and memory.
        config_data["model"] = args.model
    assert (
        "127.0.0.1" in OLLAMA_URL or "localhost" in OLLAMA_URL
    ), "refusing non-local endpoint"

    domain = load_domain(
        args.domain or config_data.get("domain") or "office_demo"
    )
    paths = agent_runtime_paths(folder, domain)
    max_calls = args.max_calls
    if max_calls is None:
        max_calls = config_data.get("max_calls")
    if max_calls is None:
        max_calls = 14
    run_config = RunConfig(
        condition="harness",
        max_calls=max_calls,
        today=domain.default_today,
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
    confirmation_channel = ConfirmationChannel(sys.stdin, emit, args.run_id)

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
            **world_snapshot(domain, attempt_holder["attempt"]),
        )

    # Real accounts, if the run panel asked for any. The confirmation channel
    # already in place covers them: an MCP write is classified external_write
    # and the loop confirms it through the same browser prompt a simulated
    # write uses, so nothing here re-implements consent.
    registry = domain.registry
    mcp_effects = {}
    prompt_rules = domain.prompt_rules
    # Earlier turns of this conversation, if the run belongs to one.
    if args.thread:
        history = chat.prompt_block(chat.messages(folder, args.thread))
        if history:
            prompt_rules += history
    connected = None
    if args.mcp:
        mcp_cfg = config_data.get("mcp") or {}
        mcp_mode = args.mcp_mode or mcp_cfg.get("mode") or "draft"
        names = [n.strip() for n in args.mcp.split(",") if n.strip()]
        servers = mcp_config.names_to_servers(names, mcp_cfg, mode=mcp_mode)
        specs, mcp_effects, connected = mcp_bridge.enable(servers, mode=mcp_mode)
        if not args.keep_office_tools:
            registry = mcp_bridge.without_simulated(registry)
        registry = registry.merged(specs)
        prompt_rules += mcp_bridge.mail_rules(mcp_mode)

    attempt = AttemptContext(
        attempt_id=f"web:{domain.name}:{args.agent}:{time.time_ns()}",
        config=run_config,
        domain=domain,
        tools=registry,
        policy=domain.default_policy.with_effects(
            mcp_effects, confirmer=confirmation_channel.confirm
        ),
        world=world,
        memory=memory,
        workdir=workdir,
        artifact_dir=paths.artifacts,
        prompt_profile=domain.prompt_profile,
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
        toolset=domain.name,
        tiers=tiers,
        today=run_config.today_human,
        tools=list(registry.names()),
        mcp=({"mode": args.mcp_mode or "draft", "servers": connected,
              "warnings": mcp_config.count_warnings(connected)}
             if connected else None),
    )
    emit("world", **world_snapshot(domain, attempt))

    try:
        episode = run_harness(llm, args.task, attempt)
    except Exception:
        # Detailed diagnostics stay on the local terminal.  The stdout JSONL
        # stream is browser-visible and therefore carries only a generic error.
        emit_run_failure()
        raise SystemExit(1)

    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"run_{time.time_ns()}.json")
    payload = redact(
        {
            "task": args.task,
            "agent": args.agent,
            "model": config_data["model"],
            "domain": domain.name,
            "domain_version": domain.version,
            "via": "webui",
            "transcript": episode.transcript,
            "finished": episode.finished,
            "summary": episode.done_summary,
        }
    )
    encoded = json.dumps(payload, indent=1, ensure_ascii=False).encode("utf-8")
    if len(encoded) > 4 * 1024 * 1024:
        payload["transcript"] = payload.get("transcript", [])[-100:]
        payload["log_truncated"] = True
        encoded = json.dumps(payload, indent=1, ensure_ascii=False).encode("utf-8")
    if len(encoded) > 4 * 1024 * 1024:
        payload["transcript"] = payload.get("transcript", [])[-10:]
        encoded = json.dumps(payload, indent=1, ensure_ascii=False).encode("utf-8")
    temporary = log_path + ".tmp"
    with open(temporary, "xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, log_path)
    prune_logs(log_dir)

    emit("world", **world_snapshot(domain, attempt))
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
