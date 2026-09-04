# Security model

Proton Safe MCP reduces the blast radius of prompt injection by restricting capabilities in code. It does not classify email as safe.

## Threats considered

- Adversarial instructions embedded in email bodies or headers.
- A model selecting recipients, a sending identity, or outgoing attachments from untrusted mail or extracted attachment content.
- Malformed, oversized, encrypted, active, or prompt-injected received attachments.
- Header, folder, or IMAP search injection, including through a Message-ID read out of a
  received message and written into a reply's `In-Reply-To` or `References`.
- A reply threaded onto a different message than the one the user confirmed against.
- Client attempts to make the server read arbitrary local paths.
- Oversized, reordered, truncated, substituted, or expired attachment uploads.
- Draft changes after conversational confirmation.
- Accidental exposure of the Proton account password.
- Leakage of the Bridge credential, tunnel runtime API key, or account-specific ChatGPT app ID.
- A remote client attempting to turn the tunnel into general access to the Bridge host.

## Enforced controls

| Boundary | Control |
| --- | --- |
| Email actions | No SMTP, send, delete, move, or raw received-attachment download implementation |
| Transport | STDIO only; no listening network socket |
| Bridge target | Host fixed to `127.0.0.1` |
| Reads | `BODY.PEEK`, bounded plain text, no received attachment bytes or persisted files |
| Received attachments | Explicit index selection; PDF/TXT/CSV allowlist; byte, page, and character limits; SHA-256 result; no OCR or active content |
| Outgoing attachments | No paths; type, size, order, lifetime, and SHA-256 validation |
| Drafts | Exact conversational confirmation assertion; validated recipients, headers, sizes, and attachment tokens |
| Draft bodies | Plain text plus a server-generated HTML alternative; client markup is escaped, never rendered; nothing appended server-side |
| Reply threading | Threading headers only; validated bracketed message-ids; bounded reference chain; parent Message-ID reverified at the IMAP write |
| Sender identity | From header restricted to the startup allowlist, re-checked at the IMAP write |
| Credentials | Bridge-generated IMAP password in the OS keyring |
| State | `0700` directories, `0600` files, defensive no-follow behavior |
| Inputs | Length, format, recipient, header, folder, and search validation |

## Plugin and tunnel boundary

The Proton Safe plugin adds workflow instructions and install metadata. It does not add authority.
The code-enforced MCP tool surface remains the capability boundary, and the plugin cannot send a
draft.

For the primary local deployment, ChatGPT desktop or Codex launches the MCP server directly over
STDIO on the Bridge machine. The plugin skills are defense-in-depth guidance, not authorization
controls. A direct MCP registration has the same code-enforced capability boundary without those
packaged workflows.

For ChatGPT web or a Bridge on another machine, OpenAI Secure MCP Tunnel is an optional outbound
transport from the Bridge machine. The supported remote layout keeps `tunnel-client`,
`proton-safe-mcp`, and Proton Mail Bridge in the same host trust boundary:

```text
ChatGPT ── OpenAI tunnel endpoint ── tunnel-client ── STDIO MCP ── Bridge on 127.0.0.1
```

The tunnel does not justify a configurable Bridge host. Direct remote IMAP is prohibited because
Bridge's self-signed TLS certificate is accepted only under the enforced loopback assumption.

The plugin does not contain a Bridge password, tunnel API key, or ChatGPT connection ID. The
Bridge-generated password remains in the host keyring. The runtime API key remains in the
`tunnel-client` host's secret environment, and the account-specific app mapping is generated only
in the user's private plugin copy.

## Non-goals and limitations

- The server is not an antivirus, phishing detector, spam filter, or sender-authentication product.
- PDF parsing and bounded text extraction do not make a document safe or trustworthy. Encrypted,
  scanned, malformed, and unsupported documents fail closed rather than invoking external tools.
- Byte, page, and character limits reduce but do not eliminate CPU, memory, or parser-vulnerability
  risk from adversarial PDFs.
- A model sees the content of mail it reads and attachments it uploads.
- `get_reply_context` reports candidate recipients drawn from untrusted headers. Labelling them is
  a review aid, not a control: what keeps a wrong address out of a draft is that recipients remain
  explicit, confirmed inputs.
- Reverifying the parent Message-ID binds a reply to the message the user confirmed against. It
  does not authenticate that message, whose headers the sender chose.
- A tunnel keeps the MCP server private but does not keep returned mail content from the OpenAI
  product that requested it. Proton end-to-end encryption no longer applies after Bridge decrypts
  the message locally.
- Attachment bytes are temporarily readable by the local Unix account; use full-disk encryption.
- The server cannot verify surrounding conversation history. The draft tool's required
  `user_confirmed: true` value is a client assertion, not a separate authorization channel.
- A draft the server creates is inert — it cannot leave the account without a manual send in Proton
  Mail — but it can still be crafted to look like the user's own message. Reviewing recipients in
  Proton Mail before sending is the human control this design relies on.
- Tool annotations are client hints, not authorization controls.
- Bridge uses a self-signed TLS certificate. Verification is disabled only because the target is fixed to loopback.
- Unrelated write-capable tools in the same autonomous workflow can defeat the project's intended blast-radius reduction.
- Local availability depends on the client host, Proton Mail Bridge, and the keyring session.
  Remote availability additionally depends on `tunnel-client` and outbound HTTPS.

## Credential boundary

Use only the password generated by Proton Mail Bridge. The server must never receive a Proton account password, recovery phrase, 2FA secret, or hardware-key material.

If local compromise is suspected:

1. Stop Proton Safe MCP and Proton Mail Bridge.
2. Rotate the Bridge-generated client credential in the Bridge UI.
3. Preserve logs and the exact deployed commit for investigation.

## Report a vulnerability

Do not open a public issue. Use [GitHub private vulnerability reporting](https://github.com/fbossiere/proton-safe-mcp/security/advisories/new) and include the affected version or commit, reproduction steps, and impact assessment.

The canonical support policy is maintained in [`SECURITY.md`](https://github.com/fbossiere/proton-safe-mcp/blob/main/SECURITY.md).
