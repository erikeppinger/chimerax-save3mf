# Printing protein models

A worked example from a PDB entry to a multi-colour print, followed by
practical tips for each kind of model and the slicer settings that act on files
from [Save3MF](../README.md). Inside ChimeraX this page is part of the help
(`help 3mf`, then *Printing protein models*), where every command in the
example is a link that runs it.

**Have a tip that worked for you?** This page is meant to grow.
[Contributing a tip](#contributing) says how to add one.

Contents: [Worked example](#example) · [Tips by representation](#tips) ·
[Slicer settings](#slicer) · [Sources](#sources) ·
[Contributing a tip](#contributing)

<a name="example"></a>

## Worked example: ubiquitin (PDB 1ubq)

The route is ChimeraX → Save3MF →
[Support Optimizer](https://github.com/erikeppinger/support-optimizer) →
slicer. Besides Save3MF it uses the
[NIH 3D print presets](https://cxtoolshed.rbvi.ucsf.edu/apps/chimeraxnihpresets)
(install from **Tools → More Tools…**), and optionally Support Optimizer, which
runs in the browser or as a desktop app. The same steps are in the example
script [examples/1ubq-print.cxc](../examples/1ubq-print.cxc).

### 1. Open the structure

```chimerax
open 1ubq
```

A PDB ID or a local file. For an oligomer, use the biological assembly if that
is what should be printed.

### 2. Make it printable with an NIH preset

```chimerax
preset "nih3d" "ribbon by secondary structure (printable)"
```

Or choose one from the **Presets** menu. The printable presets set thicknesses
a printer can hold and add supports that hold the model together: hydrogen
bonds drawn as thick cylinders and, where pieces need joining, struts. For
1ubq the supports are all hydrogen bonds; a less compact structure also gets
struts.

<a name="supports"></a>

### 3. Check the supports

Most supports help, but an occasional one is badly placed for printing –
pinning a terminus at an awkward angle, or creating an overhang that needs
support material. Hover over a support to see which two atoms it joins, then
remove it by naming them. In 1ubq, for example, the hydrogen bond between Met1
N and Val17 O:

```chimerax
delete pbonds /A:1@N /A:17@O
```

For any structure, Ctrl+click the support to select it and use
`delete pbonds sel`. To keep it in the session but leave it out of the file,
hide it instead (`hide /A:1@N /A:17@O pbonds`); only what is displayed is
exported. `delete pbonds` removes every pseudobond whose two ends are both in
the specification, so a residue-level specification such as `/A:1,17` removes
all supports between those residues.

<a name="thickness"></a>

**Thinner supports.** If the supports dominate the model, make them thinner:

```chimerax
size pseudobondRadius 0.4
```

This sets every support – hydrogen bonds and struts – to a radius of 0.4 Å;
`size #1.1 pseudobondRadius 0.4` changes only the hydrogen bonds (model
`#1.1` here) and `size #2 pseudobondRadius 0.4` only a struts model. It keeps
their colours and leaves deleted supports deleted. Changing the radius with
`hbonds radius` or `struts … radius` instead recalculates them, which brings
deleted ones back.

Keep two limits in mind, both set by the print size. In the print a support
is 2 × radius × scale thick, the scale (mm per Å) being in the export report:
at 100 mm, 1ubq is exported at about 2.9 mm/Å, so a 0.4 Å support is 2.3 mm
across. It should stay at least three nozzle widths thick (1.2–1.5 mm with a
0.4 mm nozzle). And a support is joined to the ribbon only by its own
cross-section – its ends already sit on the ribbon's centre line – so the
joint weakens with the square of the radius: half the radius, a quarter of the
strength.

### 4. Colour it – then recolour the supports

```chimerax
color /A cornflowerblue
color strand gold
color helix tomato
```

Supports are pseudobonds between atoms, so colouring the atoms colours the
supports with them: after the commands above they are blue, gold and red like
the backbone they join, and in the print they cannot be told apart from it.
Give them their own colour as the last colouring step:

```chimerax
color lightgray target p halfbond false
```

`target p` limits the command to pseudobonds, so it recolours every support –
hydrogen bonds and struts alike – without needing their model numbers.
`halfbond false` gives each support one colour rather than two halves in the
colours of its end atoms. A later plain colour command that covers the
supports' atoms (`color /A red`, `color strand gold`, …) recolours them again,
so repeat this afterwards. Colouring by a scheme – `color bychain`, `rainbow`,
`color byattribute` – leaves them as they are.

> Every colour costs a tool change on each layer it appears in. A support
> colour that already occurs in the model – the grey of the loops, say – adds
> no tool changes at all.

### 5. Preview colours, print time and smoothness

```chimerax
3mf palette maxColors 4 size 100 tools 4
```

Writes nothing. Shows the four parts, how many layers each appears in, the
time spent changing tools on a 4-tool printer, and whether saving at this size
will [smooth](#smoothness) the model.

### 6. Export

```chimerax
save ~/Desktop/1ubq.3mf size 100 maxColors 4
```

- **size 100** – longest edge 100 mm. **scale** sets millimetres per Å instead
  (default 1).
- **maxColors 4** – merge to at most four colours. Needed for continuous
  colouring such as rainbow or B-factor on a filament printer.
- **flavor** – **prusa** (default) for PrusaSlicer, **bambu** for Bambu Studio
  and OrcaSlicer, **fullcolor** for full-colour printers.

The report in the log lists the colour parts and what a slicer will make of the
geometry. Supports scale with the model: at a small scale, well below 1 mm/Å,
they can become too thin to print. At a large scale the opposite happens:
ChimeraX's screen tessellation starts to show as flat facets, and the export
makes it finer, saying so in the log before the file is written. At 100 mm
1ubq needs none; at 200 mm the supports and ribbons are smoothed.

### 7. Orientation and cavities in Support Optimizer (optional)

Load the 3MF by drag and drop; the colours are kept.

- **Surface models only:** *Find cavities*, then *Fill selected cavities*.
  Sealed cavities would otherwise trap support material that can never be
  removed. Skip this for cartoon and strut models, where cavity detection is
  not meaningful.
- Set the critical overhang angle for the printer (FDM typically about 45°).
  Above about 20,000 triangles enable *Use low-res proxy*, then *Optimize
  orientation*.
- *Compare to start model* and *Show support paths* show whether the new
  orientation needs less support.
- *Export 3MF* for multi-colour, or *Export STL* for a single colour.

### 8. Slicer

- Open the 3MF. Colours arrive as painted extruders (or as separate parts with
  **paint false**).
- Assign filaments; use organic or tree support material.
- Do not re-orient the part if Support Optimizer has already done so.
- Check the preview: no small loose fragments, supports printed continuously.
- Check the two [slicer settings](#slicer) below that act on painted colours.

<a name="tips"></a>

## Tips by representation

<a name="general"></a>

### All models

- **Scale.** At the default scale 1 Å becomes 1 mm, which is far too small for
  most proteins. Fine features such as ribbons and bonds usually need 2–3×
  enlargement to print reliably.
- **Minimum feature size.** Plan for at least three nozzle widths (about
  1.2–1.5 mm with a 0.4 mm nozzle) for supports, bonds and ribbon edges. For
  models that will be handled, 3 mm or more is safer, and 6 mm for models over
  20 cm.
- **Smoothness.** Large prints show the flat facets of screen tessellation; the
  export smooths them automatically (see [Smoothness](#smoothness) below).
- **Remove what is not needed** before export: water, unwanted chains, loose
  ions and additives. For a molecular surface, delete atoms rather than hide
  them: a hidden atom still shapes the surface computed around it. (Hiding a
  support, by contrast, simply keeps it out of the file.) Print a ligand
  separately if it should be removable.
- **Orientation.** Automatic orientation (Support Optimizer, or Meshmixer's
  *Orientation*) noticeably reduces overhangs and support material.
- **Support material.** Organic or tree supports suit organic shapes. Accept
  unsupported regions where removal would be impossible, such as inside
  helices: short overhangs there often bridge. A second material as support
  interface (for example PETG under PLA) makes removal much easier.
- **Flat base.** If a model rocks or touches the bed at a single point, cut
  1–2 mm off the bottom in the slicer's cut tool for a stable, flat contact
  area.
- **Multi-colour.** Tool changes cost more time than colour area. Merge colours
  with **maxColors** (preview with **3mf palette**), pick support colours that
  already occur in the model, and use the wipe tower, plus purging into infill
  or the object where the slicer offers it.
- **Mesh check.** Watertight meshes avoid slicer errors; repair in the slicer or
  in MeshLab if needed.

<a name="smoothness"></a>

### Smoothness in large prints

ChimeraX draws for the screen: a support is a 10-sided cylinder, a ribbon tube
a dozen or so sides around. Scaled up for printing, the flats become visible. A
0.6 Å support printed at 200 mm is a 3.5 mm-radius prism whose flats sit
0.17 mm inside the true circle – nearly a whole 0.2 mm layer.

Save3MF therefore measures how deep the flat facets are **at the size you
export at**. Where they are deeper than 0.05 mm, it exports supports, bonds,
atoms and ribbons with more sides, then restores ChimeraX's settings, so the
display is left as it was. Before the file is written, a warning in the log
says what changes and what it costs in triangles. For 1ubq at 200 mm the
support flats go from 0.17 to 0.04 mm and the file from 0.5 to 1.0 MB; at
100 mm nothing needs changing.

```chimerax
3mf palette size 200
```

shows in advance, without writing anything, whether saving at that size will
smooth the model. The target can be changed when saving:

- `save model.3mf size 200 smoothness 0.1` – coarser: fewer triangles, a
  smaller file
- `save model.3mf size 200 smoothness 0.02` – finer
- `save model.3mf size 200 smoothness off` – exactly what is on screen

In the Save dialog this is the *Smooth for printing* option.

Molecular and map surfaces are not re-tessellated: their fineness is fixed
when they are computed. If theirs is too coarse for the print size, the log
says so; recompute a molecular surface finer with, for example,
`surface gridSpacing 0.3`, or show a map at full resolution with
`volume step 1`.

### Surface models

- The easiest representation to print on an FDM printer.
- Seal interior cavities and tunnels first (Support Optimizer), or support
  material is trapped inside.
- A smaller probe radius (for example 0.5–1.4 Å) shows more detail; a finer
  grid gives a smoother surface but a larger file. Large structures may need
  splitting into several surfaces.
- Chain colours print as painted regions; check the slicer's
  [segmented region width](#segmented).
- Large complexes such as capsids: print subunits or halves separately and join
  them with pins or magnets. That eases printing and support removal, and
  assembling them is useful for teaching.

### Cartoon and ribbon models

- Thicken ribbons (`cartoon style … thickness`, or `struts … fattenRibbon true`)
  and enlarge 2–3×.
- Struts are essential. A typical choice is
  `struts @ca length 7 loop 30 radius 0.8 fattenRibbon true`; the NIH presets
  add supports automatically. For nucleic acids,
  `struts @C5' length 15 loop 80 radius 1`.
- Hydrogen bonds shown as thick sticks (radius about 0.5 Å) stabilise sheets
  and helices as well.
- Check the supports after a preset, and recolour them after a plain colour
  command (steps [3](#supports) and 4 above). If they dominate the model,
  [make them thinner](#thickness) – within the limits the print size sets.
- In Support Optimizer, cavity detection is not meaningful for cartoons;
  orientation search and support preview are.
- Very delicate ribbons often print better on resin (SLA) or SLS printers. On
  FDM, a lower speed and organic supports help.

### Space-filling and ball-and-stick models

- Sphere models are surface-like and print robustly. Overlapping spheres are
  fused by the slicer; the export report counts bodies closer than about
  0.4 mm as one.
- In ball-and-stick, the bonds are the weak point: use thick sticks, enlarge the
  model, and print large molecules in parts if needed.
- Round undersides need support. A flat cut at the bottom, or a deliberate base
  group of atoms, reduces it.

### Materials

- PLA for most teaching models, PETG for robust handling models, PETG as a
  breakaway support interface under PLA.
- TPU only with [beam interlocking](#interlocking) and a compatible partner:
  PETG with TPU works, PLA with TPU poorly.

<a name="slicer"></a>

## Slicer settings that act on these files

Two multi-material settings apply to painted colours, and so to every
multi-colour file from Save3MF. They exist under the same names, with the same
defaults, in PrusaSlicer, OrcaSlicer and Bambu Studio; type "interlocking" into
the settings search to find them. Times below were measured with PrusaSlicer
2.9.6 on an Original Prusa XL profile (0.20 mm, 0.4 mm nozzle).

<a name="segmented"></a>

### Maximum width of a segmented region

How deep a painted colour reaches into the object. The Original Prusa XL
profiles set 5 mm (PrusaSlicer's own default is 0, meaning all the way
through). With 5 mm each painted colour is a 5 mm shell, and the core takes a
neighbouring colour. From outside the model looks the same, and filament
changes are saved; but a model that will be cut or sectioned to show solid
chain colours inside needs this set to 0. *Interlocking depth of a segmented
region*, greyed out while the width is 0, alternates the shell depth layer by
layer so shell and core interlock.

<a name="interlocking"></a>

### Beam interlocking

Weaves two materials into each other where different extruders meet: thin,
alternating, crossed beams a few millimetres into each side, hidden from the
surface by *boundary avoidance*. It is a mechanical bond, made for materials
that do not stick to each other (PLA with PETG, rigid with TPU) – but on
protein models it is needed for colours of a single material too. It acts on
painted colour boundaries as well as on separate parts.

| Variant | Print time | Tool changes |
|---|---|---|
| Interlocking off (two-part test block) | 26 m 02 s | 64 |
| On, defaults (0.8 mm, 22.5°, 2 layers, depth 2, avoidance 2) | 30 m 30 s (+17 %) | 64 |
| Painted object with horizontal colour bands, off → on | 40 m 07 s → 56 m 49 s (+42 %) | 32 → 44 |

> **Needed, but hard to hide on protein models.** Printed on an Original Prusa
> XL in PLA throughout, a 1ubq ribbon model showed both sides of it. Without
> interlocking, joints between two colours – a loop meeting a β-strand, say –
> held only briefly and broke apart at the joint surface: walls printed by
> different tools, one after the other, fuse only weakly. With it, PrusaSlicer
> often failed to connect the parts properly at the defaults, and settings
> strong enough for proper contact – depth 3, boundary avoidance 1 – pushed
> each colour into its neighbour where it showed on the surface. The parts of
> such a model are only a few millimetres thick, while interlocking works in
> cells twice the beam width (1.6 mm by default): boundary avoidance 1 keeps
> the beams just one cell from the outside. The feature is experimental, and
> it shows here.

- Turn it on for multi-colour protein models, also in a single material, and
  expect it to add 17–42 % to the print time.
- Start from the defaults and print a small test piece – a single joint of the
  model is enough – before the whole model. Raise the depth before lowering
  boundary avoidance: avoidance is what keeps the weave off the surface.
- Keep boundary avoidance at 2 or more on visible models; below that the
  striping can show on the surface, including the first and top layers.
- Give the weave room. Thin features – ribbons, supports, narrow chain contacts
  – are often thinner than the avoidance zone, so the structure mostly
  disappears there or reaches the surface; weak or one-sided interlocking on
  thin parts has been reported (PrusaSlicer issue #15011). Thicker supports and
  ribbons, or a larger print, leave space to hide it and give the joint more
  area. It works best on surface models with large contact areas.

<a name="sources"></a>

## Sources

- UCSF ChimeraX documentation:
  [struts](https://www.cgl.ucsf.edu/chimerax/docs/user/commands/struts.html),
  [color](https://www.cgl.ucsf.edu/chimerax/docs/user/commands/color.html)
- [NIH 3D print presets](https://cxtoolshed.rbvi.ucsf.edu/apps/chimeraxnihpresets)
  for ChimeraX
- E. da Veiga Beltrame, guide for 3D printing proteins
- 3Faktur, how to create molecule models for 3D printing
- Crafty Madness, optimised, separable protein models
- Formlabs forum, printing protein ribbon structures
- MolPrint, Blender add-on for printable molecules
- PrusaSlicer source code, `InterlockingGenerator` (ported from Cura's
  interlocking structure)
- Prusa Knowledge Base: multiple extruders settings; interlocking and advanced
  bonding
- [PrusaSlicer issue #15011](https://github.com/prusa3d/PrusaSlicer/issues/15011),
  weak interlocking on thin parts
- OrcaSlicer wiki, multimaterial advanced settings
- Bambu Lab wiki, beam interlocking
- Measurements of print time, tool changes and painted-region depth: test
  slices with PrusaSlicer 2.9.6 on an Original Prusa XL profile.

<a name="contributing"></a>

## Contributing a tip

Tips that worked on a real print are welcome – a setting, a material
combination, a ChimeraX command, a mistake worth avoiding.

- **Describe it:** open a
  [printing tip issue](https://github.com/erikeppinger/chimerax-save3mf/issues/new?template=printing-tip.yml).
  Say what you printed, on which printer and slicer, and what made the
  difference; a photo helps.
- **Or edit this page:** it is
  [docs/printing-protein-models.md](https://github.com/erikeppinger/chimerax-save3mf/blob/main/docs/printing-protein-models.md);
  open a pull request. See [CONTRIBUTING](../CONTRIBUTING.md) for the details.

Tips are checked before they are added, and ChimeraX commands are run, so that
everything on this page has worked at least once. Add the source if the tip
comes from somewhere else.
