# Draft approval

Draft approval is deliberately split across the MCP client and a local terminal. No MCP tool can approve its own proposal.

## End-to-end sequence

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

The approval step protects against an MCP client approving its own draft. It is not a privilege boundary against software that already has unrestricted write access as the same Unix user. Keep shell and filesystem-writing tools out of the same unattended workflow when approval integrity matters.
