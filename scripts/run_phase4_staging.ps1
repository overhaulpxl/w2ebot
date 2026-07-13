$ErrorActionPreference = "Stop"
$env:W2E_STAGING_LAUNCHER = "1"
python "$PSScriptRoot\run_phase4_staging.py"
