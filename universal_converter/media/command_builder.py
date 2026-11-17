"""Construtor de linhas de comando do FFmpeg a partir de um `ConversionJob`.

Camada de abstração própria: a interface nunca conhece argumentos do FFmpeg.
Ela descreve *o que* quer (configuração) e o `CommandBuilder` decide *como*
executar, validando combinações de codec/contêiner contra a instalação real.

Decisões importantes materializadas aqui:

* áudio e vídeo são configurados e validados separadamente;
* a seleção de stream (auto / índice / todas) vira `-map` explícito;
* capa, metadados e capítulos só são repassados quando fazem sentido;
* o destino é sempre um arquivo temporário; quem renomeia é o worker;
* os argumentos de qualidade do encoder nunca se misturam com bitrate.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field

from ..core.util import app_data_dir, sanitize_filename
from .catalog import CodecCatalog
from .codecs import (
    AUDIO_CODECS, CHANNELS, CODEC_COPY, CODEC_NONE, CONTAINERS, CONTAINER_DEFAULT_EXT,
    VIDEO_CODECS, VIDEO_EXTRA_ARGS,
)
from .models import ConversionConfig, ConversionJob, MediaInfo, StreamInfo

# Codec de entrada -> contêineres compatíveis para cópia direta (extração)
COPY_CONTAINERS_BY_CODEC: dict[str, tuple[str, ...]] = {
    "aac": ("adts", "m4a", "mka", "mkv"),
    "mp3": ("mp3", "mka", "mkv"),
    "mp2": ("mpeg", "mka", "mkv", "ts"),
    "ac3": ("ac3", "mka", "mkv", "ts"),
    "eac3": ("eac3", "mka", "mkv", "ts"),
    "dts": ("dts", "mka", "mkv", "ts"),
    "flac": ("flac", "ogg", "mka", "mkv"),
    "alac": ("m4a", "caf", "mka", "mkv"),
    "opus": ("opus", "ogg", "mka", "mkv", "webm"),
    "vorbis": ("ogg", "mka", "mkv", "webm"),
    "wma": ("wma", "mka", "mkv"),
    "wmav1": ("wma", "mka"),
    "wmav2": ("wma", "mka"),
    "amr_nb": ("amr",),
    "amr_wb": ("amr", "mka"),
    "pcm_s16le": ("wav", "mka"),
    "pcm_s24le": ("wav", "mka"),
    "pcm_s32le": ("wav", "mka"),
    "pcm_f32le": ("wav", "mka"),
    "pcm_s16be": ("aiff", "mka"),
    "pcm_s24be": ("aiff", "mka"),
}


@dataclass
class BuildResult:
    args: list[str] = field(default_factory=list)
    error: str = ""
    container: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.error


class PlanningError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Utilidades de conversão de valores
# ---------------------------------------------------------------------------

def to_int(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_resolution(text: str) -> tuple[int | None, int | None] | None:
    """'1920x1080' -> (1920, 1080); '1280xauto' -> (1280, None)."""
    text = (text or "").strip().lower().replace("*", "x")
    if not text or text in ("manter", "keep", "original", "auto"):
        return None
    if "x" not in text:
        return None
    left, _, right = text.partition("x")
    width = to_int(left) if left.strip() not in ("", "auto") else None
    height = to_int(right) if right.strip() not in ("", "auto") else None
    if not width and not height:
        return None
    # codificadores 4:2:0 exigem dimensões pares
    if width is not None:
        width = max(16, width - (width % 2))
    if height is not None:
        height = max(16, height - (height % 2))
    return width, height


def parse_fps(text: str) -> str | None:
    text = (text or "").strip()
    if not text or text.lower() in ("manter", "keep", "original", "auto"):
        return None
    if "/" in text:
        num, _, den = text.partition("/")
        if to_int(num) and to_int(den):
            return f"{to_int(num)}/{to_int(den)}"
        return None
    try:
        value = float(text.replace(",", "."))
    except ValueError:
        return None
    if value <= 0 or value > 1000:
        return None
    known = {23.976: "24000/1001", 23.98: "24000/1001", 29.97: "30000/1001",
             59.94: "60000/1001", 119.88: "120000/1001", 47.95: "48000/1001"}
    for k, frac in known.items():
        if abs(value - k) < 0.01:
            return frac
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return f"{value:.3f}"


def parse_bitrate(value) -> str | None:
    """'192k'/'192'/'1.5M' -> '192k' / '192k' / '1536k'."""
    if value in (None, "", "auto", "Automático"):
        return None
    text = str(value).strip().lower().replace(" ", "")
    multiplier = 1
    if text.endswith("k"):
        multiplier, text = 1000, text[:-1]
    elif text.endswith("m"):
        multiplier, text = 1_000_000, text[:-1]
    try:
        number = float(text.replace(",", "."))
    except ValueError:
        return None
    if number <= 0:
        return None
    return f"{int(round(number * multiplier / 1000))}k"


def number_text(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "23"
    if abs(number - round(number)) < 1e-6:
        return str(int(round(number)))
    return f"{number:g}"


def fmt_num(value: float, digits: int = 2) -> str:
    formatted = f"{value:.{digits}f}"
    return formatted if "." in formatted else formatted + ".0"


# ---------------------------------------------------------------------------
# Construtor
# ---------------------------------------------------------------------------

class CommandBuilder:
    """Monta e valida a linha de comando de um trabalho."""

    def __init__(self, catalog: CodecCatalog, threads_per_job: int = 1):
        self.catalog = catalog
        self.threads_per_job = max(1, int(threads_per_job))

    # -- planejamento ---------------------------------------------------
    def effective_container(self, config: ConversionConfig, info: MediaInfo) -> str:
        if config.container != "copy":
            return config.container
        if config.kind in ("video", "both") and info.is_video:
            return info.container_key() if info.container_key() != "unk" else "mkv"
        audio = self.target_audio_stream(config, info)
        if audio is None:
            return "mka"
        available = self.catalog.audio_encoders()
        for key in COPY_CONTAINERS_BY_CODEC.get(audio.codec, ("mka",)):
            container = CONTAINERS.get(key)
            if container is None or not self.catalog.container_available(key):
                continue
            if container.requires_native_aac and "aac" not in available:
                continue
            return key
        return "mka"

    def output_extension(self, container_key: str, kind: str = "audio") -> str:
        container = CONTAINERS.get(container_key)
        if container is None:
            return "mkv"
        if container.muxer == "ipod":
            return "m4a"
        if kind in ("video", "both") and container.video_exts:
            return container.video_exts[0]
        if container.audio_exts:
            return container.audio_exts[0]
        return CONTAINER_DEFAULT_EXT.get(container_key, "bin")

    @staticmethod
    def target_audio_stream(config: ConversionConfig, info: MediaInfo) -> StreamInfo | None:
        streams = info.audio_streams
        if not streams:
            return None
        selector = config.audio.stream
        if selector in ("", "auto", None):
            return info.main_audio
        if selector == "all":
            return info.main_audio
        index = to_int(selector)
        if index is None:
            return info.main_audio
        for stream in streams:
            if stream.index == index:
                return stream
        return info.main_audio

    # -- montagem -------------------------------------------------------
    def build(self, config: ConversionConfig, info: MediaInfo, job_file: str,
              output_path: str) -> BuildResult:
        result = BuildResult()
        if not info.analyzed:
            result.error = info.error or "Arquivo não analisado."
            return result

        config = ConversionConfig.from_dict(config.to_dict())  # cópia de segurança

        # ----- extração de áudio sem recodificação (contêiner automático)
        auto_extract = config.container == "copy" and config.kind == "audio"
        container_key = self.effective_container(config, info)
        if auto_extract:
            config.audio.codec = CODEC_COPY
            config.video.codec = CODEC_NONE
        container = CONTAINERS.get(container_key)
        if container is None:
            result.error = f"Contêiner desconhecido: {container_key}"
            return result
        result.container = container_key

        ff = self.catalog.ff
        args: list[str] = [ff.ffmpeg, "-hide_banner", "-nostdin", "-y",
                           "-loglevel", "error", "-progress", "pipe:1", "-nostats"]

        has_audio = bool(info.audio_streams)
        has_video = bool(info.video_streams)
        is_av_container = container.kind in ("video", "both", "video_only")
        want_video = (config.kind in ("video", "both")) and has_video and is_av_container
        if config.kind == "audio" and is_av_container and container.kind == "both" and \
                config.video.codec == CODEC_COPY:
            want_video = has_video  # remux de vídeo com áudio copiado
        if config.kind == "audio" and not is_av_container:
            want_video = False
        want_audio = has_audio and config.audio.codec not in (CODEC_NONE, "")

        if not want_audio and not (want_video and config.video.codec != CODEC_NONE):
            result.error = ("Nada a converter: o arquivo não possui streams de áudio "
                            "compatíveis com a operação escolhida."
                            if not has_audio else
                            "Nenhum stream seria produzido — verifique as seleções.")
            return result
        if not want_audio and config.kind == "audio":
            result.warnings.append("O arquivo não tem áudio; só o vídeo será processado.")

        # ---------------- entradas ------------------------------------
        # O muxer ipod exige a entrada principal como entrada 0 (`0:a`).
        # Para ele a capa vem depois do arquivo.
        cover_first = bool(container.muxer != "ipod")
        cover_path = ""
        if want_audio and config.audio.cover_copy and info.cover_streams and \
                self.catalog.supports_cover(container_key) and not want_video:
            cover_path = self._extract_cover(job_file, info)

        hw: list[str] = []
        if want_video and config.video.hw_decode and info.main_video:
            from .ffmpeg import hw_decoder_args
            hw = hw_decoder_args(info.main_video.codec, ff)

        media_pos = 0
        cover_pos = -1
        if cover_path and cover_first:
            args += ["-i", cover_path]
            cover_pos = media_pos
            media_pos += 1
        args += hw
        args += ["-i", job_file]
        if cover_path and not cover_first:
            args += ["-i", cover_path]
            cover_pos = media_pos + 1

        # ---------------- áudio ---------------------------------------
        if want_audio:
            spec = self._audio_map_spec(config, info, media_pos)
            args += ["-map", spec]
            if config.audio.codec == CODEC_COPY:
                args += ["-c:a", "copy"]
            else:
                input_codec = _input_audio_codec(info)
                allowed = {o.id for o in self.catalog.audio_options(container_key,
                                                                    input_codec)}
                if config.audio.codec not in allowed:
                    if config.audio.codec == CODEC_COPY:
                        result.error = (f"O contêiner \"{container.label}\" não aceita "
                                        f"cópia do áudio {input_codec}.")
                        return result
                    replacement = self._compatible_audio(config.audio.codec, container_key,
                                                         input_codec)
                    if replacement is None:
                        result.error = (f"O contêiner \"{container.label}\" não aceita "
                                        f"o codec de áudio {config.audio.codec} nesta "
                                        f"instalação do FFmpeg.")
                        return result
                    result.warnings.append(
                        f"Codec de áudio ajustado para {replacement} "
                        f"(incompatível com {container.label}).")
                    config.audio.codec = replacement
                audio_args, audio_warnings = self._audio_args(config, container_key)
                result.warnings.extend(audio_warnings)
                if audio_args is None:
                    result.error = "Não foi possível configurar o áudio."
                    return result
                args += audio_args

        # ---------------- vídeo ---------------------------------------
        if want_video:
            args += ["-map", f"{media_pos}:v:0"]
            if config.video.codec == CODEC_COPY:
                args += ["-c:v", "copy"]
            elif config.video.codec == CODEC_NONE:
                result.warnings.append("O stream de vídeo será removido.")
            else:
                allowed = {o.id for o in self.catalog.video_options(container_key)}
                if config.video.codec not in allowed:
                    replacement = self._compatible_video(config.video.codec, container_key)
                    if replacement is None:
                        result.error = (f"O contêiner \"{container.label}\" não aceita o "
                                        f"codec de vídeo {config.video.codec} nesta "
                                        f"instalação do FFmpeg.")
                        return result
                    result.warnings.append(
                        f"Codec de vídeo ajustado para {replacement} "
                        f"(incompatível com {container.label}).")
                    config.video.codec = replacement
                if hw:
                    args += ["-noautoscale"]
                video_args, video_warnings, filters = self._video_args(config, info)
                result.warnings.extend(video_warnings)
                if video_args is None:
                    result.error = "Não foi possível configurar o vídeo."
                    return result
                args += video_args
                if filters:
                    args += ["-vf", ",".join(filters)]
            if config.kind in ("video", "both") and config.subtitles == "copy" and \
                    info.subtitle_streams and container_key in ("mkv", "mp4", "mov", "ts"):
                subtitle_codec = "mov_text" if container_key in ("mp4", "mov") else "copy"
                args += ["-map", f"{media_pos}:s?", "-c:s", subtitle_codec]

        # ---------------- capa embutida -------------------------------
        if cover_path:
            args += ["-map", f"{cover_pos}:v", "-c:v", "copy",
                     "-disposition:v", "attached_pic"]
            if container.id3:
                args += ["-metadata:s:v", "title=Album cover",
                         "-metadata:s:v", "comment=Cover (front)"]
            elif container.muxer == "ipod":
                # o muxer ipod gera a capa a partir do stream anexado;
                # não copiar também a capa original evita duplicação
                args += ["-map", f"-{media_pos}:v"]

        # ---------------- metadados e capítulos -----------------------
        if want_audio and config.audio.copy_metadata:
            args += ["-map_metadata", "0"]
            if config.chapters and is_av_container:
                args += ["-map_chapters", "0"]
        else:
            args += ["-map_metadata", "-1", "-map_chapters", "-1"]

        # ---------------- opções finais do contêiner ------------------
        if container_key == "mp3":
            args += ["-id3v2_version", "3"]
        if container_key in ("mp4", "mov") or container.muxer == "ipod":
            if want_video:
                args += ["-movflags", "+faststart"]
        if container.muxer:
            args += ["-f", container.muxer]
        args += ["-threads", str(self.threads_per_job)]
        # `output_path` é o caminho final; o executor troca por um temporário
        # na mesma pasta e só renomeia após sucesso (integridade da saída).
        args += [output_path]

        result.args = args
        return result

    # -- seleção de streams --------------------------------------------
    @staticmethod
    def _audio_map_spec(config: ConversionConfig, info: MediaInfo,
                        input_pos: int = 0) -> str:
        """Especificação `-map` do áudio, relativa ao arquivo de origem."""
        def spec(rest: str) -> str:
            return f"{input_pos}:{rest}" if input_pos is not None else f"0:{rest}"

        target = info.main_audio
        default = spec(f"{target.index}") if target else spec("a:0")
        selector = config.audio.stream
        if selector == "all":
            return spec("a")
        if selector in ("", "auto", None):
            return default
        index = to_int(selector)
        if index is None:
            return default
        return spec(str(index))

    # -- áudio ----------------------------------------------------------
    def _compatible_audio(self, codec_id: str, container_key: str,
                          input_codec: str) -> str | None:
        options = [o.id for o in self.catalog.audio_options(container_key, input_codec)
                   if not o.is_copy]
        if codec_id in options:
            return codec_id
        info = AUDIO_CODECS.get(codec_id)
        if info:
            for candidate in options:
                cinfo = AUDIO_CODECS.get(candidate)
                if cinfo and cinfo.alias == info.alias:
                    return candidate
        for preferred in ("aac", "libmp3lame", "libopus", "libvorbis", "flac",
                          "pcm_s16le"):
            if preferred in options:
                return preferred
        return options[0] if options else None

    def _audio_args(self, config: ConversionConfig,
                    container_key: str) -> tuple[list[str] | None, list[str]]:
        settings = config.audio
        warnings: list[str] = []
        codec = AUDIO_CODECS.get(settings.codec)
        if codec is None:
            return ["-c:a", settings.codec], warnings
        args = ["-c:a", codec.id]

        if not codec.lossless:
            if settings.mode == "vbr" and codec.vbr:
                quality = to_int(settings.quality)
                if quality is None:
                    quality = codec.default_quality
                lo, hi = codec.quality_range or (0, 10)
                quality = max(lo, min(hi, quality))
                args += ["-q:a", str(quality)]
            else:
                bitrate = parse_bitrate(settings.bitrate)
                if bitrate and codec.bitrate:
                    value = int(bitrate[:-1]) * 1000
                    if value > codec.max_bitrate:
                        warnings.append(
                            f"{codec.label} limitado a {codec.max_bitrate // 1000} kbps.")
                        bitrate = f"{codec.max_bitrate // 1000}k"
                    args += ["-b:a", bitrate]
                elif config.audio.stream != "all" and codec.bitrate:
                    # 5.1 não pode ser convertido a 64 kbps sem destruir o som
                    from .codecs import min_bitrate
                    floor = min_bitrate(settings.channels if settings.channels != "keep"
                                        else 6, codec.alias)
                    args += ["-b:a", f"{floor // 1000}k"]
        elif codec.compression and settings.compression_level is not None:
            level = max(0, min(12, to_int(settings.compression_level) or 5))
            args += ["-compression_level", str(level)]

        if settings.sample_rate and settings.sample_rate not in ("keep", "", None):
            rate = to_int(settings.sample_rate)
            if rate:
                if rate > codec.max_sample_rate:
                    rate = codec.max_sample_rate
                    warnings.append(f"{codec.label} limitado a {rate} Hz.")
                args += ["-ar", str(rate)]

        filters: list[str] = []
        layout = ""
        if settings.channels and settings.channels != "keep":
            channel = CHANNELS.get(str(settings.channels))
            if channel and channel.layout:
                count = int(channel.name)
                if count > codec.max_channels:
                    warnings.append(
                        f"{codec.label} limita a {codec.max_channels} canais; "
                        f"ajustado para {codec.max_channels}.")
                    count = codec.max_channels
                args += ["-ac", str(count)]
                layout = "mono" if count == 1 else "stereo" if count == 2 else \
                    channel.layout if count == int(channel.name) else ""
        if settings.gain_db:
            filters.append(f"volume={float(settings.gain_db):+.2f}dB")
        if settings.trim_silence:
            filters.append("silenceremove=start_periods=1:start_threshold=-50dB")
        if settings.normalize == "ebu" and self.catalog.ff.has_filter("loudnorm"):
            filters.append("dynaudnorm=f=150:g=15:p=0.9")
            warnings.append("Normalização EBU solicitada; aplicada normalização dinâmica "
                            "de pico (a medição em 2 passadas não é usada no lote).")
        elif settings.normalize == "peak" and self.catalog.ff.has_filter("dynaudnorm"):
            filters.append("dynaudnorm=f=150:g=15")
        elif settings.normalize == "ebu" and not self.catalog.ff.has_filter("loudnorm"):
            warnings.append("Filtro loudnorm indisponível; normalização ignorada.")
        if layout and not filters:
            filters.append(f"aformat=channel_layouts={layout}")
        if filters:
            args += ["-af", ",".join(filters)]
        return args, warnings

    # -- vídeo ----------------------------------------------------------
    def _compatible_video(self, codec_id: str, container_key: str) -> str | None:
        options = [o.id for o in self.catalog.video_options(container_key)
                   if not o.is_copy and o.id != CODEC_NONE]
        if codec_id in options:
            return codec_id
        info = VIDEO_CODECS.get(codec_id)
        if info:
            for candidate in options:
                cinfo = VIDEO_CODECS.get(candidate)
                if cinfo and cinfo.family == info.family and not cinfo.hwaccel:
                    return candidate
        for preferred in ("libx264", "libx265", "libvpx-vp9", "libsvtav1", "mpeg4"):
            if preferred in options:
                return preferred
        return options[0] if options else None

    def _video_args(self, config: ConversionConfig,
                    info: MediaInfo) -> tuple[list[str] | None, list[str], list[str]]:
        settings = config.video
        warnings: list[str] = []
        codec = VIDEO_CODECS.get(settings.codec)
        if codec is None:
            args = ["-c:v", settings.codec]
            bitrate = parse_bitrate(settings.bitrate)
            if bitrate:
                args += ["-b:v", bitrate]
            return args, warnings, []
        args = ["-c:v", codec.id]

        filters: list[str] = []
        resolution = parse_resolution(settings.resolution)
        if resolution:
            width, height = resolution
            if width and height:
                filters.append(
                    f"scale={width}:{height}:force_original_aspect_ratio=decrease:"
                    f"force_divisible_by=2")
            elif width:
                filters.append(f"scale={width}:-2")
            else:
                filters.append(f"scale=-2:{height}")
        fps = parse_fps(settings.fps)
        if fps:
            filters.append(f"fps={fps}")
        if settings.pix_fmt and settings.pix_fmt not in ("manter", "keep", ""):
            filters.append(f"format={settings.pix_fmt}")
        if codec.hwaccel:
            # pix_fmt não é passado por -vf em encoders de hardware
            filters = [f for f in filters if not f.startswith("format=")]

        if not codec.hwaccel:
            bitrate = parse_bitrate(settings.bitrate) if settings.mode != "crf" else None
        else:
            bitrate = parse_bitrate(settings.bitrate) if settings.mode != "crf" else None

        if settings.mode == "crf" and codec.quality_args:
            quality = settings.quality
            lo, hi = codec.quality_range
            quality = max(lo, min(hi, float(quality)))
            replaced = [str(a).replace("{v}", number_text(quality))
                        for a in codec.quality_args]
            args += replaced
        elif bitrate:
            args += ["-b:v", bitrate]
            if settings.max_rate:
                max_rate = parse_bitrate(settings.max_rate)
                if max_rate:
                    args += ["-maxrate", max_rate, "-bufsize",
                             _double_bitrate(max_rate)]
        else:
            if codec.quality_args and codec.quality_mode == "crf":
                replaced = [str(a).replace("{v}", number_text(codec.quality_default))
                            for a in codec.quality_args]
                args += replaced
            else:
                warnings.append("Bitrate automático não é aplicável a este encoder; "
                                "usando o padrão do FFmpeg.")

        preset = settings.preset or codec.default_preset
        extra = VIDEO_EXTRA_ARGS.get(codec.id)
        if extra:
            if "{preset}" in " ".join(extra) and not preset:
                preset = codec.default_preset
            args += [str(a).replace("{preset}", preset) for a in extra]
        if settings.profile and codec.profile_args and not codec.hwaccel:
            args += ["-profile:v", settings.profile]
        if settings.level and not codec.hwaccel:
            args += ["-level:v", settings.level]
        if codec.hwaccel == "nvenc":
            args += ["-pix_fmt", "yuv420p"] if settings.pix_fmt == "manter" else []
        return args, warnings, filters

    # -- capa ------------------------------------------------------------
    def _extract_cover(self, job_file: str, info: MediaInfo) -> str:
        """Extrai a capa APIC para um arquivo temporário (necessário para remux)."""
        cover = info.cover_streams[0]
        source_codec = ""
        for stream in info.streams:
            if stream.index == cover.index:
                source_codec = stream.codec
                break
        ext = {"mjpeg": "jpg", "png": "png", "bmp": "bmp", "webp": "webp"}.get(
            source_codec, "jpg")
        folder = os.path.join(app_data_dir(), "cache")
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            folder = app_data_dir()
        name = f"cover_{abs(hash(job_file)) & 0xFFFFFFFF}_{cover.index}.{ext}"
        path = os.path.join(folder, sanitize_filename(name))
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            return path
        args = [self.catalog.ff.ffmpeg, "-hide_banner", "-nostdin", "-y",
                "-loglevel", "error", "-i", job_file, "-map", f"0:{cover.index}",
                "-frames:v", "1", path]
        try:
            proc = subprocess.run(
                args, capture_output=True, timeout=120, stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt"
                else 0)
            if proc.returncode == 0 and os.path.isfile(path) and os.path.getsize(path):
                return path
        except (OSError, subprocess.SubprocessError):
            pass
        return ""


def _double_bitrate(rate: str) -> str:
    try:
        return f"{int(rate[:-1]) * 2}k"
    except (ValueError, IndexError):
        return rate


def _input_audio_codec(info: MediaInfo) -> str:
    stream = info.main_audio
    return stream.codec if stream else ""
