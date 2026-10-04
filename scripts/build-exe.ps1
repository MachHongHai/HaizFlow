param(
  [switch]$SkipFrozenSmokeTest,
  [switch]$AllowDirtyBuild,
  [switch]$AllowUnsigned,
  [switch]$UnsignedRelease,
  [switch]$CoreLayout,
  [string]$PythonExecutable = "",
  [string]$SignCertificatePath = "",
  [string]$SignCertificateThumbprint = "",
  [string]$TimestampServer = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = if ($PythonExecutable) { [System.IO.Path]::GetFullPath($PythonExecutable) } else { Join-Path $Root ".venv\Scripts\python.exe" }
$BuildEnvironment = Split-Path -Parent (Split-Path -Parent $Python)
$DistRoot = [System.IO.Path]::GetFullPath((Join-Path $Root "dist"))
$ArtifactName = if ($CoreLayout) { "HaizFlowCore" } else { "HaizFlow" }
$ArtifactPath = [System.IO.Path]::GetFullPath((Join-Path $DistRoot $ArtifactName))
$PyInstallerRoot = [System.IO.Path]::GetFullPath((Join-Path $Root "build\pyinstaller"))
$PyInstallerWorkPath = Join-Path $PyInstallerRoot "work"
$PyInstallerSpecPath = Join-Path $PyInstallerRoot "spec"
$PyInstallerConfigPath = [System.IO.Path]::GetFullPath((Join-Path $Root "build\pyinstaller-config"))
$BuildMetadataPath = [System.IO.Path]::GetFullPath((Join-Path $Root "build\release-metadata"))
$IconPath = Join-Path $Root "src\haizflow\desktop\assets\branding\haizflow.ico"
$VersionResourcePath = Join-Path $BuildMetadataPath "HaizFlow-version.txt"
$CompliancePath = [System.IO.Path]::GetFullPath((Join-Path $Root "build\release-compliance"))
$FfmpegCompliancePath = [System.IO.Path]::GetFullPath((Join-Path $Root "runtime\compliance\ffmpeg"))
$FfmpegManifestPath = [System.IO.Path]::GetFullPath((Join-Path $Root "runtime\ffmpeg-manifest.json"))
$ResourcePackManifestPath = [System.IO.Path]::GetFullPath((Join-Path $Root "runtime\resource-pack-manifest.json"))
$ReleaseTempParent = [System.IO.Path]::GetFullPath((Join-Path $Root "build\release-temp"))
$ReleaseTemp = [System.IO.Path]::GetFullPath((Join-Path $ReleaseTempParent ([guid]::NewGuid().ToString("N"))))
$PreviousTemp = $env:TEMP
$PreviousTmp = $env:TMP
$PreviousPyInstallerConfig = $env:PYINSTALLER_CONFIG_DIR
$PreviousPath = $env:PATH

function Invoke-PythonChecked {
  param([string[]]$Arguments, [string]$Label)
  & $Python @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "$Label failed with exit code $LASTEXITCODE."
  }
}

function Sign-ReleaseExecutable {
  param([string]$Executable)
  if (!$SignCertificatePath -and !$SignCertificateThumbprint) { return }
  & (Join-Path $PSScriptRoot "sign-windows.ps1") -FilePath $Executable `
    -CertificatePath $SignCertificatePath -CertificateThumbprint $SignCertificateThumbprint -TimestampServer $TimestampServer
}

if (!(Test-Path $Python)) {
  throw "Project environment is missing. Run scripts\install-desktop-env.ps1 first."
}
if ($UnsignedRelease -and ($AllowUnsigned -or $AllowDirtyBuild -or $SignCertificatePath -or $SignCertificateThumbprint)) {
  throw "UnsignedRelease requires clean public provenance, no signing identity, and no engineering flags."
}
if (!$SignCertificatePath -and !$SignCertificateThumbprint -and !$AllowUnsigned -and !$UnsignedRelease) {
  throw "Choose a signing identity, -UnsignedRelease for public unsigned packaging, or -AllowUnsigned for internal tests."
}
if ($UnsignedRelease) {
  Write-Warning "Public unsigned build: Windows may show Unknown publisher or block execution. Legal, resource and clean-source gates remain mandatory."
} elseif (!$SignCertificatePath -and !$SignCertificateThumbprint) {
  Write-Warning "Building an unsigned engineering artifact. Do not distribute it as a public release."
}

Push-Location -LiteralPath $Root
try {

$LegalArguments = @((Join-Path $PSScriptRoot "verify-legal-state.py"))
if ($UnsignedRelease -or (($SignCertificatePath -or $SignCertificateThumbprint) -and !$AllowDirtyBuild)) { $LegalArguments += "--public-release" }
Invoke-PythonChecked -Arguments $LegalArguments -Label "Legal document and licensing review"

if (![System.IO.Path]::GetDirectoryName($ReleaseTemp).Equals($ReleaseTempParent, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Refusing to use an unsafe release temporary directory: $ReleaseTemp"
}
New-Item -ItemType Directory -Path $ReleaseTemp -Force | Out-Null
if (![System.IO.Path]::GetDirectoryName($PyInstallerConfigPath).Equals(
    [System.IO.Path]::GetFullPath((Join-Path $Root "build")),
    [System.StringComparison]::OrdinalIgnoreCase
)) {
  throw "Refusing to use an unsafe PyInstaller configuration directory: $PyInstallerConfigPath"
}
New-Item -ItemType Directory -Path $PyInstallerConfigPath -Force | Out-Null
$env:TEMP = $ReleaseTemp
$env:TMP = $ReleaseTemp
$env:PYINSTALLER_CONFIG_DIR = $PyInstallerConfigPath

$GitStatus = & git status --porcelain
if ($LASTEXITCODE -ne 0) {
  throw "Could not determine the Git worktree status. Refusing a release build."
}
if ($GitStatus -and !$AllowDirtyBuild) {
  throw "Git worktree is dirty. Commit/stash changes before building a release, or use -AllowDirtyBuild for a non-installable development artifact."
}

Invoke-PythonChecked -Arguments @((Join-Path $PSScriptRoot "generate-version-resource.py"), "--output", $VersionResourcePath) -Label "Windows version resource generation"

& (Join-Path $PSScriptRoot "test.ps1")
if ($LASTEXITCODE -ne 0) {
  throw "Source test and QML lint gate failed with exit code $LASTEXITCODE."
}
Invoke-PythonChecked -Arguments @((Join-Path $PSScriptRoot "verify-runtime.py"), "--for-build", "--profile", "core", "--environment-root", $BuildEnvironment) -Label "Core runtime verification"
$ResourceManifestArguments = @(
  (Join-Path $PSScriptRoot "verify-resource-pack-manifest.py"),
  "--manifest", $ResourcePackManifestPath
)
if ($UnsignedRelease -or (($SignCertificatePath -or $SignCertificateThumbprint) -and !$AllowDirtyBuild)) {
  $ResourceManifestArguments += "--strict"
}
Invoke-PythonChecked -Arguments $ResourceManifestArguments -Label "Resource-pack manifest verification"
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
  $ResourcePackManifestPath,
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
  if ((Test-Path -LiteralPath (Join-Path $ArtifactPath "runtime")) -or
      (Test-Path -LiteralPath (Join-Path $ArtifactPath "update-state"))) {
    throw "This dist artifact has been launched and contains mutable data. Back it up before replacing it; the builder will not delete user data."
  }
  if ((Get-Item -LiteralPath $ArtifactPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw "Refusing to remove a linked artifact directory: $ArtifactPath"
  }
  if (Get-ChildItem -LiteralPath $ArtifactPath -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) {
    throw "Refusing to remove an artifact containing reparse points: $ArtifactPath"
  }
  Remove-Item -LiteralPath $ArtifactPath -Recurse -Force
}

$ArgsList = @(
  "-m", "PyInstaller",
  "--noconfirm",
  "--clean",
  "--windowed",
  "--onedir",
  "--name", $ArtifactName,
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
  "tornado",
  "torch",
  "torchaudio",
  "torchvision",
  "whisperx",
  "pyannote",
  "torchcodec",
  "transformers",
  "accelerate",
  "llama_cpp",
  "ctranslate2",
  "faster_whisper",
  "demucs",
  "rapidocr",
  "psutil",
  "soundfile",
  "rich",
  "pygments",
  "pandas",
  "scipy",
  "sklearn",
  "matplotlib",
  "PySide6.QtWebEngineCore",
  "PySide6.QtWebEngineQuick",
  "PySide6.QtWebEngineWidgets",
  "PySide6.QtPdf",
  "PySide6.QtPdfWidgets",
  "PySide6.QtQuick3D",
  "PySide6.QtCharts",
  "PySide6.QtLocation"
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

$TranslationsPath = Join-Path $Root "src\haizflow\desktop\translations"
$EnglishCatalogPath = Join-Path $TranslationsPath "haizflow_en.qm"
if (!(Test-Path -LiteralPath $EnglishCatalogPath -PathType Leaf)) {
  throw "Translation catalog is missing: $EnglishCatalogPath"
}
$ArgsList += @("--add-data", "$TranslationsPath;haizflow\desktop\translations")

$BrandingAssetsPath = Join-Path $Root "src\haizflow\desktop\assets\branding"
foreach ($BrandingAsset in ("haizflow-mark.png", "haizflow.ico")) {
  $BrandingAssetPath = Join-Path $BrandingAssetsPath $BrandingAsset
  if (!(Test-Path -LiteralPath $BrandingAssetPath -PathType Leaf)) {
    throw "Branding asset is missing: $BrandingAssetPath"
  }
  $ArgsList += @("--add-data", "$BrandingAssetPath;haizflow\desktop\assets\branding")
}

$VoiceSamplesPath = Join-Path $Root "src\haizflow\desktop\assets\voice_samples"
if (Test-Path -LiteralPath $VoiceSamplesPath -PathType Container) {
  $ArgsList += @("--add-data", "$VoiceSamplesPath;haizflow\desktop\assets\voice_samples")
}

$SubtitleFontsPath = Join-Path $Root "src\haizflow\assets\fonts"
$SubtitleFontPath = Join-Path $SubtitleFontsPath "Bangers-Regular.ttf"
if (!(Test-Path -LiteralPath $SubtitleFontPath -PathType Leaf)) {
  throw "Subtitle font is missing: $SubtitleFontPath"
}
$ArgsList += @("--add-data", "$SubtitleFontsPath;haizflow\assets\fonts")

$ArgsList += @("--collect-all", "yt_dlp")
$BundledModelsPath = Join-Path $Root "build\bundled-models\speaker-identification"
Invoke-PythonChecked -Arguments @((Join-Path $PSScriptRoot "prepare-bundled-speaker-model.py"), "--download") -Label "Bundled speaker model"
  $BundledSpeakerFile = Join-Path $BundledModelsPath "wespeaker_en_voxceleb_resnet34.onnx"
  $ArgsList += @("--add-data", "$BundledSpeakerFile;models\speaker-identification")
$ArgsList += @("--collect-binaries", "onnxruntime")
$ArgsList += @("--hidden-import", "onnxruntime", "--hidden-import", "haizflow.engine.main")
$ArgsList += @("--hidden-import", "haizflow.pipeline.speaker_identity", "--hidden-import", "haizflow.pipeline.speaker_runtime")
$ArgsList += @("--hidden-import", "haizflow.pipeline.omnivoice_tts")
$ArgsList += @("--hidden-import", "haizflow.services.douyin_channel_worker")
$ArgsList += @("--hidden-import", "haizflow.vendor.douyin_xbogus")
$ArgsList += @("--add-data", "$ResourcePackManifestPath;.")

$PythonBase = (& $Python -c "import sys; print(sys.base_prefix)").Trim()
if (!$PythonBase -or !(Test-Path -LiteralPath $PythonBase -PathType Container)) {
  throw "Could not resolve the base Python runtime for an isolated frozen build."
}
$IsolatedBuildPath = @(
  (Split-Path -Parent $Python),
  $PythonBase,
  (Join-Path $PythonBase "Scripts"),
  (Join-Path $env:SystemRoot "System32"),
  $env:SystemRoot
) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Container) }
try {
  # PyInstaller searches PATH while resolving native imports. Restrict it to
  # the selected Python and Windows runtimes so unrelated tools (for example
  # Poppler installed by another application) cannot inject incompatible ICU
  # or C runtime DLLs into the frozen Qt process.
  $env:PATH = $IsolatedBuildPath -join [System.IO.Path]::PathSeparator
  Invoke-PythonChecked -Arguments $ArgsList -Label "PyInstaller build"
}
finally {
  $env:PATH = $PreviousPath
}

if (!(Test-Path -LiteralPath (Join-Path $ArtifactPath "$ArtifactName.exe") -PathType Leaf)) {
  throw "PyInstaller did not create the expected artifact: $ArtifactPath"
}

# PyInstaller's generic QtQml hook copies every QML module installed beside
# PySide, including WebEngine, Quick3D and charting stacks that HaizFlow never
# imports. Prune only the explicitly unsupported modules before measuring or
# signing the immutable Core artifact. The frozen smoke test below catches an
# accidental dependency on anything in this allowlist-based removal.
$FrozenPySideRoot = [System.IO.Path]::GetFullPath((Join-Path $ArtifactPath "_internal\PySide6"))
$FrozenQmlRoot = [System.IO.Path]::GetFullPath((Join-Path $FrozenPySideRoot "qml"))
$UnusedQmlModules = @(
  "Qt3D",
  "QtCharts",
  "QtDataVisualization",
  "QtGraphs",
  "QtLocation",
  "QtPositioning",
  "QtQuick3D",
  "QtWebEngine"
)
foreach ($Module in $UnusedQmlModules) {
  $ModulePath = [System.IO.Path]::GetFullPath((Join-Path $FrozenQmlRoot $Module))
  if ([System.IO.Path]::GetDirectoryName($ModulePath) -ne $FrozenQmlRoot) {
    throw "Refusing to prune an unsafe QML module path: $ModulePath"
  }
  if (Test-Path -LiteralPath $ModulePath -PathType Container) {
    Remove-Item -LiteralPath $ModulePath -Recurse -Force
  }
}
$UnusedNestedQmlModules = @("QtQuick\Pdf", "QtQuick\Timeline", "QtQuick\VirtualKeyboard")
foreach ($RelativePath in $UnusedNestedQmlModules) {
  $ModulePath = [System.IO.Path]::GetFullPath((Join-Path $FrozenQmlRoot $RelativePath))
  if (!$ModulePath.StartsWith("$FrozenQmlRoot\", [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to prune an unsafe nested QML module path: $ModulePath"
  }
  if (Test-Path -LiteralPath $ModulePath -PathType Container) {
    Remove-Item -LiteralPath $ModulePath -Recurse -Force
  }
}
$UnusedQtLibraryPrefixes = @(
  "Qt63D",
  "Qt6Charts",
  "Qt6DataVisualization",
  "Qt6Graphs",
  "Qt6Location",
  "Qt6Pdf",
  "Qt6Positioning",
  "Qt6Quick3D",
  "Qt6QuickTimeline",
  "Qt6VirtualKeyboard",
  "Qt6WebEngine"
)
Get-ChildItem -LiteralPath $FrozenPySideRoot -File | Where-Object {
  $FileName = $_.Name
  @($UnusedQtLibraryPrefixes | Where-Object {
    $FileName.StartsWith($_, [System.StringComparison]::OrdinalIgnoreCase)
  }).Count -gt 0
} | ForEach-Object {
  Remove-Item -LiteralPath $_.FullName -Force
}
# This input-context plugin belongs to the unused GPL-only Virtual Keyboard
# module, not Windows' native IME. Keep its removal scoped to one exact file.
$UnusedInputPlugin = [System.IO.Path]::GetFullPath((Join-Path $FrozenPySideRoot "plugins\platforminputcontexts\qtvirtualkeyboardplugin.dll"))
if (!$UnusedInputPlugin.StartsWith("$FrozenPySideRoot\", [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Refusing to prune an unsafe Qt input-context plugin."
}
if (Test-Path -LiteralPath $UnusedInputPlugin -PathType Leaf) {
  Remove-Item -LiteralPath $UnusedInputPlugin -Force
}

$ForbiddenReleasePatterns = @(
  "runtime\data",
  "runtime\cache",
  "runtime\models"
)
foreach ($RelativePath in $ForbiddenReleasePatterns) {
  if (Test-Path -LiteralPath (Join-Path $ArtifactPath $RelativePath)) {
    throw "Mutable runtime data leaked into the Core artifact: $RelativePath"
  }
}
$MutableFiles = Get-ChildItem -LiteralPath $ArtifactPath -Recurse -File | Where-Object {
  $_.Name.EndsWith(".part", [System.StringComparison]::OrdinalIgnoreCase) -or
  $_.Name.EndsWith(".partial", [System.StringComparison]::OrdinalIgnoreCase) -or
  $_.Name.EndsWith(".log", [System.StringComparison]::OrdinalIgnoreCase)
}
if ($MutableFiles) {
  throw "Mutable files leaked into the Core artifact: $($MutableFiles[0].FullName)"
}

$ForbiddenCoreNames = @(
  "torch", "torchaudio", "torchvision", "whisperx", "pyannote", "transformers",
  "accelerate", "llama_cpp", "ctranslate2", "demucs", "rapidocr",
  "psutil", "soundfile", "rich", "pygments"
)
foreach ($Name in $ForbiddenCoreNames) {
  $Found = Get-ChildItem -LiteralPath (Join-Path $ArtifactPath "_internal") -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq $Name -or $_.Name.StartsWith("$Name.", [System.StringComparison]::OrdinalIgnoreCase) } |
    Select-Object -First 1
  if ($Found) {
    throw "Optional AI dependency leaked into Core: $($Found.FullName)"
  }
}
$WebEngineBinary = Get-ChildItem -LiteralPath (Join-Path $ArtifactPath "_internal") -Recurse -File -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -like "*WebEngine*" } | Select-Object -First 1
if ($WebEngineBinary) {
  throw "Qt WebEngine leaked into Core: $($WebEngineBinary.FullName)"
}

$ForbiddenRootLibraries = @(
  (Join-Path $ArtifactPath "_internal\icuuc.dll"),
  (Join-Path $ArtifactPath "_internal\icudt78.dll")
)
foreach ($Library in $ForbiddenRootLibraries) {
  if (Test-Path -LiteralPath $Library -PathType Leaf) {
    throw "Frozen native dependency collision detected: $Library. Rebuild with an isolated PATH."
  }
}

Sign-ReleaseExecutable -Executable (Join-Path $ArtifactPath "$ArtifactName.exe")

Copy-Item -LiteralPath (Join-Path $Root "LICENSE") -Destination (Join-Path $ArtifactPath "LICENSE.txt") -Force
Copy-Item -LiteralPath (Join-Path $Root "NOTICE") -Destination (Join-Path $ArtifactPath "NOTICE.txt") -Force
Copy-Item -LiteralPath (Join-Path $Root "legal") -Destination $ArtifactPath -Recurse -Force
Copy-Item -LiteralPath (Join-Path $CompliancePath "THIRD_PARTY_NOTICES.md") -Destination $ArtifactPath -Force
Copy-Item -LiteralPath (Join-Path $CompliancePath "licenses") -Destination (Join-Path $ArtifactPath "licenses") -Recurse -Force
Invoke-PythonChecked -Arguments @((Join-Path $PSScriptRoot "verify-legal-state.py"), "--artifact", $ArtifactPath) -Label "Packaged legal documents"
Copy-Item -LiteralPath $FfmpegManifestPath -Destination (Join-Path $ArtifactPath "FFMPEG-MANIFEST.json") -Force
Copy-Item -LiteralPath $ResourcePackManifestPath -Destination (Join-Path $ArtifactPath "RESOURCE-PACKS.json") -Force
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
# Finalization adds BUILD-INFO.json and SHA256SUMS.txt. Refresh the embedded
# storage manifest from that complete artifact, then regenerate checksums so
# the internal numbers and the installer calculation use the same payload.
Invoke-PythonChecked -Arguments @(
  (Join-Path $PSScriptRoot "release-preflight.py"),
  "--artifact", $ArtifactPath,
  "--write", (Join-Path $ArtifactPath "INSTALL-REQUIREMENTS.json")
) -Label "Final release disk requirements"
Invoke-PythonChecked -Arguments $FinalizeArguments -Label "Final release manifest generation"
Invoke-PythonChecked -Arguments @(
  (Join-Path $PSScriptRoot "finalize-release.py"),
  "--artifact", $ArtifactPath,
  "--verify"
) -Label "Release manifest verification"

$CoreBytes = (Get-ChildItem -LiteralPath $ArtifactPath -Recurse -File | Measure-Object -Property Length -Sum).Sum
$CoreLimitBytes = [int64](1.25 * 1GB)
if ($CoreBytes -gt $CoreLimitBytes) {
  throw "Core artifact is $([math]::Round($CoreBytes / 1GB, 2)) GiB; limit is 1.25 GiB."
}

  Write-Output "Release artifact ready: $ArtifactPath"
}
finally {
  $env:TEMP = $PreviousTemp
  $env:TMP = $PreviousTmp
  $env:PYINSTALLER_CONFIG_DIR = $PreviousPyInstallerConfig
  $env:PATH = $PreviousPath
  if (Test-Path -LiteralPath $ReleaseTemp) {
    $ResolvedReleaseTemp = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $ReleaseTemp).Path)
    if (![System.IO.Path]::GetDirectoryName($ResolvedReleaseTemp).Equals($ReleaseTempParent, [System.StringComparison]::OrdinalIgnoreCase)) {
      throw "Refusing to delete an unsafe release temporary directory: $ResolvedReleaseTemp"
    }
    Remove-Item -LiteralPath $ResolvedReleaseTemp -Recurse -Force
  }
  Pop-Location
}
