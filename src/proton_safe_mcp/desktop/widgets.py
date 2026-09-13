"""Small accessible building blocks shared by the assistant's screens.

Status is always carried by text as well as by an icon, so it survives a colour-blind
reader, a monochrome theme and a screen reader.
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..onboarding.messages import explain, translate
from ..onboarding.models import Check

#: Text marks, never colour alone.
STATUS_MARKS = {
    "pass": "✓",
    "warn": "!",
    "action_required": "→",
    "fail": "✕",
    "skip": "·",
}


def status_text(status: str, language: str) -> str:
    return translate(f"status.{status}", language)


class CheckRow(QtWidgets.QWidget):
    """One prerequisite or verification line: mark, label, status word and action."""

    action_requested = QtCore.Signal(str)

    def __init__(
        self, label: str, *, language: str, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._language = language
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)

        self._mark = QtWidgets.QLabel("·")
        self._mark.setFixedWidth(24)
        self._mark.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self._label = QtWidgets.QLabel(label)
        self._label.setMinimumWidth(160)

        self._status = QtWidgets.QLabel("")
        self._status.setMinimumWidth(110)

        self._detail = QtWidgets.QLabel("")
        self._detail.setWordWrap(True)
        self._detail.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred
        )

        for widget in (self._mark, self._label, self._status, self._detail):
            layout.addWidget(widget)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(label)

    def show_check(self, check: Check) -> None:
        message, action = explain(str(check.code), self._language)
        self._mark.setText(STATUS_MARKS.get(check.status, "·"))
        self._status.setText(status_text(check.status, self._language))
        # Anything but a clean pass also shows what to do about it.
        parts = [message] if check.status == "pass" else [message, action]
        if check.hint:
            parts.append(f"({check.hint})")
        detail = " ".join(part for part in parts if part)
        self._detail.setText(detail)
        # Screen readers read the accessible description, not the colour.
        self.setAccessibleDescription(
            f"{self._label.text()}: {status_text(check.status, self._language)}. {detail}"
        )


class DetailsBox(QtWidgets.QGroupBox):
    """Technical details, collapsed by default and never required to finish the flow."""

    def __init__(self, language: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(translate("common.details", language), parent)
        self.setCheckable(True)
        self.setChecked(False)
        layout = QtWidgets.QVBoxLayout(self)
        self._text = QtWidgets.QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumHeight(160)
        self._text.setAccessibleName(translate("common.details", language))
        layout.addWidget(self._text)
        self._text.setVisible(False)
        self.toggled.connect(self._text.setVisible)

    def set_text(self, value: str) -> None:
        self._text.setPlainText(value)


class SecretField(QtWidgets.QWidget):
    """A masked field that allows pasting and reveals only on an explicit action.

    The value is handed to the service for one operation and cleared right after. Python
    cannot guarantee the string leaves memory, so the field simply does not keep it.
    """

    def __init__(self, language: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._edit = QtWidgets.QLineEdit()
        self._edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self._edit.setAccessibleName(translate("bridge.password", language))
        self._edit.setMaxLength(256)
        self._reveal = QtWidgets.QToolButton()
        self._reveal.setText(translate("bridge.reveal", language))
        self._reveal.setCheckable(True)
        self._reveal.setAccessibleName(translate("bridge.reveal", language))
        self._reveal.toggled.connect(self._on_reveal)
        layout.addWidget(self._edit)
        layout.addWidget(self._reveal)

    def _on_reveal(self, revealed: bool) -> None:
        self._edit.setEchoMode(
            QtWidgets.QLineEdit.EchoMode.Normal
            if revealed
            else QtWidgets.QLineEdit.EchoMode.Password
        )

    def take(self) -> str | None:
        """Return the typed secret once and clear the widget."""
        value = self._edit.text()
        self.clear()
        return value or None

    def clear(self) -> None:
        self._edit.clear()
        self._reveal.setChecked(False)
        self._edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)

    @property
    def has_value(self) -> bool:
        return bool(self._edit.text())

    def field(self) -> QtWidgets.QLineEdit:
        return self._edit
