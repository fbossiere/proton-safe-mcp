# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/fbossiere/proton-safe-mcp/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/fbossiere/proton-safe-mcp/releases/tag/v1.0.0
