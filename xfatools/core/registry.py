"""The single table of everything this application can convert.

One registry drives all three surfaces: the GUI builds its format dropdown and
its options panel from it, the CLI builds its ``convert`` subcommand from it, and
the job runner dispatches through it.  Adding a conversion means adding one
:class:`Converter` here - no UI code changes.

Handlers all share the signature ``(src, dst, options, ctx) -> list[Path]``.
For converters marked ``multi_output`` the ``dst`` argument is a *directory*
rather than a file, because the operation produces an unknown number of files.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import documents, engines, images, pdfops
from .errors import ConversionError
from .job import NULL_CONTEXT, Job, JobContext, JobResult, JobStatus, Timer, unique_path

Handler = Callable[[Path, Path, dict[str, Any], JobContext], list[Path]]


class Category:
    XFA = "xfa"
    PDF = "pdf"
    IMAGE = "image"
    DOCUMENT = "document"


CATEGORY_LABELS = {
    Category.XFA: "Moduli XFA / XML",
    Category.PDF: "PDF",
    Category.IMAGE: "Immagini",
    Category.DOCUMENT: "Documenti",
}


@dataclass(frozen=True)
class Option:
    """One user-adjustable setting, rendered generically by the options panel."""

    key: str
    label: str
    kind: str  # "int" | "bool" | "choice" | "text"
    default: Any
    choices: tuple[tuple[str, Any], ...] = ()
    minimum: int = 0
    maximum: int = 10_000
    suffix: str = ""
    help: str = ""


@dataclass(frozen=True)
class Converter:
    """One entry in the conversion table."""

    id: str
    label: str
    category: str
    src_exts: tuple[str, ...]
    dst_ext: str
    handler: Handler
    requires: tuple[str, ...] = ()
    options: tuple[Option, ...] = ()
    multi_output: bool = False
    description: str = ""
    approximate_without_engine: bool = False

    @property
    def available(self) -> bool:
        """False when an external engine this conversion needs is missing."""
        return all(engines.is_available(key) for key in self.requires)

    @property
    def unavailable_reason(self) -> str:
        for key in self.requires:
            if not engines.is_available(key):
                return engines.missing_hint(key)
        return ""

    def defaults(self) -> dict[str, Any]:
        return {option.key: option.default for option in self.options}

    def output_name(self, src: Path) -> str:
        return f"{src.stem}.{self.dst_ext}" if self.dst_ext else src.stem


# ---------------------------------------------------------------------------
# Adapters: give the XFA operations the common handler signature
# ---------------------------------------------------------------------------


def _extract_xml(src: Path, dst: Path, options: dict[str, Any], ctx: JobContext) -> list[Path]:
    from .extract import extract_xml

    result = extract_xml(
        src,
        mode=options.get("mode", "auto"),
        ocr_lang=options.get("ocr_lang", "ita+eng"),
        ctx=ctx,
        max_pages=None if options.get("all_pages") else int(options.get("max_pages", 100)),
    )
    # Provenance has to reach the GUI and the handler contract only returns
    # paths, so it travels on the per-job context.
    ctx.metadata["extraction"] = result
    return [result.write(dst)]


def _extract_all(src: Path, dst_dir: Path, options: dict[str, Any], ctx: JobContext) -> list[Path]:
    from .extract import extract_all_packets

    return extract_all_packets(src, dst_dir / src.stem)


def _extract_xfdf(src: Path, dst: Path, options: dict[str, Any], ctx: JobContext) -> list[Path]:
    from .extract import build_xfdf

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(build_xfdf(src), encoding="utf-8")
    return [dst]


def _unlock(src: Path, dst: Path, options: dict[str, Any], ctx: JobContext) -> list[Path]:
    from .unlock import unlock_pdf

    return [unlock_pdf(src, dst).out_path]


# ---------------------------------------------------------------------------
# Shared option definitions
# ---------------------------------------------------------------------------

OPT_QUALITY = Option(
    key="quality",
    label="Qualita'",
    kind="int",
    default=90,
    minimum=10,
    maximum=100,
    suffix="%",
    help="Piu' alta significa file piu' grande e meno artefatti.",
)

OPT_DPI = Option(
    key="dpi",
    label="Risoluzione",
    kind="int",
    default=150,
    minimum=36,
    maximum=600,
    suffix=" DPI",
    help="150 va bene per lo schermo, 300 per la stampa.",
)

OPT_MAX_WIDTH = Option(
    key="max_width",
    label="Larghezza massima",
    kind="int",
    default=0,
    minimum=0,
    maximum=10_000,
    suffix=" px",
    help="0 mantiene la dimensione originale. Non ingrandisce mai.",
)

OPT_MAX_HEIGHT = Option(
    key="max_height",
    label="Altezza massima",
    kind="int",
    default=0,
    minimum=0,
    maximum=10_000,
    suffix=" px",
    help="0 mantiene la dimensione originale.",
)

OPT_EXTRACT_MODE = Option(
    key="mode",
    label="Strategia",
    kind="choice",
    default="auto",
    choices=(
        ("Automatica (consigliata)", "auto"),
        ("Solo pacchetto XFA", "xfa"),
        ("Solo campi AcroForm", "acroform"),
        ("Solo livello di testo", "text"),
        ("Solo OCR", "ocr"),
    ),
    help="In automatico prova le strategie dalla piu' fedele alla piu' approssimata.",
)

OPT_MAX_PAGES = Option(
    key="max_pages",
    label="Pagine massime",
    kind="int",
    default=100,
    minimum=1,
    maximum=5_000,
    help="Limite per le strategie che leggono le pagine. Le altre lo ignorano.",
)

OPT_PAGE_RANGE = Option(
    key="pages",
    label="Pagine",
    kind="text",
    default="1-",
    help="Esempi: 1-3,7,10- oppure 2.",
)


# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------

IMAGE_READ_EXTS = images.supported_read_exts()

CONVERTERS: tuple[Converter, ...] = (
    # --- XFA / XML -------------------------------------------------------
    Converter(
        id="pdf-to-xml",
        label="XML (dati del modulo)",
        category=Category.XFA,
        src_exts=("pdf",),
        dst_ext="xml",
        handler=_extract_xml,
        options=(OPT_EXTRACT_MODE, OPT_MAX_PAGES),
        description=(
            "Estrae i dati del modulo. Usa il pacchetto XFA quando c'e', "
            "altrimenti ricostruisce l'XML dai campi, dal testo o via OCR."
        ),
    ),
    Converter(
        id="pdf-to-xfa-packets",
        label="XML (tutti i pacchetti XFA)",
        category=Category.XFA,
        src_exts=("pdf",),
        dst_ext="",
        handler=_extract_all,
        multi_output=True,
        description="Salva ogni pacchetto XFA (template, datasets, config...) come file separato.",
    ),
    Converter(
        id="pdf-to-xfdf",
        label="XFDF (valori dei campi)",
        category=Category.XFA,
        src_exts=("pdf",),
        dst_ext="xfdf",
        handler=_extract_xfdf,
        description="Esporta i valori AcroForm nel formato usato da Acrobat.",
    ),
    Converter(
        id="pdf-unlock-deco",
        label="PDF sbloccato (decorazione AF)",
        category=Category.XFA,
        src_exts=("pdf",),
        dst_ext="pdf",
        handler=_unlock,
        description="Rende tutti i campi modificabili e rimuove i dati personali.",
    ),
    # --- PDF -------------------------------------------------------------
    Converter(
        id="pdf-to-image",
        label="Immagini (una per pagina)",
        category=Category.PDF,
        src_exts=("pdf",),
        dst_ext="",
        handler=pdfops.pdf_to_images,
        multi_output=True,
        options=(
            Option(
                key="format",
                label="Formato",
                kind="choice",
                default="png",
                choices=(("PNG", "png"), ("JPG", "jpg"), ("TIFF", "tiff"), ("WEBP", "webp")),
            ),
            OPT_DPI,
            OPT_QUALITY,
        ),
    ),
    Converter(
        id="pdf-split",
        label="Dividi in pagine singole",
        category=Category.PDF,
        src_exts=("pdf",),
        dst_ext="",
        handler=pdfops.split_pdf,
        multi_output=True,
    ),
    Converter(
        id="pdf-rotate",
        label="Ruota",
        category=Category.PDF,
        src_exts=("pdf",),
        dst_ext="pdf",
        handler=pdfops.rotate_pdf,
        options=(
            Option(
                key="angle",
                label="Angolo",
                kind="choice",
                default=90,
                choices=(("90 gradi orari", 90), ("180 gradi", 180), ("90 gradi antiorari", 270)),
            ),
        ),
    ),
    Converter(
        id="pdf-compress",
        label="Comprimi",
        category=Category.PDF,
        src_exts=("pdf",),
        dst_ext="pdf",
        handler=pdfops.compress_pdf,
        description="Compressione senza perdita: le immagini non vengono degradate.",
    ),
    Converter(
        id="pdf-extract-pages",
        label="Estrai intervallo di pagine",
        category=Category.PDF,
        src_exts=("pdf",),
        dst_ext="pdf",
        handler=pdfops.extract_pages,
        options=(OPT_PAGE_RANGE,),
    ),
    Converter(
        id="pdf-to-txt",
        label="Testo",
        category=Category.PDF,
        src_exts=("pdf",),
        dst_ext="txt",
        handler=documents.pdf_to_text,
        options=(OPT_MAX_PAGES,),
    ),
    Converter(
        id="pdf-to-md",
        label="Markdown",
        category=Category.PDF,
        src_exts=("pdf",),
        dst_ext="md",
        handler=documents.pdf_to_markdown,
        options=(OPT_MAX_PAGES,),
    ),
    Converter(
        id="pdf-to-csv",
        label="CSV (tabelle rilevate)",
        category=Category.PDF,
        src_exts=("pdf",),
        dst_ext="csv",
        handler=documents.pdf_to_csv,
        options=(OPT_MAX_PAGES,),
    ),
    # --- Images ----------------------------------------------------------
    *(
        Converter(
            id=f"image-to-{ext}",
            label=ext.upper(),
            category=Category.IMAGE,
            src_exts=IMAGE_READ_EXTS,
            dst_ext=ext,
            handler=images.convert_image,
            options=(
                (OPT_QUALITY,) if ext in ("jpg", "webp") else ()
            )
            + (OPT_MAX_WIDTH, OPT_MAX_HEIGHT),
        )
        for ext in ("png", "jpg", "webp", "tiff", "bmp", "gif", "ico")
    ),
    Converter(
        id="image-to-pdf",
        label="PDF",
        category=Category.IMAGE,
        src_exts=IMAGE_READ_EXTS,
        dst_ext="pdf",
        handler=images.convert_image,
        options=(OPT_MAX_WIDTH, OPT_MAX_HEIGHT),
        description="Un PDF per immagine. Per unirle in un solo PDF usa l'azione 'Unisci'.",
    ),
    # --- Documents -------------------------------------------------------
    Converter(
        id="office-to-pdf",
        label="PDF",
        category=Category.DOCUMENT,
        src_exts=documents.OFFICE_EXTS,
        dst_ext="pdf",
        handler=documents.office_to_pdf,
        approximate_without_engine=True,
        description=(
            "Con LibreOffice o Word il layout e' fedele. Senza, il testo viene "
            "impaginato in modo approssimato."
        ),
    ),
    Converter(
        id="text-to-pdf",
        label="PDF",
        category=Category.DOCUMENT,
        src_exts=documents.TEXT_EXTS,
        dst_ext="pdf",
        handler=documents.text_to_pdf,
    ),
    Converter(
        id="office-to-txt",
        label="Testo",
        category=Category.DOCUMENT,
        src_exts=("docx", "xlsx", "pptx"),
        dst_ext="txt",
        handler=documents.office_to_text,
    ),
    Converter(
        id="office-to-md",
        label="Markdown",
        category=Category.DOCUMENT,
        src_exts=("docx", "xlsx", "pptx"),
        dst_ext="md",
        handler=documents.office_to_text,
    ),
    Converter(
        id="xlsx-to-csv",
        label="CSV",
        category=Category.DOCUMENT,
        src_exts=("xlsx", "xlsm"),
        dst_ext="csv",
        handler=documents.spreadsheet_to_csv,
    ),
)

BY_ID: dict[str, Converter] = {converter.id: converter for converter in CONVERTERS}


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------


def normalise_ext(path: str | Path) -> str:
    return Path(path).suffix.lstrip(".").lower()


def get(converter_id: str) -> Converter:
    try:
        return BY_ID[converter_id]
    except KeyError as exc:
        raise ConversionError(f"Conversione sconosciuta: '{converter_id}'.") from exc


def targets_for(path: str | Path) -> list[Converter]:
    """Every conversion applicable to one file, in declaration order.

    A same-extension entry is dropped only for images, where "PNG to PNG" is
    meaningless.  For PDFs it is exactly what rotate, compress, unlock and
    extract-pages do, so those must stay offered.
    """
    ext = normalise_ext(path)
    offered: list[Converter] = []
    for converter in CONVERTERS:
        if ext not in converter.src_exts:
            continue
        if converter.category == Category.IMAGE and converter.dst_ext == ext:
            continue
        offered.append(converter)
    return offered


def common_targets(paths: Iterable[str | Path]) -> list[Converter]:
    """Conversions applicable to *every* selected file.

    With a mixed selection the dropdown must only offer what works for all of
    them, otherwise a batch fails halfway through.
    """
    paths = list(paths)
    if not paths:
        return []
    shared: set[str] | None = None
    for path in paths:
        ids = {c.id for c in targets_for(path)}
        shared = ids if shared is None else (shared & ids)
    return [c for c in CONVERTERS if c.id in (shared or set())]


def supported_input_exts() -> tuple[str, ...]:
    """Every extension the application can accept, for the drop-zone filter."""
    exts: set[str] = set()
    for converter in CONVERTERS:
        exts.update(converter.src_exts)
    return tuple(sorted(exts))


def categories_of(converters: Iterable[Converter]) -> list[tuple[str, list[Converter]]]:
    """Group converters by category, preserving the declared category order."""
    order = (Category.XFA, Category.PDF, Category.IMAGE, Category.DOCUMENT)
    grouped: dict[str, list[Converter]] = {key: [] for key in order}
    for converter in converters:
        grouped.setdefault(converter.category, []).append(converter)
    return [(key, grouped[key]) for key in order if grouped.get(key)]


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def run_job(job: Job, ctx: JobContext = NULL_CONTEXT) -> JobResult:
    """Execute one job and describe what happened, without ever raising.

    A batch must survive one bad file, so every failure is captured into the
    returned :class:`JobResult` rather than propagating.
    """
    from .errors import CancelledError, XfaToolsError

    converter = get(job.target_format)
    options = {**converter.defaults(), **job.options}
    timer = Timer()

    if not converter.available:
        return JobResult(
            job=job,
            status=JobStatus.SKIPPED,
            message=f"'{converter.label}' non disponibile su questo computer.",
            hint=converter.unavailable_reason,
        )

    try:
        with timer:
            if not job.source.exists():
                raise ConversionError(f"File non trovato: {job.source}")

            destination = job.destination_dir
            destination.mkdir(parents=True, exist_ok=True)

            if converter.multi_output:
                target = destination
            else:
                target = unique_path(destination / converter.output_name(job.source))

            outputs = converter.handler(job.source, target, options, ctx)

        result = JobResult(
            job=job,
            status=JobStatus.DONE,
            outputs=[Path(p) for p in outputs],
            duration_s=timer.elapsed,
        )
        _attach_provenance(result, converter, ctx)
        return result

    except CancelledError:
        return JobResult(job=job, status=JobStatus.CANCELLED, message="Annullato.")
    except XfaToolsError as exc:
        return JobResult(
            job=job,
            status=JobStatus.FAILED,
            message=str(exc),
            hint=getattr(exc, "hint", "") or "",
            duration_s=timer.elapsed,
        )
    except Exception as exc:
        return JobResult(
            job=job,
            status=JobStatus.FAILED,
            message=f"Errore imprevisto: {exc}",
            duration_s=timer.elapsed,
        )


def _attach_provenance(result: JobResult, converter: Converter, ctx: JobContext) -> None:
    """Copy the extraction badge and warnings onto the job result, if any."""
    extraction = ctx.metadata.get("extraction")
    if extraction is not None:
        result.badge = extraction.badge
        result.detail = extraction.source_description
        result.warnings = list(extraction.warnings)
        return

    if converter.approximate_without_engine and not engines.is_available("office_to_pdf"):
        result.badge = "APPROSSIMATO"
        result.detail = "Layout ricostruito senza motore di rendering"
        result.warnings = [
            "Ne' LibreOffice ne' Word sono disponibili: il layout del documento e' "
            "approssimato. Installa LibreOffice per una conversione fedele."
        ]
