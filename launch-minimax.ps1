# launch-minimax.ps1
# Lance Claude Code avec MiniMax via rotator
# Fix : désactive les plugins hooks + corrige python3 + restauration sécurisée

$settingsPath = "$env:USERPROFILE\.claude\settings.json"

# --- Fix python3 manquant sur Windows ---
if (-not (Get-Command python3 -ErrorAction SilentlyContinue)) {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        Set-Alias python3 python -Scope Global
        Write-Host "Alias python3 -> python créé pour cette session" -ForegroundColor DarkYellow
    } else {
        Write-Host "AVERTISSEMENT : python introuvable. Certains hooks peuvent échouer." -ForegroundColor Red
    }
}

# --- Lecture du fichier settings ---
if (-not (Test-Path $settingsPath)) {
    Write-Host "ERREUR : settings.json introuvable à $settingsPath" -ForegroundColor Red
    exit 1
}

$settings = Get-Content $settingsPath -Raw | ConvertFrom-Json

# --- Plugins à désactiver temporairement ---
$pluginsToDisable = @(
    "hookify@claude-plugins-official",
    "ralph-loop@claude-plugins-official",
    "feature-dev@claude-plugins-official",
    "pr-review-toolkit@claude-plugins-official",
    "commit-commands@claude-plugins-official"
)

# --- Désactivation ---
foreach ($plugin in $pluginsToDisable) {
    if ($settings.enabledPlugins.PSObject.Properties[$plugin]) {
        $settings.enabledPlugins.$plugin = $false
    }
}
$settings | ConvertTo-Json -Depth 10 | Set-Content $settingsPath
Write-Host "Plugins hooks désactivés" -ForegroundColor Yellow

# --- Variables d'environnement pour cette session ---
$env:ANTHROPIC_BASE_URL = "http://localhost:47822"
$env:ANTHROPIC_AUTH_TOKEN = "rotator"
$env:CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS = "1"

# --- Lancement sécurisé avec restauration garantie ---
Write-Host "Lancement de Claude Code avec MiniMax..." -ForegroundColor Cyan

try {
    claude --model coding
} finally {
    # Restauration même en cas de crash ou Ctrl+C
    $settings = Get-Content $settingsPath -Raw | ConvertFrom-Json
    foreach ($plugin in $pluginsToDisable) {
        if ($settings.enabledPlugins.PSObject.Properties[$plugin]) {
            $settings.enabledPlugins.$plugin = $true
        }
    }
    $settings | ConvertTo-Json -Depth 10 | Set-Content $settingsPath
    Write-Host "Plugins restaurés proprement" -ForegroundColor Green
}
