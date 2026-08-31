"""Paired deterministic control-path evaluation: legacy vs receipt-v1.

This is engineering acceptance evidence, not a model-quality benchmark.  The
same scripted policy is run against both protocols.  It measures whether the
runtime falsely accepts incomplete work, preserves valid success, prevents an
unplanned extra effect, and refuses to call an unverified interactive request
complete.  It never imports or changes ``bench/``.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from harness.domain import load_domain
from harness.lifecycle import canonical_json_bytes, read_and_verify
from harness.memory import MemoryStore
from harness.runtime import AttemptContext, RunConfig
from harness.runtime_dispatch import run


EVALUATION_VERSION = "brick.runtime-protocol-acceptance/1"
EVALUATION_SCOPE = (
    "deterministic control-path acceptance; not model quality or hardware "
    "performance"
)
SOURCE_STATE = "working tree bound by content digests"
SOURCE_FILES = (
    "evals/runtime_protocol/run_eval.py",
    "domains/counter_demo/pack.py",
    "domains/counter_demo/tools.py",
    "domains/counter_demo/world.py",
    "harness/agent.py",
    "harness/completion.py",
    "harness/domain.py",
    "harness/grading.py",
    "harness/lifecycle.py",
    "harness/managed_agent.py",
    "harness/model_router.py",
    "harness/profiles.py",
    "harness/receipts.py",
    "harness/router_contract.py",
    "harness/runtime.py",
    "harness/runtime_dispatch.py",
    "harness/runtime_recipe.py",
    "harness/tool_pipeline.py",
    "harness/tools.py",
)

CASES = (
    {
        "id": "premature_done",
        "set": "development",
        "task_id": "counter_twice",
        "task": "Increase the counter by one twice.",
        "plan": [],
        "driver": [("done", {"summary": "claimed complete"})],
        "verifier": {"complete": True, "missing": ""},
        "max_calls": 3,
    },
    {
        "id": "valid_success",
        "set": "development",
        "task_id": "counter_twice",
        "task": "Increase the counter by one twice.",
        "plan": [
            ("increment_counter", "add one"),
            ("increment_counter", "add one"),
        ],
        "driver": [
            ("increment_counter", {"amount": 1}),
            ("increment_counter", {"amount": 1}),
            ("done", {"summary": "counter is two"}),
        ],
        "verifier": {"complete": True, "missing": ""},
        "max_calls": 5,
    },
    {
        "id": "malformed_verifier",
        "set": "acceptance",
        "task_id": "counter_twice",
        "task": "Increase the counter by one twice.",
        "plan": [],
        "driver": [("done", {"summary": "claimed complete"})],
        "verifier": "not valid json",
        "max_calls": 3,
    },
    {
        "id": "unplanned_extra_effect",
        "set": "acceptance",
        "task_id": "counter_twice",
        "task": "Increase the counter by one twice.",
        "plan": [
            ("increment_counter", "add one"),
            ("increment_counter", "add one"),
        ],
        "driver": [
            ("increment_counter", {"amount": 1}),
            ("increment_counter", {"amount": 1}),
            ("increment_counter", {"amount": 1}),
            ("done", {"summary": "counter updated"}),
        ],
        "replan": [],
        "verifier": {"complete": True, "missing": ""},
        "max_calls": 7,
    },
    {
        "id": "interactive_unknown",
        "set": "acceptance",
        "task_id": None,
        "task": "Read the counter and report it.",
        "plan": [("read_counter", "inspect")],
        "driver": [
            ("read_counter", {}),
            ("done", {"summary": "counter read"}),
        ],
        "verifier": {"complete": True, "missing": ""},
        "max_calls": 4,
    },
    {
        "id": "valid_at_budget_boundary",
        "set": "acceptance",
        "task_id": "counter_twice",
        "task": "Increase the counter by one twice.",
        "plan": [
            ("increment_counter", "add one"),
            ("increment_counter", "add one"),
        ],
        "driver": [
            ("increment_counter", {"amount": 1}),
            ("increment_counter", {"amount": 1}),
        ],
        "verifier": None,
        "max_calls": 3,
    },
)


class PolicyLLM:
    """One role-aware deterministic policy reused by both runtime variants."""

    def __init__(self, case):
        self.case = case
        self.model = "deterministic-policy"
        self.num_ctx = 8_192
        self.temperature = 0.0
        self.timeout = 1
        self.keep_alive = "0"
        self.retries = 0
        self.calls = 0
        self.prompt_tokens = 0
        self.output_tokens = 0
        self.wall = 0.0
        self._driver = list(case["driver"])

    @staticmethod
    def _steps(values):
        return {
            "steps": [
                {"tool": tool, "what": what} for tool, what in values
            ]
        }

    def chat(
        self,
        messages,
        force_json=False,
        num_predict=700,
        role=None,
        keep_alive=None,
    ):
        del force_json, num_predict, keep_alive
        self.calls += 1
        if role == "router":
            text = "\n".join(str(item.get("content", "")) for item in messages)
            values = (
                self.case.get("replan", [])
                if "A result now suggests" in text
                else self.case["plan"]
            )
            return json.dumps(self._steps(values), sort_keys=True)
        if role == "verifier":
            value = self.case.get("verifier")
            return value if isinstance(value, str) else json.dumps(value)
        if not self._driver:
            raise RuntimeError("deterministic policy has no driver action left")
        tool, arguments = self._driver.pop(0)
        return json.dumps(
            {"tool": tool, "args": arguments}, sort_keys=True
        )


def _sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git_head(root):
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def _run_case(root, case, protocol, temp_root):
    domain = load_domain("counter_demo")
    folder = Path(temp_root, case["id"], protocol)
    world = domain.make_world(folder)
    attempt = AttemptContext(
        attempt_id="eval:{}:{}".format(case["id"], protocol),
        config=RunConfig(
            condition="harness",
            max_calls=case["max_calls"],
            today=domain.default_today,
            verifier_rounds=1,
            runtime_protocol=protocol,
        ),
        domain=domain,
        tools=domain.registry,
        policy=domain.default_policy,
        world=world,
        memory=MemoryStore(str(folder / "memory.jsonl")),
        workdir=folder,
        artifact_dir=folder / "files",
        authoritative_task_id=case["task_id"],
    )
    llm = PolicyLLM(case)
    episode = run(llm, case["task"], attempt)
    strict_success = None
    if case["task_id"] is not None:
        task = next(item for item in domain.tasks if item.id == case["task_id"])
        strict_success = task.grader.grade_attempt(
            attempt, task.id
        ).strict_success
    lifecycle_valid = None
    if protocol == "receipt_v1":
        lifecycle_valid = bool(read_and_verify(episode.lifecycle_path))
    increments = sum(
        item["tool"] == "increment_counter" and item["ok"] is True
        for item in attempt.actions
    )
    return {
        "protocol": protocol,
        "finished": episode.finished,
        "terminal_status": episode.terminal_status,
        "completion_status": (
            episode.completion.get("status")
            if episode.completion is not None
            else None
        ),
        "strict_success": strict_success,
        "false_completion": bool(
            episode.finished and strict_success is False
        ),
        "unverified_completion": bool(
            episode.finished and strict_success is None
        ),
        "successful_increments": increments,
        "llm_calls": llm.calls,
        "lifecycle_valid": lifecycle_valid,
    }


def _validate_case_records(case_records):
    if not isinstance(case_records, list) or len(case_records) != len(CASES):
        raise ValueError("runtime-protocol case inventory is invalid")
    outcome_fields = {
        "protocol",
        "finished",
        "terminal_status",
        "completion_status",
        "strict_success",
        "false_completion",
        "unverified_completion",
        "successful_increments",
        "llm_calls",
        "lifecycle_valid",
    }
    for record, expected in zip(case_records, CASES):
        if not isinstance(record, dict) or set(record) != {
            "id", "set", "case_digest", "outcomes"
        }:
            raise ValueError("runtime-protocol case record is malformed")
        expected_digest = hashlib.sha256(
            canonical_json_bytes(expected)
        ).hexdigest()
        if (
            record["id"] != expected["id"]
            or record["set"] != expected["set"]
            or record["case_digest"] != expected_digest
        ):
            raise ValueError("runtime-protocol case identity is invalid")
        outcomes = record["outcomes"]
        if not isinstance(outcomes, dict) or set(outcomes) != {
            "legacy", "receipt_v1"
        }:
            raise ValueError("runtime-protocol outcome inventory is invalid")
        for protocol in ("legacy", "receipt_v1"):
            outcome = outcomes[protocol]
            if not isinstance(outcome, dict) or set(outcome) != outcome_fields:
                raise ValueError("runtime-protocol outcome is malformed")
            if outcome["protocol"] != protocol:
                raise ValueError("runtime-protocol outcome label is invalid")
            for field in (
                "finished", "false_completion", "unverified_completion"
            ):
                if type(outcome[field]) is not bool:
                    raise ValueError(
                        "runtime-protocol outcome booleans are invalid"
                    )
            if (
                outcome["strict_success"] is not None
                and type(outcome["strict_success"]) is not bool
            ):
                raise ValueError("runtime-protocol strict result is invalid")
            if (
                outcome["lifecycle_valid"] is not None
                and type(outcome["lifecycle_valid"]) is not bool
            ):
                raise ValueError("runtime-protocol lifecycle result is invalid")
            for field in ("successful_increments", "llm_calls"):
                if type(outcome[field]) is not int or outcome[field] < 0:
                    raise ValueError(
                        "runtime-protocol outcome counters are invalid"
                    )
            if outcome["false_completion"] is not bool(
                outcome["finished"]
                and outcome["strict_success"] is False
            ):
                raise ValueError(
                    "runtime-protocol false-completion flag is inconsistent"
                )
            if outcome["unverified_completion"] is not bool(
                outcome["finished"]
                and outcome["strict_success"] is None
            ):
                raise ValueError(
                    "runtime-protocol unverified-completion flag is inconsistent"
                )


def _derive_summary_and_gate(case_records):
    _validate_case_records(case_records)
    acceptance = [
        item for item in case_records if item["set"] == "acceptance"
    ]
    legacy_false = sum(
        item["outcomes"]["legacy"]["false_completion"]
        for item in acceptance
    )
    receipt_false = sum(
        item["outcomes"]["receipt_v1"]["false_completion"]
        for item in acceptance
    )
    legacy_unverified = sum(
        item["outcomes"]["legacy"]["unverified_completion"]
        for item in acceptance
    )
    receipt_unverified = sum(
        item["outcomes"]["receipt_v1"]["unverified_completion"]
        for item in acceptance
    )
    valid_cases = [
        item for item in case_records
        if item["id"] in {"valid_success", "valid_at_budget_boundary"}
    ]
    valid_regressions = sum(
        item["outcomes"]["legacy"]["strict_success"] is True
        and item["outcomes"]["receipt_v1"]["strict_success"] is not True
        for item in valid_cases
    )
    extra = next(
        item for item in case_records
        if item["id"] == "unplanned_extra_effect"
    )
    summary = {
        "acceptance_cases": len(acceptance),
        "legacy_false_completions": legacy_false,
        "receipt_false_completions": receipt_false,
        "legacy_unverified_completions": legacy_unverified,
        "receipt_unverified_completions": receipt_unverified,
        "valid_success_regressions": valid_regressions,
    }
    gate = {
        "receipt_false_completions_zero": receipt_false == 0,
        "false_completions_reduced": receipt_false < legacy_false,
        "receipt_unverified_completions_zero": receipt_unverified == 0,
        "unverified_completions_reduced": (
            receipt_unverified < legacy_unverified
        ),
        "valid_success_regressions_zero": valid_regressions == 0,
        "unplanned_extra_effect_prevented": (
            extra["outcomes"]["legacy"]["successful_increments"] == 3
            and extra["outcomes"]["receipt_v1"]["successful_increments"]
            == 2
        ),
        "all_receipt_lifecycles_valid": all(
            item["outcomes"]["receipt_v1"]["lifecycle_valid"] is True
            for item in case_records
        ),
    }
    return summary, gate


def evaluate(root=None):
    root = Path(root or Path(__file__).resolve().parents[2])
    case_records = []
    with tempfile.TemporaryDirectory(prefix="brick-runtime-eval-") as temp_root:
        for case in CASES:
            outcomes = {
                protocol: _run_case(root, case, protocol, temp_root)
                for protocol in ("legacy", "receipt_v1")
            }
            case_records.append(
                {
                    "id": case["id"],
                    "set": case["set"],
                    "case_digest": hashlib.sha256(
                        canonical_json_bytes(case)
                    ).hexdigest(),
                    "outcomes": outcomes,
                }
            )

    summary, gate = _derive_summary_and_gate(case_records)
    source = {name: _sha256_file(root / name) for name in SOURCE_FILES}
    report = {
        "schema_version": EVALUATION_VERSION,
        "scope": EVALUATION_SCOPE,
        "source_commit": _git_head(root),
        "source_state": SOURCE_STATE,
        "source_digests": source,
        "cases": case_records,
        "summary": summary,
        "promotion_gate": gate,
        "promotion_pass": all(gate.values()),
    }
    report["report_digest"] = hashlib.sha256(
        canonical_json_bytes(report)
    ).hexdigest()
    return report


def validate_report(report, root=None):
    """Recompute the report digest and every bound source digest."""
    root = Path(root or Path(__file__).resolve().parents[2])
    if (
        not isinstance(report, dict)
        or report.get("schema_version") != EVALUATION_VERSION
    ):
        raise ValueError("unsupported runtime-protocol evidence")
    claimed = report.get("report_digest")
    unsigned = dict(report)
    unsigned.pop("report_digest", None)
    actual = hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()
    if claimed != actual:
        raise ValueError("runtime-protocol report digest is invalid")
    expected_sources = {
        name: _sha256_file(root / name) for name in SOURCE_FILES
    }
    if report.get("source_digests") != expected_sources:
        raise ValueError("runtime-protocol source digests do not match")
    source_commit = report.get("source_commit")
    commit_shape_valid = (
        source_commit == "unavailable"
        or (
            isinstance(source_commit, str)
            and len(source_commit) == 40
            and all(character in "0123456789abcdef" for character in source_commit)
        )
    )
    if (
        report.get("scope") != EVALUATION_SCOPE
        or report.get("source_state") != SOURCE_STATE
        or not commit_shape_valid
    ):
        raise ValueError("runtime-protocol report provenance is inconsistent")
    summary, gate = _derive_summary_and_gate(report.get("cases"))
    if (
        report.get("summary") != summary
        or report.get("promotion_gate") != gate
        or type(report.get("promotion_pass")) is not bool
        or report["promotion_pass"] != all(gate.values())
    ):
        raise ValueError("runtime-protocol promotion decision is inconsistent")
    return True


def write_report(report, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        report, ensure_ascii=False, indent=2, sort_keys=True
    ).encode("utf-8") + b"\n"
    temporary = output.with_suffix(output.suffix + ".tmp")
    with open(temporary, "xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, output)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="evidence/runtime-protocol/acceptance-v1.json",
    )
    args = parser.parse_args(argv)
    report = evaluate()
    write_report(report, args.output)
    print(json.dumps(report["summary"], sort_keys=True))
    print("promotion_pass={}".format(report["promotion_pass"]))
    return 0 if report["promotion_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
