import io
import json
import os

import pytest

import perf.brickkv.geniex_server_replay as replay


REVISION = "sha256:" + "a" * 64


class Lines:
    def __init__(self, *chunks):
        self._stream = io.BytesIO(b"".join(chunks))

    def readline(self, limit=-1):
        return self._stream.readline(limit)


def event(value):
    if value == "[DONE]":
        return b"data: [DONE]\n\n"
    return ("data: " + json.dumps(value, separators=(",", ":")) + "\n\n").encode()


def valid_stream(*, cache=True, finish_reason="stop", reusable=True):
    chunks = [
        event({
            "object": "chat.completion.chunk",
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant", "content": "synthetic"},
                "finish_reason": None,
            }],
        }),
        event({
            "object": "chat.completion.chunk",
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant", "content": " answer"},
                "finish_reason": None,
            }],
        }),
        event({
            "object": "chat.completion.chunk",
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": finish_reason,
            }],
            **({
                "geniex_cache": {
                    "mode": "managed",
                    "status": "cold",
                    "revision": REVISION,
                    "reason": "first_request",
                    "reusable": reusable,
                }
            } if cache else {}),
        }),
        event({
            "object": "chat.completion.chunk",
            "choices": [],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 3,
                "total_tokens": 15,
            },
        }),
        event("[DONE]"),
    ]
    return chunks


def clocks():
    values = iter((1_001_000, 1_002_000, 1_003_000))
    return lambda: next(values)


@pytest.mark.parametrize(
    "mode,trace,step,expected",
    (
        ("managed", "append_only", 0, ("cold", "first_request")),
        ("managed", "append_only", 1, ("reused", "exact_extension")),
        ("managed", "planning_removed", 2, ("reset", "branch")),
        ("managed", "verifier_detour", 1, ("reset", "session_switch")),
        ("managed", "cancellation_decode", 2, ("reset", "parent_mismatch")),
        ("reset", "append_only", 1, ("reset", "reset_each_call")),
        ("legacy-test", "append_only", 1, ("legacy-test", "raw_keep_cache")),
        ("managed", "cancellation_decode", 1, ("aborted", "client_disconnect")),
    ),
)
def test_expected_server_cache_decisions(mode, trace, step, expected):
    assert replay.expected_cache_decision(mode, trace, step) == expected


def test_non_reusable_parent_forces_cold_exact_extension():
    assert replay.expected_cache_decision(
        "managed", "append_only", 1, prior_reusable=False
    ) == ("reset", "previous_not_reusable")


def test_replay_schema_is_versioned_for_reusable_state():
    assert replay.SCHEMA == "brickkv.server-replay/2"


def test_consume_managed_sse_records_metrics_without_retaining_output_in_record():
    result = replay.consume_sse(
        Lines(*valid_stream()),
        mode="managed",
        trace="append_only",
        step=0,
        started_ns=1_000_000,
        cancel_after_chunks=0,
        now_ns=clocks(),
    )
    assert result["output"] == "synthetic answer"
    assert result["output_digest"].startswith("sha256:")
    assert result["ttft_us"] == 1
    assert result["decode_stream_us"] == 1
    assert result["wall_us"] == 3
    assert result["prompt_tokens"] == 12
    assert result["generated_tokens"] == 3
    assert result["observed_output_chunks"] == 2
    assert result["cache"] == {
        "status": "cold",
        "reason": "first_request",
        "revision": REVISION,
        "reusable": True,
    }


def test_length_limited_stream_commits_only_non_reusable_logical_revision():
    result = replay.consume_sse(
        Lines(*valid_stream(finish_reason="length", reusable=False)),
        mode="managed",
        trace="append_only",
        step=0,
        started_ns=1_000_000,
        cancel_after_chunks=0,
        now_ns=clocks(),
    )
    assert result["finish_reason"] == "length"
    assert result["cache"] == {
        "status": "cold",
        "reason": "first_request",
        "revision": REVISION,
        "reusable": False,
    }


def test_consume_unmanaged_sse_rejects_cache_metadata():
    with pytest.raises(RuntimeError, match="unmanaged"):
        replay.consume_sse(
            Lines(*valid_stream()),
            mode="reset",
            trace="append_only",
            step=0,
            started_ns=1_000_000,
            cancel_after_chunks=0,
            now_ns=clocks(),
        )


def test_consume_unmanaged_sse_accepts_no_cache_metadata():
    result = replay.consume_sse(
        Lines(*valid_stream(cache=False)),
        mode="legacy-test",
        trace="append_only",
        step=0,
        started_ns=1_000_000,
        cancel_after_chunks=0,
        now_ns=clocks(),
    )
    assert result["cache"]["status"] == "legacy-test"
    assert result["cache"]["revision"] == ""


def test_consume_sse_cancellation_requires_no_terminal_provider_claim():
    result = replay.consume_sse(
        Lines(*valid_stream()),
        mode="managed",
        trace="cancellation_decode",
        step=1,
        started_ns=1_000_000,
        cancel_after_chunks=2,
        now_ns=clocks(),
    )
    assert result["cancelled"] is True
    assert result["generated_tokens"] == 0
    assert result["observed_output_chunks"] == 2
    assert result["cache"] == {
        "status": "aborted",
        "reason": "client_disconnect",
        "revision": "",
        "reusable": False,
    }
    assert "output" not in result


@pytest.mark.parametrize(
    "chunks,match",
    (
        (valid_stream()[:-1], "without \\[DONE\\]"),
        (
            [event({"object": "chat.completion.chunk", "choices": [], "provider": {}})],
            "unreviewed fields",
        ),
        (
            [event({
                "object": "chat.completion.chunk",
                "choices": [{
                    "index": 0,
                    "delta": {"reasoning_content": "hidden"},
                    "finish_reason": None,
                }],
            })],
            "reasoning",
        ),
        (
            [event({
                "object": "chat.completion.chunk",
                "choices": [{
                    "index": 0,
                    "delta": {"content": "x", "secret": "y"},
                    "finish_reason": None,
                }],
            })],
            "delta contained unreviewed fields",
        ),
    ),
)
def test_consume_sse_rejects_incomplete_or_unreviewed_streams(chunks, match):
    with pytest.raises(RuntimeError, match=match):
        replay.consume_sse(
            Lines(*chunks),
            mode="managed",
            trace="append_only",
            step=0,
            started_ns=1_000_000,
            cancel_after_chunks=0,
            now_ns=lambda: 1_001_000,
        )


def test_consume_sse_rejects_inconsistent_usage():
    chunks = valid_stream()
    usage = {
        "object": "chat.completion.chunk",
        "choices": [],
        "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 99},
    }
    chunks[-2] = event(usage)
    with pytest.raises(RuntimeError, match="inconsistent"):
        replay.consume_sse(
            Lines(*chunks),
            mode="managed",
            trace="append_only",
            step=0,
            started_ns=1_000_000,
            cancel_after_chunks=0,
            now_ns=clocks(),
        )


class FakeBinding:
    pid = 123


class FakeClient:
    def __init__(self):
        self.server_binding = FakeBinding()
        self.reset_count = 0
        self.calls = []

    def reset_model(self):
        self.reset_count += 1

    def stream(
        self,
        messages,
        *,
        mode,
        trace,
        step,
        session,
        parent,
        max_tokens,
        cancel_after_chunks=0,
        prior_reusable=True,
    ):
        self.calls.append({
            "messages": [dict(message) for message in messages],
            "mode": mode,
            "trace": trace,
            "step": step,
            "session": session,
            "parent": parent,
            "cancel_after_chunks": cancel_after_chunks,
            "prior_reusable": prior_reusable,
        })
        cancelled = bool(cancel_after_chunks)
        status, reason = replay.expected_cache_decision(
            mode, trace, step, prior_reusable
        )
        result = {
            "cancelled": cancelled,
            "ttft_us": 10,
            "decode_stream_us": 20,
            "wall_us": 40,
            "prompt_tokens": 0 if cancelled else 12,
            "generated_tokens": 0 if cancelled else 3,
            "observed_output_chunks": cancel_after_chunks if cancelled else 2,
            "finish_reason": "client_disconnect" if cancelled else "stop",
            "cache": {
                "status": status,
                "reason": reason,
                "revision": "" if cancelled or mode != "managed" else REVISION,
                "reusable": False if cancelled else mode in {"managed", "legacy-test"},
            },
            "output_digest": REVISION,
            "stream_bytes": 100,
        }
        if not cancelled:
            result["output"] = f"synthetic answer {trace} {step}"
        return result


class FirstTurnTruncatingFakeClient(FakeClient):
    def stream(self, *args, **kwargs):
        result = super().stream(*args, **kwargs)
        if kwargs["mode"] == "managed" and kwargs["step"] == 0:
            result["finish_reason"] = "length"
            result["cache"]["reusable"] = False
        return result


@pytest.mark.parametrize("trace", ("planning_removed", "invalid_deleted"))
def test_run_trace_executes_history_deletion_branch(monkeypatch, trace):
    client = FakeClient()
    monkeypatch.setattr(replay, "windows_process_working_set", lambda pid: 1000)
    records = replay.run_trace(
        client,
        mode="managed",
        trace=trace,
        append_turns=12,
        max_tokens=64,
        cancel_after_chunks=2,
    )
    assert len(records) == 4
    assert records[2]["cache_reason"] == "branch"
    assert len(client.calls[1]["messages"]) == 4
    assert len(client.calls[2]["messages"]) == 4


def test_run_trace_uses_separate_verifier_lineage(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(replay, "windows_process_working_set", lambda pid: 1000)
    records = replay.run_trace(
        client,
        mode="managed",
        trace="verifier_detour",
        append_turns=12,
        max_tokens=64,
        cancel_after_chunks=2,
    )
    assert [record["role"] for record in records] == ["driver", "verifier", "driver"]
    assert client.calls[0]["session"] != client.calls[1]["session"]
    assert client.calls[0]["session"] == client.calls[2]["session"]
    assert [record["cache_reason"] for record in records] == [
        "first_request", "session_switch", "session_switch",
    ]


def test_run_trace_forces_cold_extension_after_truncated_turn(monkeypatch):
    client = FirstTurnTruncatingFakeClient()
    monkeypatch.setattr(replay, "windows_process_working_set", lambda pid: 1000)
    records = replay.run_trace(
        client,
        mode="managed",
        trace="append_only",
        append_turns=2,
        max_tokens=64,
        cancel_after_chunks=2,
    )
    assert records[0]["finish_reason"] == "length"
    assert records[0]["reusable"] is False
    assert records[1]["cache_reason"] == "previous_not_reusable"
    assert client.calls[1]["prior_reusable"] is False


def test_reset_mode_physically_resets_before_every_request(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(replay, "windows_process_working_set", lambda pid: 1000)
    records = replay.run_trace(
        client,
        mode="reset",
        trace="append_only",
        append_turns=3,
        max_tokens=64,
        cancel_after_chunks=2,
    )
    assert len(records) == 3
    assert client.reset_count == 3
    assert {record["cache_reason"] for record in records} == {"reset_each_call"}


@pytest.mark.parametrize("mode,expected_resets", (("managed", 1), ("legacy-test", 2)))
def test_run_trace_recovers_after_cancel_without_retaining_partial_text(
    monkeypatch, mode, expected_resets
):
    client = FakeClient()
    monkeypatch.setattr(replay, "windows_process_working_set", lambda pid: 1000)
    records = replay.run_trace(
        client,
        mode=mode,
        trace="cancellation_decode",
        append_turns=12,
        max_tokens=64,
        cancel_after_chunks=2,
    )
    assert records[1]["cancelled"] is True
    assert records[1]["generated_tokens"] == 0
    assert client.reset_count == expected_resets
    assert "ACK_cancellation_recovered" in client.calls[2]["messages"][-1]["content"]


def test_forbidden_evidence_keys_fail_closed():
    with pytest.raises(RuntimeError, match=r"\$\.records\[0\]\.content"):
        replay._reject_forbidden_evidence_keys({"records": [{"content": "secret"}]})


@pytest.mark.skipif(os.name != "nt", reason="Windows process working-set API")
def test_windows_process_working_set_uses_kernel_process_counters():
    assert replay.windows_process_working_set(os.getpid()) > 0
