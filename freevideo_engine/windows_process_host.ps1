# The one-file GUI must not relaunch its unpacking bootloader as a job gate.
# PowerShell waits before spawning any child; all descendants then inherit the Job.
$ErrorActionPreference = 'Stop'
$event = [Threading.EventWaitHandle]::new($false, [Threading.EventResetMode]::ManualReset)
try {
    $event.SafeWaitHandle = [Microsoft.Win32.SafeHandles.SafeWaitHandle]::new([IntPtr]([long]$args[0]), $true)
    if (-not $event.WaitOne(30000)) { throw 'Worker was not assigned to its Windows Job Object in time.' }
} finally {
    $event.Dispose()
}
# Windows PowerShell 5.1's native argument binder removes embedded quotes and
# empty arguments. The Python controller already produced a Win32 command line;
# hand it directly to ProcessStartInfo, without shell invocation or evaluation.
$command = $env:FREEVIDEO_WINDOWS_CHILD_COMMAND | ConvertFrom-Json
Remove-Item Env:FREEVIDEO_WINDOWS_CHILD_COMMAND
if (-not $command.executable) { throw 'Missing worker executable.' }
$info = [Diagnostics.ProcessStartInfo]::new()
$info.FileName = $command.executable
$info.Arguments = $command.arguments
$info.UseShellExecute = $false
# Inherit the gate's hidden console so native helpers cannot create a new one.
$info.CreateNoWindow = $false
$info.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
# stdout/stderr redirection makes .NET set STARTF_USESTDHANDLES. With stdin
# redirection disabled it passes GetStdHandle(STD_INPUT_HANDLE) to the child:
# the controller's pipe (or NUL) itself, without another buffered pipe/pump.
# This delivers short writes and EOF directly and creates no StreamWriter/BOM.
$info.RedirectStandardInput = $false
$info.RedirectStandardOutput = $true
$info.RedirectStandardError = $true
$process = [Diagnostics.Process]::new()
$process.StartInfo = $info
try {
    if (-not $process.Start()) { throw 'Worker did not start.' }
    # Copy raw bytes continuously; do not buffer the whole log, translate its
    # encoding, or wait for a full line before forwarding progress to the GUI.
    $output = $process.StandardOutput.BaseStream.CopyToAsync([Console]::OpenStandardOutput())
    $errorOutput = $process.StandardError.BaseStream.CopyToAsync([Console]::OpenStandardError())
    $process.WaitForExit()
    # Windows PowerShell exposes the internal VoidTaskResult of CopyToAsync.
    # Consume completion without printing that value into the worker's stdout.
    [void]$output.GetAwaiter().GetResult()
    [void]$errorOutput.GetAwaiter().GetResult()
    $code = $process.ExitCode
} finally {
    $process.Dispose()
}
exit $code
