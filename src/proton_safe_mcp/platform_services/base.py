"""The seam where Linux and Windows differ, and nothing else.

The mail engine, the tool limits, the draft rules and the whole onboarding flow are
shared. Only five things are implemented per platform, because in each of them the
operating system — not this project — decides what is actually safe:

* where a user's own configuration, state and data belong;
* how a file is made private to one account, and how that is verified;
* what an ordinary, non-elevated interactive session looks like;
* which credential store may hold the Bridge password;
* how a child process is started and read without a console or a deadlock.

A platform that cannot offer one of these refuses the operation. Nothing here may weaken
a guarantee because an API is missing on the other system.
"""

from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import IO, Any, ClassVar, Final

from ..errors import ProtonMCPError

#: Reading a child's handshake must never be able to pull in an unbounded stream.
_READ_CHUNK: Final = 65536


class PrivacyError(ProtonMCPError):
    """A path is not private to this account, and could not be made private."""


class UnsupportedPlatformError(ProtonMCPError):
    """This operating system is outside the supported scope."""


@dataclass(frozen=True, slots=True)
class SessionFacts:
    """What the current session is, as far as the operating system will say.

    ``elevated`` is a refusal, not a warning: the managed setup writes into one user's
    own profile and registers a client for that user. Running it as another identity
    would install for an account the person is not using.
    """

    #: "Wayland", "X11", "Windows" … or "" when there is no interactive desktop session.
    kind: str
    elevated: bool


class LineReader(ABC):
    """Newline-delimited frames from a child's stdout, under one global deadline.

    The buffering, the byte budget and the deadline are shared; only waiting for bytes
    is platform work. ``select.select`` accepts pipes on POSIX and sockets only on
    Windows, which is the whole reason this class exists.
    """

    def __init__(self, stream: IO[bytes], *, budget: int) -> None:
        self._stream = stream
        self._budget = budget
        self._pending = bytearray()
        self._eof = False

    def read_line(self, deadline: float) -> bytes | None:
        """Return the next frame, or None at end of stream.

        Raises ``TimeoutError`` when the shared deadline passes and ``ValueError`` when
        the child produced more output than a handshake can need.
        """
        while True:
            newline = self._pending.find(b"\n")
            if newline >= 0:
                line = bytes(self._pending[:newline])
                del self._pending[: newline + 1]
                return line
            if self._eof:
                return None
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("handshake deadline reached")
            chunk = self._receive(remaining)
            if chunk is None:
                continue
            if not chunk:
                self._eof = True
                continue
            self._budget -= len(chunk)
            if self._budget < 0:
                raise ValueError("the child produced more output than a handshake needs")
            self._pending.extend(chunk)

    @abstractmethod
    def _receive(self, timeout: float) -> bytes | None:
        """Return bytes, ``b""`` at end of stream, or None when nothing arrived in time."""

    @abstractmethod
    def close(self) -> None:
        """Release the stream and any helper thread. Always safe to call twice."""


class PlatformServices(ABC):
    """The platform contract. One instance per process, resolved by ``services()``."""

    #: Stable identifier used in diagnostics and tests, never shown to the user.
    name: ClassVar[str]
    #: What this product's own executables are called here.
    executable_suffix: ClassVar[str] = ""
    #: The credential stores the managed setup accepts. A file or null backend is not
    #: one of them: falling back to a file would defeat the point of a keyring.
    approved_keyring_modules: ClassVar[frozenset[str]]
    #: Environment names a managed child may inherit. No PROTON_* value is ever passed:
    #: the runtime must work from its configuration file and the keyring alone.
    managed_environment_names: ClassVar[tuple[str, ...]]
    #: What the managed plugin asks the client to pass through when it starts the
    #: server. It is the subset the runtime needs to reach its own files and keyring;
    #: it never carries a secret, and never a PROTON_* value.
    client_passthrough_environment: ClassVar[tuple[str, ...]]
    #: What a client's own command is run with when the assistant probes or drives it.
    client_command_environment: ClassVar[tuple[str, ...]]
    #: This platform's path rules, used to judge a configured string.
    path_flavour: ClassVar[type[PurePath]]

    # -- known folders -----------------------------------------------------------

    @abstractmethod
    def config_dir(self) -> Path:
        """This account's directory for the managed configuration."""

    @abstractmethod
    def state_dir(self) -> Path:
        """This account's default directory for state and staged attachments.

        An explicit ``PROTON_MCP_STATE_DIR`` override is applied by the configuration,
        not here, so every caller that must ignore the override gets the same answer.
        """

    @abstractmethod
    def data_dir(self) -> Path:
        """This account's directory for the managed plugin and its local marketplace."""

    # -- private storage ---------------------------------------------------------

    @abstractmethod
    def ensure_private_directory(self, directory: Path) -> None:
        """Create the directory, private to this account. Only the leaf is tightened."""

    @abstractmethod
    def verify_private_directory(self, directory: Path) -> None:
        """Raise ``PrivacyError`` unless the directory exists and is private to us."""

    @abstractmethod
    def directory_privacy(self, directory: Path) -> tuple[str, str]:
        """Classify a directory without raising, for a diagnostic report.

        Returns one of ``"private"``, ``"not_private"``, ``"unreadable"`` or
        ``"missing"``, with a sentence explaining a failure in this platform's own
        terms. A caller can act on the state and print the sentence; neither has to
        know what privacy means here.
        """

    def is_private_directory(self, directory: Path) -> bool:
        """Whether the directory exists and is private, without raising."""
        return self.directory_privacy(directory)[0] == "private"

    @abstractmethod
    def read_private_file(self, path: Path, *, max_bytes: int) -> bytes:
        """Read a regular file this account owns, refusing a redirected or shared one.

        The checks run against the file that was actually opened, never against a path
        re-resolved afterwards.
        """

    @abstractmethod
    def write_private_file(self, path: Path, data: bytes) -> None:
        """Replace the file atomically, private to this account, keeping the old one
        intact when anything fails."""

    @abstractmethod
    def create_private_file(self, path: Path, data: bytes = b"") -> None:
        """Create a new private file, failing if something already exists at the path."""

    @abstractmethod
    def secure_existing_path(self, path: Path) -> None:
        """Tighten a file or directory this product owns. Never recursive."""

    @abstractmethod
    def is_plain_file(self, path: Path) -> bool:
        """Whether this is a regular file and not a symlink, junction or other
        reparse point pointing somewhere else."""

    @abstractmethod
    def append_to_private_file(self, path: Path, data: bytes) -> None:
        """Append to an existing private file without following a redirection."""

    # -- session -----------------------------------------------------------------

    @abstractmethod
    def session_facts(self) -> SessionFacts:
        """Describe the session the assistant is running in."""

    @abstractmethod
    def system_status(self) -> tuple[str, str]:
        """Return ``("pass" | "warn" | "fail", label)`` for this operating system.

        The distinction matters: on Linux an untested distribution is a warning, because
        the package still runs there. On Windows anything outside Windows 11 x64 is a
        refusal, because nothing outside that scope has been validated at all.

        The label carries a product name and a version, never a machine or account name.
        """

    # -- executables and processes -----------------------------------------------

    @abstractmethod
    def is_executable_file(self, path: Path) -> bool:
        """Whether this path is something this product may actually launch.

        A launcher script this project would have to quote into a command line is not:
        the real executable is resolved, or the mode is declared unsupported.
        """

    @abstractmethod
    def spawn_options(self) -> dict[str, Any]:
        """Extra ``subprocess`` keywords that detach the child and show no console."""

    @abstractmethod
    def open_line_reader(self, stream: IO[bytes], *, budget: int) -> LineReader:
        """Wrap a child's stdout so frames can be read under a deadline."""

    @abstractmethod
    def try_lock(self, descriptor: int) -> bool:
        """Take an exclusive lock on an open file, or return False without waiting.

        The lock is held by the process, not by the file's contents, so the operating
        system releases it however the process ends — including a power cut, which is
        what makes it safe to conclude that anything left behind by an unlocked holder
        is stale. Two launches racing each other cannot both succeed.
        """

    # -- keyring -----------------------------------------------------------------

    def configure_keyring(self, backend: object) -> None:
        """Apply this platform's storage policy to the resolved keyring backend.

        Linux has nothing to set: the Secret Service decides where a secret lives, and
        it is already scoped to the login session. Windows overrides this to pin
        Credential Manager persistence, which otherwise defaults to roaming.
        """
        return None

    def keyring_probe_targets(self, service: str, account: str) -> tuple[str, ...]:
        """Every store entry a self-test must clean up for one service and account.

        ``keyring`` may write a secondary, compound entry when two accounts collide
        under one service name. A self-test that ignored it would leave a stray value.
        """
        return (f"{service}:{account}",)

    # -- shared helpers ----------------------------------------------------------

    def managed_environment(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        """Build the minimal environment a managed child process runs with."""
        return self._environment(self.managed_environment_names, extra)

    def client_environment(self) -> dict[str, str]:
        """Build the environment a client's own command is probed and driven with."""
        return self._environment(self.client_command_environment, None)

    def _environment(self, names: Sequence[str], extra: Mapping[str, str] | None) -> dict[str, str]:
        environment = {name: os.environ[name] for name in names if name in os.environ}
        for name, value in (extra or {}).items():
            if name.startswith("PROTON_"):
                raise ValueError("a managed child never receives a PROTON_* value")
            environment[name] = value
        return environment

    def executable_name(self, stem: str) -> str:
        """The on-disk name of one of this product's own executables."""
        return f"{stem}{self.executable_suffix}"

    def executable_candidates(self, paths: Iterable[Path]) -> list[Path]:
        """Keep only real, launchable files, resolved and de-duplicated.

        Candidates come from documented locations. A file is never run just because of
        its name: the caller still corroborates it with ``--version`` and the exact
        subcommands it intends to use.
        """
        seen: set[Path] = set()
        kept: list[Path] = []
        for path in paths:
            try:
                resolved = path.resolve(strict=True)
            except OSError:
                continue
            if resolved in seen:
                continue
            if not self.is_executable_file(resolved):
                continue
            seen.add(resolved)
            kept.append(resolved)
        return kept

    def is_absolute_path(self, value: str) -> bool:
        """Whether a configured string names an absolute path on this platform.

        Judged with this platform's own path rules rather than the running
        interpreter's, so ``C:\\Users\\...`` is absolute for Windows and ``/home/...``
        is absolute for Linux, whichever machine is asking.
        """
        return bool(value) and self.path_flavour(value).is_absolute()

    @staticmethod
    def _read_stream(stream: IO[bytes], limit: int) -> bytes:
        return os.read(stream.fileno(), min(_READ_CHUNK, limit))


def _chunk_limit(budget: int) -> int:
    """One read may fetch at most one byte more than the budget, so overrun is visible."""
    return max(budget + 1, 1)


def resolve_state_directory(configured: str | None, default: Path) -> Path:
    """Apply the one rule both platforms share: an override must be absolute."""
    if configured and Path(configured).expanduser().is_absolute():
        return Path(configured).expanduser().resolve()
    return default


__all__ = [
    "LineReader",
    "PlatformServices",
    "PrivacyError",
    "SessionFacts",
    "UnsupportedPlatformError",
    "_chunk_limit",
    "resolve_state_directory",
]
