from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

root = Path(SPECPATH).parent
datas = [(str(root / 'frontend'), 'frontend')]
for package in ('chronologer', 'pymc', 'pytensor', 'arviz', 'arviz_base', 'arviz_stats', 'arviz_plots'):
    datas += collect_data_files(package)
for package in ('pymc', 'pytensor', 'arviz', 'arviz-base', 'arviz-stats', 'arviz-plots'):
    datas += copy_metadata(package)

a = Analysis(
    [str(root / 'scripts' / 'windows_launcher.py')],
    pathex=[str(root / 'src'), str(root.parent / 'chronologer' / 'src')],
    datas=datas,
    hiddenimports=['chronologer_app.native_dialog', 'tkinter.filedialog'],
    excludes=['IPython', 'notebook', 'jupyterlab', 'pytest', 'sphinx',
              'torch', 'tensorflow', 'jax', 'jaxlib', 'numba',
              'PyQt5', 'PyQt6', 'PySide2', 'PySide6'],
    hookspath=[],
    hooksconfig={'matplotlib': {'backends': ['Agg']}},
    module_collection_mode={'pymc': 'pyz+py', 'pytensor': 'pyz+py'},
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ChronoApp',
          console=True, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name='ChronoApp', upx=False)
