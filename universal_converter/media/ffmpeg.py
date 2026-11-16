"""Integração com o FFmpeg/FFprobe instalados na máquina.

Nada é baixado: o programa procura o FFmpeg no caminho configurado, na pasta
``bin/`` ao lado do programa e, por fim, no PATH do sistema. As capacidades
(encoders, muxers, filtros, aceleração) são lidas da própria instalação para
que a interface ofereça apenas combinações que realmente funcionam.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass, field

from ..core.logger import get_logger
from ..core.util import find_tool
from .codecs import VIDEO_CODECS

log = get_logger("ffmpeg")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


class FFmpegNotFound(RuntimeError):
    pass


def _run(args: list[str], timeout: float = 30.0) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            args, capture_output=True, timeout=timeout,
            creationflags=_NO_WINDOW,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise FFmpegNotFound(str(exc)) from exc
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    out = proc.stdout.decode("utf-8", "replace") if proc.stdout else ""
    err = proc.stderr.decode("utf-8", "replace") if proc.stderr else ""
    return proc.returncode, out, err


@dataclass
class FFmpegInfo:
    ffmpeg: str = ""
    ffprobe: str = ""
    version: str = ""
    configuration: str = ""
    encoders: dict[str, str] = field(default_factory=dict)   # nome -> tipo (V/A/S)
    decoders: dict[str, str] = field(default_factory=dict)
    muxers: set[str] = field(default_factory=set)
    demuxers: set[str] = field(default_factory=set)
    filters: set[str] = field(default_factory=set)
    hwaccels: set[str] = field(default_factory=set)
    error: str = ""
    loaded: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # -- carregamento ---------------------------------------------------
    @classmethod
    def locate(cls, custom: str | None = None) -> "FFmpegInfo":
        info = cls()
        info.ffmpeg = find_tool("ffmpeg", custom) or ""
        info.ffprobe = find_tool("ffprobe", custom) or ""
        if not info.ffmpeg and info.ffprobe:
            # procura o ffmpeg ao lado do ffprobe
            candidate = os.path.join(os.path.dirname(info.ffprobe),
                                     "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
            if os.path.isfile(candidate):
                info.ffmpeg = candidate
        return info

    def ensure_loaded(self) -> None:
        with self.lock:
            if self.loaded:
                return
            if not self.ffmpeg or not self.ffprobe:
                self.error = ("FFmpeg/FFprobe não encontrados. Instale o FFmpeg "
                              "(https://ffmpeg.org) ou informe o caminho nas configurações.")
                self.loaded = True
                return
            try:
                self._load()
                self.loaded = True
            except FFmpegNotFound as exc:
                self.error = f"FFmpeg não pôde ser executado: {exc}"
                self.loaded = True
            except Exception as exc:  # pragma: no cover - defensivo
                self.error = f"Falha ao consultar o FFmpeg: {exc}"
                self.loaded = True

    def _load(self) -> None:
        rc, out, err = _run([self.ffmpeg, "-hide_banner", "-version"])
        text = out or err
        first = text.splitlines()[0] if text else ""
        match = re.search(r"ffmpeg version\s+(\S+)", first)
        self.version = match.group(1) if match else first.strip()
        cfg = re.search(r"configuration:\s*(.*)", text)
        self.configuration = cfg.group(1) if cfg else ""

        par = threading.Thread(target=self._load_parallel, daemon=True)
        par.start()
        par.join(timeout=40)

    def _load_parallel(self) -> None:
        rc, out, _ = _run([self.ffmpeg, "-hide_banner", "-encoders"])
        for line in out.splitlines():
            m = re.match(r"^\s([VAS])([.A-Z]{5})\s+(\S+)\s+(.*)$", line)
            if m:
                self.encoders[m.group(3)] = m.group(1)
        rc, out, _ = _run([self.ffmpeg, "-hide_banner", "-decoders"])
        for line in out.splitlines():
            m = re.match(r"^\s([VAS])([.A-Z]{5})\s+(\S+)\s+(.*)$", line)
            if m:
                self.decoders[m.group(3)] = m.group(1)
        rc, out, _ = _run([self.ffmpeg, "-hide_banner", "-filters"])
        for line in out.splitlines():
            m = re.match(r"^\s*[TSC.]{3}\s+(\S+)\s+\S+\s", line)
            if m:
                self.filters.add(m.group(1))
        rc, out, _ = _run([self.ffmpeg, "-hide_banner", "-formats"])
        for line in out.splitlines():
            m = re.match(r"^\s*([DE ])([E ])\s+(\S+)\s+(.*)$", line)
            if not m:
                continue
            names = m.group(3).split(",")
            if m.group(2) == "E":
                self.muxers.update(names)
            if m.group(1) == "D":
                self.demuxers.update(names)
        rc, out, _ = _run([self.ffmpeg, "-hide_banner", "-hwaccels"])
        for line in out.splitlines():
            name = line.strip()
            if name and not name.endswith(":") and "Hardware" not in name:
                self.hwaccels.add(name)

    # -- consultas ------------------------------------------------------
    def has_encoder(self, name: str) -> bool:
        return name in self.encoders

    def has_filter(self, name: str) -> bool:
        return name in self.filters

    def has_muxer(self, name: str) -> bool:
        return name in self.muxers

    def audio_encoders(self) -> set[str]:
        return {n for n, t in self.encoders.items() if t == "A"}

    def video_encoders(self) -> set[str]:
        return {n for n, t in self.encoders.items() if t == "V"}

    def has_hwaccel(self, kind: str) -> bool:
        if kind == "nvenc":
            return "cuda" in self.hwaccels and bool(self.video_encoders() & {"h264_nvenc",
                                                                           "hevc_nvenc",
                                                                           "av1_nvenc"})
        if kind == "qsv":
            return "qsv" in self.hwaccels
        if kind == "amf":
            return "amf" in self.hwaccels
        if kind == "videotoolbox":
            return bool(self.video_encoders() & {"h264_videotoolbox",
                                                 "hevc_videotoolbox"})
        return False

    def summary(self) -> str:
        if self.error:
            return self.error
        hw = ", ".join(sorted(k for k in ("nvenc", "qsv", "amf", "videotoolbox")
                              if self.has_hwaccel(k))) or "nenhuma"
        return (f"FFmpeg {self.version}\n"
                f"ffmpeg: {self.ffmpeg}\nffprobe: {self.ffprobe}\n"
                f"Encoders: {len(self.audio_encoders())} de áudio, "
                f"{len(self.video_encoders())} de vídeo\n"
                f"Aceleração por hardware: {hw}")

    def licensing_note(self) -> str:
        cfg = self.configuration
        gpl = "--enable-gpl" in cfg
        nonfree = "--enable-nonfree" in cfg
        if nonfree:
            return ("Esta compilação do FFmpeg usa --enable-nonfree e NÃO pode ser "
                    "redistribuída. Distribua apenas o programa e indique que o "
                    "FFmpeg é instalado separadamente.")
        if gpl:
            return ("FFmpeg com --enable-gpl (LGPL + componentes GPL, ex.: x264/x265). "
                    "Ao redistribuir um pacote que inclua este binário, respeite a GPL. "
                    "Distribuir o FFmpeg separadamente (instalação pelo usuário) é mais simples.")
        return ("FFmpeg em modo LGPL. Verifique a licença de cada codec que for "
                "habilitado antes de distribuir o programa junto com o FFmpeg.")


# ---------------------------------------------------------------------------
# Análise de mídia
# ---------------------------------------------------------------------------

def probe_file(ffprobe: str, path: str, timeout: float = 60.0) -> dict:
    args = [ffprobe, "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", "-show_chapters", path]
    rc, out, err = _run(args, timeout=timeout)
    if rc != 0 and not out:
        raise RuntimeError((err or "ffprobe falhou").strip().splitlines()[-1])
    try:
        return json.loads(out)
    except ValueError as exc:
        raise RuntimeError(f"Resposta inválida do ffprobe: {exc}") from exc


def measure_loudness(ffmpeg: str, path: str, stream_spec: str = "0:a:0",
                     duration: float | None = None,
                     should_cancel=None) -> dict | None:
    """Mede o loudness integrado (EBU R128) para a normalização em 2 passadas."""
    args = [ffmpeg, "-hide_banner", "-nostdin", "-i", path,
            "-map", stream_spec, "-af",
            "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"]
    try:
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                creationflags=_NO_WINDOW)
    except OSError:
        return None
    chunks: list[bytes] = []
    try:
        while True:
            if should_cancel and should_cancel():
                proc.kill()
                return None
            chunk = proc.stderr.read(4096) if proc.stderr else b""
            if not chunk:
                break
            chunks.append(chunk)
            if sum(len(c) for c in chunks) > 4_000_000:
                chunks = chunks[-200:]
        proc.wait(timeout=10)
    except (OSError, subprocess.SubprocessError):
        try:
            proc.kill()
        except OSError:
            pass
        return None
    text = b"".join(chunks).decode("utf-8", "replace")
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", text, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return {
            "input_i": float(data["input_i"]),
            "input_tp": float(data["input_tp"]),
            "input_lra": float(data["input_lra"]),
            "input_thresh": float(data["input_thresh"]),
            "target_offset": float(data.get("target_offset", 0.0)),
        }
    except (ValueError, KeyError):
        return None


def find_tools(custom: str | None = None) -> tuple[str | None, str | None]:
    return find_tool("ffmpeg", custom), find_tool("ffprobe", custom)


def hw_decoder_args(codec: str, info: FFmpegInfo) -> list[str]:
    """Argumentos de decodificação por hardware, quando disponíveis."""
    mapping = {"h264": ("h264_cuvid", "cuda"), "hevc": ("hevc_cuvid", "cuda"),
               "av1": ("av1_cuvid", "cuda"), "vp9": ("vp9_cuvid", "cuda")}
    entry = mapping.get(codec)
    if not entry:
        return []
    decoder, accel = entry
    if decoder in info.decoders and accel in info.hwaccels:
        return ["-hwaccel", accel, "-hwaccel_output_format", "cuda"]
    return []


def list_video_encoder_ids() -> list[str]:
    return list(VIDEO_CODECS)
