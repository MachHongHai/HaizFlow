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
#ifndef RecommendedFreeBytes
  #error RecommendedFreeBytes must be calculated from the verified artifact.
#endif
#ifndef RecommendedFreshBytes
  #error RecommendedFreshBytes must be calculated from the verified artifact.
#endif
#ifndef ArtifactBytes
  #error ArtifactBytes must be calculated from the verified artifact.
#endif
#ifndef SetupIconPath
  #error SetupIconPath must point to the generated multi-resolution .ico file.
#endif
#ifndef BrandingMarkPath
  #error BrandingMarkPath must point to the installer branding PNG.
#endif
#ifndef SidebarArtworkPath
  #error SidebarArtworkPath must point to installer-sized artwork.
#endif
#ifndef HeaderArtworkPath
  #error HeaderArtworkPath must point to installer-sized artwork.
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
#ifndef VersionedLayout
  #define VersionedLayout "0"
#endif
#ifndef EngineeringBuild
  #define EngineeringBuild "0"
#endif
#ifndef SignedBuild
  #define SignedBuild "0"
#endif

[Setup]
#ifdef SmokeAppId
  #if EngineeringBuild != "1"
    #error SmokeAppId is engineering-only.
  #endif
AppId={#SmokeAppId}
#elif EngineeringBuild == "1"
AppId={{2E512B7B-B9A6-4FB9-A306-C836B1DA102A}
#else
AppId={{799AE20D-E7A5-4D79-96DE-708E161BF32A}
#endif
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
; The active approved license is displayed here, never draft application terms.
Compression=lzma2/ultra64
SolidCompression=yes
DefaultDialogFontName=Segoe UI
WizardStyle=modern dark slate includetitlebar hidebevels
WizardSizePercent=120,120
WizardImageFile={#SidebarArtworkPath}
WizardSmallImageFile={#HeaderArtworkPath}
WizardImageBackColor=#11100F
WizardSmallImageBackColor=#1B1A18
WizardImageStretch=yes
WizardKeepAspectRatio=yes
LanguageDetectionMethod=none
ShowLanguageDialog=yes
UninstallDisplayIcon={app}\HaizFlow.exe
UninstallDisplayName={#AppName}
CloseApplications=yes
CloseApplicationsFilter=HaizFlow.exe,HaizFlowCore.exe,HaizFlowUpdater.exe
RestartApplications=no
RestartIfNeededByRun=no
SetupLogging=yes
#if SignedBuild == "1"
SignTool=haizflow_release_sign
SignedUninstaller=yes
SignToolRunMinimized=yes
#else
SignedUninstaller=no
#endif

[Files]
; Release eligibility guarantees SourceDir has no root runtime directory.
; Do not use an Excludes wildcard here: "runtime\*" also matches dependency
; folders such as _internal\torch\_inductor\runtime and corrupts the install.
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Languages]
Name: "vietnamese"; MessagesFile: "compiler:Default.isl,vendor\Vietnamese.isl"; InfoBeforeFile: "information.vi.txt"
Name: "english"; MessagesFile: "compiler:Default.isl,vendor\English.isl"; InfoBeforeFile: "information.en.txt"

[Dirs]
; Every HaizFlow-owned mutable path is below this directory. Inno must not
; remove it unless the user explicitly requests data deletion at uninstall.
Name: "{app}\runtime"; Flags: uninsneveruninstall

[InstallDelete]
#if VersionedLayout == "1"
; Remove only this installer-owned immutable version after the mandatory
; pre-copy lock/reparse gate; old rollback versions and runtime remain intact.
Type: filesandordirs; Name: "{app}\versions\{#AppVersion}"
#endif
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
Type: filesandordirs; Name: "{app}\legal"
Type: files; Name: "{app}\FFMPEG-MANIFEST.json"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\HaizFlow.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\HaizFlow.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopShortcut}"; GroupDescription: "{cm:Shortcuts}"; Flags: unchecked

[UninstallDelete]
Type: files; Name: "{app}\offline-resources.ini"
#if VersionedLayout == "1"
Type: files; Name: "{app}\update-state\launcher.lock"
Type: files; Name: "{app}\update-state\update.lock"
Type: files; Name: "{app}\update-state\updater.lock"
Type: dirifempty; Name: "{app}\update-state"
Type: dirifempty; Name: "{app}\versions"
#endif

[Run]
Filename: "{app}\HaizFlow.exe"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[Code]
var
  DeleteRuntimeOnUninstall: Boolean;
  CompatibilityPage: TWizardPage;
  StorageValueLabel: TNewStaticText;
  StorageSpaceLabel: TNewStaticText;

function UiText(const Vietnamese, English: String): String;
begin
  if ActiveLanguage = 'vietnamese' then Result := Vietnamese else Result := English;
end;

function RoundedUpGiB(const Bytes: Int64): String; forward;
function RoundedUpTenthGiB(const Bytes: Int64): String; forward;
function GetFileAttributesW(const Name: String): Cardinal;
  external 'GetFileAttributesW@kernel32.dll stdcall';

function ContainsReparsePoint(const Path: String): Boolean;
var
  FindRec: TFindRec;
  Attributes: Cardinal;
begin
  Result := False;
  Attributes := GetFileAttributesW(Path);
  if Attributes = $FFFFFFFF then exit;
  if (Attributes and $400) <> 0 then begin Result := True; exit; end;
  if (Attributes and FILE_ATTRIBUTE_DIRECTORY) = 0 then exit;
  if not FindFirst(AddBackslash(Path) + '*', FindRec) then exit;
  try
    repeat
      if (FindRec.Name <> '.') and (FindRec.Name <> '..') then
        Result := ContainsReparsePoint(AddBackslash(Path) + FindRec.Name);
    until Result or (not FindNext(FindRec));
  finally
    FindClose(FindRec);
  end;
end;

function AncestorContainsReparsePoint(const Path: String): Boolean;
var
  CurrentPath: String;
  ParentPath: String;
  Attributes: Cardinal;
begin
  Result := False;
  CurrentPath := RemoveBackslashUnlessRoot(ExpandFileName(Path));
  repeat
    Attributes := GetFileAttributesW(CurrentPath);
    if (Attributes <> $FFFFFFFF) and ((Attributes and $400) <> 0) then
    begin Result := True; exit; end;
    ParentPath := ExtractFileDir(CurrentPath);
    if CompareText(ParentPath, CurrentPath) = 0 then exit;
    CurrentPath := ParentPath;
  until CurrentPath = '';
end;

function UnsafePayload(const Path: String): Boolean;
begin
  Result := AncestorContainsReparsePoint(Path) or
    ContainsReparsePoint(AddBackslash(Path) + '_internal') or
    ContainsReparsePoint(AddBackslash(Path) + 'versions') or
    ContainsReparsePoint(AddBackslash(Path) + 'updater') or
    ContainsReparsePoint(AddBackslash(Path) + 'licenses') or
    ContainsReparsePoint(AddBackslash(Path) + 'sources') or
    ContainsReparsePoint(AddBackslash(Path) + 'legal') or
    ContainsReparsePoint(AddBackslash(Path) + 'update-state') or
    ContainsReparsePoint(AddBackslash(Path) + 'HaizFlow.exe');
end;

function AddRequirementRow(
  Page: TWizardPage;
  const Heading: String;
  const Detail: String;
  Top: Integer
): Integer;
var
  HeadingLabel: TNewStaticText;
  DetailLabel: TNewStaticText;
begin
  HeadingLabel := TNewStaticText.Create(Page);
  HeadingLabel.Parent := Page.Surface;
  HeadingLabel.Left := ScaleX(0);
  HeadingLabel.Top := Top;
  HeadingLabel.Width := ScaleX(122);
  HeadingLabel.AutoSize := False;
  HeadingLabel.Height := ScaleY(20);
  HeadingLabel.Font.Style := [fsBold];
  HeadingLabel.Caption := Heading;
  HeadingLabel.WordWrap := True;
  HeadingLabel.AdjustHeight;

  DetailLabel := TNewStaticText.Create(Page);
  DetailLabel.Parent := Page.Surface;
  DetailLabel.Left := ScaleX(136);
  DetailLabel.Top := Top;
  DetailLabel.Width := Page.SurfaceWidth - ScaleX(136);
  DetailLabel.AutoSize := False;
  DetailLabel.Height := ScaleY(40);
  DetailLabel.WordWrap := True;
  DetailLabel.Caption := Detail;
  DetailLabel.AdjustHeight;
  Result := Top + DetailLabel.Height + ScaleY(14);
  if HeadingLabel.Height > DetailLabel.Height then
    Result := Top + HeadingLabel.Height + ScaleY(14);
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
  StorageHeading: TNewStaticText;
  SupportLink: TNewStaticText;
  ContentTop: Integer;
begin
  WizardForm.Caption := UiText('Cài đặt HaizFlow', 'HaizFlow Setup');
  WizardForm.WelcomeLabel1.Caption := UiText('Cài đặt HaizFlow', 'Install HaizFlow');
  WizardForm.WelcomeLabel2.Caption :=
    UiText('Chỉnh video, dịch phụ đề và đăng mạng xã hội.', 'Edit videos, translate subtitles and publish to social media.') + #13#10 + #13#10 +
    UiText('Chọn thư mục cài ứng dụng. Các model được cài riêng trong Cài đặt → Gói tài nguyên.', 'Choose where to install the application. Install models separately in Settings → Resource packs.');
  WizardForm.FinishedHeadingLabel.Caption := UiText('Cài đặt hoàn tất', 'Installation complete');
  WizardForm.FinishedLabel.Caption :=
    UiText('Mở HaizFlow để bắt đầu. Bạn có thể cài các gói tài nguyên cần dùng trong Cài đặt.', 'Installation completed. Launch HaizFlow, then install only the resource packs you need.');

  CompatibilityPage := CreateCustomPage(
    wpSelectDir,
    UiText('Cấu hình và dung lượng', 'System requirements'),
    UiText('Yêu cầu chạy model và dung lượng tại thư mục đã chọn.', 'Model requirements and storage at the selected location.')
  );

  IntroLabel := TNewStaticText.Create(CompatibilityPage);
  IntroLabel.Parent := CompatibilityPage.Surface;
  IntroLabel.Left := ScaleX(0);
  IntroLabel.Top := ScaleY(250);
  IntroLabel.Width := CompatibilityPage.SurfaceWidth;
  IntroLabel.AutoSize := False;
  IntroLabel.Height := ScaleY(40);
  IntroLabel.WordWrap := True;
  IntroLabel.Caption :=
    UiText('Dung lượng trên chưa gồm môi trường xử lý, model và video. Bạn có thể chọn ổ lưu tài nguyên riêng trong ứng dụng.', 'Storage above excludes processing runtimes, models and videos. Resource packs can be stored on a separate drive.');

  ContentTop := AddRequirementRow(
    CompatibilityPage,
    'Windows',
    UiText('Windows 10 (1809 trở lên) hoặc Windows 11, 64-bit.', 'Windows 10 (1809 or later) or Windows 11, 64-bit.'),
    0
  );
  ContentTop := AddRequirementRow(
    CompatibilityPage,
    UiText('Bộ nhớ', 'Memory'),
    UiText('Tối thiểu 16 GB RAM để chạy model. Chế độ CPU không cần GPU NVIDIA.', '16 GB RAM minimum for models. CPU mode works without an NVIDIA GPU.'),
    ContentTop
  );
  ContentTop := AddRequirementRow(
    CompatibilityPage,
    UiText('GPU tùy chọn', 'Optional GPU'),
    UiText('Model GPU cần NVIDIA, CUDA và VRAM tương thích. Không bắt buộc khi dùng model CPU.', 'GPU models require compatible NVIDIA hardware, CUDA and VRAM. Not required for CPU models.'),
    ContentTop
  );

  StorageValueLabel := TNewStaticText.Create(CompatibilityPage);
  StorageValueLabel.Parent := CompatibilityPage.Surface;
  StorageValueLabel.Left := ScaleX(0);
  StorageValueLabel.Top := ContentTop + ScaleY(29);
  StorageValueLabel.Width := CompatibilityPage.SurfaceWidth;
  StorageValueLabel.AutoSize := False;
  StorageValueLabel.Height := ScaleY(24);
  StorageValueLabel.WordWrap := True;
  StorageValueLabel.Font.Style := [];
  StorageValueLabel.Caption :=
    UiText('Ứng dụng: ', 'Core files: ') + IntToStr(({#ArtifactBytes} + 1048575) div 1048576) + ' MiB';
  StorageValueLabel.AdjustHeight;

  StorageHeading := TNewStaticText.Create(CompatibilityPage);
  StorageHeading.Parent := CompatibilityPage.Surface;
  StorageHeading.Top := ContentTop + ScaleY(4);
  StorageHeading.AutoSize := True;
  StorageHeading.Font.Style := [fsBold];
  StorageHeading.Caption := UiText('Dung lượng cài đặt', 'Installation storage');

  StorageSpaceLabel := TNewStaticText.Create(CompatibilityPage);
  StorageSpaceLabel.Parent := CompatibilityPage.Surface;
  StorageSpaceLabel.Top := StorageValueLabel.Top + StorageValueLabel.Height + ScaleY(6);
  StorageSpaceLabel.Width := CompatibilityPage.SurfaceWidth;
  StorageSpaceLabel.AutoSize := False;
  StorageSpaceLabel.Height := ScaleY(32);
  StorageSpaceLabel.WordWrap := True;
  IntroLabel.Top := StorageSpaceLabel.Top + StorageSpaceLabel.Height + ScaleY(12);
  IntroLabel.AdjustHeight;

  SupportLink := TNewStaticText.Create(CompatibilityPage);
  SupportLink.Parent := CompatibilityPage.Surface;
  SupportLink.Left := ScaleX(0);
  SupportLink.Top := IntroLabel.Top + IntroLabel.Height + ScaleY(12);
  SupportLink.AutoSize := True;
  SupportLink.Cursor := crHand;
  SupportLink.Font.Style := [fsUnderline];
  SupportLink.Caption := UiText('Hỗ trợ và bản phát hành', 'Support and releases');
  SupportLink.OnClick := @SupportLinkClick;
  Log(Format('Compatibility layout: content bottom %d, surface height %d', [SupportLink.Top + SupportLink.Height, CompatibilityPage.SurfaceHeight]));
  if SupportLink.Top + SupportLink.Height > CompatibilityPage.SurfaceHeight then
    RaiseException('The system requirements page does not fit the installer window.');
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

function RoundedUpTenthGiB(const Bytes: Int64): String;
var
  Tenths: Int64;
begin
  Tenths := (Bytes * 10 + 1073741823) div 1073741824;
  Result := IntToStr(Tenths div 10) + '.' + IntToStr(Tenths mod 10);
end;

function RoundedDownTenthGiB(const Bytes: Int64): String;
var
  Tenths: Int64;
begin
  Tenths := Bytes * 10 div 1073741824;
  Result := IntToStr(Tenths div 10) + '.' + IntToStr(Tenths mod 10);
end;

procedure UpdateCompatibilityStorage;
var
  FreeBytes: Int64;
  TotalBytes: Int64;
  RequiredBytes: Int64;
  RecommendedBytes: Int64;
begin
  if IsUpgradeTarget(WizardDirValue) then
  begin
    RequiredBytes := {#RequiredFreeBytes};
    RecommendedBytes := {#RecommendedFreeBytes};
  end
  else
  begin
    RequiredBytes := {#RequiredFreshBytes};
    RecommendedBytes := {#RecommendedFreshBytes};
  end;
  if GetSpaceOnDisk64(WizardDirValue, FreeBytes, TotalBytes) then
    StorageSpaceLabel.Caption :=
      UiText('Còn trống: ', 'Available: ') + RoundedDownTenthGiB(FreeBytes) + UiText(' GiB  ·  Cần tối thiểu: ', ' GiB  ·  Required: ') +
      RoundedUpTenthGiB(RequiredBytes) + ' GiB'
  else
    StorageSpaceLabel.Caption :=
      UiText('Cần tối thiểu: ', 'Required: ') + RoundedUpTenthGiB(RequiredBytes) +
      UiText(' GiB. Không đọc được dung lượng trống của ổ đích.', ' GiB. Free space on this drive could not be read.');
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CompatibilityPage <> nil) and (CurPageID = CompatibilityPage.ID) then
    UpdateCompatibilityStorage;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ExitCode: Integer;
  OfflinePath: String;
  OfflineLines: TArrayOfString;
begin
#if VersionedLayout == "1"
  if CurStep = ssPostInstall then
    if (not Exec(ExpandConstant('{app}\HaizFlow.exe'), '--initialize {#AppVersion}',
      ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ExitCode)) or (ExitCode <> 0) then
      RaiseException(UiText('Không thể khởi tạo ứng dụng đã xác minh. Dữ liệu hiện có được giữ nguyên.', 'Could not activate the verified Core. Existing runtime data is preserved.'));
#endif
#if EngineeringBuild == "1"
  if CurStep = ssPostInstall then
  begin
#ifdef SmokeResourceDirectory
    OfflinePath := '{#SmokeResourceDirectory}';
#else
    OfflinePath := ExpandConstant('{src}\offline-resources');
#endif
    if DirExists(OfflinePath) and not ContainsReparsePoint(OfflinePath) then
    begin
      SetArrayLength(OfflineLines, 2);
      OfflineLines[0] := '[resources]';
      OfflineLines[1] := 'path=' + OfflinePath;
      if not SaveStringsToUTF8File(ExpandConstant('{app}\offline-resources.ini'), OfflineLines, False) then
        RaiseException(UiText('Không thể ghi vị trí gói tài nguyên đi kèm. Dữ liệu hiện có được giữ nguyên.', 'Could not register companion resource packs. Existing runtime data is preserved.'));
    end;
  end;
#endif
end;

function ValidateInstallTarget: String;
var
  FreeBytes: Int64;
  TotalBytes: Int64;
  RequiredBytes: Int64;
  ProbePath: String;
  ExitCode: Integer;
begin
  Result := '';

  if UnsafePayload(WizardDirValue) then
  begin
    Result := UiText('Thư mục ứng dụng chứa liên kết hoặc junction. Hãy chọn thư mục cài khác.', 'The application payload contains a link or junction. Choose a new installation folder.');
    exit;
  end;

  if IsDriveRoot(WizardDirValue) then
  begin
    Result := UiText('Chọn thư mục như C:\HaizFlow hoặc D:\HaizFlow, không chọn gốc ổ đĩa.', 'Choose an application folder such as C:\HaizFlow or D:\HaizFlow, not the root of a drive.');
    exit;
  end;

  if not ForceDirectories(WizardDirValue) then
  begin
    Result := UiText('Không thể tạo thư mục cài đặt. Hãy chọn nơi tài khoản Windows của bạn có quyền ghi.', 'Could not create the selected installation folder. Choose a folder that your account can write to.');
    exit;
  end;

  if (not IsUpgradeTarget(WizardDirValue)) and FreshTargetHasConflictingContent(WizardDirValue) then
  begin
    Result :=
      UiText('Thư mục đã có nội dung khác, không phải bản HaizFlow hiện có.', 'The selected folder is not empty and is not an existing HaizFlow installation.') + #13#10 + #13#10 +
      UiText('Chọn thư mục trống hoặc tạo thư mục HaizFlow mới. Thư mục chỉ có ', 'Choose an empty folder or create a new HaizFlow subfolder. A folder containing only retained ') +
      UiText('dữ liệu runtime được giữ lại của HaizFlow cũng có thể dùng để cài lại.', 'HaizFlow runtime data is also safe to reuse.');
    exit;
  end;

#if VersionedLayout == "1"
  if IsUpgradeTarget(WizardDirValue) then
  begin
    if not FileExists(AddBackslash(WizardDirValue) + 'update-layout.json') then
    begin
      Result := UiText('Bản cũ dùng cấu trúc khác. Sao lưu runtime rồi cài bản này vào thư mục mới.', 'This older installation uses a different layout. Back up runtime and install this version in a new folder.');
      exit;
    end;
    if (not Exec(AddBackslash(WizardDirValue) + 'HaizFlow.exe', '--check-install {#AppVersion}',
      WizardDirValue, SW_HIDE, ewWaitUntilTerminated, ExitCode)) or (ExitCode <> 0) then
    begin
      Result := UiText('Đóng HaizFlow và hoàn tất cập nhật đang chờ. Không thể cài đè phiên bản thấp hơn.', 'Close HaizFlow and finish any pending update. A newer installation cannot be downgraded.');
      exit;
    end;
  end;
#endif

  { The application stores mutable runtime data below the selected install
    directory. Reject a folder that will not remain writable after setup exits. }
  ProbePath := AddBackslash(WizardDirValue) + '.haizflow-installer-write-probe.tmp';
  if FileExists(ProbePath) or
     (not SaveStringToFile(ProbePath, 'write probe', False)) then
  begin
    Result :=
      UiText('Tài khoản Windows không có quyền ghi vào thư mục đã chọn.', 'The selected installation folder is not writable by your Windows account.') + #13#10 + #13#10 +
      UiText('Chọn thư mục khác, ví dụ C:\HaizFlow hoặc D:\HaizFlow.', 'Choose another folder, for example C:\HaizFlow or D:\HaizFlow.');
    exit;
  end;
  DeleteFile(ProbePath);

  if IsUpgradeTarget(WizardDirValue) then
    RequiredBytes := {#RequiredFreeBytes}
  else
    RequiredBytes := {#RequiredFreshBytes};
  if not GetSpaceOnDisk64(WizardDirValue, FreeBytes, TotalBytes) then
  begin
    Result := UiText('Không thể kiểm tra dung lượng trống tại thư mục đã chọn.', 'Could not check free space for the selected installation folder.');
    exit;
  end;
  if FreeBytes < RequiredBytes then
    Result :=
      UiText('Ổ đĩa không đủ dung lượng trống để cài hoặc nâng cấp an toàn.', 'The selected drive does not have enough free space for a safe install or upgrade.') + #13#10 + #13#10 +
      UiText('Cần: ', 'Required: ') + RoundedUpGiB(RequiredBytes) + ' GiB' + #13#10 +
      UiText('Còn trống: ', 'Available: ') + RoundedDownGiB(FreeBytes) + ' GiB';
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
var
  ExitCode: Integer;
begin
  Result := True;
  DeleteRuntimeOnUninstall := False;
  if UnsafePayload(ExpandConstant('{app}')) then
  begin
    Result := False;
    MsgBox(UiText('Thư mục cài chứa liên kết hoặc junction. Chưa có file nào bị xóa.', 'Installation contains a link or junction. No files were removed.'), mbError, MB_OK);
    exit;
  end;
  if not UninstallSilent then
    DeleteRuntimeOnUninstall :=
      MsgBox(
        UiText('Bạn có muốn xóa vĩnh viễn dữ liệu runtime của HaizFlow không?', 'Do you also want to permanently delete HaizFlow runtime data?') + #13#10 + #13#10 +
        UiText('Gồm cài đặt, nhật ký, cache, model đã tải và chỉ mục dự án. ', 'This includes settings, logs, caches, downloaded models and the local project index. ') +
        UiText('Không xóa các thư mục dự án lưu ở nơi khác.', 'Project folders stored elsewhere are not deleted.') + #13#10 + #13#10 +
        UiText('Chọn Không để giữ dữ liệu khi cài lại.', 'Choose No to keep the data for a future reinstall.'),
        mbConfirmation,
        MB_YESNO or MB_DEFBUTTON2
      ) = IDYES;
  if DeleteRuntimeOnUninstall and ContainsReparsePoint(ExpandConstant('{app}\runtime')) then
  begin
    MsgBox(UiText('Dữ liệu runtime chứa liên kết hoặc junction. Dữ liệu sẽ được giữ nguyên.', 'Runtime data contains a link or junction. Data will be preserved.'), mbError, MB_OK);
    DeleteRuntimeOnUninstall := False;
  end;
#if VersionedLayout == "1"
  Result := Exec(ExpandConstant('{app}\HaizFlow.exe'), '--uninstall-cores',
    ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ExitCode) and (ExitCode = 0);
  if not Result then
    MsgBox(UiText('Không thể gỡ ứng dụng an toàn. Đóng HaizFlow hoặc sửa bản cài trước. Dữ liệu được giữ nguyên.', 'Core could not be safely removed. Close HaizFlow or repair the installation first. Runtime data is preserved.'), mbError, MB_OK);
#endif
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usUninstall) and DeleteRuntimeOnUninstall then
    DelTree(ExpandConstant('{app}\runtime'), True, True, True);
  if (CurUninstallStep = usPostUninstall) and DeleteRuntimeOnUninstall then
    RemoveDir(ExpandConstant('{app}'));
end;

[Messages]
english.SelectDirLabel3=Choose where to install HaizFlow. The Core application and resource packs you approve stay below this folder unless you move resource storage in Settings. Existing runtime data is preserved during upgrades.


vietnamese.SelectDirLabel3=Chọn nơi cài HaizFlow. Dữ liệu runtime được giữ khi nâng cấp. Có thể chuyển nơi lưu tài nguyên trong Cài đặt.
vietnamese.WizardInfoBefore=Trước khi cài đặt
english.WizardInfoBefore=Before installing
vietnamese.InfoBeforeLabel=Ứng dụng, tài nguyên và dữ liệu của bạn.
english.InfoBeforeLabel=Application, resources and your data.
vietnamese.WizardLicense=Giấy phép HaizFlow
english.WizardLicense=HaizFlow license
vietnamese.LicenseLabel3=Đọc giấy phép đầy đủ bên dưới. Đồng ý để tiếp tục cài đặt.
english.LicenseLabel3=Read the full license below. Accept it to continue installing.
vietnamese.WizardReady=Xác nhận cài đặt
english.WizardReady=Confirm installation
vietnamese.ReadyLabel1=Kiểm tra các lựa chọn trước khi cài HaizFlow.
english.ReadyLabel1=Review your choices before installing HaizFlow.

[CustomMessages]
vietnamese.DesktopShortcut=Tạo lối tắt trên màn hình
english.DesktopShortcut=Create a desktop shortcut
vietnamese.Shortcuts=Lối tắt:
english.Shortcuts=Shortcuts:
vietnamese.LaunchApp=Mở HaizFlow
english.LaunchApp=Launch HaizFlow
