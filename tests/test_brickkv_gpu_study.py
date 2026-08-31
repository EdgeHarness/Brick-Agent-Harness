import json
import io
import tarfile

import pytest

from perf.brickkv.gpu_prefix_study import parse_prometheus, parse_sse
from perf.brickkv.source_bundle import source_bundle_digest
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


def test_gpu_source_bundle_binds_the_executed_files():
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    assert __import__("re").fullmatch(
        r"sha256:[0-9a-f]{64}", source_bundle_digest(root)
    )


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
