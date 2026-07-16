param([Parameter(Mandatory=$true)][string]$Manifest, [Parameter(Mandatory=$true)][string]$Output)

& python "$PSScriptRoot/run_phase9c_staging.py" --manifest $Manifest --output $Output --initialize
exit $LASTEXITCODE
