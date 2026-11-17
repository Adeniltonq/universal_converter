"""Painel de configuração de conversão (áudio + vídeo + extração)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..media.catalog import AudioOption, VideoOption
from ..media.codecs import (
    AUDIO_CODECS, AUDIO_CONTAINER_KEYS, CHANNELS, CODEC_COPY, CODEC_NONE, CONTAINERS,
    INPUT_CODEC_LABEL, VIDEO_CODECS, VIDEO_CONTAINER_KEYS, VIDEO_EXTRA_ARGS,
    VIDEO_LEVELS, VIDEO_PRESETS, VIDEO_PROFILES, PIXEL_FORMATS,
)
from ..media.models import AudioSettings, VideoSettings
from ..naming.engine import NamingContext, NamingEngine
from . import theme
from .theme import hint, section, tooltip

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


def _to_int(text: str) -> int | None:
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return None


class ConversionPanel(ttk.Frame):
    """Aba "Conversão": contêiner, áudio, vídeo e prévia do resultado."""

    def __init__(self, parent: tk.Misc, controller, on_change: Callable | None = None):
        super().__init__(parent, style="TFrame", padding=(12, 10))
        self.app = controller
        self.catalog = controller.catalog
        self.on_change = on_change or (lambda: None)
        self._loading = False
        self._selected_job_ids: list[int] = []

        self._build_header()
        body = ttk.Frame(self, style="TFrame")
        body.pack(fill="both", expand=True, pady=(10, 0))
        body.columnconfigure(0, weight=3, uniform="col")
        body.columnconfigure(1, weight=2, uniform="col")
        body.rowconfigure(0, weight=1)
        self._build_audio(body)
        right = ttk.Frame(body, style="TFrame")
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)
        self.video_frame = ttk.Frame(right, style="TFrame")
        self.video_frame.grid(row=0, column=0, sticky="nsew")
        self._build_video(self.video_frame)
        self.extract_frame = ttk.Frame(right, style="TFrame")
        self.extract_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        self._build_extraction(self.extract_frame)
        self._build_summary()

        self.load_from_app()
        self.update_visibility()

    # ------------------------------------------------------------------
    def _build_header(self) -> None:
        header = ttk.Frame(self, style="TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="Conversão", style="Title.TLabel").pack(side="left")
        self.var_profile = tk.StringVar()
        self.combo_profile = ttk.Combobox(header, textvariable=self.var_profile, width=32,
                                          state="readonly")
        self.combo_profile.pack(side="right", padx=(8, 0))
        ttk.Label(header, text="Perfil:", style="MutedBg.TLabel").pack(side="right")
        self.combo_profile.bind("<<ComboboxSelected>>", self._on_profile_selected)
        self.btn_save_profile = ttk.Button(header, text="Salvar como perfil…",
                                           style="Tool.TButton",
                                           command=self._save_as_profile)
        self.btn_save_profile.pack(side="right", padx=8)
        self.var_apply_selected = tk.BooleanVar(value=False)
        ttk.Checkbutton(header, text="Aplicar somente aos selecionados",
                        variable=self.var_apply_selected, style="Bg.TCheckbutton"
                        ).pack(side="right", padx=8)
        self.refresh_profiles()

    def refresh_profiles(self) -> None:
        profiles = self.app.profiles.all()
        self._profile_map = {self._profile_label(p): p.id for p in profiles}
        values = list(self._profile_map)
        self.combo_profile.configure(values=values)
        current = self.app.profiles.find(self.app.current_profile)
        if current:
            self.var_profile.set(self._profile_label(current))
        else:
            self.var_profile.set("")

    @staticmethod
    def _profile_label(profile) -> str:
        kind = "Áudio" if profile.kind == "audio" else "Vídeo"
        suffix = " · pronto" if profile.builtin else ""
        return f"{profile.name} — {kind}{suffix}"

    def _on_profile_selected(self, _event=None) -> None:
        label = self.var_profile.get()
        profile_id = self._profile_map.get(label)
        profile = self.app.profiles.find(profile_id) if profile_id else None
        if not profile:
            return
        self.app.apply_profile(profile)
        self.load_from_app()
        self.notify("Perfil aplicado: " + profile.name)

    def _save_as_profile(self) -> None:
        from .dialogs import ask_string, info
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
    def _build_audio(self, parent: ttk.Frame) -> None:
        card = ttk.LabelFrame(parent, text="Áudio", style="TLabelframe", padding=10)
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(1, weight=1)
        row = 0

        section(card, "Formato de saída").grid(row=row, column=0, columnspan=2,
                                               sticky="w", pady=(0, 6))
        row += 1
        ttk.Label(card, text="Contêiner", style="Card.TLabel").grid(
            row=row, column=0, sticky="w", pady=3)
        self.var_container = tk.StringVar(value="MP3")
        self.combo_container = ttk.Combobox(card, textvariable=self.var_container,
                                            state="readonly", width=34)
        self.combo_container.grid(row=row, column=1, sticky="ew", pady=3)
        self.combo_container.bind("<<ComboboxSelected>>", self._on_container_changed)
        self.combo_container.bind("<FocusOut>", lambda _e: self._on_container_changed())
        tooltip(self.combo_container, "Contêiner (formato do arquivo). Oferece só os "
                                      "formatos e codecs presentes no seu FFmpeg.")
        row += 1
        ttk.Label(card, text="Codec de áudio", style="Card.TLabel").grid(
            row=row, column=0, sticky="w", pady=3)
        self.var_codec = tk.StringVar()
        self.combo_codec = ttk.Combobox(card, textvariable=self.var_codec,
                                        state="readonly", width=34)
        self.combo_codec.grid(row=row, column=1, sticky="ew", pady=3)
        self.combo_codec.bind("<<ComboboxSelected>>", self._on_codec_changed)
        self.combo_codec.bind("<FocusOut>", lambda _e: self._on_codec_changed())
        tooltip(self.combo_codec, "Codec é diferente de contêiner: AAC pode estar em "
                                  ".m4a ou .aac (ADTS); MP3 usa o contêiner MP3.")
        self._audio_option_map: dict[str, AudioOption] = {}

        row += 1
        section(card, "Qualidade").grid(row=row, column=0, columnspan=2, sticky="w",
                                        pady=(10, 4))
        row += 1
        self.var_mode = tk.StringVar(value="cbr")
        mode_frame = ttk.Frame(card, style="Card.TFrame")
        mode_frame.grid(row=row, column=0, columnspan=2, sticky="w", pady=2)
        self.rb_cbr = ttk.Radiobutton(mode_frame, text="Bitrate fixo (CBR/ABR)",
                                      value="cbr", variable=self.var_mode,
                                      command=self._on_mode_changed)
        self.rb_cbr.pack(side="left")
        self.rb_vbr = ttk.Radiobutton(mode_frame, text="Qualidade (VBR)",
                                      value="vbr", variable=self.var_mode,
                                      command=self._on_mode_changed)
        self.rb_vbr.pack(side="left", padx=(12, 0))
        row += 1
        self.lbl_bitrate = ttk.Label(card, text="Bitrate", style="Card.TLabel")
        self.lbl_bitrate.grid(row=row, column=0, sticky="w", pady=3)
        self.var_bitrate = tk.StringVar(value="192")
        self.combo_bitrate = ttk.Combobox(card, textvariable=self.var_bitrate,
                                          values=BITRATE_PRESETS, width=12)
        self.combo_bitrate.grid(row=row, column=1, sticky="w", pady=3)
        self.combo_bitrate.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        self.combo_bitrate.bind("<FocusOut>", lambda _e: self.changed())
        row += 1
        self.lbl_quality = ttk.Label(card, text="Qualidade (0-10)", style="Card.TLabel")
        self.lbl_quality.grid(row=row, column=0, sticky="w", pady=3)
        quality_frame = ttk.Frame(card, style="Card.TFrame")
        quality_frame.grid(row=row, column=1, sticky="ew", pady=3)
        self.var_quality = tk.IntVar(value=2)
        self.scale_quality = ttk.Scale(quality_frame, from_=0, to=9, orient="horizontal",
                                       variable=self.var_quality,
                                       command=lambda _v: self.changed())
        self.scale_quality.pack(side="left", fill="x", expand=True)
        self.lbl_quality_value = ttk.Label(quality_frame, text="2", width=3,
                                           style="Card.TLabel")
        self.lbl_quality_value.pack(side="left", padx=(6, 0))
        self.var_quality.trace_add("write", lambda *_a: self.lbl_quality_value.configure(
            text=str(self.var_quality.get())))
        row += 1
        self.lbl_compression = ttk.Label(card, text="Compressão (0-12)",
                                         style="Card.TLabel")
        self.lbl_compression.grid(row=row, column=0, sticky="w", pady=3)
        self.var_compression = tk.IntVar(value=5)
        self.spin_compression = ttk.Spinbox(card, from_=0, to=12, width=6,
                                            textvariable=self.var_compression,
                                            command=self.changed)
        self.spin_compression.grid(row=row, column=1, sticky="w", pady=3)
        self.spin_compression.bind("<FocusOut>", lambda _e: self.changed())

        row += 1
        section(card, "Formato do áudio").grid(row=row, column=0, columnspan=2,
                                               sticky="w", pady=(10, 4))
        row += 1
        ttk.Label(card, text="Sample rate", style="Card.TLabel").grid(
            row=row, column=0, sticky="w", pady=3)
        self.var_rate = tk.StringVar(value=SAMPLE_RATES[0])
        combo = ttk.Combobox(card, textvariable=self.var_rate, values=SAMPLE_RATES,
                             width=16)
        combo.grid(row=row, column=1, sticky="w", pady=3)
        combo.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        row += 1
        ttk.Label(card, text="Canais", style="Card.TLabel").grid(
            row=row, column=0, sticky="w", pady=3)
        self.var_channels = tk.StringVar()
        self.combo_channels = ttk.Combobox(card, textvariable=self.var_channels,
                                           state="readonly", width=24)
        self.combo_channels.grid(row=row, column=1, sticky="w", pady=3)
        self.combo_channels.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        tooltip(self.combo_channels, "5.1 só é convertido para estéreo se você escolher "
                                     "explicitamente.")
        row += 1
        ttk.Label(card, text="Ganho", style="Card.TLabel").grid(
            row=row, column=0, sticky="w", pady=3)
        gain_frame = ttk.Frame(card, style="Card.TFrame")
        gain_frame.grid(row=row, column=1, sticky="w", pady=3)
        self.var_gain = tk.DoubleVar(value=0.0)
        spin = ttk.Spinbox(gain_frame, from_=-30, to=30, increment=0.5, width=7,
                           textvariable=self.var_gain, command=self.changed)
        spin.pack(side="left")
        spin.bind("<FocusOut>", lambda _e: self.changed())
        ttk.Label(gain_frame, text="dB", style="Muted.TLabel").pack(side="left", padx=4)
        row += 1
        ttk.Label(card, text="Normalização", style="Card.TLabel").grid(
            row=row, column=0, sticky="w", pady=3)
        self.var_normalize = tk.StringVar(value="off")
        self.combo_normalize = ttk.Combobox(card, textvariable=self.var_normalize,
                                            state="readonly", width=30,
                                            values=["Desligada", "EBU R128 (loudnorm)",
                                                    "Pico (dynaudnorm)"])
        self.combo_normalize.grid(row=row, column=1, sticky="w", pady=3)
        self.combo_normalize.bind("<<ComboboxSelected>>", lambda _e: self.changed())

        row += 1
        section(card, "Opções").grid(row=row, column=0, columnspan=2, sticky="w",
                                     pady=(10, 4))
        row += 1
        self.var_metadata = tk.BooleanVar(value=True)
        self.var_cover = tk.BooleanVar(value=True)
        self.var_trim = tk.BooleanVar(value=False)
        checks = ttk.Frame(card, style="Card.TFrame")
        checks.grid(row=row, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(checks, text="Preservar metadados", variable=self.var_metadata,
                        command=self.changed).pack(anchor="w")
        ttk.Checkbutton(checks, text="Preservar capa de álbum", variable=self.var_cover,
                        command=self.changed).pack(anchor="w")
        ttk.Checkbutton(checks, text="Remover silêncio inicial", variable=self.var_trim,
                        command=self.changed).pack(anchor="w")
        row += 1
        ttk.Label(card, text="Capa", style="Card.TLabel").grid(
            row=row, column=0, sticky="w", pady=3)
        cover_frame = ttk.Frame(card, style="Card.TFrame")
        cover_frame.grid(row=row, column=1, sticky="ew", pady=3)
        self.var_cover_image = tk.StringVar(value="")
        self.lbl_cover = ttk.Label(cover_frame, text="(usar a capa do arquivo)",
                                   style="Muted.TLabel", wraplength=200)
        self.lbl_cover.pack(side="left", fill="x", expand=True)
        ttk.Button(cover_frame, text="Escolher…", style="Small.TButton",
                   command=self._pick_cover).pack(side="right")
        ttk.Button(cover_frame, text="Limpar", style="Small.TButton",
                   command=self._clear_cover).pack(side="right", padx=4)
        tooltip(cover_frame, "Imagem usada como capa do arquivo de saída "
                             "(JPEG/PNG). Sobrescreve a capa original.")
        row += 1
        ttk.Label(card, text="Faixa de áudio", style="Card.TLabel").grid(
            row=row, column=0, sticky="w", pady=3)
        self.var_stream = tk.StringVar()
        self.combo_stream = ttk.Combobox(card, textvariable=self.var_stream,
                                         state="readonly", width=30)
        self.combo_stream.grid(row=row, column=1, sticky="ew", pady=3)
        self.combo_stream.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        self._stream_map: dict[str, str] = {"auto": "auto"}

        row += 1
        self.lbl_warning = ttk.Label(card, text="", style="Hint.TLabel",
                                     foreground=theme.WARN, wraplength=420)
        self.lbl_warning.grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self._audio_rows = card

    # ------------------------------------------------------------------
    def _build_video(self, parent: ttk.Frame) -> None:
        card = ttk.LabelFrame(parent, text="Vídeo (opcional)", style="TLabelframe",
                              padding=10)
        card.pack(fill="x")
        card.columnconfigure(1, weight=1)
        rows = []
        rows.append(("Contêiner de saída", self._video_container_widget(card)))
        rows[0][1].grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(card, text=rows[0][0], style="Card.TLabel").grid(row=0, column=0,
                                                                   sticky="w", pady=3)
        ttk.Label(card, text="Codec de vídeo", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", pady=3)
        self.var_vcodec = tk.StringVar()
        self.combo_vcodec = ttk.Combobox(card, textvariable=self.var_vcodec,
                                         state="readonly")
        self.combo_vcodec.grid(row=1, column=1, sticky="ew", pady=3)
        self.combo_vcodec.bind("<<ComboboxSelected>>", self._on_vcodec_changed)
        self._video_option_map: dict[str, VideoOption] = {}

        ttk.Label(card, text="Controle de qualidade", style="Card.TLabel").grid(
            row=2, column=0, sticky="w", pady=3)
        self.var_vmode = tk.StringVar(value="crf")
        mode_frame = ttk.Frame(card, style="Card.TFrame")
        mode_frame.grid(row=2, column=2, sticky="w", pady=3)
        self.rb_vcrf = ttk.Radiobutton(mode_frame, text="Qualidade (CRF/CQ)", value="crf",
                                       variable=self.var_vmode,
                                       command=self._on_vmode_changed)
        self.rb_vcrf.pack(side="left")
        self.rb_vabr = ttk.Radiobutton(mode_frame, text="Bitrate-alvo", value="abr",
                                       variable=self.var_vmode,
                                       command=self._on_vmode_changed)
        self.rb_vabr.pack(side="left", padx=(12, 0))

        ttk.Label(card, text="Preset rápido", style="Card.TLabel").grid(
            row=2, column=0, sticky="w", pady=3)
        self.var_vpreset_quick = tk.StringVar(value=list(VIDEO_PRESETS)[0])
        self.combo_vpreset_quick = ttk.Combobox(card, textvariable=self.var_vpreset_quick,
                                                values=list(VIDEO_PRESETS),
                                                state="readonly")
        self.combo_vpreset_quick.grid(row=2, column=1, sticky="ew", pady=3)
        self.combo_vpreset_quick.bind("<<ComboboxSelected>>", self._on_quick_preset)
        tooltip(self.combo_vpreset_quick, "Ajusta rapidamente qualidade/bitrate. "
                                          "Os campos abaixo continuam editáveis.")

        ttk.Label(card, text="Qualidade", style="Card.TLabel").grid(
            row=3, column=0, sticky="w", pady=3)
        qframe = ttk.Frame(card, style="Card.TFrame")
        qframe.grid(row=3, column=1, sticky="ew", pady=3)
        self.var_vquality = tk.DoubleVar(value=23)
        self.scale_vquality = ttk.Scale(qframe, from_=0, to=51, orient="horizontal",
                                        variable=self.var_vquality,
                                        command=lambda _v: self.changed())
        self.scale_vquality.pack(side="left", fill="x", expand=True)
        self.lbl_vquality = ttk.Label(qframe, text="23", width=4, style="Card.TLabel")
        self.lbl_vquality.pack(side="left", padx=(6, 0))
        self.var_vquality.trace_add("write", lambda *_a: self.lbl_vquality.configure(
            text=f"{self.var_vquality.get():.0f}"))

        ttk.Label(card, text="Bitrate de vídeo", style="Card.TLabel").grid(
            row=4, column=0, sticky="w", pady=3)
        self.var_vbitrate = tk.StringVar(value="Automático")
        self.combo_vbitrate = ttk.Combobox(card, textvariable=self.var_vbitrate,
                                           values=VIDEO_BITRATE_PRESETS)
        self.combo_vbitrate.grid(row=4, column=1, sticky="w", pady=3)
        self.combo_vbitrate.bind("<<ComboboxSelected>>", lambda _e: self.changed())

        ttk.Label(card, text="Preset", style="Card.TLabel").grid(
            row=5, column=0, sticky="w", pady=3)
        self.var_preset = tk.StringVar()
        self.combo_preset = ttk.Combobox(card, textvariable=self.var_preset,
                                         state="readonly")
        self.combo_preset.grid(row=5, column=1, sticky="ew", pady=3)
        self.combo_preset.bind("<<ComboboxSelected>>", lambda _e: self.changed())

        ttk.Label(card, text="Resolução", style="Card.TLabel").grid(
            row=6, column=0, sticky="w", pady=3)
        self.var_resolution = tk.StringVar(value=RESOLUTION_PRESETS[0])
        self.combo_resolution = ttk.Combobox(card, textvariable=self.var_resolution,
                                             values=RESOLUTION_PRESETS)
        self.combo_resolution.grid(row=6, column=1, sticky="ew", pady=3)
        self.combo_resolution.bind("<<ComboboxSelected>>", self._on_resolution_changed)
        tooltip(self.combo_resolution, "A proporção é mantida (letterbox/pillarbox) — "
                                       "o vídeo nunca é deformado. '1280xauto' mantém o "
                                       "lado maior em 1280.")

        ttk.Label(card, text="FPS", style="Card.TLabel").grid(
            row=7, column=0, sticky="w", pady=3)
        self.var_fps = tk.StringVar(value=FPS_PRESETS[0])
        self.combo_fps = ttk.Combobox(card, textvariable=self.var_fps, values=FPS_PRESETS)
        self.combo_fps.grid(row=7, column=1, sticky="w", pady=3)
        self.combo_fps.bind("<<ComboboxSelected>>", lambda _e: self.changed())

        ttk.Label(card, text="Pixel format", style="Card.TLabel").grid(
            row=8, column=0, sticky="w", pady=3)
        self.var_pixfmt = tk.StringVar(value=PIXEL_FORMATS[0])
        self.combo_pixfmt = ttk.Combobox(card, textvariable=self.var_pixfmt,
                                         values=PIXEL_FORMATS, state="readonly", width=18)
        self.combo_pixfmt.grid(row=8, column=1, sticky="w", pady=3)
        self.combo_pixfmt.bind("<<ComboboxSelected>>", lambda _e: self.changed())

        ttk.Label(card, text="Perfil / nível", style="Card.TLabel").grid(
            row=9, column=0, sticky="w", pady=3)
        pf = ttk.Frame(card, style="Card.TFrame")
        pf.grid(row=9, column=1, sticky="ew", pady=3)
        self.var_vprofile = tk.StringVar()
        self.combo_vprofile = ttk.Combobox(pf, textvariable=self.var_vprofile,
                                           state="readonly", width=14)
        self.combo_vprofile.pack(side="left")
        self.combo_vprofile.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        self.var_vlevel = tk.StringVar()
        self.combo_vlevel = ttk.Combobox(pf, textvariable=self.var_vlevel,
                                         state="readonly", width=10)
        self.combo_vlevel.pack(side="left", padx=(6, 0))
        self.combo_vlevel.bind("<<ComboboxSelected>>", lambda _e: self.changed())

        ttk.Label(card, text="Legendas", style="Card.TLabel").grid(
            row=10, column=0, sticky="w", pady=3)
        self.var_subtitles = tk.StringVar(value="Copiar quando possível")
        self.combo_subtitles = ttk.Combobox(card, textvariable=self.var_subtitles,
                                            state="readonly",
                                            values=["Copiar quando possível",
                                                    "Não incluir"])
        self.combo_subtitles.grid(row=10, column=1, sticky="w", pady=3)
        self.combo_subtitles.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        self.var_hwdecode = tk.BooleanVar(value=False)
        ttk.Checkbutton(card, text="Usar decodificação por hardware quando disponível",
                        variable=self.var_hwdecode, command=self.changed
                        ).grid(row=11, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.video_card = card

    def _video_container_widget(self, parent: ttk.Misc) -> ttk.Widget:
        self.var_vcontainer = tk.StringVar()
        self.combo_vcontainer = ttk.Combobox(parent, textvariable=self.var_vcontainer,
                                             state="readonly")
        self.combo_vcontainer.bind("<<ComboboxSelected>>", self._on_vcontainer_changed)
        return self.combo_vcontainer

    # ------------------------------------------------------------------
    def _build_extraction(self, parent: ttk.Frame) -> None:
        card = ttk.LabelFrame(parent, text="Extração rápida", style="TLabelframe",
                              padding=10)
        card.pack(fill="x")
        hint(card, "Operações que partem do arquivo de origem, úteis para vídeos com "
                   "várias faixas. Aplicam-se aos arquivos selecionados (ou à fila toda)."
             ).pack(anchor="w", pady=(0, 6))
        grid = ttk.Frame(card, style="Card.TFrame")
        grid.pack(fill="x")
        buttons = [
            ("Extrair áudio original (sem recodificar)", self._extract_copy,
             "Escolhe automaticamente um contêiner compatível (ex.: AAC do MP4 → .aac "
             "ou .m4a) e copia o stream, sem perda."),
            ("Extrair áudio convertendo", self._extract_convert,
             "Decodifica a faixa escolhida e gera no formato configurado no painel Áudio."),
            ("Extrair vídeo sem áudio (remux)", self._extract_video_only,
             "Copia o vídeo sem recodificar e remove o áudio, quando compatível."),
            ("Remux: copiar tudo", self._remux_all,
             "Copia vídeo e áudio sem recodificar para o contêiner escolhido em Vídeo."),
        ]
        for index, (text, command, tip) in enumerate(buttons):
            button = ttk.Button(grid, text=text, command=command)
            button.grid(row=index, column=0, sticky="ew", pady=2)
            tooltip(button, tip)
        grid.columnconfigure(0, weight=1)

    def _build_summary(self) -> None:
        bar = ttk.Frame(self, style="Toolbar.TFrame", padding=(10, 6))
        bar.pack(fill="x", pady=(10, 0))
        self.summary_label = ttk.Label(bar, text="", style="StatusAccent.TLabel")
        self.summary_label.pack(side="left")
        self.btn_apply = ttk.Button(bar, text="Aplicar configuração aos selecionados",
                                    style="Accent.TButton", command=self.apply_to_selection)
        self.btn_apply.pack(side="right")
        self.btn_add = ttk.Button(bar, text="Adicionar arquivos…",
                                  command=self._add_files)
        self.btn_add.pack(side="right", padx=(0, 8))

    def _pick_cover(self) -> None:
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            parent=self, title="Escolher imagem da capa",
            filetypes=[("Imagens", "*.jpg *.jpeg *.png *.bmp *.webp"),
                       ("Todos os arquivos", "*")])
        if path:
            self.var_cover_image.set(path)
            import os as _os
            self.lbl_cover.configure(text=_os.path.basename(path))
            self.changed()

    def _clear_cover(self) -> None:
        self.var_cover_image.set("")
        self.lbl_cover.configure(text="(usar a capa do arquivo)")
        self.changed()

    def _on_quick_preset(self, _event=None) -> None:
        preset = VIDEO_PRESETS.get(self.var_vpreset_quick.get(), {})
        codec = preset.get("codec")
        if codec == "copy":
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
        elif self.var_vmode.get() == "abr" and "bitrate" not in preset:
            self.var_vmode.set("crf")
        self.update_visibility()
        self.changed()

    def _add_files(self) -> None:
        if hasattr(self.app, "request_add_files"):
            self.app.request_add_files()

    # ------------------------------------------------------------------
    # Carregar / salvar widget <-> modelo
    # ------------------------------------------------------------------
    def load_from_app(self) -> None:
        self._loading = True
        try:
            app = self.app
            self._refresh_container_choices()
            self._select_container(app.container if app.kind == "audio" else
                                   (self._first_container_for_kind("video")))
            self._refresh_audio_codecs()
            codec = app.audio.codec
            option = self._audio_option_map.get(codec)
            if option is None:
                fallback = self.catalog.default_audio_codec(app.container)
                option = self._audio_option_map.get(fallback)
            if option:
                self.var_codec.set(option.label)
            self._load_audio_values(app.audio)
            self._refresh_channel_choices()
            self._refresh_stream_choices(None)
            self.var_metadata.set(app.audio.copy_metadata)
            self.var_cover.set(app.audio.cover_copy)
            self.var_trim.set(app.audio.trim_silence)
            image = app.audio.cover_image or ""
            self.var_cover_image.set(image)
            import os as _os
            self.lbl_cover.configure(text=(_os.path.basename(image) if image
                                           else "(usar a capa do arquivo)"))
            self._refresh_video_containers(preferred=app.container
                                           if app.kind == "video" else "")
            self._refresh_video_codecs()
            voption = self._video_option_map.get(app.video.codec)
            if voption:
                self.var_vcodec.set(voption.label)
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
        normalize = {"off": "Desligada", "ebu": "EBU R128 (loudnorm)",
                     "peak": "Pico (dynaudnorm)"}.get(settings.normalize, "Desligada")
        self.var_normalize.set(normalize)
        stream = str(settings.stream or "auto")
        self.var_stream.set(self._stream_map.get(stream, self._stream_map.get(
            "auto", "Automática (faixa padrão)")))
        self._apply_channel_selection(settings.channels or "keep")

    def _apply_channel_selection(self, channels: str) -> None:
        for key, choice in CHANNELS.items():
            if key == str(channels):
                self.var_channels.set(choice.label)
                self._channel_key = key
                return
        self.var_channels.set(CHANNELS["keep"].label)
        self._channel_key = "keep"

    def _load_video_values(self, settings: VideoSettings) -> None:
        self.var_vmode.set("crf" if settings.mode == "crf" else "abr")
        try:
            self.var_vquality.set(float(settings.quality or 23))
        except (TypeError, ValueError):
            self.var_vquality.set(23)
        self.var_vbitrate.set(settings.bitrate or "Automático")
        preset = settings.preset or (VIDEO_CODECS.get(settings.codec).default_preset
                                     if settings.codec in VIDEO_CODECS else "")
        self.var_preset.set(preset)
        resolution = settings.resolution or "keep"
        if resolution in ("keep", ""):
            self.var_resolution.set(RESOLUTION_PRESETS[0])
        else:
            if resolution not in RESOLUTION_PRESETS:
                self.combo_resolution.configure(values=[resolution] + RESOLUTION_PRESETS)
            self.var_resolution.set(resolution)
        fps = str(settings.fps or "keep")
        self.var_fps.set(FPS_PRESETS[0] if fps in ("keep", "") else fps)
        self.var_pixfmt.set(settings.pix_fmt if settings.pix_fmt in PIXEL_FORMATS
                            else PIXEL_FORMATS[0])
        self.var_vprofile.set(settings.profile or "")
        self.var_vlevel.set(settings.level or "")
        if settings.codec in VIDEO_CODECS:
            self._configure_video_for_codec(VIDEO_CODECS[settings.codec], reset=False)
            self.var_vquality.set(float(settings.quality or
                                        VIDEO_CODECS[settings.codec].quality_default))
            self.var_vprofile.set(settings.profile or "")
            self.var_vlevel.set(settings.level or "")
        self.var_subtitles.set("Copiar quando possível")
        self.var_hwdecode.set(settings.hw_decode)

    def collect_audio(self) -> AudioSettings:
        option = self._current_audio_option()
        codec = option.id if option else "libmp3lame"
        bitrate_value = self.var_bitrate.get().strip() or "192"
        if bitrate_value.isdigit() is False:
            try:
                value = float(bitrate_value.replace(",", "."))
                bitrate_value = f"{value:g}"
            except ValueError:
                bitrate_value = "192"
        mode = "vbr" if self.var_mode.get() == "vbr" else "cbr"
        rate_text = self.var_rate.get().strip()
        sample_rate = "keep" if rate_text == SAMPLE_RATES[0] else rate_text
        normalize = {"EBU R128 (loudnorm)": "ebu", "Pico (dynaudnorm)": "peak"}.get(
            self.var_normalize.get(), "off")
        stream = self._stream_map_reverse().get(self.var_stream.get(), "auto")
        return AudioSettings(
            codec=codec,
            mode=mode,
            bitrate=f"{bitrate_value}k",
            quality=int(self.var_quality.get()),
            compression_level=int(self.var_compression.get())
            if str(self.var_compression.get()).lstrip("-").isdigit() else None,
            channels=getattr(self, "_channel_key", "keep"),
            sample_rate=sample_rate,
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
        codec = option.id if option else "copy"
        resolution = self.var_resolution.get()
        time_resolution = "keep" if resolution == RESOLUTION_PRESETS[0] else resolution
        fps = self.var_fps.get()
        bitrate = "" if self.var_vbitrate.get() in ("", "Automático") else \
            self.var_vbitrate.get().strip()
        preset = self.var_preset.get()
        return VideoSettings(
            codec=codec,
            mode="crf" if self.var_vmode.get() == "crf" else "abr",
            quality=float(self.var_vquality.get()),
            bitrate=bitrate,
            preset=preset,
            resolution=time_resolution,
            fps="keep" if fps == FPS_PRESETS[0] else fps,
            pix_fmt=self.var_pixfmt.get(),
            profile=self.var_vprofile.get(),
            level=self.var_vlevel.get(),
            hw_decode=bool(self.var_hwdecode.get()),
        )

    def _stream_map_reverse(self) -> dict[str, str]:
        reverse = {}
        for key, label in self._stream_map.items():
            reverse[label] = key
        return reverse

    # ------------------------------------------------------------------
    # Construtores de opções
    # ------------------------------------------------------------------
    def _refresh_container_choices(self) -> None:
        self._audio_container_map: dict[str, str] = {}
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
        self._audio_container_labels = labels
        self.combo_container.configure(values=labels)

    def _first_container_for_kind(self, kind: str) -> str:
        if kind == "audio":
            return "mp3"
        for key in VIDEO_CONTAINER_KEYS:
            if self.catalog.container_available(key):
                return key
        return "mkv"

    def _select_container(self, key: str) -> None:
        for label, value in self._audio_container_map.items():
            if value == key:
                self.var_container.set(label)
                return
        if key in self._audio_container_map.values():
            return
        # contêiner não-audio (ex.: mp4) -> usa mka como equivalente de áudio
        for label, value in self._audio_container_map.items():
            if value == "mka":
                self.var_container.set(label)
                return

    def _current_container_key(self) -> str:
        return self._audio_container_map.get(self.var_container.get(), "mp3")

    def _current_audio_option(self) -> AudioOption | None:
        return self._audio_option_map.get(self.var_codec.get())

    def _current_video_option(self) -> VideoOption | None:
        return self._video_option_map.get(self.var_vcodec.get())

    def _refresh_audio_codecs(self) -> None:
        container = self._current_container_key()
        options = self.catalog.audio_options(container)
        self._audio_option_map = {}
        labels = []
        for option in options:
            label = option.label
            if option.is_copy:
                label += "  (somente se o contêiner aceitar o codec original)"
            labels.append(label)
            self._audio_option_map[label] = option
        self.combo_codec.configure(values=labels)

    def _refresh_channel_choices(self) -> None:
        option = self._current_audio_option()
        codec = AUDIO_CODECS.get(option.id) if option and not option.is_copy else None
        labels = []
        self._channel_labels = {}
        for key, choice in CHANNELS.items():
            if key != "keep" and codec and int(key) > codec.max_channels:
                continue
            labels.append(choice.label)
            self._channel_labels[choice.label] = key
        self.combo_channels.configure(values=labels)
        current = getattr(self, "_channel_key", "keep")
        self.var_channels.set(CHANNELS.get(current, CHANNELS["keep"]).label)

    def _refresh_stream_choices(self, info) -> None:
        from ..media.analyzer import stream_choices
        self._stream_map = {}
        labels = []
        for value, label in stream_choices(info) if info else [("auto",
                                                                "Automática (faixa padrão)")]:
            self._stream_map[value] = label
            labels.append(label)
        self.combo_stream.configure(values=labels)
        if info:
            current = self.app.audio.stream or "auto"
            self.var_stream.set(self._stream_map.get(current, self._stream_map["auto"]))
        else:
            self.var_stream.set(self._stream_map.get("auto", ""))

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
        for label, key in self._video_container_map.items():
            if key == self._current_container_key() and target is None:
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
        container = self._current_vcontainer_key()
        options = self.catalog.video_options(container)
        self._video_option_map = {}
        labels = []
        for option in options:
            labels.append(option.label)
            self._video_option_map[option.label] = option
        self.combo_vcodec.configure(values=labels)

    # ------------------------------------------------------------------
    # Eventos
    # ------------------------------------------------------------------
    def _on_container_changed(self, _event=None) -> None:
        if self._loading:
            return
        self.app.container = self._current_container_key()
        self._refresh_audio_codecs()
        default_audio = self.catalog.default_audio_codec(self.app.container) \
            if self.app.container != "copy" else "copy"
        for label, option in self._audio_option_map.items():
            if option.id == default_audio:
                self.var_codec.set(label)
                break
        self._refresh_channel_choices()
        self._refresh_video_containers()
        self._refresh_video_codecs()
        self.update_visibility()
        self.changed()

    def _on_codec_changed(self, _event=None) -> None:
        if self._loading:
            return
        self._refresh_channel_choices()
        self.update_visibility()
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
        self._refresh_video_containers()
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
        elif option and option.id == CODEC_COPY:
            self.var_vmode.set("crf")
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

    # ------------------------------------------------------------------
    def update_visibility(self) -> None:
        option = self._current_audio_option()
        codec_id = option.id if option else ""
        is_copy = codec_id == CODEC_COPY
        info = AUDIO_CODECS.get(codec_id)
        lossless = bool(info and info.lossless)
        self.combo_container.state(["!disabled"] if not self.app.queue.is_running
                                   else ["disabled"])

        state = "disabled" if is_copy else "!disabled"
        show_vbr = bool(info and info.vbr)
        self.rb_vbr.state(["!disabled"] if show_vbr and not is_copy else ["disabled"])
        if not show_vbr and self.var_mode.get() == "vbr":
            self.var_mode.set("cbr")
        use_vbr = self.var_mode.get() == "vbr" and show_vbr and not is_copy
        self.combo_bitrate.configure(state="normal" if not use_vbr and not is_copy
                                     and not lossless else "disabled")
        self.scale_quality.state(["!disabled"] if use_vbr else ["disabled"])
        if info and use_vbr:
            self.scale_quality.configure(from_=info.quality_range[0],
                                         to=info.quality_range[1])
        self.spin_compression.configure(state="normal" if lossless and info and
                                        info.compression and not is_copy else "disabled")
        if info and info.quality_range and not lossless:
            self.scale_quality.configure(from_=info.quality_range[0],
                                         to=info.quality_range[1])
        self.combo_channels.state([state])
        self.combo_normalize.state([state])

        voption = self._current_video_option()
        vcodec = voption.id if voption else CODEC_COPY
        vinfo = VIDEO_CODECS.get(vcodec)
        copy_or_none = vcodec in (CODEC_COPY, CODEC_NONE)
        disable = ["disabled"] if copy_or_none else ["!disabled"]
        for widget in (self.combo_preset, self.combo_resolution, self.combo_fps,
                       self.combo_pixfmt, self.combo_vprofile, self.combo_vlevel,
                       self.combo_vbitrate, self.scale_vquality, self.rb_vcrf,
                       self.rb_vabr, self.combo_subtitles):
            widget.state(disable)
        if vcodec == CODEC_COPY:
            hint_text = "O vídeo original será copiado sem recodificar."
        elif vcodec == CODEC_NONE:
            hint_text = "O vídeo será removido (extração de áudio)."
        elif vinfo and vinfo.hwaccel:
            hint_text = ("Codificação por hardware: não assume mesma qualidade ou "
                         "velocidade da CPU. Compare com x264/x265 quando possível.")
        else:
            hint_text = ""
        existing = getattr(self, "_video_hint", None)
        if existing is None:
            self._video_hint = ttk.Label(self.video_card, text=hint_text,
                                         style="Hint.TLabel", wraplength=420)
            self._video_hint.grid(row=12, column=0, columnspan=2, sticky="w",
                                  pady=(6, 0))
        else:
            self._video_hint.configure(text=hint_text)
        self._update_extraction_hint(codec_id)

    def _update_extraction_hint(self, codec_id: str) -> None:
        lines = []
        if codec_id == CODEC_COPY:
            lines.append("Modo de extração sem recodificação: o executor escolhe um "
                         "contêiner compatível com o codec do arquivo original.")
        if getattr(self, "_channel_key", "keep") == "keep":
            lines.append("Canais: preservados como no original (5.1 não vira estéreo "
                         "sem escolha explícita).")
        self.lbl_warning.configure(text="\n".join(lines))

    def _update_summary(self) -> None:
        container = self._current_container_key()
        container_info = CONTAINERS.get(container)
        option = self._current_audio_option()
        if container == "copy":
            text = "Saída: contêiner automático, áudio copiado sem recodificar"
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
        self._loading = False  # uma alteração do usuário sempre vence um load em andamento
        app = self.app
        app.container = self._current_container_key()
        app.audio = self.collect_audio()
        app.video = self.collect_video()
        self._update_summary()
        self.on_change()

    def apply_to_selection(self) -> None:
        self.changed()
        selected = getattr(self, "_selected_job_ids", [])
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
        selected = getattr(self, "_selected_job_ids", [])
        if selected:
            return selected
        return [job.id for job in self.app.queue.snapshot()
                if job.status in ("pending", "error", "cancelled")]

    def _apply_extraction(self, config_update: dict, kind: str, container: str,
                          message: str) -> None:
        from ..media.models import ConversionConfig
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
        self.app.queue.set_job_config(self._target_ids(), config)
        self.notify("Faixa de áudio será convertida para o formato do painel Áudio.")

    def _extract_video_only(self) -> None:
        self._apply_extraction({"audio.codec": "none", "video.codec": "copy"},
                               "video", self._current_vcontainer_key(),
                               "Vídeo será copiado sem áudio.")

    def _remux_all(self) -> None:
        self._apply_extraction({"audio.codec": "copy", "video.codec": "copy"},
                               "video", self._current_vcontainer_key(),
                               "Remux (sem recodificação) agendado.")

    # ------------------------------------------------------------------
    def refresh_for_job(self, job) -> None:
        """Carrega as opções de faixa de áudio conforme o arquivo selecionado."""
        info = self.app.analyzer.analyze(job.file)
        was_loading = self._loading
        self._loading = True
        try:
            self._refresh_stream_choices(info)
        finally:
            self._loading = was_loading
