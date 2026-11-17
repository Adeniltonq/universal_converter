"""Barra de monitoramento persistente (fila, progresso, velocidade, CPU/RAM)."""

from __future__ import annotations

import os
import sys
import time
import tkinter as tk
from tkinter import ttk

from ..core.util import fmt_duration, fmt_size, fmt_speed
from . import theme
from .theme import tooltip


# ---------------------------------------------------------------------------
# Monitor do sistema (sem dependências externas)
# ---------------------------------------------------------------------------

class SystemMonitor:
    """Uso de CPU e memória do processo/máquina usando só a biblioteca padrão."""

    def __init__(self):
        self.cpus = os.cpu_count() or 1
        self._last_cpu: tuple[float, float] | None = None
        self._last_time = 0.0
        self._psutil = None
        try:  # opcional: se o usuário tiver psutil, os números ficam melhores
            import psutil  # type: ignore
            self._psutil = psutil
        except Exception:  # noqa: BLE001
            self._psutil = None
        if self._psutil is not None:
            try:
                self._psutil.cpu_percent(interval=None)
            except Exception:  # noqa: BLE001
                self._psutil = None

    def read(self) -> tuple[float | None, float | None]:
        """Retorna (uso de CPU 0-1, uso de RAM do programa em bytes)."""
        if self._psutil is not None:
            try:
                cpu = self._psutil.cpu_percent(interval=None) / 100.0
                mem = self._psutil.Process().memory_info().rss
                return cpu, float(mem)
            except Exception:  # noqa: BLE001
                self._psutil = None
        if sys.platform.startswith("linux"):
            return self._linux()
        if sys.platform == "darwin":
            return self._darwin()
        if os.name == "nt":
            return self._windows()
        return None, None

    def _linux(self) -> tuple[float | None, float | None]:
        try:
            with open("/proc/stat", encoding="ascii") as fh:
                parts = fh.readline().split()[1:]
            values = [float(p) for p in parts]
            idle = values[3] + (values[4] if len(values) > 4 else 0.0)
            total = sum(values)
            cpu = None
            if self._last_cpu:
                last_idle, last_total = self._last_cpu
                delta_total = total - last_total
                if delta_total > 0:
                    cpu = 1.0 - (idle - last_idle) / delta_total
            self._last_cpu = (idle, total)
        except (OSError, ValueError, IndexError):
            cpu = None
        mem = None
        try:
            with open("/proc/self/statm", encoding="ascii") as fh:
                rss_pages = int(fh.read().split()[1])
            mem = float(rss_pages * os.sysconf("SC_PAGE_SIZE"))
        except (OSError, ValueError, IndexError, AttributeError):
            pass
        return cpu, mem

    def _darwin(self) -> tuple[float | None, float | None]:
        cpu = None
        try:
            import subprocess
            out = subprocess.run(["ps", "-A", "-o", "%cpu"], capture_output=True,
                                 text=True, timeout=2).stdout.split("\n")[1:]
            usage = sum(float(line.strip() or 0) for line in out if line.strip()) / 100.0
            cpu = min(1.0, usage / self.cpus)
        except Exception:  # noqa: BLE001
            cpu = None
        return cpu, None

    def _windows(self) -> tuple[float | None, float | None]:
        try:
            import ctypes
            from ctypes import wintypes

            class FILETIME(ctypes.Structure):
                _fields_ = [("dwLowDateTime", wintypes.DWORD),
                            ("dwHighDateTime", wintypes.DWORD)]

            idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
            if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle),
                                                         ctypes.byref(kernel),
                                                         ctypes.byref(user)):
                return None, None
            to_int = lambda ft: (ft.dwHighDateTime << 32) + ft.dwLowDateTime  # noqa: E731
            current = (to_int(idle), to_int(kernel), to_int(user))
            cpu = None
            if self._last_cpu and len(self._last_cpu) == 3:
                idle_d = current[0] - self._last_cpu[0]
                total_d = (current[1] - self._last_cpu[1]) + (current[2] - self._last_cpu[2])
                if total_d > 0:
                    cpu = 1.0 - idle_d / total_d
            self._last_cpu = current
            return cpu, None
        except Exception:  # noqa: BLE001
            return None, None


# ---------------------------------------------------------------------------
# Barra
# ---------------------------------------------------------------------------

class MonitorBar(ttk.Frame):
    def __init__(self, parent: tk.Misc, controller, actions: dict):
        super().__init__(parent, style="Toolbar.TFrame", padding=(10, 8))
        self.app = controller
        self.actions = actions
        self.monitor = SystemMonitor()
        self._finished_at = 0.0
        self._last_update = 0.0
        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self, style="Toolbar.TFrame")
        top.pack(fill="x")
        self.btn_start = ttk.Button(top, text="▶  Iniciar", style="Accent.TButton",
                                    command=self.actions["start"])
        self.btn_start.pack(side="left")
        self.btn_pause = ttk.Button(top, text="⏸  Pausar", command=self.actions["pause"])
        self.btn_pause.pack(side="left", padx=(6, 0))
        self.btn_cancel = ttk.Button(top, text="■  Cancelar", style="Danger.TButton",
                                     command=self.actions["cancel"])
        self.btn_cancel.pack(side="left", padx=(6, 0))
        tooltip(self.btn_cancel, "Cancela as tarefas em andamento e as pendentes.")

        self.var_scope = tk.StringVar(value="Selecionados (ou toda a fila pendente)")
        self.combo_scope = ttk.Combobox(top, textvariable=self.var_scope, state="readonly",
                                        width=32,
                                        values=["Selecionados (ou toda a fila pendente)",
                                                "Somente os selecionados",
                                                "Toda a fila pendente"])
        ttk.Label(top, text="Converter:", style="Status.TLabel").pack(side="left",
                                                                     padx=(14, 6))
        self.combo_scope.pack(side="left")

        self.lbl_status = ttk.Label(top, text="Pronto", style="StatusAccent.TLabel")
        self.lbl_status.pack(side="right")
        self.lbl_cpu = ttk.Label(top, text="", style="Status.TLabel")
        self.lbl_cpu.pack(side="right", padx=8)

        bottom = ttk.Frame(self, style="Toolbar.TFrame")
        bottom.pack(fill="x", pady=(6, 0))
        self.progress = ttk.Progressbar(bottom, mode="determinate", maximum=1000)
        self.progress.pack(side="left", fill="x", expand=True)
        self.lbl_progress = ttk.Label(bottom, text="", style="Status.TLabel", width=46,
                                      anchor="e")
        self.lbl_progress.pack(side="left", padx=(10, 0))

    # ------------------------------------------------------------------
    def tick(self) -> None:
        now = time.monotonic()
        if now - self._last_update < 0.35 and not self.app.queue.events.qsize() > 0:
            return
        self._last_update = now
        jobs = self.app.queue.jobs
        running = [job for job in jobs if job.status == "running"]
        pending = [job for job in jobs if job.status in ("pending", "analyzing")]
        done = sum(1 for job in jobs if job.status == "done")
        errors = sum(1 for job in jobs if job.status == "error")
        total = len(jobs)

        if running:
            overall = sum(job.progress for job in running) / max(1, len(running))
            active = running[0]
            speed = getattr(active, "_speed", None)
            self.progress.configure(mode="determinate")
            self.progress["value"] = int(overall * 1000)
            self.lbl_progress.configure(
                text=f"{len(running)} ativo(s) · {pending} na fila · {done}/{total} ok"
                     + (f" · {errors} erro(s)" if errors else ""))
            if self.app.queue.is_paused:
                self.lbl_status.configure(text="Pausado")
                self.btn_pause.configure(text="▶  Retomar")
            else:
                self.lbl_status.configure(text="Convertendo")
                self.btn_pause.configure(text="⏸  Pausar")
            self.btn_start.state(["disabled"])
            self.btn_pause.state(["!disabled"])
            self.btn_cancel.state(["!disabled"])
        elif pending and self.app.queue.is_running:
            self.progress["value"] = 0
            self.lbl_progress.configure(text=f"{pending} aguardando início")
            self.lbl_status.configure(text="Preparando")
            self.btn_start.state(["disabled"])
            self.btn_cancel.state(["!disabled"])
        else:
            if total and self._finished_at:
                stats = self.app.queue.stats
                self.lbl_progress.configure(
                    text=f"Concluído: {stats.done} ok · {stats.errors} erro(s) · "
                         f"{fmt_size(stats.bytes_written)}")
                self.lbl_status.configure(text="Fila ociosa")
            else:
                self.lbl_progress.configure(
                    text=(f"{total} arquivo(s) na fila" if total else "Fila vazia"))
                self.lbl_status.configure(text="Pronto")
            self.progress["value"] = 0
            self.btn_start.state(["!disabled"] if pending and not self.app.queue.is_running
                                 else (["!disabled"] if not total else ["disabled"]))
            self.btn_pause.state(["disabled"])
            self.btn_cancel.state(["disabled"])
            self.btn_pause.configure(text="⏸  Pausar")

        cpu, mem = self.monitor.read()
        parts = []
        if cpu is not None:
            parts.append(f"CPU {cpu * 100:.0f}%")
        if mem is not None:
            parts.append(f"RAM {fmt_size(mem)}")
        threads, concurrent, per_job = self.app.effective_plan()
        parts.append(f"{concurrent}×{per_job} threads")
        self.lbl_cpu.configure(text="  ·  ".join(parts))

    def notify_finished(self) -> None:
        self._finished_at = time.time()
