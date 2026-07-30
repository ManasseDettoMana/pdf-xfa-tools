"""Image conversions, built on Pillow.

Handles the awkward parts that a naive ``Image.open(src).save(dst)`` gets wrong:
transparency being dropped into black when saving to JPEG, animated GIFs losing
every frame but the first, CMYK sources, EXIF orientation, and ICO's size limits.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from .errors import ConversionError
from .job import NULL_CONTEXT, JobContext

#: Extensions Pillow can read out of the box.
READABLE_EXTS = (
    "png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff", "gif", "ico", "ppm", "tga",
)

#: Extensions we offer as conversion targets.
WRITABLE_EXTS = ("png", "jpg", "webp", "bmp", "tiff", "gif", "ico", "pdf")

#: Formats with no alpha channel: transparency must be composited first.
NO_ALPHA_FORMATS = {"JPEG", "BMP"}

#: Pillow format names, keyed by our lowercase extension.
PIL_FORMAT = {
    "png": "PNG",
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "webp": "WEBP",
    "bmp": "BMP",
    "tif": "TIFF",
    "tiff": "TIFF",
    "gif": "GIF",
    "ico": "ICO",
    "pdf": "PDF",
}

#: ICO cannot hold arbitrary sizes; Windows tops out at 256 px.
ICO_MAX_SIZE = 256


def register_optional_formats() -> None:
    """Enable HEIC/HEIF support when ``pillow-heif`` is installed."""
    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
    except ImportError:
        pass


register_optional_formats()


def supported_read_exts() -> tuple[str, ...]:
    """Readable extensions, including HEIC when the plugin is present."""
    exts = list(READABLE_EXTS)
    try:
        import pillow_heif  # noqa: F401

        exts.extend(("heic", "heif"))
    except ImportError:
        pass
    return tuple(exts)


def _open(src: Path) -> Image.Image:
    try:
        image = Image.open(src)
    except UnidentifiedImageError as exc:
        raise ConversionError(f"'{src.name}' non e' un'immagine leggibile.") from exc
    except Exception as exc:
        raise ConversionError(f"Impossibile aprire '{src.name}': {exc}") from exc
    # Respect the EXIF orientation flag, otherwise phone photos come out rotated.
    return ImageOps.exif_transpose(image) or image


def _flatten_alpha(image: Image.Image, background: str) -> Image.Image:
    """Composite transparency onto a solid colour for formats without alpha."""
    if image.mode not in ("RGBA", "LA", "P"):
        return image.convert("RGB") if image.mode != "RGB" else image
    rgba = image.convert("RGBA")
    canvas = Image.new("RGBA", rgba.size, background)
    canvas.alpha_composite(rgba)
    return canvas.convert("RGB")


def _resize(image: Image.Image, max_width: int, max_height: int) -> Image.Image:
    """Scale down to fit the given box, preserving aspect ratio. Never upscales."""
    if not max_width and not max_height:
        return image
    width = max_width or image.width
    height = max_height or image.height
    if image.width <= width and image.height <= height:
        return image
    resized = image.copy()
    resized.thumbnail((width, height), Image.Resampling.LANCZOS)
    return resized


def convert_image(
    src: Path,
    dst: Path,
    options: dict[str, Any] | None = None,
    ctx: JobContext = NULL_CONTEXT,
) -> list[Path]:
    """Convert one image file into ``dst``, whose suffix decides the format."""
    options = options or {}
    src, dst = Path(src), Path(dst)
    target_ext = dst.suffix.lstrip(".").lower()
    fmt = PIL_FORMAT.get(target_ext)
    if fmt is None:
        raise ConversionError(f"Formato immagine di destinazione non supportato: .{target_ext}")

    ctx.check_cancelled()
    ctx.progress(0, 1, f"{src.name}: conversione in {target_ext.upper()}")

    image = _open(src)
    try:
        image = _resize(image, int(options.get("max_width", 0)), int(options.get("max_height", 0)))

        if fmt in NO_ALPHA_FORMATS:
            image = _flatten_alpha(image, options.get("background", "#FFFFFF"))
        elif fmt == "PDF":
            image = _flatten_alpha(image, options.get("background", "#FFFFFF"))
        elif image.mode == "P" and fmt in ("PNG", "WEBP"):
            image = image.convert("RGBA")
        elif image.mode == "CMYK" and fmt in ("PNG", "WEBP", "GIF"):
            image = image.convert("RGB")

        save_kwargs: dict[str, Any] = {}
        if fmt in ("JPEG", "WEBP"):
            save_kwargs["quality"] = int(options.get("quality", 90))
        if fmt == "JPEG":
            save_kwargs["optimize"] = True
            save_kwargs["progressive"] = True
        if fmt == "PNG":
            save_kwargs["optimize"] = True
        if fmt == "TIFF":
            save_kwargs["compression"] = options.get("compression", "tiff_lzw")
        if fmt == "ICO":
            # ICO stores a set of square icons; anything larger is rejected.
            size = min(ICO_MAX_SIZE, max(image.width, image.height))
            save_kwargs["sizes"] = [(size, size)]
        if dpi := int(options.get("dpi", 0)):
            save_kwargs["dpi"] = (dpi, dpi)

        dst.parent.mkdir(parents=True, exist_ok=True)
        image.save(dst, format=fmt, **save_kwargs)
    except ConversionError:
        raise
    except Exception as exc:
        raise ConversionError(f"Conversione di '{src.name}' non riuscita: {exc}") from exc
    finally:
        image.close()

    ctx.progress(1, 1, f"{src.name}: completato")
    return [dst]


def images_to_pdf(
    sources: list[Path],
    dst: Path,
    options: dict[str, Any] | None = None,
    ctx: JobContext = NULL_CONTEXT,
) -> list[Path]:
    """Combine images into a single multi-page PDF, one image per page."""
    options = options or {}
    if not sources:
        raise ConversionError("Nessuna immagine da convertire in PDF.")

    background = options.get("background", "#FFFFFF")
    pages: list[Image.Image] = []
    try:
        for index, src in enumerate(sources, start=1):
            ctx.check_cancelled()
            ctx.progress(index - 1, len(sources), f"{Path(src).name}: pagina {index}")
            image = _open(Path(src))
            image = _resize(
                image, int(options.get("max_width", 0)), int(options.get("max_height", 0))
            )
            pages.append(_flatten_alpha(image, background))

        dst = Path(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        first, rest = pages[0], pages[1:]
        first.save(
            dst,
            format="PDF",
            save_all=True,
            append_images=rest,
            resolution=float(options.get("dpi", 150) or 150),
        )
    except ConversionError:
        raise
    except Exception as exc:
        raise ConversionError(f"Creazione del PDF non riuscita: {exc}") from exc
    finally:
        for page in pages:
            page.close()

    ctx.progress(len(sources), len(sources), f"{dst.name}: completato")
    return [dst]
