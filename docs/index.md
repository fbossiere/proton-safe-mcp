# Proton Safe MCP

**Read and search Proton Mail, then create drafts that only you can approve and send.**

Proton Safe MCP is a local, client-agnostic [Model Context Protocol](https://modelcontextprotocol.io/) server for Proton Mail through the official [Proton Mail Bridge](https://proton.me/mail/bridge). It exposes bounded mail-reading tools and a draft workflow with an out-of-band human approval step.

![Proton Safe MCP — draft-only email tools, human-approved](assets/proton-mcp-safe.png)

!!! warning "Email remains untrusted input"

    Any sender can place adversarial instructions in a message. Proton Safe MCP limits what an injected instruction can accomplish, but it does not make email content trustworthy.

## Safety boundary

The capability restrictions are part of the product, not optional settings:

- **No send tool** and no SMTP client.
- **No delete or move tools** and no received-attachment download.
- **No client-supplied filesystem paths.** Attachments arrive as bounded base64 chunks.
- **Human approval outside MCP.** A local terminal command must approve the exact draft proposal.
- **Loopback only.** The server uses STDIO and the Bridge host is fixed to `127.0.0.1`.

## How it fits together

```text
MCP client ──STDIO──> proton-safe-mcp ──IMAP on 127.0.0.1──> Proton Bridge
                            │
                            ├── read/search tools
                            ├── bounded attachment staging
                            └── pending draft proposal
                                      │
Local terminal ──show / approve / reject──┘
                                      │
                                      └──> Proton Mail Drafts (never Sent)
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
5. Read the [attachment](attachments.md) and [draft approval](draft-approval.md) workflows before creating drafts.
6. Use the [OpenAI plugin guide](openai-plugin.md) for local ChatGPT desktop/Codex installation,
   direct MCP registration, or optional remote tunnel access.
7. Check the [FAQ](faq.md) and [Troubleshooting](troubleshooting.md) before reinstalling a client,
   plugin, or Bridge component.

Linux and Proton Mail Bridge users can also run the
[10-minute external test](external-testing.md) and report installation friction without sharing
private mail content.

The current stable version is [v1.0.2](https://github.com/fbossiere/proton-safe-mcp/releases/tag/v1.0.2).
