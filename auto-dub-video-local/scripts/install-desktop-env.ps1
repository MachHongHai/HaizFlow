param(
  [switch]$Recreate
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$DependencyLock = Join-Path $Root "requirements-lock-py313-win64.txt"

$env:PYTHONUTF8 = "1"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"

if ($Recreate -and (Test-Path -LiteralPath $Venv)) {
  $ResolvedRoot = [System.IO.Path]::GetFullPath($Root).TrimEnd('\')
  $ResolvedVenv = [System.IO.Path]::GetFullPath($Venv).TrimEnd('\')
  if (!$ResolvedVenv.StartsWith($ResolvedRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to remove a virtual environment outside the project: $ResolvedVenv"
  }
  Remove-Item -LiteralPath $ResolvedVenv -Recurse -Force
}

if (!(Test-Path $Python)) {
  $Bootstrap = Get-Command python -ErrorAction SilentlyContinue
  if (!$Bootstrap) {
    throw "Python 3.13 x64 is required to create the reproducible desktop environment."
  }
  & $Bootstrap.Source -c "import platform, sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) and platform.machine().lower() in {'amd64', 'x86_64'} else 1)"
  if ($LASTEXITCODE -ne 0) {
    throw "Unsupported Python runtime. Install Python 3.13 x64."
  }
  & $Bootstrap.Source -m venv $Venv
}

& $Python -c "import platform, sys; raise SystemExit(0 if sys.platform == 'win32' and sys.version_info[:2] == (3, 13) and platform.machine().lower() in {'amd64', 'x86_64'} else 1)"
if ($LASTEXITCODE -ne 0) {
  throw "The reproducible desktop environment requires Windows x64 with Python 3.13."
}
if (!(Test-Path -LiteralPath $DependencyLock -PathType Leaf)) {
  throw "Dependency lock is missing: $DependencyLock"
}

& $Python -m pip install --require-hashes -r $DependencyLock
if ($LASTEXITCODE -ne 0) {
  throw "Hashed dependency installation failed with exit code $LASTEXITCODE."
}
& $Python -m pip install --no-deps --no-build-isolation -e $Root
if ($LASTEXITCODE -ne 0) {
  throw "Editable project installation failed with exit code $LASTEXITCODE."
}
& $Python -m pip check
& $Python (Join-Path $PSScriptRoot "verify-dependency-lock.py")
& $Python (Join-Path $PSScriptRoot "verify-runtime.py")
