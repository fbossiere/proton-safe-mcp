from __future__ import annotations

import base64
import hashlib
import os

import pytest

from proton_safe_mcp.attachments import AttachmentStore
from proton_safe_mcp.errors import AttachmentError


def _begin(store: AttachmentStore, data: bytes, filename: str = "brief.pdf") -> str:
    result = store.begin(
        filename,
        "application/pdf",
        len(data),
        hashlib.sha256(data).hexdigest(),
    )
    return result["upload_id"]


def test_chunked_upload_round_trip_and_consumption(settings):
    store = AttachmentStore(settings)
    data = b"%PDF-1.7\nsecure test document"
    upload_id = _begin(store, data)
    first, second = data[:10], data[10:]
    store.append_chunk(upload_id, 0, base64.b64encode(first).decode())
    store.append_chunk(upload_id, 1, base64.b64encode(second).decode())
    finished = store.finish(upload_id)

    attachment = store.load(finished["attachment_token"])
    assert attachment.filename == "brief.pdf"
    assert attachment.data == data
    assert attachment.sha256 == hashlib.sha256(data).hexdigest()

    store.consume(finished["attachment_token"])
    with pytest.raises(AttachmentError, match="Unknown"):
        store.load(finished["attachment_token"])


@pytest.mark.parametrize(
    "filename",
    ["../secret.pdf", "/var/local/secret.pdf", "a\\b.pdf", "."],
)
def test_paths_are_never_accepted(settings, filename):
    store = AttachmentStore(settings)
    with pytest.raises(AttachmentError):
        store.begin(filename, "application/pdf", 3, hashlib.sha256(b"abc").hexdigest())


def test_rejects_out_of_order_chunk(settings):
    store = AttachmentStore(settings)
    upload_id = _begin(store, b"abc")
    with pytest.raises(AttachmentError, match="Expected chunk_index 0"):
        store.append_chunk(upload_id, 1, base64.b64encode(b"abc").decode())


def test_hash_mismatch_destroys_upload(settings):
    store = AttachmentStore(settings)
    upload_id = store.begin("brief.pdf", "application/pdf", 3, hashlib.sha256(b"xyz").hexdigest())[
        "upload_id"
    ]
    store.append_chunk(upload_id, 0, base64.b64encode(b"abc").decode())
    with pytest.raises(AttachmentError, match="SHA-256"):
        store.finish(upload_id)
    assert not any(settings.uploads_dir.glob(f"{upload_id}.*"))


def test_rejects_mime_extension_mismatch(settings):
    store = AttachmentStore(settings)
    with pytest.raises(AttachmentError, match="content_type"):
        store.begin("brief.pdf", "application/zip", 3, hashlib.sha256(b"abc").hexdigest())


def test_short_os_writes_do_not_truncate_upload(settings, monkeypatch):
    original_write = os.write

    def short_write(fd, data):
        return original_write(fd, data[:3])

    monkeypatch.setattr("proton_safe_mcp.attachments.os.write", short_write)
    data = b"%PDF-1.7\nshort-write-test"
    store = AttachmentStore(settings)
    upload_id = _begin(store, data)
    store.append_chunk(upload_id, 0, base64.b64encode(data).decode())
    finished = store.finish(upload_id)
    assert store.load(finished["attachment_token"]).data == data
