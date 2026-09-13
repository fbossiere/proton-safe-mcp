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

SERVICE_NAME = "proton-safe-mcp"

# The managed setup stores the credential where the session keyring protects it. A backend
# that keeps secrets in a plain file, or none at all, is refused rather than silently used:
# falling back to a file, the environment or a client's JSON would defeat the whole point.
APPROVED_BACKEND_MODULES: Final = frozenset({"keyring.backends.SecretService"})

# Written and removed by the assistant's own keyring self-test. It is never a credential.
PROBE_KEY: Final = "assistant-keyring-probe"

KeyringState = Literal["available", "locked", "unavailable", "unapproved"]


@dataclass(frozen=True, slots=True)
class KeyringStatus:
    state: KeyringState
    code: str
    backend: str

    @property
    def usable_for_managed_setup(self) -> bool:
        return self.state == "available"


def store_bridge_password(user: str, password: str) -> None:
    if not password:
        raise ConfigurationError("The Bridge password cannot be empty")
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


def secret_service_backend_available() -> bool:
    """Whether this installation actually ships a usable Secret Service backend.

    A packaged build resolves keyring backends dynamically, so a missing module would
    otherwise look exactly like a session with no keyring daemon. Telling the two apart
    is what makes a packaging defect visible instead of blamed on the user's session.
    """
    try:
        import keyring.backends.SecretService  # noqa: F401
        import secretstorage
    except ImportError:
        return False
    return getattr(secretstorage, "__version_tuple__", (0,)) >= (3, 2)


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
    backend = keyring.get_keyring()
    name = backend_name(backend)
    modules = _backend_modules(backend)
    if not any(module in APPROVED_BACKEND_MODULES for module in modules):
        return KeyringStatus("unapproved", "KEYRING_UNAVAILABLE", name)
    try:
        keyring.get_password(SERVICE_NAME, PROBE_KEY)
    except keyring.errors.KeyringLocked:
        return KeyringStatus("locked", "KEYRING_LOCKED", name)
    except keyring.errors.KeyringError:
        return KeyringStatus("unavailable", "KEYRING_UNAVAILABLE", name)
    return KeyringStatus("available", "KEYRING_AVAILABLE", name)


def verify_keyring_round_trip() -> KeyringStatus:
    """Write, read back and delete one random, non-sensitive value under the probe key.

    No other keyring entry is read or modified.
    """
    current = keyring_status()
    if not current.usable_for_managed_setup:
        return current
    token = base64.urlsafe_b64encode(os.urandom(18)).decode("ascii")
    try:
        keyring.set_password(SERVICE_NAME, PROBE_KEY, token)
        read_back = keyring.get_password(SERVICE_NAME, PROBE_KEY)
    except keyring.errors.KeyringLocked:
        return KeyringStatus("locked", "KEYRING_LOCKED", current.backend)
    except keyring.errors.KeyringError:
        return KeyringStatus("unavailable", "KEYRING_UNAVAILABLE", current.backend)
    finally:
        with contextlib.suppress(keyring.errors.KeyringError):
            keyring.delete_password(SERVICE_NAME, PROBE_KEY)
    if read_back != token:
        return KeyringStatus("unavailable", "KEYRING_UNAVAILABLE", current.backend)
    return current


def require_managed_keyring() -> KeyringStatus:
    """Raise a coded error unless the keyring may hold the managed credential."""
    status = keyring_status()
    if not status.usable_for_managed_setup:
        raise KeyringError(
            "The session keyring cannot be used to store the Bridge credential.",
            code=status.code,
        )
    return status
