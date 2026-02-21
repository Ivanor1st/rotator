$null = [System.Management.Automation.Language.Parser]::ParseFile('d:\Project\rotator\start.ps1',[ref]$null,[ref]$null)
if ($?) { Write-Host 'ok' } else { Write-Host 'parse failed' }
