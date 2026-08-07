"""End-to-end release archive and annotated-tag binding tests."""

from pathlib import Path
import subprocess

from bench.next_study_descriptive import (
    build_report as build_descriptive_report,
    eligible_schedule,
    extract_descriptive_results,
    extract_primary_trial_0_controls,
    seal_descriptive_eligibility,
)
from bench.next_study_program import (
    HOST_FINGERPRINT_SCHEMA,
    REQUIRED_ARTIFACT_DIGESTS,
    RUNTIME_FINGERPRINT_SCHEMA,
    SEALED_GATE_SCHEMA,
    advance_program,
    build_authorization,
    build_fingerprint,
    initial_program_state,
    primary_mask_key_commitment,
)
from bench.next_study_rehearsal import MASKING_KEY, _attempts, _positive_values
from bench.next_study_report import build_study_report
from bench.next_study_runtime import (
    build_masked_grade_ledger,
    build_release_archive_manifest,
    unmask_primary,
    verify_release,
)
from bench.next_study_schedule import build_descriptive_schedule, build_phase_schedule
from bench.next_study_statistics import analyze_primary
from harness.evidence import canonical_json_bytes
from harness.instances import load_canonical_json, sha256_bytes


ROOT = Path(__file__).resolve().parents[1]


def _digest(value):
    return sha256_bytes(canonical_json_bytes(value, allow_float=False))


def _commit(repository, message):
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(
        ["git", "commit", "-m", message], cwd=repository, check=True,
        capture_output=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repository, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def test_release_archive_is_semantic_commit_bound_and_tag_verified(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Brick Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "brick@example.invalid"], cwd=tmp_path, check=True)
    (tmp_path / ".gitattributes").write_text("*.json text eol=lf\n", encoding="ascii")
    (tmp_path / "instrument.txt").write_text("qualified\n", encoding="ascii")
    instrument_commit = _commit(tmp_path, "instrument")
    subprocess.run(
        ["git", "tag", "-a", "v0.13.3", "-m", "instrument"],
        cwd=tmp_path, check=True,
    )
    instrument_tag = subprocess.run(
        ["git", "rev-parse", "refs/tags/v0.13.3"], cwd=tmp_path,
        check=True, capture_output=True, text=True,
    ).stdout.strip()

    retained = load_canonical_json(
        ROOT / "bench" / "manifests" / "office-v2" / "retained.json"
    )
    primary_schedule = build_phase_schedule(retained, "primary", "4" * 64)
    descriptive_schedule = build_descriptive_schedule(
        retained, {"2b": "2" * 64, "4b": "4" * 64, "9b": "9" * 64},
    )
    primary_attempts = _attempts(
        primary_schedule, _positive_values(retained, 57)
    )
    masked = build_masked_grade_ledger(
        primary_schedule, primary_attempts, retained,
        "2026-08-05T10:00:00Z", MASKING_KEY,
    )
    grade = unmask_primary(
        masked, primary_schedule, retained, primary_attempts, MASKING_KEY,
        "2026-08-05T10:01:00Z",
    )
    analysis = analyze_primary(grade, retained, primary_schedule)
    eligibility = seal_descriptive_eligibility(
        analysis, grade, descriptive_schedule
    )
    eligible = eligible_schedule(
        descriptive_schedule, {"2b": True, "4b": True, "9b": True},
        eligibility,
    )
    descriptive_evidence = extract_descriptive_results(
        eligible, _attempts(descriptive_schedule, {})
    )
    controls = extract_primary_trial_0_controls(grade, descriptive_schedule)
    descriptives = build_descriptive_report(
        eligible, descriptive_evidence, controls
    )

    manifest_lock = load_canonical_json(
        ROOT / "bench" / "manifests" / "office-v2" / "manifest-lock.json"
    )
    artifact_digests = {
        name: "b" * 64 for name in REQUIRED_ARTIFACT_DIGESTS
    }
    artifact_digests["manifest_lock"] = sha256_bytes(
        canonical_json_bytes(manifest_lock, allow_float=False, newline=True)
    )
    authorization = build_authorization(
        tag="v0.13.3", tag_object_sha=instrument_tag,
        commit_sha=instrument_commit, artifact_digests=artifact_digests,
        host_fingerprint=build_fingerprint(
            HOST_FINGERPRINT_SCHEMA, {"host": "test"}
        ),
        runtime_fingerprint=build_fingerprint(
            RUNTIME_FINGERPRINT_SCHEMA, {"runtime": "test"}
        ),
        schedule_digests={
            "calibration": "1" * 64, "sentinel": "2" * 64,
            "primary": _digest(primary_schedule),
            "descriptives": _digest(descriptive_schedule),
        },
        model_digests={"2b": "2" * 64, "4b": "4" * 64, "9b": "9" * 64},
        descriptive_selection_sha256=descriptive_schedule["selection_sha256"],
        primary_mask_key_commitment_sha256=primary_mask_key_commitment(
            MASKING_KEY
        ),
        issued_at="2026-08-05T10:02:00Z", issuer="release integration test",
    )
    calibration = {"schema_version": "test.calibration/1", "status": "passed"}
    sentinel = {"schema_version": "test.sentinel/1", "status": "passed"}
    state = initial_program_state(authorization["authorization_sha256"])
    for phase, logical, artifact in (
        ("calibration", 352, calibration),
        ("sentinel", 88, sentinel),
        ("primary", 880, masked),
        ("primary_analysis", 0, analysis),
        ("descriptives", 222, descriptives),
    ):
        state = advance_program(state, {
            "schema_version": SEALED_GATE_SCHEMA,
            "authorization_sha256": authorization["authorization_sha256"],
            "phase": phase, "status": "sealed_pass",
            "logical_cells_completed": logical,
            "physical_attempts_completed": logical,
            "sealed_artifact_sha256": _digest(artifact),
        })
    study, resource, taxonomy, bindings = build_study_report(
        analysis, descriptives, manifest_lock, grade, authorization, state, [],
    )
    documents = {
        "authorization": authorization,
        "calibration": calibration,
        "sentinel": sentinel,
        "masked_primary_ledger": masked,
        "primary_grade_ledger": grade,
        "primary_analysis": analysis,
        "descriptives": descriptives,
        "resource_report": resource,
        "failure_taxonomy": taxonomy,
        "program_bindings": bindings,
        "study_report": study,
        "program_state": state,
    }
    paths = {}
    for name, document in documents.items():
        relative = Path("archive") / (name + ".json")
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(canonical_json_bytes(document, newline=True))
        paths[name] = relative
    archived_commit = _commit(tmp_path, "study archive")
    subprocess.run(
        ["git", "tag", "-a", "v0.14.0", "-m", "study release"],
        cwd=tmp_path, check=True,
    )
    archive = build_release_archive_manifest(
        tmp_path, authorization, archived_commit, paths
    )
    attestation = verify_release(
        tmp_path, authorization, state, archive, annotated_tag="v0.14.0"
    )
    assert attestation["status"] == "verified"
    assert attestation["archived_commit"] == archived_commit
