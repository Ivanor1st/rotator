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

$Port = Get-Port
$Base = "http://127.0.0.1:$Port"
$PidFile = Join-Path $ScriptRoot "rotator.pid"

function Invoke-RotatorApi {
    param(
        [string]$Path,
        [string]$Method = "GET",
        [hashtable]$Body
    )
    if ($Body) {
        return Invoke-RestMethod -Uri "$Base$Path" -Method $Method -ContentType "application/json" -Body ($Body | ConvertTo-Json)
    }
    return Invoke-RestMethod -Uri "$Base$Path" -Method $Method
}

function Start-Proxy {
    $python = if (Test-Path (Join-Path $ScriptRoot ".venv\Scripts\python.exe")) { Join-Path $ScriptRoot ".venv\Scripts\python.exe" } else { "python" }
    $proc = Start-Process -FilePath $python -ArgumentList "main.py" -WorkingDirectory $ScriptRoot -PassThru
    $proc.Id | Out-File $PidFile -Force
    Write-Host "Started proxy (PID=$($proc.Id))" -ForegroundColor Green
}

function Stop-Proxy {
    param([switch]$Force)
    $pidValue = $null
    if (Test-Path $PidFile) {
        $pidValue = Get-Content $PidFile | Select-Object -First 1
    }

    # Fallback: find by port if no PID file
    if (-not $pidValue) {
        try {
            $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($conn -and $conn.OwningProcess -gt 0) { $pidValue = [int]$conn.OwningProcess }
        } catch {}
    }

    if (-not $pidValue) {
        Write-Host "No proxy found (no PID file, port $Port not in use)." -ForegroundColor Yellow
        return
    }

    try {
        Invoke-RotatorApi -Path "/api/maintenance/backup" -Method "POST" -Body @{} | Out-Null
        Write-Host "Backup snapshot created before stop." -ForegroundColor Cyan
    }
    catch {
        Write-Host "Could not create backup before stop (continuing)." -ForegroundColor Yellow
    }

    Stop-Process -Id $pidValue -Force:$Force -ErrorAction SilentlyContinue
    Remove-Item $PidFile -ErrorAction SilentlyContinue

    # Wait for port to be freed
    $freed = $false
    for ($i = 0; $i -lt 10; $i++) {
        Start-Sleep -Milliseconds 500
        $still = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        if (-not $still) { $freed = $true; break }
    }
    if ($freed) {
        Write-Host "Stopped proxy (PID=$pidValue), port $Port freed." -ForegroundColor Green
    } else {
        Write-Host "Stopped proxy (PID=$pidValue) but port $Port may still be in use." -ForegroundColor Yellow
    }
}

function Show-Usage {
    Write-Host "Usage: .\rotator.ps1 <command>" -ForegroundColor Cyan
}

if ($args.Count -eq 0) { Show-Usage; exit 0 }

try {
    switch ($args[0].ToLower()) {
        "start" { Start-Proxy }
        "stop" { Stop-Proxy -Force:($args[1] -eq "--force") }
        "restart" { Stop-Proxy; Start-Proxy }
        "status" {
            $status = Invoke-RotatorApi -Path "/api/status"
            Write-Host "Mode: $($status.mode)  Paused: $($status.paused)" -ForegroundColor Cyan
            $status.profiles | ForEach-Object {
                Write-Host ("{0}: {1}/{2} override={3} req={4}" -f $_.name, $_.provider, $_.model, $_.override, $_.requests_today)
            }
        }
        "keys" { Invoke-RotatorApi -Path "/api/keys" | ConvertTo-Json -Depth 5 }
        "logs" {
            if ($args[1] -eq "--follow") {
                while ($true) {
                    (Invoke-RotatorApi -Path "/api/logs").items | ForEach-Object { "[$($_.time)] [$($_.profile)] $($_.message)" }
                    Start-Sleep -Seconds 2
                }
            } else {
                Invoke-RotatorApi -Path "/api/logs" | ConvertTo-Json -Depth 5
            }
        }
        "force" {
            if ($args[1] -eq "all") {
                $status = Invoke-RotatorApi -Path "/api/status"
                $status.profiles | ForEach-Object { Invoke-RotatorApi -Path "/api/override/force" -Method "POST" -Body @{ profile = $_.name; provider = $args[2] } | Out-Null }
            } else {
                Invoke-RotatorApi -Path "/api/override/force" -Method "POST" -Body @{ profile = $args[1]; provider = $args[2] } | Out-Null
            }
        }
        "unforce" {
            if ($args[1] -eq "all") {
                $status = Invoke-RotatorApi -Path "/api/status"
                $status.profiles | ForEach-Object { Invoke-RotatorApi -Path "/api/override/force" -Method "POST" -Body @{ profile = $_.name; provider = "auto" } | Out-Null }
            } else {
                Invoke-RotatorApi -Path "/api/override/force" -Method "POST" -Body @{ profile = $args[1]; provider = "auto" } | Out-Null
            }
        }
        "lock" {
            if ($args.Count -eq 2) { Invoke-RotatorApi -Path "/api/lock" -Method "POST" -Body @{ profile = "all"; model = $args[1] } | Out-Null }
            else { Invoke-RotatorApi -Path "/api/lock" -Method "POST" -Body @{ profile = $args[1]; model = $args[2] } | Out-Null }
        }
        "unlock" {
            if ($args[1] -eq "all") { Invoke-RotatorApi -Path "/api/lock/all" -Method "DELETE" | Out-Null }
            else { Invoke-RotatorApi -Path "/api/lock/$($args[1])" -Method "DELETE" | Out-Null }
        }
        "suspend" {
            $duration = $null
            if ($args[2]) {
                if ($args[2] -like "*h") {
                    $duration = [int]($args[2] -replace 'h','') * 60
                } else {
                    $duration = [int]$args[2]
                }
            }
            Invoke-RotatorApi -Path "/api/suspend" -Method "POST" -Body @{ provider = $args[1]; duration_minutes = $duration } | Out-Null
        }
        "resume" {
            if ($args[1] -eq "all") { @("ollama_cloud","nvidia","openrouter","google","local") | ForEach-Object { Invoke-RotatorApi -Path "/api/resume" -Method "POST" -Body @{ provider = $_ } | Out-Null } }
            else { Invoke-RotatorApi -Path "/api/resume" -Method "POST" -Body @{ provider = $args[1] } | Out-Null }
        }
        "skip" {
            $profileName = if ($args[1]) { $args[1] } else { "chat" }
            Invoke-RotatorApi -Path "/api/skip" -Method "POST" -Body @{ profile = $profileName } | Out-Null
        }
        "key" {
            switch ($args[1]) {
                "reset" { Invoke-RotatorApi -Path "/api/keys/reset" -Method "POST" -Body @{ provider = $args[2] } | Out-Null }
                "block" { Invoke-RotatorApi -Path "/api/keys/block" -Method "POST" -Body @{ label = $args[2] } | Out-Null }
                "unblock" { Invoke-RotatorApi -Path "/api/keys/unblock" -Method "POST" -Body @{ label = $args[2] } | Out-Null }
            }
        }
        "preset" {
            switch ($args[1]) {
                "list" { Invoke-RotatorApi -Path "/api/presets" | ConvertTo-Json -Depth 6 }
                "apply" {
                    $presets = Invoke-RotatorApi -Path "/api/presets"
                    $preset = $presets.items | Where-Object { $_.name -eq $args[2] } | Select-Object -First 1
                    if ($preset) { Invoke-RotatorApi -Path "/api/presets/$($preset.id)/apply" -Method "POST" | Out-Null }
                }
                "save" { Invoke-RotatorApi -Path "/api/presets" -Method "POST" -Body @{ name = $args[2]; description = ""; data = @{ profiles = @{} } } | Out-Null }
                "delete" {
                    $presets = Invoke-RotatorApi -Path "/api/presets"
                    $preset = $presets.items | Where-Object { $_.name -eq $args[2] } | Select-Object -First 1
                    if ($preset) { Invoke-RotatorApi -Path "/api/presets/$($preset.id)" -Method "DELETE" | Out-Null }
                }
            }
        }
        "test" {
            if ($args[1]) { Invoke-RotatorApi -Path "/api/tests/run/$($args[1])" -Method "POST" | ConvertTo-Json -Depth 6 }
            else { Invoke-RotatorApi -Path "/api/tests/run" -Method "POST" | ConvertTo-Json -Depth 6 }
        }
        "benchmark" { Invoke-RotatorApi -Path "/api/benchmark/start" -Method "POST" | Out-Null }
        "ping" { Invoke-RotatorApi -Path "/api/ping" | ConvertTo-Json -Depth 3 }
        "stats" {
            if ($args[1] -eq "--week") { Invoke-RotatorApi -Path "/api/stats?period=week" | ConvertTo-Json -Depth 6 }
            elseif ($args[1] -eq "export") { Invoke-RotatorApi -Path "/api/stats/export" | Out-File "stats.csv" }
            else { Invoke-RotatorApi -Path "/api/stats?period=today" | ConvertTo-Json -Depth 6 }
        }
        "schedule" {
            switch ($args[1]) {
                "list" { Invoke-RotatorApi -Path "/api/schedules" | ConvertTo-Json -Depth 6 }
                "add" { Invoke-RotatorApi -Path "/api/schedules" -Method "POST" -Body @{ name = "schedule"; action = "block_provider"; target = $args[2]; value = ""; time_start = "22:00"; time_end = "07:00"; days_of_week = "mon,tue,wed,thu,fri"; active = $true } | Out-Null }
                "delete" { Invoke-RotatorApi -Path "/api/schedules/$($args[2])" -Method "DELETE" | Out-Null }
            }
        }
        "reload" { Invoke-RotatorApi -Path "/api/reload-config" -Method "POST" | Out-Null }
        "reset" {
            if ($args[1] -eq "--hard") {
                if (Test-Path "rotator.db") { Remove-Item "rotator.db" -Force }
            }
            Invoke-RotatorApi -Path "/api/override/reset" -Method "POST" | Out-Null
        }
        "open" { Start-Process "$Base/dashboard" }
        "quota" { Invoke-RotatorApi -Path "/api/quota" | ConvertTo-Json -Depth 6 }
        "models" {
            $data = Invoke-RotatorApi -Path "/api/models"
            if ($args[1]) {
                $provider = $args[1]
                $data.providers.$provider | ConvertTo-Json -Depth 6
            } else {
                $data | ConvertTo-Json -Depth 6
            }
        }
        "compare" { Invoke-RotatorApi -Path "/api/compare" -Method "POST" -Body @{ prompt = $args[1]; models = @($args[2], $args[3]) } | ConvertTo-Json -Depth 6 }
        "health" { Invoke-RotatorApi -Path "/api/health" | ConvertTo-Json -Depth 6 }
        "doctor" {
            if (-not (Test-Path "config.yaml")) { Write-Host "config.yaml missing" -ForegroundColor Red }
            try { Invoke-RotatorApi -Path "/api/status" | Out-Null; Write-Host "Proxy OK" -ForegroundColor Green } catch { Write-Host "Proxy not running" -ForegroundColor Yellow }
        }
        default { Show-Usage }
    }
}
catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}