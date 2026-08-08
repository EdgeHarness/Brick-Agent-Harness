"""Focused, deadline-bound follow-up comparison for the frozen v0.13.3 suite.

This module deliberately has no model-facing implementation of its own.  It
builds a separately versioned schedule and authorization, then reuses the
already-qualified v0.13.3 producer, transport, and marker-last evidence store.
It is an exploratory follow-up after the original 11-family calibration gate
retired the complete successor program; it must never be passed to the
production v0.14.0 release verifier.

The public CLI deliberately prints only progress and score-free seal status
until ``analyze`` is invoked after a complete block is sealed.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as _datetime
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

from domains.office_demo.generators_v2 import FAMILIES, GENERATOR_VERSION
from domains.office_demo.generators_v2 import validate_office_instance_v2
from harness.evidence import AttemptKey, EvidenceStore, canonical_json_bytes, validate_committed
from harness.experiment import OllamaTransport, validate_protocol as validate_execution_protocol
from harness.instances import load_canonical_json, sha256_bytes, validate_manifest

from . import next_study_live as _live
from .next_study_runtime import _resource_metrics, extract_attempt_records
from .next_study_program import (
    BenchmarkLease,
    validate_authorization as _validate_base_program_authorization,
)
from .next_study_schedule import (
    validate_development_shakeout_schedule,
    validate_phase_schedule,
)
from .next_study_runtime import resume_queue as _base_resume_queue
from .next_study_validated_outcomes import (
    DEFAULT_PATH as VALIDATED_OUTCOMES_PATH,
    load_manifests,
    validate_validated_outcomes,
)


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "bench" / "focused_followup_protocol.json"
MANIFEST_DIRECTORY = ROOT / "bench" / "manifests" / "office-v2"
BASE_AUTHORIZATION_PATH = (
    ROOT / "results-next-study" / "qualification-v230-r1" / "program-authorization.json"
)
CALIBRATION_ARTIFACT_PATH = (
    ROOT / "results-next-study" / "qualification-v230-r1" / "operations" / "artifacts" / "calibration.json"
)
RECOVERED_CALIBRATION_OUTPUT_PATH = (
    ROOT / "results-next-study" / "qualification-v230-r1" / "operations" / "artifacts"
    / "recovered-calibration-analysis.json"
)
CALIBRATION_SCHEDULE_PATH = (
    ROOT / "results-next-study" / "qualification-v230-r1" / "schedules" / "calibration.json"
)
CALIBRATION_MANIFEST_PATH = MANIFEST_DIRECTORY / "calibration.json"
CALIBRATION_RUNS_ROOT = ROOT / "results-next-study" / "qualification-v230-r1" / "research-runs"
CALIBRATION_RUN_ID = "v133-calibration-fa900f39-r1"
FOCUSED_RUN_ID = "v0134-focused-followup-r1"
FOCUSED_RUNS_ROOT_RELATIVE = "results-next-study/focused-" + FOCUSED_RUN_ID
SHAKEOUT_SCHEDULE_PATH = ROOT / "results-next-study" / "qualification-v230-r1" / "schedules" / "development-shakeout.json"
SHAKEOUT_AUTHORIZATION_PATH = ROOT / "results-next-study" / "qualification-v230-r1" / "shakeout-authorization.json"
SHAKEOUT_DECISION_PATH = ROOT / "results-next-study" / "qualification-v230-r1" / "shakeout-decision.json"
EXPLORATORY_PLAN_PATH = ROOT / "evidence" / "next-study" / "office-v2.3.0-exploratory-analysis-plan.json"

PROTOCOL_SCHEMA = "brick.focused-followup.protocol/1"
SCHEDULE_SCHEMA = "brick.next-study.schedule/1"
AUTHORIZATION_SCHEMA = "brick.focused-followup.authorization/1"
RUN_METADATA_SCHEMA = "brick.focused-followup.run-metadata/1"
ATTEMPT_RECORD_SCHEMA = "brick.focused-followup.attempt-record/1"
RECOVERY_SCHEMA = "brick.focused-followup.recovery-attestation/1"
BLOCK_SEAL_SCHEMA = "brick.focused-followup.block-seal/1"
BLOCK_START_SCHEMA = "brick.focused-followup.block-start/1"
TERMINATION_SCHEMA = "brick.focused-followup.block-termination/1"
ANALYSIS_SCHEMA = "brick.focused-followup.analysis/1"
REPORT_SCHEMA = "brick.focused-followup.study-report/1"
RECOVERED_CALIBRATION_SCHEMA = "brick.focused-followup.recovered-calibration-analysis/1"
EXECUTION_CONTEXT_SCHEMA = "brick.focused-followup.execution-context/1"

BLOCKS = ("B1a", "B1b", "B2")
CONDITIONS = ("native_tools", "harness_full")
NON_CALIBRATION_SPLITS = (
    "development", "validation", "sentinel", "retained", "adversarial",
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SAFE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


class FocusedFollowupError(ValueError):
    """Focused follow-up inputs, evidence, or state are invalid."""


def _digest(value):
    return sha256_bytes(canonical_json_bytes(value, allow_float=False))


def _file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _require_sha256(value, label):
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise FocusedFollowupError("%s must be lowercase SHA-256" % label)
    return value


def _require_sha1(value, label):
    if not isinstance(value, str) or _SHA1.fullmatch(value) is None:
        raise FocusedFollowupError("%s must be lowercase Git SHA-1" % label)
    return value


def _require_component(value, label):
    if not isinstance(value, str) or _SAFE_COMPONENT.fullmatch(value) is None:
        raise FocusedFollowupError("%s is not a safe path component" % label)
    return value


def _timestamp(value, label):
    try:
        parsed = _datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise FocusedFollowupError("%s must be ISO-8601" % label) from exc
    if parsed.utcoffset() is None:
        raise FocusedFollowupError("%s must include a timezone" % label)
    return parsed


def _utcnow():
    return _datetime.datetime.now(_datetime.timezone.utc).isoformat()


def _fraction_text(value):
    value = Fraction(value)
    return "%d/%d" % (value.numerator, value.denominator)


def _decimal_text(value, places=12):
    value = Fraction(value)
    with localcontext() as context:
        context.prec = max(40, places + 16)
        decimal = Decimal(value.numerator) / Decimal(value.denominator)
        return format(decimal, ".%df" % places)


def _normal_text(value):
    """Render a non-authoritative planning float as a canonical decimal string."""

    return format(value, ".12f")


def _git(*args):
    try:
        result = subprocess.run(
            ["git", *args], cwd=str(ROOT), check=True, capture_output=True,
            text=True, timeout=30,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise FocusedFollowupError("Git identity lookup failed") from exc
    return result.stdout.strip()


def _annotated_tag_binding(tag, expected_commit=None):
    if not isinstance(tag, str) or not tag:
        raise FocusedFollowupError("tag is invalid")
    try:
        object_type = _git("cat-file", "-t", "refs/tags/" + tag)
        object_sha = _git("rev-parse", "refs/tags/" + tag)
        commit_sha = _git("rev-parse", "refs/tags/%s^{}" % tag)
    except FocusedFollowupError as exc:
        raise FocusedFollowupError("required annotated tag is missing") from exc
    if object_type != "tag":
        raise FocusedFollowupError("follow-up tag must be annotated")
    _require_sha1(object_sha, "tag object")
    _require_sha1(commit_sha, "tag commit")
    if expected_commit is not None and commit_sha != expected_commit:
        raise FocusedFollowupError("tag does not peel to its bound commit")
    return {"tag": tag, "tag_object_sha": object_sha, "commit_sha": commit_sha}


def load_protocol(path=PROTOCOL_PATH):
    try:
        protocol = load_canonical_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise FocusedFollowupError("focused follow-up protocol is unreadable") from exc
    validate_protocol(protocol)
    return protocol


def validate_protocol(protocol):
    expected = {
        "schema_version", "version", "status", "classification",
        "base_instrument", "selection", "sampling", "blocks", "estimands",
        "claim_rule", "planning", "reporting", "execution",
    }
    if not isinstance(protocol, dict) or set(protocol) != expected:
        raise FocusedFollowupError("focused protocol has unexpected keys")
    if (
        protocol["schema_version"] != PROTOCOL_SCHEMA
        or protocol["version"] != "1.0.0"
        or protocol["status"] != "frozen_before_focused_followup_execution"
        or protocol["classification"] != "prospective_exploratory_fixed_synthetic_benchmark"
    ):
        raise FocusedFollowupError("focused protocol identity drifted")
    base = protocol["base_instrument"]
    if (
        not isinstance(base, dict)
        or set(base) != {"tag", "generator_version", "model_role", "conditions", "opportunity_budget"}
        or base["tag"] != "v0.13.3"
        or base["generator_version"] != GENERATOR_VERSION
        or base["model_role"] != "4b"
        or tuple(base["conditions"]) != CONDITIONS
        or base["opportunity_budget"] != {
            "model_calls": 18, "generated_tokens": 6144,
            "generated_tokens_per_request": 700,
            "shared_across_subepisodes": True,
        }
    ):
        raise FocusedFollowupError("focused base-instrument contract drifted")
    selection = protocol["selection"]
    selection_keys = {
        "criterion", "comparative_calibration_outcomes_known_when_frozen",
        "transparency", "combined_calibration_artifact", "combined_calibration_artifact_sha256", "ranking",
        "ranked_selected_families", "non_calibration_splits", "clusters_per_family",
        "adversarial_pool_tradeoff", "B1a_families", "B1b_families", "B2_families",
    }
    if not isinstance(selection, dict) or set(selection) != selection_keys:
        raise FocusedFollowupError("focused selection schema drifted")
    if (
        tuple(selection["non_calibration_splits"]) != NON_CALIBRATION_SPLITS
        or selection["clusters_per_family"] != 40
        or selection["comparative_calibration_outcomes_known_when_frozen"] is not True
        or selection["combined_calibration_artifact"]
        != "results-next-study/qualification-v230-r1/operations/artifacts/calibration.json"
        or selection["combined_calibration_artifact_sha256"]
        != "e58dc31837647f86002f2e603d13031d839047fd26d4c4eabe616239b18d7fd1"
    ):
        raise FocusedFollowupError("focused selection policy drifted")
    if (
        selection["criterion"]
        != "the family rule and rank derive only from sealed condition-combined calibration totals; the focused protocol itself is post-comparative-exposure and no later direction or score may alter a family"
        or selection["ranking"]
        != "sort every family by c*(1-c) descending, where c is the sealed condition-combined total divided by 32; break exact ties by family name ascending; take the first six, then assign the three in-band families to B1a and the remaining three to B1b"
        or selection["transparency"]
        != "B1 is prospective on fresh non-calibration attempts, but it is not independent of all prior comparative-outcome exposure. The family rule itself uses only pre-direction condition-combined totals."
    ):
        raise FocusedFollowupError("focused selection wording drifted")
    chosen = tuple(selection["B1a_families"]) + tuple(selection["B1b_families"])
    if (
        len(chosen) != 6 or len(set(chosen)) != 6
        or any(family not in FAMILIES for family in chosen)
        or tuple(selection["B2_families"]) != tuple(selection["B1a_families"])
        or tuple(selection["ranked_selected_families"])
        != ("pptx_basic", "remind_msg", "cal_freeslot", "pptx_from_email", "cal_brief", "xlsx_basic")
        or tuple(selection["B1a_families"])
        != ("cal_freeslot", "pptx_basic", "remind_msg")
        or tuple(selection["B1b_families"])
        != ("pptx_from_email", "cal_brief", "xlsx_basic")
    ):
        raise FocusedFollowupError("focused family selection drifted")
    sampling = protocol["sampling"]
    sampling_keys = {
        "seed_namespace", "paired_seed_across_conditions", "B1_trial_index",
        "B2_trial_index", "B1_order_balance", "B2_order",
        "same_seed_retry_limit", "retry_eligibility", "seed_formula", "order_formula",
    }
    if (
        not isinstance(sampling, dict) or set(sampling) != sampling_keys
        or sampling["seed_namespace"] != "focused-followup/1.0.0"
        or sampling["paired_seed_across_conditions"] is not True
        or sampling["B1_trial_index"] != 0 or sampling["B2_trial_index"] != 1
        or sampling["same_seed_retry_limit"] != 1
        or not isinstance(sampling["seed_formula"], str)
        or not isinstance(sampling["order_formula"], str)
        or sampling["seed_formula"]
        != "low unsigned 63 bits of sha256(seed_namespace|generator_version|instance_id|trial_index|model_digest)"
        or sampling["order_formula"]
        != "sort by sha256(canonical JSON of schema_version=brick.focused-followup.order/1, protocol_sha256, family, instance_id, content_sha256); first 20 AB and remaining 20 BA; B2 reverses B1a"
    ):
        raise FocusedFollowupError("focused sampling contract drifted")
    blocks = protocol["blocks"]
    if blocks != {
        "B1a": {"families_key": "B1a_families", "logical_cells": 240, "cluster_count": 120, "role": "fallback_primary_component"},
        "B1b": {"families_key": "B1b_families", "logical_cells": 240, "cluster_count": 120, "role": "primary_component"},
        "B2": {"families_key": "B2_families", "logical_cells": 240, "cluster_count": 120, "role": "secondary_second_trial_for_repeatability"},
    }:
        raise FocusedFollowupError("focused block registry drifted")
    for block in BLOCKS:
        entry = blocks[block]
        if (
            not isinstance(entry, dict)
            or set(entry) != {"families_key", "logical_cells", "cluster_count", "role"}
            or entry["families_key"] not in selection
            or entry["logical_cells"] != 240 or entry["cluster_count"] != 120
        ):
            raise FocusedFollowupError("focused block contract drifted")
    if blocks["B2"]["families_key"] != "B2_families":
        raise FocusedFollowupError("B2 family contract drifted")
    estimands = protocol["estimands"]
    if estimands != {
        "B1": "equal-family mean strict-success difference, harness_full minus native_tools, over the six B1 families and one fresh paired trial",
        "B1a_fallback": "equal-family mean strict-success difference over B1a only; available only when B1b cannot complete by the frozen hard cutoff or has an isolated later environment failure",
        "B2": "equal-family mean strict-success difference over B1a families after averaging each instance's B1a trial 0 and B2 trial 1 outcomes; B2 trial 1 alone is descriptive only",
        "calibration": "retrospective exploratory context only; calibration observations are never pooled into B1 or B2",
    }:
        raise FocusedFollowupError("focused estimand contract drifted")
    claim = protocol["claim_rule"]
    if (
        claim != {
            "minimum_absolute_effect": "0.12", "threshold_inclusive": True,
            "interval": "two-sided 95% stratified percentile bootstrap; 50,000 exact-uniform SHA-256 rejection-sampled replicates; nearest-rank endpoints",
            "harness_superiority": "paired_effect >= 0.12 and lower_endpoint > 0",
            "native_superiority": "paired_effect <= -0.12 and upper_endpoint < 0",
            "sign_flip": "exact paired sign-flip diagnostic only; it cannot change the claim",
        }
    ):
        raise FocusedFollowupError("focused claim contract drifted")
    planning = protocol["planning"]
    if planning != {
        "B1_approximate_normal_joint_claim_probability_at_true_0_12": "0.500",
        "B1_approximate_normal_zero_exclusion_probability_at_true_0_12": "0.823",
        "B1_observed_single_trial_paired_variance": "0.414450",
        "B1_projected_normal_95_percent_half_width_from_observed_variance": "0.081448",
        "B1_projected_normal_standard_error_from_observed_variance": "0.041556",
        "B1a_approximate_normal_joint_claim_probability_at_true_0_12": "0.500",
        "B1a_approximate_normal_zero_exclusion_probability_at_true_0_12": "0.520",
        "B1a_observed_single_trial_paired_variance": "0.427536",
        "B1a_projected_normal_95_percent_half_width_from_observed_variance": "0.116986",
        "B1a_projected_normal_standard_error_from_observed_variance": "0.059688",
        "B2_approximate_normal_joint_claim_probability_at_true_0_12": "0.500",
        "B2_approximate_normal_zero_exclusion_probability_at_true_0_12": "0.688",
        "B2_observed_two_trial_paired_variance": "0.288043",
        "B2_projected_normal_95_percent_half_width_from_observed_variance": "0.096025",
        "B2_projected_normal_standard_error_from_observed_variance": "0.048993",
        "calibration_variance_is_empirical_not_guaranteed": True,
        "warning": "These are conditional planning calculations from only eight calibration clusters per family. The observed selected-family effect is descriptive and is not an assumed future effect.",
    }:
        raise FocusedFollowupError("focused planning contract drifted")
    reporting = protocol["reporting"]
    if reporting != {
        "cap_hit_report": "Report cap-hit rate by condition, capped/uncapped success counts, and paired cap-status patterns. Never exclude cap-hit clusters from the primary estimand.",
        "limitations": [
            "fixed synthetic benchmark only",
            "selected six-family follow-up estimand",
            "one primary fresh trial",
            "no mechanism attribution",
            "not validation of the separate Brix production harness",
            "six of 240 B1 task contexts appeared in the score-masked development shakeout at different seeds; no shakeout efficacy result was pooled or used in selection",
        ],
        "lofo": "descriptive leave-one-family-out sensitivity; it cannot alter a claim or justify exclusion",
        "retain_all_valid_attempts": True,
        "timing": "Report block-boundary elapsed time only. Per-attempt model_time_ms and wall_time_ms are known unavailable metrics in the base runtime.",
    }:
        raise FocusedFollowupError("focused reporting contract drifted")
    execution = protocol["execution"]
    if not isinstance(execution, dict) or set(execution) != {
        "B2_start_cutoff", "hard_stop", "run_console_may_not_report_scores", "block_seal",
    }:
        raise FocusedFollowupError("focused execution schema drifted")
    b2_cutoff = _timestamp(execution["B2_start_cutoff"], "B2 start cutoff")
    hard_stop = _timestamp(execution["hard_stop"], "hard stop")
    if (
        b2_cutoff >= hard_stop or execution["run_console_may_not_report_scores"] is not True
        or execution["B2_start_cutoff"] != "2026-08-10T03:00:00-05:00"
        or execution["hard_stop"] != "2026-08-10T20:00:00-05:00"
        or execution["block_seal"] != "marker-last; only sealed_complete_valid may be analyzed"
    ):
        raise FocusedFollowupError("focused execution cutoff drifted")
    return protocol


def protocol_sha256(protocol=None):
    return _digest(load_protocol() if protocol is None else validate_protocol(protocol))


def _manifest_path(split):
    if split not in NON_CALIBRATION_SPLITS + ("calibration",):
        raise FocusedFollowupError("unknown focused manifest split")
    return MANIFEST_DIRECTORY / (split + ".json")


def _validate_combined_calibration_selection(protocol):
    """Validate the direction-blind aggregate ranking that selected the six families.

    This reads only the published combined totals, never condition-level scores
    or attempt traces.  The focused protocol remains post-comparative-exposure;
    this function proves only that its mechanical family rule did not use that
    later directional information.
    """

    document = _load_published(CALIBRATION_ARTIFACT_PATH, "combined calibration")
    if _file_digest(CALIBRATION_ARTIFACT_PATH) != protocol["selection"]["combined_calibration_artifact_sha256"]:
        raise FocusedFollowupError("combined calibration artifact digest drifted")
    expected = {"condition_combined_totals", "per_condition_totals_exposed", "status"}
    if not isinstance(document, dict) or set(document) != expected:
        raise FocusedFollowupError("combined calibration artifact schema drifted")
    totals = document["condition_combined_totals"]
    if (
        document["status"] != "retire_generator"
        or document["per_condition_totals_exposed"] is not False
        or not isinstance(totals, dict) or set(totals) != set(FAMILIES)
    ):
        raise FocusedFollowupError("combined calibration artifact is not direction-blind terminal evidence")
    for family, total in totals.items():
        if type(total) is not int or not 0 <= total <= 32:
            raise FocusedFollowupError("combined calibration total is invalid")
    ranked = sorted(
        FAMILIES,
        key=lambda family: (-(totals[family] * (32 - totals[family])), family),
    )
    selection = protocol["selection"]
    if tuple(ranked[:6]) != tuple(selection["ranked_selected_families"]):
        raise FocusedFollowupError("focused families differ from exact combined-difficulty ranking")
    b1a = tuple(selection["B1a_families"])
    b1b = tuple(selection["B1b_families"])
    in_band = tuple(family for family in ranked[:6] if 10 <= totals[family] <= 22)
    remaining = tuple(family for family in ranked[:6] if family not in in_band)
    if set(b1a) != set(in_band) or set(b1b) != set(remaining):
        raise FocusedFollowupError("focused B1a/B1b grouping differs from combined-only rule")
    return {
        "artifact": document,
        "artifact_sha256": _file_digest(CALIBRATION_ARTIFACT_PATH),
        "ranked_families": ranked,
        "selected_families": ranked[:6],
    }


def _load_shakeout_bindings():
    """Validate the score-masked shakeout provenance that overlaps six contexts."""

    try:
        schedule = load_canonical_json(SHAKEOUT_SCHEDULE_PATH)
        authorization = _load_published(SHAKEOUT_AUTHORIZATION_PATH, "shakeout authorization")
        decision = _load_published(SHAKEOUT_DECISION_PATH, "shakeout decision")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise FocusedFollowupError("shakeout provenance is unreadable") from exc
    # File digests and the documents' self-digests intentionally differ: a
    # marker-last JSON file contains its own digest field.  Bind both so a
    # replacement cannot preserve just one layer of provenance.
    known = {
        "schedule_file_sha256": "2b90035f6b9e257e6b84d17e4920e6bcb53be3dfbb5d9b4cf8d2610574660753",
        "authorization_file_sha256": "1708eb5667ccb786bd0b5b01c33bf7ecf3b3fba4856071a443ba0108f060f8de",
        "decision_file_sha256": "d6ad146d78b8b6b2380e83115dfadeb6b64b86c0c1e249602fbd0a967dd4ddc3",
        "authorization_sha256": "d31c4f483387183ba8d5f077ab7606495fc71dfdc1095ef82833d9c655d295dd",
        "decision_sha256": "cd41a00e2ce52afb3093957fff3d2435ff870436807086d2ed835460f297a794",
    }
    development_manifest = load_canonical_json(_manifest_path("development"))
    try:
        validate_development_shakeout_schedule(schedule, development_manifest)
        _live.validate_shakeout_authorization(authorization)
        _live.validate_shakeout_decision(decision)
    except (TypeError, ValueError) as exc:
        raise FocusedFollowupError("shakeout provenance semantic validation failed") from exc
    if (
        _file_digest(SHAKEOUT_SCHEDULE_PATH) != known["schedule_file_sha256"]
        or _file_digest(SHAKEOUT_AUTHORIZATION_PATH) != known["authorization_file_sha256"]
        or _file_digest(SHAKEOUT_DECISION_PATH) != known["decision_file_sha256"]
        or authorization.get("authorization_sha256") != known["authorization_sha256"]
        or decision.get("decision_sha256") != known["decision_sha256"]
        or authorization.get("schedule_sha256") != _digest(schedule)
        or decision.get("authorization_sha256") != authorization.get("authorization_sha256")
        or decision.get("schedule_sha256") != authorization.get("schedule_sha256")
        or decision.get("scores_read") is not False
        or decision.get("condition_scores_read") is not False
        or decision.get("status") != "passed"
    ):
        raise FocusedFollowupError("shakeout provenance binding drifted")
    return {"schedule": schedule, **known}


def _assert_focused_seed_nonreuse(schedules):
    """Assert both full provider seeds and low-31 request seeds are fresh."""

    calibration = load_canonical_json(CALIBRATION_SCHEDULE_PATH)
    shakeout = _load_shakeout_bindings()["schedule"]
    baseline = calibration["records"] + shakeout["records"]
    baseline_full = {item["trial_seed"] for item in baseline}
    baseline_low31 = {item["trial_seed"] & 0x7FFFFFFF for item in baseline}
    focused = [cell for schedule in schedules.values() for cell in schedule["records"]]
    focused_full = {item["trial_seed"] for item in focused}
    focused_low31 = {item["trial_seed"] & 0x7FFFFFFF for item in focused}
    if focused_full & baseline_full or focused_low31 & baseline_low31:
        raise FocusedFollowupError("focused full or request seed overlaps calibration/shakeout")
    b1_ids = {
        item["instance_id"] for block in ("B1a", "B1b")
        for item in schedules[block]["records"]
    }
    shakeout_ids = {item["instance_id"] for item in shakeout["records"]}
    if len(b1_ids & shakeout_ids) != 6:
        raise FocusedFollowupError("focused shakeout-context overlap drifted")
    b1a_ids = {item["instance_id"] for item in schedules["B1a"]["records"]}
    b2_ids = {item["instance_id"] for item in schedules["B2"]["records"]}
    if b1a_ids != b2_ids:
        raise FocusedFollowupError("B2 must repeat the B1a cluster contexts")
    return {
        **{key: value for key, value in _load_shakeout_bindings().items() if key != "schedule"},
        "B1_shakeout_context_overlap_clusters": 6,
        "B2_repeats_B1a_clusters": len(b2_ids),
        "full_seed_overlap": 0,
        "request_seed_low31_overlap": 0,
    }


def _non_calibration_instances(protocol):
    selection = protocol["selection"]
    expected_splits = tuple(selection["non_calibration_splits"])
    by_family = defaultdict(list)
    seen_ids = set()
    for split in expected_splits:
        manifest = load_canonical_json(_manifest_path(split))
        validate_manifest(manifest)
        if manifest["split"] != split or manifest["generator_version"] != GENERATOR_VERSION:
            raise FocusedFollowupError("focused source manifest drifted")
        for instance in manifest["instances"]:
            content = instance["content"]
            if content["split"] != split:
                raise FocusedFollowupError("manifest content split drifted")
            instance_id = content["id"]
            if instance_id in seen_ids:
                raise FocusedFollowupError("non-calibration instance identity is duplicated")
            seen_ids.add(instance_id)
            by_family[content["family"]].append(instance)
    for family in FAMILIES:
        instances = by_family[family]
        if len(instances) != selection["clusters_per_family"]:
            raise FocusedFollowupError("non-calibration family allocation drifted")
        workloads = Counter(item["content"]["structure"]["workload"] for item in instances)
        distractors = Counter(item["content"]["structure"]["distractor_count"] for item in instances)
        policies = Counter(item["content"]["structure"]["decision_policy"] for item in instances)
        if sorted(workloads.values()) != [10, 10, 10, 10] or sorted(distractors.values()) != [10, 10, 10, 10]:
            raise FocusedFollowupError("non-calibration factorial balance drifted")
        if sorted(policies.values()) != [13, 13, 14]:
            raise FocusedFollowupError("non-calibration policy balance drifted")
    return by_family


def focused_trial_seed(protocol, instance_id, trial_index, model_digest):
    if trial_index not in (0, 1):
        raise FocusedFollowupError("focused trial index is invalid")
    _require_sha256(model_digest, "focused model digest")
    payload = "|".join((
        protocol["sampling"]["seed_namespace"], GENERATOR_VERSION,
        instance_id, str(trial_index), model_digest,
    ))
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest(), "big") & ((1 << 63) - 1)


def _order_strata(protocol, family, instances, trial_index):
    if len(instances) != 40:
        raise FocusedFollowupError("focused order requires forty clusters per family")
    ranked = sorted(instances, key=lambda item: _digest({
        "schema_version": "brick.focused-followup.order/1",
        "protocol_sha256": protocol_sha256(protocol),
        "family": family,
        "instance_id": item["content"]["id"],
        "content_sha256": item["content_sha256"],
    }))
    result = {}
    for index, instance in enumerate(ranked):
        order = "AB" if index < 20 else "BA"
        if trial_index == 1:
            order = "BA" if order == "AB" else "AB"
        result[instance["content"]["id"]] = order
    return result


def build_schedule(block, model_digest, protocol=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    if block not in BLOCKS:
        raise FocusedFollowupError("unknown focused block")
    _require_sha256(model_digest, "focused model digest")
    selection = protocol["selection"]
    block_contract = protocol["blocks"][block]
    families = tuple(selection[block_contract["families_key"]])
    trial_index = protocol["sampling"]["B2_trial_index"] if block == "B2" else protocol["sampling"]["B1_trial_index"]
    by_family = _non_calibration_instances(protocol)
    records = []
    for family in families:
        instances = sorted(by_family[family], key=lambda item: item["content"]["id"])
        strata = _order_strata(protocol, family, instances, trial_index)
        if Counter(strata.values()) != {"AB": 20, "BA": 20}:
            raise FocusedFollowupError("focused order counterbalance drifted")
        for instance in instances:
            content = instance["content"]
            instance_id = content["id"]
            order = strata[instance_id]
            seed = focused_trial_seed(protocol, instance_id, trial_index, model_digest)
            ordered_conditions = CONDITIONS if order == "AB" else tuple(reversed(CONDITIONS))
            for order_position, condition in enumerate(ordered_conditions):
                cell_identity = {
                    "schema_version": "brick.focused-followup.cell/1",
                    "block": block,
                    "instance_id": instance_id,
                    "content_sha256": instance["content_sha256"],
                    "condition": condition,
                    "trial_index": trial_index,
                    "trial_seed": seed,
                }
                records.append({
                    "logical_cell_id": _digest(cell_identity),
                    "phase": "focused_" + block,
                    "block": block,
                    "instance_id": instance_id,
                    "content_sha256": instance["content_sha256"],
                    "family": family,
                    "source_split": content["split"],
                    "condition": condition,
                    "trial_index": trial_index,
                    "order_stratum": order,
                    "order_position": order_position,
                    "trial_seed": seed,
                })
    if len(records) != block_contract["logical_cells"]:
        raise FocusedFollowupError("focused schedule cell count drifted")
    if len({item["logical_cell_id"] for item in records}) != len(records):
        raise FocusedFollowupError("focused schedule has duplicate cells")
    document = {
        "schema_version": SCHEDULE_SCHEMA,
        "protocol_version": protocol["version"],
        "protocol_sha256": protocol_sha256(protocol),
        "generator_version": GENERATOR_VERSION,
        "model_sha256": model_digest,
        "phase": "focused_" + block,
        "split": "non_calibration_pool",
        "logical_cell_count": len(records),
        "maximum_physical_attempts": len(records) * 2,
        "same_seed_retry_limit": 1,
        "records": records,
    }
    return validate_schedule(document, protocol)


def validate_schedule(schedule, protocol=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    expected_keys = {
        "schema_version", "protocol_version", "protocol_sha256", "generator_version",
        "model_sha256", "phase", "split", "logical_cell_count",
        "maximum_physical_attempts", "same_seed_retry_limit", "records",
    }
    if not isinstance(schedule, dict) or set(schedule) != expected_keys:
        raise FocusedFollowupError("focused schedule has unexpected keys")
    if schedule["schema_version"] != SCHEDULE_SCHEMA or schedule["protocol_version"] != protocol["version"]:
        raise FocusedFollowupError("focused schedule schema drifted")
    if schedule["protocol_sha256"] != protocol_sha256(protocol) or schedule["generator_version"] != GENERATOR_VERSION:
        raise FocusedFollowupError("focused schedule binding drifted")
    _require_sha256(schedule["model_sha256"], "focused schedule model")
    phase = schedule["phase"]
    if not isinstance(phase, str) or not phase.startswith("focused_") or phase[8:] not in BLOCKS:
        raise FocusedFollowupError("focused schedule phase is invalid")
    block = phase[8:]
    expected = _build_schedule_unvalidated(block, schedule["model_sha256"], protocol)
    if schedule != expected:
        raise FocusedFollowupError("focused schedule differs from exact reconstruction")
    return schedule


def _build_schedule_unvalidated(block, model_digest, protocol):
    """Build then strip validation recursion for :func:`validate_schedule`."""

    selection = protocol["selection"]
    block_contract = protocol["blocks"][block]
    families = tuple(selection[block_contract["families_key"]])
    trial_index = protocol["sampling"]["B2_trial_index"] if block == "B2" else protocol["sampling"]["B1_trial_index"]
    by_family = _non_calibration_instances(protocol)
    records = []
    for family in families:
        instances = sorted(by_family[family], key=lambda item: item["content"]["id"])
        strata = _order_strata(protocol, family, instances, trial_index)
        for instance in instances:
            content = instance["content"]
            instance_id = content["id"]
            order = strata[instance_id]
            seed = focused_trial_seed(protocol, instance_id, trial_index, model_digest)
            ordered_conditions = CONDITIONS if order == "AB" else tuple(reversed(CONDITIONS))
            for order_position, condition in enumerate(ordered_conditions):
                records.append({
                    "logical_cell_id": _digest({
                        "schema_version": "brick.focused-followup.cell/1",
                        "block": block,
                        "instance_id": instance_id,
                        "content_sha256": instance["content_sha256"],
                        "condition": condition,
                        "trial_index": trial_index,
                        "trial_seed": seed,
                    }),
                    "phase": "focused_" + block,
                    "block": block,
                    "instance_id": instance_id,
                    "content_sha256": instance["content_sha256"],
                    "family": family,
                    "source_split": content["split"],
                    "condition": condition,
                    "trial_index": trial_index,
                    "order_stratum": order,
                    "order_position": order_position,
                    "trial_seed": seed,
                })
    return {
        "schema_version": SCHEDULE_SCHEMA,
        "protocol_version": protocol["version"],
        "protocol_sha256": protocol_sha256(protocol),
        "generator_version": GENERATOR_VERSION,
        "model_sha256": model_digest,
        "phase": "focused_" + block,
        "split": "non_calibration_pool",
        "logical_cell_count": len(records),
        "maximum_physical_attempts": len(records) * 2,
        "same_seed_retry_limit": 1,
        "records": records,
    }


def build_schedules(model_digest, protocol=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    return {block: build_schedule(block, model_digest, protocol) for block in BLOCKS}


def _source_digests(supervisor_path):
    supervisor = Path(supervisor_path)
    try:
        relative_supervisor = supervisor.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise FocusedFollowupError("supervisor must be inside the project root") from exc
    if not supervisor.is_file():
        raise FocusedFollowupError("tracked focused supervisor is missing")
    paths = {
        "generator": ROOT / "domains" / "office_demo" / "generators_v2.py",
        "outcome_oracle_implementation": ROOT / "domains" / "office_demo" / "outcome_oracle_v2.py",
        "validated_outcomes": VALIDATED_OUTCOMES_PATH,
        "tool_contracts": ROOT / "domains" / "office_demo" / "contracts.py",
        "reviewed_grader": ROOT / "domains" / "office_demo" / "reviewed_grader_v2.py",
        "strict_graders": ROOT / "domains" / "office_demo" / "strict_graders.py",
        "office_files": ROOT / "domains" / "office_demo" / "office_files.py",
        "world": ROOT / "domains" / "office_demo" / "world.py",
        "validated_outcomes_compiler": ROOT / "bench" / "next_study_validated_outcomes.py",
        "focused_protocol": PROTOCOL_PATH,
        "focused_analyzer": Path(__file__),
        "focused_supervisor": supervisor,
        "manifest_lock": MANIFEST_DIRECTORY / "manifest-lock.json",
        "exploratory_plan": EXPLORATORY_PLAN_PATH,
        "pptx_basic_static_validity_audit": ROOT / "evidence" / "next-study" / "office-v2.3.0-pptx-basic-static-validity-audit.json",
        "combined_calibration": CALIBRATION_ARTIFACT_PATH,
    }
    for label, path in paths.items():
        if not path.is_file():
            raise FocusedFollowupError("bound source %s is missing" % label)
    return {
        "implementation_sha256": _live._implementation_sha256(),
        "supervisor_path": relative_supervisor,
        **{label: _file_digest(path) for label, path in paths.items()},
    }


def _validate_preflight_for_authorization(preflight):
    try:
        _live.validate_native_preflight(preflight)
    except (TypeError, ValueError) as exc:
        raise FocusedFollowupError("focused authorization needs a valid native preflight") from exc
    if preflight["git_clean"] is not True or preflight["passed"] is not True:
        raise FocusedFollowupError("focused authorization needs a clean passing preflight")
    model = preflight["model_digests"].get("4b")
    _require_sha256(model, "focused 4b model digest")
    runtime = preflight["runtime_fingerprint"]
    details = runtime.get("details") if isinstance(runtime, dict) else None
    if not isinstance(details, dict) or details.get("implementation_sha256") != _live._implementation_sha256():
        raise FocusedFollowupError("current runtime implementation differs from frozen v0.13.3 core")
    return preflight


def _load_base_program_authorization():
    try:
        document = _load_published(BASE_AUTHORIZATION_PATH, "base v0.13.3 authorization")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise FocusedFollowupError("base v0.13.3 authorization is unreadable") from exc
    try:
        _validate_base_program_authorization(document)
    except (TypeError, ValueError) as exc:
        raise FocusedFollowupError("base v0.13.3 authorization is invalid") from exc
    expected = {
        "schema_version", "status", "tag", "tag_object_sha", "commit_sha",
        "authorization_sha256", "model_digests", "runtime_fingerprint",
    }
    if not expected <= set(document):
        raise FocusedFollowupError("base authorization lacks required bindings")
    if document["tag"] != "v0.13.3":
        raise FocusedFollowupError("base authorization tag drifted")
    _require_sha256(document["authorization_sha256"], "base authorization digest")
    return document


def build_authorization(
    preflight, issued_at, issuer, supervisor_path, run_id,
    followup_tag="v0.13.4", base_tag="v0.13.3", protocol=None,
):
    """Build a clean-worktree, tag-bound authorization for all three blocks."""

    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    preflight = _validate_preflight_for_authorization(preflight)
    _timestamp(issued_at, "focused authorization issue time")
    if not isinstance(issuer, str) or not issuer.strip():
        raise FocusedFollowupError("focused authorization issuer is empty")
    _require_component(run_id, "focused authorized run id")
    if run_id != FOCUSED_RUN_ID:
        raise FocusedFollowupError("focused authorization run id is not the sole frozen run id")
    current_commit = preflight["commit_sha"]
    _require_sha1(current_commit, "focused follow-up commit")
    base = _annotated_tag_binding(base_tag)
    followup = _annotated_tag_binding(followup_tag, current_commit)
    base_program = _load_base_program_authorization()
    if (
        base["commit_sha"] != base_program["commit_sha"]
        or base["tag_object_sha"] != base_program["tag_object_sha"]
    ):
        raise FocusedFollowupError("base tag differs from its sealed v0.13.3 authorization")
    if (
        preflight["host_fingerprint"] != base_program["host_fingerprint"]
        or preflight["runtime_fingerprint"] != base_program["runtime_fingerprint"]
        or preflight["model_digests"] != base_program["model_digests"]
        or preflight["tool_schema_sha256"]
        != base_program["runtime_fingerprint"]["details"].get("tool_schema_sha256")
        or preflight["validated_outcomes_sha256"]
        != base_program["artifact_digests"].get("validated_outcomes")
    ):
        raise FocusedFollowupError("current preflight differs from sealed v0.13.3 runtime bindings")
    source_digests = _source_digests(supervisor_path)
    if source_digests["implementation_sha256"] != base_program["runtime_fingerprint"]["details"]["implementation_sha256"]:
        raise FocusedFollowupError("focused code changed a v0.13.3 model-facing implementation")
    selection_evidence = _validate_combined_calibration_selection(protocol)
    schedules = build_schedules(preflight["model_digests"]["4b"], protocol)
    shakeout_bindings = _assert_focused_seed_nonreuse(schedules)
    document = {
        "schema_version": AUTHORIZATION_SCHEMA,
        "status": "authorized",
        "execution_context": {
            "schema_version": EXECUTION_CONTEXT_SCHEMA,
            "value": "focused_followup_exploratory",
        },
        "protocol_sha256": protocol_sha256(protocol),
        "base_tag": base["tag"],
        "base_tag_object_sha": base["tag_object_sha"],
        "base_commit_sha": base["commit_sha"],
        "base_program_authorization_sha256": base_program["authorization_sha256"],
        "followup_tag": followup["tag"],
        "followup_tag_object_sha": followup["tag_object_sha"],
        "followup_commit_sha": followup["commit_sha"],
        "issued_at": issued_at,
        "issuer": issuer.strip(),
        "run_id": run_id,
        "runs_root": FOCUSED_RUNS_ROOT_RELATIVE,
        "preflight_sha256": preflight["preflight_sha256"],
        "host_fingerprint": preflight["host_fingerprint"],
        "runtime_fingerprint": preflight["runtime_fingerprint"],
        "model_digests": preflight["model_digests"],
        "validated_outcomes_sha256": preflight["validated_outcomes_sha256"],
        "tool_schema_sha256": preflight["tool_schema_sha256"],
        "combined_calibration_sha256": selection_evidence["artifact_sha256"],
        "shakeout_bindings": shakeout_bindings,
        "source_digests": source_digests,
        "schedule_digests": {block: _digest(schedule) for block, schedule in schedules.items()},
        "maximum_logical_cells": 720,
        "maximum_physical_attempts": 1440,
        "same_seed_retry_limit": 1,
        "cutoffs": dict(protocol["execution"]),
    }
    document["authorization_sha256"] = _digest(document)
    document = validate_authorization(document, protocol)
    _validate_authorization_repository_bindings(document)
    return document


def validate_authorization(document, protocol=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    expected = {
        "schema_version", "status", "execution_context", "protocol_sha256",
        "base_tag", "base_tag_object_sha", "base_commit_sha",
        "base_program_authorization_sha256", "followup_tag", "followup_tag_object_sha",
        "followup_commit_sha", "issued_at", "issuer", "preflight_sha256",
        "run_id", "runs_root",
        "host_fingerprint", "runtime_fingerprint", "model_digests",
        "validated_outcomes_sha256", "tool_schema_sha256", "source_digests",
        "combined_calibration_sha256", "shakeout_bindings",
        "schedule_digests", "maximum_logical_cells", "maximum_physical_attempts",
        "same_seed_retry_limit", "cutoffs", "authorization_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise FocusedFollowupError("focused authorization has unexpected keys")
    unsigned = dict(document)
    supplied = unsigned.pop("authorization_sha256")
    _require_sha256(supplied, "focused authorization digest")
    if supplied != _digest(unsigned):
        raise FocusedFollowupError("focused authorization digest drifted")
    if (
        document["schema_version"] != AUTHORIZATION_SCHEMA
        or document["status"] != "authorized"
        or document["protocol_sha256"] != protocol_sha256(protocol)
        or document["base_tag"] != protocol["base_instrument"]["tag"]
        or document["followup_tag"] != "v0.13.4"
        or document["maximum_logical_cells"] != 720
        or document["maximum_physical_attempts"] != 1440
        or document["same_seed_retry_limit"] != 1
        or document["cutoffs"] != protocol["execution"]
        or document["run_id"] != FOCUSED_RUN_ID
        or document["runs_root"] != FOCUSED_RUNS_ROOT_RELATIVE
    ):
        raise FocusedFollowupError("focused authorization contract drifted")
    context = document["execution_context"]
    if context != {"schema_version": EXECUTION_CONTEXT_SCHEMA, "value": "focused_followup_exploratory"}:
        raise FocusedFollowupError("focused execution context drifted")
    for label in (
        "base_program_authorization_sha256", "preflight_sha256",
        "validated_outcomes_sha256", "tool_schema_sha256", "combined_calibration_sha256",
    ):
        _require_sha256(document[label], label)
    for label in (
        "base_tag_object_sha", "followup_tag_object_sha", "base_commit_sha",
        "followup_commit_sha",
    ):
        _require_sha1(document[label], label)
    _timestamp(document["issued_at"], "focused authorization issue time")
    if not isinstance(document["issuer"], str) or not document["issuer"].strip():
        raise FocusedFollowupError("focused authorization issuer is empty")
    _require_component(document["run_id"], "focused authorized run id")
    if not isinstance(document["model_digests"], dict) or set(document["model_digests"]) != {"2b", "4b", "9b"}:
        raise FocusedFollowupError("focused authorization model digest schema drifted")
    for digest in document["model_digests"].values():
        _require_sha256(digest, "focused authorization model digest")
    source = document["source_digests"]
    source_keys = {
        "implementation_sha256", "supervisor_path", "generator", "outcome_oracle_implementation",
        "validated_outcomes", "tool_contracts", "reviewed_grader", "strict_graders", "office_files", "world",
        "validated_outcomes_compiler",
        "focused_protocol", "focused_analyzer", "focused_supervisor", "manifest_lock",
        "exploratory_plan", "pptx_basic_static_validity_audit", "combined_calibration",
    }
    if not isinstance(source, dict) or set(source) != source_keys:
        raise FocusedFollowupError("focused source digest schema drifted")
    _require_sha256(source["implementation_sha256"], "focused implementation digest")
    if source["supervisor_path"] != "scripts/run-focused-followup.ps1":
        raise FocusedFollowupError("focused supervisor path drifted")
    for label, digest in source.items():
        if label not in {"implementation_sha256", "supervisor_path"}:
            _require_sha256(digest, "focused source " + label)
    if not isinstance(document["schedule_digests"], dict) or set(document["schedule_digests"]) != set(BLOCKS):
        raise FocusedFollowupError("focused authorization schedule schema drifted")
    for block, digest in document["schedule_digests"].items():
        _require_sha256(digest, "focused schedule " + block)
        expected_schedule = build_schedule(block, document["model_digests"]["4b"], protocol)
        if digest != _digest(expected_schedule):
            raise FocusedFollowupError("focused authorization schedule binding drifted")
    if document["combined_calibration_sha256"] != protocol["selection"]["combined_calibration_artifact_sha256"]:
        raise FocusedFollowupError("focused authorization combined calibration binding drifted")
    expected_shakeout = _assert_focused_seed_nonreuse({
        block: build_schedule(block, document["model_digests"]["4b"], protocol)
        for block in BLOCKS
    })
    if document["shakeout_bindings"] != expected_shakeout:
        raise FocusedFollowupError("focused authorization shakeout or seed-reuse binding drifted")
    return document


def _validate_authorization_repository_bindings(authorization):
    """Re-open immutable Git and v0.13.3 authorization bindings at use time."""

    base = _annotated_tag_binding("v0.13.3", authorization["base_commit_sha"])
    followup = _annotated_tag_binding("v0.13.4", authorization["followup_commit_sha"])
    if (
        base["tag_object_sha"] != authorization["base_tag_object_sha"]
        or followup["tag_object_sha"] != authorization["followup_tag_object_sha"]
    ):
        raise FocusedFollowupError("focused authorization annotated tag binding drifted")
    base_program = _load_base_program_authorization()
    if (
        base_program["authorization_sha256"] != authorization["base_program_authorization_sha256"]
        or base_program["tag"] != authorization["base_tag"]
        or base_program["tag_object_sha"] != authorization["base_tag_object_sha"]
        or base_program["commit_sha"] != authorization["base_commit_sha"]
        or base_program["model_digests"] != authorization["model_digests"]
        or base_program["runtime_fingerprint"] != authorization["runtime_fingerprint"]
    ):
        raise FocusedFollowupError("focused authorization base v0.13.3 binding drifted")
    if _git("rev-parse", "HEAD") != authorization["followup_commit_sha"]:
        raise FocusedFollowupError("focused authorization current HEAD drifted")
    if _git("status", "--porcelain", "--untracked-files=all"):
        raise FocusedFollowupError("focused authorization requires a clean tracked worktree")
    current_source = _source_digests(ROOT / authorization["source_digests"]["supervisor_path"])
    if current_source != authorization["source_digests"]:
        raise FocusedFollowupError("focused authorization source binding drifted")
    return authorization


def authorized_runs_root(authorization):
    """Return the single authorization-bound project-relative evidence root."""

    validate_authorization(authorization)
    relative = authorization["runs_root"]
    if relative != FOCUSED_RUNS_ROOT_RELATIVE:
        raise FocusedFollowupError("focused authorization evidence root drifted")
    expected = (ROOT / relative).resolve()
    try:
        expected.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise FocusedFollowupError("focused authorization evidence root escapes project") from exc
    return expected


def require_authorized_runs_root(authorization, supplied):
    """Reject a CLI-selected alternate evidence universe before any mutation."""

    expected = authorized_runs_root(authorization)
    if Path(supplied).resolve() != expected:
        raise FocusedFollowupError("focused runs root differs from the authorization-bound root")
    return expected


def require_authorized_run_id(authorization, supplied):
    """Reject a CLI-selected alternate run before preflight or evidence access."""

    if supplied != authorization["run_id"] or supplied != FOCUSED_RUN_ID:
        raise FocusedFollowupError("focused run id differs from the sole authorization-bound run id")
    return authorization["run_id"]


def validate_current_environment(
    authorization, preflight=None, supervisor_path=None, protocol=None, preflight_provider=None,
):
    """Recollect and compare all runtime bindings immediately before inference."""

    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    validate_authorization(authorization, protocol)
    _validate_authorization_repository_bindings(authorization)
    provider = preflight_provider or (lambda: _live.collect_native_preflight(require_clean=True))
    recollected = _validate_preflight_for_authorization(provider())
    if preflight is not None and preflight != recollected:
        raise FocusedFollowupError("caller-supplied preflight differs from freshly recollected preflight")
    preflight = recollected
    exact_fields = (
        "preflight_sha256", "host_fingerprint", "runtime_fingerprint", "model_digests",
        "validated_outcomes_sha256", "tool_schema_sha256",
    )
    for field in exact_fields:
        if preflight[field] != authorization[field]:
            raise FocusedFollowupError("current preflight differs from focused authorization: " + field)
    if preflight["commit_sha"] != authorization["followup_commit_sha"]:
        raise FocusedFollowupError("current commit differs from focused authorization")
    binding = _annotated_tag_binding(authorization["followup_tag"], preflight["commit_sha"])
    if binding["tag_object_sha"] != authorization["followup_tag_object_sha"]:
        raise FocusedFollowupError("focused annotated tag object drifted")
    if supervisor_path is None:
        supervisor_path = ROOT / authorization["source_digests"]["supervisor_path"]
    current_source = _source_digests(supervisor_path)
    if current_source != authorization["source_digests"]:
        raise FocusedFollowupError("focused source binding drifted")
    return preflight


def _publish_marker_last(path, document):
    """Publish canonical immutable JSON followed by an empty completion marker."""

    path = Path(path)
    marker = path.with_name(path.name + ".complete")
    if path.exists() or marker.exists():
        raise FocusedFollowupError("refusing to replace published focused evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(document, newline=True, allow_float=False)
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    with marker.open("xb") as handle:
        handle.flush()
        os.fsync(handle.fileno())
    return path


def _load_published(path, label):
    path = Path(path)
    marker = path.with_name(path.name + ".complete")
    if not path.is_file() or not marker.is_file() or marker.stat().st_size != 0:
        raise FocusedFollowupError("%s marker-last artifact is missing" % label)
    try:
        return load_canonical_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise FocusedFollowupError("%s artifact is unreadable" % label) from exc


def _run_metadata(authorization):
    return {
        "schema_version": RUN_METADATA_SCHEMA,
        "run_id": authorization["run_id"],
        "runs_root": authorization["runs_root"],
        "authorization_sha256": authorization["authorization_sha256"],
        "protocol_sha256": authorization["protocol_sha256"],
        "followup_commit_sha": authorization["followup_commit_sha"],
        "schedule_digests": dict(authorization["schedule_digests"]),
        "preflight_sha256": authorization["preflight_sha256"],
        "score_masked_console": True,
    }


def _open_or_create_store(runs_root, run_id, authorization):
    _require_component(run_id, "focused run id")
    if run_id != authorization["run_id"]:
        raise FocusedFollowupError("focused run id differs from authorization")
    return EvidenceStore.create_run(runs_root, run_id, _run_metadata(authorization))


def _validate_store_metadata(store, authorization):
    if store.run_id != authorization["run_id"]:
        raise FocusedFollowupError("focused EvidenceStore run id differs from authorization")
    metadata = store.run_document.get("metadata") if isinstance(store.run_document, dict) else None
    if metadata != _run_metadata(authorization):
        raise FocusedFollowupError("focused EvidenceStore metadata differs from authorization")
    return store


def _block_artifact_path(runs_root, authorization, block):
    if block not in BLOCKS:
        raise FocusedFollowupError("unknown focused block")
    return Path(runs_root) / "focused-followup-blocks" / authorization["authorization_sha256"] / (block + ".json")


def _block_start_artifact_path(runs_root, authorization, block):
    if block not in BLOCKS:
        raise FocusedFollowupError("unknown focused block")
    return Path(runs_root) / "focused-followup-block-starts" / authorization["authorization_sha256"] / (block + ".json")


def _termination_artifact_path(runs_root, authorization, block):
    if block not in BLOCKS:
        raise FocusedFollowupError("unknown focused block")
    return Path(runs_root) / "focused-followup-terminations" / authorization["authorization_sha256"] / (block + ".json")


def _analysis_artifact_path(runs_root, authorization):
    """The single marker-last analysis location that closes further execution."""

    return Path(runs_root) / "focused-followup-analysis" / authorization["authorization_sha256"] / "analysis.json"


def _report_artifact_path(runs_root, authorization):
    return Path(runs_root) / "focused-followup-reports" / authorization["authorization_sha256"] / "study-report.json"


def _assert_execution_open(runs_root, authorization):
    path = _analysis_artifact_path(runs_root, authorization)
    if path.exists() or path.with_name(path.name + ".complete").exists():
        raise FocusedFollowupError("focused analysis is already published; no later block mutation is permitted")


def _recovery_artifact_path(runs_root, authorization, run_id, logical_cell_id):
    _require_component(run_id, "focused recovery run id")
    _require_sha256(logical_cell_id, "focused recovery logical cell")
    # Keep the Windows path materially below MAX_PATH even when callers use a
    # deep writable root.  The immutable document itself binds the full
    # authorization digest; run metadata independently prevents cross-auth
    # reuse of the same run id.
    return (
        Path(runs_root) / "ffr" / run_id / (logical_cell_id + ".json")
    )


def _record_digest(record):
    return sha256_bytes(canonical_json_bytes(record, allow_float=True))


def _expected_attempt_key(instance, cell, authorization, repeat):
    """Reconstruct the complete frozen producer key for one physical attempt.

    Coordinates alone are not a sufficient provenance check: a re-signed
    marker-last record could otherwise carry a different grader, tool schema,
    mechanism set, prompt identity, model tag, or budget while occupying a
    legitimate focused cell.  The live producer uses precisely this builder.
    """

    if type(repeat) is not int or repeat not in (0, 1):
        raise FocusedFollowupError("focused expected evidence repeat is invalid")
    try:
        implementation = authorization["source_digests"]["implementation_sha256"]
        condition, execution_protocol = _live._condition(cell["condition"], implementation)
        execution_protocol["primary_model"] = _live.MODEL_TAGS["4b"]
        environment = {
            "runtime_fingerprint": authorization["runtime_fingerprint"],
            "tool_schema_sha256": authorization["tool_schema_sha256"],
        }
        return _live._attempt_key(
            instance, cell, condition, execution_protocol,
            execution_protocol["primary_model"], authorization["model_digests"]["4b"],
            repeat, environment,
        ).to_dict()
    except (KeyError, TypeError, ValueError) as exc:
        raise FocusedFollowupError("focused expected evidence key is unreadable") from exc


def _attempt_record_from_committed(
    committed, store, schedule_by_coordinate, schedule_by_cell, authorization, instances_by_id,
):
    try:
        key = committed["attempt_key"]
        coordinate = (
            key["instance"]["id"], key["condition"]["name"],
            key["sampling"]["seed"], key["sampling"]["trial_index"],
        )
        repeat = key["repeat"]
    except (KeyError, TypeError) as exc:
        raise FocusedFollowupError("focused committed evidence key is incomplete") from exc
    cell = schedule_by_coordinate.get(coordinate)
    if cell is None:
        return None
    logical_cell_id = cell["logical_cell_id"]
    if logical_cell_id not in schedule_by_cell:
        raise FocusedFollowupError("focused schedule coordinate map drifted")
    if type(repeat) is not int or repeat not in (0, 1):
        raise FocusedFollowupError("focused evidence repeat is invalid")
    instance = instances_by_id.get(cell["instance_id"])
    if instance is None or instance.get("content_sha256") != cell["content_sha256"]:
        raise FocusedFollowupError("focused scheduled instance binding is unreadable")
    expected_key_document = _expected_attempt_key(instance, cell, authorization, repeat)
    expected_key = AttemptKey.from_dict(expected_key_document)
    candidate = store.attempts_dir / committed["logical_hash"] / committed["physical_uuid"]
    try:
        validated = validate_committed(
            candidate,
            expected_key=expected_key,
            expected_run={"run_id": store.run_id, "run_sha256": store.run_sha256},
        )
    except Exception as exc:
        raise FocusedFollowupError("focused committed evidence failed marker-last validation") from exc
    semantic = validated["semantic"]
    semantic_key = semantic["key"].to_dict()
    if semantic_key != key:
        raise FocusedFollowupError("focused evidence projection changed after validation")
    if key != expected_key_document:
        raise FocusedFollowupError("focused evidence AttemptKey differs from frozen producer identity")
    result = semantic["result"]
    grade = semantic["grade"]
    raw_origin = result.get("failure_origin")
    if raw_origin in ("none", "model") and grade.get("grader_status") == "graded":
        origin = raw_origin
        strict_success = grade.get("candidate_decision")
        if type(strict_success) is not bool:
            raise FocusedFollowupError("focused graded attempt success is invalid")
    elif raw_origin == "environment":
        origin = "environment"; strict_success = None
    else:
        origin = "instrument"; strict_success = None
    failure = result.get("failure")
    retryable = bool(
        origin == "environment" and repeat == 0
        and isinstance(failure, dict) and failure.get("retryable") is True
    )
    metrics = _resource_metrics(result, semantic["actions"]["actions"])
    evidence_digest = _record_digest(committed)
    record = {
        "schema_version": ATTEMPT_RECORD_SCHEMA,
        "logical_cell_id": logical_cell_id,
        "repeat": repeat,
        "trial_seed": cell["trial_seed"],
        "failure_origin": origin,
        "retryable": retryable,
        "strict_success": strict_success,
        "evidence_sha256": evidence_digest,
        "grade_record_sha256": sha256_bytes(canonical_json_bytes(committed.get("grade"), allow_float=True)),
        "marker_last_verified": True,
        **metrics,
    }
    validate_attempt_record(record, cell)
    return record


def validate_attempt_record(record, cell):
    expected = {
        "schema_version", "logical_cell_id", "repeat", "trial_seed", "failure_origin",
        "retryable", "strict_success", "evidence_sha256", "grade_record_sha256",
        "marker_last_verified", "model_calls", "successful_reads", "successful_mutations",
        "generated_tokens_exact", "generated_tokens_lower_bound", "generated_tokens_upper_bound",
        "model_time_ms", "wall_time_ms",
    }
    if not isinstance(record, dict) or set(record) != expected:
        raise FocusedFollowupError("focused attempt record has unexpected keys")
    if (
        record["schema_version"] != ATTEMPT_RECORD_SCHEMA
        or record["logical_cell_id"] != cell["logical_cell_id"]
        or record["trial_seed"] != cell["trial_seed"]
        or type(record["repeat"]) is not int or record["repeat"] not in (0, 1)
        or record["failure_origin"] not in ("none", "model", "environment", "instrument")
        or type(record["retryable"]) is not bool
        or record["marker_last_verified"] is not True
    ):
        raise FocusedFollowupError("focused attempt record identity drifted")
    for label in ("evidence_sha256", "grade_record_sha256"):
        _require_sha256(record[label], "focused attempt " + label)
    if record["failure_origin"] in ("none", "model"):
        if type(record["strict_success"]) is not bool:
            raise FocusedFollowupError("focused valid attempt must have strict success")
    elif record["strict_success"] is not None:
        raise FocusedFollowupError("focused invalid attempt success must be null")
    if record["retryable"] and not (record["failure_origin"] == "environment" and record["repeat"] == 0):
        raise FocusedFollowupError("focused retry eligibility drifted")
    for field in ("model_calls", "successful_reads", "successful_mutations", "model_time_ms", "wall_time_ms"):
        if type(record[field]) is not int or record[field] < 0:
            raise FocusedFollowupError("focused resource metric is invalid")
    exact = record["generated_tokens_exact"]
    lower = record["generated_tokens_lower_bound"]
    upper = record["generated_tokens_upper_bound"]
    if exact is None:
        if type(lower) is not int or lower < 0 or (upper is not None and (type(upper) is not int or upper < lower)):
            raise FocusedFollowupError("focused token bounds are invalid")
    elif type(exact) is not int or exact < 0 or lower is not None or upper is not None:
        raise FocusedFollowupError("focused exact-token metric is invalid")
    return record


def extract_block_attempts(store, schedule, authorization):
    """Extract only one exact reconstructed schedule from a shared evidence run."""

    validate_schedule(schedule)
    validate_authorization(authorization)
    schedule_by_cell = {cell["logical_cell_id"]: cell for cell in schedule["records"]}
    if len(schedule_by_cell) != len(schedule["records"]):
        raise FocusedFollowupError("focused schedule cell identity is duplicated")
    schedule_by_coordinate = {}
    for cell in schedule["records"]:
        coordinate = (cell["instance_id"], cell["condition"], cell["trial_seed"], cell["trial_index"])
        if coordinate in schedule_by_coordinate:
            raise FocusedFollowupError("focused schedule sampling coordinate is duplicated")
        schedule_by_coordinate[coordinate] = cell
    projection = store.read_committed()
    if not isinstance(projection, dict) or not isinstance(projection.get("records"), list):
        raise FocusedFollowupError("focused evidence projection is invalid")
    instances_by_id = _instances_by_id()
    records = []
    seen = set()
    for committed in projection["records"]:
        record = _attempt_record_from_committed(
            committed, store, schedule_by_coordinate, schedule_by_cell,
            authorization, instances_by_id,
        )
        if record is None:
            continue
        identity = (record["logical_cell_id"], record["repeat"])
        if identity in seen:
            raise FocusedFollowupError("focused physical attempt is duplicated")
        seen.add(identity)
        records.append(record)
    if len(records) > schedule["maximum_physical_attempts"]:
        raise FocusedFollowupError("focused physical attempt ceiling exceeded")
    return sorted(records, key=lambda item: (item["logical_cell_id"], item["repeat"]))


def validate_authorized_run_union(store, authorization, protocol=None):
    """Reject foreign or over-ceiling evidence in the shared focused run."""

    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    validate_authorization(authorization, protocol)
    _validate_store_metadata(store, authorization)
    schedules = build_schedules(authorization["model_digests"]["4b"], protocol)
    schedule_by_coordinate = {}
    schedule_by_cell = {}
    for block, schedule in schedules.items():
        if _digest(schedule) != authorization["schedule_digests"][block]:
            raise FocusedFollowupError("focused union schedule differs from authorization")
        for cell in schedule["records"]:
            coordinate = (
                cell["instance_id"], cell["condition"], cell["trial_seed"], cell["trial_index"],
            )
            if coordinate in schedule_by_coordinate or cell["logical_cell_id"] in schedule_by_cell:
                raise FocusedFollowupError("focused union schedule identity is duplicated")
            schedule_by_coordinate[coordinate] = cell
            schedule_by_cell[cell["logical_cell_id"]] = cell
    instances_by_id = _instances_by_id()
    projection = store.read_committed()
    records = projection.get("records") if isinstance(projection, dict) else None
    if not isinstance(records, list) or len(records) > authorization["maximum_physical_attempts"]:
        raise FocusedFollowupError("focused shared evidence physical ceiling drifted")
    seen = set()
    for committed in records:
        record = _attempt_record_from_committed(
            committed, store, schedule_by_coordinate, schedule_by_cell,
            authorization, instances_by_id,
        )
        if record is None:
            raise FocusedFollowupError("focused shared evidence contains a foreign attempt")
        identity = (record["logical_cell_id"], record["repeat"])
        if identity in seen:
            raise FocusedFollowupError("focused shared evidence physical attempt is duplicated")
        seen.add(identity)
    return len(records)


def _recovery_document(authorization, record, attested_at):
    _timestamp(attested_at, "focused recovery attestation time")
    if not (record["failure_origin"] == "environment" and record["repeat"] == 0 and record["retryable"]):
        raise FocusedFollowupError("focused recovery record is ineligible")
    document = {
        "schema_version": RECOVERY_SCHEMA,
        "authorization_sha256": authorization["authorization_sha256"],
        "logical_cell_id": record["logical_cell_id"],
        "repeat": 0,
        "trial_seed": record["trial_seed"],
        "evidence_sha256": record["evidence_sha256"],
        "health_verified": True,
        "same_seed_available": True,
        "attested_at": attested_at,
    }
    document["attestation_sha256"] = _digest(document)
    return validate_recovery_attestation(document, authorization, record)


def validate_recovery_attestation(document, authorization, record):
    expected = {
        "schema_version", "authorization_sha256", "logical_cell_id", "repeat",
        "trial_seed", "evidence_sha256", "health_verified", "same_seed_available",
        "attested_at", "attestation_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise FocusedFollowupError("focused recovery attestation has unexpected keys")
    unsigned = dict(document); supplied = unsigned.pop("attestation_sha256")
    if not isinstance(supplied, str) or supplied != _digest(unsigned):
        raise FocusedFollowupError("focused recovery attestation digest drifted")
    if (
        document["schema_version"] != RECOVERY_SCHEMA
        or document["authorization_sha256"] != authorization["authorization_sha256"]
        or document["logical_cell_id"] != record["logical_cell_id"]
        or document["repeat"] != 0 or document["trial_seed"] != record["trial_seed"]
        or document["evidence_sha256"] != record["evidence_sha256"]
        or document["health_verified"] is not True or document["same_seed_available"] is not True
    ):
        raise FocusedFollowupError("focused recovery attestation binding drifted")
    _timestamp(document["attested_at"], "focused recovery attestation time")
    return document


def _load_or_create_recovery_attestation(runs_root, authorization, run_id, record, health_check, attested_at=None):
    path = _recovery_artifact_path(runs_root, authorization, run_id, record["logical_cell_id"])
    if path.exists() or path.with_name(path.name + ".complete").exists():
        document = _load_published(path, "focused recovery attestation")
        return validate_recovery_attestation(document, authorization, record)
    health_check()
    document = _recovery_document(authorization, record, attested_at or _utcnow())
    _publish_marker_last(path, document)
    return document


def _final_attempts(schedule, attempts, authorization=None, runs_root=None, run_id=None):
    """Validate retry topology and return the terminal physical record per cell."""

    scheduled = {cell["logical_cell_id"]: cell for cell in schedule["records"]}
    by_cell = defaultdict(dict)
    for record in attempts:
        cell = scheduled.get(record.get("logical_cell_id"))
        if cell is None:
            raise FocusedFollowupError("focused attempt is unscheduled")
        validate_attempt_record(record, cell)
        if record["repeat"] in by_cell[record["logical_cell_id"]]:
            raise FocusedFollowupError("focused attempt repeat is duplicated")
        by_cell[record["logical_cell_id"]][record["repeat"]] = record
    final = {}
    missing = []
    invalid = []
    for logical_id, cell in scheduled.items():
        entries = by_cell.get(logical_id, {})
        first = entries.get(0)
        second = entries.get(1)
        if first is None:
            if second is not None:
                raise FocusedFollowupError("focused recovery exists without repeat zero")
            missing.append(logical_id); continue
        if second is not None:
            if not first["retryable"]:
                raise FocusedFollowupError("focused ineligible retry was executed")
            if authorization is not None:
                path = _recovery_artifact_path(runs_root, authorization, run_id, logical_id)
                attestation = _load_published(path, "focused recovery attestation")
                validate_recovery_attestation(attestation, authorization, first)
            final[logical_id] = second
        else:
            final[logical_id] = first
        if final[logical_id]["failure_origin"] not in ("none", "model"):
            invalid.append(logical_id)
    return final, missing, invalid


def _validate_block_start(document, authorization, schedule, run_id):
    expected = {
        "schema_version", "status", "authorization_sha256", "schedule_sha256",
        "run_id", "block", "scores_exposed", "started_at", "start_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise FocusedFollowupError("focused block start has unexpected keys")
    unsigned = dict(document)
    supplied = unsigned.pop("start_sha256")
    if not isinstance(supplied, str) or supplied != _digest(unsigned):
        raise FocusedFollowupError("focused block start digest drifted")
    if (
        document["schema_version"] != BLOCK_START_SCHEMA
        or document["status"] != "started_score_masked"
        or document["authorization_sha256"] != authorization["authorization_sha256"]
        or document["schedule_sha256"] != _digest(schedule)
        or document["run_id"] != run_id
        or document["block"] != schedule["phase"][8:]
        or document["scores_exposed"] is not False
    ):
        raise FocusedFollowupError("focused block start binding drifted")
    _timestamp(document["started_at"], "focused block start time")
    return document


def _load_or_publish_block_start(authorization, runs_root, run_id, block, started_at, protocol):
    """Persist the score-free boundary before the first model attempt.

    A resume must reuse this marker.  In particular, sealing cannot manufacture
    a later start time or a zero elapsed duration after an interrupted run.
    """

    schedule = build_schedule(block, authorization["model_digests"]["4b"], protocol)
    path = _block_start_artifact_path(runs_root, authorization, block)
    if path.exists() or path.with_name(path.name + ".complete").exists():
        return _validate_block_start(
            _load_published(path, "focused block start"), authorization, schedule, run_id,
        )
    _timestamp(started_at, "focused block start time")
    document = {
        "schema_version": BLOCK_START_SCHEMA,
        "status": "started_score_masked",
        "authorization_sha256": authorization["authorization_sha256"],
        "schedule_sha256": _digest(schedule),
        "run_id": run_id,
        "block": block,
        "scores_exposed": False,
        "started_at": started_at,
    }
    document["start_sha256"] = _digest(document)
    _validate_block_start(document, authorization, schedule, run_id)
    _publish_marker_last(path, document)
    return document


def _load_block_start(authorization, runs_root, run_id, block, protocol):
    schedule = build_schedule(block, authorization["model_digests"]["4b"], protocol)
    return _validate_block_start(
        _load_published(_block_start_artifact_path(runs_root, authorization, block), "focused block start"),
        authorization, schedule, run_id,
    )


def _validate_block_seal(document, authorization, schedule, run_id):
    expected = {
        "schema_version", "status", "authorization_sha256", "schedule_sha256",
        "run_id", "run_sha256", "block", "logical_cells_expected",
        "logical_cells_complete", "physical_attempts", "instrument_invalid_cells",
        "scores_exposed", "block_started_at", "block_finished_at", "block_elapsed_ms",
        "attempt_records_sha256", "seal_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise FocusedFollowupError("focused block seal has unexpected keys")
    unsigned = dict(document); supplied = unsigned.pop("seal_sha256")
    if not isinstance(supplied, str) or supplied != _digest(unsigned):
        raise FocusedFollowupError("focused block seal digest drifted")
    block = schedule["phase"][8:]
    if (
        document["schema_version"] != BLOCK_SEAL_SCHEMA
        or document["status"] != "sealed_complete_valid"
        or document["authorization_sha256"] != authorization["authorization_sha256"]
        or document["schedule_sha256"] != _digest(schedule)
        or document["run_id"] != run_id
        or document["block"] != block
        or document["logical_cells_expected"] != schedule["logical_cell_count"]
        or document["logical_cells_complete"] != schedule["logical_cell_count"]
        or document["instrument_invalid_cells"] != 0
        or document["scores_exposed"] is not False
    ):
        raise FocusedFollowupError("focused block seal binding drifted")
    _require_sha256(document["run_sha256"], "focused block run digest")
    _require_sha256(document["attempt_records_sha256"], "focused block attempt digest")
    if type(document["physical_attempts"]) is not int or not document["logical_cells_expected"] <= document["physical_attempts"] <= document["logical_cells_expected"] * 2:
        raise FocusedFollowupError("focused block physical-attempt count drifted")
    _timestamp(document["block_started_at"], "focused block start time")
    _timestamp(document["block_finished_at"], "focused block finish time")
    if type(document["block_elapsed_ms"]) is not int or document["block_elapsed_ms"] < 0:
        raise FocusedFollowupError("focused block elapsed time is invalid")
    return document


def seal_block(authorization, runs_root, run_id, block, protocol=None):
    """Validate all committed evidence and publish the score-free block marker last."""

    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    validate_authorization(authorization, protocol)
    if block not in BLOCKS:
        raise FocusedFollowupError("unknown focused block")
    schedule = build_schedule(block, authorization["model_digests"]["4b"], protocol)
    if _digest(schedule) != authorization["schedule_digests"][block]:
        raise FocusedFollowupError("focused block schedule differs from authorization")
    output = _block_artifact_path(runs_root, authorization, block)
    if output.exists() or output.with_name(output.name + ".complete").exists():
        return load_block_seal(authorization, runs_root, run_id, block, protocol)
    _require_seal_sequence(authorization, runs_root, run_id, block, protocol)
    _assert_execution_open(runs_root, authorization)
    store = EvidenceStore.open_run(runs_root, run_id)
    _validate_store_metadata(store, authorization)
    validate_authorized_run_union(store, authorization, protocol)
    attempts = extract_block_attempts(store, schedule, authorization)
    final, missing, invalid = _final_attempts(schedule, attempts, authorization, runs_root, run_id)
    if missing:
        raise FocusedFollowupError("focused block cannot seal with missing cells")
    if invalid:
        raise FocusedFollowupError("focused block cannot seal with instrument-invalid cells")
    if len(final) != schedule["logical_cell_count"]:
        raise FocusedFollowupError("focused block final-attempt count drifted")
    start = _load_block_start(authorization, runs_root, run_id, block, protocol)
    finished_at = _utcnow()
    elapsed_ms = int(round((_timestamp(finished_at, "focused block finish time") - _timestamp(
        start["started_at"], "focused block start time",
    )).total_seconds() * 1000))
    if elapsed_ms < 0:
        raise FocusedFollowupError("focused clock moved backward across the block boundary")
    document = {
        "schema_version": BLOCK_SEAL_SCHEMA,
        "status": "sealed_complete_valid",
        "authorization_sha256": authorization["authorization_sha256"],
        "schedule_sha256": _digest(schedule),
        "run_id": run_id,
        "run_sha256": store.run_sha256,
        "block": block,
        "logical_cells_expected": schedule["logical_cell_count"],
        "logical_cells_complete": len(final),
        "physical_attempts": len(attempts),
        "instrument_invalid_cells": 0,
        "scores_exposed": False,
        "block_started_at": start["started_at"],
        "block_finished_at": finished_at,
        "block_elapsed_ms": elapsed_ms,
        "attempt_records_sha256": _digest(attempts),
    }
    _timestamp(document["block_started_at"], "focused block start time")
    _timestamp(document["block_finished_at"], "focused block finish time")
    document["seal_sha256"] = _digest(document)
    _validate_block_seal(document, authorization, schedule, run_id)
    _publish_marker_last(output, document)
    return document


def load_block_seal(authorization, runs_root, run_id, block, protocol=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    schedule = build_schedule(block, authorization["model_digests"]["4b"], protocol)
    output = _block_artifact_path(runs_root, authorization, block)
    seal = _validate_block_seal(
        _load_published(output, "focused block seal"), authorization, schedule, run_id,
    )
    start = _load_block_start(authorization, runs_root, run_id, block, protocol)
    if seal["block_started_at"] != start["started_at"]:
        raise FocusedFollowupError("focused block seal start boundary drifted")
    elapsed = int(round((_timestamp(seal["block_finished_at"], "focused block finish time") - _timestamp(
        start["started_at"], "focused block start time",
    )).total_seconds() * 1000))
    if elapsed < 0:
        raise FocusedFollowupError("focused block seal finishes before its marker-last start")
    if seal["block_elapsed_ms"] != elapsed:
        raise FocusedFollowupError("focused block seal elapsed timing differs from marker-last boundaries")
    store = EvidenceStore.open_run(runs_root, run_id)
    _validate_store_metadata(store, authorization)
    validate_authorized_run_union(store, authorization, protocol)
    if seal["run_sha256"] != store.run_sha256:
        raise FocusedFollowupError("focused block seal run binding drifted")
    attempts = extract_block_attempts(store, schedule, authorization)
    final, missing, invalid = _final_attempts(schedule, attempts, authorization, runs_root, run_id)
    if missing or invalid or len(final) != schedule["logical_cell_count"]:
        raise FocusedFollowupError("focused block seal no longer has complete valid evidence")
    if seal["attempt_records_sha256"] != _digest(attempts):
        raise FocusedFollowupError("focused block seal attempt binding drifted")
    if seal["physical_attempts"] != len(attempts):
        raise FocusedFollowupError("focused block seal physical-attempt count drifted")
    return seal


def validate_block_seal(authorization, runs_root, run_id, block, protocol=None):
    """Public score-free verifier used by the supervisor before resuming a block."""

    return load_block_seal(authorization, runs_root, run_id, block, protocol)


def _validate_termination(document, authorization, schedule, run_id):
    expected = {
        "schema_version", "status", "authorization_sha256", "schedule_sha256",
        "run_id", "run_sha256", "block", "reason", "logical_cells_expected",
        "logical_cells_complete", "missing_cells", "instrument_invalid_cells",
        "scores_exposed", "terminated_at", "attempt_records_sha256", "termination_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise FocusedFollowupError("focused termination has unexpected keys")
    unsigned = dict(document); supplied = unsigned.pop("termination_sha256")
    if not isinstance(supplied, str) or supplied != _digest(unsigned):
        raise FocusedFollowupError("focused termination digest drifted")
    if (
        document["schema_version"] != TERMINATION_SCHEMA
        or document["status"] != "terminated_incomplete"
        or document["authorization_sha256"] != authorization["authorization_sha256"]
        or document["schedule_sha256"] != _digest(schedule)
        or document["run_id"] != run_id
        or document["block"] != schedule["phase"][8:]
        or document["reason"] not in ("deadline", "B2_start_cutoff", "environment_failure", "instrument_failure")
        or document["logical_cells_expected"] != schedule["logical_cell_count"]
        or document["scores_exposed"] is not False
    ):
        raise FocusedFollowupError("focused termination binding drifted")
    for field in ("run_sha256", "attempt_records_sha256"):
        _require_sha256(document[field], "focused termination " + field)
    for field in ("logical_cells_complete", "missing_cells", "instrument_invalid_cells"):
        if type(document[field]) is not int or document[field] < 0:
            raise FocusedFollowupError("focused termination count is invalid")
    if document["logical_cells_complete"] + document["missing_cells"] != document["logical_cells_expected"]:
        raise FocusedFollowupError("focused termination completion counts drifted")
    _timestamp(document["terminated_at"], "focused termination time")
    return document


def _open_termination_store(authorization, runs_root, run_id, block, reason, timestamp):
    """Open immutable evidence for termination, with one narrowly safe empty-run case.

    A hard-stop that arrives before B1a begins still needs a marker-last terminal
    disposition: otherwise the required recovered-only report cannot be issued.
    There is no inference in that case, so we may create *only* the exact
    authorization-bound empty EvidenceStore.  Every other termination reason
    and phase must be grounded in already-published evidence.
    """

    _require_component(run_id, "focused run id")
    if run_id != authorization["run_id"]:
        raise FocusedFollowupError("focused run id differs from authorization")
    run_dir = Path(runs_root) / run_id
    empty_b1a_deadline = (
        reason == "deadline"
        and block == "B1a"
        and timestamp >= _timestamp(authorization["cutoffs"]["hard_stop"], "focused hard stop")
    )
    # ``lexists`` prevents a dangling symlink or malformed pre-existing run
    # from being mistaken for an absent store and replaced with fresh state.
    if empty_b1a_deadline and not os.path.lexists(os.fspath(run_dir)):
        return _open_or_create_store(runs_root, run_id, authorization)
    return EvidenceStore.open_run(runs_root, run_id)


def terminate_block(authorization, runs_root, run_id, block, reason, terminated_at=None, protocol=None):
    """Publish a score-free, evidence-derived terminal incomplete marker.

    Operators cannot declare an arbitrary failure reason: deadline requires the
    frozen hard stop; environment/instrument reasons are derived from terminal
    evidence for the exact reconstructed schedule.
    """

    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    validate_authorization(authorization, protocol)
    if block not in BLOCKS:
        raise FocusedFollowupError("unknown focused block")
    schedule = build_schedule(block, authorization["model_digests"]["4b"], protocol)
    output = _termination_artifact_path(runs_root, authorization, block)
    if output.exists() or output.with_name(output.name + ".complete").exists():
        return load_termination(authorization, runs_root, run_id, block, protocol)
    if _block_artifact_path(runs_root, authorization, block).exists():
        raise FocusedFollowupError("a sealed complete block cannot be terminated")
    _require_prior_block_seals(authorization, runs_root, run_id, block, protocol)
    _assert_execution_open(runs_root, authorization)
    timestamp = _timestamp(terminated_at or _utcnow(), "focused termination time")
    store = _open_termination_store(
        authorization, runs_root, run_id, block, reason, timestamp,
    )
    _validate_store_metadata(store, authorization)
    validate_authorized_run_union(store, authorization, protocol)
    attempts = extract_block_attempts(store, schedule, authorization)
    final, missing, invalid = _final_attempts(schedule, attempts, authorization, runs_root, run_id)
    final_invalid = [final[cell] for cell in invalid]
    if reason == "deadline":
        if timestamp < _timestamp(authorization["cutoffs"]["hard_stop"], "focused hard stop"):
            raise FocusedFollowupError("deadline termination cannot precede the authorized hard stop")
        if not missing or invalid:
            raise FocusedFollowupError("deadline termination requires an incomplete block")
    elif reason == "B2_start_cutoff":
        if block != "B2" or timestamp < _timestamp(authorization["cutoffs"]["B2_start_cutoff"], "focused B2 cutoff"):
            raise FocusedFollowupError("B2 cutoff termination is not eligible")
        b1b_seal = load_block_seal(authorization, runs_root, run_id, "B1b", protocol)
        if _timestamp(b1b_seal["block_finished_at"], "B1b block finish time") <= _timestamp(
            authorization["cutoffs"]["B2_start_cutoff"], "focused B2 cutoff",
        ):
            raise FocusedFollowupError("B2 cutoff cannot skip a B2 made eligible by timely B1 sealing")
        if final or invalid:
            raise FocusedFollowupError("B2 cutoff termination requires no B2 execution")
    elif reason == "environment_failure":
        if len(final_invalid) != 1 or any(item["failure_origin"] != "environment" for item in final_invalid):
            raise FocusedFollowupError("environment termination requires an isolated terminal environment failure")
    elif reason == "instrument_failure":
        if not final_invalid or not any(item["failure_origin"] == "instrument" for item in final_invalid):
            raise FocusedFollowupError("instrument termination requires terminal instrument failure evidence")
    else:
        raise FocusedFollowupError("focused termination reason is invalid")
    document = {
        "schema_version": TERMINATION_SCHEMA,
        "status": "terminated_incomplete",
        "authorization_sha256": authorization["authorization_sha256"],
        "schedule_sha256": _digest(schedule),
        "run_id": run_id,
        "run_sha256": store.run_sha256,
        "block": block,
        "reason": reason,
        "logical_cells_expected": schedule["logical_cell_count"],
        "logical_cells_complete": len(final),
        "missing_cells": len(missing),
        "instrument_invalid_cells": len(invalid),
        "scores_exposed": False,
        "terminated_at": timestamp.isoformat(),
        "attempt_records_sha256": _digest(attempts),
    }
    document["termination_sha256"] = _digest(document)
    _validate_termination(document, authorization, schedule, run_id)
    _publish_marker_last(output, document)
    return document


def load_termination(authorization, runs_root, run_id, block, protocol=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    schedule = build_schedule(block, authorization["model_digests"]["4b"], protocol)
    output = _termination_artifact_path(runs_root, authorization, block)
    document = _validate_termination(
        _load_published(output, "focused termination"), authorization, schedule, run_id,
    )
    store = EvidenceStore.open_run(runs_root, run_id)
    _validate_store_metadata(store, authorization)
    validate_authorized_run_union(store, authorization, protocol)
    if document["run_sha256"] != store.run_sha256:
        raise FocusedFollowupError("focused termination run binding drifted")
    attempts = extract_block_attempts(store, schedule, authorization)
    if document["attempt_records_sha256"] != _digest(attempts):
        raise FocusedFollowupError("focused termination attempt binding drifted")
    final, missing, invalid = _final_attempts(schedule, attempts, authorization, runs_root, run_id)
    if (
        document["logical_cells_complete"] != len(final)
        or document["missing_cells"] != len(missing)
        or document["instrument_invalid_cells"] != len(invalid)
    ):
        raise FocusedFollowupError("focused termination counts differ from evidence")
    timestamp = _timestamp(document["terminated_at"], "focused termination time")
    invalid_records = [final[cell] for cell in invalid]
    if document["reason"] == "deadline":
        if timestamp < _timestamp(authorization["cutoffs"]["hard_stop"], "focused hard stop") or not missing or invalid:
            raise FocusedFollowupError("focused deadline termination is not evidence-derived")
    elif document["reason"] == "B2_start_cutoff":
        b1b_seal = load_block_seal(authorization, runs_root, run_id, "B1b", protocol)
        if (
            block != "B2" or timestamp < _timestamp(authorization["cutoffs"]["B2_start_cutoff"], "focused B2 cutoff")
            or _timestamp(b1b_seal["block_finished_at"], "B1b block finish time") <= _timestamp(
                authorization["cutoffs"]["B2_start_cutoff"], "focused B2 cutoff",
            )
            or final or invalid
        ):
            raise FocusedFollowupError("focused B2 cutoff termination is not evidence-derived")
    elif document["reason"] == "environment_failure":
        if len(invalid_records) != 1 or invalid_records[0]["failure_origin"] != "environment":
            raise FocusedFollowupError("focused environment termination is not evidence-derived")
    elif document["reason"] == "instrument_failure":
        if not invalid_records or not any(item["failure_origin"] == "instrument" for item in invalid_records):
            raise FocusedFollowupError("focused instrument termination is not evidence-derived")
    return document


def _hard_stop_reached(authorization, now):
    now = _timestamp(now, "focused current time")
    return now >= _timestamp(authorization["cutoffs"]["hard_stop"], "focused hard stop")


def _require_prior_block_seals(authorization, runs_root, run_id, block, protocol):
    required = ()
    if block == "B1b":
        required = ("B1a",)
    elif block == "B2":
        required = ("B1a", "B1b")
    for previous in required:
        load_block_seal(authorization, runs_root, run_id, previous, protocol)


def _require_b2_eligibility(authorization, runs_root, run_id, protocol):
    b1b_seal = load_block_seal(authorization, runs_root, run_id, "B1b", protocol)
    if _timestamp(b1b_seal["block_finished_at"], "B1b block finish time") > _timestamp(
        authorization["cutoffs"]["B2_start_cutoff"], "focused B2 cutoff",
    ):
        raise FocusedFollowupError("focused B2 is ineligible because B1 sealed after its cutoff")


def _require_seal_sequence(authorization, runs_root, run_id, block, protocol):
    _require_prior_block_seals(authorization, runs_root, run_id, block, protocol)
    if block == "B2":
        _require_b2_eligibility(authorization, runs_root, run_id, protocol)


def _require_start_eligibility(authorization, runs_root, run_id, block, now, protocol):
    _require_seal_sequence(authorization, runs_root, run_id, block, protocol)
    if _hard_stop_reached(authorization, now):
        raise FocusedFollowupError("focused hard stop reached before starting block")


def _instances_by_id():
    records = {}
    for manifest in load_manifests(ROOT):
        validate_manifest(manifest)
        for instance in manifest["instances"]:
            instance_id = instance["content"]["id"]
            if instance_id in records:
                raise FocusedFollowupError("focused instance identity is duplicated across manifests")
            records[instance_id] = instance
    return records


def _validated_outcomes():
    document = load_canonical_json(VALIDATED_OUTCOMES_PATH)
    manifests = load_manifests(ROOT)
    validate_validated_outcomes(document, manifests)
    outcomes = {item["instance_id"]: item for item in document["records"]}
    if len(outcomes) != len(document["records"]):
        raise FocusedFollowupError("focused validated outcome identity is duplicated")
    return outcomes


def _execute_cell(store, authorization, preflight, cell, instance, outcome):
    """Reuse the frozen producer exactly; only scheduling and evidence seals differ."""

    validate_office_instance_v2(instance)
    implementation = _live._implementation_sha256()
    condition, protocol = _live._condition(cell["condition"], implementation)
    protocol["primary_model"] = _live.MODEL_TAGS["4b"]
    validate_execution_protocol(protocol)
    transport = OllamaTransport(
        protocol["transport"]["endpoint"], protocol["transport"]["request_timeout_seconds"],
    )
    key0 = _live._attempt_key(
        instance, cell, condition, protocol, protocol["primary_model"],
        authorization["model_digests"]["4b"], 0, preflight,
    )
    first = store.execute_or_resume(
        key0, _live._producer(instance, outcome, cell, condition, protocol, transport),
    )
    if first.state != "committed":
        raise FocusedFollowupError("focused attempt did not publish marker-last evidence")
    final = first.record
    if final["failure_origin"] != "environment":
        return final
    failure = final["result"].get("failure")
    retryable = isinstance(failure, dict) and failure.get("retryable") is True
    if not retryable:
        return final
    schedule = {cell["logical_cell_id"]: cell}
    record = _attempt_record_from_committed(
        final, store,
        {(cell["instance_id"], cell["condition"], cell["trial_seed"], cell["trial_index"]): cell},
        schedule, authorization, {cell["instance_id"]: instance},
    )
    def health_check():
        transport.verify_health(protocol, {
            "ollama": {
                "version": protocol["f0_binding"]["ollama_version"],
                "model_digest": "sha256:" + authorization["model_digests"]["4b"],
            },
        })
    # A resumed cell reuses a validated marker-last attestation when it exists;
    # an absent attestation means the prior process stopped before it could be
    # published, so health is verified once before it is created.
    _load_or_create_recovery_attestation(
        store.runs_root, authorization, store.run_id, record, health_check,
    )
    key1 = _live._attempt_key(
        instance, cell, condition, protocol, protocol["primary_model"],
        authorization["model_digests"]["4b"], 1, preflight,
    )
    second = store.execute_or_resume(
        key1, _live._producer(instance, outcome, cell, condition, protocol, transport),
    )
    if second.state != "committed":
        raise FocusedFollowupError("focused recovery attempt did not publish marker-last evidence")
    return second.record


def run_block(
    authorization, runs_root, run_id, block, supervisor_path,
    preflight=None, now=None, protocol=None, preflight_provider=None, lease_path=None,
):
    """Execute or resume one score-masked block and then seal it marker-last."""

    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    validate_authorization(authorization, protocol)
    if block not in BLOCKS:
        raise FocusedFollowupError("unknown focused block")
    now = now or _utcnow()
    _assert_execution_open(runs_root, authorization)
    seal_path = _block_artifact_path(runs_root, authorization, block)
    if seal_path.exists() or seal_path.with_name(seal_path.name + ".complete").exists():
        return load_block_seal(authorization, runs_root, run_id, block, protocol)
    termination_path = _termination_artifact_path(runs_root, authorization, block)
    if termination_path.exists() or termination_path.with_name(termination_path.name + ".complete").exists():
        load_termination(authorization, runs_root, run_id, block, protocol)
        raise FocusedFollowupError("focused block has a sealed terminal incomplete marker")
    _require_start_eligibility(authorization, runs_root, run_id, block, now, protocol)
    lease = BenchmarkLease(lease_path)
    lease.acquire(authorization["authorization_sha256"])
    try:
        # The machine-wide lease covers every live phase check and the first
        # marker written for the block, not merely the model requests.
        current = validate_current_environment(
            authorization, preflight, supervisor_path, protocol, preflight_provider,
        )
        schedule = build_schedule(block, authorization["model_digests"]["4b"], protocol)
        if _digest(schedule) != authorization["schedule_digests"][block]:
            raise FocusedFollowupError("focused execution schedule differs from authorization")
        store = _open_or_create_store(runs_root, run_id, authorization)
        _validate_store_metadata(store, authorization)
        validate_authorized_run_union(store, authorization, protocol)
        _load_or_publish_block_start(
            authorization, runs_root, run_id, block, _utcnow(), protocol,
        )
        instances = _instances_by_id()
        outcomes = _validated_outcomes()
        emitted = []
        for cell in schedule["records"]:
            if _hard_stop_reached(authorization, _utcnow()):
                terminate_block(
                    authorization, runs_root, run_id, block, "deadline", _utcnow(), protocol,
                )
                raise FocusedFollowupError("focused hard stop reached with block incomplete")
            instance = instances.get(cell["instance_id"])
            outcome = outcomes.get(cell["instance_id"])
            if instance is None or outcome is None or instance["content_sha256"] != cell["content_sha256"]:
                raise FocusedFollowupError("focused scheduled instance or outcome binding drifted")
            final = _execute_cell(store, authorization, current, cell, instance, outcome)
            instrument_valid = final["failure_origin"] in {"none", "model"}
            event = {
                "event": "cell_complete", "block": block,
                "logical_cell_id": cell["logical_cell_id"], "family": cell["family"],
                "instrument_valid": instrument_valid,
            }
            emitted.append(event)
            print(json.dumps(event, sort_keys=True), flush=True)
            if not instrument_valid:
                attempts = extract_block_attempts(store, schedule, authorization)
                terminal, _missing, invalid = _final_attempts(
                    schedule, attempts, authorization, runs_root, run_id,
                )
                invalid_records = [terminal[item] for item in invalid]
                if any(item["failure_origin"] == "instrument" for item in invalid_records):
                    terminate_block(
                        authorization, runs_root, run_id, block, "instrument_failure", protocol=protocol,
                    )
                elif len(invalid_records) == 1 and invalid_records[0]["failure_origin"] == "environment":
                    terminate_block(
                        authorization, runs_root, run_id, block, "environment_failure", protocol=protocol,
                    )
                else:
                    raise FocusedFollowupError("focused terminal invalid evidence has no eligible termination class")
                raise FocusedFollowupError("focused block stopped after terminal invalid evidence")
        if len(emitted) != schedule["logical_cell_count"]:
            raise FocusedFollowupError("focused executor did not visit the complete schedule")
        store.read_committed()
        validate_current_environment(
            authorization, None, supervisor_path, protocol, preflight_provider,
        )
        try:
            # ``seal_block`` reloads the immutable score-free start boundary.
            return seal_block(authorization, runs_root, run_id, block, protocol=protocol)
        except FocusedFollowupError:
            attempts = extract_block_attempts(store, schedule, authorization)
            final, _missing, invalid = _final_attempts(schedule, attempts, authorization, runs_root, run_id)
            if len(invalid) == 1 and all(final[item]["failure_origin"] == "environment" for item in invalid):
                terminate_block(authorization, runs_root, run_id, block, "environment_failure", protocol=protocol)
            elif invalid and any(final[item]["failure_origin"] == "instrument" for item in invalid):
                terminate_block(authorization, runs_root, run_id, block, "instrument_failure", protocol=protocol)
            raise
    finally:
        lease.release()


def _seed_index(protocol_digest_value, analysis_label, replicate, family, draw, population):
    if population < 1:
        raise FocusedFollowupError("bootstrap population is empty")
    limit = (1 << 256) - ((1 << 256) % population)
    counter = 0
    while True:
        payload = "|".join((
            protocol_digest_value, "bootstrap", analysis_label, str(replicate),
            family, str(draw), str(counter),
        ))
        value = int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest(), "big")
        if value < limit:
            return value % population
        counter += 1


def _bootstrap_interval(family_differences, protocol_digest_value, analysis_label, replicates=50000):
    if type(replicates) is not int or replicates < 1:
        raise FocusedFollowupError("bootstrap replicate count is invalid")
    families = sorted(family_differences)
    if not families:
        raise FocusedFollowupError("bootstrap requires at least one family")
    # A stratified bootstrap is exactly degenerate when every family has a
    # constant within-family difference.  Preserve the frozen sampling audit
    # (the first min(100, R) index vectors are still generated byte-for-byte),
    # but do not spend R identical arithmetic draws.  This is an exact
    # identity, not an approximation; the ordinary nonconstant path below is
    # intentionally unchanged.
    constants = {}
    for family in families:
        differences = family_differences[family]
        if not differences:
            raise FocusedFollowupError("bootstrap family has no clusters")
        first = differences[0]
        if any(value != first for value in differences[1:]):
            constants = None
            break
        constants[family] = first
    if constants is not None:
        first_hundred = []
        for replicate in range(min(100, replicates)):
            vector = []
            for family in families:
                population = len(family_differences[family])
                selected = [
                    _seed_index(protocol_digest_value, analysis_label, replicate, family, draw, population)
                    for draw in range(population)
                ]
                vector.append({"family": family, "indices": selected})
            first_hundred.append(vector)
        constant_effect = sum(constants.values(), Fraction(0, 1)) / len(constants)
        return {
            "replicates": replicates,
            "sampling": "exact-uniform SHA-256 rejection sampling",
            "interval": "two-sided percentile nearest-rank 0.025 and 0.975",
            "lower": constant_effect,
            "upper": constant_effect,
            "first_100_index_vectors_sha256": _digest(first_hundred),
        }
    first_hundred = []
    values = []
    for replicate in range(replicates):
        family_means = []
        vector = []
        for family in families:
            differences = family_differences[family]
            if not differences:
                raise FocusedFollowupError("bootstrap family has no clusters")
            selected = []
            for draw in range(len(differences)):
                index = _seed_index(protocol_digest_value, analysis_label, replicate, family, draw, len(differences))
                selected.append(index)
            if replicate < 100:
                vector.append({"family": family, "indices": selected})
            family_means.append(sum((differences[index] for index in selected), Fraction(0, 1)) / len(selected))
        if replicate < 100:
            first_hundred.append(vector)
        values.append(sum(family_means, Fraction(0, 1)) / len(family_means))
    values.sort()
    lower = values[math.ceil(Fraction(25, 1000) * replicates) - 1]
    upper = values[math.ceil(Fraction(975, 1000) * replicates) - 1]
    return {
        "replicates": replicates,
        "sampling": "exact-uniform SHA-256 rejection sampling",
        "interval": "two-sided percentile nearest-rank 0.025 and 0.975",
        "lower": lower,
        "upper": upper,
        "first_100_index_vectors_sha256": _digest(first_hundred),
    }


def _recovered_calibration_seed_index(replicate, family, draw):
    """Frozen modulo generator for the completed 8-cluster calibration run.

    Eight divides 2**256, so this exact legacy/recovery generator is uniform
    without rejection sampling.  It intentionally differs from the focused
    follow-up's general rejection-sampled generator.
    """

    payload = "|".join(("office-v2.3.0-exploratory", str(replicate), family, str(draw)))
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest(), "big") % 8


def _recovered_calibration_bootstrap_interval(family_differences, replicates=50000):
    if type(replicates) is not int or replicates < 1:
        raise FocusedFollowupError("recovered calibration bootstrap replicate count is invalid")
    families = sorted(family_differences)
    if not families or any(len(family_differences[family]) != 8 for family in families):
        raise FocusedFollowupError("recovered calibration bootstrap requires eight clusters per family")
    first_hundred = []
    values = []
    for replicate in range(replicates):
        family_means = []
        vector = []
        for family in families:
            selected = [
                _recovered_calibration_seed_index(replicate, family, draw)
                for draw in range(8)
            ]
            if replicate < 100:
                vector.append({"family": family, "indices": selected})
            differences = family_differences[family]
            family_means.append(sum((differences[index] for index in selected), Fraction(0, 1)) / 8)
        if replicate < 100:
            first_hundred.append(vector)
        values.append(sum(family_means, Fraction(0, 1)) / len(family_means))
    values.sort()
    return {
        "replicates": replicates,
        "sampling": "exact-uniform SHA-256 modulo 8",
        "interval": "two-sided percentile nearest-rank 0.025 and 0.975",
        "lower": values[math.ceil(Fraction(25, 1000) * replicates) - 1],
        "upper": values[math.ceil(Fraction(975, 1000) * replicates) - 1],
        "first_100_index_vectors_sha256": _digest(first_hundred),
    }


def _sign_flip(differences):
    nonzero = [Fraction(value) for value in differences if value]
    observed = abs(sum(nonzero, Fraction(0, 1)))
    count = len(nonzero)
    if count == 0:
        return {"nonzero_clusters": 0, "two_sided_p": Fraction(1, 1), "method": "exact sign-flip"}
    denominator_lcm = 1
    for value in nonzero:
        denominator_lcm = math.lcm(denominator_lcm, value.denominator)
    weights = [abs(value.numerator * (denominator_lcm // value.denominator)) for value in nonzero]
    observed_scaled = abs(observed.numerator * (denominator_lcm // observed.denominator))
    distribution = {0: 1}
    for weight in weights:
        updated = defaultdict(int)
        for total, multiplicity in distribution.items():
            updated[total + weight] += multiplicity
            updated[total - weight] += multiplicity
        distribution = dict(updated)
    numerator = sum(
        multiplicity for total, multiplicity in distribution.items()
        if abs(total) >= observed_scaled
    )
    denominator = 1 << count
    return {
        "nonzero_clusters": count,
        "two_sided_p": Fraction(numerator, denominator),
        "method": "exact sign-flip dynamic programming",
    }


def _variance_records(family_differences):
    values = [value for family in sorted(family_differences) for value in family_differences[family]]
    if not values:
        raise FocusedFollowupError("variance needs cluster differences")
    mean = sum(values, Fraction(0, 1)) / len(values)
    pooled = (
        sum(((value - mean) ** 2 for value in values), Fraction(0, 1)) / (len(values) - 1)
        if len(values) > 1 else Fraction(0, 1)
    )
    stratified = Fraction(0, 1)
    families = sorted(family_differences)
    for family in families:
        items = family_differences[family]
        family_mean = sum(items, Fraction(0, 1)) / len(items)
        sample_var = (
            sum(((value - family_mean) ** 2 for value in items), Fraction(0, 1)) / (len(items) - 1)
            if len(items) > 1 else Fraction(0, 1)
        )
        stratified += sample_var / len(items)
    stratified /= len(families) ** 2
    return {
        "pooled_cluster_difference_sample_variance": pooled,
        "stratified_variance_of_equal_family_estimator": stratified,
        "stratified_standard_error": Fraction.from_float(math.sqrt(float(stratified))).limit_denominator(10 ** 12),
    }


def _claim(delta, lower, upper, protocol):
    threshold = Fraction(12, 100)
    if delta >= threshold and lower > 0:
        return "harness_superiority"
    if delta <= -threshold and upper < 0:
        return "native_superiority"
    return "no_directional_superiority_claim"


def _analyze_paired_records(
    records, label, protocol, repeats_per_condition, *, bootstrap_builder=None,
    issue_directional_claim=True,
):
    """Analyze complete final attempts; no externally supplied claim is accepted."""

    by_cluster = defaultdict(dict)
    for record, cell in records:
        key = (cell["family"], cell["instance_id"])
        condition = cell["condition"]
        trial = cell["trial_index"]
        if trial in by_cluster[key].setdefault(condition, {}):
            raise FocusedFollowupError("focused analysis has duplicate condition trial")
        by_cluster[key][condition][trial] = record
    family_differences = defaultdict(list)
    condition_success = {condition: [] for condition in CONDITIONS}
    cap_by_condition = {condition: [] for condition in CONDITIONS}
    cap_patterns = Counter()
    resource_by_condition = {condition: [] for condition in CONDITIONS}
    all_cluster_diffs = []
    expected_trials = tuple(sorted(repeats_per_condition))
    for (family, instance_id), condition_records in sorted(by_cluster.items()):
        if set(condition_records) != set(CONDITIONS):
            raise FocusedFollowupError("focused analysis cluster lacks a condition")
        values = {}
        caps = {}
        for condition in CONDITIONS:
            trials = condition_records[condition]
            if tuple(sorted(trials)) != expected_trials:
                raise FocusedFollowupError("focused analysis cluster trial set drifted")
            chosen = [trials[trial] for trial in expected_trials]
            if any(item["failure_origin"] not in ("none", "model") for item in chosen):
                raise FocusedFollowupError("focused analysis contains invalid attempt")
            values[condition] = sum((Fraction(int(item["strict_success"]), 1) for item in chosen), Fraction(0, 1)) / len(chosen)
            caps[condition] = any(item["model_calls"] >= 18 for item in chosen)
            condition_success[condition].append(values[condition])
            cap_by_condition[condition].append((caps[condition], values[condition]))
            resource_by_condition[condition].extend(chosen)
        diff = values["harness_full"] - values["native_tools"]
        family_differences[family].append(diff)
        all_cluster_diffs.append(diff)
        cap_patterns[(caps["harness_full"], caps["native_tools"])] += 1
    families = sorted(family_differences)
    if not families:
        raise FocusedFollowupError("focused analysis has no paired clusters")
    family_effects = {
        family: sum(family_differences[family], Fraction(0, 1)) / len(family_differences[family])
        for family in families
    }
    delta = sum(family_effects.values(), Fraction(0, 1)) / len(family_effects)
    if bootstrap_builder is None:
        bootstrap = _bootstrap_interval(family_differences, protocol_sha256(protocol), label)
    else:
        bootstrap = bootstrap_builder(family_differences)
    lofo = []
    for family in families:
        excluded = (len(families) * delta - family_effects[family]) / (len(families) - 1) if len(families) > 1 else delta
        lofo.append({
            "excluded_family": family,
            "clusters": sum(len(values) for other, values in family_differences.items() if other != family),
            "paired_effect": excluded,
            "shift_from_all_family": excluded - delta,
        })
    cap_report = {}
    for condition in CONDITIONS:
        entries = cap_by_condition[condition]
        cap_count = sum(flag for flag, _value in entries)
        capped = [value for flag, value in entries if flag]
        uncapped = [value for flag, value in entries if not flag]
        cap_report[condition] = {
            "clusters": len(entries),
            "cap_hit_clusters": cap_count,
            "cap_hit_rate": Fraction(cap_count, len(entries)),
            "capped_successes": sum(capped, Fraction(0, 1)),
            "capped_clusters": len(capped),
            "uncapped_successes": sum(uncapped, Fraction(0, 1)),
            "uncapped_clusters": len(uncapped),
        }
    resource_report = {}
    for condition in CONDITIONS:
        entries = resource_by_condition[condition]
        exact_entries = [item for item in entries if item["generated_tokens_exact"] is not None]
        bound_entries = [item for item in entries if item["generated_tokens_exact"] is None]
        resource_report[condition] = {
            "attempts": len(entries),
            "total_model_calls": sum(item["model_calls"] for item in entries),
            "mean_model_calls": Fraction(sum(item["model_calls"] for item in entries), len(entries)),
            "mean_successful_reads": Fraction(sum(item["successful_reads"] for item in entries), len(entries)),
            "mean_successful_mutations": Fraction(sum(item["successful_mutations"] for item in entries), len(entries)),
            "generated_tokens_exact_attempts": len(exact_entries),
            "generated_tokens_bound_only_attempts": len(bound_entries),
            "generated_tokens_exact_total_for_exact_attempts": sum(
                item["generated_tokens_exact"] for item in exact_entries
            ),
            "generated_tokens_lower_bound_total_for_bound_only_attempts": sum(
                item["generated_tokens_lower_bound"] for item in bound_entries
            ),
            "generated_tokens_upper_bound_total_for_bound_only_attempts": (
                None if any(item["generated_tokens_upper_bound"] is None for item in bound_entries)
                else sum(item["generated_tokens_upper_bound"] for item in bound_entries)
            ),
        }
    document = {
        "label": label,
        "families": families,
        "clusters": len(by_cluster),
        "trials_per_condition": len(expected_trials),
        "condition_success": {
            condition: sum(values, Fraction(0, 1)) / len(values)
            for condition, values in condition_success.items()
        },
        "paired_effect": delta,
        "interval": bootstrap,
        "family_effects": family_effects,
        "leave_one_family_out": lofo,
        "variance": _variance_records(family_differences),
        "sign_flip": _sign_flip(all_cluster_diffs),
        "cap_report": cap_report,
        "cap_patterns": {
            "neither_cap_hit": cap_patterns[(False, False)],
            "harness_full_only_cap_hit": cap_patterns[(True, False)],
            "native_tools_only_cap_hit": cap_patterns[(False, True)],
            "both_conditions_cap_hit": cap_patterns[(True, True)],
        },
        "resource_report": resource_report,
    }
    if issue_directional_claim:
        document["claim"] = _claim(delta, bootstrap["lower"], bootstrap["upper"], protocol)
    return document


def _jsonify_analysis(value):
    if isinstance(value, Fraction):
        return {"fraction": _fraction_text(value), "decimal": _decimal_text(value)}
    if isinstance(value, Counter):
        return {str(key): _jsonify_analysis(member) for key, member in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, dict):
        return {key: _jsonify_analysis(member) for key, member in value.items()}
    if isinstance(value, list):
        return [_jsonify_analysis(member) for member in value]
    if isinstance(value, tuple):
        return [_jsonify_analysis(member) for member in value]
    return value


def _recovered_cluster_reliability(rows):
    """Return only aggregate two-trial reliability summaries, never raw cells."""

    by_cluster = defaultdict(lambda: defaultdict(dict))
    for record, cell in rows:
        by_cluster[(cell["family"], cell["instance_id"])][cell["condition"]][cell["trial_index"]] = record
    result = {}
    for condition in CONDITIONS:
        values = []
        for condition_records in by_cluster.values():
            trials = condition_records[condition]
            if tuple(sorted(trials)) != (0, 1):
                raise FocusedFollowupError("recovered calibration reliability trial topology drifted")
            values.append(tuple(bool(trials[index]["strict_success"]) for index in (0, 1)))
        result[condition] = {
            "clusters": len(values),
            "pass_at_2": Fraction(sum(any(value) for value in values), len(values)),
            "pass_pow_2": Fraction(sum(all(value) for value in values), len(values)),
        }
    return result


def _recovered_in_band_effect(rows):
    wanted = ("cal_freeslot", "pptx_basic", "remind_msg")
    by_cluster = defaultdict(lambda: defaultdict(dict))
    for record, cell in rows:
        if cell["family"] in wanted:
            by_cluster[(cell["family"], cell["instance_id"])][cell["condition"]][cell["trial_index"]] = record
    by_family = defaultdict(list)
    for (family, _instance_id), conditions in by_cluster.items():
        if set(conditions) != set(CONDITIONS) or any(tuple(sorted(conditions[item])) != (0, 1) for item in CONDITIONS):
            raise FocusedFollowupError("recovered calibration in-band topology drifted")
        values = {
            condition: sum((Fraction(int(conditions[condition][trial]["strict_success"]), 1) for trial in (0, 1)), Fraction(0, 1)) / 2
            for condition in CONDITIONS
        }
        by_family[family].append(values["harness_full"] - values["native_tools"])
    if tuple(sorted(by_family)) != tuple(sorted(wanted)) or any(len(by_family[family]) != 8 for family in wanted):
        raise FocusedFollowupError("recovered calibration in-band family allocation drifted")
    family_effects = {
        family: sum(by_family[family], Fraction(0, 1)) / len(by_family[family])
        for family in wanted
    }
    return {
        "families": list(wanted),
        "clusters": 24,
        "equal_family_paired_effect": sum(family_effects.values(), Fraction(0, 1)) / len(family_effects),
        "family_effects": family_effects,
        "descriptive_only": True,
    }


def _rebuild_recovered_calibration_components(protocol):
    """Re-extract the original marker-last evidence for validation and reporting."""

    base = _load_base_program_authorization()
    selection = _validate_combined_calibration_selection(protocol)
    try:
        plan = load_canonical_json(EXPLORATORY_PLAN_PATH)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise FocusedFollowupError("exploratory calibration plan is unreadable") from exc
    if (
        not isinstance(plan, dict)
        or plan.get("schema_version") != "brick.next-study.exploratory-analysis-plan/1"
        or plan.get("classification") != "retrospective_descriptive_context"
        or plan.get("inputs", {}).get("run_id") != CALIBRATION_RUN_ID
        or plan.get("inputs", {}).get("authorization_sha256") != base["authorization_sha256"]
    ):
        raise FocusedFollowupError("exploratory calibration plan binding drifted")
    schedule = load_canonical_json(CALIBRATION_SCHEDULE_PATH)
    manifest = load_canonical_json(CALIBRATION_MANIFEST_PATH)
    try:
        validate_phase_schedule(schedule, manifest)
    except (TypeError, ValueError) as exc:
        raise FocusedFollowupError("sealed calibration schedule is invalid") from exc
    if plan["inputs"].get("calibration_schedule_sha256") != _digest(schedule):
        raise FocusedFollowupError("exploratory calibration plan schedule binding drifted")
    store = EvidenceStore.open_run(CALIBRATION_RUNS_ROOT, CALIBRATION_RUN_ID)
    attempts = extract_attempt_records(store, schedule, authorization_sha256=base["authorization_sha256"])
    try:
        pending = _base_resume_queue(schedule, attempts)
    except (TypeError, ValueError) as exc:
        raise FocusedFollowupError("recovered calibration attempt topology is invalid") from exc
    if pending:
        raise FocusedFollowupError("recovered calibration requires all 352 completed cells")
    cells = {cell["logical_cell_id"]: cell for cell in schedule["records"]}
    by_cell = defaultdict(list)
    for attempt in attempts:
        by_cell[attempt["logical_cell_id"]].append(attempt)
    final = {logical_id: max(entries, key=lambda item: item["repeat"]) for logical_id, entries in by_cell.items()}
    if len(final) != 352 or any(item["failure_origin"] not in ("none", "model") for item in final.values()):
        raise FocusedFollowupError("recovered calibration contains invalid evidence")
    rows = [(final[logical_id], cells[logical_id]) for logical_id in sorted(cells)]
    aggregate = _analyze_paired_records(
        rows,
        "recovered_calibration_all_11",
        protocol,
        (0, 1),
        bootstrap_builder=_recovered_calibration_bootstrap_interval,
        issue_directional_claim=False,
    )
    # This is a retrospective descriptive direction/interval, not a claim.
    aggregate["interpretation"] = {
        "claim_applicable": False,
        "directional_interval_context_only": True,
        "reason": "post-terminal-calibration retrospective exploratory context; it cannot revive the retired v0.13.3 confirmatory program",
    }
    aggregate["reliability_metrics"] = _recovered_cluster_reliability(rows)
    aggregate["in_band_subset"] = _recovered_in_band_effect(rows)
    totals = selection["artifact"]["condition_combined_totals"]
    aggregate["measurable_effect_bounds"] = {
        family: 2 * min(Fraction(totals[family], 32), Fraction(32 - totals[family], 32))
        for family in sorted(totals)
    }
    return {
        "base": base,
        "selection": selection,
        "schedule": schedule,
        "store": store,
        "attempts": attempts,
        "aggregate": _jsonify_analysis(aggregate),
        "exploratory_plan_sha256": _file_digest(EXPLORATORY_PLAN_PATH),
    }


def _validate_recovered_calibration(document, protocol=None, components=None):
    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    expected = {
        "schema_version", "status", "base_program_authorization_sha256",
        "exploratory_plan_sha256", "calibration_artifact_sha256", "calibration_schedule_sha256", "run_id",
        "run_sha256", "attempt_records_sha256", "analysis", "recovered_at",
        "recovered_calibration_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise FocusedFollowupError("recovered calibration artifact has unexpected keys")
    unsigned = dict(document)
    supplied = unsigned.pop("recovered_calibration_sha256")
    if not isinstance(supplied, str) or supplied != _digest(unsigned):
        raise FocusedFollowupError("recovered calibration artifact digest drifted")
    for field in (
        "exploratory_plan_sha256", "calibration_artifact_sha256", "calibration_schedule_sha256",
        "run_sha256", "attempt_records_sha256",
    ):
        _require_sha256(document[field], "recovered calibration " + field)
    _timestamp(document["recovered_at"], "recovered calibration time")
    components = components or _rebuild_recovered_calibration_components(protocol)
    expected_fields = {
        "base_program_authorization_sha256": components["base"]["authorization_sha256"],
        "exploratory_plan_sha256": components["exploratory_plan_sha256"],
        "calibration_artifact_sha256": components["selection"]["artifact_sha256"],
        "calibration_schedule_sha256": _digest(components["schedule"]),
        "run_id": CALIBRATION_RUN_ID,
        "run_sha256": components["store"].run_sha256,
        "attempt_records_sha256": _digest(components["attempts"]),
        "analysis": components["aggregate"],
    }
    if (
        document["schema_version"] != RECOVERED_CALIBRATION_SCHEMA
        or document["status"] != "sealed_complete_retrospective_exploratory"
        or any(document[field] != value for field, value in expected_fields.items())
    ):
        raise FocusedFollowupError("recovered calibration artifact differs from re-extracted evidence")
    if "claim" in document["analysis"] or document["analysis"].get("interpretation", {}).get("claim_applicable") is not False:
        raise FocusedFollowupError("recovered calibration cannot carry a directional claim")
    return document


def recover_calibration(recovered_at=None, protocol=None):
    """Derive score-aggregate-only retrospective context from completed calibration.

    The output contains no raw traces or individual outcomes and is explicitly
    non-claiming.  Validation always re-extracts the sealed evidence rather than
    trusting a self-signed recovered JSON document.
    """

    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    components = _rebuild_recovered_calibration_components(protocol)
    document = {
        "schema_version": RECOVERED_CALIBRATION_SCHEMA,
        "status": "sealed_complete_retrospective_exploratory",
        "base_program_authorization_sha256": components["base"]["authorization_sha256"],
        "exploratory_plan_sha256": components["exploratory_plan_sha256"],
        "calibration_artifact_sha256": components["selection"]["artifact_sha256"],
        "calibration_schedule_sha256": _digest(components["schedule"]),
        "run_id": CALIBRATION_RUN_ID,
        "run_sha256": components["store"].run_sha256,
        "attempt_records_sha256": _digest(components["attempts"]),
        "analysis": components["aggregate"],
        "recovered_at": recovered_at or _utcnow(),
    }
    _timestamp(document["recovered_at"], "recovered calibration time")
    document["recovered_calibration_sha256"] = _digest(document)
    return _validate_recovered_calibration(document, protocol, components)


def _records_for_blocks(store, authorization, runs_root, run_id, blocks, protocol):
    result = {}
    for block in blocks:
        schedule = build_schedule(block, authorization["model_digests"]["4b"], protocol)
        seal = load_block_seal(authorization, runs_root, run_id, block, protocol)
        attempts = extract_block_attempts(store, schedule, authorization)
        final, missing, invalid = _final_attempts(schedule, attempts, authorization, runs_root, run_id)
        if missing or invalid or len(final) != schedule["logical_cell_count"]:
            raise FocusedFollowupError("focused sealed block evidence is incomplete")
        if seal["attempt_records_sha256"] != _digest(attempts):
            raise FocusedFollowupError("focused block seal differs from extracted attempts")
        result[block] = (schedule, attempts, final, seal)
    return result


def _paired_records_for_block(data, block):
    schedule, _attempts, final, _seal = data[block]
    by_id = {cell["logical_cell_id"]: cell for cell in schedule["records"]}
    return [(final[cell_id], cell) for cell_id, cell in sorted(by_id.items())]


def _two_trial_records(data):
    """Join B1a trial 0 to B2 trial 1 by exact family/instance/condition."""

    rows = _paired_records_for_block(data, "B1a") + _paired_records_for_block(data, "B2")
    return rows


def _validate_analysis(document, authorization, protocol):
    expected = {
        "schema_version", "status", "authorization_sha256", "protocol_sha256",
        "run_id", "recovered_calibration_sha256", "block_seals", "primary", "fallback", "secondary_B2",
        "termination_artifacts", "terminal_disposition", "limitations", "analyzed_at", "analysis_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise FocusedFollowupError("focused analysis has unexpected keys")
    unsigned = dict(document); supplied = unsigned.pop("analysis_sha256")
    if not isinstance(supplied, str) or supplied != _digest(unsigned):
        raise FocusedFollowupError("focused analysis digest drifted")
    if (
        document["schema_version"] != ANALYSIS_SCHEMA
        or document["status"] not in {"sealed_complete", "sealed_incomplete_no_prospective_claim"}
        or document["authorization_sha256"] != authorization["authorization_sha256"]
        or document["protocol_sha256"] != protocol_sha256(protocol)
        or not isinstance(document["run_id"], str)
        or not isinstance(document["block_seals"], dict)
        or not isinstance(document["termination_artifacts"], dict)
        or not isinstance(document["limitations"], list)
    ):
        raise FocusedFollowupError("focused analysis contract drifted")
    _require_sha256(document["recovered_calibration_sha256"], "focused recovered calibration digest")
    for label, digest in document["block_seals"].items():
        if label not in BLOCKS:
            raise FocusedFollowupError("focused analysis has an unknown sealed block")
        _require_sha256(digest, "focused analysis block seal")
    for label, digest in document["termination_artifacts"].items():
        if label not in BLOCKS or label in document["block_seals"]:
            raise FocusedFollowupError("focused analysis has an invalid termination binding")
        _require_sha256(digest, "focused analysis termination")
    _timestamp(document["analyzed_at"], "focused analysis time")
    if not isinstance(document["terminal_disposition"], dict):
        raise FocusedFollowupError("focused analysis terminal disposition is invalid")
    fallback = document["fallback"]
    if not isinstance(fallback, dict) or set(fallback) != {"used", "reason", "analysis"}:
        raise FocusedFollowupError("focused analysis fallback schema drifted")
    if document["status"] == "sealed_incomplete_no_prospective_claim":
        if document["primary"] is not None or fallback != {"used": False, "reason": None, "analysis": None}:
            raise FocusedFollowupError("incomplete focused analysis cannot carry a prospective claim")
        if document["secondary_B2"] is not None:
            raise FocusedFollowupError("incomplete focused analysis cannot carry B2 evidence")
    elif document["primary"] is None and fallback.get("used") is not True:
        raise FocusedFollowupError("complete focused analysis lacks its primary or eligible fallback")
    return document


def analyze_followup(
    authorization, runs_root, run_id, analyzed_at=None,
    allow_fallback=False, fallback_reason=None, now=None, protocol=None,
    recovered_calibration=None,
):
    """Generate the primary B1 analysis and optional B2 repeatability record."""

    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    validate_authorization(authorization, protocol)
    if recovered_calibration is None:
        raise FocusedFollowupError("focused analysis requires a sealed recovered calibration context")
    _validate_recovered_calibration(recovered_calibration)
    store = EvidenceStore.open_run(runs_root, run_id)
    _validate_store_metadata(store, authorization)
    validate_authorized_run_union(store, authorization, protocol)
    seals = {}
    terminations = {}
    for block in BLOCKS:
        path = _block_artifact_path(runs_root, authorization, block)
        if path.is_file() and path.with_name(path.name + ".complete").is_file():
            seals[block] = load_block_seal(authorization, runs_root, run_id, block, protocol)
        termination_path = _termination_artifact_path(runs_root, authorization, block)
        if termination_path.is_file() and termination_path.with_name(termination_path.name + ".complete").is_file():
            terminations[block] = load_termination(authorization, runs_root, run_id, block, protocol)
        if block in seals and block in terminations:
            raise FocusedFollowupError("focused block cannot be both complete and terminated")
    data = _records_for_blocks(store, authorization, runs_root, run_id, tuple(seals), protocol)
    primary = None
    fallback = None
    status = "sealed_complete"
    terminal_disposition = {"B1": "pending", "B2": "pending"}
    if "B1a" in data and "B1b" in data:
        rows = _paired_records_for_block(data, "B1a") + _paired_records_for_block(data, "B1b")
        primary = _jsonify_analysis(_analyze_paired_records(rows, "B1", protocol, (0,)))
        terminal_disposition["B1"] = "sealed_complete"
    elif allow_fallback:
        if "B1a" not in data or "B1b" in data:
            raise FocusedFollowupError("focused fallback eligibility is not satisfied")
        if fallback_reason not in ("deadline", "environment_failure"):
            raise FocusedFollowupError("focused fallback reason is invalid")
        termination = load_termination(authorization, runs_root, run_id, "B1b", protocol)
        if termination["reason"] != fallback_reason:
            raise FocusedFollowupError("focused fallback reason differs from sealed B1b termination")
        fallback = _jsonify_analysis(_analyze_paired_records(_paired_records_for_block(data, "B1a"), "B1a_fallback", protocol, (0,)))
        terminal_disposition["B1"] = "B1a_fallback_" + fallback_reason
    elif "B1a" in terminations:
        status = "sealed_incomplete_no_prospective_claim"
        terminal_disposition["B1"] = "B1a_terminated_" + terminations["B1a"]["reason"]
    elif "B1a" in data and "B1b" in terminations:
        # An instrument failure is deliberately not eligible for B1a fallback;
        # preserve the recovered context without turning an invalid partial B1
        # execution into a directional result.
        if terminations["B1b"]["reason"] != "instrument_failure":
            raise FocusedFollowupError("eligible B1b fallback requires an explicit declared fallback analysis")
        status = "sealed_incomplete_no_prospective_claim"
        terminal_disposition["B1"] = "B1b_terminated_instrument_failure"
    else:
        raise FocusedFollowupError("focused primary requires both B1 blocks or declared fallback")
    secondary = None
    if status == "sealed_complete" and "B1a" in data and "B1b" in data:
        if "B2" not in data and "B2" not in terminations:
            raise FocusedFollowupError("focused analysis requires a sealed B2 result or terminal B2 disposition")
    if "B2" in data:
        if "B1a" not in data:
            raise FocusedFollowupError("B2 requires sealed B1a first trial")
        two_trial = _jsonify_analysis(_analyze_paired_records(
            _two_trial_records(data), "B2_two_trial", protocol, (0, 1),
        ))
        trial_one = _jsonify_analysis(_analyze_paired_records(
            _paired_records_for_block(data, "B2"), "B2_trial_1_descriptive", protocol, (1,),
        ))
        trial_zero = _jsonify_analysis(_analyze_paired_records(
            _paired_records_for_block(data, "B1a"), "B2_trial_0_descriptive", protocol, (0,),
        ))
        for record in (two_trial, trial_zero, trial_one):
            criterion = record.pop("claim", None)
            record["secondary_directional_criterion"] = {
                "would_satisfy_primary_rule": criterion,
                "may_not_issue_or_alter_primary_claim": True,
            }
        secondary = {
            "status": "sealed_complete_secondary_only",
            "two_trial": two_trial,
            "trial_0_descriptive": trial_zero,
            "trial_1_descriptive": trial_one,
        }
        terminal_disposition["B2"] = "sealed_complete_secondary_only"
    elif "B2" in terminations:
        secondary = {
            "status": "terminated_incomplete_secondary_only",
            "reason": terminations["B2"]["reason"],
            "may_not_issue_or_alter_primary_claim": True,
        }
        terminal_disposition["B2"] = "terminated_" + terminations["B2"]["reason"]
    elif fallback is not None:
        # B2 is intentionally ineligible when B1b did not seal: its defined
        # two-trial comparison requires complete B1a/B1b primary execution.
        terminal_disposition["B2"] = "not_eligible_after_B1a_fallback"
    elif status == "sealed_incomplete_no_prospective_claim":
        terminal_disposition["B2"] = "not_started_after_incomplete_B1"
    document = {
        "schema_version": ANALYSIS_SCHEMA,
        "status": status,
        "authorization_sha256": authorization["authorization_sha256"],
        "protocol_sha256": protocol_sha256(protocol),
        "run_id": run_id,
        "recovered_calibration_sha256": recovered_calibration["recovered_calibration_sha256"],
        "block_seals": {block: seal["seal_sha256"] for block, seal in sorted(seals.items())},
        "termination_artifacts": {
            block: termination["termination_sha256"] for block, termination in sorted(terminations.items())
        },
        "primary": primary,
        "fallback": {"used": fallback is not None, "reason": fallback_reason if fallback else None, "analysis": fallback},
        "secondary_B2": secondary,
        "terminal_disposition": terminal_disposition,
        "limitations": list(protocol["reporting"]["limitations"]) + [
            "Comparative calibration outcomes were known when this focused protocol was frozen.",
            "Per-attempt model_time_ms and wall_time_ms are unavailable in the frozen runtime; only block-boundary elapsed time may be reported externally.",
            "Cap-hit summaries are descriptive; cap-hit clusters remain in every primary estimate.",
        ],
        "analyzed_at": analyzed_at or _utcnow(),
    }
    _timestamp(document["analyzed_at"], "focused analysis time")
    document["analysis_sha256"] = _digest(document)
    return _validate_analysis(document, authorization, protocol)


def build_report(
    authorization, analysis, runs_root=None, run_id=None, recovered_calibration=None,
    reported_at=None, protocol=None,
):
    """Build a report only from a sealed, evidence-derived analysis document."""

    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    validate_authorization(authorization, protocol)
    _validate_analysis(analysis, authorization, protocol)
    if runs_root is None or run_id is None or recovered_calibration is None:
        raise FocusedFollowupError("focused report requires evidence inputs for analysis rederivation")
    rebuilt = analyze_followup(
        authorization, runs_root, run_id, analyzed_at=analysis["analyzed_at"], protocol=protocol,
        recovered_calibration=recovered_calibration,
        allow_fallback=analysis["fallback"]["used"],
        fallback_reason=analysis["fallback"]["reason"],
    )
    if analysis != rebuilt:
        raise FocusedFollowupError("focused report input analysis differs from evidence-derived analysis")
    validated_recovered = _validate_recovered_calibration(recovered_calibration)
    block_boundary_timing = {}
    for block, digest in sorted(analysis["block_seals"].items()):
        seal = load_block_seal(authorization, runs_root, run_id, block, protocol)
        if seal["seal_sha256"] != digest:
            raise FocusedFollowupError("focused report block-seal binding differs from evidence")
        block_boundary_timing[block] = {
            "block_started_at": seal["block_started_at"],
            "block_finished_at": seal["block_finished_at"],
            "block_elapsed_ms": seal["block_elapsed_ms"],
        }
    termination_artifacts = {}
    for block, digest in sorted(analysis["termination_artifacts"].items()):
        termination = load_termination(authorization, runs_root, run_id, block, protocol)
        if termination["termination_sha256"] != digest:
            raise FocusedFollowupError("focused report termination binding differs from evidence")
        termination_artifacts[block] = {
            "reason": termination["reason"],
            "terminated_at": termination["terminated_at"],
            "termination_sha256": digest,
        }
    document = {
        "schema_version": REPORT_SCHEMA,
        "status": (
            "focused_followup_complete"
            if analysis["status"] == "sealed_complete"
            else "focused_followup_incomplete_no_prospective_claim"
        ),
        "classification": protocol["classification"],
        "display_label": "v0.14.0-focused.1",
        "authorization_sha256": authorization["authorization_sha256"],
        "analysis_sha256": analysis["analysis_sha256"],
        "recovered_calibration_sha256": analysis["recovered_calibration_sha256"],
        "recovered_calibration_context": validated_recovered["analysis"],
        "primary": analysis["primary"],
        "fallback": analysis["fallback"],
        "secondary_B2": analysis["secondary_B2"],
        "terminal_disposition": analysis["terminal_disposition"],
        "block_boundary_timing": block_boundary_timing,
        "termination_artifacts": termination_artifacts,
        "limitations": analysis["limitations"],
        "reported_at": reported_at or _utcnow(),
    }
    _timestamp(document["reported_at"], "focused report time")
    document["report_sha256"] = _digest(document)
    return _validate_report(document, authorization, analysis, protocol)


def _validate_report(document, authorization, analysis, protocol):
    expected = {
        "schema_version", "status", "classification", "display_label", "authorization_sha256",
        "analysis_sha256", "recovered_calibration_sha256", "recovered_calibration_context", "primary",
        "fallback", "secondary_B2", "terminal_disposition", "block_boundary_timing",
        "termination_artifacts", "limitations", "reported_at", "report_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise FocusedFollowupError("focused report has unexpected keys")
    unsigned = dict(document)
    supplied = unsigned.pop("report_sha256")
    if not isinstance(supplied, str) or supplied != _digest(unsigned):
        raise FocusedFollowupError("focused report digest drifted")
    expected_status = (
        "focused_followup_complete"
        if analysis["status"] == "sealed_complete"
        else "focused_followup_incomplete_no_prospective_claim"
    )
    if (
        document["schema_version"] != REPORT_SCHEMA
        or document["status"] != expected_status
        or document["classification"] != protocol["classification"]
        or document["display_label"] != "v0.14.0-focused.1"
        or document["authorization_sha256"] != authorization["authorization_sha256"]
        or document["analysis_sha256"] != analysis["analysis_sha256"]
        or document["recovered_calibration_sha256"] != analysis["recovered_calibration_sha256"]
        or document["primary"] != analysis["primary"]
        or document["fallback"] != analysis["fallback"]
        or document["secondary_B2"] != analysis["secondary_B2"]
        or document["terminal_disposition"] != analysis["terminal_disposition"]
        or not isinstance(document["recovered_calibration_context"], dict)
        or not isinstance(document["block_boundary_timing"], dict)
        or not isinstance(document["termination_artifacts"], dict)
    ):
        raise FocusedFollowupError("focused report binding drifted")
    _timestamp(document["reported_at"], "focused report time")
    return document


def _publish_canonical_analysis(authorization, runs_root, analysis):
    path = _analysis_artifact_path(runs_root, authorization)
    if path.exists() or path.with_name(path.name + ".complete").exists():
        published = _load_published(path, "focused analysis")
        if published != analysis:
            raise FocusedFollowupError("focused analysis location already contains different evidence")
        return path
    _publish_marker_last(path, analysis)
    return path


def _publish_canonical_report(authorization, runs_root, report):
    path = _report_artifact_path(runs_root, authorization)
    if path.exists() or path.with_name(path.name + ".complete").exists():
        published = _load_published(path, "focused report")
        if published != report:
            raise FocusedFollowupError("focused report location already contains different evidence")
        return path
    _publish_marker_last(path, report)
    return path


def _require_canonical_output(output, expected, label):
    if Path(output).resolve() != Path(expected).resolve():
        raise FocusedFollowupError("%s output must be the canonical authorization-bound path" % label)
    return Path(expected)


def validate_termination(authorization, runs_root, run_id, block, protocol=None):
    """Public score-free termination verifier for the supervisor."""

    return load_termination(authorization, runs_root, run_id, block, protocol)


def validate_analysis(
    authorization, analysis, runs_root, run_id, recovered_calibration, protocol=None,
):
    """Rebuild the evidence-derived analysis and require exact equality."""

    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    _validate_analysis(analysis, authorization, protocol)
    rebuilt = analyze_followup(
        authorization, runs_root, run_id, analyzed_at=analysis["analyzed_at"], protocol=protocol,
        recovered_calibration=recovered_calibration,
        allow_fallback=analysis["fallback"]["used"],
        fallback_reason=analysis["fallback"]["reason"],
    )
    if analysis != rebuilt:
        raise FocusedFollowupError("focused analysis differs from re-derived evidence")
    return analysis


def validate_report(
    authorization, report, analysis, runs_root, run_id, recovered_calibration, protocol=None,
):
    """Rebuild the report from evidence and reject a re-signed supplied report."""

    protocol = load_protocol() if protocol is None else validate_protocol(protocol)
    validate_analysis(authorization, analysis, runs_root, run_id, recovered_calibration, protocol)
    rebuilt = build_report(
        authorization, analysis, runs_root, run_id, recovered_calibration,
        reported_at=report.get("reported_at") if isinstance(report, dict) else None,
        protocol=protocol,
    )
    if report != rebuilt:
        raise FocusedFollowupError("focused report differs from re-derived evidence")
    return report


def _load_document(path, label):
    try:
        return load_canonical_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise FocusedFollowupError(label + " is unreadable") from exc


def _cli_authorize(args):
    preflight = _load_document(args.preflight, "native preflight")
    document = build_authorization(
        preflight, args.issued_at, args.issuer, args.supervisor_path,
        FOCUSED_RUN_ID, followup_tag=args.followup_tag, base_tag=args.base_tag,
    )
    _publish_marker_last(args.output, document)
    print(json.dumps({"status": "authorized", "authorization_sha256": document["authorization_sha256"]}, sort_keys=True))


def _cli_run(args, seal_only=False):
    authorization = _load_published(args.authorization, "focused authorization")
    runs_root = require_authorized_runs_root(authorization, args.runs_root)
    run_id = require_authorized_run_id(authorization, args.run_id)
    if seal_only:
        # Recovery after a crash is permitted only when the machine still
        # matches the fingerprint that governed the completed attempts.  A
        # score-free seal must never turn a postflight runtime/model/host drift
        # into a successful block merely because all cells were written first.
        lease = BenchmarkLease()
        lease.acquire(authorization["authorization_sha256"])
        try:
            validate_current_environment(
                authorization, supervisor_path=args.supervisor_path,
            )
            document = seal_block(authorization, runs_root, run_id, args.block)
        finally:
            lease.release()
    else:
        preflight = _load_document(args.preflight, "native preflight") if args.preflight else None
        document = run_block(
            authorization, runs_root, run_id, args.block, args.supervisor_path,
            preflight=preflight,
        )
    print(json.dumps({
        "status": document["status"], "block": document["block"],
        "logical_cells_complete": document["logical_cells_complete"],
        "instrument_invalid_cells": document["instrument_invalid_cells"],
        "scores_exposed": False,
    }, sort_keys=True))


def _cli_analyze(args):
    authorization = _load_published(args.authorization, "focused authorization")
    _validate_authorization_repository_bindings(authorization)
    runs_root = require_authorized_runs_root(authorization, args.runs_root)
    run_id = require_authorized_run_id(authorization, args.run_id)
    recovered = _load_published(args.recovered_calibration, "recovered calibration")
    expected_output = _analysis_artifact_path(runs_root, authorization)
    _require_canonical_output(args.output, expected_output, "focused analysis")
    document = analyze_followup(
        authorization, runs_root, run_id,
        allow_fallback=args.allow_fallback, fallback_reason=args.fallback_reason,
        recovered_calibration=recovered,
    )
    _publish_canonical_analysis(authorization, runs_root, document)
    print(json.dumps({"status": document["status"], "analysis_sha256": document["analysis_sha256"]}, sort_keys=True))


def _cli_report(args):
    authorization = _load_published(args.authorization, "focused authorization")
    _validate_authorization_repository_bindings(authorization)
    runs_root = require_authorized_runs_root(authorization, args.runs_root)
    run_id = require_authorized_run_id(authorization, args.run_id)
    analysis = _load_published(args.analysis, "focused analysis")
    recovered = _load_published(args.recovered_calibration, "recovered calibration")
    expected_output = _report_artifact_path(runs_root, authorization)
    _require_canonical_output(args.output, expected_output, "focused report")
    document = build_report(
        authorization, analysis, runs_root, run_id, recovered,
    )
    _publish_canonical_report(authorization, runs_root, document)
    print(json.dumps({"status": document["status"], "report_sha256": document["report_sha256"]}, sort_keys=True))


def _cli_recover_calibration(args):
    _require_canonical_output(args.output, RECOVERED_CALIBRATION_OUTPUT_PATH, "recovered calibration")
    document = recover_calibration()
    _publish_marker_last(RECOVERED_CALIBRATION_OUTPUT_PATH, document)
    print(json.dumps({
        "status": document["status"],
        "recovered_calibration_sha256": document["recovered_calibration_sha256"],
        "scores_exposed": False,
    }, sort_keys=True))


def _cli_validate_block_seal(args):
    authorization = _load_published(args.authorization, "focused authorization")
    _validate_authorization_repository_bindings(authorization)
    runs_root = require_authorized_runs_root(authorization, args.runs_root)
    run_id = require_authorized_run_id(authorization, args.run_id)
    document = validate_block_seal(authorization, runs_root, run_id, args.block)
    print(json.dumps({
        "status": document["status"], "block": document["block"],
        "logical_cells_complete": document["logical_cells_complete"],
        "scores_exposed": False,
    }, sort_keys=True))


def _cli_validate_authorization(args):
    authorization = _load_published(args.authorization, "focused authorization")
    validate_authorization(authorization)
    _validate_authorization_repository_bindings(authorization)
    print(json.dumps({
        "status": "authorized", "authorization_sha256": authorization["authorization_sha256"],
        "run_id": authorization["run_id"], "scores_exposed": False,
    }, sort_keys=True))


def _cli_validate_termination(args):
    authorization = _load_published(args.authorization, "focused authorization")
    _validate_authorization_repository_bindings(authorization)
    runs_root = require_authorized_runs_root(authorization, args.runs_root)
    run_id = require_authorized_run_id(authorization, args.run_id)
    document = validate_termination(authorization, runs_root, run_id, args.block)
    print(json.dumps({
        "status": document["status"], "block": document["block"], "reason": document["reason"],
        "scores_exposed": False,
    }, sort_keys=True))


def _cli_validate_analysis(args):
    authorization = _load_published(args.authorization, "focused authorization")
    _validate_authorization_repository_bindings(authorization)
    runs_root = require_authorized_runs_root(authorization, args.runs_root)
    run_id = require_authorized_run_id(authorization, args.run_id)
    analysis = _load_published(args.analysis, "focused analysis")
    recovered = _load_published(args.recovered_calibration, "recovered calibration")
    validate_analysis(authorization, analysis, runs_root, run_id, recovered)
    print(json.dumps({
        "status": analysis["status"], "analysis_sha256": analysis["analysis_sha256"],
    }, sort_keys=True))


def _cli_validate_report(args):
    authorization = _load_published(args.authorization, "focused authorization")
    _validate_authorization_repository_bindings(authorization)
    runs_root = require_authorized_runs_root(authorization, args.runs_root)
    run_id = require_authorized_run_id(authorization, args.run_id)
    analysis = _load_published(args.analysis, "focused analysis")
    report = _load_published(args.report, "focused report")
    recovered = _load_published(args.recovered_calibration, "recovered calibration")
    validate_report(authorization, report, analysis, runs_root, run_id, recovered)
    print(json.dumps({
        "status": report["status"], "report_sha256": report["report_sha256"],
    }, sort_keys=True))


def _cli_terminate_block(args):
    authorization = _load_published(args.authorization, "focused authorization")
    _validate_authorization_repository_bindings(authorization)
    runs_root = require_authorized_runs_root(authorization, args.runs_root)
    run_id = require_authorized_run_id(authorization, args.run_id)
    document = terminate_block(authorization, runs_root, run_id, args.block, args.reason)
    print(json.dumps({
        "status": document["status"], "block": document["block"],
        "reason": document["reason"], "scores_exposed": False,
    }, sort_keys=True))


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    authorize = subparsers.add_parser("authorize")
    authorize.add_argument("--preflight", required=True)
    authorize.add_argument("--output", required=True)
    authorize.add_argument("--issued-at", required=True)
    authorize.add_argument("--issuer", required=True)
    authorize.add_argument("--supervisor-path", required=True)
    authorize.add_argument("--base-tag", default="v0.13.3")
    authorize.add_argument("--followup-tag", default="v0.13.4")
    authorize.set_defaults(handler=_cli_authorize)
    validate_auth = subparsers.add_parser("validate-authorization")
    validate_auth.add_argument("--authorization", required=True)
    validate_auth.set_defaults(handler=_cli_validate_authorization)
    for name, seal_only in (("run-block", False), ("seal-block", True)):
        command = subparsers.add_parser(name)
        command.add_argument("--authorization", required=True)
        command.add_argument("--runs-root", required=True)
        command.add_argument("--run-id", required=True)
        command.add_argument("--block", choices=BLOCKS, required=True)
        command.add_argument("--supervisor-path", required=True)
        if not seal_only:
            command.add_argument("--preflight")
        command.set_defaults(handler=lambda args, _seal=seal_only: _cli_run(args, _seal))
    verify = subparsers.add_parser("validate-block-seal")
    verify.add_argument("--authorization", required=True)
    verify.add_argument("--runs-root", required=True)
    verify.add_argument("--run-id", required=True)
    verify.add_argument("--block", choices=BLOCKS, required=True)
    verify.set_defaults(handler=_cli_validate_block_seal)
    verify_termination = subparsers.add_parser("validate-termination")
    verify_termination.add_argument("--authorization", required=True)
    verify_termination.add_argument("--runs-root", required=True)
    verify_termination.add_argument("--run-id", required=True)
    verify_termination.add_argument("--block", choices=BLOCKS, required=True)
    verify_termination.set_defaults(handler=_cli_validate_termination)
    terminate = subparsers.add_parser("terminate-block")
    terminate.add_argument("--authorization", required=True)
    terminate.add_argument("--runs-root", required=True)
    terminate.add_argument("--run-id", required=True)
    terminate.add_argument("--block", choices=BLOCKS, required=True)
    terminate.add_argument("--reason", choices=("deadline", "B2_start_cutoff", "environment_failure", "instrument_failure"), required=True)
    terminate.set_defaults(handler=_cli_terminate_block)
    recovered = subparsers.add_parser("recover-calibration")
    recovered.add_argument("--output", required=True)
    recovered.set_defaults(handler=_cli_recover_calibration)
    analyze = subparsers.add_parser("analyze")
    analyze.add_argument("--authorization", required=True)
    analyze.add_argument("--runs-root", required=True)
    analyze.add_argument("--run-id", required=True)
    analyze.add_argument("--output", required=True)
    analyze.add_argument("--recovered-calibration", required=True)
    analyze.add_argument("--allow-fallback", action="store_true")
    analyze.add_argument("--fallback-reason", choices=("deadline", "environment_failure"))
    analyze.set_defaults(handler=_cli_analyze)
    verify_analysis = subparsers.add_parser("validate-analysis")
    verify_analysis.add_argument("--authorization", required=True)
    verify_analysis.add_argument("--analysis", required=True)
    verify_analysis.add_argument("--runs-root", required=True)
    verify_analysis.add_argument("--run-id", required=True)
    verify_analysis.add_argument("--recovered-calibration", required=True)
    verify_analysis.set_defaults(handler=_cli_validate_analysis)
    report = subparsers.add_parser("report")
    report.add_argument("--authorization", required=True)
    report.add_argument("--analysis", required=True)
    report.add_argument("--runs-root", required=True)
    report.add_argument("--run-id", required=True)
    report.add_argument("--recovered-calibration", required=True)
    report.add_argument("--output", required=True)
    report.set_defaults(handler=_cli_report)
    verify_report = subparsers.add_parser("validate-report")
    verify_report.add_argument("--authorization", required=True)
    verify_report.add_argument("--analysis", required=True)
    verify_report.add_argument("--report", required=True)
    verify_report.add_argument("--runs-root", required=True)
    verify_report.add_argument("--run-id", required=True)
    verify_report.add_argument("--recovered-calibration", required=True)
    verify_report.set_defaults(handler=_cli_validate_report)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.handler(args)
    except FocusedFollowupError as exc:
        parser.exit(2, "focused follow-up error: %s\n" % exc)


if __name__ == "__main__":
    main()
