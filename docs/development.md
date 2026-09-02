# Development

The test suite fakes the IMAP layer, so Proton Mail Bridge is not required for development.

## Setup

```bash
git clone https://github.com/fbossiere/proton-safe-mcp.git
cd proton-safe-mcp
uv sync --extra dev --extra docs
```

## Quality gate

Run the same checks as CI:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --cov
uv run mkdocs build --strict
```

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
6. Explicit confirmation for direct drafts; optional enhanced approval outside MCP.

Plugin skills may explain or orchestrate these controls, but they must not claim to authorize an
action. Account-specific `.app.json` mappings, Bridge credentials, and tunnel API keys must never be
committed.

Read the canonical [`CONTRIBUTING.md`](https://github.com/fbossiere/proton-safe-mcp/blob/main/CONTRIBUTING.md) before opening a pull request.
