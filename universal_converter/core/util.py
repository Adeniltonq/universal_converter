"""Utilidades comuns: caminhos, formatação e funções de sistema."""

from __future__ import annotations

import os
import re
import shutil
import sys
import unicodedata

# ---------------------------------------------------------------------------
# Caminhos específicos de cada plataforma
# ---------------------------------------------------------------------------

_EXE = ".exe" if os.name == "nt" else ""


def app_data_dir() -> str:
    """Diretório de dados do programa, conforme a plataforma."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(base, "UniversalMediaConverter")
    elif sys.platform == "darwin":
        path = os.path.join(os.path.expanduser("~"), "Library", "Application Support",
                            "UniversalMediaConverter")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
        path = os.path.join(base, "universal-media-converter")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        path = os.path.expanduser("~")
    return path


def local_bin_dir() -> str:
    """Pasta bin/ junto ao programa (para colocar ffmpeg.exe ao lado do app)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "bin")


def find_tool(name: str, custom_dir: str | None = None) -> str | None:
    """Localiza um executável do FFmpeg, com prioridade:
    1) caminho customizado (pasta/executável definido nas configurações)
    2) pasta bin/ do programa
    3) PATH do sistema
    """
    exe = name + _EXE
    candidates: list[str] = []
    if custom_dir:
        custom_dir = os.path.expanduser(custom_dir)
        if os.path.isdir(custom_dir):
            candidates.append(os.path.join(custom_dir, exe))
        else:
            candidates.append(custom_dir)
    candidates.append(os.path.join(local_bin_dir(), exe))
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    found = shutil.which(exe)
    return found


def open_in_file_manager(path: str) -> bool:
    """Abre a pasta no gerenciador de arquivos do sistema."""
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
            return True
        if sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", path])
            return True
        import subprocess
        subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Formatação
# ---------------------------------------------------------------------------

def fmt_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "—"
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def fmt_size(num_bytes: float | None) -> str:
    if num_bytes is None:
        return "—"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def fmt_bitrate(bps: float | None) -> str:
    if not bps:
        return "—"
    if bps >= 1_000_000:
        return f"{bps / 1_000_000:.2f} Mbps"
    if bps >= 1_000:
        return f"{int(round(bps / 1000))} kbps"
    return f"{int(bps)} bps"


def fmt_speed(speed: float | None) -> str:
    if not speed or speed <= 0:
        return "—"
    return f"{speed:.2f}×"


# ---------------------------------------------------------------------------
# Nomes de arquivo seguros em todos os sistemas
# ---------------------------------------------------------------------------

_INVALID_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_filename(name: str, max_len: int = 180) -> str:
    """Remove caracteres inválidos para nomes de arquivo (Windows/Linux/macOS)."""
    name = _INVALID_FS.sub("", name)
    name = name.replace("\t", " ").strip().rstrip(". ")
    if not name:
        name = "arquivo"
    stem, dot, ext = name.rpartition(".")
    if dot and stem and stem.upper() in _WINDOWS_RESERVED:
        name = stem + "_." + ext
    elif not dot and name.upper() in _WINDOWS_RESERVED:
        name += "_"
    if len(name) > max_len:
        root, dot, extension = name.rpartition(".")
        if dot and len(extension) <= 6:
            name = root[: max_len - len(extension) - 1] + "." + extension
        else:
            name = name[:max_len]
    return name


def sanitize_dir_name(name: str) -> str:
    name = _INVALID_FS.sub("", name).strip().rstrip(". ")
    return name or "pasta"


def is_subpath(child: str, parent: str) -> bool:
    """Verifica se `child` está dentro de `parent` (inclusive igual)."""
    try:
        child_real = os.path.realpath(child)
        parent_real = os.path.realpath(parent)
        return os.path.commonpath([child_real, parent_real]) == parent_real
    except (ValueError, OSError):
        return False


def same_file(path_a: str, path_b: str) -> bool:
    try:
        return os.path.samefile(path_a, path_b)
    except OSError:
        return os.path.normcase(os.path.abspath(path_a)) == os.path.normcase(os.path.abspath(path_b))


def display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)
