# QuickSight localhost — run each command separately (PowerShell)
Set-Location $PSScriptRoot

aws sso login --profile onedatasoftware-customer-poc
if ($LASTEXITCODE -ne 0) {
    Write-Host "SSO login failed. Use the full profile name above (one line only)."
    exit $LASTEXITCODE
}

python server.py
