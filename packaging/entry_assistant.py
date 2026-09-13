"""PyInstaller entry point for the bundled desktop assistant."""

from __future__ import annotations

import sys

from proton_safe_mcp.desktop.app import main

if __name__ == "__main__":
    sys.exit(main())
