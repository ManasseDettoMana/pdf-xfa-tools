"""Exception hierarchy shared by the whole toolkit.

Every error carries a message that is safe to show to an end user: the GUI puts
``str(exc)`` straight into the result panel, so no raw tracebacks or library
internals should leak through.
"""


class XfaToolsError(Exception):
    """Base class for every error this toolkit raises deliberately."""

    #: Optional hint shown under the error message in the GUI.
    hint: str | None = None

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        if hint is not None:
            self.hint = hint


class PdfOpenError(XfaToolsError):
    """The file could not be opened as a PDF (corrupt, missing, or encrypted)."""


class NoXfaError(XfaToolsError):
    """The PDF carries no XFA packets.

    This is the expected outcome for a flattened form: flattening *deletes* the
    XFA packets, so there is nothing left to recover.  Callers that want a
    best-effort XML should use the extraction fallback chain instead.
    """

    hint = (
        "Questo PDF non contiene pacchetti XFA (probabilmente e' stato appiattito). "
        "Usa la modalita' automatica per ottenere comunque un XML."
    )


class PacketNotFoundError(XfaToolsError):
    """The requested XFA packet name does not exist in this PDF."""


class ExtractionError(XfaToolsError):
    """No extraction strategy managed to produce an XML."""


class InjectionError(XfaToolsError):
    """The XML could not be written back into the PDF."""


class ConversionError(XfaToolsError):
    """A file conversion failed."""


class EngineMissingError(ConversionError):
    """The conversion needs an external engine that is not installed."""

    def __init__(self, engine: str, purpose: str, install_hint: str):
        super().__init__(
            f"'{engine}' non e' installato: richiesto per {purpose}.",
            hint=install_hint,
        )
        self.engine = engine


class CancelledError(XfaToolsError):
    """The user cancelled the job while it was running."""
