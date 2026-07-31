param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
$env:W2E_STAGING_LAUNCHER = "1"
python (Join-Path $PSScriptRoot "run_phase3_staging.py") @Arguments
exit $LASTEXITCODE
