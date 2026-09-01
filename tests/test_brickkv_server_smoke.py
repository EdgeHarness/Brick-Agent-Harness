import json
import os
from pathlib import Path
import socket
import sys

import pytest

import perf.brickkv.geniex_managed_smoke as smoke
from perf.brickkv.geniex_managed_smoke import (
    WindowsServerBinding,
    artifact_manifest,
    loopback_target,
    parse_args,
    resolve_bound_model_artifact,
    response_record,
    validate_cache_metadata,
)


def response(status="cold", reason="first_request"):
    return {
        "geniex_cache": {
            "mode": "managed",
            "status": status,
            "revision": "sha256:" + "a" * 64,
            "reason": reason,
            "reusable": True,
        },
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": "synthetic answer"},
        }],
        "usage": {"prompt_tokens": 12, "completion_tokens": 3},
    }


def runtime_files(tmp_path: Path) -> list[Path]:
    files = []
    for name in ("geniex.dll", "geniex_core.dll", "geniex_plugin.dll"):
        path = tmp_path / name
        path.write_bytes(("runtime:" + name).encode())
        files.append(path)
    return files


@pytest.mark.parametrize(
    "origin",
    (
        "https://127.0.0.1:18181",
        "http://localhost:18181",
        "http://127.0.0.1",
        "http://user@127.0.0.1:18181",
        "http://127.0.0.1:18181/v1",
        "http://127.0.0.1:18181?next=remote",
    ),
)
def test_smoke_runner_rejects_non_exact_loopback_origins(origin):
    with pytest.raises(ValueError):
        loopback_target(origin)


def test_smoke_runner_accepts_explicit_ipv4_loopback_port():
    assert loopback_target("http://127.0.0.1:18182") == ("127.0.0.1", 18182)


def test_smoke_schema_is_versioned_for_reusable_state():
    assert smoke.SCHEMA == "brickkv.geniex-managed-smoke/2"


def test_smoke_cache_record_requires_exact_decision_and_shape():
    clean = response()["geniex_cache"]
    assert validate_cache_metadata(clean, "cold")["reason"] == "first_request"
    wrong = dict(clean, reason="exact_extension")
    with pytest.raises(RuntimeError, match="expected"):
        validate_cache_metadata(wrong, "cold")
    extra = dict(clean, provider_debug="unsafe")
    with pytest.raises(RuntimeError, match="shape"):
        validate_cache_metadata(extra, "cold")
    non_reusable = dict(clean, reusable=False)
    assert validate_cache_metadata(
        non_reusable, "cold", expected_reusable=False
    )["reusable"] is False


def test_smoke_response_rejects_finish_reason_mismatch():
    invalid = response()
    invalid["choices"][0]["finish_reason"] = "length"
    with pytest.raises(RuntimeError, match="finish_reason"):
        response_record(invalid, "cold")


def test_smoke_response_record_hashes_output_without_retaining_it():
    record, content = response_record(response(), "cold")
    assert content == "synthetic answer"
    assert record["output_sha256"].startswith("sha256:")
    assert record["output_bytes"] == len(content.encode())
    serialized = json.dumps(record)
    assert content not in serialized
    for forbidden in ("messages", "content", "prompt", "generated_text"):
        assert f'"{forbidden}"' not in serialized


def test_smoke_response_rejects_invalid_token_accounting():
    invalid = response()
    invalid["usage"]["prompt_tokens"] = 0
    with pytest.raises(RuntimeError, match="prompt_tokens"):
        response_record(invalid, "cold")


def test_smoke_artifact_manifest_binds_tree_paths_and_bytes(tmp_path):
    artifact = tmp_path / "model"
    artifact.mkdir()
    (artifact / "config.json").write_text("one", encoding="utf-8")
    (artifact / "weights.bin").write_bytes(b"weights")
    first = artifact_manifest(artifact)
    assert first["kind"] == "directory"
    assert first["files"] == 2
    assert first["bytes"] == len(b"oneweights")
    assert first["sha256"].startswith("sha256:")
    (artifact / "config.json").write_text("two", encoding="utf-8")
    assert artifact_manifest(artifact)["sha256"] != first["sha256"]


def test_smoke_model_artifact_must_match_data_catalogue_path(tmp_path):
    data = tmp_path / "data"
    expected = data / "models" / "qualcomm" / "qwen3_0_6b"
    different = data / "models" / "qualcomm" / "different"
    expected.mkdir(parents=True)
    different.mkdir()
    assert resolve_bound_model_artifact(
        data, "qualcomm/qwen3_0_6b", expected
    ) == (data.resolve(), expected.resolve())
    with pytest.raises(RuntimeError, match="selected model directory"):
        resolve_bound_model_artifact(
            data, "qualcomm/qwen3_0_6b", different
        )


@pytest.mark.parametrize("model", ("../escape", "provider/../escape", "provider/"))
def test_smoke_model_catalogue_rejects_ambiguous_components(tmp_path, model):
    data = tmp_path / "data"
    data.mkdir()
    with pytest.raises((ValueError, FileNotFoundError)):
        resolve_bound_model_artifact(data, model, data)


def test_smoke_server_binding_requires_exact_process_image_and_listener(
    tmp_path, monkeypatch
):
    executable = tmp_path / "geniex.exe"
    executable.write_bytes(b"verified executable")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    runtimes = runtime_files(tmp_path)
    monkeypatch.setattr(smoke, "_windows_process_image", lambda pid: executable)
    monkeypatch.setattr(
        smoke, "_windows_listener_pids", lambda host, port: {321}
    )
    monkeypatch.setattr(smoke, "_windows_process_creation_time", lambda pid: 100)
    monkeypatch.setattr(
        smoke,
        "_windows_process_argv",
        lambda pid: [
            str(executable),
            "--data-dir", str(data_dir),
            "serve",
            "--host", "127.0.0.1:18182",
            "--compute", "npu",
        ],
    )
    monkeypatch.setattr(smoke, "_windows_process_modules", lambda pid: tuple(runtimes))
    binding = WindowsServerBinding(
        "127.0.0.1", 18182, 321, executable, data_dir, runtimes
    )
    assert binding.executable_sha256.startswith("sha256:")
    assert binding.checks == 1
    binding.verify()
    assert binding.checks == 2
    binding.verify_runtime()
    assert binding.runtime_checks == 1


def test_smoke_server_binding_rejects_listener_owned_by_another_process(
    tmp_path, monkeypatch
):
    executable = tmp_path / "geniex.exe"
    executable.write_bytes(b"verified executable")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    runtimes = runtime_files(tmp_path)
    monkeypatch.setattr(smoke, "_windows_process_image", lambda pid: executable)
    monkeypatch.setattr(
        smoke, "_windows_listener_pids", lambda host, port: {999}
    )
    monkeypatch.setattr(smoke, "_windows_process_creation_time", lambda pid: 100)
    monkeypatch.setattr(
        smoke,
        "_windows_process_argv",
        lambda pid: [
            str(executable),
            "--data-dir", str(data_dir),
            "serve",
            "--host", "127.0.0.1:18182",
            "--compute", "npu",
        ],
    )
    with pytest.raises(RuntimeError, match="ownership changed"):
        WindowsServerBinding(
            "127.0.0.1", 18182, 321, executable, data_dir, runtimes
        )


def test_smoke_server_binding_rejects_different_model_data_directory(
    tmp_path, monkeypatch
):
    executable = tmp_path / "geniex.exe"
    executable.write_bytes(b"verified executable")
    intended = tmp_path / "intended"
    different = tmp_path / "different"
    intended.mkdir()
    different.mkdir()
    runtimes = runtime_files(tmp_path)
    monkeypatch.setattr(smoke, "_windows_process_image", lambda pid: executable)
    monkeypatch.setattr(
        smoke, "_windows_listener_pids", lambda host, port: {321}
    )
    monkeypatch.setattr(smoke, "_windows_process_creation_time", lambda pid: 100)
    monkeypatch.setattr(
        smoke,
        "_windows_process_argv",
        lambda pid: [
            str(executable),
            "--data-dir", str(different),
            "serve",
            "--host", "127.0.0.1:18182",
            "--compute", "npu",
        ],
    )
    with pytest.raises(RuntimeError, match="different data directory"):
        WindowsServerBinding(
            "127.0.0.1", 18182, 321, executable, intended, runtimes
        )


def test_smoke_server_binding_rejects_pid_reuse(tmp_path, monkeypatch):
    executable = tmp_path / "geniex.exe"
    executable.write_bytes(b"verified executable")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    runtimes = runtime_files(tmp_path)
    monkeypatch.setattr(smoke, "_windows_process_image", lambda pid: executable)
    monkeypatch.setattr(smoke, "_windows_listener_pids", lambda host, port: {321})
    monkeypatch.setattr(
        smoke,
        "_windows_process_argv",
        lambda pid: [
            str(executable),
            "--data-dir", str(data_dir),
            "serve",
            "--host", "127.0.0.1:18182",
            "--compute", "npu",
        ],
    )
    times = iter((100, 100, 101))
    monkeypatch.setattr(
        smoke, "_windows_process_creation_time", lambda pid: next(times)
    )
    binding = WindowsServerBinding(
        "127.0.0.1", 18182, 321, executable, data_dir, runtimes
    )
    with pytest.raises(RuntimeError, match="PID was reused"):
        binding.verify()


def _parse_args(tmp_path: Path, *extra: str):
    data_dir = tmp_path / "data"
    model = data_dir / "models" / "qualcomm" / "qwen3_0_6b"
    model.mkdir(parents=True)
    cli = tmp_path / "geniex.exe"
    runtimes = runtime_files(tmp_path)
    (model / "weights.bin").write_bytes(b"model")
    cli.write_bytes(b"cli")
    arguments = [
        "--execute",
        "--server", "http://127.0.0.1:18182",
        "--server-pid", "321",
        "--model", "qualcomm/qwen3_0_6b",
        "--model-role", "smoke",
        "--model-artifact", str(model),
        "--geniex-cli", str(cli),
        "--geniex-data-dir", str(data_dir),
        "--output", str(tmp_path / "evidence.json"),
        "--source-revision", "a" * 40,
        "--geniex-revision", "b" * 40,
        "--runtime-version", "2.45.0.260326",
        "--hardware-label", "Snapdragon X Elite X1E-78-100",
    ]
    for runtime in runtimes:
        arguments.extend(("--runtime-artifact", str(runtime)))
    arguments.extend(extra)
    return parse_args(arguments)


@pytest.mark.parametrize("value", ("nan", "inf", "301", "0"))
def test_smoke_runner_rejects_unbounded_timeout(tmp_path, value):
    with pytest.raises(SystemExit):
        _parse_args(tmp_path, "--timeout", value)


@pytest.mark.skipif(os.name != "nt", reason="Windows TCP ownership API")
def test_windows_listener_pid_attestation_uses_kernel_table():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        assert smoke._windows_listener_pids("127.0.0.1", port) == {os.getpid()}


@pytest.mark.skipif(os.name != "nt", reason="Windows process image API")
def test_windows_process_image_attestation_uses_kernel_handle():
    actual = smoke._windows_process_image(os.getpid())
    assert os.path.normcase(str(actual)) == os.path.normcase(
        str(Path(sys.executable).resolve(strict=True))
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows process timing API")
def test_windows_process_creation_attestation_uses_kernel_handle():
    assert smoke._windows_process_creation_time(os.getpid()) > 0


@pytest.mark.skipif(os.name != "nt", reason="Windows process command-line API")
def test_windows_process_argv_attestation_uses_cim_and_system_parser():
    arguments = smoke._windows_process_argv(os.getpid())
    assert os.path.normcase(str(Path(arguments[0]).resolve(strict=True))) == os.path.normcase(
        str(Path(sys.executable).resolve(strict=True))
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows loaded-module API")
def test_windows_module_attestation_uses_toolhelp_snapshot():
    modules = smoke._windows_process_modules(os.getpid())
    expected = os.path.normcase(str(Path(sys.executable).resolve(strict=True)))
    assert expected in {os.path.normcase(str(path)) for path in modules}
