# ChimeraX-Save3MF

A ChimeraX bundle that saves the current scene as a **3MF** file for 3D printing,
preserving the colouring you set up in ChimeraX as separately assignable parts
in the slicer.

```
save molecule.3mf size 80
```

Status: **phase 2 complete** — geometry and colour parts both work, verified
end to end in PrusaSlicer, Bambu Studio and OrcaSlicer.

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
              [maxColors N] [flavor prusa|bambu|generic] [check true|false]
```

- `models` — which models to export; default is everything displayed
- `scale` — millimetres per Ångström (default 1.0)
- `size` — scale so the longest edge is N mm; overrides `scale`
- `colors` — split the model into one part per colour (default true)
- `maxColors` — merge down to at most N parts; default is no merging
- `flavor` — which slicer the part structure targets (default `prusa`)
- `check` — run the printability check (default true)

The model sits in the positive octant with its lowest point at z = 0.
Coordinates must not go negative or slicers place the model off the bed.

### Colours become printable parts

Each distinct colour in the scene becomes a separate part with a pre-assigned
extruder, named after the drawing and the colour — `1a3n_A SES surface medium
slate blue` — so a slicer's part list says which chain is which.

Continuous colouring (rainbow, by B-factor) can produce hundreds of distinct
colours. `maxColors N` clusters them in CIELAB, weighted by triangle area, and
reports the mean colour shift:

```
526 distinct colors merged into 5 printable parts (mean color shift ΔE 16.6)
```

Each part's colour is always a real colour from the scene, never an averaged
one.

### Choosing the part count before exporting

```
3mf palette [models SPEC] [maxColors N]
```

Prints the colour regions the scene would produce, and what merging to each
part count would cost — as swatches in the log, with the perceptual error in
plain words:

```
526 distinct colors across 814254 triangles
  merge to 4    ■■■■               ΔE 21.7   strong shift
  merge to 8    ■■■■■■■■           ΔE 9.3    clearly different
  merge to 16   ■■■■■■■■■■■■■■■■   ΔE 4.7    slight shift
  no merge                         ΔE 0.0    526 parts, exactly as colored
```

With `maxColors N` it shows that exact palette instead. Nothing is written —
pick a number, then pass it to `save`.

## Layout

| Path | What |
|---|---|
| `pyproject.toml` | bundle declaration: the 3MF data format plus its save provider |
| `src/__init__.py` | `BundleAPI` / `SaverInfo` — wires `save x.3mf` to the writer |
| `src/scene.py` | walks displayed drawings, expands instances, welds vertices, scales to mm |
| `src/writer3mf.py` | builds the 3MF (OPC zip + `3D/3dmodel.model`) |
| `src/gui.py` | options shown in ChimeraX's Save dialog |
| `src/cmd.py` | the `3mf palette` preview command |
| `src/printcheck.py` | printability report (never modifies geometry) |
| `docs/commands/3mf.html` | user documentation, installed into ChimeraX help |
| `probes/` | phase 0.5 slicer experiments and [RESULTS.md](probes/RESULTS.md) |
| `tools/` | probe generator, 3MF validator, 3MF inspector |
| `tests/` | headless test scripts |

## Testing

```
& "C:\Program Files\ChimeraX 1.12\bin\ChimeraX-console.exe" --nogui --exit --silent tests\test_basic.cxc
& "C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe" --info tests\out\surface.3mf
& "C:\Program Files\ChimeraX 1.12\bin\python.exe" tools\inspect_3mf.py tests\out\surface.3mf
```

Note: the `python` on PATH is the Microsoft Store stub and does not run.
Use ChimeraX's bundled interpreter as above.

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
