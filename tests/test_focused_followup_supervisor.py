"""Static, model-free contract checks for the focused follow-up supervisor."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR = ROOT / "scripts" / "run-focused-followup.ps1"


def test_supervisor_is_tracked_score_blind_and_closed_to_operator_mutators():
    """The wrapper may orchestrate, but cannot change the frozen experiment."""

    text = SUPERVISOR.read_text(encoding="utf-8")
    assert "[ValidateSet(\"Authorize\", \"Run\")]" in text
    assert "function Start-Authorize" in text
    assert "function Start-Run" in text
    assert "return" in text[text.index("function Start-Authorize") : text.index("function Start-Run")]
    assert "validate-authorization" in text
    assert "validate-block-seal" in text
    assert "validate-termination" in text
    assert "validate-analysis" in text
    assert "validate-report" in text
    assert "--supervisor-path" in text
    assert "$script:SupervisorPath" in text
    assert "B1a" in text and "B1b" in text and "B2" in text
    assert "B2_start_cutoff" in text

    # There is intentionally no operator-facing switch for a phase, deadline,
    # model, seed, schedule, score, claim, or Run-mode run-ID.
    parameter_block = text[: text.index("Set-StrictMode")]
    forbidden = (
        "SkipB2",
        "Skip-B2",
        "--cutoff",
        "--hard-stop",
        "--deadline",
        "--model",
        "--seed",
        "--schedule",
        "--claim",
        "[string]$RunId",
        "[string]$RunsRoot",
        "[string]$AuthorizedRunId",
        "[string]$Python",
    )
    for token in forbidden:
        assert token not in parameter_block


def test_supervisor_has_marker_last_precedence_and_canonical_paths():
    text = SUPERVISOR.read_text(encoding="utf-8")
    assert "function Get-MarkerState" in text
    assert ".complete" in text
    assert "valid, independently re-derived marker is authoritative" in text
    assert "focused-followup-blocks" in text
    assert "focused-followup-terminations" in text
    assert "focused-followup-analysis" in text
    assert "focused-followup-reports" in text
    assert "recovered-calibration-analysis.json" in text
    assert "authorization.runs_root" in text
    assert '"authorization-bound runs root"' in text
    assert "ConvertFrom-Json" in text
    assert "score-blind" in text.lower()


def test_supervisor_recovers_completed_evidence_before_deriving_terminal_state():
    """A crash after the final attempt cannot discard an otherwise sealable block."""

    text = SUPERVISOR.read_text(encoding="utf-8")
    recovery = text[
        text.index("function Try-CoreTerminalDisposition") : text.index("function Invoke-BlockOrResume")
    ]
    assert '"seal-block"' in recovery
    assert '"environment_failure"' in recovery
    assert '"instrument_failure"' in recovery
    assert '"deadline"' in recovery
    assert recovery.index('"seal-block"') < recovery.index('"environment_failure"')
    assert "Get-BlockDisposition" in recovery
    assert '"--supervisor-path", $script:SupervisorPath' in recovery
    assert "Push-Location -LiteralPath $script:ProjectRoot" in text
    assert "Pop-Location" in text


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows PowerShell 5.1 native-stderr regression",
)
@pytest.mark.skipif(
    shutil.which("pwsh") is None and shutil.which("powershell") is None,
    reason="PowerShell is unavailable on this host",
)
def test_supervisor_captures_an_expected_rejected_core_command_without_native_abort():
    """PS 5.1 stderr must not abort the B2 cutoff/termination probe wrapper."""

    executable = shutil.which("pwsh") or shutil.which("powershell")
    fixture_root = ROOT / ".test-tmp-supervisor-native-error"
    shutil.rmtree(fixture_root, ignore_errors=True)
    fixture_root.mkdir(parents=True)
    authorization = fixture_root / "invalid-authorization.json"
    authorization.write_bytes(b"{}\n")
    authorization.with_name(authorization.name + ".complete").write_bytes(b"")
    try:
        result = subprocess.run(
            [
                executable,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SUPERVISOR),
                "-Mode",
                "Run",
                "-AuthorizationPath",
                str(authorization),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    finally:
        shutil.rmtree(fixture_root, ignore_errors=True)
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "authorization failed core cryptographic validation" in combined
    assert "NativeCommandError" not in combined


@pytest.mark.skipif(
    shutil.which("pwsh") is None and shutil.which("powershell") is None,
    reason="PowerShell is unavailable on this host",
)
@pytest.mark.parametrize("parameter", ["RunsRoot", "RunId", "AuthorizedRunId", "Python"])
def test_supervisor_has_no_operator_run_or_root_override(parameter):
    """Run identity and evidence root must come only from validated authorization."""

    executable = shutil.which("pwsh") or shutil.which("powershell")
    result = subprocess.run(
        [
            executable,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SUPERVISOR),
            "-Mode",
            "Run",
            "-AuthorizationPath",
            "not-used.json",
            "-" + parameter,
            "operator-value",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert parameter in combined
    assert "parameter" in combined.lower()


@pytest.mark.skipif(
    shutil.which("pwsh") is None and shutil.which("powershell") is None,
    reason="PowerShell parser is unavailable on this host",
)
def test_supervisor_parses_without_executing_a_phase():
    executable = shutil.which("pwsh") or shutil.which("powershell")
    command = (
        "$tokens=$null; $errors=$null; "
        "$null=[System.Management.Automation.Language.Parser]::ParseFile("
        "(Resolve-Path 'scripts/run-focused-followup.ps1'),[ref]$tokens,[ref]$errors); "
        "if($errors.Count){$errors | ForEach-Object {$_.Message}; exit 1}"
    )
    result = subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr + result.stdout
