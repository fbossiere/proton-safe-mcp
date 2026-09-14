# Acceptance sheet — Windows installer

Every scenario starts at **Not tested** and stays there until someone has actually run it
on Windows. Nothing on this page may be marked passed because the automated suite covers
something similar, because a screenshot looks right, or because a fake client answered as
expected. This sheet is about the real path: Windows 11 x64, a real Proton Mail Bridge, a
real AI client, and a real standard Windows account.

!!! warning "Status: nothing here has been validated"
    **13 September 2026 — every scenario below is Not tested.** The Windows platform
    layer, the installer script, the build pipeline and this sheet exist; no Windows
    machine has run any of it. Two external dependencies are still open and both block a
    stable Windows release:

    - **at least one Windows AI client whose full path is qualified** (W08, W09);
    - **a signing identity usable from CI** (W20).

    Until those are settled, Proton Safe must not be described as available for Windows,
    and no Windows download button may be published. See
    [order of work](#order-of-work).

## How to get the installer

The installer is never committed. Build it on a Windows 11 x64 machine:

```powershell
uv sync --frozen --extra dev --extra desktop --extra packaging
$env:PYINSTALLER = "$PWD\.venv\Scripts\pyinstaller.exe"
$env:PROTON_SAFE_PYTHON = "$PWD\.venv\Scripts\python.exe"
pwsh packaging/windows/build_windows.ps1
```

Without `PROTON_SAFE_SIGN_COMMAND` the build completes and names its output
`ProtonSafe-Setup-<version>-x64-unsigned.exe`. That name is deliberate: an unsigned build
is a test build and must never be published or handed to a non-technical tester as "the
Windows download".

Compiling the installer also needs the pinned Inno Setup recorded in
`packaging/windows/innosetup.lock`. Its version, URL, size and SHA-256 are pinned, and
the lock file records exactly what was checked to arrive at them — including the two
checks left for the machine that builds a release: the ECDSA signature inside the
publisher's `.issig`, and the Authenticode signature, which must read **Pyrsys B.V.**

## Test environment

Fill in before starting. A result recorded without these is not a result.

| | |
|---|---|
| Windows edition, version and build | |
| Native processor architecture | |
| Windows account type (standard / administrator) | |
| Interface language used (fr / en) | |
| Display resolution and scaling | |
| Proton Mail Bridge version | |
| AI client name, version and distribution | |
| Installer SHA-256 | |
| Signing identity (or "unsigned") | |
| Source commit | |
| Tester and date | |

## Scenarios

| ID | Scenario | Passes when | Status |
|---|---|---|---|
| W01 | Clean Windows 11, **standard account**, no Python or `uv` | Installed from the browser download, **no UAC prompt at any point**, shortcut and window usable | Not tested |
| W02 | Offline install, then the fr and en paths | Files install with no download; missing prerequisites are explained on opening, not during install | Not tested |
| W03 | Windows 10, 32-bit, ARM64, WSL, or an elevated run | Refused explicitly, naming the scope, **before anything is written**; no silent adaptation under WSL | Not tested |
| W04 | Account and paths with spaces, accents and special characters | Install, JSON/TOML, activation, update and uninstall all work; nothing is interpreted as a command | Not tested |
| W05 | Credential Manager, then a full restart | The same secret is readable by the server under the same account; no secret-bearing variable is needed | Not tested |
| W06 | Credential Manager refused, or an unapproved backend | Blocked clearly; no secret written anywhere else; the self-test modifies no existing entry | Not tested |
| W07 | Real Bridge: absent, stopped, wrong secret, correct secret | Each is diagnosed specifically; a new secret is tested before it replaces a working one; no mailbox content is read during the test | Not tested |
| W08 | A real client, then a missing or incompatible one | Activation completes for the qualified client; absence or incompatibility is stated honestly, never worked around | Not tested |
| W09 | The server started by the client itself | The absolute path of the embedded `.exe`, the right profile and credential, no stray console, the expected MCP surface | Not tested |
| W10 | Deliberate use on a **test account** | Search, read, bounded extraction and a confirmed draft, under the existing rules; nothing is sent | Not tested |
| W11 | Update N to N+1 with a live connection | Settings and secret kept, plugin refreshed, exactly one connection; locked files handled without killing the client | Not tested |
| W12 | The same version, then an older one | Repairing files is offered; the downgrade is refused with nothing lost | Not tested |
| W13 | Cancel, out of disk space, and a failure mid-replacement | The last complete installation is recoverable; resume is demonstrable; never a mixed bundle | Not tested |
| W14 | An earlier installation and other plugins present | Take-over is explicit, no duplicate is created, other people's resources are untouched | Not tested |
| W15 | Standard uninstall, then reinstall | Managed registrations removed, binaries and shortcuts gone, settings kept and found again | Not tested |
| W16 | Erase requested, or client removal failing | The erase is strictly targeted; state is kept when removal is incomplete; revocation is never falsely announced | Not tested |
| W17 | Two Windows accounts, wide ACLs, a junction, a locked file | Ordinary accounts are isolated, dangerous redirections refused, errors actionable | Not tested |
| W18 | A server that hangs, floods output, or never exits | Deadlines and volume limits hold; the window stays responsive; no diagnostic process is left behind | Not tested |
| W19 | Accessibility and displays | Keyboard and Narrator, light, dark and high contrast, 100/150/200 % scaling, 1280×720 and 1920×1080; actions always reachable | Not tested |
| W20 | The signed file downloaded with Defender and SmartScreen active | Signature and publisher verified, the observed result recorded as it happened, **no protection disabled** | Not tested |
| W21 | Ubuntu and Python package non-regression | The existing checks still pass; no weakening of the Linux policy; no Qt added to the PyPI server package | Not tested |

## What "passed" means for each result

Record, per scenario: the date, the Windows build, the Bridge and client versions, the
Windows account type, the interface language, the display resolution, the installer's
SHA-256 and the source commit. A scenario run with a fake client, or demonstrated with a
screenshot alone, is not that scenario.

W01 deserves particular care. GitHub's Windows runners sign in as an administrator, so the
automated silent install in CI proves the installer completes unattended and returns 0 —
and proves **nothing** about whether a UAC prompt appears. Only a standard account settles
that.

## Order of work

1. **Settle the unknowns before finishing the installer.** Credential Manager with local
   persistence; the native file protections; the embedded STDIO server started by a real
   Windows client; activation in that client. Produce evidence for each. The Inno Setup
   digest is pinned; confirm its Authenticode publisher on Windows at the same time.
2. **Port the platform services**, keeping the Linux security tests and adding their
   Windows equivalents. Largely done: see `src/proton_safe_mcp/platform_services/`,
   `tests/test_platform_services.py` and `tests/test_windows_behaviour.py`.
3. **Build the installer and the maintenance paths**, then test them on a clean machine
   with a standard account — scenarios W01 to W19.
4. **Wire signing and publication**, then complete this sheet with the versions actually
   validated, and only then publish a Windows download.

A successful build, or an installer that opens, is not any of these.

## Product metadata

`pyproject.toml` still declares `Operating System :: POSIX :: Linux` and nothing else. That
is deliberate: a classifier is a compatibility claim, and the PyPI server package has not
been validated on Windows. Adding `Operating System :: Microsoft :: Windows` is part of
closing W21, not a preparatory step.

The same rule governs the website. `docs/download.md` and `docs/fr/telecharger.md` list
Windows as *not available* and link to the status rather than to a file. A Windows download
button may be published only once the artefact exists, is signed, and has been verified.

## Diagnostics

What a tester may share from a run: versions, check codes, step names, timings and
results. What must not leave the machine: passwords, email addresses, paths containing a
personal name, message content and raw client output. The installer's own log stays local;
nothing is sent anywhere automatically.
