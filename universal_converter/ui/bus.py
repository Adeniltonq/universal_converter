"""Barramento de eventos simples entre o núcleo (threads) e a interface (Tk).

O núcleo nunca chama a GUI diretamente: ele publica eventos aqui e a interface
os consome periodicamente na thread principal do Tk.
"""

from __future__ import annotations

import queue
from typing import Callable


class UiBus:
    def __init__(self) -> None:
        self._queue: "queue.Queue[tuple[str, dict]]" = queue.Queue()
        self._listeners: dict[str, list[Callable[[dict], None]]] = {}

    def emit(self, topic: str, **payload) -> None:
        self._queue.put((topic, payload))

    def subscribe(self, topic: str, callback: Callable[[dict], None]) -> None:
        self._listeners.setdefault(topic, []).append(callback)

    def dispatch(self, limit: int = 600) -> int:
        """Consome eventos pendentes (chamado pela interface)."""
        count = 0
        while count < limit:
            try:
                topic, payload = self._queue.get_nowait()
            except queue.Empty:
                break
            count += 1
            for callback in self._listeners.get(topic, ()):
                try:
                    callback(payload)
                except Exception:  # noqa: BLE001 - um listener não pode derrubar a UI
                    import logging
                    logging.getLogger("umc.ui").exception("Erro no evento %s", topic)
            for callback in self._listeners.get("*", ()):
                try:
                    callback({"topic": topic, **payload})
                except Exception:  # noqa: BLE001
                    import logging
                    logging.getLogger("umc.ui").exception("Erro no evento %s", topic)
        return count

    def pending(self) -> bool:
        return not self._queue.empty()
