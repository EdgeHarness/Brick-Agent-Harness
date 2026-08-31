import json
import io
import os
from pathlib import Path
from types import SimpleNamespace
import tarfile

import pytest

from perf.brickkv.gpu_prefix_study import (
    Server,
    UnixHTTPConnection,
    UnixHTTPTransport,
    parse_prometheus,
    parse_sse,
    private_socket_endpoint,
)
from perf.brickkv.source_bundle import (
    source_bundle_digest,
    verify_git_revision,
)
from perf.brickkv.safe_extract import extract_stream


def test_prometheus_parser_prefers_current_prefix_counters():
    text = """
# TYPE vllm:prefix_cache_queries_total counter
vllm:prefix_cache_queries_total{model_name="m"} 100
vllm:prefix_cache_hits_total{model_name="m"} 40
vllm:gpu_prefix_cache_queries_total{model_name="m"} 200
vllm:gpu_prefix_cache_hits_total{model_name="m"} 10
"""
    assert parse_prometheus(text) == {"queries": 100.0, "hits": 40.0}


def test_prometheus_parser_accepts_deprecated_counter_names():
    text = """
vllm:gpu_prefix_cache_queries_total 20
vllm:gpu_prefix_cache_hits_total 5
"""
    assert parse_prometheus(text) == {"queries": 20.0, "hits": 5.0}


def test_sse_parser_returns_text_only_to_the_in_memory_caller(monkeypatch):
    ticks = iter((1_100_000, 1_300_000))
    monkeypatch.setattr("time.perf_counter_ns", lambda: next(ticks))
    chunks = [
        b'data: {"choices":[{"delta":{"content":"safe"}}]}',
        b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
        b'data: {"choices":[],"usage":{"prompt_tokens":9,"completion_tokens":1}}',
        b"data: [DONE]",
    ]
    result = parse_sse(chunks, 1_000_000)
    assert result == {
        "text": "safe",
        "ttft_us": 100,
        "wall_us": 300,
        "prompt_tokens": 9,
        "generated_tokens": 1,
        "cancelled": False,
    }


def test_sse_parser_marks_decode_disconnect_after_first_token(monkeypatch):
    ticks = iter((2_000_000, 2_100_000))
    monkeypatch.setattr("time.perf_counter_ns", lambda: next(ticks))
    line = b'data: ' + json.dumps({
        "choices": [{"delta": {"content": "partial"}}]
    }).encode()
    result = parse_sse([line], 1_900_000, cancel_after_first=True)
    assert result["cancelled"] is True
    assert result["text"] == "partial"


def test_sse_parser_surfaces_server_errors():
    with pytest.raises(RuntimeError, match="vLLM stream error"):
        parse_sse([b'data: {"error":"failed"}'], 0)


def test_sse_parser_rejects_premature_eof_after_content(monkeypatch):
    ticks = iter((1_100_000, 1_300_000))
    monkeypatch.setattr("time.perf_counter_ns", lambda: next(ticks))
    with pytest.raises(RuntimeError, match=r"finish, usage, and \[DONE\]"):
        parse_sse([
            b'data: {"choices":[{"delta":{"content":"partial"}}]}'
        ], 1_000_000)


def test_prometheus_parser_rejects_partial_or_nonfinite_pairs():
    with pytest.raises(RuntimeError, match="only part"):
        parse_prometheus("vllm:prefix_cache_queries_total 1\n")
    with pytest.raises(RuntimeError, match="finite"):
        parse_prometheus(
            "vllm:prefix_cache_queries_total NaN\n"
            "vllm:prefix_cache_hits_total 0\n"
        )


def test_unix_transport_rejects_every_unreviewed_target():
    transport = UnixHTTPTransport(Path("/tmp/vllm.sock"), "test-key")
    for method, path in (
        ("GET", "http://127.0.0.1/metrics"),
        ("GET", "/invocations"),
        ("POST", "/metrics"),
        ("DELETE", "/v1/models"),
    ):
        with pytest.raises(ValueError, match="unreviewed"):
            transport.open(method, path, 1)


def test_unix_transport_checks_endpoint_before_opening(monkeypatch):
    opened = []

    def reject_dead_process():
        raise RuntimeError("vLLM process is not alive")

    monkeypatch.setattr(
        "perf.brickkv.gpu_prefix_study.UnixHTTPConnection",
        lambda *_args, **_kwargs: opened.append(True),
    )
    transport = UnixHTTPTransport(
        Path("/private/vllm.sock"), "test-key", reject_dead_process
    )
    with pytest.raises(RuntimeError, match="not alive"):
        transport.open("GET", "/metrics", 1)
    assert opened == []


def test_unix_transport_preserves_allowed_request_and_owns_auth(monkeypatch):
    calls = []

    class FakeResponse:
        status = 200

    class FakeConnection:
        def __init__(self, socket_path, timeout):
            calls.append(("init", socket_path, timeout))

        def request(self, method, path, body=None, headers=None):
            calls.append(("request", method, path, body, headers))

        def getresponse(self):
            return FakeResponse()

        def close(self):
            calls.append(("close",))

    monkeypatch.setattr(
        "perf.brickkv.gpu_prefix_study.UnixHTTPConnection",
        FakeConnection,
    )
    transport = UnixHTTPTransport(Path("/private/vllm.sock"), "real-key")
    connection, response = transport.open(
        "GET",
        "/metrics",
        4,
        headers={"Authorization": "Bearer replaced"},
    )
    assert response.status == 200
    assert calls[1] == (
        "request",
        "GET",
        "/metrics",
        None,
        {"Authorization": "Bearer real-key"},
    )
    connection.close()
    assert calls[-1] == ("close",)


def test_unix_connection_uses_only_the_selected_socket(monkeypatch):
    calls = []
    unix_family = object()

    class FakeSocket:
        def settimeout(self, timeout):
            calls.append(("timeout", timeout))

        def connect(self, path):
            calls.append(("connect", path))

        def close(self):
            calls.append(("close",))

    def fake_socket(family, kind):
        calls.append(("socket", family, kind))
        return FakeSocket()

    monkeypatch.setattr(
        "perf.brickkv.gpu_prefix_study.socket.socket", fake_socket
    )
    monkeypatch.setattr(
        "perf.brickkv.gpu_prefix_study.socket.AF_UNIX",
        unix_family,
        raising=False,
    )
    connection = UnixHTTPConnection(Path("/private/vllm.sock"), 3.5)
    connection.connect()
    assert calls == [
        ("socket", unix_family, __import__("socket").SOCK_STREAM),
        ("timeout", 3.5),
        ("connect", os.fspath(Path("/private/vllm.sock"))),
    ]


def test_vllm_command_has_private_uds_and_no_tcp_flags(tmp_path):
    args = SimpleNamespace(
        model=tmp_path / "model",
        served_model="brickkv-test",
        context=8192,
        gpu_memory_utilization=0.9,
        mode="on",
    )
    server = Server(args, tmp_path / "server.log")
    server.socket_path = Path("/private/vllm.sock")
    command = server._command()
    assert command[command.index("--uds") + 1] == str(server.socket_path)
    assert "--host" not in command
    assert "--port" not in command
    assert "--enable-prefix-caching" in command
    assert server.api_key not in command


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission fixture")
def test_private_socket_endpoint_is_owned_and_mode_0700():
    directory, endpoint = private_socket_endpoint()
    try:
        assert endpoint.parent == directory
        assert not endpoint.exists()
        assert directory.stat().st_uid == os.geteuid()
        assert directory.stat().st_mode & 0o777 == 0o700
    finally:
        directory.rmdir()


def test_gpu_source_bundle_binds_the_executed_files():
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    first = source_bundle_digest(root, "a" * 40)
    second = source_bundle_digest(root, "b" * 40)
    assert __import__("re").fullmatch(r"sha256:[0-9a-f]{64}", first)
    assert first != second


def test_source_bundle_git_verification_rejects_dirty_runner(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()
    runner = repository / "runner.py"
    runner.write_text("print('safe')\n", encoding="utf-8")
    for command in (
        ("git", "init"),
        ("git", "config", "user.email", "brickkv@example.com"),
        ("git", "config", "user.name", "BrickKV Test"),
        ("git", "add", "runner.py"),
        ("git", "commit", "-m", "fixture"),
    ):
        __import__("subprocess").run(
            command, cwd=repository, check=True, capture_output=True
        )
    revision = __import__("subprocess").run(
        ("git", "rev-parse", "HEAD"), cwd=repository, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    verify_git_revision(repository, revision, ("runner.py",))
    runner.write_text("print('changed')\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="differ"):
        verify_git_revision(repository, revision, ("runner.py",))


def _tar_bytes(entries):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        for name, kind, content in entries:
            item = tarfile.TarInfo(name)
            if kind == "file":
                item.size = len(content)
                archive.addfile(item, io.BytesIO(content))
            elif kind == "symlink":
                item.type = tarfile.SYMTYPE
                item.linkname = content.decode()
                archive.addfile(item)
    output.seek(0)
    return output


def test_safe_model_extract_accepts_only_regular_tree(tmp_path):
    stream = _tar_bytes([
        ("model/config.json", "file", b"{}"),
        ("model/weights.bin", "file", b"weights"),
    ])
    destination = tmp_path / "model"
    extract_stream(stream, destination)
    assert (destination / "model" / "weights.bin").read_bytes() == b"weights"


@pytest.mark.parametrize("name,kind,content", [
    ("../escape", "file", b"bad"),
    ("model/link", "symlink", b"../../escape"),
])
def test_safe_model_extract_rejects_traversal_and_links(
    tmp_path, name, kind, content
):
    stream = _tar_bytes([
        ("model/config.json", "file", b"{}"),
        (name, kind, content),
    ])
    with pytest.raises(RuntimeError, match="unsafe|link"):
        extract_stream(stream, tmp_path / "model")
