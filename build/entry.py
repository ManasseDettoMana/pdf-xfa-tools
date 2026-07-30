"""Entry point for the frozen executable.

Deliberately separate from ``xfatools/__main__.py``: PyInstaller runs its entry
script as top-level ``__main__`` with no package context, so the relative import
that ``__main__.py`` uses ("from .gui.app import run") fails inside the bundle
and the application exits immediately. This module uses absolute imports only.

``python -m xfatools`` still goes through ``xfatools/__main__.py``.

A windowed build has no console, so anything printed to stderr during startup is
lost and a failure looks like the program simply not opening. Any exception that
escapes is therefore written to a log file and shown in a message box.
"""

from __future__ import annotations

import sys
import traceback
from datetime import datetime


def _log_path():
    from pathlib import Path

    try:
        from xfatools.gui.settings import config_dir

        return config_dir() / "startup-error.log"
    except Exception:
        return Path.home() / "XfaStudio-startup-error.log"


def _report(exc: BaseException) -> None:
    """Record a startup failure where the user can actually find it."""
    details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    stamp = datetime.now().isoformat(timespec="seconds")
    target = _log_path()

    try:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(f"\n===== {stamp} =====\n{details}")
    except OSError:
        target = None

    message = (
        "XFA Studio non e' riuscito ad avviarsi.\n\n"
        f"{type(exc).__name__}: {exc}"
    )
    if target is not None:
        message += f"\n\nDettagli in:\n{target}"

    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance() or QApplication([])  # noqa: F841
        QMessageBox.critical(None, "XFA Studio", message)
    except Exception:
        # Qt itself may be what failed; stderr is better than nothing.
        print(message, file=sys.stderr)


def main() -> int:
    try:
        from xfatools.gui.app import run

        return run(sys.argv)
    except Exception as exc:
        _report(exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
