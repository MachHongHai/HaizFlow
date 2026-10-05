param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("cpu", "cuda128", "vision")]
  [string]$Profile,
  [string]$Version = "1",
  [string]$ReleaseUrl = "",
  [switch]$AllowUnsigned,
  [switch]$UnsignedRelease,
  [string]$SignCertificatePath = "",
  [string]$SignCertificateThumbprint = "",
  [string]$TimestampServer = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Uv = (Get-Command uv -ErrorAction Stop).Source
$PackId = switch ($Profile) {
  "cpu" { "engine-cpu-py313" }
  "cuda128" { "engine-cuda128-py313" }
  "vision" { "engine-vision-onnx" }
}
$BuildRoot = [System.IO.Path]::GetFullPath((Join-Path $Root "build\resource-engines\$PackId"))
$Environment = Join-Path $BuildRoot "venv"
$Python = Join-Path $Environment "Scripts\python.exe"
$Artifact = Join-Path $BuildRoot "dist\HaizFlowEngine"
$Compliance = Join-Path $BuildRoot "compliance"
$Archive = Join-Path $BuildRoot "$PackId-$Version.zip"
$Lock = Join-Path $Root "requirements-lock-engine-$Profile-py313-win64.txt"
$EntryPoint = Join-Path $Root "src\haizflow\engine\main.py"
$VerifierPython = if (Test-Path -LiteralPath (Join-Path $Root ".venv\Scripts\python.exe")) {
  Join-Path $Root ".venv\Scripts\python.exe"
} else {
  (Get-Command python -ErrorAction Stop).Source
}
$BuildCache = Join-Path $BuildRoot "cache\uv"
$BuildTemp = Join-Path $BuildRoot "tmp"
$PreviousUvCache = $env:UV_CACHE_DIR
$PreviousTemp = $env:TEMP
$PreviousTmp = $env:TMP

if ($UnsignedRelease -and ($AllowUnsigned -or $SignCertificatePath -or $SignCertificateThumbprint)) {
  throw "UnsignedRelease cannot be combined with signing or engineering flags."
}
if (!$SignCertificatePath -and !$SignCertificateThumbprint -and !$AllowUnsigned -and !$UnsignedRelease) {
  throw "Choose a signing identity, UnsignedRelease for public unsigned engines, or AllowUnsigned for internal tests."
}
if ($UnsignedRelease) {
  $GitStatus = & git -C $Root status --porcelain
  if ($LASTEXITCODE -ne 0 -or $GitStatus) { throw "Public unsigned engine builds require a clean Git checkout." }
  Write-Warning "Building a public unsigned engine; Windows policy may block its executable."
}
if (!(Test-Path -LiteralPath $Lock -PathType Leaf)) {
  throw "Engine lock is missing: $Lock. Run scripts\lock-engine-dependencies.ps1 -Profile $Profile."
}
& $VerifierPython (Join-Path $PSScriptRoot "verify-engine-dependency-locks.py")
if ($LASTEXITCODE -ne 0) {
  throw "Engine dependency locks do not match their reviewed manifest."
}
$LegalArguments = @((Join-Path $PSScriptRoot "verify-legal-state.py"))
if (!$AllowUnsigned) { $LegalArguments += "--public-release" }
& $VerifierPython @LegalArguments
if ($LASTEXITCODE -ne 0) { throw "Engine licensing review failed." }

function Sign-EngineExecutable {
  param([string]$Executable)
  if (!$SignCertificatePath -and !$SignCertificateThumbprint) { return }
  & (Join-Path $PSScriptRoot "sign-windows.ps1") -FilePath $Executable `
    -CertificatePath $SignCertificatePath -CertificateThumbprint $SignCertificateThumbprint -TimestampServer $TimestampServer
}

Push-Location -LiteralPath $Root
try {
  New-Item -ItemType Directory -Path $BuildRoot -Force | Out-Null
  New-Item -ItemType Directory -Path $BuildCache -Force | Out-Null
  New-Item -ItemType Directory -Path $BuildTemp -Force | Out-Null
  $env:UV_CACHE_DIR = $BuildCache
  $env:TEMP = $BuildTemp
  $env:TMP = $BuildTemp
  if (!(Test-Path -LiteralPath $Python -PathType Leaf)) {
    & $Uv venv $Environment --python 3.13
    if ($LASTEXITCODE -ne 0) { throw "Could not create the engine environment." }
  }
  # The compiled lock contains exact wheel hashes, but does not emit the vendor
  # indexes from its input files. Supply only the reviewed profile wheel index.
  $EngineIndexArguments = switch ($Profile) {
    "cpu" { @("--extra-index-url", "https://download.pytorch.org/whl/cpu") }
    "cuda128" { @("--extra-index-url", "https://download.pytorch.org/whl/cu128") }
    default { @() }
  }
  if ($Profile -eq "cpu") {
    $WheelDirectory = Join-Path $BuildRoot "wheels"
    New-Item -ItemType Directory -Path $WheelDirectory -Force | Out-Null
    $LlamaWheel = Join-Path $WheelDirectory "llama_cpp_python-0.3.34-py3-none-win_amd64.whl"
    $LlamaHash = "6526fff614e5ef7e439e6369e076a78073e45e1d791dbe1d5e5d42661f46ca1a"
    if (!(Test-Path -LiteralPath $LlamaWheel)) {
      Invoke-WebRequest -Uri "https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.34/llama_cpp_python-0.3.34-py3-none-win_amd64.whl" -OutFile $LlamaWheel
    }
    if ((Get-FileHash -LiteralPath $LlamaWheel -Algorithm SHA256).Hash.ToLowerInvariant() -ne $LlamaHash) {
      throw "The official Windows llama.cpp wheel does not match its reviewed SHA-256."
    }
    $EngineIndexArguments += @("--find-links", $WheelDirectory)
  }
  & $Uv pip sync --python $Python --require-hashes --index-strategy unsafe-best-match @EngineIndexArguments $Lock
  if ($LASTEXITCODE -ne 0) { throw "Could not install the locked engine environment." }

  $Arguments = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--console",
    "--onedir",
    "--name", "HaizFlowEngine",
    "--distpath", (Join-Path $BuildRoot "dist"),
    "--workpath", (Join-Path $BuildRoot "work"),
    "--specpath", (Join-Path $BuildRoot "spec"),
    "--paths", (Join-Path $Root "src"),
    "--additional-hooks-dir", (Join-Path $PSScriptRoot "hooks"),
    "--exclude-module", "PySide6",
    $EntryPoint
  )
  if ($Profile -in @("cpu", "cuda128")) {
    # PyInstaller's Torch hooks collect native libraries. Add only data that
    # these runtimes read dynamically; collect-all would pull tests, demos and
    # unrelated scientific packages back into every engine.
    foreach ($Module in @("whisperx", "faster_whisper", "transformers", "demucs", "lightning", "lightning_fabric", "pytorch_lightning")) {
      $Arguments += @("--collect-data", $Module)
    }
    foreach ($Module in @("torch", "torchaudio", "ctranslate2", "onnxruntime")) {
      $Arguments += @("--collect-binaries", $Module)
    }
    foreach ($Module in @(
      "haizflow.pipeline.transcribe",
      "haizflow.pipeline.audio_separation",
      "haizflow.pipeline.omnivoice_tts",
      "haizflow.services.translation",
      "haizflow.services.hymt2_worker"
    )) {
      $Arguments += @("--hidden-import", $Module)
    }
    $Arguments += @("--exclude-module", "rapidocr")
  }
  else {
    # Do not collect RapidOCR's mutable default model payload. HaizFlow loads
    # only the separately checksum-pinned subtitle OCR assets.
    $Arguments += @("--collect-binaries", "onnxruntime")
    $Arguments += @("--hidden-import", "rapidocr", "--hidden-import", "haizflow.pipeline.subtitle_ocr")
    foreach ($Module in @("torch", "torchaudio", "torchvision", "whisperx", "transformers", "demucs")) {
      $Arguments += @("--exclude-module", $Module)
    }
  }
  & $Python @Arguments
  if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed for $PackId." }

  & $Python (Join-Path $PSScriptRoot "write-engine-manifest.py") --profile $Profile --version $Version --output (Join-Path $Artifact "engine.json")
  if ($LASTEXITCODE -ne 0) { throw "Could not write engine.json." }
  & $Python (Join-Path $PSScriptRoot "generate-third-party-notices.py") `
    --output $Compliance `
    --strict `
    --lock $Lock `
    --direct-input (Join-Path $Root "requirements-engine-common.in") `
    --direct-input (Join-Path $Root "requirements-engine-$Profile.in") `
    --profile "engine-$Profile"
  if ($LASTEXITCODE -ne 0) { throw "Could not generate engine compliance notices." }
  Copy-Item -LiteralPath (Join-Path $Root "LICENSE") -Destination $Artifact -Force
  Copy-Item -LiteralPath (Join-Path $Root "NOTICE") -Destination $Artifact -Force
  Copy-Item -LiteralPath (Join-Path $Root "legal") -Destination $Artifact -Recurse -Force
  Copy-Item -LiteralPath (Join-Path $Compliance "THIRD_PARTY_NOTICES.md") -Destination $Artifact -Force
  Copy-Item -LiteralPath (Join-Path $Compliance "licenses") -Destination $Artifact -Recurse -Force
  & $VerifierPython (Join-Path $PSScriptRoot "verify-legal-state.py") --artifact $Artifact
  if ($LASTEXITCODE -ne 0) { throw "Packaged engine legal documents differ from source." }
  Sign-EngineExecutable (Join-Path $Artifact "HaizFlowEngine.exe")
  $SmokeRoot = Join-Path $BuildRoot ("smoke-" + [guid]::NewGuid().ToString("N"))
  $SmokeEnvironment = @{}
  foreach ($Name in @("HAIZFLOW_HOME", "RUNTIME_DATA_DIR", "MODELS_DIR", "HAIZFLOW_TMP_DIR", "HAIZFLOW_SMOKE_TEST")) {
    $SmokeEnvironment[$Name] = [Environment]::GetEnvironmentVariable($Name, "Process")
  }
  try {
    $env:HAIZFLOW_HOME = $SmokeRoot
    $env:RUNTIME_DATA_DIR = Join-Path $SmokeRoot "data"
    $env:MODELS_DIR = Join-Path $SmokeRoot "models"
    $env:HAIZFLOW_TMP_DIR = Join-Path $SmokeRoot "tmp"
    $env:HAIZFLOW_SMOKE_TEST = "1"
    & (Join-Path $Artifact "HaizFlowEngine.exe") --smoke --profile $Profile
    if ($LASTEXITCODE -ne 0) { throw "Frozen engine smoke test failed." }
  } finally {
    foreach ($Name in $SmokeEnvironment.Keys) {
      [Environment]::SetEnvironmentVariable($Name, $SmokeEnvironment[$Name], "Process")
    }
  }
  if (Test-Path -LiteralPath (Join-Path $Artifact "runtime")) { throw "Engine smoke polluted the immutable artifact with runtime data." }

  if (Test-Path -LiteralPath $Archive) { Remove-Item -LiteralPath $Archive -Force }
  Compress-Archive -Path (Join-Path $Artifact "*") -DestinationPath $Archive -CompressionLevel Optimal
  if ((Get-Item -LiteralPath $Archive).Length -ge 2GB) {
    $PartsOutput = Join-Path $BuildRoot ("multipart-" + $Version + "-" + [guid]::NewGuid().ToString("N"))
    & $VerifierPython (Join-Path $PSScriptRoot "split-resource-archive.py") --archive $Archive --output $PartsOutput
    if ($LASTEXITCODE -ne 0) { throw "Could not split the engine into GitHub-sized assets." }
    Write-Output "Upload these checksum-pinned parts, not the oversized ZIP: $PartsOutput"
    if ($ReleaseUrl) { throw "Finalize this multipart engine with --parts-manifest and --parts-url-prefix, not a single ReleaseUrl." }
  }
  if ($ReleaseUrl) {
    & $Python (Join-Path $PSScriptRoot "finalize-resource-pack.py") `
      --pack-id $PackId --version $Version --archive $Archive --url $ReleaseUrl
    if ($LASTEXITCODE -ne 0) { throw "Could not pin the engine archive in the release manifest." }
  }
  Write-Host "Engine archive ready: $Archive"
}
finally {
  Pop-Location
  $env:UV_CACHE_DIR = $PreviousUvCache
  $env:TEMP = $PreviousTemp
  $env:TMP = $PreviousTmp
}
