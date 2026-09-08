#ifndef SourceDir
  #error SourceDir must point to the verified dist\HaizFlow artifact.
#endif
#ifndef AppVersion
  #error AppVersion must be supplied by scripts\build-installer.ps1.
#endif
#ifndef RequiredFreeBytes
  #error RequiredFreeBytes must be calculated from the verified artifact.
#endif
#ifndef RequiredFreshBytes
  #error RequiredFreshBytes must be calculated from the verified artifact.
#endif
#ifndef SetupIconPath
  #error SetupIconPath must point to the generated multi-resolution .ico file.
#endif
#ifndef BrandingMarkPath
  #error BrandingMarkPath must point to the installer branding PNG.
#endif
#ifndef OutputBaseFilename
  #error OutputBaseFilename must be supplied by scripts\build-installer.ps1.
#endif

#if Ver < EncodeVer(6, 5, 0)
  #error HaizFlow requires Inno Setup 6.5 or later for the high-DPI dark wizard.
#endif

#define AppName "HaizFlow"
#define AppPublisher "Mach Hong Hai"
#define AppUrl "https://github.com/MachHongHai/HaizFlow"

[Setup]
AppId={{799AE20D-E7A5-4D79-96DE-708E161BF32A}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
AppVerName={#AppName} {#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Windows installer
VersionInfoCopyright=Copyright (c) 2026 Mach Hong Hai
VersionInfoOriginalFileName={#OutputBaseFilename}.exe
VersionInfoProductName={#AppName}
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
UsePreviousAppDir=yes
DisableDirPage=auto
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
AllowUNCPath=no
AllowNetworkDrive=no
OutputDir=..\dist\installer
OutputBaseFilename={#OutputBaseFilename}
SetupIconFile={#SetupIconPath}
LicenseFile={#SourceDir}\LICENSE.txt
Compression=lzma2/ultra64
SolidCompression=yes
DefaultDialogFontName=Segoe UI
WizardStyle=modern dark slate includetitlebar hidebevels
WizardSizePercent=120,120
WizardImageFile={#BrandingMarkPath}
WizardSmallImageFile={#BrandingMarkPath}
WizardImageBackColor=#11100F
WizardSmallImageBackColor=#1B1A18
WizardImageStretch=yes
WizardKeepAspectRatio=yes
UninstallDisplayIcon={app}\HaizFlow.exe
UninstallDisplayName={#AppName}
CloseApplications=yes
CloseApplicationsFilter=HaizFlow.exe
RestartApplications=no
RestartIfNeededByRun=no
SetupLogging=yes

[Files]
; Release eligibility guarantees SourceDir has no root runtime directory.
; Do not use an Excludes wildcard here: "runtime\*" also matches dependency
; folders such as _internal\torch\_inductor\runtime and corrupts the install.
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; Every HaizFlow-owned mutable path is below this directory. Inno must not
; remove it unless the user explicitly requests data deletion at uninstall.
Name: "{app}\runtime"; Flags: uninsneveruninstall

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
var
  DeleteRuntimeOnUninstall: Boolean;
  CompatibilityPage: TWizardPage;
  StorageValueLabel: TNewStaticText;

function RoundedUpGiB(const Bytes: Int64): String; forward;

procedure AddRequirementRow(
  Page: TWizardPage;
  const Heading: String;
  const Detail: String;
  Top: Integer
);
var
  HeadingLabel: TNewStaticText;
  DetailLabel: TNewStaticText;
begin
  HeadingLabel := TNewStaticText.Create(Page);
  HeadingLabel.Parent := Page.Surface;
  HeadingLabel.Left := ScaleX(0);
  HeadingLabel.Top := ScaleY(Top);
  HeadingLabel.Width := Page.SurfaceWidth;
  HeadingLabel.AutoSize := False;
  HeadingLabel.Height := ScaleY(20);
  HeadingLabel.Font.Style := [fsBold];
  HeadingLabel.Caption := Heading;

  DetailLabel := TNewStaticText.Create(Page);
  DetailLabel.Parent := Page.Surface;
  DetailLabel.Left := ScaleX(0);
  DetailLabel.Top := ScaleY(Top + 21);
  DetailLabel.Width := Page.SurfaceWidth;
  DetailLabel.AutoSize := False;
  DetailLabel.Height := ScaleY(32);
  DetailLabel.WordWrap := True;
  DetailLabel.Caption := Detail;
end;

procedure SupportLinkClick(Sender: TObject);
var
  ErrorCode: Integer;
begin
  ShellExec('open', '{#AppUrl}', '', '', SW_SHOWNORMAL, ewNoWait, ErrorCode);
end;

procedure InitializeWizard;
var
  IntroLabel: TNewStaticText;
  SupportLink: TNewStaticText;
begin
  WizardForm.Caption := 'HaizFlow Setup';
  WizardForm.WelcomeLabel1.Caption := 'Install HaizFlow';
  WizardForm.WelcomeLabel2.Caption :=
    'Set up the local-first video workspace on this computer.' + #13#10 + #13#10 +
    'The application is installed now. Verified AI models are downloaded on first launch.';
  WizardForm.FinishedHeadingLabel.Caption := 'HaizFlow is ready';
  WizardForm.FinishedLabel.Caption :=
    'Installation completed. Launch HaizFlow to select CPU or GPU processing and download the required models.';

  CompatibilityPage := CreateCustomPage(
    wpSelectDir,
    'System requirements',
    'Review the runtime requirements before installation.'
  );

  IntroLabel := TNewStaticText.Create(CompatibilityPage);
  IntroLabel.Parent := CompatibilityPage.Surface;
  IntroLabel.Left := ScaleX(0);
  IntroLabel.Top := ScaleY(0);
  IntroLabel.Width := CompatibilityPage.SurfaceWidth;
  IntroLabel.AutoSize := False;
  IntroLabel.Height := ScaleY(38);
  IntroLabel.WordWrap := True;
  IntroLabel.Caption :=
    'Core processing runs locally. An internet connection is required for the first model download, URL imports and online voices.';

  AddRequirementRow(
    CompatibilityPage,
    'Windows',
    'Windows 10 version 1809 or later, or Windows 11, on a 64-bit PC.',
    52
  );
  AddRequirementRow(
    CompatibilityPage,
    'Processor and memory',
    'CPU mode works without an NVIDIA GPU. 8 GB RAM is the practical minimum; 16 GB or more is recommended.',
    110
  );
  AddRequirementRow(
    CompatibilityPage,
    'Graphics',
    'An NVIDIA GPU is optional. HaizFlow falls back to CPU processing when CUDA is unavailable or unsupported.',
    168
  );

  StorageValueLabel := TNewStaticText.Create(CompatibilityPage);
  StorageValueLabel.Parent := CompatibilityPage.Surface;
  StorageValueLabel.Left := ScaleX(0);
  StorageValueLabel.Top := ScaleY(226);
  StorageValueLabel.Width := CompatibilityPage.SurfaceWidth;
  StorageValueLabel.AutoSize := False;
  StorageValueLabel.Height := ScaleY(48);
  StorageValueLabel.WordWrap := True;
  StorageValueLabel.Font.Style := [fsBold];
  StorageValueLabel.Caption :=
    'Storage: at least ' + RoundedUpGiB({#RequiredFreshBytes}) + ' GiB free for the application, models and working space.';

  SupportLink := TNewStaticText.Create(CompatibilityPage);
  SupportLink.Parent := CompatibilityPage.Surface;
  SupportLink.Left := ScaleX(0);
  SupportLink.Top := ScaleY(286);
  SupportLink.AutoSize := True;
  SupportLink.Cursor := crHand;
  SupportLink.Font.Style := [fsUnderline];
  SupportLink.Caption := 'Source, releases and support';
  SupportLink.OnClick := @SupportLinkClick;
end;

function IsDriveRoot(const Path: String): Boolean;
begin
  Result :=
    CompareText(
      AddBackslash(ExpandFileName(Path)),
      AddBackslash(ExtractFileDrive(ExpandFileName(Path)))
    ) = 0;
end;

function IsUpgradeTarget(const Path: String): Boolean;
begin
  { A retained runtime directory by itself is not an installed immutable
    payload. Treat it as a fresh install so disk preflight is conservative.
    Do not trust an unrelated folder merely because it contains a file with
    the executable name: require release metadata and the PyInstaller payload. }
  Result :=
    FileExists(AddBackslash(Path) + 'HaizFlow.exe') and
    FileExists(AddBackslash(Path) + 'BUILD-INFO.json') and
    DirExists(AddBackslash(Path) + '_internal');
end;

function FreshTargetHasConflictingContent(const Path: String): Boolean;
var
  FindRec: TFindRec;
  EntryName: String;
begin
  Result := False;
  if not FindFirst(AddBackslash(Path) + '*', FindRec) then
    exit;
  try
    repeat
      EntryName := FindRec.Name;
      if
        (EntryName <> '.') and
        (EntryName <> '..') and
        not (
          ((FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0) and
          (CompareText(EntryName, 'runtime') = 0)
        )
      then
        Result := True;
    until Result or (not FindNext(FindRec));
  finally
    FindClose(FindRec);
  end;
end;

function RoundedUpGiB(const Bytes: Int64): String;
begin
  Result := IntToStr((Bytes + 1073741823) div 1073741824);
end;

function RoundedDownGiB(const Bytes: Int64): String;
begin
  Result := IntToStr(Bytes div 1073741824);
end;

procedure UpdateCompatibilityStorage;
var
  FreeBytes: Int64;
  TotalBytes: Int64;
  RequiredBytes: Int64;
begin
  if IsUpgradeTarget(WizardDirValue) then
    RequiredBytes := {#RequiredFreeBytes}
  else
    RequiredBytes := {#RequiredFreshBytes};
  if GetSpaceOnDisk64(WizardDirValue, FreeBytes, TotalBytes) then
    StorageValueLabel.Caption :=
      'Storage: ' + RoundedDownGiB(FreeBytes) + ' GiB available; ' +
      RoundedUpGiB(RequiredBytes) + ' GiB required for a safe install and first model download.'
  else
    StorageValueLabel.Caption :=
      'Storage: ' + RoundedUpGiB(RequiredBytes) + ' GiB is required. Setup will verify the selected folder before copying files.';
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CompatibilityPage <> nil) and (CurPageID = CompatibilityPage.ID) then
    UpdateCompatibilityStorage;
end;

function ValidateInstallTarget: String;
var
  FreeBytes: Int64;
  TotalBytes: Int64;
  RequiredBytes: Int64;
  ProbePath: String;
begin
  Result := '';

  if IsDriveRoot(WizardDirValue) then
  begin
    Result := 'Choose an application folder such as C:\HaizFlow or D:\HaizFlow, not the root of a drive.';
    exit;
  end;

  if not ForceDirectories(WizardDirValue) then
  begin
    Result := 'Could not create the selected installation folder. Choose a folder that your account can write to.';
    exit;
  end;

  if (not IsUpgradeTarget(WizardDirValue)) and FreshTargetHasConflictingContent(WizardDirValue) then
  begin
    Result :=
      'The selected folder is not empty and is not an existing HaizFlow installation.' + #13#10 + #13#10 +
      'Choose an empty folder or create a new HaizFlow subfolder. A folder containing only retained ' +
      'HaizFlow runtime data is also safe to reuse.';
    exit;
  end;

  { The application stores mutable runtime data below the selected install
    directory. Reject a folder that will not remain writable after setup exits. }
  ProbePath := AddBackslash(WizardDirValue) + '.haizflow-installer-write-probe.tmp';
  if FileExists(ProbePath) or
     (not SaveStringToFile(ProbePath, 'write probe', False)) then
  begin
    Result :=
      'The selected installation folder is not writable by your Windows account.' + #13#10 + #13#10 +
      'Choose another folder, for example C:\HaizFlow or D:\HaizFlow.';
    exit;
  end;
  DeleteFile(ProbePath);

  if IsUpgradeTarget(WizardDirValue) then
    RequiredBytes := {#RequiredFreeBytes}
  else
    RequiredBytes := {#RequiredFreshBytes};
  if not GetSpaceOnDisk64(WizardDirValue, FreeBytes, TotalBytes) then
  begin
    Result := 'Could not check free space for the selected installation folder.';
    exit;
  end;
  if FreeBytes < RequiredBytes then
    Result :=
      'The selected drive does not have enough free space for a safe install or upgrade.' + #13#10 + #13#10 +
      'Required: ' + RoundedUpGiB(RequiredBytes) + ' GiB' + #13#10 +
      'Available: ' + RoundedDownGiB(FreeBytes) + ' GiB';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  ValidationError: String;
begin
  Result := True;
  if CurPageID <> wpSelectDir then
    exit;
  ValidationError := ValidateInstallTarget;
  if ValidationError <> '' then
  begin
    MsgBox(ValidationError, mbError, MB_OK);
    Result := False;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  { DisableDirPage=auto hides the directory page during an upgrade, so repeat
    containment, writeability and disk checks at the mandatory install gate. }
  Result := ValidateInstallTarget;
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  DeleteRuntimeOnUninstall := False;
  if not UninstallSilent then
    DeleteRuntimeOnUninstall :=
      MsgBox(
        'Do you also want to permanently delete HaizFlow runtime data?' + #13#10 + #13#10 +
        'This includes settings, logs, caches, downloaded models and the local project index. ' +
        'Project folders stored elsewhere are not deleted.' + #13#10 + #13#10 +
        'Choose No to keep the data for a future reinstall.',
        mbConfirmation,
        MB_YESNO or MB_DEFBUTTON2
      ) = IDYES;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usUninstall) and DeleteRuntimeOnUninstall then
    DelTree(ExpandConstant('{app}\runtime'), True, True, True);
  if (CurUninstallStep = usPostUninstall) and DeleteRuntimeOnUninstall then
    RemoveDir(ExpandConstant('{app}'));
end;

[Messages]
SelectDirLabel3=Choose where to install HaizFlow. The application and runtime data, including models downloaded on first launch, will stay below this folder. Existing runtime data is preserved during upgrades.
