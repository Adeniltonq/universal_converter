"""Aba "Arquivos": adicionar, filtrar, ordenar e gerenciar a fila.

A tabela é **virtualizada**: o `Treeview` contém apenas um bloco de linhas em
torno da área visível, com espaçadores (linhas vazias aninhadas) para que a
barra de rolagem reflita o total e o deslocamento continue funcionando. Assim
a interface permanece fluida com dezenas de milhares de tarefas. A fonte de
dados é o `QueueManager`, persistido em SQLite.

O layout se adapta: em janelas estreitas a busca quebra a linha abaixo dos
filtros, e a barra de ferramentas quebra em duas linhas quando necessário.
"""

from __future__ import annotations

import os
import time
import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..core.util import fmt_bitrate, fmt_duration, fmt_size
from ..media.codecs import CONTAINERS, INPUT_CODEC_LABEL
from ..media.models import MediaInfo
from ..queue.manager import STATUS_LABEL
from . import theme
from .theme import make_button, tooltip

COLUMNS = [
    ("status", "Status", 96),
    ("name", "Arquivo", 230),
    ("format", "Formato", 72),
    ("vcodec", "Vídeo", 88),
    ("acodec", "Áudio", 92),
    ("resolution", "Resolução", 88),
    ("fps", "FPS", 48),
    ("duration", "Duração", 66),
    ("size", "Tamanho", 74),
    ("bitrate", "Bitrate", 84),
    ("output", "Saída", 70),
    ("progress", "Progresso", 76),
    ("message", "Detalhes", 200),
]

# colunas que somem primeiro quando a janela é estreita
OPTIONAL_COLUMNS = ("fps", "bitrate", "resolution", "format", "output")

FILTERS = ["Todos", "Aguardando", "Convertendo", "Concluídos", "Com erro", "Cancelados",
           "Somente áudio", "Somente vídeo"]

STATUS_FILTERS = {
    "Aguardando": ("pending", "analyzing"),
    "Convertendo": ("running",),
    "Concluídos": ("done",),
    "Com erro": ("error",),
    "Cancelados": ("cancelled", "skipped"),
}


class FileQueuePanel(ttk.Frame):
    def __init__(self, parent: tk.Misc, controller, callbacks: dict[str, Callable]):
        super().__init__(parent, style="TFrame", padding=(12, 10))
        self.app = controller
        self.callbacks = callbacks
        self._infos: dict[int, MediaInfo] = {}
        self._visible_ids: list[int] = []
        self._iid_job: dict[str, int] = {}
        self._gap_ids: set[str] = set()
        self._filter = FILTERS[0]
        self._search = ""
        self._sort_column = ""
        self._sort_reverse = False
        self._dirty = True
        self._last_tick = 0.0
        self._refresh_list = True
        self._compact = False
        self._hidden_columns: tuple[str, ...] = ()

        self._build_toolbar()
        self._build_tree()
        self._build_footer()
        self.refresh(force=True)
        self.bind("<Configure>", self._on_resize)

    # ------------------------------------------------------------------
    # Construção
    # ------------------------------------------------------------------
    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self, style="TFrame")
        bar.pack(fill="x", pady=(0, 6))
        self._toolbar = bar

        # linha 1: título + ações
        top = ttk.Frame(bar, style="TFrame")
        top.pack(fill="x")
        ttk.Label(top, text="Arquivos", style="Title.TLabel").pack(side="left")
        self._actions = ttk.Frame(top, style="TFrame")
        self._actions.pack(side="left", padx=(10, 0))
        buttons = [
            ("+ Arquivos…", lambda: self.callbacks["add_files"](), "AddFiles.TButton",
             "Selecionar arquivos de mídia (Ctrl+O)"),
            ("+ Pasta…", lambda: self.callbacks["add_folder"](), "AddFolder.TButton",
             "Adicionar uma pasta, com subpastas opcionais (Ctrl+Shift+O)"),
            ("Remover", self._remove_selected, "TButton", "Remover selecionados (Del)"),
            ("Limpar", self._clear, "TButton", "Remover todas as tarefas"),
        ]
        for text, command, style, tip in buttons:
            button = make_button(self._actions, text, command,
                                 style if style != "TButton" else "Tool.TButton")
            button.pack(side="left", padx=(0, 4))
            tooltip(button, tip)
            if text == "Limpar":
                self._btn_clear = button
        self._btn_up = make_button(self._actions, "↑", lambda: self._move(-1),
                                   "Icon.TButton")
        self._btn_up.pack(side="left", padx=(6, 2))
        tooltip(self._btn_up, "Subir a tarefa selecionada")
        self._btn_down = make_button(self._actions, "↓", lambda: self._move(1),
                                     "Icon.TButton")
        self._btn_down.pack(side="left")
        tooltip(self._btn_down, "Descer a tarefa selecionada")

        # linha 2: busca + filtro
        controls = ttk.Frame(bar, style="TFrame")
        controls.pack(fill="x", pady=(6, 0))
        self._controls = controls
        label = ttk.Label(controls, text="Buscar", style="MutedBg.TLabel")
        label.pack(side="left")
        self.var_search = tk.StringVar()
        self.search_entry = ttk.Entry(controls, textvariable=self.var_search)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(6, 12))
        self.var_search.trace_add("write", lambda *_a: self.set_search(
            self.var_search.get()))
        ttk.Label(controls, text="Filtro", style="MutedBg.TLabel").pack(side="left")
        self.var_filter = tk.StringVar(value=FILTERS[0])
        self.combo_filter = ttk.Combobox(controls, textvariable=self.var_filter,
                                         values=FILTERS, state="readonly", width=16)
        self.combo_filter.pack(side="left", padx=(6, 0))
        self.combo_filter.bind("<<ComboboxSelected>>",
                               lambda _e: self.set_filter(self.var_filter.get()))

    def _build_tree(self) -> None:
        wrap = ttk.Frame(self, style="TFrame")
        wrap.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(wrap, columns=[c[0] for c in COLUMNS], show="headings",
                                 selectmode="extended")
        for key, title, width in COLUMNS:
            self.tree.heading(key, text=title, command=lambda k=key: self._sort_by(k))
            anchor = "e" if key in ("duration", "size", "bitrate", "fps", "progress") \
                else "w"
            self.tree.column(key, width=width, minwidth=40, anchor=anchor,
                             stretch=(key in ("name", "message")))
        for status, color in theme.STATUS_COLORS.items():
            self.tree.tag_configure(status, foreground=color)
        self.tree.tag_configure("odd", background=theme.BG_ALT)
        self.tree.tag_configure("even", background="#22272e")
        self.tree.tag_configure("gap", background=theme.BG_ALT)
        self.yscroll = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        self.yscroll.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Button-3>", self._on_right_click)
        self.tree.bind("<Delete>", lambda _e: self._remove_selected())
        self.tree.bind("<Return>", lambda _e: self._open_properties())
        self.tree.bind("<Configure>", lambda _e: self._virtualize())
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>", "<Prior>", "<Next>",
                         "<Home>", "<End>", "<Up>", "<Down>"):
            self.tree.bind(sequence, lambda _e: self.after_idle(self._virtualize),
                           add="+")

        self.menu = tk.Menu(self, tearoff=0, background=theme.PANEL, foreground=theme.FG,
                            activebackground=theme.SEL, activeforeground=theme.FG,
                            borderwidth=1)
        self.menu.add_command(label="Propriedades / análise",
                              command=self._open_properties)
        self.menu.add_command(label="Abrir pasta do arquivo", command=self._open_folder)
        self.menu.add_command(label="Reanalisar", command=self._reanalyze)
        self.menu.add_separator()
        self.menu.add_command(label="Aplicar configuração atual (aba Conversão)",
                              command=self._apply_settings)
        self.menu.add_command(label="Repetir / recolocar na fila", command=self._retry)
        self.menu.add_command(label="Cancelar", command=self._cancel)
        self.menu.add_command(label="Remover", command=self._remove_selected)

    def _build_footer(self) -> None:
        footer = ttk.Frame(self, style="Toolbar.TFrame", padding=(10, 6))
        footer.pack(fill="x", pady=(6, 0))
        self.lbl_visible = ttk.Label(footer, text="", style="Status.TLabel")
        self.lbl_visible.pack(side="right")
        self.lbl_session = ttk.Label(footer, text="", style="Status.TLabel")
        self.lbl_session.pack(side="left", padx=(10, 0))
        self.lbl_totals = ttk.Label(footer, text="", style="StatusAccent.TLabel")
        self.lbl_totals.pack(side="left")

    # ------------------------------------------------------------------
    # Adaptação ao tamanho
    # ------------------------------------------------------------------
    def _on_resize(self, event) -> None:
        """Esconde colunas opcionais e compacta a barra em janelas estreitas."""
        width = event.width
        compact = width < 1180
        if compact != self._compact:
            self._compact = compact
            if compact:
                self._btn_clear.pack_forget()
            else:
                self._btn_clear.pack(side="left", padx=(0, 4))
            self._apply_columns(width)
        else:
            self._apply_columns(width)

    def _apply_columns(self, width: int) -> None:
        # esconde da última para a primeira até o nome ter espaço confortável
        hidden: list[str] = []
        budget = width
        total = sum(c[2] for c in COLUMNS)
        for key in reversed(OPTIONAL_COLUMNS):
            if budget >= 760 and total <= width - 20:
                break
            hidden.append(key)
            total -= next(c[2] for c in COLUMNS if c[0] == key)
        if tuple(hidden) == self._hidden_columns:
            return
        self._hidden_columns = tuple(hidden)
        visible = [c[0] for c in COLUMNS if c[0] not in hidden]
        self.tree.configure(displaycolumns=visible)
        # distribui o espaço extra entre nome e detalhes
        extra = max(0, width - 30 - total)
        name_width = next(c[2] for c in COLUMNS if c[0] == "name") + extra // 2
        msg_width = next(c[2] for c in COLUMNS if c[0] == "message") + extra // 2
        self.tree.column("name", width=max(160, name_width))
        self.tree.column("message", width=max(120, msg_width))

    # ------------------------------------------------------------------
    # Dados
    # ------------------------------------------------------------------
    def set_analysis(self, job_id: int, info: MediaInfo) -> None:
        self._infos[job_id] = info
        self._dirty = True
        self._virtualize()

    def invalidate_row(self, job_id: int) -> None:
        """Marca uma linha para atualização (progresso/status)."""
        self._dirty = True

    def mark_dirty(self, relist: bool = False) -> None:
        self._dirty = True
        if relist:
            self._refresh_list = True

    def set_filter(self, name: str) -> None:
        self._filter = name
        self.refresh(force=True)

    def set_search(self, text: str) -> None:
        self._search = text.strip().lower()
        self.refresh(force=True)

    def _matches(self, job, info: MediaInfo | None) -> bool:
        if self._filter == "Somente áudio":
            if not (info and info.is_audio_only):
                return False
        elif self._filter == "Somente vídeo":
            if not (info and info.is_video):
                return False
        elif self._filter in STATUS_FILTERS:
            if job.status not in STATUS_FILTERS[self._filter]:
                return False
        if self._search:
            haystack = f"{job.file} {job.message} {job.config.container}".lower()
            if self._search not in haystack:
                matching = getattr(self, "_search_ids", None)
                if matching is None:
                    matching = {other.id for other in self.app.queue.snapshot()
                                if self._search in f"{other.file} {other.message} "
                                                  f"{other.config.container}".lower()}
                    self._search_ids = matching
                    self.after(1500, lambda: setattr(self, "_search_ids", None))
                if job.id not in matching:
                    return False
        return True

    def _sort_key(self, job):
        key = self._sort_column
        info = self._infos.get(job.id)
        if key == "status":
            return job.status
        if key == "size":
            return job.size or 0
        if key == "duration":
            return job.duration or 0
        if key == "format":
            return info.format_label() if info else ""
        if key == "vcodec":
            video = info.main_video if info else None
            return video.codec if video else ""
        if key == "acodec":
            audio = info.main_audio if info else None
            return audio.codec if audio else ""
        if key == "output":
            container = CONTAINERS.get(job.config.container)
            return container.label if container else job.config.container
        if key == "progress":
            return job.progress
        if key == "bitrate":
            return (info.bitrate if info else 0) or 0
        return os.path.basename(job.file).lower()

    def _sort_by(self, column: str) -> None:
        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = False
        for key, title, _w in COLUMNS:
            indicator = ""
            if key == self._sort_column:
                indicator = " ▼" if self._sort_reverse else " ▲"
            self.tree.heading(key, text=title + indicator)
        self.refresh(force=True)

    def refresh(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and not self._refresh_list:
            if self._dirty and now - self._last_tick > 0.4:
                self._virtualize()
            return
        self._last_tick = now
        self._refresh_list = False
        self._dirty = False
        jobs = self.app.queue.snapshot()
        visible = [job for job in jobs if self._matches(job, self._infos.get(job.id))]
        if self._sort_column:
            try:
                visible.sort(key=self._sort_key, reverse=self._sort_reverse)
            except TypeError:
                pass
        self._visible_ids = [job.id for job in visible]
        selected = set(self.selected_ids())
        self.tree.delete(*self.tree.get_children())
        self._iid_job.clear()
        self._gap_ids.clear()
        self._virtualize()
        for job_id in selected:
            iid = f"job{job_id}"
            if iid in self.tree.get_children():
                self.tree.selection_add(iid)
        self._update_totals(jobs, selected)

    def _gap_height(self) -> int:
        return theme.row_height(self)

    def _visible_count(self) -> int:
        height = max(120, self.tree.winfo_height())
        return int(height / self._gap_height()) + 6

    def _virtualize(self) -> None:
        total = len(self._visible_ids)
        visible_rows = self._visible_count()
        block = max(2000, visible_rows * 3)

        children = self.tree.get_children()
        top_job_id = None
        for iid in children:
            if iid in self._iid_job:
                top_job_id = self._iid_job[iid]
                break
        if top_job_id is not None:
            anchor_index = self._visible_ids.index(top_job_id)
        else:
            anchor_index = getattr(self, "_window_start", 0)
        if total > block and children:
            try:
                fraction = self.tree.yview()[0]
                top_row = int(fraction * (total + visible_rows))
            except tk.TclError:
                top_row = anchor_index
        else:
            top_row = anchor_index

        if total <= block:
            start, end = 0, total
        else:
            start = max(0, min(total - block, top_row - visible_rows // 2))
            end = min(total, start + block)

        before = start
        after = total - end
        target: dict[str, tuple[int, int]] = {}
        if before:
            target["gap_before"] = (before, 0)
        line = before + 1
        for index in range(start, end):
            job_id = self._visible_ids[index]
            job = self.app.queue.job(job_id)
            if job is None:
                continue
            target[f"job{job_id}"] = (1, line)
            line += 1
        if after:
            target["gap_after"] = (after, line)

        existing = set(children)
        wanted = set(target)
        for iid in existing - wanted:
            self.tree.delete(iid)
            self._iid_job.pop(iid, None)
            self._gap_ids.discard(iid)

        self._rebuild_gaps(target)
        for index in range(start, end):
            job_id = self._visible_ids[index]
            job = self.app.queue.job(job_id)
            if job is None:
                continue
            iid = f"job{job_id}"
            values = self._row_values(job, index)
            tags = (job.status, "even" if index % 2 else "odd")
            try:
                self.tree.item(iid, values=values, tags=tags)
            except tk.TclError:
                self.tree.insert("", "end", iid=iid)
                self.tree.item(iid, values=values, tags=tags)
            self._iid_job[iid] = job_id
        self._window_start = start

    def _rebuild_gaps(self, target: dict[str, tuple[int, int]]) -> None:
        """Posiciona espaçadores para representar as linhas não carregadas."""
        for gap_iid in ("gap_before", "gap_after"):
            count, line = target.get(gap_iid, (0, 0))
            if gap_iid in self.tree.get_children():
                self.tree.delete(gap_iid)
                self._gap_ids.discard(gap_iid)
            if count <= 0 or line <= 0:
                continue
            gap_parent = f"{gap_iid}_root"
            if gap_parent in self.tree.get_children():
                self.tree.delete(gap_parent)
            parent = self.tree.insert("", line - 1, iid=gap_parent, tags=("gap",))
            for _ in range(count):
                self.tree.insert(parent, "end", text="", tags=("gap",))
            self._gap_ids.add(gap_parent)

    def _row_values(self, job, index: int) -> tuple:
        info = self._infos.get(job.id)
        status = STATUS_LABEL.get(job.status, job.status)
        if job.status == "running":
            status = f"{job.progress * 100:.0f}%"
        fmt = info.format_label() if info else ""
        vcodec = acodec = resolution = fps = bitrate = ""
        if info:
            if info.main_video:
                video = info.main_video
                vcodec = INPUT_CODEC_LABEL.get(video.codec, video.codec)
                resolution = f"{video.width}×{video.height}"
                fps = f"{video.fps:.2f}".rstrip("0").rstrip(".") if video.fps else ""
            if info.main_audio:
                audio = info.main_audio
                acodec = INPUT_CODEC_LABEL.get(audio.codec, audio.codec)
                if audio.channels > 2:
                    acodec += f" {audio.channels}ch"
                if audio.bitrate:
                    bitrate = fmt_bitrate(audio.bitrate)
            if not bitrate and info.bitrate:
                bitrate = fmt_bitrate(info.bitrate)
        container = CONTAINERS.get(job.config.container)
        output = container.label.split(" (")[0] if container else job.config.container
        duration = fmt_duration(job.duration if job.duration is not None
                                else (info.duration if info else None))
        message = job.output_path if job.status == "done" else job.message
        return (
            status,
            os.path.basename(job.file),
            fmt, vcodec, acodec, resolution, fps, duration, fmt_size(job.size),
            bitrate, output,
            f"{job.progress * 100:.0f}%" if job.progress else "",
            message,
        )

    def _update_totals(self, jobs: list, selected: set[int]) -> None:
        counts: dict[str, int] = {}
        total_size = 0
        for job in jobs:
            counts[job.status] = counts.get(job.status, 0) + 1
            total_size += job.size or 0
        parts = [f"{len(jobs)} arquivos", fmt_size(total_size)]
        for status in ("pending", "running", "done", "error", "cancelled"):
            if counts.get(status):
                parts.append(f"{STATUS_LABEL.get(status, status)}: {counts[status]}")
        self.lbl_totals.configure(text=" · ".join(parts))
        stats = self.app.queue.stats
        if stats.started and stats.finished:
            elapsed = stats.finished - stats.started
            self.lbl_session.configure(
                text=f"Sessão: {stats.done} ok, {stats.errors} erros em "
                     f"{fmt_duration(elapsed)} · {fmt_size(stats.bytes_written)}")
        elif stats.started:
            self.lbl_session.configure(text=f"Sessão em andamento: {stats.done}/"
                                            f"{stats.total} concluídos")
        else:
            self.lbl_session.configure(text="")
        self.lbl_visible.configure(
            text=f"{len(self._visible_ids)} visíveis"
                 + (f" · filtro: {self._filter}" if self._filter != "Todos" else ""))

    # ------------------------------------------------------------------
    # Seleção
    # ------------------------------------------------------------------
    def selected_ids(self) -> list[int]:
        return [self._iid_job[iid] for iid in self.tree.selection()
                if iid in self._iid_job]

    def selected_jobs(self) -> list:
        return [job for job in (self.app.queue.job(i) for i in self.selected_ids())
                if job is not None]

    def _on_select(self, _event=None) -> None:
        jobs = self.selected_jobs()
        if len(jobs) == 1:
            self.callbacks["job_selected"](jobs[0])
        elif len(jobs) > 1:
            self.callbacks["jobs_selected"](jobs)

    def _on_double_click(self, event) -> None:
        if self.tree.identify_row(event.y):
            self._open_properties()

    def _on_right_click(self, event) -> None:
        row = self.tree.identify_row(event.y)
        if row and row not in self.tree.selection():
            self.tree.selection_set(row)
            self._on_select()
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------
    def _remove_selected(self) -> None:
        ids = self.selected_ids()
        if ids:
            self.app.queue.remove_jobs(ids)
            self.refresh(force=True)

    def _clear(self) -> None:
        from .dialogs import confirm
        if not self.app.queue.jobs:
            return
        if confirm(self, "Limpar fila", "Remover todas as tarefas da fila?"):
            self.app.queue.clear()
            self.refresh(force=True)
            self.callbacks["notify"]("Fila limpa.")

    def _move(self, offset: int) -> None:
        ids = self.selected_ids()
        if len(ids) != 1:
            self.callbacks["notify"]("Selecione uma única tarefa para reordenar.")
            return
        self.app.queue.move(ids[0], offset)
        self._sort_column = ""
        self.refresh(force=True)

    def _open_properties(self) -> None:
        jobs = self.selected_jobs()
        if not jobs:
            return
        info = self.app.analyze_job(jobs[0])
        from .dialogs import MediaInfoDialog
        MediaInfoDialog(self, info)

    def _open_folder(self) -> None:
        from ..core.util import open_in_file_manager
        jobs = self.selected_jobs()
        if jobs:
            open_in_file_manager(os.path.dirname(jobs[0].file))

    def _reanalyze(self) -> None:
        ids = self.selected_ids()
        if not ids:
            return
        for job_id in ids:
            job = self.app.queue.job(job_id)
            if job:
                self.app.invalidate_analysis(job.file)
        self.app.queue.analyze_jobs(ids)
        self.callbacks["notify"]("Reanalisando arquivos selecionados…")

    def _apply_settings(self) -> None:
        ids = self.selected_ids()
        if ids:
            self.app.apply_config_to(ids)
            self.callbacks["notify"]("Configuração aplicada aos selecionados.")
            self.refresh(force=True)

    def _retry(self) -> None:
        ids = self.selected_ids()
        if not ids:
            ids = [job.id for job in self.app.queue.jobs
                   if job.status in ("error", "cancelled")]
        if ids:
            self.app.queue.reset_jobs(ids)
            self.callbacks["notify"]("Tarefas recolocadas na fila.")
            self.refresh(force=True)

    def _cancel(self) -> None:
        for job_id in self.selected_ids():
            self.app.queue.cancel_job(job_id)
        self.mark_dirty()
