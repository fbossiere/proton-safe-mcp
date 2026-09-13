"""Orchestration of the managed setup: prerequisites, Bridge, local commit, client.

Every operation here is testable without Qt and without a real client. The order is fixed
by what can be undone: the credential and the configuration are committed first, and the
client is registered last, because a client may start a server the moment a plugin appears.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import __version__
from ..addresses import validate_address
from ..config import Settings
from ..configuration_store import StoredConfiguration, default_config_path
from ..configuration_store import read as read_configuration
from ..configuration_store import write as write_configuration
from ..errors import ConfigurationError, ProtonMCPError
from ..mail import ProtonBridgeClient
from ..secrets import (
    delete_bridge_password,
    has_bridge_password,
    read_bridge_password,
    require_managed_keyring,
    store_bridge_password,
)
from . import journal as journal_store
from . import plugin_assets
from .clients.base import ClientAdapter
from .clients.openai_local import OpenAILocalAdapter
from .inventory import discover_clients, prerequisites
from .journal import Journal, ManagedResource
from .models import (
    Check,
    ClientInstallation,
    Code,
    InstallState,
    Outcome,
    RegistrationOutcome,
    RegistrationPlan,
)
from .runtime import RuntimeLocation, locate_runtime, probe_runtime, serve_command


class Cancelled(ProtonMCPError):
    """The user cancelled before the operation reached its commit phase."""


class CancelToken:
    """Cooperative cancellation checked only where stopping is actually safe.

    It is never checked in the middle of a commit: an interface that says "cancelled"
    while a worker keeps writing would be lying.
    """

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def checkpoint(self) -> None:
        if self._event.is_set():
            raise Cancelled("Cancelled before any change was made", code=Code.CANCELLED)


def mask_address(address: str) -> str:
    """Hide the local part while leaving the account recognisable to its owner."""
    local, separator, domain = address.partition("@")
    if not separator:
        return "•" * len(address)
    return f"{local[:1]}{'•' * max(len(local) - 1, 3)}@{domain}"


@dataclass(frozen=True, slots=True)
class Snapshot:
    """State rebuilt from what exists right now, not from what the journal claims."""

    state: InstallState
    account_masked: str = ""
    configuration_present: bool = False
    credential_present: bool = False
    client_registered: bool = False
    client_confirmed_manually: bool = False
    plugin_current: bool = False
    engine_version: str = __version__
    #: When the last verification ran, in UTC, and what each level then reported.
    last_verified_at: str = ""
    last_checks: dict[str, str] = field(default_factory=dict)
    #: Non-private notes for the collapsed technical section.
    notes: tuple[str, ...] = ()


@dataclass(slots=True)
class BridgeCandidate:
    """What the user typed on the Bridge screen.

    ``password`` is held for the duration of one operation. It is never written to the
    configuration, a process argument, an environment variable or a log line, and the
    caller clears it as soon as the operation returns.
    """

    user: str
    imap_port: int = 1143
    aliases: tuple[str, ...] = ()
    password: str | None = None

    def cleared(self) -> BridgeCandidate:
        return BridgeCandidate(self.user, self.imap_port, self.aliases, None)


@dataclass(slots=True)
class SetupService:
    """The whole managed flow, independent of any interface."""

    config_path: Path = field(default_factory=default_config_path)
    journal_path: Path | None = None
    plugin_dir: Path | None = None
    adapters: Sequence[ClientAdapter] = ()
    runtime: RuntimeLocation | None = None

    def __post_init__(self) -> None:
        if not self.adapters:
            self.adapters = (OpenAILocalAdapter(),)
        if self.runtime is None:
            self.runtime = locate_runtime()

    # -- reading reality ---------------------------------------------------------

    def journal(self) -> Journal:
        return journal_store.read(self.journal_path)

    def _save_journal(self, journal: Journal) -> None:
        journal_store.write(journal, self.journal_path)

    def stored_configuration(self) -> StoredConfiguration | None:
        try:
            return read_configuration(self.config_path)
        except ProtonMCPError:
            return None

    def configuration_problem(self) -> Code | None:
        """Return the coded reason the configuration cannot be used, or None."""
        try:
            read_configuration(self.config_path)
        except ProtonMCPError as exc:
            try:
                return Code(exc.code or Code.CONFIG_INVALID)
            except ValueError:
                # An error carrying a code this layer does not model is still a problem.
                return Code.CONFIG_INVALID
        return None

    def prerequisites(self) -> list[Check]:
        return prerequisites(self.discover())

    def discover(self) -> list[ClientInstallation]:
        return discover_clients(self.adapters)

    def adapter_for(self, installation: ClientInstallation) -> ClientAdapter:
        for adapter in self.adapters:
            if adapter.id == installation.adapter:
                return adapter
        raise ConfigurationError("No adapter owns this installation", code=Code.CLIENT_NOT_FOUND)

    def snapshot(self) -> Snapshot:
        """Rebuild the real state from configuration, keyring, plugin and journal.

        A journal saying READY proves nothing about today; it only says what was recorded.
        """
        recorded = self.journal()
        stored = self.stored_configuration()
        notes: list[str] = []
        if stored is None:
            problem = self.configuration_problem()
            if problem is not None and problem is not Code.CONFIG_MISSING:
                notes.append(str(problem))
            state = (
                InstallState.REPAIR_REQUIRED
                if recorded.resources or recorded.pending_step
                else InstallState.NEW
            )
            return Snapshot(
                state=state,
                last_verified_at=recorded.last_verified_at,
                last_checks=dict(recorded.last_checks),
                notes=tuple(notes),
            )

        credential = has_bridge_password(stored.bridge_user)
        registered = bool(recorded.owned("plugin"))
        plugin_current = plugin_assets.is_current(self.plugin_dir)
        if recorded.disconnect_pending:
            # A disconnect the client refused. Reopening must not look like a healthy
            # installation, or the outstanding entries would never be taken back.
            state = InstallState.REPAIR_REQUIRED
            notes.append(Code.CLIENT_ACTION_REQUIRED)
        elif recorded.pending_step:
            state = InstallState.REPAIR_REQUIRED
            notes.append(Code.INSTALLATION_INCOMPLETE)
        elif not credential:
            state = InstallState.REPAIR_REQUIRED
            notes.append(Code.CREDENTIAL_MISSING)
        elif not registered:
            state = InstallState.CLIENT_REGISTRATION_PENDING
        elif not recorded.client_confirmed_manually:
            state = InstallState.CLIENT_VERIFICATION_PENDING
        elif not plugin_current:
            # The package moved on; the registered plugin no longer matches the runtime.
            state = InstallState.REPAIR_REQUIRED
            notes.append("PLUGIN_OUTDATED")
        else:
            state = InstallState.READY
        return Snapshot(
            state=state,
            account_masked=mask_address(stored.bridge_user),
            configuration_present=True,
            credential_present=credential,
            client_registered=registered,
            client_confirmed_manually=recorded.client_confirmed_manually,
            plugin_current=plugin_current,
            last_verified_at=recorded.last_verified_at,
            last_checks=dict(recorded.last_checks),
            notes=tuple(notes),
        )

    # -- Bridge ------------------------------------------------------------------

    def _settings_for(self, candidate: BridgeCandidate) -> Settings:
        stored = StoredConfiguration(
            bridge_user=candidate.user,
            imap_port=candidate.imap_port,
            aliases=candidate.aliases,
        )
        return Settings.from_stored(stored, path=self.config_path, create_directories=False)

    @staticmethod
    def validate_candidate(candidate: BridgeCandidate) -> BridgeCandidate:
        """Check the address and port locally before opening any connection."""
        user = validate_address(candidate.user.strip(), error=ConfigurationError)
        if not 1 <= candidate.imap_port <= 65535:
            raise ConfigurationError(
                "The IMAP port must be between 1 and 65535", code=Code.CONFIG_INVALID
            )
        aliases = tuple(
            validate_address(item.strip(), error=ConfigurationError)
            for item in candidate.aliases
            if item.strip()
        )
        return BridgeCandidate(user, candidate.imap_port, aliases, candidate.password)

    def test_bridge(
        self, candidate: BridgeCandidate, *, cancel: CancelToken | None = None
    ) -> Outcome:
        """Authenticate with the candidate credential. Nothing is stored and no mail read."""
        if cancel is not None:
            cancel.checkpoint()
        try:
            checked = self.validate_candidate(candidate)
        except ProtonMCPError as exc:
            return Outcome.failure(Code.CONFIG_INVALID, reason=str(exc))
        password = checked.password or read_bridge_password(checked.user)
        if not password:
            return Outcome.failure(Code.CREDENTIAL_MISSING)
        try:
            ProtonBridgeClient(self._settings_for(checked)).probe(password=password)
        except ProtonMCPError as exc:
            code = exc.code or Code.BRIDGE_CONNECTION_FAILED
            return Outcome.failure(Code(code))
        finally:
            del password
        return Outcome.success(Code.BRIDGE_AUTHENTICATED)

    def save_bridge(
        self, candidate: BridgeCandidate, *, cancel: CancelToken | None = None
    ) -> Outcome:
        """Test, then commit the credential and the configuration, or change nothing.

        A credential that fails leaves the previous working installation exactly as it
        was. If the configuration cannot be written after the credential changed, the
        previous credential is put back from memory — it is never written to disk.
        """
        if cancel is not None:
            cancel.checkpoint()
        try:
            checked = self.validate_candidate(candidate)
            require_managed_keyring()
        except ProtonMCPError as exc:
            return Outcome.failure(Code(exc.code or Code.CONFIG_INVALID))

        probe = self.test_bridge(checked, cancel=cancel)
        if not probe.ok:
            return probe
        if cancel is not None:
            # Last safe point: everything below is one short, uninterrupted commit.
            cancel.checkpoint()

        previous = read_bridge_password(checked.user)
        replacing = checked.password is not None and checked.password != previous
        try:
            if replacing and checked.password is not None:
                store_bridge_password(checked.user, checked.password)
            write_configuration(
                StoredConfiguration(
                    bridge_user=checked.user,
                    imap_port=checked.imap_port,
                    aliases=checked.aliases,
                ),
                self.config_path,
            )
        except (ProtonMCPError, OSError) as exc:
            if replacing:
                if previous is not None:
                    store_bridge_password(checked.user, previous)
                else:
                    delete_bridge_password(checked.user)
            code = getattr(exc, "code", None) or Code.CONFIG_INVALID
            return Outcome.failure(Code(code))
        finally:
            previous = None

        recorded = self.journal()
        recorded.state = InstallState.LOCAL_CONFIG_SAVED
        recorded.engine_version = __version__
        recorded.config_path = str(self.config_path)
        self._save_journal(recorded)
        return Outcome.success(Code.CONFIG_SAVED)

    # -- runtime and plugin ------------------------------------------------------

    def serve_command(self) -> tuple[str, ...]:
        if self.runtime is None:
            raise ConfigurationError(
                "The Proton Safe runtime was not found next to this assistant.",
                code=Code.RUNTIME_NOT_FOUND,
            )
        return serve_command(self.runtime, self.config_path)

    def check_runtime(self) -> Outcome:
        """Start the exact configured runtime and validate its MCP tool list."""
        if self.runtime is None:
            return Outcome.failure(Code.RUNTIME_NOT_FOUND)
        return probe_runtime(self.runtime, self.config_path)

    def render_plugin(self) -> plugin_assets.ManagedPluginAssets:
        return plugin_assets.render(serve_command=self.serve_command(), destination=self.plugin_dir)

    # -- client ------------------------------------------------------------------

    def plan_client(self, installation: ClientInstallation) -> tuple[RegistrationPlan, Any]:
        """Render the managed plugin and describe the client changes it implies."""
        adapter = self.adapter_for(installation)
        described = adapter.describe_capabilities(installation)
        assets = self.render_plugin()
        return adapter.plan(described, assets), assets

    def activate(
        self,
        plan: RegistrationPlan,
        assets: plugin_assets.ManagedPluginAssets,
        *,
        migrate: bool = False,
    ) -> RegistrationOutcome:
        """Apply the plan, recording the pending step so an interruption is recoverable.

        ``migrate`` carries the user's explicit decision to take over an earlier Proton
        Safe installation. It is never inferred from the plan alone.
        """
        adapter = self.adapter_for(plan.installation)
        recorded = self.journal()
        recorded.pending_step = "client_migration" if migrate else "client_registration"
        # Registering again withdraws any outstanding disconnect request.
        recorded.disconnect_pending = False
        recorded.erase_local_requested = False
        recorded.plugin_version = assets.plugin_version
        recorded.resource_digest = assets.resource_digest
        recorded.plugin_dir = str(assets.marketplace_dir)
        recorded.client_id = plan.installation.id
        recorded.client_adapter = plan.installation.adapter
        recorded.runtime_command = list(self.serve_command())
        self._save_journal(recorded)

        outcome = adapter.apply(plan, assets, migrate=migrate)

        recorded = self.journal()
        for step in outcome.created:
            recorded.record(ManagedResource(step.target, step.detail, plan.installation.adapter))
        # Entries taken over are recorded so a resumed run knows they are already gone.
        for step in outcome.migrated:
            if step.detail not in recorded.migrated_from:
                recorded.migrated_from.append(step.detail)
        recorded.pending_step = ""
        if outcome.ok:
            recorded.state = InstallState.CLIENT_VERIFICATION_PENDING
            # Registering is not loading: only the user can confirm the client sees it.
            recorded.client_confirmed_manually = False
        else:
            recorded.state = InstallState.CLIENT_REGISTRATION_PENDING
        self._save_journal(recorded)
        return outcome

    def confirm_client_manually(self) -> Outcome:
        """Record that the user checked the tools in their assistant. Never a proof."""
        recorded = self.journal()
        if not recorded.owned("plugin"):
            return Outcome.failure(Code.CLIENT_ACTION_REQUIRED)
        recorded.client_confirmed_manually = True
        recorded.state = InstallState.READY
        self._save_journal(recorded)
        return Outcome.success(Code.CLIENT_VERIFIED_MANUALLY)

    # -- verification ------------------------------------------------------------

    def verify(self) -> list[Check]:
        """The three distinct levels, never collapsed into one green line.

        The result is recorded with its time so the status table can say when it was last
        checked. A recorded result is history, never a claim about right now.
        """
        checks: list[Check] = []
        stored = self.stored_configuration()
        if stored is None:
            problem = self.configuration_problem() or Code.CONFIG_MISSING
            return self._record_verification(
                [
                    Check("bridge", "fail", problem),
                    Check("runtime", "skip", Code.CONFIG_MISSING),
                    Check("client", "skip", Code.CONFIG_MISSING),
                ]
            )
        bridge = self.test_bridge(
            BridgeCandidate(stored.bridge_user, stored.imap_port, stored.aliases)
        )
        checks.append(Check("bridge", "pass" if bridge.ok else "fail", bridge.code))
        if not bridge.ok:
            checks.append(Check("runtime", "skip", Code.CREDENTIAL_MISSING))
        else:
            runtime = self.check_runtime()
            checks.append(Check("runtime", "pass" if runtime.ok else "fail", runtime.code))
        checks.append(self._client_check())
        return self._record_verification(checks)

    def _record_verification(self, checks: list[Check]) -> list[Check]:
        recorded = self.journal()
        recorded.last_verified_at = datetime.now(UTC).replace(microsecond=0).isoformat()
        recorded.last_checks = {check.id: f"{check.status}:{check.code}" for check in checks}
        self._save_journal(recorded)
        return checks

    def _client_check(self) -> Check:
        recorded = self.journal()
        references = [item.name for item in recorded.owned("plugin")]
        if not references:
            return Check("client", "action_required", Code.CLIENT_ACTION_REQUIRED)
        installation = self._recorded_installation(recorded)
        if installation is not None:
            adapter = self.adapter_for(installation)
            listed = getattr(adapter, "installed_plugins", None)
            if callable(listed):
                # Ask with the capabilities this adapter actually probed, so "cannot
                # list" is never mistaken for "the plugin is gone".
                reported = listed(adapter.describe_capabilities(installation))
                if reported is not None and not set(references) & set(reported):
                    return Check("client", "action_required", Code.CLIENT_ACTION_REQUIRED)
        if not recorded.client_confirmed_manually:
            # Registered, but nothing proves the client actually loaded it.
            return Check("client", "action_required", Code.CLIENT_RESTART_REQUIRED)
        return Check("client", "pass", Code.CLIENT_VERIFIED_MANUALLY)

    def _recorded_installation(self, recorded: Journal) -> ClientInstallation | None:
        if not recorded.client_id:
            return None
        for installation in self.discover():
            if installation.id == recorded.client_id:
                return installation
        return None

    # -- removal -----------------------------------------------------------------

    def disconnect(self, *, erase_local: bool = False) -> Outcome:
        """Remove the assistant's own client resources, and optionally its local data.

        Bridge, mail, drafts and attachments are never touched, and no general cleanup of
        `~/.codex`, `~/.config` or the keyring happens. A credential that predates the
        managed setup is only removed when the user explicitly asks for it.

        When client entries could not be removed, the local erase is deferred and the
        journal is kept: it is the only record of what is still registered and of which
        installation owns it. The request is remembered and honoured once the removal
        actually succeeds.
        """
        recorded = self.journal()
        resources = [(item.kind, item.name) for item in recorded.resources]
        installation = self._recorded_installation(recorded)
        outcome: RegistrationOutcome | None = None
        if resources and installation is not None:
            adapter = self.adapter_for(installation)
            outcome = adapter.remove(adapter.describe_capabilities(installation), resources)
            for step in outcome.created:
                recorded.forget(step.target, step.detail)
        remaining = list(recorded.resources)
        recorded.state = InstallState.REPAIR_REQUIRED if remaining else InstallState.DISCONNECTED
        recorded.client_confirmed_manually = False
        # The request is remembered whether or not it can be honoured now, so a later
        # successful removal finishes what the user asked for.
        recorded.erase_local_requested = recorded.erase_local_requested or erase_local
        recorded.disconnect_pending = bool(remaining)
        self._save_journal(recorded)

        if remaining:
            # Client entries are still registered, so the journal is what a retry needs:
            # it names the resources and which installation owns them. Erasing it here
            # would strand those entries with nothing left to remove them by, so the
            # local erase is deferred rather than performed.
            return Outcome(
                ok=False,
                code=Code.CLIENT_ACTION_REQUIRED,
                details={
                    "remaining": [item.name for item in remaining],
                    "local_data_kept": recorded.erase_local_requested,
                },
            )

        if recorded.erase_local_requested:
            stored = self.stored_configuration()
            if stored is not None:
                delete_bridge_password(stored.bridge_user)
            self.config_path.unlink(missing_ok=True)
            journal_store.clear(self.journal_path)

        if outcome is not None and outcome.manual_step_required:
            return Outcome(ok=True, code=Code.CLIENT_RESTART_REQUIRED, details={"remaining": []})
        return Outcome.success(Code.CLIENT_REMOVED)

    # -- export ------------------------------------------------------------------

    def diagnostic_report(self) -> dict[str, Any]:
        """A report with no address, path, mailbox figure or raw command output."""
        from ..doctor import json_report, run_checks

        recorded = self.journal()
        report = json_report(run_checks(config_path=self.config_path))
        report["assistant"] = {
            "state": self.snapshot().state,
            "plugin_version": recorded.plugin_version,
            "resource_digest": recorded.resource_digest[:12],
            "client_adapter": recorded.client_adapter,
            "managed_resources": sorted({item.kind for item in recorded.resources}),
            "client_confirmed_manually": recorded.client_confirmed_manually,
        }
        report["prerequisites"] = [
            {"id": check.id, "status": check.status, "code": str(check.code)}
            for check in self.prerequisites()
        ]
        return report
