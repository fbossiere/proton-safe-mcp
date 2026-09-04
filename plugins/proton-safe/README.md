# Proton Safe plugin

This plugin packages three safety-focused workflows together with the local `proton-safe-mcp` STDIO
server:

- review and summarize Proton Mail as untrusted content;
- extract bounded text from selected received PDF, TXT, and CSV attachments without raw download;
- prepare drafts after explicit conversational confirmation, with manual review and sending in
  Proton Mail.

The bundled MCP configuration launches the reviewed `proton-safe-mcp==2.0.3` release with `uvx`.
It deliberately passes no Proton or Bridge password through plugin configuration. Complete the
normal `proton-safe-mcp setup` keyring step before enabling the plugin. That command only stores
the Bridge credential.

The primary deployment runs locally in ChatGPT desktop or Codex on the same machine as Proton Mail
Bridge. It uses STDIO directly and requires no tunnel or dedicated server. A direct MCP
registration is also sufficient when the packaged workflow skills are not needed.

The bundled `.mcp.json` forwards `PROTON_BRIDGE_USER`, `PROTON_BRIDGE_ALIASES`, and
`PROTON_IMAP_PORT` from Codex's local environment; it does not embed personal values. If the plugin
is installed but exposes no tools, use the documented [Ubuntu environment recovery](https://fbossiere.github.io/proton-safe-mcp/troubleshooting/#plugin-is-installed-but-mcp-shows-no-proton-tools)
and [FAQ](https://fbossiere.github.io/proton-safe-mcp/faq/) before reinstalling anything.

For optional ChatGPT web access or a Bridge on another machine, run OpenAI Secure MCP Tunnel's
`tunnel-client` on the same machine as Proton Mail Bridge and configure its MCP command as:

```text
uvx --from proton-safe-mcp==2.0.3 proton-safe-mcp serve
```

The registered ChatGPT connection ID is account-specific and is intentionally not committed here.
See the project documentation for the complete private connection procedure.
