# Development

The test suite fakes the IMAP layer, so Proton Mail Bridge is not required for development.

## Setup

```bash
git clone https://github.com/fbossiere/proton-safe-mcp.git
cd proton-safe-mcp
uv sync --frozen --extra dev --extra docs --extra desktop
```

## Quality gate

Run the same checks as CI:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
QT_QPA_PLATFORM=offscreen uv run pytest --cov
uv run pip-audit
uv run mkdocs build --strict
uv build --no-sources
```

For the Ubuntu installer, also follow the bundle and package checks in
[Desktop validation](desktop-testing.md). Qt needs `libegl1` and `libglib2.0-0t64`
on Ubuntu 24.04 even with the offscreen platform.

### Working on the Windows path from Linux

Most of the Windows implementation is ordinary Python and is tested on every platform:
`tests/test_platform_services.py` covers access control lists, launchable files, child
environments and the private-file sequencing, and `tests/test_windows_behaviour.py` covers
what the product decides — runtime discovery, paths through JSON and TOML, prerequisites,
the credential self-test and the French and English wording. Both run in the normal
`pytest` command above, so a change to `platform_services/windows.py` is checked here and
type-checked by `mypy` here too.

The `as_windows` fixture installs the Windows services with only the four Win32 calls
stubbed. Use it rather than asserting on source text.

Tests whose subject is a Unix guarantee — a mode, a uid, a symlink — carry
`@pytest.mark.posix_only` and skip themselves on Windows. Do not reach for that marker to
make a test pass on Windows: if the behaviour matters on both systems, the fix is a
platform-neutral test, or a Windows equivalent beside the POSIX one.

What cannot be settled from Linux: starting a real client, reading a real Credential
Manager entry, surviving a restart, and the absence of a UAC prompt on a standard account.
Those are the [Windows acceptance scenarios](windows-acceptance.md).

The repository test suite validates the checked-in plugin manifest, marketplace, MCP command,
secret exclusions, and skill boundary. In a Codex development environment, also run the built-in
plugin validator before changing the plugin package:

```bash
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/proton-safe
```

## Documentation workflow

Documentation sources live in `docs/`, with navigation and theme configuration in `mkdocs.yml`.

```bash
uv run mkdocs serve
```

Open the local URL printed by MkDocs. Before committing, run the strict build so broken navigation, links, and configuration warnings fail locally.

Pull requests build the documentation but never deploy it. A push to `main` builds the same sources and deploys the generated static site to GitHub Pages.

## Design rules

Contributions must preserve the restricted capability surface:

1. No send capability.
2. No destructive mail tools.
3. No filesystem paths from MCP clients.
4. No raw received-attachment download tool or received-file persistence; extraction returns only
   bounded text and metadata.
5. Bridge host fixed to `127.0.0.1`.
6. Explicit conversational confirmation before a draft is created.

Plugin skills may explain or orchestrate these controls, but they must not claim to authorize an
action. Account-specific `.app.json` mappings, Bridge credentials, and tunnel API keys must never be
committed.

Read the canonical [`CONTRIBUTING.md`](https://github.com/fbossiere/proton-safe-mcp/blob/main/CONTRIBUTING.md) before opening a pull request.
