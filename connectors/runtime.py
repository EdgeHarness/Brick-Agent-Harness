"""Normalize HubSpot MCP and Optix GraphQL into one fixed Brick tool surface."""
import atexit
import copy
from datetime import date, datetime, time as datetime_time, timezone
import hashlib
import inspect
import json
import os
import re
import sys
import time

from harness import faults
from harness.privacy import redact

from . import config
from .credentials import KeyringSecretStore, account_fingerprint
from .errors import (
    AmbiguousWrite,
    CatalogDrift,
    ConnectorConfigError,
    ConnectorUnavailable,
    ProviderEnvironmentFault,
)
from .hubspot import HubSpotMCPClient
from .ledger import OperationLedger, client_key
from .optix import OptixGraphQLClient


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CLIENTS = []
_OUTPUT_NAME = re.compile(r"^[a-z][a-z0-9_]{0,47}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GRAPHQL_NAME = re.compile(r"^[_A-Za-z][_0-9A-Za-z]*$")
MAX_PROJECTED_RESULT_BYTES = 16 * 1024
_COMMON_BINDING_KEYS = frozenset(
    (
        "operation", "literal_arguments", "argument_map", "context_map",
        "argument_transforms", "result_map", "item_map", "error_origin",
        "verification",
    )
)
_WORKFLOW_KEYS = frozenset(("workflow_kind", "calls"))
_HUBSPOT_ALLOWED_OPERATIONS = frozenset(
    ("get_user_details", "search_crm_objects", "get_crm_objects", "search_owners")
)
_CONTACT_FIELDS = (
    "contact_id", "first_name", "last_name", "email", "lifecycle_stage",
    "lead_status", "owner_id",
)


def _canonical_hash(value):
    return hashlib.sha256(config.canonical_json(value).encode("utf-8")).hexdigest()


def _document_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _catalog_snapshot(provider, catalog):
    if provider == "hubspot":
        if not isinstance(catalog, dict):
            raise ProviderEnvironmentFault("HubSpot catalog is not an object")
        rows = []
        for name, item in sorted(catalog.items()):
            if not isinstance(name, str) or not isinstance(item, dict):
                raise ProviderEnvironmentFault("HubSpot catalog contains an invalid tool")
            schema = item.get("input_schema")
            if not isinstance(schema, dict):
                raise ProviderEnvironmentFault("HubSpot tool schema is missing")
            description = item.get("description")
            if description is None:
                description = ""
            if not isinstance(description, str):
                raise ProviderEnvironmentFault(
                    "HubSpot tool description is not text"
                )
            rows.append({
                "name": name,
                "description_sha256": hashlib.sha256(
                    description.encode("utf-8")
                ).hexdigest(),
                "input_schema_sha256": _canonical_hash(schema),
            })
        return {"provider": provider, "tools": rows}
    if not isinstance(catalog, dict):
        raise ProviderEnvironmentFault("Optix schema catalog is not an object")
    return {"provider": provider, "schema": catalog}


def _validate_projection(mapping, label):
    if not isinstance(mapping, dict) or not mapping:
        raise ConnectorConfigError(f"{label} result_map must be a nonempty object")
    for name, pointer in mapping.items():
        if not isinstance(name, str) or not _OUTPUT_NAME.fullmatch(name):
            raise ConnectorConfigError(f"{label} has an invalid output name")
        if not isinstance(pointer, str) or not pointer.startswith("/"):
            raise ConnectorConfigError(f"{label} result pointers must start with '/'")


def _validate_argument_map(mapping, declaration, label):
    if not isinstance(mapping, dict):
        raise ConnectorConfigError(f"{label} argument_map must be an object")
    if not set(mapping) <= set(declaration["params"]):
        raise ConnectorConfigError(f"{label} maps an undeclared Brick argument")
    required = {
        name for name, value in declaration["params"].items() if value["required"]
    }
    if not required <= set(mapping):
        raise ConnectorConfigError(f"{label} omits a required argument binding")
    if any(
        not isinstance(value, str) or not value.startswith("/")
        for value in mapping.values()
    ):
        raise ConnectorConfigError(f"{label} provider arguments must use JSON pointers")
    if len(set(mapping.values())) != len(mapping):
        raise ConnectorConfigError(f"{label} provider argument names must be unique")


def _validate_operation_binding(
    provider, binding, declaration, label, verification=False, allowed_args=None,
    read_only=None, allowed_context=None,
):
    provider_keys = (
        frozenset(("input_schema_sha256",))
        if provider == "hubspot"
        else frozenset(("document", "document_sha256"))
    )
    expected = _COMMON_BINDING_KEYS | provider_keys
    if verification:
        expected = expected - {"verification"}
    if not isinstance(binding, dict) or set(binding) != expected:
        raise ConnectorConfigError(
            f"{label} must contain exactly {', '.join(sorted(expected))}"
        )
    if not isinstance(binding["operation"], str) or not binding["operation"]:
        raise ConnectorConfigError(f"{label} operation must be nonempty")
    if binding["error_origin"] not in ("model", "environment"):
        raise ConnectorConfigError(f"{label} error_origin is invalid")
    config._validate_operation_shape(
        provider,
        binding,
        label,
        not verification,
        verification if read_only is None else read_only,
    )
    if allowed_args is None:
        allowed_args = set(declaration["params"])
    argument_declaration = {
        "params": {
            name: {
                "type": declaration["params"].get(name, {}).get(
                    "type", "provider result field"
                ),
                "required": (
                    declaration["params"].get(name, {}).get("required", False)
                    if not verification
                    else False
                ),
            }
            for name in allowed_args
        }
    }
    _validate_argument_map(binding["argument_map"], argument_declaration, label)
    allowed_context = set(allowed_context or ())
    if not set(binding["context_map"]) <= allowed_context:
        raise ConnectorConfigError(f"{label} maps an unavailable derived context value")
    transforms = binding["argument_transforms"]
    if not isinstance(transforms, dict) or not set(transforms) <= set(
        binding["argument_map"]
    ):
        raise ConnectorConfigError(
            f"{label} argument_transforms must name mapped Brick arguments"
        )
    if any(value not in config._ARGUMENT_TRANSFORMS for value in transforms.values()):
        raise ConnectorConfigError(f"{label} has an unsupported argument transform")
    _validate_projection(binding["result_map"], label)
    if provider == "hubspot":
        if not isinstance(binding["input_schema_sha256"], str) or not _SHA256.fullmatch(
            binding["input_schema_sha256"]
        ):
            raise ConnectorConfigError(f"{label} has invalid input schema digest")
    else:
        if not isinstance(binding["document"], str) or not binding["document"].strip():
            raise ConnectorConfigError(f"{label} GraphQL document is empty")
        if _document_hash(binding["document"]) != binding["document_sha256"]:
            raise ConnectorConfigError(f"{label} GraphQL document digest is wrong")
        document = binding["document"]
        if "__schema" in document or "__type" in document:
            raise ConnectorConfigError(
                f"{label} cannot bind GraphQL introspection as a model tool"
            )
        kind = re.match(r"^\s*(query|mutation)\b", document)
        if kind is None:
            raise ConnectorConfigError(
                f"{label} GraphQL document must declare query or mutation"
            )
        operation_is_read = (
            verification
            if read_only is None
            else read_only
        )
        if operation_is_read and (
            kind.group(1) != "query" or re.search(r"\bmutation\b", document)
        ):
            raise ConnectorConfigError(
                f"{label} read-only GraphQL document cannot contain a mutation"
            )
        variables = set(re.findall(r"\$([_A-Za-z][_0-9A-Za-z]*)", document))
        roots = {
            destination.split("/")[1]
            for destination in binding["argument_map"].values()
        }
        if not roots <= variables:
            raise ConnectorConfigError(
                f"{label} maps an argument absent from its GraphQL document"
            )
    if not verification:
        verify = binding["verification"]
        if verify is not None:
            _validate_operation_binding(
                provider,
                verify,
                declaration,
                label + ".verification",
                verification=True,
                allowed_args=set(declaration["params"]) | set(binding["result_map"]),
                read_only=True,
                allowed_context=allowed_context,
            )


def _pointer(value, pointer):
    current = value
    for raw in pointer.split("/")[1:]:
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


def _project(value, mapping, item_map=None):
    projected = {name: _pointer(value, pointer) for name, pointer in mapping.items()}
    source_truncated = False
    if item_map is not None:
        source = item_map["source"]
        rows = projected.get(source)
        if rows is None:
            rows = []
        if not isinstance(rows, list):
            raise ProviderEnvironmentFault(
                f"provider result field {source!r} is not a list"
            )
        source_truncated = len(rows) > 50
        projected[source] = [
            {
                name: _pointer(row, pointer)
                for name, pointer in item_map["fields"].items()
            }
            for row in rows[:50]
            if isinstance(row, dict)
        ]
    if source_truncated:
        projected["_source_truncated"] = True
    return redact(projected)


def _iso8601_to_unix(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise faults.ModelInputFault(
            "connector date-times must be ISO 8601 values with an offset"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise faults.ModelInputFault(
            "connector date-times must include an explicit UTC offset"
        )
    return int(parsed.timestamp())


def _iso_date_to_utc_millis_end(value):
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise faults.ModelInputFault(
            "connector dates must use YYYY-MM-DD"
        ) from exc
    end = datetime.combine(parsed, datetime_time.max, tzinfo=timezone.utc)
    # The binding selects this transform only when authenticated discovery shows
    # an epoch-millisecond end-of-date filter.
    return int(end.timestamp() * 1000)


def _transform_argument(name, value):
    if name is None:
        return value
    if name == "iso8601_to_unix":
        return _iso8601_to_unix(value)
    if name == "iso_date_to_utc_millis_end":
        return _iso_date_to_utc_millis_end(value)
    if name == "singleton_list":
        return [value]
    raise ConnectorConfigError(f"unsupported connector argument transform {name!r}")


def _set_pointer(root, pointer, value):
    parts = pointer.split("/")[1:]
    current = root
    for index, part in enumerate(parts):
        last = index + 1 == len(parts)
        next_is_index = not last and parts[index + 1].isdigit()
        if isinstance(current, dict):
            if last:
                current[part] = value
                return
            expected = [] if next_is_index else {}
            current = current.setdefault(part, expected)
        elif isinstance(current, list) and part.isdigit():
            position = int(part)
            if position > 20:
                raise ConnectorConfigError(
                    "connector argument destination index is unreasonably large"
                )
            while len(current) <= position:
                current.append(None)
            if last:
                current[position] = value
                return
            expected = [] if next_is_index else {}
            if current[position] is None:
                current[position] = expected
            current = current[position]
        else:
            raise ConnectorConfigError("connector argument destinations conflict")


def _mapped_args(
    provider, arguments, mapping, transforms, *, literals=None, context=None,
    context_map=None,
):
    del provider
    output = copy.deepcopy(literals or {})
    for brick_name, provider_name in mapping.items():
        if brick_name not in arguments or arguments[brick_name] is None:
            continue
        value = _transform_argument(transforms.get(brick_name), arguments[brick_name])
        _set_pointer(output, provider_name, value)
    context = context or {}
    for context_name, provider_name in (context_map or {}).items():
        value = context.get(context_name)
        if value in (None, ""):
            raise ProviderEnvironmentFault(
                f"connector context {context_name!r} is unavailable"
            )
        _set_pointer(output, provider_name, value)
    return output


def _validate_args(declaration, arguments):
    if not isinstance(arguments, dict):
        raise faults.ModelInputFault("connector arguments must be an object")
    unknown = set(arguments) - set(declaration["params"])
    if unknown:
        raise faults.ModelInputFault(
            "unknown connector arguments: " + ", ".join(sorted(unknown))
        )
    for name, field in declaration["params"].items():
        value = arguments.get(name)
        if field["required"] and value in (None, ""):
            raise faults.ModelInputFault(f"missing required connector argument {name!r}")
        if value is None:
            continue
        expected = field["type"].lower()
        if expected.startswith("integer"):
            if type(value) is not int:
                raise faults.ModelInputFault(f"connector argument {name!r} must be an integer")
            if "from 1 to 20" in expected and not 1 <= value <= 20:
                raise faults.ModelInputFault(
                    f"connector argument {name!r} must be between 1 and 20"
                )
        elif not isinstance(value, str):
            raise faults.ModelInputFault(f"connector argument {name!r} must be a string")
        elif expected == "iso 8601 date":
            try:
                parsed_date = date.fromisoformat(value)
            except ValueError as exc:
                raise faults.ModelInputFault(
                    f"connector argument {name!r} must be an ISO 8601 date"
                ) from exc
            if parsed_date.isoformat() != value:
                raise faults.ModelInputFault(
                    f"connector argument {name!r} must use YYYY-MM-DD"
                )
        elif expected.startswith("iso 8601 date-time"):
            _iso8601_to_unix(value)
    if "start" in arguments and "end" in arguments:
        if _iso8601_to_unix(arguments["end"]) <= _iso8601_to_unix(arguments["start"]):
            raise faults.ModelInputFault("connector end time must be after start time")


def _invoke(
    client, provider, operation_binding, arguments, *, mutating, safe_retry,
    context=None,
):
    mapped = _mapped_args(
        provider,
        arguments,
        operation_binding["argument_map"],
        operation_binding["argument_transforms"],
        literals=operation_binding["literal_arguments"],
        context=context,
        context_map=operation_binding["context_map"],
    )
    kwargs = {
        "error_origin": operation_binding["error_origin"],
    }
    if provider == "optix":
        kwargs.update(
            {
                "document": operation_binding["document"],
                "mutating": mutating,
                # Runtime owns the single safe read retry for both transports.
                # Passing it through would make Optix retry twice at each layer.
                "safe_retry": False,
            }
        )
    return client.call(operation_binding["operation"], mapped, **kwargs)


def _confirmation(provider, account, declaration):
    priority = (
        "contact_id", "member_id", "owner_user_id", "room_id",
        "booking_session_id", "start", "end",
        "due_before", "owner_id", "query",
    )

    def render(arguments):
        arguments = dict(arguments or {})
        important = {key: arguments[key] for key in priority if key in arguments}
        remainder = {
            key: value for key, value in arguments.items() if key not in important
        }
        return json.dumps(
            {
                "provider": provider,
                "account": account,
                "tool": declaration["name"],
                "effect": declaration["effect"],
                "transmits": declaration["transmits"],
                "invites": declaration["invites"],
                "important": redact(important),
                "payload_preview": redact(remainder),
            },
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )

    return render


def _operation_object_id(result, arguments):
    for key in (
        "booking_id", "booking_session_id", "contact_id", "member_id",
        "room_id", "draft_id", "id",
    ):
        if key in result:
            return result[key]
        if key in arguments:
            return arguments[key]
    return None


def _short_text(value, limit=512):
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _contact_record(value):
    value = value if isinstance(value, dict) else {}
    return {
        field: _short_text(value.get(field), 512)
        for field in _CONTACT_FIELDS
    }


def _rows(projected, name):
    value = projected.get(name)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ProviderEnvironmentFault(f"projected provider field {name!r} is not a list")
    return [item for item in value if isinstance(item, dict)]


def _total_exceeds(value, limit):
    try:
        return int(value) > limit
    except (TypeError, ValueError):
        return False


def _activity_sort_key(item):
    value = item.get("timestamp")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return float("-inf")


def _normalize_result(declaration, projected, arguments, context=None):
    """Enforce Brick's stable public result shapes after provider projection."""
    name = declaration["name"]
    context = context or {}
    if name == "hs_find_contact":
        raw = _rows(projected, "matches")
        matches = [_contact_record(item) for item in raw[:5]]
        return {
            "matches": matches,
            "truncated": bool(
                projected.get("_source_truncated")
                or len(raw) > 5
                or _total_exceeds(projected.get("total"), 5)
            ),
        }
    if name == "hs_get_contact":
        contact = _contact_record(projected)
        return {
            "contact": contact,
            "missing_fields": [
                field for field, value in contact.items() if value in (None, "")
            ],
        }
    if name == "hs_recent_activity":
        raw = _rows(projected, "activities")
        activities = []
        for item in raw:
            activities.append(
                {
                    "activity_id": _short_text(item.get("activity_id"), 256),
                    "type": _short_text(item.get("type"), 64),
                    "timestamp": _short_text(item.get("timestamp"), 128),
                    "status": _short_text(item.get("status"), 128),
                    "subject": _short_text(item.get("subject"), 256),
                    "summary": _short_text(item.get("summary"), 768),
                }
            )
        activities.sort(key=_activity_sort_key, reverse=True)
        return {
            "contact_id": arguments["contact_id"],
            "activities": activities[:10],
            "truncated": bool(projected.get("_source_truncated") or len(activities) > 10),
        }
    if name == "hs_my_open_followups":
        raw = _rows(projected, "tasks")
        tasks = [
            {
                "task_id": _short_text(item.get("task_id"), 256),
                "contact_id": _short_text(item.get("contact_id"), 256),
                "due_at": _short_text(item.get("due_at"), 128),
                "status": _short_text(item.get("status"), 128),
                "subject": _short_text(item.get("subject"), 256),
                "summary": _short_text(item.get("summary"), 768),
            }
            for item in raw[:10]
        ]
        owner = context.get("owner") or {}
        return {
            "owner": {
                "owner_id": _short_text(owner.get("owner_id"), 256),
                "name": _short_text(owner.get("name"), 256),
                "email": _short_text(owner.get("email"), 320),
            },
            "due_before": arguments["due_before"],
            "tasks": tasks,
            "truncated": bool(
                projected.get("_source_truncated")
                or len(raw) > 10
                or _total_exceeds(projected.get("total"), 10)
            ),
        }
    return projected


def _bounded_observation(value):
    value = redact(value)
    encoded = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), default=str
    ).encode("utf-8")
    if len(encoded) > MAX_PROJECTED_RESULT_BYTES:
        raise ProviderEnvironmentFault(
            "provider result exceeds the reviewed connector observation limit"
        )
    return value


def _executor(
    provider,
    account,
    declaration,
    operation_binding,
    client,
    ledger,
    expected_catalog_sha256,
    context=None,
):
    mutating = declaration["effect"] != "read"
    safe_retry = declaration["retry"] == "safe" and not mutating

    def reconcile_ambiguous(arguments, key):
        verification = operation_binding["verification"]
        if verification is None:
            return None
        needed = set(verification["argument_map"])
        if not needed <= set(arguments) or any(
            arguments.get(name) in (None, "") for name in needed
        ):
            # A verifier that needs a provider-returned ID cannot run when the
            # mutation response itself was lost.  Keep the ledger unknown.
            return None
        try:
            verify_raw = _invoke(
                client,
                provider,
                verification,
                arguments,
                mutating=False,
                safe_retry=True,
                context=context,
            )
            verified = _project(
                verify_raw, verification["result_map"], verification["item_map"]
            )
        except Exception:
            return None
        if not verified or any(
            value in (None, "", False, [], {}) for value in verified.values()
        ):
            return None
        ledger.record(
            provider=provider,
            operation=operation_binding["operation"],
            key=key,
            status="verified",
            object_id=_operation_object_id(verified, arguments),
        )
        return {
            "result": None,
            "verification": verified,
            "reconciled_after_ambiguous_write": True,
        }

    def run(attempt, arguments):
        _validate_args(declaration, arguments)
        key = client_key(
            f"{provider}:{account}", declaration["name"], arguments
        )
        if mutating:
            live_snapshot = _catalog_snapshot(provider, client.catalog())
            if _canonical_hash(live_snapshot) != expected_catalog_sha256:
                raise CatalogDrift(
                    f"{provider} catalog changed after this run connected; write refused"
                )
            ledger.reserve(
                provider=provider,
                operation=operation_binding["operation"],
                key=key,
                object_id=_operation_object_id({}, arguments),
            )
        attempts = 2 if safe_retry else 1
        write_completed = False
        try:
            raw = None
            for index in range(attempts):
                try:
                    raw = _invoke(
                        client,
                        provider,
                        operation_binding,
                        arguments,
                        mutating=mutating,
                        safe_retry=safe_retry,
                        context=context,
                    )
                    break
                except ProviderEnvironmentFault:
                    if index + 1 == attempts:
                        raise
                    time.sleep(0.1)
            result = _project(
                raw, operation_binding["result_map"], operation_binding["item_map"]
            )
            result = _bounded_observation(
                _normalize_result(declaration, result, arguments, context)
            )
            if mutating:
                write_completed = True
                ledger.record(
                    provider=provider,
                    operation=operation_binding["operation"],
                    key=key,
                    status="done",
                    object_id=_operation_object_id(result, arguments),
                )
                verification = operation_binding["verification"]
                if verification is not None:
                    verify_raw = _invoke(
                        client,
                        provider,
                        verification,
                        {**arguments, **result},
                        mutating=False,
                        safe_retry=True,
                        context=context,
                    )
                    verified = _project(
                        verify_raw, verification["result_map"], verification["item_map"]
                    )
                    ledger.record(
                        provider=provider,
                        operation=operation_binding["operation"],
                        key=key,
                        status="verified",
                        object_id=_operation_object_id(result, arguments),
                    )
                    return {"result": result, "verification": verified}
            return result
        except faults.ModelInputFault:
            if mutating:
                ledger.record(
                    provider=provider,
                    operation=operation_binding["operation"],
                    key=key,
                    # A verification error occurs after the write already
                    # succeeded.  It must never reopen the idempotency gate.
                    status="unknown" if write_completed else "rejected",
                    object_id=_operation_object_id({}, arguments),
                )
            raise
        except Exception as error:
            if mutating:
                if isinstance(error, AmbiguousWrite):
                    reconciled = reconcile_ambiguous(arguments, key)
                    if reconciled is not None:
                        return reconciled
                ledger.record(
                    provider=provider,
                    operation=operation_binding["operation"],
                    key=key,
                    status="unknown",
                    object_id=_operation_object_id({}, arguments),
                )
            raise

    return run


def _workflow_executor(provider, declaration, workflow, client, context=None):
    """Run the one reviewed fixed multi-call workflow exposed in this release."""
    if provider != "hubspot" or workflow["workflow_kind"] != \
            "hubspot_recent_activity_v1":
        raise ConnectorConfigError("unsupported connector workflow")

    def run(attempt, arguments):
        del attempt
        _validate_args(declaration, arguments)
        merged = []
        truncated = False
        for step in workflow["calls"]:
            operation = step["binding"]
            raw = None
            for index in range(2):
                try:
                    raw = _invoke(
                        client,
                        provider,
                        operation,
                        arguments,
                        mutating=False,
                        safe_retry=True,
                        context=context,
                    )
                    break
                except ProviderEnvironmentFault:
                    if index == 1:
                        raise
                    time.sleep(0.1)
            projected = _project(
                raw, operation["result_map"], operation["item_map"]
            )
            rows = _rows(projected, "activities")
            for row in rows:
                row = dict(row)
                row["type"] = step["label"]
                merged.append(row)
            truncated = truncated or bool(projected.get("_source_truncated"))
        projected = {"activities": merged, "_source_truncated": truncated}
        return _bounded_observation(
            _normalize_result(declaration, projected, arguments, context)
        )

    return run


def _validate_account(provider, binding, secrets):
    account = binding["account_alias"]
    identity = secrets.get(provider, account, "account_identity")
    if identity is None:
        raise ConnectorUnavailable(
            f"{provider} account identity is not present in the OS keyring"
        )
    if account_fingerprint(identity) != binding["account_fingerprint_sha256"]:
        raise ConnectorUnavailable(f"{provider} account does not match the reviewed binding")
    return account


def _validate_live_identity(provider, binding, client):
    declaration = {"params": {}}
    identity = binding["identity"]
    _validate_operation_binding(
        provider,
        identity,
        declaration,
        f"{provider}.identity",
        verification=True,
        allowed_args=set(),
        read_only=True,
    )
    if identity["error_origin"] != "environment":
        raise ConnectorConfigError(
            f"{provider} identity errors must be environment-origin"
        )
    allowed_identity_fields = {
        "account_identity", "portal_id", "account_name", "user_id",
        "user_name", "user_email", "owner_id", "accessible_objects",
    }
    if "account_identity" not in identity["result_map"] or not set(
        identity["result_map"]
    ) <= allowed_identity_fields:
        raise ConnectorConfigError(
            f"{provider} identity binding has an unsupported result surface"
        )
    raw = _invoke(
        client,
        provider,
        identity,
        {},
        mutating=False,
        safe_retry=True,
    )
    projected = _project(raw, identity["result_map"], identity["item_map"])
    live_identity = projected["account_identity"]
    if live_identity in (None, "") or account_fingerprint(str(live_identity)) != binding[
        "account_fingerprint_sha256"
    ]:
        raise ConnectorUnavailable(
            f"{provider} authenticated account does not match the reviewed binding"
        )
    return projected


def _resolve_hubspot_owner(binding, client, live_identity):
    owner_id = live_identity.get("owner_id")
    if owner_id not in (None, ""):
        return {
            "owner_id": str(owner_id),
            "name": live_identity.get("user_name"),
            "email": live_identity.get("user_email"),
        }
    email = live_identity.get("user_email")
    lookup = binding["support"].get("owner_lookup")
    if email in (None, "") or lookup is None:
        raise ConnectorUnavailable(
            "HubSpot could not derive one owner for the authenticated user"
        )
    declaration = {"params": {}}
    _validate_operation_binding(
        "hubspot",
        lookup,
        declaration,
        "hubspot.support.owner_lookup",
        verification=True,
        allowed_args=set(),
        allowed_context={"user_email"},
        read_only=True,
    )
    raw = _invoke(
        client,
        "hubspot",
        lookup,
        {},
        mutating=False,
        safe_retry=True,
        context={"user_email": email},
    )
    projected = _project(raw, lookup["result_map"], lookup["item_map"])
    owners = _rows(projected, "owners")
    matches = [
        owner for owner in owners
        if str(owner.get("email") or "").casefold() == str(email).casefold()
    ]
    if len(matches) != 1 or matches[0].get("owner_id") in (None, ""):
        raise ConnectorUnavailable(
            "HubSpot owner lookup did not return exactly one authenticated-user match"
        )
    return {
        "owner_id": str(matches[0]["owner_id"]),
        "name": matches[0].get("name"),
        "email": matches[0].get("email"),
    }


def _make_client(provider, binding, secrets):
    account = binding["account_alias"]
    if provider == "hubspot":
        return HubSpotMCPClient(
            account_alias=account,
            secrets=secrets,
            endpoint=binding["endpoint"],
            oauth_scope=binding["oauth_scope"],
            interactive_auth=False,
        )
    token = secrets.get("optix", account, "api_token")
    if token is None:
        raise ConnectorUnavailable("Optix API token is not present in the OS keyring")
    return OptixGraphQLClient(endpoint=binding["endpoint"], token=token)


def _provider_tools(declarations, provider):
    return {
        tool["binding_key"]: tool
        for tool in declarations["providers"][provider]["tools"]
    }


def _validate_hubspot_catalog_binding(catalog, operation_binding, label):
    operation = operation_binding["operation"]
    if operation not in _HUBSPOT_ALLOWED_OPERATIONS:
        raise ConnectorConfigError(
            f"{label} binds a HubSpot operation outside the read-only allow list"
        )
    live = catalog.get(operation)
    if live is None:
        raise CatalogDrift(f"HubSpot operation {operation!r} disappeared")
    if _canonical_hash(live["input_schema"]) != operation_binding[
        "input_schema_sha256"
    ]:
        raise CatalogDrift(f"HubSpot operation {operation!r} schema drifted")
    schema = live["input_schema"]
    properties = schema.get("properties")
    required = schema.get("required") or []
    if (
        schema.get("type") != "object"
        or not isinstance(properties, dict)
        or not isinstance(required, list)
        or any(not isinstance(name, str) for name in required)
    ):
        raise CatalogDrift(
            f"HubSpot operation {operation!r} has an unsupported input schema"
        )
    roots = set(operation_binding["literal_arguments"])
    for mapping in (
        operation_binding["argument_map"], operation_binding["context_map"]
    ):
        roots.update(pointer.split("/")[1] for pointer in mapping.values())
    if not roots <= set(properties) or not set(required) <= roots:
        raise ConnectorConfigError(
            f"{label} argument binding does not cover the reviewed HubSpot schema"
        )


def _require_item_contract(binding, source, fields, label):
    item_map = binding["item_map"]
    if not isinstance(item_map, dict) or item_map.get("source") != source:
        raise ConnectorConfigError(f"{label} must project the {source} list")
    if set(item_map.get("fields") or {}) != set(fields):
        raise ConnectorConfigError(f"{label} has the wrong normalized item fields")


def _validate_hubspot_tool_binding(catalog, binding, declaration, label):
    name = declaration["name"]
    if isinstance(binding, dict) and set(binding) == _WORKFLOW_KEYS:
        if name != "hs_recent_activity" or binding["workflow_kind"] != \
                "hubspot_recent_activity_v1":
            raise ConnectorConfigError(f"{label} has an unsupported workflow")
        for step in binding["calls"]:
            operation = step["binding"]
            _validate_operation_binding(
                "hubspot", operation, declaration, f"{label}.{step['label']}",
                verification=True, allowed_args={"contact_id"}, read_only=True,
            )
            _validate_hubspot_catalog_binding(
                catalog, operation, f"{label}.{step['label']}"
            )
            _require_item_contract(
                operation,
                "activities",
                ("activity_id", "timestamp", "status", "subject", "summary"),
                f"{label}.{step['label']}",
            )
        return

    allowed_context = {"owner_id"} if name == "hs_my_open_followups" else set()
    _validate_operation_binding(
        "hubspot",
        binding,
        declaration,
        label,
        read_only=True,
        allowed_context=allowed_context,
    )
    _validate_hubspot_catalog_binding(catalog, binding, label)
    if name == "hs_find_contact":
        if set(binding["result_map"]) != {"matches", "total"}:
            raise ConnectorConfigError(f"{label} has the wrong result projection")
        _require_item_contract(binding, "matches", _CONTACT_FIELDS, label)
    elif name == "hs_get_contact":
        if binding["item_map"] is not None or set(binding["result_map"]) != set(
            _CONTACT_FIELDS
        ):
            raise ConnectorConfigError(f"{label} has the wrong contact projection")
    elif name == "hs_recent_activity":
        if set(binding["result_map"]) != {"activities"}:
            raise ConnectorConfigError(f"{label} has the wrong activity projection")
        _require_item_contract(
            binding,
            "activities",
            ("activity_id", "type", "timestamp", "status", "subject", "summary"),
            label,
        )
    elif name == "hs_my_open_followups":
        if set(binding["context_map"]) != {"owner_id"}:
            raise ConnectorConfigError(f"{label} must derive owner_id from authentication")
        if set(binding["result_map"]) != {"tasks", "total"}:
            raise ConnectorConfigError(f"{label} has the wrong follow-up projection")
        _require_item_contract(
            binding,
            "tasks",
            ("task_id", "contact_id", "due_at", "status", "subject", "summary"),
            label,
        )


def validate_reviewed_bindings(declarations_path=None, bindings_path=None):
    """Validate every byte of the static provider-operation contract offline."""
    declarations = config.load_declarations(declarations_path)
    bindings = config.load_bindings(
        config.runtime_bindings_path(bindings_path), declarations
    )
    for provider, binding in bindings["providers"].items():
        if binding["status"] == "unbound":
            continue
        identity_declaration = {"params": {}}
        _validate_operation_binding(
            provider,
            binding["identity"],
            identity_declaration,
            f"{provider}.identity",
            verification=True,
            allowed_args=set(),
            read_only=True,
        )
        if binding["identity"]["error_origin"] != "environment":
            raise ConnectorConfigError(
                f"{provider} identity errors must be environment-origin"
            )
        if "account_identity" not in binding["identity"]["result_map"]:
            raise ConnectorConfigError(
                f"{provider} identity binding must project account_identity"
            )
        if provider == "hubspot" and binding["identity"]["operation"] != \
                "get_user_details":
            raise ConnectorConfigError("HubSpot identity must use get_user_details")
        if provider == "hubspot" and "owner_lookup" in binding["support"]:
            owner_lookup = binding["support"]["owner_lookup"]
            if owner_lookup["operation"] != "search_owners":
                raise ConnectorConfigError("HubSpot owner lookup must use search_owners")
            _validate_operation_binding(
                provider,
                owner_lookup,
                {"params": {}},
                "hubspot.support.owner_lookup",
                verification=True,
                allowed_args=set(),
                allowed_context={"user_email"},
                read_only=True,
            )
            _require_item_contract(
                owner_lookup, "owners", ("owner_id", "name", "email"),
                "hubspot.support.owner_lookup",
            )
        declarations_by_key = _provider_tools(declarations, provider)
        for binding_key, operation in binding["tools"].items():
            declaration = declarations_by_key[binding_key]
            label = f"{provider}.{binding_key}"
            if isinstance(operation, dict) and set(operation) == _WORKFLOW_KEYS:
                for step in operation["calls"]:
                    if provider == "hubspot" and step["binding"]["operation"] not in \
                            _HUBSPOT_ALLOWED_OPERATIONS:
                        raise ConnectorConfigError(
                            f"{label} binds a HubSpot operation outside the read-only allow list"
                        )
                    _validate_operation_binding(
                        provider,
                        step["binding"],
                        declaration,
                        f"{label}.{step['label']}",
                        verification=True,
                        allowed_args={"contact_id"},
                        read_only=True,
                    )
            else:
                if provider == "hubspot" and operation["operation"] not in \
                        _HUBSPOT_ALLOWED_OPERATIONS:
                    raise ConnectorConfigError(
                        f"{label} binds a HubSpot operation outside the read-only allow list"
                    )
                _validate_operation_binding(
                    provider,
                    operation,
                    declaration,
                    label,
                    read_only=declaration["effect"] == "read",
                    allowed_context=(
                        {"owner_id"}
                        if declaration["name"] == "hs_my_open_followups"
                        else set()
                    ),
                )
    return declarations, bindings


def discovery_record(provider, account_alias, account_identity, catalog, endpoint):
    """Create a canonical, secret-free input for a human binding review."""
    if provider not in ("hubspot", "optix"):
        raise ConnectorConfigError(f"unknown connector {provider!r}")
    snapshot = _catalog_snapshot(provider, catalog)
    record = {
        "schema_version": "brick.connector-discovery/1",
        "provider": provider,
        "endpoint": endpoint,
        "account_alias": account_alias,
        "account_fingerprint_sha256": account_fingerprint(account_identity),
        "catalog_sha256": _canonical_hash(snapshot),
        "catalog": snapshot,
    }
    if provider == "hubspot":
        record["reviewed_operation_candidates"] = [
            {
                "operation": name,
                "description": item.get("description", ""),
                "input_schema": item["input_schema"],
                "input_schema_sha256": _canonical_hash(item["input_schema"]),
            }
            for name, item in sorted(catalog.items())
        ]
    else:
        record["reviewed_operation_candidates"] = []
    return redact(record)


def enable(
    names,
    mode="draft",
    *,
    declarations_path=None,
    bindings_path=None,
    clients=None,
    secrets=None,
    ledger=None,
):
    """Return fixed ToolRegistry specs, effects, and score-free status summary."""
    if sys.version_info < (3, 10):
        raise ConnectorUnavailable(
            "business connectors require Python 3.10 or newer; Brick core remains available"
        )
    config.require_mode(mode)
    if not isinstance(names, (list, tuple)) or not names:
        raise ConnectorConfigError("connector names must be a nonempty list")
    if len(names) != len(set(names)) or any(not isinstance(name, str) for name in names):
        raise ConnectorConfigError("connector names must be unique strings")
    declarations, bindings = validate_reviewed_bindings(
        declarations_path, bindings_path
    )
    unknown = set(names) - set(declarations["providers"])
    if unknown:
        raise ConnectorConfigError("unknown connectors: " + ", ".join(sorted(unknown)))
    shutdown()
    clients = dict(clients or {})
    secrets = secrets or KeyringSecretStore()
    ledger = ledger or OperationLedger(project_root=ROOT)
    specs, effects, summary = {}, {}, []
    try:
        for provider in names:
            binding = bindings["providers"][provider]
            if binding["status"] != "bound":
                raise ConnectorUnavailable(
                    f"{provider} is unbound; run authenticated sandbox discovery first"
                )
            account = _validate_account(provider, binding, secrets)
            client = clients.get(provider) or _make_client(provider, binding, secrets)
            _CLIENTS.append(client)
            catalog = client.catalog()
            snapshot = _catalog_snapshot(provider, catalog)
            if _canonical_hash(snapshot) != binding["catalog_sha256"]:
                raise CatalogDrift(
                    f"{provider} catalog differs from its reviewed binding"
                )
            if provider == "hubspot":
                _validate_hubspot_catalog_binding(
                    catalog, binding["identity"], "hubspot.identity"
                )
            live_identity = _validate_live_identity(provider, binding, client)
            context = dict(live_identity)
            if provider == "hubspot" and "open_followups" in binding["tools"]:
                owner_lookup = binding["support"].get("owner_lookup")
                if owner_lookup is not None:
                    _validate_hubspot_catalog_binding(
                        catalog, owner_lookup, "hubspot.support.owner_lookup"
                    )
                owner = _resolve_hubspot_owner(binding, client, live_identity)
                context["owner"] = owner
                context["owner_id"] = owner["owner_id"]
            declarations_by_key = _provider_tools(declarations, provider)
            added, writes = [], []
            for binding_key, operation_binding in binding["tools"].items():
                declaration = declarations_by_key[binding_key]
                label = f"{provider}.{binding_key}"
                if provider == "hubspot":
                    _validate_hubspot_tool_binding(
                        catalog, operation_binding, declaration, label
                    )
                else:
                    _validate_operation_binding(
                        provider, operation_binding, declaration, label,
                        read_only=declaration["effect"] == "read",
                    )
                if mode not in declaration["modes"]:
                    continue
                if mode == "read_only" and declaration["effect"] != "read":
                    continue
                if mode == "draft" and (
                    declaration["transmits"] or declaration["invites"]
                ):
                    continue
                params = {
                    name: (value["type"], value["required"])
                    for name, value in declaration["params"].items()
                }
                name = declaration["name"]
                run = (
                    _workflow_executor(
                        provider, declaration, operation_binding, client, context
                    )
                    if isinstance(operation_binding, dict)
                    and set(operation_binding) == _WORKFLOW_KEYS
                    else _executor(
                        provider,
                        account,
                        declaration,
                        operation_binding,
                        client,
                        ledger,
                        binding["catalog_sha256"],
                        context,
                    )
                )
                specs[name] = {
                    "desc": (
                        "[real, needs confirmation] "
                        if declaration["effect"] != "read"
                        else "[real, read-only] "
                    ) + declaration["description"],
                    "params": params,
                    "example": {"tool": name, "args": declaration["example"]},
                    "run": run,
                    "confirmation": _confirmation(provider, account, declaration),
                    "propagate_faults": True,
                }
                effects[name] = declaration["effect"]
                added.append(name)
                if declaration["effect"] != "read":
                    writes.append(name)
            if not added:
                raise ConnectorUnavailable(
                    f"{provider} has no reviewed tools available in {mode} mode"
                )
            summary.append(
                {
                    "id": provider,
                    "mode": mode,
                    "account": account,
                    "tools": added,
                    "writes": writes,
                    "effects": {
                        name: {
                            "effect": effects[name],
                            "transmits": declarations_by_key[key]["transmits"],
                            "invites": declarations_by_key[key]["invites"],
                            "classified_by": "reviewed declaration",
                        }
                        for key in binding["tools"]
                        for name in [declarations_by_key[key]["name"]]
                        if name in added
                    },
                    "catalog_sha256": binding["catalog_sha256"],
                }
            )
        limit = declarations["limits"]["max_connector_tools"]
        if len(specs) > limit:
            raise ConnectorConfigError(
                f"{len(specs)} connector tools exceed the hard limit of {limit}"
            )
    except BaseException:
        shutdown()
        raise
    return specs, effects, summary


def enforce_total_tools(
    base_registry, connector_specs, declarations_path=None, other_external_specs=None
):
    declarations = config.load_declarations(declarations_path)
    other_external_specs = other_external_specs or {}
    external = len(connector_specs) + len(other_external_specs)
    connector_limit = declarations["limits"]["max_connector_tools"]
    if external > connector_limit:
        raise ConnectorConfigError(
            f"{external} connector tools exceed the hard limit of {connector_limit}"
        )
    total = len(base_registry) + external
    limit = declarations["limits"]["max_total_tools"]
    if total > limit:
        raise ConnectorConfigError(
            f"{total} total tools exceed the hard connector-run limit of {limit}"
        )
    return total


def preflight_backend(backend):
    """Reject model backends that cannot satisfy Brick's structured chat seam."""
    chat = getattr(backend, "chat", None)
    if not callable(chat):
        raise ConnectorUnavailable("local model backend does not provide chat(...)")
    try:
        inspect.signature(chat).bind(
            [], force_json=True, num_predict=1, role="driver"
        )
    except (TypeError, ValueError) as exc:
        raise ConnectorUnavailable(
            "local model backend is incompatible with Brick's structured chat contract"
        ) from exc
    return True


def prompt_rules(mode="draft"):
    config.require_mode(mode)
    text = (
        "\n\nYou also have REAL connector tools for explicitly selected business accounts.\n"
        "- Read the current provider state before proposing a change.\n"
        "- Never invent contact, member, room, booking, owner, date, or account identifiers.\n"
        "- A listed write requires one operator confirmation. If declined, do not retry it.\n"
        "- Memory is temporary for this real-account run and is discarded when it ends.\n"
    )
    if mode == "read_only":
        text += "- Read-only mode exposes no provider-changing operation."
    elif mode == "draft":
        text += "- Draft mode omits every operation declared to transmit or invite."
    else:
        text += "- Live mode may change provider state only after explicit confirmation."
    return text


def shutdown():
    while _CLIENTS:
        client = _CLIENTS.pop()
        try:
            client.close()
        except Exception:
            pass


atexit.register(shutdown)
