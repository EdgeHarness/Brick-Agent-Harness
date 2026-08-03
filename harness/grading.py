"""Deterministic, versioned grading over immutable attempt snapshots.

Graders never receive a live world, memory store, or writable path. The runtime
first copies JSON state, actions, memory, and artifact bytes into a
``GradingEvidence`` value. A grader exception is an instrument failure with a
null candidate decision; it is never converted into a model failure.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType
import unicodedata

from .evidence import canonical_json_bytes


_GRADER_ID = re.compile(r"^[a-z][a-z0-9_.-]*$")
_CHECK_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-(?:[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)
_WINDOWS_FORBIDDEN = frozenset('<>:"|?*')


class GradingError(Exception):
    """The grading instrument could not produce a candidate decision."""


def _json_copy(value, label):
    try:
        return canonical_json_bytes(value)
    except (TypeError, ValueError) as exc:
        raise GradingError(f"{label} is not canonical JSON: {exc}") from exc


def _decode(payload, label):
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise GradingError(f"{label} is corrupt: {exc}") from exc
    if _json_copy(value, label) != payload:
        raise GradingError(f"{label} bytes are not canonical JSON")
    return value


def _portable_artifact_name(relative):
    if not relative or "\\" in relative:
        raise GradingError("artifact path is empty or noncanonical")
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise GradingError("artifact path can traverse")
    for part in parts:
        if unicodedata.normalize("NFC", part) != part:
            raise GradingError("artifact path is not NFC-normalized")
        if (
            part.endswith((" ", "."))
            or part.split(".", 1)[0].casefold() in _WINDOWS_RESERVED
            or any(character in _WINDOWS_FORBIDDEN for character in part)
            or any(ord(character) < 32 for character in part)
        ):
            raise GradingError("artifact path is not portable")
    return relative


def _artifact_bytes(root):
    root = Path(root)
    if not os.path.lexists(str(root)):
        return ()
    root_stat = root.lstat()
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if (
        not stat.S_ISDIR(root_stat.st_mode)
        or stat.S_ISLNK(root_stat.st_mode)
        or getattr(root_stat, "st_file_attributes", 0) & reparse
    ):
        raise GradingError("artifact root is not a regular directory")
    found = []

    def visit(directory, prefix=""):
        entries = sorted(os.scandir(str(directory)), key=lambda item: item.name)
        for entry in entries:
            relative = entry.name if not prefix else prefix + "/" + entry.name
            _portable_artifact_name(relative)
            info = entry.stat(follow_symlinks=False)
            if (
                stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & reparse
            ):
                raise GradingError(
                    f"artifact {relative!r} is a link or reparse point"
                )
            if stat.S_ISDIR(info.st_mode):
                visit(entry.path, relative)
            elif stat.S_ISREG(info.st_mode):
                found.append((relative, Path(entry.path).read_bytes()))
            else:
                raise GradingError(f"artifact {relative!r} is irregular")

    visit(root)
    folded = {}
    for name, _payload in found:
        key = name.casefold()
        if key in folded and folded[key] != name:
            raise GradingError("artifact paths collide across supported hosts")
        folded[key] = name
    return tuple(found)


@dataclass(frozen=True)
class ArtifactEvidence:
    name: str
    payload: bytes
    sha256: str

    @classmethod
    def from_bytes(cls, name, payload):
        if not isinstance(payload, bytes):
            raise TypeError("artifact payload must be bytes")
        return cls(
            _portable_artifact_name(name),
            bytes(payload),
            hashlib.sha256(payload).hexdigest(),
        )


@dataclass(frozen=True)
class GradingEvidence:
    domain: str
    domain_version: str
    task_id: str
    state_json: bytes
    actions_json: bytes
    memory_json: bytes
    artifacts: tuple

    @classmethod
    def capture(cls, attempt, task_id):
        state = attempt.domain.capture_grading_state(attempt)
        artifacts = tuple(
            ArtifactEvidence.from_bytes(name, payload)
            for name, payload in _artifact_bytes(attempt.artifact_dir)
        )
        return cls(
            domain=attempt.domain.name,
            domain_version=attempt.domain.version,
            task_id=task_id,
            state_json=_json_copy(state, "grading state"),
            actions_json=_json_copy(attempt.actions, "action evidence"),
            memory_json=_json_copy(attempt.memory.all(), "memory evidence"),
            artifacts=artifacts,
        )

    @classmethod
    def from_values(
        cls,
        *,
        domain,
        domain_version,
        task_id,
        state,
        actions=(),
        memory=(),
        artifacts=(),
    ):
        return cls(
            domain=domain,
            domain_version=domain_version,
            task_id=task_id,
            state_json=_json_copy(state, "grading state"),
            actions_json=_json_copy(list(actions), "action evidence"),
            memory_json=_json_copy(list(memory), "memory evidence"),
            artifacts=tuple(
                ArtifactEvidence.from_bytes(name, payload)
                for name, payload in artifacts
            ),
        )

    @property
    def state(self):
        return _decode(self.state_json, "grading state")

    @property
    def actions(self):
        return _decode(self.actions_json, "action evidence")

    @property
    def memory(self):
        return _decode(self.memory_json, "memory evidence")

    def artifact_map(self):
        return MappingProxyType(
            {item.name: item.payload for item in self.artifacts}
        )


@dataclass(frozen=True)
class GradeOutcome:
    grader_id: str
    grader_version: str
    grader_status: str
    candidate_decision: object
    checks: tuple
    error: object = None

    @property
    def strict_success(self):
        return (
            self.candidate_decision
            if self.grader_status == "graded"
            else None
        )

    @property
    def diagnostic_fraction(self):
        if self.grader_status != "graded":
            return None
        return sum(ok for _key, _description, ok in self.checks) / len(
            self.checks
        )


@dataclass(frozen=True)
class GraderSpec:
    id: str
    version: str
    checks: tuple
    evaluate: object

    def __post_init__(self):
        if not isinstance(self.id, str) or not _GRADER_ID.fullmatch(self.id):
            raise ValueError("grader id is invalid")
        if not isinstance(self.version, str) or not _SEMVER.fullmatch(
            self.version
        ):
            raise ValueError("grader version is not semantic versioning")
        if not callable(self.evaluate):
            raise TypeError("grader evaluate must be callable")
        if not isinstance(self.checks, tuple) or not self.checks:
            raise ValueError("grader checks must be a nonempty tuple")
        ids = []
        for item in self.checks:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], str)
                or not _CHECK_ID.fullmatch(item[0])
                or not isinstance(item[1], str)
                or not item[1]
            ):
                raise ValueError(
                    "grader checks require (portable id, description)"
                )
            ids.append(item[0])
        if len(set(ids)) != len(ids):
            raise ValueError("grader check ids must be unique")

    def grade_evidence(self, evidence):
        descriptions = dict(self.checks)
        try:
            if not isinstance(evidence, GradingEvidence):
                raise GradingError("grader input is not GradingEvidence")
            if self.id != f"{evidence.domain}.{evidence.task_id}":
                raise GradingError("grader identity does not match its evidence")
            # Decode all JSON axes before the domain evaluator runs. This keeps
            # ignored-but-corrupt memory/action bytes from silently passing.
            evidence.state
            evidence.actions
            evidence.memory
            names = []
            for artifact in evidence.artifacts:
                if not isinstance(artifact, ArtifactEvidence):
                    raise GradingError("artifact evidence has the wrong type")
                _portable_artifact_name(artifact.name)
                if hashlib.sha256(artifact.payload).hexdigest() != artifact.sha256:
                    raise GradingError("artifact digest does not match its bytes")
                names.append(artifact.name)
            if names != sorted(names) or len({name.casefold() for name in names}) != len(names):
                raise GradingError("artifact evidence is unsorted or colliding")
            values = self.evaluate(evidence)
            if not isinstance(values, dict) or set(values) != set(
                descriptions
            ):
                raise GradingError("grader returned a non-fixed check set")
            if not all(type(value) is bool for value in values.values()):
                raise GradingError("grader checks must be booleans")
            checks = tuple(
                (key, description, values[key])
                for key, description in self.checks
            )
            return GradeOutcome(
                self.id,
                self.version,
                "graded",
                all(values.values()),
                checks,
            )
        except Exception as exc:
            return GradeOutcome(
                self.id,
                self.version,
                "grader_error",
                None,
                (),
                f"{type(exc).__name__}: {exc}",
            )

    def grade_attempt(self, attempt, task_id):
        try:
            evidence = GradingEvidence.capture(attempt, task_id)
        except Exception as exc:
            return GradeOutcome(
                self.id,
                self.version,
                "grader_error",
                None,
                (),
                f"{type(exc).__name__}: {exc}",
            )
        return self.grade_evidence(evidence)

    def __call__(self, attempt):
        """Compatibility form for callers expecting ``(score, checks)``."""
        outcome = self.grade_attempt(
            attempt,
            getattr(attempt, "task_id", self.id.rsplit(".", 1)[-1]),
        )
        if outcome.grader_status != "graded":
            raise GradingError(outcome.error)
        return (
            1.0 if outcome.candidate_decision else 0.0,
            [
                (description, ok)
                for _key, description, ok in outcome.checks
            ],
        )
