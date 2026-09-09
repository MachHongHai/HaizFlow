param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$DependencyLocks = @(
  (Join-Path $Root "requirements-lock-py313-win64.txt"),
  (Join-Path $Root "requirements-lock-engine-cpu-py313-win64.txt"),
  (Join-Path $Root "requirements-lock-engine-cuda128-py313-win64.txt"),
  (Join-Path $Root "requirements-lock-engine-vision-py313-win64.txt")
)
$Uv = Get-Command uvx -ErrorAction SilentlyContinue

if (!$Uv) {
  throw "uvx is required to run the pinned dependency vulnerability audit."
}
if (!(Test-Path -LiteralPath $Python -PathType Leaf)) {
  throw "Project Python is missing: $Python"
}
foreach ($DependencyLock in $DependencyLocks) {
  if (!(Test-Path -LiteralPath $DependencyLock -PathType Leaf)) {
    throw "Dependency lock is missing: $DependencyLock"
  }
}
& $Python (Join-Path $PSScriptRoot "verify-dependency-lock.py") --no-installed-check
if ($LASTEXITCODE -ne 0) { throw "Core dependency lock verification failed." }
& $Python (Join-Path $PSScriptRoot "verify-engine-dependency-locks.py")
if ($LASTEXITCODE -ne 0) { throw "Engine dependency lock verification failed." }

# Reviewed exceptions are documented in docs/dependency-security.md. Any new
# advisory remains fatal. Keep the IDs explicit so a broad package ignore
# cannot conceal a newly disclosed vulnerability.
$AcceptedVulnerabilities = @(
  "PYSEC-2025-217",
  "PYSEC-2026-2288",
  "PYSEC-2026-2289",
  "PYSEC-2026-2290",
  "PYSEC-2026-2447",
  # NLTK 3.10.3 fixes the earlier parser/corpus advisories. The remaining
  # pathsec advisory affects model-artifact persistence APIs that HaizFlow does
  # not call; WhisperX alignment is routed through the internal sentence
  # splitter and cannot accept a caller-controlled NLTK model path.
  "PYSEC-2026-3740",
  # Transformers CVE-2026-9856 is in save_pretrained() filename generation.
  # HaizFlow only loads checksum-pinned local HY-MT2 safetensors with remote
  # code disabled and never calls tokenizer/processor save_pretrained().
  "CVE-2026-9856",
  # Accelerate CVE-2026-69112 concerns caller-controlled weight_map shard
  # paths. Both HY-MT2 and OmniVoice now validate every local checkpoint index
  # and regular shard before Accelerate can access it; all model files are also
  # delivered by immutable SHA-256-verified resource packs.
  "CVE-2026-69112",
  # Lightning 2.6.5 is the newest compatible release and upstream has not
  # published the merged CVE-2026-58659 fix yet. HaizFlow backports the exact
  # instantiator allowlist in core/dependency_security.py and tests it.
  "PYSEC-2026-3624"
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

foreach ($DependencyLock in $DependencyLocks) {
  $Arguments = @(
    "--from", "pip-audit==2.10.1",
    "pip-audit",
    "--requirement", $DependencyLock,
    "--no-deps",
    "--disable-pip",
    "--progress-spinner", "off"
  )
  foreach ($Vulnerability in $AcceptedVulnerabilities) {
    $Arguments += @("--ignore-vuln", $Vulnerability)
  }
  & $Uv.Source @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Dependency vulnerability audit found an unreviewed advisory in $([System.IO.Path]::GetFileName($DependencyLock))."
  }
}

# The CUDA wheels report local versions such as 2.8.0+cu128, which pip-audit
# cannot map to PyPI and otherwise skips. Audit their canonical upstream
# versions separately so a new PyTorch advisory still blocks the release.
$CanonicalTorchPackages = & $Python -c @"
import re
from pathlib import Path
root = Path(r'$($Root.Replace("'", "''"))')
found = {}
for profile in ('cpu', 'cuda128'):
    text = (root / f'requirements-lock-engine-{profile}-py313-win64.txt').read_text(encoding='utf-8')
    for name in ('torch', 'torchaudio', 'torchvision'):
        match = re.search(rf'(?m)^{name}==([^\s\\]+)', text)
        if match:
            found[name] = match.group(1).split('+', 1)[0]
for name, version in sorted(found.items()):
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
    "--disable-pip",
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

Write-Output "Dependency vulnerability audit passed for the Core and three exact engine locks; reviewed exceptions are documented and PyTorch wheels were audited by canonical version."
