"""Entry point for ``python -m xfatools`` - launches the desktop application."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from .gui.app import run
    except ImportError as exc:
        # PySide6 is the only dependency that is plausibly absent (it is large,
        # and the CLI works fine without it), so fail with an actionable message
        # rather than a traceback.
        print(
            "Impossibile avviare l'interfaccia grafica: "
            f"{exc}\n\n"
            "Installa le dipendenze con:\n"
            "    python -m pip install -r requirements.txt\n\n"
            "In alternativa usa la riga di comando:\n"
            "    python -m xfatools.cli --help",
            file=sys.stderr,
        )
        return 1
    return run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
