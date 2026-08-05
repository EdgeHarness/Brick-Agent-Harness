"""Staffed, sealed, proportionate human validation for the successor suite.

Human validity evidence covers the 308 calibration and retained cases.  Every
case receives one cold review; an outcome-blind 88-case subset receives a
second review.  Mismatches escalate the affected case, and two reliability
events expand the second review to all 308 cases.  The other generated cohorts
remain machine-conformance evidence and cannot be mislabeled as human reviewed.
"""

import copy
from collections import Counter
import datetime
import itertools
from pathlib import Path
import re
from functools import lru_cache

from domains.office_demo.contracts import SCHEMAS
from domains.office_demo.generators_v2 import (
    FAMILIES,
    GENERATOR_VERSION,
    validate_office_instance_v2,
)
from domains.office_demo.outcome_oracle_v2 import derive_outcome
from domains.office_demo.pack import PACK
from harness.evidence import canonical_json_bytes
from harness.instances import replace_canonical_json, sha256_bytes, validate_manifest

from .next_study_review_training import verify_artifacts as verify_training_artifacts
from .next_study_review_selection import (
    build_review_selection, validate_review_selection,
)


LEDGER_SCHEMA = "brick.next-study.review-ledger/3"
PACKET_SCHEMA = "brick.next-study.blind-review-packet/2"
STAFFING_SCHEMA = "brick.next-study.review-staffing/3"
ASSIGNMENT_SCHEMA = "brick.next-study.review-assignments/3"
PILOT_SCHEMA = "brick.next-study.review-pilot/3"
PILOT_RESULT_SCHEMA = "brick.next-study.review-pilot-result/2"
SUBMISSION_SCHEMA = "brick.next-study.sealed-review-submission/3"
ADJUDICATED_OUTCOMES_SCHEMA = "brick.next-study.adjudicated-outcomes/2"
REVIEW_PROTOCOL_VERSION = "office-tiered-human-validation/3.0.0"
_SLOTS = ("primary", "secondary")
_SAFE_REVIEWER_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


class ReviewLedgerError(ValueError):
    pass


def _digest(value):
    return sha256_bytes(canonical_json_bytes(value, allow_float=False))


def _validate_sha256(value, label):
    if (
        not isinstance(value, str) or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ReviewLedgerError("%s must be lowercase SHA-256 hex" % label)
    return value


def _validate_reviewer_id(value, label="reviewer_id"):
    if not isinstance(value, str) or _SAFE_REVIEWER_ID.fullmatch(value) is None:
        raise ReviewLedgerError(
            "%s must be a safe 1-64 character opaque identifier" % label
        )
    return value


def digest_review_artifact(value):
    return _digest(value)


def review_packet(instance):
    """Return only agent-visible task material; hidden outcomes are excluded."""

    validate_office_instance_v2(instance)
    content = instance["content"]
    packet_id = _digest({
        "namespace": "brick.next-study.review-packet/2",
        "content_sha256": instance["content_sha256"],
    })
    tool_schemas = []
    for name in content["tool_names"]:
        specification = PACK.registry.get(name)
        tool_schemas.append({
            "name": name,
            "description": specification["desc"],
            "parameters": copy.deepcopy(SCHEMAS[name]),
        })
    return {
        "schema_version": PACKET_SCHEMA,
        "packet_id": packet_id,
        "family": content["family"],
        "today": content["today"],
        "prompt": content["prompt"],
        "subepisode_prompts": [
            episode["prompt"] for episode in content["ordered_subepisodes"]
        ],
        "initial_state": copy.deepcopy(content["initial_state"]),
        "tool_schemas": tool_schemas,
    }


def _oracle_outcome(instance):
    packet = review_packet(instance)
    return derive_outcome(
        packet["family"], packet["prompt"], packet["subepisode_prompts"],
        packet["initial_state"], packet["today"],
    )


def _instances(manifests):
    if not isinstance(manifests, (list, tuple)) or len(manifests) != 6:
        raise ReviewLedgerError("review workflow requires all six frozen manifests")
    expected_splits = {
        "development", "calibration", "validation", "sentinel",
        "retained", "adversarial",
    }
    for manifest in manifests:
        validate_manifest(manifest)
    if {manifest["split"] for manifest in manifests} != expected_splits:
        raise ReviewLedgerError("review manifests have missing or duplicate splits")
    instances = [instance for manifest in manifests for instance in manifest["instances"]]
    identifiers = [instance["content"]["id"] for instance in instances]
    hashes = [instance["content_sha256"] for instance in instances]
    if (
        len(instances) != 528 or len(set(identifiers)) != 528
        or len(set(hashes)) != 528
    ):
        raise ReviewLedgerError("review manifests must contain 528 unique cases")
    return sorted(instances, key=lambda item: item["content"]["id"])


def _selection(manifests, selection=None):
    value = build_review_selection(manifests) if selection is None else selection
    return validate_review_selection(value, manifests)


def _review_instances(manifests, selection=None):
    selected = _selection(manifests, selection)
    by_id = {item["content"]["id"]: item for item in _instances(manifests)}
    instances = [by_id[item["instance_id"]] for item in selected["records"]]
    if len(instances) != 308:
        raise ReviewLedgerError("human-validity scope must contain 308 cases")
    return instances, selected


def build_pending_ledger(manifests, selection=None):
    instances, selection = _review_instances(manifests, selection)
    selected_by_id = {item["instance_id"]: item for item in selection["records"]}
    entries = []
    for instance in instances:
        content = instance["content"]
        fixed = selected_by_id[content["id"]]["fixed_double_review"]
        entries.append({
            "instance_id": content["id"],
            "content_sha256": instance["content_sha256"],
            "review_packet_sha256": _digest(review_packet(instance)),
            "oracle_outcome_sha256": _digest(_oracle_outcome(instance)),
            "fixed_double_review": fixed,
            "secondary_required": fixed,
            "reviews": {"primary": None, "secondary": None},
            "adjudication": None,
            "status": "pending",
        })
    ledger = {
        "schema_version": LEDGER_SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "review_protocol_version": REVIEW_PROTOCOL_VERSION,
        "review_selection_sha256": selection["selection_sha256"],
        "status": "pending_human_review",
        "planned_judgments": 396,
        "required_secondary_judgments": 88,
        "global_escalation": False,
        "reliability_event_cases": [],
        "cases": len(entries),
        "completed_cases": 0,
        "entries": entries,
    }
    return validate_ledger(ledger, manifests, selection)


def _validate_review(value, label):
    expected = {
        "reviewer_id", "prompt_valid", "outcome", "accepted_alternatives",
        "rationale",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ReviewLedgerError("%s has unexpected keys" % label)
    _validate_reviewer_id(value["reviewer_id"], "%s reviewer_id" % label)
    if type(value["prompt_valid"]) is not bool:
        raise ReviewLedgerError("%s prompt_valid must be boolean" % label)
    if not isinstance(value["outcome"], list):
        raise ReviewLedgerError("%s outcome must be a list" % label)
    if not isinstance(value["accepted_alternatives"], list):
        raise ReviewLedgerError("%s accepted alternatives must be a list" % label)
    if not isinstance(value["rationale"], str) or not value["rationale"].strip():
        raise ReviewLedgerError("%s rationale is empty" % label)
    canonical_json_bytes(value, allow_float=False)
    return value


def _validate_adjudication(value):
    expected = {
        "adjudicator_id", "prompt_valid", "outcome", "accepted_alternatives",
        "rationale",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ReviewLedgerError("adjudication has unexpected keys")
    _validate_reviewer_id(value["adjudicator_id"], "adjudicator_id")
    if type(value["prompt_valid"]) is not bool:
        raise ReviewLedgerError("adjudication prompt_valid must be boolean")
    if not isinstance(value["outcome"], list):
        raise ReviewLedgerError("adjudication outcome must be a list")
    if not isinstance(value["accepted_alternatives"], list):
        raise ReviewLedgerError("adjudication alternatives must be a list")
    if not isinstance(value["rationale"], str) or not value["rationale"].strip():
        raise ReviewLedgerError("adjudication rationale is empty")
    canonical_json_bytes(value, allow_float=False)
    return value


def _response_signature(submission):
    response = submission["response"]
    return (
        response["prompt_valid"], response["outcome"],
        response["accepted_alternatives"],
    )


def _canonical_submission(submission, expected):
    response = submission["response"]
    return (
        response["prompt_valid"] is True
        and response["outcome"] == expected
        and response["accepted_alternatives"] == []
    )


def _validate_bound_submission(submission, role, packet, assigned_ids=None):
    _validate_sealed_submission(submission)
    if submission["role"] != role:
        raise ReviewLedgerError("sealed review role drifted")
    if (
        submission["packet_id"] != packet["packet_id"]
        or submission["review_packet_sha256"] != _digest(packet)
    ):
        raise ReviewLedgerError("sealed review packet binding drifted")
    if assigned_ids is not None and submission["reviewer_id"] != assigned_ids[role]:
        raise ReviewLedgerError("sealed submission signer is not assigned")


def _entry_status(entry, instance, global_escalation=False):
    reviews = entry["reviews"]
    first, second = (reviews[slot] for slot in _SLOTS)
    if first is None and second is None:
        if entry["adjudication"] is not None:
            raise ReviewLedgerError("pending entry has an adjudication")
        return "pending", False
    if first is None:
        raise ReviewLedgerError("secondary review cannot precede primary review")
    packet = review_packet(instance)
    _validate_bound_submission(first, "primary", packet)
    expected = _oracle_outcome(instance)
    secondary_required = (
        entry["fixed_double_review"]
        or not _canonical_submission(first, expected)
        or global_escalation
    )
    if second is None and secondary_required:
        if entry["adjudication"] is not None:
            raise ReviewLedgerError("partially reviewed entry has an adjudication")
        return "in_review", False
    if second is None:
        if entry["adjudication"] is not None:
            raise ReviewLedgerError("single accepted review must not be adjudicated")
        return "accepted_single", True
    _validate_bound_submission(second, "secondary", packet)
    if first["reviewer_id"] == second["reviewer_id"]:
        raise ReviewLedgerError("the two review slots use the same reviewer")
    reviews_agree = _response_signature(first) == _response_signature(second)
    if reviews_agree:
        if _canonical_submission(first, expected):
            if entry["adjudication"] is not None:
                raise ReviewLedgerError("canonical agreed reviews must not be adjudicated")
            return "agreed", True
        # Agreement against the key is still independently adjudicated; two
        # humans can correctly expose a prompt/key defect.
    adjudication = entry["adjudication"]
    if adjudication is None:
        return "disputed", False
    _validate_bound_submission(adjudication, "adjudicator", packet)
    if adjudication["reviewer_id"] in {
        first["reviewer_id"], second["reviewer_id"],
    }:
        raise ReviewLedgerError("adjudicator must be independent of both reviewers")
    complete = _canonical_submission(adjudication, expected)
    return ("adjudicated" if complete else "rejected"), complete


def _reliability_events(entries, instances):
    events = []
    for entry, instance in zip(entries, instances):
        first, second = (entry["reviews"][slot] for slot in _SLOTS)
        if first is None:
            continue
        expected = _oracle_outcome(instance)
        primary_mismatch = not _canonical_submission(first, expected)
        reviewer_disagreement = (
            second is not None and _response_signature(first) != _response_signature(second)
        )
        if primary_mismatch or reviewer_disagreement:
            events.append(entry["instance_id"])
    return sorted(events)


def validate_ledger(ledger, manifests, selection=None):
    expected_keys = {
        "schema_version", "generator_version", "review_protocol_version",
        "review_selection_sha256", "status", "planned_judgments",
        "required_secondary_judgments", "global_escalation",
        "reliability_event_cases", "cases", "completed_cases", "entries",
    }
    if not isinstance(ledger, dict) or set(ledger) != expected_keys:
        raise ReviewLedgerError("review ledger has unexpected keys")
    if ledger["schema_version"] != LEDGER_SCHEMA:
        raise ReviewLedgerError("review ledger schema drifted")
    if ledger["generator_version"] != GENERATOR_VERSION:
        raise ReviewLedgerError("review ledger generator version drifted")
    if ledger["review_protocol_version"] != REVIEW_PROTOCOL_VERSION:
        raise ReviewLedgerError("review protocol version drifted")
    instances, selection = _review_instances(manifests, selection)
    if ledger["review_selection_sha256"] != selection["selection_sha256"]:
        raise ReviewLedgerError("review ledger selection binding drifted")
    if ledger["planned_judgments"] != 396:
        raise ReviewLedgerError("planned review judgment count drifted")
    entries = ledger["entries"]
    if not isinstance(entries, list) or len(entries) != len(instances):
        raise ReviewLedgerError("review ledger does not cover human-validity scope")
    if ledger["cases"] != len(instances):
        raise ReviewLedgerError("review ledger case count is inconsistent")
    completed = 0
    terminal_rejection = False
    for entry, instance in zip(entries, instances):
        expected_entry_keys = {
            "instance_id", "content_sha256", "review_packet_sha256",
            "oracle_outcome_sha256", "fixed_double_review", "secondary_required",
            "reviews", "adjudication", "status",
        }
        if not isinstance(entry, dict) or set(entry) != expected_entry_keys:
            raise ReviewLedgerError("review entry has unexpected keys")
        content = instance["content"]
        bindings = {
            "instance_id": content["id"],
            "content_sha256": instance["content_sha256"],
            "review_packet_sha256": _digest(review_packet(instance)),
            "oracle_outcome_sha256": _digest(_oracle_outcome(instance)),
        }
        if any(entry[key] != value for key, value in bindings.items()):
            raise ReviewLedgerError("review entry binding drifted for %s" % content["id"])
        selected_record = next(
            item for item in selection["records"] if item["instance_id"] == content["id"]
        )
        if entry["fixed_double_review"] is not selected_record["fixed_double_review"]:
            raise ReviewLedgerError("fixed double-review flag drifted")
        if not isinstance(entry["reviews"], dict) or set(entry["reviews"]) != set(_SLOTS):
            raise ReviewLedgerError("review slots drifted")
    events = _reliability_events(entries, instances)
    global_escalation = len(events) >= 2
    required_secondary = sum(
        entry["fixed_double_review"]
        or entry["reviews"]["primary"] is not None
        and not _canonical_submission(entry["reviews"]["primary"], _oracle_outcome(instance))
        or global_escalation
        for entry, instance in zip(entries, instances)
    )
    completed = 0
    terminal_rejection = False
    for entry, instance in zip(entries, instances):
        expected_secondary = (
            entry["fixed_double_review"]
            or entry["reviews"]["primary"] is not None
            and not _canonical_submission(entry["reviews"]["primary"], _oracle_outcome(instance))
            or global_escalation
        )
        if entry["secondary_required"] is not expected_secondary:
            raise ReviewLedgerError("secondary-review requirement is not derived")
        status, is_complete = _entry_status(entry, instance, global_escalation)
        if entry["status"] != status:
            raise ReviewLedgerError("review entry status is not derived")
        completed += int(is_complete)
        terminal_rejection = terminal_rejection or status == "rejected"
    if ledger["reliability_event_cases"] != events:
        raise ReviewLedgerError("reliability event list is not derived")
    if ledger["global_escalation"] is not global_escalation:
        raise ReviewLedgerError("global review escalation is not derived")
    if ledger["required_secondary_judgments"] != required_secondary:
        raise ReviewLedgerError("required secondary judgment count is not derived")
    if ledger["completed_cases"] != completed:
        raise ReviewLedgerError("completed review count is not derived")
    expected_status = (
        "rejected" if terminal_rejection
        else "complete" if completed == len(entries)
        else "pending_human_review"
    )
    if ledger["status"] != expected_status:
        raise ReviewLedgerError("ledger status is not derived")
    return ledger


def refresh_status(ledger, manifests, selection=None):
    """Derive entry/ledger states after caller-recorded human judgments."""

    updated = copy.deepcopy(ledger)
    instances, selection = _review_instances(manifests, selection)
    events = _reliability_events(updated["entries"], instances)
    global_escalation = len(events) >= 2
    completed = 0
    rejected = False
    for entry, instance in zip(updated["entries"], instances):
        first = entry["reviews"]["primary"]
        entry["secondary_required"] = (
            entry["fixed_double_review"]
            or first is not None and not _canonical_submission(first, _oracle_outcome(instance))
            or global_escalation
        )
        status, complete = _entry_status(entry, instance, global_escalation)
        entry["status"] = status
        completed += int(complete)
        rejected = rejected or status == "rejected"
    updated["completed_cases"] = completed
    updated["reliability_event_cases"] = events
    updated["global_escalation"] = global_escalation
    updated["required_secondary_judgments"] = sum(
        item["secondary_required"] for item in updated["entries"]
    )
    updated["status"] = (
        "rejected" if rejected
        else "complete" if completed == len(instances)
        else "pending_human_review"
    )
    return validate_ledger(updated, manifests, selection)


def review_complete(ledger, manifests, selection=None):
    validate_ledger(ledger, manifests, selection)
    return ledger["status"] == "complete"


def _validate_qualification(value, reviewer_id):
    expected = {
        "reviewer_id", "submission_sha256", "sealed_at",
        "practice_set_version", "practice_set_sha256", "answer_key_sha256",
        "families", "seeded_ambiguity_passed",
        "accepted_alternatives_passed", "score_numerator",
        "score_denominator", "minimum_score", "case_results_sha256",
        "qualification_result_sha256", "qualified",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ReviewLedgerError("qualification record drifted for %s" % reviewer_id)
    protocol = verify_training_artifacts()
    if value["reviewer_id"] != reviewer_id:
        raise ReviewLedgerError("qualification identity drifted for %s" % reviewer_id)
    for field in (
        "submission_sha256", "case_results_sha256",
        "qualification_result_sha256",
    ):
        _validate_sha256(value[field], "qualification %s" % field)
    try:
        sealed = datetime.datetime.fromisoformat(
            value["sealed_at"].replace("Z", "+00:00")
        )
    except (AttributeError, ValueError):
        raise ReviewLedgerError("qualification timestamp is invalid")
    if sealed.utcoffset() is None:
        raise ReviewLedgerError("qualification timestamp requires a timezone")
    if (
        value["practice_set_version"] != protocol["practice_version"]
        or value["practice_set_sha256"] != protocol["practice_sha256"]
        or value["answer_key_sha256"] != protocol["practice_answer_key_sha256"]
    ):
        raise ReviewLedgerError("qualification set binding drifted")
    if sorted(value["families"]) != sorted(FAMILIES):
        raise ReviewLedgerError("qualification set must cover all 11 families")
    if value["seeded_ambiguity_passed"] is not True:
        raise ReviewLedgerError("seeded ambiguity qualification was not passed")
    if value["accepted_alternatives_passed"] is not True:
        raise ReviewLedgerError("alternative-outcome qualification was not passed")
    numerator, denominator = value["score_numerator"], value["score_denominator"]
    if (
        isinstance(numerator, bool) or not isinstance(numerator, int)
        or isinstance(denominator, bool) or not isinstance(denominator, int)
        or denominator <= 0 or not 0 <= numerator <= denominator
    ):
        raise ReviewLedgerError("qualification score is invalid")
    if (
        value["minimum_score"] != protocol["minimum_score"]
        or value["score_denominator"] != protocol["score_denominator"]
        or value["score_numerator"] < value["minimum_score"]
    ):
        raise ReviewLedgerError("qualification threshold was not met")
    if value["qualified"] is not True:
        raise ReviewLedgerError("reviewer is not qualified")


def validate_staffing(staffing, require_ready=True):
    expected = {
        "schema_version", "review_protocol_version", "status",
        "active_reviewers", "backup_reviewers",
    }
    if not isinstance(staffing, dict) or set(staffing) != expected:
        raise ReviewLedgerError("review staffing artifact has unexpected keys")
    if staffing["schema_version"] != STAFFING_SCHEMA:
        raise ReviewLedgerError("review staffing schema drifted")
    if staffing["review_protocol_version"] != REVIEW_PROTOCOL_VERSION:
        raise ReviewLedgerError("review staffing protocol drifted")
    active = staffing["active_reviewers"]
    backups = staffing["backup_reviewers"]
    if not isinstance(active, list) or not isinstance(backups, list):
        raise ReviewLedgerError("reviewer rosters must be lists")
    if not require_ready and not active:
        if staffing["status"] != "pending_real_human_roster":
            raise ReviewLedgerError("empty staffing artifact must remain pending")
        return staffing
    if not 3 <= len(active) <= 4:
        raise ReviewLedgerError("review staffing requires three or four active humans")
    reviewer_keys = {
        "reviewer_id", "name", "identity_attested", "conflicts_attested",
        "availability_attested", "access_ready", "compensation_arranged",
        "confidentiality_attested", "no_generative_ai_attested",
        "no_source_access_attested", "qualification",
    }
    all_people = active + backups
    ids = []
    for reviewer in all_people:
        if not isinstance(reviewer, dict) or set(reviewer) != reviewer_keys:
            raise ReviewLedgerError("reviewer roster record has unexpected keys")
        reviewer_id = _validate_reviewer_id(reviewer["reviewer_id"])
        if not isinstance(reviewer["name"], str) or not reviewer["name"].strip():
            raise ReviewLedgerError("reviewer name is empty")
        for key in reviewer_keys - {"reviewer_id", "name", "qualification"}:
            if reviewer[key] is not True:
                raise ReviewLedgerError("%s is not attested for %s" % (key, reviewer_id))
        _validate_qualification(reviewer["qualification"], reviewer_id)
        ids.append(reviewer_id)
    if len(ids) != len(set(ids)):
        raise ReviewLedgerError("reviewer identities must be unique")
    if staffing["status"] != "ready":
        raise ReviewLedgerError("valid staffing must have status ready")
    return staffing


def build_staffing_template():
    """Return a deliberately unready artifact; software cannot invent humans."""

    return {
        "schema_version": STAFFING_SCHEMA,
        "review_protocol_version": REVIEW_PROTOCOL_VERSION,
        "status": "pending_real_human_roster",
        "active_reviewers": [],
        "backup_reviewers": [],
    }


def staffing_ready(staffing):
    try:
        validate_staffing(staffing, require_ready=True)
    except ReviewLedgerError:
        return False
    return True


def _spread(counter, reviewers):
    values = [counter[item] for item in reviewers]
    return max(values) - min(values)


def build_assignments(manifests, staffing, selection=None):
    validate_staffing(staffing)
    reviewers = sorted(item["reviewer_id"] for item in staffing["active_reviewers"])
    instances, selection = _review_instances(manifests, selection)
    selection_by_id = {item["instance_id"]: item for item in selection["records"]}
    instances = sorted(instances, key=lambda item: (
        not selection_by_id[item["content"]["id"]]["pilot"],
        not selection_by_id[item["content"]["id"]]["fixed_double_review"],
        _digest({
            "namespace": "brick.next-study.review-assignment/3",
            "content_sha256": item["content_sha256"],
        }),
    ))
    ordered_pairs = list(itertools.permutations(reviewers, 2))
    records = []
    primary_counts, expanded_counts = Counter(), Counter()
    planned_counts, fixed_secondary_counts = Counter(), Counter()
    pair_counts, pilot_counts = Counter(), Counter()
    adjudicator_counts = Counter()
    for instance in instances:
        selected = selection_by_id[instance["content"]["id"]]
        fixed, pilot = selected["fixed_double_review"], selected["pilot"]
        choices = []
        for primary, secondary in ordered_pairs:
            trial_primary = primary_counts.copy(); trial_primary[primary] += 1
            trial_expanded = expanded_counts.copy()
            trial_expanded[primary] += 1; trial_expanded[secondary] += 1
            trial_planned = planned_counts.copy(); trial_planned[primary] += 1
            trial_fixed = fixed_secondary_counts.copy()
            if fixed:
                trial_planned[secondary] += 1
                trial_fixed[secondary] += 1
            trial_pilot = pilot_counts.copy()
            if pilot:
                trial_pilot[primary] += 1; trial_pilot[secondary] += 1
            unordered = "|".join(sorted((primary, secondary)))
            trial_pairs = pair_counts.copy(); trial_pairs[unordered] += 1
            choices.append(((
                _spread(trial_pilot, reviewers) if pilot else 0,
                _spread(trial_fixed, reviewers) if fixed else 0,
                _spread(trial_planned, reviewers),
                _spread(trial_expanded, reviewers),
                _spread(trial_primary, reviewers),
                max(trial_pairs.values()) - min(
                    trial_pairs[pair] for pair in (
                        "%s|%s" % pair for pair in itertools.combinations(reviewers, 2)
                    )
                ),
                _digest({
                    "namespace": "brick.next-study.review-assignment-choice/3",
                    "content_sha256": instance["content_sha256"],
                    "primary": primary, "secondary": secondary,
                }),
            ), primary, secondary))
        _score, primary, secondary = min(choices)
        primary_counts[primary] += 1
        expanded_counts[primary] += 1; expanded_counts[secondary] += 1
        planned_counts[primary] += 1
        if fixed:
            planned_counts[secondary] += 1
            fixed_secondary_counts[secondary] += 1
        if pilot:
            pilot_counts[primary] += 1; pilot_counts[secondary] += 1
        pair_counts["|".join(sorted((primary, secondary)))] += 1
        candidates = [item for item in reviewers if item not in (primary, secondary)]
        adjudicator = min(candidates, key=lambda item: (adjudicator_counts[item], item))
        adjudicator_counts[adjudicator] += 1
        packet = review_packet(instance)
        records.append({
            "instance_id": instance["content"]["id"],
            "content_sha256": instance["content_sha256"],
            "packet_id": packet["packet_id"],
            "review_packet_sha256": _digest(packet),
            "fixed_double_review": fixed,
            "pilot": pilot,
            "primary": primary,
            "secondary": secondary,
            "adjudicator": adjudicator,
        })
    # The online greedy choice preserves exact pilot/fixed loads.  Repair the
    # expandable secondary allocation (only outside the fixed sample) so four
    # reviewers also receive exactly equal all-expanded workloads.
    while True:
        secondary_totals = Counter(item["secondary"] for item in records)
        donor = max(reviewers, key=lambda item: (secondary_totals[item], item))
        recipient = min(reviewers, key=lambda item: (secondary_totals[item], item))
        if secondary_totals[donor] - secondary_totals[recipient] <= 1:
            break
        candidates = [
            item for item in records
            if not item["fixed_double_review"] and item["secondary"] == donor
            and item["primary"] != recipient
        ]
        if not candidates:
            raise ReviewLedgerError("secondary allocation cannot be balanced")
        chosen = min(candidates, key=lambda item: _digest({
            "namespace": "brick.next-study.review-secondary-repair/3",
            "packet_id": item["packet_id"], "recipient": recipient,
        }))
        chosen["secondary"] = recipient

    primary_counts, expanded_counts = Counter(), Counter()
    planned_counts, fixed_secondary_counts = Counter(), Counter()
    pair_counts, pilot_counts, adjudicator_counts = Counter(), Counter(), Counter()
    for item in records:
        primary, secondary = item["primary"], item["secondary"]
        primary_counts[primary] += 1
        expanded_counts[primary] += 1; expanded_counts[secondary] += 1
        planned_counts[primary] += 1
        if item["fixed_double_review"]:
            fixed_secondary_counts[secondary] += 1; planned_counts[secondary] += 1
        if item["pilot"]:
            pilot_counts[primary] += 1; pilot_counts[secondary] += 1
        pair_counts["|".join(sorted((primary, secondary)))] += 1
        candidates = [value for value in reviewers if value not in (primary, secondary)]
        adjudicator = min(candidates, key=lambda value: (adjudicator_counts[value], value))
        adjudicator_counts[adjudicator] += 1
        item["adjudicator"] = adjudicator

    document = {
        "schema_version": ASSIGNMENT_SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "review_protocol_version": REVIEW_PROTOCOL_VERSION,
        "staffing_sha256": _digest(staffing),
        "review_selection_sha256": selection["selection_sha256"],
        "case_count": len(records),
        "planned_judgment_count": 396,
        "expanded_judgment_count": 616,
        "fixed_double_review_cases": 88,
        "pilot_cases": 44,
        "pair_counts": dict(sorted(pair_counts.items())),
        "reviewer_primary_counts": dict(sorted(primary_counts.items())),
        "reviewer_fixed_secondary_counts": dict(sorted(fixed_secondary_counts.items())),
        "reviewer_planned_judgment_counts": dict(sorted(planned_counts.items())),
        "reviewer_expanded_judgment_counts": dict(sorted(expanded_counts.items())),
        "reviewer_pilot_judgment_counts": dict(sorted(pilot_counts.items())),
        "records": records,
    }
    return document


def validate_assignments(assignments, manifests, staffing=None, selection=None):
    expected_keys = {
        "schema_version", "generator_version", "review_protocol_version",
        "staffing_sha256", "review_selection_sha256", "case_count",
        "planned_judgment_count", "expanded_judgment_count",
        "fixed_double_review_cases", "pilot_cases", "pair_counts",
        "reviewer_primary_counts", "reviewer_fixed_secondary_counts",
        "reviewer_planned_judgment_counts", "reviewer_expanded_judgment_counts",
        "reviewer_pilot_judgment_counts", "records",
    }
    if not isinstance(assignments, dict) or set(assignments) != expected_keys:
        raise ReviewLedgerError("review assignments have unexpected keys")
    if (
        assignments["schema_version"] != ASSIGNMENT_SCHEMA
        or assignments["generator_version"] != GENERATOR_VERSION
        or assignments["review_protocol_version"] != REVIEW_PROTOCOL_VERSION
    ):
        raise ReviewLedgerError("review assignment version drifted")
    _validate_sha256(assignments["staffing_sha256"], "assignment staffing digest")
    instances, selection = _review_instances(manifests, selection)
    if assignments["review_selection_sha256"] != selection["selection_sha256"]:
        raise ReviewLedgerError("review assignment selection binding drifted")
    by_id = {item["content"]["id"]: item for item in instances}
    selection_by_id = {item["instance_id"]: item for item in selection["records"]}
    records = assignments["records"]
    if (
        not isinstance(records, list) or len(records) != 308
        or assignments["case_count"] != 308
        or assignments["planned_judgment_count"] != 396
        or assignments["expanded_judgment_count"] != 616
        or assignments["fixed_double_review_cases"] != 88
        or assignments["pilot_cases"] != 44
    ):
        raise ReviewLedgerError("review assignment counts drifted")
    record_keys = {
        "instance_id", "content_sha256", "packet_id", "review_packet_sha256",
        "fixed_double_review", "pilot", "primary", "secondary", "adjudicator",
    }
    seen_instances, seen_packets = set(), set()
    pair_counts = Counter()
    primary_counts, fixed_counts = Counter(), Counter()
    planned_counts, expanded_counts, pilot_counts = Counter(), Counter(), Counter()
    for record in records:
        if not isinstance(record, dict) or set(record) != record_keys:
            raise ReviewLedgerError("review assignment record drifted")
        instance = by_id.get(record["instance_id"])
        if instance is None or record["instance_id"] in seen_instances:
            raise ReviewLedgerError("review assignment instance is duplicate or unknown")
        packet = review_packet(instance)
        if (
            record["content_sha256"] != instance["content_sha256"]
            or record["packet_id"] != packet["packet_id"]
            or record["review_packet_sha256"] != _digest(packet)
            or record["packet_id"] in seen_packets
        ):
            raise ReviewLedgerError("review assignment packet binding drifted")
        selected = selection_by_id[record["instance_id"]]
        if (
            record["fixed_double_review"] is not selected["fixed_double_review"]
            or record["pilot"] is not selected["pilot"]
        ):
            raise ReviewLedgerError("review assignment selection flag drifted")
        people = [_validate_reviewer_id(record[role], role) for role in (
            "primary", "secondary", "adjudicator",
        )]
        if len(set(people)) != 3:
            raise ReviewLedgerError("review assignment roles must use three humans")
        seen_instances.add(record["instance_id"])
        seen_packets.add(record["packet_id"])
        pair_counts["|".join(sorted(people[:2]))] += 1
        primary_counts[people[0]] += 1
        expanded_counts[people[0]] += 1; expanded_counts[people[1]] += 1
        planned_counts[people[0]] += 1
        if record["fixed_double_review"]:
            fixed_counts[people[1]] += 1; planned_counts[people[1]] += 1
        if record["pilot"]:
            pilot_counts[people[0]] += 1; pilot_counts[people[1]] += 1
    if set(seen_instances) != set(by_id):
        raise ReviewLedgerError("review assignments do not cover every case")
    if assignments["pair_counts"] != dict(sorted(pair_counts.items())):
        raise ReviewLedgerError("review assignment pair counts are not derived")
    derived = {
        "reviewer_primary_counts": primary_counts,
        "reviewer_fixed_secondary_counts": fixed_counts,
        "reviewer_planned_judgment_counts": planned_counts,
        "reviewer_expanded_judgment_counts": expanded_counts,
        "reviewer_pilot_judgment_counts": pilot_counts,
    }
    for key, counter in derived.items():
        if assignments[key] != dict(sorted(counter.items())):
            raise ReviewLedgerError("%s is not derived" % key)
    reviewer_total = len(primary_counts)
    if reviewer_total not in (3, 4) or any(
        _spread(counter, sorted(primary_counts)) > 1 for counter in derived.values()
    ):
        raise ReviewLedgerError("review assignment allocation is not balanced")
    if staffing is not None:
        validate_staffing(staffing)
        if assignments["staffing_sha256"] != _digest(staffing):
            raise ReviewLedgerError("review assignment staffing binding drifted")
        if assignments != build_assignments(manifests, staffing, selection):
            raise ReviewLedgerError("review assignments are not the frozen deterministic allocation")
    return assignments


def build_pilot(assignments, manifests, frozen_bindings, selection=None):
    validate_assignments(assignments, manifests, selection=selection)
    if not isinstance(frozen_bindings, dict) or not frozen_bindings:
        raise ReviewLedgerError("pilot requires nonempty frozen artifact bindings")
    selected = [item for item in assignments["records"] if item["pilot"]]
    if len(selected) != 44:
        raise ReviewLedgerError("pilot must contain exactly four cases per family")
    pilot_pair_counts = Counter(
        "|".join(sorted((item["primary"], item["secondary"]))) for item in selected
    )
    pilot_reviewer_counts = Counter(
        reviewer for item in selected
        for reviewer in (item["primary"], item["secondary"])
    )
    if max(pilot_reviewer_counts.values()) - min(pilot_reviewer_counts.values()) > 1:
        raise ReviewLedgerError("pilot reviewer workloads are not balanced")
    return {
        "schema_version": PILOT_SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "review_protocol_version": REVIEW_PROTOCOL_VERSION,
        "assignment_sha256": _digest(assignments),
        "frozen_bindings": copy.deepcopy(frozen_bindings),
        "frozen_bindings_sha256": _digest(frozen_bindings),
        "case_count": 44,
        "judgment_count": 88,
        "pair_counts": dict(sorted(pilot_pair_counts.items())),
        "reviewer_judgment_counts": dict(sorted(pilot_reviewer_counts.items())),
        "status": "pending_sealed_reviews",
        "records": selected,
    }


def validate_pilot(pilot, assignments, manifests, frozen_bindings, selection=None):
    if not isinstance(pilot, dict) or pilot != build_pilot(
        assignments, manifests, frozen_bindings, selection
    ):
        raise ReviewLedgerError("review pilot drifted from its frozen selection")
    return pilot


def export_review_packets(
    output_directory, manifests, staffing, assignments, handbook_sha256,
    included_packet_ids=None, requested_roles=None,
):
    """Export blind packets only after the real-human staffing gate passes."""

    validate_staffing(staffing)
    validate_assignments(assignments, manifests, staffing)
    _validate_sha256(handbook_sha256, "packet export handbook digest")
    by_id = {item["content"]["id"]: item for item in _instances(manifests)}
    exports = {
        item["reviewer_id"]: [] for item in staffing["active_reviewers"]
    }
    included_values = None if included_packet_ids is None else list(included_packet_ids)
    included = None if included_values is None else set(included_values)
    known_packet_ids = {item["packet_id"] for item in assignments["records"]}
    if included is not None and (
        len(included) != len(included_values)
        or not included <= known_packet_ids
    ):
        raise ReviewLedgerError("packet export selection is duplicate or unknown")
    if requested_roles is not None:
        if not isinstance(requested_roles, dict):
            raise ReviewLedgerError("requested packet roles must be a mapping")
        for packet_id, roles in requested_roles.items():
            if packet_id not in known_packet_ids or not set(roles) <= set(_SLOTS):
                raise ReviewLedgerError("requested packet role is unknown")
    for assignment in assignments["records"]:
        if included is not None and assignment["packet_id"] not in included:
            continue
        packet = review_packet(by_id[assignment["instance_id"]])
        roles = (
            requested_roles.get(assignment["packet_id"], ())
            if requested_roles is not None
            else ("primary", "secondary") if assignment["fixed_double_review"]
            else ("primary",)
        )
        for role in roles:
            exports[assignment[role]].append({"role": role, "packet": packet})
    output_directory = Path(output_directory)
    written = []
    for reviewer_id, packets in sorted(exports.items()):
        document = {
            "schema_version": "brick.next-study.reviewer-packet-bundle/1",
            "generator_version": GENERATOR_VERSION,
            "review_protocol_version": REVIEW_PROTOCOL_VERSION,
            "assignment_sha256": _digest(assignments),
            "handbook_sha256": handbook_sha256,
            "reviewer_id": reviewer_id,
            "case_count": len(packets),
            "packets": packets,
        }
        path = output_directory / (reviewer_id + ".json")
        replace_canonical_json(path, document)
        written.append(path)
    return written


def export_adjudication_packet(
    output_path, manifests, staffing, assignments, packet_id, handbook_sha256,
):
    """Export one blind packet to its preassigned independent adjudicator."""

    validate_staffing(staffing)
    validate_assignments(assignments, manifests, staffing)
    _validate_sha256(handbook_sha256, "adjudication handbook digest")
    assignment = next(
        (item for item in assignments["records"] if item["packet_id"] == packet_id),
        None,
    )
    if assignment is None:
        raise ReviewLedgerError("adjudication packet is not assigned")
    by_id = {item["content"]["id"]: item for item in _instances(manifests)}
    packet = review_packet(by_id[assignment["instance_id"]])
    document = {
        "schema_version": "brick.next-study.reviewer-packet-bundle/1",
        "generator_version": GENERATOR_VERSION,
        "review_protocol_version": REVIEW_PROTOCOL_VERSION,
        "assignment_sha256": _digest(assignments),
        "handbook_sha256": handbook_sha256,
        "reviewer_id": assignment["adjudicator"],
        "case_count": 1,
        "packets": [{"role": "adjudicator", "packet": packet}],
    }
    output_path = Path(output_path)
    replace_canonical_json(output_path, document)
    return output_path


def seal_submission(
    packet, reviewer_id, role, response, started_at, sealed_at, attestations,
):
    if role not in ("primary", "secondary", "adjudicator"):
        raise ReviewLedgerError("unknown review submission role")
    _validate_reviewer_id(reviewer_id)
    if not isinstance(packet, dict) or set(packet) != {
        "schema_version", "packet_id", "family", "today", "prompt",
        "subepisode_prompts", "initial_state", "tool_schemas",
    } or packet["schema_version"] != PACKET_SCHEMA:
        raise ReviewLedgerError("submission packet schema drifted")
    _validate_sha256(packet["packet_id"], "packet id")
    _validate_review(response, role) if role != "adjudicator" else _validate_adjudication(response)
    identity_key = "reviewer_id" if role != "adjudicator" else "adjudicator_id"
    if response[identity_key] != reviewer_id:
        raise ReviewLedgerError("submission signer disagrees with response identity")
    try:
        started = datetime.datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        sealed = datetime.datetime.fromisoformat(sealed_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise ReviewLedgerError("review timestamps must be ISO-8601")
    if started.utcoffset() is None or sealed.utcoffset() is None:
        raise ReviewLedgerError("review timestamps must include a timezone")
    duration = (sealed - started).total_seconds()
    if duration < 0 or not duration.is_integer():
        raise ReviewLedgerError("review duration must be nonnegative whole seconds")
    required_attestations = {
        "identity_confirmed", "no_source_access", "no_generative_ai",
        "no_case_discussion", "independent_response",
    }
    if role == "adjudicator":
        required_attestations |= {"reviews_unseen_before_seal", "oracle_unseen"}
    if (
        not isinstance(attestations, dict)
        or set(attestations) != required_attestations
        or any(value is not True for value in attestations.values())
    ):
        raise ReviewLedgerError("submission secrecy attestations are incomplete")
    body = {
        "schema_version": SUBMISSION_SCHEMA,
        "packet_id": packet["packet_id"],
        "review_packet_sha256": _digest(packet),
        "reviewer_id": reviewer_id,
        "role": role,
        "response": copy.deepcopy(response),
        "started_at": started_at,
        "sealed_at": sealed_at,
        "review_duration_seconds": int(duration),
        "attestations": copy.deepcopy(attestations),
    }
    body["sealed_response_sha256"] = _digest(body)
    return body


def _validate_sealed_submission(submission):
    expected = {
        "schema_version", "packet_id", "review_packet_sha256", "reviewer_id",
        "role", "response", "started_at", "sealed_at",
        "review_duration_seconds", "attestations",
        "sealed_response_sha256",
    }
    if not isinstance(submission, dict) or set(submission) != expected:
        raise ReviewLedgerError("sealed submission has unexpected keys")
    if submission["schema_version"] != SUBMISSION_SCHEMA:
        raise ReviewLedgerError("sealed submission schema drifted")
    _validate_sha256(submission["packet_id"], "sealed packet id")
    _validate_sha256(
        submission["review_packet_sha256"], "sealed review packet digest"
    )
    _validate_sha256(submission["sealed_response_sha256"], "sealed response digest")
    _validate_reviewer_id(submission["reviewer_id"])
    unsigned = dict(submission)
    supplied = unsigned.pop("sealed_response_sha256")
    if supplied != _digest(unsigned):
        raise ReviewLedgerError("sealed submission digest drifted")
    role = submission["role"]
    if role not in ("primary", "secondary", "adjudicator"):
        raise ReviewLedgerError("sealed submission role is invalid")
    response = submission["response"]
    _validate_review(response, role) if role != "adjudicator" else _validate_adjudication(response)
    identity_key = "reviewer_id" if role != "adjudicator" else "adjudicator_id"
    if response[identity_key] != submission["reviewer_id"]:
        raise ReviewLedgerError("sealed response identity drifted")
    try:
        started = datetime.datetime.fromisoformat(
            submission["started_at"].replace("Z", "+00:00")
        )
        sealed = datetime.datetime.fromisoformat(
            submission["sealed_at"].replace("Z", "+00:00")
        )
    except (AttributeError, ValueError):
        raise ReviewLedgerError("review timestamps must be ISO-8601")
    if started.utcoffset() is None or sealed.utcoffset() is None:
        raise ReviewLedgerError("review timestamps must include a timezone")
    duration = (sealed - started).total_seconds()
    if duration < 0 or not duration.is_integer():
        raise ReviewLedgerError("review duration must be nonnegative whole seconds")
    if int(duration) != submission["review_duration_seconds"]:
        raise ReviewLedgerError("sealed submission duration drifted")
    required_attestations = {
        "identity_confirmed", "no_source_access", "no_generative_ai",
        "no_case_discussion", "independent_response",
    }
    if role == "adjudicator":
        required_attestations |= {"reviews_unseen_before_seal", "oracle_unseen"}
    if (
        not isinstance(submission["attestations"], dict)
        or set(submission["attestations"]) != required_attestations
        or any(value is not True for value in submission["attestations"].values())
    ):
        raise ReviewLedgerError("sealed submission attestations are incomplete")
    return submission


def validate_sealed_submission(submission):
    return _validate_sealed_submission(submission)


def materialize_ledger(
    pending_ledger, manifests, assignments, review_submissions,
    adjudication_submissions=(), selection=None,
):
    """Compile immutable sealed submissions into the derived review ledger."""

    validate_ledger(pending_ledger, manifests, selection)
    validate_assignments(assignments, manifests, selection=selection)
    if pending_ledger["completed_cases"] != 0:
        raise ReviewLedgerError("materialization requires the pristine pending ledger")
    assignment_by_packet = {
        item["packet_id"]: item for item in assignments["records"]
    }
    if len(assignment_by_packet) != 308:
        raise ReviewLedgerError("review assignments do not cover 308 packets")
    instances = {
        item["content"]["id"]: item
        for item in _review_instances(manifests, selection)[0]
    }
    output = copy.deepcopy(pending_ledger)
    entry_by_id = {item["instance_id"]: item for item in output["entries"]}
    seen = set()
    all_submissions = list(review_submissions) + list(adjudication_submissions)
    for submission in all_submissions:
        _validate_sealed_submission(submission)
        packet_id = submission["packet_id"]
        assignment = assignment_by_packet.get(packet_id)
        if assignment is None:
            raise ReviewLedgerError("sealed submission is not assigned")
        role = submission["role"]
        key = (packet_id, role)
        if key in seen:
            raise ReviewLedgerError("duplicate sealed submission")
        seen.add(key)
        expected_reviewer = assignment[role]
        if submission["reviewer_id"] != expected_reviewer:
            raise ReviewLedgerError("sealed submission signer is not assigned")
        instance = instances[assignment["instance_id"]]
        packet = review_packet(instance)
        if (
            submission["review_packet_sha256"] != _digest(packet)
            or submission["review_packet_sha256"]
            != assignment["review_packet_sha256"]
        ):
            raise ReviewLedgerError("sealed submission packet binding drifted")
        entry = entry_by_id[assignment["instance_id"]]
        if role in _SLOTS:
            entry["reviews"][role] = copy.deepcopy(submission)
        else:
            entry["adjudication"] = copy.deepcopy(submission)
    return refresh_status(output, manifests, selection)


def validate_pilot_result(pilot, result, current_frozen_bindings):
    pilot_keys = {
        "schema_version", "generator_version", "review_protocol_version",
        "assignment_sha256", "frozen_bindings", "frozen_bindings_sha256",
        "case_count", "judgment_count", "pair_counts",
        "reviewer_judgment_counts", "status", "records",
    }
    if (
        not isinstance(pilot, dict) or set(pilot) != pilot_keys
        or pilot["schema_version"] != PILOT_SCHEMA
        or pilot["generator_version"] != GENERATOR_VERSION
        or pilot["review_protocol_version"] != REVIEW_PROTOCOL_VERSION
        or pilot["case_count"] != 44 or pilot["judgment_count"] != 88
        or pilot["status"] != "pending_sealed_reviews"
        or not isinstance(pilot["records"], list) or len(pilot["records"]) != 44
        or len({item.get("packet_id") for item in pilot["records"]}) != 44
        or pilot["frozen_bindings_sha256"] != _digest(pilot["frozen_bindings"])
    ):
        raise ReviewLedgerError("pilot artifact is invalid")
    _validate_sha256(pilot["assignment_sha256"], "pilot assignment digest")
    expected = {
        "schema_version", "pilot_sha256", "status", "case_count",
        "judgment_count", "median_review_seconds", "p90_review_seconds",
        "entry_errors", "exact_agreements", "disputes", "adjudications",
        "median_adjudication_seconds", "protocol_changed",
        "prompt_or_oracle_defects", "reliability_events",
        "global_escalation_triggered",
    }
    if not isinstance(result, dict) or set(result) != expected:
        raise ReviewLedgerError("pilot result has unexpected keys")
    if result["schema_version"] != PILOT_RESULT_SCHEMA:
        raise ReviewLedgerError("pilot result schema drifted")
    if result["pilot_sha256"] != _digest(pilot):
        raise ReviewLedgerError("pilot result binding drifted")
    if current_frozen_bindings != pilot["frozen_bindings"]:
        raise ReviewLedgerError("pilot bindings changed after freeze")
    if result["case_count"] != 44 or result["judgment_count"] != 88:
        raise ReviewLedgerError("pilot count drifted")
    for key in (
        "median_review_seconds", "p90_review_seconds", "entry_errors",
        "exact_agreements", "disputes", "adjudications",
        "median_adjudication_seconds", "prompt_or_oracle_defects",
        "reliability_events",
    ):
        if isinstance(result[key], bool) or not isinstance(result[key], int) or result[key] < 0:
            raise ReviewLedgerError("pilot metric %s is invalid" % key)
    if result["protocol_changed"] is not False:
        raise ReviewLedgerError("changed packet or handbook invalidates the pilot")
    if type(result["global_escalation_triggered"]) is not bool:
        raise ReviewLedgerError("pilot escalation flag must be boolean")
    if result["prompt_or_oracle_defects"]:
        raise ReviewLedgerError("pilot prompt/oracle defect retires the generator")
    if result["global_escalation_triggered"] is not (
        result["reliability_events"] >= 2
    ):
        raise ReviewLedgerError("pilot global escalation is not derived")
    if result["adjudications"] != result["disputes"]:
        raise ReviewLedgerError("every pilot dispute requires adjudication")
    if result["exact_agreements"] + result["disputes"] != 44:
        raise ReviewLedgerError("pilot resolutions do not cover all cases")
    if result["status"] != "complete_counted_toward_full_review":
        raise ReviewLedgerError("unchanged valid pilot must count toward completion")
    return result


def compile_adjudicated_outcomes(ledger, manifests, selection=None):
    selection = _selection(manifests, selection)
    validate_ledger(ledger, manifests, selection)
    if not review_complete(ledger, manifests, selection):
        raise ReviewLedgerError("adjudicated outcomes require a complete review ledger")
    records = []
    for entry, instance in zip(ledger["entries"], _review_instances(manifests, selection)[0]):
        reviews = [entry["reviews"][slot] for slot in _SLOTS]
        final_submission = (
            entry["adjudication"] if entry["status"] == "adjudicated"
            else reviews[0]
        )
        final = final_submission["response"]
        records.append({
            "instance_id": entry["instance_id"],
            "content_sha256": entry["content_sha256"],
            "review_packet_sha256": entry["review_packet_sha256"],
            "prompt_valid": final["prompt_valid"],
            "outcome": copy.deepcopy(final["outcome"]),
            "accepted_alternatives": copy.deepcopy(final["accepted_alternatives"]),
            "review_resolution": entry["status"],
        })
    return {
        "schema_version": ADJUDICATED_OUTCOMES_SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "review_protocol_version": REVIEW_PROTOCOL_VERSION,
        "review_selection_sha256": selection["selection_sha256"],
        "review_ledger_sha256": _digest(ledger),
        "case_count": len(records),
        "records": records,
    }


def validate_adjudicated_outcomes(document, manifests, ledger=None, selection=None):
    expected_keys = {
        "schema_version", "generator_version", "review_protocol_version",
        "review_selection_sha256", "review_ledger_sha256", "case_count", "records",
    }
    if not isinstance(document, dict) or set(document) != expected_keys:
        raise ReviewLedgerError("adjudicated outcomes have unexpected keys")
    if (
        document["schema_version"] != ADJUDICATED_OUTCOMES_SCHEMA
        or document["generator_version"] != GENERATOR_VERSION
        or document["review_protocol_version"] != REVIEW_PROTOCOL_VERSION
        or document["case_count"] != 308
    ):
        raise ReviewLedgerError("adjudicated outcome version or count drifted")
    _validate_sha256(document["review_ledger_sha256"], "review ledger digest")
    selection = _selection(manifests, selection)
    if document["review_selection_sha256"] != selection["selection_sha256"]:
        raise ReviewLedgerError("adjudicated outcome selection binding drifted")
    instances = _review_instances(manifests, selection)[0]
    by_id = {item["content"]["id"]: item for item in instances}
    records = document["records"]
    if not isinstance(records, list) or len(records) != 308:
        raise ReviewLedgerError("adjudicated outcomes do not cover human-validity scope")
    record_keys = {
        "instance_id", "content_sha256", "review_packet_sha256",
        "prompt_valid", "outcome", "accepted_alternatives",
        "review_resolution",
    }
    seen = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != record_keys:
            raise ReviewLedgerError("adjudicated outcome record drifted")
        instance = by_id.get(record["instance_id"])
        if instance is None or record["instance_id"] in seen:
            raise ReviewLedgerError("adjudicated outcome identity is duplicate or unknown")
        if (
            record["content_sha256"] != instance["content_sha256"]
            or record["review_packet_sha256"] != _digest(review_packet(instance))
        ):
            raise ReviewLedgerError("adjudicated outcome binding drifted")
        if (
            record["prompt_valid"] is not True
            or not isinstance(record["outcome"], list) or not record["outcome"]
            or record["accepted_alternatives"] != []
            or record["review_resolution"] not in (
                "accepted_single", "agreed", "adjudicated",
            )
        ):
            raise ReviewLedgerError("adjudicated outcome is not a canonical final answer")
        canonical_json_bytes(record["outcome"], allow_float=False)
        seen.add(record["instance_id"])
    if seen != set(by_id):
        raise ReviewLedgerError("adjudicated outcomes omit cases")
    if ledger is not None:
        expected = compile_adjudicated_outcomes(ledger, manifests, selection)
        if document != expected:
            raise ReviewLedgerError("adjudicated outcomes drifted from the sealed ledger")
    return document


__all__ = [
    "LEDGER_SCHEMA",
    "PACKET_SCHEMA",
    "STAFFING_SCHEMA",
    "ASSIGNMENT_SCHEMA",
    "PILOT_SCHEMA",
    "PILOT_RESULT_SCHEMA",
    "SUBMISSION_SCHEMA",
    "ADJUDICATED_OUTCOMES_SCHEMA",
    "REVIEW_PROTOCOL_VERSION",
    "ReviewLedgerError",
    "build_pending_ledger",
    "build_staffing_template",
    "validate_staffing",
    "staffing_ready",
    "build_assignments",
    "build_pilot",
    "export_review_packets",
    "export_adjudication_packet",
    "seal_submission",
    "compile_adjudicated_outcomes",
    "digest_review_artifact",
    "materialize_ledger",
    "validate_pilot_result",
    "validate_pilot",
    "validate_assignments",
    "validate_adjudicated_outcomes",
    "validate_sealed_submission",
    "refresh_status",
    "review_complete",
    "review_packet",
    "validate_ledger",
]
