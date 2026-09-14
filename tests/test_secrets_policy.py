"""The credential policy: where a managed setup may and may not keep the Bridge password."""

from __future__ import annotations

from typing import ClassVar

import keyring
import keyring.errors
import pytest

from proton_safe_mcp import secrets as secrets_module
from proton_safe_mcp.errors import KeyringError

SERVICE = secrets_module.SERVICE_NAME
ACCOUNT = "person@example.com"


def test_an_approved_backend_is_usable_for_a_managed_setup(fake_keyring):
    status = secrets_module.keyring_status()

    assert status.state == "available"
    assert status.code == "KEYRING_AVAILABLE"
    assert status.usable_for_managed_setup
    assert type(fake_keyring).__module__ in status.backend


def test_a_locked_keyring_is_told_apart_from_a_missing_one(fake_keyring):
    fake_keyring.locked = True

    status = secrets_module.keyring_status()

    assert status.state == "locked"
    assert status.code == "KEYRING_LOCKED"
    assert not status.usable_for_managed_setup


def test_an_unapproved_backend_is_refused_even_when_it_works(monkeypatch):
    """A backend that stores secrets in the clear must never become the fallback."""

    class PlaintextKeyring(keyring.backend.KeyringBackend):
        priority = 1  # type: ignore[assignment]

        def get_password(self, service, username):
            return "stored-in-the-clear"

        def set_password(self, service, username, password):
            return None

        def delete_password(self, service, username):
            return None

    PlaintextKeyring.__module__ = "keyrings.alt.file"
    backend = PlaintextKeyring()
    monkeypatch.setattr(keyring, "get_keyring", lambda: backend)

    status = secrets_module.keyring_status()

    assert status.state == "unapproved"
    assert status.code == "KEYRING_UNAVAILABLE"
    with pytest.raises(KeyringError) as caught:
        secrets_module.require_managed_keyring()
    assert caught.value.code == "KEYRING_UNAVAILABLE"


def test_a_chainer_containing_the_approved_backend_is_accepted(monkeypatch, fake_keyring):
    class Chainer:
        backends: ClassVar[list[object]] = [fake_keyring]

    Chainer.__module__ = "keyring.backends.chainer"
    monkeypatch.setattr(keyring, "get_keyring", lambda: Chainer())

    assert secrets_module.keyring_status().state == "available"


def test_an_unreachable_keyring_is_reported_rather_than_raised(unavailable_keyring):
    status = secrets_module.keyring_status()

    assert status.state in {"unapproved", "unavailable"}
    assert not status.usable_for_managed_setup


def test_the_round_trip_probe_writes_a_random_value_and_removes_it(fake_keyring):
    status = secrets_module.verify_keyring_round_trip()

    assert status.usable_for_managed_setup
    # Nothing is left behind, and the account's own entry was never touched.
    assert fake_keyring.store == {}


def test_the_round_trip_probe_never_touches_another_entry(fake_keyring):
    fake_keyring.set_password(SERVICE, ACCOUNT, "bridge-secret")
    fake_keyring.set_password("some-other-service", "someone", "unrelated")

    secrets_module.verify_keyring_round_trip()

    assert fake_keyring.store[(SERVICE, ACCOUNT)] == "bridge-secret"
    assert fake_keyring.store[("some-other-service", "someone")] == "unrelated"
    assert (SERVICE, secrets_module.PROBE_KEY) not in fake_keyring.store


def test_the_round_trip_probe_reports_a_backend_that_does_not_store_what_it_was_given(
    fake_keyring, monkeypatch
):
    monkeypatch.setattr(keyring, "get_password", lambda _service, _user: "something-else")

    status = secrets_module.verify_keyring_round_trip()

    assert not status.usable_for_managed_setup


def test_the_round_trip_probe_reports_a_keyring_that_locks_mid_write(fake_keyring, monkeypatch):
    def lock(*_args, **_kwargs):
        raise keyring.errors.KeyringLocked("locked")

    monkeypatch.setattr(keyring, "set_password", lock)

    assert secrets_module.verify_keyring_round_trip().code == "KEYRING_LOCKED"


def test_the_round_trip_probe_is_skipped_when_the_backend_is_not_approved(unavailable_keyring):
    status = secrets_module.verify_keyring_round_trip()

    assert not status.usable_for_managed_setup


def test_reading_a_credential_never_raises_on_a_broken_keyring(monkeypatch):
    def fail(*_args, **_kwargs):
        raise keyring.errors.KeyringError("private detail")

    monkeypatch.setattr(keyring, "get_password", fail)

    assert secrets_module.read_bridge_password(ACCOUNT) is None
    assert secrets_module.has_bridge_password(ACCOUNT) is False


def test_storing_an_empty_credential_is_refused(fake_keyring):
    from proton_safe_mcp.errors import ConfigurationError

    with pytest.raises(ConfigurationError):
        secrets_module.store_bridge_password(ACCOUNT, "")
    assert fake_keyring.store == {}


def test_deleting_an_absent_credential_reports_false_rather_than_failing(fake_keyring):
    assert secrets_module.delete_bridge_password(ACCOUNT) is False

    fake_keyring.set_password(SERVICE, ACCOUNT, "bridge-secret")
    assert secrets_module.delete_bridge_password(ACCOUNT) is True
    assert fake_keyring.store == {}


def test_the_secret_service_backend_ships_with_this_installation():
    """A packaged build that lost the dynamic backend must be detectable."""
    assert secrets_module.secret_service_backend_available() is True


@pytest.mark.posix_only
def test_a_missing_secret_service_module_is_detected(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name in {"secretstorage", "keyring.backends.SecretService"}:
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)

    assert secrets_module.secret_service_backend_available() is False


@pytest.mark.posix_only
def test_a_too_old_secretstorage_is_refused(monkeypatch):
    import secretstorage

    monkeypatch.setattr(secretstorage, "__version_tuple__", (3, 1), raising=False)

    assert secrets_module.secret_service_backend_available() is False


def test_require_managed_keyring_returns_the_status_when_it_is_usable(fake_keyring):
    assert secrets_module.require_managed_keyring().state == "available"
