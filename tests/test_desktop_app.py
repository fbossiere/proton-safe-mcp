"""Interface checks: accessibility, keyboard reach, honest wording, and no leaks.

These run against the real widgets on Qt's offscreen platform, so they exercise the
screens rather than asserting on source text. They skip when Qt is absent, which is the
supported state for a PyPI install of the server.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# exc_type=ImportError, not the ModuleNotFoundError pytest defaults to: Qt can be
# installed and still fail to load because a system library such as libEGL is absent.
# Both are supported states for a server-only installation, so both must skip rather
# than break collection.
_QT = "the desktop assistant needs PySide6 and its Qt system libraries"
QtCore = pytest.importorskip("PySide6.QtCore", reason=_QT, exc_type=ImportError)
QtWidgets = pytest.importorskip("PySide6.QtWidgets", reason=_QT, exc_type=ImportError)

from proton_safe_mcp.desktop.app import MainWindow  # noqa: E402
from proton_safe_mcp.desktop.widgets import (  # noqa: E402
    STATUS_MARKS,
    CheckRow,
    Disclosure,
    SecretField,
)
from proton_safe_mcp.onboarding.messages import OFFICIAL_LINKS, translate  # noqa: E402
from proton_safe_mcp.onboarding.models import Check, Code, InstallState  # noqa: E402
from proton_safe_mcp.onboarding.service import SetupService, Snapshot  # noqa: E402

INTERACTIVE = (
    QtWidgets.QPushButton,
    QtWidgets.QToolButton,
    QtWidgets.QLineEdit,
    QtWidgets.QSpinBox,
    QtWidgets.QCheckBox,
    QtWidgets.QListWidget,
)


@pytest.fixture(scope="session")
def application():
    existing = QtWidgets.QApplication.instance()
    yield existing or QtWidgets.QApplication([])


@pytest.fixture
def service(tmp_path, monkeypatch, fake_keyring):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    directory = tmp_path / "config" / "proton-safe-mcp"
    directory.mkdir(mode=0o700, parents=True)
    return SetupService(
        config_path=directory / "config.toml",
        journal_path=tmp_path / "state" / "install.json",
        plugin_dir=tmp_path / "plugin",
        adapters=(),
    )


@pytest.fixture
def window(application, service):
    built = MainWindow(service, language="fr")
    yield built
    built.runner.cancel()
    built.runner.wait(10_000)
    built.deleteLater()


def _settle(window, application):
    """Wait out every task, including ones a completed task starts in its handler."""
    for _ in range(8):
        window.runner.wait(20_000)
        for _ in range(3):
            application.processEvents()
        if not window.runner.busy:
            break


def test_a_fresh_computer_opens_on_the_welcome_screen(window, application):
    window.start()
    _settle(window, application)

    assert window.stack.currentWidget() is window.screens["welcome"]
    assert translate("app.title", "fr") in window.windowTitle()


def test_an_existing_installation_opens_on_the_dashboard(
    window, application, service, write_managed_config
):
    write_managed_config(service.config_path)
    window.start()
    _settle(window, application)

    assert window.stack.currentWidget() is window.screens["dashboard"]


@pytest.mark.parametrize("language", ["fr", "en"])
def test_the_window_fits_a_1280_by_720_screen_at_200_percent_scaling(
    application, tmp_path, language
):
    service = RecordingService(tmp_path)
    window = MainWindow(service, language=language)
    window.selected_client = service.installation
    # Leave room for the window decoration: 640x330 logical pixels on 1280x720 at 2x.
    window.resize(640, 330)
    window.show()
    try:
        for name, screen in window.screens.items():
            window.show_screen(name)
            _settle(window, application)
            assert window.width() == 640
            assert window.height() == 330
            scroll = screen.content_scroll
            assert scroll.horizontalScrollBar().maximum() == 0
            assert scroll.viewport().height() > 100
            for value in (0, scroll.verticalScrollBar().maximum()):
                scroll.verticalScrollBar().setValue(value)
                application.processEvents()
                for button in (screen.back, screen.primary):
                    if button.isVisible():
                        position = button.mapTo(window, QtCore.QPoint(0, 0))
                        assert window.rect().contains(QtCore.QRect(position, button.size()))
    finally:
        window.close()
        window.deleteLater()


def test_every_interactive_control_can_be_reached_with_the_keyboard(window):
    unreachable = [
        f"{name}:{type(child).__name__}"
        for name, screen in window.screens.items()
        for child in screen.findChildren(QtWidgets.QWidget)
        if isinstance(child, INTERACTIVE) and child.focusPolicy() == QtCore.Qt.FocusPolicy.NoFocus
    ]

    assert unreachable == []


def test_every_interactive_control_has_an_accessible_name(window):
    unnamed = [
        f"{name}:{type(child).__name__}"
        for name, screen in window.screens.items()
        for child in screen.findChildren(QtWidgets.QWidget)
        if isinstance(child, INTERACTIVE)
        and not (child.accessibleName() or getattr(child, "text", lambda: "")())
    ]

    assert unnamed == []


def test_a_status_is_never_carried_by_colour_alone():
    row = CheckRow("Trousseau", language="fr")
    row.show_check(Check("keyring", "fail", Code.KEYRING_LOCKED))

    description = row.accessibleDescription()
    marks = row.findChildren(QtWidgets.QLabel)
    assert translate("status.fail", "fr") in description
    assert "verrouillé" in description
    assert marks[0].text() == STATUS_MARKS["fail"]
    # Distinct statuses produce distinct text and a distinct mark, not just a colour.
    row.show_check(Check("keyring", "pass", Code.KEYRING_AVAILABLE))
    assert translate("status.pass", "fr") in row.accessibleDescription()
    assert marks[0].text() == STATUS_MARKS["pass"]
    assert STATUS_MARKS["pass"] != STATUS_MARKS["fail"]


def test_the_secret_field_is_masked_and_only_reveals_on_an_explicit_action(application):
    field = SecretField("fr")
    field.field().setText("candidate")

    assert field.field().echoMode() == QtWidgets.QLineEdit.EchoMode.Password
    reveal = field.findChild(QtWidgets.QToolButton)
    reveal.setChecked(True)
    assert field.field().echoMode() == QtWidgets.QLineEdit.EchoMode.Normal
    reveal.setChecked(False)
    assert field.field().echoMode() == QtWidgets.QLineEdit.EchoMode.Password


def test_taking_the_secret_clears_the_widget(application):
    field = SecretField("fr")
    field.field().setText("candidate")

    assert field.take() == "candidate"
    assert field.field().text() == ""
    assert not field.has_value
    assert field.take() is None


def test_pasting_into_the_secret_field_is_allowed(application):
    field = SecretField("fr")

    assert not field.field().isReadOnly()
    assert field.field().maxLength() >= 64


def test_returning_to_the_bridge_screen_preserves_the_non_secret_fields(
    window, application, service
):
    window.show_screen("bridge")
    screen = window.screens["bridge"]
    screen.user.setText("typed@example.com")
    screen.port.setValue(1188)
    window.show_screen("client")
    _settle(window, application)
    window.go_back()

    assert screen.user.text() == "typed@example.com"
    assert screen.port.value() == 1188


def test_technical_details_are_collapsed_by_default(window):
    boxes = window.findChildren(Disclosure)
    assert len(boxes) == 4
    for box in boxes:
        assert not box.isChecked()
        assert box.content.isHidden()


def test_a_pending_client_step_is_never_reported_as_finished(window, application, monkeypatch):
    monkeypatch.setattr(
        SetupService,
        "verify",
        lambda _self: [
            Check("bridge", "pass", Code.BRIDGE_AUTHENTICATED),
            Check("runtime", "pass", Code.RUNTIME_READY),
            Check("client", "action_required", Code.CLIENT_RESTART_REQUIRED),
        ],
    )
    window.show_screen("verify")
    _settle(window, application)
    screen = window.screens["verify"]

    assert "vérification" in screen.status.text().lower()
    assert "terminé" not in screen.status.text().lower()
    assert translate("status.action_required", "fr") in (
        screen.rows["client"].accessibleDescription()
    )


def test_the_verification_screen_offers_a_copyable_prompt_that_reads_nothing(window):
    screen = window.screens["verify"]
    text = screen.prompt.toPlainText()

    assert "sans lire mes messages" in text
    assert "brouillon" in text
    assert screen.prompt.isReadOnly()


def test_the_dashboard_shows_a_masked_account(window, application, monkeypatch):
    monkeypatch.setattr(
        SetupService,
        "snapshot",
        lambda _self: Snapshot(
            state=InstallState.READY,
            account_masked="p•••••@example.com",
            configuration_present=True,
        ),
    )
    window.show_screen("dashboard")
    _settle(window, application)

    assert window.screens["dashboard"].account.text() == "p•••••@example.com"


def test_the_browser_only_ever_opens_a_fixed_official_link(window, monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(
        "proton_safe_mcp.desktop.app.QtGui.QDesktopServices.openUrl",
        lambda url: opened.append(url.toString()),
    )

    window.open_official("bridge")
    window.open_official("not-a-known-key")

    assert opened == [OFFICIAL_LINKS["bridge"]]
    assert all(url.startswith("https://") for url in opened)


def test_a_failed_operation_shows_a_translated_code_not_a_raw_message(
    window, application, monkeypatch
):
    monkeypatch.setattr(
        SetupService,
        "prerequisites",
        lambda _self: (_ for _ in ()).throw(
            __import__("proton_safe_mcp.errors", fromlist=["ProtonMCPError"]).ProtonMCPError(
                "/home/someone/private path and a secret", code=str(Code.KEYRING_LOCKED)
            )
        ),
    )
    window.show_screen("prerequisites")
    _settle(window, application)
    text = window.screens["prerequisites"].status.text()

    assert "/home/someone/private" not in text
    assert "verrouillé" in text


def test_cancelling_a_running_operation_reports_it_as_cancelled(window, application):
    import threading

    release = threading.Event()

    def slow(token):
        release.wait(5)
        token.checkpoint()
        return None

    screen = window.screens["bridge"]
    window.run(slow, lambda _r: None, screen._failed)
    window.cancel_current()
    release.set()
    _settle(window, application)

    assert screen.status.text() == translate("common.cancelled", "fr")


def test_the_runner_refuses_to_start_a_second_task_while_one_runs(window, application):
    import threading

    release = threading.Event()
    started = threading.Event()

    def slow(_token):
        started.set()
        release.wait(5)
        return None

    assert window.runner.start(slow)
    started.wait(5)
    assert not window.runner.start(lambda _token: None)
    release.set()
    _settle(window, application)


def test_the_interface_imports_no_bridge_or_keyring_module_of_its_own():
    """Screens must go through the service, never talk to Bridge or the keyring directly."""
    import proton_safe_mcp.desktop.app as module

    source = module.__dict__
    assert "ProtonBridgeClient" not in source
    assert "keyring" not in source
    assert "store_bridge_password" not in source


# -- the wizard, driven end to end against a fake service --------------------------


class RecordingService:
    """A service double that records what the screens asked it to do."""

    def __init__(self, tmp_path):
        from proton_safe_mcp.onboarding.models import (
            ClientInstallation,
            PlanStep,
            RegistrationOutcome,
            RegistrationPlan,
        )
        from proton_safe_mcp.onboarding.plugin_assets import ManagedPluginAssets

        self.config_path = tmp_path / "config.toml"
        self.plugin_dir = tmp_path / "plugin"
        self.saved: list[object] = []
        self.activated: list[object] = []
        self.confirmed = 0
        self.disconnected: list[bool] = []
        self.installation = ClientInstallation(
            id="fake:0",
            adapter="fake",
            display_name="ChatGPT desktop / Codex",
            executable=tmp_path / "codex",
            version="codex-cli 1.4.0",
            capabilities=frozenset({"plugin"}),
            shared_surfaces=("ChatGPT desktop", "Codex CLI"),
        )
        self.assets = ManagedPluginAssets(
            marketplace_dir=tmp_path / "plugin",
            plugin_dir=tmp_path / "plugin" / "plugins" / "proton-safe",
            marketplace_name="proton-safe-desktop",
            plugin_name="proton-safe",
            plugin_version="0.1.0+codex.test",
            engine_version="test",
            resource_digest="d" * 64,
        )
        self.plan = RegistrationPlan(
            installation=self.installation,
            steps=(PlanStep("add", "plan.plugin", "proton-safe@proton-safe-desktop"),),
        )
        self._outcome = RegistrationOutcome(ok=True, code=Code.CLIENT_REGISTERED)

    def prerequisites(self):
        return [
            Check("system", "pass", Code.SYSTEM_SUPPORTED, "Ubuntu 24.04"),
            Check("session", "pass", Code.SESSION_OK, "Wayland"),
            Check("keyring", "pass", Code.KEYRING_AVAILABLE),
            Check("bridge", "pass", Code.BRIDGE_APP_DETECTED),
            Check("client", "pass", Code.CLIENT_DETECTED, "codex-cli 1.4.0"),
        ]

    def discover(self):
        return [self.installation]

    def stored_configuration(self):
        return None

    def snapshot(self):
        return Snapshot(state=InstallState.NEW)

    def save_bridge(self, candidate, *, cancel=None):
        from proton_safe_mcp.onboarding.models import Outcome

        self.saved.append(candidate)
        return Outcome.success(Code.CONFIG_SAVED)

    def plan_client(self, installation):
        return self.plan, self.assets

    def activate(self, plan, assets, *, migrate=False):
        self.activated.append((plan, assets, migrate))
        return self._outcome

    def verify(self):
        return [
            Check("bridge", "pass", Code.BRIDGE_AUTHENTICATED),
            Check("runtime", "pass", Code.RUNTIME_READY),
            Check("client", "action_required", Code.CLIENT_RESTART_REQUIRED),
        ]

    def confirm_client_manually(self):
        from proton_safe_mcp.onboarding.models import Outcome

        self.confirmed += 1
        return Outcome.success(Code.CLIENT_VERIFIED_MANUALLY)

    def disconnect(self, *, erase_local=False):
        from proton_safe_mcp.onboarding.models import Outcome

        self.disconnected.append(erase_local)
        return Outcome.success(Code.CLIENT_REMOVED)

    def diagnostic_report(self):
        return {"schema_version": 1, "overall": "ok", "checks": []}


@pytest.fixture
def wizard(application, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "proton_safe_mcp.desktop.app.MainWindow.service_has_secret", lambda _self, _user: False
    )
    service = RecordingService(tmp_path)
    window = MainWindow(service, language="fr")
    yield window, service
    window.runner.cancel()
    window.runner.wait(10_000)
    window.deleteLater()


def test_the_whole_wizard_reaches_verification_without_touching_mail(wizard, application):
    window, service = wizard
    window.start()
    _settle(window, application)
    assert window.stack.currentWidget() is window.screens["welcome"]

    window.screens["welcome"].primary.click()
    _settle(window, application)
    assert window.screens["prerequisites"].primary.isEnabled()

    window.screens["prerequisites"].primary.click()
    _settle(window, application)
    bridge = window.screens["bridge"]
    bridge.user.setText("person@example.com")
    bridge.port.setValue(1143)
    bridge.secret.field().setText("bridge-generated")
    bridge.primary.click()
    _settle(window, application)

    assert len(service.saved) == 1
    candidate = service.saved[0]
    assert candidate.user == "person@example.com"
    # The screen hands the secret over once and keeps nothing.
    assert bridge.secret.field().text() == ""

    assert window.stack.currentWidget() is window.screens["client"]
    assert window.screens["client"].primary.isEnabled()
    window.screens["client"].primary.click()
    _settle(window, application)

    activate = window.screens["activate"]
    assert activate.primary.isEnabled()
    assert "ChatGPT desktop / Codex" in activate.primary.accessibleName()
    assert "ChatGPT desktop / Codex" in activate.summary.text()
    activate.primary.click()
    _settle(window, application)

    assert len(service.activated) == 1
    # Nothing to take over, so no migration was authorised.
    assert service.activated[0][2] is False
    assert window.stack.currentWidget() is window.screens["verify"]
    # Registered is not ready: the client step is still outstanding.
    assert "vérification" in window.screens["verify"].status.text().lower()


def test_confirming_manually_is_an_explicit_user_action(wizard, application):
    window, service = wizard
    window.show_screen("verify")
    _settle(window, application)
    assert service.confirmed == 0

    window.screens["verify"].confirm.click()
    _settle(window, application)

    assert service.confirmed == 1


def test_a_conflicting_plan_blocks_activation(wizard, application, monkeypatch):
    from dataclasses import replace as dataclass_replace

    window, service = wizard
    service.plan = dataclass_replace(service.plan, conflicts=("proton-safe",))
    window.selected_client = service.installation
    window.show_screen("activate")
    _settle(window, application)

    assert not window.screens["activate"].primary.isEnabled()
    assert "existe déjà" in window.screens["activate"].status.text()
    assert service.activated == []


def test_the_diagnostic_is_previewed_before_it_is_copied(wizard, application):
    window, _service = wizard
    window.show_screen("dashboard")
    _settle(window, application)

    window.screens["dashboard"].copy_diagnostic.click()
    _settle(window, application)

    details = window.screens["dashboard"].diagnostic
    assert details.isChecked()
    assert '"schema_version": 1' in details._text.toPlainText()


def test_disconnecting_requires_a_confirmation_and_honours_the_erase_choice(
    wizard, application, monkeypatch
):
    window, service = wizard
    window.show_screen("dashboard")
    _settle(window, application)
    dashboard = window.screens["dashboard"]

    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        classmethod(lambda _cls, *_a, **_k: QtWidgets.QMessageBox.StandardButton.No),
    )
    dashboard.disconnect_button.click()
    _settle(window, application)
    assert service.disconnected == []

    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        classmethod(lambda _cls, *_a, **_k: QtWidgets.QMessageBox.StandardButton.Yes),
    )
    assert not dashboard.erase.isChecked()
    dashboard.disconnect_button.click()
    _settle(window, application)

    assert service.disconnected == [False]


def test_an_unsupported_client_outcome_is_explained_not_hidden(wizard, application):
    from proton_safe_mcp.onboarding.models import RegistrationOutcome

    window, service = wizard
    service._outcome = RegistrationOutcome(
        ok=False, code=Code.UNSUPPORTED_CLIENT, manual_step_required=True
    )
    window.selected_client = service.installation
    window.show_screen("activate")
    _settle(window, application)
    window.screens["activate"].primary.click()
    _settle(window, application)

    status = window.screens["activate"].status.text()
    assert "ne permet pas cette installation" in status
    assert window.stack.currentWidget() is window.screens["activate"]


# -- the status table and the two copyable prompts ---------------------------------


def test_the_status_table_lists_the_three_levels_and_when_they_were_checked(
    wizard, application, monkeypatch
):
    window, _service = wizard
    monkeypatch.setattr(
        type(window.service),
        "snapshot",
        lambda _self: Snapshot(
            state=InstallState.CLIENT_VERIFICATION_PENDING,
            account_masked="p•••••@example.com",
            configuration_present=True,
            last_verified_at="2026-09-13T09:30:00+00:00",
            last_checks={
                "bridge": "pass:BRIDGE_AUTHENTICATED",
                "runtime": "pass:RUNTIME_READY",
                "client": "action_required:CLIENT_RESTART_REQUIRED",
            },
        ),
        raising=False,
    )
    window.show_screen("dashboard")
    _settle(window, application)
    dashboard = window.screens["dashboard"]

    assert dashboard.account.text() == "p•••••@example.com"
    assert translate("status.pass", "fr") in dashboard.levels["bridge"].text()
    assert translate("status.pass", "fr") in dashboard.levels["runtime"].text()
    assert translate("status.action_required", "fr") in dashboard.levels["client"].text()
    assert dashboard.last_check.text() == "2026-09-13T09:30:00+00:00"
    # A pending client step is never dressed up as finished.
    assert translate("status.action_required", "fr") in dashboard.status.text()


def test_a_never_checked_installation_says_so_rather_than_showing_a_stale_state(
    wizard, application
):
    window, _service = wizard
    window.show_screen("dashboard")
    _settle(window, application)
    dashboard = window.screens["dashboard"]

    assert dashboard.last_check.text() == translate("dashboard.never", "fr")
    assert all(label.text() == "—" for label in dashboard.levels.values())


def test_both_prompts_are_offered_and_neither_is_sent_automatically(window):
    screen = window.screens["verify"]

    check = screen.prompt.toPlainText()
    first_use = screen.first_use_prompt.toPlainText()

    assert "sans lire mes messages" in check
    assert "résume les points encore ouverts" in first_use
    assert screen.prompt.isReadOnly() and screen.first_use_prompt.isReadOnly()
    # The first-use text is framed as a choice, not as a technical step.
    labels = [
        label.text()
        for label in screen.findChildren(QtWidgets.QLabel)
        if "première utilisation" in label.text()
    ]
    assert labels


def test_copying_a_prompt_puts_exactly_that_text_on_the_clipboard(window, application):
    screen = window.screens["verify"]
    buttons = [
        child
        for child in screen.findChildren(QtWidgets.QPushButton)
        if child.text() == translate("verify.copy", "fr")
    ]
    assert len(buttons) == 2

    buttons[1].click()
    application.processEvents()

    assert QtWidgets.QApplication.clipboard().text() == screen.first_use_prompt.toPlainText()


# -- the take-over choice on the activation screen ---------------------------------


def _plan_with_migration(service):
    from dataclasses import replace as dataclass_replace

    from proton_safe_mcp.onboarding.models import PlanStep

    return dataclass_replace(
        service.plan,
        migrations=(PlanStep("remove", "plugin", "proton-safe@personal"),),
    )


def test_a_take_over_is_offered_but_never_preselected(wizard, application):
    window, service = wizard
    service.plan = _plan_with_migration(service)
    window.selected_client = service.installation
    window.show_screen("activate")
    _settle(window, application)
    screen = window.screens["activate"]

    assert screen.migrate.isVisible() or screen.migrate.isVisibleTo(screen)
    assert not screen.migrate.isChecked()
    # The action stays out of reach until the user authorises the take-over.
    assert not screen.primary.isEnabled()
    assert "installée autrement" in screen.status.text()
    assert "proton-safe@personal" in screen.migrate.accessibleName()
    assert "proton-safe@personal" in screen.migrate_notice.text()
    assert service.activated == []


def test_ticking_the_take_over_enables_the_action_and_passes_the_choice_on(wizard, application):
    window, service = wizard
    service.plan = _plan_with_migration(service)
    window.selected_client = service.installation
    window.show_screen("activate")
    _settle(window, application)
    screen = window.screens["activate"]

    screen.migrate.setChecked(True)
    assert screen.primary.isEnabled()
    screen.primary.click()
    _settle(window, application)

    assert len(service.activated) == 1
    assert service.activated[0][2] is True
    assert window.stack.currentWidget() is window.screens["verify"]


def test_the_take_over_explains_what_is_kept(wizard, application):
    window, service = wizard
    service.plan = _plan_with_migration(service)
    window.selected_client = service.installation
    window.show_screen("activate")
    _settle(window, application)
    screen = window.screens["activate"]

    notice = screen.migrate_notice.text()
    assert "identifiant Bridge sont conservés" in notice
    assert "autres plugins ne sont pas touchés" in notice


def test_an_unresolvable_conflict_still_blocks_even_with_a_take_over_offered(wizard, application):
    from dataclasses import replace as dataclass_replace

    window, service = wizard
    service.plan = dataclass_replace(_plan_with_migration(service), conflicts=("my-proton",))
    window.selected_client = service.installation
    window.show_screen("activate")
    _settle(window, application)
    screen = window.screens["activate"]

    screen.migrate.setChecked(True)

    assert not screen.primary.isEnabled()
    assert "existe déjà" in screen.status.text()


def test_a_refused_take_over_leaves_the_screen_resumable(wizard, application):
    from proton_safe_mcp.onboarding.models import RegistrationOutcome

    window, service = wizard
    service.plan = _plan_with_migration(service)
    service._outcome = RegistrationOutcome(ok=False, code=Code.MIGRATION_MANUAL)
    window.selected_client = service.installation
    window.show_screen("activate")
    _settle(window, application)
    screen = window.screens["activate"]
    screen.migrate.setChecked(True)
    screen.primary.click()
    _settle(window, application)

    assert window.stack.currentWidget() is window.screens["activate"]
    assert "retirée dans votre assistant" in screen.status.text()
    # The choice and the action are still there, so the user can retry after fixing it.
    assert screen.migrate.isChecked()
    assert screen.primary.isEnabled()


def test_no_take_over_choice_is_shown_when_there_is_nothing_to_take_over(wizard, application):
    window, service = wizard
    window.selected_client = service.installation
    window.show_screen("activate")
    _settle(window, application)
    screen = window.screens["activate"]

    assert not screen.migrate.isVisibleTo(screen)
    assert screen.primary.isEnabled()


def test_advanced_fields_expand_by_keyboard_and_survive_back(wizard, application):
    from PySide6 import QtTest

    window, _service = wizard
    window.show_screen("bridge")
    window.show()
    screen = window.screens["bridge"]
    assert not screen.port.isVisible()
    screen.advanced.toggle.setFocus()
    QtTest.QTest.keyClick(screen.advanced.toggle, QtCore.Qt.Key.Key_Space)
    assert screen.port.isVisible()
    screen.port.setValue(1188)
    screen.aliases.setText("alias@example.com")
    screen.advanced.setChecked(False)
    window.show_screen("client")
    _settle(window, application)
    window.go_back()
    assert not screen.advanced.isChecked()
    candidate = screen.candidate()
    assert candidate.imap_port == 1188
    assert candidate.aliases == ("alias@example.com",)
    assert candidate.password is None
    window.close()


def test_bridge_fields_stay_inside_the_small_viewport(wizard, application):
    window, _service = wizard
    window.resize(640, 330)
    window.show_screen("bridge")
    window.show()
    screen = window.screens["bridge"]
    screen.advanced.setChecked(True)
    application.processEvents()
    for field in (screen.user, screen.secret.field(), screen.port, screen.aliases):
        field.setFocus()
        screen.content_scroll.ensureWidgetVisible(field)
        application.processEvents()
        viewport = screen.content_scroll.viewport()
        position = field.mapTo(viewport, QtCore.QPoint(0, 0))
        assert viewport.rect().contains(QtCore.QRect(position, field.size()))
    window.close()


def test_progress_follows_back_navigation(wizard, application):
    window, _service = wizard
    window.show_screen("bridge")
    window.show_screen("client")
    _settle(window, application)
    assert window.step_label.text() == "Étape 4 sur 6"
    window.go_back()
    assert window.step_label.text() == "Étape 3 sur 6"
    assert [segment.property("reached") for segment in window.segments] == [
        True,
        True,
        True,
        False,
        False,
        False,
    ]


@pytest.mark.parametrize("width", [640, 900])
def test_long_diagnostic_text_grows_instead_of_being_cropped(wizard, application, width):
    window, service = wizard
    window.resize(width, 700)
    window.show()
    window.show_screen("prerequisites")
    _settle(window, application)
    screen = window.screens["prerequisites"]
    checks = service.prerequisites()
    checks[2] = Check("keyring", "fail", Code.KEYRING_LOCKED)
    screen._show(checks)
    for _ in range(10):
        application.processEvents()
    row = screen.rows["keyring"]
    detail = row._detail
    assert detail.height() >= detail.heightForWidth(detail.width())
    assert row.rect().contains(detail.geometry())
    # A second resize must recalculate the wrapping, including when growing wider.
    window.resize(900 if width == 640 else 640, 700)
    for _ in range(10):
        application.processEvents()
    assert detail.height() >= detail.heightForWidth(detail.width())
    assert row.rect().contains(detail.geometry())
    window.close()
