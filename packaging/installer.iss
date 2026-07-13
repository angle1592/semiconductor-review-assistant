#define MyAppName "半导体复习台"
#define MyAppVersion "0.1.0-beta"
#define MyAppPublisher "angle1592"
#define MyAppExeName "SemiconductorReview.exe"

[Setup]
AppId={{A74E3B83-222F-4C35-B27C-7238356FE5CD}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\SemiconductorReview
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release
OutputBaseFilename=半导体复习台-0.1.0-beta-Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion=0.1.0.0
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion=0.1.0.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\release\staging\SemiconductorReview\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
procedure StopInstalledApplication();
var
  ResultCode: Integer;
begin
  if FileExists(ExpandConstant('{app}\{#MyAppExeName}')) then
  begin
    Exec(ExpandConstant('{app}\{#MyAppExeName}'), '--shutdown', '', SW_HIDE,
      ewWaitUntilTerminated, ResultCode);
    Sleep(1200);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopInstalledApplication();
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usUninstall then
    StopInstalledApplication();

  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\SemiconductorReview');
    if DirExists(DataDir) and
       (MsgBox('是否同时永久删除本机课程、课件、答案、复习历史、备份和日志？' + #13#10 +
         '默认建议保留，方便以后重装或升级。', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES) then
      DelTree(DataDir, True, True, True);
  end;
end;
