from __future__ import annotations

import pytest

from proton_safe_mcp.addresses import validate_address
from proton_safe_mcp.attachments import Attachment
from proton_safe_mcp.drafts import resolve_sender, validate_draft
from proton_safe_mcp.errors import DraftError


def _attachment(upload_id: str, *, size_bytes: int = 10) -> Attachment:
    return Attachment(
        upload_id=upload_id,
        filename="brief.pdf",
        content_type="application/pdf",
        size_bytes=size_bytes,
        sha256="b" * 64,
        data=b"",
    )


def _validate(settings, **overrides):
    kwargs = {
        "from_address": None,
        "to": ["recipient@example.com"],
        "cc": [],
        "bcc": [],
        "subject": "A safe draft",
        "body_text": "Hello",
        "attachment_tokens": [],
        "attachments": [],
    }
    kwargs.update(overrides)
    return validate_draft(settings, **kwargs)


def test_valid_draft_is_frozen_into_content(settings):
    draft = _validate(settings, cc=["cc@example.com"])
    assert draft.from_address == "user@example.com"
    assert draft.to == ("recipient@example.com",)
    assert draft.cc == ("cc@example.com",)
    assert draft.subject == "A safe draft"


@pytest.mark.parametrize(
    "address",
    ["Display Name <user@example.com>", "user@example.com\r\nBcc: attacker@example.com", "bad"],
)
def test_rejects_ambiguous_or_injected_addresses(address):
    with pytest.raises(DraftError):
        validate_address(address)


def test_subject_header_injection_is_rejected(settings):
    with pytest.raises(DraftError, match="Subject"):
        _validate(settings, subject="Hello\r\nBcc: attacker@example.com")


def test_at_least_one_recipient_is_required(settings):
    with pytest.raises(DraftError, match="At least one To recipient"):
        _validate(settings, to=[])


def test_total_recipient_count_is_bounded(settings):
    with pytest.raises(DraftError, match="at most 25 recipients"):
        _validate(
            settings,
            to=[f"to{index}@example.com" for index in range(13)],
            cc=[f"cc{index}@example.com" for index in range(13)],
        )


def test_body_length_is_bounded(settings):
    with pytest.raises(DraftError, match="body_text must contain"):
        _validate(settings, body_text="x" * (settings.max_body_chars + 1))


def test_token_resolution_mismatch_is_rejected(settings):
    with pytest.raises(DraftError, match="token resolution mismatch"):
        _validate(settings, attachment_tokens=["token"], attachments=[])


def test_attachment_count_is_bounded(settings):
    with pytest.raises(DraftError, match="at most 10 attachments"):
        _validate(
            settings,
            attachment_tokens=[f"token{index}" for index in range(11)],
            attachments=[_attachment(f"{index:032d}") for index in range(11)],
        )


def test_duplicate_attachments_are_rejected(settings):
    with pytest.raises(DraftError, match="Duplicate attachments"):
        _validate(
            settings,
            attachment_tokens=["token-a", "token-b"],
            attachments=[_attachment("a" * 32), _attachment("a" * 32)],
        )


def test_combined_attachment_size_is_bounded(settings):
    with pytest.raises(DraftError, match="Combined attachment size"):
        _validate(
            settings,
            attachment_tokens=["token"],
            attachments=[_attachment("a" * 32, size_bytes=settings.max_attachment_bytes + 1)],
        )


def test_sender_defaults_to_the_primary_address(settings):
    assert resolve_sender(settings, None) == "user@example.com"
    assert resolve_sender(settings, "   ") == "user@example.com"


def test_configured_alias_is_accepted_in_its_configured_spelling(settings):
    # Client casing never reaches the header: the configured spelling wins.
    assert resolve_sender(settings, "ALIAS@Example.com") == "alias@example.com"
    assert _validate(settings, from_address="ALIAS@Example.com").from_address == "alias@example.com"


@pytest.mark.parametrize(
    "sender",
    [
        "attacker@example.com",
        "Alias <alias@example.com>",
        "alias@example.com\r\nFrom: attacker@example.com",
    ],
)
def test_unconfigured_or_injected_sender_is_rejected(settings, sender):
    with pytest.raises(DraftError):
        resolve_sender(settings, sender)


def test_draft_validation_rejects_an_unconfigured_sender(settings):
    with pytest.raises(DraftError, match="not a configured sender address"):
        _validate(settings, from_address="attacker@example.com")
