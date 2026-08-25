"""Strict declarations and authenticated provider bindings."""
import hashlib
import json
import os
import re
from urllib.parse import urlparse

from .errors import ConnectorConfigError


HERE = os.path.dirname(os.path.abspath(__file__))
DECLARATIONS_PATH = os.path.join(HERE, "connectors.json")
BINDINGS_PATH = os.path.join(HERE, "bindings.json")
SCHEMA_VERSION = "brick.connectors/1"
BINDINGS_VERSION = "brick.connector-bindings/2"
MODES = frozenset(("read_only", "draft", "live"))
EFFECTS = frozenset(("read", "external_write"))
RETRY_POLICIES = frozenset(("never", "safe"))
TRANSPORTS = frozenset(("mcp_streamable_http", "graphql"))
_NAME = re.compile(r"^[a-z][a-z0-9_]{0,23}$")
_ACCOUNT = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GRAPHQL_NAME = re.compile(r"^[_A-Za-z][_0-9A-Za-z]*$")
_POINTER_PART = re.compile(r"^[_A-Za-z][_0-9A-Za-z.\-]*$")
_TOP_KEYS = frozenset(("schema_version", "limits", "providers"))
_LIMIT_KEYS = frozenset(("max_connector_tools", "max_total_tools"))
_PROVIDER_KEYS = frozenset(("summary", "transport", "setup", "tools"))
_TOOL_KEYS = frozenset(
    (
        "name", "binding_key", "description", "params", "example", "effect",
        "transmits", "invites", "modes", "idempotent", "retry",
        "rate_limit_bucket", "normalized_schema_sha256",
    )
)
_PARAM_KEYS = frozenset(("type", "required"))
_BINDING_TOP_KEYS = frozenset(("schema_version", "providers"))
_BINDING_PROVIDER_KEYS = frozenset(
    (
        "status", "endpoint", "account_alias", "account_fingerprint_sha256",
        "catalog_sha256", "oauth_scope", "identity", "support", "tools",
    )
)
_OPERATION_KEYS = frozenset(
    (
        "operation", "literal_arguments", "argument_map", "context_map",
        "argument_transforms", "result_map", "item_map", "error_origin",
        "verification",
    )
)
_WORKFLOW_KEYS = frozenset(("workflow_kind", "calls"))
_WORKFLOW_STEP_KEYS = frozenset(("label", "binding"))
_ITEM_MAP_KEYS = frozenset(("source", "fields"))
_ARGUMENT_TRANSFORMS = frozenset(
    ("iso8601_to_unix", "iso_date_to_utc_millis_end", "singleton_list")
)
_CONTEXT_ARGUMENTS = frozenset(("owner_id", "user_email"))
_ACTIVITY_LABELS = frozenset(("call", "email", "meeting", "note", "task"))


def canonical_json(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def digest(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalized_schema_digest(tool):
    """Bind exactly the model-facing name, documentation, schema, and example."""
    return digest(
        {
            key: tool[key]
            for key in ("name", "description", "params", "example")
        }
    )


def local_bindings_path():
    """Operator-local binding path; never a repository artifact."""
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return os.path.join(base, "BrickAgentHarness", "connectors", "bindings.json")
    return os.path.join(
        os.path.expanduser("~"), ".brick-agent-harness", "connectors", "bindings.json"
    )


def runtime_bindings_path(path=None):
    """Use an explicit path, then an installed local binding, else safe defaults."""
    if path is not None:
        return os.fspath(path)
    local = local_bindings_path()
    return local if os.path.isfile(local) else BINDINGS_PATH


def _load(path):
    try:
        with open(path, encoding="utf-8-sig") as handle:
            return json.load(handle)
    except (OSError, ValueError) as exc:
        raise ConnectorConfigError(f"connector JSON is unreadable: {path}") from exc


def _exact(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        got = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise ConnectorConfigError(
            f"{label} must contain exactly {', '.join(sorted(expected))}; got {got}"
        )


def require_mode(mode):
    if mode not in MODES:
        raise ConnectorConfigError(
            "connector mode must be one of " + ", ".join(sorted(MODES))
        )
    return mode


def load_declarations(path=None):
    doc = _load(path or DECLARATIONS_PATH)
    _exact(doc, _TOP_KEYS, "connector declarations")
    if doc["schema_version"] != SCHEMA_VERSION:
        raise ConnectorConfigError("unsupported connector declaration schema")
    _exact(doc["limits"], _LIMIT_KEYS, "connector limits")
    max_connector = doc["limits"]["max_connector_tools"]
    max_total = doc["limits"]["max_total_tools"]
    if type(max_connector) is not int or not 1 <= max_connector <= 8:
        raise ConnectorConfigError("max_connector_tools must be between 1 and 8")
    if type(max_total) is not int or not max_connector <= max_total <= 25:
        raise ConnectorConfigError("max_total_tools must be between connector limit and 25")
    providers = doc["providers"]
    if not isinstance(providers, dict) or not providers:
        raise ConnectorConfigError("providers must be a nonempty object")
    seen = set()
    for provider_name, provider in providers.items():
        if not _NAME.fullmatch(provider_name):
            raise ConnectorConfigError(f"invalid provider name {provider_name!r}")
        _exact(provider, _PROVIDER_KEYS, f"provider {provider_name}")
        if provider["transport"] not in TRANSPORTS:
            raise ConnectorConfigError(f"invalid transport for {provider_name}")
        if not isinstance(provider["summary"], str) or not provider["summary"]:
            raise ConnectorConfigError(f"provider {provider_name} needs a summary")
        if not isinstance(provider["setup"], list) or any(
            not isinstance(item, str) or not item for item in provider["setup"]
        ):
            raise ConnectorConfigError(f"provider {provider_name} setup must be strings")
        tools = provider["tools"]
        if not isinstance(tools, list) or not tools:
            raise ConnectorConfigError(f"provider {provider_name} needs tools")
        binding_keys = set()
        for tool in tools:
            _exact(tool, _TOOL_KEYS, f"{provider_name} tool")
            name = tool["name"]
            if not isinstance(name, str) or not _NAME.fullmatch(name):
                raise ConnectorConfigError(f"invalid connector tool name {name!r}")
            if name in seen:
                raise ConnectorConfigError(f"duplicate connector tool name {name!r}")
            seen.add(name)
            if not isinstance(tool["binding_key"], str) or not _NAME.fullmatch(
                tool["binding_key"]
            ):
                raise ConnectorConfigError(f"invalid binding key for {name}")
            if tool["binding_key"] in binding_keys:
                raise ConnectorConfigError(
                    f"duplicate binding key {tool['binding_key']!r} for {provider_name}"
                )
            binding_keys.add(tool["binding_key"])
            if not isinstance(tool["description"], str) or not tool["description"]:
                raise ConnectorConfigError(f"tool {name} needs a description")
            if tool["effect"] not in EFFECTS:
                raise ConnectorConfigError(f"tool {name} has invalid effect")
            if type(tool["transmits"]) is not bool or type(tool["invites"]) is not bool:
                raise ConnectorConfigError(f"tool {name} flags must be bool")
            if tool["effect"] == "read" and (tool["transmits"] or tool["invites"]):
                raise ConnectorConfigError(f"read tool {name} cannot transmit or invite")
            modes = tool["modes"]
            if not isinstance(modes, list) or not modes or not set(modes) <= MODES:
                raise ConnectorConfigError(f"tool {name} has invalid modes")
            if len(modes) != len(set(modes)):
                raise ConnectorConfigError(f"tool {name} has duplicate modes")
            if type(tool["idempotent"]) is not bool:
                raise ConnectorConfigError(f"tool {name} idempotent must be bool")
            if tool["retry"] not in RETRY_POLICIES:
                raise ConnectorConfigError(f"tool {name} has invalid retry policy")
            if tool["effect"] != "read" and tool["retry"] != "never" \
                    and not tool["idempotent"]:
                raise ConnectorConfigError(f"non-idempotent write {name} cannot retry")
            if not isinstance(tool["rate_limit_bucket"], str) or not _NAME.fullmatch(
                tool["rate_limit_bucket"]
            ):
                raise ConnectorConfigError(f"tool {name} has invalid rate bucket")
            params = tool["params"]
            if not isinstance(params, dict) or len(params) > 6:
                raise ConnectorConfigError(f"tool {name} may have at most six params")
            for param_name, param in params.items():
                if not _NAME.fullmatch(param_name):
                    raise ConnectorConfigError(f"tool {name} has invalid param {param_name}")
                _exact(param, _PARAM_KEYS, f"{name}.{param_name}")
                if not isinstance(param["type"], str) or not param["type"]:
                    raise ConnectorConfigError(f"tool {name} param type is empty")
                if type(param["required"]) is not bool:
                    raise ConnectorConfigError(f"tool {name} param required must be bool")
            if not isinstance(tool["example"], dict) or not set(tool["example"]) <= set(params):
                raise ConnectorConfigError(f"tool {name} example contains unknown params")
            required = {key for key, value in params.items() if value["required"]}
            if not required <= set(tool["example"]):
                raise ConnectorConfigError(f"tool {name} example omits required params")
            if tool["normalized_schema_sha256"] != normalized_schema_digest(tool):
                raise ConnectorConfigError(
                    f"tool {name} normalized schema digest is wrong"
                )
    if len(seen) > max_connector:
        # The total catalog may exceed the per-run cap; each provider must not.
        for provider_name, provider in providers.items():
            if len(provider["tools"]) > max_connector:
                raise ConnectorConfigError(
                    f"provider {provider_name} exceeds the connector tool cap"
                )
    return doc


def _validate_endpoint(provider, endpoint, status):
    if status == "unbound":
        if endpoint is not None and provider == "hubspot" \
                and endpoint != "https://mcp.hubspot.com/":
            raise ConnectorConfigError("unbound HubSpot endpoint must be official")
        return
    if not isinstance(endpoint, str):
        raise ConnectorConfigError(f"bound provider {provider} needs an endpoint")
    parsed = urlparse(endpoint)
    if parsed.scheme != "https":
        raise ConnectorConfigError("bound connector endpoints must use HTTPS")
    if provider == "hubspot" and endpoint != "https://mcp.hubspot.com/":
        raise ConnectorConfigError("HubSpot binding must use the official MCP endpoint")
    if provider == "optix" and endpoint.rstrip("/") != \
            "https://api.optixapp.com/graphql":
        raise ConnectorConfigError(
            "Optix binding must use the official GraphQL endpoint"
        )


def _pointer_parts(pointer, label):
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ConnectorConfigError(f"{label} must be a JSON pointer")
    parts = pointer.split("/")[1:]
    if not parts or any(
        not part
        or (part.isdigit() and int(part) > 20)
        or not (part.isdigit() or _POINTER_PART.fullmatch(part))
        for part in parts
    ):
        raise ConnectorConfigError(f"{label} is an invalid JSON pointer")
    return tuple(parts)


def _literal_leaf_paths(value, prefix=()):
    if isinstance(value, dict):
        if not value and prefix:
            yield prefix
        for key, item in value.items():
            if not isinstance(key, str) or not _POINTER_PART.fullmatch(key):
                raise ConnectorConfigError("literal provider argument keys are invalid")
            yield from _literal_leaf_paths(item, prefix + (key,))
    elif isinstance(value, list):
        if len(value) > 21:
            raise ConnectorConfigError("literal provider argument lists are too large")
        if not value and prefix:
            yield prefix
        for index, item in enumerate(value):
            yield from _literal_leaf_paths(item, prefix + (str(index),))
    else:
        yield prefix


def _validate_destinations(operation, label):
    destinations = []
    for field in ("argument_map", "context_map"):
        for destination in operation[field].values():
            destinations.append(_pointer_parts(destination, f"{label} {field} destination"))
    if len(destinations) != len(set(destinations)):
        raise ConnectorConfigError(f"{label} provider argument destinations must be unique")
    if any(
        left != right
        and ((len(left) < len(right) and right[:len(left)] == left)
             or (len(right) < len(left) and left[:len(right)] == right))
        for index, left in enumerate(destinations)
        for right in destinations[index + 1:]
    ):
        raise ConnectorConfigError(f"{label} provider argument destinations may not overlap")
    literal_paths = list(_literal_leaf_paths(operation["literal_arguments"]))
    for destination in destinations:
        if any(
            (len(leaf) <= len(destination) and destination[:len(leaf)] == leaf)
            or (len(destination) < len(leaf) and leaf[:len(destination)] == destination)
            for leaf in literal_paths
        ):
            raise ConnectorConfigError(
                f"{label} model or context argument would overwrite a fixed literal"
            )


def _validate_item_map(operation, label):
    item_map = operation["item_map"]
    if item_map is None:
        return
    _exact(item_map, _ITEM_MAP_KEYS, f"{label} item_map")
    source = item_map["source"]
    if source not in operation["result_map"]:
        raise ConnectorConfigError(f"{label} item_map source is not projected")
    fields = item_map["fields"]
    if not isinstance(fields, dict) or not fields:
        raise ConnectorConfigError(f"{label} item_map fields must be nonempty")
    for name, pointer in fields.items():
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise ConnectorConfigError(f"{label} item_map has an invalid field name")
        _pointer_parts(pointer, f"{label} item field")


def _validate_operation_shape(
    provider, operation, label, allow_verification, read_only=False
):
    provider_keys = (
        {"input_schema_sha256"}
        if provider == "hubspot"
        else {"document", "document_sha256"}
    )
    expected = set(_OPERATION_KEYS) | provider_keys
    if not allow_verification:
        expected.remove("verification")
    _exact(operation, expected, label)
    if not isinstance(operation["operation"], str) or not operation["operation"]:
        raise ConnectorConfigError(f"{label} operation must be nonempty")
    for field in ("argument_map", "context_map", "result_map"):
        mapping = operation[field]
        if not isinstance(mapping, dict):
            raise ConnectorConfigError(f"{label} {field} must be an object")
        if field == "result_map" and not mapping:
            raise ConnectorConfigError(f"{label} result_map must be nonempty")
        if any(
            not isinstance(key, str) or not isinstance(value, str) or not value
            for key, value in mapping.items()
        ):
            raise ConnectorConfigError(f"{label} {field} must map nonempty strings")
    literals = operation["literal_arguments"]
    if not isinstance(literals, dict):
        raise ConnectorConfigError(f"{label} literal_arguments must be an object")
    try:
        encoded_literals = canonical_json(literals).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ConnectorConfigError(f"{label} literals are not JSON-compatible") from exc
    if len(encoded_literals) > 32 * 1024:
        raise ConnectorConfigError(f"{label} literals exceed the binding limit")
    if not set(operation["context_map"]) <= _CONTEXT_ARGUMENTS:
        raise ConnectorConfigError(f"{label} uses an unsupported derived context argument")
    _validate_destinations(operation, label)
    transforms = operation["argument_transforms"]
    if not isinstance(transforms, dict) or not set(transforms) <= set(
        operation["argument_map"]
    ):
        raise ConnectorConfigError(
            f"{label} argument_transforms must name mapped Brick arguments"
        )
    if any(value not in _ARGUMENT_TRANSFORMS for value in transforms.values()):
        raise ConnectorConfigError(f"{label} has an unsupported argument transform")
    if any(not pointer.startswith("/") for pointer in operation["result_map"].values()):
        raise ConnectorConfigError(f"{label} result pointers must start with '/'")
    for pointer in operation["result_map"].values():
        _pointer_parts(pointer, f"{label} result field")
    _validate_item_map(operation, label)
    if operation["error_origin"] not in ("model", "environment"):
        raise ConnectorConfigError(f"{label} error_origin is invalid")
    if provider == "hubspot":
        if not isinstance(operation["input_schema_sha256"], str) or not _SHA256.fullmatch(
            operation["input_schema_sha256"]
        ):
            raise ConnectorConfigError(f"{label} input schema digest is invalid")
    else:
        document = operation["document"]
        if not isinstance(document, str) or not document.strip():
            raise ConnectorConfigError(f"{label} GraphQL document is empty")
        document_digest = hashlib.sha256(document.encode("utf-8")).hexdigest()
        if document_digest != operation["document_sha256"]:
            raise ConnectorConfigError(f"{label} GraphQL document digest is wrong")
        if "__schema" in document or "__type" in document:
            raise ConnectorConfigError(
                f"{label} cannot bind GraphQL introspection as a model tool"
            )
        kind = re.match(r"^\s*(query|mutation)\b", document)
        if kind is None:
            raise ConnectorConfigError(
                f"{label} GraphQL document must declare query or mutation"
            )
        if read_only and (
            kind.group(1) != "query" or re.search(r"\bmutation\b", document)
        ):
            raise ConnectorConfigError(
                f"{label} read-only GraphQL document cannot contain a mutation"
            )
        variables = set(re.findall(r"\$([_A-Za-z][_0-9A-Za-z]*)", document))
        roots = {
            destination.split("/")[1]
            for mapping in (operation["argument_map"], operation["context_map"])
            for destination in mapping.values()
        } | set(operation["literal_arguments"])
        if not roots <= variables:
            raise ConnectorConfigError(
                f"{label} maps an argument absent from its GraphQL document"
            )
    if allow_verification and operation["verification"] is not None:
        _validate_operation_shape(
            provider,
            operation["verification"],
            label + ".verification",
            False,
            True,
        )


def _validate_tool_binding(provider, binding, declaration, label):
    if isinstance(binding, dict) and set(binding) == _WORKFLOW_KEYS:
        if provider != "hubspot" or declaration["name"] != "hs_recent_activity":
            raise ConnectorConfigError(f"{label} cannot use a provider workflow")
        if binding["workflow_kind"] != "hubspot_recent_activity_v1":
            raise ConnectorConfigError(f"{label} has an unsupported workflow")
        calls = binding["calls"]
        if not isinstance(calls, list) or len(calls) != len(_ACTIVITY_LABELS):
            raise ConnectorConfigError(f"{label} must bind all five activity reads")
        labels = set()
        for index, step in enumerate(calls):
            _exact(step, _WORKFLOW_STEP_KEYS, f"{label}.calls[{index}]")
            step_label = step["label"]
            if step_label not in _ACTIVITY_LABELS or step_label in labels:
                raise ConnectorConfigError(f"{label} has invalid activity labels")
            labels.add(step_label)
            _validate_operation_shape(
                provider, step["binding"], f"{label}.{step_label}", False, True
            )
        if labels != _ACTIVITY_LABELS:
            raise ConnectorConfigError(f"{label} activity workflow is incomplete")
        return
    _validate_operation_shape(
        provider, binding, label, True, declaration["effect"] == "read"
    )


def load_bindings(path=None, declarations=None):
    declarations = declarations or load_declarations()
    doc = _load(path or BINDINGS_PATH)
    _exact(doc, _BINDING_TOP_KEYS, "connector bindings")
    if doc["schema_version"] != BINDINGS_VERSION:
        raise ConnectorConfigError("unsupported connector binding schema")
    if set(doc["providers"]) != set(declarations["providers"]):
        raise ConnectorConfigError("bindings must name exactly the declared providers")
    for provider_name, binding in doc["providers"].items():
        _exact(binding, _BINDING_PROVIDER_KEYS, f"{provider_name} binding")
        status = binding["status"]
        if status not in ("unbound", "bound"):
            raise ConnectorConfigError(f"invalid binding status for {provider_name}")
        _validate_endpoint(provider_name, binding["endpoint"], status)
        if status == "unbound":
            if any(
                binding[key] is not None
                for key in (
                    "account_alias", "account_fingerprint_sha256", "catalog_sha256",
                )
            ) or binding["identity"] is not None or binding["support"] or binding["tools"]:
                raise ConnectorConfigError(
                    f"unbound provider {provider_name} cannot carry live bindings"
                )
            continue
        if not isinstance(binding["account_alias"], str) or not _ACCOUNT.fullmatch(
            binding["account_alias"]
        ):
            raise ConnectorConfigError(f"invalid account alias for {provider_name}")
        for field in ("account_fingerprint_sha256", "catalog_sha256"):
            if not isinstance(binding[field], str) or not _SHA256.fullmatch(binding[field]):
                raise ConnectorConfigError(f"invalid {field} for {provider_name}")
        if binding["oauth_scope"] is not None and not isinstance(
            binding["oauth_scope"], str
        ):
            raise ConnectorConfigError(f"invalid OAuth scope for {provider_name}")
        if not isinstance(binding["tools"], dict) or not binding["tools"]:
            raise ConnectorConfigError(f"bound provider {provider_name} needs tool bindings")
        if not isinstance(binding["support"], dict):
            raise ConnectorConfigError(f"{provider_name} support bindings must be an object")
        if not isinstance(binding["identity"], dict):
            raise ConnectorConfigError(
                f"bound provider {provider_name} needs a live identity binding"
            )
        _validate_operation_shape(
            provider_name, binding["identity"], f"{provider_name}.identity", False,
            True,
        )
        if binding["identity"]["error_origin"] != "environment":
            raise ConnectorConfigError(
                f"{provider_name} identity errors must be environment-origin"
            )
        declared_keys = {
            tool["binding_key"] for tool in declarations["providers"][provider_name]["tools"]
        }
        if provider_name == "hubspot" and set(binding["tools"]) != declared_keys:
            raise ConnectorConfigError(
                "hubspot must bind exactly its four declared read tools"
            )
        if provider_name != "hubspot" and not set(binding["tools"]) <= declared_keys:
            raise ConnectorConfigError(f"{provider_name} has unknown bound tools")
        if provider_name == "hubspot":
            unknown_support = set(binding["support"]) - {"owner_lookup"}
            if unknown_support:
                raise ConnectorConfigError("HubSpot has unknown support bindings")
            if "owner_lookup" in binding["support"]:
                _validate_operation_shape(
                    "hubspot", binding["support"]["owner_lookup"],
                    "hubspot.support.owner_lookup", False, True,
                )
        elif binding["support"]:
            raise ConnectorConfigError(f"{provider_name} does not use support bindings")
        for key, operation in binding["tools"].items():
            declaration = next(
                tool
                for tool in declarations["providers"][provider_name]["tools"]
                if tool["binding_key"] == key
            )
            _validate_tool_binding(
                provider_name, operation, declaration, f"{provider_name}.{key}"
            )
    return doc


def binding_status(provider, binding, secrets=None):
    if binding["status"] == "unbound":
        return "unbound"
    if secrets is None:
        try:
            from .credentials import KeyringSecretStore
            secrets = KeyringSecretStore()
        except Exception:
            return "authorization required"
    account = binding["account_alias"]
    if provider == "hubspot":
        if secrets.get_json(provider, account, "oauth_client") is None or \
                secrets.get_json(provider, account, "oauth_tokens") is None:
            return "authorization required"
    elif secrets.get(provider, account, "api_token") is None:
        return "authorization required"
    identity = secrets.get(provider, account, "account_identity")
    if identity is None:
        return "authorization required"
    from .credentials import account_fingerprint
    if account_fingerprint(identity) != binding["account_fingerprint_sha256"]:
        return "account mismatch"
    return "ready"


def available(declarations_path=None, bindings_path=None, secrets=None):
    declarations = load_declarations(declarations_path)
    bindings = load_bindings(runtime_bindings_path(bindings_path), declarations)
    return [
        (
            name,
            provider["summary"],
            binding_status(name, bindings["providers"][name], secrets),
        )
        for name, provider in sorted(declarations["providers"].items())
    ]


def setup_notes(name, declarations_path=None, bindings_path=None, secrets=None):
    declarations = load_declarations(declarations_path)
    bindings = load_bindings(runtime_bindings_path(bindings_path), declarations)
    if name not in declarations["providers"]:
        raise ConnectorConfigError(f"unknown connector {name!r}")
    provider = declarations["providers"][name]
    status = binding_status(name, bindings["providers"][name], secrets)
    return "\n".join(
        [f"{name} - {provider['summary']} [{status}]"]
        + [f"    {line}" for line in provider["setup"]]
    )
