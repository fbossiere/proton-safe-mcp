"""Render the Windows icon from the interface's own drawing.

The `.ico` is built, never committed. It comes from ``desktop.theme.icon_pixmap``, the
same code that draws the window icon, so the installer, the Start menu entry, the task
bar and the window cannot end up showing three different marks.

Usage::

    python packaging/windows/make_icon.py build/windows/proton-safe.ico
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

#: Windows 11 reads PNG-compressed entries at every size, and they keep the alpha edge
#: clean where a 4-bit DIB would not.
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_bytes(pixmap: object) -> bytes:
    from PySide6 import QtCore

    buffer = QtCore.QBuffer()
    buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
    if not pixmap.save(buffer, "PNG"):  # type: ignore[attr-defined]
        raise SystemExit("the icon could not be encoded as PNG")
    data = bytes(buffer.data())
    buffer.close()
    if not data.startswith(_PNG_SIGNATURE):
        raise SystemExit("the encoded icon is not a PNG")
    return data


def build_ico(images: list[tuple[int, bytes]]) -> bytes:
    """Assemble an ICO container from one PNG per size."""
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)
    directory = b""
    payload = b""
    offset = len(header) + count * 16
    for size, data in images:
        # 0 means 256 in an icon directory entry; anything larger has no encoding.
        stored = 0 if size >= 256 else size
        directory += struct.pack(
            "<BBBBHHII", stored, stored, 0, 0, 1, 32, len(data), offset + len(payload)
        )
        payload += data
    return header + directory + payload


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    destination = Path(argv[1]).resolve()

    from PySide6 import QtGui

    from proton_safe_mcp.desktop.theme import ICON_SIZES, icon_pixmap

    # Drawing needs a QGuiApplication, but never a display: offscreen is enough and is
    # what the build machine has.
    application = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication(
        [argv[0], "-platform", "offscreen"]
    )
    images = [(size, _png_bytes(icon_pixmap(size))) for size in ICON_SIZES]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(build_ico(images))
    del application
    print(f"icon written to {destination} ({len(ICON_SIZES)} sizes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
