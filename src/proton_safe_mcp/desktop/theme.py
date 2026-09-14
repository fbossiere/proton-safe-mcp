"""A small, palette-aware visual system for the native setup assistant."""

from typing import Final

from PySide6 import QtCore, QtGui, QtWidgets

#: The sizes the window, the task bar and a Windows shortcut ask for. Small sizes are
#: included so the icon stays legible where Windows scales it down hardest.
ICON_SIZES: Final = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def icon_pixmap(size: int) -> QtGui.QPixmap:
    """Draw the product mark at one resolution, without a runtime asset.

    The same drawing serves the window icon on both platforms and the `.ico` the
    Windows installer ships, so the identity cannot drift between them.
    """
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.scale(size / 64, size / 64)
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.setBrush(QtGui.QColor("#7860db"))
    painter.drawRoundedRect(QtCore.QRectF(0, 0, 64, 64), 17, 17)
    painter.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 3))
    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QtCore.QRectF(13, 18, 38, 28), 5, 5)
    painter.drawPolyline(
        QtGui.QPolygonF([QtCore.QPointF(14, 21), QtCore.QPointF(32, 34), QtCore.QPointF(50, 21)])
    )
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.setBrush(QtGui.QColor("#d0f5df"))
    painter.drawEllipse(QtCore.QRectF(36, 35, 24, 24))
    painter.setPen(QtGui.QPen(QtGui.QColor("#24563e"), 2.5))
    painter.drawPolyline(
        QtGui.QPolygonF([QtCore.QPointF(42, 47), QtCore.QPointF(46, 51), QtCore.QPointF(54, 43)])
    )
    painter.end()
    return pixmap


def app_icon() -> QtGui.QIcon:
    """The window icon, drawn at every resolution the desktop may ask for."""
    icon = QtGui.QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(icon_pixmap(size))
    return icon


def apply_theme(window: QtWidgets.QWidget, *, dark: bool | None = None) -> None:
    """Scope styling to this window; preserve the system's light/dark preference."""
    if dark is None:
        dark = window.palette().color(QtGui.QPalette.ColorRole.Window).lightness() < 128
    colors = (
        {
            "bg": "#191a22",
            "surface": "#23252f",
            "field": "#1c1e27",
            "text": "#f1f0f7",
            "muted": "#bab9cc",
            "border": "#3f4152",
            "accent": "#c0adff",
            "primary": "#b9a5ff",
            "on_primary": "#21123f",
            "hover": "#343443",
            "focus": "#d5c7ff",
            "success": "#a2dfc0",
            "success_bg": "#233b32",
            "note": "#2d293f",
        }
        if dark
        else {
            "bg": "#f5f4f9",
            "surface": "#ffffff",
            "field": "#ffffff",
            "text": "#242137",
            "muted": "#625e75",
            "border": "#d8d5e3",
            "accent": "#6543c5",
            "primary": "#6945cf",
            "on_primary": "#ffffff",
            "hover": "#eeebf7",
            "focus": "#6543c5",
            "success": "#276445",
            "success_bg": "#e9f5ee",
            "note": "#eee9fa",
        }
    )
    palette = window.palette()
    for role, color in (
        (QtGui.QPalette.ColorRole.Window, "bg"),
        (QtGui.QPalette.ColorRole.WindowText, "text"),
        (QtGui.QPalette.ColorRole.Base, "field"),
        (QtGui.QPalette.ColorRole.Text, "text"),
        (QtGui.QPalette.ColorRole.Button, "surface"),
        (QtGui.QPalette.ColorRole.ButtonText, "text"),
        (QtGui.QPalette.ColorRole.Highlight, "primary"),
        (QtGui.QPalette.ColorRole.HighlightedText, "on_primary"),
    ):
        palette.setColor(role, QtGui.QColor(colors[color]))
    window.setPalette(palette)
    window.setStyleSheet(
        """
        QWidget {{ color: {text}; font-size: 11pt; }}
        QMainWindow, QWidget#shell, QWidget#screen, QWidget#page,
        QScrollArea, QScrollArea > QWidget > QWidget {{ background: {bg}; }}
        QLabel {{ background: transparent; }}
        QLabel#brand {{ font-size: 13pt; font-weight: 700; }}
        QLabel#eyebrow, QLabel#muted {{ color: {muted}; }}
        QLabel#heading {{ font-size: 25pt; font-weight: 700; }}
        QLabel#fieldLabel, QLabel#checkTitle {{ font-weight: 600; }}
        QLabel#note, QLabel#feedback {{
            background: {note}; border-radius: 10px; padding: 12px;
        }}
        QWidget#footer {{ border-top: 1px solid {border}; background: {bg}; }}
        QWidget#checkRow {{ background: {surface}; border: 1px solid {border};
            border-radius: 10px; }}
        QLabel#checkMark {{ color: {muted}; font-size: 17pt; }}
        QLabel#checkMark[state="pass"], QLabel#badge[state="pass"] {{
            color: {success}; background: {success_bg}; border-radius: 8px;
        }}
        QLabel#badge {{ color: {muted}; padding: 4px 8px; font-size: 10pt; }}
        QFrame#segment {{ background: {border}; border: none; border-radius: 2px; }}
        QFrame#segment[reached="true"] {{ background: {accent}; }}
        QPushButton, QToolButton {{
            background: {surface}; border: 1px solid {border}; border-radius: 8px;
            padding: 9px 14px; font-weight: 600;
        }}
        QPushButton:hover, QToolButton:hover {{ background: {hover}; }}
        QPushButton#primary {{ background: {primary}; color: {on_primary};
            border: 2px solid {primary}; padding: 8px 20px; }}
        QPushButton#primary:hover {{ border-color: {text}; }}
        QPushButton:disabled, QPushButton#primary:disabled, QToolButton:disabled {{ color: {muted};
            background: {bg}; border-color: {border}; }}
        QPushButton:focus, QToolButton:focus, QLineEdit:focus, QSpinBox:focus,
        QListWidget:focus, QPlainTextEdit:focus, QGroupBox:focus, QCheckBox:focus,
        QWidget#checkRow:focus {{ border: 2px solid {focus}; }}
        QLineEdit, QSpinBox, QPlainTextEdit, QListWidget {{
            background: {field}; border: 1px solid {border}; border-radius: 8px;
            padding: 9px; selection-background-color: {primary};
            selection-color: {on_primary};
        }}
        QLineEdit, QSpinBox {{ min-height: 22px; }}
        QListWidget::item {{ padding: 14px; border-radius: 6px; }}
        QListWidget::item:selected {{ background: {note}; color: {text}; }}
        QCheckBox {{ spacing: 9px; padding: 6px 2px; border: 2px solid transparent; }}
        QCheckBox::indicator {{ width: 18px; height: 18px; }}
        QToolButton#disclosure {{ background: transparent; border: 2px solid transparent;
            color: {muted}; padding: 7px 4px; font-weight: 400; }}
        QToolButton#disclosure:hover {{ background: {hover}; }}
        QToolButton#disclosure:focus {{ border-color: {focus}; }}
        QScrollArea {{ border: none; }}
        QScrollBar:vertical {{ width: 10px; background: transparent; margin: 0; }}
        QScrollBar::handle:vertical {{ background: {border}; border-radius: 4px;
            min-height: 30px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
    """.format(**colors)
    )
