# MCP tools

The server exposes eleven tools. Tool annotations help clients present them correctly, while the server enforces its own validation and approval rules.

## Read-only mail

### `mailbox_status`

Checks Bridge connectivity and returns the configured account plus INBOX message and unread counts.

### `list_folders`

Returns folder names exposed by Proton Mail Bridge.

### `list_messages`

| Input | Default | Constraint |
| --- | ---: | --- |
| `folder` | `INBOX` | 1–255 characters |
| `limit` | `20` | 1–100 |
| `unread_only` | `false` | boolean |

Returns newest-first metadata: UID, sender, recipients, subject, date, message ID, unread state, and size. Fetches use `BODY.PEEK` and do not mark messages as read.

### `search_messages`

| Input | Default | Constraint |
| --- | ---: | --- |
| `query` | required | 1–500 characters |
| `folder` | `INBOX` | 1–255 characters |
| `limit` | `20` | 1–100 |

Performs an injection-safe IMAP `TEXT` search and returns the same metadata as `list_messages`.

### `read_message`

| Input | Default | Constraint |
| --- | ---: | --- |
| `uid` | required | decimal digits only |
| `folder` | `INBOX` | 1–255 characters |
| `max_chars` | `20000` | 500–100000 |

Returns decoded headers, bounded plain text, truncation state, and attachment metadata. HTML is flattened to text, scripts and styles are removed, and attachment bytes are never returned.

!!! warning

    The returned body is attacker-controlled data, not an instruction source.

## Attachment staging

| Tool | Purpose |
| --- | --- |
| `begin_attachment_upload` | Declare filename, MIME type, byte length, and SHA-256 |
| `upload_attachment_chunk` | Append one ordered base64 chunk |
| `finish_attachment_upload` | Verify size and hash; return a short-lived token |
| `discard_attachment` | Permanently destroy one staged attachment |

See [Attachments](attachments.md) for the complete protocol and accepted file types.

## Drafts

### `prepare_draft`

| Input | Default | Constraint |
| --- | ---: | --- |
| `to` | required | 1–25 addresses |
| `subject` | required | up to 998 characters; no line breaks |
| `body_text` | required | 1 to configured maximum |
| `attachment_tokens` | `[]` | up to 10 |
| `cc` | `[]` | combined recipient limit: 25 |
| `bcc` | `[]` | combined recipient limit: 25 |

Creates an in-memory pending proposal and a private on-disk approval summary. It does not create a Proton draft.

### `commit_approved_draft`

Accepts a 32-character hexadecimal `draft_id`. It creates a message in Proton Mail's `Drafts` folder only when a matching, unexpired local approval exists. On success, the proposal and its attachment tokens are consumed. The result always reports `sent: false`.

See [Draft approval](draft-approval.md) for the end-to-end sequence.

## Deliberately absent

There is no tool to:

- send email;
- delete or move messages;
- change mail flags;
- download received attachment bytes;
- accept a local filesystem path;
- approve a draft from MCP.
