import inspect

import pytest

from bench import grade as g
from bench import tasks
from harness import office
from harness.memory import MemoryStore
from harness.world import World


@pytest.mark.parametrize("task", tasks.TASKS, ids=lambda task: task["id"])
def test_every_current_grader_scores_a_fresh_world_zero(tmp_path, task):
    world = World(str(tmp_path / task["id"]))
    memory = MemoryStore(str(tmp_path / "memory.jsonl"))
    grader = task["grade"]

    if "mem" in inspect.signature(grader).parameters:
        score, checks = grader(world, mem=memory)
    else:
        score, checks = grader(world)

    assert score == 0.0
    assert checks
    assert not any(passed for _, passed in checks)


@pytest.mark.office
def test_pptx_basic_golden_artifact_scores_full_credit(tmp_path):
    world = World(str(tmp_path / "world"))
    slides = [
        {"title": "Q3 Business Review"},
        {"title": "Agenda", "bullets": ["one", "two", "three"]},
        {"title": "Sales", "bullets": ["one", "two", "three"]},
        {"title": "Marketing", "bullets": ["one", "two", "three"]},
        {"title": "Next Steps", "bullets": ["one", "two", "three"]},
    ]
    office.create_presentation(world.files_dir, "q3_review.pptx", slides)

    score, checks = tasks.grade_pptx_basic(world)

    assert score == 1.0
    assert len(checks) == 11


@pytest.mark.office
def test_xlsx_basic_golden_artifact_scores_full_credit(tmp_path):
    world = World(str(tmp_path / "world"))
    rows = [
        ["Item", "Cost"],
        ["Laptops", 3200],
        ["Software licenses", 1150],
        ["Training", 800],
        ["Travel", 2400],
        ["Total", "=SUM(B2:B5)"],
    ]
    office.create_spreadsheet(world.files_dir, "budget.xlsx", rows)

    score, checks = tasks.grade_xlsx_basic(world)

    assert score == 1.0
    assert len(checks) == 7


@pytest.mark.characterization
def test_file_lookup_uses_substring_not_exact_stem(tmp_path):
    misleading = tmp_path / "not_q3_cheat.pptx"
    misleading.touch()

    assert g._find_file(str(tmp_path), "q3", ".pptx") == str(misleading)


@pytest.mark.characterization
def test_formula_evaluator_crashes_on_multi_letter_columns():
    rows = [[1] * 28, [2] * 28]

    with pytest.raises(TypeError):
        g._cell_number("=SUM(AA1:AB2)", rows)


@pytest.mark.characterization
def test_spreadsheet_grader_does_not_associate_items_with_cost_rows(monkeypatch, tmp_path):
    world = World(str(tmp_path / "world"))
    disconnected = [
        ["laptops"],
        ["software licenses"],
        ["training"],
        ["travel"],
        ["total"],
        [3200, 1150, 800, 2400, 7550],
    ]
    monkeypatch.setattr(g, "_find_file", lambda *_args: "synthetic.xlsx")
    monkeypatch.setattr(g, "xlsx_cells", lambda _path: disconnected)

    score, checks = tasks.grade_xlsx_basic(world)

    assert score == 1.0
    assert len(checks) == 7


@pytest.mark.characterization
def test_presentation_grader_does_not_associate_regions_with_values(monkeypatch, tmp_path):
    world = World(str(tmp_path / "world"))
    slides = [
        ("Summary", []),
        ("West", []),
        ("East", []),
        ("Online", []),
    ]
    monkeypatch.setattr(g, "_find_file", lambda *_args: "synthetic.pptx")
    monkeypatch.setattr(g, "pptx_slides", lambda _path: slides)
    monkeypatch.setattr(
        g,
        "pptx_all_text",
        lambda _path: "all figures together: 1240000 845000 610000",
    )

    score, checks = tasks.grade_pptx_from_email(world)

    assert score == 1.0
    assert len(checks) == 6


@pytest.mark.characterization
def test_conditional_checks_shrink_the_reminder_task_denominator(tmp_path):
    world = World(str(tmp_path / "world"))
    world.send_message("Casey", "The TPS report will be done Friday.")

    score, checks = tasks.grade_remind_msg(world)

    assert score == 0.75
    assert len(checks) == 4


@pytest.mark.characterization
def test_calendar_brief_treats_sam_inside_same_as_a_name_match(tmp_path):
    world = World(str(tmp_path / "world"))
    world.send_message(
        "Jordan",
        "Design review, then 1:1 with the same notes, then Marketing sync.",
    )

    score, checks = tasks.grade_cal_brief(world)

    assert score == 1.0
    assert len(checks) == 5


@pytest.mark.characterization
def test_email_reply_can_pass_without_reading_the_source_email(tmp_path):
    world = World(str(tmp_path / "world"))
    world.send_email("mia@corp.com", "Northwind kickoff", "Yes, I will attend.")

    score, checks = tasks.grade_email_reply(world)

    assert score == 1.0
    assert world.actions == []
    assert len(checks) == 4


@pytest.mark.characterization
def test_learning_store_can_pass_from_preexisting_shared_memory(tmp_path):
    world = World(str(tmp_path / "world"))
    memory = MemoryStore(str(tmp_path / "memory.jsonl"))
    memory.save("Meetings are 25 minutes and never before 10am.")

    score, checks = tasks.grade_learn_store(world, mem=memory)

    assert score == 1.0
    assert world.actions == []
    assert len(checks) == 3
