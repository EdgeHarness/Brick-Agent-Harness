"""Shared on-device runner used by every configured agent folder."""
import argparse
import json
import os
from pathlib import Path
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

from harness.agent import run_harness  # noqa: E402
from harness.domain import load_domain  # noqa: E402
from harness.llm import LLM, OLLAMA_URL  # noqa: E402
from harness.memory import MemoryStore  # noqa: E402
from harness import mcp_bridge, mcp_config, profiles  # noqa: E402
from harness.model_router import (  # noqa: E402
    ModelRouter,
    adapters_note,
    default_roles,
)
from harness.runtime import (  # noqa: E402
    AttemptContext,
    RunConfig,
)
from harness.storage import agent_runtime_paths  # noqa: E402


# LLM calls one interactive run may spend before the loop stops it. A ceiling,
# not a target: an agent that finishes in four calls costs four, so headroom is
# cheap while a tight number mostly buys premature cut-offs. Raised from 14,
# which was too tight once a run had to look before it wrote and every listing
# spent a call.
#
# NOT the benchmark budget. bench/run_bench.py keeps its own DEFAULT_MAX_CALLS,
# because that number is part of a recorded experiment.
DEFAULT_MAX_CALLS = 50


ALLOWED_CONFIG_KEYS = frozenset(
    {
        "domain",
        "harness",
        "max_calls",
        "mcp",
        "model",
        "name",
        "note",
        "num_ctx",
        "router",
    }
)
REMOVED_CAPABILITY_FLAGS = frozenset(
    {
        "--root",
        "--shell",
        "--yolo",
        "--with-domain",
        "--with-office",
    }
)


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def parse_flags(argv):
    """Parse the shared CLI without treating misspelled flags as model tasks."""
    parser = argparse.ArgumentParser(
        description="Run one configured synthetic-domain research agent.",
        allow_abbrev=False,
    )
    parser.add_argument("--max-calls", type=_positive_int)
    parser.add_argument("--tiers", action="store_true")
    parser.add_argument("--small")
    parser.add_argument("--deep")
    parser.add_argument("--domain", dest="domain_name")
    parser.add_argument(
        "--mcp",
        help="comma-separated MCP servers from mcp/servers.json, or "
             "'none' to override a config that enables some",
    )
    parser.add_argument(
        "--mcp-mode", choices=("draft", "live", "read_only")
    )
    parser.add_argument(
        "--mcp-list",
        action="store_true",
        help="connect, print the tools each server would expose, and exit",
    )
    parser.add_argument(
        "--mcp-help",
        action="store_true",
        help="print what each registered server needs, and exit",
    )
    parser.add_argument(
        "--keep-office-tools",
        action="store_true",
        help="keep the simulated inbox and calendar alongside real ones",
    )
    parser.add_argument("task", nargs="*")
    # Preserve the historical ability to put flags between unquoted task
    # words while retaining argparse's strict option validation.
    parsed = parser.parse_intermixed_args(argv)
    options = {
        "max_calls": parsed.max_calls,
        "tiers": parsed.tiers or bool(parsed.small) or bool(parsed.deep),
        "small": parsed.small,
        "deep": parsed.deep,
        "domain_name": parsed.domain_name,
        "mcp": parsed.mcp,
        "mcp_mode": parsed.mcp_mode,
        "mcp_list": parsed.mcp_list,
        "mcp_help": parsed.mcp_help,
        "keep_office_tools": parsed.keep_office_tools,
    }
    return options, " ".join(parsed.task).strip()


def validate_config(config):
    """Reject undeclared configuration before model or runtime access."""
    if not isinstance(config, dict):
        raise TypeError("configured-agent JSON must contain an object")
    unknown = sorted(set(config) - ALLOWED_CONFIG_KEYS)
    if unknown:
        raise ValueError(
            "unsupported configured-agent fields: " + ", ".join(unknown)
        )
    for required in ("name", "model"):
        if not isinstance(config.get(required), str) or not config[required]:
            raise ValueError(
                f"configured-agent field {required!r} must be nonempty"
            )


def build_llm(config, options, log_dir, stream_hook=None):
    """Construct one LLM/router for this active attempt."""
    use_router = options["tiers"] or bool(config.get("router"))
    if not use_router:
        return (
            LLM(
                config["model"],
                num_ctx=config.get("num_ctx", 8192),
                stream_hook=stream_hook,
                retries=2,
            ),
            None,
        )
    router_config = config.get("router", {})
    roles = router_config.get("roles") or default_roles(
        base=router_config.get("base", config["model"]),
        small=options["small"] or router_config.get("small"),
        deep=options["deep"]
        or router_config.get("deep", "qwen2.5:14b"),
    )
    log_path = os.path.join(log_dir, "model_calls.jsonl")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    router = ModelRouter(
        roles=roles,
        num_ctx=config.get("num_ctx", 8192),
        log_path=log_path,
        stream_hook=stream_hook,
    )
    return router, router


def _mcp_names(options, config_data):
    """Which servers to connect: --mcp overrides the agent config entirely.

    An explicit empty --mcp (or "none") means none, so a flag can switch a
    config that enables connectors back off. Absent, the config decides.
    """
    cfg = config_data.get("mcp") or {}
    if options["mcp"] is None:
        return list(cfg.get("enable") or []), cfg
    asked = [n.strip() for n in options["mcp"].split(",") if n.strip()]
    return ([] if asked == ["none"] else asked), cfg


def _terminal_confirmer(mode):
    """Consent for a write that touches a real account.

    ActionPolicy denies when there is no confirmer, so the CLI has to supply
    one or every real write fails. A bare Enter is not consent."""
    def confirm(action, detail):
        print(f"\n  [{mode}] {action}: {detail}")
        try:
            return input("  allow this? [y/N] ").strip().lower() in ("y", "yes")
        except EOFError:
            return False
    return confirm


def _connect_mcp(options, config_data):
    """Launch the requested servers and return (specs, effects, summary, mode).

    Returns None when no connector was asked for, which is the default: without
    --mcp nothing in mcp/ runs and the agent talks to the simulated office.
    """
    names, cfg = _mcp_names(options, config_data)
    if not names:
        return None
    mode = options["mcp_mode"] or cfg.get("mode") or "draft"
    servers = mcp_config.names_to_servers(names, cfg, mode=mode)
    specs, effects, summary = mcp_bridge.enable(servers, mode=mode)
    return specs, effects, summary, mode


def _print_mcp_tools(summary, specs, effects):
    for server in summary:
        print(f"{server['id']}  ({server['mode']})")
        for name in server["tools"]:
            kind = "write" if effects[name] == "external_write" else "read"
            print(f"    {kind:>5}  {name}")
    for warning in mcp_config.count_warnings(summary):
        print(f"  ! {warning}")


def main(agent_dir=None, argv=None):
    if agent_dir is None:
        raise ValueError("agent_dir is required; invoke an agents/<size> shim")
    options, task = parse_flags(
        list(sys.argv[1:] if argv is None else argv)
    )
    if options["mcp_help"]:
        for name, _ in mcp_config.available():
            print(mcp_config.setup_notes(name))
            print()
        return
    agent_dir = os.path.abspath(agent_dir)
    with open(
        os.path.join(agent_dir, "config.json"), encoding="utf-8-sig"
    ) as handle:
        config_data = json.load(handle)
    validate_config(config_data)
    assert (
        "127.0.0.1" in OLLAMA_URL or "localhost" in OLLAMA_URL
    ), "refusing non-local endpoint"

    connected = _connect_mcp(options, config_data)
    if options["mcp_list"]:
        if connected is None:
            print("no MCP servers requested; pass --mcp <name> or --mcp-help")
        else:
            specs, effects, summary, _ = connected
            _print_mcp_tools(summary, specs, effects)
        return

    if not task:
        task = input("Task for the agent: ").strip()
    if not task:
        print("No task given.")
        return

    domain = load_domain(
        options["domain_name"]
        or config_data.get("domain")
        or "office_demo"
    )
    registry = domain.registry
    policy = domain.default_policy
    prompt_rules = domain.prompt_rules
    if connected is not None:
        specs, effects, summary, mcp_mode = connected
        if not options["keep_office_tools"]:
            registry = mcp_bridge.without_simulated(registry)
        registry = registry.merged(specs)
        policy = policy.with_effects(
            effects, confirmer=_terminal_confirmer(mcp_mode)
        )
        prompt_rules += mcp_bridge.mail_rules(mcp_mode)

    paths = agent_runtime_paths(agent_dir, domain)
    profile = profiles.for_model(
        config_data["model"], config_data.get("harness")
    )
    max_calls = options["max_calls"]
    if max_calls is None:
        max_calls = config_data.get("max_calls")
    if max_calls is None:
        max_calls = profile.max_calls
    run_config = RunConfig(
        condition="harness",
        max_calls=max_calls,
        today=domain.default_today,
        verifier_rounds=profile.verify_rounds,
        guards=True,
        profile=profile,
    )

    workdir = paths.workspace
    world = domain.make_world(workdir, persistent=True)
    memory = MemoryStore(
        str(paths.memory)
    )
    attempt = AttemptContext(
        attempt_id=f"{domain.name}:{Path(agent_dir).name}",
        config=run_config,
        domain=domain,
        tools=registry,
        policy=policy,
        world=world,
        memory=memory,
        workdir=workdir,
        artifact_dir=paths.artifacts,
        prompt_profile=domain.prompt_profile,
        prompt_rules=prompt_rules,
    )
    llm, router = build_llm(
        config_data, options, str(paths.logs)
    )

    print(
        f"[{config_data['name']}] configured for local Ollama endpoint "
        f"{OLLAMA_URL}"
    )
    print(f"  domain: {domain.name}@{domain.version}")
    if connected is not None:
        specs, effects, summary, mcp_mode = connected
        print(f"  real accounts: "
              + ", ".join(f"{x['id']} ({len(x['tools'])} tools)" for x in summary)
              + f"  mode: {mcp_mode}")
        # Inference is still local; the loopback assertion above still holds.
        # It is the TOOLS that can now leave. Say so, because "nothing leaves
        # the machine" stops being true for the tool calls. Worded without
        # claiming every connector is remote: selftest is not, and a warning
        # that is wrong about the connector people test with is a warning they
        # learn to skip.
        print("  NOTE: model inference stays on this machine. Connector tool "
              "calls need not: a real-account connector reaches its provider.")
        for warning in mcp_config.count_warnings(summary):
            print(f"  ! {warning}")
    if router:
        print(
            "  model tiers: "
            + ", ".join(
                f"{role}={spec['model']}"
                for role, spec in router.roles.items()
            )
        )
        print(
            "  configured for reuse: "
            + ", ".join(router.retained_model_hints())
            + "  (keep-alive hints; actual residency is backend-managed)"
        )
        print(f"  {adapters_note()}")
    else:
        print(f"  model: {config_data['model']}")
    print(f"  profile: {profile.label}")
    print(f"  budget: {run_config.max_calls} LLM calls")
    episode = run_harness(llm, task, attempt)

    print("\n--- run finished ---")
    print(
        f"finished cleanly: {episode.finished}   llm calls: {llm.calls}   "
        f"tokens out: {llm.output_tokens}   wall: {llm.wall:.0f}s"
    )
    if router:
        for role, usage in router.usage_by_role().items():
            print(
                f"  tier {role:<8} {usage['model']:<16} "
                f"{usage['calls']:>2} calls  "
                f"{usage['output_tokens']:>5} out-tok  "
                f"{usage['ms'] / 1000:>5.1f}s"
            )
    if episode.done_summary:
        print(f"agent summary: {episode.done_summary}")
    actions = [
        action for action in attempt.actions if action["tool"] != "think"
    ]
    if actions:
        print("actions taken:")
        for action in actions:
            print(
                f"  - {action['tool']}("
                f"{json.dumps(action['args'], ensure_ascii=False, default=str)[:120]})"
                f" -> {'ok' if action['ok'] else 'ERROR'}"
            )
    print(f"files: {attempt.artifact_dir}")
    log_dir = str(paths.logs)
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(
        log_dir, f"run_{len(os.listdir(log_dir)) + 1:03d}.json"
    )
    with open(log_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "task": task,
                "domain": domain.name,
                "domain_version": domain.version,
                "transcript": episode.transcript,
                "finished": episode.finished,
                "summary": episode.done_summary,
            },
            handle,
            indent=1,
            ensure_ascii=False,
        )
    print(f"transcript: {log_path}")


if __name__ == "__main__":
    main()
