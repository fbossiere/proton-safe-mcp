"""Bounded text extraction for selected received attachments."""

from __future__ import annotations

import io
import re
from typing import Any

from pypdf import PdfReader

from .errors import BridgeError

_PDF_MIME = "application/pdf"
_TEXT_MIME_TYPES = {"text/plain", "text/csv"}


def _clean_text(value: str) -> str:
    value = value.replace("\x00", "")
    value = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


class ReceivedAttachmentTextExtractor:
    """Extract text without returning attachment bytes or writing files."""

    supported_content_types = frozenset({_PDF_MIME, *_TEXT_MIME_TYPES})

    def extract(
        self,
        *,
        data: bytes,
        content_type: str,
        charset: str | None,
        max_chars: int,
        max_pages: int,
    ) -> dict[str, Any]:
        if content_type == _PDF_MIME:
            return self._extract_pdf(data=data, max_chars=max_chars, max_pages=max_pages)
        if content_type in _TEXT_MIME_TYPES:
            return self._extract_text(data=data, charset=charset, max_chars=max_chars)
        raise BridgeError("Attachment text extraction supports PDF, plain-text, and CSV files only")

    @staticmethod
    def _extract_text(*, data: bytes, charset: str | None, max_chars: int) -> dict[str, Any]:
        try:
            value = data.decode(charset or "utf-8", errors="replace")
        except LookupError:
            value = data.decode("utf-8", errors="replace")
        value = _clean_text(value)
        return {
            "text": value[:max_chars],
            "truncated": len(value) > max_chars,
            "pages_read": None,
            "total_pages": None,
        }

    @staticmethod
    def _extract_pdf(*, data: bytes, max_chars: int, max_pages: int) -> dict[str, Any]:
        if not data.startswith(b"%PDF-"):
            raise BridgeError("Attachment is not a valid PDF document")
        try:
            reader = PdfReader(io.BytesIO(data), strict=False)
            if reader.is_encrypted:
                raise BridgeError("Encrypted PDF attachments are not supported")
            total_pages = len(reader.pages)
            page_limit = min(total_pages, max_pages)
            parts: list[str] = []
            text_length = 0
            truncated = total_pages > max_pages
            pages_read = 0
            for page in reader.pages[:page_limit]:
                page_text = _clean_text(page.extract_text() or "")
                separator_length = 2 if parts and page_text else 0
                remaining = max_chars - text_length - separator_length
                if remaining <= 0:
                    truncated = True
                    break
                if page_text:
                    parts.append(page_text[:remaining])
                    text_length += min(len(page_text), remaining) + separator_length
                    if len(page_text) > remaining:
                        truncated = True
                        pages_read += 1
                        break
                pages_read += 1
            return {
                "text": "\n\n".join(parts)[:max_chars],
                "truncated": truncated,
                "pages_read": pages_read,
                "total_pages": total_pages,
            }
        except BridgeError:
            raise
        except Exception as exc:
            raise BridgeError("Unable to extract text from PDF attachment") from exc
