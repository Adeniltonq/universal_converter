"""Catálogo de encoders disponíveis, derivado da instalação real do FFmpeg.

`CodecCatalog` cruza o conhecimento estático (`codecs.py`) com o que o
FFmpeg da máquina realmente oferece e expõe consultas como "quais contêineres
aceitam este codec?" ou "quais codecs um contêiner aceita?".
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from .codecs import (
    AUDIO_CODECS, AUDIO_CODEC_ORDER, CONTAINERS, CONTAINER_DEFAULT_EXT, VIDEO_CODECS,
    VIDEO_CODEC_ORDER, CODEC_COPY, CODEC_NONE, Container, AudioCodec, VideoCodec,
)
from .ffmpeg import FFmpegInfo


@dataclass(frozen=True)
class AudioOption:
    id: str
    label: str
    info: AudioCodec | None
    is_copy: bool = False


@dataclass(frozen=True)
class VideoOption:
    id: str
    label: str
    info: VideoCodec | None
    is_copy: bool = False


_FALLBACK_VIDEO = (
    ("ffv1", "FFV1 (sem perdas)", None),
    ("utvideo", "Ut Video (sem perdas)", None),
    ("huffyuv", "HuffYUV (sem perdas)", None),
    ("prores", "Apple ProRes", None),
    ("mjpeg", "MJPEG", None),
    ("theora", "Theora", None),
    ("flv1", "Sorenson H.263", None),
    ("wmv1", "WMV1", None),
)


class CodecCatalog:
    """Consultas sobre codecs/contêineres suportados nesta instalação."""

    def __init__(self, ff: FFmpegInfo):
        self.ff = ff
        self._lock = threading.Lock()
        self._audio_cache: dict[tuple, list[AudioOption]] = {}
        self._video_cache: dict[tuple, list[VideoOption]] = {}

    @property
    def ready(self) -> bool:
        return self.ff.loaded and not self.ff.error

    # -- padrões --------------------------------------------------------
    def default_audio_codec(self, container_key: str) -> str:
        """Encoder de áudio preferido para o contêiner (o "óbvio" para o usuário)."""
        preferences = {
            "mp3": ("libmp3lame",),
            "m4a": ("aac", "libfdk_aac", "alac"),
            "adts": ("aac", "libfdk_aac"),
            "flac": ("flac",),
            "ogg": ("libvorbis", "libopus", "flac"),
            "opus": ("libopus",),
            "wav": ("pcm_s16le", "pcm_s24le", "pcm_f32le"),
            "aiff": ("pcm_s16be", "pcm_s24be"),
            "caf": ("alac", "pcm_s16le"),
            "wma": ("wmav2", "wmav1"),
            "ac3": ("ac3",),
            "eac3": ("eac3",),
            "dts": ("dca",),
            "amr": ("libopencore_amrnb", "libvo_amrwbenc"),
        }
        available = self.audio_encoders()
        for candidate in preferences.get(container_key, ()):
            if candidate in available:
                return candidate
        container = CONTAINERS.get(container_key)
        if container:
            for codec_id in container.audio_codecs:
                if codec_id in AUDIO_CODECS and codec_id in available:
                    return codec_id
        return "libmp3lame"

    def default_video_codec(self, container_key: str) -> str:
        preferences = {
            "mp4": ("libx264", "h264_nvenc", "libopenh264", "mpeg4", "copy"),
            "mkv": ("libx264", "copy"),
            "mov": ("libx264", "h264_videotoolbox", "mpeg4", "copy"),
            "webm": ("libvpx-vp9", "copy"),
            "avi": ("mpeg4", "copy"),
            "mpeg": ("mpeg2video", "copy"),
            "ts": ("libx264", "copy"),
            "flv": ("libx264", "copy"),
            "wmv": ("wmv2", "copy"),
            "3gp": ("h263", "mpeg4", "copy"),
            "ogv": ("libtheora", "copy"),
        }
        available = self.video_encoders()
        for candidate in preferences.get(container_key, ("copy",)):
            if candidate == "copy" or candidate in available:
                return candidate
        options = [o.id for o in self.video_options(container_key) if not o.is_copy
                   and o.id != CODEC_NONE]
        return options[0] if options else CODEC_COPY

    def audio_encoders(self) -> set[str]:
        return self.ff.audio_encoders()

    def video_encoders(self) -> set[str]:
        return self.ff.video_encoders()

    # -- contêineres ----------------------------------------------------
    def container_available(self, key: str) -> bool:
        if key == "copy":
            return True
        container = CONTAINERS.get(key)
        if not container:
            return False
        if container.muxer is None:
            return True  # a extensão decide o muxer
        return self.ff.has_muxer(container.muxer)

    def container_extension(self, key: str, kind: str = "audio") -> str:
        container = CONTAINERS.get(key)
        if not container:
            return "bin"
        if container.kind == "copy":
            return ""
        exts = container.video_exts if kind in ("video", "both") else container.audio_exts
        if exts:
            return exts[0]
        return CONTAINER_DEFAULT_EXT.get(key, "bin")

    def _container_audio_ok(self, container: Container, encoder: str) -> bool:
        if encoder == CODEC_COPY:
            return container.kind != "video_only"
        if container.kind == "copy":
            return True
        return encoder in container.audio_codecs

    def _container_video_ok(self, container: Container, encoder: str) -> bool:
        if container.kind in ("audio", "copy"):
            return encoder in (CODEC_COPY, CODEC_NONE)
        if encoder in (CODEC_COPY, CODEC_NONE):
            return True
        return encoder in container.video_codecs

    # -- áudio ----------------------------------------------------------
    def audio_options(self, container_key: str,
                      input_codec: str = "") -> list[AudioOption]:
        """Encoders de áudio válidos para o contêiner (só os disponíveis)."""
        container = CONTAINERS.get(container_key)
        if container is None:
            return []
        available = self.audio_encoders()
        options: list[AudioOption] = [AudioOption(CODEC_COPY, "Copiar sem recodificar", None,
                                                  True)]
        native_required = container.requires_native_aac and "aac" in available
        ids: list[str] = [
            codec_id for codec_id in container.audio_codecs
            if codec_id in AUDIO_CODECS and codec_id in available
            and not (native_required and codec_id == "libfdk_aac")
            and self._container_audio_ok(container, codec_id)]
        preferred = self.default_audio_codec(container_key)
        ids.sort(key=lambda i: (i != preferred,))
        for codec_id in ids:
            info = AUDIO_CODECS[codec_id]
            label = info.label
            input_alias = "mp3" if codec_id == "libmp3lame" else info.alias
            if input_codec and input_codec == input_alias:
                label += "  (mesmo do original)"
            options.append(AudioOption(codec_id, label, info))
        return options

    def audio_containers(self, encoder: str, kind: str = "audio") -> list[str]:
        """Contêineres válidos para o encoder informado."""
        result = []
        for key, container in CONTAINERS.items():
            if container.kind == "copy":
                continue
            if kind == "audio" and container.kind != "audio":
                continue
            if encoder == CODEC_COPY:
                if kind == "audio" and container.kind == "audio":
                    result.append(key)
                continue
            if encoder not in self.ff.encoders:
                continue
            if self._container_audio_ok(container, encoder) and \
                    self.container_available(key):
                if container.kind == "copy":
                    continue
                result.append(key)
        return result

    # -- vídeo ----------------------------------------------------------
    def video_options(self, container_key: str,
                      input_container: str = "") -> list[VideoOption]:
        container = CONTAINERS.get(container_key)
        if container is None or container.kind in ("audio", "copy"):
            return [VideoOption(CODEC_COPY, "Copiar sem recodificar", None, True),
                    VideoOption(CODEC_NONE, "Remover vídeo", None)]
        available = self.video_encoders()
        options: list[VideoOption] = [
            VideoOption(CODEC_COPY, "Copiar sem recodificar", None, True),
            VideoOption(CODEC_NONE, "Remover vídeo", None),
        ]
        ids: list[str] = []
        for codec_id in VIDEO_CODEC_ORDER:
            if codec_id not in available or codec_id in ids:
                continue
            if not self._container_video_ok(container, codec_id):
                continue
            ids.append(codec_id)
        # encoders presentes no FFmpeg mas não catalogados (ex.: ffv1, prores)
        for codec_id, _, _ in _FALLBACK_VIDEO:
            if codec_id in available and codec_id not in ids and \
                    self._container_video_ok(container, codec_id):
                ids.append(codec_id)
        for codec_id in ids:
            if codec_id in VIDEO_CODECS:
                info: VideoCodec | None = VIDEO_CODECS[codec_id]
                label = info.label
            else:
                info = None
                label = dict((c, l) for c, l, _ in _FALLBACK_VIDEO).get(codec_id, codec_id)
            options.append(VideoOption(codec_id, label, info))
        return options

    def video_containers(self, encoder: str) -> list[str]:
        result = []
        for key, container in CONTAINERS.items():
            if container.kind in ("audio", "copy"):
                continue
            if encoder in self.ff.encoders and \
                    self._container_video_ok(container, encoder) and \
                    self.container_available(key):
                result.append(key)
        return result

    def audio_containers_for_video(self, encoder: str) -> list[str]:
        result = []
        for key, container in CONTAINERS.items():
            if container.kind in ("audio", "copy"):
                continue
            if encoder == CODEC_COPY:
                result.append(key)
            elif encoder in self.ff.encoders and \
                    self._container_audio_ok(container, encoder) and \
                    self.container_available(key):
                result.append(key)
        return result

    # -- detectores auxiliares -----------------------------------------
    def supports_cover(self, container_key: str) -> bool:
        container = CONTAINERS.get(container_key)
        if container is None:
            return False
        return container.kind in ("audio", "video", "both") and container.cover

    def video_codec_info(self, codec_id: str) -> VideoCodec | None:
        return VIDEO_CODECS.get(codec_id)

    def audio_codec_info(self, codec_id: str) -> AudioCodec | None:
        return AUDIO_CODECS.get(codec_id)

    def native_aac_available(self) -> bool:
        return "aac" in self.ff.encoders

    def hw_encoder_available(self, codec_id: str) -> bool:
        info = VIDEO_CODECS.get(codec_id)
        if not info or not info.hwaccel:
            return False
        return codec_id in self.ff.encoders and self.ff.has_hwaccel(info.hwaccel)
