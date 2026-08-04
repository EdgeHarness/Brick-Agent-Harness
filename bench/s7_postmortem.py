"""Build the terminal, direction-blind S7 postmortem.

This module consumes only the tracked runtime decision, the tracked
direction-blind floor/ceiling audit, and the public development manifest.  It
never opens raw D0 attempts and cannot compute a condition contrast.
"""

from collections import Counter
import hashlib
from pathlib import Path

from domains.office_demo.generators import FAMILIES
from harness.evidence import canonical_json_bytes
from harness.instances import load_canonical_json, validate_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / "bench" / "manifests" / "office-v1"
DECISION = ROOT / "evidence" / "s7" / "d0b-runtime-decision.json"
AUDIT = ROOT / "evidence" / "s7" / "d0b-floor-ceiling-audit.json"
GRADER_MUTATION_AUDIT = (
    ROOT / "evidence" / "s7" / "office-v1-grader-mutation-audit.json"
)

EXPECTED_DECISION_SHA256 = (
    "d46e07476040bc3833a314ae2f382c49525496b1afec2f706a4b3fd54c4d670f"
)
EXPECTED_AUDIT_SHA256 = (
    "361132449a778d3906b6a095c1c89ea2df2e69f23ca5c2bcb184c42cc4ef2337"
)
EXPECTED_GRADER_MUTATION_AUDIT_SHA256 = (
    "30e99c6d1d82e5520ce42202847e0a38fdc2c0539a5e69f9b3d9a186d112ac49"
)

_EMAIL_SOURCES = frozenset({"source_read", "sources_read"})
_MUTATIONS = frozenset(
    {
        "presentation_created",
        "spreadsheet_created",
        "email_sent",
        "event_created",
        "message_sent",
        "reminder_created",
        "memory_saved",
    }
)


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def minimum_action_profile(content):
    """Return a conservative lower bound on required model-facing tool calls."""

    effects = content["required_effects"]
    email_effects = [item for item in effects if item["type"] in _EMAIL_SOURCES]
    discovery = 1 if email_effects else 0
    reads = 0
    for effect in email_effects:
        reads += 1 if effect["type"] == "source_read" else len(effect["ids"])
    calendar_reads = sum(
        effect["type"] == "calendar_read" for effect in effects
    )
    mutations = sum(effect["type"] in _MUTATIONS for effect in effects)
    return {
        "discovery_calls": discovery,
        "source_read_calls": reads + calendar_reads,
        "mutating_calls": mutations,
        "minimum_agent_tool_calls": (
            discovery + reads + calendar_reads + mutations
        ),
    }


def _require_terminal_inputs(decision, audit):
    if _sha256(DECISION) != EXPECTED_DECISION_SHA256:
        raise RuntimeError("tracked D0-B runtime decision digest drifted")
    if _sha256(AUDIT) != EXPECTED_AUDIT_SHA256:
        raise RuntimeError("tracked D0-B direction-blind audit digest drifted")
    if _sha256(GRADER_MUTATION_AUDIT) != EXPECTED_GRADER_MUTATION_AUDIT_SHA256:
        raise RuntimeError(
            "tracked retired-suite grader mutation audit digest drifted"
        )
    if decision.get("efficacy_fields_read") is not False:
        raise RuntimeError("runtime decision is not efficacy blind")
    if audit.get("condition_scores_emitted") is not False:
        raise RuntimeError("audit emitted condition scores")
    if audit.get("directional_effects_computed") is not False:
        raise RuntimeError("audit computed directional effects")
    if audit.get("protocol_freeze_allowed") is not False:
        raise RuntimeError("terminal audit unexpectedly permits a freeze")
    if audit.get("runtime_decision_sha256") != EXPECTED_DECISION_SHA256:
        raise RuntimeError("audit does not bind the tracked runtime decision")


def build_postmortem():
    decision = load_canonical_json(DECISION)
    audit = load_canonical_json(AUDIT)
    _require_terminal_inputs(decision, audit)

    development = load_canonical_json(MANIFESTS / "development.json")
    validate_manifest(development)
    d0b = [
        item
        for item in development["instances"]
        if item["content"]["id"].startswith("development.d0b.")
    ]
    if len(d0b) != 44:
        raise RuntimeError("D0-B manifest projection is not exactly 44 cases")
    total_records = audit["family_combined_totals"]
    if len(total_records) != len(FAMILIES):
        raise RuntimeError(
            "direction-blind audit does not contain 11 family totals"
        )
    totals = {item["family"]: item for item in total_records}
    if set(totals) != set(FAMILIES) or len(totals) != len(total_records):
        raise RuntimeError(
            "direction-blind audit family totals are missing or duplicated"
        )
    if sum(item["combined_outcomes"] for item in total_records) != 88:
        raise RuntimeError("direction-blind audit does not contain 88 outcomes")
    flags = {item["family"]: item["flag"] for item in audit["flags"]}

    families = []
    for family in FAMILIES:
        cases = sorted(
            (
                item["content"]
                for item in d0b
                if item["content"]["family"] == family
            ),
            key=lambda item: item["id"],
        )
        if len(cases) != 4:
            raise RuntimeError("D0-B family %s is not exactly four cases" % family)
        profiles = [minimum_action_profile(item) for item in cases]
        structures = [item["structure"] for item in cases]
        marginals = {
            "workload_values": sorted(item["workload"] for item in structures),
            "distractor_count_values": sorted(
                item["distractor_count"] for item in structures
            ),
            "constraint_profile_counts": dict(
                sorted(
                    Counter(
                        item["constraint_profile"] for item in structures
                    ).items()
                )
            ),
        }
        if marginals != {
            "workload_values": [3, 4, 5, 6],
            "distractor_count_values": [0, 1, 2, 3],
            "constraint_profile_counts": {
                "exact_order": 2,
                "selection_rule": 2,
            },
        }:
            raise RuntimeError("D0-B structural marginals drifted for %s" % family)
        families.append(
            {
                "family": family,
                "case_count": 4,
                "combined_successes": totals[family]["combined_successes"],
                "combined_outcomes": totals[family]["combined_outcomes"],
                "floor_ceiling_flag": flags.get(family, "none"),
                "minimum_agent_tool_calls": sorted(
                    item["minimum_agent_tool_calls"] for item in profiles
                ),
                "minimum_source_read_calls": sorted(
                    item["source_read_calls"] for item in profiles
                ),
                "minimum_mutating_calls": sorted(
                    item["mutating_calls"] for item in profiles
                ),
            }
        )

    return {
        "schema_version": "brick.s7.direction-blind-postmortem/1",
        "run_id": audit["run_id"],
        "runtime_decision_sha256": EXPECTED_DECISION_SHA256,
        "floor_ceiling_audit_sha256": EXPECTED_AUDIT_SHA256,
        "condition_scores_read": False,
        "directional_effects_computed": False,
        "raw_attempt_evidence_read": False,
        "current_study_terminal": True,
        "next_study_execution_allowed": False,
        "selected_cases_per_family": decision["selected_cases_per_family"],
        "d0b_structural_marginals_per_family": {
            "workload_values": [3, 4, 5, 6],
            "distractor_count_values": [0, 1, 2, 3],
            "constraint_profile_counts": {
                "exact_order": 2,
                "selection_rule": 2,
            },
        },
        "families": families,
        "resolved_controls": [
            {
                "id": "retired_suite_generated_grader_mutation_matrix",
                "status": "resolved_for_retired_suite_only",
                "evidence_path": "evidence/s7/office-v1-grader-mutation-audit.json",
                "evidence_sha256": EXPECTED_GRADER_MUTATION_AUDIT_SHA256,
                "case_count": 352,
                "applicable_named_check_probes": 1984,
                "live_model_calls": 0,
            }
        ],
        "verified_blockers": [
            {
                "id": "terminal_floor_ceiling_gate",
                "severity": "critical",
                "evidence": (
                    "three ceiling flags and one floor flag; "
                    "protocol_freeze_allowed=false"
                ),
                "required_control": (
                    "retire protocol 1.0.2 without D0-C, S8, or retained "
                    "execution"
                ),
            },
            {
                "id": "difficulty_not_action_normalized",
                "severity": "critical",
                "evidence": (
                    "matched structural marginals coexist with family-specific "
                    "1-to-8-call lower bounds"
                ),
                "required_control": (
                    "generate and balance explicit observation, mutation, and "
                    "artifact-complexity axes"
                ),
            },
            {
                "id": "coarse_family_calibration",
                "severity": "high",
                "evidence": (
                    "eight combined binary outcomes give 12.5-percentage-point "
                    "resolution per family"
                ),
                "required_control": (
                    "use a larger disjoint direction-blind calibration cohort "
                    "with repeated trials"
                ),
            },
            {
                "id": "correlated_oracle_and_grader",
                "severity": "critical",
                "evidence": (
                    "rules_reference.py and generated_grader.py both compile "
                    "content.required_effects"
                ),
                "required_control": (
                    "add an independently implemented prompt-to-outcome oracle "
                    "and human review ledger"
                ),
            },
            {
                "id": "single_trial_stochasticity",
                "severity": "critical",
                "evidence": (
                    "the frozen primary specifies one stochastic trajectory per "
                    "retained cell at temperature 1.0"
                ),
                "required_control": (
                    "freeze repeated independent trials and a cluster-aware "
                    "paired analysis before execution"
                ),
            },
            {
                "id": "weak_sentinel_detection_power",
                "severity": "high",
                "evidence": (
                    "one sentinel case per family yields only 22 "
                    "primary-condition cells"
                ),
                "required_control": (
                    "increase disjoint sentinel coverage and predeclare an "
                    "instrument-failure bound"
                ),
            },
        ],
    }


def main():
    print(canonical_json_bytes(build_postmortem(), newline=True).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
