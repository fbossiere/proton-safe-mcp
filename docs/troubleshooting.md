# Troubleshooting

Start with the privacy-safe diagnostic:

```bash
proton-safe-mcp doctor
```

It checks the supported runtime and platform, configuration, state-directory permissions,
credential lookup, and Bridge connectivity without printing email addresses, credentials, mailbox
counts, or message content.

## Quick symptom map

| Symptom | Likely layer | First check |
| --- | --- | --- |
| Plugin is installed but `/mcp` shows no Proton tools | MCP server exited before tool discovery | Check the user-manager variables below |
| `PROTON_BRIDGE_USER is required` | Codex did not inherit the account variable | Reload `environment.d` and verify names |
| `echo "$PROTON_BRIDGE_USER"` is empty after a reload | Current shell kept its old environment | Check `systemctl --user show-environment`; source the file only for a CLI test |
| `doctor` passes through `systemd-run` but the plugin has no tools | GNOME or ChatGPT kept an older environment | Fully quit, then launch ChatGPT once from the prepared terminal |
| `NoKeyringError` appears only inside a sandbox | That process cannot reach the desktop keyring | Run `doctor` from the normal user session; do not copy the password into plugin JSON |
| Bridge authentication fails everywhere | Bridge, port, or stored Bridge credential | Check Bridge and rerun `setup` if its credential changed |

## Startup and configuration

### Plugin is installed but `/mcp` shows no Proton tools

This means installation and MCP startup are different states. The bundled plugin can be present
while its local STDIO server exits before returning its tool list. OpenAI's Codex MCP configuration
distinguishes between `env`, which sets a value, and `env_vars`, which only allows and forwards a
value already present in Codex's local environment. Proton Safe deliberately uses `env_vars` so a
personal address is not committed to the plugin package.

Use this sequence on Ubuntu:

1. Confirm the plugin is installed with the same verified Codex binary used during installation:

   ```bash
   "$CODEX_BIN" plugin list
   ```

2. Confirm the non-secret file exists and contains assignments in `KEY=VALUE` form, without
   `export`:

   ```ini
   PROTON_BRIDGE_USER=your-address@proton.me
   PROTON_BRIDGE_ALIASES=billing@example.com,legal@example.com
   PROTON_IMAP_PORT=1143
   ```

3. Reload the user environment generator:

   ```bash
   systemctl --user daemon-reload
   ```

4. Verify only the variable names, without printing their values:

   ```bash
   systemctl --user show-environment |
     awk -F= '$1 == "PROTON_BRIDGE_USER" || $1 == "PROTON_BRIDGE_ALIASES" || $1 == "PROTON_IMAP_PORT" { print $1 "=<set>" }'
   ```

   The two required names must appear, plus `PROTON_BRIDGE_ALIASES` when configured. Logging out
   and back in is not a substitute for this check; the user manager may have retained its earlier
   environment.

5. Test the corrected user-manager environment with the plugin's pinned runtime:

   ```bash
   systemd-run --user --wait --pipe \
     uvx --from proton-safe-mcp==2.0.1 proton-safe-mcp doctor
   ```

   This privacy-safe command separates environment, keyring, and Bridge failures before ChatGPT is
   involved. It does **not** prove that GNOME or an already-running ChatGPT process inherited the
   same variables.

6. Quit ChatGPT completely, including background processes, reopen it, start a new task, and type
   `/mcp`. The `proton-safe` server should now list its tools.

7. If the menu relaunch still has no tools, quit ChatGPT again. Confirm that no old application
   process remains:

   ```bash
   pgrep -a -x ChatGPT
   ```

   Wait until the command prints nothing. Then launch ChatGPT from a terminal that explicitly
   loads the same non-secret file:

   ```bash
   set -a
   . ~/.config/environment.d/90-proton-safe.conf
   set +a
   chatgpt
   ```

   An Electron single-instance launch can hand control to an older process, so starting this
   command before the previous instance exits will not repair its environment. After the app
   opens, create a new task and check `/mcp` again.

#### Make the menu launch permanent

The terminal launch above is only a diagnostic. You do **not** need to type it every time. If it
restores the plugin, create a per-user launcher that keeps the normal `ChatGPT` desktop ID and
loads only the two allowed settings.

Create the private executable directory if needed:

```bash
mkdir -p ~/.local/bin
```

Then create `~/.local/bin/chatgpt-proton-safe` with this content:

```sh
#!/bin/sh

set -eu

settings_file="${XDG_CONFIG_HOME:-$HOME/.config}/environment.d/90-proton-safe.conf"

if [ ! -r "$settings_file" ]; then
    printf 'ChatGPT launcher: cannot read %s\n' "$settings_file" >&2
    exit 1
fi

proton_bridge_user=""
proton_bridge_aliases=""
proton_imap_port=""

# Parse only the non-secret settings; never evaluate the file as shell code.
while IFS='=' read -r setting_name setting_value; do
    # environment.d accepts quoted values. Remove one matching outer quote pair
    # without evaluating substitutions, commands, or backslash escapes.
    case "$setting_value" in
        \"*\") setting_value=${setting_value#\"}; setting_value=${setting_value%\"} ;;
        \'*\') setting_value=${setting_value#\'}; setting_value=${setting_value%\'} ;;
    esac

    case "$setting_name" in
        PROTON_BRIDGE_USER) proton_bridge_user=$setting_value ;;
        PROTON_BRIDGE_ALIASES) proton_bridge_aliases=$setting_value ;;
        PROTON_IMAP_PORT) proton_imap_port=$setting_value ;;
    esac
done < "$settings_file"

if [ -z "$proton_bridge_user" ]; then
    printf 'ChatGPT launcher: PROTON_BRIDGE_USER is missing from %s\n' "$settings_file" >&2
    exit 1
fi

case "$proton_imap_port" in
    ''|*[!0-9]*)
        printf 'ChatGPT launcher: PROTON_IMAP_PORT must be numeric in %s\n' "$settings_file" >&2
        exit 1
        ;;
esac

export PROTON_BRIDGE_USER="$proton_bridge_user"
export PROTON_BRIDGE_ALIASES="$proton_bridge_aliases"
export PROTON_IMAP_PORT="$proton_imap_port"
exec /usr/bin/chatgpt "$@"
```

Make the script executable, copy the system desktop entry to the per-user application directory,
and replace only its launch command:

```bash
chmod 0755 ~/.local/bin/chatgpt-proton-safe
mkdir -p ~/.local/share/applications
cp /usr/share/applications/chatgpt.desktop ~/.local/share/applications/chatgpt.desktop
sed -i "s|^Exec=.*|Exec=$HOME/.local/bin/chatgpt-proton-safe %U|" \
  ~/.local/share/applications/chatgpt.desktop
update-desktop-database ~/.local/share/applications
```

Verify that Ubuntu resolves the normal desktop ID to the per-user entry:

```bash
gio mime x-scheme-handler/codex
```

The default application should be `chatgpt.desktop`. Fully quit the stale ChatGPT process one last
time, then use the normal icon. Future menu and dock launches will load the Proton settings without
a terminal. The wrapper never reads or exports `PROTON_BRIDGE_PASSWORD`.

The per-user desktop entry shadows the packaged one. After a ChatGPT package upgrade, compare
`/usr/share/applications/chatgpt.desktop` with the per-user copy and refresh the copy if OpenAI
added desktop-entry fields; then reapply the `Exec=` replacement above.

Do not add `PROTON_BRIDGE_PASSWORD` to `.mcp.json`, `environment.d`, or a checked-in file. Do not
reinstall the Bridge or plugin unless the commands above identify an installation failure.

See the [FAQ](faq.md) for why the current terminal may still show an empty variable and how to
collect privacy-safe evidence.

### ChatGPT desktop on Ubuntu cannot find `codex`

The ChatGPT desktop package can use Codex and share MCP configuration without installing a separate
system-wide `codex` command. On the Ubuntu package tested by this project, first verify the bundled
binary:

```bash
test -x /usr/lib/chatgpt/resources/codex
/usr/lib/chatgpt/resources/codex --version
/usr/lib/chatgpt/resources/codex plugin --help
/usr/lib/chatgpt/resources/codex plugin marketplace --help
/usr/lib/chatgpt/resources/codex plugin add --help
```

The `/usr/lib/chatgpt/resources/codex` path is package-specific and may change. Do not install a
same-named third-party package solely because the shell's command-not-found helper suggests it.

### `unexpected argument 'marketplace'` or `unrecognized subcommand 'add'`

A different or older `codex` executable is probably first in `PATH`. Inspect every candidate and
require the plugin help to work:

```bash
type -a codex
codex --version
codex plugin --help
codex plugin marketplace --help
codex plugin add --help
```

If the Ubuntu ChatGPT bundled command passes the check, use its absolute path for installation:

```bash
/usr/lib/chatgpt/resources/codex plugin marketplace add fbossiere/proton-safe-mcp --ref main
/usr/lib/chatgpt/resources/codex plugin add proton-safe@personal
```

### Bash still points to a removed `/snap/bin/codex`

Clear the command cache or start a fresh login shell:

```bash
hash -r
exec bash -l
```

If `codex` is still unavailable, use the verified app-owned absolute path instead of installing an
unrelated package.

### The plugin is installed but ChatGPT cannot see its settings

An app launched from the Ubuntu desktop menu does not inherit variables exported later in an
unrelated terminal. Follow the complete procedure under
[Plugin is installed but `/mcp` shows no Proton tools](#plugin-is-installed-but-mcp-shows-no-proton-tools).

### `PROTON_BRIDGE_USER is required`

Set the address in the environment inherited by the CLI or MCP client:

```bash
export PROTON_BRIDGE_USER="your-address@proton.me"
```

### An integer setting is rejected

All numeric settings must be positive integers within the limits in [Configuration](configuration.md). Remove the override to return to the safe default.

## Bridge connection

### `No Proton Bridge password found`

Ensure `PROTON_BRIDGE_USER` exactly matches the address used during setup, then run:

```bash
proton-safe-mcp setup
```

The credential is keyed by that address in the OS keyring.

### Bridge login or IMAP connection fails

Check that:

1. Proton Mail Bridge is installed, signed in, and running.
2. `PROTON_IMAP_PORT` matches the IMAP port shown by Bridge.
3. The stored password is the Bridge-generated IMAP password, not the Proton account password.
4. No sandbox prevents the local process from connecting to `127.0.0.1`.

If Bridge regenerated its credential, run `setup` again.

## Folders and messages

### A folder cannot be opened

Call `list_folders` and pass the exact returned name. Folder input is validated and the mailbox is opened read-only.

### A message is missing from a short list

Increase `limit` up to 100, use `search_messages`, or select a different folder. Results are newest first.

### A body is truncated

Increase `max_chars` on `read_message`, up to 100000. Large output remains bounded by design.

## Attachments

### Why does received attachment extraction fail?

Call `read_message` first and copy the exact zero-based `attachment_index`. The extraction tool
supports only PDF, TXT, and CSV files. It rejects encrypted or malformed PDFs, unsupported MIME
types, attachments above `PROTON_MCP_MAX_RECEIVED_ATTACHMENT_BYTES`, and indexes that do not exist.

A scanned PDF can succeed with empty text because Proton Safe does not perform OCR or render pages.
Ask the user to provide the file explicitly to a separate visual or OCR workflow when that is
required; do not use shell, browser automation, or filesystem tools to export it from Proton Mail.

See [Common attachment failures](attachments.md#common-failures) for filename, MIME, ordering, size, hash, and expiry errors.

Do not retry one chunk with the same index after the server has accepted it. Resume with the returned `next_chunk`, or discard and restart the upload if client state is uncertain.

## Drafts

### `Explicit user confirmation of the exact draft is required`

`create_confirmed_draft` requires `user_confirmed: true`. Present the exact recipients, subject,
complete body, and attachment list, obtain confirmation in the conversation, then call the tool
again with the unchanged values.

### `Use a bare email address, without display name`

Recipients must be bare addresses such as `person@example.com`. Strip any `Display Name <…>`
wrapper before calling the tool.

### A draft was created but is not in `Drafts`

Check the folder name Bridge exposes with `list_folders`. Some Proton locales expose a translated
Drafts folder.

## Documentation build

Install the documentation extra and build with warnings treated as errors:

```bash
uv sync --extra docs
uv run mkdocs build --strict
```

Preview locally with:

```bash
uv run mkdocs serve
```
