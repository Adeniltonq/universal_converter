"""Tema visual e utilitários de widgets Tkinter (somente biblioteca padrão)."""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# Paleta -------------------------------------------------------------------
BG = "#1e2227"
BG_ALT = "#262b31"
PANEL = "#2b3138"
CARD = "#323941"
FG = "#e6edf3"
FG_MUTED = "#9aa7b4"
BORDER = "#3d454f"
ACCENT = "#3ea6ff"
ACCENT_DARK = "#2b86d4"
OK = "#3fb950"
WARN = "#d29922"
ERROR = "#f85149"
INFO = "#58a6ff"
SEL = "#2f4b63"

STATUS_COLORS = {
    "pending": FG_MUTED,
    "analyzing": INFO,
    "running": ACCENT,
    "done": OK,
    "error": ERROR,
    "cancelled": WARN,
    "skipped": FG_MUTED,
}

# Tamanho de fonte padrão um pouco maior em telas de alta densidade
def base_fonts(root: tk.Misc) -> None:
    if sys.platform == "darwin":
        size = 13
    elif sys.platform.startswith("win"):
        size = 9
    else:
        size = 10
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont",
                 "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont"):
        try:
            tkfont.nametofont(name).configure(size=size)
        except tk.TclError:
            continue
    try:
        tkfont.nametofont("TkFixedFont").configure(size=size)
    except tk.TclError:
        pass


def apply_theme(root: tk.Tk) -> ttk.Style:
    base_fonts(root)
    style = ttk.Style(root)
    for theme in ("clam", "alt", "default"):
        if theme in style.theme_names():
            style.theme_use(theme)
            break

    try:
        root.configure(background=BG)
    except tk.TclError:
        pass

    style.configure(".", background=BG, foreground=FG, fieldbackground=BG_ALT,
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                    troughcolor=BG_ALT, selectbackground=SEL, selectforeground=FG,
                    insertcolor=FG)
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=PANEL, relief="flat")
    style.configure("Toolbar.TFrame", background=BG_ALT)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("Card.TLabel", background=PANEL, foreground=FG)
    style.configure("Muted.TLabel", background=PANEL, foreground=FG_MUTED)
    style.configure("MutedBg.TLabel", background=BG, foreground=FG_MUTED)
    style.configure("Title.TLabel", background=BG, foreground=FG,
                    font=(None, 13, "bold"))
    style.configure("BgTitle.TLabel", background=BG, foreground=FG,
                    font=(None, 13, "bold"))
    style.configure("Section.TLabel", background=PANEL, foreground=ACCENT,
                    font=(None, 10, "bold"))
    style.configure("Big.TLabel", background=BG, foreground=FG,
                    font=(None, 16, "bold"))
    style.configure("Hint.TLabel", background=PANEL, foreground=FG_MUTED,
                    wraplength=520, justify="left")

    style.configure("TButton", background=PANEL, foreground=FG, bordercolor=BORDER,
                    focusthickness=1, focuscolor=ACCENT, padding=(10, 5))
    style.map("TButton",
              background=[("active", CARD), ("pressed", BORDER), ("disabled", BG_ALT)],
              foreground=[("disabled", FG_MUTED)])
    style.configure("Accent.TButton", background=ACCENT_DARK, foreground="#ffffff",
                    padding=(14, 6), font=(None, 10, "bold"))
    style.map("Accent.TButton",
              background=[("active", ACCENT), ("pressed", ACCENT_DARK),
                          ("disabled", BORDER)],
              foreground=[("disabled", FG_MUTED)])
    style.configure("Danger.TButton", background=PANEL, foreground=ERROR)
    style.map("Danger.TButton", background=[("active", CARD)])
    style.configure("Tool.TButton", padding=(8, 3))
    style.configure("Small.TButton", padding=(6, 2))

    style.configure("TEntry", fieldbackground=BG_ALT, foreground=FG,
                    bordercolor=BORDER, padding=3)
    style.map("TEntry", bordercolor=[("focus", ACCENT)],
              fieldbackground=[("disabled", BG)])
    style.configure("TCombobox", fieldbackground=BG_ALT, foreground=FG,
                    background=PANEL, arrowcolor=FG, bordercolor=BORDER, padding=3)
    style.map("TCombobox",
              fieldbackground=[("readonly", BG_ALT), ("disabled", BG)],
              foreground=[("disabled", FG_MUTED)],
              selectbackground=[("readonly", BG_ALT)],
              selectforeground=[("readonly", FG)])
    style.configure("TSpinbox", fieldbackground=BG_ALT, foreground=FG,
                    arrowcolor=FG, bordercolor=BORDER, padding=3)
    style.configure("TCheckbutton", background=PANEL, foreground=FG)
    style.map("TCheckbutton", background=[("active", PANEL)],
              indicatorcolor=[("selected", ACCENT)])
    style.configure("Bg.TCheckbutton", background=BG, foreground=FG)
    style.map("Bg.TCheckbutton", background=[("active", BG)])
    style.configure("TRadiobutton", background=PANEL, foreground=FG)
    style.map("TRadiobutton", background=[("active", PANEL)],
              indicatorcolor=[("selected", ACCENT)])
    style.configure("TScale", background=PANEL, troughcolor=BG_ALT)
    style.configure("TToolbutton", background=PANEL, foreground=FG, padding=(6, 3))
    style.map("TToolbutton", background=[("selected", ACCENT_DARK), ("active", CARD)])
    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(4, 6, 4, 0))
    style.configure("TNotebook.Tab", background=BG_ALT, foreground=FG_MUTED,
                    padding=(16, 8), borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", PANEL), ("active", CARD)],
              foreground=[("selected", FG), ("active", FG)],
              expand=[("selected", (0, 0, 0, 0))])
    style.configure("TPanedwindow", background=BG)
    style.configure("TSeparator", background=BORDER)

    style.configure("Treeview", background=BG_ALT, fieldbackground=BG_ALT,
                    foreground=FG, bordercolor=BORDER, rowheight=_row_height(root),
                    borderwidth=0)
    style.configure("Treeview.Heading", background=PANEL, foreground=FG_MUTED,
                    relief="flat", padding=(6, 4), font=(None, 9, "bold"))
    style.map("Treeview.Heading", background=[("active", CARD)],
              foreground=[("active", FG)])
    style.map("Treeview", background=[("selected", SEL)], foreground=[("selected", FG)])
    style.configure("TProgressbar", background=ACCENT, troughcolor=BG_ALT,
                    bordercolor=BORDER, lightcolor=ACCENT, darkcolor=ACCENT_DARK,
                    thickness=_row_height(root))
    style.configure("Vertical.TScrollbar", background=CARD, troughcolor=BG,
                    arrowcolor=FG_MUTED, bordercolor=BG)
    style.map("Vertical.TScrollbar", background=[("active", BORDER)])
    style.configure("Horizontal.TScrollbar", background=CARD, troughcolor=BG,
                    arrowcolor=FG_MUTED, bordercolor=BG)
    style.configure("Status.TLabel", background=BG_ALT, foreground=FG_MUTED,
                    padding=(8, 4))
    style.configure("StatusAccent.TLabel", background=BG_ALT, foreground=FG,
                    padding=(8, 4))
    style.configure("TLabelframe", background=PANEL, foreground=ACCENT,
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
    style.configure("TLabelframe.Label", background=PANEL, foreground=ACCENT,
                    font=(None, 10, "bold"))
    style.configure("Card.TLabelframe", background=PANEL)
    return style


def row_height(root: tk.Misc) -> int:
    """Altura de linha usada na tabela (para virtualização)."""
    return _row_height(root)


def _row_height(root: tk.Misc) -> int:
    try:
        linespace = tkfont.nametofont("TkDefaultFont").metrics("linespace")
    except tk.TclError:
        linespace = 16
    return max(22, linespace + 8)


def card(parent: tk.Misc, **pack_kw) -> ttk.Frame:
    frame = ttk.Frame(parent, style="Card.TFrame", padding=12)
    if pack_kw:
        frame.pack(**pack_kw)
    return frame


def label(parent: tk.Misc, text: str = "", style: str = "Card.TLabel",
          **kw) -> ttk.Label:
    return ttk.Label(parent, text=text, style=style, **kw)


def section(parent: tk.Misc, title: str) -> ttk.Label:
    return ttk.Label(parent, text=title.upper(), style="Section.TLabel")


def hint(parent: tk.Misc, text: str, wrap: int = 520) -> ttk.Label:
    return ttk.Label(parent, text=text, style="Hint.TLabel", wraplength=wrap)


def tooltip(widget: tk.Widget, text: str, delay: int = 500) -> None:
    """Dica (tooltip) nativa para qualquer widget."""
    state: dict = {"id": None, "window": None, "count": 0}

    def show(event=None) -> None:
        hide()
        try:
            x = widget.winfo_rootx() + 14
            y = widget.winfo_rooty() + widget.winfo_height() + 6
        except tk.TclError:
            return
        window = tk.Toplevel(widget)
        window.wm_overrideredirect(True)
        window.wm_geometry(f"+{x}+{y}")
        try:
            window.attributes("-topmost", True)
        except tk.TclError:
            pass
        frame = tk.Frame(window, background=CARD, highlightbackground=BORDER,
                         highlightthickness=1)
        frame.pack()
        tk.Label(frame, text=text, background=CARD, foreground=FG, justify="left",
                 padx=8, pady=5, wraplength=380).pack()
        state["window"] = window

    def hide(event=None) -> None:
        if state["id"]:
            widget.after_cancel(state["id"])
            state["id"] = None
        window = state["window"]
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass
            state["window"] = None

    def schedule(event=None) -> None:
        hide()
        state["id"] = widget.after(delay, show)

    widget.bind("<Enter>", schedule, add="+")
    widget.bind("<Leave>", hide, add="+")
    widget.bind("<ButtonPress>", hide, add="+")


def center_window(window: tk.Misc, width: int, height: int,
                  parent: tk.Misc | None = None) -> None:
    window.update_idletasks()
    if parent is not None:
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            x = px + max(0, (pw - width) // 2)
            y = py + max(0, (ph - height) // 3)
            window.geometry(f"{width}x{height}+{x}+{y}")
            return
        except tk.TclError:
            pass
    screen_w = window.winfo_screenwidth()
    screen_h = window.winfo_screenheight()
    x = max(0, (screen_w - width) // 2)
    y = max(0, (screen_h - height) // 3)
    window.geometry(f"{width}x{height}+{x}+{y}")


class ScrollableFrame(ttk.Frame):
    """Área vertical rolável com largura automática."""

    def __init__(self, parent: tk.Misc, background: str = BG, **kw):
        super().__init__(parent, style="TFrame", **kw)
        self.canvas = tk.Canvas(self, background=background, highlightthickness=0,
                                borderwidth=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas, style="TFrame")
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._on_config)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)

    def _on_config(self, event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)

    def _bind_wheel(self, event=None) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)
        self.canvas.bind_all("<Button-4>", self._on_wheel)
        self.canvas.bind_all("<Button-5>", self._on_wheel)

    def _unbind_wheel(self, event=None) -> None:
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_wheel(self, event) -> None:
        try:
            if event.num == 4:
                delta = -3
            elif event.num == 5:
                delta = 3
            else:
                delta = -1 * int(event.delta / (120 if sys.platform != "darwin" else 1))
        except (AttributeError, ValueError):
            return
        self.canvas.yview_scroll(delta, "units")


class LabeledRow:
    """Linha 'rótulo: valor' padronizada para os painéis."""

    def __init__(self, parent: tk.Misc, title: str, widget_factory, tip: str = "",
                 row: int = 0, col: int = 0):
        self.label = ttk.Label(parent, text=title, style="Card.TLabel")
        self.label.grid(row=row, column=col, sticky="w", padx=(0, 10), pady=3)
        self.widget = widget_factory(parent)
        self.widget.grid(row=row, column=col + 1, sticky="ew", pady=3)
        if tip:
            tooltip(self.widget, tip)
            tooltip(self.label, tip)


def bind_combobox_search(combo: ttk.Combobox) -> None:
    """Filtra opções digitando no combobox (modo "normal")."""
    state = {"all": list(combo.cget("values"))}

    def on_key(_event) -> None:
        typed = combo.get().lower()
        combo.configure(values=state["all"])
        if not typed:
            return
        matches = [v for v in state["all"] if typed in str(v).lower()]
        if matches:
            combo.configure(values=matches)

    combo.bind("<KeyRelease>", on_key, add="+")
