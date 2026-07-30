# Architecture

## The one rule

```
xfatools/gui/  ---depends on--->  xfatools/core/
xfatools/cli.py ---depends on-->  xfatools/core/
```

`core/` must never import PySide6. That single constraint is what makes the CLI,
the test suite and the packaged application run *identical* conversion code: a
bug reproduced from the command line is the same bug the GUI has, and a test that
passes headless is testing the real path.

The core communicates progress and cancellation through `core.job.JobContext`,
which holds two plain callables rather than Qt signals. The GUI adapts them to
signals in `gui/workers.py`; the CLI prints to stderr; the tests pass nothing.

## Module map

```
xfatools/
  core/
    errors.py     XfaToolsError and friends. Every message is safe to show a
                  user; the GUI prints str(exc) directly, so no tracebacks leak.
    xfa.py        XfaObj: a dict view over the flat [name, stream, ...] XFA
                  array, also handling the single-stream variant.
    probe.py      PdfProfile: classifies a PDF and measures its text density.
    extract.py    The fallback chain. The most important module in the project.
    inject.py     Validated XML written back into a packet, always to a new file.
    unlock.py     The AF decoration transform, ported unchanged in behaviour.
    images.py     Pillow conversions.
    pdfops.py     Rasterise, merge, split, rotate, compress, extract pages.
    documents.py  Office and text formats, with a three-tier back-end.
    registry.py   The single conversion table + run_job().
    engines.py    Runtime detection of LibreOffice, Tesseract, Word COM.
    job.py        Job, JobResult, JobContext, unique_path.
  gui/
    app.py           QApplication bootstrap.
    main_window.py   Header, body, side panel, footer.
    workers.py       QThreadPool wrapper; the only place threads are created.
    theme.py         Palette dataclass -> full stylesheet.
    i18n.py          Live language switching.
    translations.py  Both catalogs, side by side.
    settings.py      Atomic JSON in %APPDATA%.
    widgets/         dropzone, queue_table, options_panel, diagnostics.
  cli.py        argparse over the same core.
```

## The extraction chain

`extract.extract_xml(path, mode="auto")` walks four strategies, skipping any the
`PdfProfile` already rules out, and returns an `ExtractResult` carrying the XML
*and its provenance*:

| Strategy | Reads | Confidence | Badge |
|---|---|---|---|
| `xfa` | the `datasets` packet | EXACT | EXACT |
| `acroform` | `/AcroForm` field values | EXACT | EXACT |
| `text` | pdfplumber words with bounding boxes | HEURISTIC | HEURISTIC |
| `ocr` | pypdfium2 render into Tesseract | LOW | OCR |

The provenance is not decoration. A flattened PDF has had its XFA packets
*deleted*; the text and OCR strategies produce a plausible XML that is
nonetheless a reconstruction, and presenting that as the form's real data would
be actively misleading. The badge is how the interface stays honest.

`unwrap_datasets()` is deliberately a textual transform rather than a DOM one.
Re-serialising through a parser reflows whitespace and reorders attributes, and
LiveCycle Designer rejects the result. `rewrap_datasets()` is its exact inverse,
which is what makes the extract-edit-inject round trip lossless.

## The conversion registry

`core/registry.py` holds one tuple of `Converter` entries. Each declares its
source extensions, target extension, handler, required engines and options. That
single table drives:

- the GUI's per-row format dropdown, grouped by category
- which entries are greyed out, and the install hint shown when they are
- the options panel, built generically from the `Option` list
- the CLI's `convert` and `formats` subcommands
- `run_job()` dispatch

Adding a conversion means adding one entry. No UI code changes.

Handlers share `(src, dst, options, ctx) -> list[Path]`. When `multi_output` is
set, `dst` is a *directory*, because the operation produces an unknown number of
files.

## Threading

`gui/workers.py` is the only place that creates threads. One `QRunnable` per
job, `min(4, cpu_count)` at a time.

Cancellation is cooperative. A `threading.Event` is exposed to the core through
`JobContext.is_cancelled`, and long loops call `ctx.check_cancelled()` between
pages. Nothing is killed mid-write, so a cancelled batch never leaves a
truncated file behind.

The pool is deliberately **not** cleared on cancel: a dropped runnable never
emits `finished`, which would leave the batch permanently short of results. Every
queued job runs, sees the flag on its first check and returns at once.

## Error handling

Everything the toolkit raises deliberately subclasses `XfaToolsError` and carries
a user-safe message plus an optional `hint`. `run_job()` never raises: failures
come back as a `JobResult` with a status, so one bad file cannot take down a
batch or strand the queue.

## Themes and translation

`theme.Palette` is a frozen dataclass of colour *roles*. `build_stylesheet()`
renders the entire application stylesheet from one palette, so light and dark
cannot drift apart and a third theme is one more palette. Widgets select a role
with `setObjectName` or a dynamic property (`variant`, `badge`, `state`); after
changing a property, `theme.restyle(widget)` must be called because Qt does not
repolish automatically.

Translation is live. Widgets never store translated text: they implement
`retranslate()`, call `tr()` inside it, and connect it to
`translator.language_changed`. Switching costs one signal emission.

## Deliberate non-goals

- **No database.** Settings are one small JSON file.
- **No network.** Nothing is uploaded, and there is no update check.
- **No audio or video.** Out of scope by decision.
- **No required external engine.** Everything pure-Python works out of the box.
