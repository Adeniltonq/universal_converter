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
    # o ttk.Combobox (clam) reserva ~22 letras de largura natural; sem isso
    # a coluna com widgets (weight=1) fica mais larga que o rótulo e o texto
    # do cartão pode extrapolar. O mínimo fica com o próprio combobox.
    style.configure("TCombobox", width=16)
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

    # O tema "clam" dá a cada botão uma largura mínima de 10 letras — mesma fonte
    # e padding pequeno eliminam botões gigantes como "↑" e "↓".
    style.configure("TButton", background=PANEL, foreground=FG, bordercolor=BORDER,
                    focusthickness=1, focuscolor=ACCENT, padding=(8, 4),
                    width=0, font=_button_font())
    style.map("TButton",
              background=[("active", CARD), ("pressed", BORDER), ("disabled", BG_ALT)],
              foreground=[("disabled", FG_MUTED)])
    style.configure("Accent.TButton", background=ACCENT_DARK, foreground="#ffffff",
                    padding=(12, 5), font=_button_font(bold=True))
    style.map("Accent.TButton",
              background=[("active", ACCENT), ("pressed", ACCENT_DARK),
                          ("disabled", BORDER)],
              foreground=[("disabled", FG_MUTED)])
    style.configure("Danger.TButton", background=PANEL, foreground=ERROR)
    style.map("Danger.TButton", background=[("active", CARD)])
    style.configure("Tool.TButton", padding=(7, 3), font=_button_font())
    style.configure("Small.TButton", padding=(5, 2), font=_button_font())
    style.configure("Icon.TButton", padding=(2, 2), font=_button_font(bold=True),
                    width=-2)

    style.configure("TEntry", fieldbackground=BG_ALT, foreground=FG,
                    bordercolor=BORDER, padding=3)
    style.map("TEntry", bordercolor=[("focus", ACCENT)],
              fieldbackground=[("disabled", BG)])
    style.configure("TCombobox", fieldbackground=BG_ALT, foreground=FG,
                    background=PANEL, arrowcolor=FG, bordercolor=BORDER, padding=3,
                    arrowsize=14)
    # o combobox "clam" também reserva espaço extra; limitamos a largura natural
    root.option_add("*TCombobox*Listbox.background", BG_ALT)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", SEL)
    root.option_add("*TCombobox*Listbox.selectForeground", FG)
    style.map("TCombobox",
              fieldbackground=[("readonly", BG_ALT), ("disabled", BG)],
              foreground=[("disabled", FG_MUTED)],
              selectbackground=[("readonly", BG_ALT)],
              selectforeground=[("readonly", FG)])
    style.configure("TSpinbox", fieldbackground=BG_ALT, foreground=FG,
                    arrowcolor=FG, bordercolor=BORDER, padding=3,
                    arrowsize=12)
    style.configure("TCheckbutton", background=PANEL, foreground=FG)
    style.map("TCheckbutton", background=[("active", PANEL)],
              indicatorcolor=[("selected", ACCENT)])
    style.configure("Bg.TCheckbutton", background=BG, foreground=FG)
    style.map("Bg.TCheckbutton", background=[("active", BG)])
    style.configure("TRadiobutton", background=PANEL, foreground=FG)
    style.map("TRadiobutton", background=[("active", PANEL)],
              indicatorcolor=[("selected", ACCENT)])
    style.configure("TScale", background=PANEL, troughcolor=BG_ALT,
                    sliderlength=18, gripsize=8)
    style.configure("TToolbutton", background=PANEL, foreground=FG, padding=(6, 3))
    style.map("TToolbutton", background=[("selected", ACCENT_DARK), ("active", CARD)])
    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(4, 6, 4, 0))
    style.configure("TNotebook.Tab", background=BG_ALT, foreground=FG_MUTED,
                    padding=(14, 7), borderwidth=0)
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
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=8)
    style.configure("TLabelframe.Label", background=PANEL, foreground=ACCENT,
                    font=(None, 10, "bold"))
    style.configure("Card.TLabelframe", background=PANEL)
    return style


# ---------------------------------------------------------------------------
# Botões e marcações nativos (tk.*): tamanho exato em px, sem mínimo em letras
# ---------------------------------------------------------------------------

BUTTON_STYLES = {
    "TButton": (PANEL, FG, BORDER),
    "Tool.TButton": (PANEL, FG, BORDER),
    "Small.TButton": (PANEL, FG, BORDER),
    "Icon.TButton": (PANEL, FG, BORDER),
    "Accent.TButton": (ACCENT_DARK, "#ffffff", ACCENT_DARK),
    "Danger.TButton": (PANEL, ERROR, BORDER),
}


def make_button(parent: tk.Misc, text: str = "", command=None, style: str = "TButton",
                padx: int | None = None, pady: int = 4, **kw) -> tk.Button:
    """Botão compacto: o widget nativo aceita largura exata (ttk não)."""
    background, foreground, active_bg = BUTTON_STYLES.get(style, BUTTON_STYLES["TButton"])
    font = _button_font(bold=style == "Accent.TButton")
    if padx is None:
        padx = 10 if style == "Icon.TButton" else (10 if style != "Small.TButton" else 7)
    button = tk.Button(
        parent, text=text, command=command, font=font,
        background=background, foreground=foreground,
        activebackground=ACCENT if style == "Accent.TButton" else CARD,
        activeforeground="#ffffff" if style == "Accent.TButton" else FG,
        disabledforeground=FG_MUTED, relief="flat", bd=0, padx=padx, pady=pady,
        highlightthickness=1,
        highlightbackground=BORDER if style != "Accent.TButton" else ACCENT_DARK,
        highlightcolor=BORDER, cursor="hand2", takefocus=True, **kw)
    button.bind("<Enter>", lambda _e: button.configure(
        background=ACCENT if style == "Accent.TButton" else CARD), add="+")
    button.bind("<Leave>", lambda _e: button.configure(background=background), add="+")
    return button


def make_checkbutton(parent: tk.Misc, text: str, variable, command=None,
                     background: str = PANEL, **kw) -> tk.Checkbutton:
    """Marca de seleção nativa, compacta e com as cores do tema."""
    return tk.Checkbutton(
        parent, text=text, variable=variable, command=command,
        background=background, foreground=FG, activebackground=background,
        activeforeground=FG, selectcolor=BG_ALT, bd=0, highlightthickness=0,
        anchor="w", font=_button_font(), padx=0, pady=1, cursor="hand2", **kw)


def make_radiobutton(parent: tk.Misc, text: str, variable, value,
                     command=None, background: str = PANEL, **kw) -> tk.Radiobutton:
    return tk.Radiobutton(
        parent, text=text, variable=variable, value=value, command=command,
        background=background, foreground=FG, activebackground=background,
        activeforeground=FG, selectcolor=BG_ALT, bd=0, highlightthickness=0,
        anchor="w", font=_button_font(), padx=0, pady=1, cursor="hand2", **kw)


def row_height(root: tk.Misc) -> int:
    """Altura de linha usada na tabela (para virtualização)."""
    return _row_height(root)


def _button_font(bold: bool = False):
    """Fonte dos botões: a do tema (menor) evita o mínimo gigante do clam."""
    try:
        family = tkfont.nametofont("TkDefaultFont").actual().get("family")
    except tk.TclError:
        family = None
    size = 9 if sys.platform.startswith("win") else 9
    return (family, size, "bold") if bold else (family, size)


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
    """Área vertical rolável com barra automática e largura acompanhando o pai."""

    def __init__(self, parent: tk.Misc, background: str = BG, **kw):
        super().__init__(parent, style="TFrame", **kw)
        self.canvas = tk.Canvas(self, background=background, highlightthickness=0,
                                borderwidth=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas, style="TFrame")
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner.bind("<Configure>", self._on_config)
        self.canvas.bind("<Configure>", self._on_canvas)
        # roda do mouse em qualquer ponto da área (inclusive sobre campos)
        self._wheel_bound = False
        self.bind("<Enter>", self._bind_wheel, add="+")
        self.bind("<Leave>", self._unbind_wheel, add="+")
        self._refresh_scrollbar()

    def _on_config(self, event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._refresh_scrollbar()

    def _on_canvas(self, event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)
        self._refresh_scrollbar()

    def _on_scroll(self, first: str, last: str) -> None:
        self.scrollbar.set(first, last)

    def _refresh_scrollbar(self) -> None:
        """Mostra a barra só quando há conteúdo fora da área visível."""
        try:
            height = self.inner.winfo_reqheight()
            visible = self.canvas.winfo_height()
        except tk.TclError:
            return
        needed = height > visible + 2
        if needed and not self.scrollbar.winfo_ismapped():
            self.scrollbar.pack(side="right", fill="y")
        elif not needed and self.scrollbar.winfo_ismapped():
            self.scrollbar.pack_forget()

    def _bind_wheel(self, event=None) -> None:
        if not self._wheel_bound:
            self._wheel_bound = True
            self.bind_all("<MouseWheel>", self._on_wheel, add="+")
            self.bind_all("<Button-4>", self._on_wheel, add="+")
            self.bind_all("<Button-5>", self._on_wheel, add="+")

    def _unbind_wheel(self, event=None) -> None:
        if not self._wheel_bound:
            return
        self._wheel_bound = False
        self.unbind_all("<MouseWheel>")
        self.unbind_all("<Button-4>")
        self.unbind_all("<Button-5>")

    def _on_wheel(self, event) -> None:
        try:
            if event.num == 4:
                delta = -3
            elif event.num == 5:
                delta = 3
            else:
                unit = 120 if sys.platform != "darwin" else 1
                delta = -1 * int(event.delta / unit) if event.delta else 0
        except (AttributeError, ValueError, TypeError):
            return
        if not delta:
            return
        first, last = self.canvas.yview()
        if first <= 0.0 and last >= 1.0:
            return  # nada para rolar
        self.canvas.yview_scroll(delta, "units")


def _button_font(bold: bool = False):
    """Fonte dos botões: a do tema (menor) evita o mínimo gigante do clam."""
    try:
        family = tkfont.nametofont("TkDefaultFont").actual().get("family")
    except tk.TclError:
        family = None
    size = 9 if sys.platform.startswith("win") else 9
    return (family, size, "bold") if bold else (family, size)


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
        self.bind("<Enter>", self._bind_wheel)
        self.bind("<Leave>", self._unbind_wheel)
        # roda do mouse também sobre os widgets filhos
        self._wheel_bound = False

    def _on_config(self, event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)

    def _bind_wheel(self, event=None) -> None:
        self._wheel_bound = True
        self.canvas.bind_all("<MouseWheel>", self._on_wheel, add="+")
        self.canvas.bind_all("<Button-4>", self._on_wheel, add="+")
        self.canvas.bind_all("<Button-5>", self._on_wheel, add="+")

    def _unbind_wheel(self, event=None) -> None:
        if not self._wheel_bound:
            return
        self._wheel_bound = False
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


def field(parent: tk.Misc, row: int, title: str, factory, tip: str = "",
          label_style: str = "Card.TLabel", col: int = 0, sticky_widget: str = "w",
          columnspan: int = 1):
    """Cria 'Rótulo | widget' em uma grade, com largura automática.

    O widget sempre cabe: sem `width` fixo, ele parte da largura natural e
    estica conforme a coluna. Use `anchor`/`sticky` para alinhar.
    """
    if title:
        ttk.Label(parent, text=title, style=label_style).grid(
            row=row, column=col, sticky="w", padx=(0, 10), pady=3)
    widget = factory(parent)
    widget.grid(row=row, column=col + 1, columnspan=columnspan, sticky=sticky_widget,
                pady=3)
    if tip:
        tooltip(widget, tip)
    return widget


def make_columns(parent: tk.Misc, columns: int, weight: int = 1) -> None:
    for index in range(columns):
        parent.columnconfigure(index, weight=weight)


class ScrollablePanel(ScrollableFrame):
    """Aba inteira rolável: nunca corta conteúdo em janelas pequenas."""

    def __init__(self, parent: tk.Misc, **kw):
        super().__init__(parent, background=BG, **kw)

    def content(self) -> ttk.Frame:
        return self.inner


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
