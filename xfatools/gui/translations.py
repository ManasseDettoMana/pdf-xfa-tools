"""Translation catalogs.

Both languages live in one file, side by side, so a missing key is obvious at a
glance and the test suite can assert the two stay in step.  Plain Python dicts
rather than JSON resources: nothing to locate at runtime, which keeps the
packaged executable simple.

Keys are dotted and namespaced by area (``queue.``, ``options.``...).  Values may
contain ``{placeholders}`` filled by :func:`xfatools.gui.i18n.tr`.
"""

from __future__ import annotations

ITALIAN: dict[str, str] = {
    # -- application ---------------------------------------------------
    "app.title": "XFA Studio",
    "app.subtitle": "Estrazione XML e conversione file, in locale",
    # -- header --------------------------------------------------------
    "header.theme.light": "Tema chiaro",
    "header.theme.dark": "Tema scuro",
    "header.theme.tooltip": "Cambia tema chiaro/scuro",
    "header.language.tooltip": "Cambia lingua",
    "header.diagnostics": "Diagnostica",
    "header.diagnostics.tooltip": "Mostra i componenti installati",
    "header.about": "Informazioni",
    # -- drop zone -----------------------------------------------------
    "drop.title": "Trascina qui i tuoi file",
    "drop.subtitle": "PDF, immagini e documenti. Nessun caricamento su internet.",
    "drop.browse": "Sfoglia i file",
    "drop.browse_folder": "Aggiungi una cartella",
    "drop.active": "Rilascia per aggiungere",
    "drop.rejected": "{count} file ignorati: formato non supportato",
    "drop.filter": "Tutti i file supportati",
    "drop.filter_all": "Tutti i file",
    # -- queue ---------------------------------------------------------
    "queue.header.name": "File",
    "queue.header.type": "Tipo rilevato",
    "queue.header.target": "Converti in",
    "queue.header.status": "Stato",
    "queue.header.result": "Risultato",
    "queue.empty": "Nessun file in coda",
    "queue.count": "{count} file in coda",
    "queue.count_one": "1 file in coda",
    "queue.remove": "Rimuovi dalla coda",
    "queue.open_file": "Apri il file prodotto",
    "queue.open_folder": "Apri la cartella",
    "queue.analysing": "Analisi...",
    # -- statuses ------------------------------------------------------
    "status.pending": "In attesa",
    "status.running": "In corso",
    "status.done": "Completato",
    "status.failed": "Errore",
    "status.cancelled": "Annullato",
    "status.skipped": "Non disponibile",
    # -- pdf kinds -----------------------------------------------------
    "kind.dynamic_xfa": "Modulo XFA dinamico",
    "kind.static_xfa": "Modulo XFA statico",
    "kind.acroform": "Modulo PDF (AcroForm)",
    "kind.text": "PDF appiattito / testo",
    "kind.scanned": "PDF scansionato",
    "kind.unknown": "Sconosciuto",
    # -- badges --------------------------------------------------------
    "badge.EXACT": "ESATTO",
    "badge.HEURISTIC": "EURISTICO",
    "badge.OCR": "OCR",
    "badge.APPROSSIMATO": "APPROSSIMATO",
    "badge.exact.tooltip": "I dati provengono dal modulo stesso: estrazione fedele.",
    "badge.heuristic.tooltip": (
        "Il PDF non contiene dati strutturati. L'XML e' stato ricostruito dal "
        "contenuto della pagina: va verificato."
    ),
    "badge.ocr.tooltip": "Testo riconosciuto otticamente da un'immagine: verifica i valori.",
    "badge.approssimato.tooltip": "Layout ricostruito senza motore di rendering.",
    # -- options -------------------------------------------------------
    "options.title": "Opzioni",
    "options.none": "Questa conversione non ha opzioni.",
    "options.no_selection": "Seleziona un file per vederne le opzioni.",
    "options.reset": "Ripristina i valori predefiniti",
    "options.apply_all": "Applica a tutti i file dello stesso tipo",
    # -- footer --------------------------------------------------------
    "footer.output": "Salva in:",
    "footer.output.beside": "Accanto al file di origine",
    "footer.output.custom": "Cartella scelta...",
    "footer.choose_folder": "Scegli...",
    "footer.convert": "Converti",
    "footer.convert_count": "Converti {count} file",
    "footer.cancel": "Annulla",
    "footer.clear": "Svuota la coda",
    "footer.progress": "{done} di {total} completati",
    # -- results -------------------------------------------------------
    "result.title": "Risultato",
    "result.source": "Strategia usata:",
    "result.warnings": "Da verificare",
    "result.outputs": "File prodotti",
    "result.preview": "Anteprima",
    "result.copy": "Copia negli appunti",
    "result.copied": "Copiato negli appunti",
    "result.summary_ok": "{count} conversioni completate",
    "result.summary_mixed": "{ok} completate, {failed} con errori",
    "result.summary_failed": "Nessuna conversione completata",
    # -- diagnostics ---------------------------------------------------
    "diag.title": "Componenti installati",
    "diag.intro": (
        "L'applicazione funziona senza componenti esterni. Quelli mancanti "
        "disattivano solo alcune conversioni."
    ),
    "diag.component": "Componente",
    "diag.status": "Stato",
    "diag.purpose": "Serve per",
    "diag.available": "Disponibile",
    "diag.missing": "Non installato",
    "diag.refresh": "Rileva di nuovo",
    "diag.close": "Chiudi",
    # -- errors and dialogs --------------------------------------------
    "error.title": "Errore",
    "error.no_converter": "Nessuna conversione disponibile per '{name}'.",
    "error.nothing_to_do": "Aggiungi almeno un file prima di convertire.",
    "dialog.choose_output": "Scegli la cartella di destinazione",
    "dialog.choose_files": "Scegli i file da convertire",
    "dialog.choose_folder": "Scegli una cartella",
    "dialog.close_running.title": "Conversione in corso",
    "dialog.close_running.body": "Ci sono conversioni in corso. Vuoi annullarle e uscire?",
    "dialog.yes": "Si'",
    "dialog.no": "No",
    # -- about ---------------------------------------------------------
    "about.title": "Informazioni su XFA Studio",
    "about.version": "Versione {version}",
    "about.description": (
        "Estrae l'XML dai moduli PDF e converte immagini e documenti, "
        "interamente sul tuo computer. Nessun caricamento, nessun account."
    ),
    "about.note_flattened": (
        "Nota: un PDF appiattito non contiene piu' i pacchetti XFA originali. "
        "In quel caso l'XML viene ricostruito e marcato come tale."
    ),
}

ENGLISH: dict[str, str] = {
    "app.title": "XFA Studio",
    "app.subtitle": "XML extraction and file conversion, offline",
    "header.theme.light": "Light theme",
    "header.theme.dark": "Dark theme",
    "header.theme.tooltip": "Switch between light and dark",
    "header.language.tooltip": "Change language",
    "header.diagnostics": "Diagnostics",
    "header.diagnostics.tooltip": "Show which components are installed",
    "header.about": "About",
    "drop.title": "Drop your files here",
    "drop.subtitle": "PDFs, images and documents. Nothing is uploaded anywhere.",
    "drop.browse": "Browse files",
    "drop.browse_folder": "Add a folder",
    "drop.active": "Release to add",
    "drop.rejected": "{count} files ignored: unsupported format",
    "drop.filter": "All supported files",
    "drop.filter_all": "All files",
    "queue.header.name": "File",
    "queue.header.type": "Detected type",
    "queue.header.target": "Convert to",
    "queue.header.status": "Status",
    "queue.header.result": "Result",
    "queue.empty": "No files queued",
    "queue.count": "{count} files queued",
    "queue.count_one": "1 file queued",
    "queue.remove": "Remove from queue",
    "queue.open_file": "Open the produced file",
    "queue.open_folder": "Open containing folder",
    "queue.analysing": "Analysing...",
    "status.pending": "Waiting",
    "status.running": "Running",
    "status.done": "Done",
    "status.failed": "Failed",
    "status.cancelled": "Cancelled",
    "status.skipped": "Unavailable",
    "kind.dynamic_xfa": "Dynamic XFA form",
    "kind.static_xfa": "Static XFA form",
    "kind.acroform": "PDF form (AcroForm)",
    "kind.text": "Flattened / text PDF",
    "kind.scanned": "Scanned PDF",
    "kind.unknown": "Unknown",
    "badge.EXACT": "EXACT",
    "badge.HEURISTIC": "HEURISTIC",
    "badge.OCR": "OCR",
    "badge.APPROSSIMATO": "APPROXIMATE",
    "badge.exact.tooltip": "The data comes from the form itself: a faithful extraction.",
    "badge.heuristic.tooltip": (
        "This PDF holds no structured form data. The XML was reconstructed from "
        "the page content and should be checked."
    ),
    "badge.ocr.tooltip": "Text recognised optically from an image: verify the values.",
    "badge.approssimato.tooltip": "Layout rebuilt without a rendering engine.",
    "options.title": "Options",
    "options.none": "This conversion has no options.",
    "options.no_selection": "Select a file to see its options.",
    "options.reset": "Reset to defaults",
    "options.apply_all": "Apply to every file of the same type",
    "footer.output": "Save to:",
    "footer.output.beside": "Next to the source file",
    "footer.output.custom": "Chosen folder...",
    "footer.choose_folder": "Choose...",
    "footer.convert": "Convert",
    "footer.convert_count": "Convert {count} files",
    "footer.cancel": "Cancel",
    "footer.clear": "Clear the queue",
    "footer.progress": "{done} of {total} done",
    "result.title": "Result",
    "result.source": "Strategy used:",
    "result.warnings": "Worth checking",
    "result.outputs": "Files produced",
    "result.preview": "Preview",
    "result.copy": "Copy to clipboard",
    "result.copied": "Copied to clipboard",
    "result.summary_ok": "{count} conversions completed",
    "result.summary_mixed": "{ok} completed, {failed} failed",
    "result.summary_failed": "No conversion completed",
    "diag.title": "Installed components",
    "diag.intro": (
        "The application works without any external component. Missing ones only "
        "disable specific conversions."
    ),
    "diag.component": "Component",
    "diag.status": "Status",
    "diag.purpose": "Used for",
    "diag.available": "Available",
    "diag.missing": "Not installed",
    "diag.refresh": "Detect again",
    "diag.close": "Close",
    "error.title": "Error",
    "error.no_converter": "No conversion available for '{name}'.",
    "error.nothing_to_do": "Add at least one file before converting.",
    "dialog.choose_output": "Choose the destination folder",
    "dialog.choose_files": "Choose the files to convert",
    "dialog.choose_folder": "Choose a folder",
    "dialog.close_running.title": "Conversion in progress",
    "dialog.close_running.body": "Conversions are still running. Cancel them and quit?",
    "dialog.yes": "Yes",
    "dialog.no": "No",
    "about.title": "About XFA Studio",
    "about.version": "Version {version}",
    "about.description": (
        "Extracts XML from PDF forms and converts images and documents entirely "
        "on your own machine. No upload, no account."
    ),
    "about.note_flattened": (
        "Note: a flattened PDF no longer contains the original XFA packets. In "
        "that case the XML is reconstructed and labelled accordingly."
    ),
}

CATALOGS: dict[str, dict[str, str]] = {
    "it": ITALIAN,
    "en": ENGLISH,
}

#: Shown in the language selector.
LANGUAGE_NAMES: dict[str, str] = {
    "it": "Italiano",
    "en": "English",
}

DEFAULT_LANGUAGE = "it"
