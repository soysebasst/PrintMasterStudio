"""Ejecución en segundo plano con QThreadPool."""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

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


def run_async(fn: Callable, *args, on_done: Callable | None = None,
              on_failed: Callable[[str], None] | None = None, **kwargs) -> Worker:
    worker = Worker(fn, *args, **kwargs)
    if on_done is not None:
        worker.signals.done.connect(on_done)
    if on_failed is not None:
        worker.signals.failed.connect(on_failed)
    _alive.add(worker)
    QThreadPool.globalInstance().start(worker)
    return worker
