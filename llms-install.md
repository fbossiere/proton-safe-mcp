# Install Proton Safe MCP

This file is an installation guide for AI coding agents. Proton Safe MCP is a local, Linux-only,
STDIO MCP server that connects to the official Proton Mail Bridge on `127.0.0.1`.

## Safety rules

- Never ask the user for their Proton password, Bridge-generated password, recovery phrase, 2FA
  data, or hardware-key material.
- Never place `PROTON_BRIDGE_PASSWORD` in an MCP client configuration.
- Ask the user to run `proton-safe-mcp setup` themselves in a separate local terminal. The command
  prompts privately and stores the Bridge-generated IMAP password in the operating-system keyring.
- Do not add send, delete, move, or received-attachment-download capabilities. They are excluded by
  design.
- Do not replace the loopback Bridge host with a configurable or remote host.

## Prerequisites

- Linux
- Proton Mail Bridge installed, signed in, and running
- a Proton plan that supports Bridge
- Python 3.11 or newer
- `uv`
- a Secret Service keyring such as `gnome-keyring`

Stop and explain the missing prerequisite if any of these requirements is not met.

## Install

Install the reviewed release:

```bash
uv tool install proton-safe-mcp==1.2.1
```

Find the executable path:

```bash
command -v proton-safe-mcp
```

Ask the user to open Proton Mail Bridge and obtain the configured email address, IMAP port, and
Bridge-generated IMAP password. The user may provide the address and port for the client
configuration, but must enter the Bridge password only into this local interactive command:

```bash
export PROTON_BRIDGE_USER="your-address@proton.me"
export PROTON_IMAP_PORT="1143"
proton-safe-mcp setup
```

Run the privacy-safe diagnostic:

```bash
proton-safe-mcp doctor
```

The report is designed to be shareable: it does not print credentials, email addresses, mailbox
counts, or message content.

## Register the STDIO server

Use the absolute path returned by `command -v proton-safe-mcp`:

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

Client-specific configuration is documented at:

<https://fbossiere.github.io/proton-safe-mcp/clients/>

## Verify

Restart or reload the MCP client, then call `mailbox_status`. A successful result contains
`connected: true`. Do not paste tool output into a public issue because it can contain account or
mailbox information.

If setup fails, run `proton-safe-mcp doctor` and follow:

<https://fbossiere.github.io/proton-safe-mcp/troubleshooting/>

Report only redacted installation feedback through the repository's installation feedback form.
