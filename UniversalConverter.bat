@echo off
REM Universal Converter — launcher para Windows (duplo clique).
REM Requer Python 3.9+ com Tkinter (versao do python.org ja inclui) e FFmpeg.
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python nao encontrado no PATH.
    echo Instale em https://www.python.org/downloads/windows/ e marque "Add python.exe to PATH".
    pause
    exit /b 1
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
    if not exist "%~dp0bin\ffmpeg.exe" (
        echo AVISO: FFmpeg nao encontrado no PATH nem em bin\ffmpeg.exe
        echo Baixe em https://www.gyan.dev/ffmpeg/builds/ e coloque ffmpeg.exe e ffprobe.exe em bin\
    )
)

start "" pythonw "%~dp0universal_converter_launcher.py"
exit /b 0
