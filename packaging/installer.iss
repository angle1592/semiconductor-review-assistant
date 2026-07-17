#define MyAppName "拾要"
#define MyAppVersion "0.2.2-beta"
#define MyAppPublisher "angle1592"
#define MyAppExeName "Shiyao.exe"

[Setup]
AppId={{A74E3B83-222F-4C35-B27C-7238356FE5CD}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Shiyao
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.17763
OutputDir=..\release
OutputBaseFilename=Shiyao-0.2.2-beta-Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion=0.2.2.0
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion=0.2.2.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\release\staging\Shiyao\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
function StopInstalledApplication(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  if FileExists(ExpandConstant('{app}\{#MyAppExeName}')) then
    Result := Exec(ExpandConstant('{app}\{#MyAppExeName}'), '--shutdown', '', SW_HIDE,
      ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  if StopInstalledApplication() then
    Result := ''
  else
    Result := '无法安全停止正在运行的拾要。请稍后重试。';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usUninstall then
    if not StopInstalledApplication() then
      RaiseException('无法安全停止正在运行的拾要。');

  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\Shiyao');
    if DirExists(DataDir) and
       (SuppressibleMsgBox('是否同时永久删除本机资料、重点、题目、复习内容、掌握记录、备份和日志？' + #13#10 +
         '默认建议保留，方便以后重装或升级。', mbConfirmation, MB_YESNO, IDNO) = IDYES) then
      DelTree(DataDir, True, True, True);
  end;
end;
