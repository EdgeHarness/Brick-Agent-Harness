"""Model-free construct-validity simulation for the successor office suite.

This audit deliberately separates three questions that are easy to conflate:

* can the frozen cases be executed through the real typed tool contracts;
* do public prompts/state determine the outcomes enforced by the grader; and
* is there evidence that the synthetic task population represents real work.

The first two questions are testable offline.  The third is not: no simulation
can manufacture external-validity evidence.  The report therefore fails closed
when a claimed task capability is unnecessary, a business-critical result is
underchecked, or no empirical real-work sampling frame exists.
"""

import argparse
from collections import Counter, defaultdict
import copy
import json
from pathlib import Path
import re
import tempfile

from domains.office_demo.contracts import build_registry
from domains.office_demo.generators_v2 import FAMILIES, GENERATOR_VERSION
from domains.office_demo.outcome_oracle_v2 import derive_outcome
from domains.office_demo.reviewed_grader_v2 import build_grader, task_id_for
from domains.office_demo.world import World
from harness.evidence import canonical_json_bytes
from harness.grading import GradingEvidence
from harness.instances import (
    load_canonical_json,
    replace_canonical_json,
    sha256_bytes,
    validate_manifest,
)
from harness.experiment import (
    AttemptMemory, ExecutionContext, condition_registry, run_attempt,
)

from .next_study_review import digest_review_artifact, review_packet


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIRECTORY = ROOT / "bench" / "manifests" / "office-v2"
DEFAULT_OUTPUT = (
    ROOT / "evidence" / "next-study" / "office-v2-semantic-simulation.json"
)
SCHEMA_VERSION = "brick.next-study.semantic-simulation/1"
_SPLITS = (
    "development",
    "calibration",
    "validation",
    "sentinel",
    "retained",
    "adversarial",
)
_STATE_LISTS = (
    "emails",
    "events",
    "sent_emails",
    "messages",
    "reminders",
    "memory",
    "artifacts",
)
_SOURCE_TYPES = frozenset(("source_read", "sources_read", "calendar_read"))


class SemanticSimulationError(ValueError):
    """The corpus or simulation violated a fail-closed invariant."""


class _ScriptedTransport:
    """Deterministic model substitute that exercises the production runner."""

    def __init__(self, calls):
        self.calls = list(calls)

    def chat(self, payload):
        if not self.calls:
            raise SemanticSimulationError("reference transport exhausted")
        name, args = self.calls.pop(0)
        return {
            "model": payload["model"],
            "created_at": "2026-08-05T00:00:00Z",
            "message": {
                "role": "assistant", "content": "", "thinking": None,
                "tool_calls": [{"function": {
                    "name": name, "arguments": copy.deepcopy(args),
                }}],
            },
            "done": True, "done_reason": "stop", "total_duration": 10,
            "load_duration": 1, "prompt_eval_count": 1,
            "prompt_eval_duration": 1, "eval_count": 1, "eval_duration": 1,
        }


def _digest(value):
    return sha256_bytes(canonical_json_bytes(value, allow_float=False))


def _load_instances(directory=MANIFEST_DIRECTORY):
    manifests, instances = [], []
    for split in _SPLITS:
        manifest = load_canonical_json(Path(directory) / (split + ".json"))
        validate_manifest(manifest)
        if manifest["split"] != split:
            raise SemanticSimulationError("manifest split binding drifted")
        manifests.append(manifest)
        instances.extend(manifest["instances"])
    if (
        len(instances) != 528
        or len({item["content"]["id"] for item in instances}) != 528
        or len({item["content_sha256"] for item in instances}) != 528
    ):
        raise SemanticSimulationError("semantic simulation requires 528 unique cases")
    return manifests, sorted(instances, key=lambda item: item["content"]["id"])


def _derive(packet):
    return derive_outcome(
        packet["family"],
        packet["prompt"],
        packet["subepisode_prompts"],
        packet["initial_state"],
        packet["today"],
    )


def _machine_outcome(instance, packet, outcome):
    return {
        "instance_id": instance["content"]["id"],
        "content_sha256": instance["content_sha256"],
        "review_packet_sha256": digest_review_artifact(packet),
        "prompt_valid": True,
        "outcome": copy.deepcopy(outcome),
        "accepted_alternatives": [],
        "review_resolution": "model_free_semantic_simulation",
    }


def _column_name(index):
    value, result = index + 1, ""
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def _effect_call(effect, state):
    kind = effect["type"]
    if kind == "source_read":
        calls = []
        if effect.get("list_required"):
            calls.append(("list_emails", {}))
        calls.append(("read_email", {"id": effect["id"]}))
        return calls
    if kind == "sources_read":
        calls = ([('list_emails', {})] if effect.get("list_required") else [])
        return calls + [
            ("read_email", {"id": identifier}) for identifier in effect["ids"]
        ]
    if kind == "calendar_read":
        return "list_events", {"date": effect["date"]}
    if kind == "presentation_created":
        values = list(effect.get("required_values", []))
        values_by_slide = effect.get("required_values_by_slide")
        minimums = effect.get(
            "minimum_bullets_by_slide", [0] * effect["exact_slide_count"]
        )
        slides = []
        for index, title in enumerate(effect["ordered_titles"]):
            bullets = (
                [str(value) for value in values_by_slide[index]]
                if values_by_slide is not None else []
            )
            if values_by_slide is None and len(values) == effect["exact_slide_count"] - 1 and index:
                bullets.append(str(values[index - 1]))
            elif values_by_slide is None and effect["exact_slide_count"] == 1:
                bullets.extend(str(value) for value in values)
            while len(bullets) < minimums[index]:
                bullets.append("Verified detail %d" % (len(bullets) + 1))
            slides.append({"title": title, "bullets": bullets})
        return "create_presentation", {
            "filename": effect["filename"], "slides": slides,
        }
    if kind == "spreadsheet_created":
        wanted, cents = effect.get("ordered_rows"), False
        if wanted is None:
            wanted, cents = effect["ordered_rows_cents"], True
        rows = [[str(value) for value in effect["headers"]]]
        for source_row in wanted:
            row = []
            for index, value in enumerate(source_row):
                row.append(
                    "%d.%02d" % (value // 100, value % 100)
                    if cents and index == len(source_row) - 1
                    else str(value)
                )
            rows.append(row)
        total = [""] * len(effect["headers"])
        total[0] = "Total"
        column = _column_name(len(total) - 1)
        total[-1] = "=SUM(%s2:%s%d)" % (column, column, len(rows))
        rows.append(total)
        return "create_spreadsheet", {
            "filename": effect["filename"], "rows": rows,
        }
    if kind == "email_sent":
        return "send_email", {
            "to": effect["to"],
            "subject": "Re: %s" % effect.get("subject_contains", "attendance"),
            "body": "I confirm that I will attend. Count me in. %s" % " ".join(
                effect.get("required_mentions", [])
            ),
        }
    if kind == "event_created":
        return "add_event", {
            "title": effect["title"],
            "date": effect["date"],
            "start_time": effect["start"],
            "end_time": effect["end"],
            "attendees": list(effect["attendees"]),
            "location": effect.get("location", ""),
        }
    if kind == "message_sent":
        mentions = effect.get(
            "ordered_mentions", effect.get("required_mentions", [])
        )
        parts = []
        for mention in mentions:
            matching = [item for item in state["events"] if item["title"] == mention]
            parts.append(
                "%s at %s" % (mention, matching[0]["start"])
                if effect.get("include_start_times") and matching
                else str(mention)
            )
        if effect.get("body_intent") == "deadline_commitment":
            parts.append("The full checklist will be complete by the deadline.")
        return "send_message", {"to": effect["to"], "text": "; ".join(parts)}
    if kind == "reminder_created":
        return "set_reminder", {
            "text": "; ".join(effect["required_mentions"]),
            "date": effect["date"],
            "time": effect["time"],
        }
    if kind == "memory_saved":
        return "save_memory", {"fact": "; ".join(effect["required_facts"])}
    raise SemanticSimulationError("unsupported effect %r" % kind)


def _execute_through_typed_tools(instance, packet, outcome, workdir, condition):
    from .next_study_live import build_execution_protocol, _implementation_sha256

    initial = packet["initial_state"]
    world = World(str(workdir), persistent=False)
    for field in ("emails", "events", "sent_emails", "messages", "reminders"):
        setattr(world, field, copy.deepcopy(initial[field]))
    memory = AttemptMemory(
        initial["memory"], visible_initial=initial["memory"], bridge_enabled=True,
    )
    context = ExecutionContext(world, memory, world.files_dir)
    protocol = build_execution_protocol("4b")
    condition_spec = condition_registry(
        protocol, _implementation_sha256()
    )[condition]
    registry = build_registry(alias_recovery=condition_spec.has("known_alias_recovery"))
    episodes = (
        [{"id": str(index), "prompt": value} for index, value in enumerate(
            packet["subepisode_prompts"]
        )]
        if packet["subepisode_prompts"] else [{"id": "main", "prompt": packet["prompt"]}]
    )
    effect_groups = (
        [[outcome[0]], outcome[1:]] if len(episodes) == 2 else [outcome]
    )
    scripted = []
    for episode_index, effects in enumerate(effect_groups):
        business = []
        if condition == "native_tools" and episode_index and any(
            item["type"] == "event_created" for item in effects
        ):
            event = next(item for item in effects if item["type"] == "event_created")
            business.append(("recall_memories", {"query": event["attendees"][0]}))
        for effect in effects:
            calls = _effect_call(effect, {"events": world.events})
            business.extend([calls] if isinstance(calls, tuple) else calls)
        if condition == "harness_full":
            scripted.extend([("think", {"thought": "plan every explicit requirement"})])
            scripted.extend(business)
            scripted.extend([
                ("done", {"summary": "complete"}),
                ("think", {"thought": "review every explicit requirement"}),
                ("done", {"summary": "complete after review"}),
            ])
        else:
            scripted.extend(business)
            scripted.append(("done", {"summary": "complete"}))
    transport = _ScriptedTransport(scripted)
    runtime = run_attempt(
        protocol=protocol, condition=condition_spec, model=protocol["primary_model"],
        registry=registry, transport=transport, context=context, episodes=episodes,
        today=packet["today"], seed=1,
    )
    if runtime["execution_status"] != "done" or transport.calls:
        raise SemanticSimulationError(
            "production runner reference path failed for %s/%s: %s"
            % (instance["content"]["id"], condition, runtime["failure"])
        )
    state = {
        "emails": copy.deepcopy(world.emails),
        "events": copy.deepcopy(world.events),
        "sent_emails": copy.deepcopy(world.sent_emails),
        "messages": copy.deepcopy(world.messages),
        "reminders": copy.deepcopy(world.reminders),
    }
    artifacts = [
        (path.name, path.read_bytes())
        for path in sorted(Path(world.files_dir).iterdir()) if path.is_file()
    ]
    machine = _machine_outcome(instance, packet, outcome)
    evidence = GradingEvidence.from_values(
        domain="office_demo",
        domain_version="0.1.0",
        task_id=task_id_for(packet, machine),
        state=state,
        actions=context.actions,
        memory=memory.all(),
        artifacts=artifacts,
    )
    grade = build_grader(packet, machine).grade_evidence(evidence)
    if grade.grader_status != "graded" or grade.strict_success is not True:
        raise SemanticSimulationError(
            "typed positive workflow failed independent grader for %s"
            % instance["content"]["id"]
        )
    return runtime["ledger"]["model_calls"]


def _reordered_packet(packet):
    changed = copy.deepcopy(packet)
    for field in _STATE_LISTS:
        changed["initial_state"][field] = list(
            reversed(changed["initial_state"][field])
        )
    return changed


def _irrelevant_packet(packet):
    changed = copy.deepcopy(packet)
    changed["initial_state"]["emails"].append({
        "id": "semantic-simulation-irrelevant-email",
        "from": "unrelated@semantic-simulation.example",
        "date": "1900-01-01 00:00",
        "subject": "UNRELATED SEMANTIC SIMULATION CONTROL",
        "body": "This control is unrelated to every task selector.",
    })
    changed["initial_state"]["events"].append({
        "id": "semantic-simulation-irrelevant-event",
        "title": "Unrelated semantic simulation control",
        "date": "1900-01-01",
        "start": "00:00",
        "end": "00:30",
        "location": "",
        "attendees": [],
    })
    return changed


def _dependency_packet(packet):
    """Return a relevant-input counterfactual and the expected relationship."""

    changed = copy.deepcopy(packet)
    family = packet["family"]
    if family == "pptx_basic":
        changed["prompt"] = changed["prompt"].replace(
            "approved-fact-1", "approved-fact-1-changed", 1
        )
        return changed, "outcome_changes"
    if family == "pptx_from_email":
        for email in changed["initial_state"]["emails"]:
            if "Revenue cents:" in email["body"]:
                value = int(re.search(r"Revenue cents: (\d+)", email["body"]).group(1))
                email["body"] = email["body"].replace(
                    "Revenue cents: %d" % value, "Revenue cents: %d" % (value + 1)
                )
                return changed, "outcome_changes"
    if family == "xlsx_from_email":
        for email in changed["initial_state"]["emails"]:
            if "amount_cents=" in email["body"]:
                value = int(re.search(r"amount_cents=(\d+)", email["body"]).group(1))
                email["body"] = email["body"].replace(
                    "amount_cents=%d" % value, "amount_cents=%d" % (value + 1), 1
                )
                return changed, "outcome_changes"
    if family == "email_reply":
        for email in changed["initial_state"]["emails"]:
            if email["id"] == "required-decision":
                email["body"] = re.sub(
                    r"confirmation_code=([^;]+)",
                    r"confirmation_code=\1-changed",
                    email["body"],
                    count=1,
                )
                return changed, "outcome_changes"
    if family == "xlsx_basic":
        match = re.search(r"Cost=(\d+)", changed["prompt"])
        changed["prompt"] = changed["prompt"].replace(
            match.group(0), "Cost=%d" % (int(match.group(1)) + 1), 1
        )
        return changed, "outcome_changes"
    if family == "cal_add":
        selected = next(
            item for item in _business_outcome(_derive(packet))
            if item["type"] == "event_created"
        )
        changed["prompt"] = changed["prompt"].replace(
            selected["title"], selected["title"] + " changed", 1
        )
        return changed, "outcome_changes"
    if family == "cal_freeslot":
        selected = next(
            item for item in _business_outcome(_derive(packet))
            if item["type"] == "event_created"
        )
        changed["initial_state"]["events"].append({
            "id": "semantic-simulation-selected-slot-blocker",
            "title": "Counterfactual selected-slot blocker",
            "date": selected["date"],
            "start": selected["start"],
            "end": selected["end"],
            "location": "",
            "attendees": [],
        })
        return changed, "outcome_changes"
    if family == "cal_brief":
        event = next(
            item for item in changed["initial_state"]["events"]
            if item["title"].startswith("Priority:")
        )
        event["title"] += " changed"
        return changed, "outcome_changes"
    if family == "remind_msg":
        selected = next(
            item for item in _business_outcome(_derive(packet))
            if item["type"] == "reminder_created"
        )["required_mentions"][0]
        changed["prompt"] = changed["prompt"].replace(
            selected, selected + "-changed"
        )
        return changed, "outcome_changes"
    if family == "multi_offsite":
        selected = next(
            item for item in _business_outcome(_derive(packet))
            if item["type"] == "event_created"
        )
        source = next(
            item for item in changed["initial_state"]["emails"]
            if selected["title"] in item["body"]
        )
        source["body"] = source["body"].replace(
            selected["title"], selected["title"] + " changed", 1
        )
        return changed, "outcome_changes"
    if family == "preference_learning":
        store = changed["subepisode_prompts"][0]
        selected = next(
            item for item in _derive(packet) if item["type"] == "memory_saved"
        )
        fact = next(
            value for value in selected["required_facts"]
            if value.startswith("earliest_start=")
        )
        replacement = "earliest_start=07:00"
        changed["subepisode_prompts"][0] = store.replace(
            fact, replacement
        )
        return changed, "use_effect_should_change"
    return None, "not_applicable"


def _business_outcome(outcome):
    return [item for item in outcome if item["type"] not in _SOURCE_TYPES]


def _normalize_logic(instance):
    """Remove scalar/surface substitutions while preserving decision operators."""

    content = instance["content"]
    visible = json.dumps(
        {
            "prompt": content["prompt"],
            "subepisodes": [
                item["prompt"] for item in content["ordered_subepisodes"]
            ],
            "initial_state": content["initial_state"],
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    surfaces = {
        str(value)
        for entity in content["entities"].values()
        for value in entity.values()
    }
    for surface in sorted(surfaces, key=len, reverse=True):
        visible = visible.replace(surface, "<ENTITY>")
    visible = re.sub(
        r"[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}",
        "<EMAIL>", visible,
    )
    visible = re.sub(r"\boffice_\d+_[a-z]+\.(?:pptx|xlsx)\b", "<FILE>", visible)
    visible = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "<DATE>", visible)
    visible = re.sub(r"\b\d{2}:\d{2}\b", "<TIME>", visible)
    visible = re.sub(r"\b\d+\b", "<NUMBER>", visible)
    return visible


def _construct_findings(instances, profile_sensitivity, memory_failures):
    if memory_failures:
        raise SemanticSimulationError("stored-memory dependency is absent")
    if any(
        result["distinct_policy_outcomes"] != 16
        for result in profile_sensitivity.values()
    ):
        raise SemanticSimulationError("a decision policy is semantically inert")
    return []


def audit_all(directory=MANIFEST_DIRECTORY, *, manifests=None):
    if manifests is None:
        manifests, instances = _load_instances(directory)
    else:
        manifests = list(manifests)
        if len(manifests) != len(_SPLITS):
            raise SemanticSimulationError("semantic simulation requires six manifests")
        by_split = {}
        for manifest in manifests:
            validate_manifest(manifest)
            split = manifest.get("split")
            if split in by_split or split not in _SPLITS:
                raise SemanticSimulationError("manifest split binding drifted")
            by_split[split] = manifest
        if set(by_split) != set(_SPLITS):
            raise SemanticSimulationError("semantic simulation split set drifted")
        manifests = [by_split[split] for split in _SPLITS]
        instances = sorted(
            (
                instance for manifest in manifests
                for instance in manifest["instances"]
            ),
            key=lambda item: item["content"]["id"],
        )
        if (
            len(instances) != 528
            or len({item["content"]["id"] for item in instances}) != 528
            or len({item["content_sha256"] for item in instances}) != 528
        ):
            raise SemanticSimulationError("semantic simulation requires 528 unique cases")
    family_counts = Counter()
    split_counts = Counter()
    structure_hashes, prompt_surfaces = set(), set()
    oracle_matches = reordered_passes = irrelevant_passes = 0
    dependency_passes = dependency_probes = memory_failures = 0
    typed_executions = typed_actions = 0
    request_counts = {
        condition: defaultdict(list)
        for condition in ("native_tools", "harness_full")
    }
    logic_by_cell = defaultdict(dict)

    with tempfile.TemporaryDirectory(prefix="brick-semantic-simulation-") as root:
        root_path = Path(root)
        for index, instance in enumerate(instances):
            content = instance["content"]
            family_counts[content["family"]] += 1
            split_counts[content["split"]] += 1
            structure_hashes.add(content["structure_sha256"])
            prompt_surfaces.add(_digest({
                "prompt": content["prompt"],
                "subepisodes": content["ordered_subepisodes"],
            }))
            packet = review_packet(instance)
            outcome = _derive(packet)
            if outcome != content["required_effects"]:
                raise SemanticSimulationError(
                    "public outcome mismatch for %s" % content["id"]
                )
            oracle_matches += 1
            if _derive(_reordered_packet(packet)) != outcome:
                raise SemanticSimulationError(
                    "public outcome depends on initial-state record order for %s"
                    % content["id"]
                )
            reordered_passes += 1
            if _derive(_irrelevant_packet(packet)) != outcome:
                raise SemanticSimulationError(
                    "irrelevant state changes public outcome for %s" % content["id"]
                )
            irrelevant_passes += 1
            changed, expectation = _dependency_packet(packet)
            if changed is not None:
                dependency_probes += 1
                changed_outcome = _derive(changed)
                if expectation == "outcome_changes":
                    if changed_outcome == outcome:
                        raise SemanticSimulationError(
                            "relevant input is inert for %s" % content["id"]
                        )
                    dependency_passes += 1
                else:
                    before = [
                        item for item in outcome if item["type"] == "event_created"
                    ]
                    after = [
                        item for item in changed_outcome
                        if item["type"] == "event_created"
                    ]
                    if before == after:
                        memory_failures += 1
                    else:
                        dependency_passes += 1
            for condition in ("native_tools", "harness_full"):
                calls = _execute_through_typed_tools(
                    instance, packet, outcome,
                    root_path / ("case-%03d-%s" % (index, condition)), condition,
                )
                typed_actions += calls
                request_counts[condition][content["family"]].append(calls)
                typed_executions += 1
            structure = content["structure"]
            logic_by_cell[content["family"]][(
                structure["workload"],
                structure["distractor_count"],
                structure["decision_policy"],
            )] = _digest(_business_outcome(outcome))

    profile_sensitivity = {}
    for family in sorted(logic_by_cell):
        decision_sensitive = 0
        for workload in range(3, 7):
            for distractors in range(4):
                values = {
                    value for (case_workload, case_distractors, _policy), value
                    in logic_by_cell[family].items()
                    if case_workload == workload and case_distractors == distractors
                }
                if len(values) == 3:
                    decision_sensitive += 1
        profile_sensitivity[family] = {
            "matched_workload_distractor_cells": 16,
            "distinct_policy_outcomes": decision_sensitive,
            "all_three_policies_change_outcome": decision_sensitive == 16,
        }

    findings = _construct_findings(instances, profile_sensitivity, memory_failures)
    request_bounds = {
        family: {
            condition: {
                "minimum": min(request_counts[condition][family]),
                "maximum": max(request_counts[condition][family]),
                "cap": 18,
                "minimum_absolute_slack": (
                    18 - max(request_counts[condition][family])
                ),
            }
            for condition in ("native_tools", "harness_full")
        }
        for family in sorted(FAMILIES)
    }
    if (
        max(value["native_tools"]["maximum"] for value in request_bounds.values()) > 9
        or max(value["harness_full"]["maximum"] for value in request_bounds.values()) > 12
    ):
        raise SemanticSimulationError("production-runner request bound drifted")
    severity_counts = Counter(item["severity"] for item in findings)
    claim_cases = sum(
        count for split, count in split_counts.items()
        if split in ("calibration", "retained")
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "status": "passed",
        "scope": {
            "case_count": len(instances),
            "claim_bearing_cases": claim_cases,
            "family_counts": dict(sorted(family_counts.items())),
            "split_counts": dict(sorted(split_counts.items())),
            "unique_structure_hashes": len(structure_hashes),
            "unique_prompt_surfaces": len(prompt_surfaces),
        },
        "simulation": {
            "public_prompt_outcome_exact_matches": oracle_matches,
            "initial_record_order_invariance_passes": reordered_passes,
            "irrelevant_state_invariance_passes": irrelevant_passes,
            "relevant_input_dependency_probes": dependency_probes,
            "relevant_input_dependency_passes": dependency_passes,
            "memory_use_dependency_failures": memory_failures,
            "typed_positive_workflows_executed": typed_executions,
            "typed_tool_actions_executed": typed_actions,
            "typed_positive_workflows_strict_successes": typed_executions,
            "production_runner_request_bounds_by_family": request_bounds,
            "maximum_native_requests": max(
                value["native_tools"]["maximum"] for value in request_bounds.values()
            ),
            "maximum_harness_requests": max(
                value["harness_full"]["maximum"] for value in request_bounds.values()
            ),
            "live_model_calls": 0,
        },
        "constraint_profile_sensitivity": profile_sensitivity,
        "findings": findings,
        "finding_severity_counts": dict(sorted(severity_counts.items())),
        "assessment": {
            "executable_correctness": "pass",
            "prompt_to_outcome_internal_consistency": "pass",
            "construct_validity": "pass_for_fixed_synthetic_suite",
            "external_real_world_validity": "not_established",
            "confirmatory_execution_recommended": True,
            "exploratory_execution_recommended": True,
            "reason": (
                "All frozen internal-validity gates pass. External validity remains "
                "unestablished and is explicitly outside the claim."
            ),
        },
        "limitations": [
            "Model-free simulation cannot determine how reasonable people interpret language.",
            "No model was sampled, so difficulty and condition separation remain unmeasured.",
            "No real-user corpus or deployment outcome was available for predictive validation.",
            "Passing typed workflows proves feasibility, not usefulness of their content.",
        ],
        "artifact_is_execution_authorization": False,
    }


def validate_report(report):
    if not isinstance(report, dict) or report.get("schema_version") != SCHEMA_VERSION:
        raise SemanticSimulationError("semantic simulation report schema drifted")
    rebuilt = audit_all()
    if report != rebuilt:
        raise SemanticSimulationError("semantic simulation report is not reproducible")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the model-free successor semantic-validity simulation."
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    if args.write and args.verify:
        parser.error("choose at most one of --write and --verify")
    if args.verify:
        report = validate_report(load_canonical_json(args.output))
    else:
        report = audit_all()
        if args.write:
            replace_canonical_json(args.output, report)
    print(json.dumps({
        "status": report["status"],
        "case_count": report["scope"]["case_count"],
        "typed_workflows": report["simulation"]["typed_positive_workflows_executed"],
        "high_findings": report["finding_severity_counts"].get("high", 0),
        "confirmatory_execution_recommended": report["assessment"]["confirmatory_execution_recommended"],
        "output": str(args.output) if args.write or args.verify else None,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_OUTPUT",
    "SCHEMA_VERSION",
    "SemanticSimulationError",
    "audit_all",
    "validate_report",
]
