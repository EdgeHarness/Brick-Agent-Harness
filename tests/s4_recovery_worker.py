"""Non-collected subprocess worker for S4 recovery and locking tests."""

import argparse
import json
import os
from pathlib import Path
import sys
import time


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from harness import evidence  # noqa: E402


FAULT_EXIT = 91
LOCKED_EXIT = 73

BOUNDARIES = frozenset(
    {
        "none",
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
    }
)


def _hard_exit():
    os._exit(FAULT_EXIT)


def _install_fault(boundary):
    if boundary in {"candidate_created", "attempt_written"}:
        real_write_bytes = evidence._write_bytes

        def write_bytes(path, payload, exclusive=True):
            name = Path(path).name
            if name == "attempt.json" and boundary == "candidate_created":
                _hard_exit()
            result = real_write_bytes(
                path,
                payload,
                exclusive=exclusive,
            )
            if name == "attempt.json" and boundary == "attempt_written":
                _hard_exit()
            return result

        evidence._write_bytes = write_bytes

    if boundary == "prepared_written":
        real_write_json = evidence._write_json

        def write_json(path, value, exclusive=True):
            name = Path(path).name
            result = real_write_json(
                path,
                value,
                exclusive=exclusive,
            )
            if name == evidence.PREPARED:
                _hard_exit()
            return result

        evidence._write_json = write_json

    if boundary in {"before_committed", "after_committed"}:
        real_marker = evidence._create_commit_marker

        def create_commit_marker(candidate):
            if boundary == "before_committed":
                _hard_exit()
            result = real_marker(candidate)
            if boundary == "after_committed":
                _hard_exit()
            return result

        evidence._create_commit_marker = create_commit_marker

    if boundary == "projection_temp_written":
        real_write_bytes = evidence._write_bytes

        def write_bytes(path, payload, exclusive=True):
            result = real_write_bytes(
                path,
                payload,
                exclusive=exclusive,
            )
            if Path(path).name == evidence.RESULTS_TEMP:
                _hard_exit()
            return result

        evidence._write_bytes = write_bytes

    if boundary in {
        "before_projection_replace",
        "after_projection_replace",
    }:
        real_replace = evidence.os.replace

        def replace(source, destination):
            if (
                Path(destination).name == evidence.RESULTS
                and boundary == "before_projection_replace"
            ):
                _hard_exit()
            result = real_replace(source, destination)
            if (
                Path(destination).name == evidence.RESULTS
                and boundary == "after_projection_replace"
            ):
                _hard_exit()
            return result

        evidence.os.replace = replace


def _append_counter(path):
    path = Path(path)
    with path.open("ab") as handle:
        handle.write(b"producer\n")
        handle.flush()
        os.fsync(handle.fileno())


def _producer(boundary, counter, delay_seconds):
    def produce(writer):
        _append_counter(counter)
        if delay_seconds:
            time.sleep(delay_seconds)

        writer.write_json(
            "initial-state.json",
            {
                "schema_version": "brick.evidence-state/1",
                "state_kind": "initial",
                "payload": {"counter": 0},
            },
        )
        if boundary == "initial_state_written":
            _hard_exit()

        writer.write_json(
            "final-state.json",
            {
                "schema_version": "brick.evidence-state/1",
                "state_kind": "final",
                "payload": {"counter": 1},
            },
        )
        if boundary == "final_state_written":
            _hard_exit()

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
        if boundary == "result_written":
            _hard_exit()

        writer.write_json(
            "grade.json",
            {
                "schema_version": "brick.evidence-grade/1",
                "grader_status": "graded",
                "candidate_decision": True,
                "diagnostics": [],
            },
        )
        if boundary == "grade_written":
            _hard_exit()

        writer.write_json(
            "actions.json",
            {
                "schema_version": "brick.evidence-actions/1",
                "actions": [{"ok": True, "tool": "recovery_probe"}],
            },
        )
        if boundary == "actions_written":
            _hard_exit()

        writer.write_bytes("transcript.md", b"# Recovery probe\n")
        if boundary == "transcript_written":
            _hard_exit()

        writer.write_bytes(
            "memory-delta.jsonl",
            b'{"delta":[],"schema_version":"brick.memory-delta/1"}\n',
        )
        if boundary == "memory_written":
            _hard_exit()

        writer.write_bytes(
            "artifacts/recovery.txt",
            b"recovery artifact\n",
        )
        if boundary == "artifact_written":
            _hard_exit()

    return produce


def _parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--counter", required=True)
    parser.add_argument("--boundary", choices=sorted(BOUNDARIES), default="none")
    parser.add_argument("--producer-delay", type=float, default=0.0)
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    key_document = json.loads(
        Path(args.key_file).read_text(encoding="utf-8")
    )
    key = evidence.AttemptKey.from_dict(key_document)
    store = evidence.EvidenceStore.open_run(args.runs_root, args.run_id)
    _install_fault(args.boundary)
    try:
        resolution = store.execute_or_resume(
            key,
            _producer(
                args.boundary,
                args.counter,
                args.producer_delay,
            ),
        )
    except evidence.RunLockedError:
        return LOCKED_EXIT
    sys.stdout.write(
        json.dumps(
            {
                "state": resolution.state,
                "producer_called": resolution.producer_called,
                "candidate_path": str(resolution.candidate_path),
            },
            sort_keys=True,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
