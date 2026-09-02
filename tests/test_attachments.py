from __future__ import annotations

import base64
import hashlib
import os
import time

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


@pytest.mark.parametrize(
    "token",
    ["0" * 32 + "." + "a" * 200, "0" * 32 + "." + "a" * 31, "not-a-token"],
)
def test_tokens_outside_the_issued_shape_are_rejected(settings, token):
    """Token parsing is bounded, so an oversized string never reaches the metadata lookup."""
    store = AttachmentStore(settings)
    with pytest.raises(AttachmentError, match="Invalid attachment token"):
        store.load(token)


def _finished(store: AttachmentStore, data: bytes = b"%PDF-1.7 doc") -> tuple[str, str]:
    """Drive one upload to the ready state and return its id and single-use token."""
    upload_id = _begin(store, data)
    store.append_chunk(upload_id, 0, base64.b64encode(data).decode())
    return upload_id, store.finish(upload_id)["attachment_token"]


@pytest.mark.parametrize(
    ("filename", "size_bytes", "expected"),
    [
        ("brief\x01.pdf", 3, "control characters or is too long"),
        ("x" * 181 + ".pdf", 3, "control characters or is too long"),
        ("brief.exe", 3, r"File type \.exe is not allowed"),
        ("brief", 3, r"File type \(none\) is not allowed"),
        ("brief.pdf", 0, "size_bytes must be between 1 and"),
        ("brief.pdf", 3 * 1024 * 1024, "size_bytes must be between 1 and"),
    ],
)
def test_begin_rejects_unusable_file_metadata(settings, filename, size_bytes, expected):
    store = AttachmentStore(settings)
    with pytest.raises(AttachmentError, match=expected):
        store.begin(filename, "application/pdf", size_bytes, hashlib.sha256(b"abc").hexdigest())


def test_begin_rejects_a_malformed_digest(settings):
    store = AttachmentStore(settings)
    with pytest.raises(AttachmentError, match="exactly 64 hexadecimal characters"):
        store.begin("brief.pdf", "application/pdf", 3, "not-a-digest")


def test_append_chunk_rejects_a_negative_index(settings):
    store = AttachmentStore(settings)
    upload_id = _begin(store, b"abc")
    with pytest.raises(AttachmentError, match="chunk_index must be non-negative"):
        store.append_chunk(upload_id, -1, base64.b64encode(b"abc").decode())


def test_append_chunk_rejects_data_that_is_not_base64(settings):
    store = AttachmentStore(settings)
    upload_id = _begin(store, b"abc")
    with pytest.raises(AttachmentError, match="not valid base64"):
        store.append_chunk(upload_id, 0, "not base64!!")


def test_append_chunk_rejects_an_empty_chunk(settings):
    store = AttachmentStore(settings)
    upload_id = _begin(store, b"abc")
    with pytest.raises(AttachmentError, match="Empty chunks are not accepted"):
        store.append_chunk(upload_id, 0, "")


def test_append_chunk_rejects_a_chunk_over_the_configured_maximum(settings):
    store = AttachmentStore(settings)
    oversized = b"x" * (settings.max_chunk_bytes + 1)
    upload_id = _begin(store, oversized)
    with pytest.raises(AttachmentError, match="Decoded chunk exceeds"):
        store.append_chunk(upload_id, 0, base64.b64encode(oversized).decode())


def test_append_chunk_cannot_exceed_the_declared_size(settings):
    store = AttachmentStore(settings)
    upload_id = _begin(store, b"abc")
    with pytest.raises(AttachmentError, match="exceed the declared attachment size"):
        store.append_chunk(upload_id, 0, base64.b64encode(b"abcd").decode())


def test_finish_requires_the_declared_byte_count(settings):
    store = AttachmentStore(settings)
    upload_id = _begin(store, b"abc")
    store.append_chunk(upload_id, 0, base64.b64encode(b"ab").decode())
    with pytest.raises(AttachmentError, match="Expected 3 bytes, received 2"):
        store.finish(upload_id)


def test_finish_is_not_repeatable(settings):
    store = AttachmentStore(settings)
    upload_id, _ = _finished(store)
    with pytest.raises(AttachmentError, match="not in the 'uploading' state"):
        store.finish(upload_id)


@pytest.mark.parametrize("upload_id", ["not-hex", "0" * 31, "0" * 33, "A" * 32])
def test_upload_ids_outside_the_issued_shape_are_rejected(settings, upload_id):
    store = AttachmentStore(settings)
    with pytest.raises(AttachmentError, match="Invalid upload_id"):
        store.finish(upload_id)


def test_a_forged_token_secret_neither_loads_nor_destroys_the_upload(settings):
    store = AttachmentStore(settings)
    upload_id, token = _finished(store)
    forged = f"{upload_id}.{'z' * 43}"

    with pytest.raises(AttachmentError, match="Invalid attachment token"):
        store.load(forged)
    with pytest.raises(AttachmentError, match="Invalid attachment token"):
        store.consume(forged)

    # The genuine token still works, so a forged secret cannot destroy staged bytes either.
    store.consume(token)


def test_load_reports_a_staged_blob_that_disappeared(settings):
    store = AttachmentStore(settings)
    upload_id, token = _finished(store)
    store._blob_path(upload_id, partial=False).unlink()
    with pytest.raises(AttachmentError, match="Staged attachment is unavailable"):
        store.load(token)


def test_load_rejects_staged_bytes_whose_length_changed(settings):
    store = AttachmentStore(settings)
    upload_id, token = _finished(store)
    store._blob_path(upload_id, partial=False).write_bytes(b"short")
    with pytest.raises(AttachmentError, match="Staged attachment size changed"):
        store.load(token)


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [("not json at all", "metadata is unreadable"), ("[]", "metadata is malformed")],
)
def test_unusable_metadata_never_yields_an_attachment(settings, metadata, expected):
    store = AttachmentStore(settings)
    upload_id, token = _finished(store)
    store._meta_path(upload_id).write_text(metadata, encoding="utf-8")
    with pytest.raises(AttachmentError, match=expected):
        store.load(token)


def test_an_expired_upload_is_refused_and_its_bytes_are_removed(settings, monkeypatch):
    store = AttachmentStore(settings)
    upload_id = _begin(store, b"abc")

    expired = time.time() + settings.upload_ttl_seconds + 1
    monkeypatch.setattr("proton_safe_mcp.attachments.time.time", lambda: expired)

    with pytest.raises(AttachmentError, match="Attachment upload expired"):
        store.append_chunk(upload_id, 0, base64.b64encode(b"abc").decode())
    assert not any(settings.uploads_dir.glob(f"{upload_id}.*"))


def test_cleanup_removes_expired_uploads_and_leaves_foreign_files_alone(settings, monkeypatch):
    store = AttachmentStore(settings)
    upload_id = _begin(store, b"abc")
    # A file this server did not write must never be followed or deleted.
    foreign = settings.uploads_dir / "unrelated.json"
    foreign.write_text("{}", encoding="utf-8")

    expired = time.time() + settings.upload_ttl_seconds + 1
    monkeypatch.setattr("proton_safe_mcp.attachments.time.time", lambda: expired)
    store.cleanup_expired()

    assert not any(settings.uploads_dir.glob(f"{upload_id}.*"))
    assert foreign.exists()


def test_cleanup_keeps_an_upload_that_has_not_expired(settings):
    store = AttachmentStore(settings)
    upload_id = _begin(store, b"abc")

    store.cleanup_expired()

    assert store._meta_path(upload_id).is_file()
    assert store._blob_path(upload_id, partial=True).is_file()
