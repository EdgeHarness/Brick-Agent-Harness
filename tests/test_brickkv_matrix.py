import json

import pytest

from perf.brickkv.run_matrix import (
    coefficient_of_variation,
    correctness_mismatches,
    mode_order,
    needs_extra_repetitions,
    paired_bootstrap_improvement,
    performance_claim_gate,
    percentile,
    process_metrics,
    runtime_bundle_manifest,
    summarize_observations,
    validate_evidence,
    write_json_exclusive,
    write_integrity_manifest,
)


def record(trace, mode, ttft, wall=1000):
    status = {
        "managed": "reused", "reset": "reset", "legacy-test": "legacy-test"
    }[mode]
    reason = {
        "managed": "exact_extension",
        "reset": "reset_each_call",
        "legacy-test": "raw_keep_cache",
    }[mode]
    return {
        "trace": trace,
        "mode": mode,
        "ttft_us": ttft,
        "wall_us": wall,
        "prompt_tokens": 10,
        "generated_tokens": 2,
        "prompt_us": 50,
        "decode_us": 100,
        "cache_status": status,
        "cache_reason": reason,
        "revision": "sha256:" + "b" * 64 if mode == "managed" else "",
        "role": "driver",
        "step": 0,
        "result_code": 0,
        "stop_reason": "eos",
        "callback_cancelled": False,
        "reusable": mode in {"managed", "legacy-test"},
        "working_set_bytes": 1024,
        "output_digest": "sha256:" + "a" * 64,
    }


def payload(mode, values=(100, 200)):
    records = [record("append_only", mode, value) for value in values]
    for step, item in enumerate(records):
        item["step"] = step
        if mode == "managed" and step == 0:
            item["cache_status"] = "cold"
            item["cache_reason"] = "first_request"
    return {
        "schema_version": "brickkv.replay/4",
        "status": "complete",
        "created_at": "2026-08-30T12:00:00Z",
        "attestation": {
            "source_revision": "c" * 40,
            "source_bundle_digest": "sha256:" + "1" * 64,
            "replay_executable_digest": "sha256:" + "2" * 64,
            "runtime_bundle_digest": "sha256:" + "3" * 64,
            "sdk_version": "1.2.3",
            "plugin": "qairt",
            "plugin_version": "2.0.0",
            "model_digest": "sha256:" + "d" * 64,
            "tokenizer_digest": "none",
            "requested_device": "npu",
            "resolved_device": "NPU",
            "device_warning": "none",
            "hardware_label": "test-x1e",
            "process_architecture": "arm64",
            "host_processor": "Qualcomm Oryon",
            "system_product_name": "test-system",
        },
        "configuration": {
            "context": 8192,
            "runtime_n_ctx": 0,
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

    producer_warning = payload("managed", (100,))
    producer_warning["attestation"]["device_warning"] = "present"
    with pytest.raises(ValueError, match="unexpected coercion warning"):
        validate_evidence(producer_warning, "managed")

    malformed_warning = payload("managed", (100,))
    malformed_warning["attestation"]["device_warning"] = ""
    with pytest.raises(ValueError, match="must be none or present"):
        validate_evidence(malformed_warning, "managed")


def test_runtime_bundle_manifest_is_order_independent_and_content_bound(tmp_path):
    first = tmp_path / "runtime-a.dll"
    second = tmp_path / "runtime-b.dll"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    forward = runtime_bundle_manifest([first, second])
    reverse = runtime_bundle_manifest([second, first])
    assert forward == reverse
    assert forward["runtime_bundle_digest"] == (
        "sha256:c1e2a53eb4f63e167531868d3137155f"
        "34a9b72a34a60d4f6b27b6e2dcbd8115"
    )
    second.write_bytes(b"changed")
    assert runtime_bundle_manifest([first, second]) != forward


def test_runtime_bundle_manifest_rejects_duplicate_names(tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "geniex.dll").write_bytes(b"one")
    (right / "GENIEX.DLL").write_bytes(b"two")
    with pytest.raises(RuntimeError, match="duplicated"):
        runtime_bundle_manifest([
            left / "geniex.dll", right / "GENIEX.DLL",
        ])


def test_evidence_validation_enforces_plugin_context_semantics():
    qairt_override = payload("managed", (100,))
    qairt_override["configuration"]["runtime_n_ctx"] = 8192
    with pytest.raises(ValueError, match="model-defined"):
        validate_evidence(qairt_override, "managed")

    llama = payload("managed", (100,))
    llama["attestation"].update({
        "plugin": "llama_cpp",
        "requested_device": "cpu",
        "resolved_device": "",
    })
    llama["configuration"]["runtime_n_ctx"] = 4096
    with pytest.raises(ValueError, match="must match"):
        validate_evidence(llama, "managed")


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

    shifted = payload("managed", (100, 200))
    shifted["records"][0]["step"] = 10
    shifted["records"][1]["step"] = 11
    shifted["records"][0]["cache_status"] = "reused"
    shifted["records"][0]["cache_reason"] = "exact_extension"
    with pytest.raises(ValueError, match="exact trace-step"):
        validate_evidence(shifted, "managed")

    reversed_records = payload("managed", (100, 200, 300))
    reversed_records["records"].reverse()
    with pytest.raises(ValueError, match="canonical trace-step order"):
        validate_evidence(reversed_records, "managed")


def test_evidence_validation_rejects_failed_or_impossible_measurements():
    failed = payload("managed", (100,))
    failed["records"][0]["result_code"] = 999
    failed["records"][0]["stop_reason"] = "error"
    with pytest.raises(ValueError, match="failed result code"):
        validate_evidence(failed, "managed")

    for field in (
        "ttft_us", "prompt_us", "decode_us", "wall_us", "prompt_tokens",
        "generated_tokens", "working_set_bytes",
    ):
        impossible = payload("managed", (100,))
        impossible["records"][0][field] = 0
        with pytest.raises(ValueError, match="must be positive"):
            validate_evidence(impossible, "managed")

    inverted = payload("managed", (100,))
    inverted["records"][0]["wall_us"] = 99
    with pytest.raises(ValueError, match="smaller than TTFT"):
        validate_evidence(inverted, "managed")


def test_evidence_validation_tracks_non_reusable_truncated_parent():
    evidence = payload("managed", (100, 200))
    evidence["records"][0]["stop_reason"] = "length"
    evidence["records"][0]["reusable"] = False
    evidence["records"][1]["cache_status"] = "reset"
    evidence["records"][1]["cache_reason"] = "previous_not_reusable"
    validate_evidence(evidence, "managed")

    unsafe = payload("managed", (100, 200))
    unsafe["records"][0]["stop_reason"] = "length"
    with pytest.raises(ValueError, match="reusable decision"):
        validate_evidence(unsafe, "managed")


@pytest.mark.parametrize(
    "trace", ("planning_removed", "invalid_deleted", "context_pruning")
)
def test_evidence_validation_enforces_branch_reset_sequence(trace):
    branch = payload("managed", (100,))
    branch["records"] = [record(trace, "managed", 100) for _ in range(4)]
    decisions = (
        ("cold", "first_request"),
        ("reused", "exact_extension"),
        ("reset", "branch"),
        ("reused", "exact_extension"),
    )
    for step, (item, (status, reason)) in enumerate(
        zip(branch["records"], decisions)
    ):
        item["step"] = step
        item["cache_status"] = status
        item["cache_reason"] = reason
    validate_evidence(branch, "managed", expected_traces=frozenset({trace}))
    branch["records"][2]["cache_status"] = "reused"
    branch["records"][2]["cache_reason"] = "exact_extension"
    with pytest.raises(ValueError, match="cache decision"):
        validate_evidence(branch, "managed", expected_traces=frozenset({trace}))


@pytest.mark.parametrize(
    ("mode", "status", "reason"),
    (
        ("reset", "reset", "reset_each_call"),
        ("legacy-test", "legacy-test", "raw_keep_cache"),
    ),
)
def test_evidence_validation_enforces_nonmanaged_decisions(mode, status, reason):
    evidence = payload(mode, (100, 200))
    validate_evidence(evidence, mode)
    assert all(item["cache_status"] == status for item in evidence["records"])
    assert all(item["cache_reason"] == reason for item in evidence["records"])
    evidence["records"][0]["cache_reason"] = "exact_extension"
    with pytest.raises(ValueError, match="cache decision"):
        validate_evidence(evidence, mode)


def test_evidence_validation_enforces_roles_and_cancellation_location():
    verifier = payload("managed", (100,))
    verifier["records"] = [
        record("verifier_detour", "managed", 100) for _ in range(3)
    ]
    for step, item in enumerate(verifier["records"]):
        item["step"] = step
        item["role"] = "verifier" if step == 1 else "driver"
        if step == 0:
            item["cache_status"] = "cold"
            item["cache_reason"] = "first_request"
        else:
            item["cache_status"] = "reset"
            item["cache_reason"] = "session_switch"
    validate_evidence(
        verifier, "managed", expected_traces=frozenset({"verifier_detour"})
    )
    verifier["records"][1]["role"] = "driver"
    with pytest.raises(ValueError, match="trace role"):
        validate_evidence(
            verifier, "managed", expected_traces=frozenset({"verifier_detour"})
        )

    cancellation = payload("managed", (100,))
    cancellation["records"] = [
        record("cancellation_decode", "managed", 100) for _ in range(4)
    ]
    for step, item in enumerate(cancellation["records"]):
        item["step"] = step
    cancellation["records"][0]["cache_status"] = "cold"
    cancellation["records"][0]["cache_reason"] = "first_request"
    interrupted = cancellation["records"][1]
    interrupted["callback_cancelled"] = True
    interrupted["reusable"] = False
    interrupted["cache_status"] = "aborted"
    interrupted["cache_reason"] = "callback_cancellation"
    interrupted["revision"] = ""
    interrupted["stop_reason"] = "callback_cancelled"
    cancellation["records"][2]["cache_status"] = "reset"
    cancellation["records"][2]["cache_reason"] = "parent_mismatch"
    validate_evidence(
        cancellation, "managed",
        expected_traces=frozenset({"cancellation_decode"}),
    )
    interrupted["callback_cancelled"] = False
    with pytest.raises(ValueError, match="cancellation placement"):
        validate_evidence(
            cancellation, "managed",
            expected_traces=frozenset({"cancellation_decode"}),
        )
    interrupted["callback_cancelled"] = True
    interrupted["cache_reason"] = "first_request"
    with pytest.raises(ValueError, match="cache decision"):
        validate_evidence(
            cancellation, "managed",
            expected_traces=frozenset({"cancellation_decode"}),
        )
    interrupted["cache_reason"] = "callback_cancellation"
    cancellation["records"][2]["cache_status"] = "reused"
    cancellation["records"][2]["cache_reason"] = "exact_extension"
    with pytest.raises(ValueError, match="cache decision"):
        validate_evidence(
            cancellation, "managed",
            expected_traces=frozenset({"cancellation_decode"}),
        )


def test_process_metrics_do_not_treat_calls_as_independent_runs():
    metrics = process_metrics(payload("managed", (100, 300)))
    assert set(metrics) == {"append_only"}
    assert metrics["append_only"]["p95_ttft_us"] == pytest.approx(290)
    assert metrics["append_only"]["cache_hits"] == 1


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


def test_performance_claim_gate_is_narrow_and_fail_closed():
    summary = {
        "reset": {"append_only": {"decode_tokens_per_s_median": 100.0}},
        "managed": {"append_only": {"decode_tokens_per_s_median": 98.0}},
    }
    improvements = {
        "append_only": {
            "paired_process_blocks": 10,
            "median_improvement_percent": 25.0,
            "bootstrap_95_ci_percent": [10.0, 30.0],
            "prompt_tokens_avoided_median": 100.0,
        }
    }
    passed = performance_claim_gate(summary, improvements, [], [])
    assert passed["authorized"] is True
    assert passed["final_research_claim_authorized"] is False

    failed = performance_claim_gate(
        summary,
        {"append_only": dict(
            improvements["append_only"],
            bootstrap_95_ci_percent=[-1.0, 30.0],
        )},
        [{"reason": "mismatch"}],
        [{"cv": 0.2}],
    )
    assert failed["authorized"] is False
    assert "p95_ttft_confidence_interval_includes_zero" in failed["reasons"]
    assert "synthetic_output_or_result_mismatch" in failed["reasons"]


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
