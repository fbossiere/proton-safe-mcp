# Releasing

Releases publish the Python distributions to PyPI with GitHub OIDC and then publish the matching
metadata to the official MCP Registry. No long-lived PyPI or MCP Registry token is stored in GitHub.

## One-time repository setup

1. Sign in to PyPI and open **Your account > Publishing > Add a new pending publisher**.
2. Use these values:

   | Field | Value |
   | --- | --- |
   | PyPI project name | `proton-safe-mcp` |
   | GitHub owner | `fbossiere` |
   | Repository | `proton-safe-mcp` |
   | Workflow | `release.yml` |
   | Environment | `pypi` |

3. In GitHub, create an environment named `pypi`. Restrict deployments to version tags when the
   repository plan supports deployment branch and tag rules.

The pending publisher creates the PyPI project during the first successful workflow run. Do not
manually upload the same version first.

## Prepare a release

1. Update `src/proton_safe_mcp/__init__.py`, `server.json`, the package version inside `server.json`,
   the documentation version, and `CHANGELOG.md` to the same semantic version.
2. Run the complete quality gate from [Development](development.md).
3. Merge the release changes to `main`.
4. Create a GitHub release whose tag is exactly `v` followed by the package version, for example
   `v1.2.0`.

Publishing the GitHub release starts `.github/workflows/release.yml`. The workflow verifies version
consistency, rebuilds and tests the distributions, publishes them to PyPI, and only then publishes
`server.json` to the MCP Registry.

If PyPI succeeds but the MCP Registry rejects the metadata, fix and merge `server.json`, then run
the **Release** workflow manually from `main` with the original release tag and
**Republish only MCP Registry metadata** enabled. This recovery path checks that both versions in
`server.json` still match the requested tag and does not rebuild or re-upload the immutable PyPI
distribution.

## Verify publication

- PyPI: `https://pypi.org/project/proton-safe-mcp/`
- MCP Registry API:
  `https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.fbossiere/proton-safe-mcp`
- Clean installation:

  ```bash
  uvx --from proton-safe-mcp==1.2.0 proton-safe-mcp --help
  ```
