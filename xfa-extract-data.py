import pikepdf
import sys
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox
from xfaTools import XfaObj


def show_help():
    print(f'''
USAGE:

    python {os.path.basename(sys.argv[0])} 'PATH_TO_PDF.pdf' [... MORE_PDFS.pdf ]

        Estrae solo il packet XFA 'datasets' da ciascun PDF e lo salva come
        '<NomePdf>.xml' nella stessa cartella di questo script, nel formato
        "sample data file" (radice <xfa:data>, senza il wrapper <xfa:datasets>)
        pronto per essere agganciato in Adobe LiveCycle Designer.

    Avviato senza argomenti (es. doppio click) si apre una finestra per scegliere i PDF.
    ''')


def pick_files_via_gui():
    root = tk.Tk()
    root.withdraw()
    paths = filedialog.askopenfilenames(
        title='Seleziona uno o più PDF da analizzare',
        filetypes=[('PDF files', '*.pdf')]
    )
    root.destroy()
    return list(paths)


def unwrap_datasets(raw):
    '''
    Converte il packet XFA 'datasets' (radice <xfa:datasets><xfa:data>...</xfa:data></xfa:datasets>)
    nel formato "sample data file" con radice <xfa:data>, spostando l'attributo xmlns:xfa
    sul tag <xfa:data>. Trasformazione puramente testuale per non alterare whitespace/attributi
    del resto del documento.
    '''
    head_match = re.match(
        r'^<xfa:datasets\s+([^>]*?)\s*\n?>\s*<xfa:data(\s[^>]*)?\n?>',
        raw
    )
    tail_match = re.search(r'</xfa:data\s*\n?>\s*</xfa:datasets\s*\n?>\s*$', raw)

    if not head_match or not tail_match:
        raise ValueError("Struttura del packet 'datasets' inattesa: impossibile rimuovere il wrapper <xfa:datasets>.")

    xmlns_attrs = head_match.group(1).strip()
    data_attrs = (head_match.group(2) or '').strip()
    new_head = f'<xfa:data {xmlns_attrs}{(" " + data_attrs) if data_attrs else ""}\n>'

    body = raw[head_match.end():tail_match.start()]
    new_tail = '</xfa:data\n>'

    return new_head + body + new_tail


launched_via_gui = False

if len(sys.argv) == 1:
    launched_via_gui = True
    fileNames = pick_files_via_gui()
    if not fileNames:
        quit()
elif re.match(r'(^-+h)', sys.argv[1]):
    show_help()
    quit()
else:
    fileNames = sys.argv[1:]

scriptDir = os.path.dirname(os.path.abspath(__file__))

processed = []
errors = []

for fileName in fileNames:
    try:
        with pikepdf.Pdf.open(fileName) as pdfData:
            xfaDict = XfaObj(pdfData)

            rawDatasets = xfaDict['datasets']
            dataXml = '<?xml version="1.0" encoding="UTF-8"?>\n' + unwrap_datasets(rawDatasets)

            baseName = re.sub(r'\.pdf$', '', os.path.basename(fileName), flags=re.IGNORECASE)
            outFile = os.path.join(scriptDir, f'{baseName}.xml')

            with open(outFile, 'w', encoding='utf-8') as f:
                f.write(dataXml)

            processed.append((fileName, outFile))
    except Exception as e:
        errors.append((fileName, str(e)))
        if not launched_via_gui:
            raise

if launched_via_gui:
    lines = [f'- {os.path.basename(f)} -> {out}' for f, out in processed]
    if errors:
        lines.append('')
        lines.append('Errori:')
        lines += [f'- {os.path.basename(f)}: {err}' for f, err in errors]
    messagebox.showinfo('Estrazione dati XFA completata', '\n'.join(lines) if lines else 'Nessun file elaborato.')
