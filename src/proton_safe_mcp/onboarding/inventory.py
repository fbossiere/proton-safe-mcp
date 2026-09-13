"""Targeted detection of what this computer already has.

Detection is a hint, never a proof. A running Bridge process does not mean an account is
connected, and an open port does not mean it belongs to Bridge — the authentication step
is the functional check. Nothing here parses a Bridge profile or looks for credentials.
"""

from __future__ import annotations

import os
import platform
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from ..secrets import keyring_status
from .clients.base import executable_candidates
from .clients.openai_local import OpenAILocalAdapter
from .models import Check, ClientInstallation, Code

#: The validated target. Anything else Linux still runs, with the scope explained.
VALIDATED_DISTRIBUTION: Final = "ubuntu"
VALIDATED_VERSION: Final = "24.04"
VALIDATED_MACHINE: Final = "x86_64"

#: Documented Proton Mail Bridge locations. Presence only; contents are never read.
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


def _os_release() -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        content = Path("/etc/os-release").read_text(encoding="utf-8")
    except OSError:
        return values
    for line in content.splitlines():
        name, separator, raw = line.partition("=")
        if separator:
            values[name.strip()] = raw.strip().strip('"')
    return values


def system_check() -> Check:
    """Report the operating system against the validated scope."""
    machine = platform.machine()
    if platform.system() != "Linux" or machine != VALIDATED_MACHINE:
        return Check("system", "fail", Code.SYSTEM_UNSUPPORTED, f"{platform.system()} {machine}")
    release = _os_release()
    distribution = release.get("ID", "").lower()
    version = release.get("VERSION_ID", "")
    label = f"{release.get('NAME', 'Linux')} {version}".strip()
    validated = distribution == VALIDATED_DISTRIBUTION and version == VALIDATED_VERSION
    # Another Linux is not refused, but the assistant says plainly what was validated.
    return Check("system", "pass" if validated else "warn", Code.SYSTEM_SUPPORTED, label)


def session_check() -> Check:
    """Require an ordinary graphical session, never root."""
    if os.geteuid() == 0:
        return Check("session", "fail", Code.SESSION_ROOT)
    graphical = bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))
    if not graphical:
        return Check("session", "fail", Code.SESSION_NO_GRAPHICAL)
    kind = "Wayland" if os.environ.get("WAYLAND_DISPLAY") else "X11"
    return Check("session", "pass", Code.SESSION_OK, kind)


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
    candidates = [Path(item) for item in BRIDGE_EXECUTABLES]
    found = shutil.which("protonmail-bridge") or shutil.which("proton-bridge")
    if found:
        candidates.insert(0, Path(found))
    if executable_candidates(candidates):
        return Check("bridge", "pass", Code.BRIDGE_APP_DETECTED)
    if any(Path(entry).is_file() for entry in BRIDGE_DESKTOP_ENTRIES):
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
