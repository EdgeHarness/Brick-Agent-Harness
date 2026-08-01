import errno
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest

from harness import evidence


WORKER = Path(__file__).with_name("s4_recovery_worker.py")
FAULT_EXIT = 91
LOCKED_EXIT = 73

HARD_EXIT_BOUNDARIES = (
    "candidate_created",
    "attempt_written",
    "initial_state_written",
    "final_state_written",
    "result_written",
    "grade_written",
    "actions_written",
    "transcript_written",
    "memory_written",
    "artifact_written",
    "prepared_written",
    "before_committed",
    "after_committed",
    "projection_temp_written",
    "before_projection_replace",
    "after_projection_replace",
)

ABANDONED_AFTER_PRODUCER = frozenset(
    {
        "initial_state_written",
        "final_state_written",
        "result_written",
        "grade_written",
        "actions_written",
        "transcript_written",
        "memory_written",
        "artifact_written",
    }
)
ABANDONED_BEFORE_PRODUCER = frozenset(
    {"candidate_created", "attempt_written"}
)
RECOVERABLE_WITHOUT_PRODUCER = frozenset(
    {
        "prepared_written",
        "before_committed",
        "after_committed",
        "projection_temp_written",
        "before_projection_replace",
        "after_projection_replace",
    }
)
PROJECTION_BOUNDARIES = frozenset(
    {
        "projection_temp_written",
        "before_projection_replace",
        "after_projection_replace",
    }
)


def make_key(**changes):
    values = {
        "domain_name": "brix_synthetic",
        "domain_version": "1.0.0",
        "domain_content_sha256": "a" * 64,
        "task_family": "lead_followup",
        "task_version": "1.0.0",
        "generator_version": "1.0.0",
        "grader_version": "1.0.0",
        "model_tag": "qwen3.5:4b",
        "model_digest": "sha256:" + "b" * 64,
        "condition_name": "harness_full",
        "condition_version": "1.0.0",
        "mechanism_sha256": "c" * 64,
        "instance_id": "lead-recovery",
        "instance_content_sha256": "d" * 64,
        "ordered_subepisodes": ("draft", "approve"),
        "repeat": 0,
        "sampling": {"seed": 17, "temperature": "0"},
        "opportunity_budget": {"model_calls": 4, "tool_calls": 12},
        "prompt_sha256": "e" * 64,
        "tool_schema_sha256": "f" * 64,
    }
    values.update(changes)
    return evidence.AttemptKey(**values)


def create_store(tmp_path, run_id="recovery-run"):
    return evidence.EvidenceStore.create_run(
        tmp_path / "runs",
        run_id,
        {
            "candidate_commit": "1" * 40,
            "protocol_sha256": "2" * 64,
        },
    )


def write_complete_evidence(writer):
    writer.write_json(
        "initial-state.json",
        {
            "schema_version": "brick.evidence-state/1",
            "state_kind": "initial",
            "payload": {"counter": 0},
        },
    )
    writer.write_json(
        "final-state.json",
        {
            "schema_version": "brick.evidence-state/1",
            "state_kind": "final",
            "payload": {"counter": 1},
        },
    )
    writer.write_json(
        "result.json",
        {
            "schema_version": "brick.evidence-result/1",
            "execution_status": "done",
            "tool_status": "clean",
            "failure_origin": "none",
            "failure": None,
            "metrics": {"model_calls": 1, "tool_calls": 1},
            "diagnostics": [],
        },
    )
    writer.write_json(
        "grade.json",
        {
            "schema_version": "brick.evidence-grade/1",
            "grader_status": "graded",
            "candidate_decision": True,
            "diagnostics": [],
        },
    )
    writer.write_json(
        "actions.json",
        {
            "schema_version": "brick.evidence-actions/1",
            "actions": [{"ok": True, "tool": "recovery_probe"}],
        },
    )
    writer.write_bytes("transcript.md", b"# Recovery probe\n")
    writer.write_bytes(
        "memory-delta.jsonl",
        b'{"delta":[],"schema_version":"brick.memory-delta/1"}\n',
    )
    writer.write_bytes(
        "artifacts/recovery.txt",
        b"recovery artifact\n",
    )


def append_counter(path):
    with Path(path).open("ab") as handle:
        handle.write(b"producer\n")
        handle.flush()
        os.fsync(handle.fileno())


def counter_value(path):
    path = Path(path)
    return 0 if not path.exists() else len(path.read_bytes().splitlines())


def write_key_file(tmp_path, key, name="attempt-key.json"):
    path = tmp_path / name
    path.write_bytes(key.canonical_bytes())
    return path


def worker_command(
    store,
    key_file,
    counter,
    *,
    boundary="none",
    producer_delay=0.0,
):
    return [
        sys.executable,
        str(WORKER),
        "--runs-root",
        str(store.runs_root),
        "--run-id",
        store.run_id,
        "--key-file",
        str(key_file),
        "--counter",
        str(counter),
        "--boundary",
        boundary,
        "--producer-delay",
        str(producer_delay),
    ]


def target_candidates(store, key):
    logical = store.attempts_dir / key.logical_hash
    return [] if not logical.exists() else sorted(logical.iterdir())


def projection(store):
    return json.loads((store.run_dir / evidence.RESULTS).read_text("utf-8"))


@pytest.mark.parametrize("boundary", HARD_EXIT_BOUNDARIES)
def test_hard_process_exit_recovers_fail_closed_without_duplicate_execution(
    tmp_path,
    boundary,
):
    store = create_store(tmp_path)
    key = make_key()
    key_file = write_key_file(tmp_path, key)
    counter = tmp_path / "producer-calls.log"
    baseline_projection = None
    baseline_count = 0

    if boundary in PROJECTION_BOUNDARIES:
        baseline_key = make_key(
            instance_id="lead-baseline",
            instance_content_sha256="9" * 64,
        )

        def baseline_producer(writer):
            write_complete_evidence(writer)

        baseline = store.execute_or_resume(
            baseline_key,
            baseline_producer,
        )
        assert baseline.state == "committed"
        baseline_projection = (
            store.run_dir / evidence.RESULTS
        ).read_bytes()
        baseline_count = 1

    completed = subprocess.run(
        worker_command(
            store,
            key_file,
            counter,
            boundary=boundary,
        ),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == FAULT_EXIT, completed.stderr[-1000:]
    candidates_before = target_candidates(store, key)
    assert len(candidates_before) == 1

    if boundary in {
        "projection_temp_written",
        "before_projection_replace",
    }:
        assert (store.run_dir / evidence.RESULTS).read_bytes() == (
            baseline_projection
        )
        assert (store.run_dir / evidence.RESULTS_TEMP).is_file()
    elif boundary == "after_projection_replace":
        assert len(projection(store)["records"]) == 2
        assert not (store.run_dir / evidence.RESULTS_TEMP).exists()

    recovery_calls = []

    def recovery_producer(writer):
        recovery_calls.append(writer.path)
        append_counter(counter)
        write_complete_evidence(writer)

    recovered = store.execute_or_resume(key, recovery_producer)

    assert recovered.state == "committed"
    assert recovered.record["record_status"] == "committed"
    assert recovered.record["publish_status"] == "committed"
    assert len(projection(store)["records"]) == baseline_count + 1
    assert not (store.run_dir / evidence.RESULTS_TEMP).exists()

    if boundary in RECOVERABLE_WITHOUT_PRODUCER:
        assert recovered.producer_called is False
        assert recovery_calls == []
        assert counter_value(counter) == 1
        assert len(target_candidates(store, key)) == 1
    elif boundary in ABANDONED_BEFORE_PRODUCER:
        assert recovered.producer_called is True
        assert counter_value(counter) == 1
        assert len(target_candidates(store, key)) == 2
    else:
        assert boundary in ABANDONED_AFTER_PRODUCER
        assert recovered.producer_called is True
        assert counter_value(counter) == 2
        assert len(target_candidates(store, key)) == 2

    committed = [
        candidate
        for candidate in target_candidates(store, key)
        if (candidate / evidence.COMMITTED).exists()
    ]
    assert committed == [recovered.candidate_path]


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.delays = []

    def __call__(self):
        return self.now

    def sleep(self, delay):
        self.delays.append(delay)
        self.now += delay


def sharing_violation(winerror=32):
    error = OSError(errno.EACCES, "simulated Windows sharing violation")
    error.winerror = winerror
    return error


def test_retry_delay_sequence_is_exact(monkeypatch):
    clock = FakeClock()
    calls = []

    def operation():
        calls.append("call")
        if len(calls) <= 9:
            raise sharing_violation()
        return "complete"

    monkeypatch.setattr(
        evidence,
        "_is_retryable_publication_error",
        lambda exc: getattr(exc, "winerror", None) in {5, 32, 33},
    )
    completed, value = evidence._retry_idempotent(
        operation,
        deadline_at=100.0,
        clock=clock,
        sleeper=clock.sleep,
    )

    assert completed is True
    assert value == "complete"
    assert len(calls) == 10
    assert clock.delays == [
        0.0,
        0.05,
        0.1,
        0.2,
        0.4,
        0.8,
        1.6,
        2.0,
        2.0,
    ]
    assert clock.now == pytest.approx(7.15)


def test_prepare_and_publish_share_one_monotonic_deadline(
    monkeypatch,
    tmp_path,
):
    store = create_store(tmp_path)
    key = make_key()
    clock = FakeClock()

    with store.locked() as session:
        writer = session.begin_attempt(key)
        write_complete_evidence(writer)
        real_validate = evidence.validate_prepared
        real_marker = evidence._create_commit_marker
        validation_calls = []

        def transient_initial_validation(*args, **kwargs):
            validation_calls.append("call")
            if len(validation_calls) <= 2:
                raise sharing_violation()
            return real_validate(*args, **kwargs)

        def persistently_blocked_marker(_candidate):
            raise sharing_violation()

        monkeypatch.setattr(
            evidence,
            "_is_retryable_publication_error",
            lambda exc: getattr(exc, "winerror", None) in {5, 32, 33},
        )
        monkeypatch.setattr(
            evidence,
            "validate_prepared",
            transient_initial_validation,
        )
        monkeypatch.setattr(
            evidence,
            "_create_commit_marker",
            persistently_blocked_marker,
        )

        blocked = writer.commit(
            deadline_seconds=1.0,
            clock=clock,
            sleeper=clock.sleep,
        )

        assert blocked.state == "publish_blocked"
        assert clock.now == pytest.approx(1.0)
        assert clock.delays == pytest.approx(
            [0.0, 0.05, 0.0, 0.05, 0.1, 0.2, 0.4, 0.2]
        )
        assert (writer.path / evidence.PREPARED).is_file()
        assert not (writer.path / evidence.COMMITTED).exists()

        monkeypatch.setattr(evidence, "validate_prepared", real_validate)
        monkeypatch.setattr(
            evidence,
            "_create_commit_marker",
            real_marker,
        )
        adopted = session.resolve(key)

    assert adopted.state == "committed"
    assert adopted.candidate_path == writer.path


def test_new_producer_publication_block_returns_without_projection_or_rerun(
    monkeypatch,
    tmp_path,
):
    store = create_store(tmp_path)
    key = make_key(instance_id="producer-side-publish-block")
    producer_calls = []
    real_marker = evidence._create_commit_marker

    def producer(writer):
        producer_calls.append(writer.path)
        write_complete_evidence(writer)

    def blocked_marker(_candidate):
        raise sharing_violation()

    monkeypatch.setattr(
        evidence,
        "_is_retryable_publication_error",
        lambda exc: getattr(exc, "winerror", None) in {5, 32, 33},
    )
    monkeypatch.setattr(evidence, "_create_commit_marker", blocked_marker)

    blocked = store.execute_or_resume(
        key,
        producer,
        deadline_seconds=0,
    )

    assert blocked.state == "publish_blocked"
    assert blocked.producer_called is True
    assert producer_calls == [blocked.candidate_path]
    assert (blocked.candidate_path / evidence.PREPARED).is_file()
    assert not (blocked.candidate_path / evidence.COMMITTED).exists()
    assert not (store.run_dir / evidence.RESULTS).exists()

    monkeypatch.setattr(evidence, "_create_commit_marker", real_marker)
    resumed = store.execute_or_resume(key, producer)

    assert resumed.state == "committed"
    assert resumed.producer_called is False
    assert producer_calls == [blocked.candidate_path]


def test_corrupt_uncommitted_prepared_is_abandoned_and_reexecuted_once(
    tmp_path,
):
    store = create_store(tmp_path)
    key = make_key(instance_id="corrupt-uncommitted-prepared")

    def first_producer(writer):
        write_complete_evidence(writer)

    first = store.execute_or_resume(key, first_producer)
    corrupt_candidate = first.candidate_path
    (corrupt_candidate / evidence.COMMITTED).unlink()
    (corrupt_candidate / evidence.PREPARED).write_bytes(b"{corrupt")

    with store.locked() as session:
        inspected = session.inspect(key)
    assert inspected.state == "abandoned"
    assert inspected.candidate_path == corrupt_candidate

    producer_calls = []

    def recovery_producer(writer):
        producer_calls.append(writer.path)
        write_complete_evidence(writer)

    recovered = store.execute_or_resume(key, recovery_producer)

    assert recovered.state == "committed"
    assert recovered.producer_called is True
    assert producer_calls == [recovered.candidate_path]
    assert recovered.candidate_path != corrupt_candidate
    assert (corrupt_candidate / evidence.PREPARED).read_bytes() == b"{corrupt"
    assert not (corrupt_candidate / evidence.COMMITTED).exists()
    assert len(target_candidates(store, key)) == 2


@pytest.mark.parametrize("committed", [False, True])
def test_semantically_invalid_canonical_prepared_uses_integrity_boundary(
    tmp_path,
    committed,
):
    store = create_store(tmp_path)
    key = make_key(
        instance_id=(
            "invalid-prepared-committed"
            if committed
            else "invalid-prepared-uncommitted"
        )
    )

    def first_producer(writer):
        write_complete_evidence(writer)

    first = store.execute_or_resume(key, first_producer)
    candidate = first.candidate_path
    if not committed:
        (candidate / evidence.COMMITTED).unlink()
    prepared_path = candidate / evidence.PREPARED
    manifest = json.loads(prepared_path.read_text("utf-8"))
    manifest["run_id"] = ".."
    prepared_path.write_bytes(
        evidence.canonical_json_bytes(manifest, newline=True)
    )

    if committed:
        with store.locked() as session:
            with pytest.raises(evidence.EvidenceIntegrityError):
                session.inspect(key)
        return

    with store.locked() as session:
        inspected = session.inspect(key)
    assert inspected.state == "abandoned"
    assert inspected.candidate_path == candidate

    producer_calls = []

    def recovery_producer(writer):
        producer_calls.append(writer.path)
        write_complete_evidence(writer)

    recovered = store.execute_or_resume(key, recovery_producer)
    assert recovered.state == "committed"
    assert recovered.producer_called is True
    assert producer_calls == [recovered.candidate_path]
    assert recovered.candidate_path != candidate
    assert not (candidate / evidence.COMMITTED).exists()


def test_retryable_attempt_identity_read_exhaustion_never_reruns_producer(
    monkeypatch,
    tmp_path,
):
    store = create_store(tmp_path)
    key = make_key(instance_id="attempt-read-blocked")
    producer_calls = []

    def producer(writer):
        producer_calls.append(writer.path)
        write_complete_evidence(writer)

    initial = store.execute_or_resume(key, producer)
    (initial.candidate_path / evidence.COMMITTED).unlink()
    real_read = evidence.RunSession._candidate_key_if_present

    def blocked_read(_session, _candidate):
        raise sharing_violation()

    monkeypatch.setattr(
        evidence,
        "_is_retryable_publication_error",
        lambda exc: getattr(exc, "winerror", None) in {5, 32, 33},
    )
    monkeypatch.setattr(
        evidence.RunSession,
        "_candidate_key_if_present",
        blocked_read,
    )

    blocked = store.execute_or_resume(
        key,
        producer,
        deadline_seconds=0,
    )

    assert blocked.state == "publish_blocked"
    assert blocked.producer_called is False
    assert producer_calls == [initial.candidate_path]

    monkeypatch.setattr(
        evidence.RunSession,
        "_candidate_key_if_present",
        real_read,
    )
    recovered = store.execute_or_resume(key, producer)

    assert recovered.state == "committed"
    assert recovered.producer_called is False
    assert producer_calls == [initial.candidate_path]


def test_transient_winerror_marker_failures_are_retried(
    monkeypatch,
    tmp_path,
):
    store = create_store(tmp_path)
    key = make_key()
    clock = FakeClock()

    with store.locked() as session:
        writer = session.begin_attempt(key)
        write_complete_evidence(writer)
        real_marker = evidence._create_commit_marker
        calls = []

        def transient_marker(candidate):
            calls.append("call")
            if len(calls) <= 3:
                raise sharing_violation()
            return real_marker(candidate)

        monkeypatch.setattr(
            evidence,
            "_is_retryable_publication_error",
            lambda exc: getattr(exc, "winerror", None) in {5, 32, 33},
        )
        monkeypatch.setattr(
            evidence,
            "_create_commit_marker",
            transient_marker,
        )
        result = writer.commit(
            deadline_seconds=5.0,
            clock=clock,
            sleeper=clock.sleep,
        )

    assert result.state == "committed"
    assert len(calls) == 4
    assert clock.delays == [0.0, 0.05, 0.1]


def test_windows_retryable_error_classification_is_exact(monkeypatch):
    monkeypatch.setattr(evidence.os, "name", "nt")

    for code in (5, 32, 33):
        assert evidence._is_retryable_publication_error(
            sharing_violation(code)
        )
    for code in (2, 87):
        assert not evidence._is_retryable_publication_error(
            sharing_violation(code)
        )

    nonretryable = OSError(errno.EINVAL, "invalid operation")
    nonretryable.winerror = None
    assert not evidence._is_retryable_publication_error(nonretryable)


def test_existing_marker_is_inspected_instead_of_blindly_accepted(
    monkeypatch,
    tmp_path,
):
    store = create_store(tmp_path)
    key = make_key()

    with store.locked() as session:
        writer = session.begin_attempt(key)
        write_complete_evidence(writer)
        first = writer.commit()

        def marker_must_not_be_called(_candidate):
            raise AssertionError("existing marker must be inspected")

        monkeypatch.setattr(
            evidence,
            "_create_commit_marker",
            marker_must_not_be_called,
        )
        second = writer.commit()

        assert first.state == second.state == "committed"
        assert first.record == second.record

        with (writer.path / "grade.json").open("ab") as handle:
            handle.write(b"tamper")
        with pytest.raises(evidence.EvidenceIntegrityError):
            writer.commit()


@pytest.mark.parametrize("marker_is_valid", [True, False])
def test_file_exists_during_marker_creation_requires_state_validation(
    monkeypatch,
    tmp_path,
    marker_is_valid,
):
    store = create_store(tmp_path)
    key = make_key()

    with store.locked() as session:
        writer = session.begin_attempt(key)
        write_complete_evidence(writer)
        real_marker = evidence._create_commit_marker

        def raced_marker(candidate):
            if marker_is_valid:
                real_marker(candidate)
            else:
                (Path(candidate) / evidence.COMMITTED).write_bytes(b"invalid")
            raise FileExistsError("simulated publication race")

        monkeypatch.setattr(
            evidence,
            "_create_commit_marker",
            raced_marker,
        )
        if marker_is_valid:
            result = writer.commit()
            assert result.state == "committed"
        else:
            with pytest.raises(evidence.EvidenceIntegrityError):
                writer.commit()


def test_uuid_collision_never_reuses_or_overwrites_a_candidate(
    monkeypatch,
    tmp_path,
):
    store = create_store(tmp_path)
    key = make_key()

    with store.locked() as session:
        first = session.begin_attempt(key)
        first.write_bytes("transcript.md", b"first candidate")
        before = {
            path.relative_to(first.path).as_posix(): path.read_bytes()
            for path in first.path.rglob("*")
            if path.is_file()
        }
        monkeypatch.setattr(
            evidence.uuid,
            "uuid4",
            lambda: uuid.UUID(first.path.name),
        )

        with pytest.raises(FileExistsError):
            session.begin_attempt(key)

    after = {
        path.relative_to(first.path).as_posix(): path.read_bytes()
        for path in first.path.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert len(target_candidates(store, key)) == 1


def test_concurrent_process_execute_invokes_exactly_one_producer(tmp_path):
    store = create_store(tmp_path)
    key = make_key()
    key_file = write_key_file(tmp_path, key)
    counter = tmp_path / "concurrent-producers.log"
    command = worker_command(
        store,
        key_file,
        counter,
        producer_delay=0.75,
    )

    first = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 10.0
    while counter_value(counter) == 0 and time.monotonic() < deadline:
        if first.poll() is not None:
            break
        time.sleep(0.02)
    assert counter_value(counter) == 1
    assert first.poll() is None

    second = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    first_stdout, first_stderr = first.communicate(timeout=20)

    assert first.returncode == 0, first_stderr[-1000:]
    assert second.returncode == LOCKED_EXIT, second.stderr[-1000:]
    assert json.loads(first_stdout)["producer_called"] is True
    assert counter_value(counter) == 1

    def forbidden_producer(_writer):
        raise AssertionError("committed concurrent work must be reused")

    recovered = store.execute_or_resume(key, forbidden_producer)

    assert recovered.state == "committed"
    assert recovered.producer_called is False
    assert counter_value(counter) == 1
    assert len(target_candidates(store, key)) == 1
    assert len(projection(store)["records"]) == 1
