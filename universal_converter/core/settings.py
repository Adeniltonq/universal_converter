"""Configurações persistentes em JSON."""

from __future__ import annotations

import json
import os
import threading
from typing import Any

from ..core.util import app_data_dir

DEFAULTS: dict[str, Any] = {
    "ffmpeg_path": "",            # pasta ou executável; vazio = detecção automática
    "output_mode": "folder",      # "folder" | "beside"
    "output_dir": "",
    "overwrite": False,
    "preserve_structure": True,
    "threads": 0,                 # 0 = automático (todas as threads lógicas)
    "concurrent": 0,              # 0 = automático
    "per_job_threads": 0,         # 0 = automático
    "hw_accel": "auto",
    "notify_on_finish": True,
    "naming": {
        "template": "{name}",
        "separator": "_",
        "prefix": "",
        "suffix": "",
        "replacement_from": "",
        "replacement_to": "",
        "case": "keep",           # keep | lower | upper | title
        "sanitize": True,
        "numbering": False,
        "number_start": 1,
        "number_padding": 2,
        "number_position": "prefix",  # prefix | suffix
    },
    "audio": {},
    "video": {},
    "profiles": [],
    "last_profile": "",
    "active_tab": "files",
}

_LOCK = threading.Lock()


class Settings:
    """Leitura/gravação das configurações do usuário."""

    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(app_data_dir(), "settings.json")
        self._data = json.loads(json.dumps(DEFAULTS))
        self.load()

    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as fh:
                stored = json.load(fh)
            if isinstance(stored, dict):
                self._merge(self._data, stored)
        except (OSError, ValueError):
            pass

    @staticmethod
    def _merge(base: dict, extra: dict) -> None:
        for key, value in extra.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                Settings._merge(base[key], value)
            else:
                base[key] = value

    def save(self) -> None:
        with _LOCK:
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                tmp = self.path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(self._data, fh, ensure_ascii=False, indent=2)
                os.replace(tmp, self.path)
            except OSError:
                pass

    # acesso por chave ---------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value
