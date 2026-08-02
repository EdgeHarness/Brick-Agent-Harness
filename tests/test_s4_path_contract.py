"""The S4 Windows path contract.

Windows fails ``CreateDirectoryW`` at ``MAX_PATH - 12 = 248``, not 260, because
it reserves twelve characters for an 8.3 name inside the new directory. A
directory junction is created through that API, so the S4 layout -- a 64-hex
logical hash plus a 36-character physical UUID -- must be bounded against 248.

Under pytest's default root the junction case reached 250 characters and failed
with ``WinError 206``. That failure was not constant: it moved with the pytest
counter and the operator's user name, so the S4 gate could pass or fail
depending on how often the suite had been run. These tests pin the derivation so
the bound cannot silently drift back.
"""

import re
from pathlib import Path

import pytest

from bench import s4_attest

import conftest


PLATFORM_TESTS = Path(__file__).with_name("test_evidence_platform.py")
STORE_TESTS = Path(__file__).with_name("test_evidence_store.py")
RECOVERY_TESTS = Path(__file__).with_name("test_evidence_recovery.py")
S4_TEST_MODULES = (PLATFORM_TESTS, STORE_TESTS, RECOVERY_TESTS)


def _module_run_ids():
    ids = []
    for path in S4_TEST_MODULES:
        for match in re.finditer(
            r'^RUN_ID\s*=\s*"([^"]+)"', path.read_text(encoding="utf-8"), re.M
        ):
            ids.append(match.group(1))
    return ids


def _artifact_leaves():
    leaves = []
    for path in S4_TEST_MODULES:
        leaves.extend(
            re.findall(
                r'"artifacts"\s*/\s*"([A-Za-z0-9._-]+)"',
                path.read_text(encoding="utf-8"),
            )
        )
    return leaves


def test_attestor_and_conftest_agree_on_the_limit():
    """One number, two call sites. Drift here silently unbounds the gate."""
    assert (
        s4_attest.WINDOWS_DIRECTORY_PATH_LIMIT
        == conftest.WINDOWS_DIRECTORY_PATH_LIMIT
        == 248
    )
    assert s4_attest.S4_PATH_MARGIN == conftest.S4_PATH_MARGIN == 32
    assert s4_attest.S4_MAX_WORST_PATH == conftest.S4_MAX_WORST_PATH == 216
    assert (
        s4_attest.s4_worst_suffix_length()
        == conftest.s4_worst_suffix_length()
        == 156
    )
    assert s4_attest.S4_PLATFORM_ROOT_ENV == conftest.S4_PLATFORM_ROOT_ENV


def test_longest_run_id_matches_the_real_modules():
    """The derivation must use the longest run id actually in use."""
    observed = _module_run_ids()
    assert observed, "no RUN_ID constants found in the S4 modules"
    longest = max(observed, key=len)
    assert len(longest) <= len(conftest.S4_LONGEST_RUN_ID), (
        "an S4 module uses a run id longer than the derivation assumes: "
        "{!r} exceeds {!r}".format(longest, conftest.S4_LONGEST_RUN_ID)
    )


def test_longest_artifact_leaf_matches_the_real_modules():
    """The derivation must use the longest artifact leaf actually in use."""
    observed = _artifact_leaves()
    assert observed, "no artifact leaves found in the S4 modules"
    longest = max(observed, key=len)
    assert len(longest) <= len(conftest.S4_LONGEST_ARTIFACT_LEAF), (
        "an S4 module creates an artifact leaf longer than the derivation "
        "assumes: {!r} exceeds {!r}".format(
            longest, conftest.S4_LONGEST_ARTIFACT_LEAF
        )
    )


def test_every_s4_module_binds_its_root():
    """A module that creates evidence runs must not use pytest's deep root."""
    for path in S4_TEST_MODULES:
        source = path.read_text(encoding="utf-8")
        assert "def tmp_path(s4_bounded_root)" in source, (
            "{} creates S4 evidence runs but does not bind the bounded "
            "root; its deepest path would follow pytest's tmp_path".format(
                path.name
            )
        )


def test_canonical_report_path_has_the_documented_headroom():
    """The canonical C:\\BrickRuns report path must clear 248 with margin."""
    report = Path("C:/BrickRuns/s4/s4-1beb3da085f4-0a1b2c3d")
    assert len(str(report)) == 40
    assert len(str(s4_attest.s4_platform_root_for(report))) == 44
    assert s4_attest.s4_worst_path_length(report) == 209
    assert s4_attest.s4_path_headroom(report) == 39
    assert s4_attest.s4_path_headroom(report) >= s4_attest.S4_PATH_MARGIN


def test_preflight_accepts_a_path_with_sufficient_headroom():
    report = Path("C:/BrickRuns/s4/s4-1beb3da085f4-0a1b2c3d")
    assert s4_attest.s4_path_headroom(report) >= s4_attest.S4_PATH_MARGIN


def test_preflight_rejects_a_path_with_insufficient_headroom():
    """One character past the margin must be refused, not merely warned about."""
    report = Path("C:/BrickRuns/s4/s4-1beb3da085f4-0a1b2c3d")
    padding = s4_attest.s4_path_headroom(report) - s4_attest.S4_PATH_MARGIN + 1
    too_long = Path(str(report.parent) + "/" + "x" * padding + "/" + report.name)
    assert s4_attest.s4_path_headroom(too_long) < s4_attest.S4_PATH_MARGIN


def test_bounded_root_stays_within_budget(tmp_path):
    """The fixture's own root must satisfy the bound it enforces."""
    assert conftest.s4_root_is_within_budget(tmp_path), (
        "bounded root is {} characters, budget {}".format(
            len(str(tmp_path)), conftest.S4_MAX_ROOT_LENGTH
        )
    )
    worst = len(str(tmp_path)) + conftest.s4_worst_suffix_length()
    assert worst <= conftest.S4_MAX_WORST_PATH
    assert worst < conftest.WINDOWS_DIRECTORY_PATH_LIMIT


@pytest.fixture
def tmp_path(s4_bounded_root):
    return s4_bounded_root


def test_attestor_environment_sets_the_bounded_root():
    env = s4_attest._native_test_environment(Path("C:/BrickRuns/s4/x/s4p"))
    assert env[s4_attest.S4_PLATFORM_ROOT_ENV] == str(
        Path("C:/BrickRuns/s4/x/s4p")
    )


def test_attestor_environment_never_inherits_an_operator_value(monkeypatch):
    """An inherited root would not be the one the attestor verified."""
    monkeypatch.setenv(s4_attest.S4_PLATFORM_ROOT_ENV, "C:/somewhere/else")
    env = s4_attest._native_test_environment()
    assert s4_attest.S4_PLATFORM_ROOT_ENV not in env
