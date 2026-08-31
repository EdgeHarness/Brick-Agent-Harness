"""Versioned, deterministic model-routing contract.

This is intentionally a fixed capability router, not a claimed reproduction
of a learned Fugu-style coordinator.  The same role manifest always produces
the same route decision, unknown roles fail closed, and the decision digest is
available to the lifecycle journal.
"""

from dataclasses import dataclass
import hashlib
import inspect

from .lifecycle import canonical_json_bytes


ROUTER_CONTRACT_VERSION = "brick.router-contract/1"
KNOWN_CAPABILITIES = frozenset({"chat", "json_object", "streaming"})
PLAIN_BACKEND_CAPABILITIES = frozenset({"chat", "json_object"})
BACKEND_CONFIG_FIELDS = (
    "model",
    "num_ctx",
    "temperature",
    "timeout",
    "keep_alive",
    "retries",
)


class CapabilityError(RuntimeError):
    """The requested role cannot meet its declared model contract."""


@dataclass(frozen=True)
class RouteDecision:
    role: str
    model: str
    required_capabilities: tuple
    contract_digest: str
    decision_digest: str


def _required_capabilities(required):
    if isinstance(required, str) or not isinstance(
        required, (list, tuple, set, frozenset)
    ):
        raise TypeError("required capabilities must be a sequence")
    values = tuple(sorted(set(required)))
    if not values or any(
        not isinstance(item, str) or item not in KNOWN_CAPABILITIES
        for item in values
    ):
        raise CapabilityError("request contains an unknown capability")
    return values


def _backend_config(llm):
    config = {}
    for field in BACKEND_CONFIG_FIELDS:
        if not hasattr(llm, field):
            continue
        value = getattr(llm, field)
        if value is None or isinstance(value, (str, bool, int, float)):
            config[field] = value
        else:
            raise CapabilityError(
                "model backend {!r} configuration is not a stable primitive"
                .format(field)
            )
    return config


def _role_record(role, spec, default_context):
    capabilities = spec.get("capabilities", ("chat", "json_object"))
    if isinstance(capabilities, str) or not isinstance(
        capabilities, (list, tuple, set, frozenset)
    ):
        raise TypeError("role capabilities must be a sequence")
    capabilities = tuple(sorted(capabilities))
    if not capabilities or any(
        not isinstance(item, str) or item not in KNOWN_CAPABILITIES
        for item in capabilities
    ):
        raise ValueError("role capabilities contain an unsupported value")
    context_window = spec.get("context_window", default_context)
    if type(context_window) is not int or context_window < 1:
        raise ValueError("role context_window must be a positive integer")
    return {
        "role": role,
        "model": spec["model"],
        "capabilities": list(capabilities),
        "context_window": context_window,
        "on_demand": bool(spec.get("on_demand", False)),
        "temperature": spec.get("temperature", 0.0),
        "num_predict": spec.get("num_predict"),
        "keep_alive": spec.get("keep_alive"),
        # Adapter remains configuration metadata in the current backend, but
        # changing it must still change the source-traceability digest.
        "adapter": spec.get("adapter"),
    }


class RouterContract:
    """Frozen role manifest with deterministic capability decisions."""

    def __init__(self, roles, default_context):
        records = [
            _role_record(role, roles[role], default_context)
            for role in sorted(roles)
        ]
        self.manifest = {
            "schema_version": ROUTER_CONTRACT_VERSION,
            "availability": "declared",
            "roles": records,
        }
        self.digest = hashlib.sha256(
            canonical_json_bytes(self.manifest)
        ).hexdigest()
        self._by_role = {record["role"]: record for record in records}

    def decide(self, role, required=("chat",), min_context=1):
        if role not in self._by_role:
            raise CapabilityError("unknown model role {!r}".format(role))
        required = _required_capabilities(required)
        record = self._by_role[role]
        missing = set(required) - set(record["capabilities"])
        if missing:
            raise CapabilityError(
                "role {!r} lacks capabilities: {}".format(
                    role, ", ".join(sorted(missing))
                )
            )
        if type(min_context) is not int or min_context < 1:
            raise ValueError("min_context must be a positive integer")
        if record["context_window"] < min_context:
            raise CapabilityError(
                "role {!r} context window is below {}".format(
                    role, min_context
                )
            )
        decision = {
            "schema_version": ROUTER_CONTRACT_VERSION,
            "contract_digest": self.digest,
            "role": role,
            "model": record["model"],
            "required_capabilities": list(required),
            "min_context": min_context,
        }
        return RouteDecision(
            role=role,
            model=record["model"],
            required_capabilities=required,
            contract_digest=self.digest,
            decision_digest=hashlib.sha256(
                canonical_json_bytes(decision)
            ).hexdigest(),
        )


def backend_contract_digest(llm):
    """Digest the interface and behavior-affecting plain-backend settings."""
    chat = getattr(llm, "chat", None)
    if not callable(chat):
        raise CapabilityError("model backend has no chat method")
    try:
        signature = inspect.signature(chat)
        signature.bind([], force_json=True, role="driver")
    except (TypeError, ValueError) as exc:
        raise CapabilityError(
            "model backend does not accept Brick's structured chat contract"
        ) from exc
    manifest = {
        "schema_version": ROUTER_CONTRACT_VERSION,
        "availability": "interface_checked",
        "backend_type": "{}.{}".format(
            type(llm).__module__, type(llm).__qualname__
        ),
        "capabilities": sorted(PLAIN_BACKEND_CAPABILITIES),
        "config": _backend_config(llm),
    }
    return hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()


def preflight_backend(
    llm, role, required=("chat", "json_object"), min_context=1
):
    """Return a deterministic route decision or reject before a model call."""
    preflight = getattr(llm, "preflight", None)
    if callable(preflight):
        return preflight(
            role, required=required, min_context=min_context
        )
    if type(min_context) is not int or min_context < 1:
        raise ValueError("min_context must be a positive integer")
    required = _required_capabilities(required)
    missing = set(required) - PLAIN_BACKEND_CAPABILITIES
    if missing:
        raise CapabilityError(
            "plain model backend lacks capabilities: {}".format(
                ", ".join(sorted(missing))
            )
        )
    context_window = getattr(llm, "num_ctx", None)
    if type(context_window) is not int or context_window < 1:
        raise CapabilityError(
            "plain model backend must declare a positive num_ctx"
        )
    if context_window < min_context:
        raise CapabilityError(
            "plain model backend context window is below {}".format(
                min_context
            )
        )
    digest = backend_contract_digest(llm)
    decision = {
        "schema_version": ROUTER_CONTRACT_VERSION,
        "contract_digest": digest,
        "role": role,
        "model": getattr(llm, "model", type(llm).__name__),
        "required_capabilities": list(required),
        "min_context": min_context,
        "context_window": context_window,
    }
    return RouteDecision(
        role=role,
        model=str(decision["model"]),
        required_capabilities=tuple(decision["required_capabilities"]),
        contract_digest=digest,
        decision_digest=hashlib.sha256(
            canonical_json_bytes(decision)
        ).hexdigest(),
    )


__all__ = [
    "CapabilityError",
    "KNOWN_CAPABILITIES",
    "ROUTER_CONTRACT_VERSION",
    "RouteDecision",
    "RouterContract",
    "backend_contract_digest",
    "preflight_backend",
]
