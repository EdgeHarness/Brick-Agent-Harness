"""Offline acceptance tests for the normalized HubSpot/Optix boundary."""
import asyncio
import copy
import hashlib
import json
from pathlib import Path
import socket
import threading
import time
from types import SimpleNamespace
from urllib.parse import parse_qs
from urllib.request import urlopen

import pytest
import requests

from connectors import config, runtime
from connectors.credentials import MemorySecretStore, account_fingerprint
from connectors.errors import (
    AmbiguousWrite,
    CatalogDrift,
    ConnectorConfigError,
    ConnectorUnavailable,
    ProviderEnvironmentFault,
    ProviderRejected,
)
from connectors.hubspot import (
    HubSpotTokenStorage,
    LoopbackOAuthCallback,
    store_client_credentials,
    validate_stored_scope,
)
from connectors.ledger import OperationLedger, client_key
from connectors.optix import INTROSPECTION_DOCUMENT, OptixGraphQLClient, RateLimiter
from connectors.privacy import EphemeralMemoryStore, EphemeralRunStorage
from harness import faults
from harness.privacy import redact, redact_text
from harness.tools import ToolRegistry


HUB_IDENTITY = "portal-123"
OPTIX_IDENTITY = "brix-sandbox"
START = "2026-08-25T10:00:00-05:00"
END = "2026-08-25T11:00:00-05:00"


def _write_json(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    return str(path)


def _sha_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hub_operation(operation, schema, argument_map, result_map, *, verification=None):
    return {
        "operation": operation,
        "argument_map": argument_map,
        "argument_transforms": {},
        "result_map": result_map,
        "error_origin": "model",
        "verification": verification,
        "input_schema_sha256": config.digest(schema),
    }


def _hub_identity(schema):
    value = _hub_operation("whoami", schema, {}, {"account_identity": "/data/portal"})
    value.pop("verification")
    value["error_origin"] = "environment"
    return value


def _optix_operation(
    operation,
    document,
    argument_map,
    result_map,
    *,
    transforms=None,
    verification=None,
):
    return {
        "operation": operation,
        "argument_map": argument_map,
        "argument_transforms": transforms or {},
        "result_map": result_map,
        "error_origin": "model",
        "verification": verification,
        "document": document,
        "document_sha256": _sha_text(document),
    }


def _optix_identity(document):
    value = _optix_operation(
        "identity", document, {}, {"account_identity": "/me/organization_id"}
    )
    value.pop("verification")
    value["error_origin"] = "environment"
    return value


class FakeHubSpot:
    def __init__(self, catalog=None, identity=HUB_IDENTITY):
        self.schemas = catalog or {
            "whoami": {"type": "object", "properties": {}},
            "search_contacts": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
                "required": ["query"],
            },
            "create_note": {
                "type": "object",
                "properties": {
                    "contactId": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["contactId", "body"],
            },
            "get_note": {
                "type": "object",
                "properties": {"noteId": {"type": "string"}},
                "required": ["noteId"],
            },
        }
        self.identity = identity
        self.calls = []
        self.catalog_calls = 0
        self.closed = False
        self.fail = {}

    def catalog(self):
        self.catalog_calls += 1
        return {
            name: {"description": name, "input_schema": copy.deepcopy(schema)}
            for name, schema in self.schemas.items()
        }

    def call(self, operation, arguments, *, error_origin="environment"):
        self.calls.append((operation, copy.deepcopy(arguments), error_origin))
        if operation in self.fail:
            error = self.fail[operation]
            raise error if isinstance(error, Exception) else error()
        if operation == "whoami":
            return {"data": {"portal": self.identity}, "message": "ok"}
        if operation == "search_contacts":
            return {"data": {"contacts": [{"id": "c1"}]}, "message": "ok"}
        if operation == "create_note":
            return {"data": {"note": {"id": "n1"}}, "message": "ok"}
        if operation == "get_note":
            return {"data": {"found": arguments.get("noteId") == "n1"}, "message": "ok"}
        raise AssertionError(operation)

    def close(self):
        self.closed = True


class FakeOptix:
    def __init__(self, identity=OPTIX_IDENTITY):
        self.schema = {
            "queryType": {"fields": [{"name": "me"}, {"name": "members"}]},
            "mutationType": {"fields": [{"name": "bookingsCommit"}]},
        }
        self.identity = identity
        self.calls = []
        self.catalog_calls = 0
        self.closed = False
        self.fail = {}

    def catalog(self):
        self.catalog_calls += 1
        return copy.deepcopy(self.schema)

    def call(
        self,
        operation,
        arguments,
        *,
        document,
        mutating=False,
        safe_retry=False,
        error_origin="environment",
    ):
        self.calls.append(
            (
                operation,
                copy.deepcopy(arguments),
                document,
                mutating,
                safe_retry,
                error_origin,
            )
        )
        if operation in self.fail:
            error = self.fail[operation]
            raise error if isinstance(error, Exception) else error()
        if operation == "identity":
            return {"me": {"organization_id": self.identity}}
        if operation == "members":
            return {"members": [{"member_id": "m1"}]}
        if operation == "bookingsDraft":
            return {
                "bookingsDraft": {
                    "booking_session_id": "s1",
                    "bookings": [{"booking_id": "b1"}],
                }
            }
        if operation == "bookingsCommit":
            return {"bookingsCommit": {"bookings": [{"booking_id": "b1"}]}}
        if operation == "booking":
            return {"booking": {"booking_id": arguments.get("bookingId")}}
        raise AssertionError(operation)

    def close(self):
        self.closed = True


def _hubspot_binding(client):
    catalog = client.catalog()
    verify = _hub_operation(
        "get_note",
        client.schemas["get_note"],
        {"note_id": "noteId"},
        {"verified": "/data/found"},
    )
    verify.pop("verification")
    return {
        "status": "bound",
        "endpoint": "https://mcp.hubspot.com/",
        "account_alias": "sandbox",
        "account_fingerprint_sha256": account_fingerprint(HUB_IDENTITY),
        "catalog_sha256": runtime.discovery_record(
            "hubspot", "sandbox", HUB_IDENTITY, catalog, "https://mcp.hubspot.com/"
        )["catalog_sha256"],
        "oauth_scope": None,
        "identity": _hub_identity(client.schemas["whoami"]),
        "tools": {
            "find_contact": _hub_operation(
                "search_contacts",
                client.schemas["search_contacts"],
                {"query": "query", "limit": "limit"},
                {"contacts": "/data/contacts"},
            ),
            "log_note": _hub_operation(
                "create_note",
                client.schemas["create_note"],
                {"contact_id": "contactId", "body": "body"},
                {"note_id": "/data/note/id"},
                verification=verify,
            ),
        },
    }


def _optix_binding(client):
    identity = "query BrickIdentity { me { organization_id } }"
    members = (
        "query BrickMembers($query:String!,$limit:Int){ "
        "members(query:$query,limit:$limit){ member_id } }"
    )
    draft = "query BrickDraft($input:BookingInput!){ bookingsDraft(input:$input){ booking_session_id bookings{ booking_id } } }"
    commit = "mutation BrickCommit($input:BookingInput!){ bookingsCommit(input:$input){ bookings{ booking_id } } }"
    booking = "query BrickBooking($bookingId:ID!){ booking(id:$bookingId){ booking_id } }"
    verification = _optix_operation(
        "booking", booking, {"booking_id": "/bookingId"},
        {"booking_id": "/booking/booking_id"}
    )
    verification.pop("verification")
    catalog = client.catalog()
    return {
        "status": "bound",
        "endpoint": "https://api.optixapp.com/graphql",
        "account_alias": "sandbox",
        "account_fingerprint_sha256": account_fingerprint(OPTIX_IDENTITY),
        "catalog_sha256": runtime.discovery_record(
            "optix", "sandbox", OPTIX_IDENTITY, catalog,
            "https://api.optixapp.com/graphql",
        )["catalog_sha256"],
        "oauth_scope": None,
        "identity": _optix_identity(identity),
        "tools": {
            "find_member": _optix_operation(
                "members", members, {"query": "/query", "limit": "/limit"},
                {"members": "/members"},
            ),
            "draft_booking": _optix_operation(
                "bookingsDraft",
                draft,
                {
                    "member_id": "/input/account/member_id",
                    "owner_user_id": "/input/owner_user_id",
                    "room_id": "/input/bookings/0/resource_id",
                    "start": "/input/bookings/0/start_timestamp",
                    "end": "/input/bookings/0/end_timestamp",
                },
                {
                    "booking_session_id": "/bookingsDraft/booking_session_id",
                    "booking_id": "/bookingsDraft/bookings/0/booking_id",
                },
                transforms={"start": "iso8601_to_unix", "end": "iso8601_to_unix"},
            ),
            "commit_booking": _optix_operation(
                "bookingsCommit",
                commit,
                {
                    "booking_session_id": "/input/booking_session_id",
                    "member_id": "/input/account/member_id",
                    "owner_user_id": "/input/owner_user_id",
                    "room_id": "/input/bookings/0/resource_id",
                    "start": "/input/bookings/0/start_timestamp",
                    "end": "/input/bookings/0/end_timestamp",
                },
                {"booking_id": "/bookingsCommit/bookings/0/booking_id"},
                transforms={"start": "iso8601_to_unix", "end": "iso8601_to_unix"},
                verification=verification,
            ),
        },
    }


def _bindings_path(tmp_path, *, hubspot=None, optix=None):
    unbound = config.load_bindings()
    doc = copy.deepcopy(unbound)
    if hubspot is not None:
        doc["providers"]["hubspot"] = hubspot
    if optix is not None:
        doc["providers"]["optix"] = optix
    return _write_json(tmp_path / "bindings.json", doc)


def _secrets():
    return MemorySecretStore(
        {
            ("hubspot", "sandbox", "account_identity"): HUB_IDENTITY,
            ("optix", "sandbox", "account_identity"): OPTIX_IDENTITY,
            ("optix", "sandbox", "api_token"): "test-token-never-logged",
        }
    )


def _attempt():
    return SimpleNamespace(attempt_id="offline-attempt")


def test_checked_in_declarations_are_strict_and_unbound_by_default():
    declarations = config.load_declarations()
    bindings = config.load_bindings(declarations=declarations)
    assert declarations["limits"] == {
        "max_connector_tools": 8,
        "max_total_tools": 25,
    }
    assert {tool["name"] for tool in declarations["providers"]["hubspot"]["tools"]} >= {
        "hs_find_contact", "hs_log_note",
    }
    assert {tool["name"] for tool in declarations["providers"]["optix"]["tools"]} >= {
        "optix_room_availability", "optix_commit_booking",
    }
    assert all(item["status"] == "unbound" for item in bindings["providers"].values())
    for provider in declarations["providers"].values():
        for tool in provider["tools"]:
            assert tool["normalized_schema_sha256"] == \
                config.normalized_schema_digest(tool)


def test_unknown_declaration_and_binding_fields_fail_closed(tmp_path):
    declarations = config.load_declarations()
    declarations["surprise"] = True
    with pytest.raises(ConnectorConfigError, match="exactly"):
        config.load_declarations(_write_json(tmp_path / "declarations.json", declarations))

    client = FakeHubSpot()
    binding = _hubspot_binding(client)
    binding["tools"]["find_contact"]["raw_graphql"] = "query Anything"
    with pytest.raises(ConnectorConfigError, match="exactly"):
        config.load_bindings(
            _bindings_path(tmp_path, hubspot=binding), config.load_declarations()
        )

    declarations = config.load_declarations()
    declarations["providers"]["hubspot"]["tools"][0][
        "normalized_schema_sha256"
    ] = "0" * 64
    with pytest.raises(ConnectorConfigError, match="normalized schema digest"):
        config.load_declarations(
            _write_json(tmp_path / "bad-schema-digest.json", declarations)
        )


def test_bound_provider_endpoints_are_exact_and_never_test_loopbacks(tmp_path):
    hubspot = _hubspot_binding(FakeHubSpot())
    hubspot["endpoint"] = "http://127.0.0.1:9999/"
    with pytest.raises(ConnectorConfigError, match="HTTPS"):
        _bindings_path(tmp_path, hubspot=hubspot)
        config.load_bindings(tmp_path / "bindings.json")

    optix = _optix_binding(FakeOptix())
    optix["endpoint"] = "https://api.optixapp.com/arbitrary"
    path = _bindings_path(tmp_path, optix=optix)
    with pytest.raises(ConnectorConfigError, match="official GraphQL"):
        config.load_bindings(path)


def test_optix_bindings_reject_mutating_reads_introspection_and_unsafe_pointers(
    tmp_path,
):
    client = FakeOptix()

    binding = _optix_binding(client)
    operation = binding["tools"]["find_member"]
    operation["document"] = (
        "mutation BrickMembers($query:String!,$limit:Int){ "
        "members(query:$query,limit:$limit){ member_id } }"
    )
    operation["document_sha256"] = _sha_text(operation["document"])
    with pytest.raises(ConnectorConfigError, match="read-only.*mutation"):
        config.load_bindings(_bindings_path(tmp_path, optix=binding))

    binding = _optix_binding(client)
    operation = binding["tools"]["find_member"]
    operation["document"] = "query BrickSchema { __schema { queryType { name } } }"
    operation["document_sha256"] = _sha_text(operation["document"])
    with pytest.raises(ConnectorConfigError, match="introspection"):
        config.load_bindings(_bindings_path(tmp_path, optix=binding))

    binding = _optix_binding(client)
    operation = binding["tools"]["find_member"]
    operation["argument_map"] = {
        "query": "/input",
        "limit": "/input/limit",
    }
    with pytest.raises(ConnectorConfigError, match="may not overlap"):
        config.load_bindings(_bindings_path(tmp_path, optix=binding))

    binding = _optix_binding(client)
    operation = binding["tools"]["find_member"]
    operation["argument_map"]["query"] = "/filter/query"
    with pytest.raises(ConnectorConfigError, match="absent from.*GraphQL document"):
        config.load_bindings(_bindings_path(tmp_path, optix=binding))


def test_invalid_modes_and_python39_fail_before_credentials(monkeypatch):
    with pytest.raises(ConnectorConfigError, match="mode"):
        runtime.enable(["hubspot"], mode="production")
    monkeypatch.setattr(runtime.sys, "version_info", (3, 9, 99))
    with pytest.raises(ConnectorUnavailable, match="Python 3.10"):
        runtime.enable(["hubspot"], mode="read_only")


def test_unbound_provider_refuses_without_opening_a_client():
    with pytest.raises(ConnectorUnavailable, match="unbound"):
        runtime.enable(
            ["hubspot"],
            mode="read_only",
            clients={"hubspot": FakeHubSpot()},
            secrets=_secrets(),
        )


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("read_only", {"hs_find_contact"}),
        ("draft", {"hs_find_contact"}),
        ("live", {"hs_find_contact", "hs_log_note"}),
    ],
)
def test_hubspot_modes_expose_only_reviewed_tools(tmp_path, mode, expected):
    client = FakeHubSpot()
    path = _bindings_path(tmp_path, hubspot=_hubspot_binding(client))
    specs, effects, summary = runtime.enable(
        ["hubspot"], mode=mode, bindings_path=path,
        clients={"hubspot": client}, secrets=_secrets(),
        ledger=OperationLedger(tmp_path / f"{mode}.jsonl"),
    )
    assert set(specs) == expected
    assert set(effects) == expected
    assert summary[0]["account"] == "sandbox"
    assert "provider" in specs[next(iter(specs))]["confirmation"]({})
    runtime.shutdown()
    assert client.closed


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("read_only", {"optix_find_member"}),
        ("draft", {"optix_find_member", "optix_draft_booking"}),
        (
            "live",
            {"optix_find_member", "optix_draft_booking", "optix_commit_booking"},
        ),
    ],
)
def test_optix_draft_is_confirmed_but_commit_is_live_only(tmp_path, mode, expected):
    client = FakeOptix()
    path = _bindings_path(tmp_path, optix=_optix_binding(client))
    specs, effects, _ = runtime.enable(
        ["optix"], mode=mode, bindings_path=path,
        clients={"optix": client}, secrets=_secrets(),
        ledger=OperationLedger(tmp_path / f"optix-{mode}.jsonl"),
    )
    assert set(specs) == expected
    if "optix_draft_booking" in specs:
        assert effects["optix_draft_booking"] == "external_write"
    runtime.shutdown()


def test_live_identity_and_catalog_are_both_bound(tmp_path):
    wrong = FakeHubSpot(identity="another-portal")
    source = FakeHubSpot()
    path = _bindings_path(tmp_path, hubspot=_hubspot_binding(source))
    with pytest.raises(ConnectorUnavailable, match="authenticated account"):
        runtime.enable(
            ["hubspot"], mode="read_only", bindings_path=path,
            clients={"hubspot": wrong}, secrets=_secrets(),
        )

    drifted = FakeHubSpot()
    drifted.schemas["extra_operation"] = {"type": "object", "properties": {}}
    with pytest.raises(CatalogDrift, match="catalog"):
        runtime.enable(
            ["hubspot"], mode="read_only", bindings_path=path,
            clients={"hubspot": drifted}, secrets=_secrets(),
        )

    client = FakeHubSpot()
    binding = _hubspot_binding(client)
    binding["tools"]["find_contact"]["argument_map"]["query"] = "qury"
    path = _bindings_path(tmp_path, hubspot=binding)
    with pytest.raises(ConnectorConfigError, match="does not cover"):
        runtime.enable(
            ["hubspot"], mode="read_only", bindings_path=path,
            clients={"hubspot": client}, secrets=_secrets(),
        )


def test_catalog_is_rechecked_immediately_before_a_write(tmp_path):
    client = FakeHubSpot()
    path = _bindings_path(tmp_path, hubspot=_hubspot_binding(client))
    specs, _, _ = runtime.enable(
        ["hubspot"], mode="live", bindings_path=path,
        clients={"hubspot": client}, secrets=_secrets(),
        ledger=OperationLedger(tmp_path / "ledger.jsonl"),
    )
    client.schemas["new_after_connect"] = {"type": "object", "properties": {}}
    with pytest.raises(CatalogDrift, match="write refused"):
        specs["hs_log_note"]["run"](
            _attempt(), {"contact_id": "c1", "body": "internal note"}
        )
    assert not any(call[0] == "create_note" for call in client.calls)
    runtime.shutdown()


def test_write_ledger_prevents_replay_and_verifies_returned_identifier(tmp_path):
    client = FakeHubSpot()
    path = _bindings_path(tmp_path, hubspot=_hubspot_binding(client))
    ledger = OperationLedger(tmp_path / "ledger.jsonl")
    specs, _, _ = runtime.enable(
        ["hubspot"], mode="live", bindings_path=path,
        clients={"hubspot": client}, secrets=_secrets(), ledger=ledger,
    )
    args = {"contact_id": "c1", "body": "internal note"}
    result = specs["hs_log_note"]["run"](_attempt(), args)
    assert result == {"result": {"note_id": "n1"}, "verification": {"verified": True}}
    assert [item[0] for item in client.calls][-2:] == ["create_note", "get_note"]
    assert client.calls[-1][1] == {"noteId": "n1"}
    with pytest.raises(AmbiguousWrite, match="already started"):
        specs["hs_log_note"]["run"](_attempt(), args)
    assert ledger.latest(next(iter({r["client_key"] for r in _ledger_rows(tmp_path / "ledger.jsonl")})))["status"] == "verified"
    runtime.shutdown()


def test_failed_readback_after_a_completed_write_never_reopens_replay(tmp_path):
    client = FakeHubSpot()
    client.fail["get_note"] = ProviderRejected("verification rejected")
    path = _bindings_path(tmp_path, hubspot=_hubspot_binding(client))
    ledger_path = tmp_path / "ledger.jsonl"
    specs, _, _ = runtime.enable(
        ["hubspot"], mode="live", bindings_path=path,
        clients={"hubspot": client}, secrets=_secrets(),
        ledger=OperationLedger(ledger_path),
    )
    args = {"contact_id": "c1", "body": "internal note"}
    with pytest.raises(ProviderRejected, match="verification rejected"):
        specs["hs_log_note"]["run"](_attempt(), args)
    assert _ledger_rows(ledger_path)[-1]["status"] == "unknown"
    with pytest.raises(AmbiguousWrite, match="already started"):
        specs["hs_log_note"]["run"](_attempt(), args)
    assert sum(call[0] == "create_note" for call in client.calls) == 1
    runtime.shutdown()


def _ledger_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_ambiguous_optix_write_is_never_retried(tmp_path):
    client = FakeOptix()
    client.fail["bookingsDraft"] = AmbiguousWrite("uncertain")
    path = _bindings_path(tmp_path, optix=_optix_binding(client))
    ledger_path = tmp_path / "ledger.jsonl"
    specs, _, _ = runtime.enable(
        ["optix"], mode="draft", bindings_path=path,
        clients={"optix": client}, secrets=_secrets(),
        ledger=OperationLedger(ledger_path),
    )
    args = {
        "member_id": "m1", "owner_user_id": "u1", "room_id": "r1",
        "start": START, "end": END,
    }
    with pytest.raises(AmbiguousWrite, match="uncertain"):
        specs["optix_draft_booking"]["run"](_attempt(), args)
    assert sum(call[0] == "bookingsDraft" for call in client.calls) == 1
    assert _ledger_rows(ledger_path)[-1]["status"] == "unknown"
    with pytest.raises(AmbiguousWrite, match="already started"):
        specs["optix_draft_booking"]["run"](_attempt(), args)
    assert sum(call[0] == "bookingsDraft" for call in client.calls) == 1
    runtime.shutdown()


def test_ambiguous_optix_write_can_only_close_through_a_bound_readback(tmp_path):
    client = FakeOptix()
    client.fail["bookingsCommit"] = AmbiguousWrite("response was lost")
    binding = _optix_binding(client)
    verification = binding["tools"]["commit_booking"]["verification"]
    verification["argument_map"] = {
        "booking_session_id": "/bookingSessionId"
    }
    verification["document"] = (
        "query BrickBookingBySession($bookingSessionId:ID!){ "
        "booking(session_id:$bookingSessionId){ booking_id } }"
    )
    verification["document_sha256"] = _sha_text(verification["document"])
    path = _bindings_path(tmp_path, optix=binding)
    ledger_path = tmp_path / "ledger.jsonl"
    specs, _, _ = runtime.enable(
        ["optix"], mode="live", bindings_path=path,
        clients={"optix": client}, secrets=_secrets(),
        ledger=OperationLedger(ledger_path),
    )
    original_call = client.call

    def call(operation, arguments, **kwargs):
        if operation == "booking":
            client.calls.append(
                (
                    operation, copy.deepcopy(arguments), kwargs.get("document"),
                    kwargs.get("mutating", False), kwargs.get("safe_retry", False),
                    kwargs.get("error_origin", "environment"),
                )
            )
            return {"booking": {"booking_id": "b1"}}
        return original_call(operation, arguments, **kwargs)

    client.call = call
    args = {
        "booking_session_id": "s1", "member_id": "m1",
        "owner_user_id": "u1", "room_id": "r1",
        "start": START, "end": END,
    }
    result = specs["optix_commit_booking"]["run"](_attempt(), args)
    assert result == {
        "result": None,
        "verification": {"booking_id": "b1"},
        "reconciled_after_ambiguous_write": True,
    }
    assert sum(call[0] == "bookingsCommit" for call in client.calls) == 1
    assert sum(call[0] == "booking" for call in client.calls) == 1
    assert _ledger_rows(ledger_path)[-1]["status"] == "verified"
    with pytest.raises(AmbiguousWrite, match="already started"):
        specs["optix_commit_booking"]["run"](_attempt(), args)
    runtime.shutdown()


def test_corrupt_operation_ledger_blocks_writes_instead_of_forgetting_them(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text("not-json\n", encoding="utf-8")
    ledger = OperationLedger(path)
    with pytest.raises(ConnectorUnavailable, match="ledger is corrupt"):
        ledger.latest("0" * 64)


def test_operation_identity_is_stable_across_attempts_and_requires_hex(tmp_path):
    args = {"contact_id": "c1", "body": "same note"}
    assert client_key("hubspot:sandbox", "hs_log_note", args) == client_key(
        "hubspot:sandbox", "hs_log_note", dict(reversed(list(args.items())))
    )
    path = tmp_path / "bad-key.jsonl"
    row = {
        "schema_version": "brick.connector-operation/1",
        "ts_unix_ms": 1,
        "provider": "hubspot",
        "operation": "create_note",
        "client_key": "z" * 64,
        "confirmed": True,
        "status": "prepared",
        "object_sha256": None,
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ConnectorUnavailable, match="key is invalid"):
        OperationLedger(path).latest("0" * 64)


def test_projected_provider_observations_have_a_hard_size_limit():
    with pytest.raises(ProviderEnvironmentFault, match="observation limit"):
        runtime._project(
            {"data": {"value": "x" * (runtime.MAX_PROJECTED_RESULT_BYTES + 1)}},
            {"value": "/data/value"},
        )


def test_iso_times_are_explicitly_converted_and_arbitrary_graphql_is_impossible(tmp_path):
    client = FakeOptix()
    path = _bindings_path(tmp_path, optix=_optix_binding(client))
    specs, _, _ = runtime.enable(
        ["optix"], mode="draft", bindings_path=path,
        clients={"optix": client}, secrets=_secrets(),
        ledger=OperationLedger(tmp_path / "ledger.jsonl"),
    )
    registry = ToolRegistry(specs)
    assert registry.validate("optix_draft_booking", {"query": "mutation { deleteAll }"})
    args = {
        "member_id": "m1", "owner_user_id": "u1", "room_id": "r1",
        "start": START, "end": END,
    }
    result = specs["optix_draft_booking"]["run"](_attempt(), args)
    assert result["booking_session_id"] == "s1"
    call = next(item for item in client.calls if item[0] == "bookingsDraft")
    assert call[1]["input"] == {
        "account": {"member_id": "m1"},
        "owner_user_id": "u1",
        "bookings": [{
            "resource_id": "r1",
            "start_timestamp": 1787670000,
            "end_timestamp": 1787673600,
        }],
    }
    assert "query" not in call[1]
    runtime.shutdown()


@pytest.mark.parametrize(
    "arguments,message",
    [
        ({"query": "x", "limit": 0}, "between 1 and 20"),
        ({"query": "x", "limit": "five"}, "must be an integer"),
    ],
)
def test_normalized_argument_types_fail_as_model_input(tmp_path, arguments, message):
    client = FakeHubSpot()
    path = _bindings_path(tmp_path, hubspot=_hubspot_binding(client))
    specs, _, _ = runtime.enable(
        ["hubspot"], mode="read_only", bindings_path=path,
        clients={"hubspot": client}, secrets=_secrets(),
    )
    with pytest.raises(faults.ModelInputFault, match=message):
        specs["hs_find_contact"]["run"](_attempt(), arguments)
    runtime.shutdown()


def test_normalized_dates_are_strict_model_input(tmp_path):
    client = FakeHubSpot()
    client.schemas["followups"] = {
        "type": "object",
        "properties": {
            "ownerId": {"type": "string"},
            "dueBefore": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "required": ["ownerId", "dueBefore"],
    }
    binding = _hubspot_binding(client)
    binding["tools"]["open_followups"] = _hub_operation(
        "followups",
        client.schemas["followups"],
        {"owner_id": "ownerId", "due_before": "dueBefore", "limit": "limit"},
        {"contacts": "/data/contacts"},
    )
    path = _bindings_path(tmp_path, hubspot=binding)
    specs, _, _ = runtime.enable(
        ["hubspot"], mode="read_only", bindings_path=path,
        clients={"hubspot": client}, secrets=_secrets(),
    )
    with pytest.raises(faults.ModelInputFault, match="ISO 8601 date"):
        specs["hs_open_followups"]["run"](
            _attempt(), {"owner_id": "owner-1", "due_before": "next Tuesday"}
        )
    runtime.shutdown()


def test_safe_read_retries_once_but_model_rejection_does_not(tmp_path):
    client = FakeHubSpot()
    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if attempts["count"] == 1:
            return ProviderEnvironmentFault("temporary")
        return None

    original = client.call

    def call(operation, arguments, *, error_origin="environment"):
        if operation == "search_contacts":
            error = flaky()
            if error:
                raise error
        return original(operation, arguments, error_origin=error_origin)

    client.call = call
    path = _bindings_path(tmp_path, hubspot=_hubspot_binding(client))
    specs, _, _ = runtime.enable(
        ["hubspot"], mode="read_only", bindings_path=path,
        clients={"hubspot": client}, secrets=_secrets(),
    )
    assert specs["hs_find_contact"]["run"](_attempt(), {"query": "alex"})[
        "contacts"
    ] == [{"id": "c1"}]
    assert attempts["count"] == 2
    runtime.shutdown()


def test_tool_limits_count_legacy_mcp_and_final_registry_together():
    class Base:
        def __len__(self):
            return 18

    with pytest.raises(ConnectorConfigError, match="connector tools"):
        runtime.enforce_total_tools(Base(), {str(i): {} for i in range(5)},
                                    other_external_specs={str(i): {} for i in range(4)})
    with pytest.raises(ConnectorConfigError, match="total tools"):
        runtime.enforce_total_tools(Base(), {str(i): {} for i in range(8)})
    assert runtime.enforce_total_tools(Base(), {str(i): {} for i in range(7)}) == 25


def test_capability_preflight_is_clear_and_side_effect_free():
    class Good:
        def chat(self, messages, force_json=False, num_predict=None, role=None):
            raise AssertionError("preflight must not call the backend")

    class Bad:
        def chat(self, messages):
            return ""

    assert runtime.preflight_backend(Good()) is True
    with pytest.raises(ConnectorUnavailable, match="structured chat"):
        runtime.preflight_backend(Bad())
    with pytest.raises(ConnectorUnavailable, match=r"chat\(\.\.\.\)"):
        runtime.preflight_backend(object())


def test_tool_documentation_is_backend_independent(tmp_path):
    client = FakeHubSpot()
    path = _bindings_path(tmp_path, hubspot=_hubspot_binding(client))
    specs, _, _ = runtime.enable(
        ["hubspot"], mode="read_only", bindings_path=path,
        clients={"hubspot": client}, secrets=_secrets(),
    )
    docs = ToolRegistry(specs).docs(with_examples=True)
    assert docs == ToolRegistry(copy.copy(specs)).docs(with_examples=True)
    assert "search_contacts" not in docs
    assert "hs_find_contact" in docs
    runtime.shutdown()


class FakeResponse:
    def __init__(self, status=200, payload=None, headers=None):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.trust_env = True
        self.closed = False

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def close(self):
        self.closed = True


def test_optix_transport_retries_reads_once_and_never_retries_writes():
    read_session = FakeSession(
        [requests.Timeout("slow"), FakeResponse(payload={"data": {"ok": True}})]
    )
    client = OptixGraphQLClient(
        endpoint="http://127.0.0.1/graphql", token="secret",
        session=read_session, sleep=lambda _: None,
    )
    assert client.call(
        "read", {}, document="query { ok }", safe_retry=True
    ) == {"ok": True}
    assert len(read_session.calls) == 2
    assert read_session.trust_env is False

    write_session = FakeSession([requests.Timeout("slow")])
    writer = OptixGraphQLClient(
        endpoint="http://127.0.0.1/graphql", token="secret",
        session=write_session, sleep=lambda _: None,
    )
    with pytest.raises(AmbiguousWrite, match="reconcile"):
        writer.call(
            "write", {}, document="mutation { write }",
            mutating=True, safe_retry=True,
        )
    assert len(write_session.calls) == 1


def test_optix_graphql_model_errors_and_environment_errors_remain_separate():
    model = FakeSession([
        FakeResponse(payload={
            "errors": [{
                "message": "bad room", "extensions": {"code": "BAD_USER_INPUT"},
            }]
        })
    ])
    client = OptixGraphQLClient(
        endpoint="http://127.0.0.1/graphql", token="secret", session=model
    )
    with pytest.raises(ProviderRejected, match="bad room"):
        client.call(
            "read", {}, document="query { room }", error_origin="model"
        )

    identity = FakeSession([FakeResponse(payload={
        "errors": [{
            "message": "bad identity input",
            "extensions": {"code": "BAD_USER_INPUT"},
        }]
    })])
    client = OptixGraphQLClient(
        endpoint="http://127.0.0.1/graphql", token="secret", session=identity
    )
    with pytest.raises(ProviderEnvironmentFault, match="bad identity input"):
        client.call("identity", {}, document="query { me { id } }")

    environment = FakeSession([
        FakeResponse(payload={
            "errors": [{
                "message": "backend unavailable", "extensions": {"code": "INTERNAL"},
            }]
        })
    ])
    client = OptixGraphQLClient(
        endpoint="http://127.0.0.1/graphql", token="secret", session=environment
    )
    with pytest.raises(ProviderEnvironmentFault, match="backend unavailable"):
        client.call("read", {}, document="query { room }")


def test_rate_limiter_enforces_sixty_per_minute_without_guessing_headers():
    now = [0.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(limit=2, window=60, clock=lambda: now[0], sleep=sleep)
    limiter.acquire()
    limiter.acquire()
    limiter.acquire()
    assert sleeps == [60.0]


def test_optix_discovery_fingerprints_nested_input_and_output_types():
    assert "types {" in INTROSPECTION_DOCUMENT
    assert "inputFields" in INTROSPECTION_DOCUMENT
    assert "defaultValue" in INTROSPECTION_DOCUMENT
    assert INTROSPECTION_DOCUMENT.count("ofType") >= 8


def test_hubspot_tokens_and_client_secret_stay_in_secret_store():
    pytest.importorskip("mcp")
    from mcp.shared.auth import OAuthToken

    secrets = MemorySecretStore()
    redirect = store_client_credentials(
        secrets,
        "sandbox",
        client_id="client-id",
        client_secret="client-secret-value",
    )
    assert redirect == "http://127.0.0.1:8765/oauth/callback"
    client_info = secrets.get_json("hubspot", "sandbox", "oauth_client")
    assert client_info["client_secret"] == "client-secret-value"
    assert client_info["token_endpoint_auth_method"] == "client_secret_post"

    storage = HubSpotTokenStorage(secrets, "sandbox")
    tokens = OAuthToken(
        access_token="access-secret", refresh_token="refresh-secret", expires_in=1
    )
    asyncio.run(storage.set_tokens(tokens))
    loaded = asyncio.run(storage.get_tokens())
    assert loaded.access_token == "access-secret"
    assert loaded.refresh_token == "refresh-secret"
    assert asyncio.run(storage.get_client_info()).client_id == "client-id"

    expired = secrets.get_json("hubspot", "sandbox", "oauth_tokens")
    expired["_brick_expires_at"] = 0
    secrets.set_json("hubspot", "sandbox", "oauth_tokens", expired)
    loaded = asyncio.run(storage.get_tokens())
    assert loaded.access_token == ""
    assert loaded.refresh_token == "refresh-secret"
    assert loaded.expires_in == 0

    assert validate_stored_scope(secrets, "sandbox", None)
    secrets.set_json(
        "hubspot", "sandbox", "oauth_tokens",
        {"access_token": "x", "token_type": "Bearer", "scope": "crm.read notes.read"},
    )
    assert validate_stored_scope(secrets, "sandbox", "crm.read")
    with pytest.raises(ProviderEnvironmentFault, match="missing reviewed scopes"):
        validate_stored_scope(secrets, "sandbox", "crm.read notes.write")


def _unused_loopback_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run_oauth_callback(callback, query):
    result = {}

    def target():
        try:
            result["value"] = asyncio.run(callback.callback())
        except BaseException as exc:  # captured for assertion in the test thread
            result["error"] = exc

    worker = threading.Thread(target=target)
    worker.start()
    deadline = time.monotonic() + 3
    while callback.server is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert callback.server is not None
    with urlopen(callback.redirect_uri + query, timeout=3) as response:
        assert response.status == 200
    worker.join(timeout=3)
    assert not worker.is_alive()
    callback.close()
    return result


def test_loopback_oauth_fake_callback_requires_the_bound_state(monkeypatch):
    pytest.importorskip("mcp")
    monkeypatch.setattr(
        "connectors.hubspot.webbrowser.open", lambda _url: True
    )

    accepted = LoopbackOAuthCallback(
        interactive=True, timeout=2, port=_unused_loopback_port()
    )
    asyncio.run(
        accepted.redirect("https://example.test/authorize?state=bound-state")
    )
    assert accepted.server is not None
    result = _run_oauth_callback(
        accepted, "?code=authorization-code&state=bound-state"
    )
    assert result["value"].code == "authorization-code"
    assert result["value"].state == "bound-state"

    rejected = LoopbackOAuthCallback(
        interactive=True, timeout=2, port=_unused_loopback_port()
    )
    asyncio.run(
        rejected.redirect("https://example.test/authorize?state=expected")
    )
    result = _run_oauth_callback(rejected, "?code=x&state=wrong")
    assert isinstance(result["error"], ConnectorUnavailable)
    assert "state mismatch" in str(result["error"])


def test_official_sdk_pkce_generation_is_s256_and_not_constant():
    pytest.importorskip("mcp")
    from mcp.client.auth import PKCEParameters

    first = PKCEParameters.generate()
    second = PKCEParameters.generate()
    assert 43 <= len(first.code_verifier) <= 128
    assert 43 <= len(first.code_challenge) <= 128
    assert first.code_verifier != second.code_verifier
    assert first.code_challenge != second.code_challenge


def test_expired_hubspot_grant_uses_the_official_refresh_flow():
    pytest.importorskip("mcp")
    httpx2 = pytest.importorskip("httpx2")
    from mcp.client.auth import OAuthClientProvider
    from mcp.shared.auth import OAuthClientMetadata, OAuthToken

    secrets = MemorySecretStore()
    store_client_credentials(
        secrets, "sandbox", client_id="client-id", client_secret="client-secret"
    )
    storage = HubSpotTokenStorage(secrets, "sandbox")

    async def exercise():
        await storage.set_tokens(
            OAuthToken(
                access_token="expired", refresh_token="refresh-token",
                expires_in=1, scope="crm.read",
            )
        )
        stored = secrets.get_json("hubspot", "sandbox", "oauth_tokens")
        stored["_brick_expires_at"] = 0
        secrets.set_json("hubspot", "sandbox", "oauth_tokens", stored)
        provider = OAuthClientProvider(
            "https://mcp.hubspot.com/",
            OAuthClientMetadata(
                client_name="Brick Agent Harness",
                redirect_uris=["http://127.0.0.1:8765/oauth/callback"],
                scope="crm.read",
            ),
            storage,
        )
        original = httpx2.Request(
            "POST", "https://mcp.hubspot.com/",
            headers={"MCP-Protocol-Version": "2025-06-18"},
        )
        flow = provider.async_auth_flow(original)
        refresh_request = await flow.__anext__()
        fields = parse_qs(refresh_request.content.decode("ascii"))
        assert fields["grant_type"] == ["refresh_token"]
        assert fields["refresh_token"] == ["refresh-token"]
        resumed = await flow.asend(
            httpx2.Response(
                200,
                json={
                    "access_token": "fresh-token", "token_type": "Bearer",
                    "expires_in": 3600,
                },
                request=refresh_request,
            )
        )
        assert resumed.headers["Authorization"] == "Bearer fresh-token"
        with pytest.raises(StopAsyncIteration):
            await flow.asend(httpx2.Response(200, json={}, request=resumed))

    asyncio.run(exercise())
    stored = secrets.get_json("hubspot", "sandbox", "oauth_tokens")
    assert stored["access_token"] == "fresh-token"
    assert stored["refresh_token"] == "refresh-token"
    assert stored["scope"] == "crm.read"


def test_credentials_are_redacted_from_structures_and_diagnostics():
    secret = "very-secret-token"
    clean = redact(
        {
            "authorization": "Bearer " + secret,
            "nested": {"client_secret": secret, "message": "token=" + secret},
        }
    )
    encoded = json.dumps(clean)
    assert secret not in encoded
    assert encoded.count("[redacted]") >= 3
    assert secret not in redact_text("Authorization: Bearer " + secret)


def test_real_account_memory_is_run_only_and_never_creates_a_file(tmp_path):
    memory = EphemeralMemoryStore()
    assert "this run only" in memory.save("Brix member detail")
    assert memory.search("member") == ["Brix member detail"]
    assert memory.path is None
    assert not list(tmp_path.iterdir())


def test_real_account_workspace_and_artifacts_are_run_only():
    storage = EphemeralRunStorage()
    root = storage.root
    (storage.workspace / "customer.txt").write_text(
        "private customer data", encoding="utf-8"
    )
    (storage.artifacts / "draft.txt").write_text("draft", encoding="utf-8")
    assert root.is_dir()
    storage.cleanup()
    assert not root.exists()


def test_connector_confirmation_is_complete_but_redacted(tmp_path):
    client = FakeOptix()
    path = _bindings_path(tmp_path, optix=_optix_binding(client))
    specs, _, _ = runtime.enable(
        ["optix"], mode="live", bindings_path=path,
        clients={"optix": client}, secrets=_secrets(),
        ledger=OperationLedger(tmp_path / "ledger.jsonl"),
    )
    detail = json.loads(
        specs["optix_commit_booking"]["confirmation"](
            {
                "booking_session_id": "s1", "member_id": "m1",
                "owner_user_id": "u1", "room_id": "r1",
                "start": START, "end": END, "token": "should-not-appear",
            }
        )
    )
    assert detail["provider"] == "optix"
    assert detail["account"] == "sandbox"
    assert detail["important"]["room_id"] == "r1"
    assert detail["important"]["start"] == START
    assert detail["invites"] is True
    assert "should-not-appear" not in json.dumps(detail)
    runtime.shutdown()


def test_shutdown_is_idempotent_and_a_new_run_gets_a_new_client(tmp_path):
    first = FakeHubSpot()
    path = _bindings_path(tmp_path, hubspot=_hubspot_binding(first))
    runtime.enable(
        ["hubspot"], mode="read_only", bindings_path=path,
        clients={"hubspot": first}, secrets=_secrets(),
    )
    second = FakeHubSpot()
    runtime.enable(
        ["hubspot"], mode="read_only", bindings_path=path,
        clients={"hubspot": second}, secrets=_secrets(),
    )
    assert first.closed
    assert not second.closed
    runtime.shutdown()
    runtime.shutdown()
    assert second.closed


def test_connector_code_and_frozen_bench_are_import_isolated():
    root = Path(__file__).resolve().parents[1]
    for path in (root / "connectors").glob("*.py"):
        assert "from bench" not in path.read_text(encoding="utf-8")
        assert "import bench" not in path.read_text(encoding="utf-8")
    for path in (root / "bench").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "from connectors" not in text
        assert "import connectors" not in text


def test_cli_never_accepts_a_secret_or_token_on_argv():
    from connectors.cli import build_parser

    parser = build_parser()
    help_text = parser.format_help()
    assert "--token" not in help_text
    assert "--client-secret" not in help_text
    assert "--endpoint" not in help_text
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["configure-optix", "--account", "sandbox", "--token", "secret"]
        )
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "discover", "--provider", "optix", "--account", "sandbox",
                "--endpoint", "https://attacker.invalid/graphql",
            ]
        )


def test_shared_runner_accepts_only_connector_names_and_modes():
    from agents._shared import run_agent

    options, task = run_agent.parse_flags(
        [
            "--connector", "hubspot,optix", "--connector-mode", "read_only",
            "inspect", "rooms",
        ]
    )
    assert options["connector"] == "hubspot,optix"
    assert options["connector_mode"] == "read_only"
    assert task == "inspect rooms"
    run_agent.validate_config(
        {"name": "local", "model": "llama3.1:8b", "connectors": {
            "enable": ["hubspot"], "mode": "read_only",
        }}
    )
    with pytest.raises(SystemExit):
        run_agent.parse_flags(["--connector-mode", "unsafe", "task"])


def test_web_runner_selects_ephemeral_memory_after_connectors_are_known():
    root = Path(__file__).resolve().parents[1]
    source = (root / "webui" / "runner.py").read_text(encoding="utf-8")
    assert source.index("external_specs = {}") < source.index(
        "if external_specs\n        else MemoryStore"
    )


def test_real_account_model_router_disables_its_persistent_usage_log(tmp_path):
    from agents._shared import run_agent
    from webui import runner as web_runner

    config_data = {
        "name": "local", "model": "llama3.1:8b",
        "router": {"base": "llama3.1:8b"},
    }
    options = {
        "tiers": True, "small": None, "deep": None,
    }
    _, router = run_agent.build_llm(
        config_data, options, str(tmp_path), persist_log=False
    )
    assert router.log_path is None

    args = SimpleNamespace(tiers=True, small=None, deep=None)
    _, router = web_runner.build_llm(
        config_data, args, str(tmp_path), stream_hook=None, persist_log=False
    )
    assert router.log_path is None
    assert not list(tmp_path.iterdir())


def test_web_boundary_rejects_unknown_and_unbound_connectors():
    from webui import server

    with pytest.raises(server.RequestError, match="nonempty strings"):
        server.require_connector_names([{}])
    with pytest.raises(server.RequestError, match="unknown connectors"):
        server.require_connector_names(["unknown"])
    with pytest.raises(server.RequestError, match="reviewed bindings"):
        server.require_connector_names(["hubspot"])
