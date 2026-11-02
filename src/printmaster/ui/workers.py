"""Ejecución en segundo plano con QThreadPool."""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

log = logging.getLogger("printmaster")

_alive: set[Worker] = set()


class Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Worker(QRunnable):
    def __init__(self, fn: Callable, *args, **kwargs) -> None:
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = Signals()
        self.setAutoDelete(False)

    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001 - se informa a la interfaz
            log.error("Tarea en segundo plano falló: %s\n%s", exc, traceback.format_exc())
            self.signals.failed.emit(str(exc))
        else:
            self.signals.done.emit(result)
        finally:
            _alive.discard(self)


class _Relay(QObject):
    """Receptor hijo del dueño: si el dueño se destruye, Qt corta la conexión."""

    def __init__(self, owner: QObject, on_done, on_failed) -> None:
        super().__init__(owner)
        self._on_done, self._on_failed = on_done, on_failed

    @Slot(object)
    def done(self, result) -> None:
        try:
            if self._on_done is not None:
                self._on_done(result)
        finally:
            self.deleteLater()

    @Slot(str)
    def failed(self, message: str) -> None:
        try:
            if self._on_failed is not None:
                self._on_failed(message)
        finally:
            self.deleteLater()


def run_async(fn: Callable, *args, on_done: Callable | None = None,
              on_failed: Callable[[str], None] | None = None,
              owner: QObject | None = None, **kwargs) -> Worker:
    """Ejecuta fn en el pool. Con `owner`, los callbacks no se llaman si el dueño ya no existe."""
    worker = Worker(fn, *args, **kwargs)
    if owner is not None:
        relay = _Relay(owner, on_done, on_failed)
        worker.signals.done.connect(relay.done)
        worker.signals.failed.connect(relay.failed)
    else:
        if on_done is not None:
            worker.signals.done.connect(on_done)
        if on_failed is not None:
            worker.signals.failed.connect(on_failed)
    _alive.add(worker)
    QThreadPool.globalInstance().start(worker)
    return worker
