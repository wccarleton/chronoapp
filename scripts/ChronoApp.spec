from pathlib import Path
import tomllib
from PyInstaller.utils.hooks import collect_data_files, copy_metadata
from PyInstaller.utils.win32.versioninfo import VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct

root = Path(SPECPATH).parent
release = tomllib.loads((root / 'pyproject.toml').read_text())['project']['version']
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=(0, 1, 0, 1), prodvers=(0, 1, 0, 1),
                      mask=0x3f, flags=0x2, OS=0x40004, fileType=0x1,
                      subtype=0, date=(0, 0)),
    kids=[StringFileInfo([StringTable('040904B0', [
        StringStruct('CompanyName', 'W. Christopher Carleton'),
        StringStruct('FileDescription', 'Chronologer'),
        StringStruct('FileVersion', release),
        StringStruct('ProductName', 'Chronologer'),
        StringStruct('ProductVersion', release),
        StringStruct('OriginalFilename', 'ChronoApp.exe'),
        StringStruct('LegalCopyright', 'Copyright (c) 2026 W. Christopher Carleton'),
    ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])],
)
datas = [(str(root / 'frontend'), 'frontend')]
for package in ('chronologer', 'pymc', 'pytensor', 'arviz', 'arviz_base', 'arviz_stats', 'arviz_plots'):
    datas += collect_data_files(package)
for package in ('chronologer-app', 'chronologer', 'pymc', 'pytensor', 'arviz', 'arviz-base', 'arviz-stats', 'arviz-plots'):
    datas += copy_metadata(package)

a = Analysis(
    [str(root / 'scripts' / 'windows_launcher.py')],
    pathex=[str(root / 'src'), str(root.parent / 'chronologer' / 'src')],
    datas=datas,
    hiddenimports=['chronologer_app.native_dialog', 'tkinter.filedialog', 'numba'],
    excludes=['IPython', 'notebook', 'jupyterlab', 'pytest', 'sphinx',
              'torch', 'tensorflow', 'jax', 'jaxlib',
              'PyQt5', 'PyQt6', 'PySide2', 'PySide6'],
    hookspath=[],
    hooksconfig={'matplotlib': {'backends': ['Agg', 'SVG']}},
    module_collection_mode={'pymc': 'pyz+py', 'pytensor': 'pyz+py'},
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ChronoApp',
          console=True, upx=False, version=version_info)
coll = COLLECT(exe, a.binaries, a.datas, name='ChronoApp', upx=False)
