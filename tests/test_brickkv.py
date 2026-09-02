"""Offline contract tests for Brick's managed GenieX cache path."""
from email.message import Message
import io
import json
import urllib.error

import pytest
import requests

from harness.agent import _AttemptLLM
from harness.kv_cache import (
    CACHE_LEGACY_TEST,
    CACHE_MANAGED,
    CACHE_OFF,
    CacheConfigurationError,
    CacheCoordinator,
    ManagedCacheProtocolError,
)
from harness.llm import LLM
from npu import ollama_shim


def managed_probe_error(*, protocol="2"):
    headers = Message()
    if protocol is not None:
        headers["GenieX-Cache-Protocol"] = protocol
    return urllib.error.HTTPError(
        "http://127.0.0.1:18181/v1/chat/completions",
        400,
        "bad request",
        headers,
        io.BytesIO(b'{"error":"managed caching requires a generative request"}'),
    )


def metadata(status, reason, marker="a", reusable=True):
    return {
        "mode": "managed",
        "status": status,
        "revision": "sha256:" + marker * 64,
        "reason": reason,
        "reusable": reusable,
    }


def test_coordinator_separates_attempts_and_reasoning_roles():
    first = CacheCoordinator()
    second = CacheCoordinator()
    driver = first.request("driver")
    router = first.request("router")
    assert first.attempt_session != second.attempt_session
    assert driver["session"] != router["session"]
    assert driver["session"] != second.request("driver")["session"]
    assert driver["parent"] == router["parent"] == ""


def test_coordinator_advances_only_after_a_valid_commit():
    coordinator = CacheCoordinator()
    original = coordinator.request("driver")
    coordinator.commit(metadata("cold", "first_request"), "driver")
    followup = coordinator.request("driver")
    assert followup["session"] == original["session"]
    assert followup["parent"] == "sha256:" + "a" * 64

    coordinator.commit(metadata("reset", "branch", "b"), "driver")
    assert coordinator.request("driver")["parent"] == "sha256:" + "b" * 64

    coordinator.commit(
        metadata("reset", "previous_not_reusable", "c", reusable=False),
        "driver",
    )
    assert coordinator.request("driver")["parent"] == "sha256:" + "c" * 64
    assert coordinator.diagnostics()["events"][-1]["reusable"] is False


@pytest.mark.parametrize("value", [
    None,
    {},
    {"mode": "managed", "status": "hit", "revision": "bad", "reason": "x"},
    metadata("reused", "branch"),
    metadata("cold", "exact_extension"),
])
def test_coordinator_rejects_untrusted_cache_metadata(value):
    coordinator = CacheCoordinator()
    coordinator.request("driver")
    with pytest.raises(ManagedCacheProtocolError):
        coordinator.commit(value, "driver")


@pytest.mark.parametrize("protocol,expected", (("2", True), ("1", False), (None, False)))
def test_npu_shim_requires_exact_managed_protocol_version(
    monkeypatch, protocol, expected
):
    def reject(_request, timeout):
        assert timeout == 10
        raise managed_probe_error(protocol=protocol)

    monkeypatch.setattr("urllib.request.urlopen", reject)
    assert ollama_shim.probe_managed_cache(
        "http://127.0.0.1:18181", "fixture"
    ) is expected


def test_npu_shim_rechecks_protocol_on_every_managed_response():
    headers = Message()
    assert ollama_shim._has_managed_protocol(headers) is False
    headers["GenieX-Cache-Protocol"] = "1"
    assert ollama_shim._has_managed_protocol(headers) is False
    headers.replace_header("GenieX-Cache-Protocol", "2")
    assert ollama_shim._has_managed_protocol(headers) is True


def test_npu_shim_closes_response_when_protocol_changes_after_probe(monkeypatch):
    class UpstreamResponse:
        def __init__(self):
            self.headers = Message()
            self.closed = False

        def close(self):
            self.closed = True

    response = UpstreamResponse()
    monkeypatch.setattr(ollama_shim, "UPSTREAM", "http://127.0.0.1:18181")
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: response)
    with pytest.raises(
        ollama_shim.ManagedCacheProtocolMismatch,
        match="managed-cache protocol 2",
    ):
        ollama_shim.post_upstream({}, {}, "managed")
    assert response.closed is True


def test_npu_shim_rejects_unversioned_managed_error_response(monkeypatch):
    upstream_error = managed_probe_error(protocol=None)
    monkeypatch.setattr(ollama_shim, "UPSTREAM", "http://127.0.0.1:18181")

    def reject(*_args, **_kwargs):
        raise upstream_error

    monkeypatch.setattr("urllib.request.urlopen", reject)
    with pytest.raises(
        ollama_shim.ManagedCacheProtocolMismatch,
        match="managed-cache protocol 2",
    ):
        ollama_shim.post_upstream({}, {}, "managed")
    assert upstream_error.fp.closed is True


class RelayResponse(list):
    def __init__(self, *chunks):
        super().__init__(chunks)
        self.closed = False

    def close(self):
        self.closed = True


class RelayHandler:
    def __init__(self):
        self.lines = []
        self.headers = []
        self.close_connection = False

    def send_response(self, status):
        assert status == 200

    def send_header(self, name, value):
        self.headers.append((name, value))

    def end_headers(self):
        pass

    def _line(self, value):
        self.lines.append(value)


def sse(value):
    return ("data: " + json.dumps(value) + "\n").encode()


def test_npu_shim_binds_metadata_to_terminal_chunk_and_preserves_stop_reason(
    monkeypatch,
):
    monkeypatch.setattr(ollama_shim, "MANAGED_CACHE_SUPPORTED", True)
    response = RelayResponse(
        sse({
            "choices": [{"delta": {"content": "partial"}, "finish_reason": None}],
        }),
        sse({
            "choices": [{"delta": {}, "finish_reason": "length"}],
            "geniex_cache": metadata(
                "cold", "first_request", reusable=False
            ),
        }),
        sse({"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 1}}),
        b"data: [DONE]\n",
    )
    handler = RelayHandler()
    ollama_shim.Handler._relay_stream(handler, response, "fixture", "managed")
    assert handler.lines[-1]["done_reason"] == "length"
    assert handler.lines[-1]["geniex_cache"]["reusable"] is False
    assert "error" not in handler.lines[-1]
    assert response.closed is True


def test_npu_shim_rejects_cache_metadata_before_terminal_chunk(monkeypatch):
    monkeypatch.setattr(ollama_shim, "MANAGED_CACHE_SUPPORTED", True)
    response = RelayResponse(
        sse({
            "choices": [{"delta": {"content": "partial"}, "finish_reason": None}],
            "geniex_cache": metadata("cold", "first_request"),
        }),
        sse({"choices": [{"delta": {}, "finish_reason": "stop"}]}),
        b"data: [DONE]\n",
    )
    handler = RelayHandler()
    ollama_shim.Handler._relay_stream(handler, response, "fixture", "managed")
    assert "terminal streaming chunk" in handler.lines[-1]["error"]
    assert "geniex_cache" not in handler.lines[-1]
    assert ollama_shim.MANAGED_CACHE_SUPPORTED is False


def test_cache_diagnostics_never_contain_messages():
    coordinator = CacheCoordinator()
    coordinator.request("driver")
    coordinator.commit(metadata("cold", "first_request"), "driver")
    serialized = json.dumps(coordinator.diagnostics())
    assert "prompt" not in serialized
    assert "message" not in serialized
    assert "content" not in serialized


class ManagedDelegate:
    cache_mode = CACHE_MANAGED

    def __init__(self):
        self.requests = []

    def chat(self, _messages, **kwargs):
        request = dict(kwargs["cache_request"])
        self.requests.append((kwargs.get("role") or "driver", request))
        count = len([role for role, _ in self.requests
                     if role == (kwargs.get("role") or "driver")])
        if count == 1:
            result = metadata("cold", "first_request", "a")
        else:
            result = metadata("reused", "exact_extension", "b")
        kwargs["cache_observer"](result)
        return "{}"


def test_attempt_wrapper_uses_separate_role_lineages_and_parents():
    delegate = ManagedDelegate()
    attempt = _AttemptLLM(delegate, 5)
    attempt.chat([], role="driver")
    attempt.chat([], role="router")
    attempt.chat([], role="driver")

    (_, first_driver), (_, router), (_, second_driver) = delegate.requests
    assert first_driver["session"] == second_driver["session"]
    assert first_driver["session"] != router["session"]
    assert first_driver["parent"] == router["parent"] == ""
    assert second_driver["parent"] == "sha256:" + "a" * 64
    assert [event["status"] for event in attempt.cache_diagnostics()["events"]] \
        == ["cold", "cold", "reused"]


def test_attempt_wrapper_off_mode_preserves_the_old_delegate_call_shape():
    class OldDelegate:
        cache_mode = CACHE_OFF

        def chat(self, messages):
            assert messages == []
            return "ok"

    assert _AttemptLLM(OldDelegate(), 1).chat([]) == "ok"


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


class FakeStreamResponse(FakeResponse):
    def __init__(self, lines):
        super().__init__({})
        self.lines = list(lines)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def iter_lines(self, decode_unicode=False):
        assert decode_unicode is True
        return iter(self.lines)


def test_llm_forwards_managed_state_and_observes_final_metadata(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "requests.get",
        lambda *_args, **_kwargs: FakeResponse({
            "version": "npu-shim",
            "brickkv": {"modes": ["managed"], "protocol": 2},
        }),
    )

    def post(url, json=None, timeout=None):
        calls.append((url, json, timeout))
        return FakeResponse({
            "message": {"content": "answer"},
            "prompt_eval_count": 3,
            "eval_count": 1,
            "geniex_cache": metadata("cold", "first_request"),
        })

    monkeypatch.setattr("requests.post", post)
    coordinator = CacheCoordinator()
    request = coordinator.request("driver")
    llm = LLM("fixture", cache_mode="managed")
    answer = llm.chat(
        [{"role": "user", "content": "hello"}],
        cache_request=request,
        cache_observer=lambda value: coordinator.commit(value, "driver"),
    )
    assert answer == "answer"
    assert calls[0][1]["brick_cache"] == request
    assert coordinator.request("driver")["parent"].startswith("sha256:")


def test_llm_retry_reuses_the_same_uncommitted_parent(monkeypatch):
    monkeypatch.setattr(
        "requests.get",
        lambda *_args, **_kwargs: FakeResponse({
            "version": "npu-shim",
            "brickkv": {"modes": ["managed"], "protocol": 2},
        }),
    )
    calls = []

    def post(_url, json=None, **_kwargs):
        calls.append(dict(json["brick_cache"]))
        if len(calls) == 1:
            raise requests.ConnectionError("synthetic disconnect")
        return FakeResponse({
            "message": {"content": "answer"},
            "geniex_cache": metadata("reset", "parent_mismatch"),
        })

    monkeypatch.setattr("requests.post", post)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    coordinator = CacheCoordinator()
    initial = coordinator.request("driver")
    llm = LLM("fixture", cache_mode="managed", retries=1)
    assert llm.chat(
        [{"role": "user", "content": "hello"}],
        cache_request=initial,
        cache_observer=lambda value: coordinator.commit(value, "driver"),
    ) == "answer"
    assert calls == [initial, initial]
    assert coordinator.request("driver")["parent"] == "sha256:" + "a" * 64


def test_stream_without_final_metadata_does_not_advance_parent(monkeypatch):
    monkeypatch.setattr(
        "requests.get",
        lambda *_args, **_kwargs: FakeResponse({
            "version": "npu-shim",
            "brickkv": {"modes": ["managed"], "protocol": 2},
        }),
    )
    response = FakeStreamResponse([
        json.dumps({"message": {"content": "partial"}, "done": False}),
        json.dumps({"message": {"content": ""}, "done": True}),
    ])
    monkeypatch.setattr("requests.post", lambda *_args, **_kwargs: response)
    coordinator = CacheCoordinator()
    initial = coordinator.request("driver")
    events = []
    llm = LLM("fixture", cache_mode="managed",
              stream_hook=lambda kind, value: events.append((kind, value)))
    with pytest.raises(ManagedCacheProtocolError, match="missing final"):
        llm.chat(
            [{"role": "user", "content": "hello"}],
            cache_request=initial,
            cache_observer=lambda value: coordinator.commit(value, "driver"),
        )
    assert coordinator.request("driver") == initial
    assert llm.calls == 0
    assert [kind for kind, _value in events] == ["start", "token"]


def test_llm_fails_when_managed_metadata_is_missing(monkeypatch):
    monkeypatch.setattr(
        "requests.get",
        lambda *_args, **_kwargs: FakeResponse({
            "version": "npu-shim",
            "brickkv": {"modes": ["managed"], "protocol": 2},
        }),
    )
    monkeypatch.setattr(
        "requests.post",
        lambda *_args, **_kwargs: FakeResponse({
            "message": {"content": "answer"},
        }),
    )
    llm = LLM("fixture", cache_mode="managed")
    with pytest.raises(ManagedCacheProtocolError, match="missing final"):
        llm.chat([], cache_request=CacheCoordinator().request("driver"))
    assert llm.calls == 0


def test_llm_refuses_an_unpatched_local_backend(monkeypatch):
    monkeypatch.setattr(
        "requests.get",
        lambda *_args, **_kwargs: FakeResponse({"version": "npu-shim"}),
    )
    llm = LLM("fixture", cache_mode="managed")
    with pytest.raises(ManagedCacheProtocolError, match="does not support"):
        llm.chat([], cache_request=CacheCoordinator().request("driver"))


@pytest.mark.parametrize("modes", ["unmanaged", {"managed": True}, 1, None])
def test_llm_rejects_wrong_shaped_capability_modes(monkeypatch, modes):
    monkeypatch.setattr(
        "requests.get",
        lambda *_args, **_kwargs: FakeResponse({
            "version": "npu-shim", "brickkv": {"modes": modes, "protocol": 2}
        }),
    )
    llm = LLM("fixture", cache_mode="managed")
    with pytest.raises(ManagedCacheProtocolError, match="prove BrickKV"):
        llm.chat([], cache_request=CacheCoordinator().request("driver"))


@pytest.mark.parametrize("protocol", (None, 1, "2", True, 3))
def test_llm_rejects_wrong_managed_protocol_version(monkeypatch, protocol):
    monkeypatch.setattr(
        "requests.get",
        lambda *_args, **_kwargs: FakeResponse({
            "version": "npu-shim",
            "brickkv": {"modes": ["managed"], "protocol": protocol},
        }),
    )
    llm = LLM("fixture", cache_mode="managed")
    with pytest.raises(ManagedCacheProtocolError, match="managed protocol 2"):
        llm.chat([], cache_request=CacheCoordinator().request("driver"))


def test_llm_rejects_invalid_metadata_before_observer_or_logging(monkeypatch):
    monkeypatch.setattr(
        "requests.get",
        lambda *_args, **_kwargs: FakeResponse({
            "version": "npu-shim",
            "brickkv": {"modes": ["managed"], "protocol": 2},
        }),
    )
    invalid = dict(metadata("cold", "first_request"), unexpected="content")
    monkeypatch.setattr(
        "requests.post",
        lambda *_args, **_kwargs: FakeResponse({
            "message": {"content": "answer"}, "geniex_cache": invalid
        }),
    )
    observed = []
    llm = LLM("fixture", cache_mode="managed")
    with pytest.raises(ManagedCacheProtocolError, match="exactly"):
        llm.chat(
            [],
            cache_request=CacheCoordinator().request("driver"),
            cache_observer=observed.append,
        )
    assert observed == []
    assert llm.last_cache is None
    assert llm.calls == 0


def test_llm_off_mode_ignores_unsolicited_cache_metadata(monkeypatch):
    monkeypatch.setattr(
        "requests.post",
        lambda *_args, **_kwargs: FakeResponse({
            "message": {"content": "answer"},
            "geniex_cache": {"content": "must-not-be-retained"},
        }),
    )
    llm = LLM("fixture", cache_mode="off")
    assert llm.chat([]) == "answer"
    assert llm.last_cache is None


def test_legacy_mode_requires_an_explicit_synthetic_runner_gate():
    with pytest.raises(CacheConfigurationError, match="synthetic BrickKV"):
        LLM("fixture", cache_mode=CACHE_LEGACY_TEST)
    allowed = LLM(
        "fixture", cache_mode=CACHE_LEGACY_TEST, allow_legacy_test=True
    )
    assert allowed.cache_mode == CACHE_LEGACY_TEST


def test_npu_shim_maps_only_reviewed_cache_headers(monkeypatch):
    monkeypatch.setattr(ollama_shim, "MANAGED_CACHE_SUPPORTED", True)
    request = CacheCoordinator().request("driver")
    headers, mode = ollama_shim.cache_headers({"brick_cache": request})
    assert mode == "managed"
    assert headers == {"GenieX-Cache-Session": request["session"]}

    request["parent"] = "sha256:" + "c" * 64
    headers, _ = ollama_shim.cache_headers({"brick_cache": request})
    assert headers["GenieX-Cache-Parent"] == request["parent"]
    assert "GenieX-KeepCache" not in headers


def test_npu_shim_legacy_mode_is_environment_gated(monkeypatch):
    monkeypatch.delenv("BRICKKV_ALLOW_LEGACY_TEST", raising=False)
    with pytest.raises(ValueError, match="disabled"):
        ollama_shim.cache_headers({"brick_cache": {"mode": "legacy-test"}})
    monkeypatch.setenv("BRICKKV_ALLOW_LEGACY_TEST", "1")
    assert ollama_shim.cache_headers(
        {"brick_cache": {"mode": "legacy-test"}}
    ) == ({"GenieX-KeepCache": "true"}, "legacy-test")


def test_npu_translation_never_places_cache_control_in_the_model_body(monkeypatch):
    monkeypatch.setattr(ollama_shim, "MODEL", "fixture")
    request = dict({
        "model": "alias",
        "messages": [],
        "brick_cache": CacheCoordinator().request("driver"),
    })
    assert "cache" not in json.dumps(ollama_shim.to_openai(request)).lower()
