# ChimeraX-Save3MF

<img src="docs/icon/save3mf-wordmark.png" alt=".3mf" height="64">

Save a ChimeraX scene as a **3MF** file for 3D printing, with the colours you
set up in ChimeraX carried through as painted extruders — so a multi-material
slicer opens the file with each chain already assigned to its own filament.

```
save molecule.3mf size 80
```

It also tells you what a slicer will make of the geometry *before* you print —
how many objects it will really produce, which bits are interior cavities,
which are genuinely loose, and what each colour costs in print time. ChimeraX
scenes are built from abutting and overlapping surfaces rather than one
stitched mesh, and the report is written around that.

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

## Which printer is this for?

Both kinds, but they need different files — pick with `flavor`:

| Your printer | Use | What the file carries |
|---|---|---|
| **Multi-filament** (MMU, toolchanger, AMS) | `flavor prusa` (default) or `flavor bambu` | each colour painted onto the triangles as an extruder assignment, up to 15 |
| **Full colour** (inkjet, binder jet, PolyJet) | `flavor fullcolor` | a colour at every vertex, interpolated across each triangle — continuous colouring such as `mlp` or B-factor survives intact |
| **Single filament** | any, colour is simply ignored | plain geometry |

`flavor fullcolor` has no colour limit and does no clustering: it writes the
scene's colours as they are. The older name `generic` still works and means
the same thing.

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

## Documentation inside ChimeraX

The bundle installs a help page. Reach it with:

```
help 3mf
```

or `help 3mf palette` to land on that command's section, or
`open help:user/commands/3mf.html` for the page directly.

A second page, **Printing protein models**, is linked from the first (or
`open help:user/commands/3mf-printing.html`). It walks ubiquitin (1ubq) from
the PDB to a four-colour print — NIH preset, checking the supports, colouring,
preview, export, Support Optimizer, slicer — with every command clickable, and
collects practical tips per representation and the slicer settings that act on
painted files. The same steps are in
[`examples/1ubq-print.cxc`](examples/1ubq-print.cxc).

Note the `help:` prefix in the last form: without it ChimeraX reads the
argument as a command name and reports "No help found".

The page is **not** listed in Help → User Guide's command index. That is a
ChimeraX limitation rather than a packaging fault — the code that adds bundle
commands to that index looks for a `<div id="clist">` which 1.12's index page
does not contain, so no bundle's commands appear there. `help 3mf` is the
route that works.

## Command

```
save PATH.3mf [models SPEC] [scale N] [size N] [colors true|false]
              [maxColors N] [flavor prusa|bambu|fullcolor] [paint true|false]
              [smoothness MM|off] [check true|false]
```

- `models` — which models to export; default is everything displayed
- `scale` — millimetres per Ångström (default 1.0)
- `size` — scale so the longest edge is N mm; overrides `scale`
- `colors` — carry the scene's colours into the file (default true)
- `maxColors` — merge down to at most N colours; default is no merging
- `flavor` — what kind of printer the file is for (default `prusa`)
- `paint` — paint extruders per triangle (default), or `false` to split the
  mesh into named parts instead
- `smoothness` — deepest flat facet allowed at print size, in mm (default
  0.05); `off` exports exactly what is drawn. See [Smoothness](#smoothness)
- `check` — run the printability check (default true)

The model sits in the positive octant with its lowest point at z = 0.
Coordinates must not go negative or slicers place the model off the bed.

### Smoothness

ChimeraX tessellates for the screen: a pseudobond is a 10-sided cylinder, a
ribbon tube a dozen sides around. Scaled up for printing, those flats become
features — a 0.6 Å support at 200 mm is a 3.5 mm-radius prism whose flats sit
0.17 mm inside the circle, nearly a full 0.2 mm layer, and they show in the
print.

So each export measures how deep the flats are **at the chosen size** and,
where they exceed `smoothness` (0.05 mm by default), raises the sides and
triangles of just those kinds of geometry, exports, and restores the previous
settings — the display is left as it was. The log says so *before* the file is
written:

```
Smoothing for print. At 5.82 mm/Å the flat facets ChimeraX draws would be up
to 0.17 mm deep (supports 0.17 mm, ribbons 0.10 mm), more than the 0.05 mm
target. Exporting with supports 10 → 20 sides, ribbons 16 → 24 sides,
20 → 30 divisions (about 39,008 → 86,888 triangles). The display is left as
it is; smoothness off exports exactly what is on screen.
```

`3mf palette` at the same `size` shows this in advance without writing
anything. A small print needs nothing: the same model at 100 mm is already
within the target and is exported as drawn.

The depth is measured from the mesh rather than predicted from settings: for
two triangles meeting at a crease angle θ, a face of width *h* across the edge
sits at most *h*·θ/8 inside the curve it approximates (corners sharper than
60°, such as a ribbon's rim, are real edges and not counted). Atoms, bonds,
pseudobonds and ribbons are smoothed through ChimeraX's level-of-detail
settings; molecular and map surfaces keep the resolution they were computed at,
so for those the log reports the depth and suggests recomputing them finer.

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

Two limits worth knowing, both specific to **filament** printers. A slicer can
paint at most **15** extruders; above that the exporter splits the mesh into
parts instead and says so. And a file can paint more extruders than your
printer has tools — the surplus then prints with filament 1 and the slicer
says nothing, so the exporter warns above five.

Neither applies to `flavor fullcolor`, which writes every colour as it is.

### Choosing the part count before exporting

```
3mf palette [models SPEC] [maxColors N] [size N] [scale N]
            [layerHeight N] [tools N] [smoothness MM|off]
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
| `src/smoothness.py` | flat-facet depth at print size, and finer tessellation for the export |
| `src/log.py` | log messages with clickable help links |
| `docs/commands/3mf.html` | user documentation, installed into ChimeraX help |
| `docs/commands/3mf-printing.html` | worked example (1ubq) and printing tips, installed alongside |
| `examples/1ubq-print.cxc` | the worked example as a ChimeraX script |
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

Every export reports what a slicer will make of the geometry. It never modifies
anything; pass `check false` to silence it.

**ChimeraX scenes are almost never stitched together**, and the report is built
around that fact. A ribbon is a separate surface per helix, strand and coil;
atoms are separate spheres; bond cylinders are open-ended tubes. These abut or
overlap instead of sharing vertices, so counting *topologically* separate
surfaces says nothing useful — a plain ribbon would look like "20 pieces that
do not touch" when it is one solid object.

What is measured instead:

- **Printed bodies** — surfaces that come within about an extrusion width fuse
  in the print, so they are counted as one body however the mesh is built.
  600 overlapping atom spheres are one object, and the report says so.
- **Interior cavities** — a closed surface wound inside-out bounds a void, not
  a solid. Density-map surfaces routinely contain them. Slicers fill what lies
  inside an odd number of surfaces, so a cavity simply stays hollow; it is not
  a loose fragment and costs no filament.
- **Genuinely loose pieces** — only geometry that touches nothing else, such
  as a water or an ion sitting in space, is reported as printing separately.
- **Open surfaces** — reported as a fact with its usual cause, not as an
  alarm: bond cylinders have no end caps and clipped surfaces are cut open.
- **Extreme sizes and thin features** — below what a 0.4 mm nozzle can hold,
  or larger than most build plates.

For example, a plain ribbon now reads:

```
One connected body, built from 20 separate surfaces that touch or overlap.
ChimeraX draws ribbons, atoms and bonds as separate pieces; a slicer fuses
anything closer than about 0.4 mm, so this prints as one object.
```

and a density map with internal voids:

```
One connected body; it will print as one object.
3 interior cavities (surfaces wound inside-out, such as voids in a density
map). Slicers leave these hollow; they cost no filament.
```

Still worth watching: ChimeraX shows cartoon by default, so adding a surface
leaves the ribbon sealed inside it. That geometry is invisible in the print
and still gets sliced — on 1a3n, 814k triangles and 9.6 MB versus 538k and
6.3 MB after `hide cartoon`.

Preparing a structure for printing (struts between disjoint pieces, thickened
ribbons, solvent removal) is what the
[NIH 3D print presets](https://cxtoolshed.rbvi.ucsf.edu/apps/chimeraxnihpresets)
bundle is for. The exporter just tells you when you need it.

After applying a preset, look over the supports it adds before exporting. It
draws hydrogen bonds as thick cylinders and adds struts where pieces need
holding together; most help, but an occasional one is badly placed for
printing — pinning a terminus at an awkward angle, say, or creating an
overhang that needs support material. Hover over it to see which two atoms it
joins, then remove it by naming them. For ubiquitin (PDB 1ubq), for example,
the hydrogen bond between Met1 N and Val17 O:

```
delete pbonds /A:1@N /A:17@O
```

or, for any structure, Ctrl+click the support and use `delete pbonds sel`. To keep it in the session but out
of the file, hide it instead (`hide /A:1@N /A:17@O pbonds`) — only what is
displayed is exported. `delete pbonds` removes every pseudobond whose two ends
are both in the specification, so a residue-level spec such as `/A:1,17`
removes all supports between those residues.

## Related

**[Support Optimizer](https://github.com/erikeppinger/support-optimizer)** —
a browser-only tool for preparing molecular structures and meshes for
printing. It picks up where this bundle leaves off: it reads the `.3mf` (or
`.stl`) written here, seals interior cavities so support material cannot get
trapped in them, searches for an orientation that minimises overhangs, and
previews the support paths before you commit to a slice.

The two fit together as a pipeline:

```
ChimeraX  →  save x.3mf  →  Support Optimizer  →  slicer
            colour + diagnostics   orientation, cavities, supports
```

Worth knowing about the handover: the cavities this bundle *reports* are
exactly the ones Support Optimizer can *seal*. A density-map surface with
internal voids slices fine either way, but sealing them first avoids support
material being generated inside a space you can never reach.

## Licence

[MIT](LICENSE). ChimeraX itself is separately licensed by UCSF.
