param([string]$OutputDirectory = "")
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (!$OutputDirectory) { $OutputDirectory = Join-Path $Root "dist\bootstrap" }
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $OutputDirectory) { throw "Choose a new bootstrap output directory." }
$Work = Join-Path $Root "build\bootstrap"
$PreviousTemp = $env:TEMP
$PreviousTmp = $env:TMP
$PreviousConfig = $env:PYINSTALLER_CONFIG_DIR
try {
  $Temp = Join-Path $Work "tmp"
  New-Item -ItemType Directory -Path $Temp -Force | Out-Null
  $env:TEMP = $Temp
  $env:TMP = $Temp
  $env:PYINSTALLER_CONFIG_DIR = Join-Path $Work "config"
  foreach ($Entry in @(@("HaizFlow", "haizflow-launcher.py"), @("HaizFlowUpdater", "haizflow-updater.py"))) {
    & $Python -m PyInstaller --noconfirm --clean --windowed --onedir `
      --name $Entry[0] --distpath $OutputDirectory --workpath (Join-Path $Work $Entry[0]) `
      --specpath $Work --paths (Join-Path $Root "src") `
      --exclude-module PySide6 --exclude-module torch --exclude-module numpy `
      --icon (Join-Path $Root "src\haizflow\desktop\assets\branding\haizflow.ico") `
      (Join-Path $PSScriptRoot $Entry[1])
    if ($LASTEXITCODE -ne 0) { throw "Bootstrap build failed: $($Entry[0])" }
  }
}
finally {
  $env:TEMP = $PreviousTemp
  $env:TMP = $PreviousTmp
  $env:PYINSTALLER_CONFIG_DIR = $PreviousConfig
}
