import copy
import errno
import json
import os
from pathlib import Path
import struct
import subprocess

import pytest

from bench import f0_probe, f0_windows


class FakeDiskUsage:
    """Disk space the mock harness controls, rather than the host's.

    Without this the offline mocks reached for the real filesystem for one
    number, so five tests about verifier logic failed on a nearly full disk
    and passed everywhere else. They would fail the same way on Windows.
    """

    free = 512 * 1024 * 1024 * 1024

    def __init__(self, _path):
        pass


def tool_response(name, arguments, model="qwen3.5:4b-q4_K_M"):
    return {
        "model": model,
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": arguments,
                    },
                }
            ],
        },
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": 20,
        "prompt_eval_duration": 1_000_000_000,
        "eval_count": 10,
        "eval_duration": 1_000_000_000,
        "total_duration": 2_000_000_000,
        "load_duration": 0,
    }


class FakeMonitor:
    def __init__(self, pid):
        self.pid = pid

    def start(self):
        return self

    def stop(self):
        return {
            "schema_version": "brick.f0.process-memory/1",
            "error": None,
            "samples": [
                {
                    "pids": [self.pid, self.pid + 1],
                    "processes": [
                        {
                            "pid": self.pid,
                            "parent_pid": 0,
                            "image": "ollama.exe",
                            "private_commit_bytes": 1,
                            "working_set_bytes": 1,
                        },
                        {
                            "pid": self.pid + 1,
                            "parent_pid": self.pid,
                            "image": "ollama-runner.exe",
                            "path": r"C:\fake\ollama-runner.exe",
                            "sha256": "b" * 64,
                            "pe_machine": {"value": 0xAA64, "name": "arm64"},
                            "identity_error": None,
                            "private_commit_bytes": 1,
                            "working_set_bytes": 1,
                        },
                    ],
                    "private_commit_bytes": 2,
                    "working_set_bytes": 2,
                }
            ],
            "peak_private_commit_bytes": 4 * 1024 ** 3,
            "peak_working_set_bytes": 3 * 1024 ** 3,
            "peak_process_count": 2,
        }


class FakeClient:
    DIGESTS = {
        "qwen3.5:2b-q4_K_M": "2" * 64,
        "qwen3.5:4b-q4_K_M": "4" * 64,
        "qwen3.5:9b-q4_K_M": "9" * 64,
    }

    def __init__(
        self,
        endpoint=f0_probe.OLLAMA_URL,
        timeout=600,
        fail_model=None,
    ):
        self.endpoint = endpoint
        self.timeout = timeout
        self.fail_model = fail_model
        self.requests = []
        self.loaded_model = None

    def get(self, path):
        if path == "/api/version":
            return {"version": "0.test"}
        if path == "/api/ps":
            if self.loaded_model is None:
                return {"models": []}
            return {
                "models": [
                    {
                        "name": self.loaded_model,
                        "model": self.loaded_model,
                        "digest": self.DIGESTS[self.loaded_model],
                        "context_length": 8192,
                        "size": 100,
                        "size_vram": 0,
                        "details": {
                            "quantization_level": "Q4_K_M"
                        },
                    }
                ]
            }
        if path == "/api/tags":
            return {
                "models": [
                    {
                        "name": model,
                        "model": model,
                        "digest": digest,
                        "size": 100,
                        "details": {
                            "quantization_level": "Q4_K_M",
                            "parameter_size": model.split(":")[1].split("-")[0],
                        },
                    }
                    for model, digest in self.DIGESTS.items()
                ]
            }
        raise AssertionError(path)

    def post(self, path, payload):
        if path == "/api/show":
            return {
                "template": "{{ .Messages }}",
                "details": {
                    "family": "qwen35",
                    "quantization_level": "Q4_K_M",
                },
                "capabilities": ["completion", "tools"],
            }
        raise AssertionError((path, payload))

    def unload(self, model):
        if self.loaded_model == model:
            self.loaded_model = None
        return {"done": True, "done_reason": "unload"}

    def pull(self, model, log_path):
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text(
            '{"status":"success"}\n', encoding="utf-8"
        )
        return {"status": "success"}

    def chat(self, payload):
        self.requests.append(copy.deepcopy(payload))
        model = payload["model"]
        self.loaded_model = model
        tools = {
            item["function"]["name"] for item in payload.get("tools", [])
        }
        if not tools:
            return {
                "model": model,
                "message": {"role": "assistant", "content": "word " * 160},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 20,
                "prompt_eval_duration": 1_000_000_000,
                "eval_count": 160,
                "eval_duration": 10_000_000_000,
                "total_duration": 11_000_000_000,
                "load_duration": 0,
            }
        if model == self.fail_model:
            return {"message": {"role": "assistant", "content": "no call"}}
        if "record_values" in tools:
            return tool_response(
                "record_values",
                {"label": "delta-7", "count": 3, "enabled": True},
                model,
            )
        if "lookup_shape" in tools:
            return tool_response(
                "lookup_shape", {"item_id": "unit-204"}, model
            )
        if any(
            message.get("role") == "tool"
            for message in payload["messages"]
        ):
            return tool_response(
                "submit_nonce", {"nonce": "F0-6E19"}, model
            )
        return tool_response("read_nonce", {"key": "alpha"}, model)

    def rejected_post(self, path, payload):
        """Mirror the measured Ollama 0.32.5 option contract.

        Unknown option names are ignored and succeed; a real option name given
        an invalid value type is rejected with a key-specific 500. That
        contrast is what proves per-key recognition.
        """
        assert path == "/api/chat"
        protocol = f0_probe.load_protocol()
        contract = protocol["option_contract"]
        sentinel = protocol["unknown_option_sentinel"]
        invalid = protocol["recognition_invalid_value"]
        options = payload["options"]
        if sentinel in options:
            return {
                "status_code": 200,
                "body": {
                    "model": payload["model"],
                    "done": True,
                    "message": {"role": "assistant", "content": "ok"},
                },
            }
        for key in sorted(contract):
            if options.get(key) == invalid:
                expected = (
                    "float32" if contract[key] == "float" else "integer"
                )
                return {
                    "status_code": 500,
                    "body": {
                        "error": f'option "{key}" must be of type {expected}'
                    },
                }
        return {
            "status_code": 200,
            "body": {
                "model": payload["model"],
                "done": True,
                "message": {"role": "assistant", "content": "ok"},
            },
        }

    def _legacy_rejected_post(self, path, payload):
        unknown = "brick_f0_unknown_option"
        assert unknown in payload["options"]
        return {
            "status_code": 400,
            "body": {"error": f"invalid option provided: {unknown}"},
        }


def fake_environment(_root, _minimum_memory, _minimum_disk):
    return {
        "schema_version": "brick.f0.environment/1",
        "passed": True,
        "failures": [],
        "windows_build": 26100,
        "machine": "ARM64",
        "physical_memory_bytes": 32 * 1024 ** 3,
        "volume": {
            "root": "C:\\",
            "filesystem": "NTFS",
            "drive_type": 3,
            "free_bytes": 100 * 1024 ** 3,
        },
        "python": {
            "sha256": "1" * 64,
            "pe_machine": {
                "value": f0_windows.ARM64_PE_MACHINE,
                "name": "arm64",
            },
        },
        "ollama_listener": {
            "pid": 123,
            "path": "ollama.exe",
            "sha256": "2" * 64,
            "pe_machine": {
                "value": f0_windows.ARM64_PE_MACHINE,
                "name": "arm64",
            },
        },
        "onedrive_contained": False,
        "hardware": {
            "computer": {
                "manufacturer": "Lenovo",
                "model": "Yoga",
            },
            "cpu": "Snapdragon X Elite",
        },
    }


def fake_repository(_root):
    return {
        "schema_version": "brick.f0.repository/1",
        "commit": "a" * 40,
        "clean": True,
        "behavior_tree_sha256": "b" * 64,
    }


def fake_listener():
    return fake_environment(None, None, None)["ollama_listener"]


def fake_storage(root, cycles, crash_cycles, held_handle_cycles):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    (root / "probe.txt").write_text("storage", encoding="utf-8")
    return {
        "schema_version": "brick.f0.storage-summary/1",
        "passed": True,
        "cycles": cycles,
        "forced_exits": crash_cycles,
        "held_handle_cycles": held_handle_cycles,
        "committed": cycles,
        "logical_commits": cycles,
        "abandoned": 0,
        "physical_candidates": cycles,
        "duplicate_valid_candidates": {},
        "invalid_committed": 0,
        "directory_renames": 0,
        "records": [
            {"kind": "mock", "state": "committed"}
            for _ in range(cycles)
        ],
    }


def test_frozen_protocol_is_valid_and_primary_is_first():
    protocol = f0_probe.load_protocol()
    assert protocol["primary_model"] == "qwen3.5:4b-q4_K_M"
    assert protocol["storage_cycles"] == 200
    assert protocol["storage_process_exits"] == 50
    ordered = sorted(
        protocol["models"],
        key=lambda item: 0 if item["role"] == "primary" else 1,
    )
    assert ordered[0]["tag"] == protocol["primary_model"]


def test_protocol_rejects_duplicate_models_and_inconsistent_storage():
    protocol = f0_probe.load_protocol()
    duplicate = copy.deepcopy(protocol)
    duplicate["models"][1]["tag"] = duplicate["models"][0]["tag"]
    with pytest.raises(f0_probe.F0Error, match="model matrix"):
        f0_probe.validate_protocol(duplicate)

    inconsistent = copy.deepcopy(protocol)
    inconsistent["storage_process_exits"] = 195
    inconsistent["storage_held_handle_cycles"] = 10
    with pytest.raises(f0_probe.F0Error, match="exceed"):
        f0_probe.validate_protocol(inconsistent)

    weakened = copy.deepcopy(protocol)
    weakened["sampling"]["temperature"] = 0.0
    with pytest.raises(f0_probe.F0Error, match="sampling differs"):
        f0_probe.validate_protocol(weakened)


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://127.0.0.1:11434",
        "http://example.com:11434",
        "http://127.0.0.1:9999",
        "http://user@127.0.0.1:11434",
        "http://127.0.0.1:11434/api",
    ],
)
def test_f0_client_refuses_noncanonical_endpoint(endpoint):
    with pytest.raises(f0_probe.F0Error, match="loopback"):
        f0_probe.OllamaProbeClient(endpoint=endpoint)


def test_native_tool_conformance_uses_exact_sampling_and_roundtrip(tmp_path):
    protocol = f0_probe.load_protocol()
    client = FakeClient()
    summary = f0_probe.run_conformance(
        client,
        protocol,
        protocol["primary_model"],
        "4" * 64,
        tmp_path,
    )
    assert summary["passed"]
    assert len(client.requests) == 4
    for request in client.requests:
        assert request["stream"] is False
        assert request["think"] is False
        assert request["options"]["num_ctx"] == 8192
        assert request["options"]["temperature"] == 1.0
        assert request["options"]["presence_penalty"] == 2.0
        assert type(request["options"]["seed"]) is int
    final_messages = client.requests[-1]["messages"]
    assert final_messages[-1] == {
        "role": "tool",
        "tool_name": "read_nonce",
        "content": '{"nonce":"F0-6E19"}',
    }


def test_content_only_or_extra_native_call_fails_exact_conformance():
    assert not f0_probe._exact_call(
        {"message": {"role": "assistant", "content": "record_values(...)"}},
        "record_values",
        {"label": "delta-7", "count": 3, "enabled": True},
    )
    response = tool_response("record_values", {"label": "delta-7"})
    response["message"]["tool_calls"].append(
        tool_response("record_values", {"label": "extra"})["message"][
            "tool_calls"
        ][0]
    )
    assert not f0_probe._exact_call(
        response, "record_values", {"label": "delta-7"}
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda response: response.update({"model": "wrong"}),
        lambda response: response.update({"done": False}),
        lambda response: response["message"].update({"role": "tool"}),
        lambda response: response["message"].update(
            {"thinking": "visible reasoning"}
        ),
    ],
)
def test_tool_response_envelope_rejects_wrong_or_nonterminal_data(
    mutation,
):
    model = "qwen3.5:4b-q4_K_M"
    response = tool_response("record_values", {}, model)
    mutation(response)
    assert not f0_probe._tool_response_envelope_valid(response, model)


def test_runtime_uses_server_eval_duration_and_median(tmp_path):
    protocol = f0_probe.load_protocol()
    summary = f0_probe.run_runtime(
        FakeClient(),
        protocol,
        protocol["primary_model"],
        "4" * 64,
        tmp_path,
    )
    assert summary["passed"]
    assert summary["valid_samples"] == 5
    assert summary["median_eval_tps"] == pytest.approx(16.0)


def test_full_probe_is_offline_mockable_and_report_verifies(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        f0_probe.shutil,
        "disk_usage",
        lambda _path: shutil_result(100 * 1024 ** 3),
    )
    clients = []

    def client_factory(**kwargs):
        client = FakeClient(**kwargs)
        clients.append(client)
        return client

    run_dir, summary = f0_probe.run_probe(
        tmp_path,
        disk_probe=FakeDiskUsage,
        client_factory=client_factory,
        environment_probe=fake_environment,
        repository_probe=fake_repository,
        storage_runner=fake_storage,
        monitor_factory=FakeMonitor,
        processor_probe=lambda _path: "NAME ID SIZE PROCESSOR\nfake",
        listener_probe=fake_listener,
        run_id="canonical",
        pull=True,
    )
    assert summary["overall_status"] == "pass"
    assert summary["primary"]["tag"] == "qwen3.5:4b-q4_K_M"
    assert len(summary["descriptive_models"]) == 2
    assert all(item["passed"] for item in summary["descriptive_models"])
    assert f0_probe.verify_report(run_dir) == summary
    assert clients and clients[0].requests


def shutil_result(free):
    return type(
        "DiskUsage",
        (),
        {"total": free * 2, "used": free, "free": free},
    )()


def test_descriptive_model_failure_does_not_invalidate_primary(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        f0_probe.shutil,
        "disk_usage",
        lambda _path: shutil_result(100 * 1024 ** 3),
    )

    def factory(**kwargs):
        return FakeClient(
            fail_model="qwen3.5:2b-q4_K_M", **kwargs
        )

    _, summary = f0_probe.run_probe(
        tmp_path,
        disk_probe=FakeDiskUsage,
        client_factory=factory,
        environment_probe=fake_environment,
        repository_probe=fake_repository,
        storage_runner=fake_storage,
        monitor_factory=FakeMonitor,
        processor_probe=lambda _path: "NAME ID SIZE PROCESSOR\nfake",
        listener_probe=fake_listener,
        run_id="secondary-failure",
        pull=True,
    )
    assert summary["overall_status"] == "pass"
    assert summary["primary"]["passed"]
    failures = [
        item
        for item in summary["descriptive_models"]
        if not item["passed"]
    ]
    assert [item["tag"] for item in failures] == [
        "qwen3.5:2b-q4_K_M"
    ]


def test_report_tamper_is_detected(monkeypatch, tmp_path):
    monkeypatch.setattr(
        f0_probe.shutil,
        "disk_usage",
        lambda _path: shutil_result(100 * 1024 ** 3),
    )
    run_dir, _ = f0_probe.run_probe(
        tmp_path,
        disk_probe=FakeDiskUsage,
        client_factory=FakeClient,
        environment_probe=fake_environment,
        repository_probe=fake_repository,
        storage_runner=fake_storage,
        monitor_factory=FakeMonitor,
        processor_probe=lambda _path: "NAME ID SIZE PROCESSOR\nfake",
        listener_probe=fake_listener,
        run_id="tamper",
        pull=True,
    )
    with (run_dir / "summary.json").open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(f0_probe.F0Error, match="size changed"):
        f0_probe.verify_report(run_dir)


def test_repository_probe_distinguishes_clean_and_dirty_worktrees(tmp_path):
    commands = (
        ["git", "init", "--quiet"],
        ["git", "config", "user.name", "F0 Test"],
        ["git", "config", "user.email", "f0@example.invalid"],
    )
    for command in commands:
        subprocess.run(command, cwd=tmp_path, check=True)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "fixture"],
        cwd=tmp_path,
        check=True,
    )
    assert f0_probe._git_environment(tmp_path)["clean"] is True
    tracked.write_text("dirty\n", encoding="utf-8")
    assert f0_probe._git_environment(tmp_path)["clean"] is False


def test_no_pull_report_is_ineligible(monkeypatch, tmp_path):
    monkeypatch.setattr(
        f0_probe.shutil,
        "disk_usage",
        lambda _path: shutil_result(100 * 1024 ** 3),
    )
    _, summary = f0_probe.run_probe(
        tmp_path,
        disk_probe=FakeDiskUsage,
        client_factory=FakeClient,
        environment_probe=fake_environment,
        repository_probe=fake_repository,
        storage_runner=fake_storage,
        monitor_factory=FakeMonitor,
        processor_probe=lambda _path: "NAME ID SIZE PROCESSOR\nfake",
        listener_probe=fake_listener,
        run_id="no-pull",
    )
    assert summary["overall_status"] == "fail"
    assert "model pull was not requested" in summary["failures"]


def test_report_rejects_unsafe_run_id_and_manifest_symlink(
    monkeypatch, tmp_path
):
    with pytest.raises(f0_probe.F0Error, match="safe path"):
        f0_probe.run_probe(tmp_path, run_id="../escape")

    monkeypatch.setattr(
        f0_probe.shutil,
        "disk_usage",
        lambda _path: shutil_result(100 * 1024 ** 3),
    )
    run_dir, _ = f0_probe.run_probe(
        tmp_path,
        disk_probe=FakeDiskUsage,
        client_factory=FakeClient,
        environment_probe=fake_environment,
        repository_probe=fake_repository,
        storage_runner=fake_storage,
        monitor_factory=FakeMonitor,
        processor_probe=lambda _path: "NAME ID SIZE PROCESSOR\nfake",
        listener_probe=fake_listener,
        run_id="symlink-check",
        pull=True,
    )
    prepared = run_dir / "PREPARED.json"
    replacement = run_dir / "manifest-copy.json"
    replacement.write_bytes(prepared.read_bytes())
    prepared.unlink()
    try:
        prepared.symlink_to(replacement.name)
    except (NotImplementedError, OSError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(f0_probe.F0Error, match="absent or irregular"):
        f0_probe.verify_report(run_dir)


def test_fabricated_pass_summary_cannot_satisfy_verifier(tmp_path):
    run_dir = tmp_path / "fabricated"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "schema_version": f0_probe.SUMMARY_SCHEMA,
                "overall_status": "pass",
            }
        ),
        encoding="utf-8",
    )
    f0_probe._publish_report(run_dir)
    with pytest.raises(f0_probe.F0Error, match="protocol.json"):
        f0_probe.verify_report(run_dir)


def test_report_publish_rereads_prepared_manifest(tmp_path, monkeypatch):
    run_dir = tmp_path / "reread"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        '{"schema_version":"brick.f0.summary/1",'
        '"overall_status":"fail"}',
        encoding="utf-8",
    )
    real_load = f0_probe._load_report_manifest
    calls = {"count": 0}

    def observed(path):
        calls["count"] += 1
        return real_load(path)

    monkeypatch.setattr(f0_probe, "_load_report_manifest", observed)
    f0_probe._publish_report(run_dir)
    assert calls["count"] >= 2
    # Publication mechanics only. Semantic verification of a failed report is
    # covered separately against a complete bundle, so this skeletal fixture
    # asserts just the marker and manifest integrity.
    assert (run_dir / "COMMITTED").is_file()
    f0_probe._validate_report_manifest(run_dir, real_load(run_dir))


def test_corrupt_prepared_report_never_gets_commit_marker(
    tmp_path, monkeypatch
):
    run_dir = tmp_path / "corrupt-before-commit"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        '{"schema_version":"brick.f0.summary/1",'
        '"overall_status":"fail"}',
        encoding="utf-8",
    )
    real_write = f0_probe._write_json

    def corrupting_write(path, value, exclusive=True):
        real_write(path, value, exclusive=exclusive)
        if Path(path).name == "PREPARED.json":
            with Path(path).open("ab") as handle:
                handle.write(b"corrupt")

    monkeypatch.setattr(f0_probe, "_write_json", corrupting_write)
    with pytest.raises(f0_probe.F0Error, match="unreadable"):
        f0_probe._publish_report(run_dir)
    assert not (run_dir / "COMMITTED").exists()


def test_report_publish_retries_sharing_violation(
    tmp_path, monkeypatch
):
    run_dir = tmp_path / "retry-report"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        '{"schema_version":"brick.f0.summary/1",'
        '"overall_status":"fail"}',
        encoding="utf-8",
    )
    real_load = f0_probe._load_report_manifest
    calls = {"count": 0}

    def flaky(path):
        calls["count"] += 1
        if calls["count"] < 3:
            raise OSError(errno.EACCES, "sharing violation")
        return real_load(path)

    monkeypatch.setattr(f0_probe, "_load_report_manifest", flaky)
    f0_probe._publish_report(run_dir)
    assert calls["count"] >= 4
    assert (run_dir / "COMMITTED").is_file()
    f0_probe._validate_report_manifest(run_dir, real_load(run_dir))


def test_late_probe_exception_can_never_leave_overall_pass(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        f0_probe.shutil,
        "disk_usage",
        lambda _path: shutil_result(100 * 1024 ** 3),
    )

    class LateFailureClient(FakeClient):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.tag_calls = 0

        def get(self, path):
            if path == "/api/tags":
                self.tag_calls += 1
                if self.tag_calls == 8:
                    raise RuntimeError("injected final-tags failure")
            return super().get(path)

    _, summary = f0_probe.run_probe(
        tmp_path,
        disk_probe=FakeDiskUsage,
        client_factory=LateFailureClient,
        environment_probe=fake_environment,
        repository_probe=fake_repository,
        storage_runner=fake_storage,
        monitor_factory=FakeMonitor,
        processor_probe=lambda _path: "NAME ID SIZE PROCESSOR\nfake",
        listener_probe=fake_listener,
        run_id="late-failure",
        pull=True,
    )
    assert summary["overall_status"] == "fail"
    assert any(
        "injected final-tags failure" in failure
        for failure in summary["failures"]
    )
    assert any(
        code["domain"] == "instrument"
        and code["code"] == "run_exception"
        and "injected final-tags failure" in code["detail"]
        for code in summary["failure_codes"]
    )


def test_early_environment_failure_is_committed_and_verifiable(tmp_path):
    def failed_environment(_root, _minimum_memory, _minimum_disk):
        return {
            "schema_version": "brick.f0.environment/1",
            "passed": False,
            "failures": ["AC power is not connected"],
        }

    def should_not_run(*_args, **_kwargs):
        raise AssertionError("later F0 stage ran after environment failure")

    run_dir, summary = f0_probe.run_probe(
        tmp_path,
        disk_probe=FakeDiskUsage,
        client_factory=should_not_run,
        environment_probe=failed_environment,
        repository_probe=fake_repository,
        storage_runner=should_not_run,
        run_id="environment-failure",
        pull=True,
    )
    assert summary["overall_status"] == "fail"
    assert summary["primary"] is None
    assert summary["descriptive_models"] == []
    assert "environment" in summary["failure_domains"]
    assert f0_probe.verify_report(run_dir) == summary


def test_live_unmeasured_process_tree_member_is_fatal(monkeypatch):
    monkeypatch.setattr(
        f0_windows,
        "_process_entries",
        lambda: {
            101: {"parent_pid": 0, "image": "ollama.exe"},
            202: {
                "parent_pid": 101,
                "image": "ollama-runner.exe",
            },
        },
    )
    monkeypatch.setattr(
        f0_windows,
        "_process_memory",
        lambda pid: (
            {
                "private_commit_bytes": 1,
                "working_set_bytes": 1,
            }
            if pid == 101
            else None
        ),
    )
    with pytest.raises(
        f0_windows.WindowsProbeError, match="descendants"
    ):
        f0_windows.sample_process_tree(101)


def test_metadata_rejects_wrong_family_size_and_tool_advertisement():
    summary = f0_probe._metadata_summary(
        "qwen3.5:4b-q4_K_M",
        {
            "digest": "4" * 64,
            "size": 100,
            "details": {"parameter_size": "7B"},
        },
        {
            "template": "{{ .Messages }}",
            "details": {
                "family": "llama",
                "quantization_level": "Q4_K_M",
            },
            "capabilities": ["completion"],
        },
    )
    assert not summary["passed"]
    assert any("family" in failure for failure in summary["failures"])
    assert any("parameter size" in failure for failure in summary["failures"])
    assert any("native tool" in failure for failure in summary["failures"])


def test_pe_machine_reads_arm64_coff_header(tmp_path):
    executable = tmp_path / "python.exe"
    payload = bytearray(256)
    payload[:2] = b"MZ"
    payload[0x3C:0x40] = struct.pack("<I", 128)
    payload[128:132] = b"PE\0\0"
    payload[132:134] = struct.pack("<H", f0_windows.ARM64_PE_MACHINE)
    executable.write_bytes(payload)
    assert f0_windows.pe_machine(executable) == {
        "value": f0_windows.ARM64_PE_MACHINE,
        "name": "arm64",
    }


def test_non_windows_environment_fails_before_live_work(tmp_path):
    if f0_windows.os.name == "nt":
        pytest.skip("non-Windows behavior")
    result = f0_windows.collect_environment(
        tmp_path, 1, 1
    )
    assert not result["passed"]
    assert result["failures"] == ["native Windows is required"]


@pytest.mark.skipif(os.name != "nt", reason="Windows ctypes smoke test")
def test_windows_ctypes_smoke_current_process_and_fixed_volume(tmp_path):
    assert f0_windows._physical_memory_bytes() > 0
    volume_root, filesystem = f0_windows._filesystem_name(tmp_path)
    assert volume_root
    assert filesystem
    assert f0_windows._drive_type(volume_root) > 0
    entries = f0_windows._process_entries()
    assert os.getpid() in entries
    assert entries[os.getpid()]["image"]
    assert f0_windows._process_memory(os.getpid())[
        "private_commit_bytes"
    ] > 0
    sample = f0_windows.sample_process_tree(os.getpid())
    assert os.getpid() in sample["pids"]
    assert sample["processes"]


def passing_mock_run(tmp_path, run_id):
    """Produce one committed, verified passing report from the offline mocks."""
    run_dir, summary = f0_probe.run_probe(
        tmp_path,
        disk_probe=FakeDiskUsage,
        client_factory=FakeClient,
        environment_probe=fake_environment,
        repository_probe=fake_repository,
        storage_runner=fake_storage,
        monitor_factory=FakeMonitor,
        processor_probe=lambda _path: "NAME ID SIZE PROCESSOR\nfake",
        listener_probe=fake_listener,
        run_id=run_id,
        pull=True,
    )
    assert summary["overall_status"] == "pass"
    return run_dir, summary


def model_summary_path(run_dir, summary):
    slug = f0_probe._safe_model_slug(summary["primary"]["tag"])
    return run_dir / "models" / slug / "summary.json"


def rewrite_model_summary(run_dir, summary, mutate):
    """Tamper the on-disk model summary the verifier actually reads."""
    path = model_summary_path(run_dir, summary)
    record = json.loads(path.read_text(encoding="utf-8"))
    mutate(record)
    path.write_text(json.dumps(record), encoding="utf-8")


def test_passing_verifier_rejects_a_non_arm64_inference_runner(tmp_path):
    """Verification must recompute runner architecture, not trust the summary.

    `_verify_passing_report` is called directly so the semantic assertion is
    exercised rather than the manifest hash check that would fire first.
    """
    run_dir, summary = passing_mock_run(tmp_path, "attestation-tamper")

    def mutate(record):
        runner = record["memory"]["runner_attestation"]["runners"][0]
        runner["native_arm64"] = False
        runner["pe_machine"] = {
            "value": f0_windows.AMD64_PE_MACHINE,
            "name": "amd64",
        }

    rewrite_model_summary(run_dir, summary, mutate)
    with pytest.raises(f0_probe.F0Error, match="runner attestation failed"):
        f0_probe._verify_passing_report(run_dir, copy.deepcopy(summary))


def test_passing_verifier_rejects_an_unrecognized_option(tmp_path):
    """A model cannot be eligible if a frozen option name went unrecognized."""
    run_dir, summary = passing_mock_run(tmp_path, "recognition-tamper")
    slug = f0_probe._safe_model_slug(summary["primary"]["tag"])
    path = run_dir / "models" / slug / "option-recognition" / "summary.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["unrecognized_options"] = ["presence_penalty"]
    record["options"]["presence_penalty"]["rejected"] = False
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(f0_probe.F0Error, match="option recognition"):
        f0_probe._verify_passing_report(run_dir, copy.deepcopy(summary))


def test_passing_verifier_recomputes_recognition_from_raw_response(tmp_path):
    run_dir, summary = passing_mock_run(tmp_path, "recognition-raw-tamper")
    slug = f0_probe._safe_model_slug(summary["primary"]["tag"])
    path = (
        run_dir
        / "models"
        / slug
        / "option-recognition"
        / "option-top_p-response.json"
    )
    response = json.loads(path.read_text(encoding="utf-8"))
    response["body"] = {"error": "generic request failure"}
    path.write_text(json.dumps(response), encoding="utf-8")
    with pytest.raises(
        f0_probe.F0Error, match="raw evidence|option recognition"
    ):
        f0_probe._verify_passing_report(run_dir, copy.deepcopy(summary))


def test_stronger_verifier_accepts_pre_audit_v2_derived_fields(tmp_path):
    """Raw evidence, not newly added cached fields, is authoritative."""
    run_dir, summary = passing_mock_run(tmp_path, "pre-audit-v2")
    verified_summary = copy.deepcopy(summary)
    rewritten = {}
    for model in [summary["primary"], *summary["descriptive_models"]]:
        slug = f0_probe._safe_model_slug(model["tag"])
        recognition_path = (
            run_dir / "models" / slug / "option-recognition" / "summary.json"
        )
        recognition = json.loads(
            recognition_path.read_text(encoding="utf-8")
        )
        for field in (
            "rejected_options",
            "accepted_options",
            "options_with_http_error",
            "options_typed_in_error",
        ):
            recognition.pop(field)
        for item in recognition["options"].values():
            item.pop("http_error")
            item.pop("recognized")
        recognition_path.write_text(
            json.dumps(recognition), encoding="utf-8"
        )

        model_path = run_dir / "models" / slug / "summary.json"
        model_record = json.loads(model_path.read_text(encoding="utf-8"))
        attestation = model_record["memory"]["runner_attestation"]
        attestation.pop("runner_set_stable")
        attestation.pop("runner_sample_count")
        for runner in attestation["runners"]:
            runner.pop("parent_pid")
        model_path.write_text(json.dumps(model_record), encoding="utf-8")
        rewritten[model["tag"]] = model_record

    verified_summary["primary"] = rewritten[summary["primary"]["tag"]]
    verified_summary["descriptive_models"] = [
        rewritten[model["tag"]]
        for model in summary["descriptive_models"]
    ]
    f0_probe._verify_passing_report(run_dir, verified_summary)


def test_passing_verifier_rejects_a_missing_runner_attestation(tmp_path):
    """A v1-shaped model summary must not satisfy the v2 verifier."""
    run_dir, summary = passing_mock_run(tmp_path, "attestation-absent")
    rewrite_model_summary(
        run_dir, summary, lambda record: record["memory"].pop(
            "runner_attestation"
        )
    )
    with pytest.raises(f0_probe.F0Error, match="runner attestation failed"):
        f0_probe._verify_passing_report(run_dir, copy.deepcopy(summary))


class ExhaustedDisk:
    """A host with almost nothing left, which the gate must still refuse."""

    free = 1024

    def __init__(self, _path):
        pass


def test_the_disk_floor_still_fails_a_host_that_is_actually_full(tmp_path):
    """Making the probe injectable must not have made the gate advisory.

    The seam exists so the offline mocks stop reaching for the real
    filesystem, not so the check can be waived. Lowering a floor to make a
    failing run pass is exactly what CLAUDE.md forbids, so this asserts the
    floor is still enforced through the new seam.
    """
    _, summary = f0_probe.run_probe(
        tmp_path,
        disk_probe=ExhaustedDisk,
        client_factory=FakeClient,
        environment_probe=fake_environment,
        repository_probe=fake_repository,
        storage_runner=fake_storage,
        monitor_factory=FakeMonitor,
        processor_probe=lambda _path: "NAME ID SIZE PROCESSOR\nfake",
        listener_probe=fake_listener,
        run_id="disk-floor",
        pull=True,
    )
    assert summary["overall_status"] == "fail"


def test_the_default_disk_probe_is_the_real_one():
    """Nothing in production gets the fake. The gate still measures a disk."""
    import inspect
    import shutil as real_shutil

    default = inspect.signature(f0_probe.run_probe).parameters["disk_probe"].default
    assert default is real_shutil.disk_usage
