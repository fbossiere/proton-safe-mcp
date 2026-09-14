# Windows installer

Status: **in development, not released.** The Windows platform layer, the installer and
the build pipeline exist in this repository; no part of the Windows path has been
validated on Windows. [Every acceptance scenario is Not tested](windows-acceptance.md),
and Proton Safe must not be described as available for Windows until that changes.

This page is for maintainers and contributors. It describes what has been built, the
decisions behind it, and what is still open.

## What the product does on Windows

Proton Safe for Windows 11 x64 is a single signed file,
`ProtonSafe-Setup-<version>-x64.exe`, published beside the Ubuntu `.deb` in the same
GitHub Release. It installs for the current user, with no elevation and no "all users"
mode, and it needs neither Python, nor `uv`, nor a terminal.

The installer places the software. The existing setup assistant makes the connection.
That separation is the same one the Ubuntu package uses, and it is why the PySide6
interface, the MCP engine and the three skills are shared rather than duplicated.

| Decision | Choice |
|---|---|
| Target | Windows 11 Home and Pro, native x64, still-supported versions |
| Install scope | Current user, no UAC, no all-users mode |
| Build | PyInstaller in one-directory mode, built on Windows, wrapped by Inno Setup |
| Installer | Inno Setup 7, pinned by version and digest |
| Interface | French and English, following the system language |
| Bridge password | Windows Credential Manager, current user, this computer only |
| Updates | Run a newer installer; settings and credential are kept |

## The platform layer

Everything the two systems share — the mail engine, the tool limits, the draft rules, the
whole onboarding flow — is one implementation. Five things are not shareable, because the
operating system decides what is safe, and those live in
`src/proton_safe_mcp/platform_services/`:

| Concern | Linux | Windows |
|---|---|---|
| Where files belong | XDG base directories | `SHGetKnownFolderPath`, never a built `C:\Users\…` path |
| Private storage | `0700` / `0600`, `O_NOFOLLOW`, owner uid | A protected DACL; reparse points refused; the opened file confirmed to be the inspected one |
| Session identity | `geteuid`, Wayland or X11 | Token elevation |
| Credential store | Secret Service | Credential Manager, persistence pinned to this computer |
| Starting and reading a child | `select` on pipes, `start_new_session` | A reader thread, `CREATE_NO_WINDOW` |

The POSIX validations are unchanged. A Unix mode has no Windows equivalent, so nothing was
generalised into a weaker rule both platforms could satisfy: where Windows cannot establish
a guarantee, the operation is refused.

### Where files go

| Resource | Location |
|---|---|
| Program | `%LOCALAPPDATA%\Programs\Proton Safe\` |
| Interface | `proton-safe-assistant.exe` in that folder |
| Embedded server | `proton-safe-mcp.exe` in the same folder |
| Configuration | `%LOCALAPPDATA%\Proton Safe\config\config.toml` |
| Connection journal | `%LOCALAPPDATA%\Proton Safe\state\assistant\install.json` |
| State and staged attachments | `%LOCALAPPDATA%\Proton Safe\state\` |
| Managed plugin and local marketplace | `%LOCALAPPDATA%\Proton Safe\data\` |

The program folder and the Inno Setup `AppId` stay the same across versions: that is what
lets an update recognise the existing installation instead of creating a second entry.
Nothing touches `PATH`, file associations, network settings, firewall rules or the
certificate store. The server is always registered by absolute path, so an unrelated
Python installation on `PATH` can never be substituted for it.

### What "private" means here

A protected DACL granting the owning user, `SYSTEM` and `Administrators`, and nobody else.
Protected, so a parent folder someone widened cannot grant access by inheritance. The
check that reads it back is in `platform_services/winacl.py`, deliberately written as
pure Python and tested on every platform — a rule only exercised on the machine where it
is hard to reproduce is a rule nobody checks.

This protects against other ordinary accounts on the computer, and against a secret
accidentally stored in the clear. It does **not** protect against a malicious program
running as the same user, against an administrator, or against a compromised system.

### The Bridge password

Stored through `keyring.backends.Windows.WinVaultKeyring` under the existing service name
`proton-safe-mcp`, with persistence pinned to `CRED_PERSIST_LOCAL_MACHINE`. The library
default in keyring 25.7 is `CRED_PERSIST_ENTERPRISE`, which asks Windows to roam the
credential to the account's other computers; the policy here is narrower on purpose. In
managed mode the file, null and unapproved backends are refused, as is the
`PROTON_BRIDGE_PASSWORD` fallback.

The store self-test writes under a **separate** service, `proton-safe-mcp-selftest`, with
a fresh random key each attempt, and removes both entries Credential Manager may create
for it. Writing under the real service name would make Credential Manager move an existing
credential to a compound target to resolve the account collision — a real secret displaced
by a diagnostic.

The secret never travels in a process argument, an environment variable, a client file or
a log line. The server reads it from the store itself. The Proton account password and its
second factor stay entirely inside Bridge.

## Building it

On a Windows 11 x64 machine:

```powershell
uv sync --frozen --extra dev --extra desktop --extra packaging
$env:PYINSTALLER = "$PWD\.venv\Scripts\pyinstaller.exe"
$env:PROTON_SAFE_PYTHON = "$PWD\.venv\Scripts\python.exe"
pwsh packaging/windows/build_windows.ps1
```

PyInstaller cannot produce a Windows bundle from Linux, so there is no cross-compilation
path. The script refuses to run anywhere else rather than producing something unusable.

What it does, in order: draws the icon from the interface's own code, freezes the bundle
with the shared spec, **runs the bundled executables to prove what they embedded**, signs
the project's own binaries when an identity is configured, compiles the installer with the
pinned Inno Setup, and records the digest, the provenance and the component inventory.

`-SkipInstaller` stops after the bundle, which is what the CI test job uses.

### Artefacts

| File | Contents |
|---|---|
| `ProtonSafe-Setup-<version>-x64.exe` | The signed installer |
| `ProtonSafe-Setup-<version>-x64.exe.sha256` | Its digest, taken after signing |
| `BUILD-PROVENANCE-windows-x64.txt` | Version, commit, run URL, build OS, tool versions, digest, signing identity |
| `SBOM-windows-x64.json` | CycloneDX inventory of the Python distributions and every binary that ships |

These names sit alongside the Ubuntu `BUILD-PROVENANCE.txt`; neither overwrites the other.

### The pinned compiler

`packaging/windows/innosetup.lock` records the Inno Setup version, its download URL and
its SHA-256. **The digest is deliberately unset.** Filling it in means someone downloaded
that exact file from jrsoftware.org, checked the publisher's Authenticode signature on it,
and recorded what they actually received. Until then
`packaging/windows/fetch_innosetup.py` refuses to download, and the CI job reports that no
installer was built rather than building one with an unverified tool.

### Signing

Driven entirely by `PROTON_SAFE_SIGN_COMMAND`, a command line carrying Inno Setup's `$f`
placeholder for the file to sign. No key material is in this repository or in any artefact.
Without it the build still completes and names its output `-unsigned`; that build is a test
build, and the release workflow refuses to publish one.

The project's own executables are signed; third-party binaries keep the signatures their
publishers gave them. The uninstaller is signed through the same tool, and the digest is
taken after signing, because signing changes the file.

**A signature is not a reputation.** Microsoft treats them separately, and SmartScreen may
still warn about a recently published installer. Never tell anyone to disable SmartScreen
or Microsoft Defender, and treat a false positive as something to resolve before calling
the package ready, not as something to explain away.

## Client qualification

The client adapter assumed Linux locations and grouped several OpenAI surfaces together.
Neither assumption carries over.

- Detection is bounded to documented locations, the user's `PATH`, and an explicit
  **Locate an assistant installed elsewhere…** choice in the interface. There is no
  recursive search through profiles or caches.
- `.cmd` and `.bat` launchers are refused rather than driven: running one would mean
  building a command line out of user-controlled paths. The real executable is resolved,
  or the mode is unsupported.
- An absolute `CODEX_HOME` is honoured and never overwritten.
- On Windows the adapter claims **no** shared surfaces. Whether ChatGPT desktop and Codex
  there really share one host and one profile is unverified, and saying so unverified
  would leave someone believing a surface is connected when it is not.

The Windows candidate paths in `openai_local.py` are provisional probes, each still
corroborated by running `--version` and every plugin subcommand. The location a real
Windows client actually uses gets recorded when that client is qualified (W08).

## Update, repair and uninstall

A newer installer recognises the existing installation and updates it in place, keeping the
configuration, the credential, the journal, other plugins and preferences. The same version
offers to repair the files. An older version is refused: the configuration schema the newer
one wrote may not be readable by it.

Restart Manager is asked to close only the processes holding the files being replaced, and
never to force one shut — a running AI client or Bridge belongs to the person using it.
Windows is never restarted, and no restart is scheduled.

Uninstalling runs `proton-safe-assistant.exe --uninstall-connection` in the user's own
session **before** the program files are removed. The uninstaller never edits a client
configuration or touches Credential Manager itself: the assistant owns the journal, the
adapters and the store, so it is the only thing that knows what Proton Safe created. Its
exit code decides what is reported — a client that refused the removal is not announced as
disconnected, and the settings, the credential and the journal are kept for a retry.

Settings and the password are kept by default. Erasing them is an explicit, opt-in choice,
it is strictly targeted, and it is deferred while any client entry is still registered.
Deleting a secret from the store does not revoke one already read into a running server:
the assistant says so rather than claiming a clean disconnection.

## What is still open

Two external dependencies block a stable Windows release, and neither can be settled from
a Linux checkout:

1. **At least one Windows AI client with its full path qualified** — W08 and W09.
2. **A signing identity usable from CI** — W20. Which provider suits depends on the
   maintainer's legal identity, eligibility and cost; some offerings distinguish
   individuals from organisations. Nothing in this repository assumes a purchase.

Neither prevents the implementation from being reviewed or extended. Both prevent
announcing Windows compatibility or publishing a Windows download.
