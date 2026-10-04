param(
  [string]$OutputDirectory = "",
  [string]$PythonExecutable = "",
  [switch]$AllowUnsigned,
  [switch]$UnsignedRelease,
  [string]$SignCertificateThumbprint = "",
  [string]$SignCertificatePath = "",
  [string]$TimestampServer = "http://timestamp.digicert.com"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = if ($PythonExecutable) { [System.IO.Path]::GetFullPath($PythonExecutable) } else { Join-Path $Root ".venv\Scripts\python.exe" }
if ($UnsignedRelease -and ($AllowUnsigned -or $SignCertificateThumbprint -or $SignCertificatePath)) {
  throw "UnsignedRelease cannot be combined with signing or engineering flags."
}
if (!$SignCertificateThumbprint -and !$SignCertificatePath -and !$AllowUnsigned -and !$UnsignedRelease) {
  throw "Choose a signing identity, UnsignedRelease for public unsigned bootstrap, or AllowUnsigned for internal tests."
}
$BootstrapSourceCommit = & git -C $Root rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or !$BootstrapSourceCommit) { throw "Could not determine bootstrap source commit." }
if (!$AllowUnsigned) {
  $GitStatus = & git -C $Root status --porcelain
  if ($LASTEXITCODE -ne 0 -or $GitStatus) { throw "Public unsigned bootstrap builds require a clean Git checkout." }
  & $Python (Join-Path $PSScriptRoot "verify-legal-state.py") --public-release
  if ($LASTEXITCODE -ne 0) { throw "Public bootstrap licensing review failed." }
  if ($UnsignedRelease) { Write-Warning "Building an unsigned launcher and updater; Windows policy may block them." }
}
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
  $VersionResource = Join-Path $Work "bootstrap-version.txt"
  & $Python (Join-Path $PSScriptRoot "generate-version-resource.py") --output $VersionResource
  if ($LASTEXITCODE -ne 0) { throw "Bootstrap version resource generation failed." }
  foreach ($Entry in @(@("HaizFlow", "haizflow-launcher.py"), @("HaizFlowUpdater", "haizflow-updater.py"))) {
    & $Python -m PyInstaller --noconfirm --clean --windowed --onedir `
      --name $Entry[0] --distpath $OutputDirectory --workpath (Join-Path $Work $Entry[0]) `
      --specpath $Work --paths (Join-Path $Root "src") `
      --version-file $VersionResource `
      --exclude-module PySide6 --exclude-module torch --exclude-module numpy `
      --icon (Join-Path $Root "src\haizflow\desktop\assets\branding\haizflow.ico") `
      (Join-Path $PSScriptRoot $Entry[1])
    if ($LASTEXITCODE -ne 0) { throw "Bootstrap build failed: $($Entry[0])" }
    if ($SignCertificateThumbprint -or $SignCertificatePath) {
      & (Join-Path $PSScriptRoot "sign-windows.ps1") `
        -FilePath (Join-Path $OutputDirectory "$($Entry[0])\$($Entry[0]).exe") `
        -CertificateThumbprint $SignCertificateThumbprint -CertificatePath $SignCertificatePath -TimestampServer $TimestampServer
    }
    $FinalizeArguments = @((Join-Path $PSScriptRoot "finalize-bootstrap.py"),
      "--artifact", (Join-Path $OutputDirectory $Entry[0]), "--entrypoint", "$($Entry[0]).exe",
      "--source-commit", $BootstrapSourceCommit)
    if ($AllowUnsigned) { $FinalizeArguments += "--engineering" }
    & $Python @FinalizeArguments
    if ($LASTEXITCODE -ne 0) { throw "Bootstrap provenance/checksum finalization failed: $($Entry[0])" }
  }
}
finally {
  $env:TEMP = $PreviousTemp
  $env:TMP = $PreviousTmp
  $env:PYINSTALLER_CONFIG_DIR = $PreviousConfig
}
