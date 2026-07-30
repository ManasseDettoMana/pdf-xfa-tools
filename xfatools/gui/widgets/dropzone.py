"""The drag-and-drop target shown when the queue is empty.

Accepts both files and folders.  Folders are walked recursively and filtered
against :func:`registry.supported_input_exts`, so dropping a project directory
picks up exactly the convertible files and silently ignores the rest - while
still reporting how many were skipped, because a silent drop looks like a bug.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr, translator
from ..theme import restyle

#: Refuse to walk a dropped folder beyond this many files, so dropping a whole
#: drive cannot freeze the interface.
MAX_FILES_PER_DROP = 500


class DropIcon(QWidget):
    """A small vector glyph: a document outline with a downward arrow.

    Drawn rather than shipped as an asset so it inherits the theme colours and
    stays crisp at any DPI without bundling image files.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(QSize(72, 72))
        self._colour = "#6B7482"

    def set_colour(self, colour: str) -> None:
        self._colour = colour
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(Qt.GlobalColor.gray)
        pen.setWidthF(2.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setColor(self.palette().windowText().color())
        painter.setPen(pen)

        w, h = self.width(), self.height()
        # Sheet outline with a folded corner.
        left, top = w * 0.22, h * 0.12
        right, bottom = w * 0.78, h * 0.72
        fold = w * 0.16

        painter.drawLine(left, top, right - fold, top)
        painter.drawLine(right - fold, top, right, top + fold)
        painter.drawLine(right, top + fold, right, bottom)
        painter.drawLine(right, bottom, left, bottom)
        painter.drawLine(left, bottom, left, top)
        painter.drawLine(right - fold, top, right - fold, top + fold)
        painter.drawLine(right - fold, top + fold, right, top + fold)

        # Downward arrow through the sheet.
        cx = w * 0.5
        painter.drawLine(cx, h * 0.30, cx, h * 0.60)
        painter.drawLine(cx, h * 0.60, cx - w * 0.10, h * 0.48)
        painter.drawLine(cx, h * 0.60, cx + w * 0.10, h * 0.48)
        painter.end()


class DropZone(QFrame):
    """Large empty-state panel inviting the user to add files."""

    files_dropped = Signal(list)  # list[Path]
    rejected = Signal(int)  # how many files were ignored

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setProperty("dragging", "false")
        self.setAcceptDrops(True)
        self.setMinimumHeight(280)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        self.icon = DropIcon(self)
        layout.addWidget(self.icon, alignment=Qt.AlignmentFlag.AlignCenter)

        self.title = QLabel(self)
        self.title.setObjectName("DropTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)

        self.subtitle = QLabel(self)
        self.subtitle.setObjectName("DropSubtitle")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.subtitle)

        buttons = QHBoxLayout()
        buttons.setAlignment(Qt.AlignmentFlag.AlignCenter)
        buttons.setSpacing(10)
        buttons.setContentsMargins(0, 14, 0, 0)

        self.browse_button = QPushButton(self)
        self.browse_button.setProperty("variant", "primary")
        self.browse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_button.clicked.connect(self.choose_files)
        buttons.addWidget(self.browse_button)

        self.folder_button = QPushButton(self)
        self.folder_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.folder_button.clicked.connect(self.choose_folder)
        buttons.addWidget(self.folder_button)

        layout.addLayout(buttons)

        self.retranslate()
        translator.language_changed.connect(self.retranslate)

    def retranslate(self) -> None:
        self.title.setText(tr("drop.title"))
        self.subtitle.setText(tr("drop.subtitle"))
        self.browse_button.setText(tr("drop.browse"))
        self.folder_button.setText(tr("drop.browse_folder"))

    # -- drag and drop ----------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_dragging(True)
            self.title.setText(tr("drop.active"))

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802
        self._set_dragging(False)
        self.title.setText(tr("drop.title"))

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self._set_dragging(False)
        self.title.setText(tr("drop.title"))

        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        accepted, rejected = collect_supported(paths)

        if accepted:
            self.files_dropped.emit(accepted)
        if rejected:
            self.rejected.emit(rejected)
        event.acceptProposedAction()

    def _set_dragging(self, active: bool) -> None:
        self.setProperty("dragging", "true" if active else "false")
        restyle(self)

    # -- browse buttons ---------------------------------------------------

    def choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("dialog.choose_files"), "", build_file_filter()
        )
        if paths:
            accepted, rejected = collect_supported([Path(p) for p in paths])
            if accepted:
                self.files_dropped.emit(accepted)
            if rejected:
                self.rejected.emit(rejected)

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("dialog.choose_folder"))
        if folder:
            accepted, rejected = collect_supported([Path(folder)])
            if accepted:
                self.files_dropped.emit(accepted)
            if rejected:
                self.rejected.emit(rejected)


# ---------------------------------------------------------------------------
# Shared helpers, used by the main window's drop handling too
# ---------------------------------------------------------------------------


def collect_supported(paths: list[Path]) -> tuple[list[Path], int]:
    """Expand folders and keep only convertible files.

    Returns the accepted paths (deduplicated, order preserved) and a count of
    everything that was skipped, so the caller can tell the user rather than
    letting files vanish without explanation.
    """
    from ...core import registry

    supported = set(registry.supported_input_exts())
    accepted: list[Path] = []
    seen: set[Path] = set()
    rejected = 0

    def consider(path: Path) -> None:
        nonlocal rejected
        if len(accepted) >= MAX_FILES_PER_DROP:
            return
        try:
            resolved = path.resolve()
        except OSError:
            rejected += 1
            return
        if resolved in seen:
            return
        if path.suffix.lstrip(".").lower() in supported:
            seen.add(resolved)
            accepted.append(path)
        else:
            rejected += 1

    for path in paths:
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if len(accepted) >= MAX_FILES_PER_DROP:
                    break
                if child.is_file():
                    consider(child)
        elif path.is_file():
            consider(path)
        else:
            rejected += 1

    return accepted, rejected


def build_file_filter() -> str:
    """A Qt file dialog filter listing every supported extension."""
    from ...core import registry

    patterns = " ".join(f"*.{ext}" for ext in registry.supported_input_exts())
    return f"{tr('drop.filter')} ({patterns});;{tr('drop.filter_all')} (*)"
