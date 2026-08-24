"""Offline tests for the Ollama-API backend shims (phase 4).

Only the pure translation layer is testable without an upstream server; the
HTTP loop is exercised on the lab machine. What matters here is that the
option mapping the harness depends on survives both shims identically.
"""
import importlib

npu_shim = importlib.import_module("npu.ollama_shim")
lcp_shim = importlib.import_module("llamacpp.ollama_shim")

REQ = {
    "model": "llama3.1:8b",
    "messages": [{"role": "user", "content": "hi"}],
    "stream": False,
    "format": "json",
    "options": {"temperature": 0.0, "seed": 42, "num_ctx": 8192,
                "num_predict": 700},
}


def test_both_shims_map_the_options_the_harness_sends():
    for shim in (npu_shim, lcp_shim):
        body = shim.to_openai(dict(REQ))
        assert body["temperature"] == 0.0
        assert body["seed"] == 42
        assert body["max_tokens"] == 700
        assert body["response_format"] == {"type": "json_object"}
        assert body["stream"] is False
        # num_ctx is deliberately NOT forwarded: context is fixed when the
        # upstream loads the model, and both docstrings say so.
        assert "num_ctx" not in str(body)


def test_streaming_requests_ask_for_the_usage_tail():
    for shim in (npu_shim, lcp_shim):
        body = shim.to_openai({**REQ, "stream": True})
        assert body["stream"] is True
        assert body["stream_options"] == {"include_usage": True}


def test_npu_shim_replaces_the_model_name_with_the_served_one(monkeypatch):
    monkeypatch.setattr(npu_shim, "MODEL", "ai-hub-models/Llama-v3.1-8B-Instruct")
    body = npu_shim.to_openai(dict(REQ))
    assert body["model"] == "ai-hub-models/Llama-v3.1-8B-Instruct"


def test_npu_normalise_tolerates_bare_hosts_and_v1_suffix():
    assert npu_shim._normalise("127.0.0.1:18181") == "http://127.0.0.1:18181"
    assert npu_shim._normalise("http://h:1/v1") == "http://h:1"
    assert npu_shim._normalise("  ") is None
