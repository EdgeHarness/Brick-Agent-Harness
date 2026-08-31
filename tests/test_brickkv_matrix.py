import json

import pytest

from perf.brickkv.run_matrix import (
    coefficient_of_variation,
    correctness_mismatches,
    mode_order,
    needs_extra_repetitions,
    paired_bootstrap_improvement,
    percentile,
    process_metrics,
    summarize_observations,
    validate_evidence,
    write_json_exclusive,
    write_integrity_manifest,
)


def record(trace, mode, ttft, wall=1000):
    return {
        "trace": trace,
        "mode": mode,
        "ttft_us": ttft,
        "wall_us": wall,
        "prompt_tokens": 10,
        "generated_tokens": 2,
        "prompt_us": 50,
        "decode_us": 100,
        "cache_status": "reused" if mode == "managed" else "reset",
        "cache_reason": "exact_extension" if mode == "managed" else "reset_each_call",
        "revision": "sha256:" + "b" * 64 if mode == "managed" else "",
        "role": "driver",
        "step": 0,
        "result_code": 0,
        "stop_reason": "eos",
        "callback_cancelled": False,
        "working_set_bytes": 1024,
        "output_digest": "sha256:" + "a" * 64,
    }


def payload(mode, values=(100, 200)):
    records = [record("append_only", mode, value) for value in values]
    for step, item in enumerate(records):
        item["step"] = step
    return {
        "schema_version": "brickkv.replay/1",
        "status": "complete",
        "created_at": "2026-08-30T12:00:00Z",
        "attestation": {
            "source_revision": "c" * 40,
            "sdk_version": "1.2.3",
            "plugin": "qairt",
            "plugin_version": "2.0.0",
            "model_digest": "sha256:" + "d" * 64,
            "tokenizer_digest": "none",
            "requested_device": "npu",
            "resolved_device": "NPU",
            "device_warning": "",
            "hardware_label": "test-x1e",
            "process_architecture": "arm64",
            "host_processor": "Qualcomm Oryon",
            "system_product_name": "test-system",
        },
        "configuration": {
            "context": 8192,
            "max_tokens": 32,
            "append_turns": len(values),
            "cancel_after_tokens": 1,
        },
        "records": records,
    }


def test_mode_order_is_deterministic_and_balanced():
    assert mode_order(7, "measure", 3) == mode_order(7, "measure", 3)
    assert set(mode_order(7, "measure", 3)) == {
        "reset", "legacy-test", "managed"
    }


def test_percentile_and_cv_are_explicit():
    assert percentile([1, 2, 3], 0.5) == 2
    assert coefficient_of_variation([10, 10, 10]) == 0
    assert coefficient_of_variation([10]) is None


def test_evidence_validation_rejects_prompt_content():
    clean = payload("managed")
    validate_evidence(clean, "managed")
    dirty = payload("managed")
    dirty["prompt"] = "do not persist me"
    with pytest.raises(ValueError, match="forbidden key"):
        validate_evidence(dirty, "managed")


def test_evidence_validation_rejects_attestation_mismatch_and_unknown_versions():
    wrong_arch = payload("managed", (100,))
    with pytest.raises(ValueError, match="attestation mismatch"):
        validate_evidence(
            wrong_arch,
            "managed",
            expected_attestation={"process_architecture": "x86_64"},
        )
    unknown_sdk = payload("managed", (100,))
    unknown_sdk["attestation"]["sdk_version"] = "unknown"
    with pytest.raises(ValueError, match="verified value"):
        validate_evidence(unknown_sdk, "managed")


def test_evidence_validation_rejects_partial_and_duplicate_traces():
    partial = payload("managed", (100,))
    with pytest.raises(ValueError, match="trace set"):
        validate_evidence(
            partial,
            "managed",
            expected_traces=frozenset({"append_only", "context_pruning"}),
        )
    duplicate = payload("managed", (100, 200))
    duplicate["records"][1]["step"] = 0
    with pytest.raises(ValueError, match="duplicate"):
        validate_evidence(duplicate, "managed")


def test_process_metrics_do_not_treat_calls_as_independent_runs():
    metrics = process_metrics(payload("managed", (100, 300)))
    assert set(metrics) == {"append_only"}
    assert metrics["append_only"]["p95_ttft_us"] == pytest.approx(290)
    assert metrics["append_only"]["cache_hits"] == 2


def test_summary_cv_and_paired_bootstrap_use_process_blocks():
    observations = []
    for block, reset, managed in ((0, 100, 70), (1, 110, 75), (2, 90, 60)):
        for mode, value in (("reset", reset), ("managed", managed)):
            observations.append({
                "block": block,
                "mode": mode,
                "metrics": {
                    "append_only": {
                        "p95_ttft_us": value,
                        "total_wall_us": value * 2,
                    "prompt_tokens": 10,
                    "decode_tokens_per_s": 20,
                    "errors": 0,
                    "output_digests": ["sha256:" + "a" * 64],
                    }
                },
            })
    summary = summarize_observations(observations)
    assert summary["managed"]["append_only"]["process_runs"] == 3
    result = paired_bootstrap_improvement(
        observations, "append_only", samples=200, seed=1
    )
    assert result["paired_process_blocks"] == 3
    assert result["median_improvement_percent"] > 20
    assert result["prompt_tokens_avoided_median"] == 0
    assert not needs_extra_repetitions(summary, 0.5)


def test_correctness_gate_detects_a_managed_output_divergence():
    observations = []
    for mode, marker in (("reset", "a"), ("managed", "a")):
        observations.append({
            "block": 0,
            "mode": mode,
            "metrics": {
                "append_only": {
                    "output_digests": ["sha256:" + marker * 64],
                    "errors": 0,
                }
            },
        })
    assert correctness_mismatches(observations, "reset", "managed") == []
    observations[1]["metrics"]["append_only"]["output_digests"] = [
        "sha256:" + "b" * 64
    ]
    mismatches = correctness_mismatches(observations, "reset", "managed")
    assert mismatches == [{
        "block": 0,
        "trace": "append_only",
        "reason": "output digest sequence differs",
    }]


def test_integrity_manifest_hashes_files_but_not_itself(tmp_path):
    (tmp_path / "result.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    write_integrity_manifest(tmp_path)
    manifest = json.loads((tmp_path / "integrity.json").read_text(encoding="utf-8"))
    assert [entry["path"] for entry in manifest["files"]] == ["result.json"]
    assert len(manifest["files"][0]["sha256"]) == 64


def test_json_evidence_publication_never_overwrites(tmp_path):
    destination = tmp_path / "evidence.json"
    write_json_exclusive(destination, {"version": 1})
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        write_json_exclusive(destination, {"version": 2})
    assert json.loads(destination.read_text(encoding="utf-8")) == {"version": 1}


def test_json_evidence_publication_preserves_abandoned_temp(tmp_path):
    destination = tmp_path / "evidence.json"
    temporary = tmp_path / "evidence.json.tmp"
    temporary.write_text("partial", encoding="utf-8")
    with pytest.raises(RuntimeError, match="partial evidence"):
        write_json_exclusive(destination, {"version": 1})
    assert temporary.read_text(encoding="utf-8") == "partial"
