from __future__ import annotations

import pytest

from proton_safe_mcp.config import Settings


@pytest.fixture(autouse=True)
def _no_inherited_aliases(monkeypatch):
    """Keep the sender allowlist under test control, whatever the developer's shell exports."""
    monkeypatch.delenv("PROTON_BRIDGE_ALIASES", raising=False)


@pytest.fixture
def settings(tmp_path):
    value = Settings(
        bridge_user="user@example.com",
        sender_addresses=("user@example.com", "alias@example.com"),
        bridge_host="127.0.0.1",
        imap_port=1143,
        state_dir=tmp_path / "state",
        max_attachment_bytes=2 * 1024 * 1024,
        max_received_attachment_bytes=1024 * 1024,
        max_chunk_bytes=1024,
        upload_ttl_seconds=1800,
        max_body_chars=100_000,
    )
    value.ensure_directories()
    return value
