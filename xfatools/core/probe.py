"""Inspect a PDF and report what kinds of data can be pulled out of it.

The profile produced here is what drives the extraction fallback chain and what
the GUI shows in the file queue ("Dynamic XFA", "AcroForm", "Scanned"...).  It is
cheap: it opens the PDF once, never rasterises anything, and samples the text
layer of at most :data:`TEXT_SAMPLE_PAGES` pages.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import pikepdf

from .errors import PdfOpenError
from .xfa import XfaObj

#: How many pages to sample when measuring the text layer.
TEXT_SAMPLE_PAGES = 3

#: Below this many characters per sampled page we consider the page image-only.
TEXT_DENSITY_THRESHOLD = 40


class PdfKind(str, Enum):
    """Coarse classification shown to the user."""

    DYNAMIC_XFA = "dynamic_xfa"
    STATIC_XFA = "static_xfa"
    ACROFORM = "acroform"
    TEXT = "text"
    SCANNED = "scanned"
    UNKNOWN = "unknown"


#: Human-readable labels, keyed by kind. The GUI translates these via i18n keys
#: of the form ``kind.<value>``; the English text here is the fallback.
KIND_LABELS = {
    PdfKind.DYNAMIC_XFA: "Dynamic XFA form",
    PdfKind.STATIC_XFA: "Static XFA form",
    PdfKind.ACROFORM: "AcroForm (standard PDF form)",
    PdfKind.TEXT: "Flattened / text PDF",
    PdfKind.SCANNED: "Scanned PDF (no text layer)",
    PdfKind.UNKNOWN: "Unknown",
}


@dataclass
class PdfProfile:
    """Everything we learned about a PDF in one pass."""

    path: Path
    page_count: int = 0
    encrypted: bool = False
    xfa_packets: list[str] = field(default_factory=list)
    has_xfa_data: bool = False
    needs_rendering: bool = False
    acroform_field_count: int = 0
    text_chars_per_page: float = 0.0
    warnings: list[str] = field(default_factory=list)

    @property
    def has_xfa(self) -> bool:
        return bool(self.xfa_packets)

    @property
    def has_acroform(self) -> bool:
        return self.acroform_field_count > 0

    @property
    def has_text_layer(self) -> bool:
        return self.text_chars_per_page >= TEXT_DENSITY_THRESHOLD

    @property
    def kind(self) -> PdfKind:
        if self.has_xfa:
            return PdfKind.DYNAMIC_XFA if self.needs_rendering else PdfKind.STATIC_XFA
        if self.has_acroform:
            return PdfKind.ACROFORM
        if self.has_text_layer:
            return PdfKind.TEXT
        if self.page_count:
            return PdfKind.SCANNED
        return PdfKind.UNKNOWN

    @property
    def label(self) -> str:
        return KIND_LABELS[self.kind]


def _count_acroform_fields(pdf: pikepdf.Pdf) -> int:
    """Count terminal form fields, recursing through ``/Kids`` hierarchies."""
    try:
        fields = pdf.Root.AcroForm.Fields
    except (AttributeError, KeyError):
        return 0

    count = 0
    seen: set[int] = set()

    def walk(nodes) -> None:
        nonlocal count
        for node in nodes:
            with contextlib.suppress(Exception):
                # Guard against cyclic /Kids graphs in malformed PDFs.
                key = id(node)
                if key in seen:
                    continue
                seen.add(key)
                kids = node.get("/Kids") if hasattr(node, "get") else None
                # A node with kids that are themselves fields is not terminal;
                # kids that are only widget annotations still count as one field.
                if kids is not None and any("/T" in kid for kid in kids):
                    walk(kids)
                else:
                    count += 1

    with contextlib.suppress(Exception):
        walk(fields)
    return count


def _measure_text(path: Path, page_count: int) -> tuple[float, list[str]]:
    """Return average characters per sampled page, plus any warnings."""
    warnings: list[str] = []
    try:
        import pdfplumber
    except ImportError:  # pragma: no cover - pdfplumber is a hard dependency
        return 0.0, ["pdfplumber non disponibile: impossibile misurare il testo."]

    sample = min(TEXT_SAMPLE_PAGES, page_count) or 1
    total = 0
    measured = 0
    try:
        with pdfplumber.open(str(path)) as doc:
            for page in doc.pages[:sample]:
                total += len(page.extract_text() or "")
                measured += 1
    except Exception as exc:
        warnings.append(f"Analisi del testo non riuscita: {exc}")
        return 0.0, warnings

    return (total / measured if measured else 0.0), warnings


def probe_pdf(path: str | Path) -> PdfProfile:
    """Open ``path`` once and describe what can be extracted from it."""
    path = Path(path)
    profile = PdfProfile(path=path)

    try:
        pdf = pikepdf.Pdf.open(str(path))
    except pikepdf.PasswordError as exc:
        raise PdfOpenError(
            f"'{path.name}' e' protetto da password: impossibile aprirlo.",
            hint="Rimuovi la protezione con Acrobat, poi riprova.",
        ) from exc
    except Exception as exc:
        raise PdfOpenError(f"Impossibile aprire '{path.name}' come PDF: {exc}") from exc

    with pdf:
        profile.page_count = len(pdf.pages)
        profile.encrypted = pdf.is_encrypted

        with contextlib.suppress(AttributeError, KeyError):
            profile.needs_rendering = bool(pdf.Root.NeedsRendering)

        try:
            xfa = XfaObj(pdf)
            profile.xfa_packets = xfa.packet_names
            profile.has_xfa_data = xfa.data_packet_name() is not None
        except Exception:
            # No XFA is a normal, expected state - not a warning.
            pass

        profile.acroform_field_count = _count_acroform_fields(pdf)

    density, warnings = _measure_text(path, profile.page_count)
    profile.text_chars_per_page = density
    profile.warnings.extend(warnings)

    return profile
