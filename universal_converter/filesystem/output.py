"""Gerenciador de saída: destino, preservação de estrutura e colisões."""

from __future__ import annotations

import os
from dataclasses import dataclass

from ..core.util import is_subpath, sanitize_dir_name
from .scanner import relative_to


@dataclass
class OutputPolicy:
    mode: str = "folder"           # folder | beside
    folder: str = ""               # aplica-se a mode="folder"
    source_root: str = ""          # raiz da varredura (para estrutura relativa)
    preserve_structure: bool = True
    overwrite: bool = False


class OutputResolver:
    """Calcula a pasta onde o arquivo convertido será escrito."""

    def __init__(self, policy: OutputPolicy):
        self.policy = policy
        self.warnings: list[str] = []

    def folder_for(self, source_file: str, job_output_dir: str = "") -> tuple[str, str]:
        """Retorna (pasta_base, subpasta_relativa) para o arquivo de origem."""
        policy = self.policy
        if policy.mode == "beside" and not job_output_dir:
            return os.path.dirname(os.path.abspath(source_file)), ""
        base = job_output_dir or policy.folder
        if not base:
            return os.path.dirname(os.path.abspath(source_file)), ""
        base = os.path.abspath(os.path.expanduser(base))
        relative = ""
        root = policy.source_root
        if policy.preserve_structure and root and is_subpath(source_file, root):
            parent_rel = os.path.dirname(relative_to(source_file, root))
            if parent_rel and parent_rel != ".":
                relative = parent_rel
        return base, relative

    def final_folder(self, source_file: str, job_output_dir: str = "") -> str:
        base, relative = self.folder_for(source_file, job_output_dir)
        if relative:
            parts = [sanitize_dir_name(p) for p in relative.replace("\\", "/").split("/")
                     if p and p != "."]
            base = os.path.join(base, *parts)
        return base

    def check_conflicts(self) -> list[str]:
        problems = []
        policy = self.policy
        if policy.mode == "folder" and policy.folder and policy.source_root:
            if is_subpath(policy.folder, policy.source_root):
                problems.append(
                    "A pasta de destino está dentro da pasta de origem. Ela será "
                    "ignorada na varredura para não reprocessar a saída.")
        return problems


def is_same_source(source: str, destination: str) -> bool:
    """Evita que a conversão sobrescreva o próprio arquivo original."""
    try:
        return os.path.normcase(os.path.realpath(source)) == \
            os.path.normcase(os.path.realpath(destination))
    except OSError:
        return False


def path_exists(path: str) -> bool:
    try:
        return os.path.exists(path)
    except OSError:
        return False
