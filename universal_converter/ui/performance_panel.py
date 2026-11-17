"""Aba "Desempenho": threads, paralelismo, destino e opções de saída."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..queue.scheduler import compute_plan, logical_cpus
from . import theme
from .dialogs import ask_folder
from .theme import hint, section, tooltip


class PerformancePanel(ttk.Frame):
    def __init__(self, parent: tk.Misc, controller, on_change: Callable | None = None):
        super().__init__(parent, style="TFrame", padding=(12, 10))
        self.app = controller
        self.on_change = on_change or (lambda: None)
        self.cpus = logical_cpus()
        self._loading = True

        header = ttk.Frame(self, style="TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="Desempenho e saída", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text=f"Detectado: {self.cpus} threads lógicas",
                  style="MutedBg.TLabel").pack(side="left", padx=12)

        body = ttk.Frame(self, style="TFrame")
        body.pack(fill="both", expand=True, pady=(10, 0))
        body.columnconfigure(0, weight=1, uniform="col")
        body.columnconfigure(1, weight=1, uniform="col")
        body.rowconfigure(0, weight=1)

        self._build_threads(body)
        self._build_output(body)
        self._loading = False
        self.load_from_settings()

    # ------------------------------------------------------------------
    def _build_threads(self, parent: ttk.Frame) -> None:
        card = ttk.LabelFrame(parent, text="Processamento", style="TLabelframe",
                              padding=10)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        card.columnconfigure(1, weight=1)

        ttk.Label(card, text="Threads de execução", style="Card.TLabel").grid(
            row=0, column=0, sticky="w", pady=3)
        frame = ttk.Frame(card, style="Card.TFrame")
        frame.grid(row=0, column=1, sticky="ew", pady=3)
        self.var_threads = tk.IntVar(value=self.cpus)
        self.scale_threads = ttk.Scale(frame, from_=1, to=max(1, self.cpus),
                                       orient="horizontal", variable=self.var_threads,
                                       command=lambda _v: self._update_math())
        self.scale_threads.pack(side="left", fill="x", expand=True)
        self.lbl_threads = ttk.Label(frame, text=str(self.cpus), width=4,
                                     style="Card.TLabel")
        self.lbl_threads.pack(side="left", padx=(6, 0))
        tooltip(self.scale_threads, "Orçamento global de threads usadas pelo programa "
                                    "(entre arquivos e dentro de cada encoder).")

        ttk.Label(card, text="Arquivos simultâneos", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", pady=3)
        self.var_concurrent = tk.StringVar(value="Automático")
        self.combo_concurrent = ttk.Combobox(card, textvariable=self.var_concurrent,
                                             width=14,
                                             values=["Automático"] + [str(i) for i in
                                                                      range(1, 33)])
        self.combo_concurrent.grid(row=1, column=1, sticky="w", pady=3)
        self.combo_concurrent.bind("<<ComboboxSelected>>", lambda _e: self._update_math())

        ttk.Label(card, text="Threads por encoder", style="Card.TLabel").grid(
            row=2, column=0, sticky="w", pady=3)
        self.var_per_job = tk.StringVar(value="Automático")
        self.combo_per_job = ttk.Combobox(card, textvariable=self.var_per_job, width=14,
                                          values=["Automático"] + [str(i) for i in
                                                                   range(1, 33)])
        self.combo_per_job.grid(row=2, column=1, sticky="w", pady=3)
        self.combo_per_job.bind("<<ComboboxSelected>>", lambda _e: self._update_math())

        self.lbl_math = ttk.Label(card, text="", style="Hint.TLabel", wraplength=420)
        self.lbl_math.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 4))
        hint(card, "Paralelismo entre arquivos e dentro de cada arquivo contam juntos: "
                   "4 arquivos × 4 threads já usam 16 threads. O programa distribui o "
                   "orçamento e rebalanceia quando as tarefas têm custos diferentes."
             ).grid(row=4, column=0, columnspan=2, sticky="w")

        self.var_hw = tk.BooleanVar(value=False)
        hw_available = [kind for kind in ("nvenc", "qsv", "amf", "videotoolbox")
                        if self.app.ff.has_hwaccel(kind)]
        ttk.Label(card, text="Aceleração por hardware", style="Card.TLabel").grid(
            row=5, column=0, sticky="w", pady=(10, 3))
        self._hw_label = ttk.Label(card, text="", style="Muted.TLabel")
        self._hw_label.grid(row=5, column=1, sticky="w", pady=(10, 3))
        if hw_available:
            self._hw_label.configure(text="Disponível: " + ", ".join(hw_available))
        else:
            self._hw_label.configure(text="Nenhuma detectada nesta máquina")
        hint(card, "Quando disponível, os encoders de hardware aparecem na aba "
                   "Conversão. Aceleração não é automaticamente mais rápida nem com a "
                   "mesma qualidade da CPU.").grid(row=6, column=0, columnspan=2,
                                                   sticky="w")

    def _build_output(self, parent: ttk.Frame) -> None:
        card = ttk.LabelFrame(parent, text="Destino e saída", style="TLabelframe",
                              padding=10)
        card.grid(row=0, column=1, sticky="nsew")
        card.columnconfigure(1, weight=1)

        self.var_mode = tk.StringVar(value="folder")
        radios = ttk.Frame(card, style="Card.TFrame")
        radios.grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(radios, text="Salvar em uma pasta de destino", value="folder",
                        variable=self.var_mode, command=self._on_mode_change
                        ).pack(anchor="w")
        ttk.Radiobutton(radios, text="Salvar ao lado do arquivo original", value="beside",
                        variable=self.var_mode, command=self._on_mode_change
                        ).pack(anchor="w")

        ttk.Label(card, text="Pasta de destino", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", pady=3)
        self.var_output = tk.StringVar()
        entry = ttk.Entry(card, textvariable=self.var_output)
        entry.grid(row=1, column=1, sticky="ew", pady=3)
        entry.bind("<FocusOut>", lambda _e: self._on_change())
        self.btn_browse = ttk.Button(card, text="Escolher…", style="Small.TButton",
                                     command=self._pick_folder)
        self.btn_browse.grid(row=1, column=2, padx=(6, 0))

        self.var_structure = tk.BooleanVar(value=True)
        self.var_overwrite = tk.BooleanVar(value=False)
        self.var_avoid = tk.BooleanVar(value=True)
        opts = ttk.Frame(card, style="Card.TFrame")
        opts.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Checkbutton(opts, text="Preservar estrutura de pastas da origem",
                        variable=self.var_structure, command=self._on_change
                        ).pack(anchor="w")
        ttk.Checkbutton(opts, text="Sobrescrever arquivos existentes", variable=self.var_overwrite,
                        command=self._on_change).pack(anchor="w")
        tooltip(opts, "Sem esta opção, nomes já existentes recebem ' (1)', ' (2)'…")
        ttk.Checkbutton(opts, text="Evitar converter arquivos já presentes na pasta de destino",
                        variable=self.var_avoid, command=self._on_change
                        ).pack(anchor="w")

        ttk.Label(card, text="Pasta de origem (raiz)", style="Card.TLabel").grid(
            row=3, column=0, sticky="w", pady=(10, 3))
        origin = ttk.Frame(card, style="Card.TFrame")
        origin.grid(row=3, column=1, columnspan=2, sticky="ew", pady=(10, 3))
        self.var_source = tk.StringVar()
        entry = ttk.Entry(origin, textvariable=self.var_source)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<FocusOut>", lambda _e: self._on_change())
        ttk.Button(origin, text="…", style="Small.TButton", width=3,
                   command=self._pick_source).pack(side="left", padx=(6, 0))
        hint(card, "Usada para calcular a hierarquia relativa e para impedir que a pasta "
                   "de destino seja varrida novamente quando estiver dentro da origem."
             ).grid(row=4, column=0, columnspan=3, sticky="w")

        self.card_output_buttons = ttk.Frame(card, style="Card.TFrame")
        self.card_output_buttons.grid(row=5, column=0, columnspan=3, sticky="ew")
        ttk.Separator(self.card_output_buttons, orient="horizontal").grid(
            row=0, column=0, columnspan=3, sticky="ew", pady=10)
        section(self.card_output_buttons, "Ações sobre a fila").grid(
            row=1, column=0, columnspan=3, sticky="w")
        actions = ttk.Frame(self.card_output_buttons, style="Card.TFrame")
        actions.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        for text, command in (
                ("Repetir erros", self._retry_errors),
                ("Remover concluídos", self._clear_finished),
                ("Recolocar tudo na fila", self._reset_all)):
            button = ttk.Button(actions, text=text, style="Small.TButton", command=command)
            button.pack(side="left", padx=(0, 6))

        ttk.Button(self.card_output_buttons, text="Diagnóstico do FFmpeg…",
                   style="Small.TButton", command=self._show_report).grid(
            row=3, column=0, sticky="w", pady=(10, 0))

    # ------------------------------------------------------------------
    def _pick_folder(self) -> None:
        folder = ask_folder(self, "Pasta de destino", self.var_output.get())
        if folder:
            self.var_output.set(folder)
            self._on_change()

    def _pick_source(self) -> None:
        folder = ask_folder(self, "Pasta de origem (raiz)", self.var_source.get())
        if folder:
            self.var_source.set(folder)
            self._on_change()

    def update_plan(self) -> None:
        """Recalcula o exemplo (usado quando a fila muda)."""
        self._update_math()

    def _on_mode_change(self) -> None:
        state = "normal" if self.var_mode.get() == "folder" else "disabled"
        try:
            self.btn_browse.configure(state=state)
        except tk.TclError:
            pass
        self._on_change()

    def _retry_errors(self) -> None:
        self.app.queue.retry_errors()
        self.app.notify("Tarefas com erro recolocadas na fila.")

    def _clear_finished(self) -> None:
        self.app.queue.clear_finished()
        self.app.notify("Tarefas concluídas removidas.")

    def _reset_all(self) -> None:
        ids = [job.id for job in self.app.queue.snapshot()
               if job.status in ("done", "error", "cancelled", "skipped")]
        if ids:
            self.app.queue.reset_jobs(ids)
            self.app.notify(f"{len(ids)} tarefas recolocadas na fila.")

    def _show_report(self) -> None:
        from .dialogs import TextDialog
        TextDialog(self, "Diagnóstico", self.app.ffmpeg_report())

    def _update_math(self) -> None:
        threads = int(self.var_threads.get() or 1)
        self.lbl_threads.configure(text=str(threads))
        concurrent_value = self.var_concurrent.get()
        per_job_value = self.var_per_job.get()
        concurrent = 0 if concurrent_value == "Automático" else int(concurrent_value)
        per_job = 0 if per_job_value == "Automático" else int(per_job_value)
        pending = max(1, sum(1 for job in self.app.queue.jobs if job.status == "pending"))
        c, p = compute_plan(threads, concurrent, per_job, pending)
        self.lbl_math.configure(
            text=f"Plano atual: {c} arquivo(s) simultâneo(s) × {p} thread(s) por "
                 f"encoder = {c * p} de {threads} threads. {'Sobra folga para o sistema.'
                 if c * p < threads else 'Orçamento totalmente utilizado.'}")
        self._on_change()

    def _on_change(self) -> None:
        if self._loading:
            return
        s = self.app.settings
        s.set("threads", int(self.var_threads.get() or 0))
        s.set("concurrent", 0 if self.var_concurrent.get() == "Automático"
              else int(self.var_concurrent.get()))
        s.set("per_job_threads", 0 if self.var_per_job.get() == "Automático"
              else int(self.var_per_job.get()))
        s.set("output_mode", self.var_mode.get())
        s.set("output_dir", self.var_output.get())
        s.set("source_root", self.var_source.get())
        s.set("preserve_structure", bool(self.var_structure.get()))
        s.set("overwrite", bool(self.var_overwrite.get()))
        self.on_change()

    def fit_to_screen(self) -> None:
        """Cede espaço vertical quando a tela é pequena (evita cortar o painel)."""
        try:
            available = self.winfo_toplevel().winfo_height()
        except tk.TclError:
            return
        if available and available < 760:
            self.card_output_buttons.pack_forget()

    def load_from_settings(self) -> None:
        self._loading = True
        s = self.app.settings
        threads = int(s.get("threads", 0) or 0) or self.cpus
        self.scale_threads.configure(to=max(1, self.cpus))
        self.var_threads.set(min(self.cpus, threads))
        concurrent = int(s.get("concurrent", 0) or 0)
        per_job = int(s.get("per_job_threads", 0) or 0)
        self.var_concurrent.set(str(concurrent) if concurrent else "Automático")
        self.var_per_job.set(str(per_job) if per_job else "Automático")
        self.var_mode.set(s.get("output_mode", "folder"))
        self.var_output.set(s.get("output_dir", ""))
        self.var_source.set(s.get("source_root", ""))
        self.var_structure.set(bool(s.get("preserve_structure", True)))
        self.var_overwrite.set(bool(s.get("overwrite", False)))
        self._loading = False
        self._update_math()
