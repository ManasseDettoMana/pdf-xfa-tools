"""PDF page operations: rasterising, merging, splitting, rotating, compressing.

Rendering goes through ``pypdfium2`` (the PDFium engine Chrome uses) rather than
a Ghostscript or Poppler subprocess, so page rasterisation needs no external
install and works identically inside the packaged .exe.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pikepdf

from .errors import ConversionError, PdfOpenError
from .job import NULL_CONTEXT, JobContext, unique_path

#: Default rasterisation density. 150 is readable on screen; 300 is print grade.
DEFAULT_DPI = 150

#: Guard against a mistyped DPI turning one page into gigabytes of bitmap.
MAX_DPI = 600

IMAGE_TARGETS = ("png", "jpg", "tiff", "webp")


def _open_pdf(path: Path) -> pikepdf.Pdf:
    try:
        return pikepdf.Pdf.open(str(path))
    except pikepdf.PasswordError as exc:
        raise PdfOpenError(f"'{path.name}' e' protetto da password.") from exc
    except Exception as exc:
        raise PdfOpenError(f"Impossibile aprire '{path.name}': {exc}") from exc


def pdf_to_images(
    src: Path,
    out_dir: Path,
    options: dict[str, Any] | None = None,
    ctx: JobContext = NULL_CONTEXT,
) -> list[Path]:
    """Render each page to its own image file. Returns the files written."""
    import pypdfium2 as pdfium

    options = options or {}
    src, out_dir = Path(src), Path(out_dir)
    fmt = str(options.get("format", "png")).lower()
    if fmt not in IMAGE_TARGETS:
        raise ConversionError(f"Formato immagine non supportato: {fmt}")

    dpi = max(36, min(int(options.get("dpi", DEFAULT_DPI)), MAX_DPI))
    scale = dpi / 72.0

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    try:
        pdf = pdfium.PdfDocument(str(src))
    except Exception as exc:
        raise PdfOpenError(f"Impossibile aprire '{src.name}': {exc}") from exc

    try:
        total = len(pdf)
        max_pages = options.get("max_pages")
        limit = min(total, int(max_pages)) if max_pages else total
        # Zero-pad so the files sort correctly in Explorer.
        width = len(str(limit))

        for index in range(limit):
            ctx.check_cancelled()
            ctx.progress(index, limit, f"{src.name}: pagina {index + 1}/{limit}")
            image = pdf[index].render(scale=scale).to_pil()
            try:
                if fmt in ("jpg", "webp"):
                    image = image.convert("RGB")
                target = unique_path(out_dir / f"{src.stem}_p{index + 1:0{width}d}.{fmt}")
                save_kwargs: dict[str, Any] = {"dpi": (dpi, dpi)}
                if fmt in ("jpg", "webp"):
                    save_kwargs["quality"] = int(options.get("quality", 90))
                image.save(target, **save_kwargs)
                written.append(target)
            finally:
                image.close()
    finally:
        pdf.close()

    if not written:
        raise ConversionError(f"'{src.name}' non contiene pagine da convertire.")

    ctx.progress(len(written), len(written), f"{src.name}: {len(written)} pagine")
    return written


def merge_pdfs(
    sources: list[Path],
    dst: Path,
    options: dict[str, Any] | None = None,
    ctx: JobContext = NULL_CONTEXT,
) -> list[Path]:
    """Concatenate several PDFs into one, in the order given."""
    if not sources:
        raise ConversionError("Nessun PDF da unire.")

    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    merged = pikepdf.Pdf.new()
    try:
        for index, raw in enumerate(sources, start=1):
            ctx.check_cancelled()
            source = Path(raw)
            ctx.progress(index - 1, len(sources), f"{source.name}: unione")
            with _open_pdf(source) as pdf:
                merged.pages.extend(pdf.pages)
        merged.save(str(dst))
    finally:
        merged.close()

    ctx.progress(len(sources), len(sources), f"{dst.name}: completato")
    return [dst]


def split_pdf(
    src: Path,
    out_dir: Path,
    options: dict[str, Any] | None = None,
    ctx: JobContext = NULL_CONTEXT,
) -> list[Path]:
    """Split a PDF into single-page files."""
    options = options or {}
    src, out_dir = Path(src), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    with _open_pdf(src) as pdf:
        total = len(pdf.pages)
        width = len(str(total))
        for index, page in enumerate(pdf.pages, start=1):
            ctx.check_cancelled()
            ctx.progress(index - 1, total, f"{src.name}: pagina {index}/{total}")
            single = pikepdf.Pdf.new()
            try:
                single.pages.append(page)
                target = unique_path(out_dir / f"{src.stem}_p{index:0{width}d}.pdf")
                single.save(str(target))
                written.append(target)
            finally:
                single.close()

    ctx.progress(len(written), len(written), f"{src.name}: {len(written)} file")
    return written


def rotate_pdf(
    src: Path,
    dst: Path,
    options: dict[str, Any] | None = None,
    ctx: JobContext = NULL_CONTEXT,
) -> list[Path]:
    """Rotate every page by a multiple of 90 degrees."""
    options = options or {}
    angle = int(options.get("angle", 90))
    if angle % 90 != 0:
        raise ConversionError("La rotazione deve essere un multiplo di 90 gradi.")

    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    with _open_pdf(src) as pdf:
        total = len(pdf.pages)
        for index, page in enumerate(pdf.pages, start=1):
            ctx.check_cancelled()
            ctx.progress(index - 1, total, f"{src.name}: pagina {index}/{total}")
            page.Rotate = (int(page.get("/Rotate", 0)) + angle) % 360
        pdf.save(str(dst))

    return [dst]


def compress_pdf(
    src: Path,
    dst: Path,
    options: dict[str, Any] | None = None,
    ctx: JobContext = NULL_CONTEXT,
) -> list[Path]:
    """Re-save a PDF with object streams and compression enabled.

    This is lossless structural compression: duplicated objects are merged and
    streams are recompressed, but images are left untouched.  Savings are modest
    and honest - we never silently degrade image quality.  If the result is not
    smaller, the original is copied instead so the user is never worse off.
    """
    import shutil

    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    ctx.progress(0, 1, f"{src.name}: compressione")

    with _open_pdf(src) as pdf:
        pdf.remove_unreferenced_resources()
        pdf.save(
            str(dst),
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
            compress_streams=True,
            recompress_flate=True,
            linearize=bool(options and options.get("linearize", False)),
        )

    before, after = src.stat().st_size, dst.stat().st_size
    if after >= before:
        shutil.copy2(src, dst)
        ctx.progress(1, 1, f"{src.name}: gia' compresso, copiato invariato")
    else:
        saved = 100 * (before - after) / before
        ctx.progress(1, 1, f"{src.name}: -{saved:.0f}%")

    return [dst]


def extract_pages(
    src: Path,
    dst: Path,
    options: dict[str, Any] | None = None,
    ctx: JobContext = NULL_CONTEXT,
) -> list[Path]:
    """Keep only the pages named by a range string such as ``1-3,7,10-``."""
    options = options or {}
    spec = str(options.get("pages", "")).strip()
    if not spec:
        raise ConversionError("Specifica quali pagine estrarre, ad esempio '1-3,7'.")

    src, dst = Path(src), Path(dst)
    with _open_pdf(src) as pdf:
        total = len(pdf.pages)
        wanted = parse_page_range(spec, total)
        if not wanted:
            raise ConversionError(f"L'intervallo '{spec}' non seleziona nessuna pagina.")

        out = pikepdf.Pdf.new()
        try:
            for number in wanted:
                ctx.check_cancelled()
                out.pages.append(pdf.pages[number - 1])
            dst.parent.mkdir(parents=True, exist_ok=True)
            out.save(str(dst))
        finally:
            out.close()

    ctx.progress(1, 1, f"{src.name}: {len(wanted)} pagine estratte")
    return [dst]


def parse_page_range(spec: str, total: int) -> list[int]:
    """Turn ``"1-3,7,10-"`` into ``[1, 2, 3, 7, 10, ..., total]``.

    Page numbers are 1-based and clamped to the document; duplicates are removed
    while preserving the order the user asked for.
    """
    pages: list[int] = []
    seen: set[int] = set()

    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            if "-" in chunk:
                start_text, end_text = chunk.split("-", 1)
                start = int(start_text) if start_text.strip() else 1
                end = int(end_text) if end_text.strip() else total
            else:
                start = end = int(chunk)
        except ValueError as exc:
            raise ConversionError(f"Intervallo di pagine non valido: '{chunk}'.") from exc

        if start > end:
            start, end = end, start
        for number in range(max(1, start), min(total, end) + 1):
            if number not in seen:
                seen.add(number)
                pages.append(number)

    return pages
