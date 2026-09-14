"""A01, A02, A03, A09 and A17: the two configuration modes never mix."""

from __future__ import annotations

import importlib
import json
import sys
import types

import pytest

from proton_safe_mcp import cli
from proton_safe_mcp.config import Settings
from proton_safe_mcp.errors import ConfigurationError
from proton_safe_mcp.secrets import get_bridge_password


@pytest.fixture(autouse=True)
def _no_pinned_settings():
    """Each test starts with the server unpinned, as a fresh process would."""
    from proton_safe_mcp import config

    config.set_startup_settings(None)
    yield
    config.set_startup_settings(None)


# -- A01: the historic mode is untouched ----------------------------------------


@pytest.mark.posix_only
def test_a01_historic_mode_never_reads_the_managed_file(
    monkeypatch, tmp_path, write_managed_config, managed_config_path
):
    write_managed_config(managed_config_path, user="managed@example.com", port=1199)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(managed_config_path.parent.parent))
    monkeypatch.setenv("PROTON_BRIDGE_USER", "historic@example.com")
    monkeypatch.setenv("PROTON_MCP_STATE_DIR", str(tmp_path / "state"))

    settings = Settings.from_env()

    assert settings.bridge_user == "historic@example.com"
    assert settings.imap_port == 1143
    assert settings.config_source == "environment"
    assert settings.allow_environment_secret is True


def test_a01_historic_doctor_output_is_unchanged(settings, monkeypatch, capsys):
    from proton_safe_mcp import doctor

    monkeypatch.setenv("PROTON_BRIDGE_USER", settings.bridge_user)
    monkeypatch.setenv("PROTON_MCP_STATE_DIR", str(settings.state_dir))
    monkeypatch.setattr(doctor.platform, "system", lambda: "Linux")
    monkeypatch.setattr(doctor, "get_bridge_password", lambda _user, **_kwargs: "not-printed")
    monkeypatch.setattr(doctor.ProtonBridgeClient, "probe", lambda _self: None)

    assert cli.main(["doctor"]) == 0
    output = capsys.readouterr().out

    # The keyring backend line belongs to the managed report only.
    assert "Keyring" not in output
    assert "from environment variables" in output
    assert "All checks passed" in output


# -- A02: an explicit file wins over a contradictory environment ------------------


@pytest.mark.posix_only
def test_a02_managed_mode_ignores_every_contradictory_proton_variable(
    monkeypatch, tmp_path, write_managed_config, managed_config_path
):
    write_managed_config(
        managed_config_path,
        user="managed@example.com",
        port=1144,
        aliases=("billing@example.com",),
    )
    monkeypatch.setenv("PROTON_BRIDGE_USER", "attacker@evil.example")
    monkeypatch.setenv("PROTON_BRIDGE_ALIASES", "attacker-alias@evil.example")
    monkeypatch.setenv("PROTON_IMAP_PORT", "9999")
    monkeypatch.setenv("PROTON_MCP_MAX_BODY_CHARS", "123")
    monkeypatch.setenv("PROTON_MCP_STATE_DIR", str(tmp_path / "hijacked"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    settings = Settings.from_config_file(managed_config_path)

    assert settings.bridge_user == "managed@example.com"
    assert settings.sender_addresses == ("managed@example.com", "billing@example.com")
    assert settings.imap_port == 1144
    assert settings.max_body_chars == 100_000
    assert settings.bridge_host == "127.0.0.1"
    assert (tmp_path / "hijacked") not in settings.state_dir.parents
    assert settings.state_dir == (tmp_path / "state" / "proton-safe-mcp").resolve()


def test_a02_the_bridge_host_stays_loopback_in_managed_mode(
    monkeypatch, write_managed_config, managed_config_path
):
    monkeypatch.setenv("PROTON_BRIDGE_HOST", "evil.example.com")
    write_managed_config(managed_config_path)

    assert Settings.from_config_file(managed_config_path).bridge_host == "127.0.0.1"


# -- A03: no environment credential fallback in managed mode ---------------------


def test_a03_managed_mode_refuses_an_environment_only_credential(
    monkeypatch, fake_keyring, write_managed_config, managed_config_path
):
    monkeypatch.setenv("PROTON_BRIDGE_PASSWORD", "from-the-environment")
    settings = Settings.from_config_file(
        managed_config_path := write_managed_config(managed_config_path), create_directories=False
    )

    assert settings.allow_environment_secret is False
    with pytest.raises(ConfigurationError) as caught:
        get_bridge_password(settings.bridge_user, allow_environment=False)
    assert caught.value.code == "CREDENTIAL_MISSING"
    assert fake_keyring.store == {}


def test_a03_the_historic_mode_keeps_its_environment_fallback(monkeypatch, fake_keyring):
    monkeypatch.setenv("PROTON_BRIDGE_PASSWORD", "from-the-environment")

    assert get_bridge_password("person@example.com") == "from-the-environment"


def test_a03_managed_mode_reads_only_the_keyring(
    monkeypatch, fake_keyring, write_managed_config, managed_config_path
):
    monkeypatch.setenv("PROTON_BRIDGE_PASSWORD", "from-the-environment")
    write_managed_config(managed_config_path, user="person@example.com")
    fake_keyring.set_password("proton-safe-mcp", "person@example.com", "from-the-keyring")

    assert get_bridge_password("person@example.com", allow_environment=False) == "from-the-keyring"


# -- A09: a restart with no exports still works ----------------------------------


@pytest.mark.posix_only
def test_a09_serve_pins_the_managed_settings_before_importing_the_tool_surface(
    monkeypatch, fake_keyring, write_managed_config, managed_config_path, tmp_path
):
    """No PROTON_* export exists, as after a session restart from the desktop menu."""
    for name in (
        "PROTON_BRIDGE_USER",
        "PROTON_BRIDGE_ALIASES",
        "PROTON_IMAP_PORT",
        "PROTON_BRIDGE_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    write_managed_config(managed_config_path, user="person@example.com", port=1144)
    fake_keyring.set_password("proton-safe-mcp", "person@example.com", "bridge-secret")

    from proton_safe_mcp import config

    # A stub stands in for the tool surface so the ordering itself is what is tested:
    # the settings must already be pinned by the time the server module is imported.
    seen: list[object] = []
    stub = types.ModuleType("proton_safe_mcp.server")
    stub.run = lambda: seen.append(config.startup_settings())  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "proton_safe_mcp.server", stub)

    assert cli.main(["serve", "--config", str(managed_config_path)]) == 0

    assert len(seen) == 1
    pinned = seen[0]
    assert pinned.bridge_user == "person@example.com"
    assert pinned.imap_port == 1144
    assert pinned.config_source == "file"
    # The credential is reachable from the keyring alone, with no export in the session.
    assert get_bridge_password(pinned.bridge_user, allow_environment=False) == "bridge-secret"


@pytest.mark.posix_only
def test_a09_the_tool_surface_builds_from_the_pinned_settings(
    monkeypatch, write_managed_config, managed_config_path, tmp_path
):
    for name in ("PROTON_BRIDGE_USER", "PROTON_BRIDGE_ALIASES"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    write_managed_config(managed_config_path, user="pinned@example.com")

    from proton_safe_mcp import config

    config.set_startup_settings(Settings.from_config_file(managed_config_path))
    import proton_safe_mcp.server as server_module

    try:
        reloaded = importlib.reload(server_module)
        # The whole tool surface, not just the CLI, is bound to the managed settings.
        assert reloaded.settings.bridge_user == "pinned@example.com"
        assert reloaded.settings.config_source == "file"
        assert reloaded.settings.allow_environment_secret is False
        assert reloaded.bridge.settings is reloaded.settings
    finally:
        config.set_startup_settings(None)
        monkeypatch.setenv("PROTON_BRIDGE_USER", "user@example.com")
        importlib.reload(server_module)


# -- CLI surface -----------------------------------------------------------------


def test_config_must_be_an_absolute_path(capsys):
    assert cli.main(["doctor", "--config", "relative.toml"]) == 1
    assert "absolute path" in capsys.readouterr().err


@pytest.mark.posix_only
def test_doctor_json_carries_codes_and_no_private_value(
    monkeypatch, fake_keyring, write_managed_config, managed_config_path, capsys, tmp_path
):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    write_managed_config(managed_config_path, user="person@example.com")
    fake_keyring.set_password("proton-safe-mcp", "person@example.com", "bridge-secret")
    Settings.from_config_file(managed_config_path).ensure_directories()
    from proton_safe_mcp import doctor

    monkeypatch.setattr(doctor.platform, "system", lambda: "Linux")
    monkeypatch.setattr(doctor.ProtonBridgeClient, "probe", lambda _self: None)

    assert cli.main(["doctor", "--config", str(managed_config_path), "--json"]) == 0
    output = capsys.readouterr().out
    report = json.loads(output)

    assert report["schema_version"] == 1
    assert report["overall"] == "ok"
    assert {"id": "keyring", "status": "pass", "code": "KEYRING_AVAILABLE"} in report["checks"]
    assert {"id": "bridge", "status": "pass", "code": "BRIDGE_AUTHENTICATED"} in report["checks"]
    assert "person@example.com" not in output
    assert "bridge-secret" not in output
    assert str(managed_config_path) not in output
    assert str(tmp_path) not in output
    # Only versions are allowed to be descriptive.
    assert set(report) == {"schema_version", "overall", "versions", "checks"}
    assert all(set(check) == {"id", "status", "code"} for check in report["checks"])


def test_a17_the_engine_imports_and_runs_without_qt(monkeypatch):
    """A17: nothing outside the desktop package may import Qt at module level."""
    import sys

    blocked = [name for name in sys.modules if name.startswith("PySide6")]
    for name in blocked:
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "PySide6", None)

    for module in (
        "proton_safe_mcp.cli",
        "proton_safe_mcp.config",
        "proton_safe_mcp.configuration_store",
        "proton_safe_mcp.doctor",
        "proton_safe_mcp.mail",
        "proton_safe_mcp.secrets",
        "proton_safe_mcp.onboarding.service",
        "proton_safe_mcp.onboarding.runtime",
        "proton_safe_mcp.onboarding.plugin_assets",
        "proton_safe_mcp.onboarding.clients.openai_local",
    ):
        importlib.reload(importlib.import_module(module))
