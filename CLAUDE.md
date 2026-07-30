# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this project is

**XFA Studio** - an offline Windows desktop application that does two things:

1. **Gets an XML out of any PDF.** Dynamic XFA forms, filled XFA forms, AcroForm
   PDFs, flattened PDFs, and scans. It always produces an XML and always says
   which strategy produced it.
2. **Converts files locally**, in the spirit of convertio.co but with no upload,
   no server and no account: images, PDFs and office documents. No audio, no video.

It replaces four loose scripts that only worked on XFA PDFs and only for someone
with the right Python packages installed.

## Commands

```powershell
python -m pip install -r requirements-dev.txt   # full dev environment
python -m xfatools                              # launch the GUI
python -m xfatools.cli --help                   # the CLI
python -m xfatools.cli doctor                   # which engines are available
python -m pytest -q                             # test suite
python -m ruff check . --fix                    # lint
.\build\build.ps1                               # build dist\XfaStudio.exe
```

## Layout

```
xfatools/
  core/        engine: no Qt imports allowed here, ever
    xfa.py       XfaObj - dict view over the XFA packet array
    probe.py     PdfProfile - what can be extracted from a given PDF
    extract.py   the fallback chain (the most important module)
    inject.py    edited XML -> back into the PDF
    unlock.py    AF decoration unlock transform
    registry.py  conversion registry driving both GUI and CLI
    engines.py   runtime detection of LibreOffice / Tesseract / Word COM
    job.py       Job, JobResult, JobContext (progress + cancellation)
  gui/         PySide6 layer; depends on core, never the reverse
  cli.py       argparse interface over the same core
tests/         pytest, using decos/*.pdf as the corpus
docs/PROJECT_CONTEXT.md   living status log - read this first
```

Root-level `xfa-extract-all.py`, `xfa-extract-data.py`, `deco-unlock.py` and
`xfaTools.py` are deprecation shims forwarding into the package. Keep them working.

## Invariants

These are not style preferences; breaking them produces wrong behaviour or misleads users.

1. **A flattened PDF can never yield real XFA XML.** Flattening deletes the XFA
   packets; Acrobat Pro cannot recover them either. The `text` and `ocr`
   strategies *reconstruct* an XML and must always be labelled `HEURISTIC` / `OCR`,
   never presented as the form's actual data.
2. **`core/` must not import PySide6.** That is what keeps the CLI, the tests and
   the packaged app running identical code.
3. **External engines are optional.** LibreOffice, Tesseract and Word COM are
   detected at runtime via `core/engines.py`. Never assume any of them exists -
   Word COM happens to be installed on the author's machine and on almost no one
   else's. Missing engines disable a conversion with an install hint; they never
   crash a batch.
4. **Never block the UI thread.** All core work runs in `QThreadPool` workers.
   Long loops accept a `JobContext` and call `ctx.check_cancelled()` per page.
5. **Never overwrite a user's file silently.** Use `core.job.unique_path()`.
6. **All user-facing strings go through `tr()`** (Phase 4 onward). Default
   language Italian, with English available; the switch is live, no restart.
7. **No emojis** anywhere - UI, code, comments, docs or commit messages.
8. `unwrap_datasets()` is deliberately textual, not DOM-based. Re-serialising
   through a parser reflows whitespace and breaks LiveCycle Designer. Do not
   "improve" it into an lxml transform.

## Conventions

- Code, comments and docstrings in English; user-facing strings in Italian
  (moving into `i18n/` catalogs in Phase 4).
- Errors subclass `core.errors.XfaToolsError` and carry a user-safe message plus
  an optional `hint`. The GUI prints `str(exc)` directly - no tracebacks leak.
- Every phase ends with: tests green, ruff clean, `docs/PROJECT_CONTEXT.md`
  updated, commit, push.
