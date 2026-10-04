param(
  [ValidateSet("cpu", "cuda128", "vision", "all")]
  [string]$Profile = "all"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Uv = (Get-Command uv -ErrorAction Stop).Source
$Python = if (Test-Path -LiteralPath (Join-Path $Root ".venv\Scripts\python.exe")) {
  Join-Path $Root ".venv\Scripts\python.exe"
} else {
  (Get-Command python -ErrorAction Stop).Source
}
$Profiles = if ($Profile -eq "all") { @("cpu", "cuda128", "vision") } else { @($Profile) }
$CommonInput = Join-Path $Root "requirements-engine-common.in"
$ToolCache = Join-Path $Root "build\dependency-cache\uv"
$ToolTemp = Join-Path $Root "build\dependency-cache\tmp"

if (!(Test-Path -LiteralPath $CommonInput -PathType Leaf)) {
  throw "Shared engine dependency input is missing: $CommonInput"
}
New-Item -ItemType Directory -Path $ToolCache -Force | Out-Null
New-Item -ItemType Directory -Path $ToolTemp -Force | Out-Null
$PreviousUvCache = $env:UV_CACHE_DIR
$PreviousTemp = $env:TEMP
$PreviousTmp = $env:TMP
$env:UV_CACHE_DIR = $ToolCache
$env:TEMP = $ToolTemp
$env:TMP = $ToolTemp

Push-Location -LiteralPath $Root
try {
  foreach ($Current in $Profiles) {
    $Input = Join-Path $Root "requirements-engine-$Current.in"
    $Output = Join-Path $Root "requirements-lock-engine-$Current-py313-win64.txt"
    if (!(Test-Path -LiteralPath $Input -PathType Leaf)) {
      throw "Engine dependency input is missing: $Input"
    }
    $VendorArguments = @()
    if ($Current -eq "cpu") {
      # Keep relocking consistent with the official Windows wheel used by the
      # engine builder; falling back to the PyPI sdist requires a C++ toolchain.
      $WheelDirectory = Join-Path $Root "build\resource-engines\engine-cpu-py313\wheels"
      New-Item -ItemType Directory -Path $WheelDirectory -Force | Out-Null
      $LlamaWheel = Join-Path $WheelDirectory "llama_cpp_python-0.3.34-py3-none-win_amd64.whl"
      if (!(Test-Path -LiteralPath $LlamaWheel)) {
        Invoke-WebRequest -Uri "https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.34/llama_cpp_python-0.3.34-py3-none-win_amd64.whl" -OutFile $LlamaWheel
      }
      if ((Get-FileHash -LiteralPath $LlamaWheel -Algorithm SHA256).Hash.ToLowerInvariant() -ne "6526fff614e5ef7e439e6369e076a78073e45e1d791dbe1d5e5d42661f46ca1a") {
        throw "The official Windows llama.cpp wheel does not match its reviewed SHA-256."
      }
      $VendorArguments += @("--find-links", $WheelDirectory)
    }
    # Engine locks consult a vendor wheel index for Torch/llama.cpp. Select
    # the best compatible release across indexes, then freeze its exact
    # artifact hashes; otherwise stale generic packages mirrored by a vendor
    # index can silently override security-fixed PyPI releases.
    & $Uv pip compile $CommonInput $Input (Join-Path $Root "requirements-build.in") `
      --python-version 3.13 `
      --python-platform x86_64-pc-windows-msvc `
      --generate-hashes `
      --no-emit-package setuptools `
      --no-emit-package wheel `
      --index-strategy unsafe-best-match `
      @VendorArguments `
      --output-file $Output
    if ($LASTEXITCODE -ne 0) {
      throw "Could not lock the $Current engine profile."
    }
  }
  if ($Profile -eq "all") {
    & $Python (Join-Path $PSScriptRoot "verify-engine-dependency-locks.py") --write-manifest
    if ($LASTEXITCODE -ne 0) {
      throw "Could not write the reviewed engine dependency-lock manifest."
    }
  }
}
finally {
  Pop-Location
  $env:UV_CACHE_DIR = $PreviousUvCache
  $env:TEMP = $PreviousTemp
  $env:TMP = $PreviousTmp
}
