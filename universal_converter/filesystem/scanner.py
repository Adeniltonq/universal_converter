"""Varredura de pastas com filtros, exclusões e proteção contra reprocessamento."""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field
from typing import Callable, Iterator

from ..core.logger import get_logger
from ..core.util import is_subpath
from ..media.codecs import INPUT_EXT

log = get_logger("scanner")


@dataclass
class ScanOptions:
    recursive: bool = True
    extensions: set[str] = field(default_factory=lambda: set(INPUT_EXT))
    include_hidden: bool = False
    exclude_patterns: list[str] = field(default_factory=list)
    exclude_dirs: list[str] = field(default_factory=list)
    output_dir: str = ""            # pasta de destino, para não reprocessar a saída
    max_files: int = 0              # 0 = sem limite


@dataclass
class ScanResult:
    files: list[str] = field(default_factory=list)
    skipped_output: int = 0
    skipped_excluded: int = 0
    skipped_extension: int = 0
    truncated: bool = False
    errors: list[str] = field(default_factory=list)


def normalized_extension(path: str) -> str:
    return os.path.splitext(path)[1].lstrip(".").lower()


def matches_exclusion(path: str, patterns: list[str]) -> bool:
    name = os.path.basename(path)
    for pattern in patterns:
        pattern = pattern.strip()
        if not pattern:
            continue
        if fnmatch.fnmatchcase(name, pattern) or fnmatch.fnmatchcase(path, pattern):
            return True
    return False


def scan_folder(folder: str, options: ScanOptions,
                progress: Callable[[int], None] | None = None,
                should_stop: Callable[[], bool] | None = None) -> ScanResult:
    """Percorre `folder` (recursivo opcional) e devolve os arquivos de mídia."""
    result = ScanResult()
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        result.errors.append(f"Pasta inexistente: {folder}")
        return result

    excluded_dirs = {folder.lower()}
    for name in options.exclude_dirs:
        if name:
            excluded_dirs.add(name.lower())
    output_dir = options.output_dir

    stack = [folder]
    while stack:
        if should_stop and should_stop():
            result.truncated = True
            return result
        current = stack.pop()
        if output_dir and is_subpath(current, output_dir) and \
                os.path.normcase(current) != os.path.normcase(output_dir):
            result.skipped_output += 1
            continue
        try:
            entries = list(os.scandir(current))
        except OSError as exc:
            result.errors.append(f"{current}: {exc}")
            continue
        for entry in sorted(entries, key=lambda e: e.name.lower()):
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if entry.name.startswith(".") and not options.include_hidden:
                continue
            if is_dir:
                if entry.name.lower() in excluded_dirs:
                    continue
                if matches_exclusion(entry.path, options.exclude_patterns):
                    result.skipped_excluded += 1
                    continue
                if output_dir and os.path.normcase(os.path.realpath(entry.path)) == \
                        os.path.normcase(os.path.realpath(output_dir)):
                    result.skipped_output += 1
                    continue
                if options.recursive:
                    stack.append(entry.path)
                continue
            ext = normalized_extension(entry.name)
            if ext not in options.extensions:
                result.skipped_extension += 1
                continue
            if matches_exclusion(entry.path, options.exclude_patterns):
                result.skipped_excluded += 1
                continue
            result.files.append(entry.path)
            if progress:
                progress(len(result.files))
            if options.max_files and len(result.files) >= options.max_files:
                result.truncated = True
                return result
    return result


def relative_to(path: str, root: str) -> str:
    """Caminho relativo seguro (sem sair de `root`)."""
    try:
        rel = os.path.relpath(os.path.abspath(path), os.path.abspath(root))
    except ValueError:
        return os.path.basename(path)
    if rel.startswith(".."):
        return os.path.basename(path)
    return rel


def iter_files(folder: str, options: ScanOptions) -> Iterator[str]:
    for path in scan_folder(folder, options).files:
        yield path
