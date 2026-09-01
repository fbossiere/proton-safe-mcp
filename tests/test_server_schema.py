from __future__ import annotations

import asyncio
import importlib

from fastmcp import Client


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
