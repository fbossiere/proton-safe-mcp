"""Configuration with a deliberately small, loopback-only attack surface.

Two sources exist and never mix:

* ``Settings.from_env`` — the historic mode. Unchanged, environment driven, and it never
  looks for the managed configuration file.
* ``Settings.from_config_file`` — the managed mode used by the desktop assistant. The file
  is the only source of settings and the OS keyring the only source of the credential; no
  ``PROTON_*`` variable is consulted.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from . import configuration_store
from .addresses import validate_address
from .configuration_store import LIMIT_BOUNDS, StoredConfiguration
from .errors import ConfigurationError

MAX_SENDER_ADDRESSES = 25

ConfigSource = Literal["environment", "file"]


def _positive_int(name: str, default: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if not 1 <= value <= maximum:
        raise ConfigurationError(f"{name} must be between 1 and {maximum}")
    return value


def _sender_aliases(primary: str) -> tuple[str, ...]:
    """Return every configured From address this account may draft as, primary first."""
    raw = os.environ.get("PROTON_BRIDGE_ALIASES", "")
    if "\r" in raw or "\n" in raw:
        raise ConfigurationError("PROTON_BRIDGE_ALIASES must not contain a line break")
    senders = [primary]
    seen = {primary.casefold()}
    for item in raw.split(","):
        candidate = item.strip()
        if not candidate:
            continue
        address = validate_address(candidate, error=ConfigurationError)
        if address.casefold() in seen:
            continue
        seen.add(address.casefold())
        senders.append(address)
    if len(senders) > MAX_SENDER_ADDRESSES:
        raise ConfigurationError(
            f"PROTON_BRIDGE_ALIASES may list at most {MAX_SENDER_ADDRESSES - 1} addresses"
        )
    return tuple(senders)


def _default_state_dir() -> Path:
    # An empty or relative XDG_STATE_HOME is ignored, as the XDG base directory
    # specification requires: Path("") would stage attachments in the working directory.
    xdg_state_home = os.environ.get("XDG_STATE_HOME", "")
    base = (
        Path(xdg_state_home) if xdg_state_home.startswith("/") else Path.home() / ".local" / "state"
    )
    return (base / "proton-safe-mcp").resolve()


def _state_dir() -> Path:
    if configured := os.environ.get("PROTON_MCP_STATE_DIR"):
        return Path(configured).expanduser().resolve()
    return _default_state_dir()


@dataclass(frozen=True, slots=True)
class Settings:
    bridge_user: str
    sender_addresses: tuple[str, ...]
    bridge_host: str
    imap_port: int
    state_dir: Path
    max_attachment_bytes: int
    max_received_attachment_bytes: int
    max_chunk_bytes: int
    upload_ttl_seconds: int
    max_body_chars: int
    config_source: ConfigSource = "environment"
    config_path: Path | None = None

    @property
    def default_sender(self) -> str:
        """The From address used when a draft does not name one."""
        return self.sender_addresses[0]

    @property
    def uploads_dir(self) -> Path:
        return self.state_dir / "uploads"

    @property
    def allow_environment_secret(self) -> bool:
        """Whether ``PROTON_BRIDGE_PASSWORD`` may stand in for the keyring.

        Only the historic mode keeps that fallback. A managed setup that could read the
        credential from the environment would defeat the point of storing it in the keyring.
        """
        return self.config_source == "environment"

    @classmethod
    def from_env(cls, *, create_directories: bool = True) -> Settings:
        user = os.environ.get("PROTON_BRIDGE_USER", "").strip()
        if not user:
            raise ConfigurationError("PROTON_BRIDGE_USER is required")
        user = validate_address(user, error=ConfigurationError)

        settings = cls(
            bridge_user=user,
            # Allowlist fixed at startup: no MCP input can introduce a new From address.
            sender_addresses=_sender_aliases(user),
            # Not configurable by design: disabling TLS verification is only safe on loopback.
            bridge_host="127.0.0.1",
            imap_port=_positive_int("PROTON_IMAP_PORT", 1143, 65535),
            state_dir=_state_dir(),
            max_attachment_bytes=_positive_int(
                "PROTON_MCP_MAX_ATTACHMENT_BYTES", 20 * 1024 * 1024, 25 * 1024 * 1024
            ),
            max_received_attachment_bytes=_positive_int(
                "PROTON_MCP_MAX_RECEIVED_ATTACHMENT_BYTES",
                10 * 1024 * 1024,
                25 * 1024 * 1024,
            ),
            max_chunk_bytes=_positive_int("PROTON_MCP_MAX_CHUNK_BYTES", 384 * 1024, 1024 * 1024),
            upload_ttl_seconds=_positive_int("PROTON_MCP_UPLOAD_TTL_SECONDS", 1800, 86400),
            max_body_chars=_positive_int("PROTON_MCP_MAX_BODY_CHARS", 100_000, 500_000),
        )
        if create_directories:
            settings.ensure_directories()
        return settings

    @classmethod
    def from_stored(
        cls,
        stored: StoredConfiguration,
        *,
        path: Path | None = None,
        create_directories: bool = True,
    ) -> Settings:
        """Build settings from a parsed managed configuration, ignoring the environment."""
        senders = (stored.bridge_user, *stored.aliases)
        if len(senders) > MAX_SENDER_ADDRESSES:
            raise ConfigurationError(
                f"A configuration may list at most {MAX_SENDER_ADDRESSES - 1} aliases",
                code="CONFIG_INVALID",
            )
        limits = {name: default for name, (default, _) in LIMIT_BOUNDS.items()}
        limits.update(stored.limits)
        settings = cls(
            bridge_user=stored.bridge_user,
            sender_addresses=senders,
            bridge_host="127.0.0.1",
            imap_port=stored.imap_port,
            state_dir=(stored.state_dir or _default_state_dir()).resolve(),
            max_attachment_bytes=limits["max_attachment_bytes"],
            max_received_attachment_bytes=limits["max_received_attachment_bytes"],
            max_chunk_bytes=limits["max_chunk_bytes"],
            upload_ttl_seconds=limits["upload_ttl_seconds"],
            max_body_chars=limits["max_body_chars"],
            config_source="file",
            config_path=path,
        )
        if create_directories:
            settings.ensure_directories()
        return settings

    @classmethod
    def from_config_file(cls, path: Path, *, create_directories: bool = True) -> Settings:
        """Load the managed configuration. No environment value can override it."""
        resolved = Path(path)
        return cls.from_stored(
            configuration_store.read(resolved),
            path=resolved,
            create_directories=create_directories,
        )

    def ensure_directories(self) -> None:
        for directory in (self.state_dir, self.uploads_dir):
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            directory.chmod(0o700)


_startup_settings: Settings | None = None


def set_startup_settings(settings: Settings | None) -> None:
    """Pin the settings the tool surface must build itself against.

    ``server`` binds its tools at import time, so ``serve --config`` resolves the managed
    configuration first and pins it here. Left unset, the server keeps its historic
    behaviour of reading the environment.
    """
    global _startup_settings
    _startup_settings = settings


def startup_settings() -> Settings:
    """Return the pinned settings, or the historic environment-driven ones."""
    if _startup_settings is not None:
        return _startup_settings
    return Settings.from_env()
