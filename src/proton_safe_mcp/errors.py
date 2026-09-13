"""Domain exceptions deliberately safe to return through MCP."""

from __future__ import annotations


class ProtonMCPError(RuntimeError):
    """Base error for expected, user-actionable failures.

    ``code`` carries a stable identifier for the desktop assistant and ``doctor --json``.
    Translated text is derived from the code, never by matching on the message.
    """

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class ConfigurationError(ProtonMCPError):
    """The local server is not configured correctly."""


class AttachmentError(ProtonMCPError):
    """An attachment upload is invalid or expired."""


class DraftError(ProtonMCPError):
    """Draft content failed validation."""


class BridgeError(ProtonMCPError):
    """Proton Bridge could not complete an IMAP operation."""


class KeyringError(ProtonMCPError):
    """The OS keyring cannot be used for the managed setup."""
