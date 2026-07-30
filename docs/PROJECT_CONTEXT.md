# Project context - living status log

Read this file first when resuming work. It records where the project stands,
what was decided and why, and what to do next. Update it at the end of every
phase, and before stopping for any reason.

- **Branch:** `feature/desktop-app` (from `master`)
- **Remote:** https://github.com/ManasseDettoMana/pdf-xfa-tools
- **Last updated:** 2026-07-30, end of Phase 1
- **Status:** Phase 1 complete. Phase 2 (conversion engine) is next.

---

## The goal

Turn four loose scripts into **XFA Studio**: a professional, offline desktop
application that (1) extracts an XML from any PDF, including flattened and filled
dynamic forms, and (2) converts images and documents locally, convertio-style,
with no upload and no database.

Requested explicitly by the user: drag and drop, dark/light theme, live IT/EN
switching, professional look and UX, runs smoothly locally, everything pushed to
GitHub. No emojis anywhere. Best practices throughout.

## Decisions and their rationale

| Decision | Why |
|---|---|
| **PySide6/Qt** for the GUI | Chosen by the user over CustomTkinter and a web UI. Native drag and drop, real stylesheets, thread pools, packages into one .exe. |
| **Fallback chain** for extraction, with a visible badge | A flattened PDF has no XFA packets left to recover. Rather than failing, reconstruct from AcroForm/text/OCR and label the confidence honestly. |
| **Engines optional and auto-detected** | The app must work out of the box. LibreOffice/Tesseract/Word COM improve fidelity but are never required. |
| **Flat `xfatools/` package, no `src/`** | `python -m xfatools` works with no install step, which keeps PyInstaller simple. |
| **Old scripts kept as shims** | Existing habits and desktop shortcuts keep working; the logic lives in one place. |
| **`DEFAULT_MAX_PAGES = 100`** | Found during Phase 1: the 1345-page spec PDF took ~3 minutes and produced a 5.4 MB XML. Capping brought it to 4.8 s. Truncation is recorded on the XML root and surfaced as a warning, never hidden. |
| **`JobContext` instead of Qt signals in core** | Keeps `core/` importable without Qt, so CLI and tests exercise identical code. |

## Phase status

- [x] **Phase 1 - skeleton and core extraction**
- [ ] **Phase 2 - conversion engine** (registry, images, pdfops, documents)
- [ ] **Phase 3 - GUI shell** (drop zone, queue, workers, settings)
- [ ] **Phase 4 - theme, i18n, polish** (QSS, live IT/EN, diagnostics, badges)
- [ ] **Phase 5 - packaging** (PyInstaller one-file .exe)
- [ ] **Phase 6 - docs, CI, release** (README, Actions, PR)

## What exists after Phase 1

Working, tested and linted (31 tests green, ruff clean):

- `core/xfa.py` - `XfaObj`, now handling both the name/stream array form and the
  rarer single-stream form, with real errors instead of `AttributeError`.
- `core/probe.py` - `PdfProfile` classifying a PDF as dynamic XFA / static XFA /
  AcroForm / text / scanned, sampling at most 3 pages.
- `core/extract.py` - the four strategies plus the `auto` chain, `unwrap_datasets`
  (preserved byte-for-byte) and its new inverse `rewrap_datasets`.
- `core/inject.py` - validated XML written back into a packet, always to a new file.
- `core/unlock.py` - the deco unlock transform, now reporting what it changed.
- `core/engines.py` - runtime detection plus install hints.
- `core/job.py` - `Job`, `JobResult`, `JobContext`, `unique_path`.
- `cli.py` - `extract`, `extract-all`, `xfdf`, `inject`, `unlock`, `info`, `doctor`.
- Shims for the four original script names.

Verified on this machine:
- `decos/*.pdf` -> `EXACT` via the XFA datasets packet.
- `xfa forms 2.8 spec.pdf` (1345 pages, no form) -> falls through to `HEURISTIC`
  text reconstruction with the truncation warning.
- Inject round-trip: edit `MemberFullName`, write, re-extract, value present.

## Environment notes

- Python 3.13.14, PySide6 6.11.1.
- **Not installed:** LibreOffice, Tesseract. So OCR and high-fidelity office
  conversion cannot be tested here - those tests are marked `requires_engine`
  and skip cleanly.
- **Installed:** Microsoft Office 16, so the Word COM path is testable locally.
  It must stay a fallback, never a requirement.

## Next step

Start Phase 2: `core/registry.py` first, since the GUI's format dropdown, the
greying-out of unavailable conversions and the CLI `convert` subcommand are all
driven by it. Then `images.py`, `pdfops.py`, `documents.py`.

## Open questions

None blocking. Worth confirming with the user eventually:
- Should the app offer to install LibreOffice/Tesseract, or only link to them?
  (Currently: link only, via the Diagnostics panel.)
