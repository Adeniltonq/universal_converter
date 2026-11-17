"""Controlador da aplicação: liga o núcleo à interface Tk.

Mantém a configuração atual (áudio/vídeo/nomenclatura), constrói as tarefas a
partir da fila do núcleo e traduz eventos para a GUI via `UiBus`.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Iterable

from ..core.settings import Settings
from ..media.analyzer import QUICK_ANALYSIS_LIMIT, MediaAnalyzer
from ..media.catalog import CodecCatalog
from ..media.command_builder import CommandBuilder
from ..media.ffmpeg import FFmpegInfo
from ..media.models import (
    AudioSettings, ConversionConfig, ConversionJob, MediaInfo, NamingTemplate, VideoSettings,
)
from ..profiles.store import Profile, ProfileStore
from ..queue.manager import BatchSettings, QueueManager
from ..queue.store import JobStore
from ..queue.scheduler import compute_plan, logical_cpus
from .bus import UiBus

log = logging.getLogger("umc.app")


class AppController:
    """Estado compartilhado pela interface."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.bus = UiBus()
        self.ff = FFmpegInfo.locate(settings.get("ffmpeg_path") or None)
        self.ff.ensure_loaded()
        self.catalog = CodecCatalog(self.ff)
        self.analyzer = MediaAnalyzer(self.ff)
        self.store = JobStore()
        self.profiles = ProfileStore()
        self.queue = QueueManager(self.ff, self.store, self.catalog, self.analyzer)

        # configuração atual (compartilhada entre as abas)
        self.kind = "audio"
        self.container = "mp3"
        self.audio = AudioSettings()
        self.video = VideoSettings(codec="copy")
        self.naming = NamingTemplate.from_dict(settings.get("naming"))
        self.tag = ""
        self.current_profile = settings.get("last_profile", "")
        self._plan_lock = threading.Lock()
        self._plan_cache: tuple[float, list] = (0.0, [])
        self._plan_generating = False
        self.last_warnings: list[str] = []
        self._apply_initial_settings()
        self._reload_plan_async()

    # ------------------------------------------------------------------
    def _apply_initial_settings(self) -> None:
        audio = self.settings.get("audio") or {}
        video = self.settings.get("video") or {}
        if audio:
            self.audio = AudioSettings.from_dict(audio)
        if video:
            self.video = VideoSettings.from_dict(video)
        self.kind = self.settings.get("kind") or "audio"
        self.container = self.settings.get("container") or \
            ("mp3" if self.kind == "audio" else "mp4")
        profile_id = self.current_profile
        if profile_id:
            profile = self.profiles.find(profile_id)
            if profile:
                self._load_profile_values(profile)
        self.tag = self.settings.get("tag", "") or ""

    def _load_profile_values(self, profile: Profile) -> None:
        self.kind = profile.kind
        self.container = profile.container
        self.audio = AudioSettings.from_dict(profile.audio.to_dict())
        self.video = VideoSettings.from_dict(profile.video.to_dict())
        self.current_profile = profile.id

    # ------------------------------------------------------------------
    # Persistência da configuração
    # ------------------------------------------------------------------
    def config_snapshot(self) -> ConversionConfig:
        return ConversionConfig(kind=self.kind, container=self.container,
                                audio=AudioSettings.from_dict(self.audio.to_dict()),
                                video=VideoSettings.from_dict(self.video.to_dict()))

    def persist(self) -> None:
        s = self.settings
        s.set("ffmpeg_path", s.get("ffmpeg_path") or "")
        s.set("kind", self.kind)
        s.set("container", self.container)
        s.set("audio", self.audio.to_dict())
        s.set("video", self.video.to_dict())
        s.set("naming", self.naming.to_dict())
        s.set("tag", self.tag)
        s.set("last_profile", self.current_profile if self.current_profile and
              not (self.profiles.find(self.current_profile) or Profile("", "")).builtin
              else self.current_profile)
        s.save()

    def batch_settings(self, extra: dict | None = None) -> BatchSettings:
        s = self.settings
        extra = extra or {}
        return BatchSettings(
            threads=int(extra.get("threads", s.get("threads", 0)) or 0),
            concurrent=int(extra.get("concurrent", s.get("concurrent", 0)) or 0),
            per_job_threads=int(extra.get("per_job_threads",
                                          s.get("per_job_threads", 0)) or 0),
            overwrite=bool(extra.get("overwrite", s.get("overwrite", False))),
            preserve_structure=bool(extra.get("preserve_structure",
                                              s.get("preserve_structure", True))),
            output_mode=extra.get("output_mode", s.get("output_mode", "folder")),
            output_dir=extra.get("output_dir", s.get("output_dir", "")),
            source_root=extra.get("source_root", s.get("source_root", "")),
            naming=self.naming,
            tag=self.tag,
            hw_accel=extra.get("hw_accel", s.get("hw_accel", "auto")),
        )

    # ------------------------------------------------------------------
    # Perfis e configuração
    # ------------------------------------------------------------------
    def apply_profile(self, profile: Profile) -> None:
        self._load_profile_values(profile)
        self.settings.set("last_profile", profile.id)
        self._reload_plan_async()

    def rebuild_plan(self) -> None:
        self._reload_plan_async()

    def _reload_plan_async(self) -> None:
        if self._plan_generating:
            self._plan_cache = (0.0, [])
            return
        self._plan_generating = True

        def worker() -> None:
            try:
                plan = self.queue.plan_paths(limit=600)
                self._plan_cache = (time.time(), plan)
            except Exception:  # noqa: BLE001
                log.exception("Falha ao gerar pré-visualização de nomes")
            finally:
                self._plan_generating = False
                self.bus.emit("plan_ready")

        self._plan_cache = (0.0, [])
        threading.Thread(target=worker, daemon=True, name="plan-preview").start()

    def configured_jobs(self) -> int:
        return len([job for job in self.queue.snapshot() if job.status == "pending"])

    def plan_preview(self) -> list:
        return self._plan_cache[1]

    def invalidate_analysis(self, path: str | None = None) -> None:
        self.analyzer.invalidate(path)
        self._reload_plan_async()

    def analyze_job(self, job: ConversionJob, force: bool = False) -> MediaInfo:
        if force:
            self.analyzer.invalidate(job.file)
        return self.analyzer.analyze(job.file)

    # ------------------------------------------------------------------
    # Fila
    # ------------------------------------------------------------------
    def add_files(self, files: Iterable[str],
                  output_dirs: dict[str, str] | None = None) -> list[ConversionJob]:
        config = self.config_snapshot()
        added = self.queue.add_files(files, config, output_dirs)
        if added:
            self.queue.analyze_jobs([job.id for job in added])
            self._reload_plan_async()
        return added

    def apply_config_to(self, job_ids: Iterable[int]) -> None:
        job_ids = list(job_ids)
        if not job_ids:
            return
        self.queue.set_job_config(job_ids, self.config_snapshot())
        self._reload_plan_async()
        self._analyze_missing(job_ids)

    def _analyze_missing(self, job_ids: Iterable[int]) -> None:
        """Analisa em segundo plano os arquivos (para a pré-visualização de nomes)."""
        pending = []
        for job_id in job_ids:
            job = self.queue.job(job_id)
            if job is None:
                continue
            key = self.analyzer._cache_key(job.file)
            if key in self.analyzer._cache:
                continue
            try:
                size = os.path.getsize(job.file)
            except OSError:
                size = 0
            if size <= QUICK_ANALYSIS_LIMIT:
                # pré-visualização basta com os metadados do cabeçalho
                continue
            pending.append(job_id)
        if pending:
            self.queue.analyze_jobs(pending)

    def start_batch(self, job_ids: Iterable[int] | None = None,
                    extra: dict | None = None) -> bool:
        if not self.ff.loaded:
            self.ff.ensure_loaded()
        if self.ff.error:
            self.bus.emit("ui_error", message=self.ff.error)
            return False
        jobs = None
        if job_ids:
            jobs = [self.queue.job(i) for i in job_ids if self.queue.job(i)]
        settings = self.batch_settings(extra)
        self.queue.settings = settings
        started = self.queue.start(jobs, settings)
        if started:
            self._pump_queue_events()
        return started

    def _pump_queue_events(self) -> None:
        for event in self.queue.poll():
            payload = dict(event)
            kind = payload.pop("type")
            self.bus.emit(f"queue:{kind}", **payload)

    def stop_batch(self) -> None:
        self.queue.cancel_all()

    def pause(self) -> None:
        self.queue.pause()

    def resume(self) -> None:
        self.queue.resume()

    def close(self) -> None:
        self.queue.cancel_all()
        self.queue.wait_idle(timeout=3.0)
        self.persist()
        self.store.close()

    # ------------------------------------------------------------------
    # Diagnóstico
    # ------------------------------------------------------------------
    def ffmpeg_report(self) -> str:
        self.ff.ensure_loaded()
        lines = ["=== FFmpeg ===", self.ff.summary(), "",
                 "=== Licenciamento ===", self.ff.licensing_note(), "",
                 "=== Encoders de áudio disponíveis ===",
                 ", ".join(sorted(self.ff.audio_encoders())), "",
                 "=== Encoders de vídeo disponíveis ===",
                 ", ".join(sorted(self.ff.video_encoders())), "",
                 "=== Fila ===",
                 f"{len(self.queue.jobs)} tarefas · banco: {self.store.path}",
                 f"Status: {self.store.count_by_status()}"]
        return "\n".join(lines)

    def effective_plan(self) -> tuple[int, int, int]:
        threads = int(self.settings.get("threads", 0) or 0) or logical_cpus()
        pending = sum(1 for job in self.queue.jobs if job.status == "pending")
        concurrent, per_job = compute_plan(
            threads, int(self.settings.get("concurrent", 0) or 0),
            int(self.settings.get("per_job_threads", 0) or 0), max(1, pending))
        return threads, concurrent, per_job

    def plan_destination(self, job: ConversionJob) -> str:
        policy = self.batch_settings()
        builder = CommandBuilder(self.catalog)
        info = self.analyzer.analyze(job.file)
        from ..naming.engine import NamingContext, NamingEngine
        container = builder.effective_container(job.config, info)
        extension = builder.output_extension(container, job.config.kind)
        engine = NamingEngine(self.naming)
        context = NamingContext(path=job.file, info=info, config=job.config,
                                index=1, tag=self.tag, extension=extension)
        relative = job.override_name or engine.render(context, self.naming)
        if job.override_name and extension and not relative.lower().endswith(
                "." + extension.lower()):
            relative = f"{relative}.{extension}"
        base = job.output_dir or policy.output_dir or "."
        return str(base) + "/" + relative if base else relative
