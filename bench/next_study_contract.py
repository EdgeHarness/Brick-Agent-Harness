"""Fail-closed contract for the post-S7 successor instrument build."""

import hashlib
from pathlib import Path

from bench.next_study_statistics import load_protocol
from bench.s7_postmortem import build_postmortem
from bench.s7_contract import load_protocol as load_s7_protocol
from bench.s7_contract import s7_protocol_sha256
from harness.evidence import canonical_json_bytes
from harness.instances import load_canonical_json


ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = ROOT / "bench" / "next_study_design.json"

_CONDITIONS = ["native_tools", "harness_full"]
_EXPECTED_GATES = {
    "calibration_protocol_frozen": True,
    "fresh_generator_complete": True,
    "grader_mutation_matrix_complete": False,
    "independent_oracle_complete": True,
    "live_execution_authorized": False,
    "power_and_cluster_analysis_frozen": True,
    "prompt_ground_truth_review_complete": False,
    "sentinel_protocol_frozen": True,
}
_DIFFICULTY_AXES = [
    "minimum_discovery_calls",
    "minimum_source_reads",
    "minimum_mutating_calls",
    "artifact_rows_or_slides",
    "source_items",
    "constraint_branches",
    "subepisodes",
]
_IDENTITY_REUSE_CHANNELS = [
    "instance_id",
    "content_sha256",
    "structure_sha256",
    "entity_key",
    "entity_surface",
]


class NextStudyDesignError(ValueError):
    pass


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _bound_path(record, path_key, digest_key):
    path = ROOT / record.get(path_key, "")
    if not path.is_file() or _sha256(path) != record.get(digest_key):
        raise NextStudyDesignError("artifact binding failed for %s" % path_key)
    return path


def load_design(path=DESIGN_PATH):
    design = load_canonical_json(path)
    validate_design(design)
    return design


def _validate_predecessor(design):
    predecessor = design.get("predecessor", {})
    for path_key, digest_key in (
        ("runtime_decision_path", "runtime_decision_sha256"),
        ("floor_ceiling_audit_path", "floor_ceiling_audit_sha256"),
    ):
        _bound_path(predecessor, path_key, digest_key)
    postmortem_path = _bound_path(
        predecessor, "postmortem_path", "postmortem_sha256"
    )
    protocol_path = ROOT / predecessor.get("s7_protocol_path", "")
    if (
        not protocol_path.is_file()
        or s7_protocol_sha256(load_s7_protocol(protocol_path))
        != predecessor.get("s7_protocol_sha256")
    ):
        raise NextStudyDesignError("predecessor binding failed for s7_protocol_path")
    postmortem_bytes = canonical_json_bytes(build_postmortem(), newline=True)
    postmortem_sha256 = hashlib.sha256(postmortem_bytes).hexdigest()
    if (
        postmortem_sha256 != predecessor.get("postmortem_sha256")
        or postmortem_path.read_bytes() != postmortem_bytes
    ):
        raise NextStudyDesignError("direction-blind postmortem digest drifted")


def _validate_successor_artifacts(design):
    artifacts = design.get("successor_artifacts", {})
    expected_keys = {
        "manifest_lock_path", "manifest_lock_sha256", "oracle_audit_path",
        "oracle_audit_sha256", "review_ledger_path", "review_ledger_sha256",
        "review_ledger_status", "review_implementation_path",
        "review_implementation_sha256", "protocol_path", "protocol_sha256",
        "statistics_implementation_path", "statistics_implementation_sha256",
    }
    if not isinstance(artifacts, dict) or set(artifacts) != expected_keys:
        raise NextStudyDesignError("successor artifact bindings have unexpected keys")
    lock_path = _bound_path(artifacts, "manifest_lock_path", "manifest_lock_sha256")
    audit_path = _bound_path(artifacts, "oracle_audit_path", "oracle_audit_sha256")
    ledger_path = _bound_path(artifacts, "review_ledger_path", "review_ledger_sha256")
    protocol_path = _bound_path(artifacts, "protocol_path", "protocol_sha256")
    _bound_path(
        artifacts, "review_implementation_path", "review_implementation_sha256"
    )
    _bound_path(
        artifacts,
        "statistics_implementation_path",
        "statistics_implementation_sha256",
    )

    lock = load_canonical_json(lock_path)
    if (
        lock.get("schema_version") != "brick.next-study.manifest-lock/1"
        or lock.get("generator_version") != "office-generators/2.0.0"
        or [item.get("split") for item in lock.get("manifests", [])]
        != [
            "development", "calibration", "validation", "sentinel",
            "retained", "adversarial",
        ]
        or sum(item.get("instances", 0) for item in lock.get("manifests", []))
        != 528
        or lock.get("overlap_review", {}).get("structures") != 528
        or lock.get("predecessor_reuse_review", {}).get("overlap_counts")
        != {
            "content_sha256": 0,
            "entity_key": 0,
            "entity_surface": 0,
            "instance_id": 0,
            "structure_sha256": 0,
        }
    ):
        raise NextStudyDesignError("fresh generator lock is incomplete")

    audit = load_canonical_json(audit_path)
    if (
        audit.get("schema_version") != "brick.next-study.oracle-audit/1"
        or audit.get("generator_version") != "office-generators/2.0.0"
        or audit.get("case_count") != 528
        or audit.get("prompt_to_hidden_outcome_exact_matches") != 528
        or audit.get("all_exact_matches") is not True
        or audit.get("oracle_accepts_required_effects_parameter") is not False
        or audit.get("required_effects_consumed_by_oracle") is not False
        or audit.get("grader_output_consumed_by_oracle") is not False
        or audit.get("live_model_calls") != 0
        or audit.get("manifest_lock_sha256") != artifacts["manifest_lock_sha256"]
    ):
        raise NextStudyDesignError("independent oracle audit is incomplete")

    ledger = load_canonical_json(ledger_path)
    if (
        ledger.get("schema_version") != "brick.next-study.review-ledger/1"
        or ledger.get("generator_version") != "office-generators/2.0.0"
        or ledger.get("cases") != 528
        or ledger.get("completed_cases") != 0
        or ledger.get("status") != "pending_human_review"
        or artifacts.get("review_ledger_status") != ledger.get("status")
    ):
        raise NextStudyDesignError("human review ledger status is inconsistent")

    if protocol_path.resolve() != (ROOT / "bench" / "next_study_protocol.json").resolve():
        raise NextStudyDesignError("next-study protocol path drifted")
    protocol = load_protocol(protocol_path)
    if protocol["execution_controls"]["live_model_execution_enabled"] is not False:
        raise NextStudyDesignError("successor protocol enables live execution")
    return lock, audit, ledger, protocol


def validate_design(design):
    if design.get("schema_version") != "brick.next-study.design/1":
        raise NextStudyDesignError("unexpected next-study design schema")
    if (
        design.get("version") != "0.2.0"
        or design.get("status") != "offline_instrument_build"
    ):
        raise NextStudyDesignError("next-study design is not the frozen offline build")
    if design.get("live_model_execution_enabled") is not False:
        raise NextStudyDesignError("next-study live model execution must remain disabled")
    if design.get("retained_execution_enabled") is not False:
        raise NextStudyDesignError("next-study retained execution must remain disabled")
    if design.get("execution_gates") != _EXPECTED_GATES:
        raise NextStudyDesignError("next-study execution gates do not match artifacts")

    _validate_predecessor(design)
    _lock, _audit, _ledger, protocol = _validate_successor_artifacts(design)

    fresh = design.get("fresh_suite", {})
    expected_fresh = {
        "generator_version": "office-generators/2.0.0",
        "seed_namespace": "office-generators/2.0.0",
        "families": 11,
        "development_cases_per_family": 8,
        "calibration_cases_per_family": 8,
        "validation_cases_per_family": 4,
        "sentinel_cases_per_family": 4,
        "retained_cases_per_family": 20,
        "adversarial_cases_per_family": 4,
        "total_cases": 528,
    }
    if fresh != expected_fresh:
        raise NextStudyDesignError("fresh-suite allocation drifted")
    if fresh["generator_version"] == design["predecessor"]["retired_generator_version"]:
        raise NextStudyDesignError("successor reuses the retired generator namespace")

    calibration = design.get("calibration", {})
    if (
        calibration.get("cases_per_family") != 8
        or calibration.get("conditions") != _CONDITIONS
        or calibration.get("independent_trials_per_cell") != 2
        or calibration.get("model_attempts") != 352
        or calibration.get("combined_outcomes_per_family") != 32
        or calibration.get("direction_blind") is not True
        or calibration.get("acceptable_combined_successes_minimum") != 10
        or calibration.get("acceptable_combined_successes_maximum") != 22
        or calibration.get("outcome_granularity_percentage_points") != "3.125"
        or calibration.get(
            "task_shape_selection_may_use_only_direction_blind_development_and_calibration_aggregates"
        ) is not True
        or calibration.get("any_family_outside_band_retires_complete_generator_version")
        is not True
    ):
        raise NextStudyDesignError("calibration design drifted")
    if protocol["calibration"]["model_attempts"] != calibration["model_attempts"]:
        raise NextStudyDesignError("calibration protocol/design mismatch")

    primary = design.get("primary_design", {})
    if (
        primary.get("cases_per_family") != 20
        or primary.get("instance_clusters") != 220
        or primary.get("conditions") != _CONDITIONS
        or primary.get("independent_trials_per_cell") != 2
        or primary.get("model_attempts") != 880
        or primary.get("paired_seed_across_conditions") is not True
        or primary.get("minimum_relevant_absolute_effect") != "0.12"
        or primary.get("normal_approximation_power") != "0.828074238908"
        or "instance-clustered paired effect" not in primary.get("required_analysis", "")
    ):
        raise NextStudyDesignError("primary design drifted")
    if protocol["primary"]["model_attempts"] != primary["model_attempts"]:
        raise NextStudyDesignError("primary protocol/design mismatch")

    sentinel = design.get("sentinel", {})
    if (
        sentinel.get("cases_per_family") != 4
        or sentinel.get("trials_per_cell") != 1
        or sentinel.get("primary_condition_cells") != 88
        or sentinel.get("instrument_invalid_cells_allowed") != 0
        or sentinel.get("zero_failure_one_sided_95_upper_bound")
        != "0.03346948891663748"
        or sentinel.get("bound_is_diagnostic_not_efficacy_claim") is not True
    ):
        raise NextStudyDesignError("sentinel design drifted")
    if protocol["sentinel"]["condition_cells"] != sentinel["primary_condition_cells"]:
        raise NextStudyDesignError("sentinel protocol/design mismatch")

    controls = design.get("required_controls", {})
    if controls.get("difficulty_axes") != _DIFFICULTY_AXES:
        raise NextStudyDesignError("required difficulty axes drifted")
    if controls.get("identity_reuse_channels") != _IDENTITY_REUSE_CHANNELS:
        raise NextStudyDesignError("identity reuse controls drifted")
    if controls.get("old_suite_model_reuse_allowed") is not False:
        raise NextStudyDesignError("retired-suite model-result reuse enabled")
    if "must not consume required_effects or grader output" not in controls.get(
        "oracle_independence", ""
    ):
        raise NextStudyDesignError("independent-oracle requirement weakened")
    if "two independent reviewers with adjudication" not in controls.get(
        "human_review", ""
    ):
        raise NextStudyDesignError("human-review requirement weakened")
    return design


def execution_allowed(design=None):
    validate_design(load_design() if design is None else design)
    return False


__all__ = [
    "DESIGN_PATH",
    "NextStudyDesignError",
    "execution_allowed",
    "load_design",
    "validate_design",
]
