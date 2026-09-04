"""Shared, injection-safe Message-ID validation and reply reference chains."""

from __future__ import annotations

import re

from .errors import DraftError, ProtonMCPError

MAX_MESSAGE_ID_CHARS = 250
MAX_REFERENCES = 20
MAX_REFERENCES_CHARS = 2_000

# RFC 5322 msg-id narrowed to printable US-ASCII with no whitespace and no nested angle
# bracket: 0x21-0x7E minus "<" (0x3C) and ">" (0x3E). Every Message-ID this server writes
# into an In-Reply-To or References header was read out of a received message, so it is
# attacker-controlled input. Refusing CR, LF, and folding whitespace here is what stops a
# crafted Message-ID from continuing into a header of its own.
_MESSAGE_ID = re.compile(rf"<[!-;=?-~]{{1,{MAX_MESSAGE_ID_CHARS - 2}}}>")


def validate_message_id(value: str, *, error: type[ProtonMCPError] = DraftError) -> str:
    """Return one header-safe bracketed Message-ID or raise ``error`` explaining the rejection."""
    if not isinstance(value, str):
        raise error("Invalid Message-ID")
    candidate = value.strip()
    if not _MESSAGE_ID.fullmatch(candidate):
        raise error(
            "Invalid Message-ID: pass the exact bracketed value reported for the message, "
            f"such as '<id@example.com>', not {value!r}"
        )
    return candidate


def parse_message_ids(header_value: object) -> tuple[str, ...]:
    """Extract every well-formed Message-ID from one received header, in order.

    This reads an attacker-controlled ``References`` or ``In-Reply-To`` header, where any
    byte sequence may appear, so malformed and oversized entries are dropped instead of
    raising. Duplicates are collapsed so a looping chain cannot inflate the reply's header.
    """
    if not header_value:
        return ()
    seen: set[str] = set()
    found: list[str] = []
    for match in _MESSAGE_ID.finditer(str(header_value)):
        value = match.group(0)
        if value not in seen:
            seen.add(value)
            found.append(value)
    return tuple(found)


def build_references(parent_references: tuple[str, ...], parent_message_id: str) -> tuple[str, ...]:
    """Return the References chain for a reply to ``parent_message_id``.

    RFC 5322 section 3.6.4 defines it as the parent's References followed by the parent's
    own Message-ID. Both the entry count and the rendered length are bounded, and trimming
    drops from just after the thread root so that the root and the parent — the two entries
    a mail client actually needs to place the reply — are the last to go. That pair always
    fits, because two Message-IDs cannot exceed ``MAX_REFERENCES_CHARS`` between them.
    """
    chain = [item for item in parent_references if item != parent_message_id]
    chain.append(parent_message_id)
    if len(chain) > MAX_REFERENCES:
        chain = [chain[0], *chain[-(MAX_REFERENCES - 1) :]]
    while len(chain) > 2 and len(" ".join(chain)) > MAX_REFERENCES_CHARS:
        del chain[1]
    return tuple(chain)
