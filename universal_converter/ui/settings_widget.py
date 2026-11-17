"""Aba "Conversão": contêiner, áudio, vídeo, extração e prévia do resultado.

O layout se adapta a qualquer janela:

* abas internas agrupam Áudio / Vídeo / Extração — nada fica fora da tela;
* larguras são automáticas (as colunas esticam), sem `width` fixo;
* cada aba interna rola verticalmente quando o conteúdo não cabe.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..media.catalog import AudioOption, VideoOption
from ..media.codecs import (
    AUDIO_CODECS, AUDIO_CONTAINER_KEYS, CHANNELS, CODEC_COPY, CODEC_NONE, CONTAINERS,
    PIXEL_FORMATS, VIDEO_CODECS, VIDEO_CONTAINER_KEYS, VIDEO_LEVELS, VIDEO_PRESETS,
    VIDEO_PROFILES,
)
from ..media.models import AudioSettings, VideoSettings
from ..naming.engine import NamingContext, NamingEngine
from . import theme
from .theme import BG
from .theme import (
    ScrollableFrame, field, hint, make_button, make_checkbutton, make_radiobutton,
    section, tooltip,
)

RESOLUTION_PRESETS = [
    "Manter original", "3840x2160", "2560x1440", "1920x1080", "1280x720", "1024x576",
    "854x480", "640x360", "480x360", "Personalizada…",
]
FPS_PRESETS = ["Manter original", "23.976", "24", "25", "29.97", "30", "50", "59.94", "60",
               "120"]
SAMPLE_RATES = ["Manter original", "8000", "11025", "16000", "22050", "24000", "32000",
                "44100", "48000", "88200", "96000", "176400", "192000"]
BITRATE_PRESETS = ["64", "96", "112", "128", "160", "192", "224", "256", "320"]
VIDEO_BITRATE_PRESETS = ["Automático", "500k", "1M", "1.5M", "2M", "3M", "4M", "6M", "8M",
                         "12M", "20M"]


class ConversionPanel(ttk.Frame):
    """Painel de configuração de conversão."""

    def __init__(self, parent: tk.Misc, controller, on_change: Callable | None = None):
        super().__init__(parent, style="TFrame", padding=(10, 8))
        self.app = controller
        self.catalog = controller.catalog
        self.on_change = on_change or (lambda: None)
        self._loading = False
        self._selected_job_ids: list[int] = []
        self._channel_key = "keep"
        self._stream_map: dict[str, str] = {}
        self._audio_option_map: dict[str, AudioOption] = {}
        self._video_option_map: dict[str, VideoOption] = {}
        self._audio_container_map: dict[str, str] = {}
        self._video_container_map: dict[str, str] = {}

        self._build_header()
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, pady=(6, 0))
        self._tab_scroller = None

        self.audio_tab = self._make_tab(" Áudio ")
        self._build_audio(self.audio_tab.inner)
        self.video_tab = self._make_tab(" Vídeo ")
        self._build_video(self.video_tab.inner)
        self.extract_tab = self._make_tab(" Extração ")
        self._build_extraction(self.extract_tab.inner)

        self._build_footer()
        self.load_from_app()
        self.update_visibility()

    # ------------------------------------------------------------------
    # Estrutura
    # ------------------------------------------------------------------
    def _make_tab(self, title: str) -> ScrollableFrame:
        holder = ttk.Frame(self.notebook, style="TFrame")
        self.notebook.add(holder, text=title)
        scroller = ScrollableFrame(holder, background=theme.PANEL)
        scroller.pack(fill="both", expand=True)
        content = scroller.inner
        content.configure(style="Card.TFrame")
        content.columnconfigure(0, weight=1)
        return scroller

    def _build_header(self) -> None:
        header = ttk.Frame(self, style="TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="Conversão", style="Title.TLabel").pack(side="left")

        right = ttk.Frame(header, style="TFrame")
        right.pack(side="right")
        self.var_profile = tk.StringVar()
        self.combo_profile = ttk.Combobox(right, textvariable=self.var_profile,
                                          state="readonly", width=30)
        self.combo_profile.pack(side="right")
        self.combo_profile.bind("<<ComboboxSelected>>", self._on_profile_selected)
        ttk.Label(right, text="Perfil", style="MutedBg.TLabel").pack(side="right",
                                                                    padx=(0, 6))
        self.btn_save_profile = make_button(right, "Salvar perfil…",
                                            style="Small.TButton",
                                            command=self._save_as_profile)
        self.btn_save_profile.pack(side="right", padx=(8, 8))
        self.var_apply_selected = tk.BooleanVar(value=False)
        make_checkbutton(right, "Só selecionados", self.var_apply_selected,
                         background=BG).pack(side="right", padx=(0, 8))
        self.refresh_profiles()

    def _card(self, parent: ttk.Frame) -> ttk.Frame:
        card = ttk.Frame(parent, style="Card.TFrame", padding=(10, 4, 12, 8))
        card.pack(fill="x", pady=(0, 6))
        card.columnconfigure(1, weight=1)
        card.columnconfigure(2, weight=0)
        return card

    def refresh_profiles(self) -> None:
        profiles = self.app.profiles.all()
        self._profile_map = {self._profile_label(p): p.id for p in profiles}
        self.combo_profile.configure(values=list(self._profile_map))
        current = self.app.profiles.find(self.app.current_profile)
        self.var_profile.set(self._profile_label(current) if current else "")

    @staticmethod
    def _profile_label(profile) -> str:
        kind = "Áudio" if profile.kind == "audio" else "Vídeo"
        suffix = " · pronto" if profile.builtin else ""
        return f"{profile.name} — {kind}{suffix}"

    def _on_profile_selected(self, _event=None) -> None:
        profile_id = self._profile_map.get(self.var_profile.get())
        profile = self.app.profiles.find(profile_id) if profile_id else None
        if not profile:
            return
        self.app.apply_profile(profile)
        self.load_from_app()
        self.notify("Perfil aplicado: " + profile.name)

    def _save_as_profile(self) -> None:
        from .dialogs import ask_string
        name = ask_string(self, "Salvar perfil", "Nome do perfil:", "Meu perfil")
        if not name:
            return
        profile = self.app.profiles.from_config(name.strip(), self.app.config_snapshot())
        existing = self.app.profiles.find(self.app.current_profile)
        if existing and not existing.builtin:
            profile.id = existing.id
        self.app.profiles.upsert(profile)
        self.app.current_profile = profile.id
        self.refresh_profiles()
        self.notify(f"Perfil \"{profile.name}\" salvo.")

    def set_selected_jobs(self, job_ids: list[int]) -> None:
        self._selected_job_ids = list(job_ids)

    # ------------------------------------------------------------------
    # Áudio
    # ------------------------------------------------------------------
    def _combo(self, parent, values=None, width=34, readonly=True,
               var=None) -> ttk.Combobox:
        combo = ttk.Combobox(parent, values=values or (), textvariable=var,
                             state="readonly" if readonly else "normal", width=width)
        # impede que a largura natural do combobox (largura do maior item)
        # estique a coluna inteira do cartão
        combo.configure(width=width or 32)
        return combo

    def _build_audio(self, parent: ttk.Frame) -> None:
        parent.configure(padding=(10, 8))
        # ---- resultado: contêiner + codec
        card = self._card(parent)
        section(card, "Formato de saída").grid(row=0, column=0, columnspan=3,
                                               sticky="w", pady=(0, 4))
        self.var_container = tk.StringVar(value="MP3")
        self.combo_container = self._combo(card, var=self.var_container)
        field(card, 1, "Contêiner", lambda p: self.combo_container,
              "Contêiner (formato do arquivo). Só aparecem formatos e codecs "
              "presentes neste FFmpeg.", sticky_widget="ew", columnspan=2)
        self.combo_container.bind("<<ComboboxSelected>>", self._on_container_changed)
        self.combo_container.bind("<FocusOut>", self._on_container_focus_out)
        self.var_codec = tk.StringVar()
        self.combo_codec = self._combo(card, var=self.var_codec)
        field(card, 2, "Codec de áudio", lambda p: self.combo_codec,
              "Codec é diferente de contêiner: AAC pode estar em .m4a ou .aac (ADTS); "
              "MP3 usa o contêiner MP3.", sticky_widget="ew", columnspan=2)
        self.combo_codec.bind("<<ComboboxSelected>>", self._on_codec_changed)

        # ---- qualidade
        card = self._card(parent)
        section(card, "Qualidade").grid(row=0, column=0, columnspan=3, sticky="w",
                                        pady=(0, 4))
        self.var_mode = tk.StringVar(value="cbr")
        modes = ttk.Frame(card, style="Card.TFrame")
        self.rb_cbr = make_radiobutton(modes, "Bitrate fixo (CBR)", self.var_mode, "cbr",
                                       command=self._on_mode_changed,
                                       background=theme.PANEL)
        self.rb_cbr.pack(side="left")
        self.rb_vbr = make_radiobutton(modes, "Qualidade (VBR)", self.var_mode, "vbr",
                                       command=self._on_mode_changed,
                                       background=theme.PANEL)
        self.rb_vbr.pack(side="left", padx=(14, 0))
        field(card, 1, "Modo", lambda p: modes, sticky_widget="w")

        self.container_audio_quality = card
        self.var_bitrate = tk.StringVar(value="192")
        self.combo_bitrate = ttk.Combobox(card, textvariable=self.var_bitrate,
                                          values=BITRATE_PRESETS, width=10)
        self.combo_bitrate.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        self.combo_bitrate.bind("<FocusOut>", lambda _e: self.changed())
        self.lbl_bitrate = ttk.Label(card, text="Bitrate (kbps)", style="Card.TLabel")
        self.lbl_bitrate.grid(row=2, column=0, sticky="w", padx=(0, 10), pady=3)
        self.combo_bitrate.grid(row=2, column=1, sticky="w", pady=3)

        quality_frame = ttk.Frame(card, style="Card.TFrame")
        self.var_quality = tk.IntVar(value=2)
        self.scale_quality = ttk.Scale(quality_frame, from_=0, to=9, orient="horizontal",
                                       variable=self.var_quality,
                                       command=lambda _v: self.changed())
        self.scale_quality.pack(side="left", fill="x", expand=True)
        self.lbl_quality_value = ttk.Label(quality_frame, text="2", width=3,
                                           style="Card.TLabel")
        self.lbl_quality_value.pack(side="left", padx=(8, 0))
        self.var_quality.trace_add("write", lambda *_a: self.lbl_quality_value.configure(
            text=str(self.var_quality.get())))
        self.lbl_quality = ttk.Label(card, text="Qualidade (VBR)", style="Card.TLabel")
        self.lbl_quality.grid(row=3, column=0, sticky="w", padx=(0, 10), pady=3)
        quality_frame.grid(row=3, column=1, columnspan=2, sticky="ew", pady=3)

        self.var_compression = tk.IntVar(value=5)
        self.spin_compression = ttk.Spinbox(card, from_=0, to=12, width=6,
                                            textvariable=self.var_compression,
                                            command=self.changed)
        self.spin_compression.bind("<FocusOut>", lambda _e: self.changed())
        self.lbl_compression = ttk.Label(card, text="Compressão FLAC (0-12)",
                                         style="Card.TLabel")
        self.lbl_compression.grid(row=4, column=0, sticky="w", padx=(0, 10), pady=3)
        self.spin_compression.grid(row=4, column=1, sticky="w", pady=3)

        # ---- formato do áudio
        card = self._card(parent)
        section(card, "Formato do áudio").grid(row=0, column=0, columnspan=3, sticky="w",
                                               pady=(0, 4))
        self.var_rate = tk.StringVar(value=SAMPLE_RATES[0])
        combo_rate = ttk.Combobox(card, textvariable=self.var_rate, values=SAMPLE_RATES,
                                  width=16)
        combo_rate.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        field(card, 1, "Sample rate (Hz)", lambda p: combo_rate, sticky_widget="w")

        self.var_channels = tk.StringVar()
        self.combo_channels = self._combo(card, var=self.var_channels, width=20)
        self.combo_channels.bind("<<ComboboxSelected>>", self._on_channels_changed)
        field(card, 2, "Canais", lambda p: self.combo_channels,
              "5.1 só é convertido para estéreo se você escolher explicitamente.",
              sticky_widget="w")

        gain_frame = ttk.Frame(card, style="Card.TFrame")
        self.var_gain = tk.DoubleVar(value=0.0)
        spin_gain = ttk.Spinbox(gain_frame, from_=-30, to=30, increment=0.5, width=7,
                                textvariable=self.var_gain, command=self.changed)
        spin_gain.pack(side="left")
        spin_gain.bind("<FocusOut>", lambda _e: self.changed())
        ttk.Label(gain_frame, text="dB", style="Muted.TLabel").pack(side="left", padx=6)
        field(card, 3, "Ganho", lambda p: gain_frame, sticky_widget="w")

        self.var_normalize = tk.StringVar(value="Desligada")
        self.combo_normalize = self._combo(
            card, ["Desligada", "EBU R128 (loudnorm)", "Pico (dynaudnorm)"],
            var=self.var_normalize, width=26)
        self.combo_normalize.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        field(card, 4, "Normalização", lambda p: self.combo_normalize, sticky_widget="ew",
              columnspan=2)

        # ---- opções
        card = self._card(parent)
        section(card, "Metadados e extras").grid(row=0, column=0, columnspan=3,
                                                 sticky="w", pady=(0, 4))
        self.var_metadata = tk.BooleanVar(value=True)
        self.var_cover = tk.BooleanVar(value=True)
        self.var_trim = tk.BooleanVar(value=False)
        checks = ttk.Frame(card, style="Card.TFrame")
        make_checkbutton(checks, "Preservar metadados", self.var_metadata,
                         command=self.changed).pack(anchor="w")
        make_checkbutton(checks, "Preservar capa de álbum", self.var_cover,
                         command=self.changed).pack(anchor="w")
        make_checkbutton(checks, "Remover silêncio inicial", self.var_trim,
                         command=self.changed).pack(anchor="w")
        field(card, 1, "Opções", lambda p: checks, sticky_widget="w")

        cover_frame = ttk.Frame(card, style="Card.TFrame")
        self.var_cover_image = tk.StringVar(value="")
        self.lbl_cover = ttk.Label(cover_frame, text="(usar a capa do arquivo)",
                                   style="Muted.TLabel")
        self.lbl_cover.pack(side="left", fill="x", expand=True)
        make_button(cover_frame, "Escolher…", self._pick_cover, "Small.TButton"
                    ).pack(side="right")
        make_button(cover_frame, "Limpar", self._clear_cover, "Small.TButton"
                    ).pack(side="right", padx=4)
        tooltip(cover_frame, "Imagem usada como capa na saída (JPEG/PNG). "
                             "Sobrescreve a capa original.")
        field(card, 2, "Capa", lambda p: cover_frame, sticky_widget="ew", columnspan=2)

        self.var_stream = tk.StringVar()
        self.combo_stream = self._combo(card, var=self.var_stream, width=30)
        self.combo_stream.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        field(card, 3, "Faixa de áudio", lambda p: self.combo_stream, sticky_widget="ew",
              columnspan=2)

        self.lbl_warning = ttk.Label(parent, text="", style="Hint.TLabel",
                                     foreground=theme.WARN, wraplength=560,
                                     justify="left")
        self.lbl_warning.pack(fill="x", pady=(0, 8))

    # ------------------------------------------------------------------
    # Vídeo
    # ------------------------------------------------------------------
    def _build_video(self, parent: ttk.Frame) -> None:
        parent.configure(padding=(10, 8))
        card = self._card(parent)
        section(card, "Vídeo de saída").grid(row=0, column=0, columnspan=3, sticky="w",
                                             pady=(0, 4))
        self.var_vcontainer = tk.StringVar()
        self.combo_vcontainer = self._combo(card, var=self.var_vcontainer)
        self.combo_vcontainer.bind("<<ComboboxSelected>>", self._on_vcontainer_changed)
        field(card, 1, "Contêiner", lambda p: self.combo_vcontainer, sticky_widget="w")
        self.var_vcodec = tk.StringVar()
        self.combo_vcodec = self._combo(card, var=self.var_vcodec)
        self.combo_vcodec.bind("<<ComboboxSelected>>", self._on_vcodec_changed)
        field(card, 2, "Codec de vídeo", lambda p: self.combo_vcodec, sticky_widget="w")

        self.var_vpreset_quick = tk.StringVar(value=list(VIDEO_PRESETS)[0])
        self.combo_vpreset_quick = self._combo(card, list(VIDEO_PRESETS),
                                               var=self.var_vpreset_quick, width=26)
        self.combo_vpreset_quick.bind("<<ComboboxSelected>>", self._on_quick_preset)
        field(card, 3, "Preset rápido", lambda p: self.combo_vpreset_quick,
              "Ajusta qualidade/bitrate rapidamente; os campos abaixo continuam "
              "editáveis.", sticky_widget="w")

        card = self._card(parent)
        section(card, "Qualidade").grid(row=0, column=0, columnspan=3, sticky="w",
                                        pady=(0, 4))
        self.var_vmode = tk.StringVar(value="crf")
        vmodes = ttk.Frame(card, style="Card.TFrame")
        self.rb_vcrf = make_radiobutton(vmodes, "Qualidade (CRF/CQ)", self.var_vmode,
                                        "crf", command=self._on_vmode_changed,
                                        background=theme.PANEL)
        self.rb_vcrf.pack(side="left")
        self.rb_vabr = make_radiobutton(vmodes, "Bitrate-alvo", self.var_vmode, "abr",
                                        command=self._on_vmode_changed,
                                        background=theme.PANEL)
        self.rb_vabr.pack(side="left", padx=(14, 0))
        field(card, 1, "Controle", lambda p: vmodes, sticky_widget="w")

        qframe = ttk.Frame(card, style="Card.TFrame")
        self.var_vquality = tk.DoubleVar(value=23)
        self.scale_vquality = ttk.Scale(qframe, from_=0, to=51, orient="horizontal",
                                        variable=self.var_vquality,
                                        command=lambda _v: self.changed())
        self.scale_vquality.pack(side="left", fill="x", expand=True)
        self.lbl_vquality = ttk.Label(qframe, text="23", width=4, style="Card.TLabel")
        self.lbl_vquality.pack(side="left", padx=(8, 0))
        self.var_vquality.trace_add("write", lambda *_a: self.lbl_vquality.configure(
            text=f"{self.var_vquality.get():.0f}"))
        field(card, 2, "Qualidade", lambda p: qframe, sticky_widget="ew", columnspan=2)

        self.var_vbitrate = tk.StringVar(value="Automático")
        self.combo_vbitrate = ttk.Combobox(card, textvariable=self.var_vbitrate,
                                           values=VIDEO_BITRATE_PRESETS, width=12)
        self.combo_vbitrate.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        field(card, 3, "Bitrate de vídeo", lambda p: self.combo_vbitrate, sticky_widget="w")

        self.var_preset = tk.StringVar()
        self.combo_preset = self._combo(card, var=self.var_preset, width=14)
        self.combo_preset.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        field(card, 4, "Preset do encoder", lambda p: self.combo_preset, sticky_widget="w")

        card = self._card(parent)
        section(card, "Imagem e tempo").grid(row=0, column=0, columnspan=3, sticky="w",
                                             pady=(0, 4))
        self.var_resolution = tk.StringVar(value=RESOLUTION_PRESETS[0])
        self.combo_resolution = self._combo(card, RESOLUTION_PRESETS,
                                            var=self.var_resolution, width=22)
        self.combo_resolution.bind("<<ComboboxSelected>>", self._on_resolution_changed)
        field(card, 1, "Resolução", lambda p: self.combo_resolution, sticky_widget="w",
              tip="A proporção é mantida — o vídeo nunca é deformado. "
                  "'1280xauto' mantém o lado maior em 1280.")

        self.var_fps = tk.StringVar(value=FPS_PRESETS[0])
        self.combo_fps = ttk.Combobox(card, textvariable=self.var_fps, values=FPS_PRESETS,
                                      width=14)
        self.combo_fps.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        field(card, 2, "FPS", lambda p: self.combo_fps, sticky_widget="w")

        self.var_pixfmt = tk.StringVar(value=PIXEL_FORMATS[0])
        self.combo_pixfmt = self._combo(card, PIXEL_FORMATS, var=self.var_pixfmt,
                                        width=16)
        self.combo_pixfmt.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        field(card, 3, "Pixel format", lambda p: self.combo_pixfmt, sticky_widget="w")

        pf = ttk.Frame(card, style="Card.TFrame")
        self.var_vprofile = tk.StringVar()
        self.combo_vprofile = self._combo(pf, var=self.var_vprofile, width=14)
        self.combo_vprofile.pack(side="left")
        self.combo_vprofile.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        self.var_vlevel = tk.StringVar()
        self.combo_vlevel = self._combo(pf, var=self.var_vlevel, width=10)
        self.combo_vlevel.pack(side="left", padx=(8, 0))
        self.combo_vlevel.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        field(card, 4, "Perfil / nível", lambda p: pf, sticky_widget="w")

        self.var_subtitles = tk.StringVar(value="Copiar quando possível")
        self.combo_subtitles = self._combo(
            card, ["Copiar quando possível", "Não incluir"], var=self.var_subtitles,
            width=24)
        self.combo_subtitles.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        field(card, 5, "Legendas", lambda p: self.combo_subtitles, sticky_widget="w")

        self.var_hwdecode = tk.BooleanVar(value=False)
        make_checkbutton(card, "Usar decodificação por hardware quando disponível",
                         self.var_hwdecode, command=self.changed).grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self._video_hint = ttk.Label(parent, text="", style="Hint.TLabel")
        self._video_hint.pack(fill="x", pady=(2, 0))
        self._video_hint_label = self._video_hint

    # ------------------------------------------------------------------
    # Extração
    # ------------------------------------------------------------------
    def _build_extraction(self, parent: ttk.Frame) -> None:
        parent.configure(padding=(10, 8))
        card = self._card(parent)
        section(card, "Operações a partir do arquivo de origem").grid(
            row=0, column=0, sticky="w", pady=(0, 4))
        hint(card, "Aplicam-se aos arquivos selecionados (ou à fila pendente). "
                   "Remux e extração não recodificam o que for possível copiar.",
             wrap=520).grid(row=1, column=0, sticky="w", pady=(0, 6))
        buttons = [
            ("Extrair áudio original (sem recodificar)", self._extract_copy,
             "Escolhe um contêiner compatível com o codec original "
             "(ex.: AAC de MP4 → .aac) e copia o stream, sem perda."),
            ("Extrair áudio convertendo", self._extract_convert,
             "Decodifica a faixa escolhida e gera no formato configurado na aba Áudio."),
            ("Extrair vídeo sem áudio (remux)", self._extract_video_only,
             "Copia o vídeo sem recodificar e remove as faixas de áudio."),
            ("Remux: copiar tudo", self._remux_all,
             "Copia vídeo e áudio sem recodificar para o contêiner escolhido no vídeo."),
        ]
        for index, (text, command, tip) in enumerate(buttons, start=2):
            button = make_button(card, text, command)
            button.grid(row=index, column=0, sticky="ew", pady=2)
            tooltip(button, tip)

    # ------------------------------------------------------------------
    # Rodapé
    # ------------------------------------------------------------------
    def _build_footer(self) -> None:
        bar = ttk.Frame(self, style="Toolbar.TFrame", padding=(10, 6))
        bar.pack(fill="x", pady=(6, 0))
        self.summary_label = ttk.Label(bar, text="", style="StatusAccent.TLabel")
        self.summary_label.pack(side="left")
        self.btn_apply = make_button(bar, "Aplicar aos selecionados",
                                     self.apply_to_selection, "Accent.TButton")
        self.btn_apply.pack(side="right")
        self.btn_add = make_button(bar, "+ Arquivos…", self._add_files, "Small.TButton")
        self.btn_add.pack(side="right", padx=(0, 8))

    def _add_files(self) -> None:
        if hasattr(self.app, "request_add_files"):
            self.app.request_add_files()

    # ------------------------------------------------------------------
    # Carregar / salvar
    # ------------------------------------------------------------------
    def load_from_app(self) -> None:
        self._loading = True
        try:
            app = self.app
            self._refresh_container_choices()
            desired_audio = app.container if app.kind == "audio" else "mka"
            if desired_audio not in AUDIO_CONTAINER_KEYS:
                desired_audio = "mka"
            self._select_container(desired_audio)
            self._refresh_audio_codecs()
            labels = list(self._audio_option_map)
            option = None
            for label in labels:
                if self._audio_option_map[label].id == app.audio.codec:
                    option = label
                    break
            if option is None:
                default = self.catalog.default_audio_codec(app.container)
                for label in labels:
                    if self._audio_option_map[label].id == default:
                        option = label
                        break
            if option is None and labels:
                option = labels[0]
            if option:
                self.var_codec.set(option)
                app.audio.codec = self._audio_option_map[option].id
            self._load_audio_values(app.audio)
            self._refresh_channel_choices()
            self._refresh_stream_choices(None)
            self.var_metadata.set(app.audio.copy_metadata)
            self.var_cover.set(app.audio.cover_copy)
            self.var_trim.set(app.audio.trim_silence)
            image = app.audio.cover_image or ""
            self.var_cover_image.set(image)
            self.lbl_cover.configure(text=(os.path.basename(image) if image
                                           else "(usar a capa do arquivo)"))
            self._refresh_video_containers(preferred=app.container
                                           if app.kind == "video" else "")
            self._refresh_video_codecs()
            voption = None
            for label, opt in self._video_option_map.items():
                if opt.id == app.video.codec:
                    voption = label
                    break
            if voption is None and self._video_option_map:
                voption = list(self._video_option_map)[0]
            if voption:
                self.var_vcodec.set(voption)
                app.video.codec = self._video_option_map[voption].id
            self._load_video_values(app.video)
            self.update_visibility()
            self._update_summary()
        finally:
            self._loading = False

    def _load_audio_values(self, settings: AudioSettings) -> None:
        self.var_mode.set(settings.mode if settings.mode in ("cbr", "vbr") else "cbr")
        bitrate = str(settings.bitrate or "192k")
        self.var_bitrate.set(bitrate[:-1] if bitrate.endswith("k") else bitrate)
        try:
            self.var_quality.set(int(settings.quality))
        except (TypeError, ValueError):
            self.var_quality.set(2)
        if settings.compression_level is not None:
            self.var_compression.set(int(settings.compression_level))
        rate = str(settings.sample_rate or "keep")
        self.var_rate.set(SAMPLE_RATES[0] if rate in ("keep", "") else rate)
        self.var_gain.set(float(settings.gain_db or 0.0))
        self.var_normalize.set({"off": "Desligada", "ebu": "EBU R128 (loudnorm)",
                                "peak": "Pico (dynaudnorm)"}.get(settings.normalize,
                                                                 "Desligada"))
        self._apply_channel_selection(settings.channels or "keep", collect=False)

    def _apply_channel_selection(self, channels: str, collect: bool = True) -> None:
        """Sincroniza o seletor de canais com um valor interno ('keep', '2'…)."""
        target = CHANNELS["keep"]
        for key, choice in CHANNELS.items():
            if key == str(channels):
                target = choice
                break
        self.var_channels.set(target.label)
        self._channel_key = target.name
        if collect and target.name != "keep":
            self.app.audio.channels = target.name

    def _load_video_values(self, settings: VideoSettings) -> None:
        self.var_vmode.set("crf" if settings.mode == "crf" else "abr")
        try:
            self.var_vquality.set(float(settings.quality or 23))
        except (TypeError, ValueError):
            self.var_vquality.set(23)
        self.var_vbitrate.set(settings.bitrate or "Automático")
        resolution = settings.resolution or "keep"
        if resolution in ("keep", ""):
            self.var_resolution.set(RESOLUTION_PRESETS[0])
        else:
            values = list(self.combo_resolution.cget("values"))
            if resolution not in values:
                self.combo_resolution.configure(values=[resolution] + values)
            self.var_resolution.set(resolution)
        fps = str(settings.fps or "keep")
        self.var_fps.set(FPS_PRESETS[0] if fps in ("keep", "") else fps)
        self.var_pixfmt.set(settings.pix_fmt if settings.pix_fmt in PIXEL_FORMATS
                            else PIXEL_FORMATS[0])
        self.var_subtitles.set("Copiar quando possível")
        self.var_hwdecode.set(settings.hw_decode)
        if settings.codec in VIDEO_CODECS:
            info = VIDEO_CODECS[settings.codec]
            self._configure_video_for_codec(info, reset=False)
            self.var_preset.set(settings.preset or info.default_preset)
            self.var_vprofile.set(settings.profile or "")
            self.var_vlevel.set(settings.level or "")
            self.var_vquality.set(float(settings.quality or info.quality_default))
        else:
            self.var_preset.set(settings.preset or "")

    def collect_audio(self) -> AudioSettings:
        option = self._current_audio_option()
        codec = option.id if option else "libmp3lame"
        bitrate_value = self.var_bitrate.get().strip() or "192"
        try:
            bitrate_value = f"{float(bitrate_value.replace(',', '.')):g}"
        except ValueError:
            bitrate_value = "192"
        rate_text = self.var_rate.get().strip()
        normalize = {"EBU R128 (loudnorm)": "ebu", "Pico (dynaudnorm)": "peak"}.get(
            self.var_normalize.get(), "off")
        stream = self._stream_map_reverse().get(self.var_stream.get(), "auto")
        compression = None
        try:
            compression = int(self.var_compression.get())
        except (tk.TclError, ValueError):
            compression = None
        return AudioSettings(
            codec=codec,
            mode="vbr" if self.var_mode.get() == "vbr" else "cbr",
            bitrate=f"{bitrate_value}k",
            quality=int(self.var_quality.get()),
            compression_level=compression,
            channels=self._channel_key,
            sample_rate="keep" if rate_text == SAMPLE_RATES[0] else rate_text,
            gain_db=float(self.var_gain.get() or 0.0),
            normalize=normalize,
            trim_silence=bool(self.var_trim.get()),
            stream=stream,
            copy_metadata=bool(self.var_metadata.get()),
            cover_copy=bool(self.var_cover.get()),
            cover_image=self.var_cover_image.get().strip(),
        )

    def collect_video(self) -> VideoSettings:
        option = self._current_video_option()
        resolution = self.var_resolution.get()
        fps = self.var_fps.get()
        bitrate = "" if self.var_vbitrate.get() in ("", "Automático") else \
            self.var_vbitrate.get().strip()
        return VideoSettings(
            codec=option.id if option else "copy",
            mode="crf" if self.var_vmode.get() == "crf" else "abr",
            quality=float(self.var_vquality.get()),
            bitrate=bitrate,
            preset=self.var_preset.get(),
            resolution="keep" if resolution == RESOLUTION_PRESETS[0] else resolution,
            fps="keep" if fps == FPS_PRESETS[0] else fps,
            pix_fmt=self.var_pixfmt.get(),
            profile=self.var_vprofile.get(),
            level=self.var_vlevel.get(),
            hw_decode=bool(self.var_hwdecode.get()),
        )

    def _stream_map_reverse(self) -> dict[str, str]:
        return {label: key for key, label in self._stream_map.items()}

    # ------------------------------------------------------------------
    # Opções
    # ------------------------------------------------------------------
    def _refresh_container_choices(self) -> None:
        self._audio_container_map = {}
        labels = []
        for key in AUDIO_CONTAINER_KEYS:
            container = CONTAINERS[key]
            if not self.catalog.container_available(key):
                continue
            if not [o for o in self.catalog.audio_options(key) if not o.is_copy]:
                continue
            labels.append(container.label)
            self._audio_container_map[container.label] = key
        labels.append(CONTAINERS["copy"].label)
        self._audio_container_map[CONTAINERS["copy"].label] = "copy"
        self.combo_container.configure(values=labels)

    def _select_container(self, key: str) -> None:
        for label, value in self._audio_container_map.items():
            if value == key:
                self.var_container.set(label)
                return

    def _current_container_key(self) -> str:
        return self._audio_container_map.get(self.var_container.get(), "mp3")

    def _current_audio_option(self) -> AudioOption | None:
        return self._audio_option_map.get(self.var_codec.get())

    def _current_video_option(self) -> VideoOption | None:
        return self._video_option_map.get(self.var_vcodec.get())

    def _refresh_audio_codecs(self, reset_to_default: bool = False) -> None:
        """Recria as opções de codec do contêiner e mantém uma escolha sensata.

        Prioridade: 1) codec já escolhido pelo usuário (se compatível);
        2) codec atual da aplicação (se compatível); 3) o padrão do contêiner
        (ex.: Vorbis no OGG); 4) o primeiro encoder real disponível.
        "Copiar sem recodificar" só é escolhido quando pedido explicitamente.
        """
        options = self.catalog.audio_options(self._current_container_key())
        self._audio_option_map = {}
        labels = []
        for option in options:
            label = option.label
            if option.is_copy:
                label += "  (só se o contêiner aceitar o codec original)"
            labels.append(label)
            self._audio_option_map[label] = option
        previous = self.var_codec.get()
        self.combo_codec.configure(values=labels)

        def pick_by_id(codec_id: str) -> str | None:
            for label, option in self._audio_option_map.items():
                if option.id == codec_id and not option.is_copy:
                    return label
            return None

        chosen: str | None = None
        if previous in self._audio_option_map:
            previous_option = self._audio_option_map[previous]
            if previous_option.is_copy:
                # cópia só continua se o usuário pediu cópia na aplicação
                if not reset_to_default and self.app.audio.codec == CODEC_COPY:
                    chosen = previous
            elif not reset_to_default:
                chosen = previous
        if chosen is None:
            chosen = pick_by_id(self.app.audio.codec)
        if chosen is None:
            chosen = pick_by_id(self.catalog.default_audio_codec(
                self._current_container_key()))
        if chosen is None:
            for label, option in self._audio_option_map.items():
                if not option.is_copy:
                    chosen = label
                    break
        if chosen is None and labels:
            chosen = labels[0]
        if chosen:
            self.var_codec.set(chosen)
            self.app.audio.codec = self._audio_option_map[chosen].id

    def _refresh_channel_choices(self) -> None:
        option = self._current_audio_option()
        codec = AUDIO_CODECS.get(option.id) if option and not option.is_copy else None
        labels = []
        for key, choice in CHANNELS.items():
            if key != "keep" and codec and int(key) > codec.max_channels:
                continue
            labels.append(choice.label)
        self.combo_channels.configure(values=labels)
        self.var_channels.set(CHANNELS.get(self._channel_key, CHANNELS["keep"]).label)

    def _refresh_stream_choices(self, info) -> None:
        from ..media.analyzer import stream_choices
        choices = stream_choices(info) if info else [("auto", "Automática (faixa padrão)")]
        self._stream_map = {}
        labels = []
        for value, label in choices:
            self._stream_map[value] = label
            labels.append(label)
        self.combo_stream.configure(values=labels)
        current = self.app.audio.stream or "auto"
        self.var_stream.set(self._stream_map.get(current, self._stream_map["auto"]))

    def _refresh_video_containers(self, preferred: str = "") -> None:
        self._video_container_map = {}
        labels = []
        for key in VIDEO_CONTAINER_KEYS:
            if not self.catalog.container_available(key):
                continue
            labels.append(CONTAINERS[key].label)
            self._video_container_map[CONTAINERS[key].label] = key
        self.combo_vcontainer.configure(values=labels)
        target = None
        if preferred:
            for label, key in self._video_container_map.items():
                if key == preferred:
                    target = label
                    break
        if target is None:
            for label, key in self._video_container_map.items():
                if key == self._current_container_key():
                    target = label
                    break
        if target is None:
            for label, key in self._video_container_map.items():
                if key == "mp4":
                    target = label
                    break
        self.var_vcontainer.set(target or (labels[0] if labels else ""))

    def _current_vcontainer_key(self) -> str:
        return self._video_container_map.get(self.var_vcontainer.get(), "mp4")

    def _refresh_video_codecs(self) -> None:
        options = self.catalog.video_options(self._current_vcontainer_key())
        self._video_option_map = {}
        labels = []
        for option in options:
            labels.append(option.label)
            self._video_option_map[option.label] = option
        previous = self.var_vcodec.get()
        self.combo_vcodec.configure(values=labels)
        if previous in self._video_option_map:
            return
        wanted = self.app.video.codec or "copy"
        chosen = None
        for label, option in self._video_option_map.items():
            if option.id == wanted:
                chosen = label
                break
        if chosen is None and labels:
            chosen = labels[0]
        if chosen:
            self.var_vcodec.set(chosen)
            self.app.video.codec = self._video_option_map[chosen].id

    # ------------------------------------------------------------------
    # Eventos
    # ------------------------------------------------------------------
    def _on_container_focus_out(self, _event=None) -> None:
        if not self._loading and self.var_container.get() in self._audio_container_map:
            self._on_container_changed()

    def _button(self, parent, style: str, **kw):
        """Botão compacto (o estilo "clam" reserva largura em letras)."""
        if not hasattr(self, "_btn_serial"):
            self._btn_serial = 0
        self._btn_serial += 1
        name = f"Umc{style.replace('.', '')}{self._btn_serial}.TButton"
        ttk.Style(self).configure(name, width=0)
        return ttk.Button(parent, style=name, **kw)

    def _on_container_changed(self, _event=None) -> None:
        if self._loading:
            return
        self.app.container = self._current_container_key()
        self._refresh_audio_codecs(reset_to_default=True)
        default = self.catalog.default_audio_codec(self.app.container) \
            if self.app.container != "copy" else "copy"
        for label, option in self._audio_option_map.items():
            if option.id == default:
                self.var_codec.set(label)
                break
        self._refresh_channel_choices()
        self.update_visibility()
        self.changed()

    def _on_codec_changed(self, _event=None) -> None:
        if self._loading:
            return
        self._refresh_channel_choices()
        self.update_visibility()
        self.changed()

    def _on_channels_changed(self, _event=None) -> None:
        label = self.var_channels.get()
        for key, choice in CHANNELS.items():
            if choice.label == label:
                self._channel_key = key
                break
        self.changed()

    def _on_mode_changed(self) -> None:
        self.update_visibility()
        self.changed()

    def _on_vmode_changed(self) -> None:
        self.update_visibility()
        self.changed()

    def _on_vcontainer_changed(self, _event=None) -> None:
        if self._loading:
            return
        key = self._current_vcontainer_key()
        self.app.container = key
        self._refresh_audio_codecs()
        self._refresh_video_codecs()
        default = self.catalog.default_video_codec(key)
        for label, option in self._video_option_map.items():
            if option.id == default:
                self.var_vcodec.set(label)
                break
        self.update_visibility()
        self.changed()

    def _on_vcodec_changed(self, _event=None) -> None:
        option = self._current_video_option()
        if option and option.info:
            self._configure_video_for_codec(option.info)
        self.update_visibility()
        self.changed()

    def _configure_video_for_codec(self, info, reset: bool = True) -> None:
        self.combo_preset.configure(values=info.presets)
        if info.presets:
            if reset or self.var_preset.get() not in info.presets:
                self.var_preset.set(info.default_preset or info.presets[0])
        else:
            self.var_preset.set("")
        self.scale_vquality.configure(from_=info.quality_range[0],
                                      to=info.quality_range[1])
        if reset:
            self.var_vquality.set(info.quality_default)
        profiles = VIDEO_PROFILES.get(info.family, ())
        levels = VIDEO_LEVELS.get(info.family, ())
        self.combo_vprofile.configure(values=("(automático)",) + profiles)
        self.combo_vlevel.configure(values=("(automático)",) + levels)
        if reset:
            self.var_vprofile.set("")
            self.var_vlevel.set("")
        if not info.quality_args:
            self.var_vmode.set("abr")

    def _on_quick_preset(self, _event=None) -> None:
        preset = VIDEO_PRESETS.get(self.var_vpreset_quick.get(), {})
        if preset.get("codec") == "copy":
            for label, option in self._video_option_map.items():
                if option.id == "copy":
                    self.var_vcodec.set(label)
                    break
            self.var_vmode.set("crf")
            self.update_visibility()
            self.changed()
            return
        if "quality" in preset:
            self.var_vmode.set("crf")
            self.var_vquality.set(float(preset["quality"]))
        if "bitrate" in preset:
            self.var_vmode.set("abr")
            self.var_vbitrate.set(preset["bitrate"])
        elif self.var_vmode.get() == "abr":
            self.var_vmode.set("crf")
        self.update_visibility()
        self.changed()

    def _on_resolution_changed(self, _event=None) -> None:
        if self.var_resolution.get() == "Personalizada…":
            from .dialogs import ask_string
            value = ask_string(self, "Resolução personalizada",
                               "Largura x altura (ex.: 1600x900, 1280xauto):", "1280x720")
            if value and "x" in value.lower():
                values = list(self.combo_resolution.cget("values"))
                if value not in values:
                    self.combo_resolution.configure(values=[value] + values)
                self.var_resolution.set(value)
            else:
                self.var_resolution.set(RESOLUTION_PRESETS[0])
        self.changed()

    def _pick_cover(self) -> None:
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            parent=self, title="Escolher imagem da capa",
            filetypes=[("Imagens", "*.jpg *.jpeg *.png *.bmp *.webp"),
                       ("Todos os arquivos", "*")])
        if path:
            self.var_cover_image.set(path)
            self.lbl_cover.configure(text=os.path.basename(path))
            self.changed()

    def _clear_cover(self) -> None:
        self.var_cover_image.set("")
        self.lbl_cover.configure(text="(usar a capa do arquivo)")
        self.changed()

    # ------------------------------------------------------------------
    def update_visibility(self) -> None:
        option = self._current_audio_option()
        codec_id = option.id if option else ""
        is_copy = codec_id == CODEC_COPY
        info = AUDIO_CODECS.get(codec_id)
        lossless = bool(info and info.lossless)

        show_vbr = bool(info and info.vbr)
        self.rb_vbr.configure(state="normal" if show_vbr and not is_copy else "disabled")
        if not show_vbr and self.var_mode.get() == "vbr":
            self.var_mode.set("cbr")
        use_vbr = self.var_mode.get() == "vbr" and show_vbr and not is_copy
        show_bitrate = not use_vbr and not is_copy and not lossless and info is not None \
            and info.bitrate
        self.combo_bitrate.configure(state="normal" if show_bitrate else "disabled")
        if not is_copy:
            self.container_audio_quality.rowconfigure(2, weight=0)
        self.scale_quality.state(["!disabled"] if use_vbr else ["disabled"])
        self.rb_cbr.configure(state="normal" if not is_copy else "disabled")
        if info and use_vbr:
            self.scale_quality.configure(from_=info.quality_range[0],
                                         to=info.quality_range[1])
        compression_ok = bool(lossless and info and info.compression and not is_copy)
        self.spin_compression.configure(state="normal" if compression_ok else "disabled")
        if not codec_id:
            compression_ok = False
        self.combo_channels.state(["disabled"] if is_copy else ["!disabled"])
        self.combo_normalize.state(["disabled"] if is_copy else ["!disabled"])

        voption = self._current_video_option()
        vcodec = voption.id if voption else CODEC_COPY
        vinfo = VIDEO_CODECS.get(vcodec)
        copy_or_none = vcodec in (CODEC_COPY, CODEC_NONE)
        disable = ["disabled"] if copy_or_none else ["!disabled"]
        for widget in (self.combo_preset, self.combo_resolution, self.combo_fps,
                       self.combo_pixfmt, self.combo_vprofile, self.combo_vlevel,
                       self.combo_vbitrate, self.scale_vquality,
                       self.combo_subtitles, self.combo_vpreset_quick):
            widget.state(disable)
        for radio in (self.rb_vcrf, self.rb_vabr):
            radio.configure(state="disabled" if copy_or_none else "normal")
        self.combo_vpreset_quick.configure(state="readonly")
        if vcodec == CODEC_COPY:
            text = "O vídeo original será copiado sem recodificar."
        elif vcodec == CODEC_NONE:
            text = "O vídeo será removido (extração de áudio)."
        elif vinfo and vinfo.hwaccel:
            text = ("Codificação por hardware: não assume mesma qualidade ou velocidade "
                    "da CPU.")
        else:
            text = ""
        self._video_hint.configure(text=text)
        self._update_extraction_hint(codec_id)
        notes = []
        if is_copy:
            notes.append("Recodificação desativada: o stream original será copiado.")
        elif lossless:
            notes.append("Codec sem perdas: o tamanho depende do conteúdo, não de bitrate.")
        elif not show_vbr:
            notes.append("Este codec não tem modo VBR; use o bitrate-alvo.")
        if notes:
            self.lbl_warning.configure(text="\n".join(notes))

    def _update_extraction_hint(self, codec_id: str) -> None:
        lines = []
        if codec_id == CODEC_COPY:
            lines.append("Extração sem recodificação: o contêiner é escolhido conforme "
                         "o codec do arquivo original.")
        if self._channel_key == "keep":
            lines.append("Canais preservados como no original (5.1 não vira estéreo "
                         "sem escolha explícita).")
        self.lbl_warning.configure(text="\n".join(lines))

    def _update_summary(self) -> None:
        container = self._current_container_key()
        container_info = CONTAINERS.get(container)
        option = self._current_audio_option()
        if container == "copy":
            text = "Saída: contêiner automático · áudio copiado sem recodificar"
        else:
            label = container_info.label if container_info else container
            codec_label = option.label if option else "?"
            if option and option.is_copy:
                codec_label = "áudio copiado"
            mode = "VBR" if self.var_mode.get() == "vbr" else "CBR"
            bitrate = "" if mode == "VBR" else f" {self.var_bitrate.get().strip()} kbps"
            text = f"Saída: {label} · {codec_label} · {mode}{bitrate}"
        self.summary_label.configure(text=text)
        self._update_extraction_hint(option.id if option else "")

    def changed(self) -> None:
        if self._loading:
            return
        app = self.app
        app.container = self._current_container_key()
        app.audio = self.collect_audio()
        app.video = self.collect_video()
        self._update_summary()
        self.on_change()

    def apply_to_selection(self) -> None:
        self.changed()
        selected = self._selected_job_ids
        self.app.apply_config_to(selected)
        self.notify("Configuração aplicada aos selecionados." if selected
                    else "Configuração padrão atualizada para os novos arquivos.")

    def notify(self, message: str) -> None:
        if hasattr(self.app, "notify"):
            self.app.notify(message)

    # ------------------------------------------------------------------
    # Extração rápida
    # ------------------------------------------------------------------
    def _target_ids(self) -> list[int]:
        if self._selected_job_ids:
            return list(self._selected_job_ids)
        return [job.id for job in self.app.queue.snapshot()
                if job.status in ("pending", "error", "cancelled")]

    def _apply_extraction(self, config_update: dict, kind: str, container: str,
                          message: str) -> None:
        ids = self._target_ids()
        if not ids:
            self.notify("Selecione arquivos na aba Arquivos primeiro.")
            return
        base = self.app.config_snapshot()
        base.kind = kind
        base.container = container
        for key, value in config_update.items():
            if key.startswith("audio."):
                setattr(base.audio, key.split(".", 1)[1], value)
            elif key.startswith("video."):
                setattr(base.video, key.split(".", 1)[1], value)
        if base.audio.codec == "copy":
            base.audio.cover_copy = False
        self.app.queue.set_job_config(ids, base)
        self.notify(message)

    def _extract_copy(self) -> None:
        self._apply_extraction({"audio.codec": "copy"}, "audio", "copy",
                               "Extração sem recodificação agendada.")

    def _extract_convert(self) -> None:
        self.changed()
        config = self.app.config_snapshot()
        config.kind = "audio"
        if config.container == "copy":
            config.container = "mp3"
            config.audio.codec = "libmp3lame"
        if not self._target_ids():
            self.notify("Selecione arquivos na aba Arquivos primeiro.")
            return
        self.app.queue.set_job_config(self._target_ids(), config)
        self.notify("Faixa de áudio será convertida para o formato da aba Áudio.")

    def _extract_video_only(self) -> None:
        self._apply_extraction({"audio.codec": "none", "video.codec": "copy"},
                               "video", self._current_vcontainer_key(),
                               "Vídeo será copiado sem áudio.")

    def _remux_all(self) -> None:
        self._apply_extraction({"audio.codec": "copy", "video.codec": "copy"},
                               "video", self._current_vcontainer_key(),
                               "Remux (sem recodificação) agendado.")

    def refresh_for_job(self, job) -> None:
        info = self.app.analyzer.analyze(job.file)
        was_loading = self._loading
        self._loading = True
        try:
            self._refresh_stream_choices(info)
        finally:
            self._loading = was_loading
