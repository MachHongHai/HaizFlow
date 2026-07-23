#ifndef SourceDir
  #error SourceDir must point to the verified dist\HaizFlow artifact.
#endif
#ifndef AppVersion
  #error AppVersion must be supplied by scripts\build-installer.ps1.
#endif
#ifndef RequiredFreeBytes
  #error RequiredFreeBytes must be calculated from the verified artifact.
#endif

#define AppName "HaizFlow"
#define AppPublisher "HaizFlow"

[Setup]
AppId={{799AE20D-E7A5-4D79-96DE-708E161BF32A}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
; Start on the drive from which the user runs the installer. This avoids an
; unasked default write to the Windows system drive; users can still choose
; any writable folder in the directory page.
DefaultDirName={code:DefaultInstallDir}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist\installer
OutputBaseFilename=HaizFlow-{#AppVersion}-Setup
SetupIconFile={#SourceDir}\HaizFlow.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\HaizFlow.exe
CloseApplications=yes
RestartApplications=no

[Files]
; runtime is mutable user data. It is deliberately neither copied nor deleted
; by setup, so upgrades and uninstall preserve projects, models and settings.
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "runtime\*"

[InstallDelete]
; Remove only immutable payload from a previous release before copying the
; verified artifact. runtime\ is intentionally absent: it contains user
; projects, settings and caches and must survive upgrade/uninstall.
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\licenses"
Type: filesandordirs; Name: "{app}\sources"
Type: files; Name: "{app}\HaizFlow.exe"
Type: files; Name: "{app}\BUILD-INFO.json"
Type: files; Name: "{app}\SHA256SUMS.txt"
Type: files; Name: "{app}\INSTALL-REQUIREMENTS.json"
Type: files; Name: "{app}\LICENSE.txt"
Type: files; Name: "{app}\NOTICE.txt"
Type: files; Name: "{app}\THIRD_PARTY_NOTICES.md"
Type: files; Name: "{app}\FFMPEG-MANIFEST.json"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\HaizFlow.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\HaizFlow.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\HaizFlow.exe"; Description: "Launch HaizFlow"; Flags: nowait postinstall skipifsilent

[Code]
function DefaultInstallDir(Param: String): String;
begin
  Result := AddBackslash(ExtractFileDrive(ExpandConstant('{srcexe}'))) + 'HaizFlow';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  FreeBytes: Int64;
  TotalBytes: Int64;
  RequiredBytes: Int64;
  ProbePath: String;
begin
  Result := True;
  if CurPageID <> wpSelectDir then
    exit;

  if not ForceDirectories(WizardDirValue) then
  begin
    MsgBox('Could not create the selected installation folder. Choose a folder that your account can write to.', mbError, MB_OK);
    Result := False;
    exit;
  end;

  { The application stores mutable runtime data below {app}. Reject a folder
    that will not remain writable after the installer exits. }
  ProbePath := AddBackslash(WizardDirValue) + '.haizflow-installer-write-probe.tmp';
  if FileExists(ProbePath) or
     (not SaveStringToFile(ProbePath, 'write probe', False)) then
  begin
    MsgBox('The selected installation folder is not writable. Choose another folder, for example D:\HaizFlow.', mbError, MB_OK);
    Result := False;
    exit;
  end;
  DeleteFile(ProbePath);

  RequiredBytes := {#RequiredFreeBytes};
  if not GetSpaceOnDisk(WizardDirValue, False, FreeBytes, TotalBytes) then
  begin
    MsgBox('Could not check free space for the selected installation folder.', mbError, MB_OK);
    Result := False;
    exit;
  end;
  if FreeBytes < RequiredBytes then
  begin
    MsgBox(
      'The selected drive does not have enough free space for a safe install or upgrade.' + #13#10 + #13#10 +
      'Required: ' + IntToStr(RequiredBytes div 1024 div 1024 div 1024) + ' GB' + #13#10 +
      'Available: ' + IntToStr(FreeBytes div 1024 div 1024 div 1024) + ' GB',
      mbError,
      MB_OK
    );
    Result := False;
  end;
end;

[Messages]
SelectDirLabel3=Choose a writable folder for HaizFlow. Existing runtime data is preserved during upgrades and uninstall.
