"""Standalone disposable S6C paired-condition runner.

The S6C release deliberately disables retained execution.  This command exists
to validate the real native transport, compiler, ledger, evidence path, and
resume behavior on development/validation/adversarial/sentinel inputs before
D0 and S8 freeze later-stage operational policy.
"""

import argparse
import copy
import datetime
import hashlib
import json
from pathlib import Path
import tempfile

from bench import s6_preflight
from domains.office_demo.contracts import build_registry
from domains.office_demo.generated_grader import (
    GRADER_VERSION,
    build_grader,
    task_id_for,
)
from domains.office_demo.generators import validate_office_instance
from domains.office_demo.world import World
from harness.evidence import (
    ACTIONS_SCHEMA,
    GRADE_SCHEMA,
    RESULT_SCHEMA,
    STATE_SCHEMA,
    AttemptKey,
    EvidenceStore,
    canonical_json_bytes,
)
from harness.experiment import (
    AttemptMemory,
    ExecutionContext,
    OllamaTransport,
    base_seed,
    condition_registry,
    protocol_sha256,
    run_raw_json_attempt,
    run_attempt,
    transcript_markdown,
)
from harness.grading import GradingEvidence
from harness.instances import load_canonical_json, validate_manifest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_PROTOCOL = HERE / "s6_protocol.json"
DEFAULT_MANIFESTS = HERE / "manifests" / "office-v1"
DEFAULT_RUNS = ROOT / "results-dev-s6c"


def _sha256(value, allow_float=False):
    return hashlib.sha256(
        canonical_json_bytes(value, allow_float=allow_float)
    ).hexdigest()


def _identity_sampling(protocol, seed):
    sampling = {}
    for key, value in protocol["sampling"].items():
        if isinstance(value, float):
            sampling[key] = repr(value)
        else:
            sampling[key] = value
    sampling["base_seed"] = seed
    sampling["seed_policy"] = protocol["base_seed"]["request_policy"]
    return sampling


def _prompt_sha256(condition, content):
    episodes = content["ordered_subepisodes"] or [
        {"id": "main", "prompt": content["prompt"]}
    ]
    return _sha256(
        {
            "schema_version": "brick.s6.prompt-identity/1",
            "condition": condition.name,
            "condition_version": condition.version,
            "today": content["today"],
            "episodes": [
                {"id": item["id"], "prompt": item["prompt"]}
                for item in episodes
            ],
            "role": "You are a careful office assistant.",
        }
    )


def _attempt_key(
    instance,
    condition,
    environment,
    protocol,
    repeat,
):
    content = instance["content"]
    seed = base_seed(environment["protocol_sha256"], content["id"])
    return AttemptKey(
        domain_name=content["domain"],
        domain_version=content["domain_version"],
        domain_content_sha256=environment["domain_sha256"],
        task_family=content["family"],
        task_version=content["family_version"],
        generator_version=content["generator_version"],
        grader_version=GRADER_VERSION,
        model_tag=protocol["primary_model"],
        model_digest=environment["ollama"]["model_digest"],
        condition_name=condition.name,
        condition_version=condition.version,
        mechanism_sha256=condition.mechanism_sha256,
        instance_id=content["id"],
        instance_content_sha256=instance["content_sha256"],
        ordered_subepisodes=[
            item["id"] for item in content["ordered_subepisodes"]
        ],
        repeat=repeat,
        sampling=_identity_sampling(protocol, seed),
        opportunity_budget={
            "model_calls": protocol["opportunity_budget"]["model_calls"],
            "generated_tokens": protocol["opportunity_budget"]["generated_tokens"],
            "generated_tokens_per_request": protocol["opportunity_budget"]["generated_tokens_per_request"],
            # Attempt identity records the policy actually enforced by
            # OpportunityLedger, not whether this particular task happens to
            # contain more than one subepisode.  Atomic attempts trivially use
            # the same single ledger and therefore still record 1 here.
            "shared_across_subepisodes": int(
                protocol["opportunity_budget"]["shared_across_subepisodes"]
            ),
        },
        prompt_sha256=_prompt_sha256(condition, content),
        tool_schema_sha256=environment["tool_schema_sha256"],
    )


def _world_from_initial(workdir, initial):
    world = World(str(workdir), persistent=False)
    world.emails = copy.deepcopy(initial["emails"])
    world.events = copy.deepcopy(initial["events"])
    world.sent_emails = copy.deepcopy(initial["sent_emails"])
    world.messages = copy.deepcopy(initial["messages"])
    world.reminders = copy.deepcopy(initial["reminders"])
    world.actions = []
    return world


def _business_state(world):
    return {
        "emails": copy.deepcopy(world.emails),
        "events": copy.deepcopy(world.events),
        "sent_emails": copy.deepcopy(world.sent_emails),
        "messages": copy.deepcopy(world.messages),
        "reminders": copy.deepcopy(world.reminders),
    }


def _episodes(content):
    if content["ordered_subepisodes"]:
        return [
            {"id": item["id"], "prompt": item["prompt"]}
            for item in content["ordered_subepisodes"]
        ]
    return [{"id": "main", "prompt": content["prompt"]}]


def _grade_document(outcome):
    if outcome is None:
        return {
            "schema_version": GRADE_SCHEMA,
            "grader_status": "not_run",
            "candidate_decision": None,
            "diagnostics": {"checks": [], "error": None},
        }
    return {
        "schema_version": GRADE_SCHEMA,
        "grader_status": outcome.grader_status,
        "candidate_decision": outcome.candidate_decision,
        "diagnostics": {
            "checks": [
                {"id": key, "description": description, "passed": passed}
                for key, description, passed in outcome.checks
            ],
            "error": outcome.error,
            "diagnostic_fraction": outcome.diagnostic_fraction,
        },
    }


def _producer(instance, condition, protocol, transport):
    content = instance["content"]

    def produce(writer):
        with tempfile.TemporaryDirectory(prefix="brick-s6-") as temporary:
            workdir = Path(temporary)
            world = _world_from_initial(workdir, content["initial_state"])
            memory = AttemptMemory(
                content["initial_state"]["memory"],
                bridge_enabled=not condition.has(
                    "attempt_scoped_memory_bridge_disabled"
                ),
            )
            registry = build_registry(
                alias_recovery=condition.has("known_alias_recovery")
            )
            context = ExecutionContext(world, memory, world.files_dir)
            seed = base_seed(protocol_sha256(protocol), content["id"])
            run_loop = (
                run_raw_json_attempt
                if condition.runner == "raw_json_loop"
                else run_attempt
            )
            runtime = run_loop(
                protocol=protocol,
                condition=condition,
                model=protocol["primary_model"],
                registry=registry,
                transport=transport,
                context=context,
                episodes=_episodes(content),
                today=content["today"],
                seed=seed,
            )
            final_state = _business_state(world)
            artifact_paths = [
                path for path in sorted(Path(world.files_dir).iterdir()) if path.is_file()
            ]
            grader_outcome = None
            if runtime["failure_origin"] in {"none", "model"}:
                evidence = GradingEvidence.from_values(
                    domain=content["domain"],
                    domain_version=content["domain_version"],
                    task_id=task_id_for(instance),
                    state=final_state,
                    actions=context.actions,
                    memory=memory.all(),
                    artifacts=[(path.name, path.read_bytes()) for path in artifact_paths],
                )
                grader_outcome = build_grader(instance).grade_evidence(evidence)
                if grader_outcome.grader_status != "graded":
                    runtime["execution_status"] = "runner_error"
                    runtime["failure_origin"] = "runner"
                    runtime["failure"] = {
                        "type": "grader_error",
                        "message": grader_outcome.error,
                    }
                elif runtime["failure_origin"] == "model":
                    # Whole-task completion is part of strict success.  A model
                    # that exhausted its opportunity budget cannot pass merely
                    # because its partial state happened to satisfy effects.
                    grader_outcome = type(grader_outcome)(
                        grader_outcome.grader_id,
                        grader_outcome.grader_version,
                        grader_outcome.grader_status,
                        False,
                        grader_outcome.checks,
                        grader_outcome.error,
                    )
            initial_payload = {
                "business": {
                    key: copy.deepcopy(content["initial_state"][key])
                    for key in ("emails", "events", "sent_emails", "messages", "reminders")
                },
                "memory": copy.deepcopy(content["initial_state"]["memory"]),
                "artifacts": copy.deepcopy(content["initial_state"]["artifacts"]),
            }
            final_payload = {
                "business": final_state,
                "memory": memory.all(),
                "artifacts": [path.name for path in artifact_paths],
                "subepisodes": runtime["subepisodes"],
            }
            writer.write_json(
                "initial-state.json",
                {
                    "schema_version": STATE_SCHEMA,
                    "state_kind": "initial",
                    "payload": initial_payload,
                },
            )
            writer.write_json(
                "final-state.json",
                {
                    "schema_version": STATE_SCHEMA,
                    "state_kind": "final",
                    "payload": final_payload,
                },
            )
            writer.write_json(
                "actions.json",
                {"schema_version": ACTIONS_SCHEMA, "actions": context.actions},
            )
            result = {
                "schema_version": RESULT_SCHEMA,
                "execution_status": runtime["execution_status"],
                "tool_status": (
                    "had_errors" if any(not item["ok"] for item in context.actions) else "clean"
                ),
                "failure_origin": runtime["failure_origin"],
                "failure": runtime["failure"],
                "metrics": runtime["metrics"],
                "diagnostics": {
                    "condition": condition.name,
                    "ledger": runtime["ledger"],
                    "requests": runtime["requests"],
                    "subepisodes": runtime["subepisodes"],
                },
            }
            writer.write_json("result.json", result)
            writer.write_json("grade.json", _grade_document(grader_outcome))
            memory_delta = b"".join(
                canonical_json_bytes(
                    {"index": index, "fact": fact}, newline=True
                )
                for index, fact in enumerate(memory.delta(), start=1)
            )
            writer.write_bytes("memory-delta.jsonl", memory_delta)
            writer.write_bytes(
                "transcript.md", transcript_markdown(runtime["transcript"])
            )
            for path in artifact_paths:
                writer.write_bytes("artifacts/" + path.name, path.read_bytes())

    return produce


def _waves(instances):
    families = {}
    for instance in instances:
        families.setdefault(instance["content"]["family"], []).append(instance)
    for values in families.values():
        values.sort(key=lambda item: item["content"]["id"])
    counts = {len(values) for values in families.values()}
    if len(counts) != 1:
        raise ValueError("paired scheduler requires equal family allocation")
    ordered_families = sorted(families)
    result = []
    for wave in range(next(iter(counts))):
        for family_index, family in enumerate(ordered_families):
            instance = families[family][wave]
            order = (
                ("native_tools", "harness_full")
                if (wave + family_index) % 2 == 0
                else ("harness_full", "native_tools")
            )
            result.append((wave, family, instance, order))
    return result


def _condition_order(primary_order, selected_conditions):
    """Keep AB/BA balance for primaries and explicit order for descriptives."""

    primary = [name for name in primary_order if name in selected_conditions]
    descriptive = [
        name
        for name in selected_conditions
        if name not in {"native_tools", "harness_full"}
    ]
    return tuple(primary + descriptive)


def run(args):
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    if args.split == "retained" or protocol.get("retained_execution_enabled") is not False:
        raise RuntimeError(
            "S6C mechanically forbids retained execution; retained unlock belongs to S8/S9"
        )
    preflight = s6_preflight.collect(
        args.protocol, require_clean=not args.allow_dirty
    )
    environment = preflight["environment"]
    conditions = condition_registry(
        protocol, environment["implementation_sha256"]
    )
    manifest = load_canonical_json(args.manifests / (args.split + ".json"))
    validate_manifest(manifest)
    instances = manifest["instances"]
    if args.instance_id:
        instances = [
            item for item in instances if item["content"]["id"] == args.instance_id
        ]
        if len(instances) != 1:
            raise ValueError("instance id is absent or ambiguous")
    schedule = _waves(instances)
    if args.max_cases is not None:
        if type(args.max_cases) is not int or args.max_cases < 1:
            raise ValueError("max-cases must be a positive integer")
        schedule = schedule[: args.max_cases]
    selected_conditions = tuple(args.condition or ("native_tools", "harness_full"))
    if len(set(selected_conditions)) != len(selected_conditions):
        raise ValueError("condition selection contains duplicates")
    if any(name not in conditions for name in selected_conditions):
        raise ValueError("unknown condition selection")
    run_id = args.run_id or (
        "s6c-%s-%s" % (
            args.split,
            datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        )
    )
    metadata = {
        "schema_version": "brick.s6.run-metadata/1",
        "run_kind": "disposable_s6c_validation",
        "split": args.split,
        "protocol": protocol,
        "environment": environment,
        "conditions": {
            name: {
                "version": spec.version,
                "mechanisms": list(spec.mechanisms),
                "mechanism_sha256": spec.mechanism_sha256,
            }
            for name, spec in conditions.items()
        },
        "schedule": [
            {
                "wave": wave,
                "family": family,
                "instance_id": instance["content"]["id"],
                "condition_order": list(
                    _condition_order(order, selected_conditions)
                ),
            }
            for wave, family, instance, order in schedule
        ],
        "retained": False,
    }
    store = EvidenceStore.create_run(args.runs_root, run_id, metadata)
    transport = OllamaTransport(
        protocol["transport"]["endpoint"],
        protocol["transport"]["request_timeout_seconds"],
    )
    cells = []
    for wave, family, instance, order in schedule:
        validate_office_instance(instance)
        for name in _condition_order(order, selected_conditions):
            condition = conditions[name]
            final = None
            for repeat in range(protocol["instrument_retry_limit"] + 1):
                key = _attempt_key(
                    instance, condition, environment, protocol, repeat
                )
                resolution = store.execute_or_resume(
                    key,
                    _producer(instance, condition, protocol, transport),
                )
                if resolution.state != "committed":
                    raise RuntimeError(
                        "attempt publication did not commit: " + resolution.state
                    )
                final = resolution.record
                if final["failure_origin"] not in {"runner", "environment"}:
                    break
            cells.append(
                {
                    "wave": wave,
                    "family": family,
                    "instance_id": instance["content"]["id"],
                    "condition": name,
                    "logical_hash": final["logical_hash"],
                    "execution_status": final["execution_status"],
                    "failure_origin": final["failure_origin"],
                    "strict_success": final["strict_success"],
                }
            )
            print(
                json.dumps(
                    {"event": "cell_complete", **cells[-1]},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                flush=True,
            )
    expected_cells = len(schedule) * len(selected_conditions)
    if len(cells) != expected_cells:
        raise RuntimeError(
            "scheduler emitted %d cells; expected %d"
            % (len(cells), expected_cells)
        )
    store.read_committed()
    summary = {
        "schema_version": "brick.s6.run-summary/1",
        "run_id": run_id,
        "cells": cells,
        "committed_attempts": len(store.read_committed()["records"]),
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True), flush=True)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--manifests", type=Path, default=DEFAULT_MANIFESTS)
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS)
    parser.add_argument(
        "--split",
        choices=("development", "validation", "sentinel", "adversarial", "retained"),
        default="development",
    )
    parser.add_argument("--instance-id")
    parser.add_argument("--condition", action="append")
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--run-id")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="disposable engineering runs only; gate evidence requires a clean tree",
    )
    args = parser.parse_args(argv)
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
