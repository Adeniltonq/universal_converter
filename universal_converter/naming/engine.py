"""Sistema de nomenclatura inteligente dos arquivos de saída.

O nome final é descrito por um modelo (template) com variáveis:

    {name} {artist} {album} {title} {date} {year} {codec} {format}
    {resolution} {bitrate} {index} {parent} {tag} {ext}

O nome original é sempre preservado internamente (``source_stem``), de modo
que qualquer mudança no modelo pode ser recalculada sem perda de informação.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from ..core.util import sanitize_dir_name, sanitize_filename
from ..media.codecs import CONTAINERS, ENCODER_TO_CODEC, INPUT_CODEC_LABEL
from ..media.models import ConversionConfig, MediaInfo, NamingTemplate

VARIABLES: list[tuple[str, str]] = [
    ("name", "Nome original do arquivo (sem extensão)"),
    ("artist", "Artista (tag ID3/Vorbis/MP4)"),
    ("album", "Álbum"),
    ("title", "Título da faixa"),
    ("date", "Data completa (AAAA-MM-DD)"),
    ("year", "Ano (4 dígitos)"),
    ("codec", "Codec de saída"),
    ("format", "Formato/contêiner de saída"),
    ("resolution", "Resolução do vídeo (1920x1080)"),
    ("bitrate", "Bitrate do áudio de saída (192 kbps)"),
    ("index", "Número sequencial na fila"),
    ("parent", "Nome da pasta de origem"),
    ("tag", "Palavra/tag adicional definida pelo usuário"),
    ("ext", "Extensão de saída (sem ponto)"),
]

_SAFE_VARIABLE = re.compile(r"\{([a-zA-Z_]+)(?::([^{}]*))?\}")

DEFAULT_PRESET_TEMPLATES = [
    "{name}",
    "{name}{separator}{tag}",
    "{artist} - {title}",
    "{album}/{index} - {title}",
    "{name}_{codec}",
    "{name} ({resolution})",
]


@dataclass
class NamingContext:
    """Dados de um arquivo disponíveis para o modelo."""
    path: str = ""
    info: MediaInfo | None = None
    config: ConversionConfig | None = None
    index: int = 0
    tag: str = ""
    extension: str = ""
    bitrate: str = ""
    codec_label: str = ""
    format_label: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def source_stem(self) -> str:
        return os.path.splitext(os.path.basename(self.path))[0]

    @property
    def parent(self) -> str:
        return os.path.basename(os.path.dirname(os.path.abspath(self.path))) or "raiz"

    def values(self, separator: str) -> dict[str, str]:
        info = self.info
        config = self.config
        resolution = ""
        if info and info.main_video:
            video = info.main_video
            resolution = f"{video.width}x{video.height}"
        date = info.tag("date", "year") if info else ""
        year = ""
        if date:
            match = re.search(r"(\d{4})", date)
            year = match.group(1) if match else date[:4]
        codec_label = _output_codec_label(config, info)
        format_label = _output_format_label(config)
        bitrate = self.bitrate or _output_bitrate(config)
        ext = self.extension or _output_extension(config)
        name = self.source_stem
        tag_value = self.tag
        values = {
            "name": name,
            "artist": info.tag("artist", "album_artist", "albumartist") if info else "",
            "album": info.tag("album") if info else "",
            "title": (info.tag("title") if info else "") or name,
            "date": date,
            "year": year,
            "codec": codec_label,
            "format": format_label,
            "resolution": resolution,
            "bitrate": bitrate,
            "index": str(self.index),
            "parent": self.parent,
            "tag": tag_value,
            "ext": ext,
            "separator": separator,
        }
        values.update(self.extra)
        return values


def _output_codec_label(config: ConversionConfig | None,
                        info: MediaInfo | None) -> str:
    if config is None:
        return ""
    if config.kind == "audio":
        codec = config.audio.codec
        if codec == "copy" and info and info.main_audio:
            return INPUT_CODEC_LABEL.get(info.main_audio.codec, info.main_audio.codec)
        return {"libmp3lame": "mp3", "aac": "aac", "libfdk_aac": "aac",
                "libopus": "opus", "libvorbis": "vorbis", "pcm_s16le": "pcm16",
                "pcm_s24le": "pcm24", "pcm_s32le": "pcm32", "pcm_f32le": "pcmf32",
                }.get(codec, codec)
    codec = config.video.codec
    if codec == "copy" and info and info.main_video:
        return INPUT_CODEC_LABEL.get(info.main_video.codec, info.main_video.codec)
    return {"libx264": "h264", "libx265": "hevc", "libsvtav1": "av1",
            "libaom-av1": "av1", "libvpx-vp9": "vp9", "libvpx": "vp8",
            "mpeg4": "mpeg4", "mpeg2video": "mpeg2"}.get(codec, codec)


def _output_format_label(config: ConversionConfig | None) -> str:
    if config is None:
        return ""
    container = CONTAINERS.get(config.container)
    if container is None or container.kind == "copy":
        return ""
    return container.label.split(" (")[0]


def _output_extension(config: ConversionConfig | None) -> str:
    if config is None:
        return ""
    container = CONTAINERS.get(config.container)
    if container is None or container.kind == "copy":
        return ""
    if container.muxer == "ipod":
        return "m4a"
    if config.kind == "video" and container.video_exts:
        return container.video_exts[0]
    exts = container.audio_exts or container.video_exts
    return exts[0] if exts else ""


def _output_bitrate(config: ConversionConfig | None) -> str:
    if config is None:
        return ""
    value = str(config.audio.bitrate or "").strip()
    if not value:
        return ""
    if value.endswith("k"):
        return value
    return f"{value}k"


class NamingEngine:
    """Aplica o modelo de nomes e resolve colisões."""

    def __init__(self, template: NamingTemplate | None = None):
        self.template = template or NamingTemplate()

    # ------------------------------------------------------------------
    def render(self, context: NamingContext, template: NamingTemplate | None = None,
               ensure_extension: bool = True) -> str:
        """Gera o caminho relativo (pode conter subpastas) do arquivo de saída."""
        model = template or self.template
        separator = model.separator or "_"
        values = context.values(separator)
        base_template = model.template or "{name}"
        if not values.get("tag"):
            # "{name}_{tag}" sem palavra adicional não deve gerar "Isolation_"
            tag_separator = re.escape(separator)
            base_template = re.sub(rf"{tag_separator}\s*\{{tag\}}", "", base_template)
            base_template = re.sub(rf"\{{tag\}}\s*{tag_separator}", "", base_template)
        raw = base_template or "{name}"
        rendered = _SAFE_VARIABLE.sub(
            lambda m: values.get(m.group(1).lower(), ""), raw)

        if model.replacement_from:
            try:
                rendered = re.sub(re.escape(model.replacement_from),
                                  model.replacement_to, rendered)
            except re.error:
                rendered = rendered.replace(model.replacement_from, model.replacement_to)

        rendered = _clean_spaces(rendered)

        if model.prefix:
            rendered = f"{_clean_spaces(model.prefix)} {rendered}"
        if model.suffix:
            rendered = f"{rendered} {_clean_spaces(model.suffix)}"

        rendered = _apply_case(rendered, model.case)

        # separa diretórios (hierarquia relativa) do nome do arquivo
        parts = [p for p in re.split(r"[\\/]+", rendered)]
        directories = parts[:-1]
        filename = parts[-1] if parts else ""

        if model.numbering:
            number = str(model.number_start + max(0, context.index))
            padding = max(1, min(10, int(model.number_padding or 1)))
            number = number.rjust(padding, "0")
            if model.number_position == "suffix":
                filename = f"{filename} {number}"
            else:
                filename = f"{number} - {filename}"

        extension = context.extension or values.get("ext", "")
        if ensure_extension and extension and not filename.lower().endswith(
                "." + extension.lower()):
            filename = f"{filename}.{extension}"

        filename = _clean_spaces(filename)
        if model.sanitize:
            filename = sanitize_filename(filename)
            directories = [sanitize_dir_name(_clean_spaces(d)) for d in directories]
        else:
            directories = [_clean_spaces(d) for d in directories if d]

        if not filename:
            filename = sanitize_filename(context.source_stem or "arquivo")
            if ensure_extension and extension:
                filename += f".{extension}"
        return os.path.join(*directories, filename) if directories else filename

    # ------------------------------------------------------------------
    def preview(self, context: NamingContext, template: NamingTemplate | None = None) -> str:
        try:
            return self.render(context, template)
        except Exception as exc:  # noqa: BLE001 - pré-visualização nunca quebra a UI
            return f"<erro ao gerar nome: {exc}>"

    @staticmethod
    def deduplicate(relative_path: str, taken: set[str],
                    exists_on_disk) -> tuple[str, bool]:
        """Garante nome único entre a fila e o disco.

        Retorna (caminho ajustado, houve_colisao).
        """
        key = os.path.normcase(os.path.normpath(relative_path))
        if key not in taken and not exists_on_disk(relative_path):
            taken.add(key)
            return relative_path, False
        folder = os.path.dirname(relative_path)
        base = os.path.basename(relative_path)
        root, dot, ext = base.rpartition(".")
        if not dot:
            root, ext = base, ""
        counter = 1
        while True:
            candidate_name = (f"{root} ({counter}).{ext}" if ext
                              else f"{root} ({counter})")
            candidate = os.path.join(folder, candidate_name) if folder else candidate_name
            ckey = os.path.normcase(os.path.normpath(candidate))
            if ckey not in taken and not exists_on_disk(candidate):
                taken.add(ckey)
                return candidate, True
            counter += 1


def _clean_spaces(text: str) -> str:
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+/\s+", "/", text)
    text = re.sub(r"/\s+", "/", text)
    text = re.sub(r"\s+/", "/", text)
    return text.strip().strip("/")


def _apply_case(text: str, case: str) -> str:
    if case == "lower":
        return text.lower()
    if case == "upper":
        return text.upper()
    if case == "title":
        return " ".join(word[:1].upper() + word[1:] for word in text.split(" "))
    return text


def validate_template(template: str) -> tuple[list[str], list[str]]:
    """Retorna (variáveis usadas, variáveis desconhecidas)."""
    known = {name for name, _ in VARIABLES}
    used, unknown = [], []
    for match in _SAFE_VARIABLE.finditer(template or ""):
        name = match.group(1).lower()
        if name in known:
            used.append(name)
        else:
            unknown.append(match.group(0))
    return used, unknown
