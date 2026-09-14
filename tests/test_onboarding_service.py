"""A05, A06, A07, A08, A11, A13, A14, A15, A16 and A19: the managed flow's real effects."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import ClassVar

import pytest

from proton_safe_mcp.errors import BridgeError
from proton_safe_mcp.onboarding import journal as journal_store
from proton_safe_mcp.onboarding import plugin_assets
from proton_safe_mcp.onboarding.clients.base import CommandResult
from proton_safe_mcp.onboarding.clients.openai_local import OpenAILocalAdapter
from proton_safe_mcp.onboarding.models import (
    ClientInstallation,
    Code,
    InstallState,
    PlanStep,
    RegistrationOutcome,
)
from proton_safe_mcp.onboarding.service import (
    BridgeCandidate,
    CancelToken,
    SetupService,
    mask_address,
)

ACCOUNT = "person@example.com"
# Fictional Bridge-generated values. They exist so the tests can prove one never leaves
# memory; nothing here is a real credential.
GOOD_SECRET = "bridge-generated-good"  # noqa: S105
BAD_SECRET = "bridge-generated-wrong"  # noqa: S105


class FakeBridge:
    """An IMAP double that records exactly which commands the flow issued."""

    commands: ClassVar[list[str]] = []

    def __init__(self, settings, *_args, **_kwargs):
        self.settings = settings

    def probe(self, *, password=None):
        FakeBridge.commands.append("LOGIN")
        if password != GOOD_SECRET:
            raise BridgeError("login refused", code="BRIDGE_AUTH_FAILED")
        FakeBridge.commands.append("NOOP")
        FakeBridge.commands.append("LOGOUT")

    def status(self):  # pragma: no cover - must never be reached by the installer
        raise AssertionError("the installer must not read mailbox statistics")

    def list_messages(self, *_args, **_kwargs):  # pragma: no cover
        raise AssertionError("the installer must not read mail")

    def append_draft(self, **_kwargs):  # pragma: no cover
        raise AssertionError("the installer must not create a draft")


@pytest.fixture
def bridge(monkeypatch):
    FakeBridge.commands = []
    monkeypatch.setattr("proton_safe_mcp.onboarding.service.ProtonBridgeClient", FakeBridge)
    return FakeBridge


class FakeClient:
    """A Codex-like client whose capabilities and answers the test controls."""

    def __init__(self, *, capabilities=("plugin", "marketplace", "add", "list", "remove")):
        self.capabilities = set(capabilities)
        self.marketplaces: list[str] = []
        self.plugins: list[str] = []
        self.calls: list[list[str]] = []
        self.fail_on: str | None = None
        self.hostile_output = ""

    def run(self, argv, *, timeout=5.0):
        arguments = [str(item) for item in argv][1:]
        self.calls.append(arguments)
        noise = self.hostile_output
        if arguments[:1] == ["--version"]:
            return CommandResult(True, 0, f"codex-cli 1.4.0{noise}")
        if arguments[-1] == "--help":
            wanted = [item for item in arguments[:-1] if item != "plugin"]
            supported = "plugin" in self.capabilities and all(
                item in self.capabilities for item in wanted
            )
            return CommandResult(supported, 0 if supported else 2, noise)
        if arguments[:3] == ["plugin", "marketplace", "add"]:
            if self.fail_on == "marketplace":
                return CommandResult(False, 1, noise)
            # A real client registers the marketplace under the name its manifest
            # declares, which is also what the remove command takes.
            manifest = Path(arguments[3]) / ".agents" / "plugins" / "marketplace.json"
            try:
                name = json.loads(manifest.read_text(encoding="utf-8"))["name"]
            except (OSError, KeyError, json.JSONDecodeError):
                return CommandResult(False, 1, noise)
            self.marketplaces.append(name)
            return CommandResult(True, 0, noise)
        if arguments[:2] == ["plugin", "add"]:
            if self.fail_on == "plugin":
                return CommandResult(False, 1, noise)
            self.plugins.append(arguments[2])
            return CommandResult(True, 0, noise)
        if arguments[:2] == ["plugin", "list"]:
            return CommandResult(True, 0, "\n".join(self.plugins) + noise)
        if arguments[:2] == ["plugin", "remove"]:
            if arguments[2] in self.plugins:
                self.plugins.remove(arguments[2])
                return CommandResult(True, 0, noise)
            return CommandResult(False, 1, noise)
        if arguments[:3] == ["plugin", "marketplace", "remove"]:
            if arguments[3] not in self.marketplaces:
                return CommandResult(False, 1, noise)
            self.marketplaces.remove(arguments[3])
            return CommandResult(True, 0, noise)
        return CommandResult(False, 2, noise)


@pytest.fixture
def client():
    return FakeClient()


@pytest.fixture
def codex_home(tmp_path):
    """Stands in for the client's own configuration directory."""
    directory = tmp_path / "codex-home"
    directory.mkdir()
    return directory


@pytest.fixture
def service(tmp_path, client, codex_home, monkeypatch, fake_keyring, make_executable):
    """A service wired to a fake client, a fake keyring and private temporary paths."""
    executable = make_executable(tmp_path / "bin", "codex")

    adapter = OpenAILocalAdapter(
        client.run, candidate_paths=(str(executable),), config_home=codex_home
    )
    monkeypatch.setattr("shutil.which", lambda _name: None)
    config_dir = tmp_path / "config" / "proton-safe-mcp"
    config_dir.mkdir(mode=0o700, parents=True)

    runtime = make_executable(tmp_path / "runtime", "proton-safe-mcp")

    from proton_safe_mcp.onboarding.runtime import RuntimeLocation

    return SetupService(
        config_path=config_dir / "config.toml",
        journal_path=tmp_path / "state" / "install.json",
        plugin_dir=tmp_path / "plugin",
        adapters=(adapter,),
        runtime=RuntimeLocation((str(runtime),), packaged=True),
    )


def _candidate(password=GOOD_SECRET, user=ACCOUNT):
    return BridgeCandidate(user=user, imap_port=1143, aliases=(), password=password)


def _installation(service):
    return service.discover()[0]


# -- account masking --------------------------------------------------------------


def test_the_account_is_masked_but_still_recognisable():
    assert mask_address(ACCOUNT) == "p•••••@example.com"
    assert ACCOUNT not in mask_address(ACCOUNT)


# -- A11: no mail is touched by the installer ------------------------------------


def test_a11_the_installer_only_authenticates_and_logs_out(service, bridge):
    assert service.save_bridge(_candidate()).ok

    assert bridge.commands == ["LOGIN", "NOOP", "LOGOUT"]


def test_a11_verification_never_reads_or_writes_mail(service, bridge):
    service.save_bridge(_candidate())
    bridge.commands.clear()
    service.verify()

    assert set(bridge.commands) <= {"LOGIN", "NOOP", "LOGOUT"}


# -- A05: a wrong new secret changes nothing -------------------------------------


def test_a05_a_wrong_new_secret_keeps_the_working_installation(service, bridge, fake_keyring):
    assert service.save_bridge(_candidate()).ok
    stored_before = service.config_path.read_bytes()

    outcome = service.save_bridge(_candidate(password=BAD_SECRET))

    assert not outcome.ok
    assert outcome.code is Code.BRIDGE_AUTH_FAILED
    assert fake_keyring.store[("proton-safe-mcp", ACCOUNT)] == GOOD_SECRET
    assert service.config_path.read_bytes() == stored_before


def test_a05_a_failed_configuration_write_restores_the_previous_secret(
    service, bridge, fake_keyring, monkeypatch
):
    service.save_bridge(_candidate())
    other_good = "second-good-secret"
    monkeypatch.setattr(FakeBridge, "probe", lambda self, *, password=None: None)

    def explode(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("proton_safe_mcp.onboarding.service.write_configuration", explode)
    outcome = service.save_bridge(_candidate(password=other_good))

    assert not outcome.ok
    # The previous, working credential is back, and it never touched the disk.
    assert fake_keyring.store[("proton-safe-mcp", ACCOUNT)] == GOOD_SECRET
    assert other_good not in service.config_path.read_text(encoding="utf-8")


def test_a_first_failed_configuration_write_leaves_no_credential_behind(
    service, bridge, fake_keyring, monkeypatch
):
    def explode(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("proton_safe_mcp.onboarding.service.write_configuration", explode)
    outcome = service.save_bridge(_candidate())

    assert not outcome.ok
    assert ("proton-safe-mcp", ACCOUNT) not in fake_keyring.store


def test_the_secret_never_reaches_the_configuration_or_the_journal(service, bridge):
    service.save_bridge(_candidate())
    installation = _installation(service)
    plan, assets = service.plan_client(installation)
    service.activate(plan, assets)

    written = service.config_path.read_text(encoding="utf-8")
    recorded = service.journal_path.read_text(encoding="utf-8")
    rendered = (assets.plugin_dir / ".mcp.json").read_text(encoding="utf-8")

    for blob in (written, recorded, rendered):
        assert GOOD_SECRET not in blob
    assert "PROTON_BRIDGE_PASSWORD" not in rendered
    assert "--config" in rendered


# -- A13: an unusable keyring blocks instead of falling back ----------------------


def test_a13_a_locked_keyring_blocks_without_a_replacement_store(
    service, bridge, fake_keyring, monkeypatch
):
    fake_keyring.locked = True

    outcome = service.save_bridge(_candidate())

    assert not outcome.ok
    assert outcome.code is Code.KEYRING_LOCKED
    assert not service.config_path.exists()


def test_a13_an_unapproved_backend_blocks_without_a_replacement_store(
    service, bridge, unavailable_keyring
):
    outcome = service.save_bridge(_candidate())

    assert not outcome.ok
    assert outcome.code is Code.KEYRING_UNAVAILABLE
    assert not service.config_path.exists()


# -- A14: cancellation stops before a commit, never during one --------------------


def test_a14_cancelling_before_the_commit_changes_nothing(service, bridge):
    token = CancelToken()
    token.cancel()

    from proton_safe_mcp.onboarding.service import Cancelled

    with pytest.raises(Cancelled):
        service.save_bridge(_candidate(), cancel=token)

    assert not service.config_path.exists()
    assert FakeBridge.commands == []


def test_a14_cancelling_after_the_test_still_completes_the_commit(service, bridge, fake_keyring):
    token = CancelToken()
    original = FakeBridge.probe

    def probe_then_cancel(self, *, password=None):
        original(self, password=password)
        # The user presses Cancel while the connection test is running.
        token.cancel()

    FakeBridge.probe = probe_then_cancel  # type: ignore[method-assign]
    try:
        from proton_safe_mcp.onboarding.service import Cancelled

        with pytest.raises(Cancelled):
            service.save_bridge(_candidate(), cancel=token)
    finally:
        FakeBridge.probe = original  # type: ignore[method-assign]

    # Stopping at the checkpoint means nothing was half-written.
    assert not service.config_path.exists()
    assert ("proton-safe-mcp", ACCOUNT) not in fake_keyring.store


# -- A07: running twice produces one installation --------------------------------


def test_a07_two_identical_runs_leave_one_configuration_and_one_connection(service, bridge):
    installation = _installation(service)
    for _ in range(2):
        assert service.save_bridge(_candidate()).ok
        plan, assets = service.plan_client(installation)
        service.activate(plan, assets)

    recorded = service.journal()

    assert len([item for item in recorded.resources if item.kind == "plugin"]) == 1
    assert len([item for item in recorded.resources if item.kind == "marketplace"]) == 1
    assert [item.name for item in service.config_path.parent.iterdir()] == ["config.toml"]


def test_a07_the_second_run_replaces_rather_than_duplicating(service, bridge, client):
    installation = _installation(service)
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(installation)
    service.activate(plan, assets)

    second_plan, _ = service.plan_client(installation)

    assert assets.plugin_reference in second_plan.replaces
    assert not second_plan.has_conflicts
    assert client.plugins == [assets.plugin_reference]


# -- A08: an unmanaged or edited entry is a visible conflict ----------------------


def test_a08_an_unmanaged_proton_safe_server_is_a_conflict_not_an_overwrite(
    service, bridge, codex_home
):
    service.save_bridge(_candidate())
    config = codex_home / "config.toml"
    config.write_text(
        "[mcp_servers.proton-safe]\n"
        'command = "uvx"\n'
        'args = ["--from", "proton-safe-mcp==2.0.3", "proton-safe-mcp", "serve"]\n',
        encoding="utf-8",
    )
    before = config.read_bytes()

    plan, _assets = service.plan_client(_installation(service))

    assert plan.has_conflicts
    assert "proton-safe" in plan.conflicts
    # The client's own file is never rewritten by the adapter.
    assert config.read_bytes() == before


def test_a08_activation_refuses_while_a_conflict_stands(service, bridge, client, codex_home):
    service.save_bridge(_candidate())
    config = codex_home / "config.toml"
    config.write_text(
        '[mcp_servers.proton-safe]\ncommand = "uvx"\nargs = ["proton-safe-mcp"]\n',
        encoding="utf-8",
    )
    plan, assets = service.plan_client(_installation(service))

    outcome = service.activate(plan, assets)

    assert not outcome.ok
    assert outcome.code is Code.CONFIG_CONFLICT
    assert client.plugins == []
    assert client.marketplaces == []


def test_an_unrelated_server_is_never_claimed_by_this_project(service):
    entry = {"command": "uvx", "args": ["--from", "proton-notes", "serve"]}

    assert not OpenAILocalAdapter.looks_like_proton_safe(entry)


def test_a_managed_entry_is_told_apart_from_the_historic_one():
    managed = {"command": "/opt/x/proton-safe-mcp", "args": ["serve", "--config", "/tmp/a.toml"]}
    historic = {"command": "uvx", "args": ["--from", "proton-safe-mcp==2.0.3", "serve"]}

    assert OpenAILocalAdapter.is_managed_command(managed)
    assert not OpenAILocalAdapter.is_managed_command(historic)
    assert OpenAILocalAdapter.looks_like_proton_safe(historic)


# -- A16: the historic plugin migrates without a double registration -------------


def test_a16_a_historic_plugin_in_another_marketplace_is_offered_as_a_migration(
    service, bridge, client
):
    client.plugins.append("proton-safe@personal")
    service.save_bridge(_candidate())

    plan, _assets = service.plan_client(_installation(service))

    # This project's own plugin can be taken over; it is not an unresolvable conflict.
    assert [step.detail for step in plan.migrations] == ["proton-safe@personal"]
    assert plan.requires_migration
    assert not plan.has_conflicts
    assert plan.replaces == ()


def test_a16_a_migration_is_refused_until_the_user_asks_for_it(service, bridge, client):
    client.plugins.append("proton-safe@personal")
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))

    outcome = service.activate(plan, assets)

    assert not outcome.ok
    assert outcome.code is Code.MIGRATION_REQUIRED
    assert outcome.details["entries"] == ["proton-safe@personal"]
    # Nothing was written, and the old installation is untouched.
    assert client.plugins == ["proton-safe@personal"]
    assert client.marketplaces == []
    assert service.journal().resources == []


def test_a16_an_authorised_migration_completes_end_to_end(service, bridge, client, fake_keyring):
    """The whole migration, not just its detection."""
    client.plugins.append("proton-safe@personal")
    client.plugins.append("unrelated-tool@personal")
    client.marketplaces.append("personal")
    assert service.save_bridge(_candidate()).ok
    stored_secret = fake_keyring.store[("proton-safe-mcp", ACCOUNT)]
    plan, assets = service.plan_client(_installation(service))

    outcome = service.activate(plan, assets, migrate=True)

    assert outcome.ok
    assert outcome.code is Code.MIGRATION_DONE
    assert [step.detail for step in outcome.migrated] == ["proton-safe@personal"]
    # Exactly one managed connection, and the old one is gone.
    assert client.plugins == ["unrelated-tool@personal", assets.plugin_reference]
    # Other plugins and their marketplace survive.
    assert "personal" in client.marketplaces
    assert "unrelated-tool@personal" in client.plugins
    # The credential was never retyped and never changed.
    assert fake_keyring.store[("proton-safe-mcp", ACCOUNT)] == stored_secret
    # The state is honest: registered, not yet confirmed by the client.
    assert service.snapshot().state is InstallState.CLIENT_VERIFICATION_PENDING
    recorded = service.journal()
    assert recorded.migrated_from == ["proton-safe@personal"]
    assert recorded.pending_step == ""


def test_a16_a_migration_reuses_the_stored_credential_without_retyping(
    service, bridge, client, fake_keyring
):
    client.plugins.append("proton-safe@personal")
    service.save_bridge(_candidate())
    bridge.commands.clear()

    # The Bridge screen hands over no password when the field is left empty.
    assert service.save_bridge(BridgeCandidate(ACCOUNT, 1143, (), None)).ok
    plan, assets = service.plan_client(_installation(service))
    assert service.activate(plan, assets, migrate=True).ok

    assert fake_keyring.store[("proton-safe-mcp", ACCOUNT)] == GOOD_SECRET
    assert bridge.commands == ["LOGIN", "NOOP", "LOGOUT"]


def test_a16_a_second_run_after_a_migration_finds_nothing_left_to_migrate(service, bridge, client):
    client.plugins.append("proton-safe@personal")
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))
    service.activate(plan, assets, migrate=True)

    second_plan, _assets = service.plan_client(_installation(service))

    assert second_plan.migrations == ()
    assert assets.plugin_reference in second_plan.replaces
    assert not second_plan.has_conflicts


def test_a16_a_client_that_cannot_remove_asks_for_a_manual_step_and_writes_nothing(
    service, bridge, client
):
    client.plugins.append("proton-safe@personal")
    client.capabilities.discard("remove")
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))

    outcome = service.activate(plan, assets, migrate=True)

    assert not outcome.ok
    assert outcome.code is Code.MIGRATION_MANUAL
    assert outcome.manual_step_required
    assert outcome.details["entries"] == ["proton-safe@personal"]
    # Refusing before writing avoids leaving two Proton Safe servers registered.
    assert client.plugins == ["proton-safe@personal"]
    assert client.marketplaces == []


def test_a16_an_interrupted_migration_is_resumable(service, bridge, client, monkeypatch):
    client.plugins.append("proton-safe@personal")
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))

    # The client accepts the removal, then fails to install the replacement.
    client.fail_on = "marketplace"
    first = service.activate(plan, assets, migrate=True)

    assert not first.ok
    assert [step.detail for step in first.migrated] == ["proton-safe@personal"]
    recorded = service.journal()
    assert recorded.pending_step == ""
    assert recorded.migrated_from == ["proton-safe@personal"]
    # The local connection survived the failed client step.
    assert service.config_path.exists()
    assert service.snapshot().state is InstallState.CLIENT_REGISTRATION_PENDING

    # Reopening the assistant: the old entry is already gone, so nothing is re-migrated.
    client.fail_on = None
    resumed_plan, resumed_assets = service.plan_client(_installation(service))
    assert resumed_plan.migrations == ()
    assert not resumed_plan.has_conflicts

    outcome = service.activate(resumed_plan, resumed_assets)

    assert outcome.ok
    assert client.plugins == [resumed_assets.plugin_reference]


def test_an_unmanaged_server_entry_is_never_offered_as_a_migration(service, bridge, codex_home):
    """The assistant cannot rewrite the client's own file, so this stays a conflict."""
    service.save_bridge(_candidate())
    (codex_home / "config.toml").write_text(
        '[mcp_servers.my-proton]\ncommand = "uvx"\nargs = ["proton-safe-mcp"]\n',
        encoding="utf-8",
    )

    plan, _assets = service.plan_client(_installation(service))

    assert "my-proton" in plan.conflicts
    assert plan.migrations == ()


def test_a16_other_plugins_are_left_alone_by_a_removal(service, bridge, client):
    client.plugins.append("unrelated-tool@personal")
    client.marketplaces.append("personal")
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))
    service.activate(plan, assets)

    service.disconnect()

    assert client.plugins == ["unrelated-tool@personal"]
    assert client.marketplaces == ["personal"]


# -- A06: an interruption between commit and registration is recoverable ----------


def test_a06_an_interrupted_registration_is_detected_at_the_next_start(service, bridge):
    service.save_bridge(_candidate())
    recorded = service.journal()
    recorded.pending_step = "client_registration"
    journal_store.write(recorded, service.journal_path)

    snapshot = service.snapshot()

    assert snapshot.state is InstallState.REPAIR_REQUIRED
    assert str(Code.INSTALLATION_INCOMPLETE) in snapshot.notes
    assert service.journal_path.read_text(encoding="utf-8").count("password") == 0


def test_a06_a_failed_client_step_keeps_the_local_connection(service, bridge, client):
    service.save_bridge(_candidate())
    client.fail_on = "plugin"
    installation = _installation(service)
    plan, assets = service.plan_client(installation)

    outcome = service.activate(plan, assets)

    assert not outcome.ok
    assert service.config_path.exists()
    recorded = service.journal()
    assert recorded.state == InstallState.CLIENT_REGISTRATION_PENDING
    assert recorded.pending_step == ""
    # The marketplace that was created is recorded, so a later removal can find it.
    assert [item.kind for item in recorded.resources] == ["marketplace"]


def test_a06_no_credential_is_ever_written_to_the_journal(service, bridge):
    service.save_bridge(_candidate())
    recorded = service.journal()
    recorded.config_path = str(service.config_path)
    journal_store.write(recorded, service.journal_path)

    payload = json.loads(service.journal_path.read_text(encoding="utf-8"))
    blob = json.dumps(payload).lower()

    assert GOOD_SECRET not in blob
    assert "password" not in blob


def test_the_journal_refuses_a_credential_shaped_field(service):
    recorded = service.journal()
    recorded.resources.append(journal_store.ManagedResource("password", "oops"))
    # The guard matches on keys, so a field named like a credential is what it rejects.
    recorded.resources.clear()
    recorded.pending_step = "x"
    journal_store.write(recorded, service.journal_path)

    with pytest.raises(ValueError, match="never hold a credential"):
        journal_store._reject_secrets({"bridge_password": "leak"})


# -- A19: a local success is never a client confirmation -------------------------


def test_a19_registration_alone_never_reaches_ready(service, bridge):
    service.save_bridge(_candidate())
    installation = _installation(service)
    plan, assets = service.plan_client(installation)

    outcome = service.activate(plan, assets)

    assert outcome.ok
    assert outcome.manual_step_required
    snapshot = service.snapshot()
    assert snapshot.state is InstallState.CLIENT_VERIFICATION_PENDING
    assert snapshot.state is not InstallState.READY


def test_a19_the_three_levels_stay_distinct(service, bridge, monkeypatch):
    from proton_safe_mcp.onboarding.models import Outcome

    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))
    service.activate(plan, assets)
    monkeypatch.setattr(
        SetupService, "check_runtime", lambda _self: Outcome.success(Code.RUNTIME_READY)
    )

    checks = {check.id: check for check in service.verify()}

    assert checks["bridge"].status == "pass"
    assert checks["runtime"].status == "pass"
    # Registered, but the client itself has confirmed nothing.
    assert checks["client"].status == "action_required"
    assert checks["client"].code is Code.CLIENT_RESTART_REQUIRED


def test_a19_only_an_explicit_confirmation_reaches_ready(service, bridge):
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))
    service.activate(plan, assets)

    assert service.confirm_client_manually().ok
    assert service.snapshot().state is InstallState.READY


def test_a_manual_confirmation_is_refused_before_any_registration(service, bridge):
    service.save_bridge(_candidate())

    outcome = service.confirm_client_manually()

    assert not outcome.ok
    assert service.snapshot().state is InstallState.CLIENT_REGISTRATION_PENDING


# -- A15: removal touches only what the assistant created -------------------------


def test_a15_removal_takes_back_only_the_managed_resources(service, bridge, client):
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))
    service.activate(plan, assets)

    outcome = service.disconnect()

    assert outcome.ok
    assert client.plugins == []
    assert service.journal().resources == []
    # Local data survives a plain disconnect.
    assert service.config_path.exists()


def test_a15_a_running_server_is_reported_rather_than_killed(service, bridge):
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))
    service.activate(plan, assets)

    outcome = service.disconnect()

    assert outcome.code in {Code.CLIENT_REMOVED, Code.CLIENT_RESTART_REQUIRED}


def test_a15_a_client_without_a_remove_command_asks_for_a_manual_step(service, bridge, client):
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))
    service.activate(plan, assets)
    client.capabilities.discard("remove")

    outcome = service.disconnect()

    assert not outcome.ok
    assert outcome.code is Code.CLIENT_ACTION_REQUIRED
    assert outcome.details["remaining"]


def test_erasing_local_data_is_opt_in(service, bridge, fake_keyring):
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))
    service.activate(plan, assets)

    service.disconnect(erase_local=False)
    assert service.config_path.exists()
    assert ("proton-safe-mcp", ACCOUNT) in fake_keyring.store

    service.disconnect(erase_local=True)
    assert not service.config_path.exists()
    assert ("proton-safe-mcp", ACCOUNT) not in fake_keyring.store


# -- A12: adversarial client output never leaks ------------------------------------


def test_a12_hostile_client_output_never_reaches_a_report_or_an_outcome(
    service, bridge, client, capsys
):
    leak = "\nBearer sk-secret-token victim@example.com /home/someone/private"
    client.hostile_output = leak
    service.save_bridge(_candidate())
    installation = _installation(service)
    plan, assets = service.plan_client(installation)
    outcome = service.activate(plan, assets)

    report = json.dumps(service.diagnostic_report())
    rendered = json.dumps(
        {"plan": [step.detail for step in plan.steps], "outcome": str(outcome.details)}
    )
    printed = capsys.readouterr()

    for blob in (report, rendered, printed.out, printed.err):
        assert "sk-secret-token" not in blob
        assert "victim@example.com" not in blob
        assert "/home/someone/private" not in blob


def test_the_diagnostic_report_carries_no_address_or_path(service, bridge):
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))
    service.activate(plan, assets)

    report = json.dumps(service.diagnostic_report())

    assert ACCOUNT not in report
    assert str(service.config_path) not in report
    assert str(service.plugin_dir) not in report
    assert GOOD_SECRET not in report


# -- unsupported client -----------------------------------------------------------


def test_an_unsupported_client_is_reported_instead_of_being_driven_blind(service, bridge, client):
    client.capabilities = {"plugin"}
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))

    outcome = service.activate(plan, assets)

    assert not outcome.ok
    assert outcome.code is Code.UNSUPPORTED_CLIENT
    assert outcome.manual_step_required
    # The local marketplace is still available for a guided manual install.
    assert assets.marketplace_dir.is_dir()
    assert client.marketplaces == []


def test_capabilities_come_from_the_client_not_from_its_version(service, client):
    client.capabilities = {"plugin", "marketplace", "add", "list"}
    installation = service.discover()[0]

    described = service.adapters[0].describe_capabilities(installation)

    assert "plugin.add" in described.capabilities
    assert "plugin.remove" not in described.capabilities
    assert described.version == "codex-cli 1.4.0"


@pytest.mark.posix_only
def test_two_paths_to_the_same_executable_are_reported_once(tmp_path, client, monkeypatch):
    executable = tmp_path / "codex"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o700)
    link = tmp_path / "codex-link"
    link.symlink_to(executable)
    monkeypatch.setattr("shutil.which", lambda _name: None)
    adapter = OpenAILocalAdapter(
        client.run, candidate_paths=(str(executable), str(link)), config_home=tmp_path
    )

    found = adapter.discover()

    assert len(found) == 1
    assert "ChatGPT desktop" in found[0].shared_surfaces
    assert "Codex CLI" in found[0].shared_surfaces


def test_a_removal_outcome_only_lists_what_it_actually_removed(service):
    installation = ClientInstallation(
        id="openai-local:0",
        adapter="openai-local",
        display_name="x",
        executable=service.config_path,
        version="1",
        capabilities=frozenset(),
    )
    outcome = service.adapters[0].remove(installation, [("plugin", "proton-safe@x")])

    assert isinstance(outcome, RegistrationOutcome)
    assert outcome.created == ()
    assert outcome.details["remaining"] == ["proton-safe@x"]


# -- A18: the plugin and the runtime move together --------------------------------


def test_a18_the_rendered_plugin_records_its_provenance(service, bridge):
    service.save_bridge(_candidate())
    assets = service.render_plugin()

    provenance = plugin_assets.read_provenance(service.plugin_dir)

    assert provenance["resource_digest"] == assets.resource_digest
    assert provenance["plugin_version"] == assets.plugin_version
    assert plugin_assets.is_current(service.plugin_dir)


def test_a18_a_changed_engine_version_invalidates_the_rendered_plugin(service, bridge, monkeypatch):
    service.save_bridge(_candidate())
    service.render_plugin()
    monkeypatch.setattr(plugin_assets, "__version__", "99.0.0")

    assert not plugin_assets.is_current(service.plugin_dir)


def test_a18_an_outdated_plugin_puts_the_installation_into_repair(service, bridge, monkeypatch):
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))
    service.activate(plan, assets)
    service.confirm_client_manually()
    assert service.snapshot().state is InstallState.READY

    monkeypatch.setattr(plugin_assets, "__version__", "99.0.0")

    snapshot = service.snapshot()
    assert snapshot.state is InstallState.REPAIR_REQUIRED
    assert "PLUGIN_OUTDATED" in snapshot.notes


def test_the_plugin_version_changes_with_the_resources(service, bridge, monkeypatch):
    service.save_bridge(_candidate())
    first = service.render_plugin().plugin_version
    monkeypatch.setattr(plugin_assets, "resource_digest", lambda _root: "f" * 64)
    second = service.render_plugin().plugin_version

    assert first != second


def test_rendering_replaces_a_stale_skill_left_by_an_earlier_version(service, bridge):
    service.save_bridge(_candidate())
    assets = service.render_plugin()
    stale = assets.plugin_dir / "skills" / "removed-skill" / "SKILL.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("outdated", encoding="utf-8")

    service.render_plugin()

    assert not stale.exists()


def test_the_managed_plugin_keeps_the_three_canonical_skills(service, bridge):
    service.save_bridge(_candidate())
    assets = service.render_plugin()

    names = sorted(path.parent.name for path in (assets.plugin_dir / "skills").glob("*/SKILL.md"))
    assert names == list(plugin_assets.CANONICAL_SKILLS)

    manifest = json.loads((assets.plugin_dir / ".codex-plugin" / "plugin.json").read_text())
    assert manifest["skills"] == "./skills/"
    assert manifest["mcpServers"] == "./.mcp.json"


def test_the_managed_server_needs_neither_uvx_nor_proton_variables(service, bridge):
    service.save_bridge(_candidate())
    assets = service.render_plugin()
    config = json.loads((assets.plugin_dir / ".mcp.json").read_text(encoding="utf-8"))
    server = config["mcpServers"]["proton-safe"]

    assert server["command"].endswith("proton-safe-mcp")
    assert server["command"].startswith("/")
    assert server["args"][:2] == ["serve", "--config"]
    assert "uvx" not in json.dumps(config)
    assert not [name for name in server["env_vars"] if name.startswith("PROTON_")]


def test_a_relative_runtime_path_is_refused(service):
    with pytest.raises(plugin_assets.PluginAssetError):
        plugin_assets.render(
            serve_command=("proton-safe-mcp", "serve"), destination=service.plugin_dir
        )


# -- state is rebuilt from reality, never trusted from the journal ----------------


def test_a_journal_claiming_ready_does_not_survive_a_missing_credential(
    service, bridge, fake_keyring
):
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))
    service.activate(plan, assets)
    service.confirm_client_manually()
    assert service.snapshot().state is InstallState.READY

    fake_keyring.store.clear()

    snapshot = service.snapshot()
    assert snapshot.state is InstallState.REPAIR_REQUIRED
    assert str(Code.CREDENTIAL_MISSING) in snapshot.notes


def test_a_missing_configuration_with_recorded_resources_asks_for_a_repair(service, bridge):
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))
    service.activate(plan, assets)
    service.config_path.unlink()

    assert service.snapshot().state is InstallState.REPAIR_REQUIRED


def test_a_fresh_computer_reports_a_new_installation(service):
    assert service.snapshot().state is InstallState.NEW
    assert service.snapshot().account_masked == ""


def test_verification_without_a_configuration_skips_instead_of_guessing(service):
    checks = {check.id: check for check in service.verify()}

    assert checks["bridge"].status == "fail"
    assert checks["runtime"].status == "skip"
    assert checks["client"].status == "skip"


def test_a_plan_step_carries_no_private_value(service, bridge):
    service.save_bridge(_candidate())
    plan, _assets = service.plan_client(_installation(service))

    for step in plan.steps:
        assert ACCOUNT not in step.detail
        assert GOOD_SECRET not in step.detail
    assert plan.steps == (
        PlanStep("add", "plan.marketplace", "proton-safe-desktop"),
        PlanStep("add", "plan.plugin", "proton-safe@proton-safe-desktop"),
    )


def test_an_installation_can_be_described_without_running_anything(service):
    installation = _installation(service)
    frozen = replace(installation, capabilities=frozenset({"plugin"}))

    assert not service.adapters[0].supports_automatic_install(frozen)


# -- the recorded verification is history, never a live claim ---------------------


def test_a_verification_records_when_it_ran_and_what_each_level_said(service, bridge, monkeypatch):
    from proton_safe_mcp.onboarding.models import Outcome

    service.save_bridge(_candidate())
    monkeypatch.setattr(
        SetupService, "check_runtime", lambda _self: Outcome.success(Code.RUNTIME_READY)
    )

    service.verify()
    snapshot = service.snapshot()

    assert snapshot.last_verified_at.endswith("+00:00")
    assert snapshot.last_checks["bridge"] == "pass:BRIDGE_AUTHENTICATED"
    assert snapshot.last_checks["runtime"] == "pass:RUNTIME_READY"
    assert snapshot.last_checks["client"].startswith("action_required:")


def test_a_recorded_pass_does_not_survive_a_bridge_that_stopped_answering(
    service, bridge, monkeypatch
):
    from proton_safe_mcp.onboarding.models import Outcome

    service.save_bridge(_candidate())
    monkeypatch.setattr(
        SetupService, "check_runtime", lambda _self: Outcome.success(Code.RUNTIME_READY)
    )
    service.verify()
    assert service.snapshot().last_checks["bridge"] == "pass:BRIDGE_AUTHENTICATED"

    def refuse(self, *, password=None):
        raise BridgeError("bridge is down", code="BRIDGE_UNREACHABLE")

    monkeypatch.setattr(FakeBridge, "probe", refuse)
    checks = {check.id: check for check in service.verify()}

    assert checks["bridge"].code is Code.BRIDGE_UNREACHABLE
    assert service.snapshot().last_checks["bridge"] == "fail:BRIDGE_UNREACHABLE"


def test_the_recorded_verification_holds_no_address_or_secret(service, bridge):
    service.save_bridge(_candidate())
    service.verify()

    recorded = service.journal_path.read_text(encoding="utf-8")

    assert ACCOUNT not in recorded
    assert GOOD_SECRET not in recorded


# -- a failed removal must not destroy what a retry needs -------------------------


def _fresh_service(service):
    """A new SetupService on the same paths, as reopening the application would."""
    return SetupService(
        config_path=service.config_path,
        journal_path=service.journal_path,
        plugin_dir=service.plugin_dir,
        adapters=service.adapters,
        runtime=service.runtime,
    )


def test_a_partial_removal_keeps_the_journal_a_retry_needs(service, bridge, client, fake_keyring):
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))
    service.activate(plan, assets)
    client.capabilities.discard("remove")

    outcome = service.disconnect(erase_local=True)

    assert not outcome.ok
    assert outcome.code is Code.CLIENT_ACTION_REQUIRED
    assert outcome.details["remaining"]
    # The erase is deferred, not performed: the journal is the only record of what is
    # still registered in the client and of which installation owns it.
    assert service.journal_path.exists()
    assert service.config_path.exists()
    assert ("proton-safe-mcp", ACCOUNT) in fake_keyring.store
    recorded = service.journal()
    assert recorded.erase_local_requested is True
    assert [item.name for item in recorded.resources]


def test_a_failed_removal_then_reopen_then_a_successful_retry(
    service, bridge, client, fake_keyring
):
    """Partial failure, close, reopen, retry: the whole recovery path."""
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))
    service.activate(plan, assets)
    registered = list(client.plugins)
    assert registered == [assets.plugin_reference]

    # The client cannot remove anything yet.
    client.capabilities.discard("remove")
    first = service.disconnect(erase_local=True)
    assert not first.ok
    assert client.plugins == registered

    # The application is closed and reopened: only the journal survives in memory-free
    # form, and it must still name what has to be taken back.
    reopened = _fresh_service(service)
    snapshot = reopened.snapshot()
    assert snapshot.state is InstallState.REPAIR_REQUIRED
    assert [item.name for item in reopened.journal().resources] == [
        assets.marketplace_name,
        assets.plugin_reference,
    ]
    assert reopened.journal().erase_local_requested is True

    # The user fixes their client, then retries.
    client.capabilities.add("remove")
    second = reopened.disconnect()

    assert second.ok
    assert client.plugins == []
    assert client.marketplaces == []
    # The deferred erase is honoured now that the entries are actually gone.
    assert not reopened.config_path.exists()
    assert ("proton-safe-mcp", ACCOUNT) not in fake_keyring.store
    assert not reopened.journal_path.exists()


def test_a_retry_without_asking_again_still_honours_the_earlier_erase_request(
    service, bridge, client, fake_keyring
):
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))
    service.activate(plan, assets)
    client.capabilities.discard("remove")
    service.disconnect(erase_local=True)

    client.capabilities.add("remove")
    # The second call does not repeat erase_local; the recorded intent carries it.
    outcome = _fresh_service(service).disconnect()

    assert outcome.ok
    assert not service.config_path.exists()
    assert ("proton-safe-mcp", ACCOUNT) not in fake_keyring.store


def test_a_partial_removal_without_an_erase_request_keeps_everything_too(
    service, bridge, client, fake_keyring
):
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))
    service.activate(plan, assets)
    client.capabilities.discard("remove")

    outcome = service.disconnect(erase_local=False)

    assert not outcome.ok
    assert service.journal_path.exists()
    assert service.config_path.exists()
    assert service.journal().erase_local_requested is False
    assert ("proton-safe-mcp", ACCOUNT) in fake_keyring.store


def test_a_clean_removal_without_an_erase_request_keeps_the_local_data(
    service, bridge, client, fake_keyring
):
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))
    service.activate(plan, assets)

    outcome = service.disconnect(erase_local=False)

    assert outcome.ok
    assert service.config_path.exists()
    assert ("proton-safe-mcp", ACCOUNT) in fake_keyring.store
    assert service.journal().resources == []


def test_a_client_chosen_by_hand_is_found_again_after_reopening_and_can_be_disconnected(
    tmp_path, client, codex_home, bridge, fake_keyring, make_executable, monkeypatch
):
    """The full path for an installation none of the bounded probes reach.

    Choose it, activate, close and reopen, verify, disconnect. Discovery never produces
    this installation — that is the whole point of choosing it — so a resumed session
    that looked it up by discovery identifier alone would find nothing, report that the
    client needed attention, and remove none of the entries it had created.
    """
    elsewhere = make_executable(tmp_path / "opt" / "vendor" / "tools", "codex")
    # Nothing probes there, and nothing on the PATH answers either.
    adapter = OpenAILocalAdapter(client.run, candidate_paths=(), config_home=codex_home)
    monkeypatch.setattr("shutil.which", lambda _name: None)
    config_dir = tmp_path / "config" / "proton-safe-mcp"
    config_dir.mkdir(mode=0o700, parents=True)
    runtime_path = make_executable(tmp_path / "runtime", "proton-safe-mcp")

    from proton_safe_mcp.onboarding.runtime import RuntimeLocation

    service = SetupService(
        config_path=config_dir / "config.toml",
        journal_path=tmp_path / "state" / "install.json",
        plugin_dir=tmp_path / "plugin",
        adapters=(adapter,),
        runtime=RuntimeLocation((str(runtime_path),), packaged=True),
    )
    assert service.discover() == [], "this installation is deliberately undiscoverable"

    chosen = service.inspect_client(elsewhere)
    assert chosen is not None
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(chosen)
    service.activate(plan, assets)
    service.confirm_client_manually()

    recorded = service.journal()
    assert recorded.client_executable == str(elsewhere)
    assert recorded.client_profile == str(codex_home)

    reopened = _fresh_service(service)
    assert reopened.snapshot().state is InstallState.READY

    outcome = reopened.disconnect()

    assert outcome.ok, "the client chosen by hand must be reachable again to disconnect"
    assert client.plugins == [] and client.marketplaces == []
    assert reopened.journal().resources == []


def test_a_recorded_client_whose_executable_is_gone_reports_nothing_rather_than_stale(
    service, bridge, client, tmp_path
):
    """Being recorded is not being trusted: the path is re-inspected, not assumed."""
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))
    service.activate(plan, assets)

    recorded = service.journal()
    recorded.client_executable = str(tmp_path / "removed" / "codex")
    recorded.client_id = "openai-local:chosen"
    service._save_journal(recorded)

    reopened = _fresh_service(service)

    assert reopened._recorded_installation(reopened.journal()) is None


def test_an_outstanding_disconnect_is_visible_after_reopening(service, bridge, client):
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))
    service.activate(plan, assets)
    service.confirm_client_manually()
    assert service.snapshot().state is InstallState.READY

    client.capabilities.discard("remove")
    service.disconnect()

    reopened = _fresh_service(service)
    snapshot = reopened.snapshot()
    assert snapshot.state is InstallState.REPAIR_REQUIRED
    assert str(Code.CLIENT_ACTION_REQUIRED) in snapshot.notes


def test_registering_again_withdraws_an_outstanding_disconnect(service, bridge, client):
    service.save_bridge(_candidate())
    plan, assets = service.plan_client(_installation(service))
    service.activate(plan, assets)
    client.capabilities.discard("remove")
    service.disconnect(erase_local=True)
    assert service.journal().disconnect_pending is True

    client.capabilities.add("remove")
    reopened = _fresh_service(service)
    new_plan, new_assets = reopened.plan_client(_installation(reopened))
    reopened.activate(new_plan, new_assets)

    recorded = reopened.journal()
    assert recorded.disconnect_pending is False
    # A withdrawn disconnect must not erase the local data later on.
    assert recorded.erase_local_requested is False
    assert reopened.snapshot().state is InstallState.CLIENT_VERIFICATION_PENDING
