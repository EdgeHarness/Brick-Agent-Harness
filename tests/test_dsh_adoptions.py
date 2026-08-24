"""Mechanisms adopted from the DeepSeek Harness sweep (docs/DSH_GAP_ANALYSIS.md).

Each is default-off or bench-invisible; these tests pin both the new behavior
and the unchanged default.
"""
import datetime
import json

import pytest
import requests

from harness import agent
from harness.agent import _obs, _shrink_context
from harness.llm import LLM
from harness.mcp_bridge import _child_env
from harness.profiles import PROFILES


# ------------------------------------------------------------- env scrub ----

def test_child_env_drops_credential_shaped_variables(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_x")
    monkeypatch.setenv("DB_PASSWORD", "hunter2")
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("HOME", "/home/u")

    env = _child_env(None)

    assert "OPENAI_API_KEY" not in env
    assert "GITHUB_TOKEN" not in env
    assert "DB_PASSWORD" not in env
    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/home/u"


def test_child_env_keeps_what_the_server_config_declares(monkeypatch):
    monkeypatch.delenv("MY_MCP_TOKEN", raising=False)
    env = _child_env({"MY_MCP_TOKEN": "explicit"})
    assert env["MY_MCP_TOKEN"] == "explicit"


# ------------------------------------------------------------ llm retries ----

class _Boom(Exception):
    pass


def _llm_with_scripted_attempts(retries, outcomes):
    llm = LLM("m", retries=retries)
    calls = {"n": 0}

    def attempt(payload, hook):
        outcome = outcomes[min(calls["n"], len(outcomes) - 1)]
        calls["n"] += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome, {}

    llm._attempt = attempt
    return llm, calls


def test_retries_recover_from_a_transient_connection_error(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    llm, calls = _llm_with_scripted_attempts(
        2, [requests.ConnectionError("down"), ("ok", {})[0]]
    )
    assert llm.chat([{"role": "user", "content": "hi"}]) == "ok"
    assert calls["n"] == 2


def test_zero_retries_is_the_default_and_raises_immediately():
    llm, calls = _llm_with_scripted_attempts(0, [requests.ConnectionError("down")])
    assert llm.retries == 0
    with pytest.raises(requests.ConnectionError):
        llm.chat([{"role": "user", "content": "hi"}])
    assert calls["n"] == 1


def test_a_partially_streamed_reply_is_never_retried(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    err = requests.ConnectionError("mid-stream")
    err.streamed_partial = True
    llm, calls = _llm_with_scripted_attempts(2, [err])
    with pytest.raises(requests.ConnectionError):
        llm.chat([{"role": "user", "content": "hi"}])
    assert calls["n"] == 1


def test_a_client_error_is_never_retried(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    response = requests.Response()
    response.status_code = 404
    err = requests.HTTPError(response=response)
    llm, calls = _llm_with_scripted_attempts(2, [err])
    with pytest.raises(requests.HTTPError):
        llm.chat([{"role": "user", "content": "hi"}])
    assert calls["n"] == 1


# -------------------------------------------------- observation keep-tail ----

def test_obs_default_clip_is_unchanged():
    assert _obs("x" * 30, limit=10) == "x" * 10 + " ...[truncated]"


def test_obs_keep_tail_preserves_the_end_of_a_result():
    text = "HEAD" + "x" * 100 + "total: $412.30"
    clipped = _obs(text, limit=40, keep_tail=14)
    assert clipped.startswith("HEAD")
    assert clipped.endswith("total: $412.30")
    assert "...[middle truncated]..." in clipped


# ------------------------------------------------------- context pressure ----

def _messages(n_obs, obs_len):
    msgs = [{"role": "system", "content": "S" * 200}]
    for i in range(n_obs):
        msgs.append({"role": "assistant", "content": json.dumps({"tool": "t"})})
        msgs.append({"role": "user", "content": "OBSERVATION: " + "o" * obs_len})
    return msgs


def test_shrink_context_prunes_old_observations_under_pressure():
    ep = agent.Episode()
    msgs = _messages(n_obs=10, obs_len=2000)
    changed = _shrink_context(msgs, num_ctx=1024, ep=ep)
    assert changed is True
    pruned = [m for m in msgs if "pruned to fit the context" in str(m.get("content"))]
    assert pruned
    # the newest messages are untouched
    assert "pruned" not in msgs[-1]["content"]
    assert any(n["kind"] == "context" for n in ep.transcript)


def test_shrink_context_is_a_no_op_below_the_threshold():
    ep = agent.Episode()
    msgs = _messages(n_obs=2, obs_len=300)
    assert _shrink_context(msgs, num_ctx=8192, ep=ep) is False
    assert not ep.transcript


def test_every_named_profile_opts_into_both_mechanisms():
    for tag, prof in PROFILES.items():
        assert prof.observation_keep_tail > 0, tag
        assert prof.prune_context is True, tag
