$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    # Refresh local package metadata; Python normalizes the beta version to 0.1.0b1.
    conda run -n chronoapp python -m pip install --no-deps --no-build-isolation -e .
    if ($LASTEXITCODE -ne 0) { throw 'Application metadata update failed.' }
    conda run -n chronoapp python -m PyInstaller --noconfirm scripts/ChronoApp.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
    New-Item -ItemType Directory -Force -Path dist/ChronoApp/docs/examples | Out-Null
    Copy-Item -Path docs/examples/*.csv -Destination dist/ChronoApp/docs/examples
    Copy-Item -LiteralPath LICENSE -Destination dist/ChronoApp/LICENSE
    conda run -n chronoapp python -c "import shutil, tomllib; from pathlib import Path; v = tomllib.loads(Path('pyproject.toml').read_text())['project']['version']; shutil.make_archive(f'dist/Chronologer-{v}-win64', 'zip', 'dist', 'ChronoApp')"
    if ($LASTEXITCODE -ne 0) { throw 'ZIP creation failed.' }
} finally {
    Pop-Location
}
