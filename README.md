# ChimeraX-Save3MF

A ChimeraX bundle that saves the current scene as a **3MF** file for 3D printing,
preserving the colouring you set up in ChimeraX as separately assignable parts
in the slicer.

```
save molecule.3mf size 80
```

Status: **complete through phase 5** — geometry, colour painting, printability
and print-cost reporting, Save-dialog options, docs, and a full test suite
verified against PrusaSlicer, Bambu Studio and OrcaSlicer.

## Install

```
devel install C:\Users\Erik\Desktop\chimerax-3mf
```

or headless:

```
& "C:\Program Files\ChimeraX 1.12\bin\ChimeraX-console.exe" --nogui --exit --cmd "devel install C:\Users\Erik\Desktop\chimerax-3mf exit true"
```

**Run it from the bundle directory.** `devel install` copies the documentation
files relative to the *process* working directory rather than the bundle path,
so from anywhere else the build fails and leaves an empty `src/docs` tree
wherever it was launched.

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
3mf palette [models SPEC] [maxColors N] [size N] [scale N] [layerHeight N]
```

Prints the colour regions the scene would produce and what each merge level
costs, on both axes that matter — how different it looks, and how long it
takes to print:

```
526 distinct colors across 814254 triangles; 269 layers at 0.20 mm
  merge to 4    ■■■■               ΔE 21.7   strong shift         ~638 tool changes
  merge to 8    ■■■■■■■■           ΔE 9.3    clearly different   ~1720 tool changes
  merge to 16   ■■■■■■■■■■■■■■■■   ΔE 4.7    slight shift        ~3672 tool changes
  no merge                         ΔE 0.0    526 parts          ~38434 tool changes
```

With `maxColors N` it shows that exact palette instead. Nothing is written —
pick a number, then pass it to `save`.

### Print cost

A multi-material print spends most of its time changing tools, and each change
purges filament into a wipe tower. What makes a colour expensive is not its
area but **how many layers it appears in**, since it forces a tool change on
each one. A part covering 0.4% of the model can drive 6% of the print time:

```
Part 5 (1a3n_D SES surface red) is 0.4% of the model but drives about 6% of the
tool changes, because it appears in 52 of 269 layers. Dropping it with
'maxColors 4' would save roughly 52 tool changes.
```

The estimate is parts-per-layer less one, summed over layers. Against real
PrusaSlicer output it lands within ~1%: 805 vs 811 actual at five colours, 506
vs 512 at three. [tools/check_cost_model.py](tools/check_cost_model.py)
re-checks it against any painted export and its G-code.

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
