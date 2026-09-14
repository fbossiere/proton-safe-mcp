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
from functools import lru_cache
from pathlib import Path, PurePath, PureWindowsPath
from types import SimpleNamespace
from typing import IO, Any, ClassVar, Final

from .base import (
    LineReader,
    PlatformServices,
    PrivacyError,
    SessionFacts,
    UnsupportedPlatformError,
)
from .winacl import assess_privacy, private_descriptor, private_sddl

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


@lru_cache(maxsize=1)
def _require_windows() -> Any:
    """Bind pointer-width-correct Win32 signatures and preserve GetLastError."""
    loader = getattr(ctypes, "WinDLL", None)
    if loader is None:
        raise UnsupportedPlatformError("This operation needs Windows.", code="SYSTEM_UNSUPPORTED")
    api = SimpleNamespace(
        **{
            name: loader(name, use_last_error=True)
            for name in ("kernel32", "advapi32", "ole32", "shell32")
        }
    )
    pointer, dword, boolean = ctypes.c_void_p, wintypes.DWORD, wintypes.BOOL
    signatures: dict[str, dict[str, tuple[Any, list[Any]]]] = {
        "kernel32": {
            "GetCurrentProcess": (pointer, []),
            "CloseHandle": (boolean, [pointer]),
            "LocalFree": (pointer, [pointer]),
            "GetNativeSystemInfo": (None, [pointer]),
        },
        "advapi32": {
            "OpenProcessToken": (boolean, [pointer, dword, pointer]),
            "GetTokenInformation": (boolean, [pointer, dword, pointer, dword, pointer]),
            "ConvertSidToStringSidW": (boolean, [pointer, pointer]),
            "GetNamedSecurityInfoW": (
                dword,
                [wintypes.LPCWSTR, dword, dword, pointer, pointer, pointer, pointer, pointer],
            ),
            "SetNamedSecurityInfoW": (
                dword,
                [wintypes.LPCWSTR, dword, dword, pointer, pointer, pointer, pointer],
            ),
            "ConvertSecurityDescriptorToStringSecurityDescriptorW": (
                boolean,
                [pointer, dword, dword, pointer, pointer],
            ),
            "ConvertStringSecurityDescriptorToSecurityDescriptorW": (
                boolean,
                [wintypes.LPCWSTR, dword, pointer, pointer],
            ),
            "GetSecurityDescriptorDacl": (boolean, [pointer, pointer, pointer, pointer]),
            "GetSecurityDescriptorOwner": (boolean, [pointer, pointer, pointer]),
        },
        "ole32": {
            "IIDFromString": (ctypes.c_long, [wintypes.LPCWSTR, pointer]),
            "CoTaskMemFree": (None, [pointer]),
        },
        "shell32": {
            "SHGetKnownFolderPath": (ctypes.c_long, [pointer, dword, pointer, pointer]),
        },
    }
    for library, functions in signatures.items():
        for name, (result, arguments) in functions.items():
            function = getattr(getattr(api, library), name)
            function.restype = result
            function.argtypes = arguments
    return api


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
        raise _last_error("Reading this session's privileges")
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
            raise _last_error("Reading this session's privileges")
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
    user_sid = current_user_sid()
    sddl = f"O:{user_sid}" + private_sddl(user_sid, directory=directory)
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
        owner = ctypes.c_void_p()
        if not windll.advapi32.GetSecurityDescriptorOwner(
            descriptor, ctypes.byref(owner), ctypes.byref(defaulted)
        ):
            raise _last_error("Preparing file ownership")
        status = windll.advapi32.SetNamedSecurityInfoW(
            ctypes.c_wchar_p(str(path)),
            _SE_FILE_OBJECT,
            _OWNER_SECURITY_INFORMATION
            | _DACL_SECURITY_INFORMATION
            | _PROTECTED_DACL_SECURITY_INFORMATION,
            owner,
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

    _CHUNK: ClassVar[int] = 16 * 1024

    def __init__(self, stream: IO[bytes], *, budget: int) -> None:
        super().__init__(stream, budget=budget)
        self._queue: queue.Queue[bytes | None] = queue.Queue(maxsize=2)
        self._allowance = budget + 1
        self._closed = threading.Event()
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _put(self, item: bytes | None) -> bool:
        while not self._closed.is_set():
            try:
                self._queue.put(item, timeout=0.05)
                return True
            except queue.Full:
                continue
        return False

    def _pump(self) -> None:
        while self._allowance > 0 and not self._closed.is_set():
            try:
                chunk = os.read(self._stream.fileno(), min(self._CHUNK, self._allowance))
            except (OSError, ValueError):
                break
            if not chunk or not self._put(chunk):
                break
            self._allowance -= len(chunk)
        self._put(None)

    def _receive(self, timeout: float) -> bytes | None:
        try:
            item = self._queue.get(timeout=min(timeout, 0.5))
        except queue.Empty:
            return None
        return b"" if item is None else item

    def close(self) -> None:
        self._closed.set()
        # The caller terminates the child before closing its reader, so a blocked
        # native read has reached EOF. A full queue is interruptible via _closed.
        self._thread.join(timeout=1)
        with contextlib.suppress(OSError, ValueError):
            self._stream.close()


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
        if (
            existed
            and not assess_privacy(
                describe_security(directory), user_sid=current_user_sid()
            ).owner_ok
        ):
            raise PrivacyError("This folder belongs to another account.", code="CONFIG_PERMISSIONS")
        if not existed or not private_descriptor(
            describe_security(directory), current_user_sid(), directory=True
        ):
            apply_private_dacl(directory, directory=True)
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

    def _require_private(self, path: Path) -> None:
        sddl = describe_security(path)
        if not private_descriptor(sddl, current_user_sid(), directory=path.is_dir()):
            raise PrivacyError(
                "Other accounts on this computer can open this item.",
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
        if not private_descriptor(sddl, current_user_sid(), directory=True):
            return "not_private", shared
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
        self.verify_private_directory(path.parent)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_BINARY | _O_NOINHERIT
        descriptor = os.open(path, flags, 0o600)
        failed = True
        try:
            # The verified parent restricts inheritance from creation; seal the file
            # before any data is written, then verify Windows accepted the change.
            apply_private_dacl(path, directory=False)
            self._require_private(path)
            _write_all(descriptor, data)
            os.fsync(descriptor)
            failed = False
        finally:
            os.close(descriptor)
            if failed:
                with contextlib.suppress(OSError):
                    path.unlink(missing_ok=True)

    def append_to_private_file(self, path: Path, data: bytes) -> None:
        if _is_reparse_point(path):
            raise PrivacyError(
                "This file is a link to somewhere else, which Proton Safe will not write to.",
                code="CONFIG_PERMISSIONS",
            )
        self._require_private(path)
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
