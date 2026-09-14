# A disposable local account exercises the actual per-user installer without elevation.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "process.ps1")
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$installer = (Get-ChildItem "$root\dist\windows\ProtonSafe-Setup-*.exe" | Select-Object -First 1).FullName
if ((Invoke-NativeProcess $installer @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-')) -eq 0) {
    throw "An elevated setup must be refused."
}
$name = "Proton CI " + [guid]::NewGuid().ToString('N').Substring(0, 6)
$password = ConvertTo-SecureString ([guid]::NewGuid().ToString('N') + 'aA!7') -AsPlainText -Force
$credential = [pscredential]::new("$env:COMPUTERNAME\$name", $password)
$work = Join-Path $env:PUBLIC ("Proton Safe test " + [guid]::NewGuid())
New-Item -ItemType Directory $work | Out-Null
try {
    $account = New-LocalUser -Name $name -Password $password -AccountNeverExpires
    # Built-in Users is resolved by SID, independently of the runner's language.
    Add-LocalGroupMember -SID 'S-1-5-32-545' -Member $account
    & icacls.exe $work /inheritance:r /grant:r "*$($account.SID.Value):(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not isolate the test directory." }
    $out = Join-Path $work 'stdout.log'
    $err = Join-Path $work 'stderr.log'
    # Start-Process uses one command string when credentials are supplied. Every path
    # is quoted explicitly here; argument preservation inside tests uses ArgumentList.
    $script = Join-Path $PSScriptRoot 'test_install.ps1'
    $arguments = '-NoProfile -File "{0}" -InstallerPath "{1}" -TestPython "{2}"' -f $script, $installer, "$root\.venv\Scripts\python.exe"
    $process = Start-Process -FilePath (Get-Command pwsh).Source -Credential $credential `
        -LoadUserProfile -WorkingDirectory $work -ArgumentList $arguments `
        -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
    if (-not $process.WaitForExit(300000)) {
        $process.Kill($true)
        throw "Standard account test exceeded five minutes."
    }
    Get-Content $out | Write-Host
    Get-Content $err | Write-Host
    if ($process.ExitCode -ne 0) { throw "Standard account tests failed ($($process.ExitCode))." }
} finally {
    if (Get-LocalUser -Name $name -ErrorAction SilentlyContinue) { Remove-LocalUser -Name $name }
    Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
}
