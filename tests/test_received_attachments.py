from __future__ import annotations

import io

import pytest
from pypdf import PdfWriter

from proton_safe_mcp.errors import BridgeError
from proton_safe_mcp.received_attachments import ReceivedAttachmentTextExtractor


def test_plain_text_is_sanitized_and_bounded():
    result = ReceivedAttachmentTextExtractor().extract(
        data=b"first\x00 line\n\n\nsecond line",
        content_type="text/plain",
        charset="utf-8",
        max_chars=13,
        max_pages=50,
    )

    assert result == {
        "text": "first line\n\ns",
        "truncated": True,
        "pages_read": None,
        "total_pages": None,
    }


def test_pdf_extraction_is_page_and_character_bounded(monkeypatch):
    class FakePage:
        def __init__(self, text: str):
            self.text = text

        def extract_text(self):
            return self.text

    class FakeReader:
        def __init__(self):
            self.is_encrypted = False
            self.pages = [FakePage("page one"), FakePage("page two"), FakePage("page three")]

    monkeypatch.setattr(
        "proton_safe_mcp.received_attachments.PdfReader", lambda *_args, **_kwargs: FakeReader()
    )

    result = ReceivedAttachmentTextExtractor().extract(
        data=b"%PDF-1.7 fake",
        content_type="application/pdf",
        charset=None,
        max_chars=500,
        max_pages=2,
    )

    assert result["text"] == "page one\n\npage two"
    assert result["pages_read"] == 2
    assert result["total_pages"] == 3
    assert result["truncated"] is True


def test_real_blank_pdf_is_parsed_in_memory():
    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(output)

    result = ReceivedAttachmentTextExtractor().extract(
        data=output.getvalue(),
        content_type="application/pdf",
        charset=None,
        max_chars=500,
        max_pages=1,
    )

    assert result == {
        "text": "",
        "truncated": False,
        "pages_read": 1,
        "total_pages": 1,
    }


def test_pdf_header_may_appear_within_first_1024_bytes(monkeypatch):
    class EmptyReader:
        def __init__(self):
            self.is_encrypted = False
            self.pages = []

    monkeypatch.setattr(
        "proton_safe_mcp.received_attachments.PdfReader",
        lambda *_args, **_kwargs: EmptyReader(),
    )

    result = ReceivedAttachmentTextExtractor().extract(
        data=b"leading bytes\n%PDF-1.7 fake",
        content_type="application/pdf",
        charset=None,
        max_chars=500,
        max_pages=1,
    )

    assert result["total_pages"] == 0


def test_pdf_magic_and_encryption_are_rejected(monkeypatch):
    extractor = ReceivedAttachmentTextExtractor()
    with pytest.raises(BridgeError, match="valid PDF"):
        extractor.extract(
            data=b"not a pdf",
            content_type="application/pdf",
            charset=None,
            max_chars=500,
            max_pages=1,
        )

    with pytest.raises(BridgeError, match="valid PDF"):
        extractor.extract(
            data=b"x" * 1024 + b"%PDF-1.7",
            content_type="application/pdf",
            charset=None,
            max_chars=500,
            max_pages=1,
        )

    class EncryptedReader:
        def __init__(self):
            self.is_encrypted = True
            self.pages = []

    monkeypatch.setattr(
        "proton_safe_mcp.received_attachments.PdfReader",
        lambda *_args, **_kwargs: EncryptedReader(),
    )
    with pytest.raises(BridgeError, match="Encrypted PDF"):
        extractor.extract(
            data=b"%PDF-1.7 fake",
            content_type="application/pdf",
            charset=None,
            max_chars=500,
            max_pages=1,
        )


def test_pdf_parser_details_are_not_exposed(monkeypatch):
    def fail_reader(*_args, **_kwargs):
        raise ValueError("sensitive parser detail")

    monkeypatch.setattr("proton_safe_mcp.received_attachments.PdfReader", fail_reader)

    with pytest.raises(BridgeError) as exc_info:
        ReceivedAttachmentTextExtractor().extract(
            data=b"%PDF-1.7 fake",
            content_type="application/pdf",
            charset=None,
            max_chars=500,
            max_pages=1,
        )

    assert str(exc_info.value) == "Unable to extract text from PDF attachment"


def test_active_or_binary_formats_are_not_extracted():
    with pytest.raises(BridgeError, match="supports PDF"):
        ReceivedAttachmentTextExtractor().extract(
            data=b"PK",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            charset=None,
            max_chars=500,
            max_pages=1,
        )


def _fake_pdf(monkeypatch, *page_texts: str) -> None:
    """Replace PdfReader with a reader whose pages return exactly `page_texts`."""

    class FakePage:
        def __init__(self, text: str):
            self.text = text

        def extract_text(self):
            return self.text

    class FakeReader:
        def __init__(self):
            self.is_encrypted = False
            self.pages = [FakePage(text) for text in page_texts]

    monkeypatch.setattr(
        "proton_safe_mcp.received_attachments.PdfReader", lambda *_args, **_kwargs: FakeReader()
    )


def test_unknown_attachment_charset_falls_back_to_utf8():
    # The charset comes from an attacker-controlled MIME header, so an unknown value
    # must degrade to a UTF-8 read rather than raise.
    result = ReceivedAttachmentTextExtractor().extract(
        data="café".encode(),
        content_type="text/plain",
        charset="x-attacker-controlled",
        max_chars=50,
        max_pages=1,
    )

    assert result["text"] == "café"
    assert result["truncated"] is False


def test_pdf_extraction_stops_when_the_character_budget_is_spent(monkeypatch):
    _fake_pdf(monkeypatch, "aaaa", "bbbb")

    result = ReceivedAttachmentTextExtractor().extract(
        data=b"%PDF-1.7 fake",
        content_type="application/pdf",
        charset=None,
        max_chars=6,
        max_pages=50,
    )

    # The second page cannot fit even its separator, so it is reported as truncated.
    assert result == {"text": "aaaa", "truncated": True, "pages_read": 1, "total_pages": 2}


def test_pdf_extraction_truncates_inside_an_oversized_page(monkeypatch):
    _fake_pdf(monkeypatch, "aaaaaaaa")

    result = ReceivedAttachmentTextExtractor().extract(
        data=b"%PDF-1.7 fake",
        content_type="application/pdf",
        charset=None,
        max_chars=4,
        max_pages=50,
    )

    assert result == {"text": "aaaa", "truncated": True, "pages_read": 1, "total_pages": 1}
