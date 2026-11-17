"""Análise de arquivos multimídia (largura de banda de streams e metadados)."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Iterable

from ..core.logger import get_logger
from ..core.util import is_subpath
from .codecs import INPUT_CODEC_LABEL
from .ffmpeg import FFmpegInfo, probe_file
from .models import MediaInfo, StreamInfo, media_info_from_probe

log = get_logger("analyzer")

# Entradas pequenas não precisam do FFprobe para a pré-visualização de nomes:
# as tags são lidas direto do cabeçalho (ID3v2/FLAC/MP4/Matroska/CDDA).
QUICK_ANALYSIS_LIMIT = 24 * 1024 * 1024


class MediaAnalyzer:
    """Encapsula o FFprobe e mantém um cache limitado de análises."""

    def __init__(self, ff: FFmpegInfo, cache_size: int = 4000):
        self.ff = ff
        self.cache_size = cache_size
        self._cache: dict[str, MediaInfo] = {}
        self._skeletons: dict[str, MediaInfo] = {}

    # ------------------------------------------------------------------
    def quick_info(self, path: str) -> MediaInfo:
        """Análise por cabeçalho, sem executar o FFprobe (rápida e barata).

        Usada na pré-visualização de nomes: basta tamanho, contêiner aproximado
        e metadados. A análise completa continua sendo feita pelo FFprobe na
        fila de trabalho (`analyze`).
        """
        key = self._cache_key(path)
        info = self._skeletons.get(key)
        if info is None:
            info = self._build_skeleton(path)
            if len(self._skeletons) > self.cache_size:
                for old in list(self._skeletons)[: self.cache_size // 4]:
                    self._skeletons.pop(old, None)
            self._skeletons[key] = info
        return info

    def _build_skeleton(self, path: str) -> MediaInfo:
        info = MediaInfo(path=path, analyzed=True)
        try:
            info.size = os.path.getsize(path)
        except OSError:
            info.analyzed = False
            info.error = "Arquivo não encontrado."
            return info
        try:
            with open(path, "rb") as fh:
                head = fh.read(64)
        except OSError:
            info.analyzed = False
            return info
        info.format_name = _sniff_format(head)
        ext = os.path.splitext(path)[1].lstrip(".").lower()
        if ext in ("mp3", "flac", "m4a", "m4b", "aac", "ogg", "oga", "opus", "wav",
                   "aiff", "aif", "wma", "mka", "caf", "alac", "amr", "ac3", "eac3",
                   "dts", "ape", "wv", "tta", "au", "snd", "w64"):
            info.streams.append(StreamInfo(index=0, type="audio", codec=_codec_guess(ext)))
        info.tags = self._read_tags(path)
        return info

    # ------------------------------------------------------------------
    def analyze(self, path: str, use_cache: bool = True) -> MediaInfo:
        cache_key = self._cache_key(path)
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]
        info = self._probe(path)
        if len(self._cache) >= self.cache_size:
            for key in list(self._cache)[: self.cache_size // 4]:
                self._cache.pop(key, None)
        self._cache[cache_key] = info
        return info

    def _cache_key(self, path: str) -> str:
        try:
            stat = os.stat(path)
            return f"{path}|{stat.st_size}|{int(stat.st_mtime)}"
        except OSError:
            return path

    def _probe(self, path: str) -> MediaInfo:
        self.ff.ensure_loaded()
        if self.ff.error:
            return MediaInfo(path=path, error=self.ff.error)
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        if not os.path.isfile(path):
            return MediaInfo(path=path, error="Arquivo não encontrado.", size=size)
        try:
            data = probe_file(self.ff.ffprobe, path)
        except Exception as exc:  # noqa: BLE001 - erro do ffprobe é texto livre
            log.warning("Falha ao analisar %s: %s", path, exc)
            return MediaInfo(path=path, error=f"Falha ao analisar: {exc}", size=size)
        info = media_info_from_probe(path, data, size=size)
        if not info.streams:
            info.error = "Nenhum stream reconhecido (arquivo inválido ou não suportado)."
        if not info.tags:
            info.tags = self._read_tags(path)
        return info

    def _read_tags(self, path: str) -> dict[str, str]:
        """Lê apenas a primeira unidade do arquivo (rápido) para achar tags.

        Contêineres que guardam tags no final (ID3v1) ficam sem metadados, mas
        ID3v2, Vorbis comments, MP4 e Matroska são encontrados no início.
        """
        try:
            with open(path, "rb") as fh:
                chunk = fh.read(256 * 1024)
        except OSError:
            return {}
        tags: dict[str, str] = {}
        try:
            if chunk.startswith(b"ID3") and len(chunk) > 10:
                size = ((chunk[6] & 0x7F) << 21 | (chunk[7] & 0x7F) << 14 |
                        (chunk[8] & 0x7F) << 7 | (chunk[9] & 0x7F))
                body = chunk[10:10 + size]
                tags.update(_parse_id3v2(body))
            elif chunk[:4] == b"fLaC":
                pos = 4
                while pos + 4 <= len(chunk):
                    header = chunk[pos]
                    block_type = header & 0x7F
                    length = int.from_bytes(chunk[pos + 1:pos + 4], "big")
                    body = chunk[pos + 4:pos + 4 + length]
                    if block_type == 4:
                        tags.update(_parse_vorbis_comments(body))
                    pos += 4 + length
                    if header & 0x80:
                        break
            elif b"ftyp" in chunk[:32]:
                tags.update(_parse_mp4_tags(chunk))
            elif chunk[:4] == b"\x1a\x45\xdf\xa3":
                tags.update(_parse_matroska_tags(chunk))
        except Exception:  # noqa: BLE001 - metadados nunca devem impedir a análise
            return tags
        return {k: v for k, v in tags.items() if v}

    def invalidate(self, path: str | None = None) -> None:
        if path is None:
            self._cache.clear()
            return
        for key in [k for k in self._cache if k.split("|", 1)[0] == path]:
            self._cache.pop(key, None)

    # ------------------------------------------------------------------
    def analyze_streams(self, paths: Iterable[str], workers: int = 4,
                        progress: Callable[[int, int], None] | None = None) -> None:
        """Executa o FFprobe em vários arquivos sem guardar os resultados.

        Usado para contabilizar tamanho/duração na fila sem inflar a memória.
        """
        paths = list(paths)
        total = len(paths)
        if not total:
            return

        def worker(path: str) -> None:
            self.analyze(path)

        images = min(max(1, workers), self.ff_workers(total))
        with ThreadPoolExecutor(max_workers=images, thread_name_prefix="probe") as pool:
            futures = [pool.submit(worker, path) for path in paths]
            done = 0
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:  # noqa: BLE001
                    pass
                done += 1
                if progress:
                    progress(done, total)

    def ff_workers(self, total: int) -> int:
        cpus = os.cpu_count() or 1
        return max(1, min(8, total, cpus))

    def merge_skeletons(self) -> None:
        """Copia tags dos esqueletos para o cache de análise completo."""
        for key, skeleton in list(self._skeletons.items()):
            info = self._cache.get(key)
            if info is not None and not info.tags and skeleton.tags:
                info.tags = skeleton.tags

    def analyze_many(self, paths: Iterable[str], workers: int = 4,
                     progress: Callable[[int, int], None] | None = None,
                     should_stop: Callable[[], bool] | None = None) -> list[MediaInfo]:
        paths = list(paths)
        results: list[MediaInfo] = []
        total = len(paths)
        if total == 0:
            return results
        images = min(max(1, workers), 8, total)
        with ThreadPoolExecutor(max_workers=images, thread_name_prefix="analyze") as pool:
            futures = {pool.submit(self.analyze, path): path for path in paths}
            done = 0
            for future in as_completed(futures):
                if should_stop and should_stop():
                    break
                try:
                    results.append(future.result())
                except Exception as exc:  # noqa: BLE001
                    results.append(MediaInfo(path=futures[future], error=str(exc)))
                done += 1
                if progress:
                    progress(done, total)
        return results


def _sniff_format(head: bytes) -> str:
    if head.startswith(b"ID3"):
        return "mp3"
    if head[:4] == b"fLaC":
        return "flac"
    if head[:4] == b"OggS":
        return "ogg"
    if head[:4] == b"RIFF":
        return "wav"
    if head[:4] == b"FORM":
        return "aiff"
    if head[:4] == b"caff":
        return "caf"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "matroska,webm"
    if head[:3] == b"ID3" or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "mp3"
    if b"ftyp" in head[:32]:
        return "mov,mp4,m4a,3gp,3g2,mj2"
    if head[:4] in (b"\x30\x26\xb2\x75", b"\x30\x26\xb2\x75"):
        return "asf"
    return ""


def _codec_guess(ext: str) -> str:
    return {
        "mp3": "mp3", "flac": "flac", "m4a": "aac", "alac": "alac", "aac": "aac",
        "ogg": "vorbis", "oga": "vorbis", "opus": "opus", "wav": "pcm_s16le",
        "aiff": "pcm_s16be", "aif": "pcm_s16be", "wma": "wmav2", "mka": "flac",
        "caf": "pcm_s16le", "amr": "amr_nb", "ac3": "ac3", "eac3": "eac3",
        "dts": "dts", "au": "pcm_s16be", "snd": "pcm_s16be", "w64": "pcm_s16le",
        "ape": "ape", "wv": "wavpack", "tta": "tta", "mp4": "aac",
    }.get(ext, "")


# ---------------------------------------------------------------------------
# Leitura rápida de tags
# ---------------------------------------------------------------------------

_ID3_FRAMES = {"TIT2": "title", "TPE1": "artist", "TPE2": "albumartist",
               "TALB": "album", "TDRC": "date", "TYER": "year", "TCON": "genre",
               "TRCK": "track", "TPOS": "disc", "TCOM": "composer"}


def _decode_id3_text(data: bytes) -> str:
    if not data:
        return ""
    encoding = data[0]
    payload = data[1:]
    try:
        if encoding == 0:
            text = payload.decode("latin-1", "replace")
        elif encoding == 1:
            text = payload.decode("utf-16", "replace")
        elif encoding == 2:
            text = payload.decode("utf-16-be", "replace")
        else:
            text = payload.decode("utf-8", "replace")
    except (UnicodeDecodeError, LookupError):
        return ""
    return text.split("\x00")[0].strip()


def _parse_id3v2(body: bytes) -> dict[str, str]:
    tags: dict[str, str] = {}
    pos = 0
    while pos + 10 <= len(body):
        frame_id = body[pos:pos + 4]
        if not frame_id.strip(b"\x00") or not frame_id.isalnum():
            break
        size = int.from_bytes(body[pos + 4:pos + 8], "big")
        payload = body[pos + 10:pos + 10 + size]
        name = _ID3_FRAMES.get(frame_id.decode("latin-1", "replace"))
        if name and payload:
            value = _decode_id3_text(payload)
            if value and name not in tags:
                tags[name] = value
        pos += 10 + size
    return tags


def _parse_vorbis_comments(body: bytes) -> dict[str, str]:
    tags: dict[str, str] = {}
    try:
        pos = 0
        length = int.from_bytes(body[pos:pos + 4], "little")
        pos += 4 + length            # nome do vendor
        count = int.from_bytes(body[pos:pos + 4], "little")
        pos += 4
        for _ in range(min(count, 200)):
            length = int.from_bytes(body[pos:pos + 4], "little")
            pos += 4
            entry = body[pos:pos + length].decode("utf-8", "replace")
            pos += length
            key, _, value = entry.partition("=")
            tags.setdefault(key.strip().lower(), value.strip())
    except (IndexError, ValueError):
        pass
    return tags


_MP4_KEYS = {b"\xa9nam": "title", b"\xa9ART": "artist", b"aART": "albumartist",
             b"\xa9alb": "album", b"\xa9day": "date", b"\xa9gen": "genre",
             b"trkn": "track", b"\xa9wrt": "composer", b"\xa9cmt": "comment",
             b"\xa9too": "encoder"}


def _parse_mp4_tags(chunk: bytes) -> dict[str, str]:
    tags: dict[str, str] = {}
    for key, name in _MP4_KEYS.items():
        index = chunk.find(key)
        if index < 0:
            continue
        data_marker = chunk.find(b"data", index, index + 64)
        if data_marker < 0:
            continue
        start = data_marker + 12
        end = chunk.find(b"\x00\x00\x00", start)
        value = chunk[start:end if end > start else start + 128]
        text = value.lstrip(b"\x00\x01").decode("utf-8", "replace").strip()
        if text and text.isprintable():
            tags.setdefault(name, text.split("\x00")[0])
    return tags


def _parse_matroska_tags(chunk: bytes) -> dict[str, str]:
    """Lê os SimpleTag do Matroska (TagName + TagString, IDs 0x45A3/0x4487)."""
    tags: dict[str, str] = {}
    pos = 0
    while True:
        index = chunk.find(b"\x45\xa3", pos)
        if index < 0:
            break
        try:
            name, pos = _ebml_value(chunk, index + 2)
            if not name:
                break
            name_text = name.decode("utf-8", "replace").strip().lower()
            value_index = chunk.find(b"\x44\x87", pos)
            if value_index < 0:
                break
            value, pos = _ebml_value(chunk, value_index + 2)
            text = value.decode("utf-8", "replace").strip()
            if name_text and text and name_text.isprintable():
                tags.setdefault(name_text, text)
        except (IndexError, UnicodeDecodeError):
            break
    return tags


def _ebml_value(data: bytes, pos: int) -> tuple[bytes, int]:
    """Decodifica o tamanho (VINT) e devolve (conteúdo, próxima posição)."""
    if pos >= len(data):
        return b"", pos
    first = data[pos]
    mask = 0x80
    length = 1
    while not (first & mask):
        mask >>= 1
        length += 1
        if length > 8:
            return b"", pos
    raw = int.from_bytes(data[pos:pos + length], "big")
    size = raw & ((1 << (7 * length)) - 1)
    start = pos + length
    return data[start:start + size], start + size


def quick_summary(info: MediaInfo) -> dict[str, str]:
    """Linhas de resumo para exibição na fila."""
    audio = info.main_audio
    video = info.main_video
    return {
        "format": info.format_label(),
        "audio_codec": INPUT_CODEC_LABEL.get(audio.codec, audio.codec) if audio else "",
        "video_codec": INPUT_CODEC_LABEL.get(video.codec, video.codec) if video else "",
        "resolution": f"{video.width}×{video.height}" if video else "",
        "audio_bitrate": audio.bitrate if audio else 0,
        "video_bitrate": video.bitrate if video else 0,
        "channels": audio.channels if audio else 0,
        "sample_rate": audio.sample_rate if audio else 0,
        "error": info.error,
    }


def ensure_output_outside(source_root: str, output_dir: str) -> str | None:
    """Impede que a saída fique dentro de uma pasta de origem sendo varrida."""
    if is_subpath(output_dir, source_root):
        return ("A pasta de destino está dentro da pasta de origem. Os arquivos gerados "
                "podem ser varridos novamente numa próxima varredura.")
    return None


def stream_choices(info: MediaInfo) -> list[tuple[str, str]]:
    """Opções (valor, rótulo) para o seletor de faixa de áudio."""
    choices: list[tuple[str, str]] = [("auto", "Automática (faixa padrão)")]
    for position, stream in enumerate(info.audio_streams):
        label = stream.display_label()
        if len(info.audio_streams) > 1:
            label = f"Faixa {position + 1}: {label}"
        choices.append((str(stream.index), label))
    if len(info.audio_streams) > 1:
        choices.append(("all", "Todas as faixas de áudio"))
    return choices


def describe_stream(stream: StreamInfo) -> str:
    return stream.display_label()
