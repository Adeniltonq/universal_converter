#!/usr/bin/env python3
"""Gera o executável do Universal Converter com PyInstaller.

O FFmpeg **não** é empacotado: o programa usa o FFmpeg instalado na máquina
(ou um binário colocado na pasta ``bin/`` ao lado do executável). Isso mantém o
pacote pequeno e evita misturar licenças (GPL/LGPL) do FFmpeg distribuído.

Uso:
    pip install pyinstaller
    python build.py                 # onefile
    python build.py --onedir        # pasta com dependências
    python build.py --ffmpeg C:/ffmpeg/bin/ffmpeg.exe   # inclui um FFmpeg em bin/
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "UniversalConverter"
ICON = os.path.join(ROOT, "resources", "icon.png")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--onedir", action="store_true",
                        help="gera uma pasta em vez de um arquivo único")
    parser.add_argument("--ffmpeg", default="", help="ffmpeg(.exe) para incluir em bin/")
    parser.add_argument("--ffprobe", default="", help="ffprobe(.exe) para incluir em bin/")
    parser.add_argument("--name", default=APP_NAME)
    parser.add_argument("--console", action="store_true",
                        help="mantém a janela de console (útil para depurar)")
    args = parser.parse_args(argv)

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller não encontrado. Instale com:  pip install pyinstaller",
              file=sys.stderr)
        return 1

    if args.ffmpeg:
        shutil.copy2(args.ffmpeg, os.path.join(ROOT, "bin", os.path.basename(args.ffmpeg)))
        print(f"FFmpeg copiado para bin/{os.path.basename(args.ffmpeg)}")
    if args.ffprobe:
        shutil.copy2(args.ffprobe, os.path.join(ROOT, "bin", os.path.basename(args.ffprobe)))
        print(f"FFprobe copiado para bin/{os.path.basename(args.ffprobe)}")

    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", args.name,
        "--onedir" if args.onedir else "--onefile",
        "--windowed" if not args.console else "--console",
        "--add-data", f"{ROOT}{os.pathsep}{os.path.basename(ROOT)}",
        "--collect-submodules", "tkinter",
        os.path.join(ROOT, "universal_converter_launcher.py"),
    ]
    bin_dir = os.path.join(ROOT, "bin")
    if os.path.isdir(bin_dir) and os.listdir(bin_dir):
        command[-2:-2] = ["--add-data", f"{bin_dir}{os.pathsep}bin"]
    if os.path.isfile(ICON) and not sys.platform.startswith("linux"):
        command[-2:-2] = ["--icon", ICON]
    print("Executando:\n  " + " ".join(command))
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode == 0:
        target = os.path.join(ROOT, "dist", args.name)
        print(f"\nPronto: {target}")
        print("Lembre-se: o FFmpeg precisa estar instalado e no PATH, ou copiado em bin/.")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
