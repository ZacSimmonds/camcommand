# Build the camcommand Windows installer end-to-end.
#
#   1. Freezes camcommand into a single-file camcommand.exe with PyInstaller
#      (bundles Python + pyserial - the target machine needs NEITHER).
#   2. Compiles installer\Output\camcommand-setup.exe with Inno Setup.
#
# Usage (from the repo root or anywhere):
#   powershell -ExecutionPolicy Bypass -File installer\build.ps1
#
# Requirements on THIS build machine only (not the end user's):
#   - Python with camcommand installed (`pip install -e .` from repo root)
#   - pyinstaller (`pip install pyinstaller`)
#   - Inno Setup 6 (`winget install JRSoftware.InnoSetup`)

$ErrorActionPreference = 'Stop'

$here     = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $here
$workDir  = Join-Path $here 'build-tmp'

Write-Host '==> Freezing camcommand.exe with PyInstaller...' -ForegroundColor Cyan
Push-Location $repoRoot
try {
    python -m PyInstaller `
        --onefile --name camcommand --console `
        --collect-submodules camcommand `
        --collect-submodules serial `
        --copy-metadata camcommand `
        --distpath (Join-Path $workDir 'dist') `
        --workpath (Join-Path $workDir 'build') `
        --specpath $workDir `
        --noconfirm `
        (Join-Path $here 'entry.py')
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }
}
finally {
    Pop-Location
}

Copy-Item (Join-Path $workDir 'dist\camcommand.exe') (Join-Path $here 'camcommand.exe') -Force
Write-Host '==> camcommand.exe built.' -ForegroundColor Green

# Locate the Inno Setup compiler.
$iscc = @(
    Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'
    'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
    'C:\Program Files\Inno Setup 6\ISCC.exe'
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
    throw 'ISCC.exe not found. Install Inno Setup 6: winget install JRSoftware.InnoSetup'
}

Write-Host '==> Compiling installer with Inno Setup...' -ForegroundColor Cyan
& $iscc (Join-Path $here 'camcommand.iss')
if ($LASTEXITCODE -ne 0) { throw "ISCC failed ($LASTEXITCODE)" }

$setup = Join-Path $here 'Output\camcommand-setup.exe'
Write-Host "==> Done. Installer: $setup" -ForegroundColor Green
