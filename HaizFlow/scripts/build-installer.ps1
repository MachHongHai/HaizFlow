param(
  [string]$ArtifactPath = "",
  [string]$SignCertificatePath = "",
  [string]$TimestampServer = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
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
if ($LASTEXITCODE -ne 0) { throw "Artifact provenance/model eligibility verification failed." }

$RequirementJson = & $Python (Join-Path $PSScriptRoot "release-preflight.py") --artifact $ArtifactPath
if ($LASTEXITCODE -ne 0) { throw "Installer disk preflight calculation failed." }
$Requirements = $RequirementJson | ConvertFrom-Json
$Version = (& $Python -c "import tomllib, pathlib; print(tomllib.loads((pathlib.Path(r'$Root') / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version'])").Trim()
$Iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
if (!$Iscc) { throw "Inno Setup 6 (iscc.exe) is required to build the installer." }

$InstallerScript = Join-Path $Root "installer\HaizFlow.iss"
& $Iscc.Source "/DSourceDir=$ArtifactPath" "/DAppVersion=$Version" "/DRequiredFreeBytes=$($Requirements.required_free_bytes)" $InstallerScript
if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed with exit code $LASTEXITCODE." }

$InstallerPath = Join-Path $Root "dist\installer\HaizFlow-$Version-Setup.exe"
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
