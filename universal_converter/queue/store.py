"""Persistência da fila em SQLite (permite retomar sessões interrompidas).

Somente os *metadados* das tarefas são guardados; a análise completa de cada
arquivo fica em um cache em memória com limite, para que milhares de arquivos
não ocupem gigabytes de RAM.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Iterable

from ..core.logger import get_logger
from ..core.util import app_data_dir
from ..media.models import ConversionJob, MediaInfo

log = get_logger("queue.store")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file TEXT NOT NULL,
    config TEXT NOT NULL,
    output_dir TEXT DEFAULT '',
    override_name TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    progress REAL DEFAULT 0,
    message TEXT DEFAULT '',
    output_path TEXT DEFAULT '',
    duration REAL,
    size INTEGER DEFAULT 0,
    created REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS media_cache (
    path TEXT PRIMARY KEY,
    stamp TEXT,
    data TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""


class JobStore:
    """Armazena tarefas no banco local do programa."""

    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(app_data_dir(), "queue.db")
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._connect()

    # ------------------------------------------------------------------
    def _connect(self) -> None:
        try:
            folder = os.path.dirname(self.path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            self._conn = sqlite3.connect(self.path, check_same_thread=False,
                                         timeout=15.0)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(SCHEMA)
            self._conn.commit()
        except sqlite3.Error as exc:
            log.error("Falha ao abrir o banco de fila (%s): %s", self.path, exc)
            self._conn = None

    @property
    def available(self) -> bool:
        return self._conn is not None

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.commit()
                    self._conn.close()
                except sqlite3.Error:
                    pass
                self._conn = None

    # ------------------------------------------------------------------
    def add_jobs(self, jobs: Iterable[ConversionJob]) -> list[int]:
        jobs = list(jobs)
        if not jobs:
            return []
        with self._lock:
            if self._conn is None:
                for job in jobs:
                    job.id = int(job.id or (time.time() * 1000) % 1_000_000_000)
                return [job.id for job in jobs]
            cursor = self._conn.cursor()
            ids = []
            for job in jobs:
                job.created = job.created or time.time()
                cursor.execute(
                    "INSERT INTO jobs (file, config, output_dir, override_name, status,"
                    " progress, message, output_path, duration, size, created)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (job.file, json.dumps(job.config.to_dict(), ensure_ascii=False),
                     job.output_dir, job.override_name, job.status, job.progress,
                     job.message, job.output_path, job.duration, job.size, job.created))
                job.id = int(cursor.lastrowid or 0)
                ids.append(job.id)
            self._conn.commit()
            return ids

    def update(self, job: ConversionJob, fields: Iterable[str] | None = None) -> None:
        data = {
            "file": job.file,
            "config": json.dumps(job.config.to_dict(), ensure_ascii=False),
            "output_dir": job.output_dir,
            "override_name": job.override_name,
            "status": job.status,
            "progress": job.progress,
            "message": job.message,
            "output_path": job.output_path,
            "duration": job.duration,
            "size": job.size,
        }
        if fields:
            data = {k: v for k, v in data.items() if k in set(fields)}
        if not data:
            return
        assignments = ", ".join(f"{key} = ?" for key in data)
        with self._lock:
            if self._conn is None:
                return
            try:
                self._conn.execute(f"UPDATE jobs SET {assignments} WHERE id = ?",
                                   (*data.values(), job.id))
                self._conn.commit()
            except sqlite3.Error as exc:
                log.warning("Falha ao atualizar tarefa %s: %s", job.id, exc)

    def delete(self, job_ids: Iterable[int]) -> None:
        ids = [(int(i),) for i in job_ids]
        if not ids:
            return
        with self._lock:
            if self._conn is None:
                return
            try:
                self._conn.executemany("DELETE FROM jobs WHERE id = ?", ids)
                self._conn.commit()
            except sqlite3.Error as exc:
                log.warning("Falha ao remover tarefas: %s", exc)

    def clear(self) -> None:
        with self._lock:
            if self._conn is None:
                return
            try:
                self._conn.execute("DELETE FROM jobs")
                self._conn.commit()
            except sqlite3.Error as exc:
                log.warning("Falha ao limpar fila: %s", exc)

    def load_jobs(self) -> list[ConversionJob]:
        with self._lock:
            if self._conn is None:
                return []
            try:
                rows = self._conn.execute(
                    "SELECT id, file, config, output_dir, override_name, status,"
                    " progress, message, output_path, duration, size, created"
                    " FROM jobs ORDER BY id").fetchall()
            except sqlite3.Error as exc:
                log.warning("Falha ao ler a fila: %s", exc)
                return []
        jobs = []
        for row in rows:
            try:
                config = json.loads(row[2]) if row[2] else {}
            except ValueError:
                config = {}
            job = ConversionJob.from_dict({
                "id": row[0], "file": row[1], "config": config, "output_dir": row[3],
                "override_name": row[4], "status": row[5], "progress": row[6],
                "message": row[7], "output_path": row[8], "duration": row[9],
                "size": row[10], "created": row[11],
            })
            jobs.append(job)
        return jobs

    def reset_running(self) -> None:
        """Tarefas que estavam rodando na sessão anterior voltam para a fila."""
        with self._lock:
            if self._conn is None:
                return
            try:
                self._conn.execute(
                    "UPDATE jobs SET status = 'pending', progress = 0,"
                    " message = 'Retomada após encerramento' WHERE status = 'running'")
                self._conn.commit()
            except sqlite3.Error:
                pass

    def known_files(self) -> set[str]:
        with self._lock:
            if self._conn is None:
                return set()
            try:
                rows = self._conn.execute("SELECT file FROM jobs").fetchall()
            except sqlite3.Error:
                return set()
        return {os.path.normcase(os.path.abspath(row[0])) for row in rows if row and row[0]}

    def count_by_status(self) -> dict[str, int]:
        with self._lock:
            if self._conn is None:
                return {}
            try:
                rows = self._conn.execute(
                    "SELECT status, COUNT(*) FROM jobs GROUP BY status").fetchall()
            except sqlite3.Error:
                return {}
        return {row[0]: row[1] for row in rows}

    # -- cache de análise -------------------------------------------------
    def save_media(self, info: MediaInfo) -> None:
        if not self.available or not info.analyzed:
            return
        stamp = _file_stamp(info.path)
        with self._lock:
            if self._conn is None:
                return
            try:
                self._conn.execute(
                    "INSERT OR REPLACE INTO media_cache (path, stamp, data) VALUES (?,?,?)",
                    (info.path, stamp, json.dumps(info.to_dict(), ensure_ascii=False)))
                self._conn.commit()
            except sqlite3.Error:
                pass

    def load_media(self, paths: Iterable[str]) -> dict[str, MediaInfo]:
        paths = list(paths)
        result: dict[str, MediaInfo] = {}
        if not paths or not self.available:
            return result
        with self._lock:
            if self._conn is None:
                return result
            try:
                for start in range(0, len(paths), 400):
                    chunk = paths[start:start + 400]
                    marks = ",".join("?" for _ in chunk)
                    rows = self._conn.execute(
                        f"SELECT path, stamp, data FROM media_cache WHERE path IN ({marks})",
                        chunk).fetchall()
                    for path, stamp, data in rows:
                        if stamp != _file_stamp(path):
                            continue
                        try:
                            payload = json.loads(data)
                        except ValueError:
                            continue
                        info = MediaInfo.from_dict(payload)
                        result[path] = info
            except sqlite3.Error:
                return result
        return result

    def prune_media_cache(self, keep_paths: set[str] | None = None) -> None:
        if not self.available:
            return
        with self._lock:
            if self._conn is None:
                return
            try:
                rows = self._conn.execute("SELECT path FROM media_cache").fetchall()
                stale = [row[0] for row in rows
                         if keep_paths is not None and row[0] not in keep_paths]
                if stale:
                    self._conn.executemany("DELETE FROM media_cache WHERE path = ?",
                                           [(p,) for p in stale])
                    self._conn.commit()
            except sqlite3.Error:
                pass


def _file_stamp(path: str) -> str:
    try:
        stat = os.stat(path)
        return f"{stat.st_size}:{int(stat.st_mtime)}"
    except OSError:
        return "missing"
