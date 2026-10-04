param(
  [Parameter(Mandatory = $true)][string]$FilePath,
  [string]$CertificateThumbprint = $env:HAIZFLOW_SIGN_THUMBPRINT,
  [string]$CertificatePath = $env:HAIZFLOW_SIGN_CERT_PATH,
  [string]$TimestampServer = $env:HAIZFLOW_SIGN_TIMESTAMP
)
$ErrorActionPreference = "Stop"
if (!$TimestampServer) { $TimestampServer = "http://timestamp.digicert.com" }
if ($CertificateThumbprint -and $CertificatePath) { throw "Select one signing identity, not both." }
if (!$CertificateThumbprint -and !$CertificatePath) { throw "No signing identity configured." }
if (!(Test-Path -LiteralPath $FilePath -PathType Leaf)) { throw "Signing target is missing." }
$SignTool = Get-Command signtool.exe -ErrorAction SilentlyContinue
$SignToolPath = if ($SignTool) { $SignTool.Source } else { "" }
if (!$SignToolPath) {
  $SdkRoot = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
  if (Test-Path -LiteralPath $SdkRoot) {
    $SignToolPath = Get-ChildItem -LiteralPath $SdkRoot -Directory |
      Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName "x64\signtool.exe" } |
      Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
  }
}
if (!$SignToolPath) { throw "Install the Windows SDK Signing Tools or add signtool.exe to PATH." }
$SignArguments = @("sign", "/fd", "SHA256", "/tr", $TimestampServer, "/td", "SHA256")
if ($CertificateThumbprint) {
  $CertificateThumbprint = $CertificateThumbprint -replace '\s', ''
  if ($CertificateThumbprint -notmatch '^[a-fA-F0-9]{40}$') { throw "Invalid certificate thumbprint." }
  # The token/HSM provider owns the private key. Never export it to a PFX.
  $SignArguments += @("/sha1", $CertificateThumbprint, "/s", "My")
} else {
  if (!(Test-Path -LiteralPath $CertificatePath -PathType Leaf)) { throw "Certificate file is missing." }
  if (!$env:HAIZFLOW_SIGN_CERT_PASSWORD) { throw "Set HAIZFLOW_SIGN_CERT_PASSWORD for an authorized PFX workflow." }
  $SignArguments += @("/f", $CertificatePath, "/p", $env:HAIZFLOW_SIGN_CERT_PASSWORD)
}
& $SignToolPath @SignArguments $FilePath
if ($LASTEXITCODE -ne 0) { throw "Authenticode signing failed." }
& $SignToolPath verify /pa /all /v $FilePath
if ($LASTEXITCODE -ne 0) { throw "Authenticode verification failed." }
$Signature = Get-AuthenticodeSignature -LiteralPath $FilePath
if ($Signature.Status -ne "Valid" -or !$Signature.TimeStamperCertificate) {
  throw "The signature must be valid and timestamped."
}
if ($CertificateThumbprint -and $Signature.SignerCertificate.Thumbprint -ne $CertificateThumbprint) {
  throw "Signature publisher does not match the selected identity."
}
