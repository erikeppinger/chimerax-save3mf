# Phase 0.5 — slicer probe results

Tested 2026-09-23 against **PrusaSlicer 2.9.6** (Windows), headless via
`prusa-slicer-console.exe`. Each probe is the same shape: three stacked
30×30×10 mm slabs (red / green / blue), 36 triangles. Only the way colour is
expressed differs.

Method: round-trip each probe through `--export-3mf`, then read back what
PrusaSlicer wrote (`tools/inspect_3mf.py`). What survives the round trip is
exactly what PrusaSlicer understood on import.

## Results

| Probe | Colour expressed as | PrusaSlicer 2.9.6 result |
|---|---|---|
| **A** | `m:colorgroup` (Materials extension), per triangle | **Ignored.** Collapsed to 1 object / 1 volume, no colour, no extruders |
| **B** | 3 `<component>` children, each with `basematerials` | **3 separate objects.** Names survive, but each object is dropped to the bed independently — the assembly falls apart (all three landed at the same spot with the CLI default `--ensure-on-bed`) |
| **C** | one mesh + `Metadata/Slic3r_PE_model.config` volumes with `extruder` | **Exact.** 1 object, 3 named volumes, extruders 1/2/3 preserved, geometry untouched (z 0..30, identity transform) |
| **D** | core-spec `basematerials` referenced per triangle | **Ignored.** Same as A |
| **E** | C + colorgroup + basematerials together | **Exact, same as C.** The extra colour tags are harmless to PrusaSlicer |
| **F** | components + `Metadata/model_settings.config` parts (Bambu-native) | **Prusa: 3 separate objects, no extruders.** Bambu/Orca: exact |
| **G** | F + Prusa volume config + colour tags (universal attempt) | **Prusa: still 3 separate objects, no extruders.** Bambu/Orca: exact |

## End-to-end proof

Probe E sliced with *Original Prusa XL – 5T Input Shaper 0.4 nozzle*,
`0.20mm SPEED @XLIS 0.4`, `Generic PLA @XLIS`:

```
; filament used [g] = 5.28, 4.64, 3.99, 0.00, 0.00
```

Three extruders used, one per colour region, in the assigned order — the
colour split reaches the G-code without a single manual click.

## Bambu Studio 2.x / OrcaSlicer (tested 2026-09-23, same method)

Both are PrusaSlicer forks but have diverged completely on this point.

| Input | Bambu Studio / OrcaSlicer result |
|---|---|
| Probe E (Prusa volumes + colour tags) | **Collapsed to 1 part, extruder 1.** Both `Slic3r_PE_model.config` and `m:colorgroup` ignored |
| Probe F (components + `model_settings.config`) | **Exact.** 1 object, 3 named parts, extruders 1/2/3, stack positions preserved |
| Probe G (both configs at once) | Same as F — exact in Bambu/Orca, still broken in Prusa |

Caveat: Bambu's "Standard 3MF Color Parsing" is a GUI dialog, so the CLI may
skip `m:colorgroup` parsing that the GUI would offer. Untested. It costs
nothing to keep writing the colour tags either way.

## Probe H: painting beats splitting (tested 2026-09-23)

Splitting a mesh into one volume per colour works, but every patch is then
edged with open boundaries. PrusaSlicer flags each part with a repair warning,
and a real export of 1a3n showed exactly that — eight parts, eight warnings.

Slicers have a purpose-built mechanism for this: **per-triangle extruder
painting**, which is what their own multi-material paint tool writes. The mesh
stays whole.

| | Attribute | Namespace |
|---|---|---|
| PrusaSlicer | `slic3rpe:mmu_segmentation` | `http://schemas.slic3r.org/3mf/2017/06` |
| Bambu Studio / OrcaSlicer | `paint_color` | none |

A triangle painted entirely with one extruder carries a short code. **The
published tables are off by one**, so probe H was sliced to settle it: three
slabs of volume ratio 1:2:3, painted with codes `4`, `8`, `0C`, produced

```
; filament used [g] = 3.02, 4.64, 5.44, 0.00, 0.00
```

— smallest slab on extruder 1, largest on extruder 3. So the mapping is
**extruder N → `MMU_CODES[N]`**, with index 0 meaning unpainted:

```
["0", "4", "8", "0C", "1C", "2C", "3C", "4C",
 "5C", "6C", "7C", "8C", "9C", "AC", "BC", "CC"]
```

Both families use the identical encoding, differing only in attribute name.
Round-tripping a real painted export gave back the same codes on the same
triangles in all three slicers, one volume, `manifold = yes`, and the sliced
G-code used one filament per chain.

Limit: 15 painted extruders. Above that the exporter falls back to split parts
and says why.

## There is no universal layout

The two families need mutually exclusive *geometry* layouts, which no amount of
extra metadata can bridge:

- **PrusaSlicer** needs **one object, one merged mesh**, regions declared as
  triangle ranges in `Slic3r_PE_model.config`. Given components, it makes
  separate objects and drops each to the bed.
- **Bambu / Orca** need **components**, one per region, with parts declared in
  `model_settings.config`. Given a merged mesh, they see one part; they have no
  triangle-range concept at all.

Probe G proved this directly: carrying both config files changes nothing,
because the geometry layout alone decides the outcome.

**So the exporter needs a `flavor` option** — `prusa` (default, probe E layout)
or `bambu` (probe F layout, also correct for Orca). Colour tags
(`m:colorgroup` + `basematerials`) are written in both flavours since they are
harmless everywhere and useful to generic viewers.

## Decision

**In `flavor prusa` (default) the exporter writes probe E's structure:**

1. **One `<object>`, one mesh**, triangles sorted so that each colour region is a
   contiguous run.
2. **`Metadata/Slic3r_PE_model.config`** — one `<volume>` per colour region with
   its triangle range, a readable `name`, and an `extruder` number.
   This is the only thing PrusaSlicer honours, and it honours it perfectly.
3. **`m:colorgroup` + `basematerials`** alongside it — ignored by PrusaSlicer,
   read by Bambu Studio's standard 3MF colour parsing, and used by generic
   3MF viewers.

Rejected for the Prusa flavour: `<component>`-based splitting (probes B, F, G).
It produces separate objects that PrusaSlicer drops to the bed individually,
which destroys the assembly.

**In `flavor bambu` the exporter writes probe F's structure:** one component
object per colour region inside a wrapper object, with
`Metadata/model_settings.config` naming each part and assigning its extruder.

## Still to verify

- Whether the GUI import path behaves like the CLI (expected yes; same loader).
- Whether Bambu's GUI colour-parsing dialog picks up `m:colorgroup` in files
  that have no `model_settings.config`.
- ~~Extruder numbers above the printer's extruder count~~ — answered by probe I
  below: they silently collapse onto filament 1.

## Reproducing

```
& "C:\Program Files\ChimeraX 1.12\bin\python.exe" tools\make_probes.py
& "C:\Program Files\ChimeraX 1.12\bin\python.exe" tools\check_probes.py
& "C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe" --export-3mf --dont-arrange -o probes\roundtrip\rt.3mf probes\probe_E_combined.3mf
& "C:\Program Files\ChimeraX 1.12\bin\python.exe" tools\inspect_3mf.py probes\roundtrip\rt.3mf
```

## Probe I: extruders above the printer's tool count (tested 2026-09-23)

A file can paint more extruders than the printer has tools. Eight stacked
slabs of heights 2..16 mm were painted extruders 1..8 and sliced on the
5-tool XL profile, then the G-code was read back to see which tool actually
printed each slab:

| painted extruder | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| tool used | 0 | 1 | 2 | 3 | 4 | **0** | **0** | **0** |

Surplus colours do **not** wrap around modulo the tool count — they all
collapse onto filament 1, silently. Filament usage confirms it:
`14.87, 1.95, 2.85, 3.74, 4.64`, where extruders 2-5 track their slab volumes
(4:6:8:10) exactly and extruder 1 absorbs everything above the tool count.

The exporter therefore warns whenever more than 5 regions are painted.
