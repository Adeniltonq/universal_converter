"""Execução de um trabalho: abre o FFmpeg, acompanha o progresso e valida a saída.

O arquivo é sempre escrito em um nome temporário na **mesma pasta** do destino
e só é renomeado para o nome final se o FFmpeg terminar com sucesso e o
resultado for válido — evitando arquivos quebrados no destino.
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable

from ..core.logger import get_logger
from ..core.util import sanitize_filename

log = get_logger("media.runner")

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


@dataclass
class RunOutcome:
    success: bool
    cancelled: bool = False
    message: str = ""
    output_path: str = ""
    duration: float = 0.0
    speed: float = 0.0
    stderr_tail: str = ""


class Cancelled(RuntimeError):
    pass


def temporary_path(final_path: str) -> str:
    folder = os.path.dirname(final_path) or "."
    base = os.path.basename(final_path)
    root, dot, ext = base.rpartition(".")
    if not dot:
        root, ext = base, ""
    stem = sanitize_filename(root, max_len=120)
    token = f"{os.getpid()}_{int(time.time() * 1000) % 10_000_000}"
    name = f".{stem}.umc-{token}" + (f".{ext}" if ext else "")
    return os.path.join(folder, name)


class JobRunner:
    """Executa um único comando do FFmpeg de forma cancelável."""

    def __init__(self, ffmpeg: str, threads_cap: int | None = None):
        self.ffmpeg = ffmpeg
        self.threads_cap = threads_cap

    def run(self, args: list[str], final_path: str, duration: float | None,
            on_progress: Callable[[float, float], None] | None = None,
            cancel_event: threading.Event | None = None,
            overwrite: bool = True) -> RunOutcome:
        temp_path = temporary_path(final_path)
        folder = os.path.dirname(final_path)
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as exc:
            return RunOutcome(False, message=f"Não foi possível criar a pasta de saída: {exc}")
        # troca o caminho final pelo temporário (compara caminhos normalizados)
        final_key = os.path.normcase(os.path.abspath(final_path))
        args = [temp_path if os.path.normcase(os.path.abspath(a)) == final_key else a
                for a in args]
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

        creationflags = _NO_WINDOW
        popen_kwargs: dict = {}
        if os.name == "nt":
            popen_kwargs["creationflags"] = creationflags
        else:
            # grupo próprio para encerrar o FFmpeg e filhos (se houver) de uma vez
            popen_kwargs["start_new_session"] = True

        try:
            proc = subprocess.Popen(
                args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, **popen_kwargs)
        except FileNotFoundError:
            return RunOutcome(False, message="FFmpeg não encontrado.")
        except OSError as exc:
            return RunOutcome(False, message=f"Falha ao iniciar o FFmpeg: {exc}")

        stderr_lines: list[str] = []

        def read_stderr() -> None:
            assert proc.stderr is not None
            for raw in proc.stderr:
                line = raw.decode("utf-8", "replace").rstrip()
                if not line:
                    continue
                if line.startswith(("[out#", "[in#", "[aost#", "[vost#")):
                    continue
                stderr_lines.append(line[1:] if line.startswith("[") else line)
                if len(stderr_lines) > 60:
                    del stderr_lines[:20]

        stderr_thread = threading.Thread(target=read_stderr, daemon=True,
                                         name="ffmpeg-stderr")
        stderr_thread.start()

        progress = 0.0
        speed = 0.0
        last_emit = 0.0
        cancelled = False
        out_time = 0.0

        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                if cancel_event is not None and cancel_event.is_set():
                    cancelled = True
                    break
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                    self._update_time(line, duration, stderr_lines)
                    value = line.split("=", 1)[1]
                    try:
                        micro = int(value)
                    except ValueError:
                        continue
                    if micro > 0:
                        out_time = micro / 1_000_000
                        if duration and duration > 0:
                            progress = min(1.0, out_time / duration)
                elif line.startswith("speed="):
                    speed = _parse_speed(line.split("=", 1)[1])
                elif line.startswith("progress="):
                    now = time.monotonic()
                    if on_progress and (now - last_emit >= 0.15 or line.endswith("end")):
                        on_progress(progress, speed)
                        last_emit = now
            if cancelled:
                self._terminate(proc)
        except Exception as exc:  # noqa: BLE001 - leitura da saída do processo
            log.exception("Erro ao ler progresso: %s", exc)
            self._terminate(proc)
        finally:
            try:
                returncode = proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                self._terminate(proc)
                returncode = proc.returncode
            stderr_thread.join(timeout=3)

        if cancelled:
            _remove(temp_path)
            return RunOutcome(False, cancelled=True, message="Cancelado",
                              stderr_tail="\n".join(stderr_lines))
        if cancel_event is not None and cancel_event.is_set():
            _remove(temp_path)
            return RunOutcome(False, cancelled=True, message="Cancelado",
                              stderr_tail="\n".join(stderr_lines))

        if returncode != 0:
            _remove(temp_path)
            message = _friendly_error(stderr_lines)
            return RunOutcome(False, message=message, stderr_tail="\n".join(stderr_lines))

        if not os.path.isfile(temp_path) or os.path.getsize(temp_path) == 0:
            _remove(temp_path)
            return RunOutcome(False, message="O FFmpeg não gerou nenhum dado "
                                              "(seleção de streams vazia?).",
                              stderr_tail="\n".join(stderr_lines))

        final_path = _resolve_collision(final_path, overwrite=overwrite)
        try:
            os.replace(temp_path, final_path)
        except OSError as exc:
            _remove(temp_path)
            return RunOutcome(False, message=f"Não foi possível finalizar o arquivo: {exc}")

        if on_progress:
            on_progress(1.0, speed)
        return RunOutcome(True, message="Concluído", output_path=final_path,
                          duration=out_time, speed=speed,
                          stderr_tail="\n".join(stderr_lines))

    @staticmethod
    def _update_time(line: str, duration: float | None, _buffer: list[str]) -> None:
        return

    @staticmethod
    def _terminate(proc: subprocess.Popen) -> None:
        if proc.poll() is not None:
            return
        try:
            if os.name == "nt":
                proc.kill()
            else:
                import signal
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            try:
                proc.kill()
            except OSError:
                pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except OSError:
                pass


def _remove(path: str) -> None:
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def _resolve_collision(path: str, overwrite: bool) -> str:
    if overwrite or not os.path.exists(path):
        return path
    root, dot, ext = path.rpartition(".")
    if not dot:
        root, ext = path, ""
    counter = 1
    while True:
        if ext:
            candidate = f"{root} ({counter}).{ext}"
        else:
            candidate = f"{root} ({counter})"
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def _parse_speed(text: str) -> float:
    match = re.match(r"\s*([0-9.]+)x", text)
    if not match:
        return 0.0
    try:
        return float(match.group(1))
    except ValueError:
        return 0.0


def _friendly_error(lines: list[str]) -> str:
    """Transforma o stderr do FFmpeg em uma mensagem curta e útil."""
    if not lines:
        return "FFmpeg terminou com erro (sem mensagem)."
    joined = "\n".join(lines)
    checks = [
        (r"Invalid data found when processing input", "Arquivo de entrada inválido ou corrompido."),
        (r"No such file or directory", "Arquivo não encontrado."),
        (r"Permission denied", "Sem permissão para ler/escrever o arquivo."),
        (r"No space left on device", "Disco cheio."),
        (r"Unknown encoder '(.+?)'", "Encoder indisponível nesta instalação do FFmpeg: {}."),
        (r"Encoder '(.+?)' not found", "Encoder indisponível nesta instalação do FFmpeg: {}."),
        (r"Error initializing (?:output stream|decoder|encoder)", "Falha ao inicializar o "
                                                                    "encoder/decoder."),
        (r"Could not open (?:codec|file)", "Não foi possível abrir os dados de entrada."),
        (r"Too many packets buffered", "Dados malformados; tente outro codec de decodificação."),
        (r"Conversion failed", "A conversão falhou."),
    ]
    for pattern, message in checks:
        match = re.search(pattern, joined, re.I)
        if match:
            groups = match.groups()
            return message.format(*groups) if "{}" in message else message
    tail = [ln for ln in lines if ln.strip()][-2:]
    return " · ".join(tail)[:400] or "FFmpeg terminou com erro."
