"""Benchmark runner: domain x models x conditions x tasks.

Each (domain, model, condition) run receives fresh shared memory, while every
task receives a fresh domain world and explicit attempt context.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness.agent import Episode, run  # noqa: E402
from harness.domain import load_domain  # noqa: E402
from harness.llm import LLM  # noqa: E402
from harness.memory import MemoryStore  # noqa: E402
from harness.runtime import AttemptContext, RunConfig  # noqa: E402


DEFAULT_MAX_CALLS = 14
_WINDOWS_DEVICE_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
)


def slug(value):
    """Return a deterministic, non-traversing output-path component."""
    if not isinstance(value, str) or not value:
        raise ValueError("path component must be a nonempty string")
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    if not cleaned:
        raise ValueError(f"path component {value!r} has no safe characters")
    if cleaned != value:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
        cleaned = f"{cleaned}-{digest}"
    if cleaned.split(".", 1)[0].casefold() in _WINDOWS_DEVICE_NAMES:
        raise ValueError(
            f"path component {value!r} is a reserved Windows device name"
        )
    return cleaned


def _reject_duplicates(parser, values, label):
    if len(set(values)) != len(values):
        parser.error(f"duplicate {label} values are not allowed")


def save_transcript(
    path, episode, task, model, condition, score, checks, domain
):
    lines = [
        f"# {task.id}  |  {domain.name}@{domain.version}  |  "
        f"{model}  |  {condition}",
        f"**Score: {score:.2f}**  (finished: {episode.finished})",
        "",
        "| check | passed |",
        "|---|---|",
    ]
    for description, ok in checks:
        lines.append(
            f"| {description} | {'PASS' if ok else 'FAIL'} |"
        )
    lines.append("")
    for item in episode.transcript:
        lines.append(f"### {item['kind']}")
        lines.append("```")
        lines.append(str(item["content"]))
        lines.append("```")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", default="office_demo")
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument(
        "--conditions", nargs="+", default=["raw", "harness"]
    )
    parser.add_argument("--tasks", nargs="+", default=None)
    parser.add_argument("--outdir", default="results")
    parser.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    args = parser.parse_args(argv)

    domain = load_domain(args.domain)
    _reject_duplicates(parser, args.models, "model")
    _reject_duplicates(parser, args.conditions, "condition")
    if args.tasks:
        _reject_duplicates(parser, args.tasks, "task")
    try:
        model_slugs = {model: slug(model) for model in args.models}
        if len(
            {component.casefold() for component in model_slugs.values()}
        ) != len(model_slugs):
            raise ValueError(
                "model names collide after cross-platform path normalization"
            )
        version_slug = slug(domain.version)
        configs = {
            condition: RunConfig(
                condition=condition,
                max_calls=args.max_calls,
                today=domain.default_today,
            )
            for condition in args.conditions
        }
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))
    tasks = (
        domain.tasks
        if not args.tasks
        else tuple(task for task in domain.tasks if task.id in args.tasks)
    )
    unknown_tasks = set(args.tasks or ()) - {task.id for task in tasks}
    if unknown_tasks:
        parser.error(
            "unknown tasks for domain "
            f"{domain.name!r}: {', '.join(sorted(unknown_tasks))}"
        )
    os.makedirs(args.outdir, exist_ok=True)
    results_path = os.path.join(args.outdir, "results.json")
    results = []
    if os.path.exists(results_path):
        with open(results_path, encoding="utf-8") as handle:
            results = json.load(handle)

    for model in args.models:
        for condition in args.conditions:
            run_dir = os.path.join(
                args.outdir,
                domain.name,
                version_slug,
                model_slugs[model],
                condition,
            )
            os.makedirs(run_dir, exist_ok=True)
            memory_path = os.path.join(run_dir, "memory.jsonl")
            if os.path.exists(memory_path):
                os.remove(memory_path)
            for task in tasks:
                if any(
                    result.get("domain", "office_demo") == domain.name
                    and result.get("domain_version") == domain.version
                    and result["model"] == model
                    and result["condition"] == condition
                    and result["task"] == task.id
                    for result in results
                ):
                    print(
                        f"[skip] {domain.name}@{domain.version} {model} "
                        f"{condition} {task.id} already done",
                        flush=True,
                    )
                    continue
                workdir = Path(run_dir, task.id)
                workdir.mkdir(parents=True, exist_ok=True)
                world = domain.make_world(workdir, persistent=False)
                memory = MemoryStore(memory_path)
                config = configs[condition]
                attempt = AttemptContext(
                    attempt_id=(
                        f"{domain.name}:{domain.version}:{model}:"
                        f"{condition}:{task.id}"
                    ),
                    config=config,
                    domain=domain,
                    tools=domain.registry_for(task),
                    policy=domain.default_policy,
                    world=world,
                    memory=memory,
                    workdir=workdir,
                    artifact_dir=workdir / "files",
                )
                llm = LLM(model)
                initial_calls = llm.calls
                started = time.time()
                error = None
                try:
                    episode = run(llm, task.prompt, attempt)
                except Exception as exc:
                    episode = Episode()
                    error = f"{type(exc).__name__}: {exc}"
                    episode.note("runner_error", error)
                    attempt.snapshot()
                wall = time.time() - started
                try:
                    score, checks = task.grade(attempt)
                except Exception as exc:
                    score, checks = 0.0, [
                        (f"grader crashed: {exc}", False)
                    ]
                calls = llm.calls - initial_calls
                record = {
                    "domain": domain.name,
                    "domain_version": domain.version,
                    "model": model,
                    "condition": condition,
                    "task": task.id,
                    "caps": list(task.capabilities),
                    "tools": list(task.tool_names),
                    "score": round(score, 4),
                    "checks": [
                        [description, bool(ok)]
                        for description, ok in checks
                    ],
                    "finished": episode.finished,
                    "llm_calls": calls,
                    "parse_failures": episode.parse_failures,
                    "invalid_calls": episode.invalid_calls,
                    "tool_errors": episode.tool_errors,
                    "prompt_tokens": llm.prompt_tokens,
                    "output_tokens": llm.output_tokens,
                    "wall_seconds": round(wall, 1),
                    "error": error,
                    "max_calls": config.max_calls,
                }
                results.append(record)
                with open(results_path, "w", encoding="utf-8") as handle:
                    json.dump(results, handle, indent=1)
                save_transcript(
                    workdir / "transcript.md",
                    episode,
                    task,
                    model,
                    condition,
                    score,
                    checks,
                    domain,
                )
                print(
                    f"[{domain.name}@{domain.version} | {model} | "
                    f"{condition}] {task.id}: score={score:.2f} "
                    f"calls={calls} wall={wall:.0f}s"
                    + (f" ERROR={error}" if error else ""),
                    flush=True,
                )
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
