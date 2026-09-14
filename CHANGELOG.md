# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Windows 11 x64 support in the repository: a platform services layer, a per-user Inno
  Setup installer, a Windows build and packaging pipeline, CI jobs, and French and English
  documentation. **Nothing on the Windows path has been validated on Windows**, no Windows
  installer is published, and Proton Safe is not yet compatible with Windows. Every
  scenario in the new [Windows acceptance sheet](docs/windows-acceptance.md) is Not tested,
  and two external dependencies remain open: a Windows AI client whose full path is
  qualified, and a signing identity usable from CI.
- A platform services layer (`src/proton_safe_mcp/platform_services/`) holding the five
  concerns the two systems cannot share: known folders, private storage, session identity,
  credential store policy, and starting and reading a child process. The mail engine, the
  tool limits, the draft rules and the whole onboarding flow stay single-implementation.
- Windows private storage as an explicit protected DACL, with reparse points refused and
  the opened file confirmed to be the inspected one, standing in for `O_NOFOLLOW`. A
  descriptor is read for what it actually establishes: an absent DACL, a null one — which
  Windows treats as granting every account full access, the opposite of an empty one — an
  unreadable one and a foreign owner are each refused by name, and a folder that blocks
  inheritance while granting Everyone is corrected rather than mistaken for a tightened
  one. A new file carries its DACL before it carries any content.
- One assistant per account, held by an exclusive file lock rather than by the endpoint
  alone. Two launches can each find nothing answering and then each claim the endpoint,
  the second clearing the first's; the lock is what makes that impossible, and what makes
  clearing an endpoint left by a killed process safe.
- The registered client is recorded by absolute path and profile, not only by the
  identifier discovery gave it. An installation the user pointed at is never rediscovered,
  so a later repair or disconnect had no way to find it again; it is now looked up by path
  and revalidated like any other.
- The Bridge password on Windows in Credential Manager, with persistence pinned to this
  computer instead of the library default, which asks Windows to roam it.
- An explicit **Locate an assistant installed elsewhere…** choice on the client screen,
  for an installation the bounded probes do not reach. It is verified like any other.
- `--uninstall-connection` on the assistant, so the Windows uninstaller asks the component
  that owns the journal, the client adapters and the credential store to disconnect rather
  than reimplementing any of it. Its exit code decides whether the uninstall proceeds at
  all: a refused removal stops before a single file is deleted and offers Retry or Cancel,
  removing the software on its own stays available as an explicit answer, and a silent
  uninstall that can ask nothing removes nothing and returns a failure.
- Both the installer and the uninstaller refuse an elevated run, tested on the privileges
  the process actually holds rather than on the install mode, which stays non
  administrative under `PrivilegesRequired=lowest` however the process was started.
- `packaging/make_sbom.py` and `packaging/version.py`, shared by both platforms' builds.
- The home page and both download pages now present two systems, Ubuntu and Windows, with
  both always visible, and quote the published installer's size alongside its version. A
  small script marks the visitor's likely system to bring one card forward; it makes no
  request, stores nothing, and the page behaves identically without it. No Windows
  download is offered: `tests/check_built_site.py` fails the build if one appears while
  `extra.windows_release.available` is false.

### Changed

- The credential-store self-test now uses a separate service name and a fresh random key
  each attempt, and removes every entry the store may have created for it. Under the real
  service name, Windows Credential Manager would have displaced an existing credential to
  a compound target to resolve the account collision.
- The runtime locator refuses an ambiguous resolution instead of falling back to the
  running executable. In a bundle that would have opened a window instead of serving MCP.
- `doctor` reports the state directory through the platform, so "private" means a Unix
  mode on Linux and an access control list on Windows, each explained in its own terms.
- The Windows pipe reader is bounded where it reads rather than where it is consumed. Its
  thread stops one byte past the budget and blocks on a short queue, so a child flooding
  its output can no longer put megabytes in memory to answer a question bounded at
  kilobytes, and closing the reader joins the thread instead of leaving it behind.
- The Inno Setup compiler is pinned to a real download: the publisher's GitHub release,
  verified against its immutable release attestation, then checked for a valid
  Authenticode signature from Pyrsys B.V. before execution. An unpinned
  digest now fails the Windows job rather than skipping the setup build, so CI cannot go
  green without compiling the installer and running install, reinstall and uninstall.
- The POSIX validations are unchanged. No check was relaxed into a weaker rule both
  systems could satisfy.

## [2.1.2] - 2026-09-13

### Fixed

- Restore `replied_to` as a deprecated alias of `reply_target` so clients that read the older
  result field remain compatible. Both fields describe the requested parent, never verified
  Proton conversation membership. The default refusal, explicit separate-draft acceptance,
  `threading_verified: false`, and threading notice introduced in 2.1.1 remain in force.
- Use a release-based plugin cache version instead of a timestamp. This changes the cache key
  without implying a future build time.

## [2.1.1] - 2026-09-13

### Fixed

- Reply drafts no longer report successful conversation threading after IMAP storage alone.
  Proton Bridge reconstructs drafts without forwarding the parent link. Reply targets now fail
  before connection or writing unless the user explicitly accepts a possibly separate draft via
  `allow_unthreaded_reply`. Refusal preserves staged attachments. Accepted fallback results carry
  `threading_verified: false`, a clear notice, and `reply_target` instead of `replied_to`.
- Reply context, the MCP schema, plugin workflow, and documentation explain the limitation before
  draft confirmation and describe using Reply or Reply all in Proton Mail to preserve the thread.
  This corrects the unsupported conversation-grouping promise in the 2.0.3 notes below; it does
  not repair Proton Bridge or add send, delete, move, or Proton-account credential access.

### Added

- Add English/French product pages, verified Ubuntu download guidance and a first-use feedback route.

- Include Python 3.14 in the CI matrix and supported runtime metadata.

## [2.1.0] - 2026-09-13

### Changed

- Refreshed the desktop assistant with light/dark palettes, visible setup progress, a
  compact reading column, status cards and a dedicated application icon. Navigation stays
  visible while content scrolls at 200% scaling; the Bridge port and aliases move into
  keyboard-accessible advanced options. Shorter action labels retain the target client in
  their accessible names and in the activation summary.

### Added

- Release automation builds and verifies the Ubuntu installer, then attaches the `.deb`,
  SHA-256 and source provenance to the draft GitHub Release. Both package builds must pass
  before publishing to PyPI; the release is published only after all outputs are ready,
  respecting GitHub release immutability.

- A native **desktop setup assistant** for Ubuntu (PySide6), packaged as a `.deb` that
  carries its own Python runtime, the MCP server and the plugin resources. It configures
  Bridge, enables the existing plugin, verifies the result, repairs a connection and removes
  it, with no terminal and no user-installed Python or `uv`. See
  [Desktop assistant](docs/desktop-assistant.md).

  Qt is an optional `desktop` extra. The PyPI package, its CLI and the whole engine test
  suite keep working without it, and the desktop code is never imported at module level from
  anywhere outside `proton_safe_mcp.desktop`.

- A persistent **managed configuration** in `$XDG_CONFIG_HOME/proton-safe-mcp/config.toml`,
  selected by a new `--config <absolute path>` option on `setup`, `serve` and `doctor`.

  The two modes never mix. With `--config`, that file is the only source of settings and the
  OS keyring the only source of the Bridge credential: no `PROTON_*` variable is read, and
  `PROTON_BRIDGE_PASSWORD` is not a fallback. Without `--config`, every command behaves
  exactly as before and never looks for the file, so creating one cannot change an
  installation that has not been migrated.

  The schema is closed and the file is treated as security-relevant: an unknown key, an
  unknown future schema version, a symlink, an owner that is not the current account or
  permissions readable by others all refuse the start instead of falling back to another
  source. Writes are atomic, the directory is `0700` and the file `0600`, and no parent
  directory is modified. The file holds no password and no host.

- `doctor --json`, a redacted machine-readable report carrying stable check identifiers and
  codes plus software and system versions — and no address, folder name, mailbox figure,
  filesystem path, configuration value or raw command output. The text report is unchanged.

- `ProtonBridgeClient.probe()`, a minimal authentication that issues LOGIN, NOOP and LOGOUT
  and nothing else. The setup assistant uses it so installing can never read a message, mark
  one as seen or create a draft. `doctor` now uses it too, which removes the INBOX counter
  read its Bridge check previously performed.

- Errors now carry a stable `code`. User-visible text is translated from the code and never
  parsed out of an exception message. French and English strings live in one catalogue.

- A guided take-over for an existing Proton Safe plugin installed from another marketplace,
  typically the published `proton-safe@personal`. The assistant offers an explicit, unticked
  choice; without it nothing is written and the plan stops with a stated reason. Taking over
  removes only that plugin entry — its marketplace stays registered, because other plugins
  may come from it — reuses the stored credential without a retype, and records what it took
  over so a resumed run does not try to remove it twice. A client with no removal command
  stops before writing anything and names the entry to remove by hand, rather than leaving
  two Proton Safe servers registered.

  An entry the assistant does not own, such as a hand-registered MCP server, remains a
  conflict to resolve: the client's own configuration file is never rewritten.

### Changed

- Disconnecting no longer erases local data while client entries are still registered. The
  tracking record is the only thing a retry has to work from, so it is kept, the erase is
  deferred, and the request is remembered and carried out once the entries are actually gone.
  A refused disconnection now also shows up at the next start as an installation needing
  repair rather than a healthy one, and registering again withdraws the pending request.

- The plugin resources under `plugins/proton-safe/` now also ship inside the wheel as
  package data, so the managed plugin is rendered from the exact revision the runtime was
  built from. Nothing is downloaded from `main` during an installation, and the rendered
  plugin's version embeds the engine version and a digest of the resources so a package
  update cannot leave a client serving the previous skills.

  The managed registration uses its own `proton-safe-desktop` marketplace and launches an
  absolute runtime path with `--config`. It requires neither `uvx` nor any `PROTON_*`
  variable in the graphical session. The published `personal` marketplace entry and the
  manual procedure are unchanged.

- A refused IMAP LOGIN is now reported as an authentication failure rather than a generic
  protocol error, while a dropped connection stays a connection failure. A cause that cannot
  be determined reliably gets a generic connection code instead of being blamed on the
  password.

- The keyring is now classified explicitly: available, locked, unavailable, or a backend not
  approved for a managed setup. A build missing the Secret Service backend is reported as a
  packaging fault rather than looking like a user's locked session, and no unapproved backend
  ever becomes a silent place to store the credential.

### Fixed

- Runtime diagnostics now enforce a real shared handshake deadline and byte limit, including
  silent processes and responses without newlines. Malformed tool responses return a
  redacted failure instead of raising an exception.

## [2.0.3] - 2026-09-04

### Added

- Drafts can now be replies. `create_confirmed_draft` accepts `reply_to_uid`,
  `reply_to_folder`, and `reply_to_message_id`, and sets `In-Reply-To` plus a `References`
  chain built from the parent's own chain, so the draft waits in Proton Mail inside the
  thread instead of as a standalone message. **Correction in 2.1.1:** Bridge discards that
  parent link; those headers alone did not establish conversation membership.

  Threading headers are the entire contribution. The message being replied to supplies no
  recipient, no subject, and no body: those stay explicit inputs the user confirmed. In
  particular the server still appends nothing to a body, so a reply quote reaches the draft
  only as part of the confirmed `body_text` — the stored draft remains exactly what the user
  approved.

  `reply_to_message_id` is a required assertion rather than a convenience. At the IMAP write
  the server re-reads the headers of the message at `reply_to_uid` and refuses the draft
  unless it still carries exactly that Message-ID, so a mailbox that changed since the
  confirmation is rejected instead of threaded onto a different message. Both identifiers are
  validated as bracketed message-ids restricted to printable US-ASCII with no whitespace,
  because a Message-ID read out of a received message is attacker-controlled input going into
  a header the server writes; the reference chain is bounded in entry count and rendered
  length.

- A read-only `get_reply_context` tool returns what composing a reply needs: the parent's
  Message-ID, a `Re:` subject that does not stack onto an existing one, the bare addresses
  found in `Reply-To`, `From`, `To`, and `Cc` — each labelled with its header and flagged when
  it is one of the configured senders — and the body as a bounded `> ` quote. Every value is a
  suggestion drawn from untrusted headers: no address it reports is a confirmed recipient, and
  the draft tool still takes its recipients as explicit inputs. The `message_id` it reports is
  validated first and comes back empty when the message carries nothing a reply can thread on,
  so a draft is never refused over it after the user already confirmed one.

### Fixed

- A received message whose `Message-ID` header is `<>` or `<` no longer aborts the read that
  touched it on Python 3.11, where the standard library's structured-header parser raises
  `IndexError` on both shapes. `list_messages` and `search_messages` read that header for every
  message they summarize, so one crafted message took out the whole listing rather than just
  itself, and the error surfaced as an internal failure instead of a validation error. Header
  reads now report an unparsable value as absent. Python 3.12 and later parse both shapes and
  were unaffected.

## [2.0.2] - 2026-09-02

### Fixed

- The bundled Codex plugin now forwards `PROTON_BRIDGE_ALIASES` from the desktop environment, so
  sending aliases introduced in 1.2.1 are available through `list_sender_addresses`. Troubleshooting
  documents how to tell that packaging defect apart from a stale ChatGPT process environment, since
  both leave `list_sender_addresses` reporting the primary address with no startup error.
- The installation path now documents `PROTON_BRIDGE_ALIASES` where it is actually set. The README
  and Getting started only described the primary address, and the client `env` examples omitted the
  variable, so the sending-alias allowlist was discoverable only in the configuration reference.

## [2.0.1] - 2026-09-02

### Fixed

- An empty or relative `XDG_STATE_HOME` is now ignored, as the XDG base directory specification
  requires. It previously resolved to the working directory, so a client launched from an arbitrary
  directory staged attachment bytes in `./proton-safe-mcp` instead of the private state directory.
- A `PROTON_BRIDGE_USER` containing a line break is now reported as an invalid address rather than
  as a missing variable.
- Documented the `list_sender_addresses` tool in the README tool table, and removed the reference
  to the approval digest and the second draft path that 2.0.0 deleted.

### Changed

- Bounded the attachment-token inputs of `discard_attachment` and `create_confirmed_draft` in the
  published tool schema, matching every other tool input.
- Internal cleanup with no behavior change: removed the `AttachmentStore.discard` alias, the unused
  `cleanup_expired` count, the unreachable CLI exit path, and the leftover single-use draft helpers;
  split `doctor.run_checks` into one function per check; and de-duplicated the IMAP fetch and search
  paths in `mail.py`.

## [2.0.0] - 2026-09-02

### Removed

- **Breaking.** Removed the optional terminal draft-approval workflow: the `prepare_draft` and
  `commit_approved_draft` MCP tools, the `proton-safe-mcp show / approve / reject` CLI commands,
  the on-disk approval state machine, and `PROTON_MCP_DRAFT_TTL_SECONDS`. `create_confirmed_draft`
  is now the only way to create a draft, and it keeps `from_address` and every other input
  unchanged.

  It was never a security boundary. The choice between it and `create_confirmed_draft` was made by
  the model — precisely the component the threat model does not trust — so a prompt injection
  simply took the direct path. And the asset it guarded does not need guarding: the server has no
  SMTP implementation, so a draft cannot leave the account until the user presses Send in Proton
  Mail, where the full body, recipients, and sender are visible. The terminal step reviewed a
  500-character truncated preview instead.

  Its one genuine control, binding attachment digests and the sender across the approval window,
  defended against an attacker with write access to the state directory — an attacker who could
  equally well write the approval marker. Staged bytes are still re-hashed against their recorded
  digest at load time, and `append_draft` still re-checks the sender allowlist, which is what
  actually catches tampering.

  The `~/.local/state/proton-safe-mcp/approvals` directory is no longer created and can be deleted.

### Changed

- `ApprovalError` is now `DraftError`, matching what it actually reports.
- The architecture diagram now shows the manual send in Proton Mail as the human gate, in place
  of the terminal approval box.

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

[Unreleased]: https://github.com/fbossiere/proton-safe-mcp/compare/v2.1.2...HEAD
[2.1.2]: https://github.com/fbossiere/proton-safe-mcp/compare/v2.1.1...v2.1.2
[2.1.1]: https://github.com/fbossiere/proton-safe-mcp/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/fbossiere/proton-safe-mcp/compare/v2.0.3...v2.1.0
[2.0.3]: https://github.com/fbossiere/proton-safe-mcp/compare/v2.0.2...v2.0.3
[2.0.2]: https://github.com/fbossiere/proton-safe-mcp/compare/v2.0.1...v2.0.2
[2.0.1]: https://github.com/fbossiere/proton-safe-mcp/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/fbossiere/proton-safe-mcp/compare/v1.2.1...v2.0.0
[1.2.1]: https://github.com/fbossiere/proton-safe-mcp/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/fbossiere/proton-safe-mcp/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/fbossiere/proton-safe-mcp/compare/v1.0.2...v1.1.0
[1.0.2]: https://github.com/fbossiere/proton-safe-mcp/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/fbossiere/proton-safe-mcp/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/fbossiere/proton-safe-mcp/releases/tag/v1.0.0
