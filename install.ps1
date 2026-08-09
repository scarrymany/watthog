<#
.SYNOPSIS
    WattHog installer for Windows.

.DESCRIPTION
    Downloads the latest WattHog.exe from GitHub releases, puts it into a
    per-user directory and adds that directory to PATH. No administrator
    rights are required.

    This script is deliberately pure ASCII. Windows PowerShell 5.1 reads a
    .ps1 file without a byte order mark using the system ANSI code page, which
    corrupts any non-ASCII text and breaks parsing; adding a BOM would fix that
    but would then break `irm ... | iex`, because the mark survives into the
    downloaded string and stops `param` from being the first statement. Staying
    within ASCII keeps both invocation paths working.

.PARAMETER InstallDir
    Target directory. Defaults to %LOCALAPPDATA%\Programs\WattHog.

.PARAMETER SkipPath
    Leave the PATH variable alone.

.EXAMPLE
    irm https://raw.githubusercontent.com/scarrymany/watthog/main/install.ps1 | iex

.EXAMPLE
    .\install.ps1 -InstallDir D:\Tools\WattHog
#>
[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'Programs\WattHog'),
    [switch]$SkipPath
)

$ErrorActionPreference = 'Stop'

$AssetUrl = 'https://github.com/scarrymany/watthog/releases/latest/download/WattHog.exe'
$ExecutableName = 'WattHog.exe'

Write-Host ''
Write-Host '  WattHog - PC power consumption meter' -ForegroundColor Yellow
Write-Host ''

if ($env:OS -ne 'Windows_NT') {
    throw 'This installer targets Windows. On Linux use install.sh instead.'
}

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
} catch {
    Write-Verbose 'This .NET version already negotiates a modern TLS version.'
}

Write-Host "  Install directory: $InstallDir" -ForegroundColor Cyan
if (-not (Test-Path -LiteralPath $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

$target = Join-Path $InstallDir $ExecutableName
Write-Host '  Downloading the latest build...' -ForegroundColor Cyan
try {
    Invoke-WebRequest -Uri $AssetUrl -OutFile $target -UseBasicParsing
} catch {
    throw "Could not download $AssetUrl. Check your internet connection. Error: $($_.Exception.Message)"
}

$sizeMb = [math]::Round((Get-Item -LiteralPath $target).Length / 1MB, 1)
Write-Host "  Installed: $target ($sizeMb MB)" -ForegroundColor Green

if (-not $SkipPath) {
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $entries = @()
    if ($userPath) {
        $entries = $userPath.Split(';') | Where-Object { $_ -ne '' }
    }
    if ($entries -notcontains $InstallDir) {
        [Environment]::SetEnvironmentVariable('Path', (($entries + $InstallDir) -join ';'), 'User')
        $env:Path = "$env:Path;$InstallDir"
        Write-Host '  Added to the user PATH.' -ForegroundColor Green
        Write-Host '  Open a new terminal so the change takes effect.' -ForegroundColor DarkGray
    } else {
        Write-Host '  Already on PATH.' -ForegroundColor Green
    }
}

Write-Host ''
Write-Host '  Done. Run it:' -ForegroundColor Yellow
Write-Host '    WattHog              ' -NoNewline -ForegroundColor White
Write-Host '# menu' -ForegroundColor DarkGray
Write-Host '    WattHog run          ' -NoNewline -ForegroundColor White
Write-Host '# 60 second measurement' -ForegroundColor DarkGray
Write-Host '    WattHog info         ' -NoNewline -ForegroundColor White
Write-Host '# detected hardware and sensors' -ForegroundColor DarkGray
Write-Host ''
Write-Host '  The application interface is in Russian. Author: @yeet17' -ForegroundColor DarkGray
Write-Host ''
