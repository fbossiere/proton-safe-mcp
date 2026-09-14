; Proton Safe — Windows 11 x64 installer.
;
; Deliberate choices, each one load-bearing:
;
;   PrivilegesRequired=lowest   The whole product is per-user. Nothing is written outside
;                               this account's profile, so Windows never has to ask for
;                               elevation and the setup cannot install for someone else.
;   AppId                       Fixed forever. It is what makes an update recognise the
;                               existing installation instead of creating a second entry.
;   ArchitecturesAllowed        x64 native only. Windows 10, 32-bit and ARM64 are out of
;                               scope and are refused before anything is written.
;
; Built by packaging/windows/build_windows.ps1, which passes the version and the paths.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef BundleDir
  #define BundleDir "..\..\dist\windows\proton-safe-assistant"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\dist\windows"
#endif
#ifndef IconFile
  #define IconFile "..\..\build\windows\proton-safe.ico"
#endif

; The identity that must never change: it is what an update looks itself up by, both in
; Windows' installed-applications list and in the code below.
#define AppGuid "{7F3A6C21-58D4-4E0B-9E2E-3B7D1C9A4F58}"
#define AppName "Proton Safe"
#define AppPublisher "Proton Safe (independent project)"
#define AppUrl "https://fbossiere.github.io/proton-safe-mcp/"
#define AssistantExe "proton-safe-assistant.exe"

[Setup]
AppId={{7F3A6C21-58D4-4E0B-9E2E-3B7D1C9A4F58}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
VersionInfoVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}
AppUpdatesURL={#AppUrl}

; Per-user throughout: the program, the uninstall entry and the shortcuts.
PrivilegesRequired=lowest
; No override: there is no "for all users" mode to opt into. Offering one and then
; refusing it in code would be a dialog that leads nowhere.
PrivilegesRequiredOverridesAllowed=
DefaultDirName={localappdata}\Programs\{#AppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
; Inno Setup hides the Welcome page by default. It is the first screen this product
; specifies — the one that says what Proton Safe is, where it installs and that it
; installs for this account only — so it is turned back on explicitly. Without this the
; captions set in InitializeWizard below would be written to a page nobody ever sees.
DisableWelcomePage=no
DefaultGroupName={#AppName}
UsePreviousAppDir=yes

; Windows 11 x64 only. "arm64" is absent on purpose: Proton Mail Bridge excludes ARM
; devices outside Apple silicon, so emulating x64 here would not give a working setup.
ArchitecturesAllowed=x64compatible and not arm64
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.22000

; Only one install, update or uninstall may be active for this user at a time.
SetupMutex=ProtonSafeSetup_7F3A6C21-58D4-4E0B-9E2E-3B7D1C9A4F58
OutputDir={#OutputDir}
#ifdef Signed
OutputBaseFilename=ProtonSafe-Setup-{#AppVersion}-x64
#else
; A build made without a signing identity says so in its own name. It is a test build,
; and it must never be mistaken for, or published as, the Windows download.
OutputBaseFilename=ProtonSafe-Setup-{#AppVersion}-x64-unsigned
#endif
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#AssistantExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
LicenseFile=..\..\LICENSE
; Restarting Windows is never required, and never scheduled behind the user's back.
RestartIfNeededByRun=no
; Ask Restart Manager to close only the processes that hold the files being replaced,
; and never force one shut: a running assistant, Bridge or AI client belongs to the
; person using it, and an update is not a reason to end their work.
CloseApplications=yes
ForceCloseApplications=no
RestartApplications=no
SetupLogging=yes

#ifdef Signed
; Signed in the same pass as the installer, through the sign tool the build passes in.
; Enabled only when a signing identity exists, so an unsigned test build still compiles.
SignedUninstaller=yes
SignTool=protonsafe
#endif

[Messages]
; Replace the generic refusals so an out-of-scope system is told what the scope is,
; before anything has been written.
fr.OnlyOnTheseArchitectures=Proton Safe nécessite un Windows 11 en 64 bits (x64). Les versions 32 bits et les processeurs ARM ne sont pas pris en charge.
en.OnlyOnTheseArchitectures=Proton Safe needs 64-bit (x64) Windows 11. 32-bit versions and ARM processors are not supported.
fr.WinVersionTooLowError=Proton Safe nécessite Windows 11 (version 10.0.22000) ou plus récent. Windows 10 n'est pas pris en charge par cette version.
en.WinVersionTooLowError=Proton Safe needs Windows 11 (version 10.0.22000) or newer. Windows 10 is not supported by this version.

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
fr.AppTitle=Installer Proton Safe
fr.AppIntro=Connectez Proton Mail à votre assistant. Proton Safe s'installe uniquement pour votre compte Windows.
fr.DesktopIcon=Créer un raccourci sur le Bureau
fr.LaunchApp=Ouvrir Proton Safe
fr.Installed=Proton Safe est installé. La connexion à votre compte reste à faire dans l'assistant.
fr.InstallLocation=Emplacement d'installation : %1
fr.SameVersion=Proton Safe %1 est déjà installé. Continuer réinstallera ses fichiers sans toucher à vos réglages, à votre mot de passe enregistré ni à vos autres plugins.
fr.NeedsBridge=Proton Mail Bridge et un assistant compatible sont nécessaires pour utiliser la connexion. Ils s'installent séparément.
fr.Downgrade=Une version plus récente de Proton Safe (%1) est déjà installée. Cet installateur (%2) ne peut pas la remplacer. Désinstallez d'abord la version installée si vous voulez vraiment revenir en arrière.
fr.NotWindows11=Proton Safe nécessite Windows 11 en 64 bits (x64). Windows 10, les versions 32 bits et les processeurs ARM ne sont pas pris en charge.
fr.Elevated=Cet installateur doit être lancé depuis votre compte Windows habituel, sans « Exécuter en tant qu'administrateur » : Proton Safe s'installe pour le compte qui le lance.
fr.RemovingConnection=Retrait de la connexion dans votre assistant…
fr.EraseData=Effacer aussi les réglages et le mot de passe Bridge enregistrés par Proton Safe
fr.RemovalIncomplete=La connexion n'a pas pu être entièrement retirée de votre assistant. Vos réglages et votre mot de passe sont conservés pour pouvoir réessayer. Une entrée peut subsister dans votre assistant.

en.AppTitle=Install Proton Safe
en.AppIntro=Connect Proton Mail to your assistant. Proton Safe installs for your Windows account only.
en.DesktopIcon=Create a shortcut on the Desktop
en.LaunchApp=Open Proton Safe
en.Installed=Proton Safe is installed. Connecting your account is still done in the assistant.
en.InstallLocation=Install location: %1
en.SameVersion=Proton Safe %1 is already installed. Continuing reinstalls its files without touching your settings, your saved password or your other plugins.
en.NeedsBridge=Proton Mail Bridge and a compatible assistant are needed to use the connection. They are installed separately.
en.Downgrade=A newer version of Proton Safe (%1) is already installed. This installer (%2) cannot replace it. Uninstall the installed version first if you really want to go back.
en.NotWindows11=Proton Safe needs Windows 11 on 64-bit (x64). Windows 10, 32-bit versions and ARM processors are not supported.
en.Elevated=Run this installer from your usual Windows account, without "Run as administrator": Proton Safe installs for the account that starts it.
en.RemovingConnection=Removing the connection from your assistant…
en.EraseData=Also erase the settings and the Bridge password saved by Proton Safe
en.RemovalIncomplete=The connection could not be fully removed from your assistant. Your settings and password are kept so you can try again. An entry may remain in your assistant.

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The whole PyInstaller tree, both executables and the shared _internal directory.
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; A Start menu entry is always created; the Desktop shortcut is opt-in.
Name: "{userprograms}\{#AppName}"; Filename: "{app}\{#AssistantExe}"; IconFilename: "{app}\{#AssistantExe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AssistantExe}"; IconFilename: "{app}\{#AssistantExe}"; Tasks: desktopicon

[Run]
; Never in silent mode: an unattended install must not open a window.
Filename: "{app}\{#AssistantExe}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[Code]
var
  EraseChosen: Boolean;

function IsWindows11OrNewer(): Boolean;
var
  Version: TWindowsVersion;
begin
  GetWindowsVersionEx(Version);
  Result := (Version.Major > 10) or ((Version.Major = 10) and (Version.Build >= 22000));
end;

function InstalledVersion(var Version: String): Boolean;
begin
  { Per-user installs record themselves under HKCU. The key is the AppId plus _is1,
    which is why the AppId must never change between releases. }
  Result := RegQueryStringValue(HKEY_CURRENT_USER,
    'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppGuid}_is1',
    'DisplayVersion', Version);
end;

function InitializeSetup(): Boolean;
var
  Existing: String;
  ExistingPacked, ThisPacked: Int64;
begin
  Result := True;

  { ArchitecturesAllowed and MinVersion already refuse an out-of-scope system with the
    messages above. This is the same refusal stated once more from the code, so a build
    compiled with those directives changed cannot quietly widen the scope. }
  if not IsWindows11OrNewer() then
  begin
    MsgBox(ExpandConstant('{cm:NotWindows11}'), mbCriticalError, MB_OK);
    Result := False;
    Exit;
  end;

  { An elevated run would install into the administrator's profile, leaving the person
    actually signed in with no Proton Safe at all. }
  if IsAdminInstallMode then
  begin
    MsgBox(ExpandConstant('{cm:Elevated}'), mbCriticalError, MB_OK);
    Result := False;
    Exit;
  end;

  { A newer installation is never silently replaced: the configuration schema it wrote
    may be one this build does not understand, and downgrading it would lose settings. }
  if InstalledVersion(Existing) then
    if StrToVersion(Existing, ExistingPacked) and StrToVersion('{#AppVersion}', ThisPacked) then
      if ComparePackedVersion(ExistingPacked, ThisPacked) > 0 then
      begin
        MsgBox(FmtMessage(ExpandConstant('{cm:Downgrade}'), [Existing, '{#AppVersion}']),
          mbCriticalError, MB_OK);
        Result := False;
        Exit;
      end;
end;

procedure InitializeWizard();
var
  Existing, Intro: String;
begin
  { The destination page is disabled because there is nothing to choose: the product is
    per-user and goes in one place. The location is still shown, read-only, so nobody has
    to guess where their files went, and it appears beside the one option there is. }
  Intro := ExpandConstant('{cm:AppIntro}') + #13#10#13#10 +
    FmtMessage(ExpandConstant('{cm:InstallLocation}'), [ExpandConstant('{app}')]) + #13#10#13#10 +
    ExpandConstant('{cm:NeedsBridge}');

  { Reinstalling the same version is the "repair the files" path. Saying so is the
    difference between a confident click and a worried one. }
  if InstalledVersion(Existing) then
    if CompareStr(Existing, '{#AppVersion}') = 0 then
      Intro := FmtMessage(ExpandConstant('{cm:SameVersion}'), [Existing]) + #13#10#13#10 + Intro;

  WizardForm.WelcomeLabel1.Caption := ExpandConstant('{cm:AppTitle}');
  WizardForm.WelcomeLabel2.Caption := Intro;
  { Appended, not replaced: the page keeps its own instruction and gains the one thing
    it cannot otherwise say, now that the destination page is disabled. }
  WizardForm.SelectTasksLabel.Caption := WizardForm.SelectTasksLabel.Caption + #13#10#13#10 +
    FmtMessage(ExpandConstant('{cm:InstallLocation}'), [ExpandConstant('{app}')]);
  WizardForm.FinishedLabel.Caption := ExpandConstant('{cm:Installed}');
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  EraseChosen := False;

  { Default: keep the settings and the password so a reinstall finds them. Erasing is
    an explicit, opt-in choice, and it is carried out by the assistant, the only
    component that knows which entries Proton Safe actually created. }
  if not UninstallSilent then
    EraseChosen := MsgBox(ExpandConstant('{cm:EraseData}'), mbConfirmation, MB_YESNO) = IDYES;
end;

procedure InitializeUninstallProgressForm();
begin
  UninstallProgressForm.StatusLabel.Caption := ExpandConstant('{cm:RemovingConnection}');
end;

procedure CurUninstallStepChanged(CurStep: TUninstallStep);
var
  Assistant, Parameters: String;
  ResultCode: Integer;
begin
  if CurStep <> usUninstall then
    Exit;

  { The assistant owns client registrations, Credential Manager and the configuration
    format. The uninstaller asks it to disconnect rather than reimplementing any of
    that, and it reads the exit code: a client that refused the removal must not be
    reported as disconnected. What is kept when the removal is incomplete are the
    settings, the password and the journal, which are exactly what a retry needs. }
  Assistant := ExpandConstant('{app}\{#AssistantExe}');
  if not FileExists(Assistant) then
    Exit;

  Parameters := '--uninstall-connection';
  if EraseChosen then
    Parameters := Parameters + ' --erase-local';

  if not Exec(Assistant, Parameters, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    ResultCode := 1;

  if (ResultCode <> 0) and (not UninstallSilent) then
    MsgBox(ExpandConstant('{cm:RemovalIncomplete}'), mbInformation, MB_OK);
end;
