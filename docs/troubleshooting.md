# Troubleshooting

Start with the privacy-safe diagnostic:

```bash
proton-safe-mcp doctor
```

It checks the supported runtime and platform, configuration, state-directory permissions,
credential lookup, and Bridge connectivity without printing email addresses, credentials, mailbox
counts, or message content.

## Startup and configuration

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
unrelated terminal. Follow the `environment.d` procedure in the
[OpenAI plugin guide](openai-plugin.md#3-make-non-secret-settings-available-to-the-desktop-app),
sign out and back in, quit ChatGPT completely, and start a new task. Type `/mcp` to inspect the
connected servers.

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

See [Common attachment failures](attachments.md#common-failures) for filename, MIME, ordering, size, hash, and expiry errors.

Do not retry one chunk with the same index after the server has accepted it. Resume with the returned `next_chunk`, or discard and restart the upload if client state is uncertain.

## Draft approval

### `Unknown draft proposal or server was restarted`

The body is kept only in process memory. Prepare a new proposal after any server restart.

### `Draft proposal expired`

Prepare and approve a new draft within `PROTON_MCP_DRAFT_TTL_SECONDS`.

### `Local approval required`

Run the exact `approval_command` returned by `prepare_draft` in a separate local terminal.

### Approval does not match

The approval marker digest differs from the in-memory proposal. Reject it and prepare a new draft; do not modify approval state manually.

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
