# Desktop validation

This page separates what is already proven by automated tests from what still needs a human
with a real Proton Mail Bridge and a real client. Nothing below is claimed as validated
until someone has actually run it.

## Validation report

Implementation environment: Debian 12 container, x86_64, Python 3.13, **no D-Bus session,
no Secret Service daemon, no Proton Mail Bridge, no ChatGPT desktop or Codex installation,
and no Wayland or X11 session**. That environment determines what could and could not be
proven.

| Area | Real here | Simulated | Not tested |
|---|---|---|---|
| Configuration loading, schema, permissions, atomic writes | Real files, real `chmod`, real symlinks and a real foreign-owner case | — | — |
| Managed vs historic mode, credential policy | Real `Settings` loading with a contradictory environment | Keyring behaviour, through an in-memory approved backend | A real `gnome-keyring` session |
| Bridge authentication and error classification | — | IMAP doubles that record every command issued | A real Proton Mail Bridge |
| MCP runtime | Real: the installed executable is started as a child process and answers `initialize` and `tools/list` with the 13 reviewed tools | — | — |
| Packaged bundle | Real, on Debian 12 locally and on Ubuntu 24.04 in CI: the bundle is built, the `.deb` assembled, the archive contents checked, and the assistant renders the plugin and starts its embedded runtime | — | Installation through Ubuntu's graphical package installer, and running the interface on a real display |
| Client registration | — | A Codex-like fake that models marketplace names, capability probes and refusals | **The real `codex plugin` commands** |
| Interface | Real widgets on Qt's `offscreen` platform: keyboard reach, accessible names, status text, secret handling, cancellation, the whole wizard | — | Wayland, X11, 1280 × 720, 200 % scaling on a real display |
| Keyring backend packaging | Real: the built bundle is asked whether it carries the Secret Service backend, and distinguishes that from an unreachable session | — | Storing and reading a credential in a real keyring |

Two defects were found by these tests and fixed rather than worked around: the Bridge screen
decided whether to take the typed secret from widget visibility, which left the secret in the
field on a window that was not shown; and the client check treated "this client cannot list
its plugins" as "the plugin is gone".

### Batch 0 is partially validated

The specification's batch 0 asks for proof of the distribution path before the rest is built.
Half of it is proven and half is not:

| Batch 0 item | Status |
|---|---|
| Read the repository's instructions and reconcile the specification with HEAD | **Done.** HEAD is v2.0.3, not the v2.0.0 the specification was written against; the later changes were kept. |
| Produce a minimal desktop package that starts, reaches the keyring and launches the embedded MCP runtime | **Partially validated.** On Ubuntu 24.04 in CI, the package builds, the bundled runtime starts and completes an MCP handshake, and the build proves the Secret Service backend is embedded and loadable. But it has never *reached* a real keyring, and the interface has never run on a real display, because CI has neither. |
| Verify the target client and the local plugin path on a real version | **Not validated.** No ChatGPT desktop or Codex installation was available. |
| Record versions, constraints and any change needed to the `.deb` / PySide6 choice | **Done.** Recorded in the version matrix above; neither choice needed to change, and `PySide6-Essentials` was chosen over the full `PySide6` to keep the bundle smaller. |

Batch 0 therefore stays **partially validated** until the acceptance sheet's first four
scenarios pass on the target system. Building on Ubuntu 24.04 is not installing on it: the
graphical installer, the session keyring, Bridge and the client are all still unproven. Batches 1 to 4 were implemented on that basis, which is
a deliberate, stated risk rather than an oversight: the client adapter is the part most
likely to need revision once a real client answers.

## Version matrix

| Component | Version the code targets | Status |
|---|---|---|
| Ubuntu | 24.04 LTS, x86_64 | **Build verified.** CI builds the bundle and the `.deb` on `ubuntu-24.04`, and the bundled runtime starts there and completes an MCP handshake. **Installing and running the application on Ubuntu is still untested**: the runner has no display, no keyring daemon, no Bridge and no client. |
| Python runtime | Bundled by PyInstaller; built with 3.12 in CI, 3.13 locally | Bundle verified: it starts and serves MCP. |
| PySide6 | `PySide6-Essentials` 6.11.2 | Screens exercised on Qt's `offscreen` platform, on Debian 12 locally and on `ubuntu-24.04` in CI. **No Wayland or X11 session tested.** |
| Proton Mail Bridge | Any version exposing local IMAP with STARTTLS | **Not tested**: no Bridge was reachable during implementation. |
| ChatGPT desktop / Codex | Version exposing `plugin`, `plugin marketplace add`, `plugin add`, `plugin list` | **Not tested**: no client was installed during implementation. Capabilities are probed at runtime from the client's own `--help`, not guessed from a version number. |
| Keyring | Secret Service (`gnome-keyring`) | Policy tested with an in-memory backend. The packaged build is checked to actually contain the Secret Service backend, on Debian 12 and on Ubuntu 24.04. **No real `gnome-keyring` session tested.** |

## What the automated tests cover

Run the whole suite with:

```bash
uv sync --frozen --extra dev --extra desktop
QT_QPA_PLATFORM=offscreen uv run pytest -q
```

| Specification ID | Covered by |
|---|---|
| A01 historic mode unchanged | `tests/test_managed_mode.py` |
| A02 managed file beats a contradictory environment | `tests/test_managed_mode.py` |
| A03 no environment credential fallback when managed | `tests/test_managed_mode.py` |
| A04 missing, unknown-schema, symlinked or permissive file | `tests/test_configuration_store.py` |
| A05 wrong new secret keeps the working installation | `tests/test_onboarding_service.py` |
| A06 interruption between commit and registration | `tests/test_onboarding_service.py` |
| A07 two identical runs, no duplicate | `tests/test_onboarding_service.py` |
| A08 unmanaged or edited entry is a visible conflict | `tests/test_onboarding_service.py` |
| A09 restart with no exports | `tests/test_managed_mode.py`, `tests/test_runtime_probe.py` |
| A10 MCP initialisation of the packaged runtime | `tests/test_runtime_probe.py` (real subprocess, real MCP handshake) |
| A11 no mail read or written during installation | `tests/test_onboarding_service.py` |
| A12 adversarial client output never leaks | `tests/test_onboarding_service.py` |
| A13 locked or unapproved keyring blocks | `tests/test_onboarding_service.py` |
| A14 cancellation during a slow test | `tests/test_onboarding_service.py`, `tests/test_desktop_app.py` |
| A15 removal touches only managed resources | `tests/test_onboarding_service.py` |
| A16 historic plugin migration | `tests/test_onboarding_service.py` |
| A17 engine works without Qt | `tests/test_managed_mode.py`, `tests/test_desktop_package.py` |
| A18 package update and plugin resources | `tests/test_onboarding_service.py` |
| A19 local success is never a client confirmation | `tests/test_onboarding_service.py`, `tests/test_desktop_app.py` |

The package itself is verified by building it:

```bash
uv sync --frozen --extra dev --extra desktop --extra packaging
PYINSTALLER="$(pwd)/.venv/bin/pyinstaller" bash packaging/build_bundle.sh
bash packaging/build_deb.sh
```

`build_bundle.sh` runs the built executables rather than inspecting files: it starts the
bundled runtime, checks that the Secret Service backend really travelled with it, renders
the managed plugin from the embedded resources and performs an MCP handshake against the
embedded runtime. A bundle that starts on a developer's machine is not evidence that these
dependencies were embedded, which is why the checks run the artefact.

## Getting a package to test

The `.deb` is never committed to the repository. The CI `desktop` job uploads a
`desktop-package` artefact holding the package, its `.sha256` file and
`BUILD-PROVENANCE.txt`, which records the package name, its SHA-256, the engine version, the
source commit it was built from and the build host. Verify the download with
`sha256sum -c` and check the commit before installing.

## What still needs a human

Record the outcome on the [acceptance sheet](desktop-acceptance.md), which has a
passed / failed / not tested box per scenario. Everything on it is currently **not tested**.


Do this on a clean Ubuntu 24.04 install with no `uv`, no Git, no user `pip` and no Python
development environment, with Proton Mail Bridge and ChatGPT desktop or Codex already
installed and signed in. Use a test Proton account. **Never share the Bridge password with
anyone, including an AI assistant.**

Time the prerequisite downloads separately from the assistant itself.

### 1. Install and first run

1. Download the `.deb` and open it with the graphical package installer only — no terminal.
   *If this requires installing a non-standard tool first, record that as a blocker: the V1
   goal is a path with no terminal.*
2. Open **Proton Safe** from the applications menu.
3. Record: does the window open on Wayland? On X11? At 1280 × 720? At 200 % scaling?

### 2. Connect

4. Walk the flow to **Connecter Bridge**. Type the address, the port shown by Bridge and the
   Bridge-generated password.
5. Confirm: the field is masked, pasting works, the reveal button is explicit, and the field
   clears after the test.
6. Confirm the system keyring dialog appears if the keyring is locked, and that unlocking it
   lets the step continue.
7. Confirm Bridge reports no message as read afterwards.

### 3. Enable in the client

8. Choose the detected assistant. Confirm ChatGPT desktop and Codex appear as **one** shared
   connection, not two.
9. Run the activation. Record the exact commands the client accepted or rejected — this is
   the step with no automated coverage, because the client's plugin subcommands could not be
   verified during implementation.
10. Restart the client, open a new conversation, and paste the copyable prompt. Confirm the
    Proton Safe tools appear.
11. Press **J'ai vérifié dans mon assistant** and confirm the status becomes ready.

### 4. Persistence, repair, removal

12. Close and reopen the assistant from the menu. Confirm it opens on the status table.
13. Restart the session or the machine. Open Bridge and the client normally. Confirm the
    connection still works **with no `PROTON_*` variable exported anywhere**.
14. Change the password in Bridge. Confirm the assistant reports a specific authentication
    failure, then repair it and confirm the old credential was only replaced after the new
    one was accepted.
15. Cancel a slow test mid-flight and confirm nothing was written.
16. Disconnect. Confirm other plugins survive and the client is told a restart is needed.
17. Install an updated package. Confirm the configuration and credential survive and that
    the plugin version changed.

### 5. Usability target

Proposed threshold, to validate rather than to claim: **at least 3 testers out of 5 reach
their first result in under 10 minutes, with no terminal and no spoken help**, after Bridge
and the client are already installed and signed in.

Collect, with consent, only: operating system, versions, the step that blocked, the elapsed
time and the outcome. Never collect mail content or an identifier.

## Known gaps at the end of this implementation

- No real Proton Mail Bridge, ChatGPT desktop, Codex, `gnome-keyring` session or graphical
  session was available. Everything depending on those is **untested**, not "expected to
  work".
- The client's plugin subcommands come from this project's own documented procedure. The
  adapter probes each one with `--help` before using it and reports an unsupported client
  instead of guessing, but the successful path has not been observed.
- The build machine used for validation lacked the Qt xcb system libraries. They are
  declared in the package's `Depends`, and CI installs them on `ubuntu-24.04`, but the xcb
  platform plugin has not been exercised in a real X11 session.
- The application icon is the project's banner artwork placed in `/usr/share/pixmaps`. A
  dedicated square icon is still to be produced.
- Only French and English strings exist, and only French has been reviewed in context.
