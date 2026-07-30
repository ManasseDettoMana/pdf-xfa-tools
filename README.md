# XFA Studio

Desktop application that pulls an XML out of any PDF form and converts images and
documents locally. No upload, no server, no account, no database.

*[Italiano](#italiano) - [English](#english)*

---

## Italiano

### Cosa fa

**1. Estrae un XML da qualsiasi PDF.** Moduli XFA dinamici, moduli compilati,
moduli AcroForm, PDF appiattiti e scansioni. Produce sempre un XML e dice sempre
con quale strategia lo ha ottenuto.

**2. Converte file in locale**, nello spirito di convertio.co ma senza caricare
niente su internet: immagini, PDF e documenti Office.

### Le quattro strategie di estrazione

L'applicazione le prova in ordine di fedelta' e mostra sempre quale ha usato:

| Strategia | Fonte | Etichetta |
|---|---|---|
| XFA | il pacchetto `datasets` del modulo | **ESATTO** |
| AcroForm | i valori dei campi `/AcroForm` | **ESATTO** |
| Testo | il livello di testo con le coordinate | **EURISTICO** |
| OCR | Tesseract sulle pagine renderizzate | **OCR** |

Le prime due leggono i dati che il modulo contiene davvero: l'XML *e'* il
contenuto del modulo. Le altre due lo **ricostruiscono** partendo da cio' che e'
stampato sulla pagina.

> **Importante.** Appiattire un PDF cancella i pacchetti XFA. Nessuno strumento,
> nemmeno Acrobat Pro, puo' recuperarli da un file appiattito. Per questo esistono
> la terza e la quarta strategia, ed e' per questo che il risultato viene sempre
> marcato come ricostruito: cosi' sai quando fidarti e quando verificare.

### Installazione

Serve Python 3.10 o successivo.

```powershell
git clone https://github.com/ManasseDettoMana/pdf-xfa-tools.git
cd pdf-xfa-tools
python -m pip install -r requirements.txt
python -m xfatools
```

In alternativa scarica `XfaStudio.exe` dalla pagina delle release: e' autonomo,
non richiede Python ne' diritti di amministratore.

### Componenti opzionali

L'applicazione funziona senza nulla di esterno. Questi componenti aggiungono
funzionalita' e vengono rilevati automaticamente; quando mancano, le conversioni
interessate appaiono disattivate con un suggerimento invece di fallire a meta'
di un lotto.

| Componente | Serve per | Dove prenderlo |
|---|---|---|
| LibreOffice | DOCX/XLSX/PPTX -> PDF con layout fedele | [libreoffice.org](https://www.libreoffice.org/download/) |
| Tesseract OCR | leggere i PDF scansionati | [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki) |
| Microsoft Word | alternativa a LibreOffice per i DOCX | gia' installato, piu' `pip install pywin32` |
| pillow-heif | immagini HEIC/HEIF (foto iPhone) | `pip install pillow-heif` |

Per vedere cosa e' presente sul tuo computer: pulsante **Diagnostica**
nell'applicazione, oppure `python -m xfatools.cli doctor`.

### Formati supportati

- **Moduli**: PDF -> XML dei dati, XML di tutti i pacchetti XFA, XFDF, PDF
  sbloccato, piu' il reinserimento di un XML modificato dentro il PDF
- **PDF**: -> PNG / JPG / TIFF / WEBP, testo, Markdown, CSV; unione, divisione,
  rotazione, compressione, estrazione di intervalli di pagine
- **Immagini**: PNG, JPG, WEBP, BMP, TIFF, GIF, ICO, HEIC, tra loro e in PDF
- **Documenti**: DOCX, XLSX, PPTX, ODT, RTF, CSV, MD, HTML -> PDF, testo, Markdown

Niente audio e niente video, per scelta.

### Riga di comando

```powershell
python -m xfatools.cli extract documento.pdf          # catena automatica
python -m xfatools.cli extract modulo.pdf -m xfa      # forza una strategia
python -m xfatools.cli inject modulo.pdf dati.xml     # rimetti l'XML nel PDF
python -m xfatools.cli unlock decorazione.pdf         # rendi editabile
python -m xfatools.cli convert foto.png -t image-to-jpg -x quality=85
python -m xfatools.cli formats documento.pdf          # cosa si puo' fare
python -m xfatools.cli info documento.pdf             # cosa contiene il PDF
python -m xfatools.cli doctor                         # cosa e' installato
```

---

## English

### What it does

**1. Gets an XML out of any PDF.** Dynamic XFA forms, filled forms, AcroForm
PDFs, flattened PDFs and scans. It always produces an XML, and always says which
strategy produced it.

**2. Converts files locally**, in the spirit of convertio.co but with nothing
uploaded anywhere: images, PDFs and office documents.

### The four extraction strategies

Tried in descending order of fidelity, with the one used always shown:

| Strategy | Source | Badge |
|---|---|---|
| XFA | the form's `datasets` packet | **EXACT** |
| AcroForm | `/AcroForm` field values | **EXACT** |
| Text | the text layer, with coordinates | **HEURISTIC** |
| OCR | Tesseract over rendered pages | **OCR** |

The first two read data the form genuinely stores, so the XML *is* the form's
data. The other two **reconstruct** it from what is printed on the page.

> **Important.** Flattening a PDF deletes the XFA packets. No tool, Acrobat Pro
> included, can recover them from a flattened file. That is exactly why the third
> and fourth strategies exist, and why their output is always labelled as a
> reconstruction, so you know when to trust it and when to check it.

### Install

Python 3.10 or newer.

```powershell
git clone https://github.com/ManasseDettoMana/pdf-xfa-tools.git
cd pdf-xfa-tools
python -m pip install -r requirements.txt
python -m xfatools
```

Or download `XfaStudio.exe` from the releases page: it is self-contained and
needs neither Python nor administrator rights.

### Optional components

The application works with nothing external installed. LibreOffice, Tesseract,
Word via COM and pillow-heif each add capabilities, are detected at runtime, and
when absent the affected conversions appear disabled with an install hint rather
than failing mid-batch. See the table above, or run
`python -m xfatools.cli doctor`.

### Development

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q            # test suite
python -m ruff check . --fix   # lint
.\build\build.ps1              # produces dist\XfaStudio.exe
```

`xfatools/core/` never imports PySide6, so the CLI, the tests and the packaged
application all run the exact same conversion code. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design and
[docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md) for the current status.

### History

This began as four standalone scripts for reading XFA packets out of Adobe
LiveCycle forms, written during the early stages of the
[pdf-bullets](https://www.github.com/af-vcd/pdf-bullets) project. Those script
names still work, as thin wrappers over the package:

```powershell
python xfa-extract-data.py modulo.pdf   # -> xfatools.cli extract
python xfa-extract-all.py modulo.pdf    # -> xfatools.cli extract-all
python deco-unlock.py decorazione.pdf   # -> xfatools.cli unlock
```

`decos/` holds pre-unlocked AF decoration forms for drafting decos, and the
bundled XFA 2.8 specification documents the packet structure these tools read.

### Licence

Not yet decided. This repository is a fork of an upstream project that never
carried a licence file, so no licence is asserted here. If you intend to share
the executable outside your own team, settle this first: check the terms of the
original [pdf-bullets](https://www.github.com/af-vcd/pdf-bullets) project, then
add a `LICENSE` file.
