# Outgoing attachments

Outgoing attachments enter through a bounded, client-neutral byte protocol. The MCP server never receives a local filesystem path. For received PDF, TXT, or CSV inspection, use [Received attachment extraction](received-attachments.md); received bytes are never exported into this upload workflow.

## Accepted types

The filename extension and MIME type must agree.

| Extension | MIME type |
| --- | --- |
| `.pdf` | `application/pdf` |
| `.docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| `.xlsx` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| `.pptx` | `application/vnd.openxmlformats-officedocument.presentationml.presentation` |
| `.txt` | `text/plain` |
| `.csv` | `text/csv` |
| `.png` | `image/png` |
| `.jpg`, `.jpeg` | `image/jpeg` |

`application/octet-stream` is accepted at the start of an upload and normalized from the filename extension.

## Upload protocol

Given the raw file bytes:

1. Calculate the exact byte length and lowercase SHA-256 digest.
2. Call `begin_attachment_upload(filename, content_type, size_bytes, sha256_hex)`.
3. Split the raw bytes into consecutive chunks no larger than the returned `max_chunk_bytes`.
4. Base64-encode each raw chunk independently.
5. Call `upload_attachment_chunk(upload_id, chunk_index, data_base64)` for indexes `0`, `1`, `2`, and so on.
6. Call `finish_attachment_upload(upload_id)`.
7. Retain the returned opaque `attachment_token` and include it in the exact attachment list shown
   to the user before calling `create_confirmed_draft`.

Example calculation:

```python
import base64
import hashlib

payload = open("brief.pdf", "rb").read()
size_bytes = len(payload)
sha256_hex = hashlib.sha256(payload).hexdigest()

chunks = [
    base64.b64encode(payload[offset : offset + 393_216]).decode("ascii")
    for offset in range(0, len(payload), 393_216)
]
```

The example only demonstrates byte preparation. The MCP client is responsible for invoking the tools with the resulting values.

## Integrity and lifecycle

- Chunks must arrive in strict index order.
- The cumulative byte count cannot exceed the declared size.
- `finish_attachment_upload` requires an exact size match and re-computes SHA-256.
- A hash mismatch destroys the upload.
- Ready tokens are random, short-lived, and revalidated before draft creation.
- Tokens are single-use and are destroyed after the draft is created.
- `discard_attachment` destroys a staged attachment before use.

One draft can contain at most ten attachments. The combined attachment size cannot exceed `PROTON_MCP_MAX_ATTACHMENT_BYTES`.

## Common failures

| Error | Likely cause |
| --- | --- |
| Invalid filename | A path, directory separator, control character, or unsupported extension was supplied |
| MIME mismatch | `content_type` does not match the extension |
| Expected chunk index | Chunks arrived out of order or one was retried |
| Declared size exceeded | Chunking used the wrong source bytes or size |
| SHA-256 verification failed | Bytes changed, a chunk was omitted, or the declared digest was wrong |
| Unknown attachment upload | The upload expired, was consumed, discarded, or already failed |
