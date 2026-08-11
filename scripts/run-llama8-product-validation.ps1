[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Preflight", "Authorize", "Run", "Validate")]
    [string]$Mode,

    [string]$SharvinCheckout = "C:\bft-final-agent-8b-audit-7efc9b9"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$script:ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Invoke-FocusedCore {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $priorLocation = Get-Location
    $priorPreference = $ErrorActionPreference
    try {
        Set-Location -LiteralPath $script:ProjectRoot
        # Windows PowerShell 5.1 promotes native stderr to NativeCommandError
        # under Stop. Capture the real native exit code first.
        $ErrorActionPreference = "Continue"
        $output = @(& python -m bench.llama8_product_validation @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $priorPreference
        Set-Location -LiteralPath $priorLocation
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = @($output | ForEach-Object { "$_" })
    }
}

function Assert-ZeroExit {
    param(
        [Parameter(Mandatory = $true)]$Result,
        [Parameter(Mandatory = $true)][string]$Operation
    )
    if ($Result.ExitCode -ne 0) {
        $message = ($Result.Output -join [Environment]::NewLine)
        throw "$Operation failed with exit code $($Result.ExitCode): $message"
    }
}

switch ($Mode) {
    "Preflight" {
        $result = Invoke-FocusedCore -Arguments @("preflight", "--sharvin-checkout", $SharvinCheckout)
        Assert-ZeroExit $result "Llama 8B preflight"
        Write-Host "Llama 8B preflight sealed."
        exit 0
    }
    "Authorize" {
        $result = Invoke-FocusedCore -Arguments @("authorize")
        Assert-ZeroExit $result "Llama 8B authorization"
        Write-Host "Llama 8B authorization and exact schedule sealed."
        exit 0
    }
    "Validate" {
        $result = Invoke-FocusedCore -Arguments @("validate", "--kind", "lifecycle")
        Assert-ZeroExit $result "Llama 8B lifecycle validation"
        Write-Host "Llama 8B lifecycle validation passed."
        exit 0
    }
    "Run" {
        $authorization = Invoke-FocusedCore -Arguments @("validate", "--kind", "authorization")
        Assert-ZeroExit $authorization "Llama 8B authorization validation"

        $run = Invoke-FocusedCore -Arguments @("run")
        if ($run.ExitCode -ne 0) {
            # A process can finish all marker-last attempts and then fail its
            # final environment check. The core recovery seal revalidates the
            # current environment and exact evidence; it cannot seal a partial
            # or invalid run.
            $seal = Invoke-FocusedCore -Arguments @("seal")
            Assert-ZeroExit $seal "Llama 8B run/recovery seal"
        }

        $analysis = Invoke-FocusedCore -Arguments @("analyze")
        Assert-ZeroExit $analysis "Llama 8B analysis"
        $report = Invoke-FocusedCore -Arguments @("report")
        Assert-ZeroExit $report "Llama 8B report"
        $verify = Invoke-FocusedCore -Arguments @("validate", "--kind", "lifecycle")
        Assert-ZeroExit $verify "Llama 8B final verification"
        $priorLocation = Get-Location
        $priorPreference = $ErrorActionPreference
        try {
            Set-Location -LiteralPath $script:ProjectRoot
            $ErrorActionPreference = "Continue"
            $independentOutput = @(& python -m bench.llama8_product_validation_verifier 2>&1)
            $independentExit = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $priorPreference
            Set-Location -LiteralPath $priorLocation
        }
        Assert-ZeroExit ([pscustomobject]@{ ExitCode = $independentExit; Output = $independentOutput }) "Llama 8B separate verification"
        Write-Host "Llama 8B benchmark, analysis, report, and verification completed."
        exit 0
    }
}
