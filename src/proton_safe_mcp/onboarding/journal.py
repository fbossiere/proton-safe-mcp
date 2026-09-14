"""A private record of what the assistant created, for resume and removal.

It holds no credential and no mailbox data. Its purpose is to know which resources belong
to Proton Safe so a repair or a disconnect touches only those, and so an interrupted run
can be recognised at the next start. It is never evidence that anything works today.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final

from ..platform_services import PrivacyError, services
from .models import InstallState

JOURNAL_SCHEMA_VERSION: Final = 1
_JOURNAL_NAME: Final = "install.json"

#: Fields that must never appear, checked before every write.
_FORBIDDEN_KEYS: Final = frozenset({"password", "secret", "token", "credential", "api_key"})


def default_journal_path() -> Path:
    """This account's journal location, alongside the rest of its private state."""
    return services().state_dir() / "assistant" / _JOURNAL_NAME


@dataclass(slots=True)
class ManagedResource:
    """One thing the assistant created and may therefore remove."""

    kind: str
    name: str
    #: Adapter that owns it, so another client's resources are never touched.
    adapter: str = ""


@dataclass(slots=True)
class Journal:
    """What this account's managed installation recorded, as facts, not as a verdict."""

    state: str = InstallState.NEW
    schema_version: int = JOURNAL_SCHEMA_VERSION
    engine_version: str = ""
    plugin_version: str = ""
    resource_digest: str = ""
    config_path: str = ""
    plugin_dir: str = ""
    client_id: str = ""
    client_adapter: str = ""
    #: The absolute path of the executable that was registered. A discovery identifier
    #: describes where a client was found, not which one it is: an installation the user
    #: pointed at is never rediscovered, and a probed one can change position when
    #: another candidate appears. The path is what a later repair or disconnect looks
    #: the installation up by, after revalidating it like any other.
    client_executable: str = ""
    #: The client profile directory that was written to, so a disconnect removes entries
    #: from the same profile they were added to.
    client_profile: str = ""
    runtime_command: list[str] = field(default_factory=list)
    resources: list[ManagedResource] = field(default_factory=list)
    #: Set only by an explicit "I checked in my assistant" action, never by a probe.
    client_confirmed_manually: bool = False
    #: When the last verification ran, in UTC, and what each level reported. These are
    #: recorded facts about a past run, never evidence that the connection works now.
    last_verified_at: str = ""
    last_checks: dict[str, str] = field(default_factory=dict)
    #: A step began but its completion was not recorded: the next start must repair.
    pending_step: str = ""
    #: Earlier Proton Safe entries this installation took over, so a resumed run does not
    #: try to remove them again.
    migrated_from: list[str] = field(default_factory=list)
    #: The user asked to erase the local configuration and credential, but client entries
    #: were still registered. The erase happens once they are actually gone.
    erase_local_requested: bool = False
    #: The user asked to disconnect and some client entries could not be removed. The next
    #: start must surface that rather than presenting a normal, healthy installation.
    disconnect_pending: bool = False

    def record(self, resource: ManagedResource) -> None:
        if not any(
            existing.kind == resource.kind and existing.name == resource.name
            for existing in self.resources
        ):
            self.resources.append(resource)

    def forget(self, kind: str, name: str) -> None:
        self.resources = [
            item for item in self.resources if not (item.kind == kind and item.name == name)
        ]

    def owned(self, kind: str) -> list[ManagedResource]:
        return [item for item in self.resources if item.kind == kind]


def _reject_secrets(payload: dict[str, Any]) -> None:
    """Refuse to persist anything that looks like a credential, whatever put it there."""
    stack: list[Any] = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                if any(marker in str(key).lower() for marker in _FORBIDDEN_KEYS):
                    raise ValueError("the assistant journal must never hold a credential")
                stack.append(value)
        elif isinstance(current, list):
            stack.extend(current)


#: A journal is a short record of what was created; anything larger is not one.
MAX_JOURNAL_BYTES: Final = 256 * 1024


def read(path: Path | None = None) -> Journal:
    """Load the journal, returning a fresh one when it is absent or unreadable.

    A journal that is not private to this account is treated as absent rather than
    trusted: it decides what a repair or a disconnect is allowed to remove.
    """
    location = path or default_journal_path()
    try:
        raw = services().read_private_file(location, max_bytes=MAX_JOURNAL_BYTES)
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, PrivacyError, UnicodeDecodeError, json.JSONDecodeError):
        return Journal()
    if not isinstance(payload, dict) or payload.get("schema_version") != JOURNAL_SCHEMA_VERSION:
        return Journal()
    resources = [
        ManagedResource(
            kind=str(item.get("kind", "")),
            name=str(item.get("name", "")),
            adapter=str(item.get("adapter", "")),
        )
        for item in payload.get("resources", [])
        if isinstance(item, dict)
    ]
    known = {f for f in Journal.__slots__ if f != "resources"}
    values = {key: payload[key] for key in known if key in payload}
    journal = Journal(**values)
    journal.resources = resources
    return journal


def write(journal: Journal, path: Path | None = None) -> Path:
    """Persist the journal atomically, private to this account."""
    location = path or default_journal_path()
    payload = asdict(journal)
    _reject_secrets(payload)
    document = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    services().write_private_file(location, document.encode("utf-8"))
    return location


def clear(path: Path | None = None) -> None:
    """Remove the journal only. No other file is deleted."""
    (path or default_journal_path()).unlink(missing_ok=True)
