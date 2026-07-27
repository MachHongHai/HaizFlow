param(
  [switch]$SkipCompile
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$QmlLint = Join-Path $Root ".venv\Lib\site-packages\PySide6\qmllint.exe"
$QmlDirectory = Join-Path $Root "src\haizflow\desktop\qml"
$TestTempParent = [System.IO.Path]::GetFullPath((Join-Path $Root "build\test-temp"))
$TestTemp = [System.IO.Path]::GetFullPath((Join-Path $TestTempParent ([guid]::NewGuid().ToString("N"))))

if (!(Test-Path -LiteralPath $Python)) {
  throw "Project environment is missing. Run scripts\install-desktop-env.ps1 first."
}
if (!(Test-Path -LiteralPath $QmlLint -PathType Leaf)) {
  throw "Qt QML lint tool is missing from the project environment: $QmlLint"
}

$PreviousTemp = $env:TEMP
$PreviousTmp = $env:TMP
try {
  if (![System.IO.Path]::GetDirectoryName($TestTemp).Equals($TestTempParent, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to use an unsafe test temporary directory: $TestTemp"
  }
  New-Item -ItemType Directory -Path $TestTemp -Force | Out-Null
  $env:TEMP = $TestTemp
  $env:TMP = $TestTemp
  $env:PYTHONPATH = Join-Path $Root "src"

  if (!$SkipCompile) {
    & $Python -m compileall -q (Join-Path $Root "src") (Join-Path $Root "scripts") (Join-Path $Root "test")
    if ($LASTEXITCODE -ne 0) {
      throw "Python compilation failed."
    }
  }

  & $Python -m unittest discover -s (Join-Path $Root "test") -p "test_*.py"
  if ($LASTEXITCODE -ne 0) {
    throw "Test suite failed."
  }

  $QmlFiles = Get-ChildItem -LiteralPath $QmlDirectory -Filter "*.qml" -File |
    ForEach-Object { $_.FullName }
  if (!$QmlFiles) {
    throw "No QML source files were found below $QmlDirectory."
  }
  $QmlDiagnostics = & $QmlLint -I $QmlDirectory @QmlFiles 2>&1
  if ($LASTEXITCODE -ne 0 -or $QmlDiagnostics) {
    $QmlDiagnostics | Write-Output
    throw "Qt QML lint failed or reported diagnostics."
  }
}
finally {
  $env:TEMP = $PreviousTemp
  $env:TMP = $PreviousTmp
  if (Test-Path -LiteralPath $TestTemp) {
    $ResolvedTestTemp = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $TestTemp).Path)
    if (![System.IO.Path]::GetDirectoryName($ResolvedTestTemp).Equals($TestTempParent, [System.StringComparison]::OrdinalIgnoreCase)) {
      throw "Refusing to delete an unsafe test temporary directory: $ResolvedTestTemp"
    }
    Remove-Item -LiteralPath $ResolvedTestTemp -Recurse -Force
  }
}
