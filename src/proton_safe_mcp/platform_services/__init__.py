"""Resolve the platform services this process runs on.

One instance is shared for the life of the process. Tests replace it through
``use_services`` rather than by patching the modules that depend on it, so a Windows
behaviour can be exercised from a Linux checkout wherever the logic — not the system
call — is what is under test.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager

from .base import (
    LineReader,
    PlatformServices,
    PrivacyError,
    SessionFacts,
    UnsupportedPlatformError,
    resolve_state_directory,
)

_services: PlatformServices | None = None


def _build() -> PlatformServices:
    if sys.platform == "win32":
        from .windows import WindowsServices

        return WindowsServices()
    from .posix import PosixServices

    return PosixServices()


def services() -> PlatformServices:
    """Return the platform services for this process."""
    global _services
    if _services is None:
        _services = _build()
    return _services


def is_windows() -> bool:
    return services().name == "windows"


@contextmanager
def use_services(replacement: PlatformServices) -> Iterator[PlatformServices]:
    """Run a block against another platform's services. For tests only."""
    global _services
    previous = _services
    _services = replacement
    try:
        yield replacement
    finally:
        _services = previous


__all__ = [
    "LineReader",
    "PlatformServices",
    "PrivacyError",
    "SessionFacts",
    "UnsupportedPlatformError",
    "is_windows",
    "resolve_state_directory",
    "services",
    "use_services",
]
