# Project context - living status log

Read this file first when resuming work. It records where the project stands,
what was decided and why, and what to do next. Update it at the end of every
phase, and before stopping for any reason.

- **Branch:** merged into `master`; `feature/desktop-app` kept as the phase history
- **Remote:** https://github.com/ManasseDettoMana/pdf-xfa-tools
- **Last updated:** 2026-07-30, all six phases merged to `master`
- **Status:** Phases 1-6 complete. 104 tests green, 1 skipped, ruff clean,
  `dist\XfaStudio.exe` builds (98.5 MB) and launches.

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
- [x] **Phase 2 - conversion engine** (registry, images, pdfops, documents)
- [x] **Phase 3 - GUI shell** (drop zone, queue, workers, settings)
- [x] **Phase 4 - theme, i18n, polish** - pulled forward into Phase 3. Writing
      every string hardcoded and converting later is wasteful and reliably
      misses strings, so `tr()` and the theme went in from the first widget.
      Remaining for a later pass: XML preview pane, toast notifications.
- [x] **Phase 5 - packaging** (PyInstaller one-file .exe, icon, build script)
- [x] **Phase 6 - docs, CI, release** (README, ARCHITECTURE, CI and release
      workflows, merged to `master`)

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

## What exists after Phase 2

25 converters in one table (`core/registry.py`), driving the GUI dropdown, the
CLI and the job runner alike. Adding a conversion means adding one `Converter`
entry - no UI change.

- `core/images.py` - Pillow conversions handling the cases a naive
  `open().save()` gets wrong: alpha flattened to a real background instead of
  black, EXIF orientation, CMYK, palette images, ICO clamped to 256 px.
- `core/pdfops.py` - rasterise (pypdfium2, no external binary), merge, split,
  rotate, lossless compress, extract a page range.
- `core/documents.py` - office to PDF through LibreOffice, then Word COM, then a
  ReportLab reflow; PDF to text/Markdown/CSV; spreadsheet to CSV.
- `cli.py` gains `convert` and `formats`.

Two design corrections made while building this phase, both worth keeping:

1. `targets_for()` originally hid every same-extension conversion to avoid
   offering "PNG to PNG". That silently removed rotate, compress, unlock and
   extract-pages, which are legitimately PDF to PDF. The rule now only applies
   to the image category.
2. Extraction provenance first travelled through a module-level dict keyed by
   path. That is shared mutable state and would race once several worker threads
   run. It now rides on `JobContext.metadata`, which is per job.

## What exists after Phase 3

A working desktop application: `python -m xfatools`.

- `gui/theme.py` - one `Palette` dataclass generates the entire stylesheet, so
  light and dark cannot drift apart. Widgets opt into a role via `objectName` or
  a dynamic property; `restyle()` repolishes after a property change.
- `gui/i18n.py` + `translations.py` - both catalogs in one file, live switching
  through a `language_changed` signal and a `retranslate()` method per widget.
- `gui/workers.py` - `QThreadPool`, one runnable per job, cooperative cancel.
- `gui/widgets/` - drop zone (files and folders, recursive, deduped), queue
  table with a per-row target format, generic options panel built from the
  registry, result panel with the provenance badge, diagnostics dialog.

Verified headless, end to end: four XFA forms convert with a green EXACT badge
while the 1345-page spec PDF falls through to an amber HEURISTIC badge in the
same batch.

Three bugs found and fixed during this phase, all worth remembering:

1. `WorkerSignals` had no Qt parent. Workers hold it across threads, so it could
   be destroyed mid-run: "Signal source has been deleted". Always parent it, and
   `runner.shutdown()` now runs on close unconditionally, because probe workers
   are not part of a batch and "not running" does not mean the pool is idle.
2. `JobRunner.cancel()` called `pool.clear()`. Dropped runnables never emit
   `finished`, so the batch could never complete and the UI stayed stuck on
   "running". Cancellation now lets every job start and return immediately via
   an early `ctx.check_cancelled()` in `run_job`.
3. The blanket `QWidget { background-color }` rule painted every `QLabel`,
   putting grey bands behind all text on cards. Labels and check boxes are now
   explicitly transparent, and plain container widgets inside a card use
   `objectName="PanelBody"`.

## What exists after Phase 5

`build\build.ps1` produces `dist\XfaStudio.exe`, a single windowed executable of
roughly 100 MB. It gates on the test suite unless `-SkipTests` is passed, cleans
previous output and reports the final size. `build/make_icon.py` draws
`build/icon.ico` so the mark is reviewable in the diff rather than an opaque
binary from a design tool.

The first build produced an executable that exited instantly with code 1. Cause:
PyInstaller runs its entry script as top-level `__main__` with no package
context, so the relative import in `xfatools/__main__.py`
(`from .gui.app import run`) failed inside the bundle. The frozen build now
enters through `build/entry.py`, which uses absolute imports only. `python -m
xfatools` still goes through `__main__.py`.

Because a windowed build has no console, that failure was completely silent -
stderr goes nowhere. `entry.py` now writes any startup exception to
`%APPDATA%/XfaStudio/startup-error.log` and shows a message box, so the next
such failure is diagnosable instead of invisible.

The `excludes` list in the spec is load-bearing, not cosmetic: pandas and
matplotlib arrive through pdfplumber's optional extras and magika/onnxruntime
through markitdown, none of which any converter uses.

## Environment notes

- Python 3.13.14, PySide6 6.11.1.
- **Not installed:** LibreOffice, Tesseract. So OCR and high-fidelity office
  conversion cannot be tested here - those tests are marked `requires_engine`
  and skip cleanly.
- **Installed:** Microsoft Office 16, so the Word COM path is testable locally.
  It must stay a fallback, never a requirement.

## Next step

The six planned phases are done and on `master`. In rough priority order, the
things deliberately left out so far:

1. **XML preview pane** in the result panel, with syntax highlighting. The
   result panel currently lists output file names only.
2. **An inject flow in the GUI.** `core/inject.py` and the CLI both support
   writing an edited XML back into a PDF; the interface does not expose it yet.
3. **Toast notifications** instead of the footer status label.
4. **Template-aware extraction** - the fourth option the user was offered in
   planning and did not pick: match reconstructed text against a known XFA
   template from `decos/` so a flattened form yields field names matching the
   original. This is the only way heuristic output would ever approach EXACT.
5. Verify the `.exe` on a machine with no Python at all. It has only been run on
   the build machine so far, which cannot prove independence.

Testing note: GUI tests run under `QT_QPA_PLATFORM=offscreen`, which has no
system fonts. That is fine for assertions but renders text as empty boxes in
screenshots - load `C:/Windows/Fonts/segoeui.ttf` via `QFontDatabase` first if
you need a readable capture.

## Open questions

- **Licence.** No licence file has ever existed in this repository, and it is a
  fork of an upstream project. `pyproject.toml` briefly claimed MIT during
  Phase 6; that was an invention and has been removed. The user needs to decide
  this before the `.exe` is distributed outside their own team.
- Should the app offer to install LibreOffice/Tesseract, or only link to them?
  (Currently: link only, via the Diagnostics panel.)
- OCR and high-fidelity office conversion have never been executed anywhere:
  neither Tesseract nor LibreOffice is installed on the development machine, and
  the CI runner does not have them either. That code is written and its error
  paths are tested, but its success path is unverified.
