import json
import os
import signal
import subprocess
import sys

import pytest

import perf.brickkv.gpu_matrix as gpu_matrix

from perf.brickkv.gpu_prefix_study import (
    ENDPOINT_BINDING,
    PROCESS_CONTAINMENT,
    valid_container_image,
)
from perf.brickkv.gpu_matrix import (
    apc_activity_checks,
    gpu_mode_order,
    gpu_process_metrics,
    paired_apc_improvement,
    summarize,
    validate_gpu_evidence,
)


def expected():
    return {
        "source_revision": "b" * 40,
        "source_bundle_digest": "sha256:" + "1" * 64,
        "model_archive_digest": "sha256:" + "c" * 64,
        "container_digest": "sha256:" + "d" * 64,
        "container_image": (
            "docker://registry.example/brickkv/vllm@sha256:" + "d" * 64
        ),
        "expected_gpu": "NVIDIA L40S",
        "context": 8192,
        "max_tokens": 32,
        "append_turns": 1,
        "served_model_digest": "sha256:" + "e" * 64,
        "gpu_memory_utilization": 0.9,
        "server_timeout": 1200,
        "request_timeout": 600,
    }


def evidence(mode, ttft):
    counts = {
        "append_only": 1,
        "planning_removed": 4,
        "invalid_deleted": 4,
        "context_pruning": 4,
        "verifier_detour": 3,
        "cancellation_decode": 4,
    }
    records = []
    for trace, count in counts.items():
        for step in range(count):
            records.append({
                "mode": mode,
                "trace": trace,
                "step": step,
                "role": (
                    "verifier"
                    if trace == "verifier_detour" and step == 1 else "driver"
                ),
                "ttft_us": ttft,
                "wall_us": ttft * 2,
                "prompt_tokens": 10,
                "generated_tokens": 2,
                "cancelled": trace == "cancellation_decode" and step == 1,
                "prefix_queries": 10,
                "prefix_hits": 5 if mode == "on" else 0,
                "output_digest": "sha256:" + "a" * 64,
            })
    return {
        "schema_version": "brickkv.vllm/1",
        "status": "complete",
        "mode": mode,
        "attestation": {
            "source_revision": "b" * 40,
            "source_bundle_digest": "sha256:" + "1" * 64,
            "model_archive_digest": "sha256:" + "c" * 64,
            "container_digest": "sha256:" + "d" * 64,
            "container_image": (
                "docker://registry.example/brickkv/vllm@sha256:" + "d" * 64
            ),
            "vllm_version": "1.2.3",
            "gpu": {
                "name": "NVIDIA L40S",
                "uuid_hash": "sha256:" + "f" * 64,
                "memory_mb": 46068,
                "driver_version": "600.1",
                "cuda_visible_devices_hash": "sha256:" + "0" * 64,
            },
        },
        "configuration": {
            "context": 8192,
            "max_tokens": 32,
            "append_turns": 1,
            "prefix_caching": mode == "on",
            "prefix_hash_algorithm": "sha256" if mode == "on" else None,
            "served_model_digest": "sha256:" + "e" * 64,
            "endpoint_binding": ENDPOINT_BINDING,
            "process_containment": PROCESS_CONTAINMENT,
            "gpu_memory_utilization": 0.9,
            "server_timeout_s": 1200,
            "request_timeout_s": 600,
            "dtype": "bfloat16",
            "generation_config": "vllm",
            "temperature": 0,
            "seed": 42,
            "workload_version": "brickkv.synthetic-agent-traces/1",
        },
        "records": records,
    }


def test_gpu_order_is_deterministic():
    assert gpu_mode_order(3, "measure", 4) == gpu_mode_order(3, "measure", 4)
    assert set(gpu_mode_order(3, "measure", 4)) == {"off", "on"}


def test_container_reference_is_complete_immutable_and_credential_free():
    digest = "sha256:" + "d" * 64
    assert valid_container_image(
        "docker://registry.example/team/vllm_1.2-test@" + digest, digest
    )
    for value in (
        "docker://user:secret@registry.example/team/vllm@" + digest,
        "docker://registry.example/team/vllm:latest@" + digest,
        "docker://registry.example/team//vllm@" + digest,
        "docker://registry.example/team/../vllm@" + digest,
        "registry.example/team/vllm@" + digest,
        "docker://registry.example/team/vllm@sha256:" + "e" * 64,
    ):
        assert not valid_container_image(value, digest)


def test_gpu_evidence_and_process_reduction():
    payload = evidence("on", 70)
    validate_gpu_evidence(payload, "on", expected())
    metrics = gpu_process_metrics(payload)["append_only"]
    assert metrics["p95_ttft_us"] == 70
    assert metrics["prefix_hit_rate"] == 0.5


def test_gpu_evidence_rejects_schema_drift_and_duplicate_steps():
    payload = evidence("on", 70)
    payload["unexpected"] = True
    with pytest.raises(ValueError, match="root"):
        validate_gpu_evidence(payload, "on", expected())

    payload = evidence("on", 70)
    payload["records"][1]["trace"] = payload["records"][0]["trace"]
    payload["records"][1]["step"] = payload["records"][0]["step"]
    with pytest.raises(ValueError, match="duplicate"):
        validate_gpu_evidence(payload, "on", expected())

    payload = evidence("on", 70)
    payload["configuration"]["endpoint_binding"] = (
        "random_loopback_authenticated_v1"
    )
    with pytest.raises(ValueError, match="configuration"):
        validate_gpu_evidence(payload, "on", expected())

    reordered = evidence("on", 70)
    reordered["records"].reverse()
    with pytest.raises(ValueError, match="canonical trace-step order"):
        validate_gpu_evidence(reordered, "on", expected())

    no_tokens = evidence("on", 70)
    no_tokens["records"][0]["generated_tokens"] = 0
    with pytest.raises(ValueError, match="no measured tokens"):
        validate_gpu_evidence(no_tokens, "on", expected())


def test_gpu_evidence_requires_real_apc_activity():
    inactive = evidence("on", 70)
    for record in inactive["records"]:
        record["prefix_queries"] = 0
        record["prefix_hits"] = 0
    with pytest.raises(ValueError, match="positive prefix-query"):
        validate_gpu_evidence(inactive, "on", expected())

    no_append_hit = evidence("on", 70)
    for record in no_append_hit["records"]:
        if record["trace"] == "append_only":
            record["prefix_hits"] = 0
    with pytest.raises(ValueError, match="reusable-prefix hit"):
        validate_gpu_evidence(no_append_hit, "on", expected())

    contaminated_off = evidence("off", 70)
    contaminated_off["records"][0]["prefix_hits"] = 1
    with pytest.raises(ValueError, match="APC-off"):
        validate_gpu_evidence(contaminated_off, "off", expected())


def test_gpu_summary_and_paired_interval():
    observations = []
    for block, off, on in ((0, 100, 70), (1, 110, 80), (2, 90, 60)):
        for mode, value in (("off", off), ("on", on)):
            observations.append({
                "block": block,
                "mode": mode,
                "metrics": gpu_process_metrics(evidence(mode, value)),
            })
    report = summarize(observations)
    assert report["on"]["append_only"]["process_runs"] == 3
    improvement = paired_apc_improvement(
        observations, "append_only", samples=200, seed=5
    )
    assert improvement["paired_process_blocks"] == 3
    assert improvement["median_improvement_percent"] > 20
    assert all(apc_activity_checks(observations).values())


def test_pidfd_signal_sweep_continues_after_one_failure(monkeypatch):
    attempted = []
    monkeypatch.setattr(gpu_matrix, "linux_descendants", lambda _parent: {101, 102})
    monkeypatch.setattr(
        gpu_matrix.os, "pidfd_open", lambda pid, _flags: pid + 1000,
        raising=False,
    )

    def send(descriptor, _signal_number):
        attempted.append(descriptor)
        if descriptor == 1101:
            raise PermissionError("synthetic denial")

    monkeypatch.setattr(
        gpu_matrix.signal, "pidfd_send_signal", send, raising=False
    )
    monkeypatch.setattr(gpu_matrix.os, "close", lambda _descriptor: None)
    failures = gpu_matrix.signal_linux_descendants(1, signal.SIGTERM)
    assert set(attempted) == {1101, 1102}
    assert len(failures) == 1
    assert isinstance(failures[0], PermissionError)


def _run_linux_containment_probe(
    script, *, timeout, grace, inject_communicate_failure=False
):
    injection = ""
    if inject_communicate_failure:
        injection = (
            "import time\n"
            "time.sleep(0.1)\n"
            "def fail_communicate(*_args, **_kwargs):\n"
            "    raise OSError('synthetic communicate failure')\n"
            "process.communicate = fail_communicate\n"
        )
    probe = (
        "import json, os, subprocess, sys\n"
        "from perf.brickkv.gpu_matrix import ("
        "communicate_contained, enable_linux_child_subreaper, "
        "linux_descendants)\n"
        "enable_linux_child_subreaper()\n"
        f"process = subprocess.Popen([sys.executable, {str(script)!r}], "
        "stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, "
        "stderr=subprocess.PIPE, text=True, start_new_session=True)\n"
        + injection +
        "try:\n"
        f"    result = communicate_contained(process, {timeout!r}, {grace!r}, "
        "supervisor=os.getpid())\n"
        "    payload = {'timed_out': result[2], 'residual_group': result[3], "
        "'residual_descendants': result[4]}\n"
        "except BaseException as exc:\n"
        "    payload = {'error': type(exc).__name__}\n"
        "payload['remaining'] = sorted(linux_descendants(os.getpid()))\n"
        "print(json.dumps(payload))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=os.fspath(__import__("pathlib").Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(sys.platform != "linux", reason="Linux subreaper fixture")
def test_timeout_cleans_descendant_that_escapes_process_group(tmp_path):
    script = tmp_path / "persistent_tree.py"
    script.write_text(
        "import signal, subprocess, sys, time\n"
        "signal.signal(signal.SIGTERM, lambda *_: None)\n"
        "subprocess.Popen([sys.executable, '-c', "
        "'import signal,time; signal.signal(signal.SIGTERM, lambda *_: None); "
        "time.sleep(300)'], start_new_session=True)\n"
        "print('ready', flush=True)\n"
        "time.sleep(300)\n",
        encoding="utf-8",
    )
    result = _run_linux_containment_probe(script, timeout=0.2, grace=0.2)
    assert result["timed_out"] is True
    assert result["residual_descendants"] is True
    assert result["remaining"] == []


@pytest.mark.skipif(sys.platform != "linux", reason="Linux subreaper fixture")
def test_clean_parent_with_residual_child_is_rejected_and_cleaned(tmp_path):
    script = tmp_path / "orphan_tree.py"
    script.write_text(
        "import os, signal, subprocess, sys\n"
        "subprocess.Popen([sys.executable, '-c', "
        "'import signal,time; signal.signal(signal.SIGTERM, lambda *_: None); "
        "time.sleep(300)'], stdin=subprocess.DEVNULL, "
        "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, "
        "start_new_session=True)\n"
        "os._exit(0)\n",
        encoding="utf-8",
    )
    result = _run_linux_containment_probe(script, timeout=5, grace=0.2)
    assert result["timed_out"] is False
    assert result["residual_descendants"] is True
    assert result["remaining"] == []


@pytest.mark.skipif(sys.platform != "linux", reason="Linux subreaper fixture")
def test_communicate_failure_still_cleans_process_tree(tmp_path):
    script = tmp_path / "communication_failure_tree.py"
    script.write_text(
        "import signal, time\n"
        "signal.signal(signal.SIGTERM, lambda *_: None)\n"
        "time.sleep(5)\n",
        encoding="utf-8",
    )
    result = _run_linux_containment_probe(
        script, timeout=5, grace=0.2, inject_communicate_failure=True
    )
    assert result["error"] == "OSError"
    assert result["remaining"] == []


@pytest.mark.skipif(sys.platform != "linux", reason="Linux subreaper fixture")
def test_timeout_cleans_forking_term_resistant_descendants(tmp_path):
    script = tmp_path / "forking_tree.py"
    script.write_text(
        "import signal, subprocess, sys, time\n"
        "signal.signal(signal.SIGTERM, lambda *_: None)\n"
        "deadline = time.monotonic() + 2\n"
        "while time.monotonic() < deadline:\n"
        "    subprocess.Popen([sys.executable, '-c', "
        "'import signal,time; signal.signal(signal.SIGTERM, lambda *_: None); "
        "time.sleep(5)'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
        "stderr=subprocess.DEVNULL, start_new_session=True)\n"
        "    time.sleep(0.02)\n"
        "time.sleep(5)\n",
        encoding="utf-8",
    )
    result = _run_linux_containment_probe(script, timeout=0.2, grace=0.2)
    assert result["timed_out"] is True
    assert result["residual_descendants"] is True
    assert result["remaining"] == []
