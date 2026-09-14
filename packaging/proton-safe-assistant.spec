# PyInstaller spec: one directory holding both the assistant and its MCP runtime.
#
# The two executables share one `_internal` tree, so the runtime a client launches is
# byte-for-byte the one shipped with the interface. Build with:
#
#     pyinstaller --clean --noconfirm packaging/proton-safe-assistant.spec
#
# The same spec builds both platforms. What differs is stated once, below: the keyring
# backend that actually exists there, the Linux graphics stack that must not be dragged
# into a Windows build, and the icon and version metadata Windows shows in Explorer and
# in its installed-applications list.
#
# ruff: noqa
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

ROOT = Path(SPECPATH).resolve().parent
SOURCE = ROOT / "src" / "proton_safe_mcp"
IS_WINDOWS = sys.platform == "win32"

VERSION = re.search(
    r'__version__ = "([^"]+)"', (SOURCE / "__init__.py").read_text(encoding="utf-8")
).group(1)

# The plugin resources travel with the runtime; nothing is fetched at install time.
DATAS = [(str(ROOT / "plugins" / "proton-safe"), "proton_safe_mcp/plugin_resources")]

# FastMCP and this package read their own versions through importlib.metadata, which
# needs the distribution metadata inside the bundle or the server refuses to start.
for distribution in ("fastmcp", "proton-safe-mcp"):
    DATAS += copy_metadata(distribution, recursive=True)

# keyring resolves its backends dynamically, so they must be named explicitly or the
# bundle would start and then find no keyring at all. Only the backend that can work on
# the platform being built is pulled in: shipping the Linux one inside a Windows build
# would enlarge it with a credential store that cannot exist there.
KEYRING_IMPORTS = [
    *collect_submodules("keyring.backends"),
    "keyring.backends.chainer",
    "keyring.backends.fail",
]
if IS_WINDOWS:
    KEYRING_IMPORTS += [
        "keyring.backends.Windows",
        "win32ctypes.pywin32.win32cred",
        "win32ctypes.pywin32.pywintypes",
        "win32ctypes.core",
        "win32ctypes.core.ctypes",
        "win32ctypes.core.ctypes._authentication",
        "win32ctypes.core.ctypes._common",
        "win32ctypes.core.ctypes._dll",
        "win32ctypes.core.ctypes._time",
        "win32ctypes.core.ctypes._util",
    ]
    # A Windows build must not carry the Linux session-bus stack, and must never be
    # able to fall back to it.
    PLATFORM_EXCLUDES = ["secretstorage", "jeepney", "dbus"]
else:
    KEYRING_IMPORTS += [
        "keyring.backends.SecretService",
        "secretstorage",
        "jeepney",
        "jeepney.io.blocking",
    ]
    PLATFORM_EXCLUDES = []

ICON = None
VERSION_RESOURCE = None
if IS_WINDOWS:
    # Built by packaging/windows/make_icon.py from the interface's own drawing, so no
    # binary asset is committed to the repository.
    icon_path = ROOT / "build" / "windows" / "proton-safe.ico"
    if not icon_path.is_file():
        raise SystemExit(
            "the Windows icon is missing; run packaging/windows/make_icon.py first"
        )
    ICON = str(icon_path)

    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    numeric = tuple(int(part) for part in VERSION.split(".")[:3]) + (0,)

    def version_resource(internal_name, description):
        """Windows file metadata. The publisher is this project, never Proton."""
        return VSVersionInfo(
            ffi=FixedFileInfo(filevers=numeric, prodvers=numeric),
            kids=[
                StringFileInfo(
                    [
                        StringTable(
                            "040904B0",
                            [
                                StringStruct("CompanyName", "Proton Safe (independent project)"),
                                StringStruct("FileDescription", description),
                                StringStruct("FileVersion", VERSION),
                                StringStruct("InternalName", internal_name),
                                StringStruct("LegalCopyright", "MIT licence. Not affiliated with Proton."),
                                StringStruct("OriginalFilename", f"{internal_name}.exe"),
                                StringStruct("ProductName", "Proton Safe"),
                                StringStruct("ProductVersion", VERSION),
                            ],
                        )
                    ]
                ),
                VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
            ],
        )

    VERSION_RESOURCE = version_resource

runtime_analysis = Analysis(
    [str(ROOT / "packaging" / "entry_runtime.py")],
    pathex=[str(ROOT / "src")],
    datas=DATAS,
    hiddenimports=[*KEYRING_IMPORTS, "proton_safe_mcp.server", "proton_safe_mcp.cli"],
    # The runtime has no interface: keeping Qt out of it keeps the STDIO server small.
    excludes=["PySide6", "shiboken6", "tkinter", *PLATFORM_EXCLUDES],
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
        # QLocalServer keeps one assistant window per account. It is a named pipe on
        # Windows and a Unix socket on Linux; nothing is exposed to the network.
        "PySide6.QtNetwork",
        "PySide6.QtWidgets",
    ],
    excludes=["tkinter", *PLATFORM_EXCLUDES],
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
    # The runtime speaks MCP over STDIO and must keep working streams. It stays a
    # console program; the client that starts it is what suppresses the window, and
    # the assistant passes CREATE_NO_WINDOW when it probes the runtime itself.
    console=True,
    icon=ICON,
    version=VERSION_RESOURCE("proton-safe-mcp", "Proton Safe MCP server") if VERSION_RESOURCE else None,
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
    icon=ICON,
    version=VERSION_RESOURCE("proton-safe-assistant", "Proton Safe setup assistant") if VERSION_RESOURCE else None,
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
