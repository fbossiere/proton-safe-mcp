"""The setup assistant window.

Screens are thin: every decision belongs to ``onboarding.service``, which is why the whole
flow can be tested without a display. Nothing here talks to Bridge, the keyring or the
client directly, and no screen ever shows raw command output.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from .. import __version__
from ..onboarding.messages import OFFICIAL_LINKS, detect_language, explain, translate
from ..onboarding.models import Check, ClientInstallation, Code, InstallState
from ..onboarding.service import BridgeCandidate, SetupService, Snapshot
from ..platform_services import services
from .single_instance import SingleInstanceGuard, signal_existing_instance
from .theme import app_icon, apply_theme
from .widgets import (
    CheckRow,
    DetailsBox,
    Disclosure,
    FormScrollArea,
    SecretField,
    WrappedLabel,
    status_text,
)
from .workers import TaskRunner

WINDOW_MINIMUM = QtCore.QSize(560, 300)
STEPS = ("welcome", "prerequisites", "bridge", "client", "activate", "verify")


def _heading(text: str) -> QtWidgets.QLabel:
    label = WrappedLabel(text)
    label.setObjectName("heading")
    label.setWordWrap(True)
    # Headings are announced as headings rather than as decorative text.
    label.setAccessibleName(text)
    return label


def _body(text: str) -> QtWidgets.QLabel:
    label = WrappedLabel(text)
    label.setWordWrap(True)
    label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


class Screen(QtWidgets.QWidget):
    """A step with a heading, a body and a consistent button row."""

    def __init__(self, window: MainWindow, title_key: str) -> None:
        super().__init__(window)
        self.window_ref = window
        self.language = window.language
        self.setObjectName("screen")
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.content_scroll = FormScrollArea()
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        page = QtWidgets.QWidget()
        page.setObjectName("page")
        centered = QtWidgets.QHBoxLayout(page)
        centered.setContentsMargins(24, 12, 24, 20)
        content = QtWidgets.QWidget()
        content.setMaximumWidth(740)
        column = QtWidgets.QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(18)
        column.addWidget(_heading(translate(title_key, self.language)))
        self.body = QtWidgets.QVBoxLayout()
        self.body.setSpacing(12)
        column.addLayout(self.body)
        column.addStretch(1)
        centered.addWidget(content)
        self.content_scroll.setWidget(page)
        outer.addWidget(self.content_scroll, 1)

        self.status = _body("")
        self.status.setAccessibleName(translate("common.working", self.language))
        self.status.setObjectName("feedback")
        self.status.setVisible(False)
        column.insertWidget(1, self.status)

        footer = QtWidgets.QWidget()
        footer.setObjectName("footer")
        buttons = QtWidgets.QHBoxLayout(footer)
        buttons.setContentsMargins(24, 14, 24, 14)
        self.back = QtWidgets.QPushButton(translate("common.back", self.language))
        self.cancel = QtWidgets.QPushButton(translate("common.cancel", self.language))
        self.primary = QtWidgets.QPushButton(translate("common.continue", self.language))
        self.primary.setObjectName("primary")
        self.primary.setDefault(True)
        self.cancel.setVisible(False)
        buttons.addWidget(self.back)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel)
        buttons.addWidget(self.primary)
        outer.addWidget(footer)

        self.back.clicked.connect(window.go_back)
        self.cancel.clicked.connect(window.cancel_current)

    def set_status(self, text: str) -> None:
        self.status.setText(text)
        self.status.setVisible(bool(text))
        if text:
            QtCore.QTimer.singleShot(
                0, lambda: self.content_scroll.ensureWidgetVisible(self.status)
            )

    def show_code(self, code: str) -> None:
        message, action = explain(code, self.language)
        self.set_status(f"{message} {action}".strip())

    def on_enter(self) -> None:
        """Refresh when the screen becomes visible. Fields are preserved across Back."""


class WelcomeScreen(Screen):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(window, "app.title")
        self.back.setVisible(False)
        self.body.addWidget(_body(translate("welcome.intro", self.language)))
        for number, key in enumerate(("find", "summarise", "draft"), 1):
            card = QtWidgets.QWidget()
            card.setObjectName("checkRow")
            row = QtWidgets.QHBoxLayout(card)
            row.setContentsMargins(16, 12, 16, 12)
            mark = _body(f"{number:02}")
            mark.setObjectName("muted")
            mark.setFixedWidth(36)
            row.addWidget(mark)
            text = _body(translate(f"welcome.feature.{key}", self.language))
            text.setObjectName("fieldLabel")
            row.addWidget(text, 1)
            self.body.addWidget(card)
        note = _body(
            "\n".join(
                translate(key, self.language)
                for key in ("welcome.point.bridge", "welcome.point.local", "welcome.point.cloud")
            )
        )
        note.setObjectName("note")
        self.body.addWidget(note)
        independent = _body(translate("app.independent", self.language))
        independent.setObjectName("muted")
        self.body.addWidget(independent)
        self.primary.setText(translate("welcome.start", self.language))
        self.primary.clicked.connect(lambda: window.show_screen("prerequisites"))


class PrerequisitesScreen(Screen):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(window, "prereq.title")
        self.body.addWidget(_body(translate("prereq.intro", self.language)))
        self.rows: dict[str, CheckRow] = {}
        for check_id, key in (
            ("system", "prereq.system"),
            ("session", "prereq.session"),
            ("keyring", "prereq.keyring"),
            ("bridge", "prereq.bridge"),
            ("client", "prereq.client"),
        ):
            row = CheckRow(translate(key, self.language), language=self.language)
            self.rows[check_id] = row
            self.body.addWidget(row)

        links = QtWidgets.QVBoxLayout()
        self.bridge_link = QtWidgets.QPushButton(translate("prereq.bridge_help", self.language))
        self.bridge_link.setAccessibleName("proton.me/mail/bridge")
        self.bridge_link.clicked.connect(lambda: window.open_official("bridge"))
        self.recheck = QtWidgets.QPushButton(translate("prereq.recheck", self.language))
        self.recheck.clicked.connect(self.refresh)
        links.addWidget(self.bridge_link)
        links.addWidget(self.recheck)
        self.body.addLayout(links)

        self.primary.clicked.connect(lambda: window.show_screen("bridge"))
        self.primary.setEnabled(False)

    def on_enter(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.set_status(translate("common.working", self.language))
        self.window_ref.run(
            lambda _token: self.window_ref.service.prerequisites(), self._show, self._on_error
        )

    def _show(self, checks: Sequence[Check]) -> None:
        blocking = 0
        for check in checks:
            row = self.rows.get(check.id)
            if row is not None:
                row.show_check(check)
            if check.blocking:
                blocking += 1
        self.window_ref.client_checks = list(checks)
        self.primary.setEnabled(blocking == 0)
        self.set_status("" if blocking == 0 else translate("status.action_required", self.language))

    def _on_error(self, code: str) -> None:
        self.show_code(code)


class BridgeScreen(Screen):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(window, "bridge.title")
        self.body.addWidget(_body(translate("bridge.guide", self.language)))
        form = QtWidgets.QVBoxLayout()
        form.setSpacing(9)
        self.user = QtWidgets.QLineEdit()
        self.user.setAccessibleName(translate("bridge.user", self.language))
        self.user.setMaxLength(320)
        self.user.setPlaceholderText("name@proton.me")
        self.port = QtWidgets.QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(1143)
        self.port.setAccessibleName(translate("bridge.port", self.language))
        self.aliases = QtWidgets.QLineEdit()
        self.aliases.setAccessibleName(translate("bridge.aliases", self.language))
        self.secret = SecretField(self.language)

        for key, field in (("bridge.user", self.user), ("bridge.password", self.secret)):
            label = _body(translate(key, self.language))
            label.setObjectName("fieldLabel")
            label.setBuddy(field.field() if isinstance(field, SecretField) else field)
            form.addWidget(label)
            form.addWidget(field)
        self.body.addLayout(form)
        help_text = _body(translate("bridge.password.help", self.language))
        help_text.setObjectName("muted")
        self.body.addWidget(help_text)

        self.advanced = Disclosure(translate("bridge.advanced", self.language))
        extra = QtWidgets.QVBoxLayout(self.advanced.content)
        extra.setContentsMargins(0, 0, 0, 0)
        extra.setSpacing(9)
        self.port.setMaximumWidth(160)
        for key, extra_field in (("bridge.port", self.port), ("bridge.aliases", self.aliases)):
            label = _body(translate(key, self.language))
            label.setBuddy(extra_field)
            extra.addWidget(label)
            extra.addWidget(extra_field)
        extra.addWidget(_body(translate("bridge.host_fixed", self.language)))
        self.body.addWidget(self.advanced)

        self.existing = _body(translate("bridge.existing", self.language))
        self.existing.setVisible(False)
        self.body.addWidget(self.existing)
        self.change = QtWidgets.QPushButton(translate("bridge.change", self.language))
        self.change.setVisible(False)
        self.change.clicked.connect(self._enable_replacement)
        self.body.addWidget(self.change)

        self.primary.setText(translate("bridge.save", self.language))
        self.primary.clicked.connect(self.save)

    def on_enter(self) -> None:
        stored = self.window_ref.service.stored_configuration()
        if stored is not None and not self.user.text():
            # Coming back keeps what the user typed; a fresh visit pre-fills from disk.
            self.user.setText(stored.bridge_user)
            self.port.setValue(stored.imap_port)
            self.aliases.setText(", ".join(stored.aliases))
        has_secret = stored is not None and self.window_ref.service_has_secret(stored.bridge_user)
        self.existing.setVisible(bool(has_secret))
        self.change.setVisible(bool(has_secret))
        self.secret.setVisible(not has_secret)
        self.primary.setText(
            translate("bridge.test", self.language)
            if has_secret
            else translate("bridge.save", self.language)
        )

    def _enable_replacement(self) -> None:
        self.secret.setVisible(True)
        self.secret.field().setFocus()
        self.primary.setText(translate("bridge.save", self.language))

    def candidate(self) -> BridgeCandidate:
        aliases = tuple(item for item in self.aliases.text().split(",") if item.strip())
        # The field is always emptied here, whatever the screen is showing: tying that to
        # widget visibility would leave a typed secret in the widget on a hidden window.
        # An empty field means "reuse the stored credential", which the service resolves.
        return BridgeCandidate(
            user=self.user.text().strip(),
            imap_port=self.port.value(),
            aliases=aliases,
            password=self.secret.take(),
        )

    def save(self) -> None:
        candidate = self.candidate()
        self.set_status(translate("common.working", self.language))
        self.cancel.setVisible(True)

        def work(token: Any) -> Any:
            try:
                return self.window_ref.service.save_bridge(candidate, cancel=token)
            finally:
                # The secret lives no longer than this one operation.
                candidate.password = None

        self.window_ref.run(work, self._saved, self._failed)

    def _saved(self, outcome: Any) -> None:
        self.cancel.setVisible(False)
        if not outcome.ok:
            self.show_code(str(outcome.code))
            return
        self.set_status("")
        self.window_ref.show_screen("client")

    def _failed(self, code: str) -> None:
        self.cancel.setVisible(False)
        if code == str(Code.CANCELLED):
            self.set_status(translate("common.cancelled", self.language))
            return
        self.show_code(code)


class ClientScreen(Screen):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(window, "client.title")
        self.body.addWidget(_body(translate("client.intro", self.language)))
        self.list = QtWidgets.QListWidget()
        self.list.setMaximumHeight(190)
        self.list.setAccessibleName(translate("client.title", self.language))
        self.body.addWidget(self.list)
        self.details = DetailsBox(self.language)
        self.body.addWidget(self.details)
        # A client installed somewhere this version does not probe is still reachable,
        # without asking anyone to type a command. What is chosen is then verified the
        # same way a discovered installation is.
        actions = QtWidgets.QHBoxLayout()
        self.locate = QtWidgets.QPushButton(translate("client.locate", self.language))
        self.locate.setAccessibleName(translate("client.locate", self.language))
        self.locate.clicked.connect(self._locate)
        actions.addWidget(self.locate)
        actions.addStretch(1)
        self.body.addLayout(actions)
        self.list.currentRowChanged.connect(self._show_details)
        self.primary.clicked.connect(self._choose)
        self.installations: list[ClientInstallation] = []

    def on_enter(self) -> None:
        # Disabled until the list actually arrives, so the button never looks ready
        # while there is nothing to choose.
        self.primary.setEnabled(False)
        self.set_status(translate("common.working", self.language))
        self.window_ref.run(
            lambda _token: self.window_ref.service.discover(), self._show, self.show_code
        )

    def _locate(self) -> None:
        """Ask for the client's own executable and verify it before offering it."""
        chosen, _filter = QtWidgets.QFileDialog.getOpenFileName(
            self, translate("client.locate", self.language)
        )
        if not chosen:
            return
        self.set_status(translate("common.working", self.language))
        self.window_ref.run(
            lambda _token: self.window_ref.service.inspect_client(Path(chosen)),
            self._located,
            self.show_code,
        )

    def _located(self, installation: ClientInstallation | None) -> None:
        if installation is None:
            self.set_status(translate("client.locate_failed", self.language))
            return
        existing = [item.executable for item in self.installations]
        if installation.executable not in existing:
            self.installations.append(installation)
        self._render()
        self.list.setCurrentRow(len(self.installations) - 1)

    def _surface_note(self, installation: ClientInstallation) -> str:
        """Say which other surfaces one registration covers, only when that is known."""
        if not installation.shared_surfaces:
            return translate("client.shared_unknown", self.language)
        return translate(
            "client.shared", self.language, surfaces=", ".join(installation.shared_surfaces)
        )

    def _show(self, installations: Sequence[ClientInstallation]) -> None:
        self.installations = list(installations)
        self._render()

    def _render(self) -> None:
        self.list.clear()
        for installation in self.installations:
            item = QtWidgets.QListWidgetItem(
                f"{installation.display_name} — {installation.version}"
            )
            item.setToolTip(self._surface_note(installation))
            self.list.addItem(item)
        if self.installations:
            self.list.setCurrentRow(0)
        self.list.setFixedHeight(min(190, max(80, len(self.installations) * 60 + 20)))
        self.primary.setEnabled(bool(self.installations))
        self.set_status(
            "" if self.installations else explain(str(Code.CLIENT_NOT_FOUND), self.language)[0]
        )

    def _show_details(self, row: int) -> None:
        if 0 <= row < len(self.installations):
            installation = self.installations[row]
            self.details.set_text(
                f"{installation.executable}\n{installation.version}\n"
                + self._surface_note(installation)
            )

    def _choose(self) -> None:
        row = self.list.currentRow()
        if 0 <= row < len(self.installations):
            self.window_ref.selected_client = self.installations[row]
            self.window_ref.show_screen("activate")


class ActivateScreen(Screen):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(window, "activate.title")
        self.summary = _body("")
        self.summary.setObjectName("note")
        self.body.addWidget(self.summary)
        self.body.addWidget(_body(translate("activate.uses", self.language)))
        limits = _body(translate("activate.limits", self.language))
        limits.setObjectName("muted")
        self.body.addWidget(limits)
        # The take-over choice: hidden unless an earlier Proton Safe installation was
        # found, unticked by default, and the only thing that authorises replacing it.
        self.migrate_notice = _body("")
        self.migrate_notice.setObjectName("note")
        self.migrate_notice.setVisible(False)
        self.body.addWidget(self.migrate_notice)
        self.migrate = QtWidgets.QCheckBox(translate("activate.migrate.label", self.language))
        # Named at construction: a control must be announced even before a plan fills in
        # which entry it would take over.
        self.migrate.setAccessibleName(translate("activate.migrate.label", self.language))
        self.migrate.setVisible(False)
        self.migrate.setChecked(False)
        self.migrate.toggled.connect(self._refresh_primary)
        self.body.addWidget(self.migrate)

        self.plan_details = DetailsBox(self.language)
        self.body.addWidget(self.plan_details)
        self.primary.clicked.connect(self._activate)
        self._plan: Any = None
        self._assets: Any = None

    def on_enter(self) -> None:
        installation = self.window_ref.selected_client
        if installation is None:
            self.window_ref.show_screen("client")
            return
        self.primary.setText(translate("activate.start", self.language))
        self.primary.setAccessibleName(
            translate("activate.button", self.language, client=installation.display_name)
        )
        snapshot = self.window_ref.service.snapshot()
        self.summary.setText(
            f"{installation.display_name}\n"
            f"{translate('dashboard.account', self.language)}: {snapshot.account_masked}"
        )
        self.set_status(translate("common.working", self.language))
        self.primary.setEnabled(False)
        self.migrate.setVisible(False)
        self.migrate_notice.setVisible(False)
        self.migrate.setChecked(False)
        self.window_ref.run(
            lambda _token: self.window_ref.service.plan_client(installation),
            self._show_plan,
            self.show_code,
        )

    def _show_plan(self, result: tuple[Any, Any]) -> None:
        self._plan, self._assets = result
        lines = [f"{step.action} {step.target} {step.detail}" for step in self._plan.steps]
        if self._plan.replaces:
            lines.append(
                translate(
                    "activate.replaces", self.language, entries=", ".join(self._plan.replaces)
                )
            )
        if self._plan.requires_migration:
            entries = ", ".join(step.detail for step in self._plan.migrations)
            lines += [
                f"{step.action} {step.target} {step.detail}" for step in self._plan.migrations
            ]
            label = translate("activate.migrate", self.language, entries=entries)
            self.migrate.setText(translate("activate.migrate.label", self.language))
            self.migrate.setAccessibleName(label)
            self.migrate.setVisible(True)
            self.migrate_notice.setText(
                label + "\n\n" + translate("activate.migrate.explain", self.language)
            )
            self.migrate_notice.setVisible(True)
        self.plan_details.set_text("\n".join(lines))
        if self._plan.has_conflicts:
            # Not something the assistant can take over on its own.
            self.show_code(str(Code.CONFIG_CONFLICT))
            self.primary.setEnabled(False)
            return
        self._refresh_primary()

    def _refresh_primary(self) -> None:
        """Enable the action only once any take-over has been explicitly authorised."""
        if self._plan is None or self._plan.has_conflicts:
            self.primary.setEnabled(False)
            return
        if self._plan.requires_migration and not self.migrate.isChecked():
            self.show_code(str(Code.MIGRATION_REQUIRED))
            self.primary.setEnabled(False)
            return
        self.set_status("")
        self.primary.setEnabled(True)

    def _activate(self) -> None:
        if self._plan is None or self._assets is None:
            return
        plan, assets = self._plan, self._assets
        migrate = self.migrate.isChecked()
        self.set_status(translate("common.working", self.language))
        self.primary.setEnabled(False)
        self.window_ref.run(
            lambda _token: self.window_ref.service.activate(plan, assets, migrate=migrate),
            self._activated,
            self.show_code,
        )

    def _activated(self, outcome: Any) -> None:
        self.primary.setEnabled(True)
        if not outcome.ok:
            # A refused take-over is resumable: the plan and the choice stay on screen.
            self.show_code(str(outcome.code))
            return
        self.window_ref.show_screen("verify")


class VerifyScreen(Screen):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(window, "verify.title")
        self.rows = {
            "bridge": CheckRow(translate("verify.bridge", self.language), language=self.language),
            "runtime": CheckRow(translate("verify.runtime", self.language), language=self.language),
            "client": CheckRow(translate("verify.client", self.language), language=self.language),
        }
        for row in self.rows.values():
            self.body.addWidget(row)

        # A prompt that checks the tools, and separately one for a deliberate first use.
        # Neither is ever sent into the client automatically.
        self.prompt = self._copyable("verify.prompt.check", window)
        self.body.addWidget(_body(translate("verify.first_use", self.language)))
        self.first_use_prompt = self._copyable("verify.prompt.first_use", window)

        self.confirm = QtWidgets.QPushButton(translate("verify.confirm", self.language))
        self.confirm.clicked.connect(self._confirm)
        self.body.addWidget(self.confirm)

        self.primary.setText(translate("verify.dashboard", self.language))
        self.primary.clicked.connect(lambda: window.show_screen("dashboard"))

    def _copyable(self, key: str, window: MainWindow) -> QtWidgets.QPlainTextEdit:
        text = translate(key, self.language)
        view = QtWidgets.QPlainTextEdit(text)
        view.setReadOnly(True)
        view.setMaximumHeight(70)
        view.setAccessibleName(text)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(view, 1)
        copy = QtWidgets.QPushButton(translate("verify.copy", self.language))
        copy.setAccessibleName(f"{translate('verify.copy', self.language)} — {text[:40]}")
        copy.clicked.connect(lambda: window.copy_text(view.toPlainText()))
        row.addWidget(copy)
        self.body.addLayout(row)
        return view

    def on_enter(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.set_status(translate("common.working", self.language))
        self.cancel.setVisible(True)
        self.window_ref.run(
            lambda _token: self.window_ref.service.verify(), self._show, self._failed
        )

    def _show(self, checks: Sequence[Check]) -> None:
        self.cancel.setVisible(False)
        for check in checks:
            row = self.rows.get(check.id)
            if row is not None:
                row.show_check(check)
        client = next((check for check in checks if check.id == "client"), None)
        installation = self.window_ref.selected_client
        name = installation.display_name if installation else translate("app.name", self.language)
        if client is not None and client.status != "pass":
            # Never "done" while the client step is still outstanding.
            self.set_status(translate("verify.client.pending", self.language, client=name))
        else:
            self.set_status("")

    def _failed(self, code: str) -> None:
        self.cancel.setVisible(False)
        self.show_code(code)

    def _confirm(self) -> None:
        self.window_ref.run(
            lambda _token: self.window_ref.service.confirm_client_manually(),
            lambda _outcome: self.refresh(),
            self.show_code,
        )


class DashboardScreen(Screen):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(window, "dashboard.title")
        self.back.setVisible(False)
        self.table = QtWidgets.QFormLayout()
        self.table.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        self.table.setVerticalSpacing(12)
        self.account = _body("")
        self.version = _body(__version__)
        self.levels = {
            "bridge": _body(""),
            "runtime": _body(""),
            "client": _body(""),
        }
        self.last_check = _body("")
        self.table.addRow(translate("dashboard.account", self.language), self.account)
        self.table.addRow(translate("dashboard.version", self.language), self.version)
        for level, key in (
            ("bridge", "verify.bridge"),
            ("runtime", "verify.runtime"),
            ("client", "verify.client"),
        ):
            self.table.addRow(translate(key, self.language), self.levels[level])
        self.table.addRow(translate("dashboard.last_check", self.language), self.last_check)
        self.body.addLayout(self.table)

        actions = QtWidgets.QGridLayout()
        self.check = QtWidgets.QPushButton(translate("dashboard.check", self.language))
        self.repair = QtWidgets.QPushButton(translate("dashboard.repair", self.language))
        self.edit = QtWidgets.QPushButton(translate("dashboard.edit", self.language))
        self.copy_diagnostic = QtWidgets.QPushButton(
            translate("dashboard.copy_diagnostic", self.language)
        )
        # Not named `disconnect`: that would shadow QObject.disconnect on this widget.
        self.disconnect_button = QtWidgets.QPushButton(
            translate("dashboard.disconnect", self.language)
        )
        self.erase = QtWidgets.QCheckBox(translate("dashboard.erase.short", self.language))
        self.erase.setAccessibleName(translate("dashboard.erase", self.language))
        self.erase.setChecked(False)
        for index, widget in enumerate(
            (self.check, self.repair, self.edit, self.copy_diagnostic, self.disconnect_button)
        ):
            actions.addWidget(widget, index, 0)
        actions.addWidget(self.erase, 5, 0)
        self.body.addLayout(actions)

        self.diagnostic = DetailsBox(self.language)
        self.body.addWidget(self.diagnostic)

        self.check.clicked.connect(lambda: window.show_screen("verify"))
        self.repair.clicked.connect(lambda: window.show_screen("prerequisites"))
        self.edit.clicked.connect(lambda: window.show_screen("bridge"))
        self.copy_diagnostic.clicked.connect(self._copy_diagnostic)
        self.disconnect_button.clicked.connect(self._disconnect)
        self.primary.setText(translate("common.close", self.language))
        self.primary.clicked.connect(window.close)

    def on_enter(self) -> None:
        self.window_ref.run(
            lambda _token: self.window_ref.service.snapshot(), self._show, self.show_code
        )

    def _show(self, snapshot: Snapshot) -> None:
        self.account.setText(snapshot.account_masked or "—")
        # These are the levels as they stood at the last check, not a live claim.
        for level, label in self.levels.items():
            recorded = snapshot.last_checks.get(level, "")
            status, _, code = recorded.partition(":")
            if not status:
                label.setText("—")
                continue
            message, _action = explain(code, self.language)
            label.setText(f"{status_text(status, self.language)} — {message}")
        self.last_check.setText(
            snapshot.last_verified_at or translate("dashboard.never", self.language)
        )
        if snapshot.state is InstallState.READY:
            self.set_status("")
        else:
            self.set_status(status_text("action_required", self.language))

    def _copy_diagnostic(self) -> None:
        self.window_ref.run(
            lambda _token: self.window_ref.service.diagnostic_report(),
            self._show_diagnostic,
            self.show_code,
        )

    def _show_diagnostic(self, report: dict[str, Any]) -> None:
        import json

        text = json.dumps(report, indent=2, sort_keys=True)
        # Previewed before it leaves the application; the user copies it deliberately.
        self.diagnostic.set_text(text)
        self.diagnostic.setChecked(True)
        self.window_ref.copy_text(text)

    def _disconnect(self) -> None:
        confirmed = QtWidgets.QMessageBox.question(
            self,
            translate("dashboard.disconnect", self.language),
            translate("dashboard.disconnect.consequences", self.language),
        )
        if confirmed is not QtWidgets.QMessageBox.StandardButton.Yes:
            return
        erase = self.erase.isChecked()
        self.window_ref.run(
            lambda _token: self.window_ref.service.disconnect(erase_local=erase),
            self._disconnected,
            self.show_code,
        )

    def _disconnected(self, outcome: Any) -> None:
        self.show_code(str(outcome.code))
        self.on_enter()


class MainWindow(QtWidgets.QMainWindow):
    """Holds the service, the screens and the single background runner."""

    def __init__(self, service: SetupService | None = None, language: str | None = None) -> None:
        super().__init__()
        self.language = language or detect_language()
        self.service = service or SetupService()
        self.selected_client: ClientInstallation | None = None
        self.client_checks: list[Check] = []
        self._history: list[str] = []
        self._connections: list[QtCore.QMetaObject.Connection] = []

        self.setWindowTitle(translate("app.title", self.language))
        self.setMinimumSize(WINDOW_MINIMUM)
        self.resize(900, 700)
        self.setWindowIcon(app_icon())
        apply_theme(self)

        self.runner = TaskRunner(self)
        self.stack = QtWidgets.QStackedWidget()
        shell = QtWidgets.QWidget()
        shell.setObjectName("shell")
        layout = QtWidgets.QVBoxLayout(shell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QtWidgets.QWidget()
        header_layout = QtWidgets.QVBoxLayout(header)
        header_layout.setContentsMargins(24, 18, 24, 16)
        header_layout.setSpacing(12)
        brand_row = QtWidgets.QHBoxLayout()
        logo = QtWidgets.QLabel()
        logo.setPixmap(self.windowIcon().pixmap(36, 36))
        brand_row.addWidget(logo)
        brand = _body(translate("app.name", self.language))
        brand.setObjectName("brand")
        brand_row.addWidget(brand)
        brand_row.addStretch(1)
        self.step_label = _body("")
        self.step_label.setObjectName("eyebrow")
        brand_row.addWidget(self.step_label)
        header_layout.addLayout(brand_row)
        progress = QtWidgets.QHBoxLayout()
        progress.setSpacing(6)
        self.segments: list[QtWidgets.QFrame] = []
        for _ in STEPS:
            segment = QtWidgets.QFrame()
            segment.setObjectName("segment")
            segment.setFixedHeight(4)
            progress.addWidget(segment)
            self.segments.append(segment)
        header_layout.addLayout(progress)
        layout.addWidget(header)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(shell)

        self.screens: dict[str, Screen] = {
            "welcome": WelcomeScreen(self),
            "prerequisites": PrerequisitesScreen(self),
            "bridge": BridgeScreen(self),
            "client": ClientScreen(self),
            "activate": ActivateScreen(self),
            "verify": VerifyScreen(self),
            "dashboard": DashboardScreen(self),
        }
        for screen in self.screens.values():
            self.stack.addWidget(screen)
        self.runner.busy_changed.connect(self._on_busy)
        self.stack.currentChanged.connect(self._update_progress)
        self._update_progress()

    def _update_progress(self) -> None:
        name = self._name_of(self.stack.currentWidget())
        index = STEPS.index(name) if name in STEPS else len(STEPS) - 1
        self.step_label.setText(
            translate("progress.step", self.language, current=str(index + 1), total=str(len(STEPS)))
            if name != "dashboard"
            else translate("progress.dashboard", self.language)
        )
        for position, segment in enumerate(self.segments):
            segment.setProperty("reached", position <= index)
            segment.setVisible(name != "dashboard")
            segment.style().unpolish(segment)
            segment.style().polish(segment)

    def start(self) -> None:
        """Open on the dashboard when an installation already exists."""
        snapshot = self.service.snapshot()
        self.show_screen("dashboard" if snapshot.configuration_present else "welcome")

    # -- navigation --------------------------------------------------------------

    def show_screen(self, name: str) -> None:
        screen = self.screens[name]
        current = self.stack.currentWidget()
        if isinstance(current, Screen) and current is not screen:
            self._history.append(self._name_of(current))
        self.stack.setCurrentWidget(screen)
        screen.on_enter()
        screen.primary.setFocus()

    def _name_of(self, screen: QtWidgets.QWidget | None) -> str:
        for name, candidate in self.screens.items():
            if candidate is screen:
                return name
        return "welcome"

    def go_back(self) -> None:
        if not self._history:
            return
        name = self._history.pop()
        screen = self.screens[name]
        self.stack.setCurrentWidget(screen)
        screen.on_enter()

    # -- background work ---------------------------------------------------------

    def run(
        self,
        work: Any,
        on_done: Any,
        on_failed: Any,
    ) -> None:
        """Run one service call off the interface thread."""
        # Only this call's own handlers are disconnected, so nothing else loses its slots.
        for connection in self._connections:
            QtCore.QObject.disconnect(connection)
        self._connections = [
            self.runner.done.connect(on_done),
            self.runner.failed.connect(on_failed),
        ]
        self.runner.start(work)

    def cancel_current(self) -> None:
        self.runner.cancel()

    def _on_busy(self, busy: bool) -> None:
        if busy:
            QtWidgets.QApplication.setOverrideCursor(
                QtGui.QCursor(QtCore.Qt.CursorShape.BusyCursor)
            )
        else:
            QtWidgets.QApplication.restoreOverrideCursor()

    # -- helpers -----------------------------------------------------------------

    def service_has_secret(self, user: str) -> bool:
        from ..secrets import has_bridge_password

        return has_bridge_password(user)

    def copy_text(self, text: str) -> None:
        clipboard = QtWidgets.QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)

    def open_official(self, key: str) -> None:
        """Open one of the fixed official links, and nothing else."""
        url = OFFICIAL_LINKS.get(key)
        if url:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))

    def present(self) -> None:
        """Bring this window back to the front, from wherever it was left.

        Called when someone opens Proton Safe a second time. A half-finished setup keeps
        its fields and its place in the flow; nothing restarts.
        """
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.runner.cancel()
        self.runner.wait(10_000)
        super().closeEvent(event)


def verify_bundle(config_path: Path) -> int:
    """Prove a packaged build carries everything it needs, without a display.

    Run by the packaging script: it renders the managed plugin from the embedded
    resources and starts the embedded runtime over MCP. A build that starts on a
    developer's machine is not evidence that these travelled with it.
    """
    import tempfile

    from ..secrets import approved_backend_available

    if not approved_backend_available():
        print("this build does not carry a usable credential store backend", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as workspace:
        service = SetupService(config_path=config_path, plugin_dir=Path(workspace) / "plugin")
        if service.runtime is None:
            print("the MCP runtime is missing from this build", file=sys.stderr)
            return 1
        assets = service.render_plugin()
        missing = [
            name
            for name in ("extract-proton-attachment", "prepare-proton-draft", "review-proton-mail")
            if not (assets.plugin_dir / "skills" / name / "SKILL.md").is_file()
        ]
        if missing:
            print(f"plugin skills missing from this build: {missing}", file=sys.stderr)
            return 1
        outcome = service.check_runtime()
        if not outcome.ok:
            print(f"the embedded runtime did not start: {outcome.code}", file=sys.stderr)
            return 1
        print(
            "bundle verified: runtime "
            f"{outcome.details.get('tool_count')} tools, plugin {assets.plugin_version}"
        )
    return 0


def uninstall_connection(*, erase_local: bool) -> int:
    """Remove this installation's client entries, without opening a window.

    The Windows uninstaller calls this before it deletes the program files, in the
    user's own session. The assistant owns the journal, the client adapters and the
    credential store, so the uninstaller never edits a client configuration or touches
    Credential Manager itself: it asks the component that knows what Proton Safe
    created, and only that is removed.

    Exit codes are stable, because an installer reads them rather than text:

    ``0`` the managed entries are gone — a client restart may still be needed before it
    stops offering the tools; ``1`` entries remain, so the settings, the password and
    the journal are kept and a requested erase is deferred until a retry succeeds.
    """
    from ..onboarding.journal import default_journal_path

    service = SetupService()
    journal_path = service.journal_path or default_journal_path()
    if not service.config_path.exists() and not journal_path.exists():
        # This account never set anything up. There is nothing to disconnect, and an
        # uninstall must not create state on its way out.
        print(translate("uninstall.nothing_to_remove", detect_language()))
        return 0

    outcome = service.disconnect(erase_local=erase_local)
    message, action = explain(str(outcome.code), detect_language())
    stream = sys.stdout if outcome.ok else sys.stderr
    print(f"{message} {action}".strip(), file=stream)
    if outcome.ok and erase_local:
        # Say plainly what an erase does and does not reach. A secret already read into
        # a running server's memory is not revoked by deleting it from the store.
        print(translate("uninstall.erase_done", detect_language()), file=stream)
    return 0 if outcome.ok else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the desktop assistant."""
    arguments = list(argv) if argv is not None else sys.argv
    if "--verify-bundle" in arguments:
        # Packaging only. It touches no account state — a temporary directory, and the
        # embedded resources — so it is the one mode that runs wherever a build does,
        # including on a CI runner signed in as an administrator.
        index = arguments.index("--config")
        return verify_bundle(Path(arguments[index + 1]).resolve())

    platform = services()
    if platform.session_facts().elevated:
        # The setup writes into one account's own profile and registers a client for
        # that account. Elevated, it would set up an account nobody is signed in as.
        # Removal is the same account question in reverse: elevated, it would look for
        # the administrator's configuration, journal and credential, find none, and
        # report a connection as removed while it stayed exactly where it was.
        code = Code.SESSION_ELEVATED if platform.name == "windows" else Code.SESSION_ROOT
        message, action = explain(str(code), detect_language())
        print(f"{message} {action}", file=sys.stderr)
        return 1

    if "--uninstall-connection" in arguments:
        return uninstall_connection(erase_local="--erase-local" in arguments)

    # Two assistants would each hold their own view of one configuration, one journal
    # and one client. Asked to open a second time, bring back the first.
    if signal_existing_instance():
        return 0

    application = QtWidgets.QApplication(arguments)
    application.setApplicationName("Proton Safe")
    application.setApplicationVersion(__version__)
    application.setDesktopFileName("proton-safe-assistant")
    window = MainWindow()
    guard = SingleInstanceGuard(window.present)
    if not guard.listen():
        # Another launch took this account's slot between the check above and here.
        # Losing that race is not a reason to open a second window: ask the one that
        # won to come forward, exactly as the early check would have done.
        signal_existing_instance()
        return 0
    application.aboutToQuit.connect(guard.close)
    window.start()
    window.show()
    return int(application.exec())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
