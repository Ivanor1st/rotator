param(
    [switch]$StatusOnly,
    [switch]$Stop,
    [switch]$Restart,
    [switch]$Dashboard,
    [switch]$Claude,
    [string]$WorkDir = ""
)

$ErrorActionPreference = "Stop"

# Locate project root
$RotatorRoot = if ($env:ROTATOR_HOME) { $env:ROTATOR_HOME } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not (Test-Path (Join-Path $RotatorRoot "main.py"))) {
    Write-Host "[ERREUR] main.py introuvable dans $RotatorRoot" -ForegroundColor Red
    Write-Host "  Definissez ROTATOR_HOME ou lancez depuis le dossier du projet." -ForegroundColor Yellow
    exit 1
}

# Read port from config
function Get-RotatorPort {
    $cfg = Join-Path $RotatorRoot "config.yaml"
    if (Test-Path $cfg) {
        $line = Get-Content $cfg | Where-Object { $_ -match '^\s*port:' } | Select-Object -First 1
        if ($line) { return ($line -replace '[^0-9]', '') }
    }
    return "47822"
}

$port = Get-RotatorPort
$baseUrl = "http://localhost:$port"

# Helpers
function Test-ProxyAlive {
    try {
        $null = Invoke-RestMethod -Uri "$baseUrl/api/status" -Method Get -TimeoutSec 3 -ErrorAction Stop
        return $true
    } catch { return $false }
}

function Get-ProxyPid {
    # Try Get-NetTCPConnection first
    try {
        $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if ($conns) { return ($conns | Select-Object -First 1).OwningProcess }
    } catch {}
    # Fallback: parse netstat
    try {
        $lines = netstat -ano 2>$null | Where-Object { $_ -match ":$port\s" -and $_ -match "LISTENING" }
        if ($lines) {
            $parts = ($lines | Select-Object -First 1).Trim() -split '\s+'
            $pidVal = $parts[-1]
            if ($pidVal -match '^\d+$') { return [int]$pidVal }
        }
    } catch {}
    return $null
}

function Start-Proxy {
    $venvPython = Join-Path $RotatorRoot ".venv\Scripts\python.exe"
    $pythonExe = if (Test-Path $venvPython) { $venvPython } else { "python" }

    $logOut = Join-Path $RotatorRoot "rotator.stdout.log"
    $logErr = Join-Path $RotatorRoot "rotator.stderr.log"

    Write-Host "Demarrage du proxy..." -ForegroundColor Yellow
    Write-Host "  Python : $pythonExe" -ForegroundColor DarkGray
    Write-Host "  Logs   : $logOut / $logErr" -ForegroundColor DarkGray

    $mainPy = Join-Path $RotatorRoot "main.py"
    Start-Process -FilePath $pythonExe -ArgumentList $mainPy -WorkingDirectory $RotatorRoot -RedirectStandardOutput $logOut -RedirectStandardError $logErr -WindowStyle Hidden

    # Poll for readiness (HTTP-level)
    $t0 = Get-Date
    $timeout = 45
    while (((Get-Date) - $t0).TotalSeconds -lt $timeout) {
        if (Test-ProxyAlive) {
            Write-Host "[OK] Proxy operationnel sur $baseUrl" -ForegroundColor Green
            return $true
        }
        Start-Sleep -Seconds 1
    }

    Write-Host "[ERREUR] Proxy n'a pas repondu dans les ${timeout}s." -ForegroundColor Red
    if (Test-Path $logErr) {
        $tail = Get-Content $logErr -Tail 12
        if ($tail) {
            Write-Host "--- stderr ---" -ForegroundColor Red
            $tail | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
        }
    }
    return $false
}

function Show-Status {
    $alive = Test-ProxyAlive
    $ppid = Get-ProxyPid
    Write-Host ""
    Write-Host "=== API Rotator - Statut ===" -ForegroundColor Cyan
    if ($alive) {
        Write-Host "  Etat      : EN LIGNE" -ForegroundColor Green
        Write-Host "  URL       : $baseUrl" -ForegroundColor White
        Write-Host "  Dashboard : $baseUrl/dashboard" -ForegroundColor White
        if ($ppid) { Write-Host "  PID       : $ppid" -ForegroundColor DarkGray }
        try {
            $st = Invoke-RestMethod -Uri "$baseUrl/api/status" -Method Get -TimeoutSec 3
            $provNames = ($st.providers | Get-Member -MemberType NoteProperty | ForEach-Object { $_.Name })
            $provStr = $provNames -join ", "
            Write-Host "  Providers : $provStr" -ForegroundColor White
        } catch {}
    } else {
        Write-Host "  Etat      : HORS LIGNE" -ForegroundColor Red
        if ($ppid) { Write-Host "  PID zombie: $ppid (port occupe mais API muette)" -ForegroundColor Yellow }
    }
    Write-Host ""
}

# === Actions ===

# -- Stop --
if ($Stop) {
    $ppid = Get-ProxyPid
    if ($ppid) {
        Write-Host "Arret du proxy (PID $ppid)..." -ForegroundColor Yellow
        try {
            Stop-Process -Id $ppid -Force -ErrorAction Stop
            Write-Host "[OK] Proxy arrete." -ForegroundColor Green
        } catch {
            Write-Host "[ERREUR] Impossible d arreter le processus." -ForegroundColor Red
        }
    } else {
        Write-Host "Aucun proxy detecte sur le port $port." -ForegroundColor DarkGray
    }
    exit 0
}

# -- Restart --
if ($Restart) {
    $ppid = Get-ProxyPid
    if ($ppid) {
        Write-Host "Arret du proxy (PID $ppid)..." -ForegroundColor Yellow
        try {
            Stop-Process -Id $ppid -Force -ErrorAction Stop
            Start-Sleep -Seconds 1
            Write-Host "[OK] Proxy arrete." -ForegroundColor Green
        } catch {
            Write-Host "[ERREUR] Impossible d arreter le processus." -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "Aucun proxy detecte, demarrage direct..." -ForegroundColor DarkGray
    }
    $started = Start-Proxy
    if ($started) {
        Write-Host "[OK] Proxy redemarre." -ForegroundColor Green
        Show-Status
    } else {
        Write-Host "[ERREUR] Echec du redemarrage." -ForegroundColor Red
        exit 1
    }
    exit 0
}

# -- Status only --
if ($StatusOnly) {
    Show-Status
    exit 0
}

# -- Ensure proxy is running --
$alive = Test-ProxyAlive
if (-not $alive) {
    $ppid = Get-ProxyPid
    if ($ppid) {
        Write-Host "Port $port occupe par PID $ppid mais l API ne repond pas." -ForegroundColor Yellow
        Write-Host "Tentez : .\rotator-quick.ps1 -Stop puis relancez." -ForegroundColor Yellow
        exit 1
    }
    $started = Start-Proxy
    if (-not $started) { exit 1 }
} else {
    Write-Host "[OK] Proxy deja en ligne sur $baseUrl" -ForegroundColor Green
}

# -- Dashboard --
if ($Dashboard -or (-not $Claude)) {
    Write-Host "Ouverture du dashboard..." -ForegroundColor Cyan
    Start-Process "$baseUrl/dashboard"
}

# -- Claude --
if ($Claude) {
    Write-Host ""
    Write-Host "Preparation de Claude Code..." -ForegroundColor Cyan

    $token = "rotator"
    $projName = "rotator"
    try {
        $body = @{} | ConvertTo-Json -Compress
        $res = Invoke-RestMethod -Uri "$baseUrl/api/projects/claude-onboarding" -Method Post -ContentType "application/json" -Body $body
        if ($res -and $res.project -and $res.project.token) {
            $token = [string]$res.project.token
            $projName = [string]$res.project.name
            $short = $token.Substring(0, [Math]::Min(16, $token.Length))
            Write-Host "  Token cree : $projName ($short)" -ForegroundColor Green
        }
    } catch {
        Write-Host "  Token dedie impossible, fallback sur rotator." -ForegroundColor Yellow
    }

    $targetDir = $RotatorRoot
    if ($WorkDir -and (Test-Path $WorkDir -PathType Container)) { $targetDir = $WorkDir }
    $safeDir = $targetDir -replace "'", "''"
    $safeToken = $token -replace "'", "''"
    $shortToken = $token.Substring(0, [Math]::Min(16, $token.Length))

    $cmdParts = @(
        "Set-Location -LiteralPath '$safeDir'"
        "`$env:ANTHROPIC_BASE_URL='$baseUrl'"
        "`$env:ANTHROPIC_AUTH_TOKEN='$safeToken'"
        "Write-Host '  BASE_URL  = $baseUrl' -ForegroundColor Cyan"
        "Write-Host '  TOKEN     = $shortToken' -ForegroundColor Cyan"
        "Write-Host '  Dossier   = $safeDir' -ForegroundColor Cyan"
        "Write-Host ''"
        "claude --model coding"
    )
    $cmd = $cmdParts -join "; "
    Start-Process -FilePath "powershell" -ArgumentList @("-NoExit", "-Command", $cmd)
    Write-Host "  Claude lance dans un nouveau terminal (dossier: $targetDir)" -ForegroundColor Green
}

Show-Status
