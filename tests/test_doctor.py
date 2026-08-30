from __future__ import annotations

from proton_safe_mcp import cli, doctor
from proton_safe_mcp.errors import BridgeError


def _configure(settings, monkeypatch):
    monkeypatch.setenv("PROTON_BRIDGE_USER", settings.bridge_user)
    monkeypatch.setenv("PROTON_MCP_STATE_DIR", str(settings.state_dir))


def test_doctor_reports_a_privacy_safe_success(settings, monkeypatch, capsys):
    _configure(settings, monkeypatch)
    monkeypatch.setattr(doctor.platform, "system", lambda: "Linux")
    monkeypatch.setattr(doctor, "get_bridge_password", lambda _user: "not-printed")
    monkeypatch.setattr(
        doctor.ProtonBridgeClient,
        "status",
        lambda _self: {
            "connected": True,
            "account": settings.bridge_user,
            "inbox_messages": 42,
            "inbox_unread": 3,
        },
    )

    assert cli.main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert "All checks passed" in output
    assert "authenticated IMAP connection succeeded" in output
    assert settings.bridge_user not in output
    assert "not-printed" not in output
    assert "42" not in output


def test_doctor_reports_missing_configuration_without_crashing(monkeypatch, capsys):
    monkeypatch.delenv("PROTON_BRIDGE_USER", raising=False)
    monkeypatch.setattr(doctor.platform, "system", lambda: "Linux")

    assert cli.main(["doctor"]) == 1
    output = capsys.readouterr().out
    assert "[FAIL] Configuration: PROTON_BRIDGE_USER is required" in output
    assert "[SKIP] Credential" in output
    assert "[SKIP] Bridge" in output


def test_doctor_warns_when_environment_credential_is_used(settings, monkeypatch, capsys):
    _configure(settings, monkeypatch)
    monkeypatch.setattr(doctor.platform, "system", lambda: "Linux")
    monkeypatch.setenv("PROTON_BRIDGE_PASSWORD", "not-printed")
    monkeypatch.setattr(doctor, "get_bridge_password", lambda _user: "not-printed")
    monkeypatch.setattr(
        doctor.ProtonBridgeClient,
        "status",
        lambda _self: {"connected": True},
    )

    assert cli.main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert "[WARN] Credential" in output
    assert "environment fallback in use" in output
    assert "not-printed" not in output


def test_doctor_reports_bridge_failure(settings, monkeypatch, capsys):
    _configure(settings, monkeypatch)
    monkeypatch.setattr(doctor.platform, "system", lambda: "Linux")
    monkeypatch.setattr(doctor, "get_bridge_password", lambda _user: "not-printed")

    def fail(_self):
        raise BridgeError("Proton Bridge IMAP error: connection refused")

    monkeypatch.setattr(doctor.ProtonBridgeClient, "status", fail)

    assert cli.main(["doctor"]) == 1
    output = capsys.readouterr().out
    assert "[FAIL] Bridge" in output
    assert "connection refused" in output
    assert "not-printed" not in output


def test_doctor_rejects_unsupported_platform(settings, monkeypatch, capsys):
    _configure(settings, monkeypatch)
    monkeypatch.setattr(doctor.platform, "system", lambda: "Darwin")

    def unexpected_call(*_args):
        raise AssertionError("unsupported platforms must not access credentials or Bridge")

    monkeypatch.setattr(doctor, "get_bridge_password", unexpected_call)
    monkeypatch.setattr(doctor.ProtonBridgeClient, "status", unexpected_call)

    assert cli.main(["doctor"]) == 1
    assert "[FAIL] Platform: Darwin (Linux required)" in capsys.readouterr().out


def test_doctor_does_not_create_the_state_directory(tmp_path, monkeypatch, capsys):
    state_dir = tmp_path / "missing" / "state"
    monkeypatch.setenv("PROTON_BRIDGE_USER", "bridge-user")
    monkeypatch.setenv("PROTON_MCP_STATE_DIR", str(state_dir))
    monkeypatch.setattr(doctor.platform, "system", lambda: "Linux")
    monkeypatch.setattr(doctor, "get_bridge_password", lambda _user: "not-printed")
    monkeypatch.setattr(
        doctor.ProtonBridgeClient,
        "status",
        lambda _self: {"connected": True},
    )

    assert cli.main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert "[WARN] State directory: not created yet" in output
    assert not state_dir.exists()
