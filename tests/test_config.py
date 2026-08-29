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
    ],
)
def test_from_env_rejects_out_of_range_values(monkeypatch, tmp_path, name, value):
    monkeypatch.setenv("PROTON_BRIDGE_USER", "user@example.com")
    monkeypatch.setenv("PROTON_MCP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigurationError, match=name):
        Settings.from_env()


def test_state_directories_are_private(monkeypatch, tmp_path):
    monkeypatch.setenv("PROTON_BRIDGE_USER", "user@example.com")
    monkeypatch.setenv("PROTON_MCP_STATE_DIR", str(tmp_path / "state"))
    settings = Settings.from_env()
    for directory in (settings.state_dir, settings.uploads_dir, settings.approvals_dir):
        assert directory.is_dir()
        assert directory.stat().st_mode & 0o777 == 0o700
