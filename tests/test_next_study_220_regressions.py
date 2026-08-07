"""Regression probes for defects that invalidated the v0.13.0 instrument."""

import copy
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook
from pptx import Presentation

from bench.next_study_grader_audit import build_positive_evidence, _rebuild
from bench.next_study_review import digest_review_artifact, review_packet
from domains.office_demo.generators_v2 import generate_instance
from domains.office_demo.outcome_oracle_v2 import derive_outcome
from domains.office_demo.reviewed_grader_v2 import build_grader


def _case(family, index=0):
    instance = generate_instance("adversarial", family, index)
    packet = review_packet(instance)
    effects = derive_outcome(
        packet["family"], packet["prompt"], packet["subepisode_prompts"],
        packet["initial_state"], packet["today"],
    )
    outcome = {
        "instance_id": instance["content"]["id"],
        "content_sha256": instance["content_sha256"],
        "review_packet_sha256": digest_review_artifact(packet),
        "prompt_valid": True,
        "outcome": effects,
        "accepted_alternatives": [],
        "review_resolution": "deterministic_regression_fixture",
    }
    return instance, packet, outcome


def _baseline(tmp_path, family, index=0):
    instance, packet, outcome = _case(family, index)
    evidence = build_positive_evidence(packet, outcome, tmp_path / family)
    assert build_grader(packet, outcome).grade_evidence(evidence).strict_success
    return instance, packet, outcome, evidence


def test_offsite_issued_rank_agrees_with_visible_date_order():
    for index in range(4):
        instance = generate_instance("adversarial", "multi_offsite", index)
        emails = {
            item["id"]: item for item in instance["content"]["initial_state"]["emails"]
        }
        candidates = [item for item in emails if item.startswith("offsite-final-")]
        by_date = sorted(candidates, key=lambda item: emails[item]["date"])
        index_body = emails["offsite-index"]["body"]
        by_rank = sorted(
            candidates,
            key=lambda item: int(index_body.split("id=" + item + ",issued_rank=")[1].split(",", 1)[0]),
        )
        assert by_date == by_rank


def test_preference_title_prefix_is_in_saved_public_facts():
    for index in range(4):
        instance = generate_instance("adversarial", "preference_learning", index)
        store = instance["content"]["ordered_subepisodes"][0]["prompt"]
        facts = store.split("applicable facts:", 1)[1]
        assert "title_prefix=" in facts


def test_reminder_prompt_does_not_print_the_derived_order():
    instance = generate_instance("adversarial", "remind_msg", 0)
    prompt = instance["content"]["prompt"]
    assert "Required checklist mentions" not in prompt
    assert "resulting full ordered ID list" in prompt


def test_receipt_prompt_pins_dollar_conversion_and_grader_enforces_it(tmp_path):
    for index in range(4):
        instance = generate_instance("adversarial", "xlsx_from_email", index)
        assert "USD dollar values" in instance["content"]["prompt"]
        assert "amount_cents=N" in instance["content"]["prompt"]
        assert "N/100 dollars" in instance["content"]["prompt"]

    _instance, packet, outcome, evidence = _baseline(tmp_path, "xlsx_from_email")
    effect = next(item for item in outcome["outcome"] if item["type"] == "spreadsheet_created")
    artifacts = dict(evidence.artifact_map())
    workbook = load_workbook(BytesIO(artifacts[effect["filename"]]))
    sheet = workbook.active
    assert float(sheet.cell(row=2, column=3).value) == (
        effect["ordered_rows_cents"][0][2] / 100
    )
    for row, wanted in enumerate(effect["ordered_rows_cents"], start=2):
        sheet.cell(row=row, column=3).value = wanted[2]
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    artifacts[effect["filename"]] = output.getvalue()
    assert not build_grader(packet, outcome).grade_evidence(
        _rebuild(evidence, artifacts=sorted(artifacts.items()))
    ).strict_success


def test_free_slot_prompt_defines_policy_precedence():
    for index in range(4):
        prompt = generate_instance("adversarial", "cal_freeslot", index)["content"]["prompt"]
        assert "Apply only the named policy" in prompt
        assert "closest_to_preferred selects" in prompt
        assert "equal-distance tie toward the earlier slot" in prompt


def test_reply_prompt_defines_policy_and_exact_field_copy():
    for index in range(4):
        prompt = generate_instance("adversarial", "email_reply", index)["content"]["prompt"]
        assert "decision_key exactly equals" in prompt
        assert "copying all three field values exactly as shown" in prompt
        assert "Do not reply to any other sender or create any reminder" in prompt


def test_reply_rejects_reformatted_required_value_and_extra_business_action(tmp_path):
    _instance, packet, outcome, evidence = _baseline(tmp_path, "email_reply")
    grader = build_grader(packet, outcome)
    effect = next(item for item in outcome["outcome"] if item["type"] == "email_sent")
    state = copy.deepcopy(evidence.state)
    iso_date = effect["required_mentions"][1]
    state["sent_emails"][-1]["body"] = state["sent_emails"][-1]["body"].replace(
        iso_date, "February 5, 2028"
    )
    assert not grader.grade_evidence(_rebuild(evidence, state=state)).strict_success

    state = copy.deepcopy(evidence.state)
    state["reminders"].append({"text": "unrequested", "date": iso_date, "time": "09:00"})
    actions = list(evidence.actions) + [{
        "tool": "set_reminder",
        "args": {"text": "unrequested", "date": iso_date, "time": "09:00"},
        "ok": True,
        "result": "created",
    }]
    assert not grader.grade_evidence(
        _rebuild(evidence, state=state, actions=actions)
    ).strict_success


def test_reminder_dependencies_are_due_date_coherent_and_outputs_are_exact(tmp_path):
    for index in range(4):
        instance = generate_instance("adversarial", "remind_msg", index)
        prompt = instance["content"]["prompt"]
        records = {}
        record_text = prompt.split("Action items: ", 1)[1].split(". Order them", 1)[0]
        for value in record_text.split(" | "):
            fields = dict(part.split("=", 1) for part in value.split(","))
            records[fields["id"]] = fields
        for record in records.values():
            if record["depends_on"] != "none":
                assert records[record["depends_on"]]["due"] <= record["due"]
        assert "breaking multiple-eligible ties by larger priority" in prompt
        assert "first ordered item's due date" in prompt

    _instance, packet, outcome, evidence = _baseline(tmp_path, "remind_msg")
    grader = build_grader(packet, outcome)
    state = copy.deepcopy(evidence.state)
    state["reminders"][-1]["text"] += "; checkpoint-99"
    assert not grader.grade_evidence(_rebuild(evidence, state=state)).strict_success
    state = copy.deepcopy(evidence.state)
    state["messages"][-1]["text"] += "; checkpoint-99"
    assert not grader.grade_evidence(_rebuild(evidence, state=state)).strict_success
    state = copy.deepcopy(evidence.state)
    state["messages"][-1]["text"] = state["messages"][-1]["text"].replace(
        next(item["deadline"] for item in outcome["outcome"] if item["type"] == "message_sent"),
        "the deadline",
    )
    assert not grader.grade_evidence(_rebuild(evidence, state=state)).strict_success


def test_offsite_prompt_defines_rank_direction():
    for index in range(4):
        prompt = generate_instance("adversarial", "multi_offsite", index)["content"]["prompt"]
        assert "largest issued_rank value" in prompt
        assert "largest approval_rank value" in prompt
        assert "largest consensus value" in prompt


def test_missing_inbox_listing_is_rejected(tmp_path):
    _instance, packet, outcome, evidence = _baseline(tmp_path, "email_reply")
    changed = _rebuild(
        evidence,
        actions=[item for item in evidence.actions if item["tool"] != "list_emails"],
    )
    assert not build_grader(packet, outcome).grade_evidence(changed).strict_success


def test_negated_affirmative_intents_are_rejected(tmp_path):
    for family, text in (
        ("email_reply", "I cannot confirm and will not attend."),
        ("remind_msg", "This will not be complete by the deadline."),
    ):
        _instance, packet, outcome, evidence = _baseline(tmp_path, family)
        state = copy.deepcopy(evidence.state)
        if family == "email_reply":
            effect = next(item for item in outcome["outcome"] if item["type"] == "email_sent")
            state["sent_emails"][-1]["body"] = text + " " + " ".join(
                effect.get("required_mentions", [])
            )
        else:
            effect = next(item for item in outcome["outcome"] if item["type"] == "message_sent")
            state["messages"][-1]["text"] = "; ".join(effect["required_mentions"]) + "; " + text
        assert not build_grader(packet, outcome).grade_evidence(
            _rebuild(evidence, state=state)
        ).strict_success


def test_calendar_brief_rejects_forbidden_date(tmp_path):
    _instance, packet, outcome, evidence = _baseline(tmp_path, "cal_brief")
    state = copy.deepcopy(evidence.state)
    state["messages"][0]["text"] += "; 2099-12-31"
    assert not build_grader(packet, outcome).grade_evidence(
        _rebuild(evidence, state=state)
    ).strict_success


def test_calendar_brief_rejects_excluded_title_and_pins_entry_format(tmp_path):
    instance, packet, outcome, evidence = _baseline(tmp_path, "cal_brief", index=1)
    assert "formatting every entry exactly as '<title> at <HH:MM>'" in packet["prompt"]
    excluded = next(
        event["title"] for event in instance["content"]["initial_state"]["events"]
        if not event["title"].startswith("Priority:")
    )
    state = copy.deepcopy(evidence.state)
    state["messages"][0]["text"] += "; " + excluded
    assert not build_grader(packet, outcome).grade_evidence(
        _rebuild(evidence, state=state)
    ).strict_success


def test_basic_families_do_not_require_nonexistent_source_reads(tmp_path):
    for family in ("pptx_basic", "xlsx_basic"):
        _instance, packet, outcome, evidence = _baseline(tmp_path, family)
        assert not any(action["tool"] == "read_email" for action in evidence.actions)
        assert build_grader(packet, outcome).grade_evidence(evidence).strict_success


def test_presentation_numeric_superstring_is_rejected(tmp_path):
    _instance, packet, outcome, evidence = _baseline(tmp_path, "pptx_from_email")
    effect = next(item for item in outcome["outcome"] if item["type"] == "presentation_created")
    artifacts = dict(evidence.artifact_map())
    deck = Presentation(Path(tmp_path / "pptx_from_email" / "artifacts" / effect["filename"]))
    changed = False
    for slide in deck.slides:
        for shape in slide.shapes:
            if not getattr(shape, "has_text_frame", False):
                continue
            for paragraph in shape.text_frame.paragraphs:
                if paragraph.text.strip().isdigit() and not changed:
                    paragraph.text = paragraph.text.strip() + "0"
                    changed = True
    output = tmp_path / "numeric-superstring.pptx"
    deck.save(output)
    artifacts[effect["filename"]] = output.read_bytes()
    assert changed
    assert not build_grader(packet, outcome).grade_evidence(
        _rebuild(evidence, artifacts=sorted(artifacts.items()))
    ).strict_success


def test_scratch_memory_is_neutral_but_requested_memory_is_exact(tmp_path):
    _instance, packet, outcome, evidence = _baseline(tmp_path, "cal_add")
    scratch = "temporary internal scratch note"
    changed = _rebuild(
        evidence,
        memory=list(evidence.memory) + [scratch],
        actions=list(evidence.actions) + [{
            "tool": "save_memory", "args": {"fact": scratch}, "ok": True,
            "result": "saved",
        }],
    )
    assert build_grader(packet, outcome).grade_evidence(changed).strict_success

    _instance, packet, outcome, evidence = _baseline(tmp_path, "preference_learning")
    changed = _rebuild(
        evidence,
        memory=list(evidence.memory) + ["unrequested extra memory"],
        actions=list(evidence.actions) + [{
            "tool": "save_memory", "args": {"fact": "unrequested extra memory"},
            "ok": True, "result": "saved",
        }],
    )
    assert not build_grader(packet, outcome).grade_evidence(changed).strict_success
