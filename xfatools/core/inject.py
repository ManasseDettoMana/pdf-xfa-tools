"""Write an edited XML back into a PDF's XFA packet.

This closes the round-trip that the original toolkit was missing: extract the
``datasets`` packet, edit it (by hand or in LiveCycle Designer), then push it
back into the PDF.  The XML is validated before anything is written, and the
result is always saved to a *new* file so the source PDF is never damaged.
"""

from __future__ import annotations

from pathlib import Path

import pikepdf

from .errors import InjectionError, NoXfaError
from .extract import rewrap_datasets
from .xfa import XfaObj

#: Packets we allow writing to. ``template`` is included because unlocking and
#: layout tweaks legitimately need it, but it is far easier to corrupt.
WRITABLE_PACKETS = ("datasets", "template", "config", "localeSet")


def validate_xml(xml: str) -> None:
    """Reject malformed XML before it can corrupt a PDF."""
    try:
        from lxml import etree

        etree.fromstring(xml.encode("utf-8"))
    except ImportError:  # pragma: no cover - lxml is a hard dependency
        import xml.etree.ElementTree as ET

        try:
            ET.fromstring(xml)
        except ET.ParseError as exc:
            raise InjectionError(f"XML non valido: {exc}") from exc
    except Exception as exc:
        raise InjectionError(f"XML non valido: {exc}") from exc


def _prepare_datasets_payload(xml: str) -> str:
    """Accept either a full ``<xfa:datasets>`` packet or a sample-data file."""
    stripped = xml.lstrip()
    if stripped.startswith("<?xml"):
        stripped = stripped.split("?>", 1)[1].lstrip()

    if stripped.startswith("<xfa:datasets"):
        return stripped
    if stripped.startswith("<xfa:data"):
        return rewrap_datasets(stripped)
    raise InjectionError(
        "L'XML deve avere come radice <xfa:data> (sample data file) oppure "
        "<xfa:datasets> (pacchetto XFA completo)."
    )


def inject_xml(
    pdf_path: str | Path,
    xml: str | Path,
    packet: str = "datasets",
    out_path: str | Path | None = None,
) -> Path:
    """Write ``xml`` into ``packet`` of ``pdf_path`` and save a new PDF.

    ``xml`` may be the XML text itself or a path to an ``.xml`` file.  Returns
    the path of the PDF that was written (``<name>_updated.pdf`` by default).
    """
    pdf_path = Path(pdf_path)

    if isinstance(xml, Path) or (isinstance(xml, str) and not xml.lstrip().startswith("<")):
        xml_path = Path(xml)
        if not xml_path.exists():
            raise InjectionError(f"File XML non trovato: {xml_path}")
        xml_text = xml_path.read_text(encoding="utf-8")
    else:
        xml_text = str(xml)

    if packet not in WRITABLE_PACKETS:
        raise InjectionError(
            f"Pacchetto '{packet}' non scrivibile. Consentiti: {', '.join(WRITABLE_PACKETS)}."
        )

    validate_xml(xml_text)
    payload = _prepare_datasets_payload(xml_text) if packet == "datasets" else xml_text

    out_path = Path(out_path) if out_path else pdf_path.with_name(f"{pdf_path.stem}_updated.pdf")

    with pikepdf.Pdf.open(str(pdf_path)) as pdf:
        try:
            xfa = XfaObj(pdf)
        except NoXfaError as exc:
            raise InjectionError(
                f"'{pdf_path.name}' non e' un modulo XFA: non c'e' nessun pacchetto in cui "
                "scrivere l'XML.",
                hint="L'iniezione funziona solo su PDF che conservano i pacchetti XFA.",
            ) from exc

        if not xfa.has(packet):
            raise InjectionError(
                f"Il PDF non contiene il pacchetto '{packet}'. "
                f"Disponibili: {', '.join(xfa.packet_names)}."
            )

        xfa[packet] = payload
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pdf.save(str(out_path))

    return out_path
