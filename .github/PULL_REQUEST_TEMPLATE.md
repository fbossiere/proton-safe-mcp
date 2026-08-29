## Summary

<!-- What does this PR change and why? -->

## Security review

<!-- This project's value is its restricted capability surface. Answer explicitly: -->

- [ ] This change adds **no** send, delete, move, or attachment-download capability.
- [ ] This change accepts **no** filesystem paths from MCP clients.
- [ ] New inputs are validated (length, charset, injection) before use.
- [ ] The Bridge host remains hard-coded to `127.0.0.1`.

## Checklist

- [ ] `uv run pytest` passes
- [ ] `uv run ruff check .` and `uv run ruff format --check .` pass
- [ ] `uv run mypy` passes
- [ ] New behavior is covered by tests
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
