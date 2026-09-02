"""Draft validation plus optional out-of-band local approval."""

from __future__ import annotations

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
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from .attachments import Attachment
from .config import Settings
from .errors import ApprovalError


def _write_all(fd: int, data: bytes) -> None:
    """Write every byte, including when the OS reports a short write."""
    remaining = memoryview(data)
    while remaining:
        written = os.write(fd, remaining)
        if written == 0:
            raise OSError("write returned zero bytes")
        remaining = remaining[written:]


def validate_address(value: str) -> str:
    if not isinstance(value, str) or not value or "\r" in value or "\n" in value:
        raise ApprovalError("Invalid email address")
    display, address = parseaddr(value)
    if display or address != value.strip() or len(address) > 254:
        raise ApprovalError(f"Use a bare email address, without display name: {value!r}")
    if address.count("@") != 1:
        raise ApprovalError(f"Invalid email address: {value!r}")
    local, domain = address.rsplit("@", 1)
    if not local or not domain or "." not in domain or " " in address:
        raise ApprovalError(f"Invalid email address: {value!r}")
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+", local):
        raise ApprovalError(f"Unsupported email address syntax: {value!r}")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", domain) or ".." in domain:
        raise ApprovalError(f"Invalid email domain: {value!r}")
    return address


@dataclass(frozen=True, slots=True)
class DraftContent:
    to: tuple[str, ...]
    cc: tuple[str, ...]
    bcc: tuple[str, ...]
    subject: str
    body_text: str
    attachment_tokens: tuple[str, ...]
    attachments: tuple[Attachment, ...]


@dataclass(frozen=True, slots=True)
class DraftProposal(DraftContent):
    draft_id: str
    digest: str
    created_at: int
    expires_at: int


def validate_draft(
    settings: Settings,
    *,
    to: list[str],
    cc: list[str],
    bcc: list[str],
    subject: str,
    body_text: str,
    attachment_tokens: list[str],
    attachments: list[Attachment],
) -> DraftContent:
    """Validate and freeze the exact content of a draft before any IMAP write."""
    recipients = tuple(validate_address(item) for item in to)
    cc_values = tuple(validate_address(item) for item in cc)
    bcc_values = tuple(validate_address(item) for item in bcc)
    if not recipients:
        raise ApprovalError("At least one To recipient is required")
    if len(recipients) + len(cc_values) + len(bcc_values) > 25:
        raise ApprovalError("A draft may contain at most 25 recipients")
    if "\r" in subject or "\n" in subject or len(subject) > 998:
        raise ApprovalError("Subject contains a line break or is too long")
    if not body_text or len(body_text) > settings.max_body_chars:
        raise ApprovalError(f"body_text must contain 1 to {settings.max_body_chars} characters")
    if len(attachment_tokens) != len(attachments):
        raise ApprovalError("Attachment token resolution mismatch")
    if len(attachments) > 10:
        raise ApprovalError("A draft may contain at most 10 attachments")
    if sum(item.size_bytes for item in attachments) > settings.max_attachment_bytes:
        raise ApprovalError("Combined attachment size exceeds the configured per-draft maximum")
    if len({item.upload_id for item in attachments}) != len(attachments):
        raise ApprovalError("Duplicate attachments are not allowed")
    return DraftContent(
        to=recipients,
        cc=cc_values,
        bcc=bcc_values,
        subject=subject,
        body_text=body_text,
        attachment_tokens=tuple(attachment_tokens),
        attachments=tuple(attachments),
    )


class DraftApprovalStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._pending: dict[str, DraftProposal] = {}
        self._lock = threading.RLock()

    def prepare(
        self,
        *,
        to: list[str],
        cc: list[str],
        bcc: list[str],
        subject: str,
        body_text: str,
        attachment_tokens: list[str],
        attachments: list[Attachment],
    ) -> dict[str, Any]:
        content = validate_draft(
            self.settings,
            to=to,
            cc=cc,
            bcc=bcc,
            subject=subject,
            body_text=body_text,
            attachment_tokens=attachment_tokens,
            attachments=attachments,
        )

        now = int(time.time())
        expires_at = now + self.settings.draft_ttl_seconds
        draft_id = uuid.uuid4().hex
        canonical = {
            "draft_id": draft_id,
            "to": content.to,
            "cc": content.cc,
            "bcc": content.bcc,
            "subject": subject,
            "body_sha256": hashlib.sha256(body_text.encode("utf-8")).hexdigest(),
            "attachments": [
                {"filename": item.filename, "size_bytes": item.size_bytes, "sha256": item.sha256}
                for item in attachments
            ],
            "created_at": now,
            "expires_at": expires_at,
        }
        digest = hashlib.sha256(
            json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        proposal = DraftProposal(
            draft_id=draft_id,
            to=content.to,
            cc=content.cc,
            bcc=content.bcc,
            subject=content.subject,
            body_text=content.body_text,
            attachment_tokens=content.attachment_tokens,
            attachments=content.attachments,
            digest=digest,
            created_at=now,
            expires_at=expires_at,
        )
        request = {
            **canonical,
            "digest": digest,
            "body_preview": body_text[:500],
            "status": "pending",
        }
        with self._lock:
            self._pending[draft_id] = proposal
            self._write_json(self.request_path(draft_id), request)
        return {
            "draft_id": draft_id,
            "digest": digest,
            "expires_at": proposal.expires_at,
            "approval_command": f"proton-safe-mcp approve {draft_id}",
            "summary": request,
        }

    def get_approved(self, draft_id: str) -> DraftProposal:
        self._validate_id(draft_id)
        with self._lock:
            proposal = self._pending.get(draft_id)
            if not proposal:
                raise ApprovalError("Unknown draft proposal or server was restarted")
            if proposal.expires_at < int(time.time()):
                self.remove(draft_id)
                raise ApprovalError("Draft proposal expired")
            if self.rejection_path(draft_id).is_file():
                raise ApprovalError("Draft proposal was rejected locally")
            marker = self.approval_path(draft_id)
            if not marker.is_file() or marker.is_symlink():
                raise ApprovalError(
                    f"Local approval required. Run `proton-safe-mcp approve {draft_id}`."
                )
            try:
                approval = json.loads(marker.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ApprovalError("Approval marker is unreadable") from exc
            if approval.get("expires_at", 0) < int(time.time()):
                raise ApprovalError("Local approval expired")
            if not hmac.compare_digest(approval.get("digest", ""), proposal.digest):
                raise ApprovalError("Approval does not match the current draft proposal")
            return proposal

    def remove(self, draft_id: str) -> None:
        self._validate_id(draft_id)
        with self._lock:
            self._pending.pop(draft_id, None)
            for path in (
                self.request_path(draft_id),
                self.approval_path(draft_id),
                self.rejection_path(draft_id),
            ):
                try:
                    if path.is_file() and not path.is_symlink():
                        path.unlink()
                except FileNotFoundError:
                    pass

    def request_path(self, draft_id: str) -> Path:
        self._validate_id(draft_id)
        return self.settings.approvals_dir / f"{draft_id}.request.json"

    def approval_path(self, draft_id: str) -> Path:
        self._validate_id(draft_id)
        return self.settings.approvals_dir / f"{draft_id}.approved.json"

    def rejection_path(self, draft_id: str) -> Path:
        self._validate_id(draft_id)
        return self.settings.approvals_dir / f"{draft_id}.rejected"

    @staticmethod
    def _validate_id(draft_id: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{32}", draft_id):
            raise ApprovalError("Invalid draft_id")

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        temporary = path.with_suffix(path.suffix + f".{secrets.token_hex(4)}.tmp")
        data = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(temporary, flags, 0o600)
        try:
            _write_all(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temporary, path)
        path.chmod(0o600)


def approve_request(settings: Settings, draft_id: str) -> dict[str, Any]:
    DraftApprovalStore._validate_id(draft_id)
    request_path = settings.approvals_dir / f"{draft_id}.request.json"
    if not request_path.is_file() or request_path.is_symlink():
        raise ApprovalError("Unknown or expired draft request")
    request = json.loads(request_path.read_text(encoding="utf-8"))
    if not isinstance(request, dict):
        raise ApprovalError("Draft request file is malformed")
    if request.get("expires_at", 0) < int(time.time()):
        raise ApprovalError("Draft request expired")
    marker = {
        "draft_id": draft_id,
        "digest": request["digest"],
        "approved_at": int(time.time()),
        "expires_at": request["expires_at"],
    }
    DraftApprovalStore._write_json(settings.approvals_dir / f"{draft_id}.approved.json", marker)
    return request


def reject_request(settings: Settings, draft_id: str) -> None:
    DraftApprovalStore._validate_id(draft_id)
    path = settings.approvals_dir / f"{draft_id}.rejected"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        return
    try:
        _write_all(fd, b"rejected\n")
        os.fsync(fd)
    finally:
        os.close(fd)
