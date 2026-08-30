"""Configuration with a deliberately small, loopback-only attack surface."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigurationError


def _positive_int(name: str, default: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if not 1 <= value <= maximum:
        raise ConfigurationError(f"{name} must be between 1 and {maximum}")
    return value


def _state_dir() -> Path:
    if configured := os.environ.get("PROTON_MCP_STATE_DIR"):
        return Path(configured).expanduser().resolve()
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return (base / "proton-safe-mcp").resolve()


@dataclass(frozen=True, slots=True)
class Settings:
    bridge_user: str
    bridge_host: str
    imap_port: int
    state_dir: Path
    max_attachment_bytes: int
    max_chunk_bytes: int
    upload_ttl_seconds: int
    draft_ttl_seconds: int
    max_body_chars: int

    @property
    def uploads_dir(self) -> Path:
        return self.state_dir / "uploads"

    @property
    def approvals_dir(self) -> Path:
        return self.state_dir / "approvals"

    @classmethod
    def from_env(cls, *, create_directories: bool = True) -> Settings:
        user = os.environ.get("PROTON_BRIDGE_USER", "").strip()
        if not user or "\r" in user or "\n" in user:
            raise ConfigurationError("PROTON_BRIDGE_USER is required")

        settings = cls(
            bridge_user=user,
            # Not configurable by design: disabling TLS verification is only safe on loopback.
            bridge_host="127.0.0.1",
            imap_port=_positive_int("PROTON_IMAP_PORT", 1143, 65535),
            state_dir=_state_dir(),
            max_attachment_bytes=_positive_int(
                "PROTON_MCP_MAX_ATTACHMENT_BYTES", 20 * 1024 * 1024, 25 * 1024 * 1024
            ),
            max_chunk_bytes=_positive_int("PROTON_MCP_MAX_CHUNK_BYTES", 384 * 1024, 1024 * 1024),
            upload_ttl_seconds=_positive_int("PROTON_MCP_UPLOAD_TTL_SECONDS", 1800, 86400),
            draft_ttl_seconds=_positive_int("PROTON_MCP_DRAFT_TTL_SECONDS", 900, 3600),
            max_body_chars=_positive_int("PROTON_MCP_MAX_BODY_CHARS", 100_000, 500_000),
        )
        if create_directories:
            settings.ensure_directories()
        return settings

    def ensure_directories(self) -> None:
        for directory in (self.state_dir, self.uploads_dir, self.approvals_dir):
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            directory.chmod(0o700)
