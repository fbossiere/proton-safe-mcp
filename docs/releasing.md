# Releasing

Releases publish the Python distributions to PyPI with GitHub OIDC and then publish the matching
metadata to the official MCP Registry. The same workflow builds the Ubuntu installer from
the release tag and attaches its `.deb`, SHA-256 and provenance to the GitHub Release. No long-lived PyPI or MCP Registry token is stored in GitHub.

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
   the lockfile, plugin runtime pin and cache version, documentation links, and `CHANGELOG.md` to the same semantic version.
2. Run the complete quality gate from [Development](development.md).
3. Merge the release changes to `main`.
4. Create and push a signed tag at the merged release commit, exactly `v` followed by the
   package version (for example `v2.1.0`). Create a **draft** GitHub Release for that tag,
   with the release notes. Do not publish it yet: this repository uses immutable releases.
5. Start the **Release** workflow on the **tag**, with its `tag` input set to the same value:

   ```bash
   gh workflow run release.yml --ref v2.1.0 -f tag=v2.1.0
   ```

The dispatched `.github/workflows/release.yml` workflow verifies version
consistency, rebuilds and tests the Python distributions and Ubuntu desktop package. Both
builds must succeed before either installer upload or PyPI publishing starts; registry
publication follows successful PyPI publication. The installer assets are attached while
GitHub Release is still a draft. Only after the installer, PyPI and registry jobs succeed
does the final job publish the GitHub Release and mark it latest. This respects release
immutability: assets cannot be added afterwards. Do not attach local build artefacts manually.

If a job fails, correct the cause and rerun the failed jobs; do not rerun a successful PyPI
upload or replace an immutable version. A registry-only dispatch deliberately leaves GitHub
Release publication alone; after recovery, rerun the failed original job chain to finish it.

The release build installs the optional desktop dependencies for strict typing and Qt
interface tests. The desktop job runs the packaged runtime handshake and archive tests on
Ubuntu 24.04. Qt remains optional for people installing the server from PyPI.

If PyPI succeeds but the MCP Registry rejects the metadata, fix and merge `server.json`, then run
the **Release** workflow manually from `main` with the original release tag and
**Republish only MCP Registry metadata** enabled. This recovery path checks that both versions in
`server.json` still match the requested tag and does not rebuild or re-upload the immutable PyPI
distribution.

## Verify publication

- Confirm every Release workflow job succeeded, including **Attach Ubuntu installer to draft release**
  and **Publish completed GitHub Release**.
- Download the `.deb`, its `.sha256` and `BUILD-PROVENANCE.txt` from the release; check the
  digest and verify the recorded source commit matches the signed tag.

- PyPI: `https://pypi.org/project/proton-safe-mcp/`
- MCP Registry API:
  `https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.fbossiere/proton-safe-mcp`
- Clean installation:

  ```bash
  uvx --from proton-safe-mcp==2.1.0 proton-safe-mcp --help
  ```
