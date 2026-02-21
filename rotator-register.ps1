<#
  rotator-register.ps1 - Enregistre la commande "rotator" dans votre profil PowerShell
  
  Apres execution, vous pourrez taper depuis n'importe quel dossier :
    rotator                  # demarre si besoin + ouvre dashboard
    rotator -StatusOnly      # statut rapide
    rotator -Stop            # arrete le proxy
    rotator -Claude          # lance Claude Code
    rotator -Dashboard       # ouvre le dashboard

  Ce script :
    1. Definit ROTATOR_HOME en variable d'environnement utilisateur
    2. Ajoute une fonction "rotator" dans votre $PROFILE PowerShell
    3. Source le profil pour rendre la commande disponible immediatement

  Usage :
    .\rotator-register.ps1             # installe
    .\rotator-register.ps1 -Uninstall  # desinstalle
#>

param(
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

$RotatorRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$QuickScript = Join-Path $RotatorRoot "rotator-quick.ps1"

if (-not (Test-Path $QuickScript)) {
    Write-Host "[ERREUR] rotator-quick.ps1 introuvable dans $RotatorRoot" -ForegroundColor Red
    exit 1
}

$profilePath = $PROFILE.CurrentUserAllHosts
$marker = "# --- API-ROTATOR-BEGIN ---"
$markerEnd = "# --- API-ROTATOR-END ---"

function Remove-RotatorBlock {
    param([string]$path)
    if (-not (Test-Path $path)) { return }
    $content = Get-Content $path -Raw
    if ($content -match [regex]::Escape($marker)) {
        $pattern = [regex]::Escape($marker) + "[\s\S]*?" + [regex]::Escape($markerEnd) + "\r?\n?"
        $cleaned = [regex]::Replace($content, $pattern, "")
        Set-Content -Path $path -Value $cleaned.TrimEnd() -Encoding UTF8
        return $true
    }
    return $false
}

# ── Uninstall ──
if ($Uninstall) {
    Write-Host "Desinstallation de la commande 'rotator'..." -ForegroundColor Yellow

    # Remove env var
    [Environment]::SetEnvironmentVariable("ROTATOR_HOME", $null, "User")
    $env:ROTATOR_HOME = $null
    Write-Host "  [OK] Variable ROTATOR_HOME supprimee." -ForegroundColor Green

    # Remove profile block
    $removed = Remove-RotatorBlock -path $profilePath
    if ($removed) {
        Write-Host "  [OK] Bloc rotator supprime de $profilePath" -ForegroundColor Green
    } else {
        Write-Host "  Aucun bloc rotator trouve dans le profil." -ForegroundColor DarkGray
    }

    Write-Host ""
    Write-Host "Desinstallation terminee. Relancez PowerShell pour appliquer." -ForegroundColor Cyan
    exit 0
}

# ── Install ──
Write-Host ""
Write-Host "=== Enregistrement de la commande 'rotator' ===" -ForegroundColor Cyan
Write-Host ""

# 1. Set ROTATOR_HOME (user-level env var)
[Environment]::SetEnvironmentVariable("ROTATOR_HOME", $RotatorRoot, "User")
$env:ROTATOR_HOME = $RotatorRoot
Write-Host "[1/3] ROTATOR_HOME = $RotatorRoot" -ForegroundColor Green

# 2. Add function to $PROFILE
$block = @"

$marker
# Commande rapide API Rotator - generee par rotator-register.ps1
`$env:ROTATOR_HOME = "$RotatorRoot"
function rotator {
    & "$QuickScript" @args
}
$markerEnd
"@

# Ensure profile file exists
if (-not (Test-Path $profilePath)) {
    $dir = Split-Path $profilePath -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    New-Item -ItemType File -Path $profilePath -Force | Out-Null
    Write-Host "  Profil cree : $profilePath" -ForegroundColor DarkGray
}

# Remove old block if present, then append
Remove-RotatorBlock -path $profilePath | Out-Null
Add-Content -Path $profilePath -Value $block -Encoding UTF8
Write-Host "[2/3] Fonction 'rotator' ajoutee a $profilePath" -ForegroundColor Green

# 3. Source the profile in the current session
try {
    . $profilePath
    Write-Host "[3/3] Profil recharge - 'rotator' disponible immediatement !" -ForegroundColor Green
} catch {
    Write-Host "[3/3] Profil ecrit mais echec du rechargement. Relancez PowerShell." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "================================================================" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  La commande 'rotator' est maintenant disponible partout !" -ForegroundColor Green
Write-Host ""
Write-Host "  Exemples d utilisation :" -ForegroundColor White
Write-Host "    rotator                    # demarre + dashboard" -ForegroundColor Cyan
Write-Host "    rotator -StatusOnly        # statut rapide" -ForegroundColor Cyan
Write-Host "    rotator -Stop              # arrete le proxy" -ForegroundColor Cyan
Write-Host "    rotator -Claude            # lance Claude Code" -ForegroundColor Cyan
Write-Host "    rotator -Dashboard         # ouvre le dashboard" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Pour desinstaller :" -ForegroundColor DarkGray
Write-Host "    .\rotator-register.ps1 -Uninstall" -ForegroundColor DarkGray
Write-Host ""
Write-Host "================================================================" -ForegroundColor DarkGray
