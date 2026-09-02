"""Shared, injection-safe email address validation."""

from __future__ import annotations

import re
from email.utils import parseaddr

from .errors import DraftError, ProtonMCPError


def validate_address(value: str, *, error: type[ProtonMCPError] = DraftError) -> str:
    """Return a bare, header-safe address or raise ``error`` explaining the rejection."""
    if not isinstance(value, str) or not value or "\r" in value or "\n" in value:
        raise error("Invalid email address")
    display, address = parseaddr(value)
    if display or address != value.strip() or len(address) > 254:
        raise error(f"Use a bare email address, without display name: {value!r}")
    if address.count("@") != 1:
        raise error(f"Invalid email address: {value!r}")
    local, domain = address.rsplit("@", 1)
    if not local or not domain or "." not in domain or " " in address:
        raise error(f"Invalid email address: {value!r}")
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+", local):
        raise error(f"Unsupported email address syntax: {value!r}")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", domain) or ".." in domain:
        raise error(f"Invalid email domain: {value!r}")
    return address
