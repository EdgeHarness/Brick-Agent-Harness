"""Model-free contract checks for the v0.13.6 recovery successor supervisor."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR = ROOT / "scripts" / "run-focused-recovery-successor.ps1"


def test_successor_supervisor_is_thin_fixed_path_score_blind_orchestration():
    text = SUPERVISOR.read_text(encoding="utf-8")

    assert '[ValidateSet("Authorize", "Run")]' in text
    assert '"bench.focused_recovery_successor"' in text
    assert '"results-next-study\\focused-recovery-v0136\\authorization.json"' in text
    assert '"B1b_recovery"' in text and '"B2_repeatability"' in text
    assert "function Start-Authorize" in text
    assert "function Start-Run" in text
    assert "function Invoke-BlockOrResume" in text
    assert "function Publish-FinalArtifacts" in text
    assert '"analyze", "--output"' in text
    assert '"report", "--output"' in text
    assert '"release"' in text
    assert '"bench.focused_recovery_release_verifier"' in text
    assert '"verify", "--output", $paths.Verification' in text
    assert '"recover-stale-lease"' in text
    assert '"validate", "--kind", "authorization"' in text
    assert '"validate", "--kind", "block", "--block", $Block' in text
    assert '"validate", "--kind", "analysis"' in text
    assert '"validate", "--kind", "report"' in text
    assert '"validate", "--kind", "release"' in text
    assert "JsonOnly" in text
    assert "MarkerOnly" in text and "NonemptyMarker" in text
    assert "both terminal lanes" in text
    assert "Push-Location -LiteralPath $script:ProjectRoot" in text
    assert "Pop-Location" in text
    assert "NativeCommandError" in text
    assert "scores" not in text[text.index("function Start-Run") :].lower().replace("score-masked", "")

    parameter_block = text[text.index("[CmdletBinding()]") : text.index("Set-StrictMode")]
    forbidden = (
        "AuthorizationPath",
        "PreflightPath",
        "RunsRoot",
        "RunId",
        "Schedule",
        "Label",
        "Fallback",
        "Python",
        "Model",
        "Seed",
        "Claim",
        "Deadline",
        "HardStop",
    )
    for token in forbidden:
        assert token not in parameter_block


def test_successor_supervisor_has_no_direct_model_or_git_mutation_commands():
    """The wrapper invokes only the fixed core; it never invokes a model itself."""

    text = SUPERVISOR.read_text(encoding="utf-8").lower()
    for forbidden in (
        "ollama run",
        "ollama chat",
        "invoke-webrequest",
        "curl ",
        "git commit",
        "git tag",
        "git push",
        "git pull",
    ):
        assert forbidden not in text
    assert "bench.next_study_live" in text  # fixed, model-free native preflight only
    assert "live_model_calls" not in text


def test_successor_supervisor_requires_b2_after_any_b1b_terminal_state():
    text = SUPERVISOR.read_text(encoding="utf-8")
    start = text[text.index("function Start-Run") : text.index("if ($Mode -eq \"Authorize\")")]
    assert 'Invoke-BlockOrResume "B1b_recovery" $authorizationSha256' in start
    assert 'Invoke-BlockOrResume "B2_repeatability" $authorizationSha256' in start
    assert start.index('"B1b_recovery"') < start.index('"B2_repeatability"')
    assert "if ($b1b" not in start
    assert start.index('"B2_repeatability"') < start.index("Publish-FinalArtifacts")


@pytest.mark.skipif(
    shutil.which("pwsh") is None and shutil.which("powershell") is None,
    reason="PowerShell is unavailable on this host",
)
def test_successor_supervisor_parses_without_executing_any_phase():
    executable = shutil.which("pwsh") or shutil.which("powershell")
    command = (
        "$tokens=$null; $errors=$null; "
        "$null=[System.Management.Automation.Language.Parser]::ParseFile("
        "(Resolve-Path 'scripts/run-focused-recovery-successor.ps1'),[ref]$tokens,[ref]$errors); "
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


@pytest.mark.skipif(
    shutil.which("pwsh") is None and shutil.which("powershell") is None,
    reason="PowerShell is unavailable on this host",
)
def test_successor_supervisor_authorize_refuses_missing_metadata_before_core_execution():
    """An executable negative path proves no preflight/model work is started."""

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
            "Authorize",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    combined = re.sub(
        r"\x1b\[[0-?]*[ -/]*[@-~]", "", result.stdout + result.stderr,
    )
    assert result.returncode != 0
    assert "Authorize requires issued-at and issuer metadata only" in combined
    assert "cell_complete" not in combined
    assert "NativeCommandError" not in combined


@pytest.mark.skipif(
    shutil.which("pwsh") is None and shutil.which("powershell") is None,
    reason="PowerShell is unavailable on this host",
)
@pytest.mark.parametrize(
    "parameter",
    ["AuthorizationPath", "PreflightPath", "RunsRoot", "RunId", "Schedule", "Python"],
)
def test_successor_supervisor_rejects_operator_identity_overrides_before_execution(parameter):
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
    assert "cell_complete" not in combined


def _write_supervisor_fixture(
    *,
    fail_without_terminal: bool,
    json_only_publications: bool = False,
    authorization_json_only: bool = False,
    invalid_terminal_marker: str | None = None,
    preexisting_verification_with_failure: bool = False,
) -> tuple[Path, dict[str, str]]:
    """Create an isolated project root whose fixed `python` is a no-inference stub.

    The real supervisor has no Python/path override by design.  Copying it to a
    throwaway root and placing a `python.cmd` first on PATH lets this test
    exercise the actual orchestration shell code without contacting Ollama or
    modifying the real successor evidence root.
    """

    # Keep the Windows fixture path below the legacy 260-character boundary;
    # terminal artifact paths intentionally include a 64-character digest.
    fixture_root = Path(tempfile.mkdtemp(prefix=".test-tmp-supervisor-", dir=ROOT))
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "--", fixture_root.relative_to(ROOT).as_posix() + "/"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if ignored.returncode != 0:
        shutil.rmtree(fixture_root, ignore_errors=True)
        raise AssertionError("supervisor fixture root is not ignored by Git")
    scripts = fixture_root / "scripts"
    scripts.mkdir(parents=True)
    fixture_supervisor = scripts / SUPERVISOR.name
    shutil.copy2(SUPERVISOR, fixture_supervisor)

    auth_sha = "a" * 64
    auth_dir = fixture_root / "results-next-study" / "focused-recovery-v0136"
    auth_dir.mkdir(parents=True)
    authorization = auth_dir / "authorization.json"
    authorization.write_text(
        """{
  "authorization_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "analysis_embargo": "both_blocks_terminal",
  "run_specs": {
    "B1b_recovery": {"run_id": "v0136-b1b-recovery-r1"},
    "B2_repeatability": {"run_id": "v0136-b2-repeatability-r1"}
  }
}
""",
        encoding="utf-8",
    )
    if not authorization_json_only:
        authorization.with_name(authorization.name + ".complete").write_bytes(b"")

    # The authorization writer needs a fixed completed preflight when an
    # executable test exercises recovery of an authorization JSON-only state.
    preflight = auth_dir / "native-preflight.json"
    preflight.write_text("{}\n", encoding="utf-8")
    preflight.with_name(preflight.name + ".complete").write_bytes(b"")

    stub_dir = fixture_root / "stub-bin"
    stub_dir.mkdir()
    # `python.cmd` is deliberately only a launcher.  The argument-sensitive
    # fake core is Python so file paths with spaces cannot accidentally alter
    # the test's command semantics in cmd.exe.
    stub_core = f'''from pathlib import Path
import os
import sys

root = Path(r"{fixture_root}")
auth = "{auth_sha}"
module = sys.argv[2]
command = sys.argv[3]
args = sys.argv[4:]
(root / "call-log.txt").open("a", encoding="utf-8").write(" ".join([module, command, *args]) + "\\n")
print("RAW_CORE_OUTPUT_MUST_NOT_SURFACE")

def publish(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("{{}}\\n", encoding="utf-8")
    marker = path.with_name(path.name + ".complete")
    if not marker.exists():
        marker.write_bytes(b"")

if module == "bench.focused_recovery_release_verifier":
    if command != "verify":
        raise SystemExit(40)
    manifest = root / "results-next-study" / "focused-recovery-v0136" / "release" / auth / "manifest.json.complete"
    if not manifest.is_file():
        raise SystemExit(35)
    if os.environ.get("STUB_VERIFIER_FAIL") == "1":
        raise SystemExit(66)
    publish(root / "results-next-study" / "focused-recovery-v0136" / "release" / auth / "independent-verification.json")
    raise SystemExit(0)

if module != "bench.focused_recovery_successor":
    raise SystemExit(40)

if command == "validate":
    raise SystemExit(0)
if command == "recover-stale-lease":
    raise SystemExit(0)
if command == "authorize":
    publish(root / "results-next-study" / "focused-recovery-v0136" / "authorization.json")
    raise SystemExit(0)
if command == "run-block":
    block = args[args.index("--block") + 1]
    if block == "B1b_recovery":
        if os.environ.get("STUB_FAIL_NO_TERMINAL") == "1":
            raise SystemExit(19)
        publish(root / "results-next-study" / "focused-recovery-v0136" / "b1b-recovery" / "focused-recovery-terminations" / auth / "B1b_recovery.json")
        raise SystemExit(17)
    if block == "B2_repeatability":
        predecessor = root / "results-next-study" / "focused-recovery-v0136" / "b1b-recovery" / "focused-recovery-terminations" / auth / "B1b_recovery.json.complete"
        if not predecessor.is_file():
            raise SystemExit(31)
        publish(root / "results-next-study" / "focused-recovery-v0136" / "b2-repeatability" / "focused-recovery-seals" / auth / "B2_repeatability.json")
        raise SystemExit(0)
if command == "analyze":
    b2 = root / "results-next-study" / "focused-recovery-v0136" / "b2-repeatability" / "focused-recovery-seals" / auth / "B2_repeatability.json.complete"
    if not b2.is_file():
        raise SystemExit(32)
    publish(root / "results-next-study" / "focused-recovery-v0136" / "analysis" / auth / "analysis.json")
    raise SystemExit(0)
if command == "report":
    analysis = root / "results-next-study" / "focused-recovery-v0136" / "analysis" / auth / "analysis.json.complete"
    if not analysis.is_file():
        raise SystemExit(33)
    publish(root / "results-next-study" / "focused-recovery-v0136" / "reports" / auth / "report.json")
    raise SystemExit(0)
if command == "release":
    report = root / "results-next-study" / "focused-recovery-v0136" / "reports" / auth / "report.json.complete"
    if not report.is_file():
        raise SystemExit(34)
    release_root = root / "results-next-study" / "focused-recovery-v0136" / "release" / auth
    publish(release_root / "archive.json")
    publish(release_root / "manifest.json")
    raise SystemExit(0)
raise SystemExit(41)
'''
    (stub_dir / "stub_core.py").write_text(stub_core, encoding="utf-8")
    launcher = f'@echo off\r\n"{sys.executable}" "%~dp0stub_core.py" %*\r\nexit /b %ERRORLEVEL%\r\n'
    (stub_dir / "python.cmd").write_text(launcher, encoding="utf-8", newline="")
    environment = os.environ.copy()
    environment["PATH"] = str(stub_dir) + os.pathsep + environment.get("PATH", "")
    environment["PATHEXT"] = ".CMD;.BAT;.EXE;.COM"
    if fail_without_terminal:
        environment["STUB_FAIL_NO_TERMINAL"] = "1"
    else:
        environment.pop("STUB_FAIL_NO_TERMINAL", None)
    if preexisting_verification_with_failure:
        environment["STUB_VERIFIER_FAIL"] = "1"
    else:
        environment.pop("STUB_VERIFIER_FAIL", None)
    if invalid_terminal_marker is not None:
        terminal = (
            auth_dir
            / "b1b-recovery"
            / "focused-recovery-terminations"
            / auth_sha
            / "B1b_recovery.json"
        )
        terminal.parent.mkdir(parents=True, exist_ok=True)
        marker = terminal.with_name(terminal.name + ".complete")
        if invalid_terminal_marker == "marker_only":
            marker.write_bytes(b"")
        elif invalid_terminal_marker == "nonempty_marker":
            terminal.write_text("{}\n", encoding="utf-8")
            marker.write_text("not empty", encoding="utf-8")
        else:
            raise ValueError("unknown invalid terminal marker fixture")

    if json_only_publications:
        for partial in (
            auth_dir / "b1b-recovery" / "focused-recovery-terminations" / auth_sha / "B1b_recovery.json",
            auth_dir / "analysis" / auth_sha / "analysis.json",
            auth_dir / "reports" / auth_sha / "report.json",
            auth_dir / "release" / auth_sha / "archive.json",
            auth_dir / "release" / auth_sha / "manifest.json",
            auth_dir / "release" / auth_sha / "independent-verification.json",
        ):
            partial.parent.mkdir(parents=True, exist_ok=True)
            partial.write_text("{}\n", encoding="utf-8")

    if preexisting_verification_with_failure:
        verification = auth_dir / "release" / auth_sha / "independent-verification.json"
        verification.parent.mkdir(parents=True, exist_ok=True)
        verification.write_text("{}\n", encoding="utf-8")
        verification.with_name(verification.name + ".complete").write_bytes(b"")

    return fixture_supervisor, environment


@pytest.mark.skipif(
    os.name != "nt" or (shutil.which("pwsh") is None and shutil.which("powershell") is None),
    reason="Windows PowerShell is unavailable on this host",
)
def test_successor_supervisor_masked_stub_advances_terminated_b1b_then_b2_before_analysis():
    """Executable no-inference test of the core orchestration safety branch."""

    fixture_supervisor, environment = _write_supervisor_fixture(fail_without_terminal=False)
    executable = shutil.which("pwsh") or shutil.which("powershell")
    try:
        result = subprocess.run(
            [
                executable,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(fixture_supervisor),
                "-Mode",
                "Run",
            ],
            cwd=fixture_supervisor.parents[1],
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, combined
        assert "RAW_CORE_OUTPUT_MUST_NOT_SURFACE" not in combined
        assert "B1b_recovery terminal: terminated" in combined
        assert "B2_repeatability terminal: sealed" in combined
        assert "both terminal lanes, canonical artifacts, and independent release verification validated" in combined

        calls = (fixture_supervisor.parents[1] / "call-log.txt").read_text(encoding="utf-8").splitlines()
        b1b_run = next(index for index, value in enumerate(calls) if value.startswith("bench.focused_recovery_successor run-block --block B1b_recovery"))
        b2_run = next(index for index, value in enumerate(calls) if value.startswith("bench.focused_recovery_successor run-block --block B2_repeatability"))
        analyze = next(index for index, value in enumerate(calls) if value.startswith("bench.focused_recovery_successor analyze --output"))
        report = next(index for index, value in enumerate(calls) if value.startswith("bench.focused_recovery_successor report --output"))
        release = next(index for index, value in enumerate(calls) if value == "bench.focused_recovery_successor release")
        release_validate = next(index for index, value in enumerate(calls) if value == "bench.focused_recovery_successor validate --kind release")
        verifier = next(index for index, value in enumerate(calls) if value.startswith("bench.focused_recovery_release_verifier verify --output"))
        assert b1b_run < b2_run < analyze < report < release < release_validate < verifier
        assert any(value == "bench.focused_recovery_successor recover-stale-lease" for value in calls[:b1b_run])
        assert any(value == "bench.focused_recovery_successor recover-stale-lease" for value in calls[b1b_run:b2_run])
        assert any(value.startswith("bench.focused_recovery_successor validate --kind block --block B1b_recovery") for value in calls)
        assert any(value.startswith("bench.focused_recovery_successor validate --kind block --block B2_repeatability") for value in calls)
    finally:
        shutil.rmtree(fixture_supervisor.parents[1], ignore_errors=True)


@pytest.mark.skipif(
    os.name != "nt" or (shutil.which("pwsh") is None and shutil.which("powershell") is None),
    reason="Windows PowerShell is unavailable on this host",
)
def test_successor_supervisor_requires_a_fresh_independent_verifier_success_on_replay():
    """A stale completed verification marker cannot hide a failed rederivation."""

    fixture_supervisor, environment = _write_supervisor_fixture(
        fail_without_terminal=False,
        preexisting_verification_with_failure=True,
    )
    executable = shutil.which("pwsh") or shutil.which("powershell")
    try:
        result = subprocess.run(
            [
                executable,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(fixture_supervisor),
                "-Mode",
                "Run",
            ],
            cwd=fixture_supervisor.parents[1],
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        combined = result.stdout + result.stderr
        assert result.returncode != 0
        assert "independent release verification failed validation" in combined
        assert "both terminal lanes, canonical artifacts, and independent release verification validated" not in combined
        assert "RAW_CORE_OUTPUT_MUST_NOT_SURFACE" not in combined
        calls = (fixture_supervisor.parents[1] / "call-log.txt").read_text(encoding="utf-8").splitlines()
        assert "bench.focused_recovery_successor release" in calls
        assert any(value.startswith("bench.focused_recovery_release_verifier verify --output") for value in calls)
    finally:
        shutil.rmtree(fixture_supervisor.parents[1], ignore_errors=True)


@pytest.mark.skipif(
    os.name != "nt" or (shutil.which("pwsh") is None and shutil.which("powershell") is None),
    reason="Windows PowerShell is unavailable on this host",
)
def test_successor_supervisor_stub_fails_closed_when_b1b_has_no_terminal_artifact():
    """A nonzero core exit without a marker cannot advance B2 or publish output."""

    fixture_supervisor, environment = _write_supervisor_fixture(fail_without_terminal=True)
    executable = shutil.which("pwsh") or shutil.which("powershell")
    try:
        result = subprocess.run(
            [
                executable,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(fixture_supervisor),
                "-Mode",
                "Run",
            ],
            cwd=fixture_supervisor.parents[1],
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        combined = result.stdout + result.stderr
        assert result.returncode != 0
        assert "B1b_recovery stopped without a valid terminal artifact" in combined
        assert "RAW_CORE_OUTPUT_MUST_NOT_SURFACE" not in combined
        calls = (fixture_supervisor.parents[1] / "call-log.txt").read_text(encoding="utf-8").splitlines()
        assert any(value.startswith("bench.focused_recovery_successor run-block --block B1b_recovery") for value in calls)
        assert not any("B2_repeatability" in value for value in calls)
        assert not any(
            value.startswith("bench.focused_recovery_successor analyze")
            or value.startswith("bench.focused_recovery_successor report")
            or value.startswith("bench.focused_recovery_successor release")
            or value.startswith("bench.focused_recovery_release_verifier")
            for value in calls
        )
    finally:
        shutil.rmtree(fixture_supervisor.parents[1], ignore_errors=True)


@pytest.mark.skipif(
    os.name != "nt" or (shutil.which("pwsh") is None and shutil.which("powershell") is None),
    reason="Windows PowerShell is unavailable on this host",
)
def test_successor_supervisor_routes_json_only_publications_to_their_owning_commands():
    """JSON-only artifacts are never trusted by the wrapper as completed."""

    fixture_supervisor, environment = _write_supervisor_fixture(
        fail_without_terminal=False,
        json_only_publications=True,
    )
    executable = shutil.which("pwsh") or shutil.which("powershell")
    try:
        result = subprocess.run(
            [
                executable,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(fixture_supervisor),
                "-Mode",
                "Run",
            ],
            cwd=fixture_supervisor.parents[1],
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, combined
        assert "RAW_CORE_OUTPUT_MUST_NOT_SURFACE" not in combined

        fixture_root = fixture_supervisor.parents[1]
        auth = "a" * 64
        expected_markers = (
            fixture_root
            / "results-next-study"
            / "focused-recovery-v0136"
            / "b1b-recovery"
            / "focused-recovery-terminations"
            / auth
            / "B1b_recovery.json.complete",
            fixture_root / "results-next-study" / "focused-recovery-v0136" / "analysis" / auth / "analysis.json.complete",
            fixture_root / "results-next-study" / "focused-recovery-v0136" / "reports" / auth / "report.json.complete",
            fixture_root / "results-next-study" / "focused-recovery-v0136" / "release" / auth / "archive.json.complete",
            fixture_root / "results-next-study" / "focused-recovery-v0136" / "release" / auth / "manifest.json.complete",
            fixture_root
            / "results-next-study"
            / "focused-recovery-v0136"
            / "release"
            / auth
            / "independent-verification.json.complete",
        )
        assert all(path.is_file() and path.stat().st_size == 0 for path in expected_markers)

        calls = (fixture_root / "call-log.txt").read_text(encoding="utf-8").splitlines()
        assert any(value.startswith("bench.focused_recovery_successor run-block --block B1b_recovery") for value in calls)
        assert any(value.startswith("bench.focused_recovery_successor analyze --output") for value in calls)
        assert any(value.startswith("bench.focused_recovery_successor report --output") for value in calls)
        assert "bench.focused_recovery_successor release" in calls
        assert any(value.startswith("bench.focused_recovery_release_verifier verify --output") for value in calls)
    finally:
        shutil.rmtree(fixture_supervisor.parents[1], ignore_errors=True)


@pytest.mark.skipif(
    os.name != "nt" or (shutil.which("pwsh") is None and shutil.which("powershell") is None),
    reason="Windows PowerShell is unavailable on this host",
)
def test_successor_supervisor_recovers_authorization_json_only_only_via_authorize():
    fixture_supervisor, environment = _write_supervisor_fixture(
        fail_without_terminal=False,
        authorization_json_only=True,
    )
    executable = shutil.which("pwsh") or shutil.which("powershell")
    try:
        result = subprocess.run(
            [
                executable,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(fixture_supervisor),
                "-Mode",
                "Authorize",
                "-IssuedAt",
                "2026-08-10T12:00:00-05:00",
                "-Issuer",
                "test-authorizer",
            ],
            cwd=fixture_supervisor.parents[1],
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, combined
        assert "RAW_CORE_OUTPUT_MUST_NOT_SURFACE" not in combined
        authorization_marker = (
            fixture_supervisor.parents[1]
            / "results-next-study"
            / "focused-recovery-v0136"
            / "authorization.json.complete"
        )
        assert authorization_marker.is_file() and authorization_marker.stat().st_size == 0
        calls = (fixture_supervisor.parents[1] / "call-log.txt").read_text(encoding="utf-8").splitlines()
        assert any(value.startswith("bench.focused_recovery_successor authorize --preflight") for value in calls)
        assert not any("run-block" in value or "cell_complete" in value for value in calls)
    finally:
        shutil.rmtree(fixture_supervisor.parents[1], ignore_errors=True)


@pytest.mark.skipif(
    os.name != "nt" or (shutil.which("pwsh") is None and shutil.which("powershell") is None),
    reason="Windows PowerShell is unavailable on this host",
)
def test_successor_supervisor_run_never_treats_authorization_json_only_as_authorized():
    fixture_supervisor, environment = _write_supervisor_fixture(
        fail_without_terminal=False,
        authorization_json_only=True,
    )
    executable = shutil.which("pwsh") or shutil.which("powershell")
    try:
        result = subprocess.run(
            [
                executable,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(fixture_supervisor),
                "-Mode",
                "Run",
            ],
            cwd=fixture_supervisor.parents[1],
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        combined = result.stdout + result.stderr
        assert result.returncode != 0
        assert "authorization is JSON-only and must be recovered by its exact owning command" in combined
        assert "RAW_CORE_OUTPUT_MUST_NOT_SURFACE" not in combined
        assert not (fixture_supervisor.parents[1] / "call-log.txt").exists()
    finally:
        shutil.rmtree(fixture_supervisor.parents[1], ignore_errors=True)


@pytest.mark.skipif(
    os.name != "nt" or (shutil.which("pwsh") is None and shutil.which("powershell") is None),
    reason="Windows PowerShell is unavailable on this host",
)
@pytest.mark.parametrize("invalid_terminal_marker", ("marker_only", "nonempty_marker"))
def test_successor_supervisor_rejects_invalid_terminal_markers_before_core_execution(invalid_terminal_marker):
    fixture_supervisor, environment = _write_supervisor_fixture(
        fail_without_terminal=False,
        invalid_terminal_marker=invalid_terminal_marker,
    )
    executable = shutil.which("pwsh") or shutil.which("powershell")
    try:
        result = subprocess.run(
            [
                executable,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(fixture_supervisor),
                "-Mode",
                "Run",
            ],
            cwd=fixture_supervisor.parents[1],
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        combined = result.stdout + result.stderr
        assert result.returncode != 0
        assert "B1b_recovery termination" in combined
        assert "RAW_CORE_OUTPUT_MUST_NOT_SURFACE" not in combined
        calls = (fixture_supervisor.parents[1] / "call-log.txt").read_text(encoding="utf-8").splitlines()
        assert calls == ["bench.focused_recovery_successor validate --kind authorization"]
    finally:
        shutil.rmtree(fixture_supervisor.parents[1], ignore_errors=True)
