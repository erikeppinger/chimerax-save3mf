# ChimeraX-Save3MF

Save a ChimeraX scene as a **3MF** file for 3D printing, with the colours you
set up in ChimeraX carried through as painted extruders — so a multi-material
slicer opens the file with each chain already assigned to its own filament.

```
save molecule.3mf size 80
```

It also tells you what a slicer will make of the geometry *before* you print:
disconnected pieces, meshes that are not watertight, geometry sealed
invisibly inside other geometry, and what each colour costs in print time.

Verified end to end against **PrusaSlicer**, **Bambu Studio** and
**OrcaSlicer**: the exports load, keep their painting through a round trip,
and slice with one filament per chain.

> **Built with AI assistance.** This bundle was written by Claude (Anthropic)
> working with Erik Eppinger, and every commit carries a `Co-Authored-By`
> trailer saying so. The file-format decisions were not taken from
> documentation — 3MF colour handling is barely documented and the published
> encoding tables are wrong — but established by experiment against the three
> slicers, with the probe files and results kept in
> [`probes/`](probes/RESULTS.md) so anyone can re-run them. The print-time
> figures are measured, and [the test suite](#testing) is itself checked by
> mutation. Please still read the code before trusting it with a nine-hour
> print.

## Install

Requires ChimeraX 1.9 or later (developed against 1.12). Clone the repository,
then from the ChimeraX command line:

```
cd /path/to/chimerax-save3mf
devel install /path/to/chimerax-save3mf
```

or headless:

```bash
& "C:\Program Files\ChimeraX 1.12\bin\ChimeraX-console.exe" --nogui --exit --cmd "devel install . exit true"
```

**Run it from the bundle directory** — note the `cd` above. `devel install`
resolves the documentation file globs against the *process* working directory
rather than the bundle path, so from anywhere else the wheel build fails and
leaves an empty `src/docs` tree wherever it was launched.

A prebuilt wheel can be made with `devel build` and installed with
`toolshed install <wheel>`.

## Command

```
save PATH.3mf [models SPEC] [scale N] [size N] [colors true|false]
              [maxColors N] [flavor prusa|bambu|generic] [paint true|false]
              [check true|false]
```

- `models` — which models to export; default is everything displayed
- `scale` — millimetres per Ångström (default 1.0)
- `size` — scale so the longest edge is N mm; overrides `scale`
- `colors` — carry the scene's colours into the file (default true)
- `maxColors` — merge down to at most N colours; default is no merging
- `flavor` — which slicer the file targets (default `prusa`)
- `paint` — paint extruders per triangle (default), or `false` to split the
  mesh into named parts instead
- `check` — run the printability check (default true)

The model sits in the positive octant with its lowest point at z = 0.
Coordinates must not go negative or slicers place the model off the bed.

### Colours become printable colours

Each distinct colour in the scene becomes an extruder painted onto those
triangles, so a multi-tool printer needs no manual assignment: open the file
and the chains are already painted.

Continuous colouring (rainbow, by B-factor) can produce hundreds of distinct
colours. `maxColors N` clusters them in CIELAB, weighted by triangle area, and
reports the mean colour shift:

```
526 distinct colors merged into 5 printable parts (mean color shift ΔE 16.6)
```

Each colour is always a real colour from the scene, never an averaged one.

Two limits worth knowing. A slicer can paint at most **15** extruders; above
that the exporter splits the mesh into parts instead and says so. And a file
can paint more extruders than your printer has tools — the surplus then prints
with filament 1 and the slicer says nothing, so the exporter warns above five.

### Choosing the part count before exporting

```
3mf palette [models SPEC] [maxColors N] [size N] [scale N]
            [layerHeight N] [tools N]
```

Prints the colour regions the scene would produce and what each merge level
costs, on both axes that matter — how different it looks, and how much print
time it adds:

```
526 distinct colors across 814254 triangles; 307 layers at 0.20 mm,
about 3h 57m spent changing tools (774 changes on a 5-tool printer)
  merge to 2    ■■                 ΔE 32.5   strong shift        +1h 28m changing tools
  merge to 4    ■■■■               ΔE 21.7   strong shift        +3h 15m changing tools
  merge to 5    ■■■■■              ΔE 16.6   strong shift        +4h 40m changing tools
  merge to 8    ■■■■■■■■           ΔE 9.3    clearly different   +5h 44m changing tools
  no merge                         ΔE 0.0    526 parts           +3h 57m changing tools
```

With `maxColors N` it shows that exact palette instead. Nothing is written —
pick a number, then pass it to `save`.

### Print cost

A multi-material print spends most of its time changing tools, and each change
purges filament into a wipe tower. What makes a colour expensive is not its
area but **how many layers it appears in**, since it forces a tool change on
each one. A part covering 0.4% of the model can cost half an hour:

```
Part 5 (1a3n_D SES surface red) is 0.4% of the model but costs about 16m of
tool changes, because it appears in 52 of 269 layers. Dropping it with
'maxColors 4' would get that time back.
```

The figure counts **only the time spent changing tools**, not the whole print:
extrusion time depends on a print profile this bundle knows nothing about.

Two measured numbers sit behind it. A tool change on an Original Prusa XL at
0.20 mm costs **18.4 s** — fitted from slicing the same scene at eight
different colour counts, worst point 4.1% off the line
([tools/calibrate_time.py](tools/calibrate_time.py) re-measures it; an MMU
that rewinds and purges is much slower). And tool changes themselves are
estimated as extruders-per-layer less one, summed over layers, which matches
real G-code within ~1%.

Colours beyond the printer's tool count add no time at all, because they print
with filament 1 — the same behaviour probe I found, visible in the ladder as
the plateau past 5. Use `tools N` if your printer differs.

[tools/check_time_model.py](tools/check_time_model.py) re-checks the whole
chain against the calibration runs.

## Layout

| Path | What |
|---|---|
| `pyproject.toml` | bundle declaration: the 3MF data format plus its save provider |
| `src/__init__.py` | `BundleAPI` / `SaverInfo` — wires `save x.3mf` to the writer |
| `src/scene.py` | walks displayed drawings, expands instances, welds vertices, scales to mm |
| `src/writer3mf.py` | builds the 3MF (OPC zip + `3D/3dmodel.model`) |
| `src/gui.py` | options shown in ChimeraX's Save dialog |
| `src/cmd.py` | the `3mf palette` preview command |
| `src/colors.py` | colour regions, CIELAB clustering, palette rendering |
| `src/printcheck.py` | printability report (never modifies geometry) |
| `src/printcost.py` | tool-change estimate behind the print-cost flag |
| `docs/commands/3mf.html` | user documentation, installed into ChimeraX help |
| `probes/` | slicer experiments and [RESULTS.md](probes/RESULTS.md) — why the file looks the way it does |
| `tools/` | probe generators, 3MF validator and inspector, cost-model check |
| `tests/` | `run_all.ps1` driver, headless export suite, widget and palette captures |

## Testing

```bash
.\tests\run_all.ps1
```

Four stages, each of which fails the run:

| Stage | What it proves |
|---|---|
| **install** | `devel install` succeeded **and** the installed bytes match `src/` — a failed build silently leaves the old version in place, so a whole run can otherwise pass against stale code |
| **export tests** | 17 checks over real exported files: geometry matches ChimeraX's own STL export, `size` is exact, nothing sits at negative coordinates, painting covers every triangle, split parts tile the mesh with no gaps, the >15-colour fallback works, an empty scene errors clearly |
| **slicers** | PrusaSlicer loads the painted export as manifold, preserves the painting through a round trip and **actually slices it**; Bambu Studio and OrcaSlicer preserve `paint_color`. The tool-change estimate is checked against the real G-code and must stay within 5% |
| **wheel** | `devel build` produces a wheel containing both the package and its documentation |

Slicers that are not installed are skipped, not failed.

The real slice matters: the negative-coordinate bug passed every round-trip
check and was caught only by slicing, because PrusaSlicer's GUI loader
auto-arranges and hides the problem.

Individual pieces can be run on their own:

```bash
& "C:\Program Files\ChimeraX 1.12\bin\ChimeraX-console.exe" --nogui --exit --silent --script tests\test_export.py
```

```bash
& "C:\Program Files\ChimeraX 1.12\bin\python.exe" tools\validate_3mf.py tests\out\t_paint.3mf
```

Note: the `python` on PATH is the Microsoft Store stub and does not run.
Use ChimeraX's bundled interpreter as above.

### A note on the suite itself

It was checked by mutation: reintroducing the negative-coordinate bug made 7
of the 17 checks fail with the right diagnosis. A suite that has never failed
has not been tested.

## Slicer notes

PrusaSlicer, Bambu Studio and OrcaSlicer disagree about how multi-part colour
information is carried in 3MF, and no single file satisfies all of them — the
geometry layout alone decides it, so no amount of extra metadata bridges the
gap. That is what `flavor` selects between; see
[probes/RESULTS.md](probes/RESULTS.md) for the experiments behind it.

| `flavor` | Layout | Honoured by |
|---|---|---|
| `prusa` (default) | one mesh, extruder painted per triangle (`slic3rpe:mmu_segmentation`) | PrusaSlicer |
| `bambu` | one mesh, extruder painted per triangle (`paint_color`) | Bambu Studio, OrcaSlicer |
| `generic` | geometry and colour tags only, no slicer data | any 3MF reader |

### Painting, not splitting

Colours are written as **per-triangle extruder painting** — the same mechanism
a slicer's own multi-material paint tool uses. The mesh stays whole, so there
is nothing for the slicer to repair.

The alternative, splitting the mesh into one part per colour, leaves every
patch edged with open boundaries and a repair warning on every part. Pass
`paint false` to get that layout anyway; it is also the automatic fallback
above 15 colours, which is the most a slicer can paint.

## Printability check

Every export runs a check and reports problems to the log. It never modifies
geometry; pass `check false` to silence it.

- **disconnected pieces** — whether the model is one body, or loose fragments
  (waters, ions) around a solid one
- **not watertight** — open or non-manifold edges, which slicers will try to
  repair unpredictably
- **sealed-in geometry** — pieces fully enclosed inside another piece, which
  print but can never be seen
- **thin features** — pieces below what a 0.4 mm nozzle can hold

The sealed-in check is worth the most in practice. ChimeraX shows cartoon by
default, so adding a surface on top leaves the ribbon inside it — invisible in
the print, but still sliced:

```
47 pieces (240628 triangles, 30% of the model) are sealed inside another piece
and will never be visible, but still cost print time and filament.
```

On 1a3n that is 814k triangles and 9.6 MB versus 538k and 6.3 MB after
`hide cartoon` — a third of the print, for nothing.

Preparing a structure for printing (struts between disjoint pieces, thickened
ribbons, solvent removal) is what the
[NIH 3D print presets](https://cxtoolshed.rbvi.ucsf.edu/apps/chimeraxnihpresets)
bundle is for. The exporter just tells you when you need it.

## Licence

[MIT](LICENSE). ChimeraX itself is separately licensed by UCSF.
