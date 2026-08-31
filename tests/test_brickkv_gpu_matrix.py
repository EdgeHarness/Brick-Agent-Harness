import pytest

from perf.brickkv.gpu_matrix import (
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
            "endpoint_binding": "random_loopback_authenticated_v1",
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
