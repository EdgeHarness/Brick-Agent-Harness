"""Fail-closed contract for the strengthened post-S7 successor program."""

import hashlib
from pathlib import Path

from bench.next_study_schedule import verify_descriptive_selection
from bench.next_study_statistics import load_protocol
from bench.next_study_claim import load_claim_contract
from bench.next_study_construct import load_contract as load_construct_contract
from bench.next_study_construct_failure import load_failure
from bench.next_study_fable_reconciliation import load_reconciliation
from bench.next_study_validated_outcomes import validate_validated_outcomes
from bench.s7_contract import load_protocol as load_s7_protocol
from bench.s7_contract import s7_protocol_sha256
from bench.s7_postmortem import build_postmortem
from harness.evidence import canonical_json_bytes
from harness.instances import load_canonical_json, replace_canonical_json


ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = ROOT / "bench" / "next_study_design.json"

_PREDECESSOR = {
    "floor_ceiling_audit_path": "evidence/s7/d0b-floor-ceiling-audit.json",
    "floor_ceiling_audit_sha256": "361132449a778d3906b6a095c1c89ea2df2e69f23ca5c2bcb184c42cc4ef2337",
    "postmortem_path": "evidence/s7/d0b-direction-blind-postmortem.json",
    "postmortem_sha256": "9b5b0f87340877b0fdcaada3ca2a4a40fc6bc557407debeed9b01f20cfe23805",
    "retired_generator_version": "office-generators/1.1.0",
    "run_id": "s7-d0b-20260804T025010Z",
    "runtime_decision_path": "evidence/s7/d0b-runtime-decision.json",
    "runtime_decision_sha256": "d46e07476040bc3833a314ae2f382c49525496b1afec2f706a4b3fd54c4d670f",
    "s7_protocol_path": "bench/s7_protocol.json",
    "s7_protocol_sha256": "c4a409144f197d3b43e70d27b50b764cade3ecca4c236a01937dfc440218249d",
}

_ARTIFACT_PATHS = {
    "retired_2_0_1": "evidence/next-study/office-v2.0.1-retirement.json",
    "invalidated_v0_13_0": "evidence/next-study/v0.13.0-invalidation.json",
    "pre_outcome_amendment": "evidence/next-study/office-v2.1.2-pre-outcome-amendment.json",
    "manifest_lock": "bench/manifests/office-v2/manifest-lock.json",
    "generator_implementation": "domains/office_demo/generators_v2.py",
    "oracle_audit": "evidence/next-study/office-v2-oracle-audit.json",
    "validated_outcomes": "evidence/next-study/office-v2-validated-outcomes.json",
    "validated_outcomes_implementation": "bench/next_study_validated_outcomes.py",
    "outcome_compiler": "domains/office_demo/outcome_oracle_v2.py",
    "claim_contract": "bench/next_study_claim_contract.json",
    "claim_implementation": "bench/next_study_claim.py",
    "construct_contract": "bench/next_study_construct_contract.json",
    "construct_implementation": "bench/next_study_construct.py",
    "semantic_simulation": "evidence/next-study/office-v2-semantic-simulation.json",
    "semantic_implementation": "bench/next_study_semantic_simulation.py",
    "semantic_rendered_report": "evidence/next-study/semantic-validation-report/artifact.json",
    "rehearsal": "evidence/next-study/office-v2-model-free-rehearsal.json",
    "rehearsal_implementation": "bench/next_study_rehearsal.py",
    "report_implementation": "bench/next_study_report.py",
    "protocol": "bench/next_study_protocol.json",
    "statistics_implementation": "bench/next_study_statistics.py",
    "descriptive_selection": "bench/next_study_descriptive_selection.json",
    "descriptive_implementation": "bench/next_study_descriptive.py",
    "schedule_implementation": "bench/next_study_schedule.py",
    "grader_implementation": "domains/office_demo/reviewed_grader_v2.py",
    "grader_audit_implementation": "bench/next_study_grader_audit.py",
    "grader_machine_conformance": "evidence/next-study/office-v2-grader-machine-conformance.json",
    "program_implementation": "bench/next_study_program.py",
    "runtime_implementation": "bench/next_study_runtime.py",
    "readiness_implementation": "bench/next_study_readiness.py",
    "live_implementation": "bench/next_study_live.py",
    "fable_reconciliation": "evidence/next-study/office-v2-fable-reconciliation.json",
    "fable_reconciliation_implementation": "bench/next_study_fable_reconciliation.py",
    "fable_reconciliation_builder": "bench/reconcile_next_study_reports.py",
    "construct_gate_failure": "evidence/next-study/office-v2.1.2-construct-gate-failure.json",
    "construct_gate_failure_implementation": "bench/next_study_construct_failure.py",
}

_EXPECTED_GATES = {
    "calibration_protocol_frozen": True,
    "condition_aware_burden_complete": True,
    "construct_contract_complete": True,
    "descriptive_selection_frozen": True,
    "fresh_generator_complete": True,
    "grader_mutation_matrix_complete": True,
    "grader_mutation_harness_complete": True,
    "grader_machine_conformance_complete": True,
    "independent_grader_implementation_complete": True,
    "independent_oracle_complete": True,
    "independent_validated_outcomes_complete": True,
    "live_execution_authorized": False,
    "linux_ci_reproduction_complete": False,
    "native_windows_clean_checkout_complete": False,
    "power_and_cluster_analysis_frozen": True,
    "semantic_internal_validity_complete": False,
    "development_shakeout_complete": False,
    "scheduler_implementation_complete": True,
    "evidence_derived_attempt_extractor_complete": True,
    "authorization_readiness_implementation_complete": True,
    "descriptive_post_primary_gate_complete": True,
    "sentinel_protocol_frozen": True,
    "split_leakage_audit_complete": True,
}


class NextStudyDesignError(ValueError):
    pass


def _sha256(path):
    path = Path(path)
    payload = path.read_bytes()
    if path.suffix.lower() in {".csv", ".json", ".md", ".py", ".txt"}:
        try:
            payload = payload.decode("utf-8").replace("\r\n", "\n").encode("utf-8")
        except UnicodeDecodeError:
            pass
    return hashlib.sha256(payload).hexdigest()


def _artifact_bindings():
    result = {}
    for name, relative_path in sorted(_ARTIFACT_PATHS.items()):
        path = ROOT / relative_path
        if not path.is_file():
            raise NextStudyDesignError("missing successor artifact %s" % relative_path)
        result["%s_path" % name] = relative_path
        result["%s_sha256" % name] = _sha256(path)
    return result


def build_design():
    return {
        "schema_version": "brick.next-study.design/5",
        "version": "0.8.2",
        "status": "construct_gate_failed",
        "release_sequence": {
            "v0.12.0": "permanently_unissued_terminal_s7",
            "v0.13.0": "invalidated_successor_candidate",
            "v0.13.1": "replacement_instrument_target",
            "v0.14.0": "completed_study_target",
            "v0.15.0": "isolated_product_demo_target",
        },
        "live_model_execution_enabled": False,
        "retained_execution_enabled": False,
        "execution_gates": dict(_EXPECTED_GATES),
        "predecessor": dict(_PREDECESSOR),
        "fresh_suite": {
            "generator_version": "office-generators/2.1.2",
            "seed_namespace": "office-generators/2.1.0",
            "families": 11,
            "development_cases_per_family": 8,
            "calibration_cases_per_family": 8,
            "validation_cases_per_family": 4,
            "sentinel_cases_per_family": 4,
            "retained_cases_per_family": 20,
            "adversarial_cases_per_family": 4,
            "total_cases": 528,
            "model_and_reviewer_visible_split_leakage": 0,
        },
        "calibration": {
            "cases_per_family": 8,
            "conditions": ["native_tools", "harness_full"],
            "independent_trials_per_cell": 2,
            "model_attempts": 352,
            "combined_outcomes_per_family": 32,
            "direction_blind": True,
            "acceptable_combined_successes_minimum": 10,
            "acceptable_combined_successes_maximum": 22,
            "outcome_granularity_percentage_points": "3.125",
            "any_family_outside_band_retires_complete_generator_version": True,
        },
        "primary_design": {
            "cases_per_family": 20,
            "instance_clusters": 220,
            "conditions": ["native_tools", "harness_full"],
            "independent_trials_per_cell": 2,
            "model_attempts": 880,
            "paired_seed_across_conditions": True,
            "minimum_relevant_absolute_effect": "0.12",
            "planning_power_is_conditional": True,
            "normal_approximation_power": "0.828074238908",
            "leave_one_family_out_descriptive_records": 11,
            "every_instance_order_reversed_on_trial_one": True,
        },
        "sentinel": {
            "cases_per_family": 4,
            "trials_per_cell": 1,
            "primary_condition_cells": 88,
            "instrument_invalid_cells_allowed": 0,
            "zero_failure_one_sided_95_upper_bound": "0.03346948891663748",
            "bound_is_diagnostic_not_efficacy_claim": True,
        },
        "descriptive_matrix": {
            "selected_retained_cases": 22,
            "maximum_logical_cells": 222,
            "runs_only_after_sealed_primary_analysis": True,
            "may_alter_primary_claim": False,
            "sealed_primary_eligibility_required": True,
            "paired_descriptive_differences_required": True,
        },
        "program": {
            "maximum_logical_cells": 1542,
            "maximum_physical_attempts": 3084,
            "same_seed_environment_retry_limit": 1,
            "auto_advance_on_sealed_pass": True,
            "machine_wide_benchmark_lease_required": True,
            "external_plugin_discovery_in_research": False,
            "attempt_records_derived_from_marker_last_evidence": True,
            "authorization_artifact_exact_key_validation": True,
            "github_actions_linux_matrix_required": True,
            "authorization_refetches_linux_ci_evidence": True,
        },
        "advisory_human_review": {
            "authorization_gate": False,
            "may_change_or_supply_validated_outcomes": False,
            "supports_real_world_performance_claim": False,
            "status": "out_of_scope_not_bound_to_authorization",
            "legacy_packet_material_may_be_retained": True,
        },
        "successor_artifacts": _artifact_bindings(),
    }


def _validate_predecessor(design):
    predecessor = design["predecessor"]
    for path_name in (
        "runtime_decision", "floor_ceiling_audit", "postmortem",
    ):
        path = ROOT / predecessor["%s_path" % path_name]
        if not path.is_file() or _sha256(path) != predecessor["%s_sha256" % path_name]:
            raise NextStudyDesignError("predecessor artifact binding drifted")
    s7_path = ROOT / predecessor["s7_protocol_path"]
    if s7_protocol_sha256(load_s7_protocol(s7_path)) != predecessor["s7_protocol_sha256"]:
        raise NextStudyDesignError("S7 protocol binding drifted")
    postmortem = canonical_json_bytes(build_postmortem(), newline=True)
    if hashlib.sha256(postmortem).hexdigest() != predecessor["postmortem_sha256"]:
        raise NextStudyDesignError("S7 postmortem replay drifted")


def _validate_successor_semantics():
    retired = load_canonical_json(ROOT / _ARTIFACT_PATHS["retired_2_0_1"])
    if (
        retired.get("generator_version") != "office-generators/2.0.1"
        or retired.get("status") != "permanently_retired"
        or retired.get("execution_enabled") is not False
        or retired.get("packet_export_enabled") is not False
    ):
        raise NextStudyDesignError("2.0.1 retirement evidence drifted")
    invalidated = load_canonical_json(
        ROOT / _ARTIFACT_PATHS["invalidated_v0_13_0"]
    )
    if (
        invalidated.get("tag") != "v0.13.0"
        or invalidated.get("status") != "invalidated_before_calibration"
        or invalidated.get("execution_allowed") is not False
        or invalidated.get("replacement_instrument_tag") != "v0.13.1"
        or invalidated.get("replacement_candidate")
        != "office-generators/2.1.1"
        or invalidated.get("replacement_seed_namespace")
        != "office-generators/2.1.0"
    ):
        raise NextStudyDesignError("v0.13.0 invalidation evidence drifted")
    amendment = load_canonical_json(
        ROOT / _ARTIFACT_PATHS["pre_outcome_amendment"]
    )
    if amendment != {
        "schema_version": "brick.next-study.pre-outcome-amendment/1",
        "status": "authorized_narrow_semantic_remediation",
        "from_generator_version": "office-generators/2.1.1",
        "to_generator_version": "office-generators/2.1.2",
        "seed_namespace": "office-generators/2.1.0",
        "oracle_version": "office-prompt-oracle/2.1.0",
        "grader_version": "office-strict-grader/3.2.0",
        "target_instrument_tag": "v0.13.1",
        "live_study_cells_run": 0,
        "no_effectiveness_data_inspected": True,
        "source_audit_commit": "a50ed8bc1a4c0fc941d3c6c27da8b39b406c3e03",
        "source_audit_files": [
            {
                "path": "docs/office-v2-prompt-audit.md",
                "canonical_text_sha256": "da99b198916b786255f20f490a67597ed2a79eb4183cb687a73c9ea6a8ae7d39",
            },
            {
                "path": "docs/office-v2-prompt-audit-responses.csv",
                "canonical_text_sha256": "38e01b8098ab246262760caaa22b8488bde4e7fe9af11aec96633839f8c5260c",
            },
            {
                "path": "docs/office-v2-prompt-audit-runbook.md",
                "canonical_text_sha256": "ec0f6235a53c4c1ec863d564c4fef1b4d535a3b24a3cbdad95ed604ff3fade9c",
            },
            {
                "path": "docs/office-v2-audit-append.py",
                "canonical_text_sha256": "655d70ba8306d8db52a02d2ff9406cdd1a1adb121e3ba71aab23abbd5a8502ae",
            },
        ],
        "approved_changes": [
            "clarify_xlsx_from_email_amount_cents_to_usd_dollars",
            "define_cal_freeslot_email_reply_and_multi_offsite_policy_precedence",
            "make_remind_msg_dependencies_due_date_coherent_and_grade_exact_identifier_sequences",
            "pin_cal_brief_entry_format_and_retain_exclusion_enforcement",
        ],
        "next_failure_disposition": "construct_gate_failed_no_2.1.3",
    }:
        raise NextStudyDesignError("2.1.2 pre-outcome amendment drifted")
    for source in amendment["source_audit_files"]:
        source_path = ROOT / source["path"]
        if (
            not source_path.is_file()
            or _sha256(source_path) != source["canonical_text_sha256"]
        ):
            raise NextStudyDesignError(
                "2.1.2 source audit binding drifted: %s" % source["path"]
            )
    lock = load_canonical_json(ROOT / _ARTIFACT_PATHS["manifest_lock"])
    if (
        lock.get("generator_version") != "office-generators/2.1.2"
        or sum(item["instances"] for item in lock.get("manifests", [])) != 528
        or lock.get("split_leakage_review", {}).get("finding_count") != 0
        or lock.get("split_leakage_review", {}).get("passed") is not True
        or lock.get("balance_review", {}).get("maximum_expected_native_requests") != 9
        or lock.get("balance_review", {}).get("maximum_expected_harness_requests") != 12
        or lock.get("balance_review", {}).get("matched_policy_triplets") != 176
        or lock.get("balance_review", {}).get("normalized_two_x_headroom_claimed") is not False
    ):
        raise NextStudyDesignError("successor generator audits are incomplete")
    audit = load_canonical_json(ROOT / _ARTIFACT_PATHS["oracle_audit"])
    if (
        audit.get("generator_version") != "office-generators/2.1.2"
        or audit.get("case_count") != 528 or audit.get("all_exact_matches") is not True
        or audit.get("live_model_calls") != 0
    ):
        raise NextStudyDesignError("successor oracle audit is incomplete")
    manifests = [
        load_canonical_json(ROOT / "bench" / "manifests" / "office-v2" / (split + ".json"))
        for split in (
            "development", "calibration", "validation", "sentinel",
            "retained", "adversarial",
        )
    ]
    validate_validated_outcomes(
        load_canonical_json(ROOT / _ARTIFACT_PATHS["validated_outcomes"]),
        manifests,
    )
    load_claim_contract(ROOT / _ARTIFACT_PATHS["claim_contract"])
    load_construct_contract(ROOT / _ARTIFACT_PATHS["construct_contract"])
    semantic = load_canonical_json(ROOT / _ARTIFACT_PATHS["semantic_simulation"])
    if (
        semantic.get("status") != "passed"
        or semantic.get("scope", {}).get("case_count") != 528
        or semantic.get("simulation", {}).get("typed_positive_workflows_strict_successes") != 1056
        or semantic.get("finding_severity_counts", {}).get("critical", 0) != 0
        or semantic.get("finding_severity_counts", {}).get("high", 0) != 0
        or semantic.get("finding_severity_counts", {}).get("medium", 0) != 0
        or semantic.get("assessment", {}).get("confirmatory_execution_recommended") is not True
    ):
        raise NextStudyDesignError("semantic internal-validity gate is incomplete")
    rendered = load_canonical_json(
        ROOT / _ARTIFACT_PATHS["semantic_rendered_report"]
    )
    try:
        summary = rendered["snapshot"]["datasets"]["summary"]
        profiles = rendered["snapshot"]["datasets"]["profile_sensitivity"]
        findings = rendered["snapshot"]["datasets"]["findings"]
        source = next(
            item for item in rendered["sources"]
            if item.get("id") == "semantic_simulation"
        )
    except (KeyError, StopIteration, TypeError):
        raise NextStudyDesignError("semantic rendered report is incomplete")
    if (
        rendered.get("surface") != "report"
        or rendered.get("snapshot", {}).get("status") != "ready"
        or summary != [{
            "typed_workflows": 1056,
            "high_findings": 0,
            "memory_failures": 0,
            "nominal_families": 0,
            "families_total": 11,
        }]
        or len(profiles) != 11
        or any(
            item.get("decision_sensitive_cells") != 16
            or item.get("matched_cells") != 16
            or item.get("classification") != "decision-rule sensitive"
            for item in profiles
        )
        or findings != []
        or source.get("path")
        != "evidence/next-study/office-v2-semantic-simulation.json"
        or "office-generators/2.1.2"
        not in rendered.get("manifest", {}).get("description", "")
    ):
        raise NextStudyDesignError("semantic rendered report drifted")
    rehearsal = load_canonical_json(ROOT / _ARTIFACT_PATHS["rehearsal"])
    if (
        rehearsal.get("status") != "passed"
        or rehearsal.get("execution_context", {}).get("value") != "synthetic_rehearsal"
        or rehearsal.get("descriptive_cells") != 222
        or rehearsal.get("git_tags_created") != 0
        or rehearsal.get("live_model_calls") != 0
        or not all(rehearsal.get("release_rejections", {}).values())
    ):
        raise NextStudyDesignError("model-free rehearsal is incomplete")
    machine = load_canonical_json(ROOT / _ARTIFACT_PATHS["grader_machine_conformance"])
    machine_marker = Path(
        str(ROOT / _ARTIFACT_PATHS["grader_machine_conformance"]) + ".complete"
    )
    if (
        not machine_marker.is_file() or machine_marker.read_bytes() != b""
        or
        machine.get("schema_version")
        != "brick.next-study.grader-validated-conformance/1"
        or machine.get("case_count") != 528
        or machine.get("positive_baselines") != 528
        or machine.get("targeted_mutations") != 4332
        or machine.get("benign_non_rejection_controls") != 1872
        or machine.get("semantic_probe_counts") != {
            "extra_identifier": 96,
            "forbidden_date": 48,
            "forbidden_mention": 36,
            "memory_exactness": 48,
            "missing_exact_deadline": 48,
            "negated_deadline": 48,
            "negated_email": 96,
            "presentation_fact": 648,
            "presentation_order": 48,
            "reformatted_email_field": 48,
            "source_list": 192,
        }
        or machine.get("passed") is not True
        or machine.get("may_satisfy_human_ground_truth_gate") is not False
        or machine.get("live_model_calls") != 0
    ):
        raise NextStudyDesignError("full-suite machine conformance is incomplete")
    protocol = load_protocol(ROOT / _ARTIFACT_PATHS["protocol"])
    if protocol["version"] != "1.4.0":
        raise NextStudyDesignError("successor protocol version drifted")
    verify_descriptive_selection()
    load_reconciliation(
        ROOT / _ARTIFACT_PATHS["fable_reconciliation"],
        require_complete=False,
    )
    load_failure(ROOT / _ARTIFACT_PATHS["construct_gate_failure"])


def validate_design(design):
    if design != build_design():
        raise NextStudyDesignError("next-study design or artifact binding drifted")
    _validate_predecessor(design)
    _validate_successor_semantics()
    return design


def load_design(path=DESIGN_PATH):
    return validate_design(load_canonical_json(path))


def write_design(path=DESIGN_PATH):
    document = build_design()
    replace_canonical_json(path, document)
    return document


def execution_allowed(design=None):
    validate_design(load_design() if design is None else design)
    return False


__all__ = [
    "DESIGN_PATH", "NextStudyDesignError", "build_design", "execution_allowed",
    "load_design", "validate_design", "write_design",
]
