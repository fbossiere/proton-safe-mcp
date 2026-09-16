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
   the lockfile, plugin runtime pin and cache version, runtime examples, and `CHANGELOG.md` to the same semantic version.
   Keep the website installer buttons and checksums on the previous published version until the
   new assets have been published and verified; update those in the follow-up described below.
2. Run the complete quality gate from [Development](development.md).
3. Merge the release changes to `main`.
4. Create and push a signed tag at the merged release commit, exactly `v` followed by the
   package version (for example `v2.2.0`). Create a **draft** GitHub Release for that tag,
   with the release notes. Do not publish it yet: this repository uses immutable releases.
5. Start the **Release** workflow on the **tag**, with its `tag` input set to the same value:

   ```bash
   gh workflow run release.yml --ref v2.2.0 -f tag=v2.2.0
   ```

   Add `-f include_windows=true` **only** once a Windows client is qualified and the
   signing identity works in CI. With it on, the Windows build, its test run, its
   signature and its unattended install/uninstall check all become blocking: the release
   will not publish anything if any of them fails, and it refuses an unsigned installer
   outright. With it off — the default — the release is Ubuntu and PyPI only, exactly as
   before, and no Windows asset or claim appears anywhere.

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

After the new installer is publicly available, update the website download links and verified
checksums using the [download maintenance checklist](launch.md#keep-downloads-coherent-at-every-release).
The site may keep offering the previous verified installer until that follow-up is deployed.

## Verify publication

- Confirm every Release workflow job succeeded, including **Attach Ubuntu installer to draft release**
  and **Publish completed GitHub Release**.
- Download the `.deb`, its `.sha256` and `BUILD-PROVENANCE.txt` from the release; check the
  digest and verify the recorded source commit matches the signed tag.
- For a Windows release, also download `ProtonSafe-Setup-<version>-x64.exe`, its `.sha256`,
  `BUILD-PROVENANCE-windows-x64.txt` and `SBOM-windows-x64.json`. Check the digest, confirm
  the recorded commit, and verify the Authenticode signature and its chain on the file as
  downloaded through a browser, with its mark-of-the-web and Microsoft Defender active.
  Record what SmartScreen actually did in [the acceptance sheet](windows-acceptance.md);
  never advise anyone to turn a protection off.

- PyPI: `https://pypi.org/project/proton-safe-mcp/`
- MCP Registry API:
  `https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.fbossiere/proton-safe-mcp`
- Clean installation:

  ```bash
  uvx --from proton-safe-mcp==2.3.0 proton-safe-mcp --help
  ```
