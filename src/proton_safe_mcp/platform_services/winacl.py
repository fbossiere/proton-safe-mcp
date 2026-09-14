"""Windows access control, expressed in SDDL so it can be read and tested.

A Unix mode has no Windows equivalent, so "private to this account" is stated as an
explicit, protected DACL: full access for the owning user and for the accounts Windows
itself needs, inheritance from the parent switched off, and no entry for any other
ordinary account.

The parsing below is deliberately pure Python. It is the part that decides whether a
file is safe to read, so it runs — and is tested — on every platform, not only on the
machine where the answer would be hard to reproduce.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

#: SDDL ACE types that grant access. Deny and audit entries never widen access.
_ALLOW_TYPES: Final = frozenset({"A", "OA", "XA", "ZA"})

#: Two-letter SDDL rights and the access mask each one stands for.
_RIGHTS: Final[dict[str, int]] = {
    "GA": 0x10000000,  # GENERIC_ALL
    "GR": 0x80000000,  # GENERIC_READ
    "GW": 0x40000000,  # GENERIC_WRITE
    "GX": 0x20000000,  # GENERIC_EXECUTE
    "RC": 0x00020000,  # READ_CONTROL
    "SD": 0x00010000,  # DELETE
    "WD": 0x00040000,  # WRITE_DAC
    "WO": 0x00080000,  # WRITE_OWNER
    "FA": 0x001F01FF,  # FILE_ALL_ACCESS
    "FR": 0x00120089,  # FILE_GENERIC_READ
    "FW": 0x00120116,  # FILE_GENERIC_WRITE
    "FX": 0x001200A0,  # FILE_GENERIC_EXECUTE
    "KA": 0x000F003F,
    "KR": 0x00020019,
    "KW": 0x00020006,
    "KX": 0x00020019,
    "CC": 0x00000001,  # FILE_READ_DATA / list directory
    "DC": 0x00000002,  # FILE_WRITE_DATA
    "LC": 0x00000004,  # FILE_APPEND_DATA
    "SW": 0x00000008,  # FILE_READ_EA
    "RP": 0x00000010,  # FILE_WRITE_EA
    "WP": 0x00000020,  # FILE_EXECUTE
    "DT": 0x00000040,  # FILE_DELETE_CHILD
    "LO": 0x00000080,  # FILE_READ_ATTRIBUTES
    "CR": 0x00000100,  # FILE_WRITE_ATTRIBUTES
}

#: Rights that reveal nothing about a file's contents and cannot change it. An entry
#: limited to these is left alone rather than reported, so a normal Windows profile
#: does not look broken.
HARMLESS_MASK: Final = (
    0x00000080  # FILE_READ_ATTRIBUTES
    | 0x00020000  # READ_CONTROL
    | 0x00100000  # SYNCHRONIZE
)

#: SDDL aliases for the accounts a private path may legitimately grant.
SYSTEM_SID: Final = "S-1-5-18"
ADMINISTRATORS_SID: Final = "S-1-5-32-544"
CREATOR_OWNER_SID: Final = "S-1-3-0"
OWNER_RIGHTS_SID: Final = "S-1-3-4"

#: Two-letter aliases Windows may emit instead of a SID string.
_SID_ALIASES: Final[dict[str, str]] = {
    "SY": SYSTEM_SID,
    "BA": ADMINISTRATORS_SID,
    "LA": "S-1-5-21-0-0-0-500",
    "CO": CREATOR_OWNER_SID,
    "OW": OWNER_RIGHTS_SID,
    "WD": "S-1-1-0",  # Everyone
    "BU": "S-1-5-32-545",  # Users
    "AU": "S-1-5-11",  # Authenticated Users
    "IU": "S-1-5-4",  # Interactive
    "NU": "S-1-5-2",  # Network
    "AN": "S-1-5-7",  # Anonymous
    "BG": "S-1-5-32-546",  # Guests
    "PU": "S-1-5-32-547",  # Power Users
}

_ACE_RE: Final = re.compile(r"\(([^()]*)\)")
_HEX_RE: Final = re.compile(r"^0x[0-9a-fA-F]+$")


@dataclass(frozen=True, slots=True)
class Ace:
    """One access control entry, reduced to what a privacy decision needs."""

    kind: str
    flags: str
    mask: int
    sid: str

    @property
    def allows(self) -> bool:
        return self.kind in _ALLOW_TYPES


def normalise_sid(value: str) -> str:
    """Turn an SDDL account string into a SID, expanding a two-letter alias."""
    token = value.strip().upper()
    return _SID_ALIASES.get(token, token)


def parse_rights(value: str) -> int:
    """Turn an SDDL rights field into an access mask.

    Both spellings occur in practice: a hexadecimal literal, or a run of two-letter
    mnemonics. An unrecognised mnemonic is treated as granting everything, because
    guessing low would silently approve an entry this code does not understand.
    """
    token = value.strip()
    if not token:
        return 0
    if _HEX_RE.match(token):
        return int(token, 16)
    upper = token.upper()
    if len(upper) % 2:
        return 0xFFFFFFFF
    mask = 0
    for index in range(0, len(upper), 2):
        pair = upper[index : index + 2]
        if pair not in _RIGHTS:
            return 0xFFFFFFFF
        mask |= _RIGHTS[pair]
    return mask


def split_sections(sddl: str) -> dict[str, str]:
    """Split a security descriptor into its O:, G:, D: and S: sections.

    A section starts at a letter immediately followed by a colon, outside any ACE.
    Scanning rather than matching a pattern is what keeps an account SID — which also
    starts with ``S`` — from being mistaken for the start of the audit section.
    """
    sections: dict[str, str] = {}
    depth = 0
    current = ""
    start = 0
    for index, character in enumerate(sddl):
        if character == "(":
            depth += 1
            continue
        if character == ")":
            depth = max(depth - 1, 0)
            continue
        if depth or character not in "OGDS":
            continue
        if index + 1 >= len(sddl) or sddl[index + 1] != ":":
            continue
        if current:
            sections[current] = sddl[start:index]
        current = character
        start = index + 2
    if current:
        sections[current] = sddl[start:]
    return sections


def parse_security_descriptor(sddl: str) -> tuple[str, list[Ace], bool]:
    """Return the owner SID, the DACL entries and whether inheritance is blocked.

    A descriptor with no DACL section is reported as inheriting with no entries, which
    every caller treats as "not established" rather than as "safe".
    """
    sections = split_sections(sddl)
    owner = normalise_sid(sections["O"]) if sections.get("O") else ""
    body = sections.get("D")
    if body is None:
        return owner, [], False
    flags = body.split("(", 1)[0]
    protected = "P" in flags.upper()
    aces: list[Ace] = []
    for raw in _ACE_RE.findall(body):
        fields = raw.split(";")
        if len(fields) < 6:
            continue
        aces.append(
            Ace(
                kind=fields[0].strip().upper(),
                flags=fields[1].strip().upper(),
                mask=parse_rights(fields[2]),
                sid=normalise_sid(fields[5]),
            )
        )
    return owner, aces, protected


def foreign_grants(sddl: str, *, allowed_sids: frozenset[str]) -> list[str]:
    """List the SIDs that are granted meaningful access and should not be.

    ``allowed_sids`` is this account plus the system accounts Windows needs. Everything
    else — Everyone, Users, Authenticated Users, another person's account — is reported.
    """
    _, aces, _ = parse_security_descriptor(sddl)
    offenders: list[str] = []
    for ace in aces:
        if not ace.allows or ace.sid in allowed_sids:
            continue
        if ace.mask & ~HARMLESS_MASK == 0:
            continue
        if ace.sid not in offenders:
            offenders.append(ace.sid)
    return offenders


def inherits_from_parent(sddl: str) -> bool:
    """Whether the DACL is still open to whatever the parent directory grants."""
    _, _, protected = parse_security_descriptor(sddl)
    return not protected


def private_sddl(user_sid: str, *, directory: bool) -> str:
    """Build the protected DACL a private path carries.

    ``P`` blocks inherited entries, so a permissive parent — a shared drive, a profile
    someone widened — cannot grant access to this product's files. Directories carry
    ``OICI`` so files created inside them start out private too.
    """
    if not user_sid.startswith("S-1-"):
        raise ValueError("a private DACL needs the account's own SID")
    flags = "OICI" if directory else ""
    entries = "".join(
        f"(A;{flags};FA;;;{sid})" for sid in (user_sid, SYSTEM_SID, ADMINISTRATORS_SID)
    )
    return f"D:P{entries}"


def allowed_sids_for(user_sid: str) -> frozenset[str]:
    """The accounts a path private to ``user_sid`` may grant access to."""
    return frozenset(
        {user_sid, SYSTEM_SID, ADMINISTRATORS_SID, CREATOR_OWNER_SID, OWNER_RIGHTS_SID}
    )


def private_descriptor(sddl: str, user_sid: str, *, directory: bool = False) -> bool:
    """Accept only a complete, protected DACL owned by this account.

    Unknown/conditional ACE syntax fails closed. A null DACL grants everyone full
    access; it is never equivalent to an empty DACL or evidence of privacy.
    """
    owner, aces, protected = parse_security_descriptor(sddl)
    body = split_sections(sddl).get("D", "")
    if owner != user_sid or not protected or not aces:
        return False
    flags = body.split("(", 1)[0]
    if not re.fullmatch(r"(?:P|AI|AR)*", flags):
        return False
    raw_entries = _ACE_RE.findall(body)
    if body != flags + "".join(f"({raw})" for raw in raw_entries):
        return False
    if any(len(raw.split(";")) != 6 for raw in raw_entries):
        return False
    if any(ace.kind not in {"A", "D"} for ace in aces):
        return False
    if foreign_grants(sddl, allowed_sids=allowed_sids_for(user_sid)):
        return False
    return any(
        ace.kind == "A"
        and ace.sid == user_sid
        and "IO" not in ace.flags
        and (not directory or ("OI" in ace.flags and "CI" in ace.flags))
        and ace.mask & 0x001F01FF == 0x001F01FF
        for ace in aces
    )
