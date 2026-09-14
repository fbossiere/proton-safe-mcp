"""Bridge credential access. The Proton account password is never used here."""

from __future__ import annotations

import base64
import contextlib
import os
from dataclasses import dataclass
from typing import Final, Literal

import keyring
import keyring.backend
import keyring.errors

from .errors import ConfigurationError, KeyringError
from .platform_services import services

SERVICE_NAME = "proton-safe-mcp"

# The self-test never touches the service that holds the real credential. On Windows,
# writing under the same service name would make Credential Manager move an existing
# entry to a compound target to resolve the account collision — a real credential
# displaced by a diagnostic. A separate service cannot do that on either platform.
PROBE_SERVICE_NAME: Final = f"{SERVICE_NAME}-selftest"

# Written and removed by the assistant's own keyring self-test. It is never a credential.
PROBE_KEY: Final = "assistant-keyring-probe"


def approved_backend_modules() -> frozenset[str]:
    """The credential stores this platform's managed setup accepts.

    A backend that keeps secrets in a plain file, or none at all, is refused rather than
    silently used: falling back to a file, the environment or a client's JSON would
    defeat the whole point.
    """
    return services().approved_keyring_modules


KeyringState = Literal["available", "locked", "unavailable", "unapproved"]


@dataclass(frozen=True, slots=True)
class KeyringStatus:
    state: KeyringState
    code: str
    backend: str

    @property
    def usable_for_managed_setup(self) -> bool:
        return self.state == "available"


def _configured_backend() -> object:
    """Resolve the keyring and apply this platform's storage policy before any write.

    On Windows this is what pins Credential Manager persistence to this computer
    instead of the library default, which asks for the credential to roam.
    """
    backend = keyring.get_keyring()
    services().configure_keyring(backend)
    return backend


def store_bridge_password(user: str, password: str) -> None:
    if not password:
        raise ConfigurationError("The Bridge password cannot be empty")
    _configured_backend()
    keyring.set_password(SERVICE_NAME, user, password)


def delete_bridge_password(user: str) -> bool:
    """Remove this account's stored Bridge credential. Nothing else is touched."""
    try:
        keyring.delete_password(SERVICE_NAME, user)
    except keyring.errors.PasswordDeleteError:
        return False
    return True


def read_bridge_password(user: str) -> str | None:
    """Return the stored credential, or None. The value stays in memory only.

    The assistant uses it to restore a working credential when a later step fails; it is
    never written to disk, passed to a subprocess or included in a report.
    """
    try:
        return keyring.get_password(SERVICE_NAME, user)
    except keyring.errors.KeyringError:
        return None


def has_bridge_password(user: str) -> bool:
    """Report whether a credential exists, without ever returning or logging its value."""
    return read_bridge_password(user) is not None


def get_bridge_password(user: str, *, allow_environment: bool = True) -> str:
    """Return the Bridge credential.

    ``allow_environment`` keeps the historic ``PROTON_BRIDGE_PASSWORD`` fallback, which is
    useful for isolated containers. The managed setup passes ``False``: it uses the keyring
    and nothing else, so a stray variable can neither substitute for nor shadow it.
    """
    password = (
        os.environ.get("PROTON_BRIDGE_PASSWORD") if allow_environment else None
    ) or keyring.get_password(SERVICE_NAME, user)
    if not password:
        raise ConfigurationError(
            "No Proton Bridge password found. Run `proton-safe-mcp setup` first.",
            code="CREDENTIAL_MISSING",
        )
    return password


def approved_backend_available() -> bool:
    """Whether this installation actually ships a usable approved backend.

    A packaged build resolves keyring backends dynamically, so a missing module would
    otherwise look exactly like a session with no credential store. Telling the two
    apart is what makes a packaging defect visible instead of blamed on the user.
    """
    if services().name == "windows":
        try:
            import keyring.backends.Windows as windows_backend
        except ImportError:
            return False
        # The backend imports on any platform but records why it cannot work; an empty
        # trap is the only proof that its Credential Manager bindings really shipped.
        return not getattr(windows_backend, "missing_deps", True)
    try:
        import keyring.backends.SecretService  # noqa: F401
        import secretstorage
    except ImportError:
        return False
    return getattr(secretstorage, "__version_tuple__", (0,)) >= (3, 2)


def secret_service_backend_available() -> bool:
    """Backwards-compatible name for the Linux packaging check."""
    return approved_backend_available()


def _backend_modules(backend: object) -> list[str]:
    """Flatten a backend, or a chainer of backends, into their defining module names."""
    nested = getattr(backend, "backends", None)
    if isinstance(nested, list | tuple):
        modules: list[str] = []
        for item in nested:
            modules.extend(_backend_modules(item))
        return modules
    return [type(backend).__module__]


def backend_name(backend: object | None = None) -> str:
    resolved = keyring.get_keyring() if backend is None else backend
    return f"{type(resolved).__module__}.{type(resolved).__name__}"


def keyring_status() -> KeyringStatus:
    """Classify the session keyring for the managed setup, without writing anything.

    ``locked`` and ``unavailable`` are distinguished because the first is something the
    user can fix with the system dialog and the second is not.
    """
    backend = _configured_backend()
    name = backend_name(backend)
    modules = _backend_modules(backend)
    if not any(module in approved_backend_modules() for module in modules):
        return KeyringStatus("unapproved", "KEYRING_UNAVAILABLE", name)
    try:
        # A read against the self-test service: it can neither return nor disturb the
        # real credential, whichever platform resolves the lookup.
        keyring.get_password(PROBE_SERVICE_NAME, PROBE_KEY)
    except keyring.errors.KeyringLocked:
        return KeyringStatus("locked", "KEYRING_LOCKED", name)
    except keyring.errors.KeyringError:
        return KeyringStatus("unavailable", "KEYRING_UNAVAILABLE", name)
    return KeyringStatus("available", "KEYRING_AVAILABLE", name)


def verify_keyring_round_trip() -> KeyringStatus:
    """Write, read back and delete one random, non-sensitive value of our own.

    It uses a separate self-test service and a fresh account key each time, so no real
    credential can be overwritten, displaced, duplicated or left behind by a diagnosis.
    Every entry the store may have created for that key is removed afterwards.
    """
    current = keyring_status()
    if not current.usable_for_managed_setup:
        return current
    account = f"{PROBE_KEY}-{base64.urlsafe_b64encode(os.urandom(9)).decode('ascii')}"
    token = base64.urlsafe_b64encode(os.urandom(18)).decode("ascii")
    try:
        keyring.set_password(PROBE_SERVICE_NAME, account, token)
        read_back = keyring.get_password(PROBE_SERVICE_NAME, account)
    except keyring.errors.KeyringLocked:
        return KeyringStatus("locked", "KEYRING_LOCKED", current.backend)
    except keyring.errors.KeyringError:
        return KeyringStatus("unavailable", "KEYRING_UNAVAILABLE", current.backend)
    finally:
        _remove_probe_entries(account)
    if read_back != token:
        return KeyringStatus("unavailable", "KEYRING_UNAVAILABLE", current.backend)
    return current


def _remove_probe_entries(account: str) -> None:
    """Delete every entry the store may have written for one self-test account.

    Credential Manager can hold a secondary, compound entry alongside the primary one;
    the platform layer names both so neither is left behind.
    """
    with contextlib.suppress(keyring.errors.KeyringError):
        keyring.delete_password(PROBE_SERVICE_NAME, account)
    for target in services().keyring_probe_targets(PROBE_SERVICE_NAME, account):
        if target == PROBE_SERVICE_NAME:
            continue
        with contextlib.suppress(keyring.errors.KeyringError):
            keyring.delete_password(target, account)


def require_managed_keyring() -> KeyringStatus:
    """Raise a coded error unless the keyring may hold the managed credential."""
    status = keyring_status()
    if not status.usable_for_managed_setup:
        raise KeyringError(
            "The session keyring cannot be used to store the Bridge credential.",
            code=status.code,
        )
    return status
