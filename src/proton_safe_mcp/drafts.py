"""Draft content validation performed before any IMAP write."""

from __future__ import annotations

from dataclasses import dataclass

from .addresses import validate_address
from .attachments import Attachment
from .config import Settings
from .errors import DraftError


def resolve_sender(settings: Settings, value: str | None) -> str:
    """Return the configured From address a draft may use, defaulting to the primary one."""
    if value is None or not value.strip():
        return settings.default_sender
    address = validate_address(value)
    for configured in settings.sender_addresses:
        if configured.casefold() == address.casefold():
            # Return the configured spelling so the header never echoes client casing.
            return configured
    raise DraftError(
        f"{address!r} is not a configured sender address. Configured senders: "
        f"{', '.join(settings.sender_addresses)}."
    )


@dataclass(frozen=True, slots=True)
class DraftContent:
    from_address: str
    to: tuple[str, ...]
    cc: tuple[str, ...]
    bcc: tuple[str, ...]
    subject: str
    body_text: str
    attachment_tokens: tuple[str, ...]
    attachments: tuple[Attachment, ...]


def validate_draft(
    settings: Settings,
    *,
    from_address: str | None,
    to: list[str],
    cc: list[str],
    bcc: list[str],
    subject: str,
    body_text: str,
    attachment_tokens: list[str],
    attachments: list[Attachment],
) -> DraftContent:
    """Validate and freeze the exact content of a draft before any IMAP write."""
    sender = resolve_sender(settings, from_address)
    recipients = tuple(validate_address(item) for item in to)
    cc_values = tuple(validate_address(item) for item in cc)
    bcc_values = tuple(validate_address(item) for item in bcc)
    if not recipients:
        raise DraftError("At least one To recipient is required")
    if len(recipients) + len(cc_values) + len(bcc_values) > 25:
        raise DraftError("A draft may contain at most 25 recipients")
    if "\r" in subject or "\n" in subject or len(subject) > 998:
        raise DraftError("Subject contains a line break or is too long")
    if not body_text or len(body_text) > settings.max_body_chars:
        raise DraftError(f"body_text must contain 1 to {settings.max_body_chars} characters")
    if len(attachment_tokens) != len(attachments):
        raise DraftError("Attachment token resolution mismatch")
    if len(attachments) > 10:
        raise DraftError("A draft may contain at most 10 attachments")
    if sum(item.size_bytes for item in attachments) > settings.max_attachment_bytes:
        raise DraftError("Combined attachment size exceeds the configured per-draft maximum")
    if len({item.upload_id for item in attachments}) != len(attachments):
        raise DraftError("Duplicate attachments are not allowed")
    return DraftContent(
        from_address=sender,
        to=recipients,
        cc=cc_values,
        bcc=bcc_values,
        subject=subject,
        body_text=body_text,
        attachment_tokens=tuple(attachment_tokens),
        attachments=tuple(attachments),
    )
