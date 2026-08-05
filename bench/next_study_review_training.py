"""Frozen out-of-suite qualification instrument for successor reviewers."""

import argparse
import copy
import datetime
import json
from pathlib import Path
import re

from domains.office_demo.contracts import CONTRACT_VERSION, SCHEMAS
from domains.office_demo.pack import PACK
from harness.evidence import canonical_json_bytes
from harness.instances import (
    load_canonical_json, replace_canonical_json, sha256_bytes,
)


ROOT = Path(__file__).resolve().parents[1]
HANDBOOK_PATH = ROOT / "bench" / "NEXT_STUDY_REVIEW_HANDBOOK.md"
PRACTICE_PATH = ROOT / "bench" / "next_study_review_practice.json"
ANSWER_KEY_PATH = ROOT / "bench" / "next_study_review_practice_key.json"
REVIEW_PROTOCOL_PATH = ROOT / "bench" / "next_study_review_protocol.json"
PRACTICE_VERSION = "office-review-practice/1.0.0"
REVIEW_PROTOCOL_VERSION = "office-tiered-human-validation/3.0.0"
PRACTICE_SCHEMA = "brick.next-study.review-practice/1"
ANSWER_KEY_SCHEMA = "brick.next-study.review-practice-key/1"
REVIEW_PROTOCOL_SCHEMA = "brick.next-study.review-protocol/1"
QUALIFICATION_SUBMISSION_SCHEMA = "brick.next-study.qualification-submission/1"
QUALIFICATION_RESULT_SCHEMA = "brick.next-study.qualification-result/1"
MINIMUM_SCORE = 12
FAMILIES = (
    "pptx_basic", "pptx_from_email", "xlsx_basic", "xlsx_from_email",
    "email_reply", "cal_add", "cal_freeslot", "cal_brief", "remind_msg",
    "preference_learning", "multi_offsite",
)
_SAFE_REVIEWER_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


class ReviewTrainingError(ValueError):
    pass


def _digest(value):
    return sha256_bytes(canonical_json_bytes(value, allow_float=False))


def _base_state(**updates):
    state = {
        "emails": [], "events": [], "sent_emails": [], "messages": [],
        "reminders": [], "memory": [], "artifacts": [],
    }
    state.update(updates)
    return state


def _tool_schemas():
    return [
        {
            "name": name,
            "description": PACK.registry.get(name)["desc"],
            "parameters": copy.deepcopy(SCHEMAS[name]),
        }
        for name in PACK.registry.names()
    ]


def _case(identifier, family, prompt, state, outcome, *, valid=True, alternatives=None, subepisodes=None):
    return {
        "packet": {
            "schema_version": "brick.next-study.review-practice-packet/1",
            "practice_id": identifier,
            "family": family,
            "today": "2030-01-15",
            "prompt": prompt,
            "subepisode_prompts": subepisodes or [],
            "initial_state": state,
            "tool_schemas": _tool_schemas(),
        },
        "answer": {
            "practice_id": identifier,
            "prompt_valid": valid,
            "outcome": outcome,
            "accepted_alternatives": alternatives or [],
        },
    }


def _cases():
    email = {
        "id": "practice-source", "from": "sender@practice.example",
        "subject": "APPROVED PRACTICE SOURCE", "date": "2030-01-14 09:00",
        "body": "Approved topic: Cedar. Amount: 125. Status: FINAL.",
    }
    cases = [
        _case(
            "practice-pptx-basic", "pptx_basic",
            "Create practice_overview.pptx with exactly two slides titled Practice Overview and Next Step, in that order.",
            _base_state(), [{
                "type": "presentation_created", "filename": "practice_overview.pptx",
                "ordered_titles": ["Practice Overview", "Next Step"],
                "exact_slide_count": 2, "minimum_bullets_by_slide": [0, 0],
            }],
        ),
        _case(
            "practice-pptx-email", "pptx_from_email",
            "Read email practice-source and create practice_source.pptx with one slide titled Cedar and one bullet containing 125.",
            _base_state(emails=[email]), [
                {"type": "source_read", "id": "practice-source"},
                {"type": "presentation_created", "filename": "practice_source.pptx", "ordered_titles": ["Cedar"], "exact_slide_count": 1, "minimum_bullets_by_slide": [1], "required_values": ["125"]},
            ],
        ),
        _case(
            "practice-xlsx-basic", "xlsx_basic",
            "Create practice_budget.xlsx with headers Item | Cost, row Cedar | 125, and a final Total formula row.",
            _base_state(), [{
                "type": "spreadsheet_created", "filename": "practice_budget.xlsx",
                "headers": ["Item", "Cost"], "ordered_rows_cents": [["Cedar", 12500]],
                "total_cents": 12500, "formula_required": True,
            }],
        ),
        _case(
            "practice-xlsx-email", "xlsx_from_email",
            "Read email practice-source and create practice_receipt.xlsx with headers Item | Amount, row Cedar | 125, and a final Total formula row.",
            _base_state(emails=[email]), [
                {"type": "source_read", "id": "practice-source"},
                {"type": "spreadsheet_created", "filename": "practice_receipt.xlsx", "headers": ["Item", "Amount"], "ordered_rows_cents": [["Cedar", 12500]], "total_cents": 12500, "formula_required": True},
            ],
        ),
        _case(
            "practice-email-reply", "email_reply",
            "Read email practice-source and email sender@practice.example with a subject containing Cedar, confirming attendance exactly once.",
            _base_state(emails=[email]), [
                {"type": "source_read", "id": "practice-source"},
                {"type": "email_sent", "to": "sender@practice.example", "subject_contains": "Cedar", "body_intent": "confirm_attendance", "exact_count": 1},
            ],
        ),
        _case(
            "practice-cal-add", "cal_add",
            "Inspect 2030-01-20, then add Cedar Review from 14:00 to 14:30 with attendee cedar@practice.example.",
            _base_state(), [
                {"type": "calendar_read", "date": "2030-01-20"},
                {"type": "event_created", "title": "Cedar Review", "date": "2030-01-20", "start": "14:00", "end": "14:30", "attendees": ["cedar@practice.example"], "exact_count": 1},
            ],
        ),
        _case(
            "practice-cal-free", "cal_freeslot",
            "Inspect 2030-01-21 and book Cedar Focus from 10:00 to 10:30 with no attendees.",
            _base_state(), [
                {"type": "calendar_read", "date": "2030-01-21"},
                {"type": "event_created", "title": "Cedar Focus", "date": "2030-01-21", "start": "10:00", "end": "10:30", "attendees": [], "exact_count": 1},
            ],
        ),
        _case(
            "practice-cal-brief", "cal_brief",
            "Inspect 2030-01-22 and send exactly one message to Pat containing Cedar Sync then 09:00.",
            _base_state(events=[{"id": "practice-event", "title": "Cedar Sync", "date": "2030-01-22", "start": "09:00", "end": "09:30", "attendees": [], "location": ""}]), [
                {"type": "calendar_read", "date": "2030-01-22"},
                {"type": "message_sent", "to": "Pat", "ordered_mentions": ["Cedar Sync", "09:00"], "exact_count": 1},
            ],
        ),
        _case(
            "practice-reminder", "remind_msg",
            "Set one reminder for 2030-01-23 at 08:00 containing Cedar, then message Pat once containing reminder set.",
            _base_state(), [
                {"type": "reminder_created", "date": "2030-01-23", "time": "08:00", "required_mentions": ["Cedar"], "exact_count": 1},
                {"type": "message_sent", "to": "Pat", "required_mentions": ["reminder set"], "exact_count": 1},
            ],
        ),
        _case(
            "practice-learning", "preference_learning", None,
            _base_state(), [
                {"type": "memory_saved", "required_facts": ["prefers Cedar room"]},
                {"type": "message_sent", "to": "Pat", "required_mentions": ["Cedar room"], "exact_count": 1},
            ], subepisodes=[
                "Remember that the user prefers Cedar room.",
                "Message Pat with the saved room preference.",
            ],
        ),
        _case(
            "practice-offsite", "multi_offsite",
            "Read email practice-source, add Cedar Offsite on 2030-01-24 from 13:00 to 15:00, email sender@practice.example confirming attendance, and create practice_offsite.pptx with one slide titled Cedar Offsite.",
            _base_state(emails=[email]), [
                {"type": "source_read", "id": "practice-source"},
                {"type": "event_created", "title": "Cedar Offsite", "date": "2030-01-24", "start": "13:00", "end": "15:00", "attendees": [], "exact_count": 1},
                {"type": "email_sent", "to": "sender@practice.example", "subject_contains": "Cedar", "body_intent": "confirm_attendance", "exact_count": 1},
                {"type": "presentation_created", "filename": "practice_offsite.pptx", "ordered_titles": ["Cedar Offsite"], "exact_slide_count": 1, "minimum_bullets_by_slide": [0]},
            ],
        ),
        _case(
            "practice-seeded-ambiguity", "seeded_ambiguity",
            "Read the final Cedar email and use it to message Pat.",
            _base_state(emails=[
                {**email, "id": "practice-final-a", "subject": "FINAL CEDAR A"},
                {**email, "id": "practice-final-b", "subject": "FINAL CEDAR B"},
            ]), [], valid=False,
        ),
        _case(
            "practice-seeded-alternative", "seeded_alternative",
            "Send Pat one friendly greeting about Cedar.",
            _base_state(), [{
                "type": "message_sent", "to": "Pat", "exact_text": "Hello Pat — Cedar!", "exact_count": 1,
            }], alternatives=[[{
                "type": "message_sent", "to": "Pat", "exact_text": "Hi Pat — Cedar!", "exact_count": 1,
            }]],
        ),
    ]
    if {item["packet"]["family"] for item in cases} & set(FAMILIES) != set(FAMILIES):
        raise ReviewTrainingError("practice set does not cover all 11 families")
    return cases


def build_artifacts():
    cases = _cases()
    practice = {
        "schema_version": PRACTICE_SCHEMA,
        "version": PRACTICE_VERSION,
        "status": "frozen_out_of_suite",
        "case_count": len(cases),
        "family_cases": 11,
        "seeded_control_cases": 2,
        "packets": [item["packet"] for item in cases],
    }
    key = {
        "schema_version": ANSWER_KEY_SCHEMA,
        "version": PRACTICE_VERSION,
        "administrator_only": True,
        "case_count": len(cases),
        "answers": [item["answer"] for item in cases],
    }
    protocol = {
        "schema_version": REVIEW_PROTOCOL_SCHEMA,
        "version": REVIEW_PROTOCOL_VERSION,
        "generator_version": "office-generators/2.1.0",
        "blind_packet_schema": "brick.next-study.blind-review-packet/2",
        "sealed_submission_schema": "brick.next-study.sealed-review-submission/3",
        "derived_ledger_schema": "brick.next-study.review-ledger/3",
        "staffing_schema": "brick.next-study.review-staffing/3",
        "assignment_schema": "brick.next-study.review-assignments/3",
        "pilot_schema": "brick.next-study.review-pilot/3",
        "pilot_result_schema": "brick.next-study.review-pilot-result/2",
        "tool_contract_version": CONTRACT_VERSION,
        "tool_schemas_sha256": _digest(SCHEMAS),
        "handbook_sha256": sha256_bytes(HANDBOOK_PATH.read_bytes()),
        "practice_version": PRACTICE_VERSION,
        "practice_sha256": _digest(practice),
        "practice_answer_key_sha256": _digest(key),
        "minimum_score": MINIMUM_SCORE,
        "score_denominator": 13,
        "seeded_ambiguity_must_pass": True,
        "seeded_alternative_must_pass": True,
        "primary_reviewers_per_case": 1,
        "fixed_double_review_cases": 88,
        "adaptive_secondary_review": True,
        "global_escalation_event_threshold": 2,
        "active_reviewers_minimum": 3,
        "active_reviewers_maximum": 4,
        "pilot_cases": 44,
        "pilot_judgments": 88,
        "human_validity_cases": 308,
        "planned_judgments": 396,
        "expanded_judgments": 616,
        "machine_conformance_cases": 528,
    }
    return practice, key, protocol


def write_artifacts():
    practice, key, protocol = build_artifacts()
    replace_canonical_json(PRACTICE_PATH, practice)
    replace_canonical_json(ANSWER_KEY_PATH, key)
    replace_canonical_json(REVIEW_PROTOCOL_PATH, protocol)
    return protocol


def verify_artifacts():
    expected = build_artifacts()
    actual = tuple(load_canonical_json(path) for path in (
        PRACTICE_PATH, ANSWER_KEY_PATH, REVIEW_PROTOCOL_PATH,
    ))
    if actual != expected:
        raise ReviewTrainingError("review qualification artifacts drifted")
    return actual[2]


def seal_qualification_submission(reviewer_id, responses, sealed_at, attestations):
    if not isinstance(reviewer_id, str) or _SAFE_REVIEWER_ID.fullmatch(reviewer_id) is None:
        raise ReviewTrainingError("qualification reviewer identity is not a safe opaque id")
    if not isinstance(responses, list) or len(responses) != 13:
        raise ReviewTrainingError("qualification requires 13 responses")
    required = {"identity_confirmed", "no_source_access", "no_generative_ai", "independent_response"}
    if not isinstance(attestations, dict) or set(attestations) != required or any(
        value is not True for value in attestations.values()
    ):
        raise ReviewTrainingError("qualification attestations are incomplete")
    try:
        sealed = datetime.datetime.fromisoformat(sealed_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise ReviewTrainingError("qualification seal timestamp is invalid")
    if sealed.utcoffset() is None:
        raise ReviewTrainingError("qualification seal timestamp requires a timezone")
    document = {
        "schema_version": QUALIFICATION_SUBMISSION_SCHEMA,
        "practice_version": PRACTICE_VERSION,
        "reviewer_id": reviewer_id,
        "responses": copy.deepcopy(responses),
        "sealed_at": sealed_at,
        "attestations": copy.deepcopy(attestations),
    }
    document["submission_sha256"] = _digest(document)
    return document


def score_qualification(submission):
    expected_keys = {
        "schema_version", "practice_version", "reviewer_id", "responses",
        "sealed_at", "attestations", "submission_sha256",
    }
    if not isinstance(submission, dict) or set(submission) != expected_keys:
        raise ReviewTrainingError("qualification submission has unexpected keys")
    unsigned = dict(submission)
    supplied = unsigned.pop("submission_sha256")
    if supplied != _digest(unsigned):
        raise ReviewTrainingError("qualification submission digest drifted")
    # Reuse the constructor for structural and attestation validation.
    seal_qualification_submission(
        submission["reviewer_id"], submission["responses"],
        submission["sealed_at"], submission["attestations"],
    )
    practice, key, protocol = build_artifacts()
    answers = {item["practice_id"]: item for item in key["answers"]}
    response_keys = {
        "practice_id", "prompt_valid", "outcome", "accepted_alternatives",
        "rationale",
    }
    seen, case_results = set(), []
    for response in submission["responses"]:
        if not isinstance(response, dict) or set(response) != response_keys:
            raise ReviewTrainingError("qualification response has unexpected keys")
        identifier = response["practice_id"]
        if identifier in seen or identifier not in answers:
            raise ReviewTrainingError("qualification response identity is invalid")
        seen.add(identifier)
        if not isinstance(response["rationale"], str) or not response["rationale"].strip():
            raise ReviewTrainingError("qualification rationale is empty")
        expected = answers[identifier]
        passed = all(response[key_name] == expected[key_name] for key_name in (
            "prompt_valid", "outcome", "accepted_alternatives",
        ))
        case_results.append({"practice_id": identifier, "passed": passed})
    if set(seen) != set(answers):
        raise ReviewTrainingError("qualification responses are incomplete")
    score = sum(item["passed"] for item in case_results)
    ambiguity_passed = next(
        item["passed"] for item in case_results
        if item["practice_id"] == "practice-seeded-ambiguity"
    )
    alternatives_passed = next(
        item["passed"] for item in case_results
        if item["practice_id"] == "practice-seeded-alternative"
    )
    qualified = score >= MINIMUM_SCORE and ambiguity_passed and alternatives_passed
    summary = {
        "schema_version": QUALIFICATION_RESULT_SCHEMA,
        "reviewer_id": submission["reviewer_id"],
        "submission_sha256": submission["submission_sha256"],
        "sealed_at": submission["sealed_at"],
        "practice_set_version": PRACTICE_VERSION,
        "practice_set_sha256": protocol["practice_sha256"],
        "answer_key_sha256": protocol["practice_answer_key_sha256"],
        "families": list(FAMILIES),
        "seeded_ambiguity_passed": ambiguity_passed,
        "accepted_alternatives_passed": alternatives_passed,
        "score_numerator": score,
        "score_denominator": 13,
        "minimum_score": MINIMUM_SCORE,
        "qualified": qualified,
        "case_results": sorted(case_results, key=lambda item: item["practice_id"]),
    }
    summary["case_results_sha256"] = _digest(summary["case_results"])
    return summary


def qualification_roster_record(result):
    if result.get("schema_version") != QUALIFICATION_RESULT_SCHEMA:
        raise ReviewTrainingError("qualification result schema drifted")
    record = {
        key: copy.deepcopy(result[key]) for key in (
            "reviewer_id", "submission_sha256", "sealed_at",
            "practice_set_version", "practice_set_sha256", "answer_key_sha256",
            "families", "seeded_ambiguity_passed",
            "accepted_alternatives_passed", "score_numerator",
            "score_denominator", "minimum_score", "case_results_sha256",
            "qualified",
        )
    }
    record["qualification_result_sha256"] = _digest(result)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    protocol = write_artifacts() if args.write else verify_artifacts()
    print(json.dumps({
        "status": "written" if args.write else "verified",
        "practice_version": protocol["practice_version"],
        "cases": protocol["score_denominator"],
        "live_model_calls": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    main()


__all__ = [
    "ANSWER_KEY_PATH", "HANDBOOK_PATH", "MINIMUM_SCORE", "PRACTICE_PATH",
    "PRACTICE_VERSION", "REVIEW_PROTOCOL_PATH", "ReviewTrainingError",
    "build_artifacts", "qualification_roster_record", "score_qualification",
    "seal_qualification_submission", "verify_artifacts", "write_artifacts",
]
