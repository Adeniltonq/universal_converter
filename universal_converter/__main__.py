"""Ponto de entrada da aplicação.

Uso:
    python -m universal_converter           # interface gráfica
    python universal_converter_launcher.py  # idem, sem instalar nada
"""

from __future__ import annotations

import argparse
import sys


def _check_tk() -> None:
    try:
        import tkinter  # noqa: F401
    except ImportError:
        message = (
            "O Tkinter não está disponível neste Python.\n\n"
            "Instalação:\n"
            "  • Debian/Ubuntu:  sudo apt install python3-tk\n"
            "  • Fedora:         sudo dnf install python3-tkinter\n"
            "  • Arch:           sudo pacman -S tk\n"
            "  • openSUSE:       sudo zypper install python3-tk\n"
            "  • macOS/Windows (python.org): já vem incluído\n"
        )
        sys.stderr.write(message)
        try:
            import tkinter.messagebox as mb  # pragma: no cover
        except ImportError:
            return
        mb.showerror("Tkinter ausente", message)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="universal-converter",
                                     description="Conversor de áudio e vídeo em lote")
    parser.add_argument("--version", action="store_true", help="mostra a versão e sai")
    parser.add_argument("--diagnostico", "--diagnostics", dest="diagnostics",
                        action="store_true",
                        help="imprime informações do FFmpeg e da fila e sai")
    args = parser.parse_args(argv)

    from . import __version__
    if args.version:
        print(f"Universal Converter {__version__}")
        return 0

    if args.diagnostics:
        from .core.logger import setup_logging
        from .core.settings import Settings
        from .ui.controller import AppController
        setup_logging()
        controller = AppController(Settings())
        print(controller.ffmpeg_report())
        return 0 if not controller.ff.error else 1

    _check_tk()
    try:
        import tkinter as tk
    except ImportError:
        return 1

    from .core.logger import setup_logging
    from .core.settings import Settings
    from .ui.controller import AppController
    from .ui.main_window import MainWindow

    setup_logging()
    controller = AppController(Settings())
    try:
        window = MainWindow(controller)
    except tk.TclError as exc:
        sys.stderr.write(f"Não foi possível abrir a janela: {exc}\n")
        return 1
    window.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
