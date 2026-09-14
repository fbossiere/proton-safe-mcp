<#
.SYNOPSIS
    Install, reinstall and uninstall the built installer without a single window.

.DESCRIPTION
    What this proves, on every run:

      * the installer completes unattended and returns 0;
      * it places both executables where the product says it does;
      * it registers exactly one entry in the installed-applications list;
      * a silent install never opens the assistant;
      * the installed runtime actually runs, from its installed location;
      * reinstalling the same version is accepted and leaves one entry, not two;
      * the uninstaller completes unattended, removes the program and its entry,
        and leaves the user's settings behind by default.

    CI invokes this script under a disposable standard account on Windows Server.
    These unattended checks do not replace scenario W01 on a real Windows 11 desktop
    or the interactive UAC, Bridge and AI-client acceptance scenarios.
#>
[CmdletBinding()]
param(
    [string] $InstallerPath = "",
    [Parameter(Mandatory)][string] $TestPython
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "process.ps1")

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Installer integration tests require a standard account."
}
# A process launched with credentials can inherit its caller's environment. Resolve
# this account's own known folders, as the installer and Python platform layer do.
$env:LOCALAPPDATA = [Environment]::GetFolderPath('LocalApplicationData')
$env:USERPROFILE = [Environment]::GetFolderPath('UserProfile')
$env:TEMP = Join-Path $env:LOCALAPPDATA 'Temp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
Write-Host "Testing account: $($identity.Name); profile: $env:USERPROFILE"

$Root    = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$DistDir = Join-Path $Root "dist\windows"
$AppDir  = Join-Path $env:LOCALAPPDATA "Programs\Proton Safe"
$AppId   = "{7F3A6C21-58D4-4E0B-9E2E-3B7D1C9A4F58}"
$RegKey  = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\${AppId}_is1"
$Silent  = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-")

function Step([string] $Message) { Write-Host "==> $Message" -ForegroundColor Cyan }
function Fail([string] $Message) { Write-Error $Message; exit 1 }

function Invoke-Installer([string] $Path, [string[]] $Arguments, [string] $What) {
    $log = Join-Path ([System.IO.Path]::GetTempPath()) "proton-safe-$What.log"
    $exitCode = Invoke-NativeProcess $Path ($Arguments + "/LOG=$log")
    if ($exitCode -ne 0) {
        if (Test-Path $log) { Get-Content $log -Tail 40 | Write-Host }
        Fail "$What returned $exitCode; it must return 0 unattended."
    }
}

if (-not $InstallerPath) {
    $InstallerPath = (Get-ChildItem -Path $DistDir -Filter "ProtonSafe-Setup-*.exe" |
        Select-Object -First 1 -ExpandProperty FullName)
}
if (-not $InstallerPath -or -not (Test-Path $InstallerPath)) {
    Fail "No installer was found in $DistDir."
}
Step "Testing $(Split-Path $InstallerPath -Leaf)"

# -- install ----------------------------------------------------------------------

Step "Installing unattended"
Invoke-Installer $InstallerPath $Silent "install"

foreach ($expected in @("proton-safe-assistant.exe", "proton-safe-mcp.exe")) {
    if (-not (Test-Path (Join-Path $AppDir $expected))) {
        Fail "missing from the installation: $expected"
    }
}
if (-not (Test-Path $RegKey)) { Fail "the installation registered no uninstall entry." }

$entry = Get-ItemProperty $RegKey
foreach ($field in @("DisplayName", "DisplayVersion", "Publisher", "DisplayIcon", "UninstallString")) {
    if (-not $entry.$field) { Fail "the installed-applications entry has no $field." }
}
Write-Host "Registered: $($entry.DisplayName) $($entry.DisplayVersion) — $($entry.Publisher)"

# A silent install must never start the interface.
$running = Get-Process -Name "proton-safe-assistant" -ErrorAction SilentlyContinue
if ($running) { Fail "a silent install started the assistant; it must not." }

Step "Running the installed runtime from where it was installed"
$config = Join-Path ([System.IO.Path]::GetTempPath()) "proton-safe-install-test\config.toml"
New-Item -ItemType Directory -Force -Path (Split-Path $config) | Out-Null
@"
schema_version = 1

[bridge]
user = "verification@example.com"
imap_port = 1143
aliases = []
"@ | Set-Content -Path $config -Encoding utf8
$report = & (Join-Path $AppDir "proton-safe-mcp.exe") doctor --config $config 2>&1 | Out-String
if ($report -notmatch "Proton Safe MCP doctor") {
    Fail "the installed runtime did not produce a diagnosis"
}
if ($report -match "missing from this installation") {
    Fail "the installed build has no Credential Manager backend"
}

# -- reinstall --------------------------------------------------------------------

Step "Reinstalling the same version unattended"
Invoke-Installer $InstallerPath $Silent "reinstall"
if (-not (Test-Path $RegKey)) { Fail "the reinstall lost the uninstall entry." }
$entries = @(Get-ChildItem "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall" |
    Where-Object { $property = (Get-ItemProperty $_.PSPath).PSObject.Properties["DisplayName"]; $property -and $property.Value -eq "Proton Safe" })
if ($entries.Count -ne 1) {
    Fail "expected exactly one installed-applications entry, found $($entries.Count)."
}

# -- uninstall --------------------------------------------------------------------

Step "Refusing uninstall when the managed client cannot be disconnected"
$uninstaller = Join-Path $AppDir "unins000.exe"
$marker = Join-Path $env:LOCALAPPDATA "Proton Safe\settings-kept.txt"
& $TestPython -c "from proton_safe_mcp.onboarding.journal import Journal, ManagedResource, write; write(Journal(client_id='missing-client', resources=[ManagedResource('plugin', 'proton-safe@test', 'openai-local')]))"
if ($LASTEXITCODE -ne 0) { Fail "Could not arrange the failed-removal scenario." }
'keep these settings' | Set-Content $marker
$refused = Invoke-NativeProcess $uninstaller $Silent
if ($refused -eq 0) { Fail "A failed client removal must fail the uninstall." }
if (-not (Test-Path (Join-Path $AppDir 'proton-safe-assistant.exe')) -or -not (Test-Path $RegKey)) {
    Fail "A failed uninstall removed the program or its registration."
}
& $TestPython -c "from proton_safe_mcp.onboarding.journal import read, clear; assert read().resources; clear()"
if ($LASTEXITCODE -ne 0) { Fail "A failed uninstall lost its recovery journal." }
Step "Retrying uninstall after the client problem is resolved"
Invoke-Installer $uninstaller $Silent "uninstall"

if (Test-Path (Join-Path $AppDir "proton-safe-assistant.exe")) {
    Fail "the uninstall left the program behind."
}
if (Test-Path $RegKey) { Fail "the uninstall left its installed-applications entry behind." }

if (-not (Test-Path $marker)) { Fail "Uninstall erased settings without consent." }
Remove-Item $marker
Remove-Item -Recurse -Force (Split-Path $config) -ErrorAction SilentlyContinue
Write-Host ""
Write-Host "Install, reinstall and uninstall all completed unattended." -ForegroundColor Green
Write-Host "This says nothing about UAC: see scenario W01." -ForegroundColor Yellow
