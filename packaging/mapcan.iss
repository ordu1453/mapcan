; Установщик mapcan для Windows (Inno Setup 6).
;
;   iscc /DAppVersion=0.6.0 packaging\mapcan.iss
;
; Берёт сборку PyInstaller из dist\mapcan и кладёт установщик в dist\mapcan-<версия>-setup.exe.
; Ставится для текущего пользователя без прав администратора (можно выбрать «для всех»).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "mapcan"
#define AppExe "mapcan-app.exe"
#define ProgId "mapcan.yaml"

[Setup]
; AppId не менять: по нему обновление находит предыдущую установку.
AppId={{6C1E2B9A-3F4D-4E8B-9A57-0D2C8F1B7E43}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=ordu1453
AppPublisherURL=https://github.com/ordu1453/mapcan
AppSupportURL=https://github.com/ordu1453/mapcan/issues
AppUpdatesURL=https://github.com/ordu1453/mapcan/releases
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=mapcan-{#AppVersion}-setup
SetupIconFile=mapcan.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
ChangesEnvironment=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
ru.AssocYaml=Добавить mapcan в меню «Открыть с помощью» для .yaml
en.AssocYaml=Add mapcan to "Open with" for .yaml files
ru.AddPath=Добавить команду mapcan в PATH (для командной строки и CI)
en.AddPath=Add the mapcan command to PATH (for the command line and CI)
ru.Launch=Запустить mapcan
en.Launch=Launch mapcan
ru.MapFile=Карта сигналов mapcan
en.MapFile=mapcan signal map

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "assoc"; Description: "{cm:AssocYaml}"
Name: "addpath"; Description: "{cm:AddPath}"; Flags: unchecked

[Files]
Source: "..\dist\mapcan\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Старые файлы сборки (имена модулей меняются от версии к версии).
Type: filesandordirs; Name: "{app}\_internal"
; Файлы и ярлыки версий до переименования canmap → mapcan.
Type: files; Name: "{app}\canmap.exe"
Type: files; Name: "{app}\canmap-app.exe"
Type: files; Name: "{autoprograms}\canmap.lnk"
Type: files; Name: "{autodesktop}\canmap.lnk"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Ассоциации версий до переименования canmap → mapcan.
Root: HKA; Subkey: "Software\Classes\canmap.yaml"; ValueType: none; Flags: deletekey
Root: HKA; Subkey: "Software\Classes\Applications\canmap-app.exe"; ValueType: none; Flags: deletekey
Root: HKA; Subkey: "Software\Classes\.yaml\OpenWithProgids"; ValueType: none; ValueName: "canmap.yaml"; Flags: deletevalue
Root: HKA; Subkey: "Software\Classes\.yml\OpenWithProgids"; ValueType: none; ValueName: "canmap.yaml"; Flags: deletevalue
; «Открыть с помощью → mapcan» для .yaml/.yml, не перехватывая программу по умолчанию.
Root: HKA; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueData: "{cm:MapFile}"; Flags: uninsdeletekey; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\{#ProgId}\DefaultIcon"; ValueType: string; ValueData: "{app}\{#AppExe},0"; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\{#ProgId}\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.yaml\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.yml\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Flags: uninsdeletekey; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".yaml"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".yml"; ValueData: ""; Tasks: assoc

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:Launch}"; Flags: nowait postinstall skipifsilent

[Code]
{ PATH: пользовательский (HKCU) при установке для себя, системный (HKLM) — для всех. }

function PathRoot: Integer;
begin
  if IsAdminInstallMode then Result := HKEY_LOCAL_MACHINE else Result := HKEY_CURRENT_USER;
end;

function PathKey: String;
begin
  if IsAdminInstallMode then
    Result := 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'
  else
    Result := 'Environment';
end;

function PathHas(const Paths, Dir: String): Boolean;
begin
  Result := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Paths) + ';') > 0;
end;

procedure AddToPath(const Dir: String);
var
  Paths: String;
begin
  if not RegQueryStringValue(PathRoot, PathKey, 'Path', Paths) then Paths := '';
  if PathHas(Paths, Dir) then Exit;
  if (Paths <> '') and (Paths[Length(Paths)] <> ';') then Paths := Paths + ';';
  RegWriteExpandStringValue(PathRoot, PathKey, 'Path', Paths + Dir);
end;

procedure RemoveFromPath(const Dir: String);
var
  Paths: String;
  P: Integer;
begin
  if not RegQueryStringValue(PathRoot, PathKey, 'Path', Paths) then Exit;
  Paths := ';' + Paths + ';';
  P := Pos(';' + Uppercase(Dir) + ';', Uppercase(Paths));
  if P = 0 then Exit;
  Delete(Paths, P, Length(Dir) + 1);
  Paths := Copy(Paths, 2, Length(Paths) - 2);
  RegWriteExpandStringValue(PathRoot, PathKey, 'Path', Paths);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('addpath') then
    AddToPath(ExpandConstant('{app}'));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemoveFromPath(ExpandConstant('{app}'));
end;
