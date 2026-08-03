"""Grade D0 in memory and emit only direction-blind floor/ceiling totals."""

import argparse
from collections import Counter
import json
from pathlib import Path

from bench.s7_artifacts import commit_artifact, verify_artifact
from bench.s7_contract import DEFAULT_PROTOCOL, load_protocol, s7_protocol_sha256
from bench.s7_decision import _final_records, build_decision
from domains.office_demo.generated_grader import (
    GRADER_VERSION,
    build_grader,
    task_id_for,
)
from harness.evidence import EvidenceStore, validate_committed
from harness.grading import GradingEvidence
from harness.instances import load_canonical_json


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFESTS = ROOT / "bench" / "manifests" / "office-v1"


def _grade_record(store, record, instance):
    candidate = (
        store.attempts_dir
        / record["logical_hash"]
        / record["physical_uuid"]
    )
    validate_committed(candidate)
    final_state = load_canonical_json(candidate / "final-state.json")["payload"]
    actions = load_canonical_json(candidate / "actions.json")["actions"]
    artifacts = [
        (path.name, path.read_bytes())
        for path in sorted((candidate / "artifacts").iterdir())
    ]
    evidence = GradingEvidence.from_values(
        domain=instance["content"]["domain"],
        domain_version=instance["content"]["domain_version"],
        task_id=task_id_for(instance),
        state=final_state["business"],
        actions=actions,
        memory=final_state["memory"],
        artifacts=artifacts,
    )
    outcome = build_grader(instance).grade_evidence(evidence)
    if outcome.grader_status != "graded":
        raise RuntimeError("deferred D0 grading failed")
    return bool(
        outcome.strict_success and record["failure_origin"] != "model"
    )


def build_audit(
    runs_root,
    run_id,
    decision_directory,
    protocol_path=DEFAULT_PROTOCOL,
    manifests=DEFAULT_MANIFESTS,
):
    protocol = load_protocol(protocol_path)
    sealed_decision = verify_artifact(
        decision_directory, "brick.s7.runtime-decision/1"
    )["document"]
    expected_decision = build_decision(
        runs_root, run_id, protocol_path, manifests
    )
    if sealed_decision != expected_decision:
        raise RuntimeError("runtime decision does not bind the current D0 evidence")
    store = EvidenceStore.open_run(runs_root, run_id)
    _projection, finals = _final_records(store, protocol, manifests)
    manifest = load_canonical_json(Path(manifests) / "development.json")
    instances = {
        item["content"]["id"]: item for item in manifest["instances"]
    }
    totals = Counter()
    counts = Counter()
    for record in finals:
        key = record["attempt_key"]
        instance = instances.get(key["instance"]["id"])
        if instance is None:
            raise RuntimeError("D0 evidence references an unknown instance")
        family = key["task"]["family"]
        totals[family] += int(_grade_record(store, record, instance))
        counts[family] += 1
    audit_rule = protocol["d0"]["floor_ceiling_audit"]
    if set(counts) != set(manifest["family_counts"]):
        raise RuntimeError("D0 audit does not cover all frozen families")
    if any(
        count != audit_rule["combined_outcomes_per_family"]
        for count in counts.values()
    ):
        raise RuntimeError("D0 audit requires eight combined outcomes per family")
    family_totals = [
        {
            "family": family,
            "combined_successes": totals[family],
            "combined_outcomes": counts[family],
        }
        for family in sorted(counts)
    ]
    flags = []
    for item in family_totals:
        if item["combined_successes"] <= audit_rule["floor_maximum_successes"]:
            flags.append({"family": item["family"], "flag": "floor"})
        elif item["combined_successes"] >= audit_rule["ceiling_minimum_successes"]:
            flags.append({"family": item["family"], "flag": "ceiling"})
    return {
        "schema_version": "brick.s7.floor-ceiling-audit/1",
        "run_id": run_id,
        "run_sha256": store.run_sha256,
        "runtime_decision_sha256": verify_artifact(
            decision_directory, "brick.s7.runtime-decision/1"
        )["artifact_sha256"],
        "s7_protocol_sha256": s7_protocol_sha256(protocol),
        "grader_version": GRADER_VERSION,
        "direction_blind": True,
        "family_combined_totals": family_totals,
        "flags": flags,
        "protocol_freeze_allowed": not flags,
        "condition_scores_emitted": False,
        "directional_effects_computed": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--decision", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--manifests", type=Path, default=DEFAULT_MANIFESTS)
    args = parser.parse_args(argv)
    sealed = commit_artifact(
        args.output,
        build_audit(
            args.runs_root, args.run_id, args.decision,
            args.protocol, args.manifests,
        ),
    )
    print(json.dumps(sealed, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
