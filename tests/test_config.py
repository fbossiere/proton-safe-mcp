from __future__ import annotations

import pytest

from proton_safe_mcp.config import Settings
from proton_safe_mcp.errors import ConfigurationError


def test_from_env_requires_user(monkeypatch, tmp_path):
    monkeypatch.delenv("PROTON_BRIDGE_USER", raising=False)
    monkeypatch.setenv("PROTON_MCP_STATE_DIR", str(tmp_path / "state"))
    with pytest.raises(ConfigurationError, match="PROTON_BRIDGE_USER"):
        Settings.from_env()


@pytest.mark.parametrize("user", ["user@example.com\r\nX: y", "user@example.com\nX"])
def test_from_env_rejects_header_injection_in_user(monkeypatch, tmp_path, user):
    monkeypatch.setenv("PROTON_BRIDGE_USER", user)
    monkeypatch.setenv("PROTON_MCP_STATE_DIR", str(tmp_path / "state"))
    with pytest.raises(ConfigurationError):
        Settings.from_env()


@pytest.mark.parametrize(
    "user",
    [
        "User <user@example.com>",
        "not-an-address",
        "user@exam..ple.com",
    ],
)
def test_from_env_rejects_a_non_bare_or_malformed_primary_sender(monkeypatch, tmp_path, user):
    monkeypatch.setenv("PROTON_BRIDGE_USER", user)
    monkeypatch.setenv("PROTON_MCP_STATE_DIR", str(tmp_path / "state"))

    with pytest.raises(ConfigurationError):
        Settings.from_env()


def test_bridge_host_is_loopback_and_not_configurable(monkeypatch, tmp_path):
    monkeypatch.setenv("PROTON_BRIDGE_USER", "user@example.com")
    monkeypatch.setenv("PROTON_MCP_STATE_DIR", str(tmp_path / "state"))
    # Even a hostile environment cannot redirect the Bridge connection.
    monkeypatch.setenv("PROTON_BRIDGE_HOST", "evil.example.com")
    settings = Settings.from_env()
    assert settings.bridge_host == "127.0.0.1"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("PROTON_IMAP_PORT", "not-a-number"),
        ("PROTON_IMAP_PORT", "0"),
        ("PROTON_IMAP_PORT", "70000"),
        ("PROTON_MCP_MAX_ATTACHMENT_BYTES", str(100 * 1024 * 1024)),
        ("PROTON_MCP_MAX_RECEIVED_ATTACHMENT_BYTES", str(100 * 1024 * 1024)),
    ],
)
def test_from_env_rejects_out_of_range_values(monkeypatch, tmp_path, name, value):
    monkeypatch.setenv("PROTON_BRIDGE_USER", "user@example.com")
    monkeypatch.setenv("PROTON_MCP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigurationError, match=name):
        Settings.from_env()


def test_received_attachment_extraction_limit_is_configurable(monkeypatch, tmp_path):
    monkeypatch.setenv("PROTON_BRIDGE_USER", "user@example.com")
    monkeypatch.setenv("PROTON_MCP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("PROTON_MCP_MAX_RECEIVED_ATTACHMENT_BYTES", "123456")

    settings = Settings.from_env()

    assert settings.max_received_attachment_bytes == 123456


def test_state_directories_are_private(monkeypatch, tmp_path):
    monkeypatch.setenv("PROTON_BRIDGE_USER", "user@example.com")
    monkeypatch.setenv("PROTON_MCP_STATE_DIR", str(tmp_path / "state"))
    settings = Settings.from_env()
    for directory in (settings.state_dir, settings.uploads_dir):
        assert directory.is_dir()
        assert directory.stat().st_mode & 0o777 == 0o700


def test_sender_aliases_are_allowlisted_primary_first(monkeypatch, tmp_path):
    monkeypatch.setenv("PROTON_BRIDGE_USER", "user@example.com")
    monkeypatch.setenv("PROTON_MCP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(
        "PROTON_BRIDGE_ALIASES",
        " billing@example.com , USER@example.com ,, legal@example.com ",
    )

    settings = Settings.from_env()

    # The primary address stays first and is never duplicated by a differently cased alias.
    assert settings.sender_addresses == (
        "user@example.com",
        "billing@example.com",
        "legal@example.com",
    )
    assert settings.default_sender == "user@example.com"


def test_sender_addresses_default_to_the_primary_address_alone(monkeypatch, tmp_path):
    monkeypatch.setenv("PROTON_BRIDGE_USER", "user@example.com")
    monkeypatch.setenv("PROTON_MCP_STATE_DIR", str(tmp_path / "state"))

    assert Settings.from_env().sender_addresses == ("user@example.com",)


@pytest.mark.parametrize(
    "aliases",
    [
        "Billing <billing@example.com>",
        "billing@example.com\r\nBcc: attacker@example.com",
        "not-an-address",
        "billing@example.com, attacker@exam..ple.com",
        ",".join(f"alias{index}@example.com" for index in range(25)),
    ],
)
def test_malformed_sender_aliases_stop_the_server(monkeypatch, tmp_path, aliases):
    monkeypatch.setenv("PROTON_BRIDGE_USER", "user@example.com")
    monkeypatch.setenv("PROTON_MCP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("PROTON_BRIDGE_ALIASES", aliases)

    with pytest.raises(ConfigurationError):
        Settings.from_env()
