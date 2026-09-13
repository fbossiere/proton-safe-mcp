from __future__ import annotations

import keyring
import keyring.backend
import keyring.backends.fail
import keyring.errors
import pytest

from proton_safe_mcp.config import Settings


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


_InMemoryKeyring.__module__ = "keyring.backends.SecretService"


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
    directory.mkdir(mode=0o700, parents=True)
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
