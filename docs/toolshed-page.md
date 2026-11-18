# Toolshed page copy

Text for https://cxtoolshed.rbvi.ucsf.edu/apps/chimeraxsave3mf
(Editor Actions → Edit this page). Icon: `docs/icon/save3mf-256.png`.

The page renderer takes basic Markdown only: headings, lists, emphasis,
inline code, fenced code and links all work, but **pipe tables do not** — they
come out as one run-together paragraph. Keep this copy table-free.

---

## Short description

> Save your ChimeraX scene as a 3MF file for 3D printing, in colour: ready
> for a multi-filament printer, or for a full-colour one.

## Tags

```
3D printing, 3MF, export, multi-material, multi-filament, full color,
color printing, PrusaSlicer, Bambu Studio, OrcaSlicer, MMU, surfaces,
molecular models, printability
```

## Full description

**Save3MF** lets ChimeraX save a scene as a 3MF file, the format 3D-printing
software opens, and keeps your colours.

```
save molecule.3mf size 80
```

What you see is what gets printed. The model is scaled to the size you ask
for – here 80 mm along its longest side – and placed on the build plate.

### Your colours reach the printer

- **Multi-filament printers** (MMU, tool changer, AMS): each colour arrives
  already assigned to a filament. Use `flavor prusa` (the default) for
  PrusaSlicer, `flavor bambu` for Bambu Studio and OrcaSlicer.
- **Full-colour printers** (inkjet, binder jet, PolyJet): use
  `flavor fullcolor` to keep every shade.
- **Single-filament printers**: any flavor works; the colours are ignored.

Colouring by chain, by element or by secondary structure comes through as it
is. Gradients such as rainbow or B-factor have more colours than you have
filaments: `maxColors 4` merges them into four, or `flavor fullcolor` keeps
them all.

### It checks the model before you print

The log tells you what the printer will make of your scene:

- how many separate pieces it will print
- hollow spaces inside the model
- loose bits, such as waters or ions
- parts hidden inside other parts, which cost filament but can't be seen
- parts too thin to print, or a model too big for the build plate

`3mf palette` previews the colours before you save: which would be merged,
how different they look, and how much printing time each colour costs.

### Smooth at any size

ChimeraX draws sticks, spheres and ribbons with a few flat sides, which is
fine on screen but shows on a large print. When you save, Save3MF checks whether the flat
sides would be visible at your print size and, if so, saves rounder shapes
instead. Your view in ChimeraX stays as it was. `smoothness off` saves
exactly what is drawn.

### One part per chain

A complex normally arrives in the slicer as one piece. With `parts chain`,
each chain becomes a part of its own that you can select and set up
separately, with its colours kept, while the complex stays together.
`parts model` does the same for each model.

```
save complex.3mf parts chain flavor bambu
```

A surface that covers several chains stays one part; `surface` makes one per
chain.

### Learn by example

The help includes a step-by-step example, from the PDB entry for ubiquitin to
a four-colour print, where every command is a link you can click. It also has
tips for each kind of model and the slicer settings that matter for
multi-colour prints. The same guide is on GitHub, where you can add tips of
your own:
[Printing protein models](https://github.com/erikeppinger/chimerax-save3mf/blob/main/docs/printing-protein-models.md).

### Tested with real slicers

How slicers read colour from 3MF files is barely documented, so every detail
was tested in PrusaSlicer, Bambu Studio and OrcaSlicer, and in PrusaSlicer
sliced all the way to printer code.

### Links

- Source, issues and documentation:
  https://github.com/erikeppinger/chimerax-save3mf
- `help 3mf` in ChimeraX lists every option
- [Printing protein models](https://github.com/erikeppinger/chimerax-save3mf/blob/main/docs/printing-protein-models.md):
  the step-by-step guide
- [NIH 3D print presets](https://cxtoolshed.rbvi.ucsf.edu/apps/chimeraxnihpresets):
  make a structure printable – thicker ribbons, supports, solvent removed.
  Save3MF saves and checks; it doesn't change your model.
- [Support Optimizer](https://github.com/erikeppinger/support-optimizer):
  fills hollow spaces, finds the best print orientation and previews supports

### Credit

Developed with AI assistance (Claude). Thanks to Tom Goddard for detailed
testing that corrected the printability diagnostics and prompted the
full-colour output.
