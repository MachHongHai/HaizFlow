param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$SitePackages = Join-Path $Root ".venv\Lib\site-packages"
$Uv = Get-Command uvx -ErrorAction SilentlyContinue

if (!$Uv) {
  throw "uvx is required to run the pinned dependency vulnerability audit."
}
if (!(Test-Path -LiteralPath $SitePackages -PathType Container)) {
  throw "Project environment is missing. Run scripts\install-desktop-env.ps1 first."
}
if (!(Test-Path -LiteralPath $Python -PathType Leaf)) {
  throw "Project Python is missing: $Python"
}

# Reviewed exceptions are documented in docs/dependency-security.md. Any new
# advisory remains fatal. Keep the IDs explicit so a broad package ignore
# cannot conceal a newly disclosed vulnerability.
$AcceptedVulnerabilities = @(
  "PYSEC-2025-217",
  "PYSEC-2026-2288",
  "PYSEC-2026-2289",
  "PYSEC-2026-2290",
  "PYSEC-2026-2447"
)
$AcceptedCanonicalTorchVulnerabilities = @(
  "PYSEC-2025-206",
  "PYSEC-2025-204",
  "PYSEC-2026-139",
  "PYSEC-2025-203",
  "PYSEC-2025-194",
  "PYSEC-2026-2286",
  "CVE-2025-2999",
  "CVE-2025-3001"
)

$Arguments = @(
  "--from", "pip-audit==2.10.1",
  "pip-audit",
  "--path", $SitePackages,
  "--progress-spinner", "off"
)
foreach ($Vulnerability in $AcceptedVulnerabilities) {
  $Arguments += @("--ignore-vuln", $Vulnerability)
}

& $Uv.Source @Arguments
if ($LASTEXITCODE -ne 0) {
  throw "Dependency vulnerability audit found an unreviewed advisory."
}

# The CUDA wheels report local versions such as 2.8.0+cu128, which pip-audit
# cannot map to PyPI and otherwise skips. Audit their canonical upstream
# versions separately so a new PyTorch advisory still blocks the release.
$CanonicalTorchPackages = & $Python -c @"
import importlib.metadata
for name in ('torch', 'torchaudio', 'torchvision'):
    version = importlib.metadata.version(name).split('+', 1)[0]
    print(f'{name}=={version}')
"@
if ($LASTEXITCODE -ne 0 -or @($CanonicalTorchPackages).Count -ne 3) {
  throw "Could not determine canonical PyTorch package versions."
}
$AuditTempDirectory = [System.IO.Path]::GetFullPath((Join-Path $Root "build\dependency-audit-$PID"))
$ExpectedBuildDirectory = [System.IO.Path]::GetFullPath((Join-Path $Root "build"))
$CanonicalRequirements = Join-Path $AuditTempDirectory "pytorch-requirements.txt"
[System.IO.Directory]::CreateDirectory($AuditTempDirectory) | Out-Null
[System.IO.File]::WriteAllLines($CanonicalRequirements, [string[]]$CanonicalTorchPackages)
try {
  $CanonicalArguments = @(
    "--from", "pip-audit==2.10.1",
    "pip-audit",
    "--requirement", $CanonicalRequirements,
    "--no-deps",
    "--progress-spinner", "off"
  )
  foreach ($Vulnerability in $AcceptedCanonicalTorchVulnerabilities) {
    $CanonicalArguments += @("--ignore-vuln", $Vulnerability)
  }
  & $Uv.Source @CanonicalArguments
  if ($LASTEXITCODE -ne 0) {
    throw "Canonical PyTorch vulnerability audit found an unreviewed advisory."
  }
}
finally {
  $ResolvedAuditDirectory = [System.IO.Path]::GetFullPath($AuditTempDirectory)
  if ([System.IO.Path]::GetDirectoryName($ResolvedAuditDirectory) -ne $ExpectedBuildDirectory) {
    throw "Refusing to remove dependency audit data outside build: $ResolvedAuditDirectory"
  }
  if (Test-Path -LiteralPath $ResolvedAuditDirectory -PathType Container) {
    [System.IO.Directory]::Delete($ResolvedAuditDirectory, $true)
  }
}

Write-Output "Dependency vulnerability audit passed; reviewed exceptions are documented and CUDA wheels were audited by canonical version."
