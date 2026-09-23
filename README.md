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

## Layout

| Path | What |
|---|---|
| `pyproject.toml` | bundle declaration: the 3MF data format plus its save provider |
| `src/__init__.py` | `BundleAPI` / `SaverInfo` — wires `save x.3mf` to the writer |
| `src/scene.py` | walks displayed drawings, expands instances, welds vertices, scales to mm |
| `src/writer3mf.py` | builds the 3MF (OPC zip + `3D/3dmodel.model`) |
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
| `prusa` (default) | one mesh, regions as triangle ranges in `Slic3r_PE_model.config` | PrusaSlicer |
| `bambu` | component parts with `model_settings.config` | Bambu Studio, OrcaSlicer |
| `generic` | geometry and colour tags only, no slicer config | any 3MF reader |

## Printability check

Every export runs a check and reports problems to the log — disconnected
pieces, loose fragments, non-watertight meshes, features too thin to print.
It never modifies geometry; pass `check false` to silence it.

Preparing a structure for printing (struts between disjoint pieces, thickened
ribbons, solvent removal) is what the
[NIH 3D print presets](https://cxtoolshed.rbvi.ucsf.edu/apps/chimeraxnihpresets)
bundle is for. The exporter just tells you when you need it.
