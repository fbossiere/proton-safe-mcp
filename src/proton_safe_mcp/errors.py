"""Domain exceptions deliberately safe to return through MCP."""


class ProtonMCPError(RuntimeError):
    """Base error for expected, user-actionable failures."""


class ConfigurationError(ProtonMCPError):
    """The local server is not configured correctly."""


class AttachmentError(ProtonMCPError):
    """An attachment upload is invalid or expired."""


class ApprovalError(ProtonMCPError):
    """Draft validation or optional out-of-band approval failed."""


class BridgeError(ProtonMCPError):
    """Proton Bridge could not complete an IMAP operation."""
