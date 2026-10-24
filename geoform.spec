# -*- mode: python ; coding: utf-8 -*-
# Build: .venv\Scripts\python -m PyInstaller geoform.spec --noconfirm
# El Python base es conda (spyder-6): PyInstaller no copia los DLL de Library/bin, se agregan a mano.
import os

from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = [('geoform/data', 'geoform/data'), ('geoform/assets', 'geoform/assets')]
CONDA_BIN = 'C:/ProgramData/spyder-6/Library/bin'
DLLS = ['ffi-8.dll', 'sqlite3.dll', 'libssl-3-x64.dll', 'libcrypto-3-x64.dll', 'libexpat.dll',
        'libbz2.dll', 'liblzma.dll', 'zlib.dll', 'zlib1.dll']
binaries = [(f'{CONDA_BIN}/{d}', '.') for d in DLLS if os.path.exists(f'{CONDA_BIN}/{d}')]
hiddenimports = []
datas += collect_data_files('pyvista')
tmp_ret = collect_all('vtkmodules')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['geoform_launcher.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='geoform',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='geoform',
)
