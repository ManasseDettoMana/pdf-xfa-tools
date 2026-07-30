"""Shared fixtures. The repository's own sample PDFs are the test corpus."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DECOS_DIR = REPO_ROOT / "decos"
SPEC_PDF = REPO_ROOT / "xfa forms 2.8 spec.pdf"


@pytest.fixture(scope="session")
def xfa_pdf() -> Path:
    """A real dynamic XFA decoration form."""
    path = DECOS_DIR / "MSM_unlocked.pdf"
    if not path.exists():
        pytest.skip(f"PDF di esempio mancante: {path}")
    return path


@pytest.fixture(scope="session")
def all_xfa_pdfs() -> list[Path]:
    paths = sorted(DECOS_DIR.glob("*_unlocked.pdf"))
    if not paths:
        pytest.skip("nessun PDF di esempio in decos/")
    return paths


@pytest.fixture(scope="session")
def non_xfa_pdf() -> Path:
    """A large, plain PDF with a text layer and no form of any kind."""
    if not SPEC_PDF.exists():
        pytest.skip(f"PDF di esempio mancante: {SPEC_PDF}")
    return SPEC_PDF


@pytest.fixture
def pdf_copy(tmp_path: Path):
    """Copy a sample PDF into a temp dir so tests never write next to the source."""

    def _copy(source: Path) -> Path:
        target = tmp_path / source.name
        shutil.copy2(source, target)
        return target

    return _copy
