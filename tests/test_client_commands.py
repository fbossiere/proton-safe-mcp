"""The bounded process runner and the targeted inventory, exercised for real.

`run_command` is what actually starts a client executable, so these tests run real
processes rather than doubles: the point is that a hostile or hung client cannot hang the
assistant, flood it, or reach a shell.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from proton_safe_mcp.onboarding import inventory
from proton_safe_mcp.onboarding.clients.base import (
    MAX_OUTPUT_BYTES,
    executable_candidates,
    run_command,
)
from proton_safe_mcp.onboarding.models import Code


def _script(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
    path.chmod(0o700)
    return path


# -- the bounded runner ------------------------------------------------------------


def test_a_command_that_succeeds_returns_its_output(tmp_path):
    script = _script(tmp_path, "ok", "print('codex-cli 1.4.0')\n")

    result = run_command([str(script)])

    assert result.ok
    assert result.returncode == 0
    assert "codex-cli 1.4.0" in result.stdout


def test_a_failing_command_is_reported_without_raising(tmp_path):
    script = _script(tmp_path, "bad", "import sys\nsys.exit(2)\n")

    result = run_command([str(script)])

    assert not result.ok
    assert result.returncode == 2
    assert not result.timed_out


def test_a_hanging_command_is_stopped_by_its_deadline(tmp_path):
    script = _script(tmp_path, "hang", "import time\ntime.sleep(30)\n")

    result = run_command([str(script)], timeout=1.0)

    assert not result.ok
    assert result.timed_out
    assert result.failed_to_run


def test_a_flooding_command_cannot_exhaust_memory(tmp_path):
    script = _script(tmp_path, "flood", "import sys\nsys.stdout.write('x' * (4 * 1024 * 1024))\n")

    result = run_command([str(script)], timeout=30.0)

    assert len(result.stdout) <= 2 * MAX_OUTPUT_BYTES + 1


def test_stderr_is_captured_too_so_a_refusal_is_classified(tmp_path):
    script = _script(
        tmp_path,
        "noisy",
        "import sys\nsys.stderr.write('unrecognized subcommand')\nsys.exit(1)\n",
    )

    result = run_command([str(script)])

    assert not result.ok
    assert "unrecognized subcommand" in result.stdout


def test_a_relative_command_is_refused(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _script(tmp_path, "local", "print('hello')\n")

    result = run_command(["local"])

    assert not result.ok
    assert result.returncode == -1


def test_an_absent_command_is_reported_rather_than_raised(tmp_path):
    result = run_command([str(tmp_path / "absent")])

    assert not result.ok
    assert result.failed_to_run


def test_arguments_never_reach_a_shell(tmp_path):
    """A shell metacharacter must be an argument, not an instruction."""
    marker = tmp_path / "pwned"
    script = _script(tmp_path, "echoer", "import sys\nprint(repr(sys.argv[1:]))\n")

    result = run_command([str(script), f"; touch {marker}"])

    assert result.ok
    assert not marker.exists()
    assert "; touch" in result.stdout


def test_the_child_environment_carries_no_proton_value(tmp_path, monkeypatch):
    monkeypatch.setenv("PROTON_BRIDGE_USER", "leaked@example.com")
    monkeypatch.setenv("PROTON_BRIDGE_PASSWORD", "leaked-secret")
    script = _script(tmp_path, "dumper", "import os\nprint(' '.join(sorted(os.environ)))\n")

    result = run_command([str(script)])

    assert "PROTON_BRIDGE_USER" not in result.stdout
    assert "PROTON_BRIDGE_PASSWORD" not in result.stdout
    assert "leaked-secret" not in result.stdout


# -- candidate selection -----------------------------------------------------------


def test_only_real_executable_files_become_candidates(tmp_path):
    executable = _script(tmp_path, "codex", "print('x')\n")
    not_executable = tmp_path / "codex-text"
    not_executable.write_text("#!/bin/sh\n")
    not_executable.chmod(0o600)
    directory = tmp_path / "codex-dir"
    directory.mkdir()

    kept = executable_candidates([executable, not_executable, directory, tmp_path / "absent"])

    assert kept == [executable.resolve()]


def test_two_paths_to_one_executable_are_kept_once(tmp_path):
    executable = _script(tmp_path, "codex", "print('x')\n")
    link = tmp_path / "codex-link"
    link.symlink_to(executable)

    assert executable_candidates([executable, link]) == [executable.resolve()]


def test_a_broken_symlink_is_skipped(tmp_path):
    link = tmp_path / "codex"
    link.symlink_to(tmp_path / "nowhere")

    assert executable_candidates([link]) == []


# -- prerequisites -----------------------------------------------------------------


def test_running_as_root_blocks_the_session_check(monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 0)

    check = inventory.session_check()

    assert check.status == "fail"
    assert check.code is Code.SESSION_ROOT


def test_a_session_with_no_display_blocks(monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)

    check = inventory.session_check()

    assert check.status == "fail"
    assert check.code is Code.SESSION_NO_GRAPHICAL


@pytest.mark.parametrize(
    ("variables", "expected_hint"),
    [({"WAYLAND_DISPLAY": "wayland-0"}, "Wayland"), ({"DISPLAY": ":0"}, "X11")],
)
def test_both_wayland_and_x11_sessions_are_accepted(monkeypatch, variables, expected_hint):
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    for name, value in variables.items():
        monkeypatch.setenv(name, value)

    check = inventory.session_check()

    assert check.status == "pass"
    assert check.hint == expected_hint


def test_a_non_x86_or_non_linux_system_is_blocked(monkeypatch):
    monkeypatch.setattr(inventory.platform, "system", lambda: "Darwin")

    assert inventory.system_check().status == "fail"

    monkeypatch.setattr(inventory.platform, "system", lambda: "Linux")
    monkeypatch.setattr(inventory.platform, "machine", lambda: "aarch64")

    assert inventory.system_check().status == "fail"


def test_the_validated_distribution_passes_and_another_linux_only_warns(monkeypatch, tmp_path):
    monkeypatch.setattr(inventory.platform, "system", lambda: "Linux")
    monkeypatch.setattr(inventory.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        inventory, "_os_release", lambda: {"ID": "ubuntu", "VERSION_ID": "24.04", "NAME": "Ubuntu"}
    )
    assert inventory.system_check().status == "pass"

    monkeypatch.setattr(
        inventory, "_os_release", lambda: {"ID": "debian", "VERSION_ID": "12", "NAME": "Debian"}
    )
    other = inventory.system_check()
    # Not refused, but the validated scope is stated rather than implied.
    assert other.status == "warn"
    assert "Debian" in other.hint


def test_a_missing_bridge_application_warns_rather_than_blocking(monkeypatch):
    monkeypatch.setattr(inventory.shutil, "which", lambda _name: None)
    monkeypatch.setattr(inventory, "BRIDGE_EXECUTABLES", ())
    monkeypatch.setattr(inventory, "BRIDGE_DESKTOP_ENTRIES", ())

    check = inventory.bridge_check()

    # Detection is a hint: the authentication step is the functional proof.
    assert check.status == "warn"
    assert check.code is Code.BRIDGE_APP_UNKNOWN


def test_a_detected_bridge_application_passes(monkeypatch, tmp_path):
    bridge = _script(tmp_path, "protonmail-bridge", "print('x')\n")
    monkeypatch.setattr(inventory.shutil, "which", lambda _name: None)
    monkeypatch.setattr(inventory, "BRIDGE_EXECUTABLES", (str(bridge),))

    assert inventory.bridge_check().code is Code.BRIDGE_APP_DETECTED


def test_a_bridge_desktop_entry_alone_is_enough_to_report_it_installed(monkeypatch, tmp_path):
    entry = tmp_path / "protonmail-bridge.desktop"
    entry.write_text("[Desktop Entry]\n", encoding="utf-8")
    monkeypatch.setattr(inventory.shutil, "which", lambda _name: None)
    monkeypatch.setattr(inventory, "BRIDGE_EXECUTABLES", ())
    monkeypatch.setattr(inventory, "BRIDGE_DESKTOP_ENTRIES", (str(entry),))

    assert inventory.bridge_check().code is Code.BRIDGE_APP_DETECTED


def test_no_client_found_blocks_the_flow(monkeypatch):
    check = inventory.client_check([])

    assert check.status == "fail"
    assert check.code is Code.CLIENT_NOT_FOUND


def test_discovery_with_no_adapter_finds_nothing_and_does_not_raise():
    assert inventory.discover_clients([]) == []


def test_the_prerequisite_list_is_the_five_documented_lines(monkeypatch):
    checks = inventory.prerequisites([])

    assert [check.id for check in checks] == [
        "system",
        "session",
        "keyring",
        "bridge",
        "client",
    ]


def test_an_unreadable_os_release_does_not_crash_the_check(monkeypatch):
    monkeypatch.setattr(
        inventory.Path, "read_text", lambda _self, **_kwargs: (_ for _ in ()).throw(OSError())
    )

    assert inventory._os_release() == {}
