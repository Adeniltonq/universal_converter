#!/usr/bin/env bash
# Instalador do Universal Converter para Linux.
# Cria um ambiente virtual local e instala o comando "universal-converter"
# (launcher no menu de aplicativos e vinculado ao desktop).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${UMC_VENV:-$ROOT/.venv}"

echo "==> Verificando Python 3.9+"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || {
    echo "É necessário Python 3.9 ou superior." >&2
    exit 1
}

echo "==> Verificando Tkinter"
python3 -c 'import tkinter' 2>/dev/null || {
    echo "Tkinter ausente. Instale com:" >&2
    echo "  Debian/Ubuntu: sudo apt install python3-tk" >&2
    echo "  Fedora:        sudo dnf install python3-tkinter" >&2
    echo "  Arch:          sudo pacman -S tk" >&2
    exit 1
}

echo "==> Verificando FFmpeg"
if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
    echo "    $(ffmpeg -hide_banner -version | head -1)"
else
    echo "    AVISO: FFmpeg/FFprobe não encontrados no PATH."
    echo "    Instale (ex.: sudo apt install ffmpeg) ou coloque os binários em $ROOT/bin/"
fi

echo "==> Criando ambiente virtual em $VENV"
python3 -m venv "$VENV"

echo "==> Criando launcher universal-converter"
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/universal-converter" <<LAUNCHER
#!/usr/bin/env bash
exec "$VENV/bin/python" "$ROOT/universal_converter_launcher.py" "\$@"
LAUNCHER
chmod +x "$HOME/.local/bin/universal-converter"

echo "==> Criando atalho no menu de aplicativos"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$APPS"
ICON="$ROOT/resources/icon.png"
cat > "$APPS/universal-converter.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Universal Converter
Comment=Conversor de áudio e vídeo em lote
Exec=$HOME/.local/bin/universal-converter
Icon=$ICON
Terminal=false
Categories=AudioVideo;Audio;Video;Utility;
Keywords=audio;video;converter;ffmpeg;mp3;flac;opus;
DESKTOP
chmod +x "$APPS/universal-converter.desktop"
command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database "$APPS" >/dev/null 2>&1 || true

cat <<DONE

Instalação concluída.

  Abrir pelo menu de aplicativos: "Universal Converter"
  Ou no terminal:                 universal-converter
  Verificação rápida:             universal-converter --diagnostico

Se o comando não aparecer no terminal, adicione ao PATH:
  export PATH="\$HOME/.local/bin:\$PATH"

DONE
