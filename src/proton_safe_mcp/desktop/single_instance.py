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

import hashlib
from collections.abc import Callable
from pathlib import Path

from PySide6 import QtCore, QtNetwork

#: A fixed prefix plus a per-account digest, so two people signed in at once each get
#: their own endpoint instead of one blocking the other.
_PREFIX = "proton-safe-assistant"


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
        self._server = QtNetwork.QLocalServer(self)
        # This account only. On Windows the pipe's DACL is restricted to the owner; on
        # Linux the socket is created inside the user's own runtime directory.
        self._server.setSocketOptions(QtNetwork.QLocalServer.SocketOption.UserAccessOption)
        self._server.newConnection.connect(self._knocked)

    def listen(self) -> bool:
        """Claim the endpoint, clearing one left behind by a crash."""
        name = endpoint_name()
        if self._server.listen(name):
            return True
        # A previous run that was killed can leave a stale endpoint. Removing it is safe
        # here precisely because the caller has already checked that nothing answers.
        QtNetwork.QLocalServer.removeServer(name)
        return bool(self._server.listen(name))

    def close(self) -> None:
        self._server.close()
        QtNetwork.QLocalServer.removeServer(endpoint_name())

    def _knocked(self) -> None:
        connection = self._server.nextPendingConnection()
        if connection is not None:
            # Nothing is read. The connection itself is the entire message.
            connection.disconnectFromServer()
            connection.deleteLater()
        self._on_raise()
