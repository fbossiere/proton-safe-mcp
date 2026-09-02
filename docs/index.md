# Proton Safe MCP

**Read and search Proton Mail, then create drafts that only you can send.**

Proton Safe MCP is a local, client-agnostic [Model Context Protocol](https://modelcontextprotocol.io/) server for Proton Mail through the official [Proton Mail Bridge](https://proton.me/mail/bridge). It exposes bounded mail-reading tools and creates drafts after exact conversational confirmation. It has no send, delete, or move capability, so every draft waits in Proton Mail for you to review and send.

![Proton Safe MCP — draft-only email tools, human-approved](assets/proton-mcp-safe.png)

!!! warning "Email remains untrusted input"

    Any sender can place adversarial instructions in a message. Proton Safe MCP limits what an injected instruction can accomplish, but it does not make email content trustworthy.

## Safety boundary

The capability restrictions are part of the product, not optional settings:

- **No send tool** and no SMTP client.
- **No delete or move tools** and no raw received-attachment download.
- **Bounded received-attachment text.** PDF, TXT, and CSV inspection returns text and metadata,
  never attachment bytes or files.
- **No client-supplied filesystem paths.** Attachments arrive as bounded base64 chunks.
- **Explicit confirmation.** Creating a draft requires confirmation of the exact content in the
  conversation, and the draft still waits in Proton Mail for you to send it.
- **Loopback only.** The server uses STDIO and the Bridge host is fixed to `127.0.0.1`.

## How it fits together

```text
MCP client ──STDIO──> proton-safe-mcp ──IMAP on 127.0.0.1──> Proton Bridge
                            │
                            ├── read/search + bounded extraction tools
                            ├── bounded attachment staging
                            └── confirmed draft ──> Proton Mail Drafts (never Sent)
                                                              │
                                              you review and press Send
```

The optional [Proton Safe OpenAI plugin](openai-plugin.md) packages guarded workflows around this
same server. ChatGPT desktop and Codex can use its local STDIO configuration directly when they run
on the Bridge machine. OpenAI Secure MCP Tunnel is an optional path for ChatGPT web or a Bridge host
on another machine; it does not change the loopback-only Bridge boundary.

## Start here

1. Follow [Getting started](getting-started.md) to install the server and connect Proton Bridge.
2. Use the [client setup guides](clients.md) for Claude Code, Cursor, or VS Code.
3. Review the [security model](security-model.md) before combining the server with other tools.
4. Use the [MCP tool reference](mcp-tools.md) for exact inputs and limits.
5. Read [received attachment extraction](received-attachments.md), [outgoing attachment
   staging](attachments.md), and the [MCP tool reference](mcp-tools.md) before
   handling files or creating drafts.
6. Use the [OpenAI plugin guide](openai-plugin.md) for local ChatGPT desktop/Codex installation,
   direct MCP registration, or optional remote tunnel access.
7. Check the [FAQ](faq.md) and [Troubleshooting](troubleshooting.md) before reinstalling a client,
   plugin, or Bridge component.

Linux and Proton Mail Bridge users can also run the
[10-minute external test](external-testing.md) and report installation friction without sharing
private mail content.

The current stable version is [v2.0.1](https://github.com/fbossiere/proton-safe-mcp/releases/tag/v2.0.1).
