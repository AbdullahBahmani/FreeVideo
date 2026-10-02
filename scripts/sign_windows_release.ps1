param(
    [Parameter(Mandatory = $true)][string]$OneFile,
    [Parameter(Mandatory = $true)][string]$FolderZip,
    [Parameter(Mandatory = $true)][string]$FolderExecutable
)

$ErrorActionPreference = 'Stop'

# Signing is deliberately opt-in. A release must never claim to be signed when
# the maintainer has not configured a certificate in the repository secrets.
$encoded = [Environment]::GetEnvironmentVariable('WINDOWS_CODESIGN_PFX_B64')
if ([string]::IsNullOrWhiteSpace($encoded)) {
    Write-Host 'Authenticode signing is not configured; retaining unsigned build.'
    exit 0
}
$password = [Environment]::GetEnvironmentVariable('WINDOWS_CODESIGN_PFX_PASSWORD')
if ($null -eq $password) { $password = '' }
$timestamp = [Environment]::GetEnvironmentVariable('WINDOWS_CODESIGN_TIMESTAMP_URL')
if ([string]::IsNullOrWhiteSpace($timestamp)) { $timestamp = 'http://timestamp.digicert.com' }

$kits = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
$signtool = Get-ChildItem -Path $kits -Filter signtool.exe -File -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
    Sort-Object FullName -Descending | Select-Object -First 1
if ($null -eq $signtool) {
    $signtool = Get-ChildItem -Path $kits -Filter signtool.exe -File -Recurse -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1
}
if ($null -eq $signtool) { throw 'Authenticode signing is configured, but signtool.exe is unavailable on the runner.' }

$pfx = Join-Path $env:RUNNER_TEMP 'freevideo-signing.pfx'
[IO.File]::WriteAllBytes($pfx, [Convert]::FromBase64String($encoded))

function Sign-Executable([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Executable is missing: $Path" }
    $signArgs = @('sign', '/fd', 'SHA256', '/td', 'SHA256', '/tr', $timestamp,
        '/f', $pfx, '/p', $password, '/d', 'FreeVideo', '/du', 'https://www.flashml.ai/', $Path)
    & $signtool.FullName @signArgs
    if ($LASTEXITCODE -ne 0) { throw "signtool failed for $Path (exit $LASTEXITCODE)" }
    & $signtool.FullName verify /pa /all $Path
    if ($LASTEXITCODE -ne 0) { throw "signtool verification failed for $Path (exit $LASTEXITCODE)" }
}

Sign-Executable $OneFile
Sign-Executable $FolderExecutable

# The ZIP itself cannot carry an Authenticode signature. Sign the executable
# inside it, then recreate the archive before hashes, scanning, and publishing.
$unpacked = Join-Path $env:RUNNER_TEMP 'freevideo-signed-folder'
Remove-Item -LiteralPath $unpacked -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -LiteralPath $FolderZip -DestinationPath $unpacked -Force
$folderExe = Join-Path $unpacked 'FreeVideo\FreeVideo.exe'
Sign-Executable $folderExe
$folderHash = (Get-FileHash -LiteralPath $folderExe -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath (Join-Path $unpacked 'FreeVideo\SHA256SUMS.txt') `
    -Value ($folderHash + '  FreeVideo.exe') -Encoding ascii
Remove-Item -LiteralPath $FolderZip -Force
Compress-Archive -Path (Join-Path $unpacked 'FreeVideo') -DestinationPath $FolderZip -CompressionLevel Optimal
Write-Host 'Authenticode signatures applied to the one-file launcher and folder launcher.'
