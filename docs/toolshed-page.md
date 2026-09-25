# Toolshed page copy

Text for https://cxtoolshed.rbvi.ucsf.edu/apps/chimeraxsave3mf
(Editor Actions → Edit this page). Icon: `docs/icon/save3mf-256.png`.

---

## Short description

> Save the current scene as 3MF for 3D printing, with ChimeraX colouring
> carried through — as extruder assignments for a multi-filament printer, or
> as a colour at every vertex for a full-colour one.

## Tags

```
3D printing, 3MF, export, multi-material, multi-filament, full color,
color printing, PrusaSlicer, Bambu Studio, OrcaSlicer, MMU, surfaces,
molecular models, printability
```

## Full description

**Save3MF** adds 3MF to the formats ChimeraX can save, and carries your
colouring into the print.

```
save molecule.3mf size 80
```

The scene is written as it is displayed. Instanced geometry — atom spheres,
bond cylinders — is expanded into real triangles, coincident vertices are
merged, and the model is scaled to millimetres and placed on the build plate.

### Colour reaches the printer

| Your printer | `flavor` | The file carries |
|---|---|---|
| Multi-filament (MMU, toolchanger, AMS) | `prusa` (default), `bambu` | each colour painted onto the triangles as an extruder assignment |
| Full colour (inkjet, binder jet, PolyJet) | `fullcolor` | a colour at every vertex, interpolated across each triangle |
| Single filament | any | geometry; colour is ignored |

On a multi-filament printer the slicer opens the file with each chain or
region already assigned to its own filament — no manual splitting, no clicking
parts. Colouring by chain, by element or by any discrete scheme comes through
directly; continuous schemes such as `mlp` or B-factor can either be reduced
to the number of filaments you have, or kept in full with `flavor fullcolor`.

### It tells you what will happen before you print

ChimeraX scenes are built from abutting and overlapping surfaces rather than
one stitched mesh, and the report is written around that:

- how many objects the print will really produce, counting surfaces that fuse
  as one body
- interior cavities, which slicers leave hollow
- pieces that genuinely float free, such as waters or ions
- geometry hidden inside other geometry, which costs filament and cannot be
  seen
- features too thin for a 0.4 mm nozzle, and models too large for the plate

`3mf palette` previews the colour regions before you export, showing both what
merging them costs perceptually (ΔE) and what it costs in print time.

### Verified against real slicers

Colour handling in 3MF is barely documented and the published encoding tables
are wrong, so every format decision here was established by experiment against
PrusaSlicer, Bambu Studio and OrcaSlicer. The probe files and results are in
the repository. Output has been checked through to G-code on PrusaSlicer.

### Links

- Source, issues and documentation:
  https://github.com/erikeppinger/chimerax-save3mf
- `help 3mf` inside ChimeraX for the full option list
- Preparing structures for printing — struts, thickened ribbons, solvent
  removal — is the job of the
  [NIH 3D print presets](https://cxtoolshed.rbvi.ucsf.edu/apps/chimeraxnihpresets)
  bundle; Save3MF only measures and reports.
- [Support Optimizer](https://github.com/erikeppinger/support-optimizer) seals
  the cavities this reports, optimises print orientation and previews supports.

### Credit

Developed with AI assistance (Claude). Thanks to Tom Goddard for detailed
testing that corrected the printability diagnostics and prompted the
full-colour output.
