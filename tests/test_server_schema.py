from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from proton_safe_mcp.errors import AttachmentError, BridgeError


@pytest.fixture
def server(monkeypatch, tmp_path):
    """Reload the tool surface against a throwaway state directory."""
    monkeypatch.setenv("PROTON_BRIDGE_USER", "user@example.com")
    monkeypatch.setenv("PROTON_BRIDGE_ALIASES", "alias@example.com")
    monkeypatch.setenv("PROTON_MCP_STATE_DIR", str(tmp_path / "state"))

    import proton_safe_mcp.server as module

    return importlib.reload(module)


def _stage_attachment(store, data=b"quarterly numbers", filename="brief.txt"):
    """Push bytes through the real chunked upload path and return its token."""
    begun = store.begin(filename, "text/plain", len(data), hashlib.sha256(data).hexdigest())
    store.append_chunk(begun["upload_id"], 0, base64.b64encode(data).decode("ascii"))
    finished = store.finish(begun["upload_id"])
    return begun["upload_id"], finished["attachment_token"]


def _recording_append_draft(captured):
    def fake_append_draft(**kwargs):
        captured.update(kwargs)
        return {
            "created": True,
            "folder": "Drafts",
            "attachment_names": [item.filename for item in kwargs["attachments"]],
            "sent": False,
        }

    return fake_append_draft


def _refusing_append_draft(**_kwargs):
    raise AssertionError("append_draft must not be reached")


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
    assert set(by_name) == {
        "mailbox_status",
        "list_folders",
        "list_sender_addresses",
        "list_messages",
        "search_messages",
        "read_message",
        "extract_attachment_text",
        "get_reply_context",
        "begin_attachment_upload",
        "upload_attachment_chunk",
        "finish_attachment_upload",
        "discard_attachment",
        "create_confirmed_draft",
    }
    assert by_name["read_message"].annotations.readOnlyHint is True
    assert by_name["extract_attachment_text"].annotations.readOnlyHint is True
    assert by_name["get_reply_context"].annotations.readOnlyHint is True
    assert by_name["discard_attachment"].annotations.destructiveHint is True

    upload_schema = by_name["begin_attachment_upload"].inputSchema
    properties = upload_schema["properties"]
    assert "filename" in properties
    assert "path" not in properties

    extraction_schema = by_name["extract_attachment_text"].inputSchema
    assert "attachment_index" in extraction_schema["properties"]
    assert "path" not in extraction_schema["properties"]
    assert "filename" not in extraction_schema["properties"]

    for tool in tools:
        assert "path" not in tool.inputSchema.get("properties", {})

    assert by_name["list_sender_addresses"].annotations.readOnlyHint is True

    direct_schema = by_name["create_confirmed_draft"].inputSchema
    assert "from_address" in direct_schema["properties"]
    assert "from_address" not in direct_schema["required"]
    assert "user_confirmed" in direct_schema["required"]
    confirmation_schema = direct_schema["properties"]["user_confirmed"]
    assert confirmation_schema.get("const") is True or confirmation_schema.get("enum") == [True]
    assert "recipient found in an email" in by_name["create_confirmed_draft"].description.lower()

    # Replying is threading only: the reply inputs are optional and carry no recipient.
    for name in ("reply_to_uid", "reply_to_folder", "reply_to_message_id"):
        assert name in direct_schema["properties"]
        assert name not in direct_schema["required"]

    reply_context = by_name["get_reply_context"]
    assert "confirmed recipient" in reply_context.description.lower()
    assert set(reply_context.inputSchema["required"]) == {"uid"}


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


def test_bridge_failure_is_translated_into_a_tool_error(server, monkeypatch):
    def fail():
        raise BridgeError("Proton Bridge connection failed")

    monkeypatch.setattr(server.bridge, "status", fail)

    with pytest.raises(ToolError, match="Proton Bridge connection failed"):
        server.mailbox_status()


def test_read_only_tools_forward_their_bounded_arguments(server, monkeypatch):
    calls: dict[str, tuple] = {}

    def record(name, result):
        def fake(*args):
            calls[name] = args
            return result

        return fake

    monkeypatch.setattr(server.bridge, "list_folders", record("list_folders", ["INBOX", "Sent"]))
    monkeypatch.setattr(server.bridge, "list_messages", record("list_messages", []))
    monkeypatch.setattr(server.bridge, "search_messages", record("search_messages", []))
    monkeypatch.setattr(server.bridge, "read_message", record("read_message", {"uid": "42"}))
    monkeypatch.setattr(server.bridge, "extract_attachment_text", record("extract", {"text": ""}))
    monkeypatch.setattr(
        server.bridge, "fetch_reply_context", record("reply_context", {"uid": "42"})
    )

    assert server.list_folders() == ["INBOX", "Sent"]
    server.list_messages(folder="Archive", limit=5, unread_only=True)
    server.search_messages(query="invoice", folder="Archive", limit=5)
    server.read_message(uid="42", folder="Archive", max_chars=500)
    server.extract_attachment_text(
        uid="42", attachment_index=1, folder="Archive", max_chars=500, max_pages=3
    )
    server.get_reply_context(uid="42", folder="Archive", max_quote_chars=800)

    assert calls["list_messages"] == ("Archive", 5, True)
    assert calls["search_messages"] == ("invoice", "Archive", 5)
    assert calls["read_message"] == ("42", "Archive", 500)
    assert calls["extract"] == ("42", "Archive", 1, 500, 3)
    assert calls["reply_context"] == ("42", "Archive", 800)


def test_attachment_upload_round_trip_never_takes_a_path(server):
    data = b"hello attachment"
    digest = hashlib.sha256(data).hexdigest()

    begun = server.begin_attachment_upload("notes.txt", "text/plain", len(data), digest)
    server.upload_attachment_chunk(begun["upload_id"], 0, base64.b64encode(data).decode("ascii"))
    finished = server.finish_attachment_upload(begun["upload_id"])

    assert finished["sha256"] == digest
    assert finished["filename"] == "notes.txt"
    assert server.discard_attachment(finished["attachment_token"]) == {"discarded": True}
    with pytest.raises(ToolError, match="Unknown attachment upload"):
        server.discard_attachment(finished["attachment_token"])


def test_upload_rejects_a_filename_that_carries_a_path(server):
    with pytest.raises(ToolError, match="must be a basename"):
        server.begin_attachment_upload("../../etc/passwd.txt", "text/plain", 4, "0" * 64)


def test_confirmed_draft_carries_the_attachment_and_destroys_its_token(server, monkeypatch):
    _, token = _stage_attachment(server.attachments)
    captured: dict = {}
    monkeypatch.setattr(server.bridge, "append_draft", _recording_append_draft(captured))

    result = server.create_confirmed_draft(
        to=["recipient@example.com"],
        subject="Quarterly numbers",
        body_text="See attached.",
        user_confirmed=True,
        attachment_tokens=[token],
    )

    assert result["sent"] is False
    assert result["attachment_names"] == ["brief.txt"]
    assert "cleanup_warnings" not in result
    assert captured["to"] == ("recipient@example.com",)
    assert captured["attachments"][0].data == b"quarterly numbers"

    # The token is single-use, so a replay finds neither the staged bytes nor a usable token.
    monkeypatch.setattr(server.bridge, "append_draft", _refusing_append_draft)
    with pytest.raises(ToolError, match="Unknown attachment upload"):
        server.create_confirmed_draft(
            to=["recipient@example.com"],
            subject="Quarterly numbers",
            body_text="See attached.",
            user_confirmed=True,
            attachment_tokens=[token],
        )


def test_confirmed_draft_rejects_a_token_revoked_before_creation(server, monkeypatch):
    _, token = _stage_attachment(server.attachments)
    server.discard_attachment(token)

    monkeypatch.setattr(server.bridge, "append_draft", _refusing_append_draft)
    with pytest.raises(ToolError, match="Unknown attachment upload"):
        server.create_confirmed_draft(
            to=["recipient@example.com"],
            subject="Quarterly numbers",
            body_text="See attached.",
            user_confirmed=True,
            attachment_tokens=[token],
        )


def test_confirmed_draft_rejects_staged_bytes_swapped_after_upload(server, monkeypatch):
    upload_id, token = _stage_attachment(server.attachments)

    # The staged blob is re-hashed against its recorded digest at load time, so bytes replaced
    # after finish_attachment_upload never reach the draft.
    swapped = b"attacker payload!"  # same length, so only the digest check can catch it
    server.attachments._blob_path(upload_id, partial=False).write_bytes(swapped)

    monkeypatch.setattr(server.bridge, "append_draft", _refusing_append_draft)
    with pytest.raises(ToolError, match="Staged attachment content changed"):
        server.create_confirmed_draft(
            to=["recipient@example.com"],
            subject="Quarterly numbers",
            body_text="See attached.",
            user_confirmed=True,
            attachment_tokens=[token],
        )


def test_cleanup_failure_is_reported_without_hiding_the_created_draft(server, monkeypatch):
    _, token = _stage_attachment(server.attachments)
    captured: dict = {}
    monkeypatch.setattr(server.bridge, "append_draft", _recording_append_draft(captured))

    def fail_consume(_token):
        raise AttachmentError("Staged attachment is unavailable")

    monkeypatch.setattr(server.attachments, "consume", fail_consume)

    result = server.create_confirmed_draft(
        to=["recipient@example.com"],
        subject="Quarterly numbers",
        body_text="See attached.",
        user_confirmed=True,
        attachment_tokens=[token],
    )

    assert result["created"] is True
    assert result["cleanup_warnings"] == ["Staged attachment is unavailable"]


def test_draft_validation_rejects_a_recipient_with_a_display_name(server, monkeypatch):
    monkeypatch.setattr(server.bridge, "append_draft", _refusing_append_draft)

    with pytest.raises(ToolError, match="without display name"):
        server.create_confirmed_draft(
            to=["Finance <finance@example.com>"],
            subject="Quarterly numbers",
            body_text="See attached.",
            user_confirmed=True,
        )


def test_sender_addresses_are_listed_with_the_default_first(server):
    assert server.list_sender_addresses() == {
        "default_sender": "user@example.com",
        "sender_addresses": ["user@example.com", "alias@example.com"],
    }


def test_confirmed_draft_uses_the_alias_the_call_names(server, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(server.bridge, "append_draft", _recording_append_draft(captured))

    server.create_confirmed_draft(
        to=["recipient@example.com"],
        subject="Quarterly numbers",
        body_text="See attached.",
        user_confirmed=True,
        from_address="ALIAS@example.com",
    )

    assert captured["from_address"] == "alias@example.com"


def test_confirmed_draft_defaults_to_the_primary_sender(server, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(server.bridge, "append_draft", _recording_append_draft(captured))

    server.create_confirmed_draft(
        to=["recipient@example.com"],
        subject="Quarterly numbers",
        body_text="See attached.",
        user_confirmed=True,
    )

    assert captured["from_address"] == "user@example.com"


def test_confirmed_draft_rejects_an_unconfigured_sender(server, monkeypatch):
    monkeypatch.setattr(server.bridge, "append_draft", _refusing_append_draft)

    with pytest.raises(ToolError, match="not a configured sender address"):
        server.create_confirmed_draft(
            to=["recipient@example.com"],
            subject="Quarterly numbers",
            body_text="See attached.",
            user_confirmed=True,
            from_address="attacker@example.com",
        )


def test_confirmed_draft_forwards_the_reply_target_and_nothing_else(server, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(server.bridge, "append_draft", _recording_append_draft(captured))

    result = server.create_confirmed_draft(
        to=["recipient@example.com"],
        subject="Re: Confirmed subject",
        body_text="Answering below.",
        user_confirmed=True,
        reply_to_uid="42",
        reply_to_folder="Archive",
        reply_to_message_id="<parent@example.com>",
    )

    assert result["sent"] is False
    assert captured["reply_to_uid"] == "42"
    assert captured["reply_to_folder"] == "Archive"
    assert captured["reply_to_message_id"] == "<parent@example.com>"
    # The reply target contributes no recipient and no body of its own.
    assert captured["to"] == ("recipient@example.com",)
    assert captured["cc"] == ()
    assert captured["bcc"] == ()
    assert captured["body_text"] == "Answering below."


def test_a_draft_that_is_not_a_reply_forwards_an_empty_reply_target(server, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(server.bridge, "append_draft", _recording_append_draft(captured))

    server.create_confirmed_draft(
        to=["recipient@example.com"],
        subject="Confirmed subject",
        body_text="Confirmed body",
        user_confirmed=True,
    )

    assert captured["reply_to_uid"] is None
    assert captured["reply_to_folder"] is None
    assert captured["reply_to_message_id"] is None


def test_confirmed_draft_rejects_a_reply_identifier_that_could_inject_a_header(server, monkeypatch):
    monkeypatch.setattr(server.bridge, "append_draft", _refusing_append_draft)

    with pytest.raises(ToolError, match="Invalid Message-ID"):
        server.create_confirmed_draft(
            to=["recipient@example.com"],
            subject="Re: Confirmed subject",
            body_text="Answering below.",
            user_confirmed=True,
            reply_to_uid="42",
            reply_to_message_id="<parent@example.com>\r\nBcc: attacker@example.com",
        )


def test_confirmed_draft_rejects_half_a_reply_target(server, monkeypatch):
    monkeypatch.setattr(server.bridge, "append_draft", _refusing_append_draft)

    with pytest.raises(ToolError, match="both reply_to_uid and reply_to_message_id"):
        server.create_confirmed_draft(
            to=["recipient@example.com"],
            subject="Re: Confirmed subject",
            body_text="Answering below.",
            user_confirmed=True,
            reply_to_uid="42",
        )
