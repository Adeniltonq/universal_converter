# Universal Converter — instalador para Windows (PowerShell).
# Cria atalhos na Área de Trabalho e no Menu Iniciar e verifica Python/FFmpeg.
# Execute:  powershell -ExecutionPolicy Bypass -File .\install-windows.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "==> Universal Converter — instalacao" -ForegroundColor Cyan

# 1) Python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "Python nao encontrado. Instale em https://www.python.org/downloads/windows/" -ForegroundColor Red
    Write-Host "Marque a opcao 'Add python.exe to PATH' durante a instalacao."
    exit 1
}
& python -c "import sys, tkinter; sys.exit(0 if sys.version_info >= (3,9) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "E necessario Python 3.9+ com Tkinter (versao do python.org ja inclui)." -ForegroundColor Red
    exit 1
}

# 2) FFmpeg
$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffmpeg -and -not (Test-Path "$root\bin\ffmpeg.exe")) {
    Write-Host "AVISO: FFmpeg nao encontrado." -ForegroundColor Yellow
    Write-Host "Baixe em https://www.gyan.dev/ffmpeg/builds/ e copie ffmpeg.exe/ffprobe.exe para $root\bin\"
    Write-Host "Ou instale via winget:  winget install Gyan.FFmpeg"
}

# 3) Atalhos
$target = Join-Path $root "universal_converter_launcher.py"
$pythonw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
if (-not $pythonw) { $pythonw = (Get-Command python).Source }

function New-Shortcut($path) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($path)
    $shortcut.TargetPath = $pythonw
    $shortcut.Arguments = "`"$target`""
    $shortcut.WorkingDirectory = $root
    $shortcut.IconLocation = (Join-Path $root "resources\icon.png")
    $shortcut.Description = "Conversor de audio e video em lote"
    $shortcut.Save()
}

New-Shortcut (Join-Path ([Environment]::GetFolderPath("Desktop")) "Universal Converter.lnk")
$startMenu = Join-Path ([Environment]::GetFolderPath("Programs")) "Universal Converter"
New-Item -ItemType Directory -Force -Path $startMenu | Out-Null
New-Shortcut (Join-Path $startMenu "Universal Converter.lnk")

Write-Host ""
Write-Host "Instalacao concluida." -ForegroundColor Green
Write-Host "  Atalho criado na Area de Trabalho e no Menu Iniciar."
Write-Host "  Diagnostico: python `"$target`" --diagnostico"
