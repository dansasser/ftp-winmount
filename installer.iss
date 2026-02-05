; Inno Setup Script for FTP-WinMount
; Build with: iscc installer.iss

#define MyAppName "FTP-WinMount"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Daniel T Sasser II"
#define MyAppURL "https://github.com/dansasser/ftp-winmount"
#define MyAppExeName "ftp-winmount.exe"

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
OutputBaseFilename=ftp-winmount-{#MyAppVersion}-setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ChangesEnvironment=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\ftp-winmount.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName} Documentation"; Filename: "{#MyAppURL}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Registry]
; Add to PATH
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; \
    ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; \
    Check: NeedsAddPath('{app}')

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
const
  WM_SETTINGCHANGE = $001A;
  SMTO_ABORTIFHUNG = $0002;

function SendMessageTimeoutW(hWnd: HWND; Msg: UINT; wParam: WPARAM;
  lParam: PAnsiChar; fuFlags: UINT; uTimeout: UINT;
  var lpdwResult: DWORD): LRESULT;
  external 'SendMessageTimeoutW@user32.dll stdcall';

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

procedure BroadcastEnvironmentChange();
var
  Dummy: DWORD;
begin
  // Notify Windows that environment variables changed
  // This broadcasts WM_SETTINGCHANGE so new terminals pick up PATH change
  SendMessageTimeoutW($FFFF, WM_SETTINGCHANGE, 0, 'Environment',
    SMTO_ABORTIFHUNG, 5000, Dummy);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    BroadcastEnvironmentChange();
  end;
end;

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

      // Broadcast the change
      BroadcastEnvironmentChange();
    end;
  end;
end;
