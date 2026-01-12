$ErrorActionPreference = "Stop"

Write-Host "Running smoke test..."
python "scripts/smoke_test.py"

Write-Host ""
Write-Host "Running pytest integration tests..."
pytest

Write-Host ""
Write-Host "DONE"

