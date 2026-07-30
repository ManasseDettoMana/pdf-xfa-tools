"""Design tokens and the stylesheet built from them.

One :class:`Palette` describes a theme; the whole stylesheet is generated from
it, so light and dark can never drift apart and adding a third theme means
adding one palette.  Widgets opt into a role with ``setObjectName`` or a dynamic
property (``variant``, ``badge``, ``status``) rather than carrying inline styles.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette


@dataclass(frozen=True)
class Palette:
    """Every colour the interface uses, named by role rather than by value."""

    name: str
    is_dark: bool

    background: str
    surface: str
    surface_alt: str
    surface_hover: str
    border: str
    border_strong: str

    text: str
    text_muted: str
    text_inverted: str

    accent: str
    accent_hover: str
    accent_pressed: str
    accent_soft: str

    success: str
    success_soft: str
    warning: str
    warning_soft: str
    danger: str
    danger_soft: str

    shadow: str


LIGHT = Palette(
    name="light",
    is_dark=False,
    background="#F4F6F9",
    surface="#FFFFFF",
    surface_alt="#EDF1F6",
    surface_hover="#E4EAF2",
    border="#D9DFE8",
    border_strong="#BCC5D2",
    text="#161B22",
    text_muted="#5F6B7A",
    text_inverted="#FFFFFF",
    accent="#2563EB",
    accent_hover="#1D4ED8",
    accent_pressed="#1E40AF",
    accent_soft="#E3EBFD",
    success="#15803D",
    success_soft="#DCFCE7",
    warning="#B45309",
    warning_soft="#FEF3C7",
    danger="#B91C1C",
    danger_soft="#FEE2E2",
    shadow="rgba(15, 23, 42, 0.10)",
)

DARK = Palette(
    name="dark",
    is_dark=True,
    background="#12151A",
    surface="#1A1E25",
    surface_alt="#212630",
    surface_hover="#2A3039",
    border="#2F3742",
    border_strong="#414B58",
    text="#E7EAEF",
    text_muted="#98A2B0",
    text_inverted="#0B0E12",
    accent="#3B82F6",
    accent_hover="#60A5FA",
    accent_pressed="#2563EB",
    accent_soft="#1E293B",
    success="#4ADE80",
    success_soft="#14321F",
    warning="#FBBF24",
    warning_soft="#3A2C0B",
    danger="#F87171",
    danger_soft="#3B1717",
    shadow="rgba(0, 0, 0, 0.45)",
)

PALETTES = {"light": LIGHT, "dark": DARK}

#: Maps an extraction badge to the palette role that colours it.
BADGE_ROLES = {
    "EXACT": "success",
    "HEURISTIC": "warning",
    "OCR": "warning",
    "APPROSSIMATO": "warning",
}


def system_prefers_dark() -> bool:
    """True when the desktop is using a dark colour scheme."""
    hints = QGuiApplication.styleHints()
    scheme = getattr(hints, "colorScheme", None)
    if scheme is not None:
        try:
            return scheme() == Qt.ColorScheme.Dark
        except Exception:
            pass
    # Fall back to comparing the default window text and background luminance.
    palette = QGuiApplication.palette()
    background = palette.color(QPalette.ColorRole.Window)
    return background.lightness() < 128


def resolve(preference: str) -> Palette:
    """Turn a stored preference ("system" / "light" / "dark") into a palette."""
    if preference in PALETTES:
        return PALETTES[preference]
    return DARK if system_prefers_dark() else LIGHT


def build_stylesheet(p: Palette) -> str:
    """Render the full application stylesheet for one palette."""
    return f"""
/* ---------- base ---------- */
QWidget {{
    background-color: {p.background};
    color: {p.text};
    font-family: "Segoe UI", "Inter", "Noto Sans", sans-serif;
    font-size: 10pt;
}}
QMainWindow, QDialog {{ background-color: {p.background}; }}

/* Labels and check boxes must not paint the window colour over whatever card
   or panel they sit on, otherwise every piece of text shows as a coloured band. */
QLabel, QCheckBox {{ background: transparent; }}

QToolTip {{
    background-color: {p.surface};
    color: {p.text};
    border: 1px solid {p.border_strong};
    border-radius: 6px;
    padding: 6px 8px;
}}

/* ---------- structural surfaces ---------- */
QFrame#Header {{
    background-color: {p.surface};
    border-bottom: 1px solid {p.border};
}}
QFrame#Footer {{
    background-color: {p.surface};
    border-top: 1px solid {p.border};
}}
QFrame#Card, QFrame#SidePanel {{
    background-color: {p.surface};
    border: 1px solid {p.border};
    border-radius: 12px;
}}
QWidget#Content {{ background-color: {p.background}; }}
/* Plain container widgets sitting inside a card must not repaint the window
   colour over it. */
QWidget#PanelBody {{ background: transparent; }}

/* ---------- typography ---------- */
QLabel#AppTitle {{
    font-size: 15pt;
    font-weight: 600;
    color: {p.text};
}}
QLabel#AppSubtitle, QLabel[variant="muted"] {{
    color: {p.text_muted};
    font-size: 9pt;
}}
QLabel#SectionTitle {{
    font-size: 11pt;
    font-weight: 600;
    padding: 2px 0 6px 0;
}}
QLabel#DropTitle {{
    font-size: 16pt;
    font-weight: 600;
}}
QLabel#DropSubtitle {{
    color: {p.text_muted};
    font-size: 10pt;
}}
QLabel#OptionHelp {{
    color: {p.text_muted};
    font-size: 8.5pt;
}}

/* ---------- buttons ---------- */
QPushButton {{
    background-color: {p.surface_alt};
    color: {p.text};
    border: 1px solid {p.border};
    border-radius: 8px;
    padding: 7px 16px;
    font-weight: 500;
}}
QPushButton:hover {{ background-color: {p.surface_hover}; border-color: {p.border_strong}; }}
QPushButton:pressed {{ background-color: {p.border}; }}
QPushButton:disabled {{ color: {p.text_muted}; background-color: {p.surface_alt}; border-color: {p.border}; }}
QPushButton:focus {{ outline: none; border-color: {p.accent}; }}

QPushButton[variant="primary"] {{
    background-color: {p.accent};
    color: {p.text_inverted};
    border: 1px solid {p.accent};
    font-weight: 600;
    padding: 8px 22px;
}}
QPushButton[variant="primary"]:hover {{ background-color: {p.accent_hover}; border-color: {p.accent_hover}; }}
QPushButton[variant="primary"]:pressed {{ background-color: {p.accent_pressed}; }}
QPushButton[variant="primary"]:disabled {{
    background-color: {p.surface_alt};
    color: {p.text_muted};
    border-color: {p.border};
}}

QPushButton[variant="ghost"] {{
    background-color: transparent;
    border: 1px solid transparent;
    padding: 6px 12px;
    color: {p.text_muted};
}}
QPushButton[variant="ghost"]:hover {{ background-color: {p.surface_alt}; color: {p.text}; }}

QPushButton[variant="danger"] {{
    background-color: transparent;
    color: {p.danger};
    border: 1px solid {p.border};
}}
QPushButton[variant="danger"]:hover {{ background-color: {p.danger_soft}; border-color: {p.danger}; }}

/* ---------- inputs ---------- */
QComboBox, QSpinBox, QLineEdit {{
    background-color: {p.surface};
    border: 1px solid {p.border};
    border-radius: 8px;
    padding: 6px 10px;
    min-height: 20px;
    selection-background-color: {p.accent};
    selection-color: {p.text_inverted};
}}
QComboBox:hover, QSpinBox:hover, QLineEdit:hover {{ border-color: {p.border_strong}; }}
QComboBox:focus, QSpinBox:focus, QLineEdit:focus {{ border-color: {p.accent}; }}
QComboBox:disabled, QSpinBox:disabled, QLineEdit:disabled {{
    background-color: {p.surface_alt};
    color: {p.text_muted};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {p.text_muted};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {p.surface};
    border: 1px solid {p.border_strong};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {p.accent_soft};
    selection-color: {p.text};
    outline: none;
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 16px; border: none; background: transparent; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {p.border_strong};
    border-radius: 4px;
    background-color: {p.surface};
}}
QCheckBox::indicator:checked {{ background-color: {p.accent}; border-color: {p.accent}; }}
QCheckBox::indicator:hover {{ border-color: {p.accent}; }}

/* ---------- table ---------- */
QTableWidget, QTableView {{
    background-color: {p.surface};
    alternate-background-color: {p.surface_alt};
    border: 1px solid {p.border};
    border-radius: 12px;
    gridline-color: transparent;
    selection-background-color: {p.accent_soft};
    selection-color: {p.text};
    outline: none;
}}
QTableWidget::item, QTableView::item {{
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid {p.border};
}}
QTableWidget::item:selected, QTableView::item:selected {{
    background-color: {p.accent_soft};
    color: {p.text};
}}
QHeaderView::section {{
    background-color: {p.surface_alt};
    color: {p.text_muted};
    border: none;
    border-bottom: 1px solid {p.border};
    padding: 9px 10px;
    font-weight: 600;
    font-size: 9pt;
}}
QHeaderView::section:first {{ border-top-left-radius: 12px; }}
QHeaderView::section:last {{ border-top-right-radius: 12px; }}
QTableCornerButton::section {{ background-color: {p.surface_alt}; border: none; }}

/* ---------- progress ---------- */
QProgressBar {{
    background-color: {p.surface_alt};
    border: none;
    border-radius: 5px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{ background-color: {p.accent}; border-radius: 5px; }}
QProgressBar[status="done"]::chunk {{ background-color: {p.success}; }}
QProgressBar[status="failed"]::chunk {{ background-color: {p.danger}; }}

/* ---------- badges ---------- */
QLabel[badge="EXACT"] {{
    background-color: {p.success_soft};
    color: {p.success};
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 8pt;
    font-weight: 700;
}}
QLabel[badge="HEURISTIC"], QLabel[badge="OCR"], QLabel[badge="APPROSSIMATO"] {{
    background-color: {p.warning_soft};
    color: {p.warning};
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 8pt;
    font-weight: 700;
}}
QLabel[state="success"] {{ color: {p.success}; }}
QLabel[state="warning"] {{ color: {p.warning}; }}
QLabel[state="danger"] {{ color: {p.danger}; }}

/* ---------- drop zone ---------- */
QFrame#DropZone {{
    background-color: {p.surface};
    border: 2px dashed {p.border_strong};
    border-radius: 16px;
}}
QFrame#DropZone[dragging="true"] {{
    background-color: {p.accent_soft};
    border: 2px dashed {p.accent};
}}

/* ---------- scrollbars ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 2px 4px 0;
}}
QScrollBar::handle:vertical {{
    background: {p.border_strong};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {p.text_muted}; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0 4px 2px 4px;
}}
QScrollBar::handle:horizontal {{
    background: {p.border_strong};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: {p.text_muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

/* ---------- text areas ---------- */
QPlainTextEdit, QTextEdit {{
    background-color: {p.surface_alt};
    border: 1px solid {p.border};
    border-radius: 8px;
    padding: 8px;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 9pt;
    selection-background-color: {p.accent};
    selection-color: {p.text_inverted};
}}

/* ---------- separators ---------- */
QFrame[variant="separator"] {{
    background-color: {p.border};
    border: none;
    max-height: 1px;
}}
"""


def apply_theme(app, preference: str) -> Palette:
    """Apply the resolved palette to ``app`` and return it."""
    palette = resolve(preference)
    app.setStyleSheet(build_stylesheet(palette))

    # Keep the native palette roughly in step so non-styled pieces (native
    # dialogs, tooltips on some platforms) do not flash the wrong colours.
    qt_palette = QPalette()
    qt_palette.setColor(QPalette.ColorRole.Window, QColor(palette.background))
    qt_palette.setColor(QPalette.ColorRole.WindowText, QColor(palette.text))
    qt_palette.setColor(QPalette.ColorRole.Base, QColor(palette.surface))
    qt_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(palette.surface_alt))
    qt_palette.setColor(QPalette.ColorRole.Text, QColor(palette.text))
    qt_palette.setColor(QPalette.ColorRole.Button, QColor(palette.surface_alt))
    qt_palette.setColor(QPalette.ColorRole.ButtonText, QColor(palette.text))
    qt_palette.setColor(QPalette.ColorRole.Highlight, QColor(palette.accent))
    qt_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(palette.text_inverted))
    app.setPalette(qt_palette)

    return palette


def restyle(widget) -> None:
    """Re-apply the stylesheet to a widget after a dynamic property changed.

    Qt does not repolish automatically when a property used in a selector
    changes, so every property-driven state switch has to call this.
    """
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()
