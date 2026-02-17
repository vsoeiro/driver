param()

$ErrorActionPreference = "Stop"

Write-Host "Checking winget availability..."
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "winget is not installed. Install App Installer from Microsoft Store and retry."
}

Write-Host "Installing Redis (Redis.Redis) via winget..."
winget install --id Redis.Redis --exact --accept-package-agreements --accept-source-agreements --silent

if ($LASTEXITCODE -ne 0) {
    throw "winget failed to install Redis.Redis (exit code $LASTEXITCODE)."
}

$redisServer = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages\Redis.Redis_Microsoft.Winget.Source_8wekyb3d8bbwe\redis-server.exe"
if (-not (Test-Path $redisServer)) {
    Write-Warning "redis-server.exe not found at expected path. Locate it with: where redis-server"
}

Write-Host "Redis installation completed."
Write-Host "Start Redis manually with: redis-server"
