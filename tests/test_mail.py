from __future__ import annotations

import imaplib
from contextlib import contextmanager
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser

from proton_safe_mcp.attachments import Attachment
from proton_safe_mcp.mail import ProtonBridgeClient


def test_imap_byte_capabilities_are_normalized(monkeypatch, settings):
    enabled = []

    class FakeIMAP:
        error = imaplib.IMAP4.error
        capabilities = (b"IMAP4REV1", b"UTF8=ACCEPT")

        def __init__(self, *_args, **_kwargs):
            pass

        def starttls(self, *, ssl_context):
            return "OK", [b"Begin TLS"]

        def login(self, user, password):
            return "OK", [b"Logged in"]

        def enable(self, capability):
            enabled.append(capability)
            return "OK", [b"Enabled"]

        def logout(self):
            return "BYE", [b"Logged out"]

    monkeypatch.setattr("proton_safe_mcp.mail.get_bridge_password", lambda _user: "password")
    monkeypatch.setattr("proton_safe_mcp.mail.imaplib.IMAP4", FakeIMAP)

    with ProtonBridgeClient(settings).connection():
        pass

    assert enabled == ["UTF8=ACCEPT"]


def test_html_only_mail_is_flattened_and_scripts_removed():
    message = EmailMessage()
    message.set_content(
        "<html><head><style>.x{display:none}</style></head>"
        "<body><h1>Invoice</h1><script>steal()</script><p>Amount: 42</p></body></html>",
        subtype="html",
    )
    text = ProtonBridgeClient._body_as_text(message)
    assert "Invoice" in text
    assert "Amount: 42" in text
    assert "steal" not in text
    assert "display:none" not in text


def test_plain_text_is_preferred_over_html():
    message = EmailMessage()
    message.set_content("Plain content")
    message.add_alternative("<p>HTML content</p>", subtype="html")
    assert ProtonBridgeClient._body_as_text(message) == "Plain content"


def test_source_contains_no_smtp_sender():
    from pathlib import Path

    import proton_safe_mcp.mail as mail_module

    source = Path(mail_module.__file__).read_text(encoding="utf-8")
    assert "smtplib" not in source
    assert "send_message(" not in source


def test_append_draft_keeps_bcc_and_attachment_but_never_sends(settings):
    captured = {}

    class FakeIMAP:
        def append(self, folder, flags, date_time, payload):
            captured.update(folder=folder, flags=flags, payload=payload)
            return "OK", [b"APPEND completed"]

    client = ProtonBridgeClient(settings)

    @contextmanager
    def fake_connection():
        yield FakeIMAP()

    client.connection = fake_connection
    attachment = Attachment(
        upload_id="a" * 32,
        filename="brief.pdf",
        content_type="application/pdf",
        size_bytes=8,
        sha256="b" * 64,
        data=b"%PDF-1.7",
    )
    result = client.append_draft(
        to=("recipient@example.com",),
        cc=(),
        bcc=("private@example.com",),
        subject="Project brief",
        body_text="Please review the attachment.",
        attachments=(attachment,),
    )

    message = BytesParser(policy=policy.default).parsebytes(captured["payload"])
    assert captured["folder"] == "Drafts"
    assert captured["flags"] == "(\\Draft)"
    assert message["Bcc"] == "private@example.com"
    assert next(iter(message.iter_attachments())).get_filename() == "brief.pdf"
    assert result["sent"] is False
