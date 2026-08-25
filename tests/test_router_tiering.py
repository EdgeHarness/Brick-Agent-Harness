"""Installed-models gate for the tiered model router.

Turning tiering on by default breaks a run when the small model named by a
role is not installed: Ollama returns 4xx for an unknown tag, and that is
raised straight through (see harness/llm.py _attempt_with_retries). These
tests pin the best-effort installed-models probe, the tag-matching rule, and
the build_llm() fallback that keeps a missing model from crashing a run.

No network access: every HTTP call is monkeypatched.
"""
import json
import os
import sys

import pytest
import requests

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

from agents._shared.run_agent import build_llm, validate_config  # noqa: E402
from harness import profiles  # noqa: E402
from harness.llm import installed_models, model_installed  # noqa: E402
from harness.model_router import ModelRouter  # noqa: E402


AGENT_8B_CONFIG = os.path.join(PROJECT, "agents", "8b", "config.json")

REAL_TAGS_BODY = {
    "models": [
        {"name": "llama3.2:1b", "model": "llama3.2:1b"},
        {"name": "llama3.1:8b", "model": "llama3.1:8b"},
    ]
}


class FakeResponse:
    def __init__(self, status_code=200, json_body=None, text="not json"):
        self.status_code = status_code
        self._json_body = json_body
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}", response=self)

    def json(self):
        if self._json_body is None:
            raise json.JSONDecodeError("bad body", self.text, 0)
        return self._json_body


def _options(tiers=False, small=None, deep=None):
    return {"tiers": tiers, "small": small, "deep": deep}


# --- installed_models() ------------------------------------------------

def test_installed_models_parses_a_realistic_tags_body(monkeypatch):
    monkeypatch.setattr(
        requests, "get", lambda url, timeout=None: FakeResponse(json_body=REAL_TAGS_BODY)
    )
    assert installed_models() == {"llama3.2:1b", "llama3.1:8b"}


def test_installed_models_returns_none_on_connection_error(monkeypatch):
    def raise_conn(url, timeout=None):
        raise requests.ConnectionError("no route")

    monkeypatch.setattr(requests, "get", raise_conn)
    assert installed_models() is None


def test_installed_models_returns_none_on_timeout(monkeypatch):
    def raise_timeout(url, timeout=None):
        raise requests.Timeout("too slow")

    monkeypatch.setattr(requests, "get", raise_timeout)
    assert installed_models() is None


def test_installed_models_returns_none_on_non_200(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, timeout=None: FakeResponse(status_code=500))
    assert installed_models() is None


def test_installed_models_returns_none_on_bad_json(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, timeout=None: FakeResponse(json_body=None))
    assert installed_models() is None


# --- model_installed() tag matching -------------------------------------

def test_bare_tag_matches_installed_latest():
    assert model_installed("llama3.2", {"llama3.2:latest"})


def test_bare_tag_does_not_match_a_different_installed_tag():
    assert not model_installed("llama3.2", {"llama3.2:1b"})


# --- build_llm() gate ----------------------------------------------------

ROLES = {
    "driver":   {"model": "llama3.1:8b"},
    "router":   {"model": "llama3.2:1b"},
    "verifier": {"model": "llama3.2:1b"},
}


def _config_with_roles(roles):
    return {"name": "t", "model": "llama3.1:8b", "router": {"roles": roles}}


def test_tiering_on_when_every_role_is_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(
        requests, "get", lambda url, timeout=None: FakeResponse(json_body=REAL_TAGS_BODY)
    )
    llm, router = build_llm(_config_with_roles(ROLES), _options(), str(tmp_path))
    assert isinstance(router, ModelRouter)
    assert llm is router


def test_tiering_off_when_a_role_model_is_missing(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        requests, "get", lambda url, timeout=None: FakeResponse(json_body=REAL_TAGS_BODY)
    )
    roles = dict(ROLES, verifier={"model": "qwen2.5:14b"})
    llm, router = build_llm(_config_with_roles(roles), _options(), str(tmp_path))
    assert router is None
    assert llm.model == "llama3.1:8b"
    assert "qwen2.5:14b" in capsys.readouterr().err


def test_tiering_stays_on_when_installed_set_is_unknown(monkeypatch, tmp_path):
    def raise_conn(url, timeout=None):
        raise requests.ConnectionError("no route")

    monkeypatch.setattr(requests, "get", raise_conn)
    roles = dict(ROLES, verifier={"model": "qwen2.5:14b"})
    llm, router = build_llm(_config_with_roles(roles), _options(), str(tmp_path))
    assert isinstance(router, ModelRouter)
    assert llm is router


# --- agents/8b/config.json -----------------------------------------------

def test_8b_config_parses_and_validates():
    with open(AGENT_8B_CONFIG, encoding="utf-8-sig") as f:
        config = json.load(f)
    validate_config(config)
    assert config["model"] == "llama3.1:8b"
    ModelRouter(roles=config["router"]["roles"])


def test_8b_config_resolves_profile_from_top_level_model_not_a_role_tag():
    with open(AGENT_8B_CONFIG, encoding="utf-8-sig") as f:
        config = json.load(f)
    profile = profiles.for_model(config["model"])
    assert profile is profiles.for_model("llama3.1:8b")
