param(
  [Parameter(Mandatory = $true)]
  [string]$InstallerPath,
  [switch]$RequireSignature,
  [switch]$AllowRegisteredInstall
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$InstallerPath = [System.IO.Path]::GetFullPath($InstallerPath)
$ChecksumPath = "$InstallerPath.sha256"
$SmokeParent = [System.IO.Path]::GetFullPath((Join-Path $Root "build\installer-smoke"))
$SmokeRoot = [System.IO.Path]::GetFullPath((Join-Path $SmokeParent ([guid]::NewGuid().ToString("N"))))
$InstallRoot = Join-Path $SmokeRoot "HaizFlow test install"
$ReportRoot = Join-Path $Root "build\installer-reports\$([System.IO.Path]::GetFileName($SmokeRoot))"
$InstallLog = Join-Path $ReportRoot "install.log"
$UninstallLog = Join-Path $ReportRoot "uninstall.log"
$PreviousTemp = $env:TEMP
$PreviousTmp = $env:TMP
$Passed = $false
$UninstallerPath = ""
$TestVersion = ""
$FixtureHashes = @{}

function Invoke-SmokeInstall {
  param([string]$Log)
  Invoke-BoundedProcess -FilePath $InstallerPath -Arguments @(
    "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/NOICONS",
    ('/DIR="' + $InstallRoot + '"'), ('/LOG="' + $Log + '"')
  ) -Label "Installer smoke test"
}

function Assert-UserData {
  foreach ($Path in $FixtureHashes.Keys) {
    if (!(Test-Path -LiteralPath $Path -PathType Leaf) -or
        (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ne $FixtureHashes[$Path]) {
      throw "Installer changed user data: $Path"
    }
  }
}

function Invoke-SmokeUninstall {
  param([string]$Log)
  Invoke-BoundedProcess -FilePath $UninstallerPath -Arguments @(
    "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", ('/LOG="' + $Log + '"')
  ) -Label "Uninstall smoke test"
  Assert-UserData
  if ((Test-Path -LiteralPath (Join-Path $InstallRoot "HaizFlow.exe")) -or
      (Test-Path -LiteralPath (Join-Path $InstallRoot "versions\$TestVersion"))) {
    throw "Uninstall left immutable application files behind."
  }
}

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
if ([System.IO.Path]::GetFileName($InstallerPath) -notlike '*-DEVELOPMENT-Setup.exe' -and !$AllowRegisteredInstall) {
  throw "Test a public AppId only in a clean Windows VM; pass -AllowRegisteredInstall there."
}
if (!$AllowRegisteredInstall) {
  # Never replace the registration/uninstaller of the user's installed test app.
  foreach ($RegistryRoot in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
      'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
      'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall')) {
    foreach ($Identity in @('{2E512B7B-B9A6-4FB9-A306-C836B1DA102A}_is1',
        '{799AE20D-E7A5-4D79-96DE-708E161BF32A}_is1')) {
      if (Test-Path -LiteralPath (Join-Path $RegistryRoot $Identity)) {
        if ([System.IO.Path]::GetFileName($InstallerPath) -notlike '*-SMOKE-*-DEVELOPMENT-Setup.exe') {
          throw 'Existing HaizFlow installation detected. Use a separately compiled SmokeAppId fixture or a clean VM.'
        }
      }
    }
  }
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
  New-Item -ItemType Directory -Path $ReportRoot -Force | Out-Null
  $SmokeTemp = Join-Path $SmokeRoot "temp"
  New-Item -ItemType Directory -Path $SmokeTemp -Force | Out-Null
  $env:TEMP = $SmokeTemp
  $env:TMP = $SmokeTemp
  Invoke-SmokeInstall $InstallLog

  $InstalledExecutable = Join-Path $InstallRoot "HaizFlow.exe"
  if (!(Test-Path -LiteralPath $InstalledExecutable -PathType Leaf)) {
    throw "Installer did not create the expected executable: $InstalledExecutable"
  }
  $TestVersion = (Get-Content -LiteralPath (Join-Path $InstallRoot "BUILD-INFO.json") -Raw | ConvertFrom-Json).version
  if ($TestVersion -notmatch '^\d+\.\d+\.\d+$') { throw "Invalid installed version." }
  # Measure the exact shipped file set, not mutable runtime/update-state or
  # Inno's generated uninstaller. Include the checksum file's own byte size.
  $InstalledRequirements = Get-Content -LiteralPath (Join-Path $InstallRoot "INSTALL-REQUIREMENTS.json") -Raw | ConvertFrom-Json
  $InstalledChecksumsPath = Join-Path $InstallRoot "SHA256SUMS.txt"
  $InstalledPayloadBytes = [int64](Get-Item -LiteralPath $InstalledChecksumsPath).Length
  foreach ($Line in Get-Content -LiteralPath $InstalledChecksumsPath) {
    $Digest, $RelativePath = $Line -split ' \*', 2
    if ($Digest -notmatch '^[a-f0-9]{64}$' -or !$RelativePath) { throw "Invalid installed checksum entry." }
    $PayloadFile = [System.IO.Path]::GetFullPath((Join-Path $InstallRoot $RelativePath))
    if (!$PayloadFile.StartsWith("$InstallRoot\", [System.StringComparison]::OrdinalIgnoreCase)) {
      throw "Installed checksum entry escapes the application folder."
    }
    $InstalledPayloadBytes += [int64](Get-Item -LiteralPath $PayloadFile).Length
  }
  if ($InstalledPayloadBytes -ne [int64]$InstalledRequirements.artifact_bytes) {
    throw "Installed payload differs from the storage estimate: $InstalledPayloadBytes bytes."
  }
  $UninstallerBytes = [int64](Get-ChildItem -LiteralPath $InstallRoot -Filter 'unins*' -File | Measure-Object -Property Length -Sum).Sum
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
  $UninstallerPath = $Uninstaller.FullName
  if ($RequireSignature) {
    foreach ($Executable in @($UninstallerPath, $InstalledExecutable,
        (Join-Path $InstallRoot "updater\HaizFlowUpdater.exe"),
        (Join-Path $InstallRoot "versions\$TestVersion\HaizFlowCore.exe"))) {
      $Signature = Get-AuthenticodeSignature -LiteralPath $Executable
      if ($Signature.Status -ne "Valid" -or !$Signature.TimeStamperCertificate) {
        throw "Installed signature is invalid or lacks a timestamp: $Executable"
      }
    }
  }
  foreach ($RelativePath in @("runtime\data\user-fixture.json", "runtime\models\user-fixture.bin",
      "runtime\projects\user-fixture\project.json", "external-project\project.json")) {
    $Base = if ($RelativePath.StartsWith("external-project")) { $SmokeRoot } else { $InstallRoot }
    $Path = Join-Path $Base $RelativePath
    New-Item -ItemType Directory -Path (Split-Path -Parent $Path) -Force | Out-Null
    Set-Content -LiteralPath $Path -Value "Preserve this isolated user fixture $RelativePath" -Encoding utf8
    $FixtureHashes[$Path] = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
  }
  $StaleCoreFile = Join-Path $InstallRoot "versions\$TestVersion\repair-stale-fixture.txt"
  Set-Content -LiteralPath $StaleCoreFile -Value "Repair must remove this stale immutable file" -Encoding utf8
  $CorruptQml = Join-Path $InstallRoot "versions\$TestVersion\_internal\haizflow\desktop\qml\Main.qml"
  Set-Content -LiteralPath $CorruptQml -Value "INTENTIONALLY CORRUPTED TEST UI" -Encoding utf8
  Invoke-SmokeInstall (Join-Path $ReportRoot "repair.log")
  if (Test-Path -LiteralPath $StaleCoreFile) { throw "Repair retained stale Core files." }
  Assert-UserData
  & (Join-Path $PSScriptRoot "smoke-test-frozen.ps1") -ArtifactPath $InstallRoot -InstalledLayout
  if ($LASTEXITCODE -ne 0) { throw "Repaired application smoke failed." }
  Invoke-SmokeUninstall $UninstallLog
  Invoke-SmokeInstall (Join-Path $ReportRoot "reinstall.log")
  Assert-UserData
  & (Join-Path $PSScriptRoot "smoke-test-frozen.ps1") -ArtifactPath $InstallRoot -InstalledLayout
  if ($LASTEXITCODE -ne 0) { throw "Reinstalled application smoke failed." }
  Invoke-SmokeUninstall (Join-Path $ReportRoot "uninstall-final.log")
  $Passed = $true
  @{
    installer = $InstallerPath; sha256 = $ActualHash; passed = $true
    scenarios = @("fresh install", "real frozen UI startup", "repair", "uninstall keeps data", "reinstall retained data", "final uninstall")
    data_files_preserved = $FixtureHashes.Count; signature_required = [bool]$RequireSignature
    estimated_payload_bytes = [int64]$InstalledRequirements.artifact_bytes
    installed_payload_bytes = $InstalledPayloadBytes; storage_estimate_matches = $true
    generated_uninstaller_bytes = $UninstallerBytes
    working_headroom_bytes = [int64]$InstalledRequirements.working_headroom_bytes
  } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $ReportRoot "result.json") -Encoding utf8
  Write-Output "Installer fresh/start/repair/uninstall/reinstall smoke passed. Reports: $ReportRoot"
}
finally {
  $env:TEMP = $PreviousTemp
  $env:TMP = $PreviousTmp
  # Keep failed installations/logs available for diagnosis instead of orphaning
  # an uninstall registry entry by deleting its directory.
  if ($Passed -and (Test-Path -LiteralPath $SmokeRoot)) {
    $ResolvedSmokeRoot = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $SmokeRoot).Path)
    if (![System.IO.Path]::GetDirectoryName($ResolvedSmokeRoot).Equals($SmokeParent, [System.StringComparison]::OrdinalIgnoreCase)) {
      throw "Refusing to delete an unsafe installer smoke directory: $ResolvedSmokeRoot"
    }
    for ($CleanupAttempt = 0; $CleanupAttempt -lt 10; $CleanupAttempt++) {
      try {
        Remove-Item -LiteralPath $ResolvedSmokeRoot -Recurse -Force -ErrorAction Stop
        break
      }
      catch {
        if ($CleanupAttempt -eq 9) {
          Write-Warning "Smoke tests passed; Windows still holds a temporary uninstaller file. Preserved: $ResolvedSmokeRoot"
        }
        else { Start-Sleep -Milliseconds 500 }
      }
    }
  }
  elseif (!$Passed) {
    Write-Warning "Failed smoke workspace preserved: $SmokeRoot; reports: $ReportRoot"
  }
}
