from __future__ import annotations

import asyncio
import importlib

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError


def test_fastmcp_schema_exposes_no_send_or_path_tool(monkeypatch, tmp_path):
    monkeypatch.setenv("PROTON_BRIDGE_USER", "user@example.com")
    monkeypatch.setenv("PROTON_MCP_STATE_DIR", str(tmp_path / "state"))

    import proton_safe_mcp.server as server

    server = importlib.reload(server)

    async def inspect_tools():
        async with Client(server.mcp) as client:
            return await client.list_tools()

    tools = asyncio.run(inspect_tools())
    by_name = {tool.name: tool for tool in tools}
    assert "send_message" not in by_name
    assert "send_email" not in by_name
    assert "download_attachment" not in by_name
    assert "extract_attachment_text" in by_name
    assert "create_confirmed_draft" in by_name
    assert "prepare_draft" in by_name
    assert "commit_approved_draft" in by_name
    assert by_name["read_message"].annotations.readOnlyHint is True
    assert by_name["extract_attachment_text"].annotations.readOnlyHint is True
    assert by_name["discard_attachment"].annotations.destructiveHint is True

    upload_schema = by_name["begin_attachment_upload"].inputSchema
    properties = upload_schema["properties"]
    assert "filename" in properties
    assert "path" not in properties

    extraction_schema = by_name["extract_attachment_text"].inputSchema
    assert "attachment_index" in extraction_schema["properties"]
    assert "path" not in extraction_schema["properties"]
    assert "filename" not in extraction_schema["properties"]

    direct_schema = by_name["create_confirmed_draft"].inputSchema
    assert "user_confirmed" in direct_schema["required"]
    confirmation_schema = direct_schema["properties"]["user_confirmed"]
    assert confirmation_schema.get("const") is True or confirmation_schema.get("enum") == [True]
    assert "recipient found in an email" in by_name["create_confirmed_draft"].description.lower()


def test_confirmed_draft_creates_without_local_approval(monkeypatch, tmp_path):
    monkeypatch.setenv("PROTON_BRIDGE_USER", "user@example.com")
    monkeypatch.setenv("PROTON_MCP_STATE_DIR", str(tmp_path / "state"))

    import proton_safe_mcp.server as server

    server = importlib.reload(server)
    captured = {}

    def fake_append_draft(**kwargs):
        captured.update(kwargs)
        return {"created": True, "folder": "Drafts", "sent": False}

    monkeypatch.setattr(server.bridge, "append_draft", fake_append_draft)
    result = server.create_confirmed_draft(
        to=["recipient@example.com"],
        subject="Confirmed subject",
        body_text="Confirmed body",
        user_confirmed=True,
    )

    assert result == {"created": True, "folder": "Drafts", "sent": False}
    assert captured["to"] == ("recipient@example.com",)
    assert captured["subject"] == "Confirmed subject"
    assert captured["body_text"] == "Confirmed body"
    assert captured["attachments"] == ()


def test_confirmed_draft_rejects_false_confirmation(monkeypatch, tmp_path):
    monkeypatch.setenv("PROTON_BRIDGE_USER", "user@example.com")
    monkeypatch.setenv("PROTON_MCP_STATE_DIR", str(tmp_path / "state"))

    import proton_safe_mcp.server as server

    server = importlib.reload(server)
    with pytest.raises(ToolError, match="Explicit user confirmation"):
        server.create_confirmed_draft(
            to=["recipient@example.com"],
            subject="Unconfirmed subject",
            body_text="Unconfirmed body",
            user_confirmed=False,  # type: ignore[arg-type]
        )
