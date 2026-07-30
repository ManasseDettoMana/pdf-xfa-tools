"""Compatibility shim - superseded by XFA Studio.

Kept so existing habits and shortcuts keep working:

    python deco-unlock.py FILE.pdf [MORE.pdf ...]

Behaviour note: the unlocked PDF is now written next to the source file rather
than into the current working directory, matching every other operation in the
toolkit.

The equivalent modern commands are::

    python -m xfatools                      # the GUI
    python -m xfatools.cli unlock FILE.pdf  # the CLI
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> int:
    if len(sys.argv) == 1:
        from xfatools.__main__ import main as gui_main

        return gui_main()

    from xfatools.cli import main as cli_main

    print(
        "Nota: questo script e' deprecato, usa 'python -m xfatools.cli unlock'.",
        file=sys.stderr,
    )
    return cli_main(["unlock", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
