# PyInstaller recipe for the desktop builds (Windows and Linux).
#   pyinstaller packaging/tcsoffice.spec --noconfirm
# Output: dist/TCsOffice/ (a folder with TCsOffice.exe or TCsOffice inside).
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
ASSETS = ROOT / "office" / "assets"

# Qt modules the app never touches; leaving them out keeps the download small.
UNUSED = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtQuick3D",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtMultimedia", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtGraphs", "PySide6.QtBluetooth",
    "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtSensors", "PySide6.QtSerialPort",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech",
    "tkinter", "pytest", "numpy", "matplotlib", "scipy", "IPython",
]

a = Analysis(
    [str(ROOT / "run_tcsoffice.py")],
    pathex=[str(ROOT)],
    datas=[(str(ASSETS), "office/assets")],
    hiddenimports=["PySide6.QtNetwork", "PySide6.QtSvg", "PySide6.QtPrintSupport"],
    excludes=UNUSED,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="TCsOffice",
    console=False,
    icon=str(ASSETS / "icon.ico"),
    version=str(ROOT / "packaging" / "windows" / "version_info.txt") if sys.platform == "win32" else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="TCsOffice")
