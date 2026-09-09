param(
  [string]$ArtifactPath = "",
  [switch]$AllowUnsigned,
  [switch]$SkipInstallerSmokeTest,
  [string]$SignCertificatePath = "",
  [string]$TimestampServer = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$BuildMetadataPath = Join-Path $Root "build\release-metadata"
$SetupIconPath = Join-Path $Root "src\haizflow\desktop\assets\branding\haizflow.ico"
$BrandingMarkPath = Join-Path $Root "src\haizflow\desktop\assets\branding\haizflow-mark.png"
$InstallerTempParent = [System.IO.Path]::GetFullPath((Join-Path $Root "build\installer-temp"))
$InstallerTemp = [System.IO.Path]::GetFullPath((Join-Path $InstallerTempParent ([guid]::NewGuid().ToString("N"))))
$PreviousTemp = $env:TEMP
$PreviousTmp = $env:TMP
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

if (!(Test-Path -LiteralPath $SetupIconPath -PathType Leaf)) {
  throw "Installer icon is missing: $SetupIconPath"
}
if (!(Test-Path -LiteralPath $BrandingMarkPath -PathType Leaf)) {
  throw "Installer branding image is missing: $BrandingMarkPath"
}
if (!$SignCertificatePath -and !$AllowUnsigned) {
  throw "A public release installer requires Authenticode signing. Supply -SignCertificatePath, or use -AllowUnsigned only for an internal engineering build."
}
if (!$SignCertificatePath) {
  Write-Warning "Building an unsigned engineering installer. The filename is marked UNSIGNED and is not suitable for public distribution."
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
$OutputBaseFilename = if ($SignCertificatePath) { "HaizFlow-$Version-Setup" } else { "HaizFlow-$Version-UNSIGNED-Setup" }
$InstallerPath = Join-Path $InstallerOutputDirectory "$OutputBaseFilename.exe"
try {
  if (![System.IO.Path]::GetDirectoryName($InstallerTemp).Equals($InstallerTempParent, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to use an unsafe installer temporary directory: $InstallerTemp"
  }
  New-Item -ItemType Directory -Path $InstallerTemp -Force | Out-Null
  $env:TEMP = $InstallerTemp
  $env:TMP = $InstallerTemp
  if (Test-Path -LiteralPath $InstallerPath -PathType Leaf) {
    Remove-Item -LiteralPath $InstallerPath -Force
  }
  & $IsccExecutable `
    "/DSourceDir=$ArtifactPath" `
    "/DAppVersion=$Version" `
    "/DRequiredFreeBytes=$($Requirements.required_free_bytes)" `
    "/DRequiredFreshBytes=$($FreshRequirements.required_free_bytes)" `
    "/DRecommendedFreeBytes=$($Requirements.recommended_free_bytes)" `
    "/DRecommendedFreshBytes=$($FreshRequirements.recommended_free_bytes)" `
    "/DArtifactBytes=$($FreshRequirements.artifact_bytes)" `
    "/DSetupIconPath=$SetupIconPath" `
    "/DBrandingMarkPath=$BrandingMarkPath" `
    "/DOutputBaseFilename=$OutputBaseFilename" `
    $InstallerScript
  if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed with exit code $LASTEXITCODE." }
}
finally {
  $env:TEMP = $PreviousTemp
  $env:TMP = $PreviousTmp
  if (Test-Path -LiteralPath $InstallerTemp) {
    $ResolvedInstallerTemp = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $InstallerTemp).Path)
    if (![System.IO.Path]::GetDirectoryName($ResolvedInstallerTemp).Equals($InstallerTempParent, [System.StringComparison]::OrdinalIgnoreCase)) {
      throw "Refusing to delete an unsafe installer temporary directory: $ResolvedInstallerTemp"
    }
    Remove-Item -LiteralPath $ResolvedInstallerTemp -Recurse -Force
  }
}

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

if (!$SkipInstallerSmokeTest) {
  $SmokeArguments = @{
    InstallerPath = $InstallerPath
  }
  if ($SignCertificatePath) {
    $SmokeArguments.RequireSignature = $true
  }
  & (Join-Path $PSScriptRoot "test-installer.ps1") @SmokeArguments
  if ($LASTEXITCODE -ne 0) {
    throw "Installer smoke test failed with exit code $LASTEXITCODE."
  }
}

Write-Output "Installer ready: $InstallerPath (SHA-256: $InstallerChecksumPath)"
