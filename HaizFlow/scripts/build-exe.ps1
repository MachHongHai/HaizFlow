param(
  [switch]$SkipFrozenSmokeTest,
  [switch]$AllowDirtyBuild,
  [string]$SignCertificatePath = "",
  [string]$TimestampServer = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$DistRoot = [System.IO.Path]::GetFullPath((Join-Path $Root "dist"))
$ArtifactPath = [System.IO.Path]::GetFullPath((Join-Path $DistRoot "HaizFlow"))
$PyInstallerRoot = [System.IO.Path]::GetFullPath((Join-Path $Root "build\pyinstaller"))
$PyInstallerWorkPath = Join-Path $PyInstallerRoot "work"
$PyInstallerSpecPath = Join-Path $PyInstallerRoot "spec"
$BuildMetadataPath = [System.IO.Path]::GetFullPath((Join-Path $Root "build\release-metadata"))
$IconPath = Join-Path $BuildMetadataPath "HaizFlow.ico"
$VersionResourcePath = Join-Path $BuildMetadataPath "HaizFlow-version.txt"
$CompliancePath = [System.IO.Path]::GetFullPath((Join-Path $Root "build\release-compliance"))
$FfmpegCompliancePath = [System.IO.Path]::GetFullPath((Join-Path $Root "runtime\compliance\ffmpeg"))
$FfmpegManifestPath = [System.IO.Path]::GetFullPath((Join-Path $Root "runtime\ffmpeg-manifest.json"))

function Invoke-PythonChecked {
  param([string[]]$Arguments, [string]$Label)
  & $Python @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "$Label failed with exit code $LASTEXITCODE."
  }
}

function Sign-ReleaseExecutable {
  param([string]$Executable)
  if (!$SignCertificatePath) {
    return
  }
  if (!(Test-Path -LiteralPath $SignCertificatePath -PathType Leaf)) {
    throw "Authenticode certificate was not found: $SignCertificatePath"
  }
  if (!$env:HAIZFLOW_SIGN_CERT_PASSWORD) {
    throw "Set HAIZFLOW_SIGN_CERT_PASSWORD before signing the release executable."
  }
  $SignTool = Get-Command signtool.exe -ErrorAction SilentlyContinue
  if (!$SignTool) {
    throw "signtool.exe is required for Authenticode signing. Install the Windows SDK."
  }
  & $SignTool.Source sign /fd SHA256 /f $SignCertificatePath /p $env:HAIZFLOW_SIGN_CERT_PASSWORD /tr $TimestampServer /td SHA256 $Executable
  if ($LASTEXITCODE -ne 0) {
    throw "Authenticode signing failed with exit code $LASTEXITCODE."
  }
  & $SignTool.Source verify /pa /v $Executable
  if ($LASTEXITCODE -ne 0) {
    throw "Authenticode verification failed with exit code $LASTEXITCODE."
  }
}

if (!(Test-Path $Python)) {
  throw "Project environment is missing. Run scripts\install-desktop-env.ps1 first."
}

Push-Location -LiteralPath $Root
try {

$GitStatus = & git status --porcelain
if ($LASTEXITCODE -ne 0) {
  throw "Could not determine the Git worktree status. Refusing a release build."
}
if ($GitStatus -and !$AllowDirtyBuild) {
  throw "Git worktree is dirty. Commit/stash changes before building a release, or use -AllowDirtyBuild for a non-installable development artifact."
}

Invoke-PythonChecked -Arguments @((Join-Path $PSScriptRoot "generate-app-icon.py"), "--output", $IconPath) -Label "Application icon generation"
Invoke-PythonChecked -Arguments @((Join-Path $PSScriptRoot "generate-version-resource.py"), "--output", $VersionResourcePath) -Label "Windows version resource generation"

& (Join-Path $PSScriptRoot "test.ps1")
if ($LASTEXITCODE -ne 0) {
  throw "Source test and QML lint gate failed with exit code $LASTEXITCODE."
}
Invoke-PythonChecked -Arguments @((Join-Path $PSScriptRoot "verify-runtime.py"), "--for-build") -Label "Runtime verification"
& (Join-Path $PSScriptRoot "audit-dependencies.ps1")
if ($LASTEXITCODE -ne 0) {
  throw "Dependency vulnerability audit failed with exit code $LASTEXITCODE."
}
Invoke-PythonChecked -Arguments @((Join-Path $PSScriptRoot "test-ffmpeg-runtime.py")) -Label "FFmpeg codec regression"
Invoke-PythonChecked -Arguments @(
  (Join-Path $PSScriptRoot "generate-third-party-notices.py"),
  "--output", $CompliancePath,
  "--strict"
) -Label "Third-party notice generation"

foreach ($RequiredFile in ("LICENSE", "NOTICE")) {
  if (!(Test-Path -LiteralPath (Join-Path $Root $RequiredFile) -PathType Leaf)) {
    throw "Release compliance file is missing: $RequiredFile"
  }
}
foreach ($RequiredFile in (
  $FfmpegManifestPath,
  (Join-Path $FfmpegCompliancePath "LICENSE.txt"),
  (Join-Path $FfmpegCompliancePath "README.txt"),
  (Join-Path $FfmpegCompliancePath "ffmpeg-8.1.2.tar.xz"),
  (Join-Path $FfmpegCompliancePath "ffmpeg-8.1.2.tar.xz.asc")
)) {
  if (!(Test-Path -LiteralPath $RequiredFile -PathType Leaf)) {
    throw "FFmpeg compliance file is missing: $RequiredFile. Run scripts\download_ffmpeg.py."
  }
}

if (Test-Path -LiteralPath $ArtifactPath) {
  if ([System.IO.Path]::GetDirectoryName($ArtifactPath) -ne $DistRoot) {
    throw "Refusing to remove an artifact outside the dist directory: $ArtifactPath"
  }
  Remove-Item -LiteralPath $ArtifactPath -Recurse -Force
}

$ArgsList = @(
  "-m", "PyInstaller",
  "--noconfirm",
  "--clean",
  "--windowed",
  "--onedir",
  "--name", "HaizFlow",
  "--distpath", $DistRoot,
  "--workpath", $PyInstallerWorkPath,
  "--specpath", $PyInstallerSpecPath,
  "--icon", $IconPath,
  "--version-file", $VersionResourcePath,
  "--paths", (Join-Path $Root "src"),
  (Join-Path $Root "haizflow_desktop.py")
)

$ExcludedModules = @(
  "bokeh",
  "cupy",
  "dash",
  "dask",
  "distributed",
  "django",
  "flask",
  "IPython",
  "ipywidgets",
  "jupyter",
  "jupyterlab",
  "notebook",
  "plotly",
  "pytest",
  "sqlalchemy",
  "tensorboard",
  "tensorflow",
  "torch.utils.tensorboard",
  "tornado"
)

foreach ($Module in $ExcludedModules) {
  $ArgsList += @("--exclude-module", $Module)
}

$BinPath = Join-Path $Root "runtime\bin"
if (Test-Path $BinPath) {
  $ArgsList += @("--add-data", "$BinPath;bin")
}

$QmlPath = Join-Path $Root "src\haizflow\desktop\qml"
if (Test-Path $QmlPath) {
  $ArgsList += @("--add-data", "$QmlPath;haizflow\desktop\qml")
}

$BrandingAssetsPath = Join-Path $Root "src\haizflow\desktop\assets\branding"
foreach ($BrandingAsset in ("haizflow-mark.png", "haizflow.ico")) {
  $BrandingAssetPath = Join-Path $BrandingAssetsPath $BrandingAsset
  if (!(Test-Path -LiteralPath $BrandingAssetPath -PathType Leaf)) {
    throw "Branding asset is missing: $BrandingAssetPath"
  }
  $ArgsList += @("--add-data", "$BrandingAssetPath;haizflow\desktop\assets\branding")
}

$SubtitleFontsPath = Join-Path $Root "src\haizflow\assets\fonts"
$SubtitleFontPath = Join-Path $SubtitleFontsPath "Bangers-Regular.ttf"
if (!(Test-Path -LiteralPath $SubtitleFontPath -PathType Leaf)) {
  throw "Subtitle font is missing: $SubtitleFontPath"
}
$ArgsList += @("--add-data", "$SubtitleFontsPath;haizflow\assets\fonts")

$ArgsList += @("--collect-all", "llama_cpp")
$ArgsList += @("--collect-all", "accelerate")
$ArgsList += @("--collect-all", "demucs")
$ArgsList += @("--collect-all", "yt_dlp")
$RapidOcrPackagePath = & $Python -c "import pathlib, rapidocr; print(pathlib.Path(rapidocr.__file__).parent)"
foreach ($RapidOcrDataFile in @("config.yaml", "default_models.yaml")) {
  $RapidOcrDataPath = Join-Path $RapidOcrPackagePath $RapidOcrDataFile
  if (!(Test-Path -LiteralPath $RapidOcrDataPath -PathType Leaf)) {
    throw "RapidOCR package data is missing: $RapidOcrDataPath"
  }
  # Do not use --collect-all here: RapidOCR ships default ONNX weights which
  # must stay out of the installer.  HaizFlow fetches pinned OCR weights on
  # first launch into runtime\models instead.
  $ArgsList += @("--add-data", "$RapidOcrDataPath;rapidocr")
}
$ArgsList += @("--collect-submodules", "rapidocr")
$WhisperxAssetsPath = & $Python -c "import importlib.util, pathlib; spec=importlib.util.find_spec('whisperx'); print(pathlib.Path(next(iter(spec.submodule_search_locations))) / 'assets')"
$WhisperxMelFilters = Join-Path $WhisperxAssetsPath "mel_filters.npz"
if (!(Test-Path -LiteralPath $WhisperxMelFilters -PathType Leaf)) {
  throw "WhisperX mel filter data is missing: $WhisperxMelFilters"
}
$ArgsList += @("--add-data", "$WhisperxMelFilters;whisperx\assets")
$ArgsList += @("--hidden-import", "haizflow.services.douyin_channel_worker")
$ArgsList += @("--hidden-import", "haizflow.vendor.douyin_xbogus")

Invoke-PythonChecked -Arguments $ArgsList -Label "PyInstaller build"

if (!(Test-Path -LiteralPath (Join-Path $ArtifactPath "HaizFlow.exe") -PathType Leaf)) {
  throw "PyInstaller did not create the expected artifact: $ArtifactPath"
}

Sign-ReleaseExecutable -Executable (Join-Path $ArtifactPath "HaizFlow.exe")

Copy-Item -LiteralPath (Join-Path $Root "LICENSE") -Destination (Join-Path $ArtifactPath "LICENSE.txt") -Force
Copy-Item -LiteralPath (Join-Path $Root "NOTICE") -Destination (Join-Path $ArtifactPath "NOTICE.txt") -Force
Copy-Item -LiteralPath (Join-Path $CompliancePath "THIRD_PARTY_NOTICES.md") -Destination $ArtifactPath -Force
Copy-Item -LiteralPath (Join-Path $CompliancePath "licenses") -Destination (Join-Path $ArtifactPath "licenses") -Recurse -Force
Copy-Item -LiteralPath $FfmpegManifestPath -Destination (Join-Path $ArtifactPath "FFMPEG-MANIFEST.json") -Force
$ArtifactSources = Join-Path $ArtifactPath "sources"
New-Item -ItemType Directory -Path $ArtifactSources -Force | Out-Null
Copy-Item -LiteralPath $FfmpegCompliancePath -Destination $ArtifactSources -Recurse -Force

Invoke-PythonChecked -Arguments @(
  (Join-Path $PSScriptRoot "release-preflight.py"),
  "--artifact", $ArtifactPath,
  "--target-directory", $DistRoot,
  "--write", (Join-Path $ArtifactPath "INSTALL-REQUIREMENTS.json")
) -Label "Release disk preflight"

if (!$SkipFrozenSmokeTest) {
  $SmokeArguments = @{
    ArtifactPath = $ArtifactPath
    PreFinalize = $true
  }
  & (Join-Path $PSScriptRoot "smoke-test-frozen.ps1") @SmokeArguments
  if ($LASTEXITCODE -ne 0) {
    throw "Frozen release smoke test failed with exit code $LASTEXITCODE."
  }
}

$FinalizeArguments = @(
  (Join-Path $PSScriptRoot "finalize-release.py"),
  "--artifact", $ArtifactPath
)
Invoke-PythonChecked -Arguments $FinalizeArguments -Label "Release manifest generation"
Invoke-PythonChecked -Arguments @(
  (Join-Path $PSScriptRoot "finalize-release.py"),
  "--artifact", $ArtifactPath,
  "--verify"
) -Label "Release manifest verification"

  Write-Output "Release artifact ready: $ArtifactPath"
}
finally {
  Pop-Location
}
