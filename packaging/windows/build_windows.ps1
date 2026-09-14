<#
.SYNOPSIS
    Build, verify and package Proton Safe for Windows 11 x64.

.DESCRIPTION
    Runs on a Windows x64 machine: PyInstaller cannot produce a Windows bundle from
    Linux, so this has no cross-compilation path and refuses to pretend otherwise.

    The steps, in the order that makes a failure visible before it ships:

      1. refuse anything but a native x64 Windows host;
      2. draw the icon from the interface's own code;
      3. freeze the bundle with the shared PyInstaller spec;
      4. prove the bundle carries what it needs, by running it;
      5. sign the project's own executables, when an identity is configured;
      6. compile the installer with a pinned Inno Setup;
      7. record the digest, the provenance and the component inventory.

    Signing is driven entirely by environment variables so no key material is ever in
    this repository or in an artefact:

      PROTON_SAFE_SIGN_COMMAND  a command line with Inno Setup's $f placeholder for the
                                file to sign, for example:
                                "signtool.exe sign /fd sha256 /tr <url> /td sha256 $f"

    Without it the build still completes, and every artefact is named "-unsigned".

.PARAMETER SkipInstaller
    Build and verify the bundle only for local development. CI always compiles the setup.
#>
[CmdletBinding()]
param(
    [string] $InnoSetupVersion = "7.1.0",
    [string] $IsccPath = "",
    [switch] $SkipInstaller
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "process.ps1")

$Root       = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$BuildDir   = Join-Path $Root "build\windows"
$DistDir    = Join-Path $Root "dist\windows"
$BundleDir  = Join-Path $DistDir "proton-safe-assistant"
$IconFile   = Join-Path $BuildDir "proton-safe.ico"
$Python     = if ($env:PROTON_SAFE_PYTHON) { $env:PROTON_SAFE_PYTHON } else { "python" }

function Step([string] $Message) { Write-Host "==> $Message" -ForegroundColor Cyan }
function Fail([string] $Message) { Write-Error $Message; exit 1 }

# -- 1. the host ------------------------------------------------------------------

Step "Checking the build host"
if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
    Fail "PyInstaller cannot build a Windows bundle from another system."
}
# The native architecture, not the one this process is emulated under.
$architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
if ($architecture -ne [System.Runtime.InteropServices.Architecture]::X64) {
    Fail "This build must run on native x64 Windows (found $architecture)."
}

$Version = (& $Python (Join-Path $Root "packaging\version.py")).Trim()
if (-not $Version) { Fail "The package version could not be read." }
Step "Building Proton Safe $Version"

Remove-Item -Recurse -Force $DistDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $BuildDir, $DistDir | Out-Null

# -- 2. the icon ------------------------------------------------------------------

Step "Drawing the Windows icon from the interface's own code"
& $Python (Join-Path $Root "packaging\windows\make_icon.py") $IconFile
if ($LASTEXITCODE -ne 0) { Fail "The icon could not be produced." }

# -- 3. the bundle ----------------------------------------------------------------

Step "Freezing the bundle"
$PyInstaller = if ($env:PYINSTALLER) { $env:PYINSTALLER } else { "pyinstaller" }
& $PyInstaller --clean --noconfirm --log-level WARN `
    --workpath (Join-Path $Root "build\pyinstaller-windows") `
    --distpath $DistDir `
    (Join-Path $Root "packaging\proton-safe-assistant.spec")
if ($LASTEXITCODE -ne 0) { Fail "PyInstaller failed." }

$Assistant = Join-Path $BundleDir "proton-safe-assistant.exe"
$Runtime   = Join-Path $BundleDir "proton-safe-mcp.exe"
foreach ($required in @($Assistant, $Runtime)) {
    if (-not (Test-Path $required)) { Fail "missing from the bundle: $required" }
}

# -- 4. proving what the bundle carries -------------------------------------------
#
# A bundle that starts on the build machine proves nothing about what it embedded.
# These checks run the bundled executables and read what they report, because pure
# Python modules live inside the archive and cannot be found on disk.

Step "Verifying the bundled runtime and its embedded resources"
$Verify = Join-Path ([System.IO.Path]::GetTempPath()) ("proton safe vérification-" + [guid]::NewGuid())
$ConfigDir = Join-Path $Verify "config"
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
$ConfigFile = Join-Path $ConfigDir "config.toml"
@"
schema_version = 1

[bridge]
user = "verification@example.com"
imap_port = 1143
aliases = []
"@ | Set-Content -Path $ConfigFile -Encoding utf8

try {
    & $Python -c "import sys; from pathlib import Path; from proton_safe_mcp.platform_services import services; p=Path(sys.argv[1]); services().ensure_private_directory(p.parent); services().secure_existing_path(p)" $ConfigFile
    if ($LASTEXITCODE -ne 0) { Fail "The verification configuration could not be made private." }
    $report = & $Runtime doctor --config $ConfigFile 2>&1 | Out-String
    if ($report -notmatch "Proton Safe MCP doctor") {
        Fail "the bundled runtime did not produce a diagnosis"
    }
    # Tell a packaging defect apart from a locked session: this sentence appears only
    # when the credential backend never made it into the bundle at all.
    if ($report -match "missing from this installation") {
        Fail "the Windows Credential Manager backend was not bundled"
    }

    $env:PROTON_MCP_STATE_DIR = Join-Path $Verify "state"
    # Wait for the GUI executable explicitly and capture its build-only report.
    # A failure must return a status, never open a bootloader exception dialog.
    $verificationReport = Join-Path $Verify "bundle-verification.log"
    $exitCode = Invoke-NativeProcess -FilePath $Assistant -Arguments @(
        "--verify-bundle", "--config", $ConfigFile, "--verification-report", $verificationReport
    )
    if (Test-Path $verificationReport) { Get-Content $verificationReport | Write-Host }
    if ($exitCode -ne 0) { Fail "bundle self-verification failed (exit $exitCode)" }
} finally {
    Remove-Item Env:\PROTON_MCP_STATE_DIR -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $Verify -ErrorAction SilentlyContinue
}

# -- 5. signing -------------------------------------------------------------------

$SignCommand = $env:PROTON_SAFE_SIGN_COMMAND
$Signed = [bool] $SignCommand
if ($Signed) {
    Step "Signing the executables this project produces"
    # Only what this build made. Third-party binaries keep the signatures their
    # publishers gave them; re-signing them would replace a verifiable origin with ours.
    foreach ($file in @($Assistant, $Runtime)) {
        $command = $SignCommand.Replace('$f', '"' + $file + '"')
        cmd.exe /c $command
        if ($LASTEXITCODE -ne 0) { Fail "signing failed for $file" }
    }
} else {
    Write-Warning "No PROTON_SAFE_SIGN_COMMAND: this is an unsigned test build."
    Write-Warning "It must not be published as the Windows download."
}

# -- 6. the installer -------------------------------------------------------------

if (-not $SkipInstaller) {
    Step "Locating Inno Setup $InnoSetupVersion"
    if (-not $IsccPath) {
        $candidates = @(
            "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
            "${env:ProgramFiles}\Inno Setup 7\ISCC.exe",
            "${env:ProgramFiles}\Inno Setup 7 x64\ISCC.exe"
        )
        $IsccPath = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    if (-not $IsccPath -or -not (Test-Path $IsccPath)) {
        Fail "Inno Setup $InnoSetupVersion was not found. Install it, or pass -IsccPath."
    }
    # The compiler version is pinned: a different one may change the uninstaller, the
    # architecture directives or the signing behaviour, none of which may drift
    # silently between releases.
    # ISCC.exe is a frontend whose PE ProductVersion can be 0.0.0.0. Ask the
    # compiler engine itself; Inno Setup 7 provides this stable version command.
    $found = (& $IsccPath --version | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $found -ne $InnoSetupVersion) {
        Fail "Inno Setup $InnoSetupVersion is required; this machine has $found."
    }

    Step "Compiling the installer"
    $arguments = @(
        "/DAppVersion=$Version",
        "/DBundleDir=$BundleDir",
        "/DOutputDir=$DistDir",
        "/DIconFile=$IconFile"
    )
    if ($Signed) {
        $arguments += "/DSigned=1"
        # Inno Setup substitutes $f with the file to sign, and signs the uninstaller
        # through the same tool because SignedUninstaller is set.
        $arguments += "/Sprotonsafe=$SignCommand"
    }
    $arguments += (Join-Path $Root "packaging\windows\proton-safe.iss")
    & $IsccPath @arguments
    if ($LASTEXITCODE -ne 0) { Fail "Inno Setup failed." }

    $suffix = if ($Signed) { "" } else { "-unsigned" }
    $Installer = Join-Path $DistDir "ProtonSafe-Setup-$Version-x64$suffix.exe"
    if (-not (Test-Path $Installer)) { Fail "the installer was not produced at $Installer" }

    if ($Signed) {
        Step "Verifying the signature on the finished installer"
        $signature = Get-AuthenticodeSignature $Installer
        if ($signature.Status -ne "Valid") {
            Fail "the installer signature is $($signature.Status), not Valid."
        }
        Write-Host "Signed by: $($signature.SignerCertificate.Subject)"
    }

    # -- 7. digest, provenance, inventory -----------------------------------------
    #
    # The digest is taken after signing, because signing changes the file.

    Step "Recording the digest, the provenance and the inventory"
    $digest = (Get-FileHash -Algorithm SHA256 $Installer).Hash.ToLower()
    $name = Split-Path $Installer -Leaf
    "$digest *$name" | Set-Content -Path "$Installer.sha256" -Encoding ascii

    $commit = if ($env:GITHUB_SHA) { $env:GITHUB_SHA } else { (git -C $Root rev-parse HEAD) }
    $runUrl = if ($env:GITHUB_RUN_ID) {
        "$env:GITHUB_SERVER_URL/$env:GITHUB_REPOSITORY/actions/runs/$env:GITHUB_RUN_ID"
    } else { "local build" }
    $identity = if ($Signed) {
        (Get-AuthenticodeSignature $Installer).SignerCertificate.Subject
    } else { "UNSIGNED — test build, not for publication" }

@"
Proton Safe for Windows — build provenance

installer:       $name
sha256:          $digest
engine version:  $Version
source commit:   $commit
build OS:        $((Get-CimInstance Win32_OperatingSystem).Caption) $([System.Environment]::OSVersion.Version)
architecture:    x64
python:          $(& $Python --version)
pyinstaller:     $(& $PyInstaller --version)
inno setup:      $found
signing:         $identity
run:             $runUrl

Verify before installing, in PowerShell:

    Get-FileHash -Algorithm SHA256 .\$name

A signature is not the same as a reputation. Windows SmartScreen may still warn about a
recently published installer; never disable SmartScreen or Microsoft Defender to install
this or any other program.

This installer is produced from the sources at the commit above and is never committed to
the repository. Obtain it from GitHub Releases or from a CI build artefact.
"@ | Set-Content -Path (Join-Path $DistDir "BUILD-PROVENANCE-windows-x64.txt") -Encoding utf8

    & $Python (Join-Path $Root "packaging\make_sbom.py") $BundleDir `
        (Join-Path $DistDir "SBOM-windows-x64.json") --platform windows-x64
    if ($LASTEXITCODE -ne 0) { Fail "the component inventory could not be produced." }

    Write-Host ""
    Write-Host "Installer: $Installer" -ForegroundColor Green
    Write-Host "SHA-256:   $digest"
    if (-not $Signed) {
        Write-Warning "This build is UNSIGNED and must not become the Windows download."
    }
} else {
    Write-Host "Bundle built and verified at $BundleDir" -ForegroundColor Green
}
