"""Configuration with a deliberately small, loopback-only attack surface."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .addresses import validate_address
from .errors import ConfigurationError

MAX_SENDER_ADDRESSES = 25


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


def _state_dir() -> Path:
    if configured := os.environ.get("PROTON_MCP_STATE_DIR"):
        return Path(configured).expanduser().resolve()
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return (base / "proton-safe-mcp").resolve()


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

    @property
    def default_sender(self) -> str:
        """The From address used when a draft does not name one."""
        return self.sender_addresses[0]

    @property
    def uploads_dir(self) -> Path:
        return self.state_dir / "uploads"

    @classmethod
    def from_env(cls, *, create_directories: bool = True) -> Settings:
        user = os.environ.get("PROTON_BRIDGE_USER", "").strip()
        if not user or "\r" in user or "\n" in user:
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

    def ensure_directories(self) -> None:
        for directory in (self.state_dir, self.uploads_dir):
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            directory.chmod(0o700)
