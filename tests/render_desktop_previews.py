"""Render the real widgets with synthetic data, without Bridge or user configuration.

Usage: QT_QPA_PLATFORM=offscreen .venv/bin/python tests/render_desktop_previews.py /tmp/previews
Pass --light or --language en; set QT_SCALE_FACTOR=2 to exercise Qt's actual scaling.
This is a developer preview tool, never imported by the installed assistant.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6 import QtCore, QtWidgets
from test_desktop_app import RecordingService, _settle

from proton_safe_mcp.desktop.app import MainWindow
from proton_safe_mcp.desktop.theme import apply_theme
from proton_safe_mcp.onboarding.models import Check, Code, InstallState
from proton_safe_mcp.onboarding.service import Snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--language", choices=("fr", "en"), default="fr")
    parser.add_argument("--light", action="store_true")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    application = QtWidgets.QApplication([])
    with TemporaryDirectory(prefix="proton-safe-preview-") as directory:
        service = RecordingService(Path(directory))
        service.snapshot = lambda: Snapshot(
            state=InstallState.CLIENT_REGISTERED,
            account_masked="d•••@proton.me",
            configuration_present=True,
            last_verified_at="2026-09-13 07:30 UTC",
            last_checks={
                "bridge": f"pass:{Code.BRIDGE_AUTHENTICATED}",
                "runtime": f"pass:{Code.RUNTIME_READY}",
                "client": f"action_required:{Code.CLIENT_RESTART_REQUIRED}",
            },
        )
        window = MainWindow(service, language=args.language)
        apply_theme(window, dark=not args.light)
        if args.compact:
            window.resize(640, 330)
        window.selected_client = service.installation
        window.show()
        for name in window.screens:
            window.show_screen(name)
            _settle(window, application)
            screen = window.screens[name]
            if name == "bridge":
                screen.user.setText("demo@proton.me")
            screen.content_scroll.verticalScrollBar().setValue(0)
            for _ in range(10):
                application.processEvents()
            window.grab().save(str(args.output / f"{name}.png"))
        window.show_screen("bridge")
        window.screens["bridge"].advanced.setChecked(True)
        for _ in range(10):
            application.processEvents()
        window.grab().save(str(args.output / "bridge-advanced.png"))
        window.show_screen("prerequisites")
        _settle(window, application)
        checks = service.prerequisites()
        checks[2] = Check("keyring", "fail", Code.KEYRING_LOCKED)
        window.screens["prerequisites"]._show(checks)
        for _ in range(10):
            application.processEvents()
        window.grab().save(str(args.output / "prerequisites-error.png"))
        window.close()
        application.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents)


if __name__ == "__main__":
    main()
