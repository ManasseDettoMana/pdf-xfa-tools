"""The file queue: one row per file, each with its own target format.

A mixed selection (a PDF and a PNG, say) shares no conversion, so the target
format belongs to the *row*, not to a single global dropdown.  Rows default to
the first conversion offered for their type and can be changed individually, or
for a whole selection at once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core import registry
from ...core.job import JobResult, JobStatus
from ...core.probe import PdfProfile
from ..i18n import tr, translator
from ..theme import restyle

COL_NAME = 0
COL_TYPE = 1
COL_TARGET = 2
COL_STATUS = 3

COLUMN_KEYS = {
    COL_NAME: "queue.header.name",
    COL_TYPE: "queue.header.type",
    COL_TARGET: "queue.header.target",
    COL_STATUS: "queue.header.status",
}

STATUS_KEYS = {
    JobStatus.PENDING: "status.pending",
    JobStatus.RUNNING: "status.running",
    JobStatus.DONE: "status.done",
    JobStatus.FAILED: "status.failed",
    JobStatus.CANCELLED: "status.cancelled",
    JobStatus.SKIPPED: "status.skipped",
}

STATUS_STATES = {
    JobStatus.DONE: "success",
    JobStatus.FAILED: "danger",
    JobStatus.SKIPPED: "warning",
    JobStatus.CANCELLED: "warning",
}


@dataclass
class QueueRow:
    """One queued file and everything currently known about it."""

    token: int
    path: Path
    profile: PdfProfile | None = None
    converter_id: str = ""
    status: JobStatus = JobStatus.PENDING
    result: JobResult | None = None
    options: dict = field(default_factory=dict)

    @property
    def type_label(self) -> str:
        if self.profile is not None:
            return tr(f"kind.{self.profile.kind.value}")
        return self.path.suffix.lstrip(".").upper() or tr("kind.unknown")


def human_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} GB"


class StatusCell(QWidget):
    """Progress bar plus a status line and, when relevant, a provenance badge."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(6)
        self.label = QLabel(tr("status.pending"), self)
        self.label.setProperty("variant", "muted")
        top.addWidget(self.label)

        self.badge = QLabel(self)
        self.badge.setVisible(False)
        top.addWidget(self.badge)
        top.addStretch(1)
        layout.addLayout(top)

        self.bar = QProgressBar(self)
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setVisible(False)
        layout.addWidget(self.bar)

    def set_status(self, status: JobStatus, detail: str = "") -> None:
        self.label.setText(detail or tr(STATUS_KEYS[status]))
        self.label.setProperty("variant", "muted" if status is JobStatus.PENDING else "")
        self.label.setProperty("state", STATUS_STATES.get(status, ""))
        restyle(self.label)

        running = status is JobStatus.RUNNING
        self.bar.setVisible(running)
        if not running:
            self.bar.setValue(0)
            self.bar.setRange(0, 100)

    def set_progress(self, completed: int, total: int, message: str) -> None:
        self.bar.setVisible(True)
        if total > 0:
            self.bar.setRange(0, total)
            self.bar.setValue(completed)
        else:
            # Unknown length: an indeterminate bar is honest, a fake percentage is not.
            self.bar.setRange(0, 0)
        if message:
            self.label.setText(message)

    def set_badge(self, badge: str) -> None:
        if not badge:
            self.badge.setVisible(False)
            return
        self.badge.setText(tr(f"badge.{badge}"))
        self.badge.setProperty("badge", badge)
        self.badge.setToolTip(tr(f"badge.{badge.lower()}.tooltip"))
        restyle(self.badge)
        self.badge.setVisible(True)


class QueueTable(QTableWidget):
    """The queue itself."""

    selection_changed = Signal(object)  # QueueRow or None
    rows_changed = Signal()
    open_requested = Signal(object)  # QueueRow
    reveal_requested = Signal(object)  # QueueRow

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, 4, parent)
        self._rows: dict[int, QueueRow] = {}
        self._next_token = 1
        self._cells: dict[int, StatusCell] = {}

        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(58)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.itemSelectionChanged.connect(self._emit_selection)

        # The name column absorbs the remaining width; the other three are sized
        # to fit their content so the four together never overflow into a
        # horizontal scrollbar at the minimum window width.
        header = self.horizontalHeader()
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_TYPE, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(COL_TARGET, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(90)
        self.setColumnWidth(COL_TYPE, 172)
        self.setColumnWidth(COL_TARGET, 200)
        self.setColumnWidth(COL_STATUS, 190)
        header.setHighlightSections(False)
        header.setStretchLastSection(False)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setWordWrap(False)

        self.retranslate()
        translator.language_changed.connect(self.retranslate)

    # -- translation ------------------------------------------------------

    def retranslate(self) -> None:
        self.setHorizontalHeaderLabels([tr(key) for key in COLUMN_KEYS.values()])
        for token, row in self._rows.items():
            index = self._index_of(token)
            if index is None:
                continue
            type_item = self.item(index, COL_TYPE)
            if type_item is not None:
                type_item.setText(row.type_label)
            combo = self.cellWidget(index, COL_TARGET)
            if isinstance(combo, QComboBox):
                self._fill_target_combo(combo, row)
            cell = self._cells.get(token)
            if cell is not None:
                cell.set_status(row.status)
                if row.result is not None:
                    self._apply_result_text(cell, row.result)

    # -- population -------------------------------------------------------

    def add_files(self, paths: list[Path]) -> list[QueueRow]:
        """Append files, skipping any already queued. Returns the new rows."""
        existing = {row.path.resolve() for row in self._rows.values()}
        added: list[QueueRow] = []

        for path in paths:
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if resolved in existing:
                continue
            existing.add(resolved)

            targets = registry.targets_for(path)
            if not targets:
                continue

            row = QueueRow(token=self._next_token, path=path, converter_id=targets[0].id)
            self._next_token += 1
            self._rows[row.token] = row
            self._append_row(row)
            added.append(row)

        if added:
            self.rows_changed.emit()
        return added

    def _append_row(self, row: QueueRow) -> None:
        index = self.rowCount()
        self.insertRow(index)

        name_item = QTableWidgetItem(row.path.name)
        name_item.setData(Qt.ItemDataRole.UserRole, row.token)
        try:
            size = human_size(row.path.stat().st_size)
        except OSError:
            size = ""
        name_item.setToolTip(f"{row.path}\n{size}" if size else str(row.path))
        self.setItem(index, COL_NAME, name_item)

        # PDFs are inspected on a worker thread, so the type starts as a
        # placeholder and is confirmed by set_profile() a moment later.
        pending = row.path.suffix.lower() == ".pdf"
        type_item = QTableWidgetItem(tr("queue.analysing") if pending else row.type_label)
        if pending:
            type_item.setForeground(self.palette().placeholderText())
        type_item.setToolTip(type_item.text())
        self.setItem(index, COL_TYPE, type_item)

        combo = QComboBox(self)
        combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fill_target_combo(combo, row)
        combo.currentIndexChanged.connect(
            lambda _index, token=row.token, box=combo: self._on_target_changed(token, box)
        )
        self.setCellWidget(index, COL_TARGET, combo)

        cell = StatusCell(self)
        self._cells[row.token] = cell
        self.setCellWidget(index, COL_STATUS, cell)

    def _fill_target_combo(self, combo: QComboBox, row: QueueRow) -> None:
        """Rebuild the dropdown, grouped by category, disabling what is missing."""
        combo.blockSignals(True)
        combo.clear()

        for category, converters in registry.categories_of(registry.targets_for(row.path)):
            combo.addItem(f"--- {registry.CATEGORY_LABELS[category]} ---")
            separator = combo.model().item(combo.count() - 1)
            separator.setEnabled(False)

            for converter in converters:
                combo.addItem(converter.label, converter.id)
                item = combo.model().item(combo.count() - 1)
                tooltip = converter.description
                if not converter.available:
                    item.setEnabled(False)
                    tooltip = f"{converter.unavailable_reason}"
                if tooltip:
                    combo.setItemData(combo.count() - 1, tooltip, Qt.ItemDataRole.ToolTipRole)

        position = combo.findData(row.converter_id)
        if position >= 0:
            combo.setCurrentIndex(position)
        combo.blockSignals(False)

    def _on_target_changed(self, token: int, combo: QComboBox) -> None:
        row = self._rows.get(token)
        if row is None:
            return
        converter_id = combo.currentData()
        if not converter_id:
            # A category header was selected; snap back to the previous choice.
            position = combo.findData(row.converter_id)
            if position >= 0:
                combo.setCurrentIndex(position)
            return
        row.converter_id = converter_id
        row.options = {}
        if self.currentRow() == self._index_of(token):
            self.selection_changed.emit(row)

    # -- updates from workers ---------------------------------------------

    def set_profile(self, token: int, profile: PdfProfile | None) -> None:
        row = self._rows.get(token)
        index = self._index_of(token)
        if row is None or index is None:
            return
        row.profile = profile
        item = self.item(index, COL_TYPE)
        if item is not None:
            item.setText(row.type_label)
            item.setToolTip(row.type_label)
            # Back to normal text colour: the value is now confirmed, not pending.
            item.setForeground(self.palette().text())

    def set_running(self, token: int) -> None:
        row = self._rows.get(token)
        cell = self._cells.get(token)
        if row is None or cell is None:
            return
        row.status = JobStatus.RUNNING
        cell.set_status(JobStatus.RUNNING)
        cell.set_badge("")

    def set_progress(self, token: int, completed: int, total: int, message: str) -> None:
        cell = self._cells.get(token)
        if cell is not None:
            cell.set_progress(completed, total, message)

    def set_result(self, token: int, result: JobResult) -> None:
        row = self._rows.get(token)
        cell = self._cells.get(token)
        if row is None or cell is None:
            return
        row.status = result.status
        row.result = result
        self._apply_result_text(cell, result)
        if self.currentRow() == self._index_of(token):
            self.selection_changed.emit(row)

    def _apply_result_text(self, cell: StatusCell, result: JobResult) -> None:
        detail = ""
        if result.status is JobStatus.DONE and result.outputs:
            count = len(result.outputs)
            detail = result.outputs[0].name if count == 1 else f"{count} file"
        elif result.message:
            detail = result.message if len(result.message) < 70 else result.message[:67] + "..."
        cell.set_status(result.status, detail)
        cell.set_badge(result.badge)
        if result.message:
            hint = f"\n{result.hint}" if result.hint else ""
            cell.setToolTip(f"{result.message}{hint}")
        elif result.outputs:
            cell.setToolTip("\n".join(str(p) for p in result.outputs))

    def reset_statuses(self) -> None:
        for token, row in self._rows.items():
            row.status = JobStatus.PENDING
            row.result = None
            cell = self._cells.get(token)
            if cell is not None:
                cell.set_status(JobStatus.PENDING)
                cell.set_badge("")
                cell.setToolTip("")

    # -- access -----------------------------------------------------------

    def rows(self) -> list[QueueRow]:
        return [self._rows[self.item(i, COL_NAME).data(Qt.ItemDataRole.UserRole)]
                for i in range(self.rowCount())
                if self.item(i, COL_NAME) is not None]

    def selected_rows(self) -> list[QueueRow]:
        tokens = {
            self.item(index.row(), COL_NAME).data(Qt.ItemDataRole.UserRole)
            for index in self.selectionModel().selectedRows()
            if self.item(index.row(), COL_NAME) is not None
        }
        return [row for token, row in self._rows.items() if token in tokens]

    def current_row_data(self) -> QueueRow | None:
        index = self.currentRow()
        if index < 0 or self.item(index, COL_NAME) is None:
            return None
        return self._rows.get(self.item(index, COL_NAME).data(Qt.ItemDataRole.UserRole))

    def is_empty(self) -> bool:
        return self.rowCount() == 0

    # -- removal ----------------------------------------------------------

    def remove_selected(self) -> None:
        for index in sorted((i.row() for i in self.selectionModel().selectedRows()), reverse=True):
            self._remove_index(index)
        self.rows_changed.emit()

    def clear_all(self) -> None:
        self.setRowCount(0)
        self._rows.clear()
        self._cells.clear()
        self.rows_changed.emit()
        self.selection_changed.emit(None)

    def _remove_index(self, index: int) -> None:
        item = self.item(index, COL_NAME)
        if item is not None:
            token = item.data(Qt.ItemDataRole.UserRole)
            self._rows.pop(token, None)
            self._cells.pop(token, None)
        self.removeRow(index)

    def _index_of(self, token: int) -> int | None:
        for index in range(self.rowCount()):
            item = self.item(index, COL_NAME)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == token:
                return index
        return None

    # -- interaction ------------------------------------------------------

    def _emit_selection(self) -> None:
        self.selection_changed.emit(self.current_row_data())

    def apply_target_to_selection(self, converter_id: str) -> None:
        """Set one target format across every selected row that supports it."""
        self.apply_target(converter_id, self.selected_rows())

    def apply_target(self, converter_id: str, rows: list[QueueRow] | None = None) -> int:
        """Set ``converter_id`` on every given row that supports it.

        Returns how many rows were changed.  Rows whose type has no such
        conversion are left alone rather than being silently broken.
        """
        changed = 0
        for row in self.rows() if rows is None else rows:
            if not any(c.id == converter_id for c in registry.targets_for(row.path)):
                continue
            row.converter_id = converter_id
            changed += 1
            index = self._index_of(row.token)
            if index is None:
                continue
            combo = self.cellWidget(index, COL_TARGET)
            if isinstance(combo, QComboBox):
                position = combo.findData(converter_id)
                if position >= 0:
                    combo.blockSignals(True)
                    combo.setCurrentIndex(position)
                    combo.blockSignals(False)
        return changed

    def _show_context_menu(self, position) -> None:
        row = self.current_row_data()
        if row is None:
            return

        menu = QMenu(self)
        if row.result is not None and row.result.outputs:
            open_action = menu.addAction(tr("queue.open_file"))
            open_action.triggered.connect(lambda: self.open_requested.emit(row))
            reveal_action = menu.addAction(tr("queue.open_folder"))
            reveal_action.triggered.connect(lambda: self.reveal_requested.emit(row))
            menu.addSeparator()
        remove_action = menu.addAction(tr("queue.remove"))
        remove_action.triggered.connect(self.remove_selected)
        menu.exec(self.viewport().mapToGlobal(position))

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Delete:
            self.remove_selected()
            return
        super().keyPressEvent(event)
