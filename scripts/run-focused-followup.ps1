<#
.SYNOPSIS
Score-blind, marker-last supervisor for the frozen focused follow-up.

.DESCRIPTION
This is deliberately a small orchestration layer.  It never derives a score,
changes a schedule, chooses a deadline, or accepts a caller-supplied run ID in
Run mode.  Those decisions are made by `bench.focused_followup` from the
sealed authorization.  A JSON artifact is never trusted merely because it
exists: the corresponding core validation command must re-derive it from the
authorization and evidence before the supervisor resumes or advances.

Authorize writes and validates an authorization only, then returns.  Run
resumes the exact authorization-bound sequence B1a -> B1b -> B2 and finally
creates the canonical analysis and report.  It intentionally emits only
score-free phase/disposition messages.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Authorize", "Run")]
    [string]$Mode,

    [Parameter(Mandatory = $true)]
    [string]$AuthorizationPath,

    # Authorize-only inputs.  Run identity and evidence root are constants of
    # the frozen protocol, not operator inputs.
    [string]$PreflightPath,
    [string]$IssuedAt,
    [string]$Issuer
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$script:ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$script:SupervisorPath = [IO.Path]::GetFullPath($PSCommandPath)
$script:PythonExecutable = "python"

function Fail-Closed {
    param([Parameter(Mandatory = $true)][string]$Message)
    throw ("Focused follow-up supervisor: " + $Message)
}

function Resolve-ProjectPath {
    param(
        [Parameter(Mandatory = $true)][string]$PathText,
        [Parameter(Mandatory = $true)][string]$Label,
        [switch]$RequireExisting
    )

    if ([string]::IsNullOrWhiteSpace($PathText)) {
        Fail-Closed "$Label is empty"
    }
    if ([IO.Path]::IsPathRooted($PathText)) {
        $candidate = [IO.Path]::GetFullPath($PathText)
    } else {
        $candidate = [IO.Path]::GetFullPath((Join-Path $script:ProjectRoot $PathText))
    }
    $root = $script:ProjectRoot.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    $prefix = $root + [IO.Path]::DirectorySeparatorChar
    if (
        -not $candidate.Equals($root, [StringComparison]::OrdinalIgnoreCase) -and
        -not $candidate.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
    ) {
        Fail-Closed "$Label must remain inside the project root"
    }
    if ($RequireExisting -and -not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        Fail-Closed "$Label does not exist"
    }
    return $candidate
}

function Get-MarkerState {
    param([Parameter(Mandatory = $true)][string]$JsonPath)

    $markerPath = $JsonPath + ".complete"
    $jsonExists = Test-Path -LiteralPath $JsonPath -PathType Leaf
    $markerExists = Test-Path -LiteralPath $markerPath -PathType Leaf
    if (-not $jsonExists -and -not $markerExists) {
        return "Absent"
    }
    if (-not $jsonExists -or -not $markerExists) {
        return "Partial"
    }
    if ((Get-Item -LiteralPath $markerPath).Length -ne 0) {
        return "Partial"
    }
    return "Complete"
}

function Assert-MarkerNotPartial {
    param([Parameter(Mandatory = $true)][string]$JsonPath, [Parameter(Mandatory = $true)][string]$Label)
    if ((Get-MarkerState $JsonPath) -eq "Partial") {
        Fail-Closed "$Label has a partial marker-last publication"
    }
}

function Invoke-FocusedCore {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    # Capture all core output.  The core itself is score-free before analysis;
    # the supervisor deliberately never forwards raw output or an analysis.
    # Windows PowerShell 5.1 turns stderr from an expected rejected core
    # request into a terminating NativeCommandError when Stop is active.  A
    # rejected `terminate-block` is part of normal B2 eligibility probing, so
    # suppress that wrapper behavior only for this native invocation and let
    # the explicit exit-code/marker logic below decide the outcome.
    $priorErrorActionPreference = $ErrorActionPreference
    Push-Location -LiteralPath $script:ProjectRoot
    try {
        $ErrorActionPreference = "Continue"
        $output = @(& $script:PythonExecutable -m bench.focused_followup @Arguments 2>&1)
        $exitCode = $global:LASTEXITCODE
    } finally {
        $ErrorActionPreference = $priorErrorActionPreference
        Pop-Location
    }
    return [PSCustomObject]@{
        ExitCode = $exitCode
        Output   = $output
    }
}

function Invoke-CoreValidation {
    param([Parameter(Mandatory = $true)][string[]]$Arguments, [Parameter(Mandatory = $true)][string]$Label)
    $result = Invoke-FocusedCore $Arguments
    if ($null -eq $result.ExitCode -or $result.ExitCode -ne 0) {
        Fail-Closed "$Label failed core cryptographic validation"
    }
}

function Invoke-WriterThenValidate {
    param(
        [Parameter(Mandatory = $true)][string[]]$WriterArguments,
        [Parameter(Mandatory = $true)][string]$ArtifactPath,
        [Parameter(Mandatory = $true)][string[]]$ValidationArguments,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $state = Get-MarkerState $ArtifactPath
    if ($state -eq "Partial") {
        Fail-Closed "$Label has a partial marker-last publication"
    }
    if ($state -eq "Absent") {
        $result = Invoke-FocusedCore $WriterArguments
        # A valid, independently re-derived marker is authoritative even if a
        # Windows wrapper exposes a null/nonzero process exit after publication.
        $state = Get-MarkerState $ArtifactPath
        if ($state -eq "Partial") {
            Fail-Closed "$Label writer left a partial marker-last publication"
        }
        if ($state -eq "Absent" -and ($null -eq $result.ExitCode -or $result.ExitCode -ne 0)) {
            Fail-Closed "$Label writer failed before publishing valid evidence"
        }
        if ($state -eq "Absent") {
            Fail-Closed "$Label writer returned without a marker-last publication"
        }
    }
    Invoke-CoreValidation $ValidationArguments $Label
}

function Get-ValidatedAuthorization {
    param([Parameter(Mandatory = $true)][string]$Path)

    Assert-MarkerNotPartial $Path "authorization"
    if ((Get-MarkerState $Path) -ne "Complete") {
        Fail-Closed "authorization marker-last artifact is missing"
    }
    Invoke-CoreValidation @("validate-authorization", "--authorization", $Path) "authorization"
    try {
        $authorization = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Fail-Closed "authorization cannot be decoded after core validation"
    }
    foreach ($field in @("authorization_sha256", "run_id", "runs_root", "cutoffs")) {
        if ($null -eq $authorization.$field) {
            Fail-Closed "authorization lacks required $field after core validation"
        }
    }
    return $authorization
}

function Get-BlockDisposition {
    param(
        [Parameter(Mandatory = $true)]$Authorization,
        [Parameter(Mandatory = $true)][string]$EvidenceRoot,
        [Parameter(Mandatory = $true)][string]$RunId,
        [Parameter(Mandatory = $true)][ValidateSet("B1a", "B1b", "B2")][string]$Block
    )

    $digest = [string]$Authorization.authorization_sha256
    $sealPath = Join-Path $EvidenceRoot ("focused-followup-blocks" + [IO.Path]::DirectorySeparatorChar + $digest + [IO.Path]::DirectorySeparatorChar + $Block + ".json")
    $terminationPath = Join-Path $EvidenceRoot ("focused-followup-terminations" + [IO.Path]::DirectorySeparatorChar + $digest + [IO.Path]::DirectorySeparatorChar + $Block + ".json")
    $sealState = Get-MarkerState $sealPath
    $terminationState = Get-MarkerState $terminationPath
    if ($sealState -eq "Partial" -or $terminationState -eq "Partial") {
        Fail-Closed "$Block has a partial marker-last terminal artifact"
    }
    if ($sealState -eq "Complete" -and $terminationState -eq "Complete") {
        Fail-Closed "$Block has both sealed and terminated artifacts"
    }
    if ($sealState -eq "Complete") {
        Invoke-CoreValidation @(
            "validate-block-seal", "--authorization", $script:AuthorizationAbsolute,
            "--runs-root", $EvidenceRoot, "--run-id", $RunId, "--block", $Block
        ) "$Block sealed evidence"
        return [PSCustomObject]@{ Kind = "sealed"; Reason = $null }
    }
    if ($terminationState -eq "Complete") {
        Invoke-CoreValidation @(
            "validate-termination", "--authorization", $script:AuthorizationAbsolute,
            "--runs-root", $EvidenceRoot, "--run-id", $RunId, "--block", $Block
        ) "$Block terminal evidence"
        try {
            $termination = Get-Content -LiteralPath $terminationPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $reason = [string]$termination.reason
        } catch {
            Fail-Closed "$Block termination cannot be decoded after core validation"
        }
        if ($reason -notin @("deadline", "B2_start_cutoff", "environment_failure", "instrument_failure")) {
            Fail-Closed "$Block termination has an unrecognized reason"
        }
        return [PSCustomObject]@{ Kind = "terminated"; Reason = $reason }
    }
    return [PSCustomObject]@{ Kind = "absent"; Reason = $null }
}

function Try-CoreTerminalDisposition {
    param(
        [Parameter(Mandatory = $true)]$Authorization,
        [Parameter(Mandatory = $true)][string]$EvidenceRoot,
        [Parameter(Mandatory = $true)][string]$RunId,
        [Parameter(Mandatory = $true)][ValidateSet("B1a", "B1b", "B2")][string]$Block
    )

    # A process can finish every attempt and die before its final marker-last
    # seal.  Ask the core to reconstruct and seal that exact evidence before
    # considering an incomplete disposition or an exit code.
    $unused = Invoke-FocusedCore @(
        "seal-block", "--authorization", $script:AuthorizationAbsolute,
        "--runs-root", $EvidenceRoot, "--run-id", $RunId, "--block", $Block,
        "--supervisor-path", $script:SupervisorPath
    )
    $disposition = Get-BlockDisposition $Authorization $EvidenceRoot $RunId $Block
    if ($disposition.Kind -ne "absent") {
        return $disposition
    }

    # Each command is an attempted request to the core, not an operator-set
    # reason.  The core derives eligibility from evidence and frozen cutoffs;
    # rejected requests leave no artifact and are intentionally silent here.
    foreach ($reason in @("environment_failure", "instrument_failure", "deadline")) {
        $unused = Invoke-FocusedCore @(
            "terminate-block", "--authorization", $script:AuthorizationAbsolute,
            "--runs-root", $EvidenceRoot, "--run-id", $RunId,
            "--block", $Block, "--reason", $reason
        )
        $disposition = Get-BlockDisposition $Authorization $EvidenceRoot $RunId $Block
        if ($disposition.Kind -ne "absent") {
            return $disposition
        }
    }
    return [PSCustomObject]@{ Kind = "absent"; Reason = $null }
}

function Invoke-BlockOrResume {
    param(
        [Parameter(Mandatory = $true)]$Authorization,
        [Parameter(Mandatory = $true)][string]$EvidenceRoot,
        [Parameter(Mandatory = $true)][string]$RunId,
        [Parameter(Mandatory = $true)][ValidateSet("B1a", "B1b", "B2")][string]$Block
    )

    $existing = Get-BlockDisposition $Authorization $EvidenceRoot $RunId $Block
    if ($existing.Kind -ne "absent") {
        return $existing
    }
    Write-Host ("[focused-followup] {0}: running or resuming score-masked evidence" -f $Block)
    $result = Invoke-FocusedCore @(
        "run-block", "--authorization", $script:AuthorizationAbsolute,
        "--runs-root", $EvidenceRoot, "--run-id", $RunId, "--block", $Block,
        "--supervisor-path", $script:SupervisorPath
    )
    # The artifact is tested and cryptographically re-derived first.  This is
    # the intentional marker-last precedence over transport exit-code quirks.
    $after = Get-BlockDisposition $Authorization $EvidenceRoot $RunId $Block
    if ($after.Kind -eq "absent") {
        $after = Try-CoreTerminalDisposition $Authorization $EvidenceRoot $RunId $Block
    }
    if ($after.Kind -ne "absent") {
        return $after
    }
    if ($null -eq $result.ExitCode -or $result.ExitCode -ne 0) {
        Fail-Closed "$Block stopped without a valid core terminal artifact"
    }
    Fail-Closed "$Block returned without a marker-last terminal artifact"
}

function Resolve-B2Disposition {
    param(
        [Parameter(Mandatory = $true)]$Authorization,
        [Parameter(Mandatory = $true)][string]$EvidenceRoot,
        [Parameter(Mandatory = $true)][string]$RunId
    )

    $existing = Get-BlockDisposition $Authorization $EvidenceRoot $RunId "B2"
    if ($existing.Kind -ne "absent") {
        return $existing
    }
    # Ask the core to derive the sole zero-attempt B2 cutoff disposition.  A
    # failed attempt is expected while B2 remains eligible; no caller clock is
    # accepted, and the core alone compares sealed B1b timing to its frozen cutoff.
    $unused = Invoke-FocusedCore @(
        "terminate-block", "--authorization", $script:AuthorizationAbsolute,
        "--runs-root", $EvidenceRoot, "--run-id", $RunId,
        "--block", "B2", "--reason", "B2_start_cutoff"
    )
    $afterTermination = Get-BlockDisposition $Authorization $EvidenceRoot $RunId "B2"
    if ($afterTermination.Kind -ne "absent") {
        return $afterTermination
    }
    return Invoke-BlockOrResume $Authorization $EvidenceRoot $RunId "B2"
}

function Ensure-RecoveredCalibration {
    $recoveredPath = Join-Path $script:ProjectRoot "results-next-study\qualification-v230-r1\operations\artifacts\recovered-calibration-analysis.json"
    $state = Get-MarkerState $recoveredPath
    if ($state -eq "Partial") {
        Fail-Closed "recovered calibration has a partial marker-last publication"
    }
    if ($state -eq "Absent") {
        $result = Invoke-FocusedCore @("recover-calibration", "--output", $recoveredPath)
        $state = Get-MarkerState $recoveredPath
        if ($state -eq "Partial") {
            Fail-Closed "recovered calibration writer left a partial marker-last publication"
        }
        if ($state -eq "Absent" -and ($null -eq $result.ExitCode -or $result.ExitCode -ne 0)) {
            Fail-Closed "recovered calibration writer failed before publication"
        }
        if ($state -eq "Absent") {
            Fail-Closed "recovered calibration writer returned without publication"
        }
    }
    return $recoveredPath
}

function Publish-FinalArtifacts {
    param(
        [Parameter(Mandatory = $true)]$Authorization,
        [Parameter(Mandatory = $true)][string]$EvidenceRoot,
        [Parameter(Mandatory = $true)][string]$RunId,
        [AllowNull()][string]$FallbackReason
    )

    $digest = [string]$Authorization.authorization_sha256
    $recovered = Ensure-RecoveredCalibration
    $analysisPath = Join-Path $EvidenceRoot ("focused-followup-analysis" + [IO.Path]::DirectorySeparatorChar + $digest + [IO.Path]::DirectorySeparatorChar + "analysis.json")
    $analysisArgs = @(
        "analyze", "--authorization", $script:AuthorizationAbsolute,
        "--runs-root", $EvidenceRoot, "--run-id", $RunId,
        "--output", $analysisPath, "--recovered-calibration", $recovered
    )
    if ($null -ne $FallbackReason) {
        if ($FallbackReason -notin @("deadline", "environment_failure")) {
            Fail-Closed "only core-validated B1b deadline/environment termination can request fallback"
        }
        $analysisArgs += @("--allow-fallback", "--fallback-reason", $FallbackReason)
    }
    Invoke-WriterThenValidate $analysisArgs $analysisPath @(
        "validate-analysis", "--authorization", $script:AuthorizationAbsolute,
        "--analysis", $analysisPath, "--runs-root", $EvidenceRoot,
        "--run-id", $RunId, "--recovered-calibration", $recovered
    ) "analysis"

    $reportPath = Join-Path $EvidenceRoot ("focused-followup-reports" + [IO.Path]::DirectorySeparatorChar + $digest + [IO.Path]::DirectorySeparatorChar + "study-report.json")
    Invoke-WriterThenValidate @(
        "report", "--authorization", $script:AuthorizationAbsolute,
        "--analysis", $analysisPath, "--runs-root", $EvidenceRoot,
        "--run-id", $RunId, "--recovered-calibration", $recovered,
        "--output", $reportPath
    ) $reportPath @(
        "validate-report", "--authorization", $script:AuthorizationAbsolute,
        "--analysis", $analysisPath, "--report", $reportPath,
        "--runs-root", $EvidenceRoot, "--run-id", $RunId,
        "--recovered-calibration", $recovered
    ) "report"
    Write-Host "[focused-followup] canonical evidence-derived analysis and report validated"
}

function Start-Authorize {
    $authorization = Resolve-ProjectPath $AuthorizationPath "authorization output"
    $preflight = Resolve-ProjectPath $PreflightPath "preflight" -RequireExisting
    Assert-MarkerNotPartial $authorization "authorization"
    if ((Get-MarkerState $authorization) -ne "Absent") {
        Fail-Closed "authorization output is already published and may not be replaced"
    }
    $result = Invoke-FocusedCore @(
        "authorize", "--preflight", $preflight, "--output", $authorization,
        "--issued-at", $IssuedAt, "--issuer", $Issuer,
        "--supervisor-path", $script:SupervisorPath
    )
    # The `.complete` marker plus core validator is authoritative even if an
    # outer Windows process loses its final exit-code update.
    if ((Get-MarkerState $authorization) -eq "Complete") {
        Invoke-CoreValidation @("validate-authorization", "--authorization", $authorization) "authorization"
        Write-Host "[focused-followup] authorization published and validated; no block was started"
        return
    }
    Assert-MarkerNotPartial $authorization "authorization"
    if ($null -eq $result.ExitCode -or $result.ExitCode -ne 0) {
        Fail-Closed "authorization failed before marker-last publication"
    }
    Fail-Closed "authorization returned without marker-last publication"
}

function Start-Run {
    $script:AuthorizationAbsolute = Resolve-ProjectPath $AuthorizationPath "authorization" -RequireExisting
    $authorization = Get-ValidatedAuthorization $script:AuthorizationAbsolute
    $runId = [string]$authorization.run_id
    $evidenceRoot = Resolve-ProjectPath ([string]$authorization.runs_root) "authorization-bound runs root"
    # Cutoffs are read only for a score-free status line.  The core owns every
    # comparison and is never passed a supervisor-provided deadline.
    $hardStop = [string]$authorization.cutoffs.hard_stop
    Write-Host ("[focused-followup] validated authorization; run={0}; hard-stop={1}" -f $runId, $hardStop)

    $b1a = Invoke-BlockOrResume $authorization $evidenceRoot $runId "B1a"
    if ($b1a.Kind -eq "terminated") {
        # No partial B1a primary is eligible, including environment termination.
        Publish-FinalArtifacts $authorization $evidenceRoot $runId $null
        return
    }

    $b1b = Invoke-BlockOrResume $authorization $evidenceRoot $runId "B1b"
    if ($b1b.Kind -eq "terminated") {
        if ($b1b.Reason -in @("deadline", "environment_failure")) {
            # Core rechecks this exact termination and emits the only permitted
            # B1a fallback; B2 is deliberately ineligible in this branch.
            Publish-FinalArtifacts $authorization $evidenceRoot $runId $b1b.Reason
        } elseif ($b1b.Reason -eq "instrument_failure") {
            Publish-FinalArtifacts $authorization $evidenceRoot $runId $null
        } else {
            Fail-Closed "B1b has a terminal disposition not eligible for analysis"
        }
        return
    }

    $b2 = Resolve-B2Disposition $authorization $evidenceRoot $runId
    if ($b2.Kind -eq "absent") {
        Fail-Closed "B2 has no core-validated terminal disposition"
    }
    # B2 is secondary only; core refuses interim B1 analysis until B2 seals or
    # a validated terminal disposition is present.
    Publish-FinalArtifacts $authorization $evidenceRoot $runId $null
}

if ($Mode -eq "Authorize") {
    if (
        [string]::IsNullOrWhiteSpace($PreflightPath) -or
        [string]::IsNullOrWhiteSpace($IssuedAt) -or
        [string]::IsNullOrWhiteSpace($Issuer)
    ) {
        Fail-Closed "Authorize requires preflight, issued-at, and issuer only"
    }
    Start-Authorize
    return
}

if (
    -not [string]::IsNullOrWhiteSpace($PreflightPath) -or
    -not [string]::IsNullOrWhiteSpace($IssuedAt) -or
    -not [string]::IsNullOrWhiteSpace($Issuer)
) {
    Fail-Closed "Run accepts only the sealed authorization; all operational inputs are bound in authorization"
}
Start-Run
