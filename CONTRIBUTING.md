# Contributing to proton-safe-mcp

Thank you for considering a contribution. This project has an unusual constraint that shapes every review: **its value is what it cannot do**. Please read the security model in the README before proposing changes.

## Non-negotiable design rules

Pull requests that violate these will be declined regardless of code quality:

1. **No send capability.** No SMTP client, no `send_message` tool, no flag that turns drafting into sending.
2. **No destructive mail tools.** No delete, no move, no flag mutation beyond what IMAP `PEEK` implies (nothing).
3. **No filesystem paths from MCP clients.** Attachments enter as bounded base64 chunks only.
4. **No raw received-attachment download tool.** Received files may expose bounded extracted text,
   metadata, and a digest, but never bytes, filesystem paths, or persisted files.
5. **The Bridge host stays `127.0.0.1`.** TLS verification is disabled only because the host is unchangeable; making the host configurable would silently break that safety argument.
6. **Draft confirmation is explicit.** Direct creation requires the client to assert that the user
   confirmed the exact recipients, subject, body, and attachments. The optional local approval
   marker stays out-of-band and must not be reachable through any MCP tool.
7. **Plugin instructions are not authorization.** Skills may guide safe workflows but cannot weaken
   tool validation, treat recipients from mail as confirmed, or create a local approval marker.
8. **Private connection material stays private.** Never commit a Bridge credential, tunnel runtime
   API key, or account-specific `.app.json` mapping.

## Development setup

```bash
git clone https://github.com/fbossiere/proton-safe-mcp.git
cd proton-safe-mcp
uv sync --extra dev
```

You do not need Proton Bridge to develop: the test suite fakes the IMAP layer.

### Dev container (optional)

A [dev container](.devcontainer/devcontainer.json) is provided for a zero-setup,
CI-matching environment (Python 3.12 + [uv](https://docs.astral.sh/uv/)). It runs
`uv sync --frozen --extra dev --extra docs` on create, so ruff, mypy, pytest,
pip-audit and mkdocs are all ready. The GitHub CLI (`gh`) is included so you can
open a pull request without leaving the container — see
[Opening the pull request](#opening-the-pull-request) for the one-time
authentication it needs.

- **VS Code**: install the *Dev Containers* extension, open the repo, then run
  **Dev Containers: Reopen in Container** from the command palette.
- **GitHub Codespaces**: **Code → Create codespace on `main`**.
- **CLI**: `devcontainer up --workspace-folder .` (from `@devcontainers/cli`).

The container is enough for the full local gate below — the test suite fakes the
IMAP layer, so no Proton Bridge is required. To run against a *real* Bridge (not
needed for tests), note it listens on `127.0.0.1` on the **host**, which the
standard container cannot reach. On Linux, a container explicitly started with
host networking can preserve that loopback boundary; otherwise, run the server
directly on the host. The Bridge host deliberately remains non-configurable.

## Before opening a PR

Run the full local gate — it matches CI exactly:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --cov
uv run mkdocs build --strict
```

Guidelines:

- **Tests are required** for new behavior, especially validation and rejection paths. This codebase treats "rejects malformed input" as a feature worth a test, not an implementation detail.
- **Type hints are required.** CI runs mypy in strict mode.
- **Keep dependencies minimal.** The runtime dependency set is deliberately tiny. Adding a dependency needs a strong justification; `pypdf` exists solely for in-memory, bounded PDF text extraction.
- **Update `CHANGELOG.md`** under the `[Unreleased]` heading using the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) categories.
- Keep commits focused; one logical change per PR.

### Opening the pull request

The dev container ships `gh` but deliberately carries no credentials, so the
first push needs a one-time authentication. **Choose HTTPS when `gh auth login`
asks for a protocol**, unless you have mounted an SSH key into the container:
picking SSH configures a protocol that has no key to use, and the push then
fails with `could not read Username for 'https://github.com'`.

```bash
gh auth login        # GitHub.com -> HTTPS -> login with a web browser
gh auth setup-git    # register gh as git's credential helper for github.com
```

VS Code injects its own credential helper into the container, which relays to
the host and returns nothing when the host has no stored GitHub credential.
`gh auth setup-git` takes precedence for `github.com`, which is what makes
`git push` work. To push once without changing your git config:

```bash
git -c credential.helper='!f() { test "$1" = get \
  && echo username=x-access-token \
  && echo "password=$(gh auth token)"; }; f' push -u origin HEAD
```

If the one-off command above already pushed the branch, skip the first command;
then open the PR against `main`:

```bash
git push -u origin HEAD
gh pr create --base main --fill
```

Prefer `--body-file` over `--fill` when the change needs more explanation than
the commit messages carry — reviewers read the PR body for *why* a rejection
path or a validation rule is shaped the way it is.

## Reporting bugs

Use the bug report template. Redact email addresses and message content from logs.

## Reporting vulnerabilities

Never open a public issue. Use [GitHub private vulnerability reporting](https://github.com/fbossiere/proton-safe-mcp/security/advisories/new). See [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
