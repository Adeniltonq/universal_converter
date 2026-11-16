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


class MediaAnalyzer:
    """Encapsula o FFprobe e mantém um cache limitado de análises."""

    def __init__(self, ff: FFmpegInfo, cache_size: int = 4000):
        self.ff = ff
        self.cache_size = cache_size
        self._cache: dict[str, MediaInfo] = {}

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
        return info

    def invalidate(self, path: str | None = None) -> None:
        if path is None:
            self._cache.clear()
            return
        for key in [k for k in self._cache if k.split("|", 1)[0] == path]:
            self._cache.pop(key, None)

    # ------------------------------------------------------------------
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
