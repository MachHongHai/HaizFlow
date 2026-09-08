param(
  [Parameter(Mandatory = $true)]
  [string]$InstallerPath,
  [switch]$RequireSignature
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$InstallerPath = [System.IO.Path]::GetFullPath($InstallerPath)
$ChecksumPath = "$InstallerPath.sha256"
$SmokeParent = [System.IO.Path]::GetFullPath((Join-Path $Root "build\installer-smoke"))
$SmokeRoot = [System.IO.Path]::GetFullPath((Join-Path $SmokeParent ([guid]::NewGuid().ToString("N"))))
$InstallRoot = Join-Path $SmokeRoot "HaizFlow"
$InstallLog = Join-Path $SmokeRoot "install.log"
$UninstallLog = Join-Path $SmokeRoot "uninstall.log"

function Invoke-BoundedProcess {
  param(
    [string]$FilePath,
    [string[]]$Arguments,
    [string]$Label,
    [int]$TimeoutSeconds = 900
  )
  $Process = Start-Process `
    -FilePath $FilePath `
    -ArgumentList $Arguments `
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
}

if (!(Test-Path -LiteralPath $InstallerPath -PathType Leaf)) {
  throw "Installer is missing: $InstallerPath"
}
if (!(Test-Path -LiteralPath $ChecksumPath -PathType Leaf)) {
  throw "Installer checksum is missing: $ChecksumPath"
}
$ChecksumLine = (Get-Content -LiteralPath $ChecksumPath -Raw).Trim()
$ExpectedHash, $ExpectedName = $ChecksumLine -split ' \*', 2
$ActualHash = (Get-FileHash -LiteralPath $InstallerPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ExpectedHash -ne $ActualHash -or $ExpectedName -ne [System.IO.Path]::GetFileName($InstallerPath)) {
  throw "Installer checksum verification failed."
}
if ($RequireSignature) {
  $Signature = Get-AuthenticodeSignature -LiteralPath $InstallerPath
  if ($Signature.Status -ne "Valid") {
    throw "Installer Authenticode signature is not valid: $($Signature.Status)"
  }
}

try {
  New-Item -ItemType Directory -Path $SmokeRoot -Force | Out-Null
  Invoke-BoundedProcess `
    -FilePath $InstallerPath `
    -Arguments @(
      "/VERYSILENT",
      "/SUPPRESSMSGBOXES",
      "/NORESTART",
      "/SP-",
      "/DIR=$InstallRoot",
      "/LOG=$InstallLog"
    ) `
    -Label "Silent installer smoke test"

  $InstalledExecutable = Join-Path $InstallRoot "HaizFlow.exe"
  if (!(Test-Path -LiteralPath $InstalledExecutable -PathType Leaf)) {
    throw "Installer did not create the expected executable: $InstalledExecutable"
  }
  & (Join-Path $PSScriptRoot "smoke-test-frozen.ps1") `
    -ArtifactPath $InstallRoot `
    -InstalledLayout
  if ($LASTEXITCODE -ne 0) {
    throw "Installed application smoke test failed with exit code $LASTEXITCODE."
  }

  $Uninstaller = Get-ChildItem -LiteralPath $InstallRoot -Filter "unins*.exe" -File |
    Select-Object -First 1
  if (!$Uninstaller) {
    throw "Installer did not create an uninstaller."
  }
  Invoke-BoundedProcess `
    -FilePath $Uninstaller.FullName `
    -Arguments @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=$UninstallLog") `
    -Label "Silent uninstall smoke test"
  if (Test-Path -LiteralPath $InstalledExecutable) {
    throw "Uninstall left the immutable application payload behind."
  }
  if (!(Test-Path -LiteralPath (Join-Path $InstallRoot "runtime") -PathType Container)) {
    throw "Silent uninstall must preserve runtime data."
  }
  Write-Output "Installer install/start/uninstall smoke test passed: $InstallerPath"
}
finally {
  if (Test-Path -LiteralPath $SmokeRoot) {
    $ResolvedSmokeRoot = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $SmokeRoot).Path)
    if (![System.IO.Path]::GetDirectoryName($ResolvedSmokeRoot).Equals($SmokeParent, [System.StringComparison]::OrdinalIgnoreCase)) {
      throw "Refusing to delete an unsafe installer smoke directory: $ResolvedSmokeRoot"
    }
    Remove-Item -LiteralPath $ResolvedSmokeRoot -Recurse -Force
  }
}
