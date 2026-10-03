param(
  [ValidateSet("python", "uv")][string]$Tool = "python",
  [Parameter(ValueFromRemainingArguments = $true)][string[]]$ToolArguments
)

$ErrorActionPreference = "Stop"
$DevRoot = Split-Path -Parent $PSScriptRoot
$DevPython = Join-Path $DevRoot ".venv\Scripts\python.exe"
if (!(Test-Path -LiteralPath $DevPython)) { throw "Project .venv is missing." }
$DevEnvironment = & $DevPython -c "import json; from haizflow.config import _RUNTIME_ENVIRONMENT, NATIVE_WINDOWS_USERPROFILE; print(json.dumps(dict(_RUNTIME_ENVIRONMENT, HAIZFLOW_NATIVE_WINDOWS_USERPROFILE=NATIVE_WINDOWS_USERPROFILE)))"
if ($LASTEXITCODE -ne 0) { throw "Cannot resolve development storage." }
$DevValues = $DevEnvironment | ConvertFrom-Json
$PreviousDevValues = @{}
foreach ($DevProperty in $DevValues.PSObject.Properties) {
  $PreviousDevValues[$DevProperty.Name] = [Environment]::GetEnvironmentVariable($DevProperty.Name, "Process")
  [Environment]::SetEnvironmentVariable($DevProperty.Name, [string]$DevProperty.Value, "Process")
}
Push-Location $DevRoot
try {
  if ($Tool -eq "uv") {
    $DevCommand = Get-Command uv -ErrorAction Stop
    & $DevCommand.Source @ToolArguments
  } else {
    & $DevPython @ToolArguments
  }
  $DevExitCode = $LASTEXITCODE
} finally {
  Pop-Location
  foreach ($DevName in $PreviousDevValues.Keys) {
    [Environment]::SetEnvironmentVariable($DevName, $PreviousDevValues[$DevName], "Process")
  }
}
exit $DevExitCode
