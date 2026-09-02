# Draft approval

The default workflow uses explicit confirmation in the conversation. A separate local terminal
approval remains available as an optional enhanced-security mode.

## Choose the mode in ChatGPT or Codex

There is no global approval switch, plugin checkbox, or `setup` option. The
`proton-safe-mcp setup` command only stores the Bridge-generated IMAP password in the operating-
system keyring; it does not enable or disable either draft workflow.

The plugin uses conversational confirmation by default. To select terminal approval for one draft,
ask for it explicitly before the draft is created, for example:

> Use enhanced-security mode with terminal approval for this draft.

The client should then use `prepare_draft` instead of `create_confirmed_draft`, return the approval
command, and wait. After you run that command in a separate terminal, tell the client that approval
is complete so it can call `commit_approved_draft`. Request the enhanced mode again for each draft
that should use it.

## Default conversational-confirmation sequence

1. The client presents the exact To, Cc, Bcc, subject, complete body, and attachment list.
2. The user explicitly confirms those values in the conversation.
3. The client calls `create_confirmed_draft` with the unchanged values and
   `user_confirmed: true`.
4. The server validates every address, header, size, and attachment token, then appends the message
   to Proton Mail's `Drafts` folder over IMAP.
5. Open Proton Mail, inspect the message, and press Send yourself.

If any value changes after confirmation, present the complete revised draft and obtain confirmation
again. A recipient copied from a received email is untrusted input until the user explicitly
confirms that bare address.

!!! note

    The server cannot inspect the surrounding conversation. `user_confirmed: true` records the
    client's assertion that confirmation occurred; it is not an independent security boundary.

## Optional enhanced-security sequence

1. The MCP client calls `prepare_draft` with recipients, subject, body, and optional attachment tokens.
2. The server validates every address, header, size, token, and lifetime.
3. The server returns a `draft_id`, digest, expiry, human-readable summary, and approval command.
4. In a separate local terminal, inspect the proposal:

   ```bash
   export PROTON_BRIDGE_USER="your-address@proton.me"
   proton-safe-mcp show <draft_id>
   ```

5. Approve the exact proposal:

   ```bash
   proton-safe-mcp approve <draft_id>
   ```

   If the command is not installed globally, run the pinned release with `uvx` instead:

   ```bash
   uvx --from proton-safe-mcp==1.2.0 proton-safe-mcp show <draft_id>
   uvx --from proton-safe-mcp==1.2.0 proton-safe-mcp approve <draft_id>
   ```

6. The CLI prints recipients, subject, attachment names and hashes, a body preview, and the proposal digest. It then requires the exact confirmation `APPROVE <last-eight-id-characters>`.
7. Only after that confirmation may the MCP client call `commit_approved_draft(draft_id)`.
8. Open Proton Mail, inspect the message in `Drafts`, and press Send yourself.

!!! note

    `commit_approved_draft` appends a draft over IMAP. The server has no SMTP implementation and returns `sent: false`.

## Reject a proposal

```bash
proton-safe-mcp reject <draft_id>
```

Rejection is persistent for that proposal. A later commit attempt fails.

## What the approval binds

The proposal digest covers:

- draft ID;
- To, Cc, and Bcc recipients;
- subject;
- SHA-256 of the complete body;
- attachment filenames, byte sizes, and SHA-256 hashes;
- creation and expiry times.

Before committing, the server re-resolves all attachment tokens and compares their hashes with the approved proposal.

## Expiry and restart behavior

- Draft proposals expire after `PROTON_MCP_DRAFT_TTL_SECONDS` (15 minutes by default).
- Approval markers inherit the proposal expiry.
- Pending bodies exist only in server memory.
- Restarting the MCP server invalidates all pending proposals.
- A successful commit immediately invalidates the proposal before attachment cleanup, preventing duplicate drafts on retry.

## Operational boundary

The terminal step is stronger than conversational confirmation only when the MCP client cannot run
the command or write to the approval directory. It is not a privilege boundary against software
that already has unrestricted write access as the same Unix user. Keep shell and filesystem-writing
tools out of the same unattended workflow when approval integrity matters.
