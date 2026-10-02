# Shared by the launcher and CPU checks. Compatible with PowerShell 5.1 and 7.
function Invoke-FreeVideoBootstrapCommand {
    param(
        [Parameter(Mandatory=$true)][string]$Executable,
        [Parameter(Mandatory=$true)][string[]]$Arguments,
        [Parameter(Mandatory=$true)][string]$LogPath,
        [Parameter(Mandatory=$true)][string]$Label,
        [switch]$Direct
    )
    # Windows PowerShell 5.1 turns redirected native stderr into ErrorRecords.
    # uv writes normal progress there. Let the child finish and inspect its
    # exit code; keep these preferences local to this function.
    $ErrorActionPreference = 'Continue'
    $PSNativeCommandUseErrorActionPreference = $false
    $encoding = [Text.UTF8Encoding]::new($false)
    if (Test-Path -LiteralPath $LogPath) {
        # Preserve older PowerShell 5.1 UTF-16 logs when appending a retry.
        $reader = [IO.StreamReader]::new($LogPath, $encoding, $true)
        try {
            [void]$reader.Peek()
            $encoding = $reader.CurrentEncoding
        } finally { $reader.Dispose() }
    }
    $log = [IO.StreamWriter]::new($LogPath, $true, $encoding)
    $log.AutoFlush = $true
    $previousExitCode = $global:LASTEXITCODE
    $savedProxy = @{}
    if ($Direct) {
        foreach ($name in @('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY')) {
            $savedProxy[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
            [Environment]::SetEnvironmentVariable($name, $null, 'Process')
        }
        [Environment]::SetEnvironmentVariable('NO_PROXY', '*', 'Process')
    }
    try {
        # Native commands update the global automatic variable. A local
        # LASTEXITCODE would shadow their result and keep a stale/null value.
        $global:LASTEXITCODE = $null
        $log.WriteLine(('[{0}] {1}' -f [DateTime]::UtcNow.ToString('o'), $Label))
        & $Executable @Arguments 2>&1 | ForEach-Object { $log.WriteLine($_.ToString()) }
        $nativeExit = $global:LASTEXITCODE
        if ($null -eq $nativeExit) { throw "Native command did not return an exit code: $Executable" }
        $log.WriteLine("Exit code: $nativeExit")
        return [int]$nativeExit
    } catch {
        $log.WriteLine('Invocation failed: ' + $_.Exception.Message)
        throw
    } finally {
        foreach ($name in $savedProxy.Keys) {
            [Environment]::SetEnvironmentVariable($name, $savedProxy[$name], 'Process')
        }
        $global:LASTEXITCODE = $previousExitCode
        $log.Dispose()
    }
}
