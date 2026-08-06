"""End-to-end model-free rehearsal of the successor study pipeline."""

import argparse
from collections import defaultdict
import copy
from pathlib import Path
import tempfile

from harness.evidence import AttemptKey, EvidenceStore, canonical_json_bytes
from harness.instances import load_canonical_json, replace_canonical_json, sha256_bytes

from .next_study_descriptive import (
    build_report as build_descriptive_report,
    eligible_schedule,
    extract_descriptive_results,
    extract_primary_trial_0_controls,
    seal_descriptive_eligibility,
)
from .next_study_program import (
    REQUIRED_ARTIFACT_DIGESTS, SEALED_GATE_SCHEMA, advance_program,
    build_authorization, build_fingerprint, initial_program_state,
    HOST_FINGERPRINT_SCHEMA, primary_mask_key_commitment,
    RUNTIME_FINGERPRINT_SCHEMA,
)
from .next_study_report import build_study_report
from .next_study_runtime import (
    ATTEMPT_RECORD_SCHEMA, NextStudyRuntimeError, build_masked_grade_ledger,
    extract_attempt_records, unmask_primary, verify_release,
)
from .next_study_schedule import build_descriptive_schedule, build_phase_schedule
from .next_study_statistics import analyze_primary


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "evidence" / "next-study" / "office-v2-model-free-rehearsal.json"
SCHEMA_VERSION = "brick.next-study.model-free-rehearsal/1"
CONTEXT = "synthetic_rehearsal"
MASKING_KEY = "7" * 64
CONTEXT_DOCUMENT = {
    "schema_version": "brick.next-study.execution-context/1", "value": CONTEXT,
}


class RehearsalError(ValueError):
    pass


def _digest(value):
    return sha256_bytes(canonical_json_bytes(value, allow_float=False))


def _families(retained):
    result = defaultdict(list)
    for instance in retained["instances"]:
        result[instance["content"]["family"]].append(instance["content"]["id"])
    return {key: value for key, value in sorted(result.items())}


def _positive_values(retained, half_units):
    groups = _families(retained)
    base, remainder = divmod(half_units, len(groups))
    values = {}
    for index, identifiers in enumerate(groups.values()):
        count = base + (index < remainder)
        for identifier in identifiers[:count]:
            values[identifier] = 0.5
    return values


def _uncertain_values(retained):
    groups = _families(retained)
    values = {}
    for index, identifiers in enumerate(groups.values()):
        positive = 12 if index < 2 else 11
        for identifier in identifiers[:positive]:
            values[identifier] = 1
        for identifier in identifiers[positive:]:
            values[identifier] = -1
    # This frozen location yields the committed nearest-rank interval exactly.
    first = next(iter(groups.values()))
    values[first[14]] = -0.5
    return values


def _outcomes(value):
    if value == 1:
        return [False, False], [True, True]
    if value == 0.5:
        return [False, False], [True, False]
    if value == -0.5:
        return [True, False], [False, False]
    if value == -1:
        return [True, True], [False, False]
    return [False, False], [False, False]


def _attempts(schedule, values):
    records = []
    for cell in schedule["records"]:
        native, harness = _outcomes(values.get(cell["instance_id"], 0))
        success = (harness if cell["condition"] == "harness_full" else native)[
            cell["trial_index"]
        ]
        records.append({
            "schema_version": ATTEMPT_RECORD_SCHEMA,
            "logical_cell_id": cell["logical_cell_id"],
            "repeat": 0,
            "trial_seed": cell["trial_seed"],
            "failure_origin": "none",
            "retryable": False,
            "strict_success": success,
            "evidence_sha256": _digest({"cell": cell["logical_cell_id"], "success": success}),
            "grade_record_sha256": _digest({"strict_success": success}),
            "marker_last_verified": True,
            "model_calls": 1,
            "successful_reads": 0,
            "successful_mutations": 0,
            "generated_tokens_exact": 1,
            "generated_tokens_lower_bound": None,
            "generated_tokens_upper_bound": None,
            "model_time_ms": 1,
            "wall_time_ms": 1,
        })
    return records


def _analyze(retained, schedule, values, *, omit_smallest=False):
    attempts = _attempts(schedule, values)
    if omit_smallest:
        smallest = min(item["logical_cell_id"] for item in attempts)
        attempts = [item for item in attempts if item["logical_cell_id"] != smallest]
    try:
        masked = build_masked_grade_ledger(
            schedule, attempts, retained, "2026-08-05T10:00:00Z",
            MASKING_KEY,
            execution_context=CONTEXT,
        )
    except ValueError:
        if omit_smallest:
            return {
                "status": "INCOMPLETE/DESCRIPTIVE",
                "omitted_logical_cell_id": smallest,
                "unmasked": False,
                "effect": None,
                "descriptives_ran": False,
                "release_attempted": False,
            }, None, None
        raise
    ledger = unmask_primary(
        masked, schedule, retained, attempts, MASKING_KEY,
        "2026-08-05T10:01:00Z",
    )
    analysis = analyze_primary(ledger, retained, schedule)
    return {
        "status": "sealed_complete",
        "paired_effect": analysis["paired_effect"],
        "interval": analysis["cluster_bootstrap_95_interval"],
        "claim_disposition": analysis["claim_disposition"],
        "unmasked": True,
    }, ledger, analysis


def _evidence_store_smoke(directory, schedule):
    cell = schedule["records"][0]
    key = AttemptKey(
        domain_name="office_demo", domain_version="0.1.0",
        domain_content_sha256="a" * 64, task_family=cell["family"],
        task_version="2.1.1", generator_version="office-generators/2.1.1",
        grader_version="3.1.0", model_tag="mock:4b",
        model_digest="sha256:" + schedule["model_sha256"],
        condition_name=cell["condition"], condition_version="1.4.0",
        mechanism_sha256="b" * 64, instance_id=cell["instance_id"],
        instance_content_sha256=cell["content_sha256"], ordered_subepisodes=(),
        repeat=0, sampling={"seed": cell["trial_seed"], "temperature": "0"},
        opportunity_budget={"model_calls": 18, "generated_tokens": 6144},
        prompt_sha256="c" * 64, tool_schema_sha256="d" * 64,
    )
    store = EvidenceStore.create_run(Path(directory) / "runs", "rehearsal-smoke", {"mock": True})
    def producer(writer):
        for name, kind in (("initial-state.json", "initial"), ("final-state.json", "final")):
            writer.write_json(name, {
                "schema_version": "brick.evidence-state/1", "state_kind": kind,
                "payload": {},
            })
        writer.write_json("result.json", {
            "schema_version": "brick.evidence-result/1", "execution_status": "done",
            "tool_status": "clean", "failure_origin": "none", "failure": None,
            "metrics": {
                "model_calls": 1, "generated_tokens": 7,
                "model_time_ms": 2, "wall_time_ms": 3,
            },
            "diagnostics": {"ledger": {"generated_tokens_exact": True}},
        })
        writer.write_json("grade.json", {
            "schema_version": "brick.evidence-grade/1", "grader_status": "graded",
            "candidate_decision": True, "diagnostics": [],
        })
        writer.write_json("actions.json", {
            "schema_version": "brick.evidence-actions/1",
            "actions": [{"tool": "read_email", "ok": True, "args": {}}],
        })
        writer.write_bytes("transcript.md", b"# synthetic rehearsal\n")
        writer.write_bytes("memory-delta.jsonl", b'{"delta":[],"schema_version":"brick.memory-delta/1"}\n')
    store.execute_or_resume(key, producer)
    extracted = extract_attempt_records(store, schedule)
    if len(extracted) != 1 or extracted[0]["generated_tokens_exact"] != 7:
        raise RehearsalError("marker-last evidence extraction smoke failed")
    return {
        "committed_cells": 1,
        "marker_last_verified": extracted[0]["marker_last_verified"],
        "resource_fields_evidence_derived": True,
    }


def _program_to_release(
    schedule, descriptive_schedule, primary_analysis, descriptive_report,
    manifest_lock,
):
    model_digests = {"2b": "2" * 64, "4b": "4" * 64, "9b": "9" * 64}
    schedules = {
        "calibration": "1" * 64, "sentinel": "2" * 64,
        "primary": _digest(schedule), "descriptives": _digest(descriptive_schedule),
    }
    artifact_digests = {name: "b" * 64 for name in REQUIRED_ARTIFACT_DIGESTS}
    artifact_digests["manifest_lock"] = sha256_bytes(
        canonical_json_bytes(manifest_lock, allow_float=False, newline=True)
    )
    authorization = build_authorization(
        tag="v0.13.1", tag_object_sha="9" * 40, commit_sha="a" * 40,
        artifact_digests=artifact_digests,
        host_fingerprint=build_fingerprint(HOST_FINGERPRINT_SCHEMA, {"host": "mock"}),
        runtime_fingerprint=build_fingerprint(RUNTIME_FINGERPRINT_SCHEMA, {"runtime": "mock"}),
        schedule_digests=schedules, model_digests=model_digests,
        descriptive_selection_sha256=descriptive_schedule["selection_sha256"],
        primary_mask_key_commitment_sha256=primary_mask_key_commitment(
            MASKING_KEY
        ),
        issued_at="2026-08-05T10:00:00Z", issuer="model-free rehearsal",
        execution_context=CONTEXT,
    )
    state = initial_program_state(authorization["authorization_sha256"])
    for phase, logical in (
        ("calibration", 352), ("sentinel", 88), ("primary", 880),
        ("primary_analysis", 0), ("descriptives", 222),
    ):
        state = advance_program(state, {
            "schema_version": SEALED_GATE_SCHEMA,
            "authorization_sha256": authorization["authorization_sha256"],
            "phase": phase, "status": "sealed_pass",
            "logical_cells_completed": logical,
            "physical_attempts_completed": logical,
            "sealed_artifact_sha256": (
                _digest(primary_analysis) if phase == "primary_analysis"
                else _digest(descriptive_report) if phase == "descriptives"
                else _digest({"phase": phase})
            ),
        })
    return authorization, state


def run_rehearsal(output_root=None):
    retained = load_canonical_json(ROOT / "bench" / "manifests" / "office-v2" / "retained.json")
    primary_schedule = build_phase_schedule(retained, "primary", "4" * 64)
    descriptive_schedule = build_descriptive_schedule(
        retained, {"2b": "2" * 64, "4b": "4" * 64, "9b": "9" * 64},
    )
    scenarios = {}
    definitions = {
        "harness_near_positive_0_13": _positive_values(retained, 57),
        "small_positive": _positive_values(retained, 48),
        "native_near_negative_0_13": {
            key: -value for key, value in _positive_values(retained, 57).items()
        },
        "null": {},
        "threshold_but_uncertain": _uncertain_values(retained),
    }
    ledgers = analyses = None
    for name, values in definitions.items():
        result, ledger, analysis = _analyze(retained, primary_schedule, values)
        scenarios[name] = result
        if name == "harness_near_positive_0_13":
            ledgers, analyses = ledger, analysis
    scenarios["incomplete"] = _analyze(
        retained, primary_schedule, {}, omit_smallest=True,
    )[0]
    boundary = {}
    for units in (52, 53):
        result, _ledger, _analysis = _analyze(
            retained, primary_schedule, _positive_values(retained, units)
        )
        boundary[str(units) + "/440"] = result

    eligibility = seal_descriptive_eligibility(analyses, ledgers, descriptive_schedule)
    eligible = eligible_schedule(
        descriptive_schedule, {"2b": True, "4b": True, "9b": True}, eligibility,
    )
    descriptive_attempts = _attempts(descriptive_schedule, {})
    descriptive_evidence = extract_descriptive_results(eligible, descriptive_attempts)
    controls = extract_primary_trial_0_controls(ledgers, descriptive_schedule)
    descriptive_report = build_descriptive_report(eligible, descriptive_evidence, controls)
    manifest_lock = load_canonical_json(
        ROOT / "bench" / "manifests" / "office-v2" / "manifest-lock.json"
    )
    authorization, state = _program_to_release(
        primary_schedule, descriptive_schedule, analyses, descriptive_report,
        manifest_lock,
    )
    study_report, resource_report, failure_taxonomy, program_bindings = build_study_report(
        analyses, descriptive_report, manifest_lock, ledgers, authorization, state,
        ["Synthetic outcomes are pipeline fixtures, not empirical findings."],
    )
    release_rejections = {}
    for attack in ("renamed", "rehashed", "copied"):
        try:
            verify_release(
                output_root or ROOT, authorization, state,
                {"attack": attack}, annotated_tag="v0.14.0",
            )
        except NextStudyRuntimeError:
            release_rejections[attack] = True
        else:
            release_rejections[attack] = False
    temporary = tempfile.TemporaryDirectory(
        prefix="brick-rehearsal-", dir=str(output_root) if output_root else None
    )
    try:
        evidence_smoke = _evidence_store_smoke(temporary.name, primary_schedule)
    finally:
        temporary.cleanup()
    expected = {
        "harness_near_positive_0_13": (
            "0.129545454545455", ["0.100000000000000", "0.159090909090909"],
            "harness_full_directional_superiority",
        ),
        "small_positive": (
            "0.109090909090909", ["0.081818181818182", "0.136363636363636"],
            "no_directional_superiority_claim",
        ),
        "native_near_negative_0_13": (
            "-0.129545454545455", ["-0.159090909090909", "-0.100000000000000"],
            "native_tools_directional_superiority",
        ),
        "null": ("0.000000000000000", ["0.000000000000000", "0.000000000000000"], "no_directional_superiority_claim"),
        "threshold_but_uncertain": (
            "0.120454545454545", ["-0.009090909090909", "0.250000000000000"],
            "no_directional_superiority_claim",
        ),
    }
    for name, (effect, interval, claim) in expected.items():
        actual = scenarios[name]
        if (
            actual["paired_effect"] != effect or actual["interval"] != interval
            or actual["claim_disposition"] != claim
        ):
            raise RehearsalError("scenario %s drifted" % name)
    if (
        boundary["52/440"]["claim_disposition"] != "no_directional_superiority_claim"
        or boundary["53/440"]["claim_disposition"] != "harness_full_directional_superiority"
        or scenarios["incomplete"]["effect"] is not None
        or not all(release_rejections.values())
    ):
        raise RehearsalError("claim boundary, incomplete, or release isolation drifted")
    return {
        "schema_version": SCHEMA_VERSION,
        "display_label": "mock-v0.14.0",
        "execution_context": copy.deepcopy(CONTEXT_DOCUMENT),
        "status": "passed",
        "scenarios": scenarios,
        "whole_ledger_boundaries": boundary,
        "descriptive_cells": descriptive_report["completed_cells"],
        "study_report_sha256": study_report["study_report_sha256"],
        "release_rejections": release_rejections,
        "evidence_store_smoke": evidence_smoke,
        "production_evidence_written": False,
        "git_tags_created": 0,
        "live_model_calls": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    result = run_rehearsal(args.output.parent if args.write else None)
    if args.write:
        replace_canonical_json(args.output, result)
    print({
        "status": result["status"], "scenarios": len(result["scenarios"]),
        "descriptive_cells": result["descriptive_cells"],
        "live_model_calls": result["live_model_calls"],
    })


if __name__ == "__main__":
    main()


__all__ = ["DEFAULT_OUTPUT", "RehearsalError", "run_rehearsal"]
