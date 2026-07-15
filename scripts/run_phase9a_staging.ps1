$ErrorActionPreference = "Stop"
$env:W2E_STAGING_LAUNCHER = "1"
python "$PSScriptRoot/run_phase9a_staging.py"
