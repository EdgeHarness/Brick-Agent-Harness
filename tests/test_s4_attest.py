import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest

from bench import s4_attest


COMMIT = "1" * 40
SHA = "a" * 64


def _required_cases():
    cases = []
    for name in sorted(s4_attest._REQUIRED_NATIVE_TESTS):
        module = "tests." + s4_attest._required_test_module(name)
        if name == "test_windows_real_symlink_is_rejected_before_publication":
            cases.append((module, name + "[False]", "passed"))
            cases.append((module, name + "[True]", "passed"))
        elif name == (
            "test_hard_process_exit_recovers_fail_closed_without_duplicate_execution"
        ):
            for index in range(16):
                cases.append((module, name + "[boundary-%d]" % index, "passed"))
        elif name in {
            "test_file_exists_during_marker_creation_requires_state_validation",
            "test_semantically_invalid_canonical_prepared_uses_integrity_boundary",
        }:
            cases.append((module, name + "[False]", "passed"))
            cases.append((module, name + "[True]", "passed"))
        elif name == (
            "test_any_two_valid_prepared_or_committed_candidates_halt_resolution"
        ):
            for index in range(3):
                cases.append((module, name + "[case-%d]" % index, "passed"))
        elif name == "test_committed_corruption_matrix_halts_fail_closed":
            for index in range(7):
                cases.append((module, name + "[case-%d]" % index, "passed"))
        else:
            cases.append((module, name, "passed"))
    cases.extend(
        [
            (
                "tests.test_evidence_platform",
                "test_posix_symlink_member_is_rejected_before_publication",
                "skipped",
            ),
            (
                "tests.test_f0_protocol_v2",
                "test_non_windows_behavior",
                "skipped",
            ),
            (
                "tests.test_s4_attest",
                "test_attestation_self_check",
                "passed",
            ),
        ]
    )
    return cases


def _write_junit(path, *, overrides=None, declared_tests=None):
    overrides = {} if overrides is None else dict(overrides)
    cases = []
    for classname, name, default_status in _required_cases():
        base = name.split("[", 1)[0]
        status = overrides.get(base, default_status)
        cases.append((classname, name, status))

    suite = ET.Element(
        "testsuite",
        {
            "name": "pytest",
            "tests": str(len(cases) if declared_tests is None else declared_tests),
            "failures": str(sum(status == "failed" for _, _, status in cases)),
            "errors": "0",
            "skipped": str(sum(status == "skipped" for _, _, status in cases)),
        },
    )
    for classname, name, status in cases:
        testcase = ET.SubElement(
            suite,
            "testcase",
            {"classname": classname, "name": name, "time": "0.001"},
        )
        if status == "failed":
            ET.SubElement(
                testcase,
                "failure",
                {"message": "fixture failure", "type": "AssertionError"},
            ).text = "fixture failure"
        elif status == "skipped":
            ET.SubElement(
                testcase,
                "skipped",
                {"message": "fixture skip", "type": "pytest.skip"},
            )
    ET.ElementTree(suite).write(
        str(path),
        encoding="utf-8",
        xml_declaration=True,
    )
    return path


def _valid_attestation(report_path):
    report_data = s4_attest.parse_junit_report(report_path)
    return {
        "schema_version": s4_attest.SCHEMA_VERSION,
        "candidate_commit": COMMIT,
        "command": [
            "python",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--basetemp",
            str(report_path.parent / "pytest-tmp"),
            "--junitxml",
            str(report_path),
        ],
        "report": report_data["report"],
        "host": {
            "manufacturer": "LENOVO",
            "model": "83ED",
            "processor": "Snapdragon X Elite - X1E80100",
            "os_build": "26200",
            "os_architecture": "arm64",
        },
        "python": {
            "version": "3.13.14",
            "architecture": "arm64",
            "executable_sha256": SHA,
        },
        "volume": {
            "root": "C:\\",
            "filesystem": "NTFS",
            "volume_id": "1234abcd",
            "outside_onedrive": True,
        },
        "services": {
            "defender_realtime_enabled": True,
            "windows_search_running": True,
            "developer_mode_enabled": True,
        },
        "tests": report_data["tests"],
        "overall_status": "pass",
        "verification_timestamp_utc": "2026-08-01T12:34:56Z",
    }


def test_junit_report_recomputes_sorted_inventory_and_platform_skips(tmp_path):
    report = _write_junit(tmp_path / "pytest.xml")

    parsed = s4_attest.parse_junit_report(report)

    assert parsed["report"]["name"] == "pytest.xml"
    assert parsed["report"]["size"] == report.stat().st_size
    assert len(parsed["report"]["sha256"]) == 64
    assert parsed["tests"]["inventory"] == sorted(
        parsed["tests"]["inventory"]
    )
    assert parsed["tests"]["failed"] == 0
    assert parsed["tests"]["skipped"] == 2
    # POSIX-only and non-S4 skips are not pending native-Windows S4 cases.
    assert parsed["tests"]["s4_skipped"] == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"test_windows_real_junction_is_rejected_before_publication": "failed"},
        {"test_windows_real_junction_is_rejected_before_publication": "skipped"},
    ],
)
def test_failed_or_skipped_required_s4_case_rejects_attestation(
    tmp_path,
    overrides,
):
    report = _write_junit(tmp_path / "pytest.xml", overrides=overrides)
    value = _valid_attestation(report)

    with pytest.raises(s4_attest.S4AttestationError):
        s4_attest.validate_attestation(
            value,
            report_path=report,
            native_required=True,
        )


def test_strict_attestation_accepts_valid_native_fixture_and_binds_report(
    tmp_path,
):
    report = _write_junit(tmp_path / "pytest.xml")
    value = _valid_attestation(report)

    assert (
        s4_attest.validate_attestation(
            value,
            report_path=report,
            native_required=True,
        )
        is value
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "top_extra",
        "top_missing",
        "report_extra",
        "host_missing",
        "boolean_as_integer",
        "unsorted_inventory",
    ],
)
def test_exact_schema_rejects_unknown_missing_and_ambiguous_fields(
    tmp_path,
    mutation,
):
    report = _write_junit(tmp_path / "pytest.xml")
    value = _valid_attestation(report)
    if mutation == "top_extra":
        value["unknown"] = True
    elif mutation == "top_missing":
        del value["services"]
    elif mutation == "report_extra":
        value["report"]["path"] = str(report)
    elif mutation == "host_missing":
        del value["host"]["model"]
    elif mutation == "boolean_as_integer":
        value["services"]["developer_mode_enabled"] = 1
    elif mutation == "unsorted_inventory":
        value["tests"]["inventory"] = list(
            reversed(value["tests"]["inventory"])
        )

    with pytest.raises(s4_attest.S4AttestationError):
        s4_attest.validate_attestation(value)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("host", {"os_architecture": "amd64"}),
        ("python", {"architecture": "amd64"}),
    ],
)
def test_native_required_rejects_non_arm64_identity(
    tmp_path,
    field,
    replacement,
):
    report = _write_junit(tmp_path / "pytest.xml")
    value = _valid_attestation(report)
    value[field].update(replacement)

    with pytest.raises(s4_attest.S4AttestationError, match="ARM64"):
        s4_attest.validate_attestation(value, native_required=True)


@pytest.mark.parametrize(
    ("section", "field", "replacement"),
    [
        ("services", "defender_realtime_enabled", False),
        ("services", "windows_search_running", False),
        ("services", "developer_mode_enabled", False),
        ("volume", "filesystem", "ReFS"),
        ("volume", "outside_onedrive", False),
    ],
)
def test_gate_rejects_invalid_services_and_volume(
    tmp_path,
    section,
    field,
    replacement,
):
    report = _write_junit(tmp_path / "pytest.xml")
    value = _valid_attestation(report)
    value[section][field] = replacement

    with pytest.raises(s4_attest.S4AttestationError):
        s4_attest.validate_attestation(value)


def test_report_tamper_breaks_strict_size_and_hash_binding(tmp_path):
    report = _write_junit(tmp_path / "pytest.xml")
    value = _valid_attestation(report)
    report.write_bytes(report.read_bytes() + b"\n")

    with pytest.raises(s4_attest.S4AttestationError, match="does not match"):
        s4_attest.validate_attestation(value, report_path=report)


def test_declared_junit_totals_must_match_testcases(tmp_path):
    report = _write_junit(tmp_path / "pytest.xml", declared_tests=999)

    with pytest.raises(s4_attest.S4AttestationError, match="does not match"):
        s4_attest.parse_junit_report(report)


def test_junit_dtd_or_entity_declaration_is_rejected(tmp_path):
    report = tmp_path / "pytest.xml"
    report.write_bytes(
        b'<!DOCTYPE testsuite [<!ENTITY x "bad">]>'
        b'<testsuite tests="0" failures="0" errors="0" skipped="0"/>'
    )

    with pytest.raises(s4_attest.S4AttestationError, match="DTD"):
        s4_attest.parse_junit_report(report)


def test_command_rejects_selection_early_stop_and_wrong_report(tmp_path):
    report = _write_junit(tmp_path / "pytest.xml")
    value = _valid_attestation(report)

    for suffix in (
        ["tests/test_evidence_store.py"],
        ["-k", "evidence"],
        ["-x"],
    ):
        invalid = copy.deepcopy(value)
        invalid["command"].extend(suffix)
        with pytest.raises(s4_attest.S4AttestationError):
            s4_attest.validate_attestation(invalid)

    invalid = copy.deepcopy(value)
    invalid["command"][-1] = "other.xml"
    with pytest.raises(s4_attest.S4AttestationError, match="does not match"):
        s4_attest.validate_attestation(invalid)

    invalid = copy.deepcopy(value)
    invalid["command"][0] = sys.executable
    with pytest.raises(s4_attest.S4AttestationError, match="path-free"):
        s4_attest.validate_attestation(invalid)


@pytest.mark.parametrize(
    "injected",
    [
        "-konly_one",
        "-mfast",
        "-c=alternate.ini",
        "-o=python_files=one_test.py",
        "--override-ini=python_files=one_test.py",
        "--stepwise",
        "-p=external_plugin",
    ],
)
def test_frozen_command_shape_rejects_compact_selection_bypasses(
    tmp_path,
    injected,
):
    report = _write_junit(tmp_path / "pytest.xml")
    value = _valid_attestation(report)
    value["command"][3] = injected

    with pytest.raises(s4_attest.S4AttestationError):
        s4_attest.validate_attestation(value)


def test_exact_candidate_inventory_is_required_when_supplied(tmp_path):
    report = _write_junit(tmp_path / "pytest.xml")
    value = _valid_attestation(report)
    incomplete = value["tests"]["inventory"][:-1]

    with pytest.raises(s4_attest.S4AttestationError, match="exactly match"):
        s4_attest.validate_attestation(
            value,
            report_path=report,
            native_required=True,
            expected_inventory=incomplete,
        )


def test_collection_normalizes_only_module_path_not_parameter_identity():
    assert s4_attest._nodeid_to_identifier(
        "tests\\test_module.py::test_case[param\\value]"
    ) == "tests.test_module::test_case[param\\value]"


def test_missing_required_native_inventory_is_rejected(tmp_path):
    report = _write_junit(tmp_path / "pytest.xml")
    value = _valid_attestation(report)
    missing = "test_windows_real_junction_is_rejected_before_publication"
    value["tests"]["inventory"] = [
        identifier
        for identifier in value["tests"]["inventory"]
        if missing not in identifier
    ]
    value["tests"]["passed"] -= 1

    with pytest.raises(s4_attest.S4AttestationError, match="missing required"):
        s4_attest.validate_attestation(value)


def test_canonical_exclusive_write_roundtrips_and_never_overwrites(tmp_path):
    report = _write_junit(tmp_path / "pytest.xml")
    value = _valid_attestation(report)
    output = tmp_path / "v0.5.0.json"

    assert s4_attest.write_attestation(output, value) == output
    before = output.read_bytes()
    assert before == s4_attest.canonical_json_bytes(value)
    verified = s4_attest.load_and_verify_attestation(
        output,
        report,
        native_required=True,
    )
    assert verified == value

    with pytest.raises(s4_attest.S4AttestationError, match="already exists"):
        s4_attest.write_attestation(output, value)
    assert output.read_bytes() == before


def test_python_executable_is_bound_only_by_hash(tmp_path):
    report = _write_junit(tmp_path / "pytest.xml")
    value = _valid_attestation(report)

    assert set(value["python"]) == {
        "version",
        "architecture",
        "executable_sha256",
    }
    encoded = json.dumps(value["python"], sort_keys=True)
    assert sys.executable not in encoded
    assert "/" not in encoded
    assert "\\\\" not in encoded


def test_collect_attestation_uses_current_fact_collectors_without_path_leak(
    monkeypatch,
    tmp_path,
):
    report = _write_junit(tmp_path / "pytest.xml")
    fixture = _valid_attestation(report)
    monkeypatch.setattr(
        s4_attest,
        "_collect_git_state",
        lambda _root: {"candidate_commit": COMMIT},
    )
    metadata = dict(fixture["host"])
    metadata.update(fixture["services"])
    monkeypatch.setattr(
        s4_attest,
        "_collect_windows_metadata",
        lambda: metadata,
    )
    monkeypatch.setattr(
        s4_attest,
        "_collect_python_identity",
        lambda _required: dict(fixture["python"]),
    )
    monkeypatch.setattr(
        s4_attest,
        "_collect_volume_identity",
        lambda _report: dict(fixture["volume"]),
    )
    monkeypatch.setattr(
        s4_attest,
        "_collect_pytest_inventory",
        lambda _root: list(fixture["tests"]["inventory"]),
    )

    value = s4_attest.collect_attestation(
        tmp_path,
        report,
        fixture["command"],
        native_required=True,
        now=datetime(2026, 8, 1, 12, 34, 56, tzinfo=timezone.utc),
    )

    assert value == fixture
    assert set(value["python"]) == {
        "version",
        "architecture",
        "executable_sha256",
    }


def test_git_state_requires_clean_worktree_and_remote_containment(
    monkeypatch,
    tmp_path,
):
    responses = {
        ("rev-parse", "--show-toplevel"): str(tmp_path) + "\n",
        ("rev-parse", "HEAD"): COMMIT + "\n",
        ("status", "--porcelain=v1", "--untracked-files=all"): "",
        (
            "for-each-ref",
            "--format=%(refname)",
            "--contains",
            COMMIT,
            "refs/remotes",
        ): "refs/remotes/origin/main\n",
    }
    monkeypatch.setattr(
        s4_attest,
        "_run_git",
        lambda _root, arguments: responses[tuple(arguments)],
    )
    assert s4_attest._collect_git_state(tmp_path) == {
        "candidate_commit": COMMIT
    }

    responses[("status", "--porcelain=v1", "--untracked-files=all")] = (
        "?? local.txt\n"
    )
    with pytest.raises(s4_attest.S4AttestationError, match="not clean"):
        s4_attest._collect_git_state(tmp_path)

    responses[("status", "--porcelain=v1", "--untracked-files=all")] = ""
    responses[
        (
            "for-each-ref",
            "--format=%(refname)",
            "--contains",
            COMMIT,
            "refs/remotes",
        )
    ] = "refs/remotes/origin/HEAD\n"
    with pytest.raises(s4_attest.S4AttestationError, match="remote-tracking"):
        s4_attest._collect_git_state(tmp_path)


def test_release_binding_is_one_regular_attestation_only_direct_descendant(
    monkeypatch,
    tmp_path,
):
    release = "2" * 40
    blob = "3" * 40
    monkeypatch.setattr(
        s4_attest,
        "_collect_git_state",
        lambda _root: {"candidate_commit": release},
    )
    responses = {
        ("rev-list", "--parents", "-n", "1", release): (
            release + " " + COMMIT + "\n"
        ),
        ("diff", "--name-status", "--no-renames", COMMIT, release, "--"): (
            "A\tevidence/s4/v0.5.0.json\n"
        ),
        (
            "ls-tree",
            "-z",
            "--full-tree",
            release,
            "--",
            "evidence/s4/v0.5.0.json",
        ): (
            "100644 blob "
            + blob
            + "\tevidence/s4/v0.5.0.json\0"
        ),
    }
    monkeypatch.setattr(
        s4_attest,
        "_run_git",
        lambda _root, arguments: responses[tuple(arguments)],
    )

    assert s4_attest._verify_release_binding(tmp_path, COMMIT) == release

    responses[
        ("diff", "--name-status", "--no-renames", COMMIT, release, "--")
    ] += (
        "M\tharness/evidence.py\n"
    )
    with pytest.raises(s4_attest.S4AttestationError, match="only add"):
        s4_attest._verify_release_binding(tmp_path, COMMIT)

    responses[
        ("diff", "--name-status", "--no-renames", COMMIT, release, "--")
    ] = "A\tevidence/s4/v0.5.0.json\n"
    responses[
        (
            "ls-tree",
            "-z",
            "--full-tree",
            release,
            "--",
            "evidence/s4/v0.5.0.json",
        )
    ] = (
        "120000 blob "
        + blob
        + "\tevidence/s4/v0.5.0.json\0"
    )
    with pytest.raises(s4_attest.S4AttestationError, match="regular"):
        s4_attest._verify_release_binding(tmp_path, COMMIT)


def test_release_verification_rejects_an_external_attestation_path(tmp_path):
    external = tmp_path / "external.json"

    with pytest.raises(s4_attest.S4AttestationError, match="tracked"):
        s4_attest.load_and_verify_attestation(
            external,
            tmp_path / "pytest.xml",
            project_root=tmp_path / "project",
            require_release_binding=True,
        )


def test_release_tag_binds_candidate_attestation_blob_and_junit(
    monkeypatch,
    tmp_path,
):
    release = "2" * 40
    blob = "3" * 40
    responses = {
        ("rev-parse", "HEAD"): release + "\n",
        ("cat-file", "-t", "refs/tags/v0.5.0"): "tag\n",
        (
            "rev-parse",
            "refs/tags/v0.5.0^{commit}",
        ): release + "\n",
        (
            "rev-parse",
            "HEAD:evidence/s4/v0.5.0.json",
        ): blob + "\n",
        (
            "for-each-ref",
            "--format=%(contents)",
            "refs/tags/v0.5.0",
        ): (
            "Brick v0.5.0\n"
            "candidate_commit=" + COMMIT + "\n"
            "attestation_blob=" + blob + "\n"
            "junit_sha256=" + SHA + "\n"
        ),
    }
    monkeypatch.setattr(
        s4_attest,
        "_run_git",
        lambda _root, arguments: responses[tuple(arguments)],
    )

    assert s4_attest._verify_release_tag(tmp_path, COMMIT, SHA) == blob

    responses[
        (
            "for-each-ref",
            "--format=%(contents)",
            "refs/tags/v0.5.0",
        )
    ] += "candidate_commit=" + ("4" * 40) + "\n"
    with pytest.raises(s4_attest.S4AttestationError, match="exactly one"):
        s4_attest._verify_release_tag(tmp_path, COMMIT, SHA)

    responses[
        (
            "for-each-ref",
            "--format=%(contents)",
            "refs/tags/v0.5.0",
        )
    ] = (
        "Brick v0.5.0\n"
        "candidate_commit=" + COMMIT + "\n"
        "attestation_blob=" + blob + "\n"
        "junit_sha256=" + SHA + "\n"
    )
    responses[("cat-file", "-t", "refs/tags/v0.5.0")] = "commit\n"
    with pytest.raises(s4_attest.S4AttestationError, match="annotated"):
        s4_attest._verify_release_tag(tmp_path, COMMIT, SHA)


def test_pe_architecture_parser_is_independent_of_executable_path(tmp_path):
    executable = tmp_path / "python fixture.exe"
    payload = bytearray(256)
    payload[:2] = b"MZ"
    payload[0x3C:0x40] = struct.pack("<I", 0x80)
    payload[0x80:0x84] = b"PE\0\0"
    payload[0x84:0x86] = struct.pack("<H", 0xAA64)
    executable.write_bytes(payload)

    assert s4_attest._pe_architecture(executable) == "arm64"


def test_release_runner_owns_exact_pytest_command_and_sanitized_environment(
    monkeypatch,
    tmp_path,
):
    project = tmp_path / "project"
    evidence_dir = project / "evidence"
    report_parent = tmp_path / "native-reports"
    project.mkdir()
    evidence_dir.mkdir()
    report_parent.mkdir()
    report_dir = report_parent / ("s4-" + COMMIT[:12] + "-run0001")
    output = evidence_dir / "s4" / "v0.5.0.json"
    fixture_report = tmp_path / "fixture.xml"
    _write_junit(fixture_report)
    fixture = _valid_attestation(fixture_report)
    observed = {}

    monkeypatch.setattr(
        s4_attest,
        "_collect_git_state",
        lambda _root: {"candidate_commit": COMMIT},
    )
    monkeypatch.setattr(
        s4_attest,
        "_require_path_python_matches_current",
        lambda: None,
    )
    monkeypatch.setattr(
        s4_attest,
        "_collect_pytest_inventory",
        lambda _root: list(fixture["tests"]["inventory"]),
    )
    metadata = dict(fixture["host"])
    metadata.update(fixture["services"])
    monkeypatch.setattr(
        s4_attest,
        "_collect_windows_metadata",
        lambda: metadata,
    )
    monkeypatch.setattr(
        s4_attest,
        "_collect_python_identity",
        lambda _required: dict(fixture["python"]),
    )
    monkeypatch.setattr(
        s4_attest,
        "_collect_volume_identity",
        lambda _report: dict(fixture["volume"]),
    )

    def run_pytest(command, **kwargs):
        observed["command"] = list(command)
        observed["environment"] = dict(kwargs["env"])
        junit = Path(command[command.index("--junitxml") + 1])
        _write_junit(junit)
        return SimpleNamespace(returncode=0, stdout="passed", stderr="")

    monkeypatch.setattr(s4_attest.subprocess, "run", run_pytest)
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k only_one")
    monkeypatch.setenv("PYTEST_PLUGINS", "untrusted_plugin")
    monkeypatch.setenv("PYTHONPATH", "untrusted_path")

    args = SimpleNamespace(
        project_root=str(project),
        report_dir=str(report_dir),
        output=str(output),
    )
    assert s4_attest._run_command(args) == 0

    assert observed["command"] == [
        "python",
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "--basetemp",
        str(report_dir / "pytest-tmp"),
        "--junitxml",
        str(report_dir / "pytest.xml"),
    ]
    environment = observed["environment"]
    assert "PYTEST_ADDOPTS" not in environment
    assert "PYTEST_PLUGINS" not in environment
    assert "PYTHONPATH" not in environment
    assert environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert environment["BRICK_S4_NATIVE_REQUIRED"] == "1"
    assert output.is_file()


def test_failed_native_preflight_does_not_consume_report_directory(
    monkeypatch,
    tmp_path,
):
    project = tmp_path / "project"
    report_parent = tmp_path / "native-reports"
    project.mkdir()
    (project / "evidence").mkdir()
    report_parent.mkdir()
    report_dir = report_parent / ("s4-" + COMMIT[:12] + "-run0002")
    metadata = {
        "manufacturer": "LENOVO",
        "model": "83ED",
        "processor": "Snapdragon",
        "os_build": "26200",
        "os_architecture": "ARM64",
        "defender_realtime_enabled": True,
        "windows_search_running": True,
        "developer_mode_enabled": False,
    }
    monkeypatch.setattr(
        s4_attest,
        "_collect_git_state",
        lambda _root: {"candidate_commit": COMMIT},
    )
    monkeypatch.setattr(
        s4_attest,
        "_require_path_python_matches_current",
        lambda: None,
    )
    monkeypatch.setattr(
        s4_attest,
        "_collect_windows_metadata",
        lambda: dict(metadata),
    )

    args = SimpleNamespace(
        project_root=str(project),
        report_dir=str(report_dir),
        output=str(project / "evidence" / "s4" / "v0.5.0.json"),
    )
    with pytest.raises(s4_attest.S4AttestationError, match="preflight"):
        s4_attest._run_command(args)

    assert not report_dir.exists()
