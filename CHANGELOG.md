# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Repo-local `proton-safe` plugin for ChatGPT and Codex with guarded mail-review and draft-preparation skills.
- Pinned STDIO MCP configuration and a local marketplace entry for plugin testing.
- Local-first ChatGPT desktop and Codex setup, plus an optional OpenAI Secure MCP Tunnel guide for
  ChatGPT web and external Bridge-host deployments.
- Plugin package tests that enforce manifest consistency, secret exclusion, loopback assumptions, and out-of-band approval language.

### Changed

- Documented Ubuntu ChatGPT desktop plugin installation, including the bundled Codex fallback,
  third-party binary conflicts, GUI environment inheritance, and post-install verification.

## [1.0.2] - 2026-08-30

### Added

- Non-destructive, privacy-safe `proton-safe-mcp doctor` diagnostics for runtime, configuration,
  credential, private-state, and Bridge connectivity checks, with system-error redaction.
- A safety-constrained `llms-install.md` guide for AI-assisted installation.

## [1.0.1] - 2026-08-29

### Added

- Version-controlled MkDocs documentation with strict pull-request builds and automatic GitHub Pages deployment from `main`.
- PyPI trusted-publishing and official MCP Registry release automation.
- Copy-paste setup guides for Claude Code, Cursor, and VS Code.
- Official MCP Registry metadata for the PyPI distribution.

### Changed

- Recommended installation now uses a version-pinned `uv tool install` instead of a source checkout.

## [1.0.0] - 2026-08-29

### Added

- Read-only IMAP tools against the local Proton Mail Bridge: `mailbox_status`, `list_folders`, `list_messages`, `search_messages`, `read_message` (all using `BODY.PEEK`, bounded plain-text output).
- Client-neutral attachment staging: `begin_attachment_upload`, `upload_attachment_chunk`, `finish_attachment_upload`, `discard_attachment` with declared size, ordered chunks, SHA-256 verification, and single-use tokens.
- Draft workflow with out-of-band local approval: `prepare_draft`, `commit_approved_draft`, and the `proton-safe-mcp show / approve / reject` CLI.
- Keyring-backed storage of the Bridge-generated IMAP credential via `proton-safe-mcp setup`.
- Hardened defaults: STDIO-only transport, loopback-only Bridge host, MIME allow-list, header-injection rejection, private (`0700`/`0600`) state files.
- GitHub-ready release metadata, strict mypy checks, multi-version CI, dependency auditing, issue templates, and Dependabot configuration.
- Defensive handling for byte-valued IMAP capabilities and short filesystem writes.
- Per-draft cumulative attachment-size enforcement and CLI draft-ID validation.

[Unreleased]: https://github.com/fbossiere/proton-safe-mcp/compare/v1.0.2...HEAD
[1.0.2]: https://github.com/fbossiere/proton-safe-mcp/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/fbossiere/proton-safe-mcp/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/fbossiere/proton-safe-mcp/releases/tag/v1.0.0
