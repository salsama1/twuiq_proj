$ErrorActionPreference = "Stop"

Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Pytest = Join-Path $RepoRoot ".venv\Scripts\pytest.exe"

if (-not (Test-Path $Py)) {
  throw "Missing venv python at $Py. Create it with: py -3.12 -m venv .venv"
}

Write-Host "Running smoke test..."
& $Py (Join-Path $RepoRoot "scripts\smoke_test.py")

Write-Host ""
Write-Host "Running pytest integration tests..."
if (Test-Path $Pytest) {
  & $Pytest
} else {
  & $Py -m pytest
}

Write-Host ""
Write-Host "DONE"

