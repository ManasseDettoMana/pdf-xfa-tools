"""GUI-agnostic engine: PDF/XFA handling, extraction, injection and conversion.

Nothing in this package may import PySide6.  The GUI depends on the core, never
the other way round - that is what keeps the CLI, the tests and the packaged
application all running the exact same code paths.
"""
