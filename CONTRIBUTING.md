# Contributing to proton-safe-mcp

Thank you for considering a contribution. This project has an unusual constraint that shapes every review: **its value is what it cannot do**. Please read the security model in the README before proposing changes.

## Non-negotiable design rules

Pull requests that violate these will be declined regardless of code quality:

1. **No send capability.** No SMTP client, no `send_message` tool, no flag that turns drafting into sending.
2. **No destructive mail tools.** No delete, no move, no flag mutation beyond what IMAP `PEEK` implies (nothing).
3. **No filesystem paths from MCP clients.** Attachments enter as bounded base64 chunks only.
4. **No received-attachment download tool.** The server returns attachment metadata, never bytes.
5. **The Bridge host stays `127.0.0.1`.** TLS verification is disabled only because the host is unchangeable; making the host configurable would silently break that safety argument.
6. **Draft approval stays out-of-band.** The approval step must not be reachable through any MCP tool.

## Development setup

```bash
git clone https://github.com/fbossiere/proton-safe-mcp.git
cd proton-safe-mcp
uv sync --extra dev
```

You do not need Proton Bridge to develop: the test suite fakes the IMAP layer.

## Before opening a PR

Run the full local gate — it matches CI exactly:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --cov
```

Guidelines:

- **Tests are required** for new behavior, especially validation and rejection paths. This codebase treats "rejects malformed input" as a feature worth a test, not an implementation detail.
- **Type hints are required.** CI runs mypy in strict mode.
- **Keep dependencies minimal.** The runtime dependency set is deliberately tiny (`fastmcp`, `keyring`). Adding a dependency needs a strong justification.
- **Update `CHANGELOG.md`** under the `[Unreleased]` heading using the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) categories.
- Keep commits focused; one logical change per PR.

## Reporting bugs

Use the bug report template. Redact email addresses and message content from logs.

## Reporting vulnerabilities

Never open a public issue. Use [GitHub private vulnerability reporting](https://github.com/fbossiere/proton-safe-mcp/security/advisories/new). See [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
