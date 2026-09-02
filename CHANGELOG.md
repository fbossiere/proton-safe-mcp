# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.2.1] - 2026-09-02

### Added

- Added sending-alias support for drafts: `PROTON_BRIDGE_ALIASES` configures an allowlist of
  additional From addresses, `list_sender_addresses` reports it, and `create_confirmed_draft` and
  `prepare_draft` accept the chosen `from_address`. Unconfigured senders are rejected, the IMAP
  write re-checks the allowlist, and the approval digest and CLI summary now bind the sender.

- Added a dev container (`.devcontainer/devcontainer.json`) that mirrors the CI toolchain (Python
  3.12 + uv) and bundles the GitHub CLI for a zero-setup contributor environment, and documented
  its usage in `CONTRIBUTING.md`.
- Documented how to open a pull request from the dev container in `CONTRIBUTING.md`, including the
  one-time `gh` authentication and why the protocol must be HTTPS without a mounted SSH key.

### Changed

- Drafts now carry a `text/html` alternative next to the confirmed plain-text body, so Proton
  opens them in the composer's default **Normal** mode instead of **Plain text** mode. The HTML is
  generated from `body_text` with HTML-special characters escaped, so quoted markup stays inert.
- Documented that a public key is attached by Proton at send time (**Encryption and keys →
  External PGP settings → Attach public key**), not by this server.
- Clarified that terminal approval is selected per draft in the conversation, is unrelated to
  `proton-safe-mcp setup`, and can use the pinned `uvx` command when the CLI is not installed
  globally.

## [1.2.0] - 2026-09-02

### Added

- Added `create_confirmed_draft` as the default draft path. It requires the client to assert exact
  in-conversation confirmation of every recipient, the subject, complete body, and attachments.

### Changed

- Kept `prepare_draft` and `commit_approved_draft` as an optional enhanced-security workflow rather
  than a requirement for every draft.
- Documented that conversational confirmation is a client workflow assertion, while local approval
  is not a strong isolation boundary when the same agent can write to the approval directory.

### Fixed

- Shortened the official MCP Registry description to satisfy its 100-character limit and added a
  registry-only recovery dispatch that cannot re-upload an existing PyPI distribution.

## [1.1.0] - 2026-09-01

### Added

- Added `extract_attachment_text` for bounded, read-only text extraction from selected received
  PDF, TXT, and CSV attachments without returning raw bytes or writing files.
- Added the `extract-proton-attachment` plugin skill, received-attachment size limits, extraction
  metadata and SHA-256 digests, rejection tests, and end-to-end user documentation.

### Changed

- Replaced the README ASCII architecture diagram with version-controlled Mermaid source and a
  rendered PNG asset.
- Documented Ubuntu ChatGPT desktop plugin installation, including the bundled Codex fallback,
  third-party binary conflicts, GUI environment inheritance, and post-install verification.
- Added a privacy-safe Ubuntu recovery workflow for plugins that install successfully but expose
  no MCP tools, including `environment.d` reload verification, separate user-manager and desktop
  diagnostics, a prepared-terminal diagnostic, a persistent per-user menu launcher, and a
  dedicated FAQ.

## [1.0.2] - 2026-08-30

### Added

- Repo-local `proton-safe` plugin for ChatGPT and Codex with guarded mail-review and
  draft-preparation skills.
- Pinned STDIO MCP configuration and a local marketplace entry for plugin testing.
- Local-first ChatGPT desktop and Codex setup, plus an optional OpenAI Secure MCP Tunnel guide for
  ChatGPT web and external Bridge-host deployments.
- Plugin package tests that enforce manifest consistency, secret exclusion, loopback assumptions,
  and out-of-band approval language.
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

[Unreleased]: https://github.com/fbossiere/proton-safe-mcp/compare/v1.2.1...HEAD
[1.2.1]: https://github.com/fbossiere/proton-safe-mcp/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/fbossiere/proton-safe-mcp/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/fbossiere/proton-safe-mcp/compare/v1.0.2...v1.1.0
[1.0.2]: https://github.com/fbossiere/proton-safe-mcp/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/fbossiere/proton-safe-mcp/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/fbossiere/proton-safe-mcp/releases/tag/v1.0.0
