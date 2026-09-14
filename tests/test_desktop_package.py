"""Packaging behaviour: what a built package really contains and how it is found.

The archive-level tests run only when a package has been built, so a plain checkout still
passes the suite; CI builds the package first and then runs them.
"""

from __future__ import annotations

import configparser
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from proton_safe_mcp import __version__
from proton_safe_mcp.onboarding import plugin_assets
from proton_safe_mcp.onboarding.runtime import RuntimeLocation, locate_runtime, serve_command

ROOT = Path(__file__).resolve().parents[1]
DESKTOP_ENTRY = ROOT / "packaging" / "proton-safe-assistant.desktop"
BUILT_PACKAGES = sorted((ROOT / "dist" / "desktop").glob("*.deb"))
# Only a wheel built from this working tree can be asserted on; an older committed
# artefact says nothing about the current sources.
# Only a wheel built from this working tree can be asserted on; an older committed
# artefact says nothing about the current sources.
BUILT_WHEELS = sorted((ROOT / "dist").glob(f"proton_safe_mcp-{__version__}-*.whl"))


# -- the desktop entry ------------------------------------------------------------


@pytest.fixture(scope="module")
def desktop_entry():
    parser = configparser.RawConfigParser(strict=True)
    parser.optionxform = str
    parser.read(DESKTOP_ENTRY, encoding="utf-8")
    return parser["Desktop Entry"]


def test_the_desktop_entry_is_a_valid_application_launcher(desktop_entry):
    assert desktop_entry["Type"] == "Application"
    assert desktop_entry["Name"]
    assert desktop_entry["Exec"] == "/usr/bin/proton-safe-assistant"
    # A graphical assistant must never drop the user into a terminal.
    assert desktop_entry["Terminal"] == "false"
    assert "Network" in desktop_entry["Categories"].split(";")


def test_the_desktop_entry_is_translated(desktop_entry):
    assert desktop_entry["Name[fr]"]
    assert desktop_entry["Comment[fr]"]
    assert desktop_entry["Comment[fr]"] != desktop_entry["Comment"]


def test_the_desktop_entry_passes_no_user_value_on_the_command_line(desktop_entry):
    command = desktop_entry["Exec"]

    assert "@" not in command
    assert "--config" not in command
    assert "password" not in command.lower()


# -- locating the runtime inside a bundle -----------------------------------------


def test_the_runtime_is_found_beside_the_assistant_in_a_bundle(
    tmp_path, monkeypatch, make_executable
):
    """The packaged layout: both executables sit in the same directory."""
    bundle = tmp_path / "opt" / "proton-safe-assistant"
    bundle.mkdir(parents=True)
    assistant = make_executable(bundle, "proton-safe-assistant")
    runtime = make_executable(bundle, "proton-safe-mcp")
    monkeypatch.setattr(sys, "executable", str(assistant))

    located = locate_runtime()

    assert located is not None
    assert located.command == (str(runtime),)
    assert located.packaged


def test_a_managed_entry_uses_the_absolute_runtime_and_an_explicit_configuration(tmp_path):
    runtime = RuntimeLocation(("/opt/proton-safe-assistant/proton-safe-mcp",), packaged=True)

    command = serve_command(runtime, tmp_path / "config.toml")

    assert command[0].startswith("/opt/")
    assert "uvx" not in command
    assert command[1] == "serve"
    assert command[2] == "--config"


# -- the wheel ---------------------------------------------------------------------


@pytest.mark.skipif(not BUILT_WHEELS, reason="no wheel has been built in dist/")
def test_the_wheel_carries_the_plugin_resources_and_the_gui_entry_point():
    with zipfile.ZipFile(BUILT_WHEELS[-1]) as wheel:
        names = wheel.namelist()
        entry_points = next(
            wheel.read(name).decode("utf-8") for name in names if name.endswith("entry_points.txt")
        )

    assert "proton_safe_mcp/plugin_resources/.codex-plugin/plugin.json" in names
    for skill in plugin_assets.CANONICAL_SKILLS:
        assert f"proton_safe_mcp/plugin_resources/skills/{skill}/SKILL.md" in names
    assert "proton-safe-mcp = proton_safe_mcp.cli:main" in entry_points
    assert "proton-safe-assistant = proton_safe_mcp.desktop.app:main" in entry_points


@pytest.mark.skipif(not BUILT_WHEELS, reason="no wheel has been built in dist/")
def test_the_wheel_does_not_require_qt():
    with zipfile.ZipFile(BUILT_WHEELS[-1]) as wheel:
        metadata = next(
            wheel.read(name).decode("utf-8")
            for name in wheel.namelist()
            if name.endswith("METADATA")
        )

    required = [
        line
        for line in metadata.splitlines()
        if line.startswith("Requires-Dist:") and "extra ==" not in line
    ]
    assert not any("pyside6" in line.lower() for line in required)
    # Qt is reachable only through the optional desktop extra.
    optional = [
        line
        for line in metadata.splitlines()
        if line.startswith("Requires-Dist:") and "desktop" in line
    ]
    assert any("pyside6" in line.lower() for line in optional)
    assert "Provides-Extra: desktop" in metadata


# -- the built package -------------------------------------------------------------


@pytest.fixture(scope="module")
def package_contents():
    if not BUILT_PACKAGES:
        pytest.skip("no .deb has been built in dist/desktop/")
    listing = subprocess.run(  # noqa: S603 - fixed argv
        ["/usr/bin/dpkg-deb", "--contents", str(BUILT_PACKAGES[-1])],
        capture_output=True,
        check=True,
        text=True,
    )
    # Each line is "perms owner size date time path [-> link target]"; the entry is the
    # path field, not the link target a naive split would pick up.
    entries = []
    for line in listing.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 6 and fields[5].startswith("."):
            entries.append(fields[5])
    return entries


def test_the_package_ships_both_executables_and_one_launcher(package_contents):
    assert "./opt/proton-safe-assistant/proton-safe-assistant" in package_contents
    assert "./opt/proton-safe-assistant/proton-safe-mcp" in package_contents
    assert "./usr/share/applications/proton-safe-assistant.desktop" in package_contents
    assert "./usr/share/icons/hicolor/scalable/apps/proton-safe-assistant.svg" in package_contents


def test_the_package_never_shadows_a_historic_cli_installation(package_contents):
    on_path = [
        name
        for name in package_contents
        if name.startswith("./usr/bin/") and not name.endswith("/")
    ]

    # Only the graphical entry point is exposed; a user's own ~/.local/bin/proton-safe-mcp
    # and any system `uv`/Python installation keep working untouched.
    assert on_path == ["./usr/bin/proton-safe-assistant"]
    assert not any(name.startswith("./home/") for name in package_contents)
    assert not any(name.startswith("./root/") for name in package_contents)
    assert not any("environment.d" in name for name in package_contents)


def test_the_package_carries_no_configuration_or_credential(package_contents):
    assert not any(name.endswith("config.toml") for name in package_contents)
    assert not any("keyring" in name and name.endswith(".conf") for name in package_contents)


@pytest.mark.skipif(not BUILT_PACKAGES, reason="no .deb has been built in dist/desktop/")
def test_the_maintainer_scripts_do_not_touch_user_data():
    control = subprocess.run(  # noqa: S603 - fixed argv
        ["/usr/bin/dpkg-deb", "--info", str(BUILT_PACKAGES[-1])],
        capture_output=True,
        check=True,
        text=True,
    ).stdout

    assert "Package: proton-safe-assistant" in control
    assert "Recommends: gnome-keyring" in control
    for forbidden in ("rm -rf", "/home/", "$HOME", "secret-tool", "chown"):
        assert forbidden not in control


@pytest.mark.skipif(
    not (ROOT / "dist" / "desktop" / "proton-safe-assistant").is_dir(),
    reason="no bundle has been built in dist/desktop/",
)
def test_the_built_bundle_verifies_itself(tmp_path, write_managed_config):
    """The strongest packaging check: run the built assistant's own verification."""
    bundle = ROOT / "dist" / "desktop" / "proton-safe-assistant"
    directory = tmp_path / "config" / "proton-safe-mcp"
    directory.mkdir(mode=0o700, parents=True)
    config = write_managed_config(directory / "config.toml")

    completed = subprocess.run(  # noqa: S603 - fixed argv from the built bundle
        [str(bundle / "proton-safe-assistant"), "--verify-bundle", "--config", str(config)],
        capture_output=True,
        text=True,
        timeout=180,
        env={
            **{k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "LANG"}},
            "XDG_STATE_HOME": str(tmp_path / "state"),
            "XDG_DATA_HOME": str(tmp_path / "data"),
        },
    )

    assert completed.returncode == 0, completed.stderr
    assert "runtime 13 tools" in completed.stdout


def test_windowed_verification_reports_failure_without_an_exception_dialog(tmp_path, monkeypatch):
    import runpy
    import sys
    from types import ModuleType

    report = tmp_path / "rapport de vérification.log"
    app = ModuleType("proton_safe_mcp.desktop.app")

    def fail():
        raise RuntimeError("intentional bundle failure")

    app.main = fail
    monkeypatch.setitem(sys.modules, "proton_safe_mcp.desktop.app", app)
    monkeypatch.setattr(
        sys, "argv", ["assistant", "--verify-bundle", "--verification-report", str(report)]
    )
    with pytest.raises(SystemExit) as exited:
        runpy.run_path(
            str(Path(__file__).parents[1] / "packaging/entry_assistant.py"), run_name="__main__"
        )
    assert exited.value.code == 1
    assert "intentional bundle failure" in report.read_text(encoding="utf-8")
