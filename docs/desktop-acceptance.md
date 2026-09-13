# Acceptance sheet — desktop assistant

Short sheet to fill in on the target system. Every line starts at **Not tested** and stays
there until someone has actually run it. Do not mark a line as passed because the automated
suite covers something similar: this sheet is only about the real path on Ubuntu 24.04 with
a real Proton Mail Bridge and a real ChatGPT desktop / Codex installation.

**Maintainer report, 13 September 2026:** the installed assistant was tested and reported
working successfully. The report did not enumerate individual scenarios or environment
versions, so it does not mark the eleven lines below as passed. This remains a worksheet
for a detailed acceptance run. See [Desktop validation](desktop-testing.md) for automated
and historical implementation evidence.

## How to get the package

The `.deb` is never committed. Download it from the [GitHub Release](https://github.com/fbossiere/proton-safe-mcp/releases/tag/v2.1.2),
which also carries `BUILD-PROVENANCE.txt` (package name, SHA-256, source commit
and build host) and the `.sha256` file. For an unreleased change, use the CI
`desktop-package` artefact instead. Before installing:

```bash
sha256sum -c proton-safe-assistant_<version>_amd64.deb.sha256
```

Check that the source commit in `BUILD-PROVENANCE.txt` is the commit you meant to test.

To build it yourself instead:

```bash
uv sync --frozen --extra dev --extra desktop --extra packaging
PYINSTALLER="$(pwd)/.venv/bin/pyinstaller" bash packaging/build_bundle.sh
bash packaging/build_deb.sh
```

## Test environment

Fill in before starting.

| | |
|---|---|
| Ubuntu version and architecture | |
| Session type (Wayland / X11) | |
| Display resolution and scaling | |
| Proton Mail Bridge version | |
| ChatGPT desktop / Codex version | |
| Package SHA-256 | |
| Source commit | |
| Tester and date | |

## Scenarios

Mark exactly one box per line. Add the observed behaviour for anything that is not a clean
pass.

| # | Scenario | Passed | Failed | Not tested | Notes |
|---|---|:---:|:---:|:---:|---|
| 1 | **Fresh graphical installation** — the `.deb` opens and installs from the graphical package installer, with no terminal and no extra tool to install first; **Proton Safe** then appears in the applications menu and opens. | ☐ | ☐ | ☒ | |
| 2 | **Keyring and Bridge connection** — the keyring line passes (system dialog appears and unlocking works if locked), the Bridge password is accepted, and the credential is stored. Bridge reports no message as read afterwards. | ☐ | ☐ | ☒ | |
| 3 | **Activation in the real client** — the detected assistant is registered; ChatGPT desktop and Codex appear as one shared connection, not two. Record the exact `codex plugin` commands accepted or rejected. | ☐ | ☐ | ☒ | |
| 4 | **The runtime actually launched** — the MCP server the client starts is `/opt/proton-safe-assistant/proton-safe-mcp` with `--config`, not `uvx` and not another installation. Confirm from the client's own MCP view or process list. | ☐ | ☐ | ☒ | |
| 5 | **Search for a test message** — in the client, find a message sent to the test account. This is the first deliberate use, not a technical test. | ☐ | ☐ | ☒ | |
| 6 | **Confirmed draft, nothing sent** — prepare a draft after explicit confirmation; it lands in `Drafts` in Proton Mail and is **not** sent. Confirm no message left the account. | ☐ | ☐ | ☒ | |
| 7 | **Full restart** — restart the session or the machine, open Bridge and the client normally, and confirm the connection still works **with no `PROTON_*` variable exported anywhere**. | ☐ | ☐ | ☒ | |
| 8 | **Repair** — change the Bridge password in Bridge, confirm the assistant reports an authentication failure specifically, then repair it. The previous credential must only be replaced after the new one is accepted. | ☐ | ☐ | ☒ | |
| 9 | **Migration of an existing installation** — with `proton-safe@personal` already installed, run the assistant: the plan is shown first, the take-over choice appears **unticked**, ticking it completes the migration, the working credential is reused without retyping, exactly one Proton Safe server remains, other plugins and the `personal` marketplace survive, and `uv` / Python / `environment.d` are left alone. | ☐ | ☐ | ☒ | |
| 10 | **Disconnection** — only the assistant's own entries are removed; other plugins, Bridge, mail, drafts and attachments are untouched. A still-running server is announced as needing a client restart rather than claimed revoked. | ☐ | ☐ | ☒ | |
| 11 | **Disconnection refused by the client** — make the removal fail, confirm the configuration, credential and tracking record are all kept, that reopening shows the installation as needing repair, and that a retry after fixing the client both removes the entries and carries out any deferred erase. | ☐ | ☐ | ☒ | |

## Additional observations

| Item | Result |
|---|---|
| Window usable at 1280 × 720 | ☐ passed ☐ failed ☒ not tested |
| Window usable at 200 % scaling | ☐ passed ☐ failed ☒ not tested |
| Full keyboard navigation on a real display | ☐ passed ☐ failed ☒ not tested |
| Cancelling a slow step leaves nothing written | ☐ passed ☐ failed ☒ not tested |
| Time from opening the installer to the first result | |
| Time spent downloading prerequisites (counted separately) | |

## Reporting

Report only the operating system, the versions, the step that blocked, the elapsed time and
the outcome. Never include mail content, an email address or a credential — and never share
the Bridge password with anyone, including an AI assistant.
