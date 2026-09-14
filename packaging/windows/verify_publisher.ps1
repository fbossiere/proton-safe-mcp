param([Parameter(Mandatory)][string] $Path)
$ErrorActionPreference = "Stop"
$signature = Get-AuthenticodeSignature -FilePath $Path
if ($signature.Status -ne "Valid" -or
    $signature.SignerCertificate.Subject -notmatch '(^|,\s*)CN=Pyrsys B\.V\.(,|$)') {
    throw "The compiler must have a valid Authenticode signature from Pyrsys B.V."
}
Write-Host "Verified compiler publisher: $($signature.SignerCertificate.Subject)"
