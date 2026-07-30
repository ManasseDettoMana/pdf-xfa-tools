"""Detection of optional external engines and Python extras.

The application must start and do useful work on a machine with nothing but the
bundled Python dependencies.  Anything that needs a separate install - LibreOffice
for faithful office-document rendering, Tesseract for OCR, Microsoft Word for COM
automation - is detected here at runtime, cached, and reported in the Diagnostics
panel.  Converters that depend on a missing engine are disabled in the UI with an
install hint rather than failing halfway through a batch.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Engine:
    """A detected (or missing) external capability."""

    key: str
    name: str
    available: bool
    version: str | None = None
    path: str | None = None
    purpose: str = ""
    install_hint: str = ""

    @property
    def status_icon(self) -> str:
        return "OK" if self.available else "--"


# --- LibreOffice -------------------------------------------------------------

_LIBREOFFICE_CANDIDATES = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/usr/bin/soffice",
    "/usr/local/bin/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
)

LIBREOFFICE_HINT = (
    "Installa LibreOffice da https://www.libreoffice.org/download/ "
    "per conversioni fedeli di DOCX/XLSX/PPTX."
)


@lru_cache(maxsize=1)
def find_libreoffice() -> str | None:
    """Return the path to ``soffice``, or ``None`` if it is not installed."""
    env = os.environ.get("XFATOOLS_SOFFICE")
    if env and Path(env).exists():
        return env
    found = shutil.which("soffice") or shutil.which("soffice.exe")
    if found:
        return found
    for candidate in _LIBREOFFICE_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


# --- Tesseract ---------------------------------------------------------------

_TESSERACT_CANDIDATES = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    "/usr/bin/tesseract",
    "/usr/local/bin/tesseract",
    "/opt/homebrew/bin/tesseract",
)

TESSERACT_HINT = (
    "Installa Tesseract OCR da https://github.com/UB-Mannheim/tesseract/wiki "
    "(aggiungi anche la lingua 'ita') per leggere i PDF scansionati."
)


@lru_cache(maxsize=1)
def find_tesseract() -> str | None:
    """Return the path to the Tesseract binary, or ``None``."""
    env = os.environ.get("XFATOOLS_TESSERACT")
    if env and Path(env).exists():
        return env
    found = shutil.which("tesseract") or shutil.which("tesseract.exe")
    if found:
        return found
    for candidate in _TESSERACT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


@lru_cache(maxsize=1)
def tesseract_languages() -> tuple[str, ...]:
    """List the OCR languages Tesseract has data files for."""
    binary = find_tesseract()
    if not binary:
        return ()
    try:
        out = subprocess.run(
            [binary, "--list-langs"],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=_no_window_flag(),
        )
    except Exception:
        return ()
    lines = [ln.strip() for ln in out.stdout.splitlines()[1:] if ln.strip()]
    return tuple(lines)


# --- Microsoft Word (COM) ----------------------------------------------------

WORD_HINT = (
    "Microsoft Word utilizzabile via COM non rilevato (servono Word installato e "
    "'pip install pywin32'). In alternativa installa LibreOffice."
)


@lru_cache(maxsize=1)
def has_word_com() -> bool:
    """True when Word can actually be driven through COM.

    Needs three things at once: Windows, an installed Word registering the
    ``Word.Application`` COM class, and ``pywin32`` to talk to it.  Checking only
    the registry would report success on a machine where the conversion then
    fails with ``ImportError``.

    Only ever used as a *fallback* for office-to-PDF conversion: it exists on the
    author's machine but must never be assumed present anywhere else.
    """
    if sys.platform != "win32":
        return False
    if not _has_module("win32com"):
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Word.Application\CurVer"):
            return True
    except (ImportError, OSError):
        return False


# --- Python extras -----------------------------------------------------------


def _module_version(module_name: str) -> str | None:
    try:
        import importlib.metadata as md

        return md.version(module_name)
    except Exception:
        return None


def _has_module(module_name: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError):
        return False


def _no_window_flag() -> int:
    """``CREATE_NO_WINDOW`` on Windows so subprocesses never flash a console."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


# --- Public report -----------------------------------------------------------


def detect_all(refresh: bool = False) -> list[Engine]:
    """Return the full capability report shown in the Diagnostics panel."""
    if refresh:
        for fn in (find_libreoffice, find_tesseract, tesseract_languages, has_word_com):
            fn.cache_clear()

    engines: list[Engine] = []

    # Core Python libraries - these ship with the app, so they are informational.
    # Columns: import name, display label, distribution name, purpose.
    for module, label, dist, purpose in (
        ("pikepdf", "pikepdf", "pikepdf", "lettura/scrittura pacchetti XFA"),
        ("pypdf", "pypdf", "pypdf", "campi AcroForm"),
        ("pypdfium2", "pypdfium2", "pypdfium2", "rendering pagine PDF in immagini"),
        ("pdfplumber", "pdfplumber", "pdfplumber", "estrazione testo con coordinate"),
        ("PIL", "Pillow", "pillow", "conversioni tra immagini"),
        ("reportlab", "ReportLab", "reportlab", "generazione PDF di fallback"),
        ("openpyxl", "openpyxl", "openpyxl", "fogli di calcolo XLSX"),
        ("pptx", "python-pptx", "python-pptx", "presentazioni PPTX"),
        ("mammoth", "mammoth", "mammoth", "DOCX -> HTML"),
        ("bs4", "BeautifulSoup", "beautifulsoup4", "riscrittura template XFA"),
        ("lxml", "lxml", "lxml", "validazione XML"),
    ):
        available = _has_module(module)
        engines.append(
            Engine(
                key=module,
                name=label,
                available=available,
                version=_module_version(dist) if available else None,
                purpose=purpose,
                install_hint="" if available else f"pip install {dist}",
            )
        )

    # Optional Python extras.
    heif = _has_module("pillow_heif")
    engines.append(
        Engine(
            key="pillow_heif",
            name="pillow-heif",
            available=heif,
            version=_module_version("pillow-heif") if heif else None,
            purpose="immagini HEIC/HEIF (foto iPhone)",
            install_hint="" if heif else "pip install pillow-heif",
        )
    )

    pytess = _has_module("pytesseract")
    engines.append(
        Engine(
            key="pytesseract",
            name="pytesseract",
            available=pytess,
            version=_module_version("pytesseract") if pytess else None,
            purpose="ponte Python verso Tesseract",
            install_hint="" if pytess else "pip install pytesseract",
        )
    )

    # External binaries.
    soffice = find_libreoffice()
    engines.append(
        Engine(
            key="libreoffice",
            name="LibreOffice",
            available=soffice is not None,
            path=soffice,
            purpose="DOCX/XLSX/PPTX/HTML -> PDF ad alta fedelta'",
            install_hint="" if soffice else LIBREOFFICE_HINT,
        )
    )

    tess = find_tesseract()
    langs = tesseract_languages() if tess else ()
    engines.append(
        Engine(
            key="tesseract",
            name="Tesseract OCR",
            available=tess is not None,
            path=tess,
            version=f"lingue: {', '.join(langs)}" if langs else None,
            purpose="OCR dei PDF scansionati",
            install_hint="" if tess else TESSERACT_HINT,
        )
    )

    word = has_word_com()
    engines.append(
        Engine(
            key="word_com",
            name="Microsoft Word (COM)",
            available=word,
            purpose="DOCX -> PDF tramite Word installato",
            install_hint="" if word else WORD_HINT,
        )
    )

    return engines


def is_available(key: str) -> bool:
    """Quick lookup used by the converter registry to enable/disable entries."""
    if key == "libreoffice":
        return find_libreoffice() is not None
    if key == "tesseract":
        return find_tesseract() is not None and _has_module("pytesseract")
    if key == "word_com":
        return has_word_com()
    if key == "office_to_pdf":
        # Either engine can do the job.
        return find_libreoffice() is not None or has_word_com()
    return _has_module(key)


def missing_hint(key: str) -> str:
    """The install hint to show when :func:`is_available` returned ``False``."""
    return {
        "libreoffice": LIBREOFFICE_HINT,
        "tesseract": TESSERACT_HINT,
        "word_com": WORD_HINT,
        "office_to_pdf": LIBREOFFICE_HINT,
        "pillow_heif": "pip install pillow-heif",
        "pytesseract": "pip install pytesseract",
    }.get(key, f"Componente '{key}' non disponibile.")


def run_hidden(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    """Run an external engine without flashing a console window on Windows."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=_no_window_flag(),
    )
