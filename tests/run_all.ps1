<#
    Full test run for the Save3MF bundle.

        .\tests\run_all.ps1

    Stages, each of which fails the run:
      1. install          devel install must succeed AND actually replace the
                          installed files - a failed build silently leaves the
                          previous version in place, so a whole test run can
                          pass against stale code
      2. tests            the headless export suite
      3. slicers          PrusaSlicer must load the painted export, preserve
                          the painting through a round trip, and slice it; the
                          tool-change estimate is checked against the G-code
      4. wheel            devel build must produce a wheel containing the
                          package and its documentation

    Slicer stages are skipped, not failed, when the slicer is not installed.
#>

# Native stderr must not be merged with 2>&1: PowerShell 5.1 wraps each line in
# an ErrorRecord, which turns harmless build warnings into terminating errors.
# Every external command below is run through Invoke-Tool, which captures the
# two streams into files instead.
$ErrorActionPreference = "Continue"

$Bundle = Split-Path -Parent $PSScriptRoot
$ChimeraX = "C:\Program Files\ChimeraX 1.12\bin\ChimeraX-console.exe"
$Python = "C:\Program Files\ChimeraX 1.12\bin\python.exe"
$PrusaSlicer = "C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe"
$Installed = "$env:LOCALAPPDATA\UCSF\ChimeraX\1.12\Python311\site-packages\chimerax\save3mf"

$script:Failures = @()
$script:Skipped = @()

function Fail([string]$stage, [string]$why) {
    $script:Failures += "$stage : $why"
    Write-Host "FAIL  $stage - $why" -ForegroundColor Red
}
function Pass([string]$stage, [string]$detail = "") {
    Write-Host "ok    $stage $detail" -ForegroundColor Green
}
function Skip([string]$stage, [string]$why) {
    $script:Skipped += "$stage : $why"
    Write-Host "skip  $stage - $why" -ForegroundColor Yellow
}

function Invoke-Tool {
    <# Run an external command, returning its combined output as lines and
       leaving the exit code in $script:LastToolExit. #>
    param([string]$Exe, [string[]]$Arguments)
    # Start-Process joins ArgumentList with spaces and quotes nothing, so any
    # argument containing a space (a command string, a profile name, a path)
    # has to be quoted here or the tool sees it as several arguments
    $quoted = $Arguments | ForEach-Object {
        if ($_ -match '\s') { '"' + $_ + '"' } else { $_ }
    }
    $out = [System.IO.Path]::GetTempFileName()
    $err = [System.IO.Path]::GetTempFileName()
    $p = Start-Process -FilePath $Exe -ArgumentList $quoted -NoNewWindow -Wait `
        -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
    $script:LastToolExit = $p.ExitCode
    $lines = @()
    foreach ($f in @($out, $err)) {
        if (Test-Path $f) {
            $lines += Get-Content $f -ErrorAction SilentlyContinue
            Remove-Item $f -Force -ErrorAction SilentlyContinue
        }
    }
    return $lines
}

# devel install resolves extra-files against the process working directory,
# so this must run from the bundle directory or the wheel build fails
Set-Location $Bundle

# ---------------------------------------------------------------- 1. install
Write-Host "`n== install ==" -ForegroundColor Cyan
$installLog = Invoke-Tool $ChimeraX @("--nogui", "--exit", "--silent", "--cmd",
                                      "devel install $Bundle exit true")
$installOk = ($script:LastToolExit -eq 0) -and
             -not ($installLog | Select-String -Quiet "RuntimeError|Traceback")
if (-not $installOk) {
    Fail "install" "devel install did not succeed; everything below would test stale code"
    $installLog | Select-Object -Last 15 | ForEach-Object { Write-Host "      $_" }
} else {
    Pass "install"
}

# a successful-looking install that did not replace the files is the failure
# mode that cost the most time on this project, so check the bytes
$stale = @()
foreach ($f in Get-ChildItem "$Bundle\src" -Filter "*.py") {
    $target = Join-Path $Installed $f.Name
    if (-not (Test-Path $target)) { $stale += "$($f.Name) missing"; continue }
    $a = (Get-FileHash $f.FullName -Algorithm SHA256).Hash
    $b = (Get-FileHash $target -Algorithm SHA256).Hash
    if ($a -ne $b) { $stale += $f.Name }
}
if ($stale.Count -gt 0) {
    Fail "install matches source" ("stale installed files: " + ($stale -join ", "))
} else {
    Pass "install matches source"
}

# ------------------------------------------------------------------ 2. tests
Write-Host "`n== export tests ==" -ForegroundColor Cyan
Invoke-Tool $ChimeraX @("--nogui", "--exit", "--silent", "--script",
                        "$Bundle\tests\test_export.py") |
    Select-String -Pattern "pass|FAIL|TESTS:" | ForEach-Object { Write-Host "      $_" }

$resultsPath = "$Bundle\tests\out\results.json"
if (-not (Test-Path $resultsPath)) {
    Fail "export tests" "no results.json written - the suite did not finish"
} else {
    $results = Get-Content $resultsPath -Raw | ConvertFrom-Json
    if ($results.failed -gt 0) {
        Fail "export tests" "$($results.failed) of $($results.passed + $results.failed) checks failed"
    } else {
        Pass "export tests" "$($results.passed) checks"
    }
}

# ------------------------------------------------- 2b. geometry rules
Write-Host "`n== body rules on known shapes ==" -ForegroundColor Cyan
$bodyOut = Invoke-Tool $Python @("$Bundle\tests\test_bodies.py")
$bodyOut | Select-String -Pattern "pass|FAIL|BODY TESTS:" | ForEach-Object { Write-Host "      $_" }
if ($script:LastToolExit -ne 0) {
    Fail "body rules" "the printed-body rules disagree with known geometry"
} else {
    Pass "body rules"
}

# ---------------------------------------------------------------- 3. slicers
Write-Host "`n== slicer acceptance ==" -ForegroundColor Cyan
$painted = "$Bundle\tests\out\t_paint.3mf"
if (-not (Test-Path $PrusaSlicer)) {
    Skip "PrusaSlicer" "not installed"
} elseif (-not (Test-Path $painted)) {
    Fail "PrusaSlicer" "no painted export to test"
} else {
    $info = Invoke-Tool $PrusaSlicer @("--info", $painted)
    if ($info | Select-String -Quiet "manifold = yes") {
        Pass "PrusaSlicer loads the painted export" "(manifold)"
    } else {
        Fail "PrusaSlicer loads the painted export" "not manifold, or would not load"
    }

    $rt = "$Bundle\tests\out\rt_paint.3mf"
    if (Test-Path $rt) { Remove-Item $rt -Force }
    Invoke-Tool $PrusaSlicer @("--export-3mf", "--dont-arrange", "-o", $rt, $painted) | Out-Null
    if (Test-Path $rt) {
        $countScript = "$env:TEMP\save3mf_count_paint.py"
        @"
import zipfile, re, collections
z = zipfile.ZipFile(r'$rt')
d = z.read('3D/3dmodel.model').decode('utf8')
print(len(collections.Counter(re.findall(r'mmu_segmentation="([^"]*)"', d))))
"@ | Set-Content $countScript -Encoding utf8
        $kept = (Invoke-Tool $Python @($countScript) | Select-Object -Last 1)
        if ([int]$kept -ge 2) {
            Pass "PrusaSlicer preserves the painting" "($kept extruders)"
        } else {
            Fail "PrusaSlicer preserves the painting" "only $kept paint codes survived the round trip"
        }
    } else {
        Fail "PrusaSlicer round trip" "no file produced"
    }

    # a real slice: the only stage that catches placement and print-cost errors
    $gcode = "$env:TEMP\save3mf_test.gcode"
    if (Test-Path $gcode) { Remove-Item $gcode -Force }
    $slice = Invoke-Tool $PrusaSlicer @(
        "--slice", "--binary-gcode=0",
        "--printer-profile", "Original Prusa XL - 5T Input Shaper 0.4 nozzle",
        "--print-profile", "0.20mm SPEED @XLIS 0.4",
        "--material-profile", "Generic PLA @XLIS",
        "-o", $gcode, $painted)
    if (Test-Path $gcode) {
        Pass "PrusaSlicer slices it"
        $cost = Invoke-Tool $Python @("$Bundle\tools\check_cost_model.py",
                                      $painted, $gcode, "0.2")
        $cost | Select-String -Pattern "measured|regions per layer - 1|OK:|FAIL:" |
            ForEach-Object { Write-Host "      $_" }
        if ($script:LastToolExit -ne 0) {
            Fail "print-cost estimate" "drifted more than 5% from the slicer"
        } else {
            Pass "print-cost estimate"
        }
    } else {
        Fail "PrusaSlicer slices it" "no G-code produced"
        $slice | Select-Object -Last 5 | ForEach-Object { Write-Host "      $_" }
    }
}

$bambuExport = "$Bundle\tests\out\t_bambu.3mf"
$forks = @{ "Bambu Studio" = "C:\Program Files\Bambu Studio\bambu-studio.exe"
            "OrcaSlicer"   = "C:\Program Files\OrcaSlicer\orca-slicer.exe" }
foreach ($name in $forks.Keys) {
    $exe = $forks[$name]
    if (-not (Test-Path $exe)) { Skip $name "not installed"; continue }
    if (-not (Test-Path $bambuExport)) { Fail $name "no bambu-flavor export to test"; continue }
    $rt = "$Bundle\tests\out\rt_$($name -replace '\s','').3mf"
    if (Test-Path $rt) { Remove-Item $rt -Force }
    Invoke-Tool $exe @("--export-3mf=$rt", $bambuExport) | Out-Null
    if (-not (Test-Path $rt)) { Fail $name "no file produced"; continue }
    $script = "$env:TEMP\save3mf_count_fork.py"
    @"
import zipfile, re, collections
z = zipfile.ZipFile(r'$rt')
names = [n for n in z.namelist() if n.endswith('.model')]
d = ''.join(z.read(n).decode('utf8') for n in names)
print(len(collections.Counter(re.findall(r'paint_color="([^"]*)"', d))))
"@ | Set-Content $script -Encoding utf8
    $kept = (Invoke-Tool $Python @($script) | Select-Object -Last 1)
    if ([int]$kept -ge 2) {
        Pass "$name preserves the painting" "($kept extruders)"
    } else {
        Fail "$name preserves the painting" "only $kept paint codes survived"
    }
}

# ------------------------------------------------------------------ 4. wheel
Write-Host "`n== wheel ==" -ForegroundColor Cyan
if (Test-Path "$Bundle\dist") { Remove-Item "$Bundle\dist" -Recurse -Force }
Invoke-Tool $ChimeraX @("--nogui", "--exit", "--silent", "--cmd",
                        "devel build $Bundle exit true") | Out-Null
$wheel = Get-ChildItem "$Bundle\dist" -Filter "*.whl" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $wheel) {
    Fail "wheel" "devel build produced no wheel"
} else {
    $listScript = "$env:TEMP\save3mf_wheel_list.py"
    @"
import zipfile
print('\n'.join(zipfile.ZipFile(r'$($wheel.FullName)').namelist()))
"@ | Set-Content $listScript -Encoding utf8
    $contents = Invoke-Tool $Python @($listScript)
    $hasCode = $contents | Select-String -Quiet "chimerax/save3mf/writer3mf.py"
    $hasDocs = $contents | Select-String -Quiet "chimerax/save3mf/docs/user/commands/3mf.html"
    if ($hasCode -and $hasDocs) {
        Pass "wheel" "$($wheel.Name)"
    } else {
        Fail "wheel" ("missing " + $(if (-not $hasCode) { "code " } else { "" }) + $(if (-not $hasDocs) { "docs" } else { "" }))
    }
}

# ---------------------------------------------------------------- conclusion
Write-Host "`n== summary ==" -ForegroundColor Cyan
foreach ($s in $script:Skipped) { Write-Host "  skipped: $s" -ForegroundColor Yellow }
if ($script:Failures.Count -gt 0) {
    foreach ($f in $script:Failures) { Write-Host "  failed:  $f" -ForegroundColor Red }
    Write-Host "`nFAILED ($($script:Failures.Count))" -ForegroundColor Red
    exit 1
}
Write-Host "`nALL PASSED" -ForegroundColor Green
exit 0
