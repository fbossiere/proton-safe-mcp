# External testing

Proton Safe MCP needs feedback from Linux users running the official Proton Mail Bridge. This
test checks the complete first-use path without granting send, delete, or move capabilities to an
MCP client.

Allow about **10 minutes** for the core test. Use only benign test content and stop if any step
would require sharing a credential, private message, or confidential attachment.

## Before you start

You need:

- Linux with Proton Mail Bridge installed, signed in, and running;
- a Proton plan that supports Bridge;
- Python 3.11 or newer and [`uv`](https://docs.astral.sh/uv/);
- Claude Code, Cursor, or VS Code;
- one harmless unread message that you sent to yourself for this test.

Record your Linux distribution, Python version, Bridge version, MCP client, and the time when you
start. Never include your Proton password, Bridge-generated password, recovery phrase, 2FA data,
email address, message content, or hardware-key material in public feedback.

## Core 10-minute test

### 1. Install and configure

Install the reviewed release:

```bash
uv tool install proton-safe-mcp==1.2.0
```

Follow [Getting started](getting-started.md) to set `PROTON_BRIDGE_USER` and
`PROTON_IMAP_PORT`, then store the **Bridge-generated IMAP password** in the operating-system
keyring:

```bash
proton-safe-mcp setup
```

Register the server using the instructions for [Claude Code, Cursor, or VS Code](clients.md).

### 2. Reach the first connected result

Ask the client to call `mailbox_status`. Stop the timer when the response reports
`connected: true` and record the elapsed time.

Then ask it to call `list_folders` and `list_messages` for the inbox. Do not paste tool output into
a public issue: it can contain private folder names, senders, and subjects.

### 3. Confirm that reading is non-destructive

Ask the client to call `read_message` for the harmless unread message you prepared. Open Proton
Mail separately and confirm that the message is still unread. The server uses `BODY.PEEK` and
should not change read state.

### 4. Exercise conversational confirmation

Ask the client to propose a plain-text draft addressed to your own Proton address. Use a neutral
subject such as `Proton Safe MCP external test` and do not add an attachment yet. Confirm the exact
recipient, subject, complete body, and empty attachment list in the conversation.

The client should call `create_confirmed_draft` with `user_confirmed: true`. Confirm that:

- the draft appears in Proton Mail;
- the recipient, subject, and body match what you confirmed;
- the result reports `sent: false`;
- the client exposes no send, delete, or move tool.

Review the draft manually and delete it in Proton Mail if you do not want to keep it. Do not send
it merely for this test.

### 5. Optionally exercise enhanced approval

Ask the client to create a second harmless proposal using `prepare_draft`. Before approving, ask it
to call `commit_approved_draft` with the returned `draft_id`. The call must fail with a
local-approval-required result.

In a separate terminal, inspect the exact proposal:

```bash
proton-safe-mcp show <draft_id>
proton-safe-mcp approve <draft_id>
```

After interactive approval, ask the client to call `commit_approved_draft` again and confirm that
the second draft matches the locally approved proposal and still reports `sent: false`.

## Optional attachment check

If the core test succeeds, repeat the default draft flow with a newly created, non-confidential TXT or PDF
file. Follow the [attachment workflow](attachments.md) and confirm that the file name, type, size,
and SHA-256 digest are checked before the draft is created.

Never use a personal document for this test. Attachment handling depends on the MCP client's
ability to obtain bytes and call the chunked upload tools, so record any client-specific friction.

## What success looks like

The core path is successful when:

1. `mailbox_status` reports `connected: true` in ten minutes or less;
2. reading the prepared message does not mark it as read;
3. direct draft creation occurs only after exact conversational confirmation;
4. the confirmed draft appears in Proton Mail and is never sent;
5. bounded PDF/TXT/CSV text extraction returns no raw bytes or filesystem path;
6. no send, delete, move, raw received-attachment-download, or MCP approval tool is exposed.

Partial and failed tests are equally useful. Report the first point of friction rather than
working around it silently.

## Send installation feedback

Open the [installation feedback form](https://github.com/fbossiere/proton-safe-mcp/issues/new?template=installation-feedback.yml)
and report the outcome. Redact all identifiers and message content. For a suspected security
vulnerability, do **not** open a public issue; use
[private vulnerability reporting](https://github.com/fbossiere/proton-safe-mcp/security/advisories/new).
