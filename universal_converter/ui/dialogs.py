"""Diálogos e janelas auxiliares (somente tkinter/tkinter.ttk)."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from ..media.models import MediaInfo, StreamInfo
from ..media.codecs import INPUT_CODEC_LABEL
from . import theme


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class ModalDialog(tk.Toplevel):
    """Janela modal com botões padrão no rodapé."""

    def __init__(self, parent: tk.Misc, title: str, width: int = 520,
                 height: int = 360, resizable: bool = False):
        super().__init__(parent)
        self.title(title)
        self.transient(parent.winfo_toplevel())
        self.configure(background=theme.BG)
        self.resizable(resizable, resizable)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        theme.center_window(self, width, height, parent)
        self.body = ttk.Frame(self, style="TFrame", padding=14)
        self.body.pack(fill="both", expand=True)
        self.button_bar = ttk.Frame(self, style="TFrame", padding=(14, 0, 14, 12))
        self.button_bar.pack(fill="x")
        self.result = None
        self.bind("<Escape>", lambda _e: self.cancel())

    def add_button(self, text: str, command: Callable | None = None, style: str = "TButton",
                   default: bool = False) -> ttk.Button:
        button = ttk.Button(self.button_bar, text=text, style=style,
                            command=command or (self.ok if default else self.cancel))
        button.pack(side="right", padx=(6, 0))
        if default:
            button.bind("<Return>", lambda _e: button.invoke())
        return button

    def ok(self) -> None:
        self.destroy()

    def cancel(self) -> None:
        self.destroy()

    def show(self):
        self.grab_set()
        self.wait_window()
        return self.result


# ---------------------------------------------------------------------------
# Análise de arquivo
# ---------------------------------------------------------------------------

class MediaInfoDialog(ModalDialog):
    """Mostra tudo o que foi identificado sobre um arquivo."""

    def __init__(self, parent: tk.Misc, info: MediaInfo):
        super().__init__(parent, f"Propriedades — {os.path.basename(info.path)}", 760, 620,
                         resizable=True)
        self.info = info
        ttk.Label(self.body, text=os.path.basename(info.path), style="BgTitle.TLabel"
                  ).pack(anchor="w")
        ttk.Label(self.body, text=info.path, style="MutedBg.TLabel").pack(anchor="w",
                                                                         pady=(0, 8))

        notebook = ttk.Notebook(self.body)
        notebook.pack(fill="both", expand=True)

        overview = ttk.Frame(notebook, style="Card.TFrame", padding=10)
        notebook.add(overview, text="Visão geral")
        rows = [
            ("Contêiner", info.format_label() + (f" ({info.format_name})"
                                                  if info.format_name else "")),
            ("Duração", _dur(info.duration)),
            ("Tamanho", _size(info.size)),
            ("Bitrate total", _rate(info.bitrate)),
            ("Streams de vídeo", str(len(info.video_streams))),
            ("Streams de áudio", str(len(info.audio_streams))),
            ("Legendas", str(len(info.subtitle_streams))),
            ("Streams de dados", str(len(info.by_type("data")))),
            ("Capítulos", str(info.chapters)),
            ("Capa embutida", "Sim" if info.cover_streams else "Não"),
        ]
        if info.error:
            rows.insert(0, ("Aviso", info.error))
        _grid_rows(overview, rows)

        streams_tab = ttk.Frame(notebook, style="Card.TFrame")
        notebook.add(streams_tab, text=f"Streams ({len(info.streams)})")
        columns = ("index", "type", "codec", "profile", "channels", "rate", "resolution",
                   "fps", "layout", "bitrate", "lang")
        tree = ttk.Treeview(streams_tab, columns=columns, show="headings",
                            selectmode="browse")
        headings = {
            "index": "#", "type": "Tipo", "codec": "Codec", "profile": "Perfil",
            "channels": "Canais", "rate": "Sample rate", "resolution": "Resolução",
            "fps": "FPS", "layout": "Layout", "bitrate": "Bitrate", "lang": "Idioma",
        }
        widths = {"index": 36, "type": 80, "codec": 110, "profile": 90, "channels": 60,
                  "rate": 90, "resolution": 90, "fps": 60, "layout": 100,
                  "bitrate": 90, "lang": 50}
        for column in columns:
            tree.heading(column, text=headings[column])
            tree.column(column, width=widths[column], anchor="w", stretch=True)
        for stream in info.streams:
            tree.insert("", "end", values=(
                stream.index,
                "imagem" if stream.is_cover else stream.type,
                INPUT_CODEC_LABEL.get(stream.codec, stream.codec),
                _profile(stream),
                stream.channels or "",
                f"{stream.sample_rate} Hz" if stream.sample_rate else "",
                f"{stream.width}×{stream.height}" if stream.width else "",
                f"{stream.fps:.3f}".rstrip("0").rstrip(".") if stream.fps else "",
                stream.channel_layout,
                _rate(stream.bitrate) if stream.bitrate else "",
                stream.language if stream.language not in ("und", "un") else "",
            ))
        _scroll_tree(tree)
        tree.pack(fill="both", expand=True)

        tags_tab = ttk.Frame(notebook, style="Card.TFrame", padding=10)
        notebook.add(tags_tab, text="Metadados")
        if info.tags:
            _grid_rows(tags_tab, [(k, v) for k, v in sorted(info.tags.items())])
        else:
            ttk.Label(tags_tab, text="Nenhum metadado encontrado.", style="Muted.TLabel"
                      ).pack(anchor="w")

        self.add_button("Fechar", self.cancel, default=True)


def _profile(stream: StreamInfo) -> str:
    parts = [stream.profile] if stream.profile else []
    if stream.level not in (None, "", -99):
        parts.append(f"nível {stream.level}")
    if stream.is_hdr:
        parts.append("HDR")
    if stream.pix_fmt:
        parts.append(stream.pix_fmt)
    return " · ".join(parts)


def _grid_rows(parent: tk.Misc, rows: list[tuple[str, str]]) -> None:
    for index, (key, value) in enumerate(rows):
        ttk.Label(parent, text=key, style="Muted.TLabel").grid(
            row=index, column=0, sticky="nw", padx=(0, 14), pady=2)
        ttk.Label(parent, text=str(value), style="Card.TLabel", wraplength=520
                  ).grid(row=index, column=1, sticky="nw", pady=2)


def _scroll_tree(tree: ttk.Treeview) -> None:
    scroll = ttk.Scrollbar(tree.master, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")


def _dur(value: float | None) -> str:
    from ..core.util import fmt_duration
    return fmt_duration(value)


def _size(value: float | None) -> str:
    from ..core.util import fmt_size
    return fmt_size(value)


def _rate(value: float | None) -> str:
    from ..core.util import fmt_bitrate
    return fmt_bitrate(value)


# ---------------------------------------------------------------------------
# Escolha de pastas / arquivos
# ---------------------------------------------------------------------------

def ask_folder(parent: tk.Misc, title: str, initial: str = "") -> str:
    return filedialog.askdirectory(parent=parent, title=title,
                                   initialdir=initial or None, mustexist=False)


def ask_files(parent: tk.Misc, title: str = "Adicionar arquivos",
              initial: str = "") -> tuple[str, ...]:
    from ..media.codecs import INPUT_EXT
    patterns = " ".join(f"*.{ext}" for ext in sorted(INPUT_EXT))
    return filedialog.askopenfilenames(
        parent=parent, title=title, initialdir=initial or None,
        filetypes=[("Mídia (áudio e vídeo)", patterns), ("Todos os arquivos", "*")])


# ---------------------------------------------------------------------------
# Adicionar pasta
# ---------------------------------------------------------------------------

class FolderImportDialog(ModalDialog):
    """Opções de importação de uma pasta."""

    def __init__(self, parent: tk.Misc, folder: str, current: dict):
        super().__init__(parent, "Adicionar pasta", 580, 470)
        self.folder = folder
        self.result = None
        ttk.Label(self.body, text="Pasta de origem", style="BgTitle.TLabel"
                  ).pack(anchor="w")
        ttk.Label(self.body, text=folder, style="MutedBg.TLabel", wraplength=540
                  ).pack(anchor="w", pady=(0, 10))

        options = ttk.Frame(self.body, style="TFrame")
        options.pack(fill="x")
        self.var_recursive = tk.BooleanVar(value=bool(current.get("recursive", True)))
        self.var_hidden = tk.BooleanVar(value=bool(current.get("include_hidden", False)))
        self.var_limit = tk.StringVar(value=str(current.get("max_files", 0) or 0))
        for text, var in (("Incluir subpastas", self.var_recursive),
                          ("Incluir arquivos ocultos", self.var_hidden)):
            ttk.Checkbutton(options, text=text, variable=var, style="Bg.TCheckbutton"
                            ).pack(anchor="w", pady=2)

        form = ttk.Frame(options, style="TFrame")
        form.pack(fill="x", pady=(8, 0))
        ttk.Label(form, text="Extensões (separadas por vírgula; vazio = todas)",
                  style="MutedBg.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        self.var_exts = tk.StringVar(value=current.get("extensions", ""))
        ttk.Entry(form, textvariable=self.var_exts, width=48).grid(
            row=1, column=0, columnspan=3, sticky="ew", pady=(2, 6))
        ttk.Label(form, text="Excluir (padrões glob, um por linha)", style="MutedBg.TLabel"
                  ).grid(row=2, column=0, columnspan=3, sticky="w")
        self.exclude_text = tk.Text(form, height=3, background=theme.BG_ALT,
                                    foreground=theme.FG, insertbackground=theme.FG,
                                    relief="flat", highlightthickness=1,
                                    highlightbackground=theme.BORDER, width=50)
        self.exclude_text.insert("1.0", current.get("exclude", ""))
        self.exclude_text.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(2, 6))
        ttk.Label(form, text="Pasta de destino (opcional, só estes arquivos)",
                  style="MutedBg.TLabel").grid(row=4, column=0, sticky="w")
        self.var_output = tk.StringVar(value=current.get("output_dir", ""))
        ttk.Entry(form, textvariable=self.var_output, width=40).grid(
            row=5, column=0, sticky="ew", pady=(2, 0))
        ttk.Button(form, text="Escolher…", style="Small.TButton",
                   command=self._pick_output).grid(row=5, column=1, padx=4)
        form.columnconfigure(0, weight=1)

        self.summary = ttk.Label(self.body, text="", style="MutedBg.TLabel",
                                 wraplength=540)
        self.summary.pack(anchor="w", pady=(10, 0))
        self.add_button("Cancelar", self.cancel)
        self.add_button("Contar arquivos", self._scan, default=False)
        self.add_button("Adicionar", self.ok, style="Accent.TButton", default=True)

    def _pick_output(self) -> None:
        folder = ask_folder(self, "Pasta de destino", self.var_output.get())
        if folder:
            self.var_output.set(folder)

    def _options(self) -> dict:
        return {
            "recursive": self.var_recursive.get(),
            "include_hidden": self.var_hidden.get(),
            "extensions": self.var_exts.get().strip(),
            "exclude": self.exclude_text.get("1.0", "end").strip(),
            "output_dir": self.var_output.get().strip(),
            "max_files": 0,
        }

    def _scan(self) -> None:
        from ..filesystem.scanner import ScanOptions, scan_folder
        from ..media.codecs import INPUT_EXT
        opts = self._options()
        exts = opts["extensions"]
        extensions = ({e.strip().lstrip(".").lower() for e in exts.split(",") if
                       e.strip()} if exts else set(INPUT_EXT))
        options = ScanOptions(
            recursive=opts["recursive"],
            extensions=extensions,
            include_hidden=opts["include_hidden"],
            exclude_patterns=[line.strip() for line in opts["exclude"].splitlines()
                              if line.strip()],
            output_dir=opts["output_dir"])
        result = scan_folder(self.folder, options)
        total = 0
        for path in result.files[:500]:
            try:
                total += os.path.getsize(path)
            except OSError:
                pass
        self.summary.configure(
            text=(f"{len(result.files)} arquivos de mídia encontrados "
                  f"(≈ {_size(total)}). Até 3 sinalizações de erro ignoradas: "
                  f"{len(result.errors)}."))

    def ok(self) -> None:
        self.result = self._options()
        self.destroy()


# ---------------------------------------------------------------------------
# Confirmação simples
# ---------------------------------------------------------------------------

def confirm(parent: tk.Misc, title: str, message: str) -> bool:
    return messagebox.askyesno(title, message, parent=parent)


def info(parent: tk.Misc, title: str, message: str) -> None:
    messagebox.showinfo(title, message, parent=parent)


def error(parent: tk.Misc, title: str, message: str) -> None:
    messagebox.showerror(title, message, parent=parent)


def warn(parent: tk.Misc, title: str, message: str) -> None:
    messagebox.showwarning(title, message, parent=parent)


def ask_string(parent: tk.Misc, title: str, prompt: str, initial: str = "") -> str | None:
    dialog = _StringDialog(parent, title, prompt, initial)
    return dialog.show()


class _StringDialog(ModalDialog):
    def __init__(self, parent, title, prompt, initial):
        super().__init__(parent, title, 460, 170)
        ttk.Label(self.body, text=prompt, style="Card.TLabel", wraplength=420
                  ).pack(anchor="w")
        self.var = tk.StringVar(value=initial)
        entry = ttk.Entry(self.body, textvariable=self.var, width=54)
        entry.pack(fill="x", pady=10)
        entry.focus_set()
        entry.select_range(0, "end")
        self.add_button("Cancelar", self.cancel)
        self.add_button("OK", self.ok, style="Accent.TButton", default=True)

    def ok(self) -> None:
        self.result = self.var.get()
        self.destroy()


# ---------------------------------------------------------------------------
# Texto longo (comandos, logs)
# ---------------------------------------------------------------------------

class TextDialog(ModalDialog):
    def __init__(self, parent: tk.Misc, title: str, content: str):
        super().__init__(parent, title, 820, 560, resizable=True)
        frame = ttk.Frame(self.body, style="TFrame")
        frame.pack(fill="both", expand=True)
        text = tk.Text(frame, wrap="none", background=theme.BG_ALT, foreground=theme.FG,
                       insertbackground=theme.FG, relief="flat",
                       highlightthickness=1, highlightbackground=theme.BORDER)
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        text.insert("1.0", content)
        text.configure(state="disabled")

        def copy_all() -> None:
            self.clipboard_clear()
            self.clipboard_append(content)

        self.add_button("Fechar", self.cancel, default=True)
        self.add_button("Copiar", copy_all)
