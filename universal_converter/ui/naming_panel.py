"""Aba "Nomenclatura": modelo de nomes com pré-visualização ao vivo."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..media.models import NamingTemplate
from ..naming.engine import DEFAULT_PRESET_TEMPLATES, VARIABLES, validate_template
from ..naming.engine import NamingContext, NamingEngine
from . import theme
from .theme import make_button, make_checkbutton, hint, section, tooltip

CASE_OPTIONS = {"Manter como está": "keep", "minúsculas": "lower",
                "MAIÚSCULAS": "upper", "Primeira Letra Maiúscula": "title"}


class NamingPanel(ttk.Frame):
    def __init__(self, parent: tk.Misc, controller, on_change: Callable | None = None):
        super().__init__(parent, style="TFrame", padding=(12, 10))
        self.app = controller
        self.on_change = on_change or (lambda: None)
        self._loading = True
        self._sample_job = None

        header = ttk.Frame(self, style="TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="Nomenclatura", style="Title.TLabel").pack(side="left")
        self.lbl_subtitle = ttk.Label(header,
                                      text="O nome original é sempre preservado.",
                                      style="MutedBg.TLabel")
        self.lbl_subtitle.pack(side="left", padx=12)

        body = ttk.Frame(self, style="TFrame")
        body.pack(fill="both", expand=True, pady=(10, 0))
        self.body = body
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(body, text="Modelo de nome", style="TLabelframe", padding=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.left = left
        self._build_model(left)
        right = ttk.LabelFrame(body, text="Pré-visualização", style="TLabelframe",
                               padding=10)
        right.grid(row=0, column=1, sticky="nsew")
        self.right = right
        self._build_preview(right)

        self._loading = False
        self.load_from_app()
        self._stacked = False
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event) -> None:
        """Empilha os painéis em janelas estreitas (nada fica espremido)."""
        stacked = event.width < 900
        if stacked == self._stacked:
            return
        self._stacked = stacked
        body = self.body
        for child in body.grid_slaves():
            child.grid_forget()
        if stacked:
            body.columnconfigure(0, weight=1)
            body.columnconfigure(1, weight=0)
            self.left.grid(row=0, column=0, sticky="ew", padx=0)
            self.right.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        else:
            body.columnconfigure(0, weight=3)
            body.columnconfigure(1, weight=2)
            self.left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
            self.right.grid(row=0, column=1, sticky="nsew")

    # ------------------------------------------------------------------
    def _build_model(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        row = 0
        ttk.Label(parent, text="Modelo", style="Card.TLabel").grid(
            row=row, column=0, sticky="w", pady=3)
        self.var_template = tk.StringVar()
        entry = ttk.Entry(parent, textvariable=self.var_template)
        entry.grid(row=row, column=1, columnspan=2, sticky="ew", pady=3)
        tooltip(entry, "Ex.: {name}{separator}{tag} · {artist} - {title} · "
                       "{album}/{index} - {title}{separator}{ext}")
        self.var_template.trace_add("write", lambda *_a: self._on_change())

        row += 1
        presets = ttk.Frame(parent, style="Card.TFrame")
        presets.grid(row=row, column=0, columnspan=3, sticky="w", pady=(2, 8))
        for label, template in (("Nome", "{name}"), ("Nome + tag", "{name}{separator}{tag}"),
                                ("Artista - título", "{artist} - {title}"),
                                ("Álbum/número", "{album}/{index} - {title}"),
                                ("Nome + codec", "{name}_{codec}")):
            make_button(presets, label, lambda t=template: self._apply_preset(t),
                        "Small.TButton").pack(side="left", padx=(0, 4))

        row += 1
        section(parent, "Ajustes").grid(row=row, column=0, columnspan=3, sticky="w",
                                        pady=(4, 4))
        fields = [
            ("Palavra / tag", "var_tag",
             "Usada por {tag} em '{name}{separator}{tag}'. Ex.: Sepultura"),
            ("Separador", "var_separator", "Substitui {separator} no modelo."),
            ("Prefixo", "var_prefix", "Adicionado ao começo do nome."),
            ("Sufixo", "var_suffix", "Adicionado ao final do nome (antes da extensão)."),
        ]
        self.vars_extra = {}
        for title, name, tip in fields:
            row += 1
            ttk.Label(parent, text=title, style="Card.TLabel").grid(
                row=row, column=0, sticky="w", pady=3)
            var = tk.StringVar()
            widget = ttk.Entry(parent, textvariable=var, width=18)
            widget.grid(row=row, column=1, sticky="w", pady=3)
            tooltip(widget, tip)
            setattr(self, name, var)
            var.trace_add("write", lambda *_a: self._on_change())
            self.vars_extra[name] = var

        row += 1
        ttk.Label(parent, text="Substituir", style="Card.TLabel").grid(
            row=row, column=0, sticky="w", pady=3)
        repl = ttk.Frame(parent, style="Card.TFrame")
        repl.grid(row=row, column=1, columnspan=2, sticky="w", pady=3)
        self.var_replace_from = tk.StringVar()
        self.var_replace_to = tk.StringVar()
        ttk.Entry(repl, textvariable=self.var_replace_from, width=16).pack(side="left")
        ttk.Label(repl, text="→", style="Muted.TLabel").pack(side="left", padx=6)
        ttk.Entry(repl, textvariable=self.var_replace_to, width=16).pack(side="left")
        self.var_replace_from.trace_add("write", lambda *_a: self._on_change())
        self.var_replace_to.trace_add("write", lambda *_a: self._on_change())
        row += 1

        ttk.Label(parent, text="Caixa", style="Card.TLabel").grid(
            row=row, column=0, sticky="w", pady=3)
        self.var_case = tk.StringVar(value=list(CASE_OPTIONS)[0])
        combo = ttk.Combobox(parent, textvariable=self.var_case, state="readonly",
                             values=list(CASE_OPTIONS), width=26)
        combo.grid(row=row, column=1, sticky="w", pady=3)
        combo.bind("<<ComboboxSelected>>", lambda _e: self._on_change())
        row += 1

        opts = ttk.Frame(parent, style="Card.TFrame")
        opts.grid(row=row, column=0, columnspan=3, sticky="w", pady=(4, 2))
        self.var_sanitize = tk.BooleanVar(value=True)
        make_checkbutton(opts, "Remover caracteres inválidos", self.var_sanitize,
                         command=self._on_change).pack(anchor="w")
        row += 1

        num = ttk.Frame(parent, style="Card.TFrame")
        num.grid(row=row, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.var_numbering = tk.BooleanVar(value=False)
        make_checkbutton(num, "Numeração automática", self.var_numbering,
                         command=self._on_change).pack(side="left")
        self.var_number_start = tk.IntVar(value=1)
        self.var_number_padding = tk.IntVar(value=2)
        self.var_number_position = tk.StringVar(value="Prefixo")
        for title, var, width in (("início", self.var_number_start, 5),
                                  ("dígitos", self.var_number_padding, 4)):
            ttk.Label(num, text=title, style="Muted.TLabel").pack(side="left", padx=(10, 2))
            spin = ttk.Spinbox(num, from_=0, to=9999, textvariable=var, width=width,
                               command=self._on_change)
            spin.pack(side="left")
            spin.bind("<FocusOut>", lambda _e: self._on_change())
        combo = ttk.Combobox(num, textvariable=self.var_number_position, state="readonly",
                             values=["Prefixo", "Sufixo"], width=8)
        combo.pack(side="left", padx=(10, 0))
        combo.bind("<<ComboboxSelected>>", lambda _e: self._on_change())

    def _build_preview(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(2, weight=1)
        parent.columnconfigure(0, weight=1)
        self.lbl_result = ttk.Label(parent, text="", style="Card.TLabel",
                                    font=(None, 11, "bold"), wraplength=340,
                                    justify="left")
        self.lbl_result.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.lbl_warning = ttk.Label(parent, text="", style="Hint.TLabel",
                                     foreground=theme.WARN, wraplength=340)
        self.lbl_warning.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        self.preview_list = tk.Listbox(parent, background=theme.BG_ALT, foreground=theme.FG,
                                       relief="flat", highlightthickness=1,
                                       highlightbackground=theme.BORDER, activestyle="none",
                                       selectbackground=theme.SEL, height=8)
        self.preview_list.grid(row=2, column=0, sticky="nsew", pady=(0, 6))
        variables = ttk.LabelFrame(parent, text="Variáveis disponíveis",
                                   style="TLabelframe", padding=6)
        variables.grid(row=3, column=0, sticky="ew")
        text = "  ".join(f"{{{name}}}" for name, _ in VARIABLES)
        self.lbl_variables = ttk.Label(variables, text=text, style="Muted.TLabel",
                                       wraplength=340, justify="left")
        self.lbl_variables.pack(fill="x")
        self.var_sample = tk.StringVar(value="Usar o primeiro arquivo da fila")
        make_checkbutton(variables, "Pré-visualizar com o arquivo selecionado",
                         self.var_sample, command=self._on_change,
                         background=theme.PANEL).pack(anchor="w", pady=(4, 0))

    # ------------------------------------------------------------------
    def _apply_preset(self, template: str) -> None:
        self.var_template.set(template)
        self.var_tag.set(self.var_tag.get() or "Sepultura")

    def load_from_app(self) -> None:
        self._loading = True
        naming = self.app.naming
        self.var_template.set(naming.template)
        self.var_separator.set(naming.separator or "_")
        self.var_prefix.set(naming.prefix)
        self.var_suffix.set(naming.suffix)
        self.var_replace_from.set(naming.replacement_from)
        self.var_replace_to.set(naming.replacement_to)
        self.var_case.set({v: k for k, v in CASE_OPTIONS.items()}.get(naming.case,
                                                                    list(CASE_OPTIONS)[0]))
        self.var_sanitize.set(naming.sanitize)
        self.var_numbering.set(naming.numbering)
        self.var_number_start.set(naming.number_start)
        self.var_number_padding.set(naming.number_padding)
        self.var_number_position.set("Sufixo" if naming.number_position == "suffix"
                                     else "Prefixo")
        self.var_tag.set(self.app.tag)
        self._loading = False
        self._on_change()

    def collect(self) -> NamingTemplate:
        def _int(var, default):
            try:
                return int(var.get())
            except (tk.TclError, ValueError):
                return default

        return NamingTemplate(
            template=self.var_template.get().strip() or "{name}",
            separator=self.var_separator.get() or "_",
            prefix=self.var_prefix.get().strip(),
            suffix=self.var_suffix.get().strip(),
            replacement_from=self.var_replace_from.get(),
            replacement_to=self.var_replace_to.get(),
            case=CASE_OPTIONS.get(self.var_case.get(), "keep"),
            sanitize=bool(self.var_sanitize.get()),
            numbering=bool(self.var_numbering.get()),
            number_start=_int(self.var_number_start, 1),
            number_padding=max(1, _int(self.var_number_padding, 2)),
            number_position="suffix" if self.var_number_position.get() == "Sufixo"
            else "prefix",
        )

    def _on_change(self) -> None:
        if self._loading:
            return
        naming = self.collect()
        self.app.naming = naming
        self.app.tag = self.var_tag.get()
        used, unknown = validate_template(naming.template)
        warnings = []
        if unknown:
            warnings.append("Variável desconhecida: " + ", ".join(unknown))
        if "{ext}" not in naming.template and "." not in naming.template:
            warnings.append("A extensão será adicionada automaticamente.")
        self.lbl_warning.configure(text="\n".join(warnings))
        self._update_preview(naming)
        self.on_change()

    def _update_preview(self, naming: NamingTemplate) -> None:
        engine = NamingEngine(naming)
        jobs = self.app.queue.snapshot()
        sample_info = None
        sample_job = None
        if self.var_sample.get() and jobs:
            sample_job = self.app.queue.job(self.app.selected_id[0]) \
                if getattr(self.app, "selected_id", None) else jobs[0]
            sample_info = self.app.analyzer.analyze(sample_job.file)
        if sample_job is None and jobs:
            sample_job = jobs[0]
            sample_info = self.app.analyzer.analyze(sample_job.file)
        if sample_job is not None and sample_info is not None:
            from ..media.command_builder import CommandBuilder
            builder = CommandBuilder(self.app.catalog)
            container = builder.effective_container(sample_job.config, sample_info)
            extension = builder.output_extension(container, sample_job.config.kind)
            context = NamingContext(path=sample_job.file, info=sample_info,
                                    config=sample_job.config, index=1,
                                    tag=self.var_tag.get(), extension=extension)
            result = engine.preview(context, naming)
            self.lbl_result.configure(text=result)
        else:
            self.lbl_result.configure(text="(adicione arquivos para pré-visualizar)")

        self.preview_list.delete(0, "end")
        for index, (job, path, warning) in enumerate(self.app.plan_preview()[:80], start=1):
            name = os.path.basename(path)
            self.preview_list.insert("end", f"{index:>3}. {name}")
            if warning:
                self.preview_list.itemconfig(index - 1, foreground=theme.WARN)
        if self.preview_list.size() == 0:
            self.preview_list.insert("end", "(sem arquivos na fila)")

    def refresh_preview(self) -> None:
        self._update_preview(self.collect())
