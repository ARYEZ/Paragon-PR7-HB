; Paragon PR7-HB installer (Inno Setup 6): a video converter, the way HandBrake converts.
;   iscc /DAppVersion=0.1.0 installer\pr7hb.iss      (after pyinstaller pr7hb.spec has made dist\PR7-HB)
;
; Per-user (no admin rights) into %LOCALAPPDATA%\Programs\PR7-HB, with a Start menu entry. The engine, the official
; HandBrakeCLI (GPL 2, unmodified; CI downloads the pinned release and checks its SHA-256), is in _internal\engine.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; AppId is permanent: it's how a new version finds and upgrades the installed one. Never change it.
AppId={{5A2D8918-1C5C-456F-AFCF-1FBA498EA280}
AppName=Paragon PR7-HB
AppVersion={#AppVersion}
AppVerName=Paragon PR7-HB {#AppVersion}
AppPublisher=Paragon
VersionInfoVersion={#AppVersion}
PrivilegesRequired=lowest
DefaultDirName={autopf}\PR7-HB
DefaultGroupName=Paragon PR7-HB
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
UsePreviousTasks=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=PR7-HB-Setup-{#AppVersion}
SetupIconFile=..\pr7hb\icons\app.ico
UninstallDisplayIcon={app}\PR7-HB.exe
UninstallDisplayName=Paragon PR7-HB
WizardStyle=modern
WizardImageFile=wizard-large-1x.bmp,wizard-large-2x.bmp
WizardSmallImageFile=wizard-small-1x.bmp,wizard-small-2x.bmp
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\PR7-HB\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\NOTICE.md"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\Paragon PR7-HB"; Filename: "{app}\PR7-HB.exe"; Comment: "Video converter"
Name: "{autodesktop}\Paragon PR7-HB"; Filename: "{app}\PR7-HB.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PR7-HB.exe"; Description: "{cm:LaunchProgram,Paragon PR7-HB}"; Flags: nowait postinstall skipifsilent
; Updates (Check for updates runs this installer with /SILENT /relaunch=1): start PR7-HB again when done.
Filename: "{app}\PR7-HB.exe"; Flags: nowait runasoriginaluser; Check: Relaunch

[Code]
// True only when the updater asked for it (/relaunch=1): normal and CI installs behave as before.
function Relaunch: Boolean;
begin
  Result := ExpandConstant('{param:relaunch|0}') = '1';
end;
