"""The Diagnostics dialog: what is installed, and what each missing piece costs.

Deliberately framed as informational rather than as a list of errors.  The
application works with nothing but its bundled dependencies; missing components
only disable specific conversions, and each row says which.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core import engines
from ..i18n import tr, translator


class DiagnosticsDialog(QDialog):
    """Lists detected libraries and external engines."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setMinimumSize(720, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        self.heading = QLabel(self)
        self.heading.setObjectName("SectionTitle")
        layout.addWidget(self.heading)

        self.intro = QLabel(self)
        self.intro.setWordWrap(True)
        self.intro.setProperty("variant", "muted")
        layout.addWidget(self.intro)

        self.table = QTableWidget(0, 3, self)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(44)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setHighlightSections(False)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)

        self.refresh_button = QPushButton(self)
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_button.clicked.connect(self.refresh)
        buttons.addWidget(self.refresh_button)

        self.close_button = QPushButton(self)
        self.close_button.setProperty("variant", "primary")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.clicked.connect(self.accept)
        buttons.addWidget(self.close_button)

        layout.addLayout(buttons)

        self.retranslate()
        translator.language_changed.connect(self.retranslate)
        self.refresh()

    def retranslate(self) -> None:
        self.setWindowTitle(tr("diag.title"))
        self.heading.setText(tr("diag.title"))
        self.intro.setText(tr("diag.intro"))
        self.refresh_button.setText(tr("diag.refresh"))
        self.close_button.setText(tr("diag.close"))
        self.table.setHorizontalHeaderLabels(
            [tr("diag.component"), tr("diag.status"), tr("diag.purpose")]
        )
        self.refresh()

    def refresh(self) -> None:
        detected = engines.detect_all(refresh=True)
        self.table.setRowCount(len(detected))

        for index, engine in enumerate(detected):
            name = QTableWidgetItem(engine.name)
            if engine.version:
                name.setToolTip(str(engine.version))
            self.table.setItem(index, 0, name)

            status = QTableWidgetItem(
                tr("diag.available") if engine.available else tr("diag.missing")
            )
            status.setData(Qt.ItemDataRole.UserRole, engine.available)
            if engine.path:
                status.setToolTip(engine.path)
            self.table.setItem(index, 1, status)

            purpose = engine.purpose
            if not engine.available and engine.install_hint:
                purpose = f"{purpose}\n{engine.install_hint}"
            detail = QTableWidgetItem(purpose)
            detail.setToolTip(purpose)
            self.table.setItem(index, 2, detail)

        self._colour_status_column()

    def _colour_status_column(self) -> None:
        """Tint the status cells using the active palette, not hard-coded hues."""
        from ..theme import LIGHT, resolve

        palette = resolve(getattr(self.parent(), "theme_preference", "system")) if self.parent() else LIGHT
        from PySide6.QtGui import QColor

        for index in range(self.table.rowCount()):
            item = self.table.item(index, 1)
            if item is None:
                continue
            available = bool(item.data(Qt.ItemDataRole.UserRole))
            item.setForeground(QColor(palette.success if available else palette.text_muted))
