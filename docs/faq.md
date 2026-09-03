# Frequently asked questions

## Why is the plugin installed but missing all Proton tools?

The plugin package and its MCP server are loaded in two separate stages. The plugin can be listed
successfully while the bundled `proton-safe-mcp` process exits before MCP tool discovery.

The most common Ubuntu cause is a missing `PROTON_BRIDGE_USER` in the environment that started
Codex. The plugin forwards that variable with `env_vars`; it intentionally does not embed a
personal address. Follow the
[no-tools recovery procedure](troubleshooting.md#plugin-is-installed-but-mcp-shows-no-proton-tools).

## Why is `echo "$PROTON_BRIDGE_USER"` empty when `environment.d` is correct?

Environment changes are not injected into processes that are already running. An existing shell
can remain empty even after the `systemd` user manager has the correct values. The authoritative
check for services launched by the user manager is:

```bash
systemctl --user show-environment |
  awk -F= '$1 == "PROTON_BRIDGE_USER" || $1 == "PROTON_BRIDGE_ALIASES" || $1 == "PROTON_IMAP_PORT" { print $1 "=<set>" }'
```

For a one-off command in the current shell, explicitly load the non-secret file:

```bash
set -a
. ~/.config/environment.d/90-proton-safe.conf
set +a
proton-safe-mcp doctor
```

This does not update other running applications.

## Why did logging out and back in not fix the environment?

The graphical session and the per-user `systemd` manager do not always have the same lifetime. A
user manager can retain its previous environment across a graphical logout. Reload its generators
and verify the result instead of assuming the logout worked:

```bash
systemctl --user daemon-reload
systemctl --user show-environment |
  awk -F= '$1 == "PROTON_BRIDGE_USER" || $1 == "PROTON_IMAP_PORT" { print $1 "=<set>" }'
```

Then quit ChatGPT completely and open a new task. If a launch from the desktop menu still fails,
use the prepared-terminal launch in the
[troubleshooting procedure](troubleshooting.md#plugin-is-installed-but-mcp-shows-no-proton-tools).

## How do I test the user-manager environment separately from ChatGPT?

On a `systemd`-managed Ubuntu session, launch the pinned diagnostic as a transient user service:

```bash
systemd-run --user --wait --pipe \
  uvx --from proton-safe-mcp==2.0.2 proton-safe-mcp doctor
```

The diagnostic prints no credentials, address, mailbox counts, or message content. It proves that
the package, keyring, Bridge, and `systemd` user-manager environment work together. It does not
prove that GNOME passed the same environment to ChatGPT.

If every check passes there but `/mcp` still has no tools, fully quit ChatGPT. Wait until
`pgrep -a -x ChatGPT` prints nothing, then launch the app once from a terminal that has loaded
`~/.config/environment.d/90-proton-safe.conf`, as shown in the
[troubleshooting procedure](troubleshooting.md#plugin-is-installed-but-mcp-shows-no-proton-tools).

## Do I have to start ChatGPT from a terminal every time?

No. The prepared-terminal command is a one-time diagnostic that proves environment inheritance is
the remaining problem. After it succeeds, install the
[persistent per-user menu launcher](troubleshooting.md#make-the-menu-launch-permanent). The normal
ChatGPT icon will then load `PROTON_BRIDGE_USER`, optional `PROTON_BRIDGE_ALIASES`, and
`PROTON_IMAP_PORT` automatically.

The launcher deliberately parses only those non-secret settings. It does not source arbitrary shell
code and never reads, stores, or exports the Bridge password.

## Why can restarting ChatGPT from the menu still fail?

The `systemd` user manager, GNOME Shell, terminals, and ChatGPT are separate processes. Reloading
`environment.d` changes the manager's environment, but it cannot rewrite an already-running GNOME
Shell or ChatGPT environment. A fresh menu launch can therefore inherit GNOME's older values.

There is a second trap: ChatGPT is a single-instance desktop app. Launching `chatgpt` while an old
instance remains can delegate to that old process instead of creating a clean one. Fully quit it
first, then use the prepared-terminal launch documented in troubleshooting.

## What does `NoKeyringError` mean inside an agent or sandbox?

It can mean the diagnostic process cannot reach the desktop Secret Service or D-Bus socket, not
that the saved Bridge credential is missing. Run `proton-safe-mcp doctor` from the normal local
user session or through the `systemd-run` command above. Do not work around a sandbox by storing
the Bridge password in plugin JSON.

## Which values may go in `environment.d`?

Only the non-secret account identifier, optional sending-alias allowlist, and local Bridge port:

```ini
PROTON_BRIDGE_USER=your-address@proton.me
PROTON_BRIDGE_ALIASES=billing@example.com,legal@example.com
PROTON_IMAP_PORT=1143
```

Never store the Proton account password, recovery phrase, 2FA material, or Bridge-generated IMAP
password there. `proton-safe-mcp setup` stores the Bridge credential in the OS keyring.

## Do I need to reinstall Proton Mail Bridge or the plugin?

Usually not. First run the user-manager diagnostic above. Reinstall only when the verified Codex
binary does not list the plugin, `uvx` cannot launch the pinned package, or the privacy-safe
diagnostic identifies a real package or Bridge failure.

## What evidence is safe to include in an issue?

Include:

- the complete `proton-safe-mcp doctor` output;
- whether both variable **names** appear in the redacted `show-environment` check;
- whether `/mcp` lists `proton-safe` and whether it exposes tools;
- the ChatGPT desktop and Codex versions;
- the Proton Safe MCP version and Linux distribution.

Do not include an email address, Bridge password, Proton password, message content, recipient,
subject, tunnel key, or account-specific plugin connection ID.

## Is the plugin required?

No. Direct MCP registration exposes the same server tools. The plugin adds the reviewed mail
workflows and bundles a pinned local STDIO launch configuration. See the
[OpenAI plugin guide](openai-plugin.md#direct-mcp-registration-without-the-plugin).
