"""Offline contract tests for the connector-only Brix lead workflow."""
import json
from pathlib import Path

from harness.domain import load_domain


ROOT = Path(__file__).resolve().parents[1]


def test_brix_hubspot_domain_has_only_reasoning_and_completion_tools():
    pack = load_domain("brix_hubspot_leads")
    assert pack.name == "brix_hubspot_leads"
    assert set(pack.registry.names()) == {"think", "done"}
    assert "HubSpot is the only source" in pack.prompt_rules
    assert "Draft, not sent" in pack.prompt_rules
    assert "Never invent" in pack.prompt_rules
    assert len(pack.presets) == 1
    assert "Do not change HubSpot or send anything" in pack.presets[0]


def test_brix_hubspot_domain_does_not_import_the_synthetic_crm():
    source = (ROOT / "domains/brix_hubspot_leads/pack.py").read_text(
        encoding="utf-8"
    )
    assert "brix_followup_synthetic" not in source
    assert "services" not in source
    assert "synthetic" not in source.lower()


def test_fictional_hubspot_fixture_is_secret_free_and_uses_reserved_addresses():
    path = ROOT / "connectors/fixtures/brix_hubspot_leads.json"
    raw = path.read_text(encoding="utf-8")
    fixture = json.loads(raw)
    assert fixture["schema_version"] == "brick.hubspot-fictional-fixture/1"
    contacts = fixture["records"]["contacts"]
    assert {row["name"] for row in contacts} == {
        "Dana Reed", "Evan Park", "Morgan Lee",
    }
    assert all(row["email"].endswith("@example.com") for row in contacts)
    lowered = raw.lower()
    assert "access_token" not in lowered
    assert "refresh_token" not in lowered
    assert "client_secret" not in lowered
    assert "portal_id" not in lowered


def test_brix_hubspot_world_exposes_no_persisted_business_state(tmp_path):
    pack = load_domain("brix_hubspot_leads")
    world = pack.make_world(tmp_path, persistent=True)
    assert world.persistent is True
    assert list(tmp_path.iterdir()) == []
    state = pack.inspect(tmp_path, tmp_path / "memory.jsonl")
    assert state["sections"] == []
    assert state["files"] == []
    assert state["memory"] == []


def test_agent_lab_discloses_hubspot_exchange_and_renders_normalized_connector():
    html = (ROOT / "webui/static/index.html").read_text(encoding="utf-8")
    script = (ROOT / "webui/static/app.js").read_text(encoding="utf-8")
    styles = (ROOT / "webui/static/style.css").read_text(encoding="utf-8")
    manifest = (ROOT / "webui/static/manifest.webmanifest").read_text(
        encoding="utf-8"
    )
    assert "Model inference stays on this machine" in html
    assert "Nothing leaves this machine" not in html
    assert "/api/connectors/inspect" in script
    assert "provider.status !== 'ready'" in script
    assert "businessConnectorPanel(e.connectors)" in script
    assert "Requested CRM data is exchanged with HubSpot" in script
    assert "max-height: calc(100vh - var(--dock-h" in styles
    assert "overflow-y: auto" in styles
    assert "Nothing leaves this machine" not in manifest
