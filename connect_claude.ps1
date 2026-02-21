param(
    [string]$Token = "rotator",
    [switch]$InstallClaude,
    [string]$WorkDir = "",
    [switch]$InstallSkills,
    [string]$SkillsJson = "",
    [string]$Model = ""
)

$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptRoot

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

function Test-ProxyReady {
    param([int]$Port)
    try {
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/status" -Method Get -TimeoutSec 2 -ErrorAction Stop
        return $true
    } catch { return $false }
}

# -- Detect proxy --
Write-Host "Verification du proxy..." -ForegroundColor Cyan
$port = Get-Port
if (-not (Test-ProxyReady -Port $port)) {
    Write-Host "Proxy non detecte sur le port $port. Demarrage automatique..." -ForegroundColor Yellow
    Start-Process -FilePath "python" -ArgumentList ".\main.py" | Out-Null
    $started = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        Write-Host "." -NoNewline -ForegroundColor DarkGray
        if (Test-ProxyReady -Port $port) {
            $started = $true
            break
        }
    }
    Write-Host ""
    if (-not $started) {
        Write-Host "[ERREUR] Proxy non joignable apres demarrage automatique." -ForegroundColor Red
        return
    }
    Write-Host "[OK] Proxy lance sur le port $port." -ForegroundColor Green
} else {
    Write-Host "[OK] Proxy actif sur le port $port." -ForegroundColor Green
}

# -- Environment variables for Claude Code --
$env:ANTHROPIC_BASE_URL = "http://localhost:$port"
$env:ANTHROPIC_AUTH_TOKEN = $Token
# Disable experimental beta headers (proxy routes to non-Anthropic providers)
$env:CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS = "1"

# Git Bash is REQUIRED for Claude Code on Windows
$gitBashPath = "C:\Program Files\Git\bin\bash.exe"
if (-not (Test-Path $gitBashPath)) {
    $gitBashPath = "C:\Program Files (x86)\Git\bin\bash.exe"
}
if (Test-Path $gitBashPath) {
    $env:CLAUDE_CODE_GIT_BASH_PATH = $gitBashPath
} else {
    Write-Host "[WARN] Git Bash non trouve. Claude Code sur Windows necessite Git for Windows." -ForegroundColor Yellow
    Write-Host "       Telechargez-le sur https://git-scm.com/downloads/win" -ForegroundColor Yellow
}

# -- Install Claude Code --
if ($InstallClaude) {
    $hasClaude = Get-Command claude -ErrorAction SilentlyContinue
    if (-not $hasClaude) {
        Write-Host "Claude Code non detecte. Installation via installeur natif..." -ForegroundColor Yellow
        try {
            & ([scriptblock]::Create((Invoke-RestMethod https://claude.ai/install.ps1)))
            Write-Host "[OK] Claude Code installe." -ForegroundColor Green
        } catch {
            Write-Host "[WARN] Echec installeur natif, tentative via npm..." -ForegroundColor Yellow
            $hasNpm = Get-Command npm -ErrorAction SilentlyContinue
            if ($hasNpm) {
                npm install -g @anthropic-ai/claude-code
            } else {
                Write-Host "npm introuvable. Installez Node.js ou telechargez Claude Code manuellement." -ForegroundColor Yellow
                Write-Host "  Windows: irm https://claude.ai/install.ps1 | iex" -ForegroundColor Cyan
            }
        }
    }
}

# -- Navigate to work directory --
if ($WorkDir -and (Test-Path $WorkDir -PathType Container)) {
    Set-Location $WorkDir
    Write-Host "Dossier de travail : $WorkDir" -ForegroundColor Cyan
} elseif ($WorkDir) {
    Write-Host "[WARN] Dossier '$WorkDir' introuvable, lancement dans le dossier courant." -ForegroundColor Yellow
}

# -- Install skills (from skills.json) --
if ($InstallSkills) {
    $hasNpx = Get-Command npx -ErrorAction SilentlyContinue
    if (-not $hasNpx) {
        Write-Host "[WARN] npx introuvable - installez Node.js pour pouvoir ajouter des skills." -ForegroundColor Yellow
    } else {
        # Load skill catalog from skills.json
        $skillsJsonFile = Join-Path $ScriptRoot "skills.json"
        $skillCatalog = $null
        if (Test-Path $skillsJsonFile) {
            try {
                $skillCatalog = Get-Content $skillsJsonFile -Raw | ConvertFrom-Json
            } catch {
                Write-Host "[WARN] Impossible de lire skills.json : $($_.Exception.Message)" -ForegroundColor Yellow
            }
        } else {
            Write-Host "[WARN] skills.json introuvable dans $ScriptRoot" -ForegroundColor Yellow
        }

        # Build skillId -> repoUrl map from the catalog
        $skillMap = @{}
        if ($skillCatalog) {
            foreach ($s in $skillCatalog.defaults) {
                if ($s.id -and $s.repo) { $skillMap[$s.id] = "https://github.com/$($s.repo)" }
            }
            foreach ($pack in $skillCatalog.packs) {
                foreach ($s in $pack.skills) {
                    if ($s.id -and $s.repo) { $skillMap[$s.id] = "https://github.com/$($s.repo)" }
                }
            }
            foreach ($s in $skillCatalog.individual) {
                if ($s.id -and $s.repo) { $skillMap[$s.id] = "https://github.com/$($s.repo)" }
            }
        }

        function Install-SkillByName {
            param(
                [string]$SkillName,
                [bool]$IsGlobal = $true
            )
            if (-not $skillMap.ContainsKey($SkillName)) {
                Write-Host "[WARN] Skill '$SkillName' non trouvee dans skills.json, ignoree." -ForegroundColor Yellow
                return
            }
            $repo = $skillMap[$SkillName]
            $modeLabel = if ($IsGlobal) { "globale" } else { "locale" }
            Write-Host "Installation de skill '$SkillName' ($modeLabel) depuis $repo ..." -ForegroundColor Yellow
            try {
                # Use cmd /c to handle npm .cmd shims on Windows (avoids Win32 error)
                # -y = auto-accept npx install, -g = global install
                $installArgs = "npx -y skills add $repo --skill $SkillName -y"
                if ($IsGlobal) { $installArgs += " -g" }
                $proc = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $installArgs -NoNewWindow -Wait -PassThru -ErrorAction Stop
                if ($proc.ExitCode -eq 0) {
                    Write-Host "[OK] $SkillName installe ($modeLabel)." -ForegroundColor Green
                } else {
                    Write-Host "[ERREUR] Installation de $SkillName retour code $($proc.ExitCode)." -ForegroundColor Red
                }
            } catch {
                Write-Host ("[ERREUR] Echec installation {0} : {1}" -f $SkillName, $_.Exception.Message) -ForegroundColor Red
            }
        }

        # Determine which skills to install
        # SkillsJson is comma-separated skill IDs. Also strip JSON residue (["  "  ]) for robustness.
        $selectedSkills = @()
        if ($SkillsJson -and $SkillsJson.Trim()) {
            $selectedSkills = @(
                $SkillsJson -split ',' |
                ForEach-Object { $_ -replace '[\[\]"]', '' } |
                ForEach-Object { $_.Trim() } |
                Where-Object { $_ -ne '' }
            )
        }

        # Build final list of skill IDs
        $skillsToInstall = @()
        if ($selectedSkills.Count -gt 0) {
            $skillsToInstall = $selectedSkills
        } elseif ($skillCatalog -and $skillCatalog.defaults) {
            $skillsToInstall = @($skillCatalog.defaults | Where-Object { $_.enabled -eq $true } | ForEach-Object { $_.id })
        }

        if ($skillsToInstall.Count -gt 0) {
            Write-Host ""
            Write-Host "==========================================" -ForegroundColor DarkGray
            Write-Host "  Installation des Skills" -ForegroundColor Green
            Write-Host "==========================================" -ForegroundColor DarkGray
            Write-Host ""
            Write-Host "  $($skillsToInstall.Count) skill(s) a installer :" -ForegroundColor Cyan
            foreach ($sk in $skillsToInstall) { Write-Host "    - $sk" -ForegroundColor White }
            Write-Host ""
            Write-Host "  Ou installer les skills ?" -ForegroundColor Yellow
            Write-Host "    [1] Globale  (~\.agents\skills\) - disponible pour tous les projets et agents" -ForegroundColor White
            Write-Host "    [2] Locale   ($((Get-Location).Path)\.agents\skills\) - uniquement ce projet" -ForegroundColor White
            Write-Host ""
            $installChoice = ""
            while ($installChoice -notin @("1", "2")) {
                $installChoice = Read-Host "  Votre choix (1/2) [defaut: 1]"
                if (-not $installChoice) { $installChoice = "1" }
            }
            $globalInstall = ($installChoice -eq "1")
            $locationLabel = if ($globalInstall) { "Globale (~\.agents\skills\)" } else { "Locale (projet courant)" }
            Write-Host "  -> $locationLabel" -ForegroundColor Green

            # If multiple skills, ask whether to remember the choice
            $rememberChoice = $true
            if ($skillsToInstall.Count -gt 1) {
                Write-Host ""
                Write-Host "  Plusieurs skills a installer. Que souhaitez-vous ?" -ForegroundColor Yellow
                Write-Host "    [1] Memoriser ce choix pour tous les skills" -ForegroundColor White
                Write-Host "    [2] Redemander l'emplacement pour chaque skill" -ForegroundColor White
                Write-Host ""
                $memChoice = ""
                while ($memChoice -notin @("1", "2")) {
                    $memChoice = Read-Host "  Votre choix (1/2) [defaut: 1]"
                    if (-not $memChoice) { $memChoice = "1" }
                }
                $rememberChoice = ($memChoice -eq "1")
                if ($rememberChoice) {
                    Write-Host "  -> Choix memorise pour tous les skills." -ForegroundColor Green
                } else {
                    Write-Host "  -> On vous redemandera pour chaque skill." -ForegroundColor Green
                }
            }

            Write-Host ""
            Write-Host "Installation de $($skillsToInstall.Count) skill(s)..." -ForegroundColor Cyan
            Write-Host ""

            foreach ($s in $skillsToInstall) {
                $currentGlobal = $globalInstall

                # If not remembering, ask for each skill
                if (-not $rememberChoice) {
                    Write-Host ""
                    Write-Host "  Skill '$s' -- ou installer ?" -ForegroundColor Yellow
                    Write-Host "    [1] Globale" -ForegroundColor White
                    Write-Host "    [2] Locale" -ForegroundColor White
                    $perChoice = ""
                    while ($perChoice -notin @("1", "2")) {
                        $perChoice = Read-Host "  Votre choix (1/2) [defaut: 1]"
                        if (-not $perChoice) { $perChoice = "1" }
                    }
                    $currentGlobal = ($perChoice -eq "1")
                }

                Install-SkillByName -SkillName $s -IsGlobal $currentGlobal
            }

            # Post-install message
            Write-Host ""
            Write-Host "==========================================" -ForegroundColor DarkGray
            Write-Host "  $($skillsToInstall.Count) skill(s) traite(s)." -ForegroundColor Green
            Write-Host "==========================================" -ForegroundColor DarkGray
            Write-Host ""
            Write-Host "  Pour voir les skills installes, demandez a votre agent :" -ForegroundColor Cyan
            Write-Host "    what skills are available" -ForegroundColor White -BackgroundColor DarkBlue
            Write-Host ""
        }
    }
}


Write-Host "" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor DarkGray
Write-Host "  Claude Code - Configuration" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  ANTHROPIC_BASE_URL       = $env:ANTHROPIC_BASE_URL" -ForegroundColor White
Write-Host "  ANTHROPIC_AUTH_TOKEN     = $($env:ANTHROPIC_AUTH_TOKEN.Substring(0, [Math]::Min(20, $env:ANTHROPIC_AUTH_TOKEN.Length)))..." -ForegroundColor White
if ($env:CLAUDE_CODE_GIT_BASH_PATH) {
    Write-Host "  CLAUDE_CODE_GIT_BASH_PATH = $env:CLAUDE_CODE_GIT_BASH_PATH" -ForegroundColor White
}
Write-Host "  Dossier                  = $(Get-Location)" -ForegroundColor White
Write-Host ""

# -- Verification: Claude Code installed? --
Write-Host "Verification de Claude Code..." -ForegroundColor Cyan
$hasClaude = Get-Command claude -ErrorAction SilentlyContinue
if (-not $hasClaude) {
    Write-Host "[ERREUR] Claude Code n'est pas installe !" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Pour l'installer :" -ForegroundColor Yellow
    Write-Host "    irm https://claude.ai/install.ps1 | iex" -ForegroundColor Cyan
    Write-Host "  Ou relancez ce script avec -InstallClaude" -ForegroundColor Yellow
    Write-Host ""
    return
}
$claudeVer = claude --version 2>&1
Write-Host "[OK] Claude Code $claudeVer detecte." -ForegroundColor Green

# -- Verification: quick connectivity test via /v1/messages --
Write-Host 'Test de connexion proxy <-> Claude Code...' -ForegroundColor Cyan
try {
    $testBody = @{
        model = "coding"
        max_tokens = 10
        messages = @(
            @{ role = "user"; content = "Reply OK" }
        )
    } | ConvertTo-Json -Depth 3
    $testHeaders = @{
        "x-api-key" = $Token
        "anthropic-version" = "2023-06-01"
        "Content-Type" = "application/json"
    }
    $testResult = Invoke-RestMethod -Uri "http://127.0.0.1:$port/v1/messages" -Method Post -Headers $testHeaders -Body $testBody -TimeoutSec 30
    $testText = ($testResult.content | Where-Object { $_.type -eq "text" } | Select-Object -First 1).text
    Write-Host "[OK] Proxy repond correctement : '$testText'" -ForegroundColor Green
}
catch {
    Write-Host "[WARN] Test de connectivity echoue : $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "       Claude Code peut ne pas fonctionner correctement." -ForegroundColor Yellow
}

# -- List available models --
try {
    $models = Invoke-RestMethod -Uri "http://127.0.0.1:$port/v1/models" -Method Get -Headers @{ Authorization = "Bearer $Token" }
    Write-Host ""
    Write-Host "Modeles disponibles :" -ForegroundColor Cyan
    $models.data | ForEach-Object {
        $prefix = if ($_.owned_by) { "  [$($_.owned_by)]" } else { "  " }
        Write-Host "$prefix $($_.id)" -ForegroundColor White
    }
}
catch {
    Write-Host "Impossible de recuperer la liste des modeles." -ForegroundColor Yellow
    if ($_.Exception.Message -match "401") {
        Write-Host "Token invalide." -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "=========================================" -ForegroundColor DarkGray
Write-Host "  Pret a lancer !" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Pour lancer Claude Code :" -ForegroundColor Cyan
Write-Host "  claude --model coding          (rotation auto, recommande)" -ForegroundColor White
Write-Host '  claude --model <nom_modele>    (modele specifique)' -ForegroundColor DarkGray
Write-Host '  claude --print "votre prompt"  (mode non-interactif)' -ForegroundColor DarkGray
Write-Host ""

if ($Model) {
    Write-Host "Lancement de Claude Code dans un nouveau terminal..." -ForegroundColor Green
    Write-Host ""

    # Build env + command for the new terminal
    $launchParts = @()
    $launchParts += "`$env:ANTHROPIC_BASE_URL = 'http://localhost:$port'"
    $launchParts += "`$env:ANTHROPIC_AUTH_TOKEN = '$Token'"
    $launchParts += "`$env:CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS = '1'"
    if ($env:CLAUDE_CODE_GIT_BASH_PATH) {
        $launchParts += "`$env:CLAUDE_CODE_GIT_BASH_PATH = '$($env:CLAUDE_CODE_GIT_BASH_PATH)'"
    }
    $launchParts += "Set-Location '$((Get-Location).Path)'"
    $launchParts += "claude --model $Model"
    $launchCmd = $launchParts -join "; "

    Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", $launchCmd

    Write-Host "[OK] Claude Code lance dans un nouveau terminal." -ForegroundColor Green
    Write-Host ""
    Write-Host "Cette fenetre peut etre fermee." -ForegroundColor DarkGray
}