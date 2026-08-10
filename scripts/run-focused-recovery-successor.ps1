<#
.SYNOPSIS
Score-blind supervisor for the v0.13.6 focused-recovery successor.

.DESCRIPTION
This is a deliberately thin orchestration boundary.  It owns no schedule,
model, evidence root, run identity, label, fallback decision, or Python
override.  Those values are fixed in `bench.focused_recovery_successor` and
are cryptographically bound into the marker-last authorization.

`Authorize` collects one fixed-path, model-free native preflight and publishes
the fixed-path authorization.  It never starts a cell.  `Run` validates that
authorization, resumes the exact B1b recovery if necessary, then always runs
or validates B2 repeatability after B1b reaches *any* valid terminal state.
Only after both blocks have terminal artifacts does it publish the canonical
analysis and report.  Core output is captured rather than forwarded so this
script cannot expose efficacy while the embargo remains in force.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Authorize", "Run")]
    [string]$Mode,

    # These are authorization metadata, not experiment controls.  Paths,
    # schedules, runs, blocks, model/runtime, and labels remain constants.
    [string]$IssuedAt,
    [string]$Issuer
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$script:SupervisorPath = [IO.Path]::GetFullPath($PSCommandPath)
$script:PythonExecutable = "python"
$script:CoreModule = "bench.focused_recovery_successor"
$script:ReleaseVerifierModule = "bench.focused_recovery_release_verifier"
$script:PreflightPath = Join-Path $script:ProjectRoot "results-next-study\focused-recovery-v0136\native-preflight.json"
$script:AuthorizationPath = Join-Path $script:ProjectRoot "results-next-study\focused-recovery-v0136\authorization.json"
$script:SuccessorRoot = Join-Path $script:ProjectRoot "results-next-study\focused-recovery-v0136"
$script:BlockSpecs = @{
    "B1b_recovery" = @{
        RunsRoot = Join-Path $script:SuccessorRoot "b1b-recovery"
        RunId = "v0136-b1b-recovery-r1"
    }
    "B2_repeatability" = @{
        RunsRoot = Join-Path $script:SuccessorRoot "b2-repeatability"
        RunId = "v0136-b2-repeatability-r1"
    }
}

function Fail-Closed {
    param([Parameter(Mandatory = $true)][string]$Message)
    throw ("Focused recovery successor supervisor: " + $Message)
}

function Get-MarkerState {
    param([Parameter(Mandatory = $true)][string]$JsonPath)

    $markerPath = $JsonPath + ".complete"
    # Test the paths themselves before testing their file types.  A directory
    # at either location must never masquerade as an absent publication.
    $jsonExists = Test-Path -LiteralPath $JsonPath
    $markerExists = Test-Path -LiteralPath $markerPath
    if (-not $jsonExists -and -not $markerExists) {
        return "Absent"
    }
    if ($jsonExists -and -not (Test-Path -LiteralPath $JsonPath -PathType Leaf)) {
        return "InvalidJsonPath"
    }
    if ($markerExists -and -not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
        return "InvalidMarkerPath"
    }
    if ($jsonExists -and -not $markerExists) {
        return "JsonOnly"
    }
    if (-not $jsonExists -and $markerExists) {
        return "MarkerOnly"
    }
    if ((Get-Item -LiteralPath $markerPath).Length -ne 0) {
        return "NonemptyMarker"
    }
    return "Complete"
}

function Assert-PublicationState {
    param(
        [Parameter(Mandatory = $true)][string]$JsonPath,
        [Parameter(Mandatory = $true)][string]$Label,
        [switch]$AllowJsonOnly
    )

    $state = Get-MarkerState $JsonPath
    switch ($state) {
        "InvalidJsonPath" { Fail-Closed "$Label JSON artifact path is not a regular file" }
        "InvalidMarkerPath" { Fail-Closed "$Label completion marker path is not a regular file" }
        "MarkerOnly" { Fail-Closed "$Label has a marker without its JSON artifact" }
        "NonemptyMarker" { Fail-Closed "$Label completion marker is nonempty" }
        "JsonOnly" {
            if (-not $AllowJsonOnly) {
                Fail-Closed "$Label is JSON-only and must be recovered by its exact owning command"
            }
        }
    }
    return $state
}

function Invoke-NativeCaptured {
    param(
        [Parameter(Mandatory = $true)][string]$Module,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    # Windows PowerShell 5.1 can turn expected stderr from a rejected native
    # invocation into a NativeCommandError under Stop.  Capture it, restore
    # the caller preference, and make marker validation plus exit code the
    # sole authority.  Never relay the raw core stream to the console.
    $priorErrorActionPreference = $ErrorActionPreference
    Push-Location -LiteralPath $script:ProjectRoot
    try {
        $ErrorActionPreference = "Continue"
        $discardedOutput = @(& $script:PythonExecutable -m $Module @Arguments 2>&1)
        $exitCode = $global:LASTEXITCODE
    } finally {
        $ErrorActionPreference = $priorErrorActionPreference
        Pop-Location
    }
    return [PSCustomObject]@{
        ExitCode = $exitCode
        Output = $discardedOutput
    }
}

function Invoke-SuccessorCore {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    return Invoke-NativeCaptured $script:CoreModule $Arguments
}

function Invoke-NativePreflight {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    return Invoke-NativeCaptured "bench.next_study_live" $Arguments
}

function Assert-ZeroExit {
    param(
        [Parameter(Mandatory = $true)]$Result,
        [Parameter(Mandatory = $true)][string]$Label
    )
    if ($null -eq $Result.ExitCode -or $Result.ExitCode -ne 0) {
        Fail-Closed "$Label failed validation"
    }
}

function Validate-Authorization {
    $state = Assert-PublicationState $script:AuthorizationPath "authorization"
    if ($state -ne "Complete") {
        Fail-Closed "fixed canonical authorization is missing"
    }
    Assert-ZeroExit (Invoke-SuccessorCore @("validate", "--kind", "authorization")) "authorization"
    try {
        $authorization = Get-Content -LiteralPath $script:AuthorizationPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Fail-Closed "authorization cannot be decoded after core validation"
    }
    foreach ($field in @("authorization_sha256", "run_specs", "analysis_embargo")) {
        if ($null -eq $authorization.$field) {
            Fail-Closed "authorization lacks required $field"
        }
    }
    if ($authorization.analysis_embargo -ne "both_blocks_terminal") {
        Fail-Closed "authorization does not bind the two-block efficacy embargo"
    }
    if ([string]$authorization.run_specs.B1b_recovery.run_id -ne $script:BlockSpecs.B1b_recovery.RunId -or
        [string]$authorization.run_specs.B2_repeatability.run_id -ne $script:BlockSpecs.B2_repeatability.RunId) {
        Fail-Closed "authorization run identities differ from the fixed successor contract"
    }
    return $authorization
}

function Get-BlockArtifactPath {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("B1b_recovery", "B2_repeatability")][string]$Block,
        [Parameter(Mandatory = $true)][ValidateSet("seals", "terminations")][string]$Kind,
        [Parameter(Mandatory = $true)][string]$AuthorizationSha256
    )

    $runsRoot = $script:BlockSpecs[$Block].RunsRoot
    return Join-Path $runsRoot ("focused-recovery-" + $Kind + [IO.Path]::DirectorySeparatorChar + $AuthorizationSha256 + [IO.Path]::DirectorySeparatorChar + $Block + ".json")
}

function Get-BlockDisposition {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("B1b_recovery", "B2_repeatability")][string]$Block,
        [Parameter(Mandatory = $true)][string]$AuthorizationSha256
    )

    $sealPath = Get-BlockArtifactPath $Block "seals" $AuthorizationSha256
    $terminationPath = Get-BlockArtifactPath $Block "terminations" $AuthorizationSha256
    $sealState = Assert-PublicationState $sealPath ("$Block seal") -AllowJsonOnly
    $terminationState = Assert-PublicationState $terminationPath ("$Block termination") -AllowJsonOnly
    if ($sealState -eq "Complete" -and $terminationState -eq "Complete") {
        Fail-Closed "$Block has conflicting seal and termination artifacts"
    }
    # The fixed core owns terminal publication.  It can recover a JSON-only
    # terminal only by rederiving and validating it under the machine-wide
    # lease.  This wrapper never treats it as terminal evidence itself.
    if ($sealState -eq "JsonOnly" -or $terminationState -eq "JsonOnly") {
        return "json_only"
    }
    if ($sealState -eq "Complete") {
        return "sealed"
    }
    if ($terminationState -eq "Complete") {
        return "terminated"
    }
    return "absent"
}

function Validate-BlockTerminal {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("B1b_recovery", "B2_repeatability")][string]$Block,
        [Parameter(Mandatory = $true)][string]$AuthorizationSha256
    )

    # The core exposes a dedicated, score-free validation branch.  It
    # revalidates a terminal artifact from immutable evidence without entering
    # execution, including when the block terminated incomplete.
    $result = Invoke-SuccessorCore @(
        "validate", "--kind", "block", "--block", $Block
    )
    Assert-ZeroExit $result "$Block terminal"
    $state = Get-BlockDisposition $Block $AuthorizationSha256
    if ($state -eq "absent" -or $state -eq "json_only") {
        Fail-Closed "$Block validation returned without a terminal marker"
    }
    return $state
}

function Invoke-BlockOrResume {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("B1b_recovery", "B2_repeatability")][string]$Block,
        [Parameter(Mandatory = $true)][string]$AuthorizationSha256
    )

    $before = Get-BlockDisposition $Block $AuthorizationSha256

    # This is a fixed, audited stale-lease recovery command.  It runs before
    # every block action, including a safe resume and a terminal validation.
    Assert-ZeroExit (Invoke-SuccessorCore @("recover-stale-lease")) "$Block stale lease recovery"

    if ($before -eq "absent" -or $before -eq "json_only") {
        Write-Host ("[focused-recovery-successor] {0}: executing or safely resuming score-masked evidence" -f $Block)
        $result = Invoke-SuccessorCore @(
            "run-block", "--block", $Block,
            "--supervisor-path", $script:SupervisorPath
        )
        # A final marker takes precedence over Windows wrapper exit-code
        # quirks.  An absent terminal marker always fails closed.
        $after = Get-BlockDisposition $Block $AuthorizationSha256
        if ($after -eq "absent" -or $after -eq "json_only") {
            if ($null -eq $result.ExitCode -or $result.ExitCode -ne 0) {
                Fail-Closed "$Block stopped without a valid terminal artifact"
            }
            Fail-Closed "$Block returned without a marker-last terminal artifact"
        }
    }
    return Validate-BlockTerminal $Block $AuthorizationSha256
}

function Get-AnalysisPath {
    param([Parameter(Mandatory = $true)][string]$AuthorizationSha256)
    return Join-Path $script:SuccessorRoot ("analysis" + [IO.Path]::DirectorySeparatorChar + $AuthorizationSha256 + [IO.Path]::DirectorySeparatorChar + "analysis.json")
}

function Get-ReportPath {
    param([Parameter(Mandatory = $true)][string]$AuthorizationSha256)
    return Join-Path $script:SuccessorRoot ("reports" + [IO.Path]::DirectorySeparatorChar + $AuthorizationSha256 + [IO.Path]::DirectorySeparatorChar + "report.json")
}

function Invoke-WriterThenValidate {
    param(
        [Parameter(Mandatory = $true)][string[]]$WriterArguments,
        [Parameter(Mandatory = $true)][string]$ArtifactPath,
        [Parameter(Mandatory = $true)][string[]]$ValidationArguments,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $state = Assert-PublicationState $ArtifactPath $Label -AllowJsonOnly
    if ($state -eq "Absent" -or $state -eq "JsonOnly") {
        $result = Invoke-SuccessorCore $WriterArguments
        $state = Assert-PublicationState $ArtifactPath $Label -AllowJsonOnly
        if ($state -eq "Absent" -or $state -eq "JsonOnly") {
            if ($null -eq $result.ExitCode -or $result.ExitCode -ne 0) {
                Fail-Closed "$Label writer failed before publication"
            }
            Fail-Closed "$Label writer returned without marker-last publication"
        }
    }
    if ($state -ne "Complete") {
        Fail-Closed "$Label is not a complete marker-last publication"
    }
    Assert-ZeroExit (Invoke-SuccessorCore $ValidationArguments) $Label
}

function Get-ReleaseArtifactPaths {
    param([Parameter(Mandatory = $true)][string]$AuthorizationSha256)

    $releaseRoot = Join-Path $script:SuccessorRoot ("release" + [IO.Path]::DirectorySeparatorChar + $AuthorizationSha256)
    return [PSCustomObject]@{
        Archive = Join-Path $releaseRoot "archive.json"
        Manifest = Join-Path $releaseRoot "manifest.json"
        Verification = Join-Path $releaseRoot "independent-verification.json"
    }
}

function Invoke-ReleaseThenIndependentlyVerify {
    param([Parameter(Mandatory = $true)][string]$AuthorizationSha256)

    $paths = Get-ReleaseArtifactPaths $AuthorizationSha256
    $archiveState = Assert-PublicationState $paths.Archive "release archive" -AllowJsonOnly
    $manifestState = Assert-PublicationState $paths.Manifest "release manifest" -AllowJsonOnly

    # `release` owns the archive and manifest together.  It safely continues
    # an exact JSON-only publication and detects any different bytes itself.
    # It is harmless to invoke when both marker-last artifacts already exist:
    # the fixed core revalidates their exact bindings before returning.
    $releaseResult = Invoke-SuccessorCore @("release")
    $archiveAfter = Assert-PublicationState $paths.Archive "release archive" -AllowJsonOnly
    $manifestAfter = Assert-PublicationState $paths.Manifest "release manifest" -AllowJsonOnly
    if ($archiveAfter -ne "Complete" -or $manifestAfter -ne "Complete") {
        if ($null -eq $releaseResult.ExitCode -or $releaseResult.ExitCode -ne 0) {
            Fail-Closed "release archive or manifest failed before marker-last publication"
        }
        Fail-Closed "release returned without complete archive and manifest publications"
    }
    Assert-ZeroExit (Invoke-SuccessorCore @("validate", "--kind", "release")) "release archive and manifest"

    # This command deliberately uses a separate module.  It rederives the
    # release binding independently and is the sole owner of its marker-last
    # verification artifact.
    $verificationState = Assert-PublicationState $paths.Verification "independent release verification" -AllowJsonOnly
    $verificationResult = Invoke-NativeCaptured $script:ReleaseVerifierModule @(
        "verify", "--output", $paths.Verification
    )
    $verificationAfter = Assert-PublicationState $paths.Verification "independent release verification" -AllowJsonOnly
    if ($verificationAfter -ne "Complete") {
        if ($null -eq $verificationResult.ExitCode -or $verificationResult.ExitCode -ne 0) {
            Fail-Closed "independent release verification failed before marker-last publication"
        }
        Fail-Closed "independent release verification returned without marker-last publication"
    }
    # Unlike a block, this independent verifier has no second read-only
    # verifier command after it.  A pre-existing marker therefore cannot mask
    # a fresh rederivation failure caused by drift in its bound inputs.
    Assert-ZeroExit $verificationResult "independent release verification"
}

function Publish-FinalArtifacts {
    param([Parameter(Mandatory = $true)][string]$AuthorizationSha256)

    $analysisPath = Get-AnalysisPath $AuthorizationSha256
    Invoke-WriterThenValidate @("analyze", "--output", $analysisPath) $analysisPath @("validate", "--kind", "analysis") "analysis"

    $reportPath = Get-ReportPath $AuthorizationSha256
    Invoke-WriterThenValidate @("report", "--output", $reportPath) $reportPath @("validate", "--kind", "report") "report"

    Invoke-ReleaseThenIndependentlyVerify $AuthorizationSha256

    # Deliberately no analysis fields or report content are printed here.
    Write-Host "[focused-recovery-successor] both terminal lanes, canonical artifacts, and independent release verification validated"
}

function Ensure-Preflight {
    $state = Assert-PublicationState $script:PreflightPath "fixed native preflight"
    if ($state -eq "Absent") {
        $result = Invoke-NativePreflight @("native-preflight", "--output", $script:PreflightPath)
        $state = Assert-PublicationState $script:PreflightPath "fixed native preflight"
        if ($state -eq "Absent") {
            if ($null -eq $result.ExitCode -or $result.ExitCode -ne 0) {
                Fail-Closed "native preflight failed before publication"
            }
            Fail-Closed "native preflight returned without marker-last publication"
        }
    }
}

function Start-Authorize {
    if ([string]::IsNullOrWhiteSpace($IssuedAt) -or [string]::IsNullOrWhiteSpace($Issuer)) {
        Fail-Closed "Authorize requires issued-at and issuer metadata only"
    }
    $authorizationState = Assert-PublicationState $script:AuthorizationPath "authorization" -AllowJsonOnly
    if ($authorizationState -eq "Complete") {
        $unused = Validate-Authorization
        Write-Host "[focused-recovery-successor] fixed canonical authorization already validates; no block was started"
        return
    }
    Ensure-Preflight
    $result = Invoke-SuccessorCore @(
        "authorize", "--preflight", $script:PreflightPath,
        "--output", $script:AuthorizationPath,
        "--issued-at", $IssuedAt,
        "--issuer", $Issuer,
        "--supervisor-path", $script:SupervisorPath
    )
    $authorizationState = Assert-PublicationState $script:AuthorizationPath "authorization" -AllowJsonOnly
    if ($authorizationState -eq "Complete") {
        $unused = Validate-Authorization
        Write-Host "[focused-recovery-successor] authorization published and validated; no block was started"
        return
    }
    if ($null -eq $result.ExitCode -or $result.ExitCode -ne 0) {
        Fail-Closed "authorization failed before marker-last publication"
    }
    Fail-Closed "authorization returned without marker-last publication"
}

function Start-Run {
    if (-not [string]::IsNullOrWhiteSpace($IssuedAt) -or -not [string]::IsNullOrWhiteSpace($Issuer)) {
        Fail-Closed "Run accepts no operational or authorization inputs"
    }
    $authorization = Validate-Authorization
    $authorizationSha256 = [string]$authorization.authorization_sha256

    # B2 is mandatory after any B1b terminal disposition.  The core enforces
    # that prerequisite itself; this wrapper never branches on results.
    $b1b = Invoke-BlockOrResume "B1b_recovery" $authorizationSha256
    Write-Host ("[focused-recovery-successor] B1b_recovery terminal: {0}" -f $b1b)
    $b2 = Invoke-BlockOrResume "B2_repeatability" $authorizationSha256
    Write-Host ("[focused-recovery-successor] B2_repeatability terminal: {0}" -f $b2)

    Publish-FinalArtifacts $authorizationSha256
}

if ($Mode -eq "Authorize") {
    Start-Authorize
    return
}

Start-Run
