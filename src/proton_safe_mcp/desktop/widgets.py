"""Small accessible building blocks shared by the assistant's screens.

Status is always carried by text as well as by an icon, so it survives a colour-blind
reader, a monochrome theme and a screen reader.
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

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


class FormScrollArea(QtWidgets.QScrollArea):
    """Bring the full focused field into view, including its border and padding."""

    def ensureWidgetVisible(
        self, childWidget: QtWidgets.QWidget, xmargin: int = 50, ymargin: int = 50
    ) -> None:
        super().ensureWidgetVisible(childWidget, xmargin, ymargin)
        page = self.widget()
        if page is None or not page.isAncestorOf(childWidget):
            return
        # QScrollArea can stop when only an input's cursor rectangle is visible.
        # Our padded fields need the full control visible, not just the text caret.
        viewport = self.viewport()
        bounds = QtCore.QRect(childWidget.mapTo(viewport, QtCore.QPoint()), childWidget.size())
        if bounds.height() > viewport.height():
            return
        padding = min(ymargin, (viewport.height() - bounds.height()) // 2)
        bar = self.verticalScrollBar()
        if bounds.top() < 0:
            bar.setValue(bar.value() + bounds.top() - padding)
        elif bounds.bottom() >= viewport.height():
            bar.setValue(bar.value() + bounds.bottom() - viewport.height() + 1 + padding)

    def focusNextPrevChild(self, next: bool) -> bool:
        moved = super().focusNextPrevChild(next)
        focused = self.focusWidget()
        if moved and focused is not None and focused.hasFocus():
            self.ensureWidgetVisible(focused)
        return moved


class WrappedLabel(QtWidgets.QLabel):
    """Keep changing, wrapped text fully visible inside a scrollable layout."""

    def __init__(self, text: str = "") -> None:
        super().__init__(text)
        self.setWordWrap(True)

    def setText(self, text: str) -> None:
        super().setText(text)
        self._fit_height()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit_height()

    def _fit_height(self) -> None:
        # Qt's default minimum size allows a wrapped label to shrink to a single line.
        # In a scroll area there is no reason to crop: let the page grow vertically.
        self.setMinimumHeight(max(0, self.heightForWidth(self.width())))


class CheckRow(QtWidgets.QWidget):
    """One prerequisite or verification line: mark, label, status word and action."""

    action_requested = QtCore.Signal(str)

    def __init__(
        self, label: str, *, language: str, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._language = language
        layout = QtWidgets.QHBoxLayout(self)
        self.setObjectName("checkRow")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        layout.setContentsMargins(14, 9, 14, 9)
        layout.setSpacing(14)

        self._mark = QtWidgets.QLabel("·")
        self._mark.setObjectName("checkMark")
        self._mark.setFixedSize(32, 32)
        self._mark.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self._label = WrappedLabel(label)
        self._label.setObjectName("checkTitle")
        self._label.setWordWrap(True)

        self._status = QtWidgets.QLabel("")
        self._status.setObjectName("badge")
        self._status.setWordWrap(True)
        self._status.setMaximumWidth(115)

        self._detail = WrappedLabel("")
        self._detail.setWordWrap(True)
        self._detail.setObjectName("muted")
        self._detail.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred
        )

        layout.addWidget(self._mark)
        description = QtWidgets.QVBoxLayout()
        description.setSpacing(3)
        description.addWidget(self._label)
        description.addWidget(self._detail)
        layout.addLayout(description, 1)
        layout.addWidget(self._status, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(label)

    def show_check(self, check: Check) -> None:
        message, action = explain(str(check.code), self._language)
        self._mark.setText(STATUS_MARKS.get(check.status, "·"))
        self._status.setText(status_text(check.status, self._language))
        for widget in (self._mark, self._status):
            widget.setProperty("state", check.status)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
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


class Disclosure(QtWidgets.QWidget):
    """Keyboard-operable disclosure, with a visible direction and a named toggle."""

    toggled = QtCore.Signal(bool)

    def __init__(self, title: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.toggle = QtWidgets.QToolButton()
        self.toggle.setObjectName("disclosure")
        self.toggle.setText(title)
        self.toggle.setAccessibleName(title)
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(QtCore.Qt.ArrowType.RightArrow)
        self.content = QtWidgets.QWidget()
        self.content.setVisible(False)
        layout.addWidget(self.toggle, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.content)
        self.toggle.toggled.connect(self._toggle)

    def _toggle(self, expanded: bool) -> None:
        self.content.setVisible(expanded)
        self.toggle.setArrowType(
            QtCore.Qt.ArrowType.DownArrow if expanded else QtCore.Qt.ArrowType.RightArrow
        )
        self.toggled.emit(expanded)

    def isChecked(self) -> bool:
        return self.toggle.isChecked()

    def setChecked(self, checked: bool) -> None:
        self.toggle.setChecked(checked)


class DetailsBox(Disclosure):
    """Technical details, collapsed by default and never required to finish the flow."""

    def __init__(self, language: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(translate("common.details", language), parent)
        layout = QtWidgets.QVBoxLayout(self.content)
        layout.setContentsMargins(0, 0, 0, 0)
        self._text = QtWidgets.QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumHeight(160)
        self._text.setAccessibleName(translate("common.details", language))
        layout.addWidget(self._text)

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
