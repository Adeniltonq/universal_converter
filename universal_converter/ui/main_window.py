"""Janela principal com as cinco abas e a barra de monitoramento."""

from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import ttk

from .. import APP_NAME, __version__
from ..filesystem.scanner import ScanOptions, scan_folder
from ..media.codecs import INPUT_EXT
from ..media.models import ConversionJob
from . import dialogs, theme
from .files_panel import FileQueuePanel
from .monitor_bar import MonitorBar
from .naming_panel import NamingPanel
from .performance_panel import PerformancePanel
from .settings_widget import ConversionPanel


class MainWindow(tk.Tk):
    def __init__(self, controller):
        super().__init__()
        self.app = controller
        self.app.notify = self.notify
        self.app.request_add_files = lambda: self.add_files()
        self.app.selected_id: list[int] = []
        self._poll_scheduled = False
        self._closing = False

        self.title(f"{APP_NAME} {__version__}")
        self.minsize(1040, 680)
        theme.apply_theme(self)
        try:
            self.tk.call("tk", "scaling", 1.25 if os.name == "nt" else 1.15)
        except tk.TclError:
            pass
        geometry = self.app.settings.get("window_geometry")
        if geometry:
            try:
                self.geometry(geometry)
            except tk.TclError:
                self.geometry("1360x840")
        else:
            theme.center_window(self, 1360, 840)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._build()
        self._wire_events()
        self._restore_queue()
        # pequeno atraso para as abas calcularem o layout antes de qualquer carga
        self.after(150, self._post_start)
        self.after(200, self._poll)
        self.after(900, self._initial_checks)

    def _post_start(self) -> None:
        """Ajustes pós-inicialização que precisam do layout pronto."""
        self.performance_panel.fit_to_screen()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        header = ttk.Frame(self, style="TFrame", padding=(14, 10, 14, 4))
        header.pack(fill="x")
        ttk.Label(header, text="Universal Converter", style="Big.TLabel").pack(side="left")
        ttk.Label(header, text="conversor de áudio e vídeo em lote", style="MutedBg.TLabel"
                  ).pack(side="left", padx=(10, 0), pady=(6, 0))
        self.lbl_ffmpeg = ttk.Label(header, text="", style="MutedBg.TLabel")
        self.lbl_ffmpeg.pack(side="right")
        self._update_ffmpeg_label()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(4, 0))

        self.files_panel = FileQueuePanel(self.notebook, self.app, {
            "add_files": self.add_files,
            "add_folder": self.add_folder,
            "job_selected": self.on_job_selected,
            "jobs_selected": self.on_jobs_selected,
            "notify": self.notify,
        })
        self.settings_panel = ConversionPanel(self.notebook, self.app,
                                              on_change=self._on_settings_changed)
        self.naming_panel = NamingPanel(self.notebook, self.app,
                                        on_change=self._on_settings_changed)
        self.performance_panel = PerformancePanel(self.notebook, self.app,
                                                  on_change=self._on_settings_changed)

        self.notebook.add(self.files_panel, text="  Arquivos  ")
        self.notebook.add(self.settings_panel, text="  Conversão  ")
        self.notebook.add(self.naming_panel, text="  Nomenclatura  ")
        self.notebook.add(self.performance_panel, text="  Desempenho  ")

        self.monitor = MonitorBar(self, self.app, {
            "start": self.start_batch,
            "pause": self.toggle_pause,
            "cancel": self.cancel_batch,
        })
        self.monitor.pack(fill="x", padx=12, pady=(8, 0))

        status = ttk.Frame(self, style="Toolbar.TFrame", padding=(10, 4))
        status.pack(fill="x", side="bottom")
        self.lbl_status = ttk.Label(status, text="Pronto.", style="Status.TLabel")
        self.lbl_status.pack(side="left")
        ttk.Button(status, text="Diagnóstico", style="Small.TButton",
                   command=self.show_report).pack(side="right")
        ttk.Button(status, text="Sobre", style="Small.TButton",
                   command=self.show_about).pack(side="right", padx=6)

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self.bind_all("<Control-o>", lambda _e: self.add_files())
        self.bind_all("<Control-O>", lambda _e: self.add_folder())
        self.bind_all("<Control-Return>", lambda _e: self.start_batch())
        self.bind_all("<Control-a>", lambda _e: self._select_all())
        self.bind_all("<F5>", lambda _e: self._reload_list())

    # ------------------------------------------------------------------
    def _wire_events(self) -> None:
        bus = self.app.bus
        bus.subscribe("plan_ready", lambda _p: self.naming_panel.refresh_preview())
        bus.subscribe("queue:jobs_added", self._on_jobs_added)
        bus.subscribe("queue:jobs_removed", lambda _p: self._reload_list())
        bus.subscribe("queue:queue_cleared", lambda p: self._after_clear(p))
        bus.subscribe("queue:job_analyzed", self._on_job_analyzed)
        bus.subscribe("queue:analysis_progress", self._on_analysis_progress)
        bus.subscribe("queue:batch_started", self._on_batch_started)
        bus.subscribe("queue:job_status", self._on_job_status)
        bus.subscribe("queue:job_progress", self._on_job_progress)
        bus.subscribe("queue:job_warning", self._on_job_warning)
        bus.subscribe("queue:batch_finished", self._on_batch_finished)
        bus.subscribe("queue:batch_paused", lambda _p: self.files_panel.mark_dirty())
        bus.subscribe("queue:batch_resumed", lambda _p: self.files_panel.mark_dirty())
        bus.subscribe("queue:error", lambda p: self.notify(p.get("message", ""),
                                                           error=True))
        bus.subscribe("ui_error", lambda p: dialogs.error(self, "Erro", p.get("message", "")))

    def _poll(self) -> None:
        if self._closing:
            return
        try:
            self.app._pump_queue_events()
            self.app.bus.dispatch()
            self.monitor.tick()
            self.files_panel.refresh()
        except Exception:  # noqa: BLE001 - o loop de eventos nunca pode morrer
            import logging
            logging.getLogger("umc.ui").exception("Erro no loop de eventos")
        self.after(120, self._poll)

    # ------------------------------------------------------------------
    def _restore_queue(self) -> None:
        self.app.queue.load()
        cached = self.app.queue.load_cached_infos()
        self.files_panel.refresh(force=True)
        self._load_queue_metadata()
        if self.app.queue.jobs:
            self.notify(f"{len(self.app.queue.jobs)} tarefa(s) restaurada(s) da sessão "
                        f"anterior" + (f" ({cached} com análise em cache)."
                                       if cached else "."))

    def _load_queue_metadata(self) -> None:
        """Pede ao FFprobe (em segundo plano) os dados que faltam na tabela."""
        jobs = [job for job in self.app.queue.jobs if not job.duration]
        if not jobs:
            return

        def worker() -> None:
            self.app.analyzer.analyze_streams([job.file for job in jobs], workers=4)

        threading.Thread(target=worker, daemon=True, name="queue-metadata").start()

    def _initial_checks(self) -> None:
        if self.app.ff.error:
            dialogs.warn(self, "FFmpeg não encontrado",
                         self.app.ff.error + "\n\nAbra Desempenho → Diagnóstico ou "
                         "instale o FFmpeg e reinicie o programa.")
        tab = self.app.settings.get("active_tab")
        order = {"files": 0, "settings": 1, "naming": 2, "performance": 3}
        if tab in order:
            self.notebook.select(order[tab])

    def _on_tab_changed(self, _event=None) -> None:
        index = self.notebook.index(self.notebook.select())
        self.app.settings.set("active_tab", ["files", "settings", "naming",
                                             "performance"][index])
        if index == 2:
            self.naming_panel.refresh_preview()

    def _update_ffmpeg_label(self) -> None:
        ff = self.app.ff
        if ff.error:
            self.lbl_ffmpeg.configure(text="FFmpeg não encontrado",
                                      foreground=theme.ERROR)
        else:
            self.lbl_ffmpeg.configure(text="via " + ff.version_line(),
                                      foreground=theme.FG_MUTED)

    # ------------------------------------------------------------------
    # Eventos da fila
    # ------------------------------------------------------------------
    def _on_jobs_added(self, payload) -> None:
        self.files_panel.mark_dirty(relist=True)
        self.files_panel.refresh(force=True)
        jobs = payload.get("jobs") or []
        if jobs:
            self.notify(f"{len(jobs)} arquivo(s) adicionado(s).")
        self.app.rebuild_plan()
        self.performance_panel._update_math()

    def _on_job_analyzed(self, payload) -> None:
        job = payload.get("job")
        info = payload.get("info")
        if job is not None and info is not None:
            self.files_panel.set_analysis(job.id, info)

    def _on_analysis_progress(self, payload) -> None:
        self.lbl_status.configure(text=f"Analisando {payload.get('done')}/"
                                       f"{payload.get('total')}…")

    def _on_batch_started(self, payload) -> None:
        self.lbl_status.configure(text=f"Conversão iniciada: {payload.get('total')} tarefa(s), "
                                       f"{payload.get('concurrent')} simultânea(s) × "
                                       f"{payload.get('per_job')} thread(s).")
        self.files_panel.mark_dirty(relist=True)

    def _on_job_status(self, payload) -> None:
        job = payload.get("job")
        status = payload.get("status")
        message = payload.get("message", "")
        if job is not None:
            job.status = status
            self.files_panel.invalidate_row(job.id)
        self.files_panel.mark_dirty(relist=True)
        if status == "error":
            self.lbl_status.configure(text=f"Erro em {os.path.basename(job.file)}: "
                                           f"{message}", foreground=theme.ERROR)
        elif status == "done":
            self.lbl_status.configure(text=f"Concluído: {os.path.basename(job.file)}",
                                      foreground=theme.FG_MUTED)

    def _on_job_progress(self, payload) -> None:
        job = payload.get("job")
        if job is not None:
            job.progress = payload.get("progress", 0.0)
            job._speed = payload.get("speed", 0.0)  # type: ignore[attr-defined]
            self.files_panel.invalidate_row(job.id)

    def _on_job_warning(self, payload) -> None:
        job = payload.get("job")
        self.notify(f"{os.path.basename(getattr(job, 'file', ''))}: "
                    f"{payload.get('message', '')}")

    def _on_batch_finished(self, payload) -> None:
        stats = payload.get("stats") or {}
        self.monitor.notify_finished()
        self.files_panel.mark_dirty(relist=True)
        self.files_panel.refresh(force=True)
        if not self.app.queue.is_running:
            self.notify(f"Conversão concluída: {stats.get('done', 0)} ok, "
                        f"{stats.get('errors', 0)} erro(s), "
                        f"{stats.get('cancelled', 0)} cancelada(s).")
        if self.app.settings.get("notify_on_finish", True):
            try:
                self.bell()
            except tk.TclError:
                pass

    def _after_clear(self, _payload) -> None:
        self.files_panel.refresh(force=True)
        self.app.invalidate_analysis()
        self.notify("Fila limpa.")

    def _reload_list(self) -> None:
        self.files_panel.refresh(force=True)

    def _select_all(self) -> None:
        if self.notebook.index(self.notebook.select()) == 0:
            self.files_panel.tree.selection_set(self.files_panel.tree.get_children())

    # ------------------------------------------------------------------
    # Configuração e seleção
    # ------------------------------------------------------------------
    def _on_settings_changed(self) -> None:
        self.app.rebuild_plan()

    def on_job_selected(self, job: ConversionJob) -> None:
        self.app.selected_id = [job.id]
        self.settings_panel.set_selected_jobs([job.id])
        self.settings_panel.refresh_for_job(job)

    def on_jobs_selected(self, jobs: list) -> None:
        ids = [job.id for job in jobs]
        self.app.selected_id = ids
        self.settings_panel.set_selected_jobs(ids)

    # ------------------------------------------------------------------
    # Adicionar arquivos / pastas
    # ------------------------------------------------------------------
    def add_files(self) -> None:
        files = dialogs.ask_files(self)
        if not files:
            return
        self._add_paths(list(files), source_root=self._common_root(files))
        self.performance_panel.load_from_settings()

    def _common_root(self, files) -> str:
        import os as _os
        try:
            root = _os.path.commonpath([_os.path.dirname(f) for f in files])
        except ValueError:
            return ""
        return root if _os.path.isdir(root) else ""

    def _add_paths(self, files: list[str], source_root: str = "",
                   output_dir: str = "") -> None:
        settings = self.app.settings
        if source_root and not settings.get("source_root"):
            settings.set("source_root", source_root)
            self.performance_panel.load_from_settings()
        elif len(files) == 1 and source_root:
            # um único arquivo escolhido: não criar subpasta replicando a origem
            settings.set("preserve_structure", False)
            self.performance_panel.load_from_settings()
        output_dirs = {path: output_dir for path in files} if output_dir else {}
        added = self.app.add_files(files, output_dirs)
        if not added:
            self.notify("Os arquivos selecionados já estão na fila.")

    def add_folder(self) -> None:
        folder = dialogs.ask_folder(self, "Adicionar pasta")
        if not folder:
            return
        cache = self.app.settings.get("folder_import") or {}
        history = self.app.settings.get("folder_history") or []
        if folder in history:
            history.remove(folder)
        history.insert(0, folder)
        self.app.settings.set("folder_history", history[:10])
        dialog = dialogs.FolderImportDialog(self, folder, cache)
        options = dialog.show()
        if not options:
            return
        self.app.settings.set("folder_import", options)
        exts_text = options.get("extensions", "")
        extensions = ({e.strip().lstrip(".").lower() for e in exts_text.split(",")
                       if e.strip()} if exts_text else set(INPUT_EXT))
        scan_options = ScanOptions(
            recursive=bool(options.get("recursive", True)),
            extensions=extensions,
            include_hidden=bool(options.get("include_hidden", False)),
            exclude_patterns=[line.strip() for line in options.get("exclude", "").splitlines()
                              if line.strip()],
            output_dir=options.get("output_dir", "") or self.app.settings.get(
                "output_dir", ""),
            max_files=0,
        )
        self.lbl_status.configure(text=f"Procurando arquivos em {folder}…")
        self.update_idletasks()
        result = scan_folder(folder, scan_options)
        if not scan_options.recursive:
            # sem subpastas não há hierarquia a preservar
            self.app.settings.set("preserve_structure", False)
            self.performance_panel.load_from_settings()
        self.lbl_status.configure(text=f"{len(result.files)} arquivo(s) encontrado(s).")
        if not result.files:
            dialogs.info(self, "Nenhum arquivo",
                         "Nenhum arquivo de mídia compatível foi encontrado nessa pasta."
                         + ("\n\nErros: " + "; ".join(result.errors[:3])
                            if result.errors else ""))
            return
        settings = self.app.settings
        if not settings.get("source_root"):
            settings.set("source_root", folder)
            self.performance_panel.load_from_settings()
        self._add_paths(result.files, source_root=folder,
                        output_dir=options.get("output_dir", ""))
        if result.skipped_output:
            self.notify(f"{result.skipped_output} pasta(s) ignorada(s) por estarem no "
                        f"destino.")

    # ------------------------------------------------------------------
    # Controle do lote
    # ------------------------------------------------------------------
    def _scope_selection(self) -> list[int] | None:
        scope = self.monitor.var_scope.get()
        selected = self.files_panel.selected_ids()
        if scope.startswith("Somente") and not selected:
            dialogs.info(self, "Nada selecionado",
                         "Selecione arquivos na aba Arquivos ou escolha toda a fila.")
            return []
        if scope.startswith("Somente") or scope.startswith("Selecionados"):
            return selected or None
        return None

    def start_batch(self) -> None:
        if self.app.queue.is_running:
            self.notify("Já existe uma conversão em andamento.")
            return
        pending = [job for job in self.app.queue.snapshot() if job.status == "pending"]
        if not pending:
            dialogs.info(self, "Nada para converter",
                         "A fila não tem tarefas pendentes. Adicione arquivos na aba "
                         "Arquivos.")
            return
        targets = self._scope_selection()
        if targets == []:
            return
        if targets is not None:
            pending = [job for job in pending if job.id in set(targets)]
        # arquivos recém-adicionados com configuração antiga recebem a atual
        self.app.queue.set_job_config([job.id for job in pending],
                                      self.app.config_snapshot())
        settings = self.app.batch_settings()
        if settings.output_mode == "folder" and not settings.output_dir:
            folder = dialogs.ask_folder(self, "Escolha a pasta de destino")
            if not folder:
                return
            self.app.settings.set("output_dir", folder)
            self.performance_panel.load_from_settings()
        self.settings_panel.changed()
        self.app.start_batch([job.id for job in pending])

    def toggle_pause(self) -> None:
        if not self.app.queue.is_running:
            return
        paused = self.app.queue.toggle_pause()
        self.notify("Conversão pausada." if paused else "Conversão retomada.")

    def cancel_batch(self) -> None:
        if self.app.queue.is_running:
            if dialogs.confirm(self, "Cancelar", "Cancelar as conversões em andamento e "
                                                 "as tarefas que ainda não começaram?"):
                self.app.stop_batch()

    # ------------------------------------------------------------------
    def notify(self, message: str, error: bool = False) -> None:
        if not message:
            return
        try:
            self.lbl_status.configure(text=message,
                                      foreground=theme.ERROR if error else theme.FG_MUTED)
        except tk.TclError:
            pass

    def show_report(self) -> None:
        from .dialogs import TextDialog
        TextDialog(self, "Diagnóstico", self.app.ffmpeg_report())

    def show_about(self) -> None:
        from .dialogs import TextDialog
        from ..core.util import app_data_dir, local_bin_dir
        from ..core.logger import log_dir
        text = (
            f"{APP_NAME} {__version__}\n\n"
            "Conversor de áudio (com suporte a vídeo) em lote, com extração de faixas, "
            "nomenclatura inteligente e processamento paralelo com orçamento de threads.\n\n"
            "Interface: Python + Tkinter (biblioteca padrão, sem dependências externas).\n"
            "Motor multimídia: FFmpeg/FFprobe instalado na máquina.\n\n"
            f"FFmpeg: {self.app.ff.ffmpeg or 'não encontrado'}\n"
            f"Procurado também em: {local_bin_dir()}\n"
            f"Configurações: {app_data_dir()}\n"
            f"Logs: {log_dir()}\n\n"
            "Licenciamento do FFmpeg:\n" + self.app.ff.licensing_note()
        )
        TextDialog(self, f"Sobre {APP_NAME}", text)

    # ------------------------------------------------------------------
    def on_close(self) -> None:
        if self._closing:
            return
        if self.app.queue.is_running:
            if not dialogs.confirm(self, "Sair", "Há conversões em andamento. Cancelar e "
                                                 "sair?"):
                return
        self._closing = True
        try:
            geometry = self.geometry()
            self.app.settings.set("window_geometry", geometry)
        except tk.TclError:
            pass
        try:
            self.app.close()
        finally:
            self.destroy()
