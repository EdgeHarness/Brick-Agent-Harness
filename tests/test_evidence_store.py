import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import uuid

import pytest

from harness.evidence import (
    AttemptKey,
    CandidateStateError,
    DuplicateCandidateError,
    EvidenceIntegrityError,
    EvidenceStore,
    LogicalCollisionError,
    RunLockedError,
)


RUN_ID = "s4-test-run"
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
SHA_F = "f" * 64

GOLDEN_CANONICAL = (
    b'{"condition":{"mechanism_sha256":"cccccccccccccccccccccccccccccccc'
    b'cccccccccccccccccccccccccccccccc","name":"harness_full","version":"1.0.0"},'
    b'"domain":{"content_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    b'aaaaaaaaaaaaaaaa","name":"brix_synthetic","version":"1.0.0"},'
    b'"generator_version":"1.0.0","grader_version":"1.0.0",'
    b'"instance":{"content_sha256":"dddddddddddddddddddddddddddddddddddddddddddddddd'
    b'dddddddddddddddd","id":"lead-0001"},'
    b'"model":{"digest":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
    b'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","tag":"qwen3.5:4b"},'
    b'"opportunity_budget":{"model_calls":4,"tool_calls":12},'
    b'"ordered_subepisodes":["draft","approve"],'
    b'"prompt_sha256":"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
    b'eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",'
    b'"repeat":0,"sampling":{"seed":17,"temperature":"0"},'
    b'"schema_version":"brick.attempt-key/1",'
    b'"task":{"family":"lead_followup","version":"1.0.0"},'
    b'"tool_schema_sha256":"ffffffffffffffffffffffffffffffff'
    b'ffffffffffffffffffffffffffffffff"}'
)
GOLDEN_LOGICAL_HASH = (
    "7303db3630be2fe2427771e4ce421f70ac276cabe85e7f983b04d753a98153e9"
)

REQUIRED_EVIDENCE = {
    "initial-state.json": {
        "schema_version": "brick.evidence-state/1",
        "state_kind": "initial",
        "payload": {"lead": {"id": "lead-0001", "status": "new"}},
    },
    "final-state.json": {
        "schema_version": "brick.evidence-state/1",
        "state_kind": "final",
        "payload": {"lead": {"id": "lead-0001", "status": "approved"}},
    },
    "result.json": {
        "schema_version": "brick.evidence-result/1",
        "execution_status": "done",
        "tool_status": "clean",
        "failure_origin": "none",
        "failure": None,
        "metrics": {"model_calls": 1, "tool_calls": 1},
        "diagnostics": [],
    },
    "grade.json": {
        "schema_version": "brick.evidence-grade/1",
        "grader_status": "graded",
        "candidate_decision": True,
        "diagnostics": [],
    },
    "actions.json": {
        "schema_version": "brick.evidence-actions/1",
        "actions": [{"tool": "draft_followup", "ok": True}],
    },
}


def make_key(_key_type=AttemptKey, **changes):
    values = {
        "domain_name": "brix_synthetic",
        "domain_version": "1.0.0",
        "domain_content_sha256": SHA_A,
        "task_family": "lead_followup",
        "task_version": "1.0.0",
        "generator_version": "1.0.0",
        "grader_version": "1.0.0",
        "model_tag": "qwen3.5:4b",
        "model_digest": f"sha256:{SHA_B}",
        "condition_name": "harness_full",
        "condition_version": "1.0.0",
        "mechanism_sha256": SHA_C,
        "instance_id": "lead-0001",
        "instance_content_sha256": SHA_D,
        "ordered_subepisodes": ("draft", "approve"),
        "repeat": 0,
        "sampling": {"seed": 17, "temperature": "0"},
        "opportunity_budget": {"model_calls": 4, "tool_calls": 12},
        "prompt_sha256": SHA_E,
        "tool_schema_sha256": SHA_F,
    }
    values.update(changes)
    return _key_type(**values)


def make_store(tmp_path, metadata=None):
    metadata = (
        {
            "protocol_sha256": "1" * 64,
            "candidate_commit": "2" * 40,
        }
        if metadata is None
        else metadata
    )
    return EvidenceStore.create_run(tmp_path / "runs", RUN_ID, metadata)


def resolution_state(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value["state"]
    return value.state


def resolution_record(value):
    if isinstance(value, dict):
        return value.get("record")
    return getattr(value, "record", None)


def resolution_producer_called(value):
    if isinstance(value, dict):
        return value["producer_called"]
    return value.producer_called


def write_complete_evidence(
    writer,
    *,
    strict_success=True,
    grader_status="graded",
    execution_status="done",
    tool_status="clean",
    failure_origin="none",
    failure=None,
    memory_payload=(
        b'{"delta":[],"schema_version":"brick.memory-delta/1"}\n'
    ),
):
    for relative, value in REQUIRED_EVIDENCE.items():
        value = json.loads(json.dumps(value))
        if relative == "result.json":
            value["execution_status"] = execution_status
            value["tool_status"] = tool_status
            value["failure_origin"] = failure_origin
            value["failure"] = failure
        if relative == "grade.json":
            value["grader_status"] = grader_status
            value["candidate_decision"] = strict_success
        writer.write_json(relative, value)
    writer.write_bytes("transcript.md", b"# S4 attempt\n")
    writer.write_bytes("memory-delta.jsonl", memory_payload)
    writer.write_bytes("artifacts/followup.txt", b"Approved synthetic draft.\n")


def source_snapshot(candidate):
    return {
        path.relative_to(candidate).as_posix(): path.read_bytes()
        for path in sorted(candidate.rglob("*"))
        if path.is_file()
    }


def clone_valid_candidate(candidate, *, committed):
    """Create a second hash-valid physical candidate as corruption injection."""
    physical_id = str(uuid.uuid4())
    clone = candidate.parent / physical_id
    shutil.copytree(candidate, clone)

    attempt_path = clone / "attempt.json"
    attempt = json.loads(attempt_path.read_text("utf-8"))
    attempt["physical_uuid"] = physical_id
    attempt_path.write_bytes(
        (
            json.dumps(
            attempt,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    )

    prepared_path = clone / "PREPARED.json"
    prepared = json.loads(prepared_path.read_text("utf-8"))
    prepared["physical_uuid"] = physical_id
    for entry in prepared["files"]:
        if entry["path"] == "attempt.json":
            payload = attempt_path.read_bytes()
            entry["size"] = len(payload)
            entry["sha256"] = hashlib.sha256(payload).hexdigest()
            break
    prepared_path.write_bytes(
        (
            json.dumps(
            prepared,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    )
    if not committed:
        (clone / "COMMITTED").unlink()
    return clone



@pytest.fixture
def tmp_path(s4_bounded_root):
    """Bound this module's test root so the deepest S4 path stays under the
    Windows directory limit. Shadows pytest's builtin for this module only, so
    no test signature changes. See tests/conftest.py for the derivation."""
    return s4_bounded_root

def test_attempt_key_golden_vector_is_exact_and_self_consistent():
    key = make_key()

    assert key.canonical_bytes() == GOLDEN_CANONICAL
    assert key.logical_hash() == GOLDEN_LOGICAL_HASH
    assert key.logical_hash() == hashlib.sha256(GOLDEN_CANONICAL).hexdigest()
    assert key.to_dict() == json.loads(GOLDEN_CANONICAL)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("domain_name", "another_domain"),
        ("domain_version", "1.0.1"),
        ("domain_content_sha256", "0" * 64),
        ("task_family", "document_generation"),
        ("task_version", "2.0.0"),
        ("generator_version", "2.0.0"),
        ("grader_version", "2.0.0"),
        ("model_tag", "qwen3.5:2b"),
        ("model_digest", f"sha256:{'0' * 64}"),
        ("condition_name", "native_tools"),
        ("condition_version", "2.0.0"),
        ("mechanism_sha256", "0" * 64),
        ("instance_id", "lead-0002"),
        ("instance_content_sha256", "0" * 64),
        ("ordered_subepisodes", ("draft", "approve", "deliver")),
        ("repeat", 1),
        ("sampling", {"seed": 18, "temperature": "0"}),
        ("opportunity_budget", {"model_calls": 5, "tool_calls": 12}),
        ("prompt_sha256", "0" * 64),
        ("tool_schema_sha256", "0" * 64),
    ],
)
def test_every_attempt_key_field_changes_the_logical_hash(field, replacement):
    baseline = make_key()
    changed = make_key(**{field: replacement})

    assert changed.logical_hash() != baseline.logical_hash()
    assert changed.canonical_bytes() != baseline.canonical_bytes()


def test_attempt_key_copies_nested_input_and_is_stable_after_caller_mutation():
    sampling = {"seed": 17, "temperature": "0"}
    budget = {"model_calls": 4, "tool_calls": 12}
    subepisodes = ["draft", "approve"]
    key = make_key(
        sampling=sampling,
        opportunity_budget=budget,
        ordered_subepisodes=subepisodes,
    )
    before = key.canonical_bytes()

    sampling["seed"] = 999
    budget["model_calls"] = 999
    subepisodes.append("deliver")

    assert key.canonical_bytes() == before
    assert key.to_dict()["sampling"]["seed"] == 17
    assert key.to_dict()["ordered_subepisodes"] == ["draft", "approve"]


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("domain_name", ""),
        ("domain_content_sha256", "A" * 64),
        ("mechanism_sha256", "abc"),
        ("instance_content_sha256", None),
        ("repeat", True),
        ("repeat", -1),
        ("ordered_subepisodes", "draft"),
        ("ordered_subepisodes", ("draft", 7)),
        ("sampling", []),
        ("sampling", {}),
        ("sampling", {"temperature": 0.0}),
        ("sampling", {"temperature": math.nan}),
        ("sampling", {"temperature": math.inf}),
        ("opportunity_budget", {}),
        ("prompt_sha256", "e" * 63),
        ("tool_schema_sha256", "g" * 64),
    ],
)
def test_attempt_key_rejects_ambiguous_or_invalid_types(field, replacement):
    with pytest.raises((TypeError, ValueError)):
        make_key(**{field: replacement})


@pytest.mark.parametrize(
    "field",
    ["domain_name", "task_family", "instance_id", "model_tag"],
)
def test_attempt_key_normalizes_text_to_nfc_before_hashing(field):
    decomposed = make_key(**{field: "Cafe\u0301"})
    composed = make_key(**{field: "Caf\u00e9"})

    assert decomposed == composed
    assert decomposed.canonical_bytes() == composed.canonical_bytes()
    assert decomposed.logical_hash == composed.logical_hash


@pytest.mark.parametrize(
    ("field", "decomposed_value", "composed_value"),
    [
        (
            "ordered_subepisodes",
            ("Cafe\u0301",),
            ("Caf\u00e9",),
        ),
        (
            "sampling",
            {"label": "Cafe\u0301"},
            {"label": "Caf\u00e9"},
        ),
        (
            "sampling",
            {"Cafe\u0301": "value"},
            {"Caf\u00e9": "value"},
        ),
    ],
)
def test_attempt_key_normalizes_nested_text_to_nfc_before_hashing(
    field,
    decomposed_value,
    composed_value,
):
    decomposed = make_key(**{field: decomposed_value})
    composed = make_key(**{field: composed_value})

    assert decomposed == composed
    assert decomposed.to_dict() == composed.to_dict()
    assert decomposed.logical_hash == composed.logical_hash


def test_attempt_key_rejects_object_keys_that_collide_after_nfc():
    with pytest.raises(ValueError):
        make_key(
            sampling={
                "Cafe\u0301": "decomposed",
                "Caf\u00e9": "composed",
            }
        )


@pytest.mark.parametrize(
    "sampling",
    [
        {"": "value"},
        {"label": ""},
        {"bad\u0001key": "value"},
        {"label": "bad\u0001value"},
    ],
)
def test_attempt_key_rejects_empty_or_control_identity_strings(sampling):
    with pytest.raises(ValueError):
        make_key(sampling=sampling)


def test_attempt_key_rejects_unknown_and_missing_constructor_fields():
    with pytest.raises(TypeError):
        make_key(unknown_field="not in the versioned schema")

    values = make_key().to_dict()
    values.pop("schema_version")
    values.pop("prompt_sha256")
    with pytest.raises(TypeError):
        AttemptKey(**values)


def test_create_run_builds_only_the_canonical_run_layout(tmp_path):
    runs_root = tmp_path / "runs"
    store = make_store(tmp_path)
    run_root = runs_root / RUN_ID

    assert store is not None
    assert run_root.is_dir()
    assert (run_root / "run.json").is_file()
    assert (run_root / "attempts").is_dir()
    assert set(path.name for path in run_root.iterdir()) <= {
        "attempts",
        "run.json",
        "run.lock",
    }
    run_bytes = (run_root / "run.json").read_bytes()
    run_record = json.loads(run_bytes)
    assert set(run_record) == {"schema_version", "run_id", "metadata"}
    assert run_record["schema_version"] == "brick.evidence-run/1"
    assert run_record["run_id"] == RUN_ID
    assert run_record["metadata"]["protocol_sha256"] == "1" * 64
    assert run_bytes == (
        json.dumps(
            run_record,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    assert not (run_root / "results.json").exists()


def test_run_creation_is_exclusive_and_open_validates_existing_metadata(tmp_path):
    runs_root = tmp_path / "runs"
    make_store(tmp_path)

    with pytest.raises((FileExistsError, RuntimeError, ValueError)):
        EvidenceStore.create_run(runs_root, RUN_ID, {"different": True})

    reopened = EvidenceStore.open_run(runs_root, RUN_ID)
    with reopened.locked() as session:
        assert session is not None


def test_run_manifest_change_invalidates_existing_committed_attempts(tmp_path):
    store = make_store(tmp_path)
    key = make_key()

    def producer(writer):
        write_complete_evidence(writer)

    store.execute_or_resume(key, producer)
    run_json = tmp_path / "runs" / RUN_ID / "run.json"
    record = json.loads(run_json.read_text("utf-8"))
    record["metadata"]["candidate_commit"] = "3" * 40
    run_json.write_bytes(
        (
            json.dumps(
                record,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    )

    reopened = EvidenceStore.open_run(tmp_path / "runs", RUN_ID)
    with reopened.locked() as session:
        with pytest.raises(EvidenceIntegrityError):
            session.resolve(key)


def test_candidate_copied_between_runs_fails_run_identity_binding(tmp_path):
    runs_root = tmp_path / "runs"
    first = EvidenceStore.create_run(runs_root, "first-run", {"protocol": "one"})
    second = EvidenceStore.create_run(runs_root, "second-run", {"protocol": "two"})
    key = make_key()
    paths = []

    def producer(writer):
        paths.append(writer.path)
        write_complete_evidence(writer)

    first.execute_or_resume(key, producer)
    source = paths[0]
    destination = (
        runs_root
        / "second-run"
        / "attempts"
        / key.logical_hash()
        / source.name
    )
    destination.parent.mkdir(parents=True)
    shutil.copytree(source, destination)

    with second.locked() as session:
        with pytest.raises(EvidenceIntegrityError):
            session.resolve(key)


@pytest.mark.parametrize(
    "run_id",
    ["", ".", "..", "alias.", "../escape", "a/b", "a\\b"],
)
def test_run_id_cannot_escape_the_runs_root(tmp_path, run_id):
    with pytest.raises((TypeError, ValueError)):
        EvidenceStore.create_run(tmp_path / "runs", run_id, {})


def test_resolution_distinguishes_not_started_and_abandoned(tmp_path):
    store = make_store(tmp_path)
    key = make_key()

    with store.locked() as session:
        not_started = session.resolve(key)
        writer = session.begin_attempt(key)
        writer.write_bytes("transcript.md", b"partial execution")
        abandoned_path = writer.path

    assert resolution_state(not_started) == "not_started"
    assert resolution_record(not_started) is None
    assert resolution_producer_called(not_started) is False

    with store.locked() as session:
        abandoned = session.resolve(key)
    assert resolution_state(abandoned) == "abandoned"
    assert abandoned.candidate_path == abandoned_path
    assert resolution_producer_called(abandoned) is False


def test_resume_preserves_abandoned_candidate_and_executes_in_new_uuid(tmp_path):
    store = make_store(tmp_path)
    key = make_key()
    calls = []

    with store.locked() as session:
        abandoned = session.begin_attempt(key)
        abandoned.write_bytes("transcript.md", b"partial execution")
        abandoned_path = abandoned.path
    abandoned_before = source_snapshot(abandoned_path)

    def producer(writer):
        calls.append(writer.path)
        write_complete_evidence(writer)

    result = store.execute_or_resume(key, producer)

    assert resolution_state(result) == "committed"
    assert resolution_producer_called(result) is True
    assert calls == [result.candidate_path]
    assert calls[0] != abandoned_path
    assert source_snapshot(abandoned_path) == abandoned_before
    assert not (abandoned_path / "COMMITTED").exists()


def test_begin_attempt_uses_exact_logical_and_canonical_uuid_layout(tmp_path):
    store = make_store(tmp_path)
    key = make_key()

    with store.locked() as session:
        writer = session.begin_attempt(key)
        candidate = writer.path

    assert candidate.parent.name == key.logical_hash()
    assert candidate.parent.parent.name == "attempts"
    assert str(uuid.UUID(candidate.name)) == candidate.name
    assert writer.artifacts_dir == candidate / "artifacts"
    assert writer.artifacts_dir.is_dir()
    attempt = json.loads((candidate / "attempt.json").read_text("utf-8"))
    assert set(attempt) == {
        "schema_version",
        "run_id",
        "run_sha256",
        "logical_hash",
        "physical_uuid",
        "attempt_key",
    }
    assert attempt["schema_version"] == "brick.evidence-attempt/1"
    assert attempt["run_id"] == RUN_ID
    run_json = candidate.parents[2] / "run.json"
    assert attempt["run_sha256"] == hashlib.sha256(
        run_json.read_bytes()
    ).hexdigest()
    assert attempt["attempt_key"] == key.to_dict()
    assert attempt["logical_hash"] == key.logical_hash()
    assert attempt["physical_uuid"] == candidate.name


@pytest.mark.parametrize(
    "relative",
    [
        "",
        ".",
        "..",
        "../escape.json",
        "artifacts/./escape.json",
        "artifacts/../../escape.json",
        r"artifacts\escape.json",
        "artifacts/CON.txt",
        "artifacts/aux",
        "artifacts/trailing.",
        "PREPARED.json",
        "COMMITTED",
        "attempt.json",
    ],
)
def test_writer_rejects_unsafe_or_store_owned_paths(tmp_path, relative):
    store = make_store(tmp_path)

    with store.locked() as session:
        writer = session.begin_attempt(make_key())
        with pytest.raises((TypeError, ValueError, CandidateStateError)):
            writer.write_bytes(relative, b"forbidden")

    assert not (tmp_path / "escape.json").exists()


def test_writer_rejects_absolute_paths(tmp_path):
    store = make_store(tmp_path)
    outside = tmp_path / "outside.json"

    with store.locked() as session:
        writer = session.begin_attempt(make_key())
        with pytest.raises((TypeError, ValueError, CandidateStateError)):
            writer.write_bytes(str(outside.resolve()), b"forbidden")

    assert not outside.exists()


def test_writer_normalizes_artifact_paths_to_nfc_before_creation(tmp_path):
    store = make_store(tmp_path)

    with store.locked() as session:
        writer = session.begin_attempt(make_key())
        created = writer.write_bytes(
            "artifacts/Cafe\u0301.txt",
            b"normalized path",
        )

    assert created.name == "Caf\u00e9.txt"
    assert created.read_bytes() == b"normalized path"
    assert not os.path.lexists(
        str(writer.artifacts_dir / "Cafe\u0301.txt")
    )


def test_non_nfc_member_injected_on_disk_blocks_publication(tmp_path):
    store = make_store(tmp_path)

    with store.locked() as session:
        writer = session.begin_attempt(make_key())
        write_complete_evidence(writer)
        (writer.artifacts_dir / "Cafe\u0301.txt").write_bytes(b"injected")

        with pytest.raises(EvidenceIntegrityError):
            writer.commit()

    assert not (writer.path / "COMMITTED").exists()


def test_writer_rejects_duplicate_and_case_colliding_artifact_paths(tmp_path):
    store = make_store(tmp_path)

    with store.locked() as session:
        writer = session.begin_attempt(make_key())
        write_complete_evidence(writer)
        writer.write_bytes("artifacts/Case.txt", b"first")
        with pytest.raises(
            (FileExistsError, ValueError, CandidateStateError)
        ):
            writer.write_bytes("artifacts/Case.txt", b"second")
        try:
            writer.write_bytes("artifacts/case.TXT", b"collision")
        except (FileExistsError, ValueError, CandidateStateError):
            pass
        else:
            with pytest.raises(EvidenceIntegrityError):
                writer.commit()

    assert (writer.artifacts_dir / "Case.txt").read_bytes() == b"first"


def test_unexpected_top_level_member_blocks_publication(tmp_path):
    store = make_store(tmp_path)

    with store.locked() as session:
        writer = session.begin_attempt(make_key())
        write_complete_evidence(writer)
        (writer.path / "rogue.txt").write_bytes(b"not declared evidence")
        with pytest.raises(EvidenceIntegrityError):
            writer.commit()
        assert not (writer.path / "COMMITTED").exists()


def test_symlink_member_blocks_publication_where_supported(tmp_path):
    store = make_store(tmp_path)

    with store.locked() as session:
        writer = session.begin_attempt(make_key())
        write_complete_evidence(writer)
        link = writer.artifacts_dir / "link.txt"
        try:
            os.symlink(
                writer.artifacts_dir / "followup.txt",
                link,
            )
        except OSError as exc:
            reason = f"symlink creation unavailable: {exc}"
            if os.environ.get("BRICK_S4_NATIVE_REQUIRED") == "1":
                pytest.fail(reason)
            pytest.skip(reason)
        with pytest.raises(EvidenceIntegrityError):
            writer.commit()
        assert not (writer.path / "COMMITTED").exists()


@pytest.mark.parametrize(
    "corruption",
    [
        "invalid_transcript_utf8",
        "noncanonical_memory_jsonl",
        "memory_jsonl_crlf",
        "memory_jsonl_bare_cr",
        "memory_jsonl_missing_final_lf",
        "duplicate_result_key",
        "unknown_result_key",
    ],
)
def test_invalid_evidence_envelopes_block_publication(tmp_path, corruption):
    store = make_store(tmp_path)

    with store.locked() as session:
        writer = session.begin_attempt(make_key())
        write_complete_evidence(writer)
        if corruption == "invalid_transcript_utf8":
            (writer.path / "transcript.md").write_bytes(b"\xff")
        elif corruption == "noncanonical_memory_jsonl":
            (writer.path / "memory-delta.jsonl").write_bytes(b'{ "x": 1 }\n')
        elif corruption == "memory_jsonl_crlf":
            (writer.path / "memory-delta.jsonl").write_bytes(b'{"x":1}\r\n')
        elif corruption == "memory_jsonl_bare_cr":
            (writer.path / "memory-delta.jsonl").write_bytes(b'{"x":1}\r')
        elif corruption == "memory_jsonl_missing_final_lf":
            (writer.path / "memory-delta.jsonl").write_bytes(b'{"x":1}')
        elif corruption == "duplicate_result_key":
            result = REQUIRED_EVIDENCE["result.json"]
            raw = json.dumps(result, separators=(",", ":"), sort_keys=True)
            raw = raw[:-1] + ',"execution_status":"done"}'
            (writer.path / "result.json").write_text(raw, encoding="utf-8")
        elif corruption == "unknown_result_key":
            result = dict(REQUIRED_EVIDENCE["result.json"])
            result["unknown"] = True
            (writer.path / "result.json").write_text(
                json.dumps(result, separators=(",", ":"), sort_keys=True),
                encoding="utf-8",
            )
        else:
            raise AssertionError(corruption)

        with pytest.raises(EvidenceIntegrityError):
            writer.commit()
        assert not (writer.path / "COMMITTED").exists()


@pytest.mark.parametrize("separator", ["\u2028", "\u2029"])
def test_memory_jsonl_treats_unicode_separators_as_json_string_data(
    tmp_path,
    separator,
):
    store = make_store(tmp_path)

    with store.locked() as session:
        writer = session.begin_attempt(make_key())
        payload = (
            json.dumps(
                {"text": "before" + separator + "after"},
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
        write_complete_evidence(writer, memory_payload=payload)
        writer_path = writer.path / "memory-delta.jsonl"
        result = writer.commit()

    assert result.state == "committed"
    assert writer_path.read_bytes() == payload


def test_marker_last_commit_is_hash_complete_and_discoverable(tmp_path):
    store = make_store(tmp_path)
    key = make_key()

    with store.locked() as session:
        writer = session.begin_attempt(key)
        write_complete_evidence(writer)
        result = writer.commit()
        candidate = writer.path
        resolved = session.resolve(key)

    assert resolution_state(result) == "committed"
    assert resolution_state(resolved) == "committed"
    assert (candidate / "COMMITTED").read_bytes() == b""
    prepared = json.loads((candidate / "PREPARED.json").read_text("utf-8"))
    actual_declared = {
        entry["path"]: (entry["size"], entry["sha256"])
        for entry in prepared["files"]
    }
    assert "PREPARED.json" not in actual_declared
    assert "COMMITTED" not in actual_declared
    for relative, (size, digest) in actual_declared.items():
        payload = (candidate / Path(relative)).read_bytes()
        assert len(payload) == size
        assert hashlib.sha256(payload).hexdigest() == digest


def test_committed_writer_rejects_every_later_mutation(tmp_path):
    store = make_store(tmp_path)
    key = make_key()

    with store.locked() as session:
        writer = session.begin_attempt(key)
        write_complete_evidence(writer)
        writer.commit()
        before = source_snapshot(writer.path)
        with pytest.raises(CandidateStateError):
            writer.write_bytes("transcript.md", b"replacement")
        with pytest.raises(CandidateStateError):
            writer.write_json("result.json", {"execution_status": "done"})
        assert resolution_state(writer.commit()) == "committed"

    assert source_snapshot(writer.path) == before


def test_writer_cannot_be_used_after_its_lock_session_exits(tmp_path):
    store = make_store(tmp_path)

    with store.locked() as session:
        writer = session.begin_attempt(make_key())
        writer.write_bytes("artifacts/external.txt", b"captured")

    with pytest.raises(RunLockedError):
        writer.write_bytes("transcript.md", b"outside lock")
    with pytest.raises(RunLockedError):
        writer.capture_artifact("artifacts/external.txt")
    with pytest.raises(RunLockedError):
        writer.commit()


def test_artifact_mutation_after_capture_blocks_publication(tmp_path):
    store = make_store(tmp_path)

    with store.locked() as session:
        writer = session.begin_attempt(make_key())
        write_complete_evidence(writer)
        external = writer.artifacts_dir / "externally-created.bin"
        external.write_bytes(b"before capture")
        writer.capture_artifact("artifacts/externally-created.bin")
        external.write_bytes(b"after capture")

        with pytest.raises(EvidenceIntegrityError):
            writer.commit()

    assert not (writer.path / "COMMITTED").exists()


def test_prepared_attempt_is_adopted_without_second_producer_call(tmp_path):
    store = make_store(tmp_path)
    key = make_key()
    calls = []

    with store.locked() as session:
        writer = session.begin_attempt(key)
        write_complete_evidence(writer)
        prepared = writer.commit(deadline_seconds=0)
        candidate = writer.path

    # A zero deadline still permits immediately successful idempotent work.
    # This test-only fault image then removes only the publication marker,
    # reproducing a process exit immediately before exclusive marker creation.
    marker = candidate / "COMMITTED"
    if marker.exists():
        marker.unlink()
    before = source_snapshot(candidate)

    def producer(_writer):
        calls.append("called")
        raise AssertionError("a valid prepared candidate must be adopted")

    resumed = store.execute_or_resume(key, producer)

    assert resolution_state(prepared) == "committed"
    assert resolution_state(resumed) == "committed"
    assert resolution_producer_called(resumed) is False
    assert calls == []
    assert (candidate / "COMMITTED").read_bytes() == b""
    after = source_snapshot(candidate)
    assert {k: v for k, v in after.items() if k != "COMMITTED"} == before


def test_execute_or_resume_calls_producer_once_then_reuses_commit(tmp_path):
    store = make_store(tmp_path)
    key = make_key()
    calls = []

    def producer(writer):
        calls.append(writer.path)
        write_complete_evidence(writer)

    first = store.execute_or_resume(key, producer)
    second = store.execute_or_resume(key, producer)

    assert resolution_state(first) == "committed"
    assert resolution_state(second) == "committed"
    assert resolution_producer_called(first) is True
    assert resolution_producer_called(second) is False
    assert len(calls) == 1
    assert calls[0].is_dir()


@pytest.mark.parametrize(
    ("first_committed", "second_committed"),
    [(False, False), (False, True), (True, True)],
)
def test_any_two_valid_prepared_or_committed_candidates_halt_resolution(
    tmp_path,
    first_committed,
    second_committed,
):
    store = make_store(tmp_path)
    key = make_key()
    paths = []

    def producer(writer):
        paths.append(writer.path)
        write_complete_evidence(writer)

    store.execute_or_resume(key, producer)
    first = paths[0]
    second = clone_valid_candidate(first, committed=second_committed)
    if not first_committed:
        (first / "COMMITTED").unlink()

    assert first != second
    with store.locked() as session:
        with pytest.raises(DuplicateCandidateError):
            session.resolve(key)


def test_distinct_full_key_under_same_logical_hash_halts_as_collision(tmp_path):
    store = make_store(tmp_path)
    original = make_key()

    def producer(writer):
        write_complete_evidence(writer)

    store.execute_or_resume(original, producer)

    class ForcedCollisionKey(AttemptKey):
        @property
        def logical_hash(self):
            return original.logical_hash

    colliding = make_key(
        _key_type=ForcedCollisionKey,
        instance_id="lead-collision",
        instance_content_sha256="7" * 64,
    )
    assert colliding.canonical_bytes() != original.canonical_bytes()
    assert colliding.logical_hash() == original.logical_hash()

    with store.locked() as session:
        with pytest.raises(LogicalCollisionError):
            session.resolve(colliding)


def test_corrupt_committed_evidence_halts_resolution_and_never_reexecutes(
    tmp_path,
):
    store = make_store(tmp_path)
    key = make_key()
    producer_calls = []

    def producer(writer):
        producer_calls.append(writer.path)
        write_complete_evidence(writer)

    store.execute_or_resume(key, producer)
    candidate = producer_calls[0]
    with (candidate / "final-state.json").open("ab") as handle:
        handle.write(b"\ntampered")

    with pytest.raises(EvidenceIntegrityError):
        store.execute_or_resume(key, producer)
    assert len(producer_calls) == 1


def test_unexpected_member_in_committed_candidate_halts_resolution(tmp_path):
    store = make_store(tmp_path)
    key = make_key()
    paths = []

    def producer(writer):
        paths.append(writer.path)
        write_complete_evidence(writer)

    store.execute_or_resume(key, producer)
    (paths[0] / "unexpected.txt").write_text("rogue", encoding="utf-8")

    with store.locked() as session:
        with pytest.raises(EvidenceIntegrityError):
            session.resolve(key)


@pytest.mark.parametrize(
    "corruption",
    [
        "missing_member",
        "truncated_member",
        "malformed_manifest",
        "wrong_manifest_schema",
        "wrong_manifest_logical_hash",
        "nonempty_marker",
        "wrong_attempt_key",
    ],
)
def test_committed_corruption_matrix_halts_fail_closed(tmp_path, corruption):
    store = make_store(tmp_path)
    key = make_key()
    paths = []

    def producer(writer):
        paths.append(writer.path)
        write_complete_evidence(writer)

    store.execute_or_resume(key, producer)
    candidate = paths[0]

    if corruption == "missing_member":
        (candidate / "actions.json").unlink()
    elif corruption == "truncated_member":
        (candidate / "transcript.md").write_bytes(b"")
    elif corruption == "malformed_manifest":
        (candidate / "PREPARED.json").write_bytes(b"{not-json")
    elif corruption == "wrong_manifest_schema":
        path = candidate / "PREPARED.json"
        manifest = json.loads(path.read_text("utf-8"))
        manifest["schema_version"] = "brick.attempt-prepared/999"
        path.write_text(json.dumps(manifest), encoding="utf-8")
    elif corruption == "wrong_manifest_logical_hash":
        path = candidate / "PREPARED.json"
        manifest = json.loads(path.read_text("utf-8"))
        manifest["logical_hash"] = "0" * 64
        path.write_text(json.dumps(manifest), encoding="utf-8")
    elif corruption == "nonempty_marker":
        (candidate / "COMMITTED").write_bytes(b"not empty")
    elif corruption == "wrong_attempt_key":
        path = candidate / "attempt.json"
        attempt = json.loads(path.read_text("utf-8"))
        attempt["attempt_key"]["instance"]["id"] = "different"
        path.write_text(json.dumps(attempt), encoding="utf-8")
        manifest_path = candidate / "PREPARED.json"
        manifest = json.loads(manifest_path.read_text("utf-8"))
        payload = path.read_bytes()
        for entry in manifest["files"]:
            if entry["path"] == "attempt.json":
                entry["size"] = len(payload)
                entry["sha256"] = hashlib.sha256(payload).hexdigest()
                break
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    else:
        raise AssertionError(f"unknown corruption fixture {corruption}")

    with store.locked() as session:
        with pytest.raises(EvidenceIntegrityError):
            session.resolve(key)


def test_strict_success_requires_a_graded_record(tmp_path):
    store = make_store(tmp_path)
    key = make_key()

    with store.locked() as session:
        writer = session.begin_attempt(key)
        write_complete_evidence(
            writer,
            strict_success=True,
            grader_status="not_run",
        )
        with pytest.raises(EvidenceIntegrityError):
            writer.commit()
        assert not (writer.path / "COMMITTED").exists()


def test_graded_false_is_a_valid_committed_task_failure(tmp_path):
    store = make_store(tmp_path)
    key = make_key()

    def producer(writer):
        write_complete_evidence(writer, strict_success=False)

    result = store.execute_or_resume(key, producer)

    assert resolution_state(result) == "committed"
    record = resolution_record(result)
    assert isinstance(record, dict)
    assert record["strict_success"] is False
    assert record["grader_status"] == "graded"
    assert record["record_status"] == "committed"
    assert record["publish_status"] == "committed"
    assert record["execution_status"] == "done"
    assert record["tool_status"] == "clean"


def test_graded_model_failure_is_instrument_valid_and_strict_false(tmp_path):
    store = make_store(tmp_path)
    key = make_key(task_version="model-failure")

    def producer(writer):
        write_complete_evidence(
            writer,
            strict_success=False,
            execution_status="model_error",
            failure_origin="model",
            failure={"code": "model_request_failed"},
        )

    result = store.execute_or_resume(key, producer)
    record = resolution_record(result)

    assert resolution_state(result) == "committed"
    assert record["execution_status"] == "model_error"
    assert record["failure_origin"] == "model"
    assert record["strict_success"] is False


def test_instrument_failure_forces_null_strict_success_even_if_graded(tmp_path):
    store = make_store(tmp_path)
    key = make_key(task_version="runner-failure")

    def producer(writer):
        write_complete_evidence(
            writer,
            strict_success=False,
            execution_status="runner_error",
            failure_origin="runner",
            failure={"code": "worker_crashed"},
        )

    result = store.execute_or_resume(key, producer)
    record = resolution_record(result)

    assert resolution_state(result) == "committed"
    assert record["execution_status"] == "runner_error"
    assert record["failure_origin"] == "runner"
    assert record["grader_status"] == "graded"
    assert record["strict_success"] is None


@pytest.mark.parametrize(
    (
        "execution_status",
        "failure_origin",
        "failure",
        "candidate_decision",
    ),
    [
        ("done", "model", {"code": "contradiction"}, False),
        ("done", "none", {"code": "must_be_null"}, False),
        ("model_error", "none", None, False),
        ("model_error", "model", {"code": "failed"}, True),
    ],
)
def test_incompatible_status_origin_failure_and_grade_are_rejected(
    tmp_path,
    execution_status,
    failure_origin,
    failure,
    candidate_decision,
):
    store = make_store(tmp_path)
    key = make_key(
        task_version=(
            f"invalid-{execution_status}-{failure_origin}-"
            f"{candidate_decision}"
        )
    )

    with store.locked() as session:
        writer = session.begin_attempt(key)
        write_complete_evidence(
            writer,
            strict_success=candidate_decision,
            execution_status=execution_status,
            failure_origin=failure_origin,
            failure=failure,
        )
        with pytest.raises(EvidenceIntegrityError):
            writer.commit()
        assert not (writer.path / "COMMITTED").exists()


@pytest.mark.parametrize("grader_status", ["not_run", "grader_error"])
def test_ungraded_committed_attempt_has_null_strict_success(
    tmp_path,
    grader_status,
):
    store = make_store(tmp_path)
    key = make_key(grader_version=f"status-{grader_status}")

    def producer(writer):
        write_complete_evidence(
            writer,
            strict_success=None,
            grader_status=grader_status,
        )

    result = store.execute_or_resume(key, producer)

    assert resolution_state(result) == "committed"
    record = resolution_record(result)
    assert isinstance(record, dict)
    assert record["grader_status"] == grader_status
    assert record["strict_success"] is None
    assert record["record_status"] == "committed"
    assert record["publish_status"] == "committed"


@pytest.mark.parametrize(
    ("status_field", "invalid_value"),
    [
        ("execution_status", "success"),
        ("tool_status", "unknown"),
        ("grader_status", "pending"),
    ],
)
def test_unknown_status_values_are_rejected_before_publication(
    tmp_path,
    status_field,
    invalid_value,
):
    store = make_store(tmp_path)
    key = make_key(task_version=f"invalid-{status_field}")

    with store.locked() as session:
        writer = session.begin_attempt(key)
        overrides = {status_field: invalid_value}
        write_complete_evidence(writer, **overrides)
        with pytest.raises(EvidenceIntegrityError):
            writer.commit()
        assert not (writer.path / "COMMITTED").exists()


def test_results_projection_is_deterministic_and_source_immutable(tmp_path):
    store = make_store(tmp_path)
    first = make_key(instance_id="lead-0001", instance_content_sha256=SHA_D)
    second = make_key(
        instance_id="lead-0002",
        instance_content_sha256="9" * 64,
        repeat=1,
    )
    candidates = []

    for key, success in ((second, False), (first, True)):
        def producer(writer, success=success):
            candidates.append(writer.path)
            write_complete_evidence(writer, strict_success=success)

        store.execute_or_resume(key, producer)

    before = {candidate: source_snapshot(candidate) for candidate in candidates}
    with store.locked() as session:
        first_projection = session.rebuild_results()
    first_bytes = Path(first_projection).read_bytes()
    with store.locked() as session:
        second_projection = session.rebuild_results()
    second_bytes = Path(second_projection).read_bytes()

    assert first_bytes == second_bytes
    assert before == {
        candidate: source_snapshot(candidate) for candidate in candidates
    }
    payload = json.loads(first_bytes)
    assert payload["schema_version"] == "brick.evidence-results/1"
    assert payload["run_id"] == RUN_ID
    records = payload["records"]
    assert [record["logical_hash"] for record in records] == sorted(
        (first.logical_hash(), second.logical_hash())
    )
    expected_record_keys = {
        "logical_hash",
        "physical_uuid",
        "attempt_key",
        "record_status",
        "execution_status",
        "grader_status",
        "tool_status",
        "publish_status",
        "failure_origin",
        "strict_success",
        "result",
        "grade",
    }
    assert all(set(record) == expected_record_keys for record in records)
    assert "rebuild_timestamp" not in payload
    assert set(payload) == {
        "schema_version",
        "run_id",
        "run_sha256",
        "records",
    }


def test_missing_corrupt_and_stale_projection_are_rebuilt_from_evidence(tmp_path):
    store = make_store(tmp_path)
    key = make_key()

    def producer(writer):
        write_complete_evidence(writer)

    result = store.execute_or_resume(key, producer)
    record = resolution_record(result)
    candidate = (
        Path(record["candidate_path"])
        if record is not None and "candidate_path" in record
        else next(
            (tmp_path / "runs" / RUN_ID / "attempts" / key.logical_hash()).iterdir()
        )
    )
    before = source_snapshot(candidate)
    projection = tmp_path / "runs" / RUN_ID / "results.json"
    run_sha256 = hashlib.sha256(
        (tmp_path / "runs" / RUN_ID / "run.json").read_bytes()
    ).hexdigest()
    stale = json.dumps(
        {
            "schema_version": "brick.evidence-results/1",
            "run_id": RUN_ID,
            "run_sha256": run_sha256,
            "records": [],
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    for invalid in (
        None,
        b"{not-json",
        stale,
    ):
        if invalid is None:
            projection.unlink(missing_ok=True)
        else:
            projection.write_bytes(invalid)
        with store.locked() as session:
            rebuilt = session.rebuild_results()
        payload = json.loads(Path(rebuilt).read_text("utf-8"))
        assert len(payload["records"]) == 1
        assert payload["records"][0]["logical_hash"] == key.logical_hash()
        assert source_snapshot(candidate) == before


def test_projection_rebuild_failure_never_publishes_a_partial_projection(
    tmp_path,
):
    store = make_store(tmp_path)
    first = make_key()
    second = make_key(
        instance_id="lead-0002",
        instance_content_sha256="9" * 64,
    )
    candidates = []

    for key in (first, second):
        def producer(writer):
            candidates.append(writer.path)
            write_complete_evidence(writer)

        store.execute_or_resume(key, producer)

    with store.locked() as session:
        projection = Path(session.rebuild_results())
    valid_projection = projection.read_bytes()
    with (candidates[1] / "result.json").open("ab") as handle:
        handle.write(b"tamper")

    with store.locked() as session:
        with pytest.raises(EvidenceIntegrityError):
            session.rebuild_results()

    assert projection.read_bytes() == valid_projection


def test_projection_never_treats_uncommitted_candidate_as_a_result(tmp_path):
    store = make_store(tmp_path)
    committed_key = make_key()
    abandoned_key = make_key(
        instance_id="lead-abandoned",
        instance_content_sha256="8" * 64,
    )

    def producer(writer):
        write_complete_evidence(writer)

    store.execute_or_resume(committed_key, producer)
    with store.locked() as session:
        abandoned = session.begin_attempt(abandoned_key)
        abandoned.write_bytes("transcript.md", b"partial")
        projection = session.rebuild_results()

    logical_hashes = {
        record["logical_hash"]
        for record in json.loads(Path(projection).read_text("utf-8"))["records"]
    }
    assert logical_hashes == {committed_key.logical_hash()}
