"""States, stable codes and result records shared by the assistant and its interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class InstallState(StrEnum):
    """Facts already recorded. Reaching a state never lets a later run skip its checks."""

    NEW = "NEW"
    PREREQUISITES_READY = "PREREQUISITES_READY"
    BRIDGE_VALIDATED = "BRIDGE_VALIDATED"
    LOCAL_CONFIG_SAVED = "LOCAL_CONFIG_SAVED"
    CLIENT_REGISTRATION_PENDING = "CLIENT_REGISTRATION_PENDING"
    CLIENT_REGISTERED = "CLIENT_REGISTERED"
    CLIENT_VERIFICATION_PENDING = "CLIENT_VERIFICATION_PENDING"
    READY = "READY"
    REPAIR_REQUIRED = "REPAIR_REQUIRED"
    DISCONNECTED = "DISCONNECTED"
    CANCELLED = "CANCELLED"


class Code(StrEnum):
    """Stable identifiers. User-visible text is translated from these, never parsed."""

    # Prerequisites
    SYSTEM_SUPPORTED = "SYSTEM_SUPPORTED"
    SYSTEM_UNSUPPORTED = "SYSTEM_UNSUPPORTED"
    SESSION_OK = "SESSION_OK"
    SESSION_ROOT = "SESSION_ROOT"
    SESSION_NO_GRAPHICAL = "SESSION_NO_GRAPHICAL"
    KEYRING_AVAILABLE = "KEYRING_AVAILABLE"
    KEYRING_LOCKED = "KEYRING_LOCKED"
    KEYRING_UNAVAILABLE = "KEYRING_UNAVAILABLE"
    BRIDGE_APP_DETECTED = "BRIDGE_APP_DETECTED"
    BRIDGE_APP_UNKNOWN = "BRIDGE_APP_UNKNOWN"
    CLIENT_DETECTED = "CLIENT_DETECTED"
    CLIENT_NOT_FOUND = "CLIENT_NOT_FOUND"

    # Bridge
    BRIDGE_AUTHENTICATED = "BRIDGE_AUTHENTICATED"
    BRIDGE_UNREACHABLE = "BRIDGE_UNREACHABLE"
    BRIDGE_AUTH_FAILED = "BRIDGE_AUTH_FAILED"
    BRIDGE_TLS_FAILED = "BRIDGE_TLS_FAILED"
    BRIDGE_CONNECTION_FAILED = "BRIDGE_CONNECTION_FAILED"

    # Local configuration
    CONFIG_SAVED = "CONFIG_SAVED"
    CONFIG_LOADED = "CONFIG_LOADED"
    CONFIG_MISSING = "CONFIG_MISSING"
    CONFIG_INVALID = "CONFIG_INVALID"
    CONFIG_PERMISSIONS = "CONFIG_PERMISSIONS"
    CONFIG_SCHEMA_UNSUPPORTED = "CONFIG_SCHEMA_UNSUPPORTED"
    CONFIG_CONFLICT = "CONFIG_CONFLICT"
    CREDENTIAL_MISSING = "CREDENTIAL_MISSING"

    # Runtime
    RUNTIME_READY = "RUNTIME_READY"
    RUNTIME_START_FAILED = "RUNTIME_START_FAILED"
    RUNTIME_TOOLS_UNEXPECTED = "RUNTIME_TOOLS_UNEXPECTED"
    RUNTIME_NOT_FOUND = "RUNTIME_NOT_FOUND"

    # Client integration
    CLIENT_REGISTERED = "CLIENT_REGISTERED"
    CLIENT_RESTART_REQUIRED = "CLIENT_RESTART_REQUIRED"
    CLIENT_ACTION_REQUIRED = "CLIENT_ACTION_REQUIRED"
    CLIENT_VERIFIED_MANUALLY = "CLIENT_VERIFIED_MANUALLY"
    CLIENT_REMOVED = "CLIENT_REMOVED"
    MIGRATION_REQUIRED = "MIGRATION_REQUIRED"
    MIGRATION_DONE = "MIGRATION_DONE"
    MIGRATION_MANUAL = "MIGRATION_MANUAL"
    UNSUPPORTED_CLIENT = "UNSUPPORTED_CLIENT"
    CLIENT_COMMAND_FAILED = "CLIENT_COMMAND_FAILED"
    CLIENT_COMMAND_TIMEOUT = "CLIENT_COMMAND_TIMEOUT"

    # Flow
    INSTALLATION_INCOMPLETE = "INSTALLATION_INCOMPLETE"
    CANCELLED = "CANCELLED"
    PLUGIN_ASSETS_INVALID = "PLUGIN_ASSETS_INVALID"
    LOCAL_DATA_KEPT = "LOCAL_DATA_KEPT"


CheckStatus = str  # "pass" | "warn" | "action_required" | "fail" | "skip"


@dataclass(frozen=True, slots=True)
class Check:
    """One prerequisite or verification line, safe to render or export."""

    id: str
    status: CheckStatus
    code: Code
    #: Non-private supporting text such as a version. Never a path, address or raw output.
    hint: str = ""

    @property
    def blocking(self) -> bool:
        return self.status in {"fail", "action_required"}


@dataclass(frozen=True, slots=True)
class Outcome:
    """The result of one assistant operation."""

    ok: bool
    code: Code
    checks: tuple[Check, ...] = ()
    #: Non-private details for the collapsed technical section.
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(cls, code: Code, **details: Any) -> Outcome:
        return cls(True, code, details=details)

    @classmethod
    def failure(cls, code: Code, **details: Any) -> Outcome:
        return cls(False, code, details=details)


@dataclass(frozen=True, slots=True)
class ClientInstallation:
    """One discovered client host the assistant may register with."""

    #: Stable identifier for this adapter and host, e.g. "openai-local:default".
    id: str
    #: Adapter identifier, e.g. "openai-local".
    adapter: str
    #: Human name shown without a path, e.g. "ChatGPT desktop / Codex".
    display_name: str
    #: Absolute path of the verified executable, shown only under "Details".
    executable: Path
    version: str
    #: Capabilities corroborated by the client's own help output, not by version number.
    capabilities: frozenset[str] = frozenset()
    #: Hosts sharing one configuration are reported once, listing what they cover.
    shared_surfaces: tuple[str, ...] = ()

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities


@dataclass(frozen=True, slots=True)
class PlanStep:
    """One announced modification. Shown before anything is written."""

    action: str
    #: Translation key describing the target, e.g. "plan.marketplace".
    target: str
    #: Non-private supporting text, e.g. a plugin name.
    detail: str = ""


@dataclass(frozen=True, slots=True)
class RegistrationPlan:
    installation: ClientInstallation
    steps: tuple[PlanStep, ...]
    #: Existing Proton Safe entries this plan replaces or disables, by name.
    replaces: tuple[str, ...] = ()
    #: Entries that look like Proton Safe but that the assistant cannot take over on its
    #: own — an MCP server someone registered by hand, for instance. They need a targeted
    #: decision and are never overwritten.
    conflicts: tuple[str, ...] = ()
    #: This project's own plugin installed from another marketplace. The assistant can
    #: take these over, but only when the user explicitly asks for the migration.
    migrations: tuple[PlanStep, ...] = ()

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)

    @property
    def requires_migration(self) -> bool:
        """Whether finishing this plan means taking over an existing installation."""
        return bool(self.migrations)


@dataclass(frozen=True, slots=True)
class RegistrationOutcome:
    ok: bool
    code: Code
    #: What the assistant actually created, for the removal path.
    created: tuple[PlanStep, ...] = ()
    #: Entries taken over from a previous installation, so a resumed run knows they are
    #: already gone and does not try to remove them twice.
    migrated: tuple[PlanStep, ...] = ()
    #: True when the client needs a restart or an in-app step before tools appear.
    manual_step_required: bool = False
    details: dict[str, Any] = field(default_factory=dict)
