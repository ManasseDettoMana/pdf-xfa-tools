<#
.SYNOPSIS
    Builds dist\XfaStudio.exe, a single portable executable.

.DESCRIPTION
    Wraps PyInstaller so the working directory, output paths and cleanup are
    always the same. The result needs no installer, no admin rights and no
    Python on the target machine.

.PARAMETER SkipTests
    Skip the test run that normally gates the build.

.EXAMPLE
    .\build\build.ps1
    .\build\build.ps1 -SkipTests
#>
[CmdletBinding()]
param(
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SpecFile    = Join-Path $PSScriptRoot 'xfatools.spec'
$DistDir     = Join-Path $ProjectRoot 'dist'
$WorkDir     = Join-Path $ProjectRoot 'build\_work'

Push-Location $ProjectRoot
try {
    Write-Host 'XFA Studio - build' -ForegroundColor Cyan
    Write-Host ''

    # --- prerequisites ---------------------------------------------------
    try { $null = & python --version } catch { throw 'Python non trovato nel PATH.' }

    & python -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller non installato. Esegui: python -m pip install -r requirements-dev.txt"
    }

    & python -c "import PySide6" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "PySide6 non installato. Esegui: python -m pip install -r requirements.txt"
    }

    # --- tests -----------------------------------------------------------
    if (-not $SkipTests) {
        Write-Host 'Esecuzione dei test...' -ForegroundColor Yellow
        $env:QT_QPA_PLATFORM = 'offscreen'
        & python -m pytest -q
        if ($LASTEXITCODE -ne 0) {
            throw 'I test non passano: build interrotta.'
        }
        Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue
        Write-Host ''
    }

    # --- clean -----------------------------------------------------------
    foreach ($path in @($DistDir, $WorkDir)) {
        if (Test-Path $path) {
            Write-Host "Pulizia di $path"
            Remove-Item -Recurse -Force $path
        }
    }

    # --- build -----------------------------------------------------------
    Write-Host 'Compilazione con PyInstaller (alcuni minuti)...' -ForegroundColor Yellow
    & python -m PyInstaller $SpecFile --distpath $DistDir --workpath $WorkDir --noconfirm --clean
    if ($LASTEXITCODE -ne 0) {
        throw 'PyInstaller ha restituito un errore.'
    }

    # --- report ----------------------------------------------------------
    $Executable = Join-Path $DistDir 'XfaStudio.exe'
    if (-not (Test-Path $Executable)) {
        throw "Build completata ma $Executable non esiste."
    }

    $SizeMb = [math]::Round((Get-Item $Executable).Length / 1MB, 1)
    Write-Host ''
    Write-Host 'Build completata.' -ForegroundColor Green
    Write-Host "  $Executable"
    Write-Host "  $SizeMb MB"
    Write-Host ''
    Write-Host 'Il file e'' autonomo: copialo dove vuoi, non serve Python.'
}
finally {
    Pop-Location
}
