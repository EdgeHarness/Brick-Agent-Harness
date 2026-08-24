"""Effect classification for MCP tools: what a connector author relies on.

The old classifier was a single regex over the tool name that fell through to
"read". These tests pin the two properties that replaced it: the server's own
declaration wins over any guess, and an unrecognised name is a write.
"""
from harness.mcp_bridge import classify
from harness.mcp_config import classification_warnings


def c(name, cfg=None, **annotations):
    tool = {"name": name}
    if annotations:
        tool["annotations"] = annotations
    return classify(name, cfg or {}, tool)


# --------------------------------------------------- the server's own word --

def test_read_only_hint_is_believed():
    assert c("frobnicate_widget", readOnlyHint=True) == (False, "declared")


def test_destructive_hint_is_believed():
    assert c("list_things", destructiveHint=True) == (True, "declared")


def test_read_only_false_declares_a_write():
    assert c("search_things", readOnlyHint=False) == (True, "declared")


def test_registry_override_beats_the_servers_annotation():
    # The operator has seen the tool behave; the server only described it.
    cfg = {"write_tools": ["quiet_deleter"]}
    assert c("quiet_deleter", cfg, readOnlyHint=True) == (True, "override")


# ------------------------------------------------------- the unsafe default --

def test_an_unrecognised_name_is_a_write_not_a_read():
    # The regression that motivated this: no verb _WRITE_RE knows, so the old
    # classifier published these read-only and skipped confirmation.
    for name in ("upsert_contact", "merge_records", "execute_workflow",
                 "sync_pipeline", "enroll_contact_in_sequence"):
        is_write, why = c(name)
        assert (is_write, why) == (True, "unclassified"), name


def test_modify_email_is_a_write_without_needing_an_override():
    # Documented in ADDING-A-CONNECTOR.md as the bite: "modify" is not in
    # _WRITE_RE. The registry still overrides it explicitly, belt and braces.
    assert c("modify_email") == (True, "unclassified")


def test_download_is_a_write_because_it_puts_a_file_on_disk():
    assert c("download_attachment")[0] is True


# ------------------------------------------------------------- read verbs --

def test_leading_read_verbs_are_reads():
    for name in ("list_emails", "get-calendar-event", "search_threads",
                 "read_email", "describe_table", "count_rows"):
        assert c(name) == (False, "read verb"), name


def test_get_mailbox_settings_is_a_read_despite_set_inside_settings():
    # The false positive the registry currently corrects with read_tools.
    assert c("get-mailbox-settings") == (False, "read verb")


def test_write_verbs_still_classify_without_annotations():
    for name in ("send_email", "create-calendar-event", "delete_thread"):
        assert c(name) == (True, "write verb"), name


def test_a_read_verb_does_not_rescue_a_declared_write():
    assert c("get_and_purge", destructiveHint=True) == (True, "declared")


# ------------------------------------------------------------- the audit --

def test_unclassified_tools_are_reported_for_the_author_to_confirm():
    summary = [{
        "id": "hubspot", "mode": "draft",
        "tools": ["hs_upsert_contact", "hs_list_contacts"],
        "writes": ["hs_upsert_contact"],
        "classified_by": {"hs_upsert_contact": "unclassified",
                          "hs_list_contacts": "read verb"},
    }]
    warnings = classification_warnings(summary)
    assert len(warnings) == 1
    assert "hs_upsert_contact" in warnings[0]
    assert "hs_list_contacts" not in warnings[0]
    assert "servers.json" in warnings[0]


def test_a_fully_classified_connector_is_quiet():
    summary = [{
        "id": "gmail", "mode": "draft", "tools": ["gmail_search_emails"],
        "writes": [], "classified_by": {"gmail_search_emails": "read verb"},
    }]
    assert classification_warnings(summary) == []
