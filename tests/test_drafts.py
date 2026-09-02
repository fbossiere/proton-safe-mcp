from __future__ import annotations

import json

import pytest

from proton_safe_mcp.attachments import Attachment
from proton_safe_mcp.drafts import (
    DraftApprovalStore,
    approve_request,
    resolve_sender,
    validate_address,
)
from proton_safe_mcp.errors import ApprovalError


def test_prepare_requires_out_of_band_approval(settings):
    store = DraftApprovalStore(settings)
    result = store.prepare(
        to=["recipient@example.com"],
        cc=[],
        bcc=[],
        subject="A safe draft",
        body_text="Hello",
        attachment_tokens=[],
        attachments=[],
    )
    with pytest.raises(ApprovalError, match="Local approval required"):
        store.get_approved(result["draft_id"])

    approve_request(settings, result["draft_id"])
    approved = store.get_approved(result["draft_id"])
    assert approved.subject == "A safe draft"
    assert approved.to == ("recipient@example.com",)


def test_tampered_approval_digest_is_rejected(settings):
    store = DraftApprovalStore(settings)
    result = store.prepare(
        to=["recipient@example.com"],
        cc=[],
        bcc=[],
        subject="A safe draft",
        body_text="Hello",
        attachment_tokens=[],
        attachments=[],
    )
    approve_request(settings, result["draft_id"])
    marker = store.approval_path(result["draft_id"])
    data = json.loads(marker.read_text())
    data["digest"] = "0" * 64
    marker.write_text(json.dumps(data))
    with pytest.raises(ApprovalError, match="does not match"):
        store.get_approved(result["draft_id"])


@pytest.mark.parametrize(
    "address",
    ["Display Name <user@example.com>", "user@example.com\r\nBcc: attacker@example.com", "bad"],
)
def test_rejects_ambiguous_or_injected_addresses(address):
    with pytest.raises(ApprovalError):
        validate_address(address)


def test_subject_header_injection_is_rejected(settings):
    store = DraftApprovalStore(settings)
    with pytest.raises(ApprovalError, match="Subject"):
        store.prepare(
            to=["recipient@example.com"],
            cc=[],
            bcc=[],
            subject="Hello\r\nBcc: attacker@example.com",
            body_text="Hello",
            attachment_tokens=[],
            attachments=[],
        )


def test_combined_attachment_size_is_bounded(settings):
    store = DraftApprovalStore(settings)
    attachment = Attachment(
        upload_id="a" * 32,
        filename="brief.pdf",
        content_type="application/pdf",
        size_bytes=settings.max_attachment_bytes + 1,
        sha256="b" * 64,
        data=b"",
    )
    with pytest.raises(ApprovalError, match="Combined attachment size"):
        store.prepare(
            to=["recipient@example.com"],
            cc=[],
            bcc=[],
            subject="Too large",
            body_text="Hello",
            attachment_tokens=["token"],
            attachments=[attachment],
        )


def test_sender_defaults_to_the_primary_address(settings):
    assert resolve_sender(settings, None) == "user@example.com"
    assert resolve_sender(settings, "   ") == "user@example.com"


def test_configured_alias_is_accepted_in_its_configured_spelling(settings):
    # Client casing never reaches the header: the configured spelling wins.
    assert resolve_sender(settings, "ALIAS@Example.com") == "alias@example.com"


@pytest.mark.parametrize(
    "sender",
    [
        "attacker@example.com",
        "Alias <alias@example.com>",
        "alias@example.com\r\nFrom: attacker@example.com",
    ],
)
def test_unconfigured_or_injected_sender_is_rejected(settings, sender):
    with pytest.raises(ApprovalError):
        resolve_sender(settings, sender)


def test_approval_digest_binds_the_sender_address(settings):
    store = DraftApprovalStore(settings)
    common = {
        "to": ["recipient@example.com"],
        "cc": [],
        "bcc": [],
        "subject": "A safe draft",
        "body_text": "Hello",
        "attachment_tokens": [],
        "attachments": [],
    }

    primary = store.prepare(**common)
    alias = store.prepare(from_address="alias@example.com", **common)

    assert primary["summary"]["from"] == "user@example.com"
    assert alias["summary"]["from"] == "alias@example.com"
    assert primary["digest"] != alias["digest"]

    approve_request(settings, alias["draft_id"])
    assert store.get_approved(alias["draft_id"]).from_address == "alias@example.com"


def test_prepare_rejects_an_unconfigured_sender_before_writing_a_request(settings):
    store = DraftApprovalStore(settings)
    with pytest.raises(ApprovalError, match="not a configured sender address"):
        store.prepare(
            from_address="attacker@example.com",
            to=["recipient@example.com"],
            cc=[],
            bcc=[],
            subject="A safe draft",
            body_text="Hello",
            attachment_tokens=[],
            attachments=[],
        )
    assert not list(settings.approvals_dir.iterdir())
