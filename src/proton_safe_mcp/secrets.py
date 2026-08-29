"""Bridge credential access. The Proton account password is never used here."""

from __future__ import annotations

import os

import keyring

from .errors import ConfigurationError

SERVICE_NAME = "proton-safe-mcp"


def store_bridge_password(user: str, password: str) -> None:
    if not password:
        raise ConfigurationError("The Bridge password cannot be empty")
    keyring.set_password(SERVICE_NAME, user, password)


def get_bridge_password(user: str) -> str:
    # Environment fallback is useful for isolated containers, but keyring is preferred.
    password = os.environ.get("PROTON_BRIDGE_PASSWORD") or keyring.get_password(SERVICE_NAME, user)
    if not password:
        raise ConfigurationError(
            "No Proton Bridge password found. Run `proton-safe-mcp setup` first."
        )
    return password
