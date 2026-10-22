# PyInstaller build: pyinstaller polyglass.spec  ->  dist/Polyglass/Polyglass.exe
# One folder (not one file) so the app starts fast and the installer can ship it as-is.
from PyInstaller.utils.hooks import collect_all, copy_metadata

datas, binaries, hiddenimports = [], [], []
# WinRT projections are compiled modules in a namespace package that PyInstaller can't follow by itself
for package in ("winrt",):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h
# Version shown in the app, and keyring's backend discovery, both read package metadata
datas += copy_metadata("polyglass") + copy_metadata("keyring")
datas += [("polyglass/resources", "polyglass/resources"), ("LICENSE", "."), ("THIRD_PARTY_NOTICES.md", ".")]

a = Analysis(
    ["polyglass/__main__.py"],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports + ["keyring.backends.Windows"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.QtQuick"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Polyglass",
    icon="polyglass/resources/polyglass.ico",
    console=False,
    version="installer/version_info.txt",
)
coll = COLLECT(exe, a.binaries, a.datas, name="Polyglass")
