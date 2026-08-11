param(
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8000,

    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 5173,

    [switch]$EnableAgentFeatures,
    [switch]$NoBrowser,
    [switch]$SkipInstall,
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$BackendPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$BackendEnv = Join-Path $BackendDir ".env"
$BackendEnvExample = Join-Path $BackendDir ".env.example"
$FrontendModules = Join-Path $FrontendDir "node_modules"
$PowerShellExe = Join-Path $PSHOME "powershell.exe"
$AgentFlag = if ($EnableAgentFeatures) { "true" } else { "false" }

function Assert-LastCommandSucceeded {
    param([string]$Description)

    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

function Test-PortAvailable {
    param([int]$Port)

    $Listener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Loopback,
        $Port
    )
    try {
        $Listener.Start()
        return $true
    }
    catch [System.Net.Sockets.SocketException] {
        return $false
    }
    finally {
        $Listener.Stop()
    }
}

function Assert-PortAvailable {
    param(
        [string]$Name,
        [int]$Port
    )

    if (-not (Test-PortAvailable -Port $Port)) {
        throw "$Name port $Port is already in use. Stop the existing process or choose another port."
    }
}

function Initialize-Backend {
    if (Test-Path -LiteralPath $BackendPython) {
        return
    }
    if ($SkipInstall) {
        throw "Backend environment is missing: $BackendPython"
    }
    if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
        throw "Backend environment is missing and uv is not installed. Install uv, then run this script again."
    }

    Write-Host "Creating backend environment and installing dependencies..." -ForegroundColor Yellow
    Push-Location $BackendDir
    try {
        & uv sync
        Assert-LastCommandSucceeded -Description "Backend dependency installation"
    }
    finally {
        Pop-Location
    }
    if (-not (Test-Path -LiteralPath $BackendPython)) {
        throw "uv completed but backend Python was not created: $BackendPython"
    }
}

function Initialize-Frontend {
    if (-not (Get-Command "node" -ErrorAction SilentlyContinue)) {
        throw "Node.js is not installed or is unavailable on PATH."
    }
    if (-not (Get-Command "npm" -ErrorAction SilentlyContinue)) {
        throw "npm is not installed or is unavailable on PATH."
    }
    if ((Test-Path -LiteralPath $FrontendModules) -or $SkipInstall) {
        if (-not (Test-Path -LiteralPath $FrontendModules)) {
            throw "Frontend dependencies are missing: $FrontendModules"
        }
        return
    }

    Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
    Push-Location $FrontendDir
    try {
        & npm install
        Assert-LastCommandSucceeded -Description "Frontend dependency installation"
    }
    finally {
        Pop-Location
    }
}

function Initialize-EnvironmentFile {
    if (-not (Test-Path -LiteralPath $BackendEnv)) {
        if (-not (Test-Path -LiteralPath $BackendEnvExample)) {
            throw "Backend environment template not found: $BackendEnvExample"
        }
        Copy-Item -LiteralPath $BackendEnvExample -Destination $BackendEnv
        Write-Warning "Created backend/.env from .env.example. Add LLM_API_KEY before generating annotations."
    }

    $ConfiguredKey = Select-String `
        -LiteralPath $BackendEnv `
        -Pattern '^\s*LLM_API_KEY\s*=\s*\S+' `
        -Quiet
    if (-not $ConfiguredKey) {
        Write-Warning "LLM_API_KEY is empty. Original reading and local data work, but annotation generation will fail until the key is configured."
    }
}

function Start-DevProcess {
    param(
        [string]$Name,
        [string]$WorkingDirectory,
        [string]$Command
    )

    $EncodedCommand = [Convert]::ToBase64String(
        [Text.Encoding]::Unicode.GetBytes($Command)
    )
    Write-Host "Starting $Name..." -ForegroundColor Cyan
    return Start-Process `
        -FilePath $PowerShellExe `
        -ArgumentList @(
            "-NoLogo",
            "-NoProfile",
            "-NoExit",
            "-ExecutionPolicy", "Bypass",
            "-EncodedCommand", $EncodedCommand
        ) `
        -WorkingDirectory $WorkingDirectory `
        -PassThru
}

function Wait-ForServers {
    param(
        [System.Diagnostics.Process]$BackendProcess,
        [System.Diagnostics.Process]$FrontendProcess,
        [int]$TimeoutSeconds = 30
    )

    $Deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $BackendReady = $false
    $FrontendReady = $false
    while ([DateTime]::UtcNow -lt $Deadline) {
        if ($BackendProcess.HasExited) {
            throw "Backend process exited before opening port $BackendPort. Check its PowerShell window for details."
        }
        if ($FrontendProcess.HasExited) {
            throw "Frontend process exited before opening port $FrontendPort. Check its PowerShell window for details."
        }
        $BackendReady = -not (Test-PortAvailable -Port $BackendPort)
        $FrontendReady = -not (Test-PortAvailable -Port $FrontendPort)
        if ($BackendReady -and $FrontendReady) {
            return $true
        }
        Start-Sleep -Milliseconds 250
    }
    return $false
}

if (-not (Test-Path -LiteralPath $BackendDir -PathType Container)) {
    throw "Backend directory not found: $BackendDir"
}
if (-not (Test-Path -LiteralPath $FrontendDir -PathType Container)) {
    throw "Frontend directory not found: $FrontendDir"
}
if ($BackendPort -eq $FrontendPort) {
    throw "BackendPort and FrontendPort must be different."
}
if (-not (Test-Path -LiteralPath $PowerShellExe -PathType Leaf)) {
    throw "Windows PowerShell executable not found: $PowerShellExe"
}

Initialize-Backend
Initialize-Frontend
Initialize-EnvironmentFile
Assert-PortAvailable -Name "Backend" -Port $BackendPort
Assert-PortAvailable -Name "Frontend" -Port $FrontendPort

Write-Host ""
Write-Host "Preflight checks passed." -ForegroundColor Green
Write-Host "  Mode:     $(if ($EnableAgentFeatures) { 'experimental Agent features' } else { 'stable reading' })"
Write-Host "  Backend:  http://127.0.0.1:$BackendPort"
Write-Host "  Frontend: http://127.0.0.1:$FrontendPort"

if ($ValidateOnly) {
    Write-Host "Validation only; no processes were started."
    exit 0
}

$BackendCommand = "`$env:AGENT_FEATURES_ENABLED='$AgentFlag'; `$env:PYTHONUTF8='1'; & '.\.venv\Scripts\python.exe' -m uvicorn superhp_agent.main:app --reload --host 127.0.0.1 --port $BackendPort"
$FrontendCommand = "`$env:VITE_AGENT_FEATURES_ENABLED='$AgentFlag'; npm run dev -- --host 127.0.0.1 --port $FrontendPort"

$BackendProcess = Start-DevProcess `
    -Name "backend http://127.0.0.1:$BackendPort" `
    -WorkingDirectory $BackendDir `
    -Command $BackendCommand
$FrontendProcess = Start-DevProcess `
    -Name "frontend http://127.0.0.1:$FrontendPort" `
    -WorkingDirectory $FrontendDir `
    -Command $FrontendCommand

Write-Host ""
Write-Host "Waiting for both development servers..."
$Ready = Wait-ForServers `
    -BackendProcess $BackendProcess `
    -FrontendProcess $FrontendProcess

if ($Ready) {
    Write-Host "SuperHP Reading Assistant is ready." -ForegroundColor Green
    if (-not $NoBrowser) {
        Start-Process "http://127.0.0.1:$FrontendPort"
    }
}
else {
    Write-Warning "Servers are still starting. Check the two PowerShell windows, then open http://127.0.0.1:$FrontendPort manually."
}

Write-Host "Two PowerShell windows contain the live logs. Close them to stop each server."
