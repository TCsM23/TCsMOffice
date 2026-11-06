; Inno Setup script for the TCsOffice installer wizard.
; Built by the release workflow:  iscc /DAppVersion=1.0.17 packaging\windows\TCsOffice.iss
; Expects PyInstaller's output in dist\TCsOffice\ (see packaging\tcsoffice.spec).

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "TCsOffice"
#define AppExe "TCsOffice.exe"
#define Root "..\.."

[Setup]
; Never change AppId: it is how a new version finds and replaces the old one.
AppId={{A3F0CC54-9CB8-4A80-99B7-B29EAF002825}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=TCsM
AppPublisherURL=https://github.com/TCsM23/TCsMOffice
AppUpdatesURL=https://github.com/TCsM23/TCsMOffice/releases
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Per-user install by default, so updates never need an admin prompt.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#Root}\dist
OutputBaseFilename=TCsOffice-Setup-{#AppVersion}
SetupIconFile={#Root}\office\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
WizardStyle=modern
WizardImageFile=wizard-large.bmp
WizardSmallImageFile=wizard-small.bmp
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Let the built-in updater run this silently over a running copy.
CloseApplications=force
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#Root}\dist\TCsOffice\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Clear the previous build's files so nothing stale is left behind after an update.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; No skipifsilent: after a silent update from inside the app, this starts the new version.
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall
