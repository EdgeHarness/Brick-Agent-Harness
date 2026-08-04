"""Two-reviewer, blind adjudication ledger for the successor office suite.

The generated ledger is intentionally pending.  Software can bind packets,
enforce reviewer independence, and verify adjudication, but it cannot invent
the two human judgments required to close the review gate.
"""

import copy

from domains.office_demo.generators_v2 import (
    GENERATOR_VERSION,
    validate_office_instance_v2,
)
from domains.office_demo.outcome_oracle_v2 import derive_outcome
from harness.evidence import canonical_json_bytes
from harness.instances import sha256_bytes


LEDGER_SCHEMA = "brick.next-study.review-ledger/1"
PACKET_SCHEMA = "brick.next-study.blind-review-packet/1"
REVIEW_PROTOCOL_VERSION = "office-two-reviewer-adjudication/1.0.0"
_SLOTS = ("reviewer_a", "reviewer_b")


class ReviewLedgerError(ValueError):
    pass


def _digest(value):
    return sha256_bytes(canonical_json_bytes(value, allow_float=False))


def review_packet(instance):
    """Return only agent-visible task material; hidden outcomes are excluded."""

    validate_office_instance_v2(instance)
    content = instance["content"]
    return {
        "schema_version": PACKET_SCHEMA,
        "instance_id": content["id"],
        "family": content["family"],
        "today": content["today"],
        "prompt": content["prompt"],
        "subepisode_prompts": [
            episode["prompt"] for episode in content["ordered_subepisodes"]
        ],
        "initial_state": copy.deepcopy(content["initial_state"]),
        "available_tools": list(content["tool_names"]),
    }


def _oracle_outcome(instance):
    packet = review_packet(instance)
    return derive_outcome(
        packet["family"], packet["prompt"], packet["subepisode_prompts"],
        packet["initial_state"], packet["today"],
    )


def _instances(manifests):
    instances = [instance for manifest in manifests for instance in manifest["instances"]]
    return sorted(instances, key=lambda item: item["content"]["id"])


def build_pending_ledger(manifests):
    entries = []
    for instance in _instances(manifests):
        content = instance["content"]
        entries.append({
            "instance_id": content["id"],
            "content_sha256": instance["content_sha256"],
            "review_packet_sha256": _digest(review_packet(instance)),
            "oracle_outcome_sha256": _digest(_oracle_outcome(instance)),
            "reviews": {"reviewer_a": None, "reviewer_b": None},
            "adjudication": None,
            "status": "pending",
        })
    ledger = {
        "schema_version": LEDGER_SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "review_protocol_version": REVIEW_PROTOCOL_VERSION,
        "status": "pending_human_review",
        "required_reviewers_per_case": 2,
        "cases": len(entries),
        "completed_cases": 0,
        "entries": entries,
    }
    return validate_ledger(ledger, manifests)


def _validate_review(value, label):
    expected = {
        "reviewer_id", "prompt_valid", "outcome", "accepted_alternatives",
        "rationale",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ReviewLedgerError("%s has unexpected keys" % label)
    if not isinstance(value["reviewer_id"], str) or not value["reviewer_id"].strip():
        raise ReviewLedgerError("%s reviewer_id is empty" % label)
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
    if not isinstance(value["adjudicator_id"], str) or not value["adjudicator_id"].strip():
        raise ReviewLedgerError("adjudicator_id is empty")
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


def _entry_status(entry, instance):
    reviews = entry["reviews"]
    first, second = (reviews[slot] for slot in _SLOTS)
    if first is None and second is None:
        if entry["adjudication"] is not None:
            raise ReviewLedgerError("pending entry has an adjudication")
        return "pending", False
    if first is None or second is None:
        if entry["adjudication"] is not None:
            raise ReviewLedgerError("partially reviewed entry has an adjudication")
        return "in_review", False
    _validate_review(first, "reviewer_a")
    _validate_review(second, "reviewer_b")
    if first["reviewer_id"] == second["reviewer_id"]:
        raise ReviewLedgerError("the two review slots use the same reviewer")
    expected = _oracle_outcome(instance)
    reviews_agree = (
        first["prompt_valid"] == second["prompt_valid"]
        and first["outcome"] == second["outcome"]
        and first["accepted_alternatives"] == second["accepted_alternatives"]
    )
    if reviews_agree:
        if entry["adjudication"] is not None:
            raise ReviewLedgerError("agreed reviews must not be adjudicated")
        complete = (
            first["prompt_valid"] is True
            and first["outcome"] == expected
            and first["accepted_alternatives"] == []
        )
        return ("agreed" if complete else "rejected"), complete
    adjudication = entry["adjudication"]
    if adjudication is None:
        return "disputed", False
    _validate_adjudication(adjudication)
    if adjudication["adjudicator_id"] in {
        first["reviewer_id"], second["reviewer_id"],
    }:
        raise ReviewLedgerError("adjudicator must be independent of both reviewers")
    complete = (
        adjudication["prompt_valid"] is True
        and adjudication["outcome"] == expected
        and adjudication["accepted_alternatives"] == []
    )
    return ("adjudicated" if complete else "rejected"), complete


def validate_ledger(ledger, manifests):
    expected_keys = {
        "schema_version", "generator_version", "review_protocol_version",
        "status", "required_reviewers_per_case", "cases", "completed_cases",
        "entries",
    }
    if not isinstance(ledger, dict) or set(ledger) != expected_keys:
        raise ReviewLedgerError("review ledger has unexpected keys")
    if ledger["schema_version"] != LEDGER_SCHEMA:
        raise ReviewLedgerError("review ledger schema drifted")
    if ledger["generator_version"] != GENERATOR_VERSION:
        raise ReviewLedgerError("review ledger generator version drifted")
    if ledger["review_protocol_version"] != REVIEW_PROTOCOL_VERSION:
        raise ReviewLedgerError("review protocol version drifted")
    if ledger["required_reviewers_per_case"] != 2:
        raise ReviewLedgerError("reviewer count must remain two")
    instances = _instances(manifests)
    entries = ledger["entries"]
    if not isinstance(entries, list) or len(entries) != len(instances):
        raise ReviewLedgerError("review ledger does not cover every case")
    if ledger["cases"] != len(instances):
        raise ReviewLedgerError("review ledger case count is inconsistent")
    completed = 0
    terminal_rejection = False
    for entry, instance in zip(entries, instances):
        expected_entry_keys = {
            "instance_id", "content_sha256", "review_packet_sha256",
            "oracle_outcome_sha256", "reviews", "adjudication", "status",
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
        if not isinstance(entry["reviews"], dict) or set(entry["reviews"]) != set(_SLOTS):
            raise ReviewLedgerError("review slots drifted")
        status, is_complete = _entry_status(entry, instance)
        if entry["status"] != status:
            raise ReviewLedgerError("review entry status is not derived")
        completed += int(is_complete)
        terminal_rejection = terminal_rejection or status == "rejected"
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


def refresh_status(ledger, manifests):
    """Derive entry/ledger states after caller-recorded human judgments."""

    updated = copy.deepcopy(ledger)
    instances = _instances(manifests)
    completed = 0
    rejected = False
    for entry, instance in zip(updated["entries"], instances):
        status, complete = _entry_status(entry, instance)
        entry["status"] = status
        completed += int(complete)
        rejected = rejected or status == "rejected"
    updated["completed_cases"] = completed
    updated["status"] = (
        "rejected" if rejected
        else "complete" if completed == len(instances)
        else "pending_human_review"
    )
    return validate_ledger(updated, manifests)


def review_complete(ledger, manifests):
    validate_ledger(ledger, manifests)
    return ledger["status"] == "complete"


__all__ = [
    "LEDGER_SCHEMA",
    "PACKET_SCHEMA",
    "REVIEW_PROTOCOL_VERSION",
    "ReviewLedgerError",
    "build_pending_ledger",
    "refresh_status",
    "review_complete",
    "review_packet",
    "validate_ledger",
]
