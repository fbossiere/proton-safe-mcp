from __future__ import annotations

import pytest

from proton_safe_mcp import secrets as secrets_module
from proton_safe_mcp.errors import ConfigurationError


@pytest.fixture(autouse=True)
def fake_keyring(monkeypatch):
    vault: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(
        secrets_module.keyring,
        "set_password",
        lambda svc, usr, pwd: vault.__setitem__((svc, usr), pwd),
    )
    monkeypatch.setattr(
        secrets_module.keyring, "get_password", lambda svc, usr: vault.get((svc, usr))
    )
    monkeypatch.delenv("PROTON_BRIDGE_PASSWORD", raising=False)
    return vault


def test_store_and_retrieve_round_trip():
    secrets_module.store_bridge_password("user@example.com", "bridge-generated")
    assert secrets_module.get_bridge_password("user@example.com") == "bridge-generated"


def test_empty_password_is_rejected():
    with pytest.raises(ConfigurationError, match="empty"):
        secrets_module.store_bridge_password("user@example.com", "")


def test_missing_password_raises_actionable_error():
    with pytest.raises(ConfigurationError, match="setup"):
        secrets_module.get_bridge_password("user@example.com")


def test_environment_fallback_takes_precedence(monkeypatch):
    secrets_module.store_bridge_password("user@example.com", "keyring-value")
    monkeypatch.setenv("PROTON_BRIDGE_PASSWORD", "env-value")
    assert secrets_module.get_bridge_password("user@example.com") == "env-value"
