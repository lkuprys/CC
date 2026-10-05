# -*- coding: utf-8 -*-
"""
Podbase WORK vizualinė kalba: spalvų žetonai, bendras stilius (QSS) ir sąsajos elementai.

Elementų pavadinimai ir sąsaja sutampa su anksčiau naudotais qfluentwidgets (PushButton, LineEdit,
InfoBar, MessageBoxBase...), todėl programos kodas jais naudojasi taip pat, bet išvaizda valdoma
vienoje vietoje. Iš qfluentwidgets naudojamos tik piktogramos (FluentIcon), nudažomos žetonų spalvomis.
"""
import os
import tempfile
from enum import Enum

from PySide6.QtCore import Qt, Signal, QObject, QTimer, QRectF, QSize, QPoint, QEvent
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPalette, QIcon
from PySide6.QtWidgets import (
    QApplication, QWidget, QFrame, QLabel, QPushButton, QToolButton, QLineEdit, QComboBox,
    QSpinBox, QCheckBox, QProgressBar, QScrollArea, QTableWidget, QAbstractItemView,
    QHBoxLayout, QVBoxLayout, QDialog, QSizePolicy, QButtonGroup
)

from qfluentwidgets import FluentIcon  # tik piktogramos

FIF = FluentIcon

# ----------------- ŽETONAI -----------------
LIGHT = {
    "page": "#F8F8F7", "card": "#FFFFFF", "fill": "#F0F0EE", "pressed": "#E7E7E5",
    "text": "#171717", "secondary": "#5F5F5F", "muted": "#8A8A8A", "disabled": "#B5B5B5",
    "border": "#E7E7E5", "divider": "#EEEEEC", "strong": "#D8D8D5",
    "primary": "#111111", "primary_hover": "#2A2A2A", "on_primary": "#FFFFFF",
    "focus": "#111111",
}
DARK = {
    "page": "#121212", "card": "#1E1E1E", "fill": "#2E2E2D", "pressed": "#2C2C2B",
    "text": "#F5F5F5", "secondary": "#A3A3A0", "muted": "#A3A3A0", "disabled": "#5F5F5F",
    "border": "#2C2C2B", "divider": "#2C2C2B", "strong": "#2E2E2D",
    "primary": "#2D2D2D", "primary_hover": "#2E2E2D", "on_primary": "#F5F5F5",
    "focus": "#A3A3A0",
}
# Būsenų spalvos: (spalva, šviesus fonas). Tamsiame režime fonas gaunamas sumaišius spalvą su kortele.
STATUS = {
    "success": ("#198754", "#EAF7EF"),
    "warning": ("#B7791F", "#FFF7E6"),
    "error": ("#D64545", "#FDEEEE"),
    "info": ("#3478F6", "#EEF4FF"),
}

RADIUS_CONTROL = 12   # mygtukai, laukai
RADIUS_CARD = 16      # kortelės, skydeliai
RADIUS_DIALOG = 24    # dialogai

FONT_STACK = '"Inter", "Segoe UI", sans-serif'

_dark = False


def is_dark():
    return _dark


def tokens():
    return DARK if _dark else LIGHT


def _mix(c1, c2, t):
    a, b = QColor(c1), QColor(c2)
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    ).name()


def status_colors(kind):
    """(spalva, fonas, rėmelis) būsenai success / warning / error / info / neutral."""
    t = tokens()
    if kind not in STATUS:
        return t["secondary"], t["fill"], t["border"]
    color, bg = STATUS[kind]
    if _dark:
        bg = _mix(t["card"], color, 0.16)
        return color, bg, _mix(t["card"], color, 0.35)
    return color, bg, _mix(bg, color, 0.22)


# ----------------- TEMOS PERJUNGIMAS -----------------
class _ThemeSignals(QObject):
    changed = Signal()


theme_signals = _ThemeSignals()


class Theme(Enum):
    LIGHT = "LIGHT"
    DARK = "DARK"
    AUTO = "AUTO"


def isDarkTheme():
    return _dark


def setTheme(theme):
    global _dark
    _dark = theme in (Theme.DARK, "DARK")
    app = QApplication.instance()
    if app is not None:
        _apply_palette(app)
        app.setStyleSheet(build_qss())
    theme_signals.changed.emit()


def _apply_palette(app):
    t = tokens()
    pal = app.palette()
    pal.setColor(QPalette.Window, QColor(t["page"]))
    pal.setColor(QPalette.Base, QColor(t["card"]))
    pal.setColor(QPalette.AlternateBase, QColor(t["fill"]))
    pal.setColor(QPalette.Text, QColor(t["text"]))
    pal.setColor(QPalette.WindowText, QColor(t["text"]))
    pal.setColor(QPalette.ButtonText, QColor(t["text"]))
    pal.setColor(QPalette.Button, QColor(t["card"]))
    pal.setColor(QPalette.PlaceholderText, QColor(t["muted"]))
    pal.setColor(QPalette.Highlight, QColor(t["fill"]))
    pal.setColor(QPalette.HighlightedText, QColor(t["text"]))
    pal.setColor(QPalette.ToolTipBase, QColor(t["card"]))
    pal.setColor(QPalette.ToolTipText, QColor(t["text"]))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(t["disabled"]))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(t["disabled"]))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor(t["disabled"]))
    app.setPalette(pal)


# ----------------- ŠRIFTAI -----------------
def load_fonts(font_dir):
    """Įkelia Inter iš programos paketo ir nustato jį numatytuoju (14 px)."""
    family = None
    if font_dir and os.path.isdir(font_dir):
        for name in sorted(os.listdir(font_dir)):
            if name.lower().endswith((".ttf", ".otf")):
                fid = QFontDatabase.addApplicationFont(os.path.join(font_dir, name))
                fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
                if fams and family is None:
                    family = fams[0]
    font = QFont(family or "Segoe UI")
    font.setPixelSize(14)
    font.setStyleStrategy(QFont.PreferAntialias)
    QApplication.setFont(font)
    return family


def _wide_letters(widget, px=1.0):
    """Platesni tarpai tarp raidžių (QSS letter-spacing Qt nepalaiko patikimai)."""
    f = widget.font()
    f.setLetterSpacing(QFont.AbsoluteSpacing, px)
    widget.setFont(f)


def tabular(widget):
    """Kintantys skaičiai (skaitikliai, laikai) – vienodo pločio skaitmenys."""
    f = widget.font()
    if hasattr(f, "setFeature") and hasattr(QFont, "Tag"):
        try:
            f.setFeature(QFont.Tag("tnum"), 1)
            widget.setFont(f)
        except Exception:
            pass
    return widget


# ----------------- PIKTOGRAMOS (SVG rodyklės QSS'ui) -----------------
_asset_dir = None


def _asset(name, svg):
    global _asset_dir
    if _asset_dir is None:
        _asset_dir = tempfile.mkdtemp(prefix="podbase_ui_")
    path = os.path.join(_asset_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    return path.replace("\\", "/")


def _chevron(color, up=False):
    d = "M4 10l4-4 4 4" if up else "M4 6l4 4 4-4"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.6" stroke-linecap="round" '
            f'stroke-linejoin="round"/></svg>')


def icon(fluent_icon, color=None):
    """FluentIcon → QIcon nurodyta spalva (numatyta – antrinė teksto spalva)."""
    if fluent_icon is None:
        return QIcon()
    if isinstance(fluent_icon, QIcon):
        return fluent_icon
    return fluent_icon.icon(color=QColor(color or tokens()["secondary"]))


# ----------------- BENDRAS STILIUS -----------------
def build_qss():
    t = tokens()
    mode = "dark" if _dark else "light"
    down = _asset(f"chev_down_{mode}.svg", _chevron(t["secondary"]))
    up = _asset(f"chev_up_{mode}.svg", _chevron(t["secondary"], up=True))
    s_fg, s_bg, _ = status_colors("success")
    e_fg, e_bg, _ = status_colors("error")
    return f"""
    * {{ font-family: {FONT_STACK}; }}
    QWidget {{ color: {t['text']}; font-size: 14px; }}
    QWidget#appRoot, QStackedWidget#pages {{ background: {t['page']}; }}
    QScrollArea > QWidget > QWidget#scrollContent {{ background: transparent; }}

    /* Kortelės */
    QFrame[card="true"] {{
        background: {t['card']}; border: 1px solid {t['border']}; border-radius: {RADIUS_CARD}px;
    }}
    QFrame[divider="h"] {{ background: {t['divider']}; border: none; max-height: 1px; min-height: 1px; }}
    QFrame[divider="v"] {{ background: {t['divider']}; border: none; max-width: 1px; min-width: 1px; }}

    /* Tekstas */
    QLabel {{ background: transparent; }}
    QLabel[role="title"] {{ font-size: 22px; font-weight: 600; }}
    QLabel[role="subtitle"] {{ font-size: 17px; font-weight: 600; }}
    QLabel[role="strong"] {{ font-size: 14px; font-weight: 600; }}
    QLabel[role="body"] {{ font-size: 14px; }}
    QLabel[role="secondary"] {{ font-size: 13px; color: {t['secondary']}; }}
    QLabel[role="caption"] {{ font-size: 12px; color: {t['muted']}; }}
    QLabel[role="label"] {{ font-size: 13px; font-weight: 600; color: {t['text']}; }}
    QLabel[role="section"] {{ font-size: 11px; font-weight: 600; color: {t['muted']}; letter-spacing: 1px; }}
    QLabel[role="appname"] {{ font-size: 15px; font-weight: 600; }}
    QLabel:disabled {{ color: {t['disabled']}; }}

    /* Mygtukai: antrinis pagal nutylėjimą */
    QPushButton {{
        background: {t['card']}; color: {t['text']}; border: 1px solid {t['border']};
        border-radius: {RADIUS_CONTROL}px; padding: 0 16px; font-size: 14px; font-weight: 500;
    }}
    QPushButton:hover {{ background: {t['fill']}; }}
    QPushButton:pressed {{ background: {t['pressed']}; }}
    QPushButton:disabled {{ color: {t['disabled']}; background: {t['card']}; }}
    QPushButton[variant="primary"] {{ background: {t['primary']}; color: {t['on_primary']}; border: 1px solid {t['primary']}; }}
    QPushButton[variant="primary"]:hover {{ background: {t['primary_hover']}; border-color: {t['primary_hover']}; }}
    QPushButton[variant="primary"]:disabled {{ background: {t['strong']}; border-color: {t['strong']}; color: {t['card']}; }}
    QPushButton[variant="success"] {{ background: {s_fg}; color: #FFFFFF; border: 1px solid {s_fg}; }}
    QPushButton[variant="success"]:disabled {{ background: {t['strong']}; border-color: {t['strong']}; color: {t['card']}; }}
    QPushButton[variant="danger"] {{ color: {e_fg}; }}
    QPushButton[variant="danger"]:hover {{ background: {e_bg}; }}
    QPushButton[variant="danger"]:disabled {{ color: {t['disabled']}; }}
    QPushButton[variant="danger-solid"] {{ background: {e_fg}; color: #FFFFFF; border: 1px solid {e_fg}; }}
    QPushButton[variant="ghost"] {{ background: transparent; border: 1px solid transparent; }}
    QPushButton[variant="ghost"]:hover {{ background: {t['fill']}; }}

    QToolButton {{
        background: transparent; border: 1px solid transparent; border-radius: {RADIUS_CONTROL}px;
    }}
    QToolButton:hover {{ background: {t['fill']}; }}
    QToolButton:pressed {{ background: {t['pressed']}; }}
    QToolButton[bordered="true"] {{ background: {t['card']}; border: 1px solid {t['border']}; }}
    QToolButton[bordered="true"]:hover {{ background: {t['fill']}; }}

    /* Pagrindiniai skirtukai (pabraukimas) */
    QPushButton[tab="true"] {{
        background: transparent; border: none; border-radius: 0; padding: 0 2px; margin: 0;
        border-bottom: 2px solid transparent; color: {t['secondary']}; font-size: 13px; font-weight: 500;
    }}
    QPushButton[tab="true"]:hover {{ color: {t['text']}; background: transparent; }}
    QPushButton[tab="true"]:checked {{ color: {t['text']}; border-bottom: 2px solid {t['text']}; }}

    /* Segmentų valdiklis */
    QFrame[segmented="true"] {{ background: {t['fill']}; border: none; border-radius: {RADIUS_CONTROL}px; }}
    QPushButton[segment="true"] {{
        background: transparent; border: 1px solid transparent; border-radius: {RADIUS_CONTROL}px;
        color: {t['secondary']}; font-size: 13px; font-weight: 500; padding: 0 14px;
    }}
    QPushButton[segment="true"]:hover {{ color: {t['text']}; background: transparent; }}
    QPushButton[segment="true"]:checked {{ background: {t['card']}; border: 1px solid {t['border']}; color: {t['text']}; }}

    /* Laukai */
    QLineEdit, QComboBox, QSpinBox, QTextBrowser[field="true"] {{
        background: {t['card']}; color: {t['text']}; border: 1px solid {t['border']};
        border-radius: {RADIUS_CONTROL}px; padding: 0 12px; font-size: 14px;
        selection-background-color: {t['strong']}; selection-color: {t['text']};
    }}
    QTextBrowser[field="true"] {{ padding: 8px 12px; background: {t['page']}; }}
    QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{ border-color: {t['strong']}; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {t['focus']}; }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: {t['disabled']}; background: {t['page']}; }}
    QComboBox {{ padding-right: 32px; }}
    QComboBox::drop-down {{ border: none; width: 32px; subcontrol-origin: padding; subcontrol-position: center right; }}
    QComboBox::down-arrow {{ image: url("{down}"); width: 16px; height: 16px; }}
    QComboBox QAbstractItemView {{
        background: {t['card']}; border: 1px solid {t['border']}; border-radius: {RADIUS_CONTROL}px;
        padding: 4px; outline: none; selection-background-color: {t['fill']}; selection-color: {t['text']};
    }}
    QComboBox QAbstractItemView::item {{ min-height: 32px; padding: 0 8px; border-radius: {RADIUS_CONTROL}px; }}
    QSpinBox {{ padding-right: 28px; }}
    QSpinBox::up-button, QSpinBox::down-button {{
        subcontrol-origin: border; width: 28px; border: none; background: transparent;
    }}
    QSpinBox::up-button {{ subcontrol-position: top right; }}
    QSpinBox::down-button {{ subcontrol-position: bottom right; }}
    QSpinBox::up-arrow {{ image: url("{up}"); width: 14px; height: 14px; }}
    QSpinBox::down-arrow {{ image: url("{down}"); width: 14px; height: 14px; }}

    /* Lentelės */
    QTableWidget {{
        background: {t['card']}; border: none; gridline-color: transparent; outline: none;
        selection-background-color: {t['fill']}; selection-color: {t['text']}; font-size: 14px;
    }}
    QTableWidget::item {{ border-bottom: 1px solid {t['divider']}; padding: 0 12px; }}
    QTableWidget::item:selected {{ background: {t['fill']}; color: {t['text']}; }}
    QTableWidget::item:hover {{ background: {t['fill']}; }}
    QHeaderView {{ background: {t['card']}; border: none; }}
    QHeaderView::section {{
        background: {t['card']}; color: {t['muted']}; border: none; border-bottom: 1px solid {t['border']};
        padding: 0 12px; font-size: 11px; font-weight: 600; letter-spacing: 1px; height: 36px;
    }}
    QTableCornerButton::section {{ background: {t['card']}; border: none; }}

    /* Slankjuostės */
    QScrollArea {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{ background: {t['strong']}; border-radius: 3px; min-height: 24px; min-width: 24px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    /* Eiga */
    QProgressBar {{ background: {t['fill']}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }}
    QProgressBar::chunk {{ background: {t['text']}; border-radius: 3px; }}

    QSplitter::handle {{ background: transparent; }}
    QToolTip {{
        background: {t['card']}; color: {t['text']}; border: 1px solid {t['border']};
        padding: 6px 8px; font-size: 12px;
    }}
    """


def repolish(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


# ----------------- TEKSTAS -----------------
class _RoleLabel(QLabel):
    ROLE = "body"

    def __init__(self, *args):
        text, parent = "", None
        for a in args:
            if isinstance(a, str):
                text = a
            elif isinstance(a, QWidget) or a is None:
                parent = a
        super().__init__(text, parent)
        self.setProperty("role", self.ROLE)


class TitleLabel(_RoleLabel):
    ROLE = "title"


class SubtitleLabel(_RoleLabel):
    ROLE = "subtitle"


class StrongBodyLabel(_RoleLabel):
    ROLE = "strong"


class BodyLabel(_RoleLabel):
    ROLE = "body"


class SecondaryLabel(_RoleLabel):
    ROLE = "secondary"


class CaptionLabel(_RoleLabel):
    ROLE = "caption"


class FieldLabel(_RoleLabel):
    """Etiketė virš įvesties lauko (13 px, pusjuodis)."""
    ROLE = "label"


class SectionLabel(_RoleLabel):
    """Mažas skyriaus pavadinimas didžiosiomis raidėmis (pvz. NUSTATYMAI)."""
    ROLE = "section"

    def setText(self, text):
        super().setText((text or "").upper())

    def __init__(self, *args):
        super().__init__(*args)
        self.setText(self.text())
        _wide_letters(self)


# ----------------- KORTELĖS, SKIRTUKAI -----------------
class CardWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("card", True)


SimpleCardWidget = CardWidget
ElevatedCardWidget = CardWidget


def divider(parent=None, vertical=False):
    line = QFrame(parent)
    line.setProperty("divider", "v" if vertical else "h")
    return line


# ----------------- MYGTUKAI -----------------
def _parse_button_args(args):
    fluent, text, parent = None, "", None
    for a in args:
        if isinstance(a, (FluentIcon, QIcon)):
            fluent = a
        elif isinstance(a, str):
            text = a
        elif isinstance(a, QWidget) or a is None:
            parent = a
    return fluent, text, parent


class PushButton(QPushButton):
    """Antrinis mygtukas: baltas, plonas rėmelis, pilkos piktogramos."""
    VARIANT = None
    HEIGHT = 40

    def __init__(self, *args):
        fluent, text, parent = _parse_button_args(args)
        super().__init__(parent)
        self._fluent_icon = fluent
        self.setText(text)
        if self.VARIANT:
            self.setProperty("variant", self.VARIANT)
        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setIconSize(QSize(16, 16))
        self._refresh_icon()
        theme_signals.changed.connect(self._refresh_icon)

    def setText(self, text):
        # Qt neleidžia QSS nustatyti tarpo tarp piktogramos ir teksto, todėl pridedamas tarpas (~8 px)
        text = (text or "").strip()
        super().setText(f"  {text}" if self._fluent_icon is not None and text else text)

    def _icon_color(self):
        t = tokens()
        if self.VARIANT in ("primary", "success", "danger-solid"):
            return "#FFFFFF" if self.VARIANT != "primary" else t["on_primary"]
        if self.VARIANT == "danger":
            return STATUS["error"][0]
        return t["secondary"]

    def _refresh_icon(self):
        if self._fluent_icon is not None:
            self.setIcon(icon(self._fluent_icon, self._icon_color()))

    def setVariant(self, variant):
        self.VARIANT = variant
        self.setProperty("variant", variant)
        repolish(self)
        self._refresh_icon()


class PrimaryPushButton(PushButton):
    VARIANT = "primary"


class SuccessPushButton(PushButton):
    VARIANT = "success"


class DangerPushButton(PushButton):
    VARIANT = "danger"


class GhostPushButton(PushButton):
    VARIANT = "ghost"


class ToolButton(QToolButton):
    """Kvadratinis piktogramos mygtukas (36 px, 12 px kampai, šviesus fonas užvedus)."""
    BORDERED = True

    def __init__(self, *args):
        fluent, _text, parent = _parse_button_args(args)
        super().__init__(parent)
        self._fluent_icon = fluent
        self._color = None
        self.setProperty("bordered", self.BORDERED)
        self.setFixedSize(36, 36)
        self.setIconSize(QSize(16, 16))
        self.setCursor(Qt.PointingHandCursor)
        self._refresh_icon()
        theme_signals.changed.connect(self._refresh_icon)

    def setIconColor(self, color):
        self._color = color
        self._refresh_icon()

    def _refresh_icon(self):
        if self._fluent_icon is not None:
            self.setIcon(icon(self._fluent_icon, self._color))


class TransparentToolButton(ToolButton):
    BORDERED = False


# ----------------- LAUKAI -----------------
class LineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)


class SearchLineEdit(LineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._action = self.addAction(icon(FIF.SEARCH, tokens()["muted"]), QLineEdit.LeadingPosition)
        self.setClearButtonEnabled(True)
        theme_signals.changed.connect(lambda: self._action.setIcon(icon(FIF.SEARCH, tokens()["muted"])))


class ComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setCursor(Qt.PointingHandCursor)

    def addItem(self, text, icon=None, userData=None):  # noqa: A002 – suderinama su qfluentwidgets
        if isinstance(icon, QIcon):
            super().addItem(icon, text, userData)
        else:
            super().addItem(text, userData)


class SpinBox(QSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        tabular(self)


class CheckBox(QCheckBox):
    """Jungiklis (pilnai suapvalintas), nes kvadratinės varnelės kampai neatitiktų leistinų spindulių."""
    TRACK_W, TRACK_H = 36, 20

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(28)
        theme_signals.changed.connect(self.update)

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(self.TRACK_W + 10 + fm.horizontalAdvance(self.text()) + 4, max(28, fm.height() + 8))

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, _event):
        t = tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        y = (self.height() - self.TRACK_H) / 2
        track = QRectF(0.5, y + 0.5, self.TRACK_W - 1, self.TRACK_H - 1)
        on = self.isChecked()
        enabled = self.isEnabled()
        track_color = QColor(t["text"] if on else t["strong"])
        if _dark and on:
            track_color = QColor(t["secondary"])
        if not enabled:
            track_color = QColor(t["fill"])
        p.setPen(Qt.NoPen)
        p.setBrush(track_color)
        p.drawRoundedRect(track, self.TRACK_H / 2, self.TRACK_H / 2)
        knob = self.TRACK_H - 6
        kx = self.TRACK_W - knob - 3 if on else 3
        p.setBrush(QColor(t["card"]))
        p.drawEllipse(QRectF(kx, y + 3, knob, knob))
        p.setPen(QColor(t["text"] if enabled else t["disabled"]))
        p.setFont(self.font())
        text_rect = self.rect().adjusted(self.TRACK_W + 10, 0, 0, 0)
        p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text())
        p.end()


class ProgressBar(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextVisible(False)
        self.setRange(0, 100)
        self.setFixedHeight(6)


class SmoothScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)


class TableWidget(QTableWidget):
    """Lentelė: eilučių skirtukai, mažos pilkos antraštės didžiosiomis raidėmis, be eilučių numerių."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(40)
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.horizontalHeader().setFixedHeight(36)
        _wide_letters(self.horizontalHeader())
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setFocusPolicy(Qt.NoFocus)
        self.setWordWrap(False)
        self.setMouseTracking(True)

    def setHorizontalHeaderLabels(self, labels):
        super().setHorizontalHeaderLabels([str(x).upper() for x in labels])


# ----------------- BŪSENOS ŽENKLIUKAS -----------------
class StatusBadge(QLabel):
    """Maža pilnai suapvalinta etiketė su tašku: success / warning / error / info / neutral."""

    def __init__(self, text="", kind="neutral", parent=None, dot=True):
        super().__init__(parent)
        self._kind = kind
        self._text = text
        self._dot = dot
        self.setFixedHeight(24)
        self.setAlignment(Qt.AlignCenter)
        tabular(self)
        self._apply()
        theme_signals.changed.connect(self._apply)

    def set_status(self, kind, text=None):
        self._kind = kind
        if text is not None:
            self._text = text
        self._apply()

    def setText(self, text):  # suderinama su QLabel
        self._text = text
        self._apply()

    def _apply(self):
        fg, bg, _border = status_colors(self._kind)
        dot = f'<span style="color:{fg}">●</span>&nbsp;&nbsp;' if self._dot else ""
        super().setText(f'{dot}<span style="color:{fg}">{self._text}</span>')
        self.setStyleSheet(
            f"QLabel {{ background: {bg}; border-radius: 12px; padding: 0 10px; font-size: 12px; font-weight: 500; }}"
        )


PillPushButton = StatusBadge


# ----------------- SEGMENTŲ VALDIKLIS -----------------
class SegmentedWidget(QFrame):
    """Pilkas takelis, pasirinktas segmentas baltas su plonu rėmeliu."""
    currentItemChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("segmented", True)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._items = {}
        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

    def addItem(self, routeKey, text, onClick=None, icon=None):  # noqa: A002
        btn = QPushButton(text, self)
        btn.setProperty("segment", True)
        btn.setCheckable(True)
        btn.setFixedHeight(32)
        btn.setCursor(Qt.PointingHandCursor)
        self._group.addButton(btn)
        self._layout.addWidget(btn)
        self._items[routeKey] = btn

        def _clicked():
            self.currentItemChanged.emit(routeKey)
            if onClick:
                onClick()
        btn.clicked.connect(_clicked)
        return btn

    def setCurrentItem(self, routeKey):
        btn = self._items.get(routeKey)
        if btn:
            btn.setChecked(True)

    def currentRouteKey(self):
        for k, b in self._items.items():
            if b.isChecked():
                return k
        return None


class UnderlineTabs(QWidget):
    """Pagrindiniai skyriai: 13 px tekstas, aktyvus – tamsus su 2 px pabraukimu."""
    currentChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(24)
        self._layout.addStretch(1)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons = []

    def addTab(self, text):
        btn = QPushButton(text, self)
        btn.setProperty("tab", True)
        btn.setCheckable(True)
        btn.setFixedHeight(44)
        btn.setCursor(Qt.PointingHandCursor)
        idx = len(self._buttons)
        btn.clicked.connect(lambda: self.currentChanged.emit(idx))
        self._group.addButton(btn)
        self._layout.insertWidget(self._layout.count() - 1, btn)
        self._buttons.append(btn)
        if idx == 0:
            btn.setChecked(True)
        return idx

    def setCurrentIndex(self, idx):
        if 0 <= idx < len(self._buttons):
            self._buttons[idx].setChecked(True)


# ----------------- PRANEŠIMAI (InfoBar) -----------------
class InfoBarPosition(Enum):
    TOP = 0
    BOTTOM = 1
    TOP_LEFT = 2
    TOP_RIGHT = 3
    BOTTOM_LEFT = 4
    BOTTOM_RIGHT = 5
    NONE = 6


_STATUS_ICON = {"success": FIF.COMPLETED, "warning": FIF.INFO, "error": FIF.INFO, "info": FIF.INFO}


class Notice(QFrame):
    """Šviesiai tonuota kortelė: piktograma, pavadinimas, trumpas tekstas. Naudojama ir kaip įterptas pranešimas."""
    closed = Signal()

    def __init__(self, kind, title, content="", parent=None, closable=False):
        super().__init__(parent)
        self.kind = kind
        fg, bg, border = status_colors(kind)
        self.setObjectName("notice")
        self.setStyleSheet(
            f"QFrame#notice {{ background: {bg}; border: 1px solid {border}; border-radius: {RADIUS_CONTROL}px; }}"
            f"QFrame#notice QLabel {{ background: transparent; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 10 if closable else 14, 12)
        lay.setSpacing(10)
        ic = QLabel(self)
        ic.setPixmap(icon(_STATUS_ICON.get(kind, FIF.INFO), fg).pixmap(16, 16))
        ic.setFixedSize(16, 20)
        ic.setAlignment(Qt.AlignTop)
        lay.addWidget(ic, 0, Qt.AlignTop)
        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        text_box.setAlignment(Qt.AlignTop)
        if title:
            tl = QLabel(title, self)
            tl.setStyleSheet(f"color: {tokens()['text']}; font-size: 14px; font-weight: 600;")
            tl.setWordWrap(True)
            text_box.addWidget(tl)
        if content:
            cl = QLabel(content, self)
            cl.setStyleSheet(f"color: {tokens()['secondary']}; font-size: 13px;")
            cl.setWordWrap(True)
            cl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            text_box.addWidget(cl)
        lay.addLayout(text_box, 1)
        if closable:
            close = TransparentToolButton(FIF.CLOSE, self)
            close.setFixedSize(28, 28)
            close.setIconSize(QSize(12, 12))
            close.clicked.connect(self._close)
            lay.addWidget(close, 0, Qt.AlignTop)

    def _close(self):
        self.closed.emit()
        self.hide()
        self.deleteLater()


class _ToastHost(QObject):
    """Išdėsto iššokančius pranešimus lango kampe vieną po kito."""
    MARGIN = 16
    TOP_OFFSET = 108   # žemiau viršutinės juostos ir skirtukų

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.toasts = []
        window.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Resize:
            self.layout()
        return False

    def add(self, toast, bottom=False):
        toast.setProperty("bottom", bottom)
        self.toasts.append(toast)
        toast.destroyed.connect(lambda *_: self._remove(toast))
        toast.closed.connect(lambda: self._remove(toast))
        toast.show()
        toast.raise_()
        self.layout()

    def _remove(self, toast):
        if toast in self.toasts:
            self.toasts.remove(toast)
            QTimer.singleShot(0, self.layout)

    def layout(self):
        w = self.window.width()
        top_y = self.TOP_OFFSET
        bottom_y = self.window.height() - self.MARGIN
        for t in list(self.toasts):
            try:
                t.adjustSize()
                width = min(420, max(280, w - 2 * self.MARGIN))
                t.setFixedWidth(width)
                h = t.layout().totalHeightForWidth(width) if t.layout() else t.sizeHint().height()
                x = w - width - self.MARGIN
                if t.property("bottom"):
                    bottom_y -= h
                    t.setGeometry(x, bottom_y, width, h)
                    bottom_y -= 8
                else:
                    t.setGeometry(x, top_y, width, h)
                    top_y += h + 8
                t.raise_()
            except RuntimeError:
                pass


def _toast_host(parent):
    window = parent.window() if parent is not None else None
    if window is None:
        return None
    host = getattr(window, "_podbase_toast_host", None)
    if host is None:
        host = _ToastHost(window)
        window._podbase_toast_host = host
    return host


class InfoBar:
    """Suderinama su qfluentwidgets InfoBar: InfoBar.success(title=..., content=..., parent=...)."""

    @staticmethod
    def _show(kind, title="", content="", orient=None, isClosable=True, position=InfoBarPosition.TOP_RIGHT,
              duration=3000, parent=None):
        host = _toast_host(parent)
        if host is None:
            return None
        persistent = duration is None or duration < 0
        toast = Notice(kind, title, content, host.window, closable=isClosable or persistent)
        host.add(toast, bottom=position in (InfoBarPosition.BOTTOM_RIGHT, InfoBarPosition.BOTTOM,
                                            InfoBarPosition.BOTTOM_LEFT))
        if not persistent:
            QTimer.singleShot(int(duration), toast._close)
        return toast

    @staticmethod
    def success(**kw):
        return InfoBar._show("success", **kw)

    @staticmethod
    def warning(**kw):
        return InfoBar._show("warning", **kw)

    @staticmethod
    def error(**kw):
        return InfoBar._show("error", **kw)

    @staticmethod
    def info(**kw):
        return InfoBar._show("info", **kw)


# ----------------- DIALOGAI -----------------
class MessageBoxBase(QDialog):
    """
    Baltas dialogas su 24 px kampais, be šešėlio. Suderinamas su qfluentwidgets MessageBoxBase:
    viewLayout (turinys), widget (kortelė), yesButton (pagrindinis), cancelButton (antrinis).
    """

    def __init__(self, parent=None):
        super().__init__(parent.window() if parent is not None else None)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.widget = QFrame(self)
        self.widget.setObjectName("dialogCard")
        t = tokens()
        self.widget.setStyleSheet(
            f"QFrame#dialogCard {{ background: {t['card']}; border: 1px solid {t['border']}; "
            f"border-radius: {RADIUS_DIALOG}px; }}"
        )
        outer.addWidget(self.widget)
        card = QVBoxLayout(self.widget)
        card.setContentsMargins(24, 24, 24, 20)
        card.setSpacing(20)
        self.viewLayout = QVBoxLayout()
        self.viewLayout.setSpacing(12)
        card.addLayout(self.viewLayout, 1)
        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.setSpacing(8)
        self.buttonLayout.addStretch(1)
        self.cancelButton = PushButton("Atšaukti", self.widget)
        self.yesButton = PrimaryPushButton("Gerai", self.widget)
        self.buttonLayout.addWidget(self.cancelButton)
        self.buttonLayout.addWidget(self.yesButton)
        card.addLayout(self.buttonLayout)
        self.yesButton.clicked.connect(self.accept)
        self.cancelButton.clicked.connect(self.reject)
        self._overlay = None

    def showEvent(self, e):
        parent = self.parentWidget()
        if parent is not None and self._overlay is None:
            # Priglušintas fonas už dialogo (be suliejimo ir šešėlių)
            self._overlay = QWidget(parent)
            self._overlay.setStyleSheet("background: rgba(23, 23, 23, 0.28);")
            self._overlay.setGeometry(parent.rect())
            self._overlay.show()
        super().showEvent(e)
        self.adjustSize()
        if parent is not None:
            center = parent.mapToGlobal(parent.rect().center())
            self.move(center - QPoint(self.width() // 2, self.height() // 2))

    def done(self, r):
        if self._overlay is not None:
            self._overlay.deleteLater()
            self._overlay = None
        super().done(r)

    def exec(self):
        return super().exec() == QDialog.Accepted


def confirm(parent, title, text, confirm_text="Ištrinti", danger=True):
    """Patvirtinimo dialogas prieš trynimą ar kitą negrįžtamą veiksmą."""
    dlg = MessageBoxBase(parent)
    dlg.widget.setMinimumWidth(420)
    dlg.viewLayout.addWidget(SubtitleLabel(title, dlg.widget))
    body = SecondaryLabel(text, dlg.widget)
    body.setWordWrap(True)
    dlg.viewLayout.addWidget(body)
    dlg.yesButton.setText(confirm_text)
    if danger:
        dlg.yesButton.setVariant("danger-solid")
    return dlg.exec()


def apply_app_theme(app, dark=False, font_dir=None):
    """Paleidžiant: šriftai, paletė ir bendras stilius."""
    load_fonts(font_dir)
    app.setStyle("Fusion")
    setTheme(Theme.DARK if dark else Theme.LIGHT)
