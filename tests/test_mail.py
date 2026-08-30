from __future__ import annotations

import imaplib
from contextlib import contextmanager
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser

import pytest

from proton_safe_mcp.attachments import Attachment
from proton_safe_mcp.errors import BridgeError
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


def test_malformed_multipart_is_parsed_as_bounded_plain_text():
    raw = (
        b'MIME-Version: 1.0\r\nContent-Type: multipart/mixed; boundary="expected"\r\n\r\n'
        b"--expected\r\nContent-Type: text/plain\r\n\r\nReadable\x00 text\r\n"
        b"--unexpected--\r\n"
    )
    message = BytesParser(policy=policy.default).parsebytes(raw)

    text = ProtonBridgeClient._body_as_text(message)

    assert "Readable text" in text
    assert "--unexpected--" in text
    assert len(text) < 100
    assert "\x00" not in text


def test_unknown_charset_falls_back_without_exposing_bytes():
    raw = (
        b"Content-Type: text/plain; charset=x-attacker-controlled\r\n"
        b"Content-Transfer-Encoding: 8bit\r\n\r\nHello \xff world"
    )
    message = BytesParser(policy=policy.default).parsebytes(raw)

    text = ProtonBridgeClient._body_as_text(message)

    assert text.startswith("Hello ")
    assert text.endswith(" world")
    assert "b'" not in text


@pytest.mark.parametrize("html_body", [False, True])
def test_read_message_bounds_oversized_text_and_never_returns_attachment_bytes(settings, html_body):
    message = EmailMessage()
    content = "visible " * 1_000
    if html_body:
        message.set_content(f"<p>{content}</p><script>hidden()</script>", subtype="html")
    else:
        message.set_content(content)
    message.add_attachment(
        b"ATTACHMENT-SECRET-BYTES",
        maintype="application",
        subtype="octet-stream",
        filename="payload.bin",
    )

    class FakeIMAP:
        def select(self, _folder, *, readonly):
            assert readonly is True
            return "OK", [b"1"]

        def uid(self, command, uid, fields):
            assert (command, uid, fields) == ("FETCH", "42", "(BODY.PEEK[] FLAGS)")
            return "OK", [(b"42 (BODY[]", message.as_bytes()), b")"]

    client = ProtonBridgeClient(settings)

    @contextmanager
    def fake_connection():
        yield FakeIMAP()

    client.connection = fake_connection
    result = client.read_message("42", max_chars=500)

    assert len(result["body_text"]) == 500
    assert result["truncated"] is True
    assert "ATTACHMENT-SECRET-BYTES" not in repr(result)
    assert result["attachments"] == [
        {
            "filename": "payload.bin",
            "content_type": "application/octet-stream",
            "size_bytes": 23,
        }
    ]
    assert "<p>" not in result["body_text"]
    assert "hidden()" not in result["body_text"]


def test_byte_valued_status_and_fetch_responses_are_normalized(settings):
    header = (
        b"From: sender@example.com\r\n"
        b"To: user@example.com\r\n"
        b"Subject: Byte response\r\n"
        b"Message-ID: <1@example.com>\r\n\r\n"
    )

    class FakeIMAP:
        def status(self, mailbox, fields):
            assert (mailbox, fields) == ("INBOX", "(MESSAGES UNSEEN)")
            return "OK", [b"INBOX (MESSAGES 12 UNSEEN 3)"]

        def select(self, _folder, *, readonly):
            assert readonly is True
            return "OK", [b"12"]

        def uid(self, command, *args):
            if command == "SEARCH":
                assert args == ("ALL",)
                return "OK", [b"7"]
            assert command == "FETCH"
            return "OK", [
                (b"7 (BODY[HEADER.FIELDS] {120}", header),
                b" FLAGS () RFC822.SIZE 456)",
            ]

    client = ProtonBridgeClient(settings)

    @contextmanager
    def fake_connection():
        yield FakeIMAP()

    client.connection = fake_connection

    assert client.status()["inbox_unread"] == 3
    assert client.list_messages(limit=1) == [
        {
            "uid": "7",
            "from": "sender@example.com",
            "to": "user@example.com",
            "subject": "Byte response",
            "date": "",
            "message_id": "<1@example.com>",
            "unread": True,
            "size_bytes": 456,
        }
    ]


def test_transient_disconnect_is_private_and_next_call_reconnects(monkeypatch, settings):
    attempts = 0
    abort_error = imaplib.IMAP4.abort

    class FakeIMAP:
        error = imaplib.IMAP4.error
        capabilities = (b"IMAP4REV1",)

        def __init__(self, *_args, **_kwargs):
            nonlocal attempts
            attempts += 1
            self.attempt = attempts

        def starttls(self, *, ssl_context):
            return "OK", [b"Begin TLS"]

        def login(self, user, password):
            assert password
            return "OK", [b"Logged in"]

        def status(self, _mailbox, _fields):
            if self.attempt == 1:
                raise abort_error("attacker text bridge-secret /home/private")
            return "OK", [b"INBOX (MESSAGES 2 UNSEEN 1)"]

        def logout(self):
            return "BYE", [b"Logged out"]

    monkeypatch.setattr("proton_safe_mcp.mail.get_bridge_password", lambda _user: "bridge-secret")
    monkeypatch.setattr("proton_safe_mcp.mail.imaplib.IMAP4", FakeIMAP)
    client = ProtonBridgeClient(settings)

    with pytest.raises(BridgeError) as caught:
        client.status()

    assert str(caught.value) == "Proton Bridge connection closed unexpectedly"
    assert "bridge-secret" not in str(caught.value)
    assert "/home/private" not in str(caught.value)
    assert client.status()["inbox_unread"] == 1
    assert attempts == 2


def test_reconnect_failure_is_bounded_and_private(monkeypatch, settings):
    def fail_to_connect(*_args, **_kwargs):
        raise OSError("bridge-secret at /home/private/socket")

    monkeypatch.setattr("proton_safe_mcp.mail.get_bridge_password", lambda _user: "bridge-secret")
    monkeypatch.setattr("proton_safe_mcp.mail.imaplib.IMAP4", fail_to_connect)

    with pytest.raises(BridgeError) as caught:
        ProtonBridgeClient(settings).status()

    assert str(caught.value) == "Proton Bridge connection failed"
    assert len(str(caught.value)) < 100
    assert "bridge-secret" not in str(caught.value)
    assert "/home/private" not in str(caught.value)


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
