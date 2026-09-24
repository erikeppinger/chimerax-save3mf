# Lab notes — ChimeraX-Save3MF

| | |
|---|---|
| **Project** | 3MF export bundle for UCSF ChimeraX, preserving scene colour as multi-material printing data |
| **Investigator** | Erik Eppinger |
| **Assistance** | Claude (Anthropic) via Claude Code; every commit carries a `Co-Authored-By` trailer |
| **Dates** | 22–24 September 2026 |
| **Repository** | https://github.com/erikeppinger/chimerax-save3mf (MIT) |
| **Status** | v0.1.1 released; submitted to the ChimeraX Toolshed 24 Sep 2026, awaiting approval |

---

## 1. Motivation

ChimeraX can export geometry as STL, but an STL is a single colourless mesh.
Any colouring applied in ChimeraX — by chain, by B-factor, by hydrophobicity —
is lost at the moment of export, and has to be recreated by hand in the slicer
by splitting the model and assigning filaments. For a multi-chain complex on a
multi-tool printer this is slow, error-prone, and has to be repeated every time
the structure is re-exported.

The aim was a bundle that carries the ChimeraX colouring through to the slicer,
so that a file opens with each coloured region already assigned to its own
filament.

## 2. Aim and success criterion

Export the displayed ChimeraX scene as 3MF such that **PrusaSlicer opens the
file with each ChimeraX colour already assigned to a separate extruder, with no
manual work**, and such that the resulting G-code really does use one filament
per region.

Secondary aim: report, before printing, whatever would make the print fail or
waste material.

## 3. Materials

| Item | Version / detail |
|---|---|
| UCSF ChimeraX | 1.12 (2026-06-12), Windows; bundled Python 3.11 |
| PrusaSlicer | 2.9.6 |
| Bambu Studio | 2.x |
| OrcaSlicer | installed, version as shipped |
| Printer profile | Original Prusa XL – 5T Input Shaper, 0.4 nozzle |
| Print profile | 0.20 mm SPEED @XLIS 0.4, Generic PLA @XLIS |
| Test structures | PDB 1UBQ (ubiquitin, single chain), 1A3N (haemoglobin, 4 chains) |

Note: the `python` on this machine's PATH is the Microsoft Store stub and does
not execute. All scripting used ChimeraX's bundled interpreter.

## 4. Method

The 3MF specification documents geometry well but says little about how slicers
carry multi-material colour, and the community documentation that does exist
proved to be wrong (§6.2). The approach was therefore **experimental rather
than documentary**:

1. Write minimal 3MF "probe" files, each expressing colour a different way.
2. Round-trip each through a slicer's command line (`--export-3mf`) and read
   back what the slicer wrote. What survives the round trip is what the slicer
   understood.
3. Where the round trip was ambiguous, slice to G-code and read the toolpaths.
4. Only then implement, and keep the probes in the repository as evidence.

All probe files and results: `probes/` and `probes/RESULTS.md`.

---

## 5. Chronological record

### 22 Sep 2026 — planning

Development plan drafted: phases for bundle skeleton, geometry export, colour,
UX/docs, printability, and testing. Key early decision: treat "which colour
representation does a slicer actually honour" as an open experimental question
rather than assuming the specification would answer it.

### 23 Sep 2026, morning — phase 0.5, colour-transport experiments

Four probe files (A–D), each the same three stacked 30×30×10 mm slabs in three
colours, differing only in how colour was expressed. Round-tripped through
PrusaSlicer 2.9.6. Results in §6.1.

Outcome: PrusaSlicer ignored both standards-compliant colour mechanisms.
Only its own `Metadata/Slic3r_PE_model.config` was honoured. Probe E (all
mechanisms combined) was then sliced end to end and produced three filaments,
confirming the route reached G-code.

Bambu Studio and OrcaSlicer were installed later the same day and tested the
same way. They ignored the PrusaSlicer config entirely and required the
opposite geometry layout (probe F). Probe G, carrying both configurations at
once, failed in PrusaSlicer — establishing that the **geometry layout alone**
decides which slicer understands a file and no metadata can bridge the two
families. Hence a `flavor` option.

### 23 Sep 2026, morning — phase 1, geometry

Bundle skeleton (`pyproject.toml`, `BundleAPI`/`SaverInfo`), scene traversal,
instance expansion, vertex welding, scaling and placement. Validated against
ChimeraX's own STL exporter on the same scene (§6.5).

Cartoon geometry was confirmed to exist in `--nogui`, removing a risk flagged
in the plan and allowing the whole test suite to run headless.

### 23 Sep 2026, morning — printability reporting

Added a report that measures but never modifies: disconnected pieces, loose
fragments, open and non-manifold edges, thin features. Piece counting was
initially by shared vertices and disagreed with PrusaSlicer (17 vs 21 on
identical geometry); switching to shared **edges** brought exact agreement.

### 23 Sep 2026, midday — phase 2, colour regions

Triangles grouped by colour; continuous schemes clustered in CIELAB weighted by
triangle area; each region keeps a real scene colour rather than a cluster
average. `3mf palette` added so the colour count could be chosen against its
perceptual cost (ΔE) before exporting.

### 23 Sep 2026, midday — phase 3, interface and documentation

Save-dialog options widget (built and rendered offscreen for testing, without
opening the GUI), user documentation page installed into ChimeraX help, and
size sanity warnings.

### 23 Sep 2026, afternoon — pivot: painting instead of splitting

**Trigger:** a real export opened in PrusaSlicer by the investigator showed a
repair warning on every one of its eight parts. Splitting a mesh into
per-colour volumes necessarily leaves open edges where parts meet.

Investigation found that slicers have a purpose-built mechanism — per-triangle
extruder painting — which keeps the mesh whole. The encoding was verified by
experiment (§6.2) because the published tables are wrong. Re-implemented on
this basis; the exported mesh is now manifold with no slicer warnings.

A second question arose from the same export: what happens when a file paints
more extruders than the printer has tools. Probe I answered it (§6.3).

### 23 Sep 2026, afternoon — print cost

Added an estimate of the tool changes each colour choice causes, then replaced
raw counts with **time**, calibrated by slicing the same scene at eight colour
counts (§6.4).

### 23 Sep 2026, afternoon — phase 5, test suite

Four-stage test driver: install integrity, export tests, slicer acceptance
(including a real slice), wheel build. The suite was validated by mutation
(§7).

### 23 Sep 2026, evening — release

MIT licence, metadata, AI-assistance disclosure, public repository, v0.1.0
tagged and released with the wheel attached. The published wheel was then
downloaded and installed to confirm the artifact itself works.

### 24 Sep 2026 — documentation fix, dependency fix, submission

- Established how the installed help page is reached (`help 3mf`); documented
  that bundle commands are not listed in ChimeraX 1.12's help index.
- Found two undeclared bundle dependencies (§6.6), fixed, released v0.1.1.
- Submitted v0.1.1 to the ChimeraX Toolshed; awaiting approval.

---

## 6. Experiments and results

### 6.1 Which colour representation does a slicer honour?

Method: round-trip each probe through the slicer's `--export-3mf` and inspect
what it wrote back (`tools/inspect_3mf.py`).

| Probe | Colour expressed as | PrusaSlicer 2.9.6 | Bambu / Orca |
|---|---|---|---|
| A | `m:colorgroup` (Materials extension), per triangle | ignored | ignored (CLI) |
| B | 3 components, each with `basematerials` | 3 separate objects, each dropped to the bed | — |
| C | one mesh + `Slic3r_PE_model.config` volumes | **exact**: 3 named volumes, extruders 1–3 | — |
| D | core `basematerials` per triangle | ignored | — |
| E | C + colour tags together | **exact**, tags harmless | collapsed to 1 part |
| F | components + `model_settings.config` | 3 separate objects, no extruders | **exact** |
| G | F + both configs (universal attempt) | still 3 separate objects | exact |

**Conclusion.** The two slicer families need mutually exclusive geometry
layouts. No single file satisfies both; extra metadata does not help.

### 6.2 Encoding of per-triangle extruder painting

Community documentation gives two contradictory tables for the code that
assigns a triangle to an extruder. Probe H resolved it empirically: three slabs
of volume ratio 1:2:3 painted with codes `4`, `8`, `0C` and sliced.

```
; filament used [g] = 3.02, 4.64, 5.44, 0.00, 0.00
```

Smallest slab on extruder 1, largest on extruder 3 → **extruder N is
`MMU_CODES[N]`** where the table is
`["0","4","8","0C","1C","2C","3C","4C","5C","6C","7C","8C","9C","AC","BC","CC"]`
and index 0 means unpainted. The published tables are off by one.

Attribute names differ between families, encoding is identical:
`slic3rpe:mmu_segmentation` (PrusaSlicer, namespace
`http://schemas.slic3r.org/3mf/2017/06`) and `paint_color` (Bambu, Orca).

### 6.3 Colours exceeding the printer's tool count

Probe I: eight stacked slabs, heights 2–16 mm, painted extruders 1–8, sliced on
the 5-tool profile; the G-code was then read to determine which tool printed
each slab.

| painted extruder | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| tool used | 0 | 1 | 2 | 3 | 4 | **0** | **0** | **0** |

Surplus colours do **not** wrap around modulo the tool count; they all collapse
onto filament 1, silently. Filament usage confirmed this
(`14.87, 1.95, 2.85, 3.74, 4.64`: extruders 2–5 track slab volumes 4:6:8:10
exactly, extruder 1 absorbs the rest). The exporter now warns above five
regions.

### 6.4 Cost of a tool change

The same scene (1A3N surface, 60 mm) was exported at eight colour counts and
each file sliced; print time was regressed against tool changes.

| colours | tool changes | print time |
|---|---|---|
| 1 | 2 | 2 h 22 m |
| 2 | 257 | 3 h 47 m |
| 3 | 512 | 5 h 10 m |
| 4 | 564 | 5 h 23 m |
| 5 | 811 | 6 h 42 m |
| 6 | 993 | 7 h 26 m |
| 8 | 997 | 7 h 29 m |
| 10 | 979 | 7 h 27 m |

**18.4 s per tool change**; intercept (print with no colour) 2 h 27 m; worst
point 4.1 % off the fit.

The plateau at 6–10 colours is §6.3 observed from the other direction: beyond
the tool count, extra colours add no changes. The cost model was therefore made
tool-count aware, after which estimated versus measured tool-change time agreed
within **4.8 %** across the whole range.

### 6.5 Geometry fidelity against ChimeraX's own exporter

1UBQ molecular surface, same scene, our 3MF versus ChimeraX's STL, both
measured by PrusaSlicer:

| | ChimeraX STL | this bundle |
|---|---|---|
| facets | 102,690 | 102,672 |
| bounding box (mm) | 33.0787 × 34.5733 × 39.4521 | 33.0786 × 34.5734 × 39.4521 |
| volume | 10004.19 | 10004.04 |
| manifold | yes | yes |
| separate shells | 21 | 21 |

The 18 missing facets are degenerate slivers removed during vertex welding;
the mesh stays manifold. Volume differs by 0.0015 %, from writing coordinates
at four decimal places.

### 6.6 End-to-end result

1A3N, solvent deleted, surface coloured by chain, exported at 60 mm and sliced
on the XL 5-tool profile:

```
; filament used [g] = 14.88, 14.43, 11.83, 10.83, 0.00
; estimated printing time (normal mode) = 3h 58m 41s
```

Four chains, four filaments, no manual assignment in the slicer. **Success
criterion met.**

---

## 7. Errors found and corrected

Recorded because each was found by a specific check, and several would have
been invisible to the user.

| # | Fault | How it surfaced | Correction |
|---|---|---|---|
| 1 | Model centred on x=0/y=0, half at negative coordinates | Only the real slice: "All objects are outside of the print volume". Round-trip tests passed because the GUI loader auto-arranges | Place the model in the positive octant |
| 2 | Stale display state: export after `hide atoms` still contained the hidden atoms (1.77 M vs 814 k triangles) | `3mf palette` and `save` disagreed on the same scene | Flush pending graphics before reading drawings; nothing draws a frame in `--nogui` |
| 3 | Piece counting by shared vertices | Disagreed with PrusaSlicer (17 vs 21) | Count by shared edges; now exact agreement |
| 4 | Region names taken from the triangle-count majority | Investigator's slicer showed "ribbons #0066FF" for chain surfaces — cartoon ribbons are many tiny triangles | Weight by area |
| 5 | Per-colour volume splitting left open edges | Investigator's screenshot: repair warning on all eight parts | Per-triangle painting on one mesh (§6.2) |
| 6 | Self-contradictory report ("779 tiny pieces = 68.9 % of volume") | Reading the output | Distinguish loose fragments from a model that is not one body |
| 7 | `devel install` silently failing, leaving the previous version installed | Edits appeared to have no effect | Test driver fails on non-zero install and compares installed bytes with source |
| 8 | Two undeclared bundle dependencies | Audit prompted by the investigator's question before submission | Declare `ChimeraX-SaveCommand`, `ChimeraX-DataFormats` |

Environment-specific traps also recorded in `CLAUDE.md`: `devel install`
resolves documentation globs against the process working directory, and
PowerShell 5.1 turns native `stderr` into terminating errors when merged with
`2>&1`.

## 8. Verification

`tests/run_all.ps1`, four stages, any of which fails the run:

1. **Install integrity** — `devel install` succeeded *and* installed bytes
   match source (fault 7 above).
2. **Export tests** — 17 checks on real exported files: geometry matches
   ChimeraX's STL export, `size` exact, no negative coordinates, painting
   covers every triangle, split parts tile the mesh, >15-colour fallback,
   empty scene errors clearly.
3. **Slicer acceptance** — PrusaSlicer loads the painted export as manifold,
   preserves painting through a round trip and **slices it**; Bambu and Orca
   preserve `paint_color`; the tool-change estimate is checked against real
   G-code (tolerance 5 %, observed −1.9 %).
4. **Wheel** — contains package and documentation.

**Validation of the suite itself:** the negative-coordinate fault was
deliberately reintroduced; 7 of 17 checks failed with the correct diagnosis,
then the change was reverted. A suite that has never failed has not been
tested.

No XML-schema validation was used: no 3MF schema ships with the project and
writing one by hand would not have constituted independent validation.
Acceptance by three independent slicers was treated as the stronger evidence.

## 9. Outcome

- Bundle providing `save *.3mf` and `3mf palette` for ChimeraX 1.9+
- Colour carried as per-triangle extruder painting, `flavor` selecting the
  slicer family; automatic fallback to split parts above 15 colours
- Printability and print-cost reporting; nothing ever modifies geometry
- Save-dialog options and an installed help page
- v0.1.0 (23 Sep) and v0.1.1 (24 Sep) released with wheels; v0.1.1 submitted
  to the ChimeraX Toolshed

## 10. Time input

Derived from commit timestamps; these are **elapsed working spans**, not
metered effort.

| Date | Span | Work |
|---|---|---|
| 22 Sep | — | Development plan; scoping of the open questions |
| 23 Sep | 09:14 – 16:01 (≈ 6 h 45 m) | Probes A–I, all five implementation phases, the painting pivot, test suite, v0.1.0 release |
| 24 Sep | ≈ 13:40 – 14:10 | Help-page documentation, dependency audit, v0.1.1, Toolshed submission |

Approximately **8 hours of elapsed work across three calendar days**, of which
a substantial share was experimental (probe generation and slicing) rather than
coding. Slicing runs alone account for roughly 30–40 minutes of machine time.

## 11. Limitations and open questions

- Tested only on ChimeraX 1.12; the wheel is pure Python and declares 1.9+.
- Only PrusaSlicer was verified through to G-code. Bambu Studio and OrcaSlicer
  were verified as far as preserving the painting.
- Whether Bambu Studio's GUI colour-parsing dialog reads `m:colorgroup` was not
  determined; it is a GUI dialog and the CLI does not offer it.
- The tool-change time constant (18.4 s) is specific to a toolchanger. An MMU,
  which rewinds and purges, will be considerably slower; the figure is for
  comparing choices, not quoting a print.
- The enclosed-geometry check samples at most the 64 largest pieces and is
  skipped above 2000 pieces.
- Geometry preparation for printing (struts, thickened ribbons, solvent
  removal) is out of scope and belongs to the NIH 3D print presets bundle.

## 12. Reproducibility

Everything in this record can be re-run from the repository:

```
tools\make_probes.py              generate probes A–H
tools\probe_extruder_overflow.py  generate probe I
tools\inspect_3mf.py <file>       read back what a slicer wrote
tools\validate_3mf.py <file>      structural validation
tools\calibrate_time.py           re-measure seconds per tool change (slices)
tools\check_time_model.py         model vs those measurements
tools\check_cost_model.py         estimate vs a real G-code
tests\run_all.ps1                 full verification
```

Probe results and the reasoning behind each format decision:
`probes/RESULTS.md`. Architecture and environment traps: `CLAUDE.md`.

## 13. Note on AI assistance

The implementation, experimental design and this record were produced by Claude
(Anthropic) working interactively with the investigator, who set the aims,
supplied the printing domain knowledge, tested builds in the real slicer and
identified several faults from that testing (faults 4 and 5 above originated
from investigator screenshots). All factual claims here rest on artefacts in
the repository — probe files, G-code measurements, test output — rather than on
model assertion.
