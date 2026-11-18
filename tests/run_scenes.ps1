<#
Stress run: every printable NIH 3D preset and a set of hand-built scenes,
exported with the common options and checked (tests/test_scenes.py).

Needs the ChimeraX GUI, because the presets do: a ChimeraX window opens on
display 1 for the length of the run (about an hour) and closes itself.
Then PrusaSlicer loads every default export that should be closed and must
call it manifold.

    .\tests\run_scenes.ps1                 # everything
    .\tests\run_scenes.ps1 -Only "1ubq"    # scenes whose name contains this

Exit code 0 when every export passed.
#>
param([string]$Only = "")

# not "Stop": PowerShell 5.1 turns a native program's stderr into errors
$Bundle = Split-Path -Parent $PSScriptRoot
$ChimeraX = "C:\Program Files\ChimeraX 1.12\bin\ChimeraX.exe"
$PrusaSlicer = "C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe"
$Out = "$Bundle\tests\out\scenes"
$Script = "$Bundle\tests\test_scenes.py"

Add-Type @"
using System; using System.Runtime.InteropServices;
public class ScenesWindow {
    [DllImport("user32.dll")]
    public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y,
                                           int cx, int cy, uint flags);
}
"@

$env:SCENES_ONLY = $Only
$p = Start-Process -FilePath $ChimeraX -WorkingDirectory $Bundle -PassThru `
    -ArgumentList "--script `"$Script`" --exit"
# Put the window on display 1 (x = -3000), leaving the main screen free. The
# window only gets a handle once it is shown; placing it from inside ChimeraX
# does not stick.
foreach ($i in 1..120) {
    Start-Sleep -Milliseconds 250
    $p.Refresh()
    if ($p.HasExited) { break }
    if ($p.MainWindowHandle -ne 0) {
        # SWP_NOZORDER | SWP_NOACTIVATE: do not take focus from the user
        [ScenesWindow]::SetWindowPos($p.MainWindowHandle, [IntPtr]::Zero,
                                     -2920, 80, 1500, 950, 0x0014) | Out-Null
        break
    }
}
$finished = $p.WaitForExit(2 * 60 * 60 * 1000)
if (-not $finished) {
    $p.Kill()
    Write-Output "FAIL  ChimeraX did not finish within two hours; results so far:"
}
$env:SCENES_ONLY = ""

if (-not (Test-Path "$Out\results.json")) {
    Write-Output "FAIL  no results written; the progress log says:"
    if (Test-Path "$Out\progress.txt") { Get-Content "$Out\progress.txt" -Tail 30 }
    exit 1
}
$results = Get-Content "$Out\results.json" -Raw -Encoding UTF8 | ConvertFrom-Json
$failed = @($results | Where-Object { -not $_.passed })

# PrusaSlicer's own verdict on every default export of a closed scene
$sliceFail = 0
$sliceCount = 0
if (Test-Path $PrusaSlicer) {
    foreach ($r in $results) {
        if (-not $r.passed -or $r.export -ne "(default)" -or -not $r.file) { continue }
        if ($r.scene -like "*clipping plane*") { continue }
        $sliceCount++
        $info = & $PrusaSlicer --info "$Out\$($r.file)" 2>$null | Out-String
        if ($info -notmatch "manifold = yes") {
            $sliceFail++
            Write-Output ("FAIL  PrusaSlicer: not manifold: {0}" -f $r.scene)
        }
    }
} else {
    Write-Output "skip  PrusaSlicer not installed"
}

foreach ($r in $failed) {
    Write-Output ("FAIL  {0}  [{1}]" -f $r.scene, $r.export)
    foreach ($m in $r.problems) { Write-Output ("        {0}" -f $m) }
}
$merged = @($results | Where-Object { $_.passed -and $_.merged })
if ($merged.Count) {
    Write-Output ""
    Write-Output "More than 15 colours, merged into 15 (warned in the log):"
    foreach ($r in $merged) { Write-Output ("  {0}  [{1}]" -f $r.scene, $r.export) }
}
Write-Output ""
Write-Output ("SCENES: {0} exports, {1} failed, {2} merged to 15 colours; PrusaSlicer: {3} loaded, {4} not manifold" `
    -f $results.Count, $failed.Count, $merged.Count, $sliceCount, $sliceFail)
if ($failed.Count -or $sliceFail -or -not $finished) { exit 1 }
exit 0
