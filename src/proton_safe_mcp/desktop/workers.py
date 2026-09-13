"""Run slow keyring, network and client calls off the interface thread.

Every long operation goes through here, so the window keeps repainting and Cancel stays
responsive. Cancellation is cooperative and only ever takes effect before a commit.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6 import QtCore

from ..errors import ProtonMCPError
from ..onboarding.models import Code
from ..onboarding.service import Cancelled, CancelToken


class _TaskSignals(QtCore.QObject):
    done = QtCore.Signal(object)
    failed = QtCore.Signal(str)


class ServiceTask(QtCore.QRunnable):
    """One service call, with its own cancellation token."""

    def __init__(self, work: Callable[[CancelToken], Any], token: CancelToken) -> None:
        super().__init__()
        self._work = work
        self._token = token
        self.signals = _TaskSignals()

    @QtCore.Slot()
    def run(self) -> None:  # pragma: no cover - exercised through TaskRunner
        try:
            result = self._work(self._token)
        except Cancelled:
            self.signals.failed.emit(str(Code.CANCELLED))
        except ProtonMCPError as exc:
            self.signals.failed.emit(str(exc.code or Code.RUNTIME_START_FAILED))
        except OSError:
            # Raw errors can carry private paths, so only a code crosses this boundary.
            self.signals.failed.emit(str(Code.RUNTIME_START_FAILED))
        else:
            self.signals.done.emit(result)


class TaskRunner(QtCore.QObject):
    """Runs one task at a time and exposes its result on the interface thread."""

    done = QtCore.Signal(object)
    failed = QtCore.Signal(str)
    busy_changed = QtCore.Signal(bool)

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QtCore.QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._token: CancelToken | None = None
        self._busy = False

    @property
    def busy(self) -> bool:
        return self._busy

    def start(self, work: Callable[[CancelToken], Any]) -> bool:
        """Start ``work``. Returns False when another task is still running."""
        if self._busy:
            return False
        self._token = CancelToken()
        task = ServiceTask(work, self._token)
        task.signals.done.connect(self._on_done)
        task.signals.failed.connect(self._on_failed)
        self._set_busy(True)
        self._pool.start(task)
        return True

    def cancel(self) -> None:
        """Ask the running task to stop at its next safe point."""
        if self._token is not None:
            self._token.cancel()

    def wait(self, milliseconds: int = 30_000) -> bool:
        """Block until the running task finishes. Used at shutdown and in tests."""
        return self._pool.waitForDone(milliseconds)

    def _set_busy(self, value: bool) -> None:
        self._busy = value
        self.busy_changed.emit(value)

    @QtCore.Slot(object)
    def _on_done(self, result: object) -> None:
        self._set_busy(False)
        self.done.emit(result)

    @QtCore.Slot(str)
    def _on_failed(self, code: str) -> None:
        self._set_busy(False)
        self.failed.emit(code)
