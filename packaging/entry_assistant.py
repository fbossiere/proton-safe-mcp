"""PyInstaller entry point for the bundled desktop assistant."""

from __future__ import annotations

import contextlib
import os
import sys
import traceback


def run() -> int:
    # A Windows GUI executable has no standard streams. Libraries may still call
    # flush/isatty/write on them while importing or preparing the assistant.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    from proton_safe_mcp.desktop.app import main

    return main()


if __name__ == "__main__":
    if "--verify-bundle" in sys.argv and "--verification-report" in sys.argv:
        report_path = sys.argv[sys.argv.index("--verification-report") + 1]
        # Only the build's temporary verification uses this diagnostic report.
        # Catch failures here, including import errors, so the windowed bootloader
        # cannot turn an unattended check into a blocking exception dialog.
        with (
            open(report_path, "w", encoding="utf-8") as report,
            contextlib.redirect_stdout(report),
            contextlib.redirect_stderr(report),
        ):
            try:
                result = run()
            except Exception:
                traceback.print_exc()
                result = 1
    else:
        result = run()
    sys.exit(result)
