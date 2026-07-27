param(
  [string]$ArtifactPath = "",
  [string]$SignCertificatePath = "",
  [string]$TimestampServer = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$BuildMetadataPath = Join-Path $Root "build\release-metadata"
$SetupIconPath = Join-Path $BuildMetadataPath "HaizFlow-installer.ico"
if (!$ArtifactPath) {
  $ArtifactPath = Join-Path $Root "dist\HaizFlow"
}
$ArtifactPath = [System.IO.Path]::GetFullPath($ArtifactPath)
if (!(Test-Path -LiteralPath (Join-Path $ArtifactPath "HaizFlow.exe") -PathType Leaf)) {
  throw "Verified frozen artifact is missing: $ArtifactPath"
}

& $Python (Join-Path $PSScriptRoot "finalize-release.py") --artifact $ArtifactPath --verify
if ($LASTEXITCODE -ne 0) { throw "Artifact checksum verification failed." }
& $Python (Join-Path $PSScriptRoot "finalize-release.py") --artifact $ArtifactPath --verify-installer-eligibility
if ($LASTEXITCODE -ne 0) { throw "Artifact provenance and payload eligibility verification failed." }

$RequirementJson = & $Python (Join-Path $PSScriptRoot "release-preflight.py") --artifact $ArtifactPath
if ($LASTEXITCODE -ne 0) { throw "Installer disk preflight calculation failed." }
$Requirements = $RequirementJson | ConvertFrom-Json
$FreshRequirementJson = & $Python (Join-Path $PSScriptRoot "release-preflight.py") --artifact $ArtifactPath --fresh-install
if ($LASTEXITCODE -ne 0) { throw "Fresh-install disk preflight calculation failed." }
$FreshRequirements = $FreshRequirementJson | ConvertFrom-Json

& $Python (Join-Path $PSScriptRoot "generate-app-icon.py") --output $SetupIconPath
if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $SetupIconPath -PathType Leaf)) {
  throw "Installer icon generation failed."
}

$Version = (& $Python -c "import tomllib, pathlib; print(tomllib.loads((pathlib.Path(r'$Root') / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version'])").Trim()
$Iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
$IsccExecutable = if ($Iscc) { $Iscc.Source } else { "" }
if (!$Iscc) {
  $IsccCandidates = @(
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
  )
  $IsccPath = $IsccCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
  if ($IsccPath) {
    $IsccExecutable = [System.IO.Path]::GetFullPath($IsccPath)
  }
}
if (!$IsccExecutable) {
  throw "Inno Setup 6 (iscc.exe) is required. Install it, then rerun scripts\build-installer.ps1."
}

$InstallerScript = Join-Path $Root "installer\HaizFlow.iss"
$InstallerOutputDirectory = Join-Path $Root "dist\installer"
$InstallerPath = Join-Path $InstallerOutputDirectory "HaizFlow-$Version-Setup.exe"
if (Test-Path -LiteralPath $InstallerPath -PathType Leaf) {
  Remove-Item -LiteralPath $InstallerPath -Force
}
& $IsccExecutable `
  "/DSourceDir=$ArtifactPath" `
  "/DAppVersion=$Version" `
  "/DRequiredFreeBytes=$($Requirements.required_free_bytes)" `
  "/DRequiredFreshBytes=$($FreshRequirements.required_free_bytes)" `
  "/DSetupIconPath=$SetupIconPath" `
  $InstallerScript
if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed with exit code $LASTEXITCODE." }

if (!(Test-Path -LiteralPath $InstallerPath -PathType Leaf)) { throw "Expected installer was not created: $InstallerPath" }
if ($SignCertificatePath) {
  if (!$env:HAIZFLOW_SIGN_CERT_PASSWORD) { throw "Set HAIZFLOW_SIGN_CERT_PASSWORD before signing the installer." }
  $SignTool = Get-Command signtool.exe -ErrorAction SilentlyContinue
  if (!$SignTool) { throw "signtool.exe is required for Authenticode signing." }
  & $SignTool.Source sign /fd SHA256 /f $SignCertificatePath /p $env:HAIZFLOW_SIGN_CERT_PASSWORD /tr $TimestampServer /td SHA256 $InstallerPath
  if ($LASTEXITCODE -ne 0) { throw "Installer signing failed." }
  & $SignTool.Source verify /pa /v $InstallerPath
  if ($LASTEXITCODE -ne 0) { throw "Installer signature verification failed." }
}

$InstallerChecksumPath = "$InstallerPath.sha256"
$InstallerHash = (Get-FileHash -LiteralPath $InstallerPath -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath $InstallerChecksumPath -Value "$InstallerHash *$([System.IO.Path]::GetFileName($InstallerPath))" -Encoding ascii

Write-Output "Installer ready: $InstallerPath (SHA-256: $InstallerChecksumPath)"
