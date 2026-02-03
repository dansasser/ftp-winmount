; Inno Setup Script for PyFTPDrive
; Build with: iscc installer.iss

#define MyAppName "PyFTPDrive"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Daniel T Sasser II"
#define MyAppURL "https://github.com/dansasser/ftp-winmount"
#define MyAppExeName "pyftpdrive.exe"

[Setup]
AppId={{E8F5A9D2-7C3B-4E1F-9A8D-6B5C4E3F2A1D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=LICENSE
OutputDir=dist
OutputBaseFilename=pyftpdrive-{#MyAppVersion}-setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ChangesEnvironment=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\pyftpdrive.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName} Documentation"; Filename: "{#MyAppURL}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Registry]
; Add to PATH
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; \
    ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; \
    Check: NeedsAddPath('{app}')

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE,
    'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
    'Path', OrigPath)
  then begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Param + ';', ';' + OrigPath + ';') = 0;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    // Notify Windows that environment variables changed
    // This broadcasts WM_SETTINGCHANGE so new terminals pick up PATH change
  end;
end;

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Path: string;
  AppPath: string;
  Parts: TArrayOfString;
  I, J, PartCount: Integer;
  NewPath: string;
  Current: string;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    AppPath := ExpandConstant('{app}');
    if RegQueryStringValue(HKEY_LOCAL_MACHINE,
      'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
      'Path', Path) then
    begin
      // Split by semicolon
      PartCount := 0;
      I := 1;
      while I <= Length(Path) do
      begin
        J := I;
        while (J <= Length(Path)) and (Path[J] <> ';') do
          J := J + 1;
        SetArrayLength(Parts, PartCount + 1);
        Parts[PartCount] := Copy(Path, I, J - I);
        PartCount := PartCount + 1;
        I := J + 1;
      end;

      // Rebuild without AppPath
      NewPath := '';
      for I := 0 to PartCount - 1 do
      begin
        Current := Parts[I];
        if CompareText(Current, AppPath) <> 0 then
        begin
          if NewPath = '' then
            NewPath := Current
          else
            NewPath := NewPath + ';' + Current;
        end;
      end;

      // Write back preserving REG_EXPAND_SZ
      RegWriteExpandStringValue(HKEY_LOCAL_MACHINE,
        'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
        'Path', NewPath);
    end;
  end;
end;
