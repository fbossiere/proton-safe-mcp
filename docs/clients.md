# Client setup

These configurations run Proton Safe MCP locally over STDIO. Complete [Getting started](getting-started.md)
first: Proton Mail Bridge must be running, the package must be installed, and the Bridge-generated
IMAP password must already be stored with `proton-safe-mcp setup`.

!!! warning "Never configure the Proton password"

    The `env` blocks below contain only the Proton address and Bridge port. Never add your Proton
    account password, recovery phrase, 2FA secret, hardware-key material, or even the
    Bridge-generated IMAP password. The server obtains the Bridge credential from the OS keyring.

Find the installed command before configuring a graphical client:

```bash
command -v proton-safe-mcp
```

Use the returned absolute path wherever an example shows `/absolute/path/to/proton-safe-mcp`.

## ChatGPT and Codex plugin

The repository includes a local marketplace and the `proton-safe` plugin. It can launch the same
STDIO server directly in Codex, or supply the canonical skills for a private ChatGPT connection
through OpenAI Secure MCP Tunnel.

Follow the dedicated [OpenAI plugin guide](openai-plugin.md). The tunnel option is the supported
way to reach a different Bridge machine: run both Proton Mail Bridge and `proton-safe-mcp` on that
machine rather than exposing Bridge IMAP over the network.

## Claude Code

Register the server at user scope so the configuration stays private and is available in all of
your projects:

```bash
claude mcp add \
  --scope user \
  --env PROTON_BRIDGE_USER="your-address@proton.me" \
  --env PROTON_IMAP_PORT="1143" \
  --transport stdio \
  proton-safe \
  -- /absolute/path/to/proton-safe-mcp serve
```

Verify the connection:

```bash
claude mcp get proton-safe
claude mcp list
```

Start Claude Code and ask it to call `mailbox_status`. The result should report `connected: true`.
Use `/mcp` inside Claude Code to inspect the exposed tools.

Reference: [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp).

## Cursor

Create or edit the global configuration at `~/.cursor/mcp.json`. Global configuration is preferable
to `.cursor/mcp.json` in a project because this server exposes personal email access and should not
be committed to another repository.

```json
{
  "mcpServers": {
    "proton-safe": {
      "type": "stdio",
      "command": "/absolute/path/to/proton-safe-mcp",
      "args": ["serve"],
      "env": {
        "PROTON_BRIDGE_USER": "your-address@proton.me",
        "PROTON_IMAP_PORT": "1143"
      }
    }
  }
}
```

Restart Cursor, open **Settings > Tools & MCP**, and confirm that `proton-safe` is enabled and its
tools are listed. Then ask the agent to call `mailbox_status`.

Reference: [Cursor MCP documentation](https://cursor.com/docs/mcp).

## VS Code

Open the Command Palette and run **MCP: Open User Configuration**. Add this server to the user-level
`mcp.json`; do not put a personal mail configuration in `.vscode/mcp.json` in a shared repository.

```json
{
  "servers": {
    "protonSafe": {
      "type": "stdio",
      "command": "/absolute/path/to/proton-safe-mcp",
      "args": ["serve"],
      "env": {
        "PROTON_BRIDGE_USER": "your-address@proton.me",
        "PROTON_IMAP_PORT": "1143"
      }
    }
  }
}
```

Run **MCP: List Servers**, start `protonSafe` if necessary, and inspect its output for startup
errors. In an agent chat, ask it to call `mailbox_status` and confirm that `connected` is `true`.

Reference: [VS Code MCP configuration](https://code.visualstudio.com/docs/agents/reference/mcp-configuration).

## Approval still happens outside the client

All three clients can prepare a pending draft, but none can approve it through MCP. Inspect and
approve the exact proposal in a separate terminal:

```bash
export PROTON_BRIDGE_USER="your-address@proton.me"
proton-safe-mcp show <draft_id>
proton-safe-mcp approve <draft_id>
```

The client may then call `commit_approved_draft`. You still review and send the resulting draft in
Proton Mail yourself.
