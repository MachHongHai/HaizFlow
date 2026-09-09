param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("cpu", "cuda128", "vision")]
  [string]$Profile,
  [string]$Version = "1",
  [string]$ReleaseUrl = "",
  [switch]$AllowUnsigned,
  [string]$SignCertificatePath = "",
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

if (!$SignCertificatePath -and !$AllowUnsigned) {
  throw "Public engine archives require Authenticode signing. Supply -SignCertificatePath or use -AllowUnsigned for engineering builds."
}
if (!(Test-Path -LiteralPath $Lock -PathType Leaf)) {
  throw "Engine lock is missing: $Lock. Run scripts\lock-engine-dependencies.ps1 -Profile $Profile."
}
& $VerifierPython (Join-Path $PSScriptRoot "verify-engine-dependency-locks.py")
if ($LASTEXITCODE -ne 0) {
  throw "Engine dependency locks do not match their reviewed manifest."
}

function Sign-EngineExecutable {
  param([string]$Executable)
  if (!$SignCertificatePath) { return }
  if (!(Test-Path -LiteralPath $SignCertificatePath -PathType Leaf)) {
    throw "Authenticode certificate was not found: $SignCertificatePath"
  }
  if (!$env:HAIZFLOW_SIGN_CERT_PASSWORD) {
    throw "Set HAIZFLOW_SIGN_CERT_PASSWORD before signing an engine."
  }
  $SignTool = Get-Command signtool.exe -ErrorAction Stop
  & $SignTool.Source sign /fd SHA256 /f $SignCertificatePath /p $env:HAIZFLOW_SIGN_CERT_PASSWORD /tr $TimestampServer /td SHA256 $Executable
  if ($LASTEXITCODE -ne 0) { throw "Engine signing failed." }
  & $SignTool.Source verify /pa /v $Executable
  if ($LASTEXITCODE -ne 0) { throw "Engine signature verification failed." }
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
  & $Uv pip sync --python $Python --require-hashes --index-strategy unsafe-first-match $Lock
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
    "--exclude-module", "PySide6",
    $EntryPoint
  )
  if ($Profile -in @("cpu", "cuda128")) {
    # PyInstaller's Torch hooks collect native libraries. Add only data that
    # these runtimes read dynamically; collect-all would pull tests, demos and
    # unrelated scientific packages back into every engine.
    foreach ($Module in @("whisperx", "transformers", "demucs")) {
      $Arguments += @("--collect-data", $Module)
    }
    foreach ($Module in @("torch", "torchaudio", "ctranslate2")) {
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
    $Arguments += @("--exclude-module", "onnxruntime", "--exclude-module", "rapidocr")
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
  Copy-Item -LiteralPath (Join-Path $Compliance "THIRD_PARTY_NOTICES.md") -Destination $Artifact -Force
  Copy-Item -LiteralPath (Join-Path $Compliance "licenses") -Destination $Artifact -Recurse -Force
  Sign-EngineExecutable (Join-Path $Artifact "HaizFlowEngine.exe")
  & (Join-Path $Artifact "HaizFlowEngine.exe") --smoke --profile $Profile
  if ($LASTEXITCODE -ne 0) { throw "Frozen engine smoke test failed." }

  if (Test-Path -LiteralPath $Archive) { Remove-Item -LiteralPath $Archive -Force }
  Compress-Archive -Path (Join-Path $Artifact "*") -DestinationPath $Archive -CompressionLevel Optimal
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
