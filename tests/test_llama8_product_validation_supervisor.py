from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run-llama8-product-validation.ps1"


def test_supervisor_has_fixed_score_blind_sequence_and_no_runtime_mutators():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'ValidateSet("Preflight", "Authorize", "Run", "Validate")' in text
    assert '@("validate", "--kind", "authorization")' in text
    assert '@("run")' in text
    assert '@("seal")' in text
    assert '@("analyze")' in text
    assert '@("report")' in text
    assert "bench.llama8_product_validation_verifier" in text
    assert "RunsRoot" not in text
    assert "RunId" not in text
    assert "Skip" not in text
    assert "deadline" not in text.casefold()


@pytest.mark.skipif(shutil.which("powershell") is None, reason="Windows PowerShell unavailable")
def test_supervisor_parses_under_windows_powershell():
    command = (
        "$errors=$null; [System.Management.Automation.Language.Parser]::ParseFile("
        f"'{str(SCRIPT).replace("'", "''")}', [ref]$null, [ref]$errors) | Out-Null; "
        "if ($errors.Count) { $errors | ForEach-Object { Write-Error $_ }; exit 1 }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
