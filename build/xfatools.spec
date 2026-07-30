# PyInstaller specification for XFA Studio.
#
# Produces a single windowed executable with no console. The exclusion list is
# not cosmetic: several heavyweight packages are installed in a typical
# environment and get pulled in transitively, roughly doubling the output size
# without any converter using them.
#
# Build with build\build.ps1 rather than calling PyInstaller directly, so the
# working directory and output paths are consistent.

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

PROJECT_ROOT = Path(SPECPATH).parent
ICON_PATH = PROJECT_ROOT / "build" / "icon.ico"

# Packages that are either unused or dragged in by an unrelated dependency.
# pandas and matplotlib come in through pdfplumber's optional extras; magika and
# onnxruntime through markitdown; the Qt modules are simply not used.
EXCLUDES = [
    "matplotlib",
    "pandas",
    "numpy.f2py",
    "magika",
    "onnxruntime",
    "scipy",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "setuptools._distutils",
    "tkinter",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQml",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtSql",
]

# Optional extras: bundled when present, absent without breaking the build.
# The application detects them at runtime, so a build machine without them
# simply produces an executable with those features disabled.
OPTIONAL_HIDDEN = []
for module in ("pytesseract", "pillow_heif", "win32com.client", "pythoncom", "markdownify"):
    try:
        __import__(module)
    except ImportError:
        continue
    OPTIONAL_HIDDEN.append(module)

HIDDEN_IMPORTS = [
    "pikepdf",
    "pypdf",
    "pypdfium2",
    "pdfplumber",
    "PIL",
    "PIL.Image",
    "reportlab.pdfbase._fontdata",
    "openpyxl",
    "pptx",
    "mammoth",
    "markdown",
    "bs4",
    "lxml.etree",
    "lxml._elementpath",
    *collect_submodules("xfatools"),
    *OPTIONAL_HIDDEN,
]


a = Analysis(
    # build/entry.py, not xfatools/__main__.py: PyInstaller runs the entry
    # script as top-level __main__ with no package context, so __main__.py's
    # relative imports would fail and the application would exit at once.
    [str(PROJECT_ROOT / "build" / "entry.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="XfaStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # windowed: no console flashes behind the interface
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON_PATH) if ICON_PATH.exists() else None,
)
