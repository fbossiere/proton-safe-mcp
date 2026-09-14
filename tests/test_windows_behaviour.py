"""What Proton Safe does on Windows, proved from a checkout on any system.

These are product decisions, not system calls: which executable a client is told to
launch, which paths survive a round trip through JSON and TOML, what the interface says
when a system is out of scope, and which credential entries a self-test is allowed to
touch. All of it is ordinary Python, so it is tested here rather than left to a manual
pass on a machine most contributors do not have.

What is *not* claimed here is that the product works on Windows. Starting a real client,
reading a real Credential Manager entry and surviving a restart are scenarios W01 to W21
in docs/windows-acceptance.md, and none of them can be settled from Linux.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import keyring
import pytest

from proton_safe_mcp import secrets as secrets_module
from proton_safe_mcp.onboarding import inventory, messages, plugin_assets, runtime
from proton_safe_mcp.onboarding.clients import openai_local
from proton_safe_mcp.onboarding.models import Code
from proton_safe_mcp.platform_services import windows as windows_services

# -- locating the runtime a client will start --------------------------------------


def test_the_runtime_is_found_by_its_windows_name_beside_the_interface(
    as_windows, windows_executable, tmp_path, monkeypatch
):
    program = tmp_path / "AppData" / "Programs" / "Proton Safe"
    windows_executable(program / "proton-safe-assistant.exe")
    expected = windows_executable(program / "proton-safe-mcp.exe")
    monkeypatch.setattr(sys, "executable", str(program / "proton-safe-assistant.exe"))

    located = runtime.locate_runtime()

    assert located is not None
    assert Path(located.command[0]) == expected
    assert located.packaged


def test_a_bundle_missing_its_runtime_reports_nothing_rather_than_the_interface(
    as_windows, windows_executable, tmp_path, monkeypatch
):
    """Falling back to the running executable would open a window instead of serving MCP."""
    program = tmp_path / "AppData" / "Programs" / "Proton Safe"
    assistant = windows_executable(program / "proton-safe-assistant.exe")
    monkeypatch.setattr(sys, "executable", str(assistant))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime.shutil, "which", lambda _name: None)

    assert runtime.locate_runtime() is None


def test_a_launcher_script_on_the_path_is_never_taken_for_the_runtime(
    as_windows, windows_executable, tmp_path, monkeypatch
):
    shim = windows_executable(tmp_path / "shims" / "proton-safe-mcp.cmd")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))
    monkeypatch.setattr(runtime.shutil, "which", lambda _name: str(shim))

    assert runtime.locate_runtime() is None


# -- paths that must survive JSON, TOML and a command line -------------------------


def test_a_windows_path_with_spaces_and_accents_survives_the_managed_plugin(
    as_windows, windows_executable, tmp_path
):
    """W04: nothing here is ever parsed by a shell, so the path is passed through whole."""
    program = tmp_path / "Program Éloïse & Co" / "Proton Safe"
    executable = windows_executable(program / "proton-safe-mcp.exe")
    config = tmp_path / "Mes Réglages (2)" / "config.toml"
    location = runtime.RuntimeLocation((str(executable),), packaged=True)

    command = runtime.serve_command(location, config)
    assets = plugin_assets.render(
        serve_command=command, destination=tmp_path / "AppData" / "plugin"
    )
    entry = json.loads((assets.plugin_dir / ".mcp.json").read_text(encoding="utf-8"))
    server = entry["mcpServers"]["proton-safe"]

    assert server["command"] == str(executable)
    assert server["args"] == ["serve", "--config", str(config)]
    # Round-tripped through JSON, the path is byte-for-byte what will be launched.
    assert Path(server["command"]).name == "proton-safe-mcp.exe"


def test_the_managed_plugin_asks_windows_for_what_a_windows_runtime_needs(
    as_windows, windows_executable, tmp_path
):
    executable = windows_executable(tmp_path / "Proton Safe" / "proton-safe-mcp.exe")
    location = runtime.RuntimeLocation((str(executable),), packaged=True)

    assets = plugin_assets.render(
        serve_command=runtime.serve_command(location, tmp_path / "config.toml"),
        destination=tmp_path / "AppData" / "plugin",
    )
    entry = json.loads((assets.plugin_dir / ".mcp.json").read_text(encoding="utf-8"))
    passed = entry["mcpServers"]["proton-safe"]["env_vars"]

    # Windows sockets need SystemRoot; the Linux session bus has no meaning here.
    assert "SystemRoot" in passed
    assert "LOCALAPPDATA" in passed
    assert "DBUS_SESSION_BUS_ADDRESS" not in passed
    assert not [name for name in passed if name.startswith("PROTON_")]


def test_a_managed_entry_is_recognised_whichever_platform_wrote_it():
    """An update must find its own entry, not register a second server beside it."""
    windows_entry = {
        "command": r"C:\Users\Éloïse\AppData\Local\Programs\Proton Safe\proton-safe-mcp.exe",
        "args": ["serve", "--config", r"C:\Users\Éloïse\AppData\Local\Proton Safe\config.toml"],
    }
    linux_entry = {
        "command": "/opt/proton-safe-assistant/proton-safe-mcp",
        "args": ["serve", "--config", "/home/e/.config/proton-safe-mcp/config.toml"],
    }

    assert openai_local.OpenAILocalAdapter.is_managed_command(windows_entry)
    assert openai_local.OpenAILocalAdapter.is_managed_command(linux_entry)
    # The historic uvx entry is someone else's, and is never taken for ours.
    assert not openai_local.OpenAILocalAdapter.is_managed_command(
        {"command": "uvx", "args": ["proton-safe-mcp"]}
    )


# -- the client's own profile ------------------------------------------------------


def test_an_absolute_windows_codex_home_is_honoured_and_never_rewritten(as_windows, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", r"D:\profiles\codex")

    assert openai_local.codex_home() == Path(r"D:\profiles\codex")
    # Reading it must not change it: the client and the assistant share one profile.
    assert openai_local.os.environ["CODEX_HOME"] == r"D:\profiles\codex"


def test_a_relative_codex_home_is_ignored_rather_than_resolved(as_windows, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", "codex")

    assert openai_local.codex_home() == Path.home() / ".codex"


def test_windows_candidates_are_bounded_and_built_from_known_folders(as_windows, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\e\AppData\Local")
    monkeypatch.setenv("PROGRAMFILES", r"C:\Program Files")

    candidates = openai_local.default_candidate_paths()

    assert candidates, "a bounded probe list, never a recursive search"
    assert all(candidate.endswith(".exe") for candidate in candidates)
    assert not any("/usr/" in candidate or "/snap/" in candidate for candidate in candidates)


def test_no_shared_connection_is_claimed_on_windows_before_it_is_verified(as_windows):
    """Saying two surfaces share one host, unverified, would leave one silently off."""
    assert openai_local.shared_surfaces() == ()


# -- prerequisites -----------------------------------------------------------------


def test_an_out_of_scope_windows_is_refused_rather_than_warned(as_windows, monkeypatch):
    """W03: on Linux an untested distribution warns; on Windows it is a refusal."""
    monkeypatch.setattr(
        as_windows, "system_status", lambda: ("fail", "Windows 10 (build 19045) x64")
    )

    check = inventory.system_check()

    assert check.status == "fail"
    assert check.code == Code.SYSTEM_UNSUPPORTED


def test_a_supported_windows_passes_with_a_label_that_names_no_machine(as_windows, monkeypatch):
    monkeypatch.setattr(
        as_windows, "system_status", lambda: ("pass", "Windows 11 (build 26100) x64")
    )

    check = inventory.system_check()

    assert check.status == "pass"
    assert "@" not in check.hint and "\\" not in check.hint


def test_an_elevated_windows_session_is_refused_with_its_own_code(as_windows, monkeypatch):
    monkeypatch.setattr(windows_services, "is_elevated", lambda: True)

    check = inventory.session_check()

    assert check.status == "fail"
    assert check.code == Code.SESSION_ELEVATED


def test_bridge_is_looked_for_in_windows_locations_only(as_windows, monkeypatch, tmp_path):
    monkeypatch.setattr(inventory.shutil, "which", lambda _name: None)
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "Program Files"))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    missing = inventory.bridge_check()
    assert missing.status == "warn"
    assert missing.code == Code.BRIDGE_APP_UNKNOWN

    bridge = tmp_path / "Program Files" / "Proton" / "Proton Mail Bridge" / "proton-bridge.exe"
    bridge.parent.mkdir(parents=True)
    bridge.write_bytes(b"MZ")

    assert inventory.bridge_check().code == Code.BRIDGE_APP_DETECTED


# -- the credential store ----------------------------------------------------------


class _RecordingKeyring:
    """Records every service name touched, so a self-test cannot go near a real one."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}
        self.touched: list[tuple[str, str, str]] = []

    def get_password(self, service: str, username: str) -> str | None:
        self.touched.append(("get", service, username))
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.touched.append(("set", service, username))
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.touched.append(("delete", service, username))
        self.store.pop((service, username), None)


@pytest.fixture
def recording_keyring(monkeypatch):
    backend = _RecordingKeyring()
    backend.__class__.__module__ = "keyring.backends.Windows"
    monkeypatch.setattr(keyring, "get_keyring", lambda: backend)
    monkeypatch.setattr(keyring, "get_password", backend.get_password)
    monkeypatch.setattr(keyring, "set_password", backend.set_password)
    monkeypatch.setattr(keyring, "delete_password", backend.delete_password)
    return backend


def test_the_self_test_never_touches_the_service_holding_the_real_credential(
    as_windows, recording_keyring
):
    """Writing under the real service would make Credential Manager displace it."""
    recording_keyring.store[(secrets_module.SERVICE_NAME, "person@example.com")] = "real"

    status = secrets_module.verify_keyring_round_trip()

    assert status.state == "available"
    assert recording_keyring.store[(secrets_module.SERVICE_NAME, "person@example.com")] == "real"
    assert all(
        service != secrets_module.SERVICE_NAME for _, service, _ in recording_keyring.touched
    )


def test_the_self_test_uses_a_fresh_key_and_leaves_nothing_behind(as_windows, recording_keyring):
    secrets_module.verify_keyring_round_trip()
    first = dict(recording_keyring.store)
    accounts = {account for action, _, account in recording_keyring.touched if action == "set"}

    secrets_module.verify_keyring_round_trip()
    second = {account for action, _, account in recording_keyring.touched if action == "set"}

    assert first == {}, "the probe value is removed once it has been read back"
    assert recording_keyring.store == {}
    assert accounts != second, "each attempt uses a key of its own"
    # Both entries Credential Manager may create for the probe are cleaned up.
    deleted = {service for action, service, _ in recording_keyring.touched if action == "delete"}
    assert secrets_module.PROBE_SERVICE_NAME in deleted
    assert any(target.endswith(f"@{secrets_module.PROBE_SERVICE_NAME}") for target in deleted)


def test_a_backend_that_is_not_credential_manager_is_refused_on_windows(as_windows, monkeypatch):
    class FileBackend:
        def get_password(self, *_args):
            return None

    FileBackend.__module__ = "keyrings.alt.file"
    monkeypatch.setattr(keyring, "get_keyring", FileBackend)

    status = secrets_module.keyring_status()

    assert status.state == "unapproved"
    assert status.code == "KEYRING_UNAVAILABLE"


# -- what the interface says -------------------------------------------------------


def test_every_windows_sentence_exists_in_both_languages():
    assert messages.missing_translations() == []


@pytest.mark.parametrize("language", ["fr", "en"])
def test_an_out_of_scope_windows_is_explained_in_windows_terms(as_windows, language):
    message, action = messages.explain(str(Code.SYSTEM_UNSUPPORTED), language)

    assert "Windows 11" in action
    assert "Ubuntu" not in action
    assert message and action


@pytest.mark.parametrize("language", ["fr", "en"])
def test_the_credential_store_is_named_the_way_windows_names_it(as_windows, language):
    message, action = messages.explain(str(Code.KEYRING_UNAVAILABLE), language)
    said = f"{message} {action}"

    assert "Credential Manager" in said or "Gestionnaire d'identifiants" in said
    assert "gnome-keyring" not in said
    assert messages.translate("prereq.keyring", language) in (
        "Gestionnaire d'identifiants",
        "Credential Manager",
    )


@pytest.mark.parametrize("language", ["fr", "en"])
def test_an_elevated_run_is_explained_before_anything_is_written(as_windows, language):
    message, action = messages.explain(str(Code.SESSION_ELEVATED), language)

    assert message and action
    assert "administra" in (message + action).lower()


def test_the_linux_wording_is_untouched_by_the_windows_overlay():
    """The overlay must never leak into the Ubuntu build's text."""
    _message, action = messages.explain(str(Code.SYSTEM_UNSUPPORTED), "fr")

    assert "Ubuntu 24.04" in action
