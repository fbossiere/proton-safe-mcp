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
from typing import Final, Literal

#: SDDL ACE types that grant access. Deny and audit entries never widen access.
_ALLOW_TYPES: Final = frozenset({"A", "OA", "XA", "ZA"})

#: What the ``D:`` section of a descriptor turned out to be. The five cases are kept
#: apart because Windows treats two of them as opposites that look alike: an object
#: with *no* DACL grants every account full access, while an object with an *empty*
#: DACL grants none. Collapsing them would report a wide-open path as private.
#: https://learn.microsoft.com/en-us/windows/win32/secauthz/null-dacls-and-empty-dacls
DaclState = Literal["invalid", "absent", "null", "empty", "present"]

#: How SDDL spells a NULL DACL — an object with no access control at all.
NULL_DACL_KEYWORD: Final = "NO_ACCESS_CONTROL"

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
EVERYONE_SID: Final = "S-1-1-0"
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
    "WD": EVERYONE_SID,
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


@dataclass(frozen=True, slots=True)
class Descriptor:
    """A security descriptor reduced to what a privacy decision needs."""

    owner: str
    dacl: DaclState
    aces: tuple[Ace, ...] = ()
    protected: bool = False


def parse_security_descriptor(sddl: str) -> Descriptor:
    """Return the owner, the state of the DACL and its entries.

    The DACL state is never guessed. ``absent`` means the descriptor carried no ``D:``
    section, ``null`` means it carried one saying there is no access control at all, and
    ``empty`` means it listed no entries. Only the last of those three denies access.
    """
    if not sddl.strip():
        return Descriptor("", "invalid")
    sections = split_sections(sddl)
    owner = normalise_sid(sections["O"]) if sections.get("O") else ""
    body = sections.get("D")
    if body is None:
        return Descriptor(owner, "absent")
    flags = body.split("(", 1)[0].strip().upper()
    if NULL_DACL_KEYWORD in flags:
        # Not an empty DACL: an object with no DACL is open to every account.
        return Descriptor(owner, "null")
    if not re.fullmatch(r"(?:P|AI|AR)*", flags):
        return Descriptor(owner, "invalid")
    raw_entries = _ACE_RE.findall(body)
    if body != flags + "".join(f"({raw})" for raw in raw_entries):
        return Descriptor(owner, "invalid")
    protected = "P" in flags
    aces: list[Ace] = []
    for raw in _ACE_RE.findall(body):
        fields = raw.split(";")
        if len(fields) != 6 or fields[0] not in {"A", "D"}:
            # An entry this code cannot read is not an entry it may ignore: the whole
            # descriptor is reported as unreadable rather than parsed around.
            return Descriptor(owner, "invalid")
        aces.append(
            Ace(
                kind=fields[0].strip().upper(),
                flags=fields[1].strip().upper(),
                mask=parse_rights(fields[2]),
                sid=normalise_sid(fields[5]),
            )
        )
    if not aces:
        return Descriptor(owner, "empty", (), protected)
    return Descriptor(owner, "present", tuple(aces), protected)


def granted_to_others(descriptor: Descriptor, *, allowed_sids: frozenset[str]) -> list[str]:
    """The SIDs the listed entries grant meaningful access to and should not.

    This reads entries only. It says nothing about a descriptor whose DACL is absent or
    null, which is why every privacy decision goes through ``assess_privacy`` instead.
    """
    offenders: list[str] = []
    for ace in descriptor.aces:
        if not ace.allows or ace.sid in allowed_sids:
            continue
        if ace.mask & ~HARMLESS_MASK == 0:
            continue
        if ace.sid not in offenders:
            offenders.append(ace.sid)
    return offenders


@dataclass(frozen=True, slots=True)
class PrivacyReport:
    """Whether a path is private to one account, and what is wrong when it is not."""

    private: bool
    #: The DACL still takes entries from the parent, so a widened profile reaches it.
    inherits: bool
    #: The owner is this account or a system account. An owner can always rewrite the
    #: DACL, so a foreign owner is never corrected in place — it is refused.
    owner_ok: bool
    #: Empty when private; otherwise one clause naming what is wrong.
    reason: str = ""
    offenders: tuple[str, ...] = ()


def assess_privacy(sddl: str, *, user_sid: str) -> PrivacyReport:
    """Decide whether a path is private to ``user_sid``, and say why when it is not.

    This is the single decision point. Callers must not reason about entries on their
    own: the cases that matter here are the ones an entry list cannot express — a
    descriptor that could not be read, one with no DACL of its own, and one explicitly
    saying there is no access control at all.
    """
    descriptor = parse_security_descriptor(sddl)
    allowed = allowed_sids_for(user_sid)
    if descriptor.dacl == "invalid":
        return PrivacyReport(False, True, False, "its permissions could not be read")
    if not descriptor.owner:
        return PrivacyReport(False, True, False, "its owner could not be established")
    owner_ok = descriptor.owner in allowed
    if not owner_ok:
        return PrivacyReport(
            False, True, False, "it belongs to another account", (descriptor.owner,)
        )
    if descriptor.dacl == "absent":
        return PrivacyReport(False, True, True, "it carries no permissions of its own")
    if descriptor.dacl == "null":
        return PrivacyReport(
            False, True, True, "every account on this computer can open it", (EVERYONE_SID,)
        )
    inherits = not descriptor.protected
    offenders = granted_to_others(descriptor, allowed_sids=allowed)
    if offenders:
        return PrivacyReport(
            False, inherits, True, "other accounts on this computer can open it", tuple(offenders)
        )
    return PrivacyReport(True, inherits, True)


def inherits_from_parent(sddl: str) -> bool:
    """Whether the DACL is still open to whatever the parent directory grants.

    A descriptor with no usable DACL of its own counts as inheriting: there is nothing
    protecting it, whatever the reason.
    """
    descriptor = parse_security_descriptor(sddl)
    return not descriptor.protected


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
    """Require a protected DACL with usable, inheritable access for this account."""
    descriptor = parse_security_descriptor(sddl)
    report = assess_privacy(sddl, user_sid=user_sid)
    return (
        report.private
        and descriptor.protected
        and any(
            ace.kind == "A"
            and ace.sid == user_sid
            and "IO" not in ace.flags
            and (not directory or ("OI" in ace.flags and "CI" in ace.flags))
            and ace.mask & 0x001F01FF == 0x001F01FF
            for ace in descriptor.aces
        )
    )
