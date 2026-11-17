#!/usr/bin/env bash
# Universal Converter — launcher para macOS (duplo clique no Finder).
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
    exec python3 ./universal_converter_launcher.py "$@"
fi
osascript -e 'display dialog "Python 3 não encontrado. Instale em python.org (a versão oficial inclui Tkinter) ou via Homebrew: brew install python-tk@3.12" buttons {"OK"}'
