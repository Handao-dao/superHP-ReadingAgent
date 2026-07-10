param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$BackendPython = Join-Path $BackendDir ".venv\Scripts\python.exe"

function Start-DevProcess {
    param(
        [string]$Name,
        [string]$WorkingDirectory,
        [string]$Command
    )

    Write-Host "Starting $Name..." -ForegroundColor Cyan
    Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $Command) `
        -WorkingDirectory $WorkingDirectory `
        -PassThru
}

if (-not (Test-Path $BackendDir)) {
    throw "Backend directory not found: $BackendDir"
}

if (-not (Test-Path $FrontendDir)) {
    throw "Frontend directory not found: $FrontendDir"
}

if (Test-Path $BackendPython) {
    $BackendCommand = ".\.venv\Scripts\python.exe -m uvicorn superhp_agent.main:app --reload --host 127.0.0.1 --port $BackendPort"
} else {
    $BackendCommand = "uv run uvicorn superhp_agent.main:app --reload --host 127.0.0.1 --port $BackendPort"
}

$FrontendCommand = "npm run dev -- --host 127.0.0.1 --port $FrontendPort"

$BackendProcess = Start-DevProcess -Name "backend http://127.0.0.1:$BackendPort" -WorkingDirectory $BackendDir -Command $BackendCommand
$FrontendProcess = Start-DevProcess -Name "frontend http://127.0.0.1:$FrontendPort" -WorkingDirectory $FrontendDir -Command $FrontendCommand

Write-Host ""
Write-Host "SuperHP Agent is starting:" -ForegroundColor Green
Write-Host "  Backend:  http://127.0.0.1:$BackendPort"
Write-Host "  Frontend: http://127.0.0.1:$FrontendPort"
Write-Host ""
Write-Host "Two PowerShell windows were opened for logs. Close them to stop each server."
Write-Host "This launcher can now be closed."
