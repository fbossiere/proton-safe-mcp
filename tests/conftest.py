from __future__ import annotations

import sys
from pathlib import Path

import keyring
import keyring.backend
import keyring.backends.fail
import keyring.errors
import pytest

from proton_safe_mcp.config import Settings
from proton_safe_mcp.platform_services import use_services
from proton_safe_mcp.platform_services import windows as windows_services
from proton_safe_mcp.platform_services.winacl import private_sddl
from proton_safe_mcp.platform_services.windows import WindowsServices

#: A plausible account SID for a fixture. It belongs to nobody.
FIXTURE_USER_SID = "S-1-5-21-1004336348-1177238915-682003330-1001"


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "posix_only: the subject of the test is a Unix guarantee — a mode, a uid or a "
        "symlink — that Windows does not have. The Windows equivalent is covered by "
        "tests/test_platform_services.py and tests/test_windows_behaviour.py.",
    )


def pytest_collection_modifyitems(config, items):
    if sys.platform != "win32":
        return
    skip = pytest.mark.skip(reason="this test's subject is a Unix-only guarantee")
    for item in items:
        if "posix_only" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def make_executable():
    """Create a stand-in executable the running platform will agree to launch.

    The name carries the platform's suffix, so a test that needs a discoverable client
    or runtime works on both systems instead of quietly finding nothing on Windows.
    """
    from proton_safe_mcp.platform_services import services

    def create(directory: Path, stem: str) -> Path:
        path = Path(directory) / services().executable_name(stem)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"MZ" if services().name == "windows" else b"#!/bin/sh\n")
        path.chmod(0o700)
        return path

    return create


@pytest.fixture
def as_windows(monkeypatch, tmp_path):
    """Run the block against the Windows services, with only the Win32 calls stubbed.

    Everything this product decides — where files go, what may be launched, what a
    child inherits, which credential entries a self-test owns — is ordinary Python and
    runs here. Only the four calls that ask Windows itself for a folder, an identity or
    a security descriptor are replaced, because this machine has none of them.
    """
    private = f"O:{FIXTURE_USER_SID}" + private_sddl(FIXTURE_USER_SID, directory=True)
    monkeypatch.setattr(windows_services, "current_user_sid", lambda: FIXTURE_USER_SID)
    monkeypatch.setattr(windows_services, "is_elevated", lambda: False)
    monkeypatch.setattr(windows_services, "known_folder", lambda *_a, **_k: tmp_path / "AppData")
    monkeypatch.setattr(windows_services, "apply_private_dacl", lambda *_a, **_k: None)
    monkeypatch.setattr(windows_services, "describe_security", lambda _path: private)
    monkeypatch.setattr(windows_services, "_is_reparse_point", lambda _path: False)
    platform = WindowsServices()
    with use_services(platform):
        yield platform


@pytest.fixture
def windows_executable(as_windows, tmp_path):
    """Create a file Windows services will agree to launch."""

    def create(path: str | Path) -> Path:
        created = Path(path)
        created.parent.mkdir(parents=True, exist_ok=True)
        created.write_bytes(b"MZ")
        return created

    return create


@pytest.fixture(autouse=True)
def _no_inherited_aliases(monkeypatch):
    """Keep the sender allowlist under test control, whatever the developer's shell exports."""
    monkeypatch.delenv("PROTON_BRIDGE_ALIASES", raising=False)


@pytest.fixture
def settings(tmp_path):
    value = Settings(
        bridge_user="user@example.com",
        sender_addresses=("user@example.com", "alias@example.com"),
        bridge_host="127.0.0.1",
        imap_port=1143,
        state_dir=tmp_path / "state",
        max_attachment_bytes=2 * 1024 * 1024,
        max_received_attachment_bytes=1024 * 1024,
        max_chunk_bytes=1024,
        upload_ttl_seconds=1800,
        max_body_chars=100_000,
    )
    value.ensure_directories()
    return value


class _InMemoryKeyring(keyring.backend.KeyringBackend):
    """An approved-looking backend that keeps secrets in memory for the test run.

    Its module is reported as the Secret Service one so the managed-mode policy sees an
    approved backend; the policy itself is what these tests exercise.
    """

    priority = 10  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}
        self.locked = False

    def get_password(self, service: str, username: str) -> str | None:
        if self.locked:
            raise keyring.errors.KeyringLocked("locked")
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        if self.locked:
            raise keyring.errors.KeyringLocked("locked")
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if self.store.pop((service, username), None) is None:
            raise keyring.errors.PasswordDeleteError("absent")


_InMemoryKeyring.__module__ = (
    "keyring.backends.Windows" if sys.platform == "win32" else "keyring.backends.SecretService"
)


@pytest.fixture
def fake_keyring(monkeypatch):
    """Install an approved in-memory keyring and clear any environment credential."""
    monkeypatch.delenv("PROTON_BRIDGE_PASSWORD", raising=False)
    backend = _InMemoryKeyring()
    monkeypatch.setattr(keyring, "get_keyring", lambda: backend)
    monkeypatch.setattr(keyring, "set_password", backend.set_password)
    monkeypatch.setattr(keyring, "get_password", backend.get_password)
    monkeypatch.setattr(keyring, "delete_password", backend.delete_password)
    return backend


@pytest.fixture
def unavailable_keyring(monkeypatch):
    """Install the backend keyring falls back to when no Secret Service is reachable."""
    backend = keyring.backends.fail.Keyring()
    monkeypatch.setattr(keyring, "get_keyring", lambda: backend)

    def refuse(*_args, **_kwargs):
        raise keyring.errors.NoKeyringError("no backend")

    monkeypatch.setattr(keyring, "get_password", refuse)
    monkeypatch.setattr(keyring, "set_password", refuse)
    return backend


@pytest.fixture
def managed_config_path(tmp_path):
    """An absolute path inside a private directory, as the assistant would create."""
    directory = tmp_path / "config" / "proton-safe-mcp"
    from proton_safe_mcp.platform_services import services

    services().ensure_private_directory(directory)
    return directory / "config.toml"


@pytest.fixture
def write_managed_config():
    """Write a valid managed configuration with the permissions the loader requires."""
    from proton_safe_mcp.configuration_store import StoredConfiguration
    from proton_safe_mcp.configuration_store import write as write_configuration

    def write(path, *, user="person@example.com", port=1143, aliases=()):
        write_configuration(
            StoredConfiguration(bridge_user=user, imap_port=port, aliases=tuple(aliases)), path
        )
        return path

    return write
