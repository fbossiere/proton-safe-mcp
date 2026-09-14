"""One assistant window per account, without exposing anything to the network.

Opening Proton Safe twice must bring back the window that is already there, not start a
second setup alongside the first. Two of them would each hold their own view of the same
configuration, the same journal and the same client — the shape of a duplicated
registration or a half-written file.

The rendezvous is a local endpoint: a named pipe on Windows, a Unix domain socket on
Linux. Neither is reachable from another machine, and the endpoint is restricted to this
account. Nothing is ever read from it: a connection means "someone tried to open Proton
Safe", and the only reaction is to raise the window that already exists.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
from collections.abc import Callable
from pathlib import Path

from PySide6 import QtCore, QtNetwork

from ..platform_services import PrivacyError, services

#: A fixed prefix plus a per-account digest, so two people signed in at once each get
#: their own endpoint instead of one blocking the other.
_PREFIX = "proton-safe-assistant"

#: The file whose exclusive lock is the slot itself. It holds no content: what matters
#: is who has it locked, which the operating system tracks and releases on its own.
_LOCK_NAME = "single-instance.lock"


def endpoint_name() -> str:
    """A stable endpoint name for this account, carrying no readable personal detail."""
    identity = str(Path.home().resolve())
    digest = hashlib.sha256(identity.encode("utf-8", "surrogateescape")).hexdigest()[:16]
    return f"{_PREFIX}-{digest}"


def signal_existing_instance(*, timeout_ms: int = 500) -> bool:
    """Return True when an assistant is already running for this account.

    Connecting is the whole message. Nothing is sent, so a program that managed to reach
    the endpoint cannot ask the running assistant to do anything.
    """
    socket = QtNetwork.QLocalSocket()
    socket.connectToServer(endpoint_name())
    connected = socket.waitForConnected(timeout_ms)
    if connected:
        # Give the running instance a moment to notice before this process exits.
        socket.waitForDisconnected(timeout_ms)
    socket.abort()
    return bool(connected)


class SingleInstanceGuard(QtCore.QObject):
    """Holds this account's endpoint and raises the window when someone knocks."""

    def __init__(self, on_raise: Callable[[], None], parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._on_raise = on_raise
        #: The descriptor whose lock is this process's claim on the slot. The operating
        #: system releases it however this process ends, so it never goes stale.
        self._lock: int | None = None
        self._server = QtNetwork.QLocalServer(self)
        # This account only. On Windows the pipe's DACL is restricted to the owner; on
        # Linux the socket is created inside the user's own runtime directory.
        self._server.setSocketOptions(QtNetwork.QLocalServer.SocketOption.UserAccessOption)
        self._server.newConnection.connect(self._knocked)

    def listen(self) -> bool:
        """Claim this account's assistant slot, or report that one is already taken.

        The endpoint alone cannot decide this. Two launches can each find nothing
        answering and then each claim the name, the second clearing the first's live
        endpoint on its way — two windows over one configuration, one journal and one
        client. So the slot is an exclusive file lock, taken first and held for the life
        of the process: only the holder goes on to claim the endpoint, and an endpoint
        found while holding the lock was necessarily left behind by a process that is
        gone, which is what makes clearing it safe.
        """
        if self._lock is not None:
            return True
        platform = services()
        directory = platform.state_dir() / "assistant"
        try:
            platform.ensure_private_directory(directory)
            handle = os.open(directory / _LOCK_NAME, os.O_RDWR | os.O_CREAT, 0o600)
        except (OSError, PrivacyError):
            # Without somewhere private to put the lock there is nothing to serialise
            # on, and opening a second window anyway is the worse of the two outcomes.
            return False
        if not platform.try_lock(handle):
            os.close(handle)
            return False
        self._lock = handle
        name = endpoint_name()
        if not self._server.listen(name):
            QtNetwork.QLocalServer.removeServer(name)
            if not self._server.listen(name):
                self.close()
                return False
        return True

    def close(self) -> None:
        self._server.close()
        if self._lock is not None:
            # Only ever this process's own endpoint, and only while it still holds the
            # lock that makes it this process's to remove.
            QtNetwork.QLocalServer.removeServer(endpoint_name())
            with contextlib.suppress(OSError):
                os.close(self._lock)
            self._lock = None

    def _knocked(self) -> None:
        connection = self._server.nextPendingConnection()
        if connection is not None:
            # Nothing is read. The connection itself is the entire message.
            connection.disconnectFromServer()
            connection.deleteLater()
        self._on_raise()
