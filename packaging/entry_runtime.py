"""PyInstaller entry point for the bundled MCP runtime.

A bundled script runs without package context, so this uses absolute imports rather
than the package's own ``__main__``.
"""

from __future__ import annotations

import sys

from proton_safe_mcp.cli import main

if __name__ == "__main__":
    sys.exit(main())
