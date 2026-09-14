"""Targeted detection of what this computer already has.

Detection is a hint, never a proof. A running Bridge process does not mean an account is
connected, and an open port does not mean it belongs to Bridge — the authentication step
is the functional check. Nothing here parses a Bridge profile or looks for credentials.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from ..platform_services import services
from ..platform_services.posix import (
    VALIDATED_DISTRIBUTION,
    VALIDATED_MACHINE,
    VALIDATED_VERSION,
)
from ..secrets import keyring_status
from .clients.base import executable_candidates
from .clients.openai_local import OpenAILocalAdapter
from .models import Check, ClientInstallation, Code

__all__ = [
    "VALIDATED_DISTRIBUTION",
    "VALIDATED_MACHINE",
    "VALIDATED_VERSION",
    "bridge_check",
    "client_check",
    "discover_clients",
    "keyring_check",
    "prerequisites",
    "session_check",
    "system_check",
]

#: Documented Proton Mail Bridge locations. Presence only; contents are never read, and
#: no Bridge profile is ever parsed: finding the application is a hint, and the
#: authentication step on the next screen is the only functional check.
BRIDGE_EXECUTABLES: Final = (
    "/usr/bin/protonmail-bridge",
    "/usr/bin/proton-bridge",
    "/usr/local/bin/protonmail-bridge",
    "/opt/proton/bridge/protonmail-bridge",
    "/snap/bin/proton-mail-bridge",
)
BRIDGE_DESKTOP_ENTRIES: Final = (
    "/usr/share/applications/protonmail-bridge.desktop",
    "/var/lib/flatpak/exports/share/applications/ch.protonmail.protonmail-bridge.desktop",
)

#: Per-user and per-machine Bridge locations on Windows, relative to a known folder.
WINDOWS_BRIDGE_TEMPLATES: Final = (
    ("PROGRAMFILES", "Proton/Proton Mail Bridge/proton-bridge.exe"),
    ("PROGRAMFILES", "Proton AG/Proton Mail Bridge/proton-bridge.exe"),
    ("PROGRAMFILES", "Proton/Proton Mail Bridge/bridge-gui.exe"),
    ("LOCALAPPDATA", "Programs/Proton Mail Bridge/proton-bridge.exe"),
    ("LOCALAPPDATA", "Programs/Proton Mail Bridge/bridge-gui.exe"),
)


def _windows_bridge_candidates() -> list[Path]:
    found: list[Path] = []
    for variable, relative in WINDOWS_BRIDGE_TEMPLATES:
        base = os.environ.get(variable, "")
        if base:
            found.append(Path(base).joinpath(*relative.split("/")))
    return found


def system_check() -> Check:
    """Report the operating system against the validated scope.

    What "out of scope" means differs by platform, and the platform layer decides: an
    untested Linux still runs and is flagged, while anything outside Windows 11 x64 is
    refused before a single file is written.
    """
    status, label = services().system_status()
    if status == "fail":
        return Check("system", "fail", Code.SYSTEM_UNSUPPORTED, label)
    return Check("system", status, Code.SYSTEM_SUPPORTED, label)


def session_check() -> Check:
    """Require an ordinary interactive session for this user, never an elevated one."""
    facts = services().session_facts()
    if facts.elevated:
        # Running as root, or with an elevated Windows token, would set up an account
        # the person is not signed in as.
        code = Code.SESSION_ELEVATED if services().name == "windows" else Code.SESSION_ROOT
        return Check("session", "fail", code)
    if not facts.kind:
        return Check("session", "fail", Code.SESSION_NO_GRAPHICAL)
    return Check("session", "pass", Code.SESSION_OK, facts.kind)


def keyring_check() -> Check:
    """Classify the session keyring; the managed credential has nowhere else to go."""
    status = keyring_status()
    if status.state == "available":
        return Check("keyring", "pass", Code.KEYRING_AVAILABLE)
    if status.state == "locked":
        return Check("keyring", "action_required", Code.KEYRING_LOCKED)
    return Check("keyring", "fail", Code.KEYRING_UNAVAILABLE)


def bridge_check() -> Check:
    """Look for an installed Bridge in documented locations only.

    Finding it proves an application is present, nothing more; not finding it does not
    block the flow, because the user may have installed it elsewhere.
    """
    windows = services().name == "windows"
    candidates = (
        _windows_bridge_candidates() if windows else [Path(item) for item in BRIDGE_EXECUTABLES]
    )
    found = shutil.which("protonmail-bridge") or shutil.which("proton-bridge")
    if found:
        candidates.insert(0, Path(found))
    if executable_candidates(candidates):
        return Check("bridge", "pass", Code.BRIDGE_APP_DETECTED)
    if not windows and any(Path(entry).is_file() for entry in BRIDGE_DESKTOP_ENTRIES):
        return Check("bridge", "pass", Code.BRIDGE_APP_DETECTED)
    # Not a hard failure: the connection test on the next screen is the real check.
    return Check("bridge", "warn", Code.BRIDGE_APP_UNKNOWN)


def client_check(installations: Sequence[ClientInstallation]) -> Check:
    if not installations:
        return Check("client", "fail", Code.CLIENT_NOT_FOUND)
    return Check("client", "pass", Code.CLIENT_DETECTED, installations[0].version)


def discover_clients(adapters: Sequence[object] | None = None) -> list[ClientInstallation]:
    """Discover installations across the adapters this version supports."""
    resolved = list(adapters) if adapters is not None else [OpenAILocalAdapter()]
    found: list[ClientInstallation] = []
    for adapter in resolved:
        discover = getattr(adapter, "discover", None)
        if callable(discover):
            found.extend(discover())
    return found


def prerequisites(installations: Sequence[ClientInstallation]) -> list[Check]:
    """Every prerequisite line, in the order the interface shows them."""
    return [
        system_check(),
        session_check(),
        keyring_check(),
        bridge_check(),
        client_check(installations),
    ]
