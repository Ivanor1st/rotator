$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptRoot

$global:NonInteractive = $false
if ($args.Count -gt 0 -and $args[0] -eq "go") { $global:NonInteractive = $true }

function Assert-Python {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Write-Host "Python is not installed or not in PATH." -ForegroundColor Red
        exit 1
    }
}

function Assert-Venv {
    if (-not (Test-Path ".venv")) {
        Write-Host "Creating virtual environment..."
        python -m venv .venv
    }
    . .\.venv\Scripts\Activate.ps1
}

function Install-Deps {
    Write-Host "Verification des dependances requises..." -ForegroundColor Cyan
    if (-not (Test-Path "requirements.txt")) {
        Write-Host "requirements.txt introuvable, verification ignoree." -ForegroundColor Yellow
        return
    }

    $requirements = Get-Content "requirements.txt" | Where-Object {
        $_ -and -not $_.Trim().StartsWith("#")
    }
    $missing = @()

    $installedMap = @{}
    $installedJson = (python -m pip list --format=json 2>$null | Out-String).Trim()
    if ($installedJson) {
        try {
            $installed = $installedJson | ConvertFrom-Json
            foreach ($pkg in $installed) {
                $name = [string]$pkg.name
                if ($name) {
                    $installedMap[$name.ToLower()] = $true
                    $installedMap[$name.ToLower().Replace('-', '_')] = $true
                    $installedMap[$name.ToLower().Replace('_', '-')] = $true
                }
            }
        }
        catch {
            Write-Host "Impossible de lire la liste des dependances installees. Installation proposee." -ForegroundColor Yellow
            $missing = $requirements
        }
    }
    else {
        Write-Host "Liste des dependances installees indisponible. Installation proposee." -ForegroundColor Yellow
        $missing = $requirements
    }

    foreach ($entry in $requirements) {
        if ($missing.Count -gt 0 -and $missing -contains $entry) { continue }
        $line = $entry.Trim()
        if (-not $line) { continue }
        if ($line -match '^([A-Za-z0-9_.-]+)') {
            $pkg = $matches[1].ToLower()
            $k1 = $pkg
            $k2 = $pkg.Replace('-', '_')
            $k3 = $pkg.Replace('_', '-')
            if (-not ($installedMap.ContainsKey($k1) -or $installedMap.ContainsKey($k2) -or $installedMap.ContainsKey($k3))) {
                $missing += $line
            }
        }
    }

    if ($missing.Count -eq 0) {
        Write-Host "Toutes les dependances sont deja installees." -ForegroundColor Green
        return
    }

    Write-Host "API Rotator requiert les dependances suivantes :" -ForegroundColor Yellow
    $missing | ForEach-Object { Write-Host " - $_" }
    if ($global:NonInteractive) {
        $answer = "Y"
    }
    else {
        $answer = Read-Host "Voulez-vous installer / mettre a jour ces dependances ? (Y/N)"
    }
    if ($answer -notin @("Y", "y", "O", "o")) {
        Write-Host "Installation annulee par l'utilisateur." -ForegroundColor Yellow
        return
    }

    Write-Host "Installation en cours (pip affichera la progression disponible)..." -ForegroundColor Cyan
    python -m pip install -r requirements.txt --upgrade
}

function Show-Menu {
    param([bool]$ProxyUp = $false)
    $statusIcon = if ($ProxyUp) { "[ON]" } else { "[OFF]" }
    $statusColor = if ($ProxyUp) { "Green" } else { "Red" }
    Write-Host ""
    Write-Host "=== API Rotator Launcher ==="  -ForegroundColor Cyan
    Write-Host "    Proxy: " -NoNewline -ForegroundColor White
    Write-Host $statusIcon -ForegroundColor $statusColor
    Write-Host ""
    Write-Host "  [1] Demarrer le proxy (foreground, logs en direct)" -ForegroundColor White
    Write-Host "  [2] Voir le statut"                                -ForegroundColor White
    Write-Host "  [3] Connecter Claude Code"                         -ForegroundColor White
    Write-Host "  [4] Ouvrir le dashboard"                           -ForegroundColor White
    if ($ProxyUp) {
        Write-Host "  [5] Arreter le proxy"                              -ForegroundColor Yellow
    }
    Write-Host "  [0] Quitter"                                       -ForegroundColor DarkGray
}

function Test-ProxyRunning {
    try {
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/status" -Method Get -TimeoutSec 2 -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Start-ProxyIfNeeded {
    <# Returns $true if proxy is ready, auto-starts if needed. Kills stale processes. #>
    if (Test-ProxyRunning) { return $true }

    # Check if port is already taken by another process
    if (Test-PortInUse -p $port) {
        $owner = Get-PortOwner -p $port
        if ($owner) {
            Write-Host "Port $port occupe par $($owner.ProcessName) (PID $($owner.Id)) - ancien proxy ?" -ForegroundColor Yellow
        } else {
            Write-Host "Port $port occupe par un processus inconnu." -ForegroundColor Yellow
        }
        Write-Host "  -> Arret automatique pour liberer le port..." -ForegroundColor Yellow
        $freed = Stop-ProxyByPort -p $port
        if (-not $freed) {
            Write-Host "Echec de liberation du port. Arretez le processus manuellement." -ForegroundColor Red
            return $false
        }
    }

    Write-Host "Proxy non detecte. Demarrage automatique" -NoNewline -ForegroundColor Yellow
    $logOut = Join-Path $ScriptRoot "rotator.stdout.log"
    $logErr = Join-Path $ScriptRoot "rotator.stderr.log"
    $venvPython = Join-Path $ScriptRoot ".venv\Scripts\python.exe"
    $pyExe = if (Test-Path $venvPython) { $venvPython } else { "python" }
    Start-Process -FilePath $pyExe -ArgumentList "main.py" -WorkingDirectory $ScriptRoot -NoNewWindow -RedirectStandardOutput $logOut -RedirectStandardError $logErr | Out-Null

    # Wait for HTTP-level readiness with progress dots
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Write-Host "." -NoNewline -ForegroundColor DarkGray
        Start-Sleep -Seconds 1
        if (Test-ProxyRunning) { $ready = $true; break }
    }
    Write-Host ""

    if ($ready) {
        Write-Host "[OK] Proxy lance et operationnel." -ForegroundColor Green
        Write-Host "  Proxy    : http://127.0.0.1:$port" -ForegroundColor Cyan
        Write-Host "  Dashboard: http://127.0.0.1:$port/dashboard" -ForegroundColor Cyan
        Write-Host "  API      : http://127.0.0.1:$port/v1" -ForegroundColor Cyan
        Write-Host ""
        return $true
    }

    Write-Host "[ERREUR] Proxy non joignable apres 30s." -ForegroundColor Red
    if (Test-Path $logErr) {
        $errLines = Get-Content $logErr -Tail 10
        if ($errLines) {
            Write-Host "--- stderr ---" -ForegroundColor Red
            $errLines | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
        }
    }
    return $false
}

function Show-ProxyStartupInfo {
    Write-Host "Starting proxy on http://localhost:$port ..." -ForegroundColor Green
    Write-Host "Dashboard: http://localhost:$port/dashboard" -ForegroundColor Cyan
    Write-Host "API Base: http://localhost:$port/v1" -ForegroundColor Cyan
    Write-Host "Quick setup (app/site):" -ForegroundColor Yellow
    Write-Host "  Base URL  = http://localhost:$port/v1"
    Write-Host "  Token     = rotator (Authorization: Bearer rotator)"
    Write-Host "  Endpoint  = /chat/completions"
    Write-Host "  Note      = localhost works only on this same machine"
    Write-Host ""
    Write-Host "-------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "  [OK] Proxy lance - logs en direct ci-dessous" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Pour plus de puissance :" -ForegroundColor Yellow
    Write-Host "     -> Dashboard : http://localhost:$port/dashboard" -ForegroundColor Cyan
    Write-Host "     -> Onglet 'Mes cles API' pour ajouter vos comptes" -ForegroundColor White
    Write-Host "     -> Plus de cles = plus de quotas disponibles" -ForegroundColor White
    Write-Host ""
    Write-Host "  Sans cle : modeles Ollama locaux utilises en fallback" -ForegroundColor DarkGray
    Write-Host "-------------------------------------------------" -ForegroundColor DarkGray
    Write-Host ""
}

function ConvertTo-EscapedSingleQuote {
    param([string]$Value)
    return ($Value -replace "'", "''")
}

function New-ClaudeProject {
    try {
        $body = @{} | ConvertTo-Json -Compress
        $res = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/projects/claude-onboarding" -Method Post -ContentType "application/json" -Body $body
        if ($res -and $res.project -and $res.project.token) {
            return $res.project
        }
    }
    catch {
        Write-Host "[WARN] Impossible de creer un token Claude dedie, fallback sur token 'rotator'." -ForegroundColor Yellow
    }
    return $null
}

function New-ClaudeManualCommand {
    param(
        [string]$WorkDir,
        [string]$Token
    )
    $gitBashPart = ""
    if (Test-Path "C:\Program Files\Git\bin\bash.exe") {
        $gitBashPart = "`$env:CLAUDE_CODE_GIT_BASH_PATH='C:\Program Files\Git\bin\bash.exe'; "
    }
    return "cd `"$WorkDir`"; `$env:ANTHROPIC_BASE_URL='http://localhost:$port'; `$env:ANTHROPIC_AUTH_TOKEN='$Token'; ${gitBashPart}claude --model coding"
}

function Get-Port {
    $cfg = Join-Path $ScriptRoot "config.yaml"
    if (Test-Path $cfg) {
        $line = Get-Content $cfg | Where-Object { $_ -match '^\s*port:' } | Select-Object -First 1
        if ($line) {
            return ($line -replace '[^0-9]', '')
        }
    }
    return "47822"
}

# --- Helpers for robust startup ---
function Test-PortInUse {
    param([int]$p)
    try {
        $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
        if ($c) { return $true }
    } catch {}
    return $false
}

function Get-PortOwner {
    <# Returns the process that is LISTENING on port $p (ignores TimeWait/Established). #>
    param([int]$p)
    try {
        $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($c -and $c.OwningProcess -gt 0) {
            $procId = [int]$c.OwningProcess
            return (Get-Process -Id $procId -ErrorAction SilentlyContinue)
        }
    } catch {}
    return $null
}

function Stop-ProxyByPort {
    <# Tue le processus qui occupe le port du proxy. Retourne $true si libere. #>
    param([int]$p)
    $owner = Get-PortOwner -p $p
    if (-not $owner) {
        # Fallback: cherche par Get-NetTCPConnection (Listen) directement
        try {
            $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($c -and $c.OwningProcess -gt 0) {
                Stop-Process -Id ([int]$c.OwningProcess) -Force -ErrorAction SilentlyContinue
            }
        } catch {}
    } else {
        Write-Host "  Arret du processus $($owner.ProcessName) (PID $($owner.Id))..." -ForegroundColor Yellow
        Stop-Process -Id $owner.Id -Force -ErrorAction SilentlyContinue
    }
    # Attendre que le port se libere
    for ($i = 0; $i -lt 10; $i++) {
        Start-Sleep -Milliseconds 500
        if (-not (Test-PortInUse -p $p)) {
            Write-Host "  Port $p libere." -ForegroundColor Green
            return $true
        }
    }
    Write-Host "  Impossible de liberer le port $p." -ForegroundColor Red
    return $false
}

function Wait-ForHttpReady {
    param([string]$url, [int]$timeoutSeconds = 30)
    $t0 = Get-Date
    while (((Get-Date) - $t0).TotalSeconds -lt $timeoutSeconds) {
        try {
            $null = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 2 -ErrorAction Stop
            return $true
        } catch { Start-Sleep -Seconds 1 }
    }
    return $false
}

Assert-Python
Assert-Venv
Install-Deps

$port = Get-Port

if ($args.Count -gt 0 -and $args[0] -eq "go") {
    Show-ProxyStartupInfo
    # If port already in use, report owner and abort
    if (Test-PortInUse -p $port) {
        $owner = Get-PortOwner -p $port
        if ($owner) { Write-Host "Port $port deja utilise par PID $($owner.Id) ($($owner.ProcessName))." -ForegroundColor Yellow }
        else { Write-Host "Port $port deja utilise." -ForegroundColor Yellow }
        exit 1
    }

    $logOut = Join-Path $ScriptRoot "rotator.stdout.log"
    $logErr = Join-Path $ScriptRoot "rotator.stderr.log"
    Write-Host "Demarrage non-interactif du proxy" -ForegroundColor Cyan
    Write-Host "  stdout -> $logOut" -ForegroundColor DarkGray
    Write-Host "  stderr -> $logErr" -ForegroundColor DarkGray
    $venvPython = Join-Path $ScriptRoot ".venv\Scripts\python.exe"
    $pyExe = if (Test-Path $venvPython) { $venvPython } else { "python" }
    $null = Start-Process -FilePath $pyExe -ArgumentList "main.py" -WorkingDirectory $ScriptRoot -NoNewWindow -RedirectStandardOutput $logOut -RedirectStandardError $logErr -PassThru

    $ready = Wait-ForHttpReady -url "http://127.0.0.1:$port/api/status" -timeoutSeconds 45
    if ($ready) {
        Write-Host "[OK] Proxy lance et repondit sur http://127.0.0.1:$port" -ForegroundColor Green
        Write-Host "Dashboard: http://127.0.0.1:$port/dashboard" -ForegroundColor Cyan
        exit 0
    } else {
        Write-Host "[WARN] Proxy demarre mais n'a pas repondu a /api/status dans le delai." -ForegroundColor Yellow
        Write-Host "  Consultez $logOut et $logErr" -ForegroundColor DarkGray
        if (Test-Path $logErr) {
            $errLines = Get-Content $logErr -Tail 15
            if ($errLines) {
                Write-Host "--- Derniers logs stderr ---" -ForegroundColor Red
                $errLines | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
            }
        }
        exit 1
    }
}

:menuLoop while ($true) {
    if ([Console]::IsInputRedirected) {
        Write-Host "Entree interactive non disponible. Lancez start.ps1 dans un terminal interactif." -ForegroundColor Red
        break
    }

    $proxyUp = Test-ProxyRunning
    Show-Menu -ProxyUp $proxyUp
    if (-not (Get-Variable -Name emptyChoiceCount -Scope Script -ErrorAction SilentlyContinue)) {
        $script:emptyChoiceCount = 0
    }

    $choice = Read-Host "Choix"
    if ([string]::IsNullOrWhiteSpace($choice)) {
        $script:emptyChoiceCount++
        if ($script:emptyChoiceCount -ge 3) {
            Write-Host "Trop de choix vides consecutifs. Arret du launcher pour eviter une boucle." -ForegroundColor Yellow
            break
        }
        Write-Host "Choix vide. Tapez 1, 2, 3, 4 ou 0." -ForegroundColor Yellow
        Start-Sleep -Milliseconds 350
        continue
    }

    $script:emptyChoiceCount = 0

    switch ($choice) {
        "1" {
            Show-ProxyStartupInfo
            python .\main.py
        }
        "2" {
            if (-not (Start-ProxyIfNeeded)) { break }
            $status = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/status" -Method Get -TimeoutSec 5
            Write-Host ""
            Write-Host "  Mode     : $($status.mode)" -ForegroundColor Cyan
            Write-Host "  Requetes : $($status.total_requests_today) aujourd'hui" -ForegroundColor White
            Write-Host "  Pause    : $($status.paused)" -ForegroundColor White
            Write-Host ""
            $status.profiles | ForEach-Object {
                $prov = if ($_.provider -eq '-') { 'aucun' } else { $_.provider }
                Write-Host "  $($_.emoji) $($_.name) -> $prov/$($_.model) (req: $($_.requests_today))" -ForegroundColor White
            }
            Write-Host ""
        }
        "3" {
            if (-not (Start-ProxyIfNeeded)) { break }
            $project = New-ClaudeProject
            $token = if ($project) { [string]$project.token } else { "rotator" }
            $projectName = if ($project) { [string]$project.name } else { "rotator" }

            Write-Host ""
            Write-Host "Token Claude actif: $projectName" -ForegroundColor Green
            Write-Host ""

            $launchNow = Read-Host "Lancer Claude maintenant dans un nouveau terminal ? (Y/N)"

            if ($launchNow -in @("Y", "y", "O", "o")) {
                $defaultDir = $ScriptRoot
                $userDir = Read-Host "Collez le dossier pour lancer Claude (Entrer = dossier actuel: $defaultDir)"
                $targetDir = if ([string]::IsNullOrWhiteSpace($userDir)) { $defaultDir } else { $userDir.Trim() }

                if (-not (Test-Path -LiteralPath $targetDir -PathType Container)) {
                    Write-Host "Dossier introuvable, fallback sur dossier actuel: $defaultDir" -ForegroundColor Yellow
                    $targetDir = $defaultDir
                }

                $safeDir = ConvertTo-EscapedSingleQuote $targetDir
                $safeToken = ConvertTo-EscapedSingleQuote $token
                $gitBash = if (Test-Path 'C:\Program Files\Git\bin\bash.exe') { 'C:\Program Files\Git\bin\bash.exe' } elseif (Test-Path 'C:\Program Files (x86)\Git\bin\bash.exe') { 'C:\Program Files (x86)\Git\bin\bash.exe' } else { '' }
                $gitBashEnv = if ($gitBash) { "`$env:CLAUDE_CODE_GIT_BASH_PATH='$gitBash'; " } else { "" }
                $cmd = "Set-Location -LiteralPath '$safeDir'; `$env:ANTHROPIC_BASE_URL='http://localhost:$port'; `$env:ANTHROPIC_AUTH_TOKEN='$safeToken'; $gitBashEnv Write-Host 'ANTHROPIC_BASE_URL=' `$env:ANTHROPIC_BASE_URL -ForegroundColor Cyan; Write-Host 'Projet=' '$projectName' -ForegroundColor Cyan; Write-Host 'Modele par defaut=' 'coding' -ForegroundColor Cyan; claude --model coding"
                Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", $cmd | Out-Null
                Write-Host "Claude lance dans un nouveau terminal (dossier: $targetDir)." -ForegroundColor Green
            }
            else {
                $manualCmd = New-ClaudeManualCommand -WorkDir $ScriptRoot -Token $token
                Write-Host ""
                Write-Host "Vous pouvez lancer Claude n'importe ou avec cette commande:" -ForegroundColor Yellow
                Write-Host "  $manualCmd" -ForegroundColor Cyan
            }
        }
        "4" {
            if (-not (Start-ProxyIfNeeded)) { break }
            Write-Host "Ouverture du dashboard..." -ForegroundColor Cyan
            Start-Process "http://127.0.0.1:$port/dashboard"
        }
        "5" {
            if (-not $proxyUp) {
                Write-Host "Le proxy n'est pas en cours d'execution." -ForegroundColor Yellow
                break
            }
            Write-Host "Arret du proxy..." -ForegroundColor Yellow
            $killed = Stop-ProxyByPort -p $port
            if ($killed) {
                Write-Host "Proxy arrete." -ForegroundColor Green
            }
        }
        "0" { break menuLoop }
        default { Write-Host "Choix invalide." -ForegroundColor Yellow }
    }
}