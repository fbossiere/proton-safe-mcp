# Keep each argument intact, including paths with spaces, and bound every wait.
function Invoke-NativeProcess {
    param(
        [Parameter(Mandatory)][string] $FilePath,
        [string[]] $Arguments = @(),
        [int] $TimeoutSeconds = 120
    )
    $info = [System.Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $FilePath
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    foreach ($argument in $Arguments) { $info.ArgumentList.Add($argument) }
    $process = [System.Diagnostics.Process]::Start($info)
    try {
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $process.Kill($true)
            $process.WaitForExit()
            throw "The process exceeded its $TimeoutSeconds second deadline."
        }
        return $process.ExitCode
    } finally { $process.Dispose() }
}
