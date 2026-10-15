; Inno Setup script for camcommand
; Builds a GUI installer (camcommand-setup.exe) that installs the standalone
; camcommand.exe, adds its folder to PATH, and registers an uninstaller in
; "Add or remove programs".
;
; Compile with:
;   "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" camcommand.iss

#define MyAppName "camcommand"
#define MyAppVersion "0.3.8"
#define MyAppPublisher "Camlock Systems"
#define MyAppExeName "camcommand.exe"

[Setup]
; A fixed AppId keeps upgrades/uninstall stable across versions. Do not change it.
AppId={{C4A1D0E2-6B3F-4B7A-9E21-0B7C5A9F3D18}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Default to a per-user install (no admin/UAC prompt). The user may pick
; "install for all users" on the privileges page, which installs to Program
; Files and puts camcommand on the system PATH.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ChangesEnvironment=yes
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=Output
OutputBaseFilename=camcommand-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#MyAppName} {#MyAppVersion}
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "camcommand.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md";    DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
Name: "{group}\{#MyAppName} (interactive)"; Filename: "{app}\{#MyAppExeName}"; Parameters: "interactive"
Name: "{group}\Uninstall {#MyAppName}";     Filename: "{uninstallexe}"

[Run]
; Offer to run it once so the user immediately sees it works.
Filename: "{cmd}"; Parameters: "/k ""{app}\{#MyAppExeName}"" --version"; \
  Description: "Open a command prompt and show camcommand version"; \
  Flags: postinstall skipifsilent shellexec

[Code]
const
  EnvKeyHKLM = 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';
  EnvKeyHKCU = 'Environment';

function EnvRootKey(): Integer;
begin
  if IsAdminInstallMode() then
    Result := HKEY_LOCAL_MACHINE
  else
    Result := HKEY_CURRENT_USER;
end;

function EnvSubKey(): string;
begin
  if IsAdminInstallMode() then
    Result := EnvKeyHKLM
  else
    Result := EnvKeyHKCU;
end;

{ Returns True if Dir already appears as a full entry in Paths. }
function DirInPath(const Paths, Dir: string): Boolean;
begin
  Result := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Paths) + ';') > 0;
end;

procedure AddToPath(const Dir: string);
var
  Paths: string;
begin
  if not RegQueryStringValue(EnvRootKey(), EnvSubKey(), 'Path', Paths) then
    Paths := '';

  if DirInPath(Paths, Dir) then
    Exit;

  if (Paths <> '') and (Copy(Paths, Length(Paths), 1) <> ';') then
    Paths := Paths + ';';
  Paths := Paths + Dir;

  RegWriteExpandStringValue(EnvRootKey(), EnvSubKey(), 'Path', Paths);
end;

procedure RemoveFromPath(const Dir: string);
var
  Paths: string;
  P: Integer;
begin
  if not RegQueryStringValue(EnvRootKey(), EnvSubKey(), 'Path', Paths) then
    Exit;

  { Locate ';Dir;' inside a sentinel-wrapped copy, then splice it out. }
  P := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Paths) + ';');
  if P = 0 then
    Exit;

  { P is relative to the sentinel-prefixed string; adjust back to Paths. }
  Dec(P);
  if P <= 0 then
  begin
    { Dir is the first entry. }
    Delete(Paths, 1, Length(Dir));
    if (Length(Paths) > 0) and (Copy(Paths, 1, 1) = ';') then
      Delete(Paths, 1, 1);
  end
  else
  begin
    { Remove the leading ';' plus Dir. }
    Delete(Paths, P, Length(Dir) + 1);
  end;

  RegWriteExpandStringValue(EnvRootKey(), EnvSubKey(), 'Path', Paths);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    AddToPath(ExpandConstant('{app}'));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    RemoveFromPath(ExpandConstant('{app}'));
end;
