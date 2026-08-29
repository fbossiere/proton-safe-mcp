from __future__ import annotations

import json

import pytest

from proton_safe_mcp.attachments import Attachment
from proton_safe_mcp.drafts import DraftApprovalStore, approve_request, validate_address
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
