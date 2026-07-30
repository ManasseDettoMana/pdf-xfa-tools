"""Application bootstrap: create the QApplication, apply theme and language, run."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from .. import APP_NAME, __version__
from .i18n import translator
from .main_window import MainWindow
from .settings import Settings
from .theme import apply_theme


def run(argv: list[str] | None = None) -> int:
    """Start the desktop application and block until it closes."""
    argv = list(argv or sys.argv)

    # Qt reads its own switches out of argv; keep only the program name plus any
    # file paths, which we treat as files to enqueue at startup.
    app = QApplication(argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_NAME)
    # Standard style, so our stylesheet renders identically on every Windows
    # build rather than inheriting the native theme's metrics.
    app.setStyle("Fusion")

    settings = Settings.load()

    translator.set_language(settings.language or translator.detect_system_language())
    apply_theme(app, settings.theme)

    window = MainWindow(settings)
    window.show()

    startup_files = _existing_paths(argv[1:])
    if startup_files:
        window.add_files(startup_files)

    return app.exec()


def _existing_paths(arguments: list[str]) -> list:
    """Files passed on the command line, so 'Open with' and drag-onto-exe work."""
    from pathlib import Path

    from .widgets.dropzone import collect_supported

    candidates = [Path(a) for a in arguments if not a.startswith("-")]
    existing = [p for p in candidates if p.exists()]
    if not existing:
        return []
    accepted, _rejected = collect_supported(existing)
    return accepted


def enable_high_dpi() -> None:
    """Opt into per-monitor DPI awareness before the QApplication exists.

    Qt 6 scales automatically; this only pins the rounding policy so a 125% or
    150% display does not produce half-pixel borders in the stylesheet.
    """
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )


enable_high_dpi()
