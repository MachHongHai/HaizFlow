param(
  [string]$ArtifactPath = "",
  [switch]$PreFinalize
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (!$ArtifactPath) {
  $ArtifactPath = Join-Path $Root "dist\HaizFlow"
}
$ArtifactPath = [System.IO.Path]::GetFullPath($ArtifactPath)
$Executable = Join-Path $ArtifactPath "HaizFlow.exe"
if (!(Test-Path -LiteralPath $Executable -PathType Leaf)) {
  throw "Frozen executable is missing: $Executable"
}

function Invoke-FrozenCheck {
  param(
    [string[]]$Arguments,
    [string]$Label,
    [int]$TimeoutSeconds = 600
  )
  $QuotedArguments = @(
    foreach ($Argument in $Arguments) {
      if ($Argument -match '[\s"]') {
        '"' + $Argument.Replace('"', '\"') + '"'
      }
      else {
        $Argument
      }
    }
  )
  $Process = Start-Process `
    -FilePath $Executable `
    -ArgumentList ($QuotedArguments -join " ") `
    -WindowStyle Hidden `
    -PassThru
  try {
    Wait-Process -Id $Process.Id -Timeout $TimeoutSeconds -ErrorAction Stop
  }
  catch {
    Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    throw "$Label timed out after $TimeoutSeconds seconds."
  }
  $Process.Refresh()
  if ($Process.ExitCode -ne 0) {
    throw "$Label failed with exit code $($Process.ExitCode)."
  }
  Write-Output "[OK] $Label"
}

$SmokeParent = [System.IO.Path]::GetFullPath((Join-Path $Root "build\smoke-runtime"))
$SmokeRoot = [System.IO.Path]::GetFullPath((Join-Path $SmokeParent ([guid]::NewGuid().ToString("N"))))
if (![System.IO.Path]::GetDirectoryName($SmokeRoot).Equals($SmokeParent, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Refusing to use an unsafe smoke-test directory: $SmokeRoot"
}
$SmokeData = Join-Path $SmokeRoot "data"
$SmokeModels = Join-Path $SmokeRoot "models"
$SmokeTemp = Join-Path $SmokeRoot "tmp"
$ReleaseArguments = @("--release-smoke")
if ($PreFinalize) {
  $ReleaseArguments += "--pre-finalize"
}

$PreviousHome = $env:HAIZFLOW_HOME
$PreviousRuntimeData = $env:RUNTIME_DATA_DIR
$PreviousModels = $env:MODELS_DIR
$PreviousTemp = $env:HAIZFLOW_TMP_DIR
$PreviousQtPlatform = $env:QT_QPA_PLATFORM
$PreviousSmokeFlag = $env:HAIZFLOW_SMOKE_TEST
try {
  New-Item -ItemType Directory -Path $SmokeRoot -Force | Out-Null
  $env:HAIZFLOW_HOME = $SmokeRoot
  $env:RUNTIME_DATA_DIR = $SmokeData
  $env:MODELS_DIR = $SmokeModels
  $env:HAIZFLOW_TMP_DIR = $SmokeTemp
  $env:QT_QPA_PLATFORM = "offscreen"
  $env:HAIZFLOW_SMOKE_TEST = "1"

  Invoke-FrozenCheck -Arguments $ReleaseArguments -Label "Frozen files and native media tools"
  Invoke-FrozenCheck -Arguments @("--ui-smoke-test") -Label "Frozen Qt/QML startup"
}
finally {
  $env:HAIZFLOW_HOME = $PreviousHome
  $env:RUNTIME_DATA_DIR = $PreviousRuntimeData
  $env:MODELS_DIR = $PreviousModels
  $env:HAIZFLOW_TMP_DIR = $PreviousTemp
  $env:QT_QPA_PLATFORM = $PreviousQtPlatform
  $env:HAIZFLOW_SMOKE_TEST = $PreviousSmokeFlag
  if (Test-Path -LiteralPath $SmokeRoot) {
    $ResolvedSmokeRoot = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $SmokeRoot).Path)
    if (![System.IO.Path]::GetDirectoryName($ResolvedSmokeRoot).Equals($SmokeParent, [System.StringComparison]::OrdinalIgnoreCase)) {
      throw "Refusing to delete an unsafe smoke-test directory: $ResolvedSmokeRoot"
    }
    Remove-Item -LiteralPath $ResolvedSmokeRoot -Recurse -Force
  }
}

Write-Output "Frozen release smoke test passed: $ArtifactPath"
