"""Fail-closed contract for the post-S7 next-study design."""

import hashlib
from pathlib import Path

from bench.s7_postmortem import build_postmortem
from bench.s7_contract import load_protocol, s7_protocol_sha256
from harness.evidence import canonical_json_bytes
from harness.instances import load_canonical_json


ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = ROOT / "bench" / "next_study_design.json"

_CONDITIONS = ["native_tools", "harness_full"]
_EXECUTION_GATES = {
    "calibration_protocol_frozen",
    "fresh_generator_complete",
    "grader_mutation_matrix_complete",
    "independent_oracle_complete",
    "live_execution_authorized",
    "power_and_cluster_analysis_frozen",
    "prompt_ground_truth_review_complete",
    "sentinel_protocol_frozen",
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


def load_design(path=DESIGN_PATH):
    design = load_canonical_json(path)
    validate_design(design)
    return design


def validate_design(design):
    if design.get("schema_version") != "brick.next-study.design/1":
        raise NextStudyDesignError("unexpected next-study design schema")
    if (
        design.get("version") != "0.1.0"
        or design.get("status") != "offline_design_only"
    ):
        raise NextStudyDesignError("next-study design is not the reviewed offline version")
    if design.get("live_model_execution_enabled") is not False:
        raise NextStudyDesignError("next-study live model execution must remain disabled")
    if design.get("retained_execution_enabled") is not False:
        raise NextStudyDesignError("next-study retained execution must remain disabled")
    gates = design.get("execution_gates")
    if not isinstance(gates, dict) or set(gates) != _EXECUTION_GATES:
        raise NextStudyDesignError("next-study execution-gate set drifted")
    if any(value is not False for value in gates.values()):
        raise NextStudyDesignError("every next-study execution gate must begin closed")

    predecessor = design.get("predecessor", {})
    bound_paths = (
        ("runtime_decision_path", "runtime_decision_sha256"),
        ("floor_ceiling_audit_path", "floor_ceiling_audit_sha256"),
    )
    for path_key, digest_key in bound_paths:
        path = ROOT / predecessor.get(path_key, "")
        if not path.is_file() or _sha256(path) != predecessor.get(digest_key):
            raise NextStudyDesignError("predecessor binding failed for %s" % path_key)
    postmortem_path = ROOT / predecessor.get("postmortem_path", "")
    if not postmortem_path.is_file():
        raise NextStudyDesignError("tracked direction-blind postmortem is missing")
    protocol_path = ROOT / predecessor.get("s7_protocol_path", "")
    if (
        not protocol_path.is_file()
        or s7_protocol_sha256(load_protocol(protocol_path))
        != predecessor.get("s7_protocol_sha256")
    ):
        raise NextStudyDesignError("predecessor binding failed for s7_protocol_path")
    postmortem_bytes = canonical_json_bytes(build_postmortem(), newline=True)
    postmortem_sha256 = hashlib.sha256(postmortem_bytes).hexdigest()
    if (
        postmortem_sha256 != predecessor.get("postmortem_sha256")
        or _sha256(postmortem_path) != postmortem_sha256
        or postmortem_path.read_bytes() != postmortem_bytes
    ):
        raise NextStudyDesignError("direction-blind postmortem digest drifted")

    fresh = design.get("fresh_suite", {})
    per_family = sum(
        fresh.get(key, -1000000)
        for key in (
            "development_cases_per_family",
            "calibration_cases_per_family",
            "validation_cases_per_family",
            "sentinel_cases_per_family",
            "retained_cases_per_family",
            "adversarial_cases_per_family",
        )
    )
    if fresh.get("families") != 11 or fresh.get("total_cases") != 11 * per_family:
        raise NextStudyDesignError("fresh-suite counts do not reconcile")
    if fresh.get("generator_version") != "office-generators/2.0.0":
        raise NextStudyDesignError("unexpected fresh generator version")
    if fresh.get("generator_version") != fresh.get("seed_namespace"):
        raise NextStudyDesignError("fresh generator and seed namespaces differ")
    if fresh.get("generator_version") == predecessor.get(
        "retired_generator_version"
    ):
        raise NextStudyDesignError("next study reuses the retired generator namespace")

    calibration = design.get("calibration", {})
    if calibration.get("cases_per_family") != fresh.get(
        "calibration_cases_per_family"
    ):
        raise NextStudyDesignError("calibration allocation differs from fresh suite")
    if calibration.get("conditions") != _CONDITIONS:
        raise NextStudyDesignError("calibration conditions drifted")
    if calibration.get("independent_trials_per_cell") != 2:
        raise NextStudyDesignError("calibration repeat count drifted")
    expected = (
        fresh["families"]
        * calibration.get("cases_per_family", 0)
        * len(calibration.get("conditions", []))
        * calibration.get("independent_trials_per_cell", 0)
    )
    if calibration.get("model_attempts") != expected:
        raise NextStudyDesignError("calibration attempt count does not reconcile")
    if calibration.get("combined_outcomes_per_family") != (
        calibration["cases_per_family"]
        * len(calibration["conditions"])
        * calibration["independent_trials_per_cell"]
    ):
        raise NextStudyDesignError("calibration family denominator is inconsistent")
    if calibration.get("direction_blind") is not True:
        raise NextStudyDesignError("calibration must remain direction blind")
    minimum = calibration.get("acceptable_combined_successes_minimum")
    maximum = calibration.get("acceptable_combined_successes_maximum")
    if not (minimum == 10 and maximum == 22 and 0 <= minimum <= maximum <= 32):
        raise NextStudyDesignError("calibration acceptance band drifted")
    if calibration.get("outcome_granularity_percentage_points") != "3.125":
        raise NextStudyDesignError("calibration outcome granularity drifted")
    if (
        calibration.get(
            "task_shape_selection_may_use_only_direction_blind_development_and_calibration_aggregates"
        )
        is not True
    ):
        raise NextStudyDesignError("calibration selection masking weakened")

    primary = design.get("primary_design", {})
    trial_factor = len(primary.get("conditions", [])) * primary.get(
        "independent_trials_per_cell", 0
    )
    options = primary.get("cases_per_family_options", [])
    if options != [12, 20]:
        raise NextStudyDesignError("primary case-count options drifted")
    if primary.get("minimum_model_attempts") != 11 * options[0] * trial_factor:
        raise NextStudyDesignError("minimum primary attempt count is inconsistent")
    if primary.get("maximum_model_attempts") != 11 * options[1] * trial_factor:
        raise NextStudyDesignError("maximum primary attempt count is inconsistent")
    if primary.get("conditions") != _CONDITIONS:
        raise NextStudyDesignError("primary conditions drifted")
    if primary.get("independent_trials_per_cell") != 2:
        raise NextStudyDesignError("primary repeat count drifted")
    if primary.get("paired_seed_across_conditions") is not True:
        raise NextStudyDesignError("primary paired-seed control weakened")

    sentinel = design.get("sentinel", {})
    expected_sentinel_cells = (
        fresh["families"]
        * fresh["sentinel_cases_per_family"]
        * len(_CONDITIONS)
        * sentinel.get("trials_per_cell", 0)
    )
    if sentinel.get("cases_per_family") != fresh["sentinel_cases_per_family"]:
        raise NextStudyDesignError("sentinel allocation differs from fresh suite")
    if sentinel.get("trials_per_cell") != 1:
        raise NextStudyDesignError("sentinel trial count drifted")
    if sentinel.get("primary_condition_cells") != expected_sentinel_cells:
        raise NextStudyDesignError("sentinel condition-cell count is inconsistent")
    if sentinel.get("instrument_invalid_cells_allowed") != 0:
        raise NextStudyDesignError("sentinel invalid-cell gate weakened")
    if sentinel.get("zero_failure_one_sided_95_upper_bound") != (
        "0.03346948891663748"
    ):
        raise NextStudyDesignError("sentinel bound drifted")

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
