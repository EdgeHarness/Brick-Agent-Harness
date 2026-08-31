"""Source-traceable assembly record for one receipt-v1 runtime."""

from dataclasses import asdict, is_dataclass
import hashlib

from .lifecycle import canonical_json_bytes, digest_value
from .router_contract import backend_contract_digest


RUNTIME_RECIPE_VERSION = "brick.runtime-recipe/1"


def _profile_record(profile):
    if is_dataclass(profile):
        values = asdict(profile)
    else:
        values = {
            key: value
            for key, value in vars(profile).items()
            if not key.startswith("_")
        }
    # Profiles are runtime configuration, but an unexpected complex value
    # should not turn this evidence record into an arbitrary serialization.
    safe = {}
    for key, value in values.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
    return safe


def build_runtime_recipe(attempt, llm):
    tools = []
    for name in attempt.tools.names():
        spec = attempt.tools[name]
        tools.append(
            {
                "name": name,
                "schema_digest": digest_value(
                    {
                        "desc": spec["desc"],
                        "params": spec["params"],
                        "example": spec["example"],
                    }
                ),
                "effect": attempt.policy.effect(name),
            }
        )
    router_digest = getattr(llm, "manifest_digest", None)
    if not isinstance(router_digest, str):
        router_digest = backend_contract_digest(llm)
    record = {
        "schema_version": RUNTIME_RECIPE_VERSION,
        "protocol": attempt.config.runtime_protocol,
        "domain": {
            "name": attempt.domain.name,
            "version": attempt.domain.version,
        },
        "tools": tools,
        "profile": _profile_record(attempt.config.profile),
        "prompt_rules_digest": digest_value(attempt.resolved_prompt_rules),
        "router_digest": router_digest,
    }
    return record, hashlib.sha256(canonical_json_bytes(record)).hexdigest()


__all__ = ["RUNTIME_RECIPE_VERSION", "build_runtime_recipe"]
