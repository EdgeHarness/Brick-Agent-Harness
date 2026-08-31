"""Tiered model router with per-role sampling and keep-alive hints.

Two ideas from the architecture doc, adapted to a Codex-style open agent loop:

1. Multi-model routing. The agent's model calls carry a `role` (driver /
   router / verifier / deep). Each role maps to a tier: a model tag, sampling
   settings, an optional keep-alive hint, and optional adapter metadata.

2. Model reuse hints. The default lineup points interactive roles at one base
   tag and gives the optional `deep` role keep_alive="0". These values are sent
   to Ollama, but this process does not observe or guarantee actual residency,
   eviction timing, or peak memory use.

Each role may name an `adapter`, but the current backend records that field as
metadata only: it neither loads nor evaluates adapters. See adapters_note().

Drop-in for harness.llm.LLM: exposes .chat(messages, force_json=, num_predict=,
role=), plus .calls / .output_tokens / .prompt_tokens / .wall, so run_harness
accepts either object unchanged.
"""
import copy
from collections.abc import Mapping
import json
import os
import time
from types import MappingProxyType

from .llm import LLM
from .kv_cache import CACHE_OFF, validate_cache_mode


def _freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return copy.deepcopy(value)


def default_roles(base="llama3.1:8b", small=None, deep="qwen2.5:14b"):
    """Reuse one base tag for interactive roles and hint that deep is ephemeral.

    Passing ``small`` selects another tag for routing and verification. Actual
    speed, residency, eviction, and memory use are backend/runtime properties
    and are not inferred here.
    """
    light = small or base
    return {
        "driver":   {"model": base,  "temperature": 0.0, "num_predict": 700, "keep_alive": "30m"},
        "router":   {"model": light, "temperature": 0.0, "num_predict": 250, "keep_alive": "30m"},
        "verifier": {"model": light, "temperature": 0.0, "num_predict": 250, "keep_alive": "30m"},
        "deep":     {"model": deep,  "temperature": 0.2, "num_predict": 900, "keep_alive": "0",
                     "on_demand": True},
    }


class ModelRouter:
    def __init__(self, roles=None, num_ctx=8192, log_path=None,
                 default_role="driver", stream_hook=None,
                 cache_mode=CACHE_OFF, allow_legacy_test=False):
        if stream_hook is not None and not callable(stream_hook):
            raise TypeError("stream_hook must be callable or None")
        role_source = default_roles() if roles is None else roles
        if not isinstance(role_source, Mapping) or not role_source:
            raise ValueError("roles must be a nonempty mapping")
        frozen_roles = {}
        for role, spec in role_source.items():
            if not isinstance(role, str) or not role:
                raise ValueError("role names must be nonempty strings")
            if not isinstance(spec, Mapping):
                raise TypeError(f"role {role!r} must map to a dictionary")
            if not isinstance(spec.get("model"), str) or not spec["model"]:
                raise ValueError(f"role {role!r} requires a model")
            for key in ("temperature",):
                if key in spec and (
                    isinstance(spec[key], bool)
                    or not isinstance(spec[key], (int, float))
                ):
                    raise TypeError(
                        f"role {role!r} {key} must be numeric"
                    )
            if "num_predict" in spec and (
                type(spec["num_predict"]) is not int
                or spec["num_predict"] < 1
            ):
                raise ValueError(
                    f"role {role!r} num_predict must be a positive integer"
                )
            if "on_demand" in spec and type(spec["on_demand"]) is not bool:
                raise TypeError(
                    f"role {role!r} on_demand must be bool"
                )
            frozen_roles[role] = _freeze(spec)
        if default_role not in frozen_roles:
            raise ValueError(
                f"default role {default_role!r} is not configured"
            )
        self.roles = MappingProxyType(frozen_roles)
        self.num_ctx = num_ctx
        self.default_role = default_role
        self.log_path = log_path
        self.stream_hook = stream_hook
        self.cache_mode = validate_cache_mode(
            cache_mode, allow_legacy_test=allow_legacy_test
        )
        self.allow_legacy_test = allow_legacy_test
        self.call_log = []          # one record per model call
        self._clients = {}          # (model, keep_alive) -> LLM, reused
        self.reset_usage()

    # --- usage, aggregated across every tier so the budget check still works --
    def reset_usage(self):
        self.calls = 0
        self.prompt_tokens = 0
        self.output_tokens = 0
        self.wall = 0.0

    def _client(self, role, spec):
        # Cache by role. Two roles may use one tag but intentionally request
        # different temperatures or future behavior-affecting client options.
        key = role
        if key not in self._clients:
            self._clients[key] = LLM(spec["model"], num_ctx=self.num_ctx,
                                     temperature=spec.get("temperature", 0.0),
                                     keep_alive=spec.get("keep_alive", "30m"),
                                     stream_hook=self.stream_hook,
                                     cache_mode=self.cache_mode,
                                     allow_legacy_test=self.allow_legacy_test)
        return self._clients[key]

    def retained_model_hints(self):
        """Tags configured without ``on_demand``; not a residency measurement."""
        return sorted({s["model"] for s in self.roles.values() if not s.get("on_demand")})

    def chat(self, messages, force_json=False, num_predict=None, role=None,
             cache_request=None, cache_observer=None):
        if role is not None and role not in self.roles:
            raise ValueError(f"unknown model role {role!r}")
        resolved_role = role or self.default_role
        spec = self.roles[resolved_role]
        llm = self._client(resolved_role, spec)
        np = num_predict if num_predict is not None else spec.get("num_predict", 700)

        before_out, before_prompt = llm.output_tokens, llm.prompt_tokens
        t0 = time.time()
        content = llm.chat(messages, force_json=force_json, num_predict=np,
                           role=role or self.default_role,
                           keep_alive=spec.get("keep_alive"),
                           cache_request=cache_request,
                           cache_observer=cache_observer)
        dt = time.time() - t0

        d_out = llm.output_tokens - before_out
        d_prompt = llm.prompt_tokens - before_prompt
        self.calls += 1
        self.wall += dt
        self.output_tokens += d_out
        self.prompt_tokens += d_prompt

        rec = {"ts": round(time.time(), 3), "role": role or self.default_role,
               "model": spec["model"], "adapter": spec.get("adapter"),
               "prompt_tokens": d_prompt, "output_tokens": d_out,
               "latency_ms": int(dt * 1000)}
        cache_metadata = getattr(llm, "last_cache", None)
        if cache_metadata is not None:
            rec["cache"] = cache_metadata
        self.call_log.append(rec)
        if self.log_path:
            try:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except OSError:
                pass
        return content

    def usage_by_role(self):
        agg = {}
        for r in self.call_log:
            a = agg.setdefault(r["role"], {"calls": 0, "output_tokens": 0, "ms": 0, "model": r["model"]})
            a["calls"] += 1
            a["output_tokens"] += r["output_tokens"]
            a["ms"] += r["latency_ms"]
        return agg


def adapters_note():
    """State exactly what the current adapter field does."""
    return (
        "LoRA adapters: per-role 'adapter' is metadata only; "
        "this backend neither loads nor evaluates adapters."
    )
