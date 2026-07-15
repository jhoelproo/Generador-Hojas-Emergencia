# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys


base = Path(SPECPATH).resolve()
python_home = Path(sys.executable).resolve().parent
tcl_root = python_home / "tcl"
dll_root = python_home / "DLLs"

# Deliberately enumerate every distributable asset. Operational files such as
# databases, spreadsheets, JSON configuration, logs and reports must never be
# added here.
template_names = (
    "EMERGENCIA GENERAL.pdf",
    "EMERGENCIA GINECOLOGIA.pdf",
    "EMERGENCIA PEDIATRICA.pdf",
)

required_paths = [
    base / "facturacion_tabs (1).py",
    base / "SumatraPDF.exe",
    base / "logo.jpg",
    base / "istipo_hospitales.png",
    base / "Gemini_Generated_Image_o7mhooo7mhooo7mh.ico",
    base / "packaging" / "version_info.txt",
    base / "packaging" / "app.manifest",
    base / "pyinstaller_hooks" / "runtime_tk.py",
    base / "pyinstaller_hooks" / "pre_find_module_path" / "hook-tkinter.py",
    dll_root / "_tkinter.pyd",
    dll_root / "tcl86t.dll",
    dll_root / "tk86t.dll",
    tcl_root / "tcl8.6",
    tcl_root / "tk8.6",
    tcl_root / "tcl8",
]
required_paths.extend(base / "HOJAS" / name for name in template_names)

missing = [str(path) for path in required_paths if not path.exists()]
if missing:
    raise FileNotFoundError("Required packaging assets are missing:\n" + "\n".join(missing))

datas = [
    (str(base / "logo.jpg"), "."),
    (str(base / "istipo_hospitales.png"), "."),
    (str(tcl_root / "tcl8.6"), "_tcl_data"),
    (str(tcl_root / "tk8.6"), "_tk_data"),
    (str(tcl_root / "tcl8"), "tcl8"),
]
datas.extend((str(base / "HOJAS" / name), "HOJAS") for name in template_names)

a = Analysis(
    [str(base / "facturacion_tabs (1).py")],
    pathex=[str(base)],
    binaries=[
        (str(base / "SumatraPDF.exe"), "."),
        (str(dll_root / "_tkinter.pyd"), "."),
        (str(dll_root / "tcl86t.dll"), "."),
        (str(dll_root / "tk86t.dll"), "."),
    ],
    datas=datas,
    hiddenimports=[
        "tkinter",
        "_tkinter",
        "tkinter.ttk",
        "tkinter.messagebox",
        "tkinter.filedialog",
        "tkinter.simpledialog",
        "emergency_core",
        "emergency_core.backup",
        "emergency_core.db_migrations",
        "emergency_core.io_utils",
        "emergency_core.paths",
        "emergency_core.security",
    ],
    hookspath=[str(base / "pyinstaller_hooks")],
    hooksconfig={},
    runtime_hooks=[str(base / "pyinstaller_hooks" / "runtime_tk.py")],
    excludes=[
        "IPython",
        "matplotlib",
        "numpy",
        "pandas",
        "pip",
        "playwright",
        "pytest",
        "PySide6",
        "setuptools",
        "tkinter.test",
        "wheel",
    ],
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
    name="GENERADOR DE HOJAS 4.1",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(base / "Gemini_Generated_Image_o7mhooo7mhooo7mh.ico"),
    version=str(base / "packaging" / "version_info.txt"),
    manifest=str(base / "packaging" / "app.manifest"),
    uac_admin=False,
    uac_uiaccess=False,
)
