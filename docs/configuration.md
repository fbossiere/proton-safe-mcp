# Configuration

Proton Safe MCP intentionally exposes a small configuration surface. The transport and Bridge host cannot be changed.

## Environment variables

| Variable | Default | Accepted range | Purpose |
| --- | ---: | ---: | --- |
| `PROTON_BRIDGE_USER` | required | non-empty, no line breaks | Proton address configured in Bridge |
| `PROTON_IMAP_PORT` | `1143` | `1`–`65535` | Local Bridge IMAP port |
| `PROTON_MCP_STATE_DIR` | `~/.local/state/proton-safe-mcp` | local directory | Private staging and approval state |
| `PROTON_MCP_MAX_ATTACHMENT_BYTES` | `20971520` | `1`–`26214400` | Maximum for one file and for all files in one draft |
| `PROTON_MCP_MAX_RECEIVED_ATTACHMENT_BYTES` | `10485760` | `1`–`26214400` | Maximum received attachment size accepted for text extraction |
| `PROTON_MCP_MAX_CHUNK_BYTES` | `393216` | `1`–`1048576` | Maximum decoded attachment chunk |
| `PROTON_MCP_UPLOAD_TTL_SECONDS` | `1800` | `1`–`86400` | Attachment staging lifetime |
| `PROTON_MCP_DRAFT_TTL_SECONDS` | `900` | `1`–`3600` | Pending draft lifetime |
| `PROTON_MCP_MAX_BODY_CHARS` | `100000` | `1`–`500000` | Maximum outgoing draft body length |

Every positive integer is validated at startup. Invalid values stop the server with a configuration error.

## Fixed security settings

The following behavior is not configurable:

- Bridge host: `127.0.0.1`.
- MCP transport: STDIO.
- Draft destination: Proton Mail's `Drafts` folder.
- Direct draft confirmation: explicit client assertion of the exact user-confirmed content.
- Enhanced draft approval: local, interactive, and outside the MCP tool surface.

`PROTON_BRIDGE_HOST` is intentionally ignored. TLS certificate verification is disabled only because the connection target is fixed to loopback; making the host configurable would invalidate that safety argument.

## Credential lookup

The preferred flow is:

```bash
export PROTON_BRIDGE_USER="your-address@proton.me"
proton-safe-mcp setup
```

At runtime, the server first checks `PROTON_BRIDGE_PASSWORD`, then the operating-system keyring. The environment fallback exists for isolated containers without Secret Service support.

!!! warning "Environment fallback"

    Environment values may be visible to the client process, diagnostics, or process-inspection tools. Use the keyring for desktop MCP clients.

## State directory

The server creates the state directory and its `uploads` and `approvals` children with mode `0700`. State files use mode `0600` and are opened defensively to avoid following symbolic links.

Uploaded attachment bytes are temporary files. Pending draft bodies remain in process memory; restarting the server invalidates pending proposals even if request summaries remain on disk.
