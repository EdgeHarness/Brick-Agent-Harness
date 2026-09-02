import json

import pytest

import perf.brickkv.server_equivalence as equivalence


DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
REVISION = "a" * 40


def record(mode, trace, role, step, *, cancelled=False, status=None, reason=None):
    if status is None or reason is None:
        status, reason = equivalence.expected_cache_decision(mode, trace, step)
    return {
        "trace": trace,
        "mode": mode,
        "role": role,
        "step": step,
        "cancelled": cancelled,
        "cache_status": status,
        "cache_reason": reason,
        "revision": DIGEST_A if mode == "managed" and not cancelled else "",
        "reusable": mode == "managed" and not cancelled,
        "ttft_us": 10,
        "decode_stream_us": 20,
        "wall_us": 40,
        "prompt_tokens": 0 if cancelled else (4 if mode == "managed" and step else 12),
        "generated_tokens": 0 if cancelled else 3,
        "observed_output_chunks": 2,
        "working_set_bytes": 1000,
        "finish_reason": "client_disconnect" if cancelled else "stop",
        "output_digest": equivalence.expected_marker_digest(
            trace, role, step, cancelled
        ) or DIGEST_A,
        "stream_bytes": 100,
    }


def payload(mode):
    records = [
        record(mode, "append_only", "driver", 0),
        record(mode, "append_only", "driver", 1),
    ]
    return {
        "schema_version": equivalence.REPLAY_SCHEMA,
        "status": "complete",
        "created_at": "2026-09-01T00:00:00Z",
        "claim_scope": {
            "kind": "attested_production_path_development_replay",
            "model_role": "smoke",
            "performance_claim_authorized": False,
            "final_benchmark_complete": False,
        },
        "attestation": {
            "source_revision": REVISION,
            "source_bundle_digest": DIGEST_A,
            "source_file_count": 5,
            "geniex_revision": "b" * 40,
            "operator_asserted_runtime_version": "2.45.0",
            "operator_asserted_hardware_label": "X1E-78-100",
            "process_architecture": "arm64",
            "model": "qualcomm/qwen3_0_6b",
            "model_artifact": {
                "kind": "directory", "files": 2, "bytes": 100,
                "sha256": DIGEST_A,
            },
            "model_artifact_binding": "geniex-data/models/<catalogue-name>",
            "cli_sha256": DIGEST_A,
            "loaded_runtime_modules": [
                {"name": "geniex.dll", "bytes": 10, "sha256": DIGEST_A}
            ],
            "server_pid": 100,
            "server_creation_time_100ns": 200,
            "listener_identity_checks": 3,
            "runtime_module_checks": 4,
            "server_origin": "http://127.0.0.1:18181",
        },
        "configuration": {
            "mode": mode,
            "traces": ["append_only"],
            "append_turns": 2,
            "max_completion_tokens": 64,
            "cancel_after_stream_chunks": 2,
            "streaming": True,
            "single_bound_server_process": True,
            "fresh_process_launch_attested": False,
        },
        "records": records,
    }


def test_equivalence_gate_requires_non_regression_and_real_prompt_reuse():
    result = equivalence.compare_replays(payload("reset"), payload("managed"))
    assert result == {
        "completed_records_compared": 2,
        "cancelled_records_excluded": 0,
        "managed_cache_hits": 1,
        "managed_hits_with_lower_prompt_tokens": 1,
        "reset_task_passes": 2,
        "managed_task_passes": 2,
        "managed_task_regressions": [],
        "managed_task_improvements": [],
        "same_outcome_mismatches": [],
        "exact_output_equivalent": True,
        "exact_output_mismatches": [],
        "task_non_regression": True,
        "managed_reuse_observed": True,
        "prompt_reduction_observed": True,
        "development_npu_gate_passed": True,
    }


@pytest.mark.parametrize("field,value", (
    ("output_digest", DIGEST_B),
    ("finish_reason", "length"),
    ("generated_tokens", 4),
))
def test_equivalence_gate_records_secret_free_result_divergence(field, value):
    reset = payload("reset")
    managed = payload("managed")
    managed["records"][1][field] = value
    if field == "finish_reason":
        managed["records"][1]["reusable"] = False
    result = equivalence.compare_replays(reset, managed)
    assert result["development_npu_gate_passed"] is False
    assert result["exact_output_mismatches"] == [{
        "trace": "append_only", "role": "driver", "step": 1, "field": field,
    }]


def test_equivalence_gate_accepts_only_oracle_proven_improvement():
    reset = payload("reset")
    reset["records"][1]["output_digest"] = DIGEST_B
    result = equivalence.compare_replays(reset, payload("managed"))
    assert result["reset_task_passes"] == 1
    assert result["managed_task_passes"] == 2
    assert result["managed_task_improvements"] == [{
        "trace": "append_only", "role": "driver", "step": 1,
    }]
    assert result["task_non_regression"] is True
    assert result["development_npu_gate_passed"] is True


@pytest.mark.parametrize("trace,role,step,expected", (
    ("append_only", "driver", 1, "ACK_append_only_2"),
    ("context_pruning", "driver", 2, "ACK_context_pruned"),
    ("verifier_detour", "verifier", 1, "ACK_verifier"),
    ("verifier_detour", "driver", 2, "ACK_verifier_detour_2"),
    ("cancellation_decode", "driver", 2, "ACK_cancellation_recovered"),
))
def test_task_oracle_covers_special_trace_markers(trace, role, step, expected):
    assert equivalence.expected_marker(trace, role, step, False) == expected


def test_equivalence_gate_rejects_zero_task_success_even_when_failures_match():
    reset = payload("reset")
    managed = payload("managed")
    for left, right in zip(reset["records"], managed["records"]):
        left["output_digest"] = DIGEST_B
        right["output_digest"] = DIGEST_B
    result = equivalence.compare_replays(reset, managed)
    assert result["reset_task_passes"] == 0
    assert result["managed_task_passes"] == 0
    assert result["task_non_regression"] is False
    assert result["development_npu_gate_passed"] is False


def test_equivalence_gate_rejects_different_failures():
    reset = payload("reset")
    managed = payload("managed")
    reset["records"][1]["output_digest"] = DIGEST_A
    managed["records"][1]["output_digest"] = DIGEST_B
    result = equivalence.compare_replays(reset, managed)
    assert result["reset_task_passes"] == 1
    assert result["managed_task_passes"] == 1
    assert result["same_outcome_mismatches"] == [{
        "trace": "append_only", "role": "driver", "step": 1,
        "field": "output_digest",
    }]
    assert result["development_npu_gate_passed"] is False


def test_equivalence_gate_rejects_inert_managed_cache():
    managed = payload("managed")
    managed["records"][0]["finish_reason"] = "length"
    managed["records"][0]["reusable"] = False
    managed["records"][1]["cache_status"] = "reset"
    managed["records"][1]["cache_reason"] = "previous_not_reusable"
    result = equivalence.compare_replays(payload("reset"), managed)
    assert result["managed_cache_hits"] == 0
    assert result["development_npu_gate_passed"] is False


def test_equivalence_gate_rejects_pairing_different_runtime_artifacts():
    managed = payload("managed")
    managed["attestation"]["loaded_runtime_modules"][0]["sha256"] = DIGEST_B
    with pytest.raises(ValueError, match="loaded_runtime_modules"):
        equivalence.compare_replays(payload("reset"), managed)


def test_equivalence_gate_rejects_content_bearing_evidence():
    reset = payload("reset")
    reset["records"][0]["content"] = "must not be persisted"
    with pytest.raises(ValueError, match="forbidden key"):
        equivalence.validate_replay(reset, "reset")


@pytest.mark.parametrize("field,value,match", (
    ("append_turns", 1_000_000_000, "append_turns"),
    ("max_completion_tokens", 1_000_000_000, "max_completion_tokens"),
    ("cancel_after_stream_chunks", 65, "exceeds"),
))
def test_equivalence_gate_bounds_untrusted_configuration(field, value, match):
    reset = payload("reset")
    reset["configuration"][field] = value
    with pytest.raises(ValueError, match=match):
        equivalence.validate_replay(reset, "reset")


def test_main_writes_failed_report_then_exits(monkeypatch, tmp_path):
    reset = payload("reset")
    managed = payload("managed")
    managed["records"][1]["output_digest"] = DIGEST_B
    reset_path = tmp_path / "reset.json"
    managed_path = tmp_path / "managed.json"
    output = tmp_path / "comparison.json"
    reset_path.write_text(json.dumps(reset), encoding="utf-8")
    managed_path.write_text(json.dumps(managed), encoding="utf-8")
    manifest = {
        "source_bundle_digest": DIGEST_A,
        "files": [
            {"path": f"x{index}", "bytes": 1, "sha256": DIGEST_A}
            for index in range(5)
        ],
    }
    monkeypatch.setattr(equivalence, "verify_git_revision", lambda *args: None)
    monkeypatch.setattr(equivalence, "source_bundle_manifest", lambda *args: manifest)
    with pytest.raises(SystemExit, match="failed task non-regression"):
        equivalence.main([
            "--execute", "--reset", str(reset_path), "--managed",
            str(managed_path), "--source-revision", REVISION, "--output",
            str(output),
        ])
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["claim_scope"]["performance_claim_authorized"] is False
    assert report["comparison"]["development_npu_gate_passed"] is False
