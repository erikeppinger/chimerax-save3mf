# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A ChimeraX bundle that saves the displayed scene as a 3MF file for 3D printing,
carrying ChimeraX colours through as per-triangle extruder painting so a
multi-material slicer opens the file already assigned.

## Commands

There is no system Python: the `python` on PATH is the Microsoft Store stub and
does not run. Use ChimeraX's interpreter for every script.

```powershell
# install the bundle (MUST be run from the bundle directory - see Gotchas)
cd C:\Users\Erik\Desktop\chimerax-3mf
& "C:\Program Files\ChimeraX 1.12\bin\ChimeraX-console.exe" --nogui --exit --silent --cmd "devel install . exit true"

# full test run: install integrity, export tests, slicer acceptance, wheel
.\tests\run_all.ps1

# just the export suite (17 checks); writes tests/out/results.json
& "C:\Program Files\ChimeraX 1.12\bin\ChimeraX-console.exe" --nogui --exit --silent --script tests\test_export.py

# build a wheel into dist/
& "C:\Program Files\ChimeraX 1.12\bin\ChimeraX-console.exe" --nogui --exit --silent --cmd "devel build . exit true"
```

To run one test, edit the `TESTS` list at the bottom of `tests/test_export.py`;
the suite is a plain list of functions, not a framework.

Inspection and validation of any 3MF:

```powershell
& "C:\Program Files\ChimeraX 1.12\bin\python.exe" tools\validate_3mf.py <file.3mf>
& "C:\Program Files\ChimeraX 1.12\bin\python.exe" tools\inspect_3mf.py <file.3mf>
```

Re-measuring the two empirical models (both slice for real, minutes not seconds):

```powershell
& "C:\Program Files\ChimeraX 1.12\bin\python.exe" tools\calibrate_time.py      # seconds per tool change
& "C:\Program Files\ChimeraX 1.12\bin\python.exe" tools\check_time_model.py    # model vs those measurements
& "C:\Program Files\ChimeraX 1.12\bin\python.exe" tools\check_cost_model.py <file.3mf> <file.gcode>
```

## Architecture

The export is a pipeline, one module per stage, all under `src/`:

```
scene.collect_geometry    walk displayed drawings -> triangle soup + colour per triangle
scene.weld_vertices       merge coincident vertices so the mesh is connected
scene.place_for_printing  scale to mm, move into the positive octant
colors.build_regions      group triangles by colour, cluster in CIELAB if asked
printcheck.analyze        measure printability (never modifies geometry)
printcost.estimate        tool changes and the time they cost
writer3mf.write_3mf       assemble the OPC zip
```

`__init__.py` is only wiring: `BundleAPI.run_provider` returns a `SaverInfo`
whose `save_args` defines the command keywords, and `register_command` hands
`3mf palette` to `cmd.py`. `gui.py` is the Save-dialog widget and exists only
to build a `save` argument string.

### The central design fact

Slicers disagree irreconcilably about multi-part colour, and the *geometry
layout* alone decides which one understands a file — extra metadata cannot
bridge it. `probes/RESULTS.md` records the experiments that established this
and is the first thing to read before changing `writer3mf.py`.

The exporter writes colour as per-triangle painting on one watertight mesh
(`_painted_package`), which is what slicers' own paint tools produce:
`slic3rpe:mmu_segmentation` for PrusaSlicer, `paint_color` for Bambu/Orca,
identical encoding. Splitting geometry into per-colour parts also works
(`_prusa_package`, `_bambu_package`, reached by `paint false` or automatically
above 15 colours) but leaves open edges between patches and a repair warning on
each one.

### Facts established by experiment, not documentation

These cost real time to discover. Do not "correct" them from a spec or a blog
post without re-running the probes.

- **The published MMU encoding tables are off by one.** Extruder N is
  `MMU_CODES[N]` (`["0", "4", "8", "0C", "1C", ...]`), index 0 meaning
  unpainted. Verified by slicing slabs of known volume ratio (probe H).
- **Colours beyond the printer's tool count do not wrap around** — they all
  print with filament 1, silently. Verified by reading tool changes per Z band
  out of real G-code (probe I). This is why print time plateaus past ~5 colours
  and why `printcost` models a tool count.
- **PrusaSlicer ignores `m:colorgroup` and `basematerials`** on import; both
  are written anyway for generic viewers, harmlessly.
- **18.4 s per tool change** on an Original Prusa XL at 0.20 mm, fitted over
  eight colour counts. The tool-change count itself is extruders-per-layer less
  one, summed over layers, which matches G-code within ~1%.

## Gotchas

- **`devel install` must run from the bundle directory.** It resolves the
  `[chimerax.extra-files]` globs against the *process* working directory, so
  from elsewhere the wheel build fails and an empty `src/docs` tree is left
  wherever ChimeraX was launched. A failed install leaves the previous version
  installed, so tests then pass against stale code — `tests/run_all.ps1`
  checks installed bytes against `src/` for exactly this reason.
- **Flush graphics before reading drawings.** ChimeraX commands mark the scene
  changed but rebuild drawings on the next frame, and nothing draws a frame in
  `--nogui`. `scene._flush_pending_graphics` exists because an export right
  after `hide atoms` otherwise contained the hidden atoms.
- **Coordinates must never go negative.** A slicer takes them literally and
  puts the model off the bed. Only a real slice catches this; round trips do
  not, because the GUI loader auto-arranges.
- **PowerShell 5.1: never `2>&1` a native command.** Each stderr line becomes
  an ErrorRecord and `$?` goes false even on success. `tests/run_all.ps1` uses
  `Invoke-Tool`, which redirects to files; it also quotes every argument
  containing a space, since `Start-Process -ArgumentList` quotes nothing.
- **Verify against the slicers, not assumptions.** Every format claim in this
  repository was checked by round-tripping through PrusaSlicer, Bambu Studio
  and OrcaSlicer CLIs, and the important ones by slicing to G-code.
- **Help topics need the `help:` prefix.** `help 3mf` works (ChimeraX derives
  `help:user/commands/3mf.html` from the command's first word), and so does
  `open help:user/commands/3mf.html`, but a bare path is read as a command
  name and reports "No help found". Bundle commands do not appear in Help →
  User Guide's index in 1.12: the injection looks for a `<div id="clist">`
  that the shipped index page lacks.

## Testing philosophy

Tests assert on exported files, not internal state. The suite was itself
validated by mutation: reintroducing the negative-coordinate bug failed 7 of
17 checks with the correct diagnosis. There is no XSD validation — no schema
ships with the project and hand-writing one would be theatre;
`tools/validate_3mf.py` checks what has actually gone wrong here instead.
