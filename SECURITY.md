# Security policy

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report vulnerabilities privately through [GitHub private vulnerability reporting](https://github.com/fbossiere/proton-safe-mcp/security/advisories/new). Include the deployed commit or version, reproduction steps, and impact assessment. You should receive an acknowledgement within 7 days.

## Supported versions

| Version | Supported |
| ------- | --------- |
| 1.1.x   | ✅        |
| 1.0.x   | ✅        |
| < 1.0   | ❌        |

Pin deployments to a reviewed release tag and update dependencies deliberately.

## Scope and non-goals

This server is not an antivirus, phishing detector, spam filter, or sender-authentication product. Email contents remain attacker-controlled input, and this project makes no claim to neutralize prompt injection — it only limits what an injected instruction can accomplish (no send, no delete, no path access, human approval before draft creation).

Reports about the *documented* threat-model limitations in the README (for example, "an MCP client with unrestricted shell access as the same Unix user can defeat the approval marker") are appreciated as discussions but are not vulnerabilities: they are explicitly out of scope by design.

## Credential boundary

The server accepts only the Bridge-generated IMAP credential. It must never receive the Proton account password, recovery phrase, 2FA secret, or hardware-key material. A report demonstrating any code path that requests or transmits those is a critical vulnerability.

## If you suspect local compromise

1. Stop the MCP server and Proton Mail Bridge.
2. Rotate the Bridge-generated client credential from the Bridge UI.
3. Preserve logs and the exact deployed commit for investigation.
