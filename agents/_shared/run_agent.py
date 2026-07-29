"""Shared on-device runner used by every configured agent folder."""
import datetime
import json
import os
from pathlib import Path
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
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
)
from harness.storage import agent_runtime_paths  # noqa: E402
from harness.tools import ToolRegistry  # noqa: E402


def parse_flags(argv):
    options = {
        "root": None,
        "shell": False,
        "yolo": False,
        "max_calls": None,
        "tiers": False,
        "small": None,
        "deep": None,
        "domain_name": None,
        "include_domain": False,
    }
    rest = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--root" and index + 1 < len(argv):
            options["root"] = argv[index + 1]
            index += 2
        elif arg == "--shell":
            options["shell"] = True
            index += 1
        elif arg == "--yolo":
            options["yolo"] = True
            index += 1
        elif arg == "--max-calls" and index + 1 < len(argv):
            options["max_calls"] = int(argv[index + 1])
            index += 2
        elif arg == "--tiers":
            options["tiers"] = True
            index += 1
        elif arg == "--small" and index + 1 < len(argv):
            options["small"] = argv[index + 1]
            options["tiers"] = True
            index += 2
        elif arg == "--deep" and index + 1 < len(argv):
            options["deep"] = argv[index + 1]
            options["tiers"] = True
            index += 2
        elif arg == "--domain" and index + 1 < len(argv):
            options["domain_name"] = argv[index + 1]
            index += 2
        elif arg in ("--with-domain", "--with-office"):
            options["include_domain"] = True
            index += 1
        else:
            rest.append(arg)
            index += 1
    return options, " ".join(rest).strip()


def build_llm(config, options, log_dir, stream_hook=None):
    """Construct one LLM/router for this active attempt."""
    use_router = options["tiers"] or bool(config.get("router"))
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


def confirm(action, detail):
    print(f"\n  the agent wants to {action}:\n    {detail}")
    try:
        return input("  allow? [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


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
        root,
        allow_shell=allow_shell,
        confirmer=confirmer,
    )
    if include_domain:
        base_registry = domain.registry
        base_policy = domain.default_policy
        profile = domain.prompt_profile
        prompt_rules = domain.prompt_rules
    else:
        base_registry = ToolRegistry(builtin_specs())
        base_policy = ActionPolicy(BUILTIN_EFFECTS)
        profile = GENERIC_PROMPT_PROFILE
        prompt_rules = ""
    surface = overlay.compose(
        base_registry, base_policy, prompt_rules=prompt_rules
    )
    return (
        surface.registry,
        surface.policy,
        profile,
        surface.prompt_rules,
        overlay.root,
    )


def main(agent_dir=None, argv=None):
    if agent_dir is None:
        raise ValueError("agent_dir is required; invoke an agents/<size> shim")
    agent_dir = os.path.abspath(agent_dir)
    with open(
        os.path.join(agent_dir, "config.json"), encoding="utf-8-sig"
    ) as handle:
        config_data = json.load(handle)
    assert (
        "127.0.0.1" in OLLAMA_URL or "localhost" in OLLAMA_URL
    ), "refusing non-local endpoint"

    options, task = parse_flags(
        list(sys.argv[1:] if argv is None else argv)
    )
    root_option = options["root"] or config_data.get("root")
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
    paths = agent_runtime_paths(agent_dir, domain)
    allow_shell = options["shell"] or bool(config_data.get("allow_shell"))
    tools, policy, profile, prompt_rules, root = _surface(
        domain,
        root_option,
        options["include_domain"],
        allow_shell,
        None if options["yolo"] else confirm,
    )
    today = datetime.date.today() if root else domain.default_today
    max_calls = options["max_calls"]
    if max_calls is None:
        max_calls = config_data.get("max_calls")
    if max_calls is None:
        max_calls = 40 if root else 14
    run_config = RunConfig(
        condition="harness",
        max_calls=max_calls,
        today=today,
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
        tools=tools,
        policy=policy,
        world=world,
        memory=memory,
        workdir=workdir,
        artifact_dir=paths.artifacts,
        prompt_profile=profile,
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
    if root:
        mode = "read/write" + (" + shell" if allow_shell else "")
        toolset = (
            f"files + {domain.name}"
            if options["include_domain"]
            else "files only (domain tools dropped)"
        )
        print(
            f"  real files: {mode}; lexical root {root}"
            + (
                "   [--yolo: confirmations off]"
                if options["yolo"]
                else ""
            )
        )
        print(f"  toolset: {toolset}")
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
                "root": root,
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
