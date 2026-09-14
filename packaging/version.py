"""Print the engine version, so no build script re-implements reading it.

The version lives in one place — ``src/proton_safe_mcp/__init__.py`` — and the release
workflow already checks that the tag, the wheel and the registry metadata agree with it.
A packaging script that parsed it its own way would be a fourth place for them to
disagree.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "proton_safe_mcp" / "__init__.py"


def engine_version() -> str:
    found = re.search(r'__version__ = "([^"]+)"', SOURCE.read_text(encoding="utf-8"))
    if found is None:  # pragma: no cover - the file always carries one
        raise SystemExit(f"no __version__ found in {SOURCE}")
    return found.group(1)


if __name__ == "__main__":
    print(engine_version())
