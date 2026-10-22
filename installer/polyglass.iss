; Inno Setup script for the Polyglass installer. Build after PyInstaller:
;   iscc /DAppVersion=0.1.0 installer\polyglass.iss   ->  dist\Polyglass-0.1.0-setup.exe
; Installs per user (no admin prompt) into %LOCALAPPDATA%\Programs\Polyglass.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8C1B6C2E-4E0B-4C83-9A5F-6F0F3E5B9A21}
AppName=Polyglass
AppVersion={#AppVersion}
AppPublisher=Polyglass
AppPublisherURL=https://github.com/lcubrilo/polyglass
AppSupportURL=https://github.com/lcubrilo/polyglass/issues
AppUpdatesURL=https://github.com/lcubrilo/polyglass/releases
DefaultDirName={localappdata}\Programs\Polyglass
DefaultGroupName=Polyglass
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Polyglass-{#AppVersion}-setup
SetupIconFile=..\polyglass\resources\polyglass.ico
UninstallDisplayIcon={app}\Polyglass.exe
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "startup"; Description: "Start Polyglass with Windows"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
Source: "..\dist\Polyglass\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Polyglass"; Filename: "{app}\Polyglass.exe"
Name: "{autodesktop}\Polyglass"; Filename: "{app}\Polyglass.exe"; Tasks: desktopicon

[Registry]
; Same value the app's own "Start with Windows" setting writes, so both stay in sync
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Polyglass"; ValueData: """{app}\Polyglass.exe"""; Tasks: startup; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "Polyglass"; Flags: uninsdeletevalue dontcreatekey

[Run]
Filename: "{app}\Polyglass.exe"; Description: "Start Polyglass now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM Polyglass.exe /F"; Flags: runhidden; RunOnceId: "StopPolyglass"
