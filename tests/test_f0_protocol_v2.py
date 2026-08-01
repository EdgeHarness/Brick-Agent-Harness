"""Tests for the F0 protocol v2 corrective contract.

F0 v1 gated eligibility on Ollama rejecting an *unknown* option name. Ollama
never promised that, and 0.32.5 ignores unknown names, so the v1 gate tested an
assumption the runtime does not make. These tests lock the replacement: Brick
owns request validation, per-key recognition is proven positively, the real
inference runner is attested, and failures are attributed to a domain rather
than collapsed into a model result.
"""

import copy
import json
import os
from pathlib import Path
import sys

import pytest

from bench import f0_probe, f0_windows


def valid_request(**overrides):
    protocol = f0_probe.load_protocol()
    payload = f0_probe._chat_payload(
        protocol,
        "qwen3.5:4b-q4_K_M",
        [{"role": "user", "content": "hi"}],
        [],
        7,
        num_predict=4,
    )
    payload.update(overrides)
    return protocol, payload


# --- protocol schema ------------------------------------------------------


def test_protocol_v2_is_the_only_supported_schema():
    protocol = f0_probe.load_protocol()
    assert protocol["schema_version"] == "brick.f0.protocol/2"
    assert protocol["recognition_suite"] == "option-recognition-v2"
    legacy = copy.deepcopy(protocol)
    legacy["schema_version"] = "brick.f0.protocol/1"
    with pytest.raises(f0_probe.F0Error, match="unsupported F0 protocol"):
        f0_probe.validate_protocol(legacy)


def test_protocol_rejects_altered_option_contract():
    protocol = copy.deepcopy(f0_probe.load_protocol())
    protocol["option_contract"]["temperature"] = "integer"
    with pytest.raises(f0_probe.F0Error, match="option contract"):
        f0_probe.validate_protocol(protocol)


def test_protocol_rejects_sentinel_colliding_with_real_option():
    protocol = copy.deepcopy(f0_probe.load_protocol())
    protocol["unknown_option_sentinel"] = "temperature"
    with pytest.raises(f0_probe.F0Error, match="collides"):
        f0_probe.validate_protocol(protocol)


def test_every_sent_option_is_covered_by_the_contract():
    protocol = f0_probe.load_protocol()
    _, payload = valid_request()
    assert set(payload["options"]) == set(protocol["option_contract"])


# --- Brick-owned fail-closed request validation ---------------------------


def test_valid_request_passes_its_own_contract():
    protocol, payload = valid_request()
    assert f0_probe.validate_chat_request(payload, protocol) is payload


def test_request_validation_rejects_unexpected_option_key():
    protocol, payload = valid_request()
    payload["options"]["brick_f0_unknown_option"] = 1
    with pytest.raises(f0_probe.F0Error, match="unexpected"):
        f0_probe.validate_chat_request(payload, protocol)


def test_request_validation_rejects_missing_option_key():
    protocol, payload = valid_request()
    del payload["options"]["min_p"]
    with pytest.raises(f0_probe.F0Error, match="missing"):
        f0_probe.validate_chat_request(payload, protocol)


def test_request_validation_rejects_bool_masquerading_as_integer():
    protocol, payload = valid_request()
    payload["options"]["top_k"] = True
    with pytest.raises(f0_probe.F0Error, match="top_k must be an integer"):
        f0_probe.validate_chat_request(payload, protocol)


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_request_validation_rejects_non_finite_float(value):
    protocol, payload = valid_request()
    payload["options"]["temperature"] = value
    with pytest.raises(f0_probe.F0Error, match="finite"):
        f0_probe.validate_chat_request(payload, protocol)


def test_request_validation_rejects_drift_from_frozen_sampling():
    protocol, payload = valid_request()
    payload["options"]["presence_penalty"] = 1.5
    with pytest.raises(f0_probe.F0Error, match="frozen sampling policy"):
        f0_probe.validate_chat_request(payload, protocol)


def test_request_validation_rejects_streaming():
    protocol, payload = valid_request()
    payload["stream"] = True
    with pytest.raises(f0_probe.F0Error, match="stream"):
        f0_probe.validate_chat_request(payload, protocol)


def test_request_validation_rejects_enabled_thinking():
    protocol, payload = valid_request()
    payload["think"] = True
    with pytest.raises(f0_probe.F0Error, match="think"):
        f0_probe.validate_chat_request(payload, protocol)


def test_request_validation_rejects_unreproducible_seed():
    protocol, payload = valid_request()
    payload["options"]["seed"] = -1
    with pytest.raises(f0_probe.F0Error, match="reproducible range"):
        f0_probe.validate_chat_request(payload, protocol)


def test_request_validation_rejects_extra_top_level_key():
    protocol, payload = valid_request()
    payload["format"] = "json"
    with pytest.raises(f0_probe.F0Error, match="request contract"):
        f0_probe.validate_chat_request(payload, protocol)


# --- per-key option recognition -------------------------------------------


class RecognitionClient:
    """Configurable stand-in for the measured Ollama option contract."""

    def __init__(self, accepted_keys=(), baseline_ok=True, health_ok=True):
        self.accepted_keys = set(accepted_keys)
        self.baseline_ok = baseline_ok
        self.health_ok = health_ok
        self.valid_calls = 0

    def rejected_post(self, path, payload):
        assert path == "/api/chat"
        protocol = f0_probe.load_protocol()
        options = payload["options"]
        invalid = protocol["recognition_invalid_value"]
        sentinel = protocol["unknown_option_sentinel"]
        ok = {
            "status_code": 200,
            "body": {"message": {"role": "assistant", "content": "ok"}},
        }
        rejected = {"status_code": 500, "body": {"error": "rejected"}}
        if sentinel in options:
            return ok
        for key in sorted(protocol["option_contract"]):
            if options.get(key) == invalid:
                if key in self.accepted_keys:
                    return ok
                return {
                    "status_code": 500,
                    "body": {
                        "error": 'option "' + key + '" must be of type float32'
                    },
                }
        self.valid_calls += 1
        if self.valid_calls == 1:
            return ok if self.baseline_ok else rejected
        return ok if self.health_ok else rejected


def run_recognition(tmp_path, client):
    return f0_probe.run_option_recognition(
        client,
        f0_probe.load_protocol(),
        "qwen3.5:4b-q4_K_M",
        "4" * 64,
        Path(tmp_path) / "rec",
    )


def test_option_recognition_passes_when_every_key_is_recognized(tmp_path):
    protocol = f0_probe.load_protocol()
    summary = run_recognition(tmp_path, RecognitionClient())
    assert summary["passed"] is True
    assert summary["unrecognized_options"] == []
    assert summary["recognized_options"] == sorted(protocol["option_contract"])
    assert summary["failure_codes"] == []


def test_unknown_name_acceptance_is_diagnostic_not_gating(tmp_path):
    """The exact v1 failure condition must no longer fail the gate."""
    summary = run_recognition(tmp_path, RecognitionClient())
    assert summary["unknown_option_accepted"] is True
    assert summary["passed"] is True
    assert "typo hazard" in summary["unknown_option_note"]


def test_option_recognition_fails_when_a_real_key_is_ignored(tmp_path):
    summary = run_recognition(
        tmp_path, RecognitionClient(accepted_keys={"presence_penalty"})
    )
    assert summary["passed"] is False
    assert summary["unrecognized_options"] == ["presence_penalty"]
    assert "option_names_not_recognized" in summary["failure_codes"]


def test_option_recognition_fails_when_frozen_map_is_rejected(tmp_path):
    summary = run_recognition(tmp_path, RecognitionClient(baseline_ok=False))
    assert summary["passed"] is False
    assert "frozen_option_map_rejected" in summary["failure_codes"]


def test_option_recognition_fails_when_server_unhealthy_after(tmp_path):
    summary = run_recognition(tmp_path, RecognitionClient(health_ok=False))
    assert summary["passed"] is False
    assert "server_unhealthy_after_probe" in summary["failure_codes"]


def test_failing_recognition_never_asserts_success_in_prose(tmp_path):
    """The v1 reporting bug: static prose claimed a pass on failure."""
    summary = run_recognition(tmp_path, RecognitionClient(accepted_keys={"top_p"}))
    assert summary["passed"] is False
    assert "Every frozen option name was recognized" not in (
        summary["interpretation"]
    )
    assert "failed" in summary["interpretation"].casefold()
    assert "top_p" in summary["interpretation"]


def test_recognition_records_expected_type_per_key(tmp_path):
    protocol = f0_probe.load_protocol()
    summary = run_recognition(tmp_path, RecognitionClient())
    for key, expected in protocol["option_contract"].items():
        assert summary["options"][key]["expected_type"] == expected
        assert summary["options"][key]["rejected"] is True


def test_recognition_writes_every_request_and_response(tmp_path):
    protocol = f0_probe.load_protocol()
    run_recognition(tmp_path, RecognitionClient())
    directory = Path(tmp_path) / "rec"
    for name in ("baseline", "unknown-option", "health"):
        assert (directory / f"{name}-request.json").is_file()
        assert (directory / f"{name}-response.json").is_file()
    for key in protocol["option_contract"]:
        assert (directory / f"option-{key}-request.json").is_file()
        assert (directory / f"option-{key}-response.json").is_file()


# --- inference-runner attestation -----------------------------------------


def runner_sample(pid=100, **overrides):
    runner = {
        "pid": pid + 1,
        "parent_pid": pid,
        "image": "ollama-runner.exe",
        "path": "C:\\fake\\ollama-runner.exe",
        "sha256": "b" * 64,
        "pe_machine": {"value": f0_windows.ARM64_PE_MACHINE, "name": "arm64"},
    }
    runner.update(overrides)
    return [
        {
            "pids": [pid, runner["pid"]],
            "processes": [
                {"pid": pid, "parent_pid": 0, "image": "ollama.exe"},
                runner,
            ],
        }
    ]


def test_runner_attestation_passes_for_native_arm64_runner():
    result = f0_probe._attest_inference_runners(runner_sample(), 100)
    assert result["observed"] is True
    assert result["passed"] is True
    assert result["failure_codes"] == []
    assert result["runners"][0]["native_arm64"] is True


def test_runner_attestation_rejects_emulated_x64_runner():
    """An ARM64 listener must not legitimise an emulated x64 runner."""
    samples = runner_sample(
        pe_machine={"value": f0_windows.AMD64_PE_MACHINE, "name": "amd64"}
    )
    result = f0_probe._attest_inference_runners(samples, 100)
    assert result["passed"] is False
    assert any(
        code.startswith("runner_not_arm64")
        for code in result["failure_codes"]
    )


def test_runner_attestation_rejects_unhashed_runner():
    result = f0_probe._attest_inference_runners(
        runner_sample(sha256=None), 100
    )
    assert result["passed"] is False
    assert any(
        code.startswith("runner_not_hashed")
        for code in result["failure_codes"]
    )


def test_runner_attestation_rejects_identity_change_mid_probe():
    first = runner_sample()[0]
    second = copy.deepcopy(first)
    second["processes"][1]["sha256"] = "c" * 64
    result = f0_probe._attest_inference_runners([first, second], 100)
    assert result["passed"] is False
    assert any(
        code.startswith("runner_identity_changed")
        for code in result["failure_codes"]
    )


def test_runner_attestation_requires_a_runner_at_all():
    samples = [
        {
            "pids": [100],
            "processes": [
                {"pid": 100, "parent_pid": 0, "image": "ollama.exe"}
            ],
        }
    ]
    result = f0_probe._attest_inference_runners(samples, 100)
    assert result["observed"] is False
    assert result["passed"] is False
    assert "no_inference_runner_observed" in result["failure_codes"]


def test_runner_attestation_needs_samples():
    result = f0_probe._attest_inference_runners([], 100)
    assert result["passed"] is False
    assert "no_process_samples" in result["failure_codes"]


def test_process_tree_sample_carries_runner_identity():
    if os.name != "nt":
        pytest.skip("non-Windows behavior")
    sample = f0_windows.sample_process_tree(os.getpid())
    mine = [p for p in sample["processes"] if p["pid"] == os.getpid()]
    assert mine and mine[0]["path"]
    assert mine[0]["pe_machine"]["value"] in {
        f0_windows.ARM64_PE_MACHINE,
        f0_windows.AMD64_PE_MACHINE,
        f0_windows.X86_PE_MACHINE,
    }
    assert len(mine[0]["sha256"]) == 64


def test_executable_identity_is_cached_by_path():
    """Caching must hold on any platform: hashing once per path, not per sample."""
    first = f0_windows.executable_identity(sys.executable)
    second = f0_windows.executable_identity(sys.executable)
    assert first == second
    assert set(first) == {"sha256", "pe_machine", "error"}


def test_executable_identity_reports_a_non_pe_file_as_an_error(tmp_path):
    """A non-PE file must fail closed with a recorded reason, never silently."""
    path = Path(tmp_path) / "not-a-pe.bin"
    path.write_bytes(b"\x7fELF not a portable executable")
    identity = f0_windows.executable_identity(str(path))
    assert identity["sha256"] is None
    assert identity["pe_machine"] is None
    assert "WindowsProbeError" in identity["error"]


@pytest.mark.skipif(os.name != "nt", reason="PE parsing is Windows-only")
def test_executable_identity_hashes_a_real_pe_binary():
    identity = f0_windows.executable_identity(sys.executable)
    assert identity["error"] is None
    assert len(identity["sha256"]) == 64
    assert identity["pe_machine"]["value"] in {
        f0_windows.ARM64_PE_MACHINE,
        f0_windows.AMD64_PE_MACHINE,
        f0_windows.X86_PE_MACHINE,
    }


# --- failure attribution --------------------------------------------------


def classify(models):
    return f0_probe._classify_failures(
        {"passed": True}, {"passed": True}, {"passed": True}, models, True
    )


def test_failure_classification_separates_contract_from_runtime():
    codes = classify(
        [
            {
                "tag": "qwen3.5:4b-q4_K_M",
                "role": "primary",
                "passed": False,
                "option_recognition_passed": False,
                "option_recognition_failure_codes": [
                    "option_names_not_recognized"
                ],
                "native_tools_passed": True,
                "throughput_passed": True,
                "memory": {"passed": True},
            }
        ]
    )
    assert {code["domain"] for code in codes} == {"protocol_contract"}
    assert any(
        code["code"] == "option_recognition_failed" for code in codes
    )


def test_throughput_failure_is_model_runtime_not_contract():
    codes = classify(
        [
            {
                "tag": "qwen3.5:4b-q4_K_M",
                "role": "primary",
                "passed": False,
                "option_recognition_passed": True,
                "native_tools_passed": True,
                "throughput_passed": False,
                "minimum_eval_tps": 5.0,
                "runtime": {"median_eval_tps": 2.0},
                "memory": {"passed": True},
            }
        ]
    )
    assert {code["domain"] for code in codes} == {"model_runtime"}
    assert codes[0]["code"] == "throughput_below_floor"


def test_runner_fault_is_instrument_not_model():
    """Hard rule: never convert a runner failure into a model failure."""
    codes = classify(
        [
            {
                "tag": "qwen3.5:4b-q4_K_M",
                "role": "primary",
                "passed": False,
                "option_recognition_passed": True,
                "native_tools_passed": True,
                "throughput_passed": True,
                "memory": {
                    "passed": False,
                    "runner_attestation": {
                        "failure_codes": ["runner_not_arm64:5"]
                    },
                },
            }
        ]
    )
    assert {code["domain"] for code in codes} == {"instrument"}
    assert codes[0]["code"] == "inference_runner_attestation_failed"


def test_native_tool_transport_failure_is_a_contract_failure():
    codes = classify(
        [
            {
                "tag": "qwen3.5:4b-q4_K_M",
                "role": "primary",
                "passed": False,
                "option_recognition_passed": True,
                "native_tools_passed": False,
                "throughput_passed": True,
                "memory": {"passed": True},
            }
        ]
    )
    assert {code["domain"] for code in codes} == {"protocol_contract"}


# --- report verification --------------------------------------------------


def write_identity(run_dir, protocol, run_id, validate_schema=True):
    digest = f0_probe._protocol_hash(protocol)
    f0_probe._write_json(run_dir / "protocol.json", protocol)
    f0_probe._write_bytes(
        run_dir / "protocol.sha256", (digest + "\n").encode("ascii")
    )
    f0_probe._write_json(
        run_dir / "run.json",
        {
            "schema_version": "brick.f0.run/1",
            "run_id": run_id,
            "pull_requested": True,
        },
    )
    f0_probe._write_json(
        run_dir / "repository.json",
        {
            "schema_version": "brick.f0.repository/1",
            "commit": "a" * 40,
            "behavior_tree_sha256": "d" * 64,
            "clean": True,
        },
    )
    return digest


def test_legacy_v1_bundle_verifies_for_integrity_but_never_passes(tmp_path):
    """The immutable failed v1 bundle must remain verifiable evidence."""
    run_dir = Path(tmp_path) / "legacy-run"
    run_dir.mkdir()
    protocol = {"schema_version": "brick.f0.protocol/1", "note": "legacy"}
    digest = write_identity(run_dir, protocol, "legacy-run")
    f0_probe._write_json(
        run_dir / "summary.json",
        {
            "schema_version": "brick.f0.summary/1",
            "run_id": "legacy-run",
            "protocol_sha256": digest,
            "overall_status": "fail",
        },
    )
    f0_probe._publish_report(run_dir)
    summary = f0_probe.verify_report(run_dir)
    assert summary["overall_status"] == "fail"

    forged = dict(summary)
    forged["overall_status"] = "pass"
    with pytest.raises(f0_probe.F0Error, match="never establish a passing"):
        f0_probe._verify_legacy_report(run_dir, forged)


def test_failed_report_must_substantiate_a_failing_model(tmp_path):
    """A failed report is verified semantically, not merely echoed back."""
    run_dir = Path(tmp_path) / "unsubstantiated"
    run_dir.mkdir()
    protocol = f0_probe.load_protocol()
    digest = write_identity(run_dir, protocol, "unsubstantiated")
    f0_probe._write_json(
        run_dir / "environment.json",
        {"schema_version": "brick.f0.environment/1", "passed": True},
    )
    f0_probe._write_json(
        run_dir / "storage" / "summary.json",
        {"schema_version": "brick.f0.storage-summary/1", "passed": True},
    )
    primary = {
        "schema_version": "brick.f0.model-summary/2",
        "tag": protocol["primary_model"],
        "role": "primary",
        "passed": False,
        "status": "ineligible",
        "digest_stable": True,
        "metadata_passed": True,
        "option_recognition_passed": True,
        "native_tools_passed": True,
        "throughput_passed": True,
        "memory": {"passed": True},
    }
    f0_probe._write_json(
        run_dir
        / "models"
        / f0_probe._safe_model_slug(protocol["primary_model"])
        / "summary.json",
        primary,
    )
    f0_probe._write_json(
        run_dir / "summary.json",
        {
            "schema_version": f0_probe.SUMMARY_SCHEMA,
            "run_id": "unsubstantiated",
            "protocol_sha256": digest,
            "overall_status": "fail",
            "environment_status": "pass",
            "storage_status": "pass",
            "failures": ["primary 4B model feasibility failed"],
            "failure_codes": [],
            "failure_domains": [],
            "primary": primary,
            "descriptive_models": [],
        },
    )
    f0_probe._publish_report(run_dir)
    with pytest.raises(f0_probe.F0Error, match="no substantiating cause"):
        f0_probe.verify_report(run_dir)


def test_failed_report_rejects_misattributed_failure_domain(tmp_path):
    run_dir = Path(tmp_path) / "misattributed"
    run_dir.mkdir()
    protocol = f0_probe.load_protocol()
    digest = write_identity(run_dir, protocol, "misattributed")
    f0_probe._write_json(
        run_dir / "environment.json",
        {"schema_version": "brick.f0.environment/1", "passed": True},
    )
    f0_probe._write_json(
        run_dir / "storage" / "summary.json",
        {"schema_version": "brick.f0.storage-summary/1", "passed": True},
    )
    primary = {
        "schema_version": "brick.f0.model-summary/2",
        "tag": protocol["primary_model"],
        "role": "primary",
        "passed": False,
        "status": "ineligible",
        "option_recognition_passed": False,
        "memory": {"passed": True},
    }
    f0_probe._write_json(
        run_dir
        / "models"
        / f0_probe._safe_model_slug(protocol["primary_model"])
        / "summary.json",
        primary,
    )
    f0_probe._write_json(
        run_dir / "summary.json",
        {
            "schema_version": f0_probe.SUMMARY_SCHEMA,
            "run_id": "misattributed",
            "protocol_sha256": digest,
            "overall_status": "fail",
            "environment_status": "pass",
            "storage_status": "pass",
            "failures": ["primary 4B model feasibility failed"],
            "failure_codes": [{"domain": "not_a_domain", "code": "x"}],
            "failure_domains": ["not_a_domain"],
            "primary": primary,
            "descriptive_models": [],
        },
    )
    f0_probe._publish_report(run_dir)
    with pytest.raises(f0_probe.F0Error, match="misattributed"):
        f0_probe.verify_report(run_dir)
