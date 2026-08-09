<#
.SYNOPSIS
    Установщик WattHog для Windows.

.DESCRIPTION
    Скачивает последнюю сборку WattHog.exe из релизов GitHub, кладёт её в
    каталог пользователя и добавляет этот каталог в PATH. Права администратора
    не нужны: всё ставится только для текущего пользователя.

.PARAMETER InstallDir
    Куда установить. По умолчанию %LOCALAPPDATA%\Programs\WattHog.

.PARAMETER SkipPath
    Не трогать переменную PATH.

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

function Write-Step {
    param([string]$Message)
    Write-Host "  $Message" -ForegroundColor Cyan
}

function Write-Done {
    param([string]$Message)
    Write-Host "  $Message" -ForegroundColor Green
}

Write-Host ''
Write-Host '  WattHog - измеритель энергопотребления ПК' -ForegroundColor Yellow
Write-Host ''

if ([Environment]::OSVersion.Platform -ne 'Win32NT') {
    throw 'Этот установщик рассчитан на Windows. Для Linux используйте install.sh.'
}

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
} catch {
    Write-Verbose 'Версия .NET уже использует современный TLS.'
}

Write-Step "Каталог установки: $InstallDir"
if (-not (Test-Path -LiteralPath $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

$target = Join-Path $InstallDir $ExecutableName
Write-Step 'Скачиваю последнюю сборку...'
try {
    Invoke-WebRequest -Uri $AssetUrl -OutFile $target -UseBasicParsing
} catch {
    throw "Не удалось скачать $AssetUrl. Проверьте подключение к интернету. Ошибка: $($_.Exception.Message)"
}

$sizeMb = [math]::Round((Get-Item -LiteralPath $target).Length / 1MB, 1)
Write-Done "Установлено: $target ($sizeMb МБ)"

if (-not $SkipPath) {
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $entries = @()
    if ($userPath) {
        $entries = $userPath.Split(';') | Where-Object { $_ -ne '' }
    }
    if ($entries -notcontains $InstallDir) {
        $updated = (($entries + $InstallDir) -join ';')
        [Environment]::SetEnvironmentVariable('Path', $updated, 'User')
        $env:Path = "$env:Path;$InstallDir"
        Write-Done 'Каталог добавлен в PATH пользователя.'
        Write-Host '  Откройте новый терминал, чтобы PATH подхватился.' -ForegroundColor DarkGray
    } else {
        Write-Done 'Каталог уже есть в PATH.'
    }
}

Write-Host ''
Write-Host '  Готово. Запуск:' -ForegroundColor Yellow
Write-Host '    WattHog              ' -NoNewline -ForegroundColor White
Write-Host '# меню' -ForegroundColor DarkGray
Write-Host '    WattHog run          ' -NoNewline -ForegroundColor White
Write-Host '# замер 60 секунд' -ForegroundColor DarkGray
Write-Host '    WattHog info         ' -NoNewline -ForegroundColor White
Write-Host '# железо и источники данных' -ForegroundColor DarkGray
Write-Host ''
Write-Host '  Автор: @yeet17' -ForegroundColor DarkGray
Write-Host ''
