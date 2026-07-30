"""The application window.

Layout: a header carrying global controls, a body that swaps between the drop
zone and the file queue, a side panel showing options and results for the
selected row, and a footer holding the destination and the action buttons.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QDragEnterEvent, QDropEvent, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__
from ..core import registry
from ..core.job import Job
from .i18n import tr, translator
from .settings import Settings
from .theme import apply_theme
from .widgets.diagnostics import DiagnosticsDialog
from .widgets.dropzone import DropZone, collect_supported
from .widgets.options_panel import OptionsPanel, ResultPanel
from .widgets.queue_table import QueueTable
from .workers import JobRunner, summarise

SIDE_PANEL_WIDTH = 340


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.theme_preference = settings.theme

        self.runner = JobRunner(settings.worker_count(), self)
        self.runner.file_probed.connect(self._on_file_probed)
        self.runner.job_progress.connect(self._on_job_progress)
        self.runner.job_finished.connect(self._on_job_finished)
        self.runner.batch_progress.connect(self._on_batch_progress)
        self.runner.batch_finished.connect(self._on_batch_finished)

        self.setAcceptDrops(True)
        self.setMinimumSize(1040, 680)
        self.resize(1180, 760)

        self._build_ui()
        self._build_shortcuts()
        self.retranslate()
        translator.language_changed.connect(self.retranslate)
        self._update_action_state()

    # -- construction -----------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        body = QWidget(central)
        body.setObjectName("Content")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(18, 16, 18, 12)
        body_layout.setSpacing(16)

        self.stack = QStackedWidget(body)
        self.drop_zone = DropZone(self.stack)
        self.drop_zone.files_dropped.connect(self.add_files)
        self.drop_zone.rejected.connect(self._report_rejected)
        self.queue = QueueTable(self.stack)
        self.queue.selection_changed.connect(self._on_selection_changed)
        self.queue.rows_changed.connect(self._on_rows_changed)
        self.queue.open_requested.connect(lambda row: self._open_result(row.result))
        self.queue.reveal_requested.connect(lambda row: self._reveal_result(row.result))
        self.stack.addWidget(self.drop_zone)
        self.stack.addWidget(self.queue)
        body_layout.addWidget(self.stack, 1)

        side = QWidget(body)
        side.setFixedWidth(SIDE_PANEL_WIDTH)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(12)

        self.options_panel = OptionsPanel(side)
        self.options_panel.options_changed.connect(self._on_options_changed)
        self.options_panel.apply_to_all_requested.connect(self._apply_to_all)
        side_layout.addWidget(self.options_panel, 1)

        self.result_panel = ResultPanel(side)
        self.result_panel.open_file_requested.connect(self._open_result)
        self.result_panel.open_folder_requested.connect(self._reveal_result)
        side_layout.addWidget(self.result_panel)

        body_layout.addWidget(side)
        root.addWidget(body, 1)
        root.addWidget(self._build_footer())

        self.setCentralWidget(central)
        self.stack.setCurrentWidget(self.drop_zone)

    def _build_header(self) -> QFrame:
        header = QFrame(self)
        header.setObjectName("Header")
        header.setFixedHeight(66)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 10, 16, 10)
        layout.setSpacing(10)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.app_title = QLabel(APP_NAME, header)
        self.app_title.setObjectName("AppTitle")
        titles.addWidget(self.app_title)
        self.app_subtitle = QLabel(header)
        self.app_subtitle.setObjectName("AppSubtitle")
        titles.addWidget(self.app_subtitle)
        layout.addLayout(titles)

        layout.addStretch(1)

        self.language_combo = QComboBox(header)
        self.language_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        for code, name in translator.available():
            self.language_combo.addItem(name, code)
        position = self.language_combo.findData(translator.language)
        if position >= 0:
            self.language_combo.setCurrentIndex(position)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        layout.addWidget(self.language_combo)

        self.theme_button = QPushButton(header)
        self.theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_button.clicked.connect(self.toggle_theme)
        layout.addWidget(self.theme_button)

        self.diagnostics_button = QPushButton(header)
        self.diagnostics_button.setProperty("variant", "ghost")
        self.diagnostics_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.diagnostics_button.clicked.connect(self.show_diagnostics)
        layout.addWidget(self.diagnostics_button)

        self.about_button = QPushButton(header)
        self.about_button.setProperty("variant", "ghost")
        self.about_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.about_button.clicked.connect(self.show_about)
        layout.addWidget(self.about_button)

        return header

    def _build_footer(self) -> QFrame:
        footer = QFrame(self)
        footer.setObjectName("Footer")
        footer.setFixedHeight(72)

        layout = QHBoxLayout(footer)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(10)

        self.output_label = QLabel(footer)
        self.output_label.setProperty("variant", "muted")
        layout.addWidget(self.output_label)

        self.output_combo = QComboBox(footer)
        self.output_combo.setMinimumWidth(230)
        self.output_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.output_combo.currentIndexChanged.connect(self._on_output_mode_changed)
        layout.addWidget(self.output_combo)

        self.choose_folder_button = QPushButton(footer)
        self.choose_folder_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.choose_folder_button.clicked.connect(self.choose_output_folder)
        layout.addWidget(self.choose_folder_button)

        layout.addStretch(1)

        self.status_label = QLabel(footer)
        self.status_label.setProperty("variant", "muted")
        layout.addWidget(self.status_label)

        self.clear_button = QPushButton(footer)
        self.clear_button.setProperty("variant", "ghost")
        self.clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_button.clicked.connect(self.queue.clear_all)
        layout.addWidget(self.clear_button)

        self.cancel_button = QPushButton(footer)
        self.cancel_button.setProperty("variant", "danger")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.runner.cancel)
        layout.addWidget(self.cancel_button)

        self.convert_button = QPushButton(footer)
        self.convert_button.setProperty("variant", "primary")
        self.convert_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.convert_button.setMinimumWidth(160)
        self.convert_button.clicked.connect(self.start_conversion)
        layout.addWidget(self.convert_button)

        return footer

    def _build_shortcuts(self) -> None:
        open_action = QAction(self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.drop_zone.choose_files)
        self.addAction(open_action)

        convert_action = QAction(self)
        convert_action.setShortcut(QKeySequence("Ctrl+Return"))
        convert_action.triggered.connect(self.start_conversion)
        self.addAction(convert_action)

        theme_action = QAction(self)
        theme_action.setShortcut(QKeySequence("Ctrl+T"))
        theme_action.triggered.connect(self.toggle_theme)
        self.addAction(theme_action)

    # -- translation ------------------------------------------------------

    def retranslate(self) -> None:
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.app_subtitle.setText(tr("app.subtitle"))
        self.language_combo.setToolTip(tr("header.language.tooltip"))
        self.diagnostics_button.setText(tr("header.diagnostics"))
        self.diagnostics_button.setToolTip(tr("header.diagnostics.tooltip"))
        self.about_button.setText(tr("header.about"))
        self.theme_button.setToolTip(tr("header.theme.tooltip"))
        self._update_theme_button()

        self.output_label.setText(tr("footer.output"))
        current_mode = self.output_combo.currentData() or self.settings.output_mode
        self.output_combo.blockSignals(True)
        self.output_combo.clear()
        self.output_combo.addItem(tr("footer.output.beside"), "beside_source")
        custom_text = self.settings.output_dir or tr("footer.output.custom")
        self.output_combo.addItem(custom_text, "custom")
        position = self.output_combo.findData(current_mode)
        self.output_combo.setCurrentIndex(max(0, position))
        self.output_combo.blockSignals(False)

        self.choose_folder_button.setText(tr("footer.choose_folder"))
        self.clear_button.setText(tr("footer.clear"))
        self.cancel_button.setText(tr("footer.cancel"))
        self._update_convert_button()
        self._update_status_label()

    def _update_theme_button(self) -> None:
        from .theme import resolve

        is_dark = resolve(self.theme_preference).is_dark
        self.theme_button.setText(
            tr("header.theme.light") if is_dark else tr("header.theme.dark")
        )

    def _update_convert_button(self) -> None:
        count = len(self.queue.rows())
        self.convert_button.setText(
            tr("footer.convert_count", count=count) if count else tr("footer.convert")
        )

    def _update_status_label(self) -> None:
        count = len(self.queue.rows())
        if self.runner.running:
            return
        if count == 0:
            self.status_label.setText("")
        elif count == 1:
            self.status_label.setText(tr("queue.count_one"))
        else:
            self.status_label.setText(tr("queue.count", count=count))

    # -- file intake ------------------------------------------------------

    def add_files(self, paths: list[Path]) -> None:
        added = self.queue.add_files(paths)
        for row in added:
            self.settings.remember_file(row.path)
            if row.path.suffix.lower() == ".pdf":
                self.runner.probe(row.token, row.path)
        if added and self.queue.currentRow() < 0:
            self.queue.selectRow(0)

    def _report_rejected(self, count: int) -> None:
        if count:
            self.status_label.setText(tr("drop.rejected", count=count))

    def _on_rows_changed(self) -> None:
        empty = self.queue.is_empty()
        self.stack.setCurrentWidget(self.drop_zone if empty else self.queue)
        self._update_action_state()
        self._update_convert_button()
        self._update_status_label()

    def _on_file_probed(self, token: int, profile) -> None:
        self.queue.set_profile(token, profile)

    # -- selection and options -------------------------------------------

    def _on_selection_changed(self, row) -> None:
        if row is None:
            self.options_panel.show_converter(None, {})
            self.result_panel.show_result(None)
            return
        try:
            converter = registry.get(row.converter_id)
        except Exception:
            converter = None
        self.options_panel.show_converter(converter, row.options)
        self.result_panel.show_result(row.result)

    def _on_options_changed(self, values: dict) -> None:
        row = self.queue.current_row_data()
        if row is not None:
            row.options = values

    def _apply_to_all(self, converter_id: str, values: dict) -> None:
        """Give every row of a compatible type the same target and options."""
        changed = self.queue.apply_target(converter_id)
        for row in self.queue.rows():
            if row.converter_id == converter_id:
                row.options = dict(values)
        if changed:
            self.status_label.setText(tr("queue.count", count=changed))

    # -- output destination ----------------------------------------------

    def _on_output_mode_changed(self, _index: int) -> None:
        mode = self.output_combo.currentData()
        if mode == "custom" and not self.settings.output_dir:
            if not self.choose_output_folder():
                self.output_combo.blockSignals(True)
                self.output_combo.setCurrentIndex(0)
                self.output_combo.blockSignals(False)
                return
        self.settings.output_mode = mode or "beside_source"
        self.settings.save()

    def choose_output_folder(self) -> bool:
        folder = QFileDialog.getExistingDirectory(
            self, tr("dialog.choose_output"), self.settings.output_dir or ""
        )
        if not folder:
            return False
        self.settings.output_dir = folder
        self.settings.output_mode = "custom"
        self.settings.save()
        self.retranslate()
        return True

    # -- conversion -------------------------------------------------------

    def start_conversion(self) -> None:
        rows = self.queue.rows()
        if not rows:
            QMessageBox.information(self, tr("error.title"), tr("error.nothing_to_do"))
            return
        if self.runner.running:
            return

        self.queue.reset_statuses()
        jobs: list[tuple[int, Job]] = []
        for row in rows:
            self.queue.set_running(row.token)
            jobs.append(
                (
                    row.token,
                    Job(
                        source=row.path,
                        target_format=row.converter_id,
                        options=dict(row.options),
                        output_dir=self.settings.resolved_output_dir(row.path),
                    ),
                )
            )

        self._update_action_state(running=True)
        self.runner.start(jobs)

    def _on_job_progress(self, token: int, completed: int, total: int, message: str) -> None:
        self.queue.set_progress(token, completed, total, message)

    def _on_job_finished(self, token: int, result) -> None:
        self.queue.set_result(token, result)

    def _on_batch_progress(self, completed: int, total: int) -> None:
        self.status_label.setText(tr("footer.progress", done=completed, total=total))

    def _on_batch_finished(self, results: list) -> None:
        ok, failed, _skipped = summarise(results)
        if failed == 0 and ok:
            self.status_label.setText(tr("result.summary_ok", count=ok))
        elif ok:
            self.status_label.setText(tr("result.summary_mixed", ok=ok, failed=failed))
        else:
            self.status_label.setText(tr("result.summary_failed"))

        self._update_action_state(running=False)
        self.settings.save()
        self._on_selection_changed(self.queue.current_row_data())

    def _update_action_state(self, running: bool | None = None) -> None:
        if running is None:
            running = self.runner.running
        has_rows = not self.queue.is_empty()

        self.convert_button.setEnabled(has_rows and not running)
        self.clear_button.setEnabled(has_rows and not running)
        self.cancel_button.setVisible(running)
        self.output_combo.setEnabled(not running)
        self.choose_folder_button.setEnabled(not running)
        self.queue.setEnabled(True)

    # -- results ----------------------------------------------------------

    def _open_result(self, result) -> None:
        if result is not None and result.primary_output:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(result.primary_output)))

    def _reveal_result(self, result) -> None:
        """Open the containing folder, selecting the file where the OS allows."""
        if result is None or not result.primary_output:
            return
        target = Path(result.primary_output)
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(target)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(target)])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.parent)))

    # -- global controls --------------------------------------------------

    def toggle_theme(self) -> None:
        from PySide6.QtWidgets import QApplication

        from .theme import resolve

        currently_dark = resolve(self.theme_preference).is_dark
        self.theme_preference = "light" if currently_dark else "dark"
        self.settings.theme = self.theme_preference
        self.settings.save()

        apply_theme(QApplication.instance(), self.theme_preference)
        self._update_theme_button()

    def _on_language_changed(self, _index: int) -> None:
        code = self.language_combo.currentData()
        if code:
            translator.set_language(code)
            self.settings.language = code
            self.settings.save()

    def show_diagnostics(self) -> None:
        DiagnosticsDialog(self).exec()

    def show_about(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(tr("about.title"))
        box.setText(f"{APP_NAME}\n{tr('about.version', version=__version__)}")
        box.setInformativeText(
            f"{tr('about.description')}\n\n{tr('about.note_flattened')}"
        )
        box.setIcon(QMessageBox.Icon.NoIcon)
        box.exec()

    # -- window-level drag and drop ---------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        accepted, rejected = collect_supported(paths)
        if accepted:
            self.add_files(accepted)
        if rejected:
            self._report_rejected(rejected)
        event.acceptProposedAction()

    # -- lifecycle --------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.runner.running:
            answer = QMessageBox.question(
                self,
                tr("dialog.close_running.title"),
                tr("dialog.close_running.body"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        # Unconditional: probe workers are not part of a batch, so "not running"
        # does not mean the pool is idle. Letting them outlive the window means
        # emitting into a destroyed object.
        self.runner.shutdown()
        self.settings.save()
        event.accept()
