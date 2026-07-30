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


ALLOWED_CONFIG_KEYS = frozenset(
    {
        "domain",
        "max_calls",
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


def main(agent_dir=None, argv=None):
    if agent_dir is None:
        raise ValueError("agent_dir is required; invoke an agents/<size> shim")
    options, task = parse_flags(
        list(sys.argv[1:] if argv is None else argv)
    )
    agent_dir = os.path.abspath(agent_dir)
    with open(
        os.path.join(agent_dir, "config.json"), encoding="utf-8-sig"
    ) as handle:
        config_data = json.load(handle)
    validate_config(config_data)
    assert (
        "127.0.0.1" in OLLAMA_URL or "localhost" in OLLAMA_URL
    ), "refusing non-local endpoint"

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
    max_calls = options["max_calls"]
    if max_calls is None:
        max_calls = config_data.get("max_calls")
    if max_calls is None:
        max_calls = 14
    run_config = RunConfig(
        condition="harness",
        max_calls=max_calls,
        today=domain.default_today,
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
        tools=domain.registry,
        policy=domain.default_policy,
        world=world,
        memory=memory,
        workdir=workdir,
        artifact_dir=paths.artifacts,
        prompt_profile=domain.prompt_profile,
        prompt_rules=domain.prompt_rules,
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
