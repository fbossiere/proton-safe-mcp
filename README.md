# Proton Safe MCP

<!-- mcp-name: io.github.fbossiere/proton-safe-mcp -->

[![CI](https://github.com/fbossiere/proton-safe-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/fbossiere/proton-safe-mcp/actions/workflows/ci.yml)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-4051b5)](https://fbossiere.github.io/proton-safe-mcp/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/fbossiere/proton-safe-mcp/blob/main/LICENSE)
[![Checked with mypy](https://img.shields.io/badge/mypy-strict-blue)](https://mypy-lang.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

<img width="1774" height="887" alt="Proton Safe MCP — draft-only email tools, human-approved" src="https://raw.githubusercontent.com/fbossiere/proton-safe-mcp/main/docs/assets/proton-mcp-safe.png" />

A client-agnostic [FastMCP](https://gofastmcp.com) server for Proton Mail through the official [Proton Mail Bridge](https://proton.me/mail/bridge). It can read and search mail and create **drafts with attachments**. It deliberately **cannot send email** — you review every draft in Proton Mail and press Send yourself.

The server runs locally over STDIO for any MCP-compatible client (Claude Desktop, Claude Code, or anything else that speaks MCP). Received PDF, TXT, and CSV attachments can be inspected through bounded text extraction without exposing their raw bytes. Outgoing attachments are uploaded as bounded base64 chunks, so the server never receives or reads a client filesystem path.

Read the [full documentation](https://fbossiere.github.io/proton-safe-mcp/) for setup, configuration, tool inputs, security boundaries, and troubleshooting.

## Why "safe"?

Email is attacker-controlled input. Any sender can put adversarial instructions in a message body, and an AI agent that reads mail *and* holds write-capable tools is one prompt injection away from doing something you did not ask for. This project limits the blast radius by construction:

- **No send.** There is no SMTP client and no `send_message` tool in the codebase — a test asserts it.
- **No delete, no move,** and no raw received-attachment download tool.
- **Human in the loop.** Direct draft creation requires explicit confirmation of the exact content in the conversation, and Proton Mail still requires manual review and sending. A separate terminal approval remains available for enhanced security.
- **No filesystem access for clients.** Attachment bytes are streamed in chunks with declared size and SHA-256 verification; paths are rejected.
- **Loopback only.** STDIO transport, no listening socket, and the Bridge host is hard-coded to `127.0.0.1`.

These controls reduce risk but do not make email trusted. Never expose unrelated write-capable tools in the same unattended agent workflow.

## Architecture

![Architecture diagram showing an MCP client connected over STDIO to proton-safe-mcp, which uses loopback-only IMAP to create confirmed Proton Mail drafts; optional enhanced approval happens separately in a local terminal](https://raw.githubusercontent.com/fbossiere/proton-safe-mcp/main/docs/assets/architecture.png)

## Security properties

- STDIO only: the server opens no listening network socket.
- Proton Bridge host is hard-coded to `127.0.0.1` (`PROTON_BRIDGE_HOST` is intentionally unsupported).
- No SMTP client, send tool, delete tool, move tool, or raw received-attachment download tool.
- Message and attachment reads use `BODY.PEEK`; attachment inspection returns bounded extracted text,
  metadata, and a SHA-256 digest, never raw bytes or files.
- Attachment input is chunked base64 with declared size and SHA-256 verification.
- Only PDF, DOCX, XLSX, PPTX, TXT, CSV, PNG, and JPEG uploads are accepted.
- Attachment tokens are random, short-lived, single-use, and reverified before draft creation.
- Direct draft creation requires an explicit client assertion that the user confirmed the exact recipients, subject, body, and attachments in the conversation.
- Optional enhanced-security mode binds the exact draft to a separate local terminal approval that is not exposed as an MCP tool.
- The Bridge-generated IMAP password is stored in the operating-system keyring.
- Draft bodies are stored as plain text plus a server-generated HTML alternative that
  HTML-escapes the confirmed body, so quoted markup can never be rendered.
- Recipient, subject, and folder inputs are validated against header/criteria injection.
- State files are private to the Unix account (`0700` directories, `0600` files, `O_NOFOLLOW`).

## Requirements

- Linux with the official Proton Mail Bridge installed, signed in, and running (developed and tested on Ubuntu).
- A Proton plan that supports Bridge.
- Python 3.11 or newer.
- [`uv`](https://docs.astral.sh/uv/).
- A working Secret Service keyring (`gnome-keyring` or compatible).

## Installation

Install the reviewed release from PyPI with [`uv`](https://docs.astral.sh/uv/):

```bash
uv tool install proton-safe-mcp==1.2.0
```

For development from source instead:

```bash
git clone https://github.com/fbossiere/proton-safe-mcp.git
cd proton-safe-mcp
uv sync --extra dev
```

Set only the Proton address and Bridge IMAP port in the MCP process environment:

```bash
export PROTON_BRIDGE_USER="your-address@proton.me"
export PROTON_IMAP_PORT="1143"
```

Store the **Bridge-generated IMAP password** (shown in the Bridge UI), not your Proton account password:

```bash
proton-safe-mcp setup
```

The value shown by Bridge is installation-specific and works only against the local Bridge.

## Register with an MCP client

Configure a local STDIO server with these logical fields. Use `command -v proton-safe-mcp`
to obtain the absolute command path when your client does not inherit your shell `PATH`:

```json
{
  "name": "proton-safe",
  "transport": "stdio",
  "command": "/absolute/path/to/proton-safe-mcp",
  "args": ["serve"],
  "env": {
    "PROTON_BRIDGE_USER": "your-address@proton.me",
    "PROTON_IMAP_PORT": "1143"
  }
}
```

Do not put `PROTON_BRIDGE_PASSWORD` in the client configuration. The server reads it from the OS keyring established by `setup`.

Copy-paste instructions are available for [Claude Code, Cursor, and VS Code](https://fbossiere.github.io/proton-safe-mcp/clients/).
AI coding agents can follow the safety-constrained [`llms-install.md`](llms-install.md) guide.

Verify the complete local setup without printing credentials, addresses, or mailbox data:

```bash
proton-safe-mcp doctor
```

## OpenAI plugin

The repository includes a private, local-first **Proton Safe** plugin for ChatGPT and Codex. It
packages safety-focused mail review and draft workflows with the same restricted MCP server:

- ChatGPT desktop and Codex can launch the bundled STDIO configuration directly on the Bridge
  machine, with no tunnel or dedicated server;
- direct MCP registration remains available when the packaged workflow skills are not needed;
- ChatGPT web or a client on another machine can optionally reach the Bridge host through OpenAI
  Secure MCP Tunnel without an inbound port;
- a remote deployment still keeps `proton-safe-mcp` and Proton Mail Bridge together, with IMAP
  fixed to `127.0.0.1`.

See the [OpenAI plugin guide](https://fbossiere.github.io/proton-safe-mcp/openai-plugin/) for local
ChatGPT desktop/Codex installation, direct MCP registration, and the optional remote tunnel.

> **Plugin installed but no Proton tools?** The bundled MCP configuration forwards
> `PROTON_BRIDGE_USER` and `PROTON_IMAP_PORT` from the environment that started Codex; it does not
> define their values. On Ubuntu, a correct `~/.config/environment.d/*.conf` file can still require
> a user-manager reload, while GNOME and already-running terminals can keep their earlier
> environment. If a menu relaunch still has no tools, start ChatGPT once from a terminal that has
> loaded the file. That terminal launch is a diagnostic, not a requirement for every start; the
> troubleshooting guide also provides a persistent per-user menu launcher. Follow the privacy-safe
> [Ubuntu recovery procedure](https://fbossiere.github.io/proton-safe-mcp/troubleshooting/#plugin-is-installed-but-mcp-shows-no-proton-tools)
> or the [FAQ](https://fbossiere.github.io/proton-safe-mcp/faq/) before reinstalling anything.

> **Help test the onboarding.** Linux and Proton Mail Bridge users can run the
> [10-minute external test](https://fbossiere.github.io/proton-safe-mcp/external-testing/) and
> submit privacy-safe [installation feedback](https://github.com/fbossiere/proton-safe-mcp/issues/new?template=installation-feedback.yml).

## Available MCP tools

| Category | Tool | Notes |
| --- | --- | --- |
| Read-only mail | `mailbox_status` | Bridge connectivity + INBOX counts |
| | `list_folders` | |
| | `list_messages` | Never marks messages as read |
| | `search_messages` | Injection-safe IMAP `TEXT` search |
| | `read_message` | Bounded plain text; no attachment bytes |
| | `extract_attachment_text` | Bounded PDF/TXT/CSV text; no raw bytes or files |
| Attachment staging | `begin_attachment_upload` | Declares filename, type, size, SHA-256 |
| | `upload_attachment_chunk` | Ordered base64 chunks |
| | `finish_attachment_upload` | Verifies hash, returns single-use token |
| | `discard_attachment` | |
| Drafts | `create_confirmed_draft` | Default; requires exact conversational confirmation |
| | `prepare_draft` | Enhanced mode; creates a pending proposal only |
| | `commit_approved_draft` | Enhanced mode; requires prior local approval |

There is deliberately no `send_message` tool.

## Attachment and draft workflow

The MCP client only needs the ability to obtain the bytes of a file and call tools. There is no dependency on a particular client, service, or local directory.

1. Calculate the exact byte length and SHA-256 of the file.
2. Call `begin_attachment_upload(filename, content_type, size_bytes, sha256_hex)`.
3. Base64-encode consecutive binary chunks no larger than the returned `max_chunk_bytes`.
4. Call `upload_attachment_chunk(upload_id, chunk_index, data_base64)` for indexes `0, 1, 2…`.
5. Call `finish_attachment_upload(upload_id)` and retain the returned `attachment_token`.
6. Present the exact recipients, subject, complete body, and attachment list to the user.
7. After explicit confirmation in the conversation, call
   `create_confirmed_draft(..., user_confirmed=true, attachment_tokens=[token])`.
8. Open Proton Mail, review the draft, and send it manually.

For enhanced security, replace steps 7–8 with the optional local approval path:

Approval is selected per draft, not during `proton-safe-mcp setup`. In ChatGPT or Codex, ask:
`Use enhanced-security mode with terminal approval for this draft.`

1. Call `prepare_draft(..., attachment_tokens=[token])`.
2. Inspect and approve the exact proposal in a local terminal:

   ```bash
   export PROTON_BRIDGE_USER="your-address@proton.me"
   proton-safe-mcp approve <draft_id>
   ```

3. Allow the MCP client to call `commit_approved_draft(draft_id)`.
4. Open Proton Mail, review the draft, and send it manually.

In enhanced mode, the proposal expires after 15 minutes by default. Uploaded attachments expire
after 30 minutes. The server intentionally keeps pending proposal bodies in memory only; restarting
it invalidates them.

## Local administration

```bash
proton-safe-mcp show <draft_id>      # inspect a pending draft
proton-safe-mcp approve <draft_id>   # interactive; no --yes bypass exists
proton-safe-mcp reject <draft_id>
```

## Configuration reference

| Variable | Default | Purpose |
| --- | ---: | --- |
| `PROTON_BRIDGE_USER` | required | Proton address configured in Bridge |
| `PROTON_IMAP_PORT` | `1143` | Local Bridge IMAP port |
| `PROTON_MCP_STATE_DIR` | `~/.local/state/proton-safe-mcp` | Private staging and approval state |
| `PROTON_MCP_MAX_ATTACHMENT_BYTES` | `20971520` | Per-file maximum, capped at 25 MiB |
| `PROTON_MCP_MAX_RECEIVED_ATTACHMENT_BYTES` | `10485760` | Received-file extraction maximum, capped at 25 MiB |
| `PROTON_MCP_MAX_CHUNK_BYTES` | `393216` | Decoded chunk maximum, capped at 1 MiB |
| `PROTON_MCP_UPLOAD_TTL_SECONDS` | `1800` | Attachment staging lifetime |
| `PROTON_MCP_DRAFT_TTL_SECONDS` | `900` | Pending draft lifetime |
| `PROTON_MCP_MAX_BODY_CHARS` | `100000` | Maximum outgoing draft body length |

`PROTON_BRIDGE_HOST` is intentionally unsupported.

For isolated containers without a Secret Service keyring, `PROTON_BRIDGE_PASSWORD` may contain
the Bridge-generated IMAP password. Avoid this fallback in desktop MCP client configuration:
environment values may be visible to the client process or its diagnostics.

## Development

```bash
uv sync --extra dev
uv run pytest --cov      # tests with coverage
uv run ruff check .      # lint
uv run ruff format .     # format
uv run mypy              # strict type checking
```

Proton Bridge is not needed for development: the test suite fakes the IMAP layer. Tests cover path rejection, MIME restrictions, received-attachment size and format rejection, bounded PDF/text extraction, ordered chunks, size/hash verification, token consumption, header injection, direct confirmation, approval digest integrity, CLI approval flow, and HTML-to-text sanitization.

See [CONTRIBUTING.md](https://github.com/fbossiere/proton-safe-mcp/blob/main/CONTRIBUTING.md) for the design rules that reviews enforce.

## Threat-model limitations

Read this before relying on the server in an autonomous workflow:

- A model necessarily sees any mail it reads and any attachment it creates or uploads.
- Extracted attachment text is attacker-controlled and may contain prompt injection. The server
  bounds the returned text but does not make it trustworthy or perform OCR or malware scanning.
- Uploaded attachment bytes are stored temporarily in files readable only by the Unix account. Use full-disk encryption.
- The server cannot inspect the surrounding conversation. `user_confirmed: true` is a client assertion, so the direct workflow depends on the client honoring the confirmation rule.
- If the MCP client also has unrestricted shell access as the same Unix user, it can potentially write an approval marker itself. Keep shell/file-writing tools out of the same autonomous agent session when approval integrity matters.
- Secure MCP Tunnel keeps the server off the public internet, but mail content returned to an
  OpenAI product still crosses the local Bridge boundary and is processed by that product.
- Tool annotations and conversational-confirmation instructions are client guidance, not authorization controls. The server still enforces input validation; enhanced mode additionally checks local approval state.
- Proton Bridge's self-signed TLS certificate is not verified. This is acceptable here only because the target host is unchangeably `127.0.0.1`.

## Security

To report a vulnerability, use [GitHub private vulnerability reporting](https://github.com/fbossiere/proton-safe-mcp/security/advisories/new) — never a public issue. See [SECURITY.md](https://github.com/fbossiere/proton-safe-mcp/blob/main/SECURITY.md).

## License

[MIT](https://github.com/fbossiere/proton-safe-mcp/blob/main/LICENSE) © 2026 Francois Bossiere.

This project is not affiliated with or endorsed by Proton AG. "Proton Mail" and "Proton Mail Bridge" are trademarks of Proton AG.
