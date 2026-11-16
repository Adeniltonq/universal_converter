"""Modelos de dados do núcleo (independentes de GUI).

`MediaInfo`, `StreamInfo`, `AudioSettings`, `VideoSettings`, `ConversionJob`,
`NamingTemplate` — tudo serializável em dicionários simples.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class StreamInfo:
    """Um stream de mídia, como reportado pelo FFprobe."""
    index: int
    type: str                        # audio | video | subtitle | data | attachment
    codec: str = ""
    codec_long: str = ""
    profile: str = ""
    level: Any = None
    language: str = ""
    title: str = ""
    # áudio
    channels: int = 0
    channel_layout: str = ""
    sample_rate: int = 0
    bit_depth: int = 0
    bitrate: int = 0
    # vídeo
    width: int = 0
    height: int = 0
    fps: float = 0.0
    pix_fmt: str = ""
    sar: str = ""
    dar: str = ""
    color_primaries: str = ""
    color_transfer: str = ""
    color_space: str = ""
    color_range: str = ""
    # controle
    duration: float | None = None
    default: bool = False
    forced: bool = False
    attached_pic: bool = False

    @property
    def is_cover(self) -> bool:
        return self.type == "video" and self.attached_pic

    @property
    def is_hdr(self) -> bool:
        return self.color_transfer in ("smpte2084", "arib-std-b67") or "HDR" in (self.codec_long or "")

    def display_label(self) -> str:
        parts = [self.type.capitalize(), self.codec or "?"]
        if self.type == "audio":
            info = f"{self.channels}ch"
            if self.sample_rate:
                info += f" {self.sample_rate} Hz"
            parts.append(info)
        elif self.type == "video" and not self.is_cover:
            parts.append(f"{self.width}×{self.height}")
        if self.language and self.language not in ("und", "un"):
            parts.append(self.language)
        if self.title:
            parts.append(self.title[:24])
        if self.is_cover:
            parts.append("(capa)")
        return " · ".join(p for p in parts if p)


@dataclass
class MediaInfo:
    """Resultado da análise de um arquivo."""
    path: str
    format_name: str = ""
    format_long: str = ""
    duration: float | None = None
    size: int = 0
    bitrate: int = 0
    tags: dict[str, str] = field(default_factory=dict)
    streams: list[StreamInfo] = field(default_factory=list)
    chapters: int = 0
    error: str = ""
    analyzed: bool = False

    # -- agrupamentos ---------------------------------------------------
    def by_type(self, type_: str) -> list[StreamInfo]:
        return [s for s in self.streams if s.type == type_]

    @property
    def audio_streams(self) -> list[StreamInfo]:
        return self.by_type("audio")

    @property
    def video_streams(self) -> list[StreamInfo]:
        return [s for s in self.by_type("video") if not s.is_cover]

    @property
    def subtitle_streams(self) -> list[StreamInfo]:
        return self.by_type("subtitle")

    @property
    def cover_streams(self) -> list[StreamInfo]:
        return [s for s in self.streams if s.is_cover]

    @property
    def is_audio_only(self) -> bool:
        return bool(self.audio_streams) and not self.video_streams

    @property
    def is_video(self) -> bool:
        return bool(self.video_streams)

    @property
    def main_video(self) -> StreamInfo | None:
        return self.video_streams[0] if self.video_streams else None

    @property
    def main_audio(self) -> StreamInfo | None:
        audio = self.audio_streams
        for stream in audio:
            if stream.default:
                return stream
        return audio[0] if audio else None

    def container_key(self) -> str:
        """Chave de contêiner aproximada a partir do format_name do FFprobe."""
        from .codecs import CONTAINERS, EXT_TO_CONTAINER
        names = set(self.format_name.split(","))
        order = [
            ("mp3", "mp3"), ("flac", "flac"), ("wav", "wav"), ("aiff", "aiff"),
            ("asf", "wma"), ("amr", "amr"), ("caf", "caf"), ("matroska", "mkv"),
            ("webm", "webm"), ("mov", "m4a"), ("mpegts", "ts"), ("avi", "avi"),
            ("flv", "flv"), ("3gp", "3gp"), ("ogg", "ogg"), ("ac3", "ac3"),
            ("eac3", "eac3"), ("dts", "dts"), ("adts", "adts"),
        ]
        for name, key in order:
            if name in names:
                if key == "mkv" and self.is_audio_only:
                    return "mka"
                if key == "ogg":
                    audio = self.main_audio
                    if audio and audio.codec == "opus":
                        return "opus"
                if key == "m4a" and self.is_video:
                    return "mp4"
                return key
        if "mpeg" in names:
            return "mpeg"
        ext = self.path.rsplit(".", 1)[-1].lower() if "." in self.path else ""
        if ext in EXT_TO_CONTAINER:
            key = EXT_TO_CONTAINER[ext]
            if key in CONTAINERS:
                return key
        return "unk"

    def format_label(self) -> str:
        key = self.container_key()
        from .codecs import CONTAINERS
        container = CONTAINERS.get(key)
        if container:
            return container.label.split(" (")[0]
        if self.format_long:
            return self.format_long.split(" (")[0]
        return (self.format_name.split(",")[0] or "?").upper()

    def cover_mime(self) -> str:
        covers = self.cover_streams
        if not covers:
            return ""
        return {"mjpeg": "image/jpeg", "png": "image/png",
                "bmp": "image/bmp", "webp": "image/webp"}.get(covers[0].codec, "")

    def tag(self, *names: str) -> str:
        lower = {k.lower(): v for k, v in self.tags.items()}
        for name in names:
            value = lower.get(name.lower())
            if value:
                return str(value)
        return ""

    def to_dict(self) -> dict:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "MediaInfo":
        streams = [StreamInfo(**s) for s in data.get("streams", [])]
        obj = cls(path=data.get("path", ""),
                  format_name=data.get("format_name", ""),
                  format_long=data.get("format_long", ""),
                  duration=data.get("duration"),
                  size=_as_int(data.get("size")) or 0,
                  bitrate=_as_int(data.get("bitrate")) or 0,
                  tags=data.get("tags", {}) or {},
                  chapters=_as_int(data.get("chapters")) or 0,
                  error=data.get("error", ""),
                  analyzed=bool(data.get("analyzed")))
        obj.streams = streams
        return obj


def parse_fps(value: str | None) -> float:
    if not value:
        return 0.0
    if "/" in value:
        num, _, den = value.partition("/")
        n, d = _as_float(num), _as_float(den)
        if not n or not d:
            return 0.0
        return n / d
    return _as_float(value) or 0.0


def media_info_from_probe(path: str, probe: dict, size: int | None = None) -> MediaInfo:
    """Converte a saída JSON do FFprobe em MediaInfo."""
    fmt = probe.get("format", {}) or {}
    info = MediaInfo(
        path=path,
        format_name=fmt.get("format_name", "") or "",
        format_long=fmt.get("format_long_name", "") or "",
        duration=_as_float(fmt.get("duration")),
        size=_as_int(fmt.get("size")) or (size or 0),
        bitrate=_as_int(fmt.get("bit_rate")) or 0,
        tags={str(k): str(v) for k, v in (fmt.get("tags") or {}).items()},
        chapters=len(probe.get("chapters") or []),
        analyzed=True,
    )
    for raw in probe.get("streams", []) or []:
        disp = raw.get("disposition") or {}
        tags = {str(k).lower(): str(v) for k, v in (raw.get("tags") or {}).items()}
        stream = StreamInfo(
            index=_as_int(raw.get("index")) or 0,
            type=raw.get("codec_type", "data"),
            codec=raw.get("codec_name", "") or "",
            codec_long=raw.get("codec_long_name", "") or "",
            profile=raw.get("profile", "") or "",
            level=raw.get("level"),
            language=tags.get("language", "") or "",
            title=tags.get("title", "") or "",
            channels=_as_int(raw.get("channels")) or 0,
            channel_layout=raw.get("channel_layout", "") or "",
            sample_rate=_as_int(raw.get("sample_rate")) or 0,
            bit_depth=_as_int(raw.get("bits_per_raw_sample")) or
                      _as_int(raw.get("bits_per_sample")) or 0,
            bitrate=_as_int(raw.get("bit_rate")) or 0,
            width=_as_int(raw.get("width")) or 0,
            height=_as_int(raw.get("height")) or 0,
            fps=parse_fps(raw.get("avg_frame_rate")) or parse_fps(raw.get("r_frame_rate")),
            pix_fmt=raw.get("pix_fmt", "") or "",
            sar=raw.get("sample_aspect_ratio", "") or "",
            dar=raw.get("display_aspect_ratio", "") or "",
            color_primaries=raw.get("color_primaries", "") or "",
            color_transfer=raw.get("color_transfer", "") or "",
            color_space=raw.get("color_space", "") or "",
            color_range=raw.get("color_range", "") or "",
            duration=_as_float(raw.get("duration")),
            default=bool(disp.get("default")),
            forced=bool(disp.get("forced")),
            attached_pic=bool(disp.get("attached_pic")),
        )
        info.streams.append(stream)
    if info.duration is None:
        durations = [s.duration for s in info.streams if s.duration]
        if durations:
            info.duration = max(durations)
    return info


# ---------------------------------------------------------------------------
# Configurações de conversão
# ---------------------------------------------------------------------------

@dataclass
class AudioSettings:
    codec: str = "libmp3lame"          # "copy" | "none" | id de encoder
    mode: str = "cbr"                  # cbr | vbr | quality
    bitrate: str = "192k"              # "192k" | "" (automático)
    quality: int = 2                   # valor de -q:a (VBR)
    compression_level: int | None = None
    channels: str = "keep"
    sample_rate: str = "keep"
    bit_depth: str = ""                # "" = automático | 16 | 24 | 32
    gain_db: float = 0.0
    normalize: str = "off"             # off | ebu (loudnorm 2 passadas) | peak
    normalize_target: float = -14.0
    trim_silence: bool = False
    stream: str = "auto"               # auto | índice | "all"
    copy_metadata: bool = True
    cover_copy: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "AudioSettings":
        obj = cls()
        for key, value in (data or {}).items():
            if hasattr(obj, key):
                setattr(obj, key, value)
        return obj


@dataclass
class VideoSettings:
    codec: str = "copy"                # "copy" | "none" | id de encoder
    mode: str = "crf"                  # crf | abr
    quality: float = 23                # CRF/CQ
    bitrate: str = ""                  # ABR alvo (ex.: "4M")
    max_rate: str = ""
    preset: str = ""
    resolution: str = "keep"           # keep | 1920x1080 ...
    fps: str = "keep"
    pix_fmt: str = "manter"
    profile: str = ""
    level: str = ""
    hw_decode: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "VideoSettings":
        obj = cls()
        for key, value in (data or {}).items():
            if hasattr(obj, key):
                setattr(obj, key, value)
        return obj


@dataclass
class NamingTemplate:
    template: str = "{name}"
    separator: str = "_"
    prefix: str = ""
    suffix: str = ""
    replacement_from: str = ""
    replacement_to: str = ""
    case: str = "keep"
    sanitize: bool = True
    numbering: bool = False
    number_start: int = 1
    number_padding: int = 2
    number_position: str = "prefix"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "NamingTemplate":
        obj = cls()
        for key, value in (data or {}).items():
            if hasattr(obj, key):
                setattr(obj, key, value)
        return obj


@dataclass
class ConversionConfig:
    """Configuração completa aplicada a uma tarefa."""
    kind: str = "audio"                 # audio | video
    container: str = "mp3"              # chave em CONTAINERS
    audio: AudioSettings = field(default_factory=AudioSettings)
    video: VideoSettings = field(default_factory=VideoSettings)
    subtitles: str = "copy"             # copy | none
    chapters: bool = True

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "container": self.container,
            "audio": self.audio.to_dict(),
            "video": self.video.to_dict(),
            "subtitles": self.subtitles,
            "chapters": self.chapters,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "ConversionConfig":
        data = data or {}
        return cls(
            kind=data.get("kind", "audio"),
            container=data.get("container", "mp3"),
            audio=AudioSettings.from_dict(data.get("audio")),
            video=VideoSettings.from_dict(data.get("video")),
            subtitles=data.get("subtitles", "copy"),
            chapters=bool(data.get("chapters", True)),
        )


@dataclass
class ConversionJob:
    """Uma tarefa da fila (referencia um arquivo no disco)."""
    id: int = 0
    file: str = ""
    config: ConversionConfig = field(default_factory=ConversionConfig)
    output_dir: str = ""
    override_name: str = ""
    status: str = "pending"             # pending | running | done | error | cancelled
    progress: float = 0.0
    message: str = ""
    output_path: str = ""
    duration: float | None = None
    size: int = 0
    created: float = 0.0

    @property
    def base_name(self) -> str:
        import os
        return os.path.splitext(os.path.basename(self.file))[0]

    def to_dict(self) -> dict:
        return {
            "id": self.id, "file": self.file, "config": self.config.to_dict(),
            "output_dir": self.output_dir, "override_name": self.override_name,
            "status": self.status, "progress": self.progress,
            "message": self.message, "output_path": self.output_path,
            "duration": self.duration, "size": self.size, "created": self.created,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConversionJob":
        return cls(
            id=int(data.get("id", 0)),
            file=data.get("file", ""),
            config=ConversionConfig.from_dict(data.get("config")),
            output_dir=data.get("output_dir", ""),
            override_name=data.get("override_name", ""),
            status="pending" if data.get("status") == "running" else data.get("status", "pending"),
            progress=float(data.get("progress") or 0.0),
            message=data.get("message", ""),
            output_path=data.get("output_path", ""),
            duration=data.get("duration"),
            size=int(data.get("size") or 0),
            created=float(data.get("created") or 0.0),
        )
