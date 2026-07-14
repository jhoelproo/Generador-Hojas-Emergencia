# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

base = Path(SPECPATH).resolve()

a = Analysis(
    [str(base / "actualizador.py")],
    pathex=[str(base)],
    hiddenimports=["emergency_core", "emergency_core.updater"],
    excludes=["openpyxl", "PIL", "PyPDF2", "reportlab", "ttkbootstrap"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ACTUALIZADOR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(base / "Gemini_Generated_Image_o7mhooo7mhooo7mh.ico"),
    uac_admin=False,
)
