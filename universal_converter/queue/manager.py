"""Orquestrador da fila: análise, nomenclatura, execução e retomada.

É independente da interface: publica eventos em uma `queue.Queue` que a GUI
consome periodicamente (`poll()`). Também serve de base para uma futura CLI.
"""

from __future__ import annotations

import os
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable

from ..core.logger import get_logger
from ..core.util import is_subpath, same_file, sanitize_filename
from ..filesystem.output import OutputPolicy, OutputResolver
from ..media.analyzer import MediaAnalyzer
from ..media.catalog import CodecCatalog
from ..media.command_builder import CommandBuilder
from ..media.codecs import CONTAINERS
from ..media.ffmpeg import FFmpegInfo
from ..media.models import ConversionConfig, ConversionJob, MediaInfo
from ..media.runner import JobRunner
from ..media.models import NamingTemplate
from ..naming.engine import NamingContext, NamingEngine
from .scheduler import Scheduler, compute_plan, logical_cpus
from .store import JobStore

log = get_logger("queue")

def _suspend(proc) -> None:
    """Suspende o processo do FFmpeg (pausa real, sem perder trabalho)."""
    try:
        if os.name == "nt":
            import ctypes
            ntdll = ctypes.windll.ntdll
            handle = ctypes.windll.kernel32.OpenProcess(0x0800, False, proc.pid)
            if handle:
                ntdll.NtSuspendProcess(handle)
                ctypes.windll.kernel32.CloseHandle(handle)
        else:
            import signal
            os.kill(proc.pid, signal.SIGSTOP)
    except OSError:
        pass


def _resume(proc) -> None:
    """Retoma um processo suspenso por `_suspend`."""
    try:
        if os.name == "nt":
            import ctypes
            ntdll = ctypes.windll.ntdll
            handle = ctypes.windll.kernel32.OpenProcess(0x0800, False, proc.pid)
            if handle:
                ntdll.NtResumeProcess(handle)
                ctypes.windll.kernel32.CloseHandle(handle)
        else:
            import signal
            os.kill(proc.pid, signal.SIGCONT)
    except OSError:
        pass


STATUS_LABEL = {
    "pending": "Aguardando",
    "analyzing": "Analisando",
    "running": "Convertendo",
    "done": "Concluído",
    "error": "Erro",
    "cancelled": "Cancelado",
    "skipped": "Pulado",
}


@dataclass
class BatchSettings:
    threads: int = 0                 # 0 = todas as threads lógicas
    concurrent: int = 0              # 0 = automático
    per_job_threads: int = 0         # 0 = automático
    overwrite: bool = False
    preserve_structure: bool = True
    output_mode: str = "folder"      # folder | beside
    output_dir: str = ""
    source_root: str = ""
    naming: NamingTemplate = field(default_factory=lambda: NamingTemplate())
    tag: str = ""
    hw_accel: str = "auto"


@dataclass
class BatchStats:
    total: int = 0
    done: int = 0
    errors: int = 0
    cancelled: int = 0
    skipped: int = 0
    started: float = 0.0
    finished: float = 0.0
    bytes_written: int = 0

    def to_dict(self) -> dict:
        elapsed = (self.finished or time.time()) - self.started if self.started else 0
        return {
            "total": self.total, "done": self.done, "errors": self.errors,
            "cancelled": self.cancelled, "skipped": self.skipped,
            "elapsed": elapsed, "bytes": self.bytes_written,
        }


class QueueManager:
    """Coordena a fila completa."""

    def __init__(self, ff: FFmpegInfo, store: JobStore,
                 catalog: CodecCatalog | None = None,
                 analyzer: MediaAnalyzer | None = None):
        self.ff = ff
        self.store = store
        self.catalog = catalog or CodecCatalog(ff)
        self.analyzer = analyzer or MediaAnalyzer(ff)
        self.events: "queue.Queue[tuple]" = queue.Queue()
        self.jobs: list[ConversionJob] = []
        self.settings = BatchSettings()
        self.stats = BatchStats()
        self._lock = threading.RLock()
        self._jobs_by_id: dict[int, ConversionJob] = {}
        self._cancel_events: dict[int, threading.Event] = {}
        self._analysis_cancel = threading.Event()
        self._scheduler = Scheduler(logical_cpus())
        self._running = False
        self._paused = False
        self._stop_requested = False
        self._planned_total = 0
        self._completed = 0
        self._active_weights = 0
        self._next_temp_id = 1
        self._reserved_outputs: dict[str, int] = {}
        self._naming = NamingEngine()

    # ------------------------------------------------------------------
    # Carregamento e persistência
    # ------------------------------------------------------------------
    def load(self) -> None:
        self.store.reset_running()
        jobs = self.store.load_jobs()
        with self._lock:
            self.jobs = jobs
            self._jobs_by_id = {job.id: job for job in jobs}
            self._next_temp_id = (max((j.id for j in jobs), default=0) + 1)
        for job in jobs:
            if os.path.isfile(job.file):
                self._reserved_outputs[os.path.normcase(job.file)] = job.id
        self._emit("queue_reloaded", jobs=len(jobs))

    def job(self, job_id: int) -> ConversionJob | None:
        return self._jobs_by_id.get(job_id)

    def job_ids(self) -> list[int]:
        with self._lock:
            return [job.id for job in self.jobs]

    def snapshot(self) -> list[ConversionJob]:
        with self._lock:
            return list(self.jobs)

    # ------------------------------------------------------------------
    # Manipulação da fila
    # ------------------------------------------------------------------
    def add_files(self, files: Iterable[str], config: ConversionConfig | None = None,
                  output_dirs: dict[str, str] | None = None) -> list[ConversionJob]:
        new_jobs: list[ConversionJob] = []
        with self._lock:
            known = self.store.known_files()
        seen = set(known)
        for path in files:
            path = os.path.abspath(path)
            key = os.path.normcase(path)
            if key in seen:
                continue
            seen.add(key)
            job = ConversionJob(
                id=self._allocate_temp_id(),
                file=path,
                config=ConversionConfig.from_dict((config or ConversionConfig()).to_dict()),
                output_dir=(output_dirs or {}).get(path, ""),
                status="pending",
                created=time.time(),
            )
            try:
                job.size = os.path.getsize(path)
            except OSError:
                job.size = 0
            new_jobs.append(job)
        if not new_jobs:
            return []
        self.store.add_jobs(new_jobs)
        with self._lock:
            self.jobs.extend(new_jobs)
            for job in new_jobs:
                self._jobs_by_id[job.id] = job
                self._reserved_outputs[os.path.normcase(job.file)] = job.id
        self._emit("jobs_added", jobs=new_jobs)
        return new_jobs

    def _allocate_temp_id(self) -> int:
        value = self._next_temp_id
        self._next_temp_id += 1
        return value

    def remove_jobs(self, job_ids: Iterable[int]) -> None:
        ids = set(job_ids)
        with self._lock:
            for job_id in ids:
                event = self._cancel_events.get(job_id)
                if event:
                    event.set()
            self.jobs = [job for job in self.jobs if job.id not in ids]
            for job_id in ids:
                job = self._jobs_by_id.pop(job_id, None)
                if job:
                    self._reserved_outputs.pop(os.path.normcase(job.file), None)
                self._cancel_events.pop(job_id, None)
        self.store.delete(ids)
        self._emit("jobs_removed", ids=list(ids))

    def clear(self) -> None:
        with self._lock:
            for event in self._cancel_events.values():
                event.set()
            self.jobs.clear()
            self._jobs_by_id.clear()
            self._reserved_outputs.clear()
            self._cancel_events.clear()
        self.store.clear()
        self._analysis_cancel.set()
        self._emit("queue_cleared")

    def clear_finished(self) -> None:
        ids = [job.id for job in self.snapshot() if job.status in ("done", "error",
                                                                 "cancelled", "skipped")]
        if ids:
            self.remove_jobs(ids)

    def reorder(self, job_ids: list[int]) -> None:
        with self._lock:
            order = {job_id: index for index, job_id in enumerate(job_ids)}
            self.jobs.sort(key=lambda job: order.get(job.id, len(order)))

    def move(self, job_id: int, offset: int) -> None:
        with self._lock:
            ids = [job.id for job in self.jobs]
            if job_id not in ids:
                return
            index = ids.index(job_id)
            new_index = max(0, min(len(ids) - 1, index + offset))
            ids.insert(new_index, ids.pop(index))
        self.reorder(ids)

    def reset_jobs(self, job_ids: Iterable[int]) -> None:
        with self._lock:
            reset = 0
            for job_id in job_ids:
                job = self._jobs_by_id.get(job_id)
                if job and job.status in ("done", "error", "cancelled", "skipped"):
                    job.status = "pending"
                    job.progress = 0.0
                    job.message = ""
                    job.output_path = ""
                    reset += 1
                    self.store.update(job, fields=["status", "progress", "message",
                                                   "output_path"])
        self._emit("jobs_reset", ids=list(job_ids), count=reset)

    def retry_errors(self) -> None:
        ids = [job.id for job in self.snapshot() if job.status in ("error", "cancelled")]
        if ids:
            self.reset_jobs(ids)

    def set_job_config(self, job_ids: Iterable[int], config: ConversionConfig) -> None:
        with self._lock:
            for job_id in job_ids:
                job = self._jobs_by_id.get(job_id)
                if job:
                    job.config = ConversionConfig.from_dict(config.to_dict())
                    self.store.update(job, fields=["config"])
        self._emit("jobs_config_changed", ids=list(job_ids))

    def set_job_output_dir(self, job_ids: Iterable[int], output_dir: str) -> None:
        with self._lock:
            for job_id in job_ids:
                job = self._jobs_by_id.get(job_id)
                if job:
                    job.output_dir = output_dir
                    self.store.update(job, fields=["output_dir"])
        self._emit("jobs_config_changed", ids=list(job_ids))

    def set_job_override_name(self, job_id: int, name: str) -> None:
        with self._lock:
            job = self._jobs_by_id.get(job_id)
            if job:
                job.override_name = name
                self.store.update(job, fields=["override_name"])
        self._emit("jobs_config_changed", ids=[job_id])

    # ------------------------------------------------------------------
    # Análise
    # ------------------------------------------------------------------
    def analyze_jobs(self, job_ids: Iterable[int] | None = None,
                     workers: int = 4) -> None:
        with self._lock:
            ids = list(job_ids) if job_ids is not None else [j.id for j in self.jobs]
            jobs = [self._jobs_by_id[i] for i in ids if i in self._jobs_by_id]
        pending = [job for job in jobs if not self.analyzer.analyze(job.file).analyzed]
        self._analysis_cancel = threading.Event()

        def worker() -> None:
            cancelled = self._analysis_cancel
            for done, job in enumerate(pending, start=1):
                if cancelled.is_set():
                    return
                info = self.analyzer.analyze(job.file)
                with self._lock:
                    job.duration = info.duration
                    if info.size:
                        job.size = info.size
                    self.store.update(job, fields=["duration", "size"])
                self._emit("job_analyzed", job=job, info=info)
                if done % 25 == 0 or done == len(pending):
                    self._emit("analysis_progress", done=done, total=len(pending))
            self._emit("analysis_done", total=len(pending))

        threading.Thread(target=worker, daemon=True, name="analyze-jobs").start()

    def info_for(self, job: ConversionJob) -> MediaInfo:
        return self.analyzer.analyze(job.file)

    def load_cached_infos(self, job_ids: Iterable[int] | None = None) -> int:
        """Preenche duração/tamanho a partir do cache, sem ler arquivos."""
        with self._lock:
            ids = list(job_ids) if job_ids is not None else [j.id for j in self.jobs]
            jobs = [self._jobs_by_id[i] for i in ids if i in self._jobs_by_id]
        cached = self.store.load_media(job.file for job in jobs)
        count = 0
        for job in jobs:
            info = cached.get(job.file)
            if info and info.analyzed:
                job.duration = info.duration
                job.size = info.size or job.size
                self.analyzer._cache[self.analyzer._cache_key(job.file)] = info
                count += 1
        return count

    # ------------------------------------------------------------------
    # Pré-visualização de nomes
    # ------------------------------------------------------------------
    def plan_paths(self, jobs: Iterable[ConversionJob] | None = None,
                   limit: int | None = None,
                   infos: dict[int, MediaInfo] | None = None
                   ) -> list[tuple[ConversionJob, str, str]]:
        """Calcula (job, caminho_final, aviso).

        `infos` permite reaproveitar análises já feitas (ex.: pré-visualização na
        interface); caso contrário usa o cache limitado do analisador.
        """
        with self._lock:
            jobs = list(jobs) if jobs is not None else list(self.jobs)
        settings = self.settings
        if jobs and not settings.output_dir and not settings.source_root and \
                settings.output_mode == "folder":
            latest = ConversionJob.from_dict(max(jobs, key=lambda j: j.created).to_dict())
            settings = self._settings_from_jobs(jobs, latest)
        resolver = OutputResolver(OutputPolicy(
            mode=settings.output_mode, folder=settings.output_dir,
            source_root=settings.source_root,
            preserve_structure=settings.preserve_structure,
            overwrite=settings.overwrite))
        builder = CommandBuilder(self.catalog)
        naming = NamingEngine(settings.naming)
        taken: set[str] = set()
        results: list[tuple[ConversionJob, str, str]] = []
        for index, job in enumerate(jobs, start=1):
            if limit and len(results) >= limit:
                break
            info = (infos or {}).get(job.id) or self.analyzer.analyze(job.file)
            warning = ""
            if not info.analyzed:
                warning = info.error or "Não foi possível analisar o arquivo."
            container_key = builder.effective_container(job.config, info)
            extension = builder.output_extension(container_key, job.config.kind)
            if job.config.container == "copy" and job.config.kind == "audio":
                config = ConversionConfig.from_dict(job.config.to_dict())
                config.audio.codec = "copy"
                extension = builder.output_extension(container_key, "audio")
            else:
                config = job.config
            context = NamingContext(
                path=job.file, info=info, config=config, index=index,
                tag=settings.tag, extension=extension)
            if job.override_name:
                name = job.override_name
                if extension and not name.lower().endswith("." + extension.lower()):
                    name = f"{name}.{extension}"
                relative = sanitize_filename(name)
            else:
                relative = naming.render(context, settings.naming)
            folder = resolver.final_folder(job.file, job.output_dir)
            final_path = os.path.join(folder, relative)
            if same_file(job.file, final_path):
                final_path = os.path.join(
                    folder, os.path.splitext(relative)[0] + f" ({extension})"
                    f"{os.path.splitext(relative)[1]}")
                warning = warning or "O destino substituiria o original; renomeado."
            key = os.path.normcase(os.path.normpath(final_path))
            if key in taken:
                base, ext = os.path.splitext(relative)
                counter = 2
                while key in taken:
                    candidate = f"{base} ({counter}){ext}"
                    key = os.path.normcase(os.path.normpath(os.path.join(folder,
                                                                         candidate)))
                    counter += 1
                final_path = os.path.join(folder, f"{base} ({counter - 1}){ext}")
                warning = warning or "Nome duplicado na fila; numerado automaticamente."
            taken.add(key)
            results.append((job, final_path, warning))
        return results

    @staticmethod
    def _settings_from_jobs(jobs: list[ConversionJob],
                            latest: ConversionJob) -> BatchSettings:
        """Configurações coerentes para pré-visualizar arquivos com configs distintas.

        Usa o modelo de nomes e o destino da tarefa mais recente; cada tarefa
        mantém sua própria configuração de conversão.
        """
        return BatchSettings(
            output_mode="beside" if not (latest.output_dir) else "folder",
            output_dir=latest.output_dir,
            source_root=os.path.dirname(os.path.dirname(latest.file)),
            preserve_structure=True,
            overwrite=False)

    # ------------------------------------------------------------------
    # Execução em lote
    # ------------------------------------------------------------------
    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return self._paused

    def start(self, jobs: Iterable[ConversionJob] | None = None,
              settings: BatchSettings | None = None) -> bool:
        if self._running:
            return False
        self.ff.ensure_loaded()
        if self.ff.error:
            self._emit("error", message=self.ff.error)
            return False
        if settings:
            self.settings = settings
        with self._lock:
            if jobs is not None:
                targets = list(jobs)
            else:
                targets = [job for job in self.jobs if job.status == "pending"]
            if not targets:
                message = ("Nenhuma tarefa pendente para converter." if not
                           any(job.status == "done" for job in self.jobs) else
                           "Os arquivos já foram convertidos. Use \"Repetir / "
                           "recolocar na fila\" para converter novamente.")
                self._emit("error", message=message)
                return False
            for job in targets:
                job.status = "pending"
                job.progress = 0.0
                job.message = ""
            self._running = True
            self._paused = False
            self._stop_requested = False
            self._planned_total = len(targets)
            self._completed = 0
            self._active_weights = 0
            self.stats = BatchStats(total=len(targets), started=time.time())
        concurrent, per_job = compute_plan(
            self.settings.threads, self.settings.concurrent,
            self.settings.per_job_threads, len(targets))
        self._scheduler = Scheduler(concurrent)
        self._scheduler.start(concurrent)
        self._emit("batch_started", total=len(targets), concurrent=concurrent,
                   per_job=per_job)

        planned = self.plan_paths(targets)
        for job, final_path, warning in planned:
            self._submit_job(job, final_path)
        if not planned:
            self._finish_batch()
        return True

    def _submit_job(self, job: ConversionJob, final_path: str) -> None:
        cancel_event = threading.Event()
        with self._lock:
            self._cancel_events[job.id] = cancel_event
            weight = 4 if (job.config.kind == "video" and
                           job.config.video.codec not in ("copy", "none")) else 1
            self._active_weights += weight
            active = self._active_weights
        total_threads = max(1, int(self.settings.threads or logical_cpus()))
        threads = max(1, min(total_threads, round(total_threads * weight / max(weight,
                                                                              active))))
        self._scheduler.submit(self._run_job, job, final_path, cancel_event, threads,
                               weight)

    def _run_job(self, job: ConversionJob, planned_path: str,
                 cancel_event: threading.Event, threads: int, weight: int) -> None:
        proc_holder: dict = {}
        gate = threading.Event()

        def gate_worker() -> None:
            while not gate.is_set():
                if self._paused and not cancel_event.is_set() and not self._stop_requested:
                    holder = proc_holder.get("proc")
                    if holder is not None and holder.poll() is None:
                        # pausa real: suspende o processo do FFmpeg
                        _suspend(holder)
                        resumed = False
                        while self._paused and not cancel_event.is_set() and \
                                not self._stop_requested:
                            time.sleep(0.1)
                        _resume(holder)
                    while self._paused and not cancel_event.is_set() and \
                            not self._stop_requested:
                        time.sleep(0.1)
                time.sleep(0.1)

        gate_thread = threading.Thread(target=gate_worker, daemon=True,
                                       name=f"gate-{job.id}")
        gate_thread.start()
        try:
            while self._paused and not cancel_event.is_set() and not self._stop_requested:
                time.sleep(0.2)
            if cancel_event.is_set() or self._stop_requested:
                self._mark(job, "cancelled", "Cancelado antes de iniciar")
                return
            self._set_status(job, "running", "Preparando…")
            info = self.analyzer.analyze(job.file, use_cache=True)
            with self._lock:
                job.duration = info.duration
                self.store.update(job, fields=["duration"])
            if not info.analyzed:
                self._mark(job, "error", info.error or "Arquivo inválido")
                return
            final_path = self._unique_destination(planned_path, job, info)
            builder = CommandBuilder(self.catalog, threads_per_job=threads)
            build = builder.build(job.config, info, job.file, final_path)
            if not build.ok:
                self._mark(job, "error", build.error)
                return
            for warning in build.warnings:
                self._emit("job_warning", job=job, message=warning)
            if build.container != job.config.container:
                job.config.container = build.container
                self.store.update(job, fields=["config"])
            duration = info.duration or 0.0
            runner = JobRunner(self.ff.ffmpeg)
            self._emit("job_output", job=job, path=final_path)

            def on_progress(progress: float, speed: float) -> None:
                job.progress = progress
                self._emit("job_progress", job=job, progress=progress, speed=speed)

            outcome = runner.run(build.args, final_path, duration,
                                 on_progress=on_progress, cancel_event=cancel_event,
                                 overwrite=self.settings.overwrite,
                                 process_holder=proc_holder)
            if outcome.cancelled:
                self._mark(job, "cancelled", "Cancelado")
            elif outcome.success:
                try:
                    written = os.path.getsize(outcome.output_path)
                except OSError:
                    written = 0
                with self._lock:
                    self.stats.bytes_written += written
                self._mark(job, "done", f"Concluído ({max(outcome.speed, 0):.2f}×)",
                           output_path=outcome.output_path)
            else:
                self._mark(job, "error", outcome.message)
        except Exception as exc:  # noqa: BLE001 - nunca derrubar a thread
            log.exception("Erro inesperado na tarefa %s", job.file)
            self._mark(job, "error", f"Erro inesperado: {exc}")
        finally:
            gate.set()
            with self._lock:
                self._active_weights = max(0, self._active_weights - weight)
                self._cancel_events.pop(job.id, None)
                self._completed += 1
                finished = self._completed >= self._planned_total
            self._emit("job_finished", job=job)
            if finished:
                self._finish_batch()

    def _unique_destination(self, planned_path: str, job: ConversionJob,
                            info: MediaInfo) -> str:
        """Adapta a extensão caso o contêiner efetivo tenha mudado."""
        builder = CommandBuilder(self.catalog)
        container_key = builder.effective_container(job.config, info)
        extension = builder.output_extension(container_key, job.config.kind)
        root, ext = os.path.splitext(planned_path)
        if ext.lstrip(".").lower() != extension.lower():
            planned_path = f"{root}.{extension}"
        if same_file(job.file, planned_path):
            planned_path = f"{root} (convertido).{extension}"
        return planned_path

    def _mark(self, job: ConversionJob, status: str, message: str,
              output_path: str = "") -> None:
        with self._lock:
            job.status = status
            job.message = message
            if output_path:
                job.output_path = output_path
            if status == "done":
                job.progress = 1.0
                self.stats.done += 1
            elif status == "error":
                self.stats.errors += 1
                log.warning("Erro em %s: %s", job.file, message)
            elif status == "cancelled":
                self.stats.cancelled += 1
            self.store.update(job, fields=["status", "progress", "message",
                                           "output_path"])
        self._emit("job_status", job=job, status=status, message=message)

    def _set_status(self, job: ConversionJob, status: str, message: str) -> None:
        with self._lock:
            job.status = status
            job.message = message
        self._emit("job_status", job=job, status=status, message=message)

    def _finish_batch(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._paused = False
            self.stats.finished = time.time()
        self._scheduler.stop(wait=False)
        self._emit("batch_finished", stats=self.stats.to_dict())

    # ------------------------------------------------------------------
    def pause(self) -> None:
        self._paused = True
        self._emit("batch_paused")

    def resume(self) -> None:
        self._paused = False
        self._emit("batch_resumed")

    def toggle_pause(self) -> bool:
        if self._paused:
            self.resume()
            return False
        self.pause()
        return True

    def cancel_job(self, job_id: int) -> None:
        with self._lock:
            job = self._jobs_by_id.get(job_id)
            event = self._cancel_events.get(job_id)
            if event:
                event.set()
            if job and job.status == "pending":
                job.status = "cancelled"
                job.message = "Cancelado"
                self.store.update(job, fields=["status", "message"])
        self._emit("job_status", job=job, status="cancelled", message="Cancelado")

    def cancel_all(self) -> None:
        self._stop_requested = True
        with self._lock:
            events = list(self._cancel_events.values())
            pending = [job for job in self.jobs if job.status == "pending"]
        for event in events:
            event.set()
        for job in pending:
            self.cancel_job(job.id)
        self._emit("batch_cancelling")

    def wait_idle(self, timeout: float | None = None) -> bool:
        start = time.time()
        while self._running:
            if timeout is not None and time.time() - start > timeout:
                return False
            time.sleep(0.1)
        return True

    # ------------------------------------------------------------------
    # Eventos
    # ------------------------------------------------------------------
    def _emit(self, kind: str, **payload) -> None:
        payload["type"] = kind
        payload["time"] = time.time()
        self.events.put(payload)

    def poll(self, limit: int = 400) -> list[dict]:
        items = []
        for _ in range(limit):
            try:
                items.append(self.events.get_nowait())
            except queue.Empty:
                break
        return items

    # -- destino -------------------------------------------------------
    def output_folder_for(self, job: ConversionJob) -> str:
        resolver = OutputResolver(OutputPolicy(
            mode=self.settings.output_mode, folder=self.settings.output_dir,
            source_root=self.settings.source_root,
            preserve_structure=self.settings.preserve_structure))
        return resolver.final_folder(job.file, job.output_dir)
