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

        Output will be saved to a folder next to each PDF, named after the PDF.

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

processed = []
errors = []

for fileName in fileNames:
    try:
        with pikepdf.Pdf.open(fileName) as pdfData:
            xfaDict = XfaObj(pdfData)

            sourceDir = os.path.dirname(os.path.abspath(fileName))
            folderName = re.sub(r'\.pdf$', '', os.path.basename(fileName))
            outDir = os.path.join(sourceDir, folderName)

            os.makedirs(outDir, exist_ok=True)

            for key in xfaDict.keys():
                outFile = re.sub(r'[<>: ]', '', key)
                outFile = re.sub('/', 'END', outFile)
                fullPath = os.path.join(outDir, f'{outFile}.xml')
                with open(fullPath, 'w', encoding="utf-8") as f:
                    data = xfaDict[key]
                    f.write(data)

            processed.append((fileName, outDir))
    except Exception as e:
        errors.append((fileName, str(e)))
        if not launched_via_gui:
            raise

if launched_via_gui:
    lines = [f'- {os.path.basename(f)} -> {d}' for f, d in processed]
    if errors:
        lines.append('')
        lines.append('Errori:')
        lines += [f'- {os.path.basename(f)}: {err}' for f, err in errors]
    messagebox.showinfo('Estrazione XFA completata', '\n'.join(lines) if lines else 'Nessun file elaborato.')
