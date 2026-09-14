"""The Linux implementation, which keeps the validations the project already had.

Nothing in here is new behaviour. ``0700``/``0600``, ``getuid`` ownership and
``O_NOFOLLOW`` are the guarantees the Ubuntu package was reviewed and tested against,
so they are preserved exactly rather than generalised into something weaker that both
platforms could satisfy.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import platform
import select
import stat
import tempfile
from pathlib import Path, PurePath, PurePosixPath
from typing import IO, Any, ClassVar, Final

from .base import (
    LineReader,
    PlatformServices,
    PrivacyError,
    SessionFacts,
    _chunk_limit,
)

_PRIVATE_DIR_MODE: Final = 0o700
_PRIVATE_FILE_MODE: Final = 0o600

#: The validated target. Any other Linux still runs, with the scope stated plainly.
VALIDATED_DISTRIBUTION: Final = "ubuntu"
VALIDATED_VERSION: Final = "24.04"
VALIDATED_MACHINE: Final = "x86_64"


class PosixLineReader(LineReader):
    """``select`` accepts pipes here, so the deadline needs no helper thread."""

    def _receive(self, timeout: float) -> bytes | None:
        if not select.select([self._stream], [], [], timeout)[0]:
            return None
        return os.read(self._stream.fileno(), _chunk_limit(self._budget))

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self._stream.close()


class PosixServices(PlatformServices):
    """Linux paths, permissions, session and process handling."""

    name: ClassVar[str] = "posix"
    executable_suffix: ClassVar[str] = ""
    approved_keyring_modules: ClassVar[frozenset[str]] = frozenset(
        {"keyring.backends.SecretService"}
    )
    managed_environment_names: ClassVar[tuple[str, ...]] = (
        "DBUS_SESSION_BUS_ADDRESS",
        "HOME",
        "LANG",
        "PATH",
        "XDG_DATA_HOME",
        "XDG_RUNTIME_DIR",
        "XDG_STATE_HOME",
    )
    client_passthrough_environment: ClassVar[tuple[str, ...]] = (
        "DBUS_SESSION_BUS_ADDRESS",
        "HOME",
        "XDG_RUNTIME_DIR",
    )
    client_command_environment: ClassVar[tuple[str, ...]] = (
        "DBUS_SESSION_BUS_ADDRESS",
        "HOME",
        "LANG",
        "PATH",
        "XDG_RUNTIME_DIR",
    )
    path_flavour: ClassVar[type[PurePath]] = PurePosixPath

    # -- known folders -----------------------------------------------------------

    @staticmethod
    def _xdg(variable: str, fallback: str) -> Path:
        # An empty or relative value is ignored, as the XDG base directory
        # specification requires: Path("") would land in the working directory.
        value = os.environ.get(variable, "")
        return Path(value) if value.startswith("/") else Path.home() / fallback

    def config_dir(self) -> Path:
        return self._xdg("XDG_CONFIG_HOME", ".config") / "proton-safe-mcp"

    def state_dir(self) -> Path:
        return (self._xdg("XDG_STATE_HOME", ".local/state") / "proton-safe-mcp").resolve()

    def data_dir(self) -> Path:
        return self._xdg("XDG_DATA_HOME", ".local/share") / "proton-safe-mcp"

    # -- private storage ---------------------------------------------------------

    def ensure_private_directory(self, directory: Path) -> None:
        directory.mkdir(mode=_PRIVATE_DIR_MODE, parents=True, exist_ok=True)
        try:
            info = os.stat(directory, follow_symlinks=False)
        except OSError as exc:
            raise PrivacyError(
                f"The directory cannot be inspected ({type(exc).__name__}).",
                code="CONFIG_PERMISSIONS",
            ) from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise PrivacyError("The path is not a directory.", code="CONFIG_PERMISSIONS")
        if stat.S_IMODE(info.st_mode) & 0o077:
            directory.chmod(_PRIVATE_DIR_MODE)

    def verify_private_directory(self, directory: Path) -> None:
        try:
            info = os.stat(directory, follow_symlinks=True)
        except FileNotFoundError as exc:
            raise PrivacyError("The directory does not exist.", code="CONFIG_MISSING") from exc
        except OSError as exc:
            raise PrivacyError(
                f"The directory cannot be inspected ({type(exc).__name__}).",
                code="CONFIG_INVALID",
            ) from exc
        if info.st_uid != os.getuid():
            raise PrivacyError(
                "The directory belongs to another account.", code="CONFIG_PERMISSIONS"
            )
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise PrivacyError(
                "The directory is readable by other accounts on this computer.",
                code="CONFIG_PERMISSIONS",
            )

    def directory_privacy(self, directory: Path) -> tuple[str, str]:
        try:
            metadata = directory.stat()
        except FileNotFoundError:
            return "missing", ""
        except OSError as exc:
            return "unreadable", f"could not inspect permissions ({type(exc).__name__})"
        mode = stat.S_IMODE(metadata.st_mode)
        # Both halves matter: a mode of 0o000 is private and unusable, and a mode of
        # 0o755 is usable and shared. Neither is an acceptable state directory.
        if not stat.S_ISDIR(metadata.st_mode) or mode & 0o700 != 0o700 or mode & 0o077:
            return "not_private", (
                "must grant rwx to the owner and be inaccessible to group and others"
            )
        return "private", ""

    def read_private_file(self, path: Path, *, max_bytes: int) -> bytes:
        try:
            # O_NOFOLLOW refuses a symlink at the final component, and every check below
            # runs against the descriptor actually opened.
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        except FileNotFoundError as exc:
            raise PrivacyError("No file was found at that path.", code="CONFIG_MISSING") from exc
        except OSError as exc:
            # ELOOP lands here when the path is a symlink.
            raise PrivacyError(
                f"The file cannot be opened ({type(exc).__name__}).",
                code="CONFIG_PERMISSIONS" if isinstance(exc, PermissionError) else "CONFIG_INVALID",
            ) from exc
        try:
            # Inspect the descriptor before wrapping it: O_RDONLY succeeds on a
            # directory, which fdopen would then reject noisily.
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise PrivacyError("The path is not a regular file.", code="CONFIG_INVALID")
            if info.st_uid != os.getuid():
                raise PrivacyError(
                    "The file belongs to another account.", code="CONFIG_PERMISSIONS"
                )
            if stat.S_IMODE(info.st_mode) & 0o077:
                raise PrivacyError(
                    "The file is readable by other accounts on this computer.",
                    code="CONFIG_PERMISSIONS",
                )
            if info.st_size > max_bytes:
                raise PrivacyError("The file is unexpectedly large.", code="CONFIG_INVALID")
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                return handle.read(max_bytes + 1)
        finally:
            os.close(descriptor)

    def write_private_file(self, path: Path, data: bytes) -> None:
        directory = path.parent
        self.ensure_private_directory(directory)
        descriptor, temporary = tempfile.mkstemp(dir=directory, prefix=".proton-safe-")
        temporary_path = Path(temporary)
        try:
            os.fchmod(descriptor, _PRIVATE_FILE_MODE)
            with os.fdopen(descriptor, "wb", closefd=True) as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise
        directory_descriptor = os.open(directory, os.O_RDONLY | os.O_CLOEXEC)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)

    def create_private_file(self, path: Path, data: bytes = b"") -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        descriptor = os.open(path, flags, _PRIVATE_FILE_MODE)
        try:
            _write_all(descriptor, data)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def append_to_private_file(self, path: Path, data: bytes) -> None:
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
        try:
            _write_all(descriptor, data)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def secure_existing_path(self, path: Path) -> None:
        if path.is_symlink():
            raise PrivacyError("The path is a symbolic link.", code="CONFIG_PERMISSIONS")
        if path.is_dir():
            path.chmod(_PRIVATE_DIR_MODE)
        elif path.exists():
            path.chmod(_PRIVATE_FILE_MODE)

    def is_plain_file(self, path: Path) -> bool:
        try:
            return path.is_file() and not path.is_symlink()
        except OSError:
            return False

    # -- session -----------------------------------------------------------------

    def session_facts(self) -> SessionFacts:
        elevated = os.geteuid() == 0
        if os.environ.get("WAYLAND_DISPLAY"):
            return SessionFacts("Wayland", elevated)
        if os.environ.get("DISPLAY"):
            return SessionFacts("X11", elevated)
        return SessionFacts("", elevated)

    def system_status(self) -> tuple[str, str]:
        machine = platform.machine()
        if platform.system() != "Linux" or machine != VALIDATED_MACHINE:
            return "fail", f"{platform.system()} {machine}"
        release = _os_release()
        version = release.get("VERSION_ID", "")
        label = f"{release.get('NAME', 'Linux')} {version}".strip()
        validated = release.get("ID", "").lower() == VALIDATED_DISTRIBUTION and (
            version == VALIDATED_VERSION
        )
        # Another Linux is not refused; the assistant just says what was validated.
        return "pass" if validated else "warn", label

    # -- executables and processes -----------------------------------------------

    def is_executable_file(self, path: Path) -> bool:
        try:
            return path.is_file() and os.access(path, os.X_OK)
        except OSError:
            return False

    def spawn_options(self) -> dict[str, Any]:
        return {"start_new_session": True}

    def open_line_reader(self, stream: IO[bytes], *, budget: int) -> LineReader:
        return PosixLineReader(stream, budget=budget)

    def try_lock(self, descriptor: int) -> bool:
        """``flock``, which the kernel drops when this process ends, however it ends."""
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True


def _write_all(descriptor: int, data: bytes) -> None:
    """Write every byte, including when the OS reports a short write."""
    remaining = memoryview(data)
    while remaining:
        written = os.write(descriptor, remaining)
        if written == 0:
            raise OSError("write returned zero bytes")
        remaining = remaining[written:]


def _os_release() -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        content = Path("/etc/os-release").read_text(encoding="utf-8")
    except OSError:
        return values
    for line in content.splitlines():
        name, separator, raw = line.partition("=")
        if separator:
            values[name.strip()] = raw.strip().strip('"')
    return values
