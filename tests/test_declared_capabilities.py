"""What a tool declares about itself, and the registry queries built on it.

These declarations exist so a cross-check can ask the registry rather than
consult a list of tool names kept somewhere else. An allow-list of names
silently drops every tool added afterwards; a declaration covers a new tool the
moment it says what it does.

The office_demo assertions are the load-bearing ones. A query that returns an
empty set turns its cross-check into a no-op with no error anywhere, which is
worse than not having the check, so "office_demo declares something" is worth a
test of its own.
"""
import pytest

from harness.domain import load_domain
from harness.tools import ToolRegistry


def _spec(**extra):
    spec = {"desc": "x", "params": {}, "example": {"tool": "t", "args": {}},
            "run": lambda attempt, args: "ok"}
    spec.update(extra)
    return {"t": spec}


def test_office_demo_actually_declares_its_file_tools():
    registry = load_domain("office_demo").registry
    assert registry.file_writing_tools() == {
        "create_presentation", "create_spreadsheet"}
    assert registry.opener_for("q3_raw.xlsx") == "read_spreadsheet"
    assert registry.opener_for("Q3_RAW.XLSX") == "read_spreadsheet", "case"


def test_a_pack_without_files_declares_nothing_and_stays_empty():
    """counter_demo is the portability check: if it ever needs an edit to keep
    working, the abstraction is wrong."""
    registry = load_domain("counter_demo").registry
    assert registry.file_writing_tools() == frozenset()
    assert registry.opener_for("anything.xlsx") is None


def test_an_unknown_extension_has_no_opener():
    registry = load_domain("office_demo").registry
    assert registry.opener_for("notes.txt") is None
    assert registry.opener_for("") is None


def test_the_opener_is_the_first_declaring_tool_in_pack_order():
    registry = ToolRegistry({
        "first": dict(_spec(opens=(".xlsx",))["t"],
                      example={"tool": "first", "args": {}}),
        "second": dict(_spec(opens=(".xlsx",))["t"],
                       example={"tool": "second", "args": {}}),
    })
    assert registry.opener_for("a.xlsx") == "first"


def test_a_misspelled_declaration_is_rejected_at_construction():
    """The one direction this must not fail in. A key that silently evaluates
    false would switch a cross-check off with no error anywhere."""
    with pytest.raises(TypeError):
        ToolRegistry(_spec(writes_file="yes"))
    with pytest.raises(TypeError):
        ToolRegistry(_spec(opens=".xlsx"))          # a bare string, not a list
    with pytest.raises(ValueError):
        ToolRegistry(_spec(opens=("xlsx",)))        # missing the dot
    with pytest.raises(ValueError):
        ToolRegistry(_spec(simulates=""))


def test_declarations_survive_a_merge_so_mcp_tools_keep_theirs():
    base = load_domain("office_demo").registry
    merged = base.merged(_spec(writes_file=True))
    assert "t" in merged.file_writing_tools()
    assert "create_spreadsheet" in merged.file_writing_tools()
