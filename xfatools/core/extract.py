"""Get an XML out of any PDF, and be honest about where it came from.

Four strategies, tried in descending order of fidelity:

===============  ==========================================  ==============
Strategy         Source                                      Confidence
===============  ==========================================  ==============
``xfa``          the XFA ``datasets`` packet                  EXACT
``acroform``     ``/AcroForm`` field values                   EXACT
``text``         the text layer, with positions               HEURISTIC
``ocr``          Tesseract over rasterised pages              LOW
===============  ==========================================  ==============

The first two read data the form actually stores, so the XML *is* the form's
data.  The last two *reconstruct* an XML from rendered output - useful, but a
guess.  :class:`ExtractResult` always reports which one ran so the GUI can badge
it and the user is never misled.

Note on flattened PDFs: flattening deletes the XFA packets outright.  Neither
this tool nor Acrobat Pro can recover the original XFA XML from a flattened
file - strategies 3 and 4 exist precisely because recovery is impossible and a
reconstruction is the best that can be offered.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import pikepdf

from .errors import CancelledError, ExtractionError, NoXfaError, PdfOpenError
from .job import NULL_CONTEXT, JobContext
from .probe import PdfProfile, probe_pdf
from .xfa import XfaObj, safe_packet_filename

XFA_DATA_NS = "http://www.xfa.org/schema/xfa-data/1.0/"
XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>\n'

#: DPI used when rasterising pages for OCR. 300 is the sweet spot for Tesseract.
OCR_DPI = 300

#: Default ceiling on pages processed by the reconstruction strategies.
#: A 1300-page reference manual would otherwise produce a multi-megabyte XML and
#: block for minutes; the caller can always raise or remove the limit.
DEFAULT_MAX_PAGES = 100


class ExtractSource(str, Enum):
    XFA = "xfa"
    ACROFORM = "acroform"
    TEXT = "text"
    OCR = "ocr"


class Confidence(str, Enum):
    EXACT = "exact"
    HEURISTIC = "heuristic"
    LOW = "low"


#: What the badge in the GUI says, per source.
SOURCE_LABELS = {
    ExtractSource.XFA: ("EXACT", "XFA datasets packet"),
    ExtractSource.ACROFORM: ("EXACT", "AcroForm field values"),
    ExtractSource.TEXT: ("HEURISTIC", "Text layer + layout"),
    ExtractSource.OCR: ("OCR", "Optical character recognition"),
}

CONFIDENCE_BY_SOURCE = {
    ExtractSource.XFA: Confidence.EXACT,
    ExtractSource.ACROFORM: Confidence.EXACT,
    ExtractSource.TEXT: Confidence.HEURISTIC,
    ExtractSource.OCR: Confidence.LOW,
}


@dataclass
class ExtractResult:
    """An XML plus the provenance needed to judge how much to trust it."""

    xml: str
    source: ExtractSource
    confidence: Confidence
    warnings: list[str] = field(default_factory=list)
    profile: PdfProfile | None = None
    field_count: int = 0

    @property
    def badge(self) -> str:
        return SOURCE_LABELS[self.source][0]

    @property
    def source_description(self) -> str:
        return SOURCE_LABELS[self.source][1]

    @property
    def is_exact(self) -> bool:
        return self.confidence is Confidence.EXACT

    def write(self, out_path: str | Path) -> Path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(self.xml, encoding="utf-8")
        return out_path


# ---------------------------------------------------------------------------
# Strategy 1: the XFA datasets packet
# ---------------------------------------------------------------------------


def unwrap_datasets(raw: str) -> str:
    """Convert an XFA ``datasets`` packet into a LiveCycle *sample data file*.

    Turns ``<xfa:datasets><xfa:data>...</xfa:data></xfa:datasets>`` into a
    document rooted at ``<xfa:data>``, hoisting the ``xmlns:xfa`` declaration
    onto it.  The transformation is deliberately textual rather than DOM-based:
    re-serialising through a parser would reflow whitespace and reorder
    attributes, and LiveCycle Designer is picky about the result.

    Preserved byte-for-byte from the original ``xfa-extract-data.py`` so existing
    outputs keep matching.
    """
    head_match = re.match(r"^<xfa:datasets\s+([^>]*?)\s*\n?>\s*<xfa:data(\s[^>]*)?\n?>", raw)
    tail_match = re.search(r"</xfa:data\s*\n?>\s*</xfa:datasets\s*\n?>\s*$", raw)

    if not head_match or not tail_match:
        raise ExtractionError(
            "Struttura del packet 'datasets' inattesa: impossibile rimuovere il wrapper "
            "<xfa:datasets>."
        )

    xmlns_attrs = head_match.group(1).strip()
    data_attrs = (head_match.group(2) or "").strip()
    new_head = f'<xfa:data {xmlns_attrs}{(" " + data_attrs) if data_attrs else ""}\n>'

    body = raw[head_match.end() : tail_match.start()]
    new_tail = "</xfa:data\n>"

    return new_head + body + new_tail


def rewrap_datasets(sample_data_xml: str) -> str:
    """Inverse of :func:`unwrap_datasets` - restore the ``<xfa:datasets>`` wrapper.

    Used by :mod:`xfatools.core.inject` to put an edited sample-data file back
    into a PDF.
    """
    body = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", sample_data_xml)

    head_match = re.match(r"^<xfa:data\s+([^>]*?)\s*\n?>", body)
    tail_match = re.search(r"</xfa:data\s*\n?>\s*$", body)
    if not head_match or not tail_match:
        raise ExtractionError(
            "L'XML non ha la radice <xfa:data> attesa per un sample data file."
        )

    attrs = head_match.group(1).strip()
    inner = body[head_match.end() : tail_match.start()]
    return f"<xfa:datasets {attrs}\n><xfa:data\n>{inner}</xfa:data\n></xfa:datasets\n>"


def extract_xfa_datasets(path: str | Path) -> str:
    """Return the sample-data XML for an XFA form. Raises :class:`NoXfaError`."""
    with pikepdf.Pdf.open(str(path)) as pdf:
        xfa = XfaObj(pdf)
        packet = xfa.data_packet_name()
        if packet is None:
            raise NoXfaError(
                "Il modulo XFA non contiene un pacchetto 'datasets' con i dati del form."
            )
        raw = xfa[packet]
    return XML_DECLARATION + unwrap_datasets(raw)


def extract_all_packets(path: str | Path, out_dir: str | Path | None = None) -> list[Path]:
    """Dump every XFA packet to its own ``.xml`` next to the PDF.

    Mirrors the historical ``xfa-extract-all.py``: output lands in a folder named
    after the PDF, in the PDF's own directory.
    """
    path = Path(path)
    out_dir = Path(out_dir) if out_dir else path.parent / path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    with pikepdf.Pdf.open(str(path)) as pdf:
        xfa = XfaObj(pdf)
        for key in xfa.packet_names:
            target = out_dir / f"{safe_packet_filename(key)}.xml"
            target.write_text(xfa[key], encoding="utf-8")
            written.append(target)
    return written


# ---------------------------------------------------------------------------
# Strategy 2: AcroForm field values
# ---------------------------------------------------------------------------

_NCNAME_RE = re.compile(r"^[A-Za-z_][\w.\-]*$")


def _is_valid_element_name(name: str) -> bool:
    return bool(_NCNAME_RE.match(name))


def _decode_field_value(value) -> str:
    """Normalise a raw PDF field value into a display string."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    text = str(value)
    # Name objects arrive as '/Yes', '/Off', '/1' - strip the marker.
    if text.startswith("/"):
        text = text[1:]
    if text == "Off":
        return ""
    return text


def read_acroform_fields(path: str | Path) -> dict[str, dict]:
    """Return ``{qualified_name: {value, type, options}}`` for every form field."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise PdfOpenError(f"Impossibile leggere i campi di '{Path(path).name}': {exc}") from exc

    raw_fields = reader.get_fields() or {}
    result: dict[str, dict] = {}
    for name, spec in raw_fields.items():
        if not name:
            continue
        field_type = _decode_field_value(spec.get("/FT")) if hasattr(spec, "get") else ""
        value = _decode_field_value(spec.get("/V")) if hasattr(spec, "get") else ""
        states = spec.get("/_States_") if hasattr(spec, "get") else None
        result[str(name)] = {
            "value": value,
            "type": field_type,
            "options": [_decode_field_value(s) for s in states] if states else [],
        }
    return result


def _nest_dotted_names(fields: dict[str, dict]) -> ET.Element:
    """Build an element tree from dotted field names (``form1.page1.name``)."""
    root = ET.Element(f"{{{XFA_DATA_NS}}}data")
    nodes: dict[str, ET.Element] = {"": root}

    for qualified, spec in sorted(fields.items()):
        parts = [p for p in qualified.split(".") if p]
        if not parts:
            continue
        parent = root
        trail = ""
        for part in parts[:-1]:
            trail = f"{trail}.{part}" if trail else part
            if trail not in nodes:
                nodes[trail] = _make_child(parent, part)
            parent = nodes[trail]

        leaf = _make_child(parent, parts[-1])
        leaf.text = spec["value"]
        if spec.get("type"):
            leaf.set("fieldType", spec["type"])
    return root


def _make_child(parent: ET.Element, name: str) -> ET.Element:
    """Create a child element, falling back to ``<field name="...">`` when the
    PDF field name is not a legal XML element name."""
    if _is_valid_element_name(name):
        return ET.SubElement(parent, name)
    child = ET.SubElement(parent, "field")
    child.set("name", name)
    return child


def _serialise(root: ET.Element) -> str:
    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode")
    return XML_DECLARATION + body + "\n"


def extract_acroform_xml(path: str | Path) -> tuple[str, int]:
    """Build an ``<xfa:data>`` document from AcroForm field values."""
    fields = read_acroform_fields(path)
    if not fields:
        raise ExtractionError("Il PDF non contiene campi AcroForm leggibili.")
    ET.register_namespace("xfa", XFA_DATA_NS)
    root = _nest_dotted_names(fields)
    return _serialise(root), len(fields)


def build_xfdf(path: str | Path) -> str:
    """Export AcroForm values as XFDF, the format Acrobat itself uses."""
    fields = read_acroform_fields(path)
    ns = "http://ns.adobe.com/xfdf/"
    root = ET.Element(f"{{{ns}}}xfdf")
    ET.register_namespace("", ns)
    fields_el = ET.SubElement(root, "fields")
    for name, spec in sorted(fields.items()):
        el = ET.SubElement(fields_el, "field")
        el.set("name", name)
        value_el = ET.SubElement(el, "value")
        value_el.text = spec["value"]
    href = ET.SubElement(root, "f")
    href.set("href", Path(path).name)
    return _serialise(root)


# ---------------------------------------------------------------------------
# Strategy 3: the text layer
# ---------------------------------------------------------------------------

#: ``Label: value`` on one line - the most common shape in a flattened form.
_LABEL_VALUE_RE = re.compile(r"^\s*(?P<label>[^:\n]{2,60}?)\s*[::]\s*(?P<value>\S.*)$")


def _slugify_label(label: str) -> str:
    """Turn a human label into something usable as an XML attribute value."""
    return re.sub(r"\s+", " ", label).strip(" .…")


def extract_text_xml(
    path: str | Path,
    ctx: JobContext = NULL_CONTEXT,
    max_pages: int | None = DEFAULT_MAX_PAGES,
) -> tuple[str, int]:
    """Reconstruct an XML from the PDF's text layer, keeping positions.

    Emits both the raw lines (with bounding boxes, so a human can see the layout)
    and a ``<fields>`` section holding every ``Label: value`` pair we could spot.
    That heuristic section is what makes the output actually useful for a
    flattened form; the caller is responsible for labelling it as a guess.

    Long documents are truncated at ``max_pages`` and the truncation is recorded
    on the root element, so the output never silently misrepresents the source.
    """
    import pdfplumber

    path = Path(path)
    root = ET.Element("document")
    root.set("source", path.name)
    root.set("extraction", "text-layout")

    field_count = 0
    try:
        with pdfplumber.open(str(path)) as doc:
            total = len(doc.pages)
            root.set("pages", str(total))
            limit = min(total, max_pages) if max_pages else total
            if limit < total:
                root.set("pagesProcessed", str(limit))
                root.set("truncated", "true")

            for index, page in enumerate(doc.pages[:limit], start=1):
                ctx.check_cancelled()
                ctx.progress(index - 1, limit, f"{path.name}: pagina {index}/{limit}")
                page_el = ET.SubElement(root, "page")
                page_el.set("number", str(index))
                page_el.set("width", f"{page.width:.1f}")
                page_el.set("height", f"{page.height:.1f}")

                lines_el = ET.SubElement(page_el, "lines")
                fields_el = ET.SubElement(page_el, "fields")

                for line in _group_words_into_lines(page):
                    text = line["text"].strip()
                    if not text:
                        continue
                    line_el = ET.SubElement(lines_el, "line")
                    line_el.set("top", f"{line['top']:.1f}")
                    line_el.set("left", f"{line['x0']:.1f}")
                    line_el.set("right", f"{line['x1']:.1f}")
                    line_el.text = text

                    match = _LABEL_VALUE_RE.match(text)
                    if match:
                        field_el = ET.SubElement(fields_el, "field")
                        field_el.set("name", _slugify_label(match.group("label")))
                        field_el.text = match.group("value").strip()
                        field_count += 1

                if len(fields_el) == 0:
                    page_el.remove(fields_el)
    except CancelledError:
        raise
    except Exception as exc:
        raise ExtractionError(f"Estrazione del testo non riuscita: {exc}") from exc

    if len(root) == 0:
        raise ExtractionError("Il PDF non contiene un livello di testo estraibile.")

    ctx.progress(1, 1, f"{path.name}: completato")
    return _serialise(root), field_count


def _group_words_into_lines(page, tolerance: float = 2.5) -> list[dict]:
    """Group pdfplumber words into visual lines by their vertical position."""
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    lines: list[dict] = []
    for word in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
        for line in reversed(lines):
            if abs(line["top"] - word["top"]) <= tolerance:
                line["text"] += " " + word["text"]
                line["x1"] = max(line["x1"], word["x1"])
                break
        else:
            lines.append(
                {
                    "text": word["text"],
                    "top": word["top"],
                    "x0": word["x0"],
                    "x1": word["x1"],
                }
            )
    return lines


# ---------------------------------------------------------------------------
# Strategy 4: OCR
# ---------------------------------------------------------------------------


def extract_ocr_xml(
    path: str | Path,
    lang: str = "ita+eng",
    dpi: int = OCR_DPI,
    ctx: JobContext = NULL_CONTEXT,
    max_pages: int | None = DEFAULT_MAX_PAGES,
) -> tuple[str, int]:
    """Rasterise every page and run Tesseract over it.

    OCR is by far the slowest strategy - roughly a second per page - so it
    reports progress per page and honours cancellation between pages.
    """
    from . import engines

    if not engines.is_available("tesseract"):
        raise ExtractionError(
            "OCR non disponibile: Tesseract non e' installato.",
            hint=engines.TESSERACT_HINT,
        )

    import pypdfium2 as pdfium
    import pytesseract

    binary = engines.find_tesseract()
    if binary:
        pytesseract.pytesseract.tesseract_cmd = binary

    available = set(engines.tesseract_languages())
    requested = [code for code in lang.split("+") if code in available]
    effective = "+".join(requested) or ("eng" if "eng" in available else next(iter(available), "eng"))

    path = Path(path)
    root = ET.Element("document")
    root.set("source", path.name)
    root.set("extraction", "ocr")
    root.set("ocrLanguage", effective)
    root.set("dpi", str(dpi))

    field_count = 0
    scale = dpi / 72.0

    pdf = pdfium.PdfDocument(str(path))
    try:
        total = len(pdf)
        root.set("pages", str(total))
        limit = min(total, max_pages) if max_pages else total
        if limit < total:
            root.set("pagesProcessed", str(limit))
            root.set("truncated", "true")

        for index in range(limit):
            ctx.check_cancelled()
            ctx.progress(index, limit, f"{path.name}: OCR pagina {index + 1}/{limit}")
            page = pdf[index]
            image = page.render(scale=scale).to_pil()
            page_el = ET.SubElement(root, "page")
            page_el.set("number", str(index + 1))

            lines_el = ET.SubElement(page_el, "lines")
            fields_el = ET.SubElement(page_el, "fields")

            for line in _ocr_lines(pytesseract, image, effective):
                line_el = ET.SubElement(lines_el, "line")
                line_el.set("top", str(line["top"]))
                line_el.set("left", str(line["left"]))
                line_el.set("confidence", f"{line['conf']:.0f}")
                line_el.text = line["text"]

                match = _LABEL_VALUE_RE.match(line["text"])
                if match:
                    field_el = ET.SubElement(fields_el, "field")
                    field_el.set("name", _slugify_label(match.group("label")))
                    field_el.text = match.group("value").strip()
                    field_count += 1

            if len(fields_el) == 0:
                page_el.remove(fields_el)
    finally:
        pdf.close()

    if len(root) == 0:
        raise ExtractionError("L'OCR non ha prodotto testo leggibile.")

    ctx.progress(1, 1, f"{path.name}: OCR completato")
    return _serialise(root), field_count


def _ocr_lines(pytesseract, image, lang: str) -> list[dict]:
    """Run Tesseract and regroup the word-level output into lines."""
    data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)
    grouped: dict[tuple, dict] = {}
    for i, text in enumerate(data["text"]):
        text = (text or "").strip()
        if not text:
            continue
        conf = float(data["conf"][i]) if data["conf"][i] not in ("-1", -1) else 0.0
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        entry = grouped.setdefault(
            key,
            {"text": "", "top": data["top"][i], "left": data["left"][i], "conf": 0.0, "n": 0},
        )
        entry["text"] = f"{entry['text']} {text}".strip()
        entry["conf"] += conf
        entry["n"] += 1

    lines = []
    for entry in grouped.values():
        entry["conf"] = entry["conf"] / entry["n"] if entry["n"] else 0.0
        lines.append(entry)
    return sorted(lines, key=lambda line: (line["top"], line["left"]))


# ---------------------------------------------------------------------------
# The chain
# ---------------------------------------------------------------------------

#: Order in which ``mode="auto"`` tries the strategies.
AUTO_ORDER = (ExtractSource.XFA, ExtractSource.ACROFORM, ExtractSource.TEXT, ExtractSource.OCR)


def extract_xml(
    path: str | Path,
    mode: str = "auto",
    ocr_lang: str = "ita+eng",
    profile: PdfProfile | None = None,
    ctx: JobContext = NULL_CONTEXT,
    max_pages: int | None = DEFAULT_MAX_PAGES,
) -> ExtractResult:
    """Produce an XML from ``path`` using the best strategy available.

    ``mode`` is either ``"auto"`` or the name of a single strategy
    (``"xfa"``, ``"acroform"``, ``"text"``, ``"ocr"``).  Forcing a strategy makes
    it raise on failure instead of falling through, which is what the CLI uses
    when the user asked for something specific.
    """
    path = Path(path)
    if not path.exists():
        raise PdfOpenError(f"File non trovato: {path}")

    if mode != "auto":
        try:
            source = ExtractSource(mode)
        except ValueError as exc:
            raise ExtractionError(
                f"Modalita' di estrazione sconosciuta: '{mode}'. "
                f"Usa una fra: auto, {', '.join(s.value for s in AUTO_ORDER)}."
            ) from exc
        xml, count = _run_strategy(source, path, ocr_lang, ctx, max_pages)
        return ExtractResult(
            xml=xml,
            source=source,
            confidence=CONFIDENCE_BY_SOURCE[source],
            profile=profile,
            field_count=count,
        )

    if profile is None:
        ctx.progress(0, 0, f"{path.name}: analisi in corso")
        profile = probe_pdf(path)
    ctx.check_cancelled()

    warnings: list[str] = list(profile.warnings)
    attempts: list[str] = []

    for source in AUTO_ORDER:
        if not _worth_trying(source, profile):
            continue
        try:
            xml, count = _run_strategy(source, path, ocr_lang, ctx, max_pages)
        except CancelledError:
            raise
        except Exception as exc:
            attempts.append(f"{source.value}: {exc}")
            continue

        if source in (ExtractSource.TEXT, ExtractSource.OCR):
            warnings.append(
                "Questo PDF non contiene dati di modulo strutturati: l'XML e' stato "
                "ricostruito dal contenuto della pagina e va verificato."
            )
            if profile.page_count > (max_pages or profile.page_count):
                warnings.append(
                    f"Elaborate solo le prime {max_pages} pagine di {profile.page_count}."
                )
        if attempts:
            warnings.append("Strategie precedenti non applicabili: " + "; ".join(attempts))

        return ExtractResult(
            xml=xml,
            source=source,
            confidence=CONFIDENCE_BY_SOURCE[source],
            warnings=warnings,
            profile=profile,
            field_count=count,
        )

    detail = "; ".join(attempts) if attempts else "nessuna strategia applicabile"
    raise ExtractionError(
        f"Impossibile estrarre un XML da '{path.name}' ({detail}).",
        hint=(
            "Se il PDF e' una scansione, installa Tesseract OCR per abilitare "
            "l'ultima strategia disponibile."
        ),
    )


def _worth_trying(source: ExtractSource, profile: PdfProfile) -> bool:
    """Skip strategies the profile already rules out, to keep the chain fast."""
    from . import engines

    if source is ExtractSource.XFA:
        return profile.has_xfa
    if source is ExtractSource.ACROFORM:
        return profile.has_acroform
    if source is ExtractSource.TEXT:
        return profile.has_text_layer
    if source is ExtractSource.OCR:
        return engines.is_available("tesseract")
    return False


def _run_strategy(
    source: ExtractSource,
    path: Path,
    ocr_lang: str,
    ctx: JobContext = NULL_CONTEXT,
    max_pages: int | None = DEFAULT_MAX_PAGES,
) -> tuple[str, int]:
    if source is ExtractSource.XFA:
        return extract_xfa_datasets(path), 0
    if source is ExtractSource.ACROFORM:
        return extract_acroform_xml(path)
    if source is ExtractSource.TEXT:
        return extract_text_xml(path, ctx=ctx, max_pages=max_pages)
    if source is ExtractSource.OCR:
        return extract_ocr_xml(path, lang=ocr_lang, ctx=ctx, max_pages=max_pages)
    raise ExtractionError(f"Strategia non implementata: {source}")
