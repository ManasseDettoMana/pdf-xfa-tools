"""PySide6 presentation layer.

Depends on :mod:`xfatools.core`, never the reverse.  Nothing here should contain
conversion logic: widgets collect intent, workers hand it to the core, and the
core hands back results to display.
"""
