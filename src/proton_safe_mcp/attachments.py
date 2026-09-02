"""Client-neutral, chunked attachment staging with no filesystem path input."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Settings
from .errors import AttachmentError

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TOKEN_RE = re.compile(r"^([0-9a-f]{32})\.([A-Za-z0-9_-]{32,64})$")

ALLOWED_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def _write_all(fd: int, data: bytes) -> None:
    """Write every byte, including when the OS reports a short write."""
    remaining = memoryview(data)
    while remaining:
        written = os.write(fd, remaining)
        if written == 0:
            raise OSError("write returned zero bytes")
        remaining = remaining[written:]


@dataclass(frozen=True, slots=True)
class Attachment:
    upload_id: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    data: bytes


class AttachmentStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.RLock()

    def begin(
        self, filename: str, content_type: str, size_bytes: int, sha256_hex: str
    ) -> dict[str, Any]:
        self.cleanup_expired()
        canonical_type = self._validate_file_metadata(
            filename, content_type, size_bytes, sha256_hex
        )
        upload_id = uuid.uuid4().hex
        now = int(time.time())
        metadata = {
            "version": 1,
            "upload_id": upload_id,
            "filename": filename,
            "content_type": canonical_type,
            "expected_size": size_bytes,
            "expected_sha256": sha256_hex.lower(),
            "current_size": 0,
            "next_chunk": 0,
            "status": "uploading",
            "created_at": now,
            "expires_at": now + self.settings.upload_ttl_seconds,
        }
        with self._lock:
            self._write_bytes(self._blob_path(upload_id, partial=True), b"")
            self._write_json(self._meta_path(upload_id), metadata)
        return {
            "upload_id": upload_id,
            "max_chunk_bytes": self.settings.max_chunk_bytes,
            "expires_at": metadata["expires_at"],
        }

    def append_chunk(self, upload_id: str, chunk_index: int, data_base64: str) -> dict[str, Any]:
        self._validate_upload_id(upload_id)
        if chunk_index < 0:
            raise AttachmentError("chunk_index must be non-negative")
        try:
            chunk = base64.b64decode(data_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise AttachmentError("data_base64 is not valid base64") from exc
        if not chunk:
            raise AttachmentError("Empty chunks are not accepted")
        if len(chunk) > self.settings.max_chunk_bytes:
            raise AttachmentError(f"Decoded chunk exceeds {self.settings.max_chunk_bytes} bytes")

        with self._lock:
            metadata = self._read_meta(upload_id)
            self._assert_active(metadata, "uploading")
            if chunk_index != metadata["next_chunk"]:
                raise AttachmentError(
                    f"Expected chunk_index {metadata['next_chunk']}, received {chunk_index}"
                )
            new_size = metadata["current_size"] + len(chunk)
            if new_size > metadata["expected_size"]:
                raise AttachmentError("Chunk would exceed the declared attachment size")
            path = self._blob_path(upload_id, partial=True)
            flags = os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(path, flags)
            try:
                _write_all(fd, chunk)
                os.fsync(fd)
            finally:
                os.close(fd)
            metadata["current_size"] = new_size
            metadata["next_chunk"] += 1
            self._write_json(self._meta_path(upload_id), metadata)
            return {
                "upload_id": upload_id,
                "received_bytes": new_size,
                "expected_bytes": metadata["expected_size"],
                "next_chunk": metadata["next_chunk"],
            }

    def finish(self, upload_id: str) -> dict[str, Any]:
        self._validate_upload_id(upload_id)
        with self._lock:
            metadata = self._read_meta(upload_id)
            self._assert_active(metadata, "uploading")
            if metadata["current_size"] != metadata["expected_size"]:
                raise AttachmentError(
                    f"Expected {metadata['expected_size']} bytes, "
                    f"received {metadata['current_size']}"
                )
            partial = self._blob_path(upload_id, partial=True)
            actual_hash = self._sha256_file(partial)
            if not hmac.compare_digest(actual_hash, metadata["expected_sha256"]):
                self._destroy_upload(upload_id)
                raise AttachmentError("Attachment SHA-256 verification failed; upload discarded")

            ready = self._blob_path(upload_id, partial=False)
            os.replace(partial, ready)
            ready.chmod(0o600)
            secret = secrets.token_urlsafe(32)
            metadata.update(
                {
                    "status": "ready",
                    "token_hash": hashlib.sha256(secret.encode()).hexdigest(),
                    "sha256": actual_hash,
                }
            )
            self._write_json(self._meta_path(upload_id), metadata)
            return {
                "attachment_token": f"{upload_id}.{secret}",
                "filename": metadata["filename"],
                "content_type": metadata["content_type"],
                "size_bytes": metadata["expected_size"],
                "sha256": actual_hash,
                "expires_at": metadata["expires_at"],
            }

    def load(self, token: str) -> Attachment:
        upload_id, secret = self._parse_token(token)
        with self._lock:
            metadata = self._read_meta(upload_id)
            self._assert_active(metadata, "ready")
            candidate = hashlib.sha256(secret.encode()).hexdigest()
            if not hmac.compare_digest(candidate, metadata.get("token_hash", "")):
                raise AttachmentError("Invalid attachment token")
            path = self._blob_path(upload_id, partial=False)
            if not path.is_file() or path.is_symlink():
                raise AttachmentError("Staged attachment is unavailable")
            data = path.read_bytes()
            if len(data) != metadata["expected_size"]:
                raise AttachmentError("Staged attachment size changed")
            actual_hash = hashlib.sha256(data).hexdigest()
            if not hmac.compare_digest(actual_hash, metadata["sha256"]):
                raise AttachmentError("Staged attachment content changed")
            return Attachment(
                upload_id=upload_id,
                filename=metadata["filename"],
                content_type=metadata["content_type"],
                size_bytes=len(data),
                sha256=actual_hash,
                data=data,
            )

    def consume(self, token: str) -> None:
        """Destroy one staged upload, whether it was used by a draft or discarded."""
        upload_id, secret = self._parse_token(token)
        with self._lock:
            metadata = self._read_meta(upload_id)
            candidate = hashlib.sha256(secret.encode()).hexdigest()
            if not hmac.compare_digest(candidate, metadata.get("token_hash", "")):
                raise AttachmentError("Invalid attachment token")
            self._destroy_upload(upload_id)

    def cleanup_expired(self) -> None:
        now = int(time.time())
        with self._lock:
            for meta_path in self.settings.uploads_dir.glob("*.json"):
                try:
                    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
                    upload_id = metadata["upload_id"]
                    self._validate_upload_id(upload_id)
                    if metadata.get("expires_at", 0) < now:
                        self._destroy_upload(upload_id)
                except (OSError, ValueError, KeyError, json.JSONDecodeError):
                    # Do not follow or delete unknown files from a compromised directory.
                    continue

    def _validate_file_metadata(
        self, filename: str, content_type: str, size_bytes: int, sha256_hex: str
    ) -> str:
        """Return the canonical content type for an accepted filename, or raise."""
        if not filename or filename in {".", ".."}:
            raise AttachmentError("filename is required")
        if Path(filename).name != filename or "/" in filename or "\\" in filename:
            raise AttachmentError("filename must be a basename, not a path")
        if any(ord(ch) < 32 for ch in filename) or len(filename.encode("utf-8")) > 180:
            raise AttachmentError("filename contains control characters or is too long")
        extension = Path(filename).suffix.lower()
        canonical_type = ALLOWED_TYPES.get(extension)
        if not canonical_type:
            raise AttachmentError(f"File type {extension or '(none)'} is not allowed")
        if content_type not in {canonical_type, "application/octet-stream"}:
            raise AttachmentError(f"content_type must be {canonical_type} for a {extension} file")
        if not 1 <= size_bytes <= self.settings.max_attachment_bytes:
            raise AttachmentError(
                f"size_bytes must be between 1 and {self.settings.max_attachment_bytes}"
            )
        if not SHA256_RE.fullmatch(sha256_hex.lower()):
            raise AttachmentError("sha256_hex must contain exactly 64 hexadecimal characters")
        return canonical_type

    def _assert_active(self, metadata: dict[str, Any], status: str) -> None:
        if metadata.get("expires_at", 0) < int(time.time()):
            self._destroy_upload(metadata["upload_id"])
            raise AttachmentError("Attachment upload expired")
        if metadata.get("status") != status:
            raise AttachmentError(f"Attachment is not in the {status!r} state")

    @staticmethod
    def _validate_upload_id(upload_id: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{32}", upload_id):
            raise AttachmentError("Invalid upload_id")

    def _parse_token(self, token: str) -> tuple[str, str]:
        match = TOKEN_RE.fullmatch(token)
        if not match:
            raise AttachmentError("Invalid attachment token")
        return match.group(1), match.group(2)

    def _meta_path(self, upload_id: str) -> Path:
        return self.settings.uploads_dir / f"{upload_id}.json"

    def _blob_path(self, upload_id: str, *, partial: bool) -> Path:
        suffix = ".part" if partial else ".blob"
        return self.settings.uploads_dir / f"{upload_id}{suffix}"

    def _read_meta(self, upload_id: str) -> dict[str, Any]:
        path = self._meta_path(upload_id)
        if not path.is_file() or path.is_symlink():
            raise AttachmentError("Unknown attachment upload")
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AttachmentError("Attachment metadata is unreadable") from exc
        if not isinstance(metadata, dict):
            raise AttachmentError("Attachment metadata is malformed")
        return metadata

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _write_bytes(path: Path, data: bytes) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        try:
            _write_all(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        temporary = path.with_suffix(path.suffix + f".{secrets.token_hex(4)}.tmp")
        data = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
        AttachmentStore._write_bytes(temporary, data)
        os.replace(temporary, path)
        path.chmod(0o600)

    def _destroy_upload(self, upload_id: str) -> None:
        for path in (
            self._meta_path(upload_id),
            self._blob_path(upload_id, partial=True),
            self._blob_path(upload_id, partial=False),
        ):
            try:
                if path.is_file() and not path.is_symlink():
                    path.unlink()
            except FileNotFoundError:
                pass
