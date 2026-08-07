"""Build the terminal reconciliation for the three completed prompt audits."""

from harness.instances import load_canonical_json

from .next_study_fable_reconciliation import DEFAULT_PATH, build_pending, write_reconciliation


SUNNY = "sunnycho100-consolidated-20260806"
MODEL_A = "model-a-kimi-k3-max-20260807"
MODEL_B = "model-b-gpt-5.6-sol-medium-20260807"
MODEL_C = "model-c-claude-fable-5-thinking-high-20260807"
BLOCKER_TEST = "tests/test_next_study_220_regressions.py::test_reported_prompt_grader_blockers_reproduce"
LIVE_GRADER_TEST = "tests/test_next_study_220_regressions.py::test_successor_live_path_uses_only_reviewed_grader"
FEASIBILITY_TEST = "tests/test_next_study_220_regressions.py::test_cal_add_feasibility_is_currently_vacuous"


def _finding(identifier, report_ids, families, severity, blocks, reproduction,
             regression, notes, disposition="confirmed_with_regression"):
    return {
        "finding_id": identifier,
        "report_ids": report_ids,
        "case_ids": ["family-wide:%s" % family for family in families],
        "severity": severity,
        "blocks_authorization": blocks,
        "disposition": disposition,
        "deterministic_reproduction": reproduction,
        "regression_test": regression,
        "notes": notes,
    }


def build_terminal_reconciliation(previous_path=DEFAULT_PATH):
    previous = load_canonical_json(previous_path)
    document = build_pending()
    document["reports_received"] = [
        {
            "report_id": SUNNY,
            "model": "Fable 5 consolidated five-pass audit",
            "source_path": "evidence/next-study/advisory-audits/sunnycho100-report.md",
            "source_content_sha256": "da99b198916b786255f20f490a67597ed2a79eb4183cb687a73c9ea6a8ae7d39",
            "reviewed_generator_version": "office-generators/2.1.0",
            "reviewed_case_count": 308,
            "findings_reported": 11,
        },
        {
            "report_id": MODEL_A,
            "model": "Kimi K3 Max",
            "source_path": "evidence/next-study/advisory-audits/model-a-report.md",
            "source_content_sha256": "5409a368f772c9eeb3df693da6ee639e37d8747aca5bcde23fc62e7aa30f1d70",
            "reviewed_generator_version": "office-generators/2.1.2",
            "reviewed_case_count": 308,
            "findings_reported": 10,
        },
        {
            "report_id": MODEL_B,
            "model": "GPT-5.6 sol medium",
            "source_path": "evidence/next-study/advisory-audits/model-b-report.md",
            "source_content_sha256": "13bb34b65315f215f2963923706131c222661b1fea59c195b7e07e0cbea174e6",
            "reviewed_generator_version": "office-generators/2.1.2",
            "reviewed_case_count": 308,
            "findings_reported": 1,
        },
        {
            "report_id": MODEL_C,
            "model": "Claude Fable 5 thinking high",
            "source_path": "evidence/next-study/advisory-audits/model-c-report.md",
            "source_content_sha256": "907209a2205f017edae9cf57a6d1033d3f35358e00cf587c35ef89c1059b1805",
            "reviewed_generator_version": "office-generators/2.1.2",
            "reviewed_case_count": 308,
            "findings_reported": 16,
        },
    ]
    repaired = []
    for finding in previous["findings"]:
        if finding["report_ids"] != [SUNNY]:
            continue
        item = dict(finding)
        item["severity"] = (
            "low" if item["disposition"] == "refuted_with_reproduction" else "medium"
        )
        item["blocks_authorization"] = False
        repaired.append(item)
    document["findings"] = repaired + [
        _finding(
            "model-a-fnd-01-formula-grammar", [MODEL_A],
            ["xlsx_basic", "xlsx_from_email"], "high", True,
            "A mathematically correct =C2+C3+C4 total fails while =SUM(C2:C4) passes, although the public prompt only requires a formula.",
            BLOCKER_TEST,
            "Confirmed public-contract mismatch in the live reviewed grader.",
        ),
        _finding(
            "model-a-fnd-02-confirmation-language", [MODEL_A],
            ["email_reply", "multi_offsite"], "high", True,
            "The natural sentence 'I confirm my attendance' fails the hidden intent matcher while 'I will attend' passes.",
            BLOCKER_TEST,
            "Confirmed hidden phrase grammar in the live reviewed grader.",
        ),
        _finding(
            "model-a-fnd-03-presentation-bullet-exactness", [MODEL_A],
            ["pptx_basic", "pptx_from_email", "multi_offsite"], "medium", True,
            "A bullet that contains the required value with a faithful public label fails because the live grader requires an exact bare bullet list.",
            BLOCKER_TEST,
            "Confirmed mismatch between include/containing language and exact-list grading.",
        ),
        _finding(
            "model-a-fnd-04-memory-separator", [MODEL_A],
            ["preference_learning"], "medium", True,
            "A memory using the prompt's visible pipe separators fails because the live grader silently splits only on semicolons.",
            BLOCKER_TEST,
            "Confirmed public-format mismatch in the live reviewed grader.",
        ),
        _finding(
            "model-a-fnd-05-legacy-generated-grader", [MODEL_A],
            ["cal_brief", "remind_msg", "email_reply", "multi_offsite", "preference_learning", "pptx_from_email", "xlsx_from_email"],
            "medium", False,
            "The legacy generated grader under-enforces several clauses, but the successor live runner imports and constructs only reviewed_grader_v2.",
            LIVE_GRADER_TEST,
            "Confirmed legacy weakness; nonblocking for the successor live path and retained as historical conformance evidence only.",
        ),
        _finding(
            "model-a-fnd-06-brief-sequence-undefined", [MODEL_A],
            ["pptx_basic"], "medium", True,
            "The public prompt names brief_sequence without defining its ordering rule, while the oracle applies a hidden sequence sort.",
            BLOCKER_TEST,
            "Confirmed family-wide policy-definition defect for the affected policy stratum.",
        ),
        _finding(
            "model-a-fnd-07-cal-add-feasibility-vacuous", [MODEL_A],
            ["cal_add"], "low", False,
            "All generated candidates are feasible under visible calendar state, so feasibility never changes selection.",
            FEASIBILITY_TEST,
            "Confirmed construct limitation without a prompt/outcome contradiction or current outcome impact.",
        ),
        _finding(
            "preference-title-grammar", [MODEL_A, MODEL_B],
            ["preference_learning"], "high", True,
            "The exact lower-case composed title passes while an equally natural title-cased composition fails; the public prompt supplies neither exact title nor composition grammar.",
            BLOCKER_TEST,
            "Independently reported by both new audits; Model A's optional-prefix wording concern is included in this defect.",
        ),
        _finding(
            "model-a-fnd-09-required-mention-order", [MODEL_A],
            ["cal_brief", "email_reply"], "low", True,
            "Reversing enumerated required values fails the live in-order matcher although the prompt does not require that order.",
            BLOCKER_TEST,
            "Confirmed correct-agent-fails alternative; low frequency does not make it safe for an all-or-nothing benchmark.",
        ),
        _finding(
            "model-a-fnd-10-calendar-date-header", [MODEL_A],
            ["cal_brief"], "low", False,
            "The proposed date header is extra content and conflicts with the public instruction to include only exact title/time entries and exclude every other date.",
            None,
            "Refuted as a correct-agent-fails case; the prompt already excludes this output.",
            disposition="refuted_with_reproduction",
        ),
        _finding(
            "model-c-001-email-confirmation-duplicate", [MODEL_C],
            ["email_reply"], "high", False,
            "Natural confirmation language fails the hidden reviewed-grader phrase grammar.",
            BLOCKER_TEST,
            "Independent corroboration of model-a-fnd-02; blocker counted once by defect class.",
        ),
        _finding(
            "model-c-002-offsite-confirmation-duplicate", [MODEL_C],
            ["multi_offsite"], "high", False,
            "Natural confirmation language fails the same hidden phrase grammar in multi_offsite.",
            BLOCKER_TEST,
            "Independent corroboration of model-a-fnd-02; blocker counted once by defect class.",
        ),
        _finding(
            "model-c-003-revenue-bullet-duplicate", [MODEL_C],
            ["pptx_from_email"], "high", False,
            "A labelled revenue bullet contains the exact value but fails exact-list grading.",
            BLOCKER_TEST,
            "Corroborates model-a-fnd-03; blocker counted once by defect class.",
        ),
        _finding(
            "model-c-004-offsite-bullets-duplicate", [MODEL_C],
            ["multi_offsite"], "high", False,
            "Labelled offsite facts satisfy containing language but fail exact-list grading.",
            BLOCKER_TEST,
            "Corroborates model-a-fnd-03; blocker counted once by defect class.",
        ),
        _finding(
            "model-c-005-basic-bullets-duplicate", [MODEL_C],
            ["pptx_basic"], "medium", False,
            "An additional faithful bullet fails although the prompt only requires inclusion.",
            BLOCKER_TEST,
            "Corroborates model-a-fnd-03; blocker counted once by defect class.",
        ),
        _finding(
            "model-c-006-memory-separator-duplicate", [MODEL_C],
            ["preference_learning"], "high", False,
            "The prompt-visible pipe separator fails the hidden semicolon-only matcher.",
            BLOCKER_TEST,
            "Corroborates model-a-fnd-04; blocker counted once by defect class.",
        ),
        _finding(
            "model-c-007-preference-title-duplicate", [MODEL_C],
            ["preference_learning"], "high", False,
            "A natural title-cased composition fails the unstated exact title grammar.",
            BLOCKER_TEST,
            "Corroborates preference-title-grammar; blocker counted once by defect class.",
        ),
        _finding(
            "model-c-008-calendar-date-header", [MODEL_C],
            ["cal_brief"], "medium", False,
            "A dated header adds content outside the exact title/time entry form and conflicts with the instruction to include only those entries.",
            None,
            "Refuted consistently with model-a-fnd-10.",
            disposition="refuted_with_reproduction",
        ),
        _finding(
            "model-c-009-email-mention-order-duplicate", [MODEL_C],
            ["email_reply"], "medium", False,
            "Reordered required fields fail the unstated in-order matcher.",
            BLOCKER_TEST,
            "Corroborates model-a-fnd-09; blocker counted once by defect class.",
        ),
        _finding(
            "model-c-010-brief-mention-order-duplicate", [MODEL_C],
            ["cal_brief"], "medium", False,
            "Reversing the auditor date/count tokens fails the unstated in-order matcher.",
            BLOCKER_TEST,
            "Corroborates model-a-fnd-09; blocker counted once by defect class.",
        ),
        _finding(
            "model-c-011-cal-add-priority-direction", [MODEL_C],
            ["cal_add"], "medium", True,
            "highest_priority_feasible is not defined as the largest numeric value, so the common P1-is-highest reading selects another event and fails.",
            BLOCKER_TEST,
            "New deterministic public-policy ambiguity.",
        ),
        _finding(
            "model-c-012-earliest-start", [MODEL_C],
            ["preference_learning"], "low", False,
            "The use prompt calls the stored value the singular winning start and requires applying it; treating it as a free lower bound does not follow that instruction.",
            None,
            "Refuted as a prompt-correct alternative; no new blocker.",
            disposition="refuted_with_reproduction",
        ),
        _finding(
            "model-c-013-offsite-slide-title", [MODEL_C],
            ["multi_offsite"], "low", True,
            "A slide title that clearly identifies the event but decorates its exact name fails exact-title grading.",
            BLOCKER_TEST,
            "New correct-agent-fails alternative under the current wording.",
        ),
        _finding(
            "model-c-014-offsite-attendees", [MODEL_C],
            ["multi_offsite"], "low", False,
            "The prompt says to use only the selected detail exactly; adding an attendee absent from that detail is an unrequested fact.",
            None,
            "Refuted as a prompt-correct alternative; explicit wording is still useful hardening.",
            disposition="refuted_with_reproduction",
        ),
        _finding(
            "model-c-015-deadline-commitment-language", [MODEL_C],
            ["remind_msg"], "low", True,
            "A clear deadline commitment containing every required identifier and date can fail the hidden phrase grammar.",
            BLOCKER_TEST,
            "New public-language/live-grader mismatch; low severity does not remove all-or-nothing bias.",
        ),
        _finding(
            "model-c-016-accepted-alternatives", [MODEL_C],
            ["all"], "medium", False,
            "The frozen successor intentionally requires a single unambiguous canonical outcome and rejects non-empty accepted alternatives.",
            LIVE_GRADER_TEST,
            "Confirmed systemic constraint, but not an independent blocker once every prompt must meet the single-outcome construct gate.",
        ),
    ]
    document["unresolved_report_count"] = 0
    document["confirmed_authorization_blocker_count"] = 10
    document["status"] = "construct_gate_failed"
    document["authorization_gate_passed"] = False
    return document


def main():
    write_reconciliation(build_terminal_reconciliation())


if __name__ == "__main__":
    main()


__all__ = ["build_terminal_reconciliation", "main"]
