"""Run and verify the native Windows ARM64 S4 release attestation.

The release CLI owns the exact pytest invocation and sanitized environment.  It
then binds the resulting JUnit report to the current clean, pushed candidate
commit, the candidate's independently collected full inventory, and the native
host facts required by the frozen S4 protocol.
"""

import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import struct
import subprocess
import sys
from datetime import datetime, timezone
import unicodedata
import xml.etree.ElementTree as ET


SCHEMA_VERSION = "brick.s4-attestation/1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SAFE_REPORT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_REPARSE_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_PE_ARCHITECTURES = {
    0x014C: "x86",
    0x8664: "amd64",
    0xAA64: "arm64",
}

_TOP_KEYS = {
    "schema_version",
    "candidate_commit",
    "command",
    "report",
    "host",
    "python",
    "volume",
    "services",
    "tests",
    "overall_status",
    "verification_timestamp_utc",
}
_REPORT_KEYS = {"name", "size", "sha256"}
_HOST_KEYS = {
    "manufacturer",
    "model",
    "processor",
    "os_build",
    "os_architecture",
}
_PYTHON_KEYS = {"version", "architecture", "executable_sha256"}
_VOLUME_KEYS = {"root", "filesystem", "volume_id", "outside_onedrive"}
_SERVICE_KEYS = {
    "defender_realtime_enabled",
    "windows_search_running",
    "developer_mode_enabled",
}
_TEST_KEYS = {"inventory", "passed", "failed", "skipped", "s4_skipped"}

# These names bind the report to the complete S4 mechanism categories frozen in
# PROJECT_SETUP.md.  Parametrized suffixes such as ``[False-True]`` are ignored.
_REQUIRED_NATIVE_TESTS = frozenset(
    {
        "test_cross_process_lock_excludes_contender_and_persists",
        "test_cross_process_lock_is_released_after_forced_termination",
        "test_execute_acquires_lock_before_candidate_or_producer",
        "test_windows_real_symlink_is_rejected_before_publication",
        "test_windows_real_junction_is_rejected_before_publication",
        "test_windows_real_held_handle_retries_without_model_rerun",
        "test_windows_held_handle_timeout_recovers_without_model_rerun",
        "test_prepared_attempt_is_adopted_without_second_producer_call",
        "test_any_two_valid_prepared_or_committed_candidates_halt_resolution",
        "test_distinct_full_key_under_same_logical_hash_halts_as_collision",
        "test_committed_corruption_matrix_halts_fail_closed",
        "test_missing_corrupt_and_stale_projection_are_rebuilt_from_evidence",
        "test_unexpected_top_level_member_blocks_publication",
        "test_artifact_mutation_after_capture_blocks_publication",
        "test_projection_rebuild_failure_never_publishes_a_partial_projection",
        "test_projection_never_treats_uncommitted_candidate_as_a_result",
        "test_hard_process_exit_recovers_fail_closed_without_duplicate_execution",
        "test_retry_delay_sequence_is_exact",
        "test_prepare_and_publish_share_one_monotonic_deadline",
        "test_new_producer_publication_block_returns_without_projection_or_rerun",
        "test_corrupt_uncommitted_prepared_is_abandoned_and_reexecuted_once",
        "test_semantically_invalid_canonical_prepared_uses_integrity_boundary",
        "test_retryable_attempt_identity_read_exhaustion_never_reruns_producer",
        "test_transient_winerror_marker_failures_are_retried",
        "test_windows_retryable_error_classification_is_exact",
        "test_existing_marker_is_inspected_instead_of_blindly_accepted",
        "test_file_exists_during_marker_creation_requires_state_validation",
        "test_uuid_collision_never_reuses_or_overwrites_a_candidate",
        "test_concurrent_process_execute_invokes_exactly_one_producer",
    }
)

_RECOVERY_TESTS = frozenset(
    name
    for name in _REQUIRED_NATIVE_TESTS
    if name
    in {
        "test_hard_process_exit_recovers_fail_closed_without_duplicate_execution",
        "test_retry_delay_sequence_is_exact",
        "test_prepare_and_publish_share_one_monotonic_deadline",
        "test_new_producer_publication_block_returns_without_projection_or_rerun",
        "test_corrupt_uncommitted_prepared_is_abandoned_and_reexecuted_once",
        "test_semantically_invalid_canonical_prepared_uses_integrity_boundary",
        "test_retryable_attempt_identity_read_exhaustion_never_reruns_producer",
        "test_transient_winerror_marker_failures_are_retried",
        "test_windows_retryable_error_classification_is_exact",
        "test_existing_marker_is_inspected_instead_of_blindly_accepted",
        "test_file_exists_during_marker_creation_requires_state_validation",
        "test_uuid_collision_never_reuses_or_overwrites_a_candidate",
        "test_concurrent_process_execute_invokes_exactly_one_producer",
    }
)

_REQUIRED_PARAMETER_COUNTS = {
    "test_windows_real_symlink_is_rejected_before_publication": 2,
    "test_hard_process_exit_recovers_fail_closed_without_duplicate_execution": 16,
    "test_file_exists_during_marker_creation_requires_state_validation": 2,
    "test_semantically_invalid_canonical_prepared_uses_integrity_boundary": 2,
    "test_any_two_valid_prepared_or_committed_candidates_halt_resolution": 3,
    "test_committed_corruption_matrix_halts_fail_closed": 7,
}


class S4AttestationError(RuntimeError):
    """The attestation or one of its source facts is not trustworthy."""


def _require(condition, message):
    if not condition:
        raise S4AttestationError(message)


def _exact_keys(value, expected, label):
    _require(isinstance(value, dict), "%s must be an object" % label)
    missing = expected - set(value)
    extra = set(value) - expected
    details = []
    if missing:
        details.append("missing " + ", ".join(sorted(missing)))
    if extra:
        details.append("unknown " + ", ".join(sorted(extra)))
    _require(not details, "%s has %s" % (label, "; ".join(details)))


def _nonempty_text(value, label):
    _require(isinstance(value, str) and bool(value), "%s must be text" % label)
    _require(
        unicodedata.is_normalized("NFC", value),
        "%s must be NFC-normalized" % label,
    )
    return value


def _nonnegative_integer(value, label):
    _require(
        type(value) is int and value >= 0,
        "%s must be a nonnegative integer" % label,
    )
    return value


def _normalize_json(value, label="value"):
    if value is None or type(value) is bool or isinstance(value, str):
        if isinstance(value, str):
            _nonempty_text(value, label)
        return value
    if type(value) is int:
        return value
    if isinstance(value, float):
        _require(math.isfinite(value), "%s contains a non-finite number" % label)
        return value
    if isinstance(value, list):
        return [
            _normalize_json(item, "%s[%d]" % (label, index))
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        normalized = {}
        for key in sorted(value):
            _nonempty_text(key, "%s key" % label)
            normalized[key] = _normalize_json(
                value[key], "%s.%s" % (label, key)
            )
        return normalized
    raise S4AttestationError("%s contains an unsupported JSON type" % label)


def canonical_json_bytes(value):
    normalized = _normalize_json(value)
    return (
        json.dumps(
            normalized,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_reparse(info):
    return bool(getattr(info, "st_file_attributes", 0) & _REPARSE_ATTRIBUTE)


def _regular_file(path, label):
    path = Path(path)
    try:
        info = path.lstat()
    except OSError as exc:
        raise S4AttestationError("%s is unavailable: %s" % (label, exc)) from exc
    _require(
        stat.S_ISREG(info.st_mode) and not _is_reparse(info),
        "%s must be a regular non-reparse file" % label,
    )
    return path


def _duplicate_rejecting_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise S4AttestationError("JSON contains duplicate key %r" % key)
        value[key] = item
    return value


def _reject_json_constant(value):
    raise S4AttestationError("JSON contains invalid constant %s" % value)


def _load_canonical_json(path, label):
    path = _regular_file(path, label)
    try:
        payload = path.read_bytes()
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_duplicate_rejecting_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, ValueError) as exc:
        if isinstance(exc, S4AttestationError):
            raise
        raise S4AttestationError("%s is not canonical JSON" % label) from exc
    _require(
        payload == canonical_json_bytes(value),
        "%s bytes are not canonical JSON" % label,
    )
    return value


def _test_identifier(element):
    classname = _nonempty_text(
        element.attrib.get("classname"), "JUnit testcase classname"
    )
    name = _nonempty_text(element.attrib.get("name"), "JUnit testcase name")
    return "%s::%s" % (classname, name)


def _test_status(element):
    failures = list(element.findall("failure"))
    errors = list(element.findall("error"))
    skips = list(element.findall("skipped"))
    _require(
        len(failures) + len(errors) + len(skips) <= 1,
        "JUnit testcase has multiple terminal statuses",
    )
    if failures or errors:
        return "failed"
    if skips:
        return "skipped"
    return "passed"


def _base_test_name(identifier):
    name = identifier.rsplit("::", 1)[-1]
    return name.split("[", 1)[0]


def _is_required_s4_case(identifier):
    classname, name = identifier.rsplit("::", 1)
    module = classname.rsplit(".", 1)[-1]
    base = name.split("[", 1)[0]
    if module == "test_evidence_store":
        return True
    if module == "test_evidence_platform":
        return not base.startswith("test_posix_")
    if module == "test_evidence_recovery":
        return True
    return module.startswith("test_s4_")


def _required_test_module(name):
    if name in _RECOVERY_TESTS:
        return "test_evidence_recovery"
    if name.startswith(("test_cross_", "test_execute_", "test_windows_")):
        return "test_evidence_platform"
    return "test_evidence_store"


def _integer_attribute(element, name, label):
    raw = element.attrib.get(name)
    if raw is None:
        return None
    _require(bool(re.fullmatch(r"\d+", raw)), "%s %s is invalid" % (label, name))
    return int(raw)


def _validate_suite_totals(suite):
    cases = list(suite.iter("testcase"))
    statuses = [_test_status(case) for case in cases]
    expected = {
        "tests": len(cases),
        "failures": statuses.count("failed"),
        "errors": 0,
        "skipped": statuses.count("skipped"),
    }
    # Pytest distinguishes <failure> and <error> in aggregate attributes.
    expected["failures"] = sum(
        1 for case in cases if case.find("failure") is not None
    )
    expected["errors"] = sum(
        1 for case in cases if case.find("error") is not None
    )
    label = "JUnit testsuite"
    for name, expected_value in expected.items():
        recorded = _integer_attribute(suite, name, label)
        if recorded is not None:
            _require(
                recorded == expected_value,
                "%s %s does not match its testcases" % (label, name),
            )


def parse_junit_report(path):
    """Return strict report metadata and recomputed testcase inventory/counts."""

    path = _regular_file(path, "JUnit report")
    payload = path.read_bytes()
    _require(payload, "JUnit report is empty")
    lowered = payload.lower()
    _require(
        b"<!doctype" not in lowered and b"<!entity" not in lowered,
        "JUnit report may not contain a DTD or entity declaration",
    )
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise S4AttestationError("JUnit report is malformed XML") from exc
    _require(
        root.tag in {"testsuite", "testsuites"},
        "JUnit report has an unsupported root element",
    )
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    _require(suites, "JUnit report contains no testsuite")
    for suite in suites:
        _validate_suite_totals(suite)

    cases = list(root.iter("testcase"))
    _require(cases, "JUnit report contains no testcases")
    records = []
    for case in cases:
        records.append((_test_identifier(case), _test_status(case)))
    inventory = sorted(identifier for identifier, _ in records)
    _require(
        len(inventory) == len(set(inventory)),
        "JUnit report contains duplicate testcase identities",
    )
    counts = {
        "inventory": inventory,
        "passed": sum(status == "passed" for _, status in records),
        "failed": sum(status == "failed" for _, status in records),
        "skipped": sum(status == "skipped" for _, status in records),
        "s4_skipped": sum(
            status == "skipped" and _is_required_s4_case(identifier)
            for identifier, status in records
        ),
    }
    return {
        "report": {
            "name": path.name,
            "size": len(payload),
            "sha256": _sha256_bytes(payload),
        },
        "tests": counts,
    }


def _required_inventory_present(inventory):
    present = set()
    for identifier in inventory:
        classname, _ = identifier.rsplit("::", 1)
        present.add((classname.rsplit(".", 1)[-1], _base_test_name(identifier)))
    missing = []
    for name in sorted(_REQUIRED_NATIVE_TESTS):
        module = _required_test_module(name)
        if (module, name) not in present:
            missing.append(name)
    _require(
        not missing,
        "JUnit report is missing required S4 tests: " + ", ".join(missing),
    )
    for name, minimum in sorted(_REQUIRED_PARAMETER_COUNTS.items()):
        module = _required_test_module(name)
        actual = sum(
            identifier.rsplit("::", 1)[0].rsplit(".", 1)[-1] == module
            and _base_test_name(identifier) == name
            for identifier in inventory
        )
        _require(
            actual >= minimum,
            "JUnit report has %d/%d required cases for %s"
            % (actual, minimum, name),
        )


def _command_report_name(command):
    _require(
        isinstance(command, list) and len(command) == 10,
        "command must use the exact native S4 argument shape",
    )
    _require(
        command[8] == "--junitxml",
        "command must contain the canonical --junitxml position",
    )
    return command[9].replace("\\", "/").rsplit("/", 1)[-1]


def _validate_command(command, report_name):
    _require(
        isinstance(command, list) and len(command) == 10,
        "command must use exactly ten native S4 arguments",
    )
    for index, argument in enumerate(command):
        _require(
            isinstance(argument, str) and bool(argument),
            "command argument %d must be nonempty text" % index,
        )
        _require(
            unicodedata.is_normalized("NFC", argument),
            "command argument %d must be NFC-normalized" % index,
        )
    _require(
        command[0].casefold() in {"python", "python.exe"},
        "command must use a path-free Python executable name",
    )
    _require(
        command[1:3] == ["-m", "pytest"],
        "command must invoke pytest with python -m",
    )
    _require(
        command[3:6] == ["-q", "-p", "no:cacheprovider"],
        "command must use the frozen quiet/cache-disabled options",
    )
    _require(
        command[6] == "--basetemp"
        and command[7].replace("\\", "/").rsplit("/", 1)[-1]
        == "pytest-tmp",
        "command must use the frozen pytest-tmp base directory",
    )
    _require(
        command[8] == "--junitxml",
        "command must use the frozen JUnit option",
    )
    _require(
        _command_report_name(command) == report_name,
        "command JUnit name does not match report.name",
    )


def validate_attestation(
    value,
    report_path=None,
    native_required=False,
    expected_inventory=None,
):
    """Strictly validate an attestation and optionally recompute its JUnit bind."""

    _exact_keys(value, _TOP_KEYS, "attestation")
    _require(
        value["schema_version"] == SCHEMA_VERSION,
        "unsupported attestation schema",
    )
    _require(
        isinstance(value["candidate_commit"], str)
        and bool(_COMMIT.fullmatch(value["candidate_commit"])),
        "candidate_commit must be lowercase 40-hex",
    )

    report = value["report"]
    _exact_keys(report, _REPORT_KEYS, "report")
    name = _nonempty_text(report["name"], "report.name")
    _require(
        bool(_SAFE_REPORT_NAME.fullmatch(name))
        and name not in {".", ".."},
        "report.name is not a safe basename",
    )
    _nonnegative_integer(report["size"], "report.size")
    _require(
        isinstance(report["sha256"], str)
        and bool(_SHA256.fullmatch(report["sha256"])),
        "report.sha256 must be lowercase 64-hex",
    )
    _validate_command(value["command"], name)

    host = value["host"]
    _exact_keys(host, _HOST_KEYS, "host")
    for key in sorted(_HOST_KEYS):
        _nonempty_text(host[key], "host.%s" % key)
    _require(
        bool(re.fullmatch(r"\d+", host["os_build"])),
        "host.os_build must be decimal digits",
    )

    python_value = value["python"]
    _exact_keys(python_value, _PYTHON_KEYS, "python")
    _nonempty_text(python_value["version"], "python.version")
    _nonempty_text(python_value["architecture"], "python.architecture")
    _require(
        isinstance(python_value["executable_sha256"], str)
        and bool(_SHA256.fullmatch(python_value["executable_sha256"])),
        "python.executable_sha256 must be lowercase 64-hex",
    )

    volume = value["volume"]
    _exact_keys(volume, _VOLUME_KEYS, "volume")
    for key in ("root", "filesystem", "volume_id"):
        _nonempty_text(volume[key], "volume.%s" % key)
    _require(
        type(volume["outside_onedrive"]) is bool,
        "volume.outside_onedrive must be boolean",
    )

    services = value["services"]
    _exact_keys(services, _SERVICE_KEYS, "services")
    for key in sorted(_SERVICE_KEYS):
        _require(type(services[key]) is bool, "services.%s must be boolean" % key)

    tests = value["tests"]
    _exact_keys(tests, _TEST_KEYS, "tests")
    inventory = tests["inventory"]
    _require(isinstance(inventory, list) and inventory, "tests.inventory is empty")
    for index, identifier in enumerate(inventory):
        _nonempty_text(identifier, "tests.inventory[%d]" % index)
    _require(
        inventory == sorted(inventory) and len(inventory) == len(set(inventory)),
        "tests.inventory must be sorted and unique",
    )
    for key in ("passed", "failed", "skipped", "s4_skipped"):
        _nonnegative_integer(tests[key], "tests.%s" % key)
    _require(
        tests["passed"] + tests["failed"] + tests["skipped"] == len(inventory),
        "test counts do not equal inventory size",
    )
    _require(
        tests["s4_skipped"] <= tests["skipped"],
        "s4_skipped exceeds skipped",
    )
    _required_inventory_present(inventory)
    if expected_inventory is not None:
        _require(
            inventory == list(expected_inventory),
            "JUnit inventory does not exactly match candidate collection",
        )

    _require(
        value["overall_status"] == "pass",
        "overall_status must be pass",
    )
    _require(tests["failed"] == 0, "failed tests leave the S4 gate pending")
    _require(tests["s4_skipped"] == 0, "an S4 skip leaves the gate pending")
    _require(services["defender_realtime_enabled"], "Defender real-time is off")
    _require(services["windows_search_running"], "Windows Search is not running")
    _require(services["developer_mode_enabled"], "Developer Mode is not enabled")
    _require(volume["filesystem"].casefold() == "ntfs", "volume is not NTFS")
    _require(volume["outside_onedrive"], "report is inside OneDrive")

    timestamp = _nonempty_text(
        value["verification_timestamp_utc"],
        "verification_timestamp_utc",
    )
    _require(
        bool(_TIMESTAMP.fullmatch(timestamp)),
        "verification_timestamp_utc is not canonical UTC",
    )
    try:
        datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise S4AttestationError(
            "verification_timestamp_utc is not a real timestamp"
        ) from exc

    if native_required:
        _require(
            "lenovo" in host["manufacturer"].casefold(),
            "native S4 host is not identified as Lenovo",
        )
        _require(
            host["os_architecture"].casefold() == "arm64",
            "native S4 OS architecture is not ARM64",
        )
        _require(
            python_value["architecture"].casefold() == "arm64",
            "native S4 Python architecture is not ARM64",
        )

    if report_path is not None:
        recomputed = parse_junit_report(report_path)
        _require(
            recomputed["report"] == report,
            "JUnit report size, name, or hash does not match",
        )
        _require(
            recomputed["tests"] == tests,
            "JUnit inventory or counts do not match",
        )
    return value


def _run_git(project_root, arguments):
    completed = subprocess.run(
        ["git"] + list(arguments),
        cwd=str(project_root),
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if completed.returncode != 0:
        raise S4AttestationError(
            "git command failed: " + completed.stderr[-500:]
        )
    return completed.stdout


def _collect_git_state(project_root):
    project_root = Path(project_root).resolve()
    top = _run_git(project_root, ["rev-parse", "--show-toplevel"]).strip()
    _require(
        Path(top).resolve() == project_root,
        "project_root is not the Git worktree root",
    )
    commit = _run_git(project_root, ["rev-parse", "HEAD"]).strip()
    _require(bool(_COMMIT.fullmatch(commit)), "HEAD is not lowercase 40-hex")
    status = _run_git(
        project_root,
        ["status", "--porcelain=v1", "--untracked-files=all"],
    )
    _require(status == "", "candidate worktree is not clean")
    refs = _run_git(
        project_root,
        [
            "for-each-ref",
            "--format=%(refname)",
            "--contains",
            commit,
            "refs/remotes",
        ],
    ).splitlines()
    pushed = [
        ref
        for ref in refs
        if ref.startswith("refs/remotes/") and not ref.endswith("/HEAD")
    ]
    _require(pushed, "candidate commit is not contained by a remote-tracking ref")
    return {"candidate_commit": commit}


def _verify_release_binding(project_root, candidate_commit):
    """Require a pushed, clean, attestation-only direct release descendant."""

    current = _collect_git_state(project_root)["candidate_commit"]
    ancestry = _run_git(
        project_root,
        ["rev-list", "--parents", "-n", "1", current],
    ).strip().split()
    _require(
        ancestry == [current, candidate_commit],
        "release commit must be a direct child of the tested candidate",
    )
    changes = [
        line
        for line in _run_git(
            project_root,
            [
                "diff",
                "--name-status",
                "--no-renames",
                candidate_commit,
                current,
                "--",
            ],
        ).splitlines()
        if line
    ]
    _require(
        changes == ["A\tevidence/s4/v0.5.0.json"],
        "release descendant may only add evidence/s4/v0.5.0.json",
    )
    tree_entry = _run_git(
        project_root,
        [
            "ls-tree",
            "-z",
            "--full-tree",
            current,
            "--",
            "evidence/s4/v0.5.0.json",
        ],
    )
    _require(
        bool(
            re.fullmatch(
                r"100644 blob [0-9a-f]{40}"
                r"\tevidence/s4/v0\.5\.0\.json\x00",
                tree_entry,
            )
        ),
        "release attestation must be one regular non-executable Git blob",
    )
    return current


def _verify_release_tag(project_root, candidate_commit, report_sha256):
    """Require the annotated v0.5.0 tag to bind release, candidate, and JUnit."""

    current = _run_git(project_root, ["rev-parse", "HEAD"]).strip()
    tag_name = "refs/tags/v0.5.0"
    tag_type = _run_git(project_root, ["cat-file", "-t", tag_name]).strip()
    _require(tag_type == "tag", "v0.5.0 must be an annotated tag")
    target = _run_git(
        project_root,
        ["rev-parse", tag_name + "^{commit}"],
    ).strip()
    _require(target == current, "v0.5.0 does not point to the release commit")
    blob = _run_git(
        project_root,
        ["rev-parse", "HEAD:evidence/s4/v0.5.0.json"],
    ).strip()
    _require(
        bool(_COMMIT.fullmatch(blob)),
        "release attestation Git blob id is not SHA-1",
    )
    message = _run_git(
        project_root,
        ["for-each-ref", "--format=%(contents)", tag_name],
    )
    required_bindings = {
        "candidate_commit": candidate_commit,
        "attestation_blob": blob,
        "junit_sha256": report_sha256,
    }
    lines = message.splitlines()
    for name, expected in required_bindings.items():
        matches = [
            line for line in lines if line.startswith(name + "=")
        ]
        _require(
            matches == [name + "=" + expected],
            "v0.5.0 annotation must contain exactly one correct %s binding"
            % name,
        )
    return blob


# Windows fails CreateDirectoryW at MAX_PATH - 12, not 260, because it reserves
# twelve characters for an 8.3 name inside the new directory. A directory
# junction is created through that API, so the S4 layout must be bounded against
# 248 rather than 260. Mirrored in tests/conftest.py and asserted equal by
# tests/test_s4_path_contract.py.
WINDOWS_DIRECTORY_PATH_LIMIT = 248
S4_PATH_MARGIN = 32
S4_MAX_WORST_PATH = WINDOWS_DIRECTORY_PATH_LIMIT - S4_PATH_MARGIN
S4_LONGEST_RUN_ID = "s4-platform-test"
S4_LONGEST_ARTIFACT_LEAF = "reparse-link"
S4_PLATFORM_ROOT_ENV = "BRICK_S4_PLATFORM_ROOT"
S4_PLATFORM_ROOT_DIRNAME = "s4p"
# mkdtemp allocates an eight-character name below the supplied root.
S4_ROOT_ALLOCATION = 1 + 8


def s4_worst_suffix_length():
    """Length of the deepest path an S4 test creates below its root."""
    return len(
        "\\runs\\{run}\\attempts\\{logical}\\{physical}\\artifacts\\{leaf}".format(
            run=S4_LONGEST_RUN_ID,
            logical="a" * 64,
            physical="b" * 36,
            leaf=S4_LONGEST_ARTIFACT_LEAF,
        )
    )


def s4_platform_root_for(report_dir):
    return Path(report_dir) / S4_PLATFORM_ROOT_DIRNAME


def s4_worst_path_length(report_dir):
    """Worst S4 path length implied by this report directory."""
    return (
        len(str(s4_platform_root_for(report_dir)))
        + S4_ROOT_ALLOCATION
        + s4_worst_suffix_length()
    )


def s4_path_headroom(report_dir):
    return WINDOWS_DIRECTORY_PATH_LIMIT - s4_worst_path_length(report_dir)


def _native_test_environment(platform_root=None):
    environment = dict(os.environ)
    for name in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONPATH"):
        environment.pop(name, None)
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    environment["BRICK_S4_NATIVE_REQUIRED"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    if platform_root is None:
        # Never inherit an operator's value: the bound is only meaningful when
        # the attestor owns the root it verified.
        environment.pop(S4_PLATFORM_ROOT_ENV, None)
    else:
        environment[S4_PLATFORM_ROOT_ENV] = str(platform_root)
    return environment


def _require_path_python_matches_current():
    executable = shutil.which("python")
    _require(executable is not None, "path-free python executable is unavailable")
    try:
        same = os.path.samefile(executable, sys.executable)
    except OSError:
        same = (
            os.path.normcase(os.path.realpath(executable))
            == os.path.normcase(os.path.realpath(sys.executable))
        )
    _require(
        same,
        "path-free python does not resolve to the attested interpreter",
    )


def _nodeid_to_identifier(nodeid):
    parts = nodeid.split("::")
    _require(
        len(parts) >= 2 and parts[0].endswith(".py"),
        "pytest collection returned an invalid node id",
    )
    module = parts[0][:-3].replace("\\", "/").replace("/", ".")
    classname = module
    if len(parts) > 2:
        classname += "." + ".".join(parts[1:-1])
    return "%s::%s" % (classname, parts[-1])


def _collect_pytest_inventory(project_root):
    """Collect the candidate's exact full-suite inventory in a clean env."""

    project_root = Path(project_root).resolve()
    _require_path_python_matches_current()
    completed = subprocess.run(
        [
            "python",
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=str(project_root),
        env=_native_test_environment(),
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        raise S4AttestationError(
            "pytest inventory collection failed: "
            + (completed.stderr or completed.stdout)[-1000:]
        )
    nodeids = [
        line.strip()
        for line in completed.stdout.splitlines()
        if "::" in line and line.strip().split("::", 1)[0].endswith(".py")
    ]
    _require(nodeids, "pytest inventory collection returned no tests")
    inventory = sorted(_nodeid_to_identifier(nodeid) for nodeid in nodeids)
    _require(
        len(inventory) == len(set(inventory)),
        "pytest collection returned duplicate testcase identities",
    )
    return inventory


_WINDOWS_METADATA_SCRIPT = r"""
$computer = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
$processor = Get-CimInstance Win32_Processor -ErrorAction Stop |
  Select-Object -First 1
$os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
$defender = Get-MpComputerStatus -ErrorAction Stop
$search = Get-Service WSearch -ErrorAction Stop
$developer = Get-ItemPropertyValue `
  'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock' `
  -Name AllowDevelopmentWithoutDevLicense -ErrorAction SilentlyContinue
[pscustomobject]@{
  manufacturer = [string]$computer.Manufacturer
  model = [string]$computer.Model
  processor = [string]$processor.Name
  os_build = [string]$os.BuildNumber
  os_architecture = [string]$os.OSArchitecture
  defender_realtime_enabled = [bool]$defender.RealTimeProtectionEnabled
  windows_search_running = ([string]$search.Status -eq 'Running')
  developer_mode_enabled = ([int]$developer -eq 1)
} | ConvertTo-Json -Compress
"""


def _collect_windows_metadata():
    _require(os.name == "nt", "native Windows is required")
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            _WINDOWS_METADATA_SCRIPT,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise S4AttestationError(
            "Windows metadata query failed: " + completed.stderr[-500:]
        )
    try:
        value = json.loads(completed.stdout)
    except ValueError as exc:
        raise S4AttestationError("Windows metadata query returned invalid JSON") from exc
    expected = _HOST_KEYS | _SERVICE_KEYS
    _exact_keys(value, expected, "Windows metadata")
    return value


def _normalize_architecture(value):
    compact = re.sub(r"[^a-z0-9]", "", str(value).casefold())
    if compact in {"arm64", "aarch64"} or compact.startswith("arm64"):
        return "arm64"
    if compact in {"amd64", "x8664", "64bit"} or "x64" in compact:
        return "amd64"
    if compact in {"x86", "i386", "32bit"}:
        return "x86"
    return compact or "unknown"


def _pe_architecture(path):
    path = _regular_file(path, "Python executable")
    try:
        with path.open("rb") as handle:
            _require(handle.read(2) == b"MZ", "Python executable is not PE")
            handle.seek(0x3C)
            raw_offset = handle.read(4)
            _require(len(raw_offset) == 4, "Python PE header is truncated")
            handle.seek(struct.unpack("<I", raw_offset)[0])
            _require(handle.read(4) == b"PE\0\0", "Python PE signature is absent")
            machine = handle.read(2)
            _require(len(machine) == 2, "Python COFF header is truncated")
    except OSError as exc:
        raise S4AttestationError("Python executable is unreadable") from exc
    return _PE_ARCHITECTURES.get(struct.unpack("<H", machine)[0], "unknown")


def _collect_python_identity(native_required):
    executable = _regular_file(sys.executable, "Python executable")
    if os.name == "nt":
        architecture = _pe_architecture(executable)
    else:
        architecture = _normalize_architecture(platform.machine())
    if native_required:
        _require(os.name == "nt", "native Windows is required")
        _require(
            architecture == "arm64"
            and _normalize_architecture(platform.machine()) == "arm64",
            "native ARM64 Python is required",
        )
    return {
        "version": platform.python_version(),
        "architecture": architecture,
        "executable_sha256": _sha256_file(executable),
    }


def _inside_onedrive(path):
    candidate = os.path.normcase(os.path.realpath(str(path)))
    for key in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        root = os.environ.get(key)
        if not root:
            continue
        root = os.path.normcase(os.path.realpath(root))
        try:
            if os.path.commonpath((candidate, root)) == root:
                return True
        except ValueError:
            continue
    return False


def _collect_volume_identity(report_path):
    _require(os.name == "nt", "native Windows volume inspection is required")
    from ctypes import wintypes

    report_path = Path(report_path).resolve()
    root = report_path.anchor
    _require(root, "JUnit report has no Windows volume root")
    filesystem = ctypes.create_unicode_buffer(64)
    serial = wintypes.DWORD()
    maximum_component = wintypes.DWORD()
    flags = wintypes.DWORD()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    volume_information = kernel32.GetVolumeInformationW
    volume_information.argtypes = (
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPWSTR,
        wintypes.DWORD,
    )
    volume_information.restype = wintypes.BOOL
    if not volume_information(
        root,
        None,
        0,
        ctypes.byref(serial),
        ctypes.byref(maximum_component),
        ctypes.byref(flags),
        filesystem,
        len(filesystem),
    ):
        raise S4AttestationError(
            "volume inspection failed: %s" % ctypes.WinError(ctypes.get_last_error())
        )
    get_drive_type = kernel32.GetDriveTypeW
    get_drive_type.argtypes = (wintypes.LPCWSTR,)
    get_drive_type.restype = wintypes.UINT
    drive_type = get_drive_type(root)
    _require(int(drive_type) == 3, "JUnit report is not on a fixed local volume")
    return {
        "root": root,
        "filesystem": filesystem.value,
        "volume_id": "%08x" % int(serial.value),
        "outside_onedrive": not _inside_onedrive(report_path),
    }


def _utc_timestamp(now=None):
    value = datetime.now(timezone.utc) if now is None else now
    _require(
        isinstance(value, datetime) and value.tzinfo is not None,
        "verification time must be timezone-aware",
    )
    return value.astimezone(timezone.utc).replace(microsecond=0).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def collect_attestation(
    project_root,
    report_path,
    command,
    native_required=True,
    now=None,
):
    """Gather current facts and return a verified in-memory attestation."""

    report_path = _regular_file(report_path, "JUnit report").resolve()
    _validate_command(command, report_path.name)
    _require(
        Path(command[9]).resolve() == report_path,
        "command JUnit path does not identify the supplied report",
    )
    base_temp = Path(command[7]).resolve()
    _require(
        base_temp.parent == report_path.parent
        and base_temp.name == "pytest-tmp",
        "pytest base directory must be pytest-tmp beside the JUnit report",
    )
    report_data = parse_junit_report(report_path)
    git_state = _collect_git_state(project_root)
    expected_inventory = _collect_pytest_inventory(project_root)
    after_collection = _collect_git_state(project_root)
    _require(
        after_collection == git_state,
        "candidate commit or worktree changed during inventory collection",
    )
    metadata = _collect_windows_metadata()
    host = {key: metadata[key] for key in _HOST_KEYS}
    host["os_architecture"] = _normalize_architecture(host["os_architecture"])
    services = {key: metadata[key] for key in _SERVICE_KEYS}
    value = {
        "schema_version": SCHEMA_VERSION,
        "candidate_commit": git_state["candidate_commit"],
        "command": list(command),
        "report": report_data["report"],
        "host": host,
        "python": _collect_python_identity(native_required),
        "volume": _collect_volume_identity(report_path),
        "services": services,
        "tests": report_data["tests"],
        "overall_status": "pass",
        "verification_timestamp_utc": _utc_timestamp(now),
    }
    return validate_attestation(
        value,
        report_path=report_path,
        native_required=native_required,
        expected_inventory=expected_inventory,
    )


def write_attestation(path, value):
    """Validate and exclusively write one canonical attestation file."""

    validate_attestation(value)
    path = Path(path)
    _require(path.name not in {"", ".", ".."}, "output path is invalid")
    _require(path.parent.is_dir(), "output parent directory does not exist")
    try:
        parent_info = path.parent.lstat()
    except OSError as exc:
        raise S4AttestationError("output parent is unavailable") from exc
    _require(
        stat.S_ISDIR(parent_info.st_mode) and not _is_reparse(parent_info),
        "output parent must be a regular non-reparse directory",
    )
    _require(not os.path.lexists(str(path)), "output path already exists")
    payload = canonical_json_bytes(value)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise S4AttestationError("output path already exists") from exc
    return path


def load_and_verify_attestation(
    attestation_path,
    report_path,
    native_required=True,
    project_root=None,
    require_release_binding=False,
    require_release_tag=False,
):
    if require_release_binding:
        _require(
            project_root is not None,
            "release binding requires project_root",
        )
        expected_attestation = (
            Path(project_root).resolve()
            / "evidence"
            / "s4"
            / "v0.5.0.json"
        ).resolve()
        _require(
            Path(attestation_path).resolve() == expected_attestation,
            "release verification requires the tracked S4 attestation path",
        )
    value = _load_canonical_json(attestation_path, "S4 attestation")
    expected_inventory = (
        None
        if project_root is None
        else _collect_pytest_inventory(project_root)
    )
    validated = validate_attestation(
        value,
        report_path=report_path,
        native_required=native_required,
        expected_inventory=expected_inventory,
    )
    if require_release_binding:
        _verify_release_binding(
            project_root,
            validated["candidate_commit"],
        )
    if require_release_tag:
        _require(
            project_root is not None and require_release_binding,
            "release tag verification requires release binding",
        )
        _verify_release_tag(
            project_root,
            validated["candidate_commit"],
            validated["report"]["sha256"],
        )
    return validated


def _path_is_within(path, root):
    try:
        return os.path.commonpath(
            (os.path.realpath(str(path)), os.path.realpath(str(root)))
        ) == os.path.realpath(str(root))
    except ValueError:
        return False


def _create_native_report_directory(project_root, report_dir, commit):
    report_dir = Path(report_dir).resolve()
    _require(
        not _path_is_within(report_dir, project_root),
        "native report directory must be outside the Git worktree",
    )
    _require(
        report_dir.name.startswith("s4-" + commit[:12] + "-")
        and bool(
            re.fullmatch(
                r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,30}[A-Za-z0-9])?",
                report_dir.name[len("s4-" + commit[:12] + "-"):],
            )
        )
        ,
        "native report directory must be named "
        "s4-<candidate-prefix>-<unique-token>",
    )
    # Derived rather than asserted: the previous flat 120-character rule was not
    # tied to any Windows limit and neither proved nor explained the bound it
    # imposed. The real constraint is CreateDirectoryW at MAX_PATH - 12 = 248,
    # which a directory junction hits. Fail before the report directory is
    # consumed so a too-long path is reported as a preflight refusal rather than
    # as a mid-run WinError 206 inside a required S4 case.
    _require(
        s4_path_headroom(report_dir) >= S4_PATH_MARGIN,
        "native report directory leaves insufficient Windows path headroom: "
        "worst S4 path would be {} characters, leaving {} below the {} "
        "directory limit; at least {} required".format(
            s4_worst_path_length(report_dir),
            s4_path_headroom(report_dir),
            WINDOWS_DIRECTORY_PATH_LIMIT,
            S4_PATH_MARGIN,
        ),
    )
    _require(
        not os.path.lexists(str(report_dir)),
        "native report directory already exists",
    )
    parent = report_dir.parent
    try:
        parent_info = parent.lstat()
    except OSError as exc:
        raise S4AttestationError(
            "native report parent is unavailable"
        ) from exc
    _require(
        stat.S_ISDIR(parent_info.st_mode) and not _is_reparse(parent_info),
        "native report parent must be a non-reparse directory",
    )
    try:
        report_dir.mkdir()
    except FileExistsError as exc:
        raise S4AttestationError(
            "native report directory already exists"
        ) from exc
    return report_dir


def _run_command(args):
    project_root = Path(args.project_root).resolve()
    before = _collect_git_state(project_root)
    _require_path_python_matches_current()
    report_dir = Path(args.report_dir).resolve()
    report_path = report_dir / "pytest.xml"
    base_temp = report_dir / "pytest-tmp"
    metadata_before = _collect_windows_metadata()
    host_before = {
        key: metadata_before[key]
        for key in _HOST_KEYS
    }
    host_before["os_architecture"] = _normalize_architecture(
        host_before["os_architecture"]
    )
    services_before = {
        key: metadata_before[key]
        for key in _SERVICE_KEYS
    }
    _require(
        "lenovo" in str(host_before["manufacturer"]).casefold()
        and host_before["os_architecture"] == "arm64",
        "native S4 preflight requires the Lenovo ARM64 host",
    )
    _require(
        services_before["defender_realtime_enabled"]
        and services_before["windows_search_running"]
        and services_before["developer_mode_enabled"],
        "Defender, Windows Search, and Developer Mode must pass preflight",
    )
    python_before = _collect_python_identity(True)
    volume_before = _collect_volume_identity(report_path)
    _require(
        volume_before["filesystem"].casefold() == "ntfs"
        and volume_before["outside_onedrive"],
        "native S4 preflight requires NTFS outside OneDrive",
    )
    report_dir = _create_native_report_directory(
        project_root,
        report_dir,
        before["candidate_commit"],
    )
    command = [
        "python",
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "--basetemp",
        str(base_temp),
        "--junitxml",
        str(report_path),
    ]
    platform_root = s4_platform_root_for(report_dir)
    platform_root.mkdir(parents=True, exist_ok=False)
    completed = subprocess.run(
        command,
        cwd=str(project_root),
        env=_native_test_environment(platform_root),
        check=False,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if completed.returncode != 0:
        raise S4AttestationError(
            "native S4 pytest failed; raw report retained at %s: %s"
            % (
                report_path,
                (completed.stderr or completed.stdout)[-1500:],
            )
        )
    after = _collect_git_state(project_root)
    _require(
        after == before,
        "candidate commit or worktree changed during native S4 pytest",
    )
    value = collect_attestation(
        project_root,
        report_path,
        command,
        native_required=True,
    )
    _require(
        value["candidate_commit"] == before["candidate_commit"],
        "attested candidate differs from the executed candidate",
    )
    _require(
        value["host"] == host_before
        and value["services"] == services_before
        and value["python"] == python_before
        and value["volume"] == volume_before,
        "native host, services, interpreter, or volume changed during pytest",
    )
    output = Path(args.output).resolve()
    expected_output = (
        project_root / "evidence" / "s4" / "v0.5.0.json"
    ).resolve()
    _require(
        output == expected_output,
        "native S4 output must be evidence/s4/v0.5.0.json",
    )
    if not output.parent.exists():
        _require(
            output.parent.parent == (project_root / "evidence").resolve()
            and output.parent.parent.is_dir(),
            "evidence directory is unavailable",
        )
        output.parent.mkdir(exist_ok=False)
    output = write_attestation(output, value)
    print(
        json.dumps(
            {
                "candidate_commit": value["candidate_commit"],
                "output": str(output),
                "report_sha256": value["report"]["sha256"],
                "status": "pass",
            },
            sort_keys=True,
        )
    )
    return 0


def _verify_command(args):
    value = load_and_verify_attestation(
        args.attestation,
        args.junit,
        native_required=args.native_required,
        project_root=args.project_root,
        require_release_binding=True,
        require_release_tag=True,
    )
    print(
        json.dumps(
            {
                "candidate_commit": value["candidate_commit"],
                "report_sha256": value["report"]["sha256"],
                "status": "pass",
            },
            sort_keys=True,
        )
    )
    return 0


def _parser():
    parser = argparse.ArgumentParser(
        description="Run or verify the native Windows ARM64 S4 attestation."
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    run = subparsers.add_parser("run")
    run.add_argument("--project-root", required=True)
    run.add_argument("--report-dir", required=True)
    run.add_argument("--output", required=True)
    run.set_defaults(handler=_run_command)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--attestation", required=True)
    verify.add_argument("--junit", required=True)
    verify.add_argument("--project-root", required=True)
    verify.add_argument("--native-required", action="store_true", required=True)
    verify.set_defaults(handler=_verify_command)
    return parser


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (OSError, S4AttestationError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
