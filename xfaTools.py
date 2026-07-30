"""Compatibility shim - ``XfaObj`` now lives in :mod:`xfatools.core.xfa`.

Existing scripts that do ``from xfaTools import XfaObj`` keep working.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from xfatools.core.xfa import XfaObj  # noqa: E402,F401

__all__ = ["XfaObj"]
