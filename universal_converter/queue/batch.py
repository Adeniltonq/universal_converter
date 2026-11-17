"""Fila: carregamento em segundo plano e limites de segurança para lotes grandes.

O app nunca deve "engasgar" ao importar uma pasta com centenas ou milhares de
arquivos: a leitura do banco, a restauração do estado e a análise das metas
acontecem fora da thread da interface, em etapas pequenas.
"""

from __future__ import annotations

import os
import time
from typing import Iterable, Callable


def load_metadata_in_background(analyzer, jobs: Iterable, callback: Callable[[], None],
                                chunks: int = 40) -> None:
    """Analisa em lotes pequenos, sem travar a interface nem saturar o disco."""
    jobs = [job for job in jobs if not job.duration]
    if not jobs:
        callback()
        return

    def worker() -> None:
        for start in range(0, len(jobs), chunks):
            batch = jobs[start:start + chunks]
            analyzer.analyze_streams([job.file for job in batch],
                                     workers=min(4, len(batch)))
            time.sleep(0.05)
        callback()

    import threading
    threading.Thread(target=worker, daemon=True, name="queue-metadata").start()


def readable_size(count: int) -> str:
    return f"{count} arquivo(s)"


def ensure_folder(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except OSError:
        return False
