param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$LockFile = Join-Path $Root "requirements-lock-py313-win64.txt"
$UvVersion = "0.11.19"
$EnvFile = Join-Path $Root ".env"

function Get-DotEnvValue([string]$Name) {
  if (!(Test-Path -LiteralPath $EnvFile)) { return "" }
  $match = Select-String -LiteralPath $EnvFile -Pattern ("^" + [regex]::Escape($Name) + "=(.*)$") | Select-Object -First 1
  if (!$match) { return "" }
  return $match.Matches[0].Groups[1].Value.Trim().Trim('"')
}

# uv runs before Python imports haizflow.config, so it cannot inherit the
# application's runtime containment automatically. Keep its resolver cache in
# the same user-selected data root instead of creating .uv-cache beside source.
$RuntimeData = Get-DotEnvValue "RUNTIME_DATA_DIR"
if (!$RuntimeData) { $RuntimeData = Join-Path $Root "data" }
$UvCache = Get-DotEnvValue "UV_CACHE_DIR"
if (!$UvCache) { $UvCache = Join-Path $RuntimeData "cache\uv" }
New-Item -ItemType Directory -Force -Path $UvCache | Out-Null
$env:UV_CACHE_DIR = $UvCache

if (!(Test-Path -LiteralPath $Python -PathType Leaf)) {
  throw "Project environment is missing. Run scripts\install-desktop-env.ps1 first."
}

& $Python -c "import platform, sys; raise SystemExit(0 if sys.platform == 'win32' and sys.version_info[:2] == (3, 13) and platform.machine().lower() in {'amd64', 'x86_64'} else 1)"
if ($LASTEXITCODE -ne 0) {
  throw "The release lock must be generated on Windows x64 with Python 3.13."
}

$Uv = Get-Command uv -ErrorAction SilentlyContinue
if (!$Uv -or (& $Uv.Source --version) -ne "uv $UvVersion (7b2cff1c3 2026-06-03 x86_64-pc-windows-msvc)") {
  throw "uv $UvVersion is required to regenerate the release dependency lock."
}

& $Uv.Source pip compile `
  (Join-Path $Root "pyproject.toml") `
  (Join-Path $Root "requirements-build.in") `
  --output-file $LockFile `
  --generate-hashes `
  --python-platform x86_64-pc-windows-msvc `
  --python-version 3.13 `
  --python $Python `
  --emit-index-url `
  --custom-compile-command ".\scripts\lock-dependencies.ps1"
if ($LASTEXITCODE -ne 0) {
  throw "Dependency lock generation failed with exit code $LASTEXITCODE."
}

# uv constrains these packages to explicit indexes while resolving, but pip still
# needs the index locations when installing the generated lock on a clean machine.
$LockContent = [System.IO.File]::ReadAllText($LockFile)
$PrimaryIndex = "--index-url https://pypi.org/simple"
$InstallIndexes = @(
  "--extra-index-url https://download.pytorch.org/whl/cu128",
  "--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu"
)
if (!$LockContent.Contains($PrimaryIndex)) {
  throw "Generated dependency lock does not declare the primary package index."
}
$SourceBlock = (@($PrimaryIndex) + $InstallIndexes) -join [Environment]::NewLine
$LockContent = $LockContent.Replace($PrimaryIndex, $SourceBlock)
[System.IO.File]::WriteAllText($LockFile, $LockContent, [System.Text.UTF8Encoding]::new($false))

& $Python (Join-Path $PSScriptRoot "verify-dependency-lock.py") --write-manifest
if ($LASTEXITCODE -ne 0) {
  throw "Generated dependency lock failed verification."
}

Write-Output "Dependency lock ready: $LockFile"
