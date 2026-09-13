# PyInstaller spec: one directory holding both the assistant and its MCP runtime.
#
# The two executables share one `_internal` tree, so the runtime a client launches is
# byte-for-byte the one shipped with the interface. Build with:
#
#     pyinstaller --clean --noconfirm packaging/proton-safe-assistant.spec
#
# ruff: noqa
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

ROOT = Path(SPECPATH).resolve().parent
SOURCE = ROOT / "src" / "proton_safe_mcp"

# The plugin resources travel with the runtime; nothing is fetched at install time.
DATAS = [(str(ROOT / "plugins" / "proton-safe"), "proton_safe_mcp/plugin_resources")]

# FastMCP and this package read their own versions through importlib.metadata, which
# needs the distribution metadata inside the bundle or the server refuses to start.
for distribution in ("fastmcp", "proton-safe-mcp"):
    DATAS += copy_metadata(distribution, recursive=True)

# keyring resolves its backends dynamically, so they must be named explicitly or the
# bundle would start and then find no keyring at all.
KEYRING_IMPORTS = [
    *collect_submodules("keyring.backends"),
    "keyring.backends.SecretService",
    "keyring.backends.chainer",
    "keyring.backends.fail",
    "secretstorage",
    "jeepney",
    "jeepney.io.blocking",
]

runtime_analysis = Analysis(
    [str(ROOT / "packaging" / "entry_runtime.py")],
    pathex=[str(ROOT / "src")],
    datas=DATAS,
    hiddenimports=[*KEYRING_IMPORTS, "proton_safe_mcp.server", "proton_safe_mcp.cli"],
    # The runtime has no interface: keeping Qt out of it keeps the STDIO server small.
    excludes=["PySide6", "shiboken6", "tkinter"],
    noarchive=False,
)

assistant_analysis = Analysis(
    [str(ROOT / "packaging" / "entry_assistant.py")],
    pathex=[str(ROOT / "src")],
    datas=DATAS,
    hiddenimports=[
        *KEYRING_IMPORTS,
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
    ],
    excludes=["tkinter"],
    noarchive=False,
)

MERGE(
    (runtime_analysis, "proton-safe-mcp", "proton-safe-mcp"),
    (assistant_analysis, "proton-safe-assistant", "proton-safe-assistant"),
)

runtime_pyz = PYZ(runtime_analysis.pure)
runtime_exe = EXE(
    runtime_pyz,
    runtime_analysis.scripts,
    [],
    exclude_binaries=True,
    name="proton-safe-mcp",
    console=True,
    strip=False,
    upx=False,
)

assistant_pyz = PYZ(assistant_analysis.pure)
assistant_exe = EXE(
    assistant_pyz,
    assistant_analysis.scripts,
    [],
    exclude_binaries=True,
    name="proton-safe-assistant",
    console=False,
    strip=False,
    upx=False,
)

COLLECT(
    runtime_exe,
    runtime_analysis.binaries,
    runtime_analysis.datas,
    assistant_exe,
    assistant_analysis.binaries,
    assistant_analysis.datas,
    strip=False,
    upx=False,
    name="proton-safe-assistant",
)
