from __future__ import annotations

import pytest

from proton_safe_mcp import cli


@pytest.fixture
def env(monkeypatch, settings):
    monkeypatch.setenv("PROTON_BRIDGE_USER", settings.bridge_user)
    monkeypatch.setenv("PROTON_MCP_STATE_DIR", str(settings.state_dir))
    return settings


@pytest.mark.parametrize("command", ["approve", "reject", "show"])
def test_draft_approval_commands_are_gone(command, capsys):
    """No draft approval state machine exists, so the CLI must not offer one."""
    with pytest.raises(SystemExit) as excinfo:
        cli.main([command, "0" * 32])
    assert excinfo.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_a_command_is_required():
    with pytest.raises(SystemExit) as excinfo:
        cli.main([])
    assert excinfo.value.code == 2


def test_configuration_error_is_reported_without_a_traceback(monkeypatch, capsys):
    monkeypatch.delenv("PROTON_BRIDGE_USER", raising=False)
    assert cli.main(["setup"]) == 1
    assert "PROTON_BRIDGE_USER is required" in capsys.readouterr().err


def _answer_prompts(monkeypatch, *answers):
    remaining = list(answers)
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: remaining.pop(0))


def test_setup_stores_the_bridge_password_in_the_keyring(env, monkeypatch, capsys):
    stored: dict[str, str] = {}
    _answer_prompts(monkeypatch, "bridge-password", "bridge-password")
    monkeypatch.setattr(
        cli,
        "store_bridge_password",
        lambda user, password: stored.update(user=user, secret=password),
    )

    assert cli.main(["setup"]) == 0
    assert stored == {"user": env.bridge_user, "secret": "bridge-password"}
    assert "stored in the OS keyring" in capsys.readouterr().out


def test_setup_rejects_mismatched_passwords(env, monkeypatch, capsys):
    _answer_prompts(monkeypatch, "one", "two")
    monkeypatch.setattr(
        cli, "store_bridge_password", lambda *_args: pytest.fail("must not store a credential")
    )

    assert cli.main(["setup"]) == 1
    assert "Passwords do not match" in capsys.readouterr().err


def test_serve_runs_the_stdio_server(env, monkeypatch):
    import proton_safe_mcp.server as server_module

    started: list[bool] = []
    monkeypatch.setattr(server_module, "run", lambda: started.append(True))

    assert cli.main(["serve"]) == 0
    assert started == [True]
