"""The Windows implementation: known folders, native ACLs, Credential Manager, pipes.

Every guarantee the Linux build gets from a Unix mode is rebuilt here from what Windows
actually offers. A mode of ``0600`` means nothing on this platform, so private storage is
an explicit protected DACL; ``O_NOFOLLOW`` does not exist, so a redirection is caught by
refusing reparse points and by confirming that the file opened is the file inspected.

Nothing falls back to "good enough because the POSIX call is missing". Where Windows
cannot establish a guarantee, the operation is refused.
"""

from __future__ import annotations

import contextlib
import ctypes
import os
import queue
import secrets as _secrets
import stat
import sys
import threading
from ctypes import wintypes
from pathlib import Path, PurePath, PureWindowsPath
from typing import IO, Any, ClassVar, Final

from .base import (
    LineReader,
    PlatformServices,
    PrivacyError,
    SessionFacts,
    UnsupportedPlatformError,
)
from .winacl import PrivacyReport, assess_privacy, private_sddl

#: Windows 11 starts at build 22000. Windows 10 is a deliberate product exclusion.
MINIMUM_BUILD: Final = 22000
#: ``GetNativeSystemInfo`` architecture codes. The native value is what matters: an ARM64
#: machine emulating x64 would otherwise look like a supported system.
_PROCESSOR_ARCHITECTURE_AMD64: Final = 9
_PROCESSOR_ARCHITECTURE_ARM64: Final = 12
_ARCHITECTURE_NAMES: Final[dict[int, str]] = {
    0: "x86",
    5: "ARM",
    6: "Itanium",
    9: "x64",
    12: "ARM64",
}

_SE_FILE_OBJECT: Final = 1
_OWNER_SECURITY_INFORMATION: Final = 0x00000001
_DACL_SECURITY_INFORMATION: Final = 0x00000004
_PROTECTED_DACL_SECURITY_INFORMATION: Final = 0x80000000
_SDDL_REVISION_1: Final = 1
_TOKEN_QUERY: Final = 0x0008
_TOKEN_USER: Final = 1
_TOKEN_ELEVATION: Final = 20

_CREATE_NEW_PROCESS_GROUP: Final = 0x00000200
_CREATE_NO_WINDOW: Final = 0x08000000

# Windows-only open flags. Read through ``getattr`` so this module stays importable — and
# type-checkable — on the Linux machine where most of it is developed and tested.
_O_BINARY: Final = getattr(os, "O_BINARY", 0)
_O_NOINHERIT: Final = getattr(os, "O_NOINHERIT", 0)

#: ``FOLDERID_LocalAppData``. Resolved through the shell so a redirected or roaming
#: profile is reported by Windows itself rather than guessed from ``C:\\Users``.
_FOLDERID_LOCAL_APP_DATA: Final = "{F1B32785-6FBA-4FCF-9D55-7B8E7F157091}"

#: The product's own folder inside the user's local application data.
PRODUCT_FOLDER: Final = "Proton Safe"

#: Executables this product is willing to launch. A ``.cmd`` or ``.bat`` launcher would
#: have to be quoted into a command line built from user-controlled paths, so it is not
#: accepted: the real executable is resolved, or the mode is declared unsupported.
LAUNCHABLE_SUFFIXES: Final = frozenset({".exe", ".com"})


def _require_windows() -> Any:
    """Return the Windows API namespace, or refuse plainly off Windows.

    ``ctypes.windll`` exists only on Windows, so its absence is the check. Reading it
    through ``getattr`` is also what keeps this module importable, and type-checkable,
    on the Linux machine where most of it is written.
    """
    windll = getattr(ctypes, "windll", None)
    if windll is None:  # pragma: no cover - platform guard
        raise UnsupportedPlatformError("This operation needs Windows.", code="SYSTEM_UNSUPPORTED")
    return windll


def _last_error(operation: str) -> PrivacyError:
    code = getattr(ctypes, "get_last_error", lambda: 0)()
    return PrivacyError(f"{operation} failed (Windows error {code}).", code="CONFIG_PERMISSIONS")


class _LocalMemory:
    """Frees a buffer Windows allocated, whatever happens while it is in use."""

    def __init__(self, pointer: Any) -> None:
        self.pointer = pointer

    def __enter__(self) -> Any:
        return self.pointer

    def __exit__(self, *_exc: object) -> None:
        if self.pointer:
            with contextlib.suppress(Exception):
                _require_windows().kernel32.LocalFree(self.pointer)


def current_user_sid() -> str:
    """Return this process's own account SID as a string."""
    windll = _require_windows()
    token = wintypes.HANDLE()
    if not windll.advapi32.OpenProcessToken(
        windll.kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)
    ):
        raise _last_error("Reading this account's identity")
    try:
        size = wintypes.DWORD()
        windll.advapi32.GetTokenInformation(token, _TOKEN_USER, None, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        if not windll.advapi32.GetTokenInformation(
            token, _TOKEN_USER, buffer, size, ctypes.byref(size)
        ):
            raise _last_error("Reading this account's identity")
        # TOKEN_USER starts with a SID_AND_ATTRIBUTES whose first member is the SID.
        sid_pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p)).contents
        text = ctypes.c_wchar_p()
        if not windll.advapi32.ConvertSidToStringSidW(sid_pointer, ctypes.byref(text)):
            raise _last_error("Reading this account's identity")
        with _LocalMemory(text):
            return str(text.value)
    finally:
        windll.kernel32.CloseHandle(token)


def is_elevated() -> bool:
    """Whether this process runs with an elevated token."""
    windll = _require_windows()
    token = wintypes.HANDLE()
    if not windll.advapi32.OpenProcessToken(
        windll.kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)
    ):
        return False
    try:
        elevation = wintypes.DWORD()
        size = wintypes.DWORD()
        if not windll.advapi32.GetTokenInformation(
            token,
            _TOKEN_ELEVATION,
            ctypes.byref(elevation),
            ctypes.sizeof(elevation),
            ctypes.byref(size),
        ):
            return False
        return bool(elevation.value)
    finally:
        windll.kernel32.CloseHandle(token)


def known_folder(folder_id: str = _FOLDERID_LOCAL_APP_DATA) -> Path:
    """Resolve a Windows known folder. Never built by joining ``C:\\Users`` and a name."""
    windll = _require_windows()
    guid = ctypes.create_string_buffer(16)
    if windll.ole32.IIDFromString(ctypes.c_wchar_p(folder_id), guid) != 0:
        raise UnsupportedPlatformError(
            "This computer's local application data folder could not be identified.",
            code="SYSTEM_UNSUPPORTED",
        )
    path_pointer = ctypes.c_wchar_p()
    if windll.shell32.SHGetKnownFolderPath(guid, 0, None, ctypes.byref(path_pointer)) != 0:
        raise UnsupportedPlatformError(
            "This computer's local application data folder is not available.",
            code="SYSTEM_UNSUPPORTED",
        )
    try:
        value = path_pointer.value
        if not value:
            raise UnsupportedPlatformError(
                "This computer's local application data folder is empty.",
                code="SYSTEM_UNSUPPORTED",
            )
        return Path(value)
    finally:
        windll.ole32.CoTaskMemFree(path_pointer)


def native_architecture() -> tuple[int, str]:
    """Return the machine's native processor architecture, ignoring any emulation."""
    windll = _require_windows()

    class _SystemInfo(ctypes.Structure):
        _fields_ = (
            ("wProcessorArchitecture", wintypes.WORD),
            ("wReserved", wintypes.WORD),
            ("dwPageSize", wintypes.DWORD),
            ("lpMinimumApplicationAddress", ctypes.c_void_p),
            ("lpMaximumApplicationAddress", ctypes.c_void_p),
            ("dwActiveProcessorMask", ctypes.c_void_p),
            ("dwNumberOfProcessors", wintypes.DWORD),
            ("dwProcessorType", wintypes.DWORD),
            ("dwAllocationGranularity", wintypes.DWORD),
            ("wProcessorLevel", wintypes.WORD),
            ("wProcessorRevision", wintypes.WORD),
        )

    info = _SystemInfo()
    windll.kernel32.GetNativeSystemInfo(ctypes.byref(info))
    code = int(info.wProcessorArchitecture)
    return code, _ARCHITECTURE_NAMES.get(code, f"unknown ({code})")


def describe_security(path: Path) -> str:
    """Return the owner and DACL of an existing path, as an SDDL string."""
    windll = _require_windows()
    descriptor = ctypes.c_void_p()
    information = _OWNER_SECURITY_INFORMATION | _DACL_SECURITY_INFORMATION
    status = windll.advapi32.GetNamedSecurityInfoW(
        ctypes.c_wchar_p(str(path)),
        _SE_FILE_OBJECT,
        information,
        None,
        None,
        None,
        None,
        ctypes.byref(descriptor),
    )
    if status != 0:
        raise PrivacyError(
            f"The permissions of this file could not be read (Windows error {status}).",
            code="CONFIG_PERMISSIONS",
        )
    with _LocalMemory(descriptor):
        text = ctypes.c_wchar_p()
        length = wintypes.DWORD()
        if not windll.advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            descriptor,
            _SDDL_REVISION_1,
            information,
            ctypes.byref(text),
            ctypes.byref(length),
        ):
            raise _last_error("Reading the permissions of this file")
        with _LocalMemory(text):
            return str(text.value or "")


def apply_private_dacl(path: Path, *, directory: bool) -> None:
    """Replace the path's DACL with one private to this account.

    The new DACL is protected, so a parent directory someone widened — a shared drive,
    a profile with inherited permissions — cannot grant access to this product's files.
    """
    windll = _require_windows()
    sddl = private_sddl(current_user_sid(), directory=directory)
    descriptor = ctypes.c_void_p()
    if not windll.advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        ctypes.c_wchar_p(sddl), _SDDL_REVISION_1, ctypes.byref(descriptor), None
    ):
        raise _last_error("Preparing the permissions for this file")
    with _LocalMemory(descriptor):
        present = wintypes.BOOL()
        acl = ctypes.c_void_p()
        defaulted = wintypes.BOOL()
        if not windll.advapi32.GetSecurityDescriptorDacl(
            descriptor, ctypes.byref(present), ctypes.byref(acl), ctypes.byref(defaulted)
        ):
            raise _last_error("Preparing the permissions for this file")
        status = windll.advapi32.SetNamedSecurityInfoW(
            ctypes.c_wchar_p(str(path)),
            _SE_FILE_OBJECT,
            _DACL_SECURITY_INFORMATION | _PROTECTED_DACL_SECURITY_INFORMATION,
            None,
            None,
            acl,
            None,
        )
        if status != 0:
            raise PrivacyError(
                f"The permissions of this file could not be set (Windows error {status}).",
                code="CONFIG_PERMISSIONS",
            )


def _is_reparse_point(path: Path) -> bool:
    """Whether the path is a symlink, junction or any other reparse point.

    Windows has no ``O_NOFOLLOW``. Refusing reparse points outright is how a managed
    directory is kept from being redirected somewhere this product does not control.
    """
    try:
        info = os.lstat(path)
    except OSError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _identity(info: os.stat_result) -> tuple[int, int]:
    return (info.st_dev, info.st_ino)


class WindowsLineReader(LineReader):
    """Read a child's pipe through a helper thread.

    ``select.select`` accepts only sockets on Windows, and a blocking read on a pipe
    cannot be interrupted, so the read happens on a daemon thread the deadline can walk
    away from. The child is terminated by the caller, which is what actually ends it.
    """

    #: One read. Small enough that the bounded queue below holds little, large enough
    #: that an ordinary handshake arrives in one or two reads.
    _CHUNK: ClassVar[int] = 16 * 1024

    def __init__(self, stream: IO[bytes], *, budget: int) -> None:
        super().__init__(stream, budget=budget)
        # Bounded on purpose. With an unbounded queue the reading thread runs ahead of
        # the consumer, so a child that floods its output has the whole flood in memory
        # before the budget in read_line ever gets to look at it. Here the thread blocks
        # once two chunks are waiting, and stops entirely once it has read one byte more
        # than the budget allows — enough for the consumer to detect the overrun.
        self._queue: queue.Queue[bytes | None] = queue.Queue(maxsize=2)
        self._allowance = budget + 1
        self._closed = threading.Event()
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        try:
            while not self._closed.is_set() and self._allowance > 0:
                try:
                    chunk = os.read(self._stream.fileno(), min(self._CHUNK, self._allowance))
                except (OSError, ValueError):
                    return
                if not chunk:
                    return
                self._allowance -= len(chunk)
                if not self._offer(chunk):
                    return
        finally:
            self._offer(None)

    def _offer(self, item: bytes | None) -> bool:
        """Hand one item to the consumer, giving up once the reader has been closed."""
        while not self._closed.is_set():
            try:
                self._queue.put(item, timeout=0.1)
            except queue.Full:
                continue
            return True
        return False

    def _receive(self, timeout: float) -> bytes | None:
        try:
            item = self._queue.get(timeout=min(timeout, 0.5))
        except queue.Empty:
            return None
        if item is None:
            return b""
        return item

    def close(self) -> None:
        self._closed.set()
        with contextlib.suppress(OSError, ValueError):
            self._stream.close()
        # Closing the pipe unblocks a thread waiting in os.read; draining unblocks one
        # waiting to hand over a chunk. Both are needed, or the thread outlives the probe.
        with contextlib.suppress(queue.Empty):
            while True:
                self._queue.get_nowait()
        self._thread.join(timeout=2.0)


class WindowsServices(PlatformServices):
    """Windows 11 x64 paths, permissions, session, credential store and processes."""

    name: ClassVar[str] = "windows"
    executable_suffix: ClassVar[str] = ".exe"
    #: Only the Windows Credential Manager. A file or null backend would put the Bridge
    #: password on disk in the clear, which is the one thing this must never do.
    approved_keyring_modules: ClassVar[frozenset[str]] = frozenset({"keyring.backends.Windows"})
    managed_environment_names: ClassVar[tuple[str, ...]] = (
        "APPDATA",
        # Set by the user when Codex keeps its profile elsewhere. Passed through, never
        # overwritten: the client and the assistant must agree on one profile.
        "CODEX_HOME",
        "COMSPEC",
        "HOMEDRIVE",
        "HOMEPATH",
        "LOCALAPPDATA",
        "NUMBER_OF_PROCESSORS",
        "PATH",
        "PATHEXT",
        "ProgramData",
        "ProgramFiles",
        "SystemDrive",
        "SystemRoot",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "windir",
    )
    #: What the client must pass through for the runtime to find its own profile, its
    #: Credential Manager entry and a temporary folder. Validated against the real
    #: client rather than assumed: a missing SystemRoot breaks Windows sockets.
    client_passthrough_environment: ClassVar[tuple[str, ...]] = (
        "APPDATA",
        "LOCALAPPDATA",
        "SystemRoot",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "windir",
    )
    #: A client needs its own profile and a working PATH; it gets the same minimal set,
    #: including CODEX_HOME so the assistant and the client agree on one profile.
    client_command_environment: ClassVar[tuple[str, ...]] = managed_environment_names
    path_flavour: ClassVar[type[PurePath]] = PureWindowsPath

    # -- known folders -----------------------------------------------------------

    def _product_root(self) -> Path:
        return known_folder() / PRODUCT_FOLDER

    def config_dir(self) -> Path:
        return self._product_root() / "config"

    def state_dir(self) -> Path:
        return self._product_root() / "state"

    def data_dir(self) -> Path:
        return self._product_root() / "data"

    def programs_dir(self) -> Path:
        """Where the installer puts the program, for this user only."""
        return known_folder() / "Programs" / PRODUCT_FOLDER

    # -- private storage ---------------------------------------------------------

    def ensure_private_directory(self, directory: Path) -> None:
        if _is_reparse_point(directory):
            raise PrivacyError(
                "This folder is a link to somewhere else, which Proton Safe will not use.",
                code="CONFIG_PERMISSIONS",
            )
        existed = directory.is_dir()
        directory.mkdir(parents=True, exist_ok=True)
        if not existed:
            # Only the leaf is tightened. Parent folders keep the permissions Windows
            # and the user chose for the profile.
            apply_private_dacl(directory, directory=True)
            return
        report = self._assess(directory)
        if report.private and not report.inherits:
            return
        if not report.owner_ok:
            # Writing a DACL here would not make the folder private: whoever owns it can
            # put the old one back, and this account may not even be able to set it.
            raise PrivacyError(
                f"This folder cannot be made private because {report.reason}.",
                code="CONFIG_PERMISSIONS",
            )
        # A folder that already blocks inheritance is not thereby private: a protected
        # DACL granting Everyone full access blocks inheritance too. It is rewritten
        # whenever it is not actually private, not only when it still inherits.
        apply_private_dacl(directory, directory=True)
        # And the result is read back, because a DACL can be reapplied by policy or by
        # another process between these two calls.
        self._require_private(directory)

    def verify_private_directory(self, directory: Path) -> None:
        if not directory.exists():
            raise PrivacyError("The folder does not exist.", code="CONFIG_MISSING")
        if _is_reparse_point(directory):
            raise PrivacyError(
                "This folder is a link to somewhere else, which Proton Safe will not use.",
                code="CONFIG_PERMISSIONS",
            )
        if not directory.is_dir():
            raise PrivacyError("The path is not a folder.", code="CONFIG_INVALID")
        self._require_private(directory)

    def _assess(self, path: Path) -> PrivacyReport:
        """What the path's owner and DACL actually establish about its privacy."""
        return assess_privacy(describe_security(path), user_sid=current_user_sid())

    def _require_private(self, path: Path) -> None:
        report = self._assess(path)
        if not report.private:
            raise PrivacyError(
                f"Proton Safe will not use this item because {report.reason}.",
                code="CONFIG_PERMISSIONS",
            )

    def directory_privacy(self, directory: Path) -> tuple[str, str]:
        shared = "must be accessible to this account only, not to other users of this computer"
        try:
            if not directory.exists():
                return "missing", ""
            if _is_reparse_point(directory):
                return "not_private", "must not be a link pointing somewhere else"
            if not directory.is_dir():
                return "not_private", shared
            sddl = describe_security(directory)
        except PrivacyError as exc:
            return "unreadable", str(exc)
        except OSError as exc:
            return "unreadable", f"could not inspect permissions ({type(exc).__name__})"
        report = assess_privacy(sddl, user_sid=current_user_sid())
        if not report.private:
            # Say which of the ways a folder can be exposed this one is, rather than one
            # sentence covering a foreign owner, a missing DACL and a shared folder alike.
            return "not_private", f"{shared} ({report.reason})"
        return "private", ""

    def read_private_file(self, path: Path, *, max_bytes: int) -> bytes:
        if _is_reparse_point(path):
            raise PrivacyError(
                "This file is a link to somewhere else, which Proton Safe will not read.",
                code="CONFIG_PERMISSIONS",
            )
        try:
            before = os.stat(path, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise PrivacyError("No file was found at that path.", code="CONFIG_MISSING") from exc
        except OSError as exc:
            raise PrivacyError(
                f"The file cannot be inspected ({type(exc).__name__}).", code="CONFIG_INVALID"
            ) from exc
        self._require_private(path)
        try:
            descriptor = os.open(path, os.O_RDONLY | _O_BINARY | _O_NOINHERIT)
        except FileNotFoundError as exc:
            raise PrivacyError("No file was found at that path.", code="CONFIG_MISSING") from exc
        except OSError as exc:
            raise PrivacyError(
                f"The file cannot be opened ({type(exc).__name__}).",
                code="CONFIG_PERMISSIONS" if isinstance(exc, PermissionError) else "CONFIG_INVALID",
            ) from exc
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise PrivacyError("The path is not a regular file.", code="CONFIG_INVALID")
            # The file inspected and the file opened must be the same one: this is what
            # Windows offers in place of O_NOFOLLOW against a swap between the two.
            if _identity(info) != _identity(before):
                raise PrivacyError(
                    "This file changed while it was being opened.", code="CONFIG_PERMISSIONS"
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
        temporary_path = directory / f".proton-safe-{_secrets.token_hex(8)}.tmp"
        try:
            self.create_private_file(temporary_path, data)
            os.replace(temporary_path, path)
        except BaseException:
            with contextlib.suppress(OSError):
                temporary_path.unlink(missing_ok=True)
            raise

    def create_private_file(self, path: Path, data: bytes = b"") -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_BINARY | _O_NOINHERIT
        # O_EXCL, so this call either created the file or failed: what follows is never
        # applied to a file that was already there.
        descriptor = os.open(path, flags, 0o600)
        failed = True
        try:
            # The DACL goes on before a single byte of content does. The parent folder's
            # permissions are not what protects this file: between creating it and
            # writing to it is exactly the window a widened parent would expose, and
            # what is exposed in the remaining gap is an empty file. Windows checks
            # permissions when a handle is opened, so the descriptor above stays usable.
            apply_private_dacl(path, directory=False)
            _write_all(descriptor, data)
            os.fsync(descriptor)
            failed = False
        finally:
            os.close(descriptor)
            if failed:
                # A file whose permissions could not be set is not left on disk.
                with contextlib.suppress(OSError):
                    path.unlink(missing_ok=True)

    def append_to_private_file(self, path: Path, data: bytes) -> None:
        if _is_reparse_point(path):
            raise PrivacyError(
                "This file is a link to somewhere else, which Proton Safe will not write to.",
                code="CONFIG_PERMISSIONS",
            )
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | _O_BINARY | _O_NOINHERIT)
        try:
            _write_all(descriptor, data)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def secure_existing_path(self, path: Path) -> None:
        if _is_reparse_point(path):
            raise PrivacyError("This item is a link to somewhere else.", code="CONFIG_PERMISSIONS")
        if path.is_dir():
            apply_private_dacl(path, directory=True)
        elif path.exists():
            apply_private_dacl(path, directory=False)

    def is_plain_file(self, path: Path) -> bool:
        try:
            return path.is_file() and not _is_reparse_point(path)
        except OSError:
            return False

    # -- session -----------------------------------------------------------------

    def session_facts(self) -> SessionFacts:
        return SessionFacts("Windows", is_elevated())

    def system_status(self) -> tuple[str, str]:
        version = getattr(sys, "getwindowsversion")()  # noqa: B009 - Windows only
        code, architecture = native_architecture()
        label = f"Windows {version.major} (build {version.build}) {architecture}"
        if code == _PROCESSOR_ARCHITECTURE_ARM64:
            # Proton Mail Bridge excludes ARM devices outside Apple silicon, so an ARM64
            # machine is refused even when it could emulate an x64 executable.
            return "fail", label
        if code != _PROCESSOR_ARCHITECTURE_AMD64 or version.build < MINIMUM_BUILD:
            return "fail", label
        return "pass", label

    # -- executables and processes -----------------------------------------------

    def is_executable_file(self, path: Path) -> bool:
        try:
            return path.is_file() and path.suffix.lower() in LAUNCHABLE_SUFFIXES
        except OSError:
            return False

    def spawn_options(self) -> dict[str, Any]:
        # No console window for an ordinary launch, and its own process group so a
        # console event aimed at the parent never reaches the child.
        return {"creationflags": _CREATE_NO_WINDOW | _CREATE_NEW_PROCESS_GROUP}

    def open_line_reader(self, stream: IO[bytes], *, budget: int) -> LineReader:
        return WindowsLineReader(stream, budget=budget)

    def try_lock(self, descriptor: int) -> bool:
        """``_locking``, which Windows drops when the handle closes with the process."""
        import msvcrt  # Windows only, so imported where it is used.

        # Read through getattr for the same reason as the open flags above: this module
        # is developed and type-checked on Linux, where these names do not exist.
        locking = getattr(msvcrt, "locking", None)
        non_blocking = getattr(msvcrt, "LK_NBLCK", None)
        if locking is None or non_blocking is None:  # pragma: no cover - platform guard
            return False
        try:
            locking(descriptor, non_blocking, 1)
        except OSError:
            return False
        return True

    # -- keyring -----------------------------------------------------------------

    def configure_keyring(self, backend: object) -> None:
        """Pin Credential Manager persistence to this computer.

        ``keyring`` 25.7 defaults to ``CRED_PERSIST_ENTERPRISE``, which asks Windows to
        roam the credential to the account's other computers. The policy here is
        narrower on purpose: the secret survives a sign-out and a restart on this
        machine, and is not offered for roaming elsewhere.
        """
        for candidate in _flatten_backends(backend):
            if type(candidate).__module__ == "keyring.backends.Windows":
                with contextlib.suppress(AttributeError, KeyError, ValueError):
                    candidate.persist = "local machine"  # type: ignore[attr-defined]

    def keyring_probe_targets(self, service: str, account: str) -> tuple[str, ...]:
        """Both entries Credential Manager may hold for one service and account.

        ``keyring`` writes under the service name, and under ``account@service`` when a
        second account collides with it. A self-test that cleaned up only the first
        would leave a stray entry behind.
        """
        return (service, f"{account}@{service}")


def _flatten_backends(backend: object) -> list[object]:
    nested = getattr(backend, "backends", None)
    if isinstance(nested, list | tuple):
        found: list[object] = []
        for item in nested:
            found.extend(_flatten_backends(item))
        return found
    return [backend]


def _write_all(descriptor: int, data: bytes) -> None:
    """Write every byte, including when the OS reports a short write."""
    remaining = memoryview(data)
    while remaining:
        written = os.write(descriptor, remaining)
        if written == 0:
            raise OSError("write returned zero bytes")
        remaining = remaining[written:]
