"""A registry override stays honest against the classifier it overrides.

Nothing previously checked a registry's read_tools / write_tools entries against
harness.mcp_bridge.classify(). That let an override go stale silently: the
classifier catches up to a name shape the override used to correct, and the
override becomes dead weight nobody notices because it still "works" - it just
duplicates what classify() would say for free. This is exactly how four
get-mailbox-settings read_tools overrides survived after _READ_RE was anchored
to the leading word: get-mailbox-settings starts with "get", so classify()
reaches "read" unaided, and the override that used to be needed for a
non-anchored regex became a no-op nobody removed.
"""
import json
import os
import re

from harness import mcp_bridge, mcp_config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_PATH = os.path.join(ROOT, "mcp", "servers.json")
MCP_DIR = os.path.join(ROOT, "mcp")

REQUIRED_KEYS = {"summary", "command", "args", "prefix"}

# Overrides that classify() would already reach unaided, kept anyway on purpose:
# each of these write_tools names carries no verb _WRITE_RE recognises, so the
# classifier already fails it closed to "write" via the unclassified default
# with no override at all. The override stays because a named entry here is a
# clearer audit trail than relying on that default landing on the same answer
# by coincidence - see the "notes" field on each server entry below for the
# same reasoning. This is the ONLY sanctioned exception; a new redundant
# override needs a new line here plus the same justification in that entry's
# own notes, not just an addition to this set.
EXPECTED_REDUNDANT = {
    (server, tool)
    for server in ("ms365", "ms365-personal", "ms365-work")
    for tool in ("copy-mail-message", "dismiss-calendar-event-reminder",
                 "snooze-calendar-event-reminder")
} | {
    ("selftest", "modify_mail"),
    ("gmail", "modify_email"),
    ("gmail", "batch_modify_emails"),
    ("gmail", "download_attachment"),
}


def _raw_registry():
    with open(REGISTRY_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


def _registry():
    return mcp_config.load_registry(REGISTRY_PATH)


def test_registry_is_valid_json_with_required_keys():
    reg = _registry()
    assert reg, "registry loaded no server entries"
    for name, cfg in reg.items():
        missing = REQUIRED_KEYS - set(cfg)
        assert not missing, f"{name} is missing required keys: {missing}"


def test_overrides_are_load_bearing():
    """For every read_tools / write_tools entry, classify() without it must
    NOT already reach the same answer - otherwise the override is dead."""
    reg = _registry()
    redundant = []
    for name, cfg in reg.items():
        for tool in cfg.get("write_tools", []):
            if (name, tool) in EXPECTED_REDUNDANT:
                continue
            stripped = {k: v for k, v in cfg.items() if k != "write_tools"}
            is_write, why = mcp_bridge.classify(tool, stripped)
            if is_write:
                redundant.append(
                    f"{name}: write_tools override on {tool!r} is redundant, "
                    f"classify() already says write without it ({why})")
        for tool in cfg.get("read_tools", []):
            if (name, tool) in EXPECTED_REDUNDANT:
                continue
            stripped = {k: v for k, v in cfg.items() if k != "read_tools"}
            is_write, why = mcp_bridge.classify(tool, stripped)
            if not is_write:
                redundant.append(
                    f"{name}: read_tools override on {tool!r} is redundant, "
                    f"classify() already says read without it ({why})")
    assert not redundant, "\n".join(redundant)


def test_every_override_is_explained_in_notes():
    reg = _registry()
    for name, cfg in reg.items():
        overridden = list(cfg.get("read_tools", [])) + list(cfg.get("write_tools", []))
        if not overridden:
            continue
        notes = " ".join(cfg.get("notes", []))
        for tool in overridden:
            assert tool in notes, (
                f"{name}: override on {tool!r} is not mentioned in 'notes', "
                f"so a reader has no way to find why it exists")


def test_documentation_pointers_resolve():
    """Any '<name>.md in this folder' pointer in the registry names a real file."""
    raw = _raw_registry()
    blob = json.dumps(raw)
    for match in re.finditer(r"([\w\-]+\.md) in this folder", blob):
        target = os.path.join(MCP_DIR, match.group(1))
        assert os.path.isfile(target), (
            f"registry points at {match.group(1)!r} in this folder, "
            f"but {target} does not exist")


def test_root_relative_command_paths_that_stay_in_repo_exist():
    reg = _registry()
    for name, cfg in reg.items():
        command = cfg.get("command", "")
        if "${ROOT}" not in command:
            continue
        expanded = os.path.normpath(command.replace("${ROOT}", ROOT))
        if os.path.commonpath([expanded, ROOT]) != ROOT:
            # Points outside this repo (a sibling checkout like ../ms365-mcp).
            # Not everyone has that checkout, so this is a skip, not a
            # failure: nothing to assert for this entry.
            continue
        assert os.path.exists(expanded), (
            f"{name}: command path {expanded} does not exist")
