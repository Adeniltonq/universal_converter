"""Escalonador: distribui tarefas entre threads respeitando o orçamento de CPU.

Dois níveis de paralelismo são considerados juntos:

* **entre arquivos** — quantas conversões simultâneas;
* **dentro de cada arquivo** — quantas threads o encoder recebe.

O usuário informa um limite global (`threads`). O escalonador calcula quantas
tarefas simultâneas cabem (`concurrent × per_job ≤ threads`) e realoca
threads entre tarefas (rebalanceamento) para não deixar CPU ociosa quando
algumas tarefas são leves (cópia de streams) e outras pesadas.
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor


def logical_cpus() -> int:
    try:
        return max(1, os.cpu_count() or 1)
    except NotImplementedError:
        return 1


def default_plan(threads: int, count: int) -> tuple[int, int]:
    threads = max(1, int(threads or logical_cpus()))
    if count <= 1:
        return 1, threads
    per_job = threads // min(count, threads)
    per_job = max(1, per_job)
    concurrent = max(1, threads // per_job)
    return concurrent, per_job


def compute_plan(threads: int, concurrent: int, per_job: int, count: int) -> tuple[int, int]:
    """Resolve valores "automáticos" (0) e aplica limites coerentes."""
    threads = max(1, int(threads or logical_cpus()))
    count = max(1, int(count or 1))
    auto_concurrent, auto_per_job = default_plan(threads, count)
    concurrent = int(concurrent or auto_concurrent)
    per_job = int(per_job or auto_per_job)
    per_job = max(1, min(per_job, threads))
    concurrent = max(1, min(concurrent, count, threads // per_job or 1))
    return concurrent, per_job


class Scheduler:
    """Dispara trabalhos em paralelo com orçamento de threads negociado."""

    def __init__(self, max_workers: int):
        self._lock = threading.Lock()
        self._executor: ThreadPoolExecutor | None = None
        self.max_workers = max(1, int(max_workers))
        self.active = 0
        self.pending = 0
        self._budget_owner: dict[str, int] = {}

    # ------------------------------------------------------------------
    def start(self, max_workers: int) -> None:
        with self._lock:
            if self._executor is not None:
                return
            self.max_workers = max(1, int(max_workers))
            self._executor = ThreadPoolExecutor(
                max_workers=self.max_workers, thread_name_prefix="convert")

    def stop(self, wait: bool = True) -> None:
        with self._lock:
            executor = self._executor
            self._executor = None
        if executor is not None:
            executor.shutdown(wait=wait, cancel_futures=not wait)

    @property
    def running_tasks(self) -> int:
        with self._lock:
            return self.active

    # ------------------------------------------------------------------
    def submit(self, fn, *args, **kwargs):
        with self._lock:
            executor = self._executor
            if executor is None:
                raise RuntimeError("Escalonador não iniciado")
            self.pending += 1
        future = executor.submit(self._wrap, fn, *args, **kwargs)
        return future

    def _wrap(self, fn, *args, **kwargs):
        with self._lock:
            self.pending = max(0, self.pending - 1)
            self.active += 1
        try:
            return fn(*args, **kwargs)
        finally:
            with self._lock:
                self.active = max(0, self.active - 1)

    # ------------------------------------------------------------------
    # Orçamento de threads entre tarefas
    # ------------------------------------------------------------------
    def acquire_threads(self, owner: str, weight: int = 1, total: int | None = None,
                        active_weight: int = 0) -> int:
        """Calcula quantas threads uma tarefa pode usar neste instante."""
        total = max(1, int(total or logical_cpus()))
        weight = max(1, int(weight))
        active_weight = max(weight, int(active_weight or weight))
        budget = int(round(total * weight / active_weight))
        return max(1, min(total, budget))

    @staticmethod
    def job_weight(is_copy_video: bool, has_video: bool) -> int:
        if is_copy_video:
            return 1
        return 4 if has_video else 1
