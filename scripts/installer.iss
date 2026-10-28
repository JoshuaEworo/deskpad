#define AppVersion "0.2.0-alpha.4"
[Setup]
AppId={{DA9327C8-01B9-4CE8-9FF3-4EB937A18EF4}
AppName=Deskpad
AppVersion={#AppVersion}
AppPublisher=Deskpad contributors
DefaultDirName={localappdata}\Programs\Deskpad
DefaultGroupName=Deskpad
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Deskpad-Setup-Windows-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\build\deskpad.ico
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\Deskpad.exe
CloseApplications=yes
[Files]
Source: "..\dist\Deskpad\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\Deskpad"; Filename: "{app}\Deskpad.exe"; AppUserModelID: "Deskpad.Desktop"
Name: "{autodesktop}\Deskpad"; Filename: "{app}\Deskpad.exe"; AppUserModelID: "Deskpad.Desktop"; Tasks: desktopicon
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked
[Run]
Filename: "{app}\Deskpad.exe"; Description: "Open Deskpad"; Flags: nowait postinstall skipifsilent
[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "Deskpad"; Flags: uninsdeletevalue
