import copy
import json
from pathlib import Path
import subprocess

import pytest

from bench.next_study_claim import load_claim_contract
from bench.next_study_construct import load_contract
from bench.next_study_contract import _sha256, load_design
from bench.next_study_program import (
    HOST_FINGERPRINT_SCHEMA, REQUIRED_ARTIFACT_DIGESTS,
    RUNTIME_FINGERPRINT_SCHEMA, SEALED_GATE_SCHEMA, advance_program,
    build_authorization, build_fingerprint, initial_program_state,
    primary_mask_key_commitment,
)
from bench.next_study_rehearsal import DEFAULT_OUTPUT
from bench.next_study_runtime import (
    NextStudyRuntimeError, build_release_archive_manifest, verify_release,
)
from harness.evidence import canonical_json_bytes
from harness.instances import load_canonical_json


def test_final_construct_claim_and_rehearsal_contracts_are_exact(tmp_path):
    construct = load_contract()
    claim = load_claim_contract()
    rehearsal = load_canonical_json(DEFAULT_OUTPUT)
    design = load_design()
    rendered = load_canonical_json(
        Path("evidence/next-study/semantic-validation-report/artifact.json")
    )
    assert construct["generator_version"] == "office-generators/2.3.0"
    assert construct["acceptance"]["cal_add_calendar_feasibility_changes_candidate_set"] is True
    assert construct["acceptance"]["preference_policy_must_be_derived_without_printed_selected_answer"] is True
    assert construct["matched_triplets"] == 176
    assert len(construct["policies"]) == 11
    assert claim["threshold_inclusive"] is True
    assert claim["sign_flip"]["may_change_claim"] is False
    assert rehearsal["status"] == "passed"
    assert rehearsal["descriptive_cells"] == 222
    assert rehearsal["scenarios"]["incomplete"]["unmasked"] is False
    assert rehearsal["whole_ledger_boundaries"]["52/440"]["claim_disposition"] == "no_directional_superiority_claim"
    assert rehearsal["whole_ledger_boundaries"]["53/440"]["claim_disposition"] == "harness_full_directional_superiority"
    assert design["successor_artifacts"]["semantic_rendered_report_path"] == (
        "evidence/next-study/semantic-validation-report/artifact.json"
    )
    assert rendered["snapshot"]["datasets"]["summary"] == [{
        "typed_workflows": 1056,
        "high_findings": 0,
        "memory_failures": 0,
        "nominal_families": 0,
        "families_total": 11,
    }]
    lf = tmp_path / "lf.txt"
    crlf = tmp_path / "crlf.txt"
    lf.write_bytes(b"alpha\nbeta\n")
    crlf.write_bytes(b"alpha\r\nbeta\r\n")
    assert _sha256(lf) == _sha256(crlf)
    lf_csv = tmp_path / "lf.csv"
    crlf_csv = tmp_path / "crlf.csv"
    lf_csv.write_bytes(b"case,result\n1,pass\n")
    crlf_csv.write_bytes(b"case,result\r\n1,pass\r\n")
    assert _sha256(lf_csv) == _sha256(crlf_csv)


def _authorization():
    return build_authorization(
        tag="v0.13.3", tag_object_sha="9" * 40, commit_sha="a" * 40,
        artifact_digests={name: "b" * 64 for name in REQUIRED_ARTIFACT_DIGESTS},
        host_fingerprint=build_fingerprint(HOST_FINGERPRINT_SCHEMA, {"host": "test"}),
        runtime_fingerprint=build_fingerprint(RUNTIME_FINGERPRINT_SCHEMA, {"runtime": "test"}),
        schedule_digests={name: "c" * 64 for name in ("calibration", "sentinel", "primary", "descriptives")},
        model_digests={name: "d" * 64 for name in ("2b", "4b", "9b")},
        descriptive_selection_sha256="e" * 64,
        primary_mask_key_commitment_sha256=primary_mask_key_commitment("7" * 64),
        issued_at="2026-08-05T10:00:00Z", issuer="release test",
    )


def _release_ready_state(authorization):
    state = initial_program_state(authorization["authorization_sha256"])
    for phase, logical in (
        ("calibration", 352), ("sentinel", 88), ("primary", 880),
        ("primary_analysis", 0), ("descriptives", 222),
    ):
        state = advance_program(state, {
            "schema_version": SEALED_GATE_SCHEMA,
            "authorization_sha256": authorization["authorization_sha256"],
            "phase": phase, "status": "sealed_pass",
            "logical_cells_completed": logical,
            "physical_attempts_completed": logical,
            "sealed_artifact_sha256": "f" * 64,
        })
    return state


def test_release_verifier_recomputes_bytes_and_requires_annotated_tag(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Brick Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "brick@example.invalid"], cwd=tmp_path, check=True)
    authorization = _authorization()
    names = (
        "authorization",
        "calibration", "sentinel", "masked_primary_ledger",
        "primary_grade_ledger", "primary_analysis", "descriptives",
        "resource_report", "failure_taxonomy", "program_bindings",
        "study_report", "program_state",
    )
    paths = {}
    for name in names:
        path = Path("archive") / (name + ".json")
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(canonical_json_bytes(
            authorization if name == "authorization" else {"name": name},
            newline=True,
        ))
        paths[name] = path
    subprocess.run(["git", "add", "archive"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "archive"], cwd=tmp_path, check=True, capture_output=True)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "tag", "-a", "v0.14.0", "-m", "study release"],
        cwd=tmp_path, check=True,
    )
    state = _release_ready_state(authorization)
    archive = build_release_archive_manifest(tmp_path, authorization, commit, paths)
    with pytest.raises(
        NextStudyRuntimeError,
        match="archived program state|semantic|sealed phase gate",
    ):
        verify_release(tmp_path, authorization, state, archive)
    (tmp_path / paths["study_report"]).write_text("tampered\n", encoding="utf-8")
    with pytest.raises(NextStudyRuntimeError, match="bytes drifted"):
        verify_release(tmp_path, authorization, state, archive)
    synthetic = copy.deepcopy(authorization)
    synthetic["execution_context"]["value"] = "synthetic_rehearsal"
    unsigned = dict(synthetic)
    unsigned.pop("authorization_sha256")
    from harness.instances import sha256_bytes
    synthetic["authorization_sha256"] = sha256_bytes(canonical_json_bytes(unsigned, allow_float=False))
    synthetic_state = _release_ready_state(synthetic)
    with pytest.raises(NextStudyRuntimeError, match="Synthetic|synthetic"):
        verify_release(tmp_path, synthetic, synthetic_state, archive)
