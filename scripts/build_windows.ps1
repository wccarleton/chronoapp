$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    conda run -n chronoapp python -m PyInstaller --noconfirm scripts/ChronoApp.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
    conda run -n chronoapp python -c "import shutil; shutil.make_archive('dist/ChronoApp-win64-beta', 'zip', 'dist', 'ChronoApp')"
    if ($LASTEXITCODE -ne 0) { throw 'ZIP creation failed.' }
} finally {
    Pop-Location
}
