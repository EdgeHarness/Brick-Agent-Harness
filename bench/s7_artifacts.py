"""Small marker-last store for immutable S7 decision artifacts."""

import hashlib
import json
import os
from pathlib import Path
import stat

from harness.evidence import canonical_json_bytes


class S7ArtifactError(RuntimeError):
    """An S7 decision artifact is incomplete, mutable, or malformed."""


def _is_reparse(metadata):
    marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(metadata, "st_file_attributes", 0) & marker)


def _require_plain(path, directory=False):
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise S7ArtifactError("cannot inspect S7 artifact member") from exc
    expected = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(
        metadata.st_mode
    )
    if not expected or stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
        raise S7ArtifactError("S7 artifacts cannot contain links or reparse points")


def _write_new(path, payload):
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def commit_artifact(directory, document):
    directory = Path(directory)
    payload = canonical_json_bytes(document, allow_float=False, newline=True)
    if os.path.lexists(str(directory)):
        existing = verify_artifact(directory)
        if existing["document"] != document:
            raise S7ArtifactError("committed S7 artifact has different content")
        return existing
    directory.mkdir(parents=True, exist_ok=False)
    digest = hashlib.sha256(payload).hexdigest()
    _write_new(directory / "artifact.json", payload)
    prepared = {
        "schema_version": "brick.s7.artifact-prepared/1",
        "artifact_sha256": digest,
        "size_bytes": len(payload),
    }
    _write_new(
        directory / "PREPARED.json",
        canonical_json_bytes(prepared, newline=True),
    )
    _write_new(directory / "COMMITTED", b"")
    return verify_artifact(directory)


def verify_artifact(directory, expected_schema=None):
    directory = Path(directory)
    _require_plain(directory, directory=True)
    expected = {"artifact.json", "PREPARED.json", "COMMITTED"}
    try:
        entries = {entry.name for entry in directory.iterdir()}
    except OSError as exc:
        raise S7ArtifactError("cannot inspect S7 artifact") from exc
    if entries != expected:
        raise S7ArtifactError("S7 artifact members differ")
    for name in expected:
        _require_plain(directory / name)
    if (directory / "COMMITTED").read_bytes() != b"":
        raise S7ArtifactError("S7 commit marker must be empty")
    try:
        prepared_bytes = (directory / "PREPARED.json").read_bytes()
        prepared = json.loads(prepared_bytes.decode("utf-8"))
        payload = (directory / "artifact.json").read_bytes()
        document = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise S7ArtifactError("cannot decode S7 artifact") from exc
    if prepared != {
        "schema_version": "brick.s7.artifact-prepared/1",
        "artifact_sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }:
        raise S7ArtifactError("S7 prepared binding differs")
    if canonical_json_bytes(prepared, newline=True) != prepared_bytes:
        raise S7ArtifactError("S7 prepared document is not canonical")
    if canonical_json_bytes(document, allow_float=False, newline=True) != payload:
        raise S7ArtifactError("S7 artifact document is not canonical")
    if expected_schema is not None and document.get("schema_version") != expected_schema:
        raise S7ArtifactError("S7 artifact schema differs")
    return {
        "document": document,
        "artifact_sha256": prepared["artifact_sha256"],
    }


__all__ = ["S7ArtifactError", "commit_artifact", "verify_artifact"]
