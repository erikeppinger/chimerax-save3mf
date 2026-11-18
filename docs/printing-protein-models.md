# Printing protein models

This guide takes one protein from the PDB to a multi-colour print, step by
step, and then collects tips for each kind of model and the slicer settings
that matter for [Save3MF](../README.md) files. In ChimeraX it is part of the
help (`help 3mf`, then *Printing protein models*), where you can click every
command to run it.

**Have a tip that worked for you?** This page is meant to grow –
[Contributing a tip](#contributing) says how.

Contents: [Worked example](#example) · [Tips by representation](#tips) ·
[Slicer settings](#slicer) · [Sources](#sources) ·
[Contributing a tip](#contributing)

<a name="example"></a>

## Worked example: ubiquitin (PDB 1ubq)

You will use three tools:

- **Save3MF**, to save the model with its colours;
- the [NIH 3D print presets](https://cxtoolshed.rbvi.ucsf.edu/apps/chimeraxnihpresets),
  to make it printable (install from **Tools → More Tools…**);
- optionally [Support Optimizer](https://github.com/erikeppinger/support-optimizer),
  to find the best orientation. It runs in the browser or as a desktop app.

All the steps are also in one script:
[examples/1ubq-print.cxc](../examples/1ubq-print.cxc).

### 1. Open the structure

```chimerax
open 1ubq
```

Any PDB ID or local file works. For a protein made of several copies, open
the biological assembly if that is what you want to print.

### 2. Make it printable

```chimerax
preset "nih3d" "ribbon by secondary structure (printable)"
```

You can also pick a preset from the **Presets** menu. The printable presets
make thin parts thick enough to print and add supports that hold the model
together: hydrogen bonds drawn as thick rods and, where needed, extra struts.

> **Good to know:** the presets delete the water molecules, and the ribbon
> presets also delete the hydrogens. `show` cannot bring them back, and a
> session saved afterwards won't have them. Your original file is not
> changed; open it again to get them back. If a particular water matters,
> save the session before running a preset.

<a name="supports"></a>

### 3. Check the supports

Most supports help, but now and then one sits badly – pinning the end of the
chain at an odd angle, say, or creating an overhang. Hover over a support to
see which two atoms it joins, then delete it by naming them. In 1ubq, for
example:

```chimerax
delete pbonds /A:1@N /A:17@O
```

Other ways to do it:

- **Click instead of typing:** Ctrl+click the support to select it, then
  `delete pbonds sel`.
- **Keep it, but leave it out of the print:** hide it instead,
  `hide /A:1@N /A:17@O pbonds`. Only what is shown gets saved.
- **Careful with whole residues:** `delete pbonds /A:1,17` removes every
  support between those two residues, not just one.

<a name="thickness"></a>

**Thinner supports.** If the supports look too heavy, make them thinner:

```chimerax
size pseudobondRadius 0.4
```

This sets all supports to a radius of 0.4 Å. It keeps their colours, and
supports you deleted stay deleted. To change only the hydrogen bonds, name
their model: `size #1.1 pseudobondRadius 0.4` (or `#2` for a struts model).
Avoid `hbonds radius …` or `struts … radius …` for this: they recalculate
the supports and bring deleted ones back.

Don't make them too thin. In the print, a 0.4 Å support at 100 mm is about
2.3 mm across; keep supports at least 1.2–1.5 mm thick (three widths of a
0.4 mm nozzle).

> **Why?** A support's thickness in the print is 2 × radius × scale, and the
> scale (mm per Å) is in the log when you save: about 2.9 mm/Å for 1ubq at
> 100 mm. A support is also attached to the ribbon only by its own
> cross-section, so its strength drops with the square of the radius – half
> the radius, a quarter of the strength.

### 4. Colour it – then recolour the supports

```chimerax
color /A cornflowerblue
color strand gold
color helix tomato
```

These commands colour the supports too, so they now blend into the ribbon.
Give them their own colour as the **last** colouring step:

```chimerax
color lightgray target p halfbond false
```

`target p` colours only the supports (hydrogen bonds and struts alike), and
`halfbond false` gives each one a single colour instead of two halves.
Repeat this after any later plain colour command such as `color /A red`.
Colour schemes – `color bychain`, `rainbow`, `color byattribute` – leave the
supports alone.

> **Tip:** each colour costs a filament change on every layer it appears in.
> A support colour that already occurs in the model – the grey of the loops,
> say – costs nothing extra.

### 5. Preview colours, print time and smoothness

```chimerax
3mf palette maxColors 4 size 100 tools 4
```

This saves nothing. It shows the four colours, how much printing time the
filament changes take on a 4-filament printer, and whether saving at this
size will [smooth](#smoothness) the model.

### 6. Save

```chimerax
save ~/Desktop/1ubq.3mf size 100 maxColors 4
```

- **size 100** – the longest side becomes 100 mm. (**scale** sets mm per Å
  instead.)
- **maxColors 4** – merge into at most four colours. Set it to the number of
  filaments your printer has; gradients such as rainbow or B-factor need it.
- **flavor** – **prusa** (the default) for PrusaSlicer, **bambu** for Bambu
  Studio and OrcaSlicer, **fullcolor** for full-colour printers.
- **parts chain** – one part per chain, for complexes (see
  [Complexes](#complexes)). 1ubq has only one chain.

The log then lists the colours and what the printer will make of the model.
Watch the scale: well below 1 mm per Å, supports can get too thin to print.
Large prints are smoothed automatically – 1ubq at 100 mm needs nothing, at
200 mm the supports and ribbons get rounder.

> **Good to know:** saving takes a moment for big models. Sticks, balls and
> spheres of a large structure are millions of triangles: haemoglobin as
> sticks takes about half a minute, ubiquitin a few seconds. ChimeraX has no
> progress bar and doesn't respond until it is done, but the status line at
> the bottom of the window shows what it is working on.

### 7. Orientation and cavities in Support Optimizer (optional)

Drag the 3MF file in; the colours are kept.

- **Surface models only:** *Find cavities*, then *Fill selected cavities*.
  Otherwise support material gets trapped inside where you can never remove
  it. Skip this for ribbon and strut models.
- Set the overhang angle your printer manages (about 45° for most FDM
  printers). For models above about 20,000 triangles, enable *Use low-res
  proxy*. Then *Optimize orientation*.
- *Compare to start model* and *Show support paths* show whether the new
  orientation needs less support.
- *Export 3MF* for multi-colour, or *Export STL* for one colour.

### 8. Slicer

- Open the 3MF. The colours arrive already assigned to filaments – as long
  as you saved with the flavour for your slicer: **prusa** for PrusaSlicer,
  **bambu** for Bambu Studio and OrcaSlicer.
- Assign your filaments, and use organic or tree supports.
- Don't re-orient the model if Support Optimizer already did.
- Check the preview: no small loose bits, supports printed without gaps.
- Check the two [slicer settings](#slicer) for multi-colour prints below.

<a name="tips"></a>

## Tips by representation

<a name="general"></a>

### All models

- **Size.** By default 1 Å becomes 1 mm, far too small for most proteins.
  Ribbons and bonds usually need 2–3× that to print reliably.
- **Thickness.** Keep supports, bonds and ribbon edges at least 1.2–1.5 mm
  thick (three nozzle widths). Models that will be handled are safer at
  3 mm, and models over 20 cm at 6 mm.
- **Smoothness.** Large prints are smoothed automatically (see
  [Smoothness](#smoothness)).
- **Remove what you don't need** before saving: water, unwanted chains, loose
  ions. For a surface, *delete* atoms rather than hide them – a hidden atom
  still shapes the surface around it. (A hidden support, on the other hand,
  is simply left out.) Print a ligand separately if it should come out.
- **Orientation.** Automatic orientation (Support Optimizer, or Meshmixer's
  *Orientation*) noticeably cuts down overhangs and support material.
- **Support material.** Organic or tree supports suit protein shapes. Leave
  places you could never reach unsupported, such as the inside of a helix:
  short overhangs there usually bridge. A second material as support
  interface (PETG under PLA, for example) makes removal much easier.
- **Flat base.** If the model rocks or touches the bed at a single point, cut
  1–2 mm off the bottom with the slicer's cut tool.
- **Multi-colour.** Filament changes cost more time than coloured area.
  Merge colours with **maxColors** (preview with **3mf palette**), reuse
  model colours for the supports, and use the wipe tower, plus purging into
  infill or the object if your slicer offers it.
- **Mesh check.** Closed meshes avoid slicer errors; repair in the slicer or
  in MeshLab if needed.

<a name="smoothness"></a>

### Smoothness in large prints

ChimeraX draws for the screen: a support has 10 flat sides, a ribbon about a
dozen. Printed large, those flat sides show. A 0.6 Å support printed at
200 mm has flat sides that sit 0.17 mm inside a true circle – almost a whole
0.2 mm layer.

So when you save, Save3MF checks how deep those flat sides would be **at your
print size**. Where they are deeper than 0.05 mm, it saves the supports,
bonds, atoms and ribbons with more sides. The log says so first, including
the extra file size, and your view in ChimeraX stays as it was. For 1ubq at
200 mm, the support flats go from 0.17 to 0.04 mm and the file from 0.5 to
1.0 MB; at 100 mm nothing changes.

To check in advance, without saving anything:

```chimerax
3mf palette size 200
```

You can change the target when saving:

- `save model.3mf size 200 smoothness 0.1` – coarser: fewer triangles, a
  smaller file
- `save model.3mf size 200 smoothness 0.02` – finer
- `save model.3mf size 200 smoothness off` – exactly what is on screen

In the Save dialog this is the *Smooth for printing* option.

Surfaces of molecules and maps are not changed: how fine they are is set
when ChimeraX computes them. If a surface is too coarse for your print size,
the log tells you. Make a molecular surface finer with, for example,
`surface gridSpacing 0.3`, or show a map at full resolution with
`volume step 1`.

<a name="complexes"></a>

### Complexes of several chains

A complex – say an AlphaFold prediction of two proteins, or a dimer from the
PDB – normally arrives in the slicer as one piece. To handle each chain on
its own, save one part per chain:
`save complex.3mf size 100 parts chain flavor bambu`.

- The slicer shows one object with a part per chain (*chain A*, *chain B*,
  …). You can select, hide or set up each one separately, and it keeps its
  colours.
- The chains stay where they are. (As separate objects, the slicer would
  drop each one onto the bed.)
- A surface that covers several chains – made with `surface … enclose`, or
  by the NIH surface presets – stays one part, *surface of chains A, B*:
  split along the chains, it would have holes. For a separate surface per
  chain, run `surface close` and then `surface` before saving.
- **parts model** does the same per model, for structures opened side by
  side.
- Use the flavour for your slicer (**prusa** or **bambu**). With the wrong
  one, the file opens but not as intended: Bambu Studio and OrcaSlicer show a
  prusa file as one part without colours, and PrusaSlicer splits a bambu file
  into separate objects.
- To print the chains as separate pieces, split the object in the slicer
  (OrcaSlicer: right-click → *Split* → *To objects*). This drops the
  colours, so assign a filament to each piece afterwards. Tiny extra pieces
  from the split are hollow spaces inside the protein and can be deleted.

In the Save dialog this is the *Parts* option.

### Surface models

- The easiest kind of model to print on an FDM printer.
- Fill hollow spaces inside first (Support Optimizer), or support material
  gets trapped.
- A smaller probe radius (0.5–1.4 Å) shows more detail; a finer grid gives a
  smoother surface but a bigger file. Very large structures may need to be
  split into several surfaces.
- Chain colours print as painted areas; see the slicer's
  [segmented region width](#segmented).
- Large complexes such as virus shells: print subunits or halves separately
  and join them with pins or magnets. That makes printing and support
  removal easier, and putting them together is great for teaching.

### Cartoon and ribbon models

- Make the ribbons thicker (`cartoon style … thickness`, or
  `struts … fattenRibbon true`) and print 2–3× larger.
- Struts are essential. A typical choice is
  `struts @ca length 7 loop 30 radius 0.8 fattenRibbon true`; the NIH presets
  add supports for you. For DNA and RNA:
  `struts @C5' length 15 loop 80 radius 1`.
- Hydrogen bonds shown as thick rods (radius about 0.5 Å) also hold sheets
  and helices together.
- After a preset, check the supports, and recolour them after a plain colour
  command (steps [3](#supports) and 4). If they look too heavy,
  [make them thinner](#thickness) – but not below what the print size
  allows.
- In Support Optimizer, skip the cavity search for ribbons; orientation and
  support preview work as usual.
- Very delicate ribbons often print better on resin (SLA) or powder (SLS)
  printers. On FDM, print slower and use organic supports.

### Space-filling and ball-and-stick models

- Sphere models behave like surfaces and print well. Touching spheres fuse
  in the print; the log counts parts closer than about 0.4 mm as one.
- In ball-and-stick, the sticks are the weak point: make them thick, print
  larger, and split big molecules into parts if needed.
- Round undersides need support. A flat cut at the bottom, or a few atoms
  chosen as a base, reduces it.

### Materials

Three plastics cover almost everything a protein model needs:

- **PLA** is made from plant starch or sugar. It is the easiest to print –
  low temperature, little warping, crisp detail – and comes in the most
  colours. It is stiff but brittle, and softens at about 60 °C, so a model
  left in a hot car can bend. Despite being plant-based, it only breaks down
  in industrial composting. The usual choice for teaching and display.
- **PETG** is related to the plastic of drinks bottles. It is tougher than
  PLA, bends a little before it breaks, and copes better with heat and
  chemicals, but strings more while printing. Good for models that get
  handled a lot.
- **TPU** is soft and rubbery. It prints slowly and needs care, but makes
  parts that bend and spring back – for example a flexible joint between two
  printed parts.

Which ones combine:

- PLA and PETG hardly stick to each other. That makes PETG ideal as support
  interface under PLA: the supports snap off cleanly. For the same reason, a
  model made of both needs [beam interlocking](#interlocking) to hold
  together.
- TPU only with beam interlocking and a suitable partner: PETG with TPU
  works, PLA with TPU poorly.

<a name="slicer"></a>

## Slicer settings for multi-colour prints

Two settings act on painted colours, so they matter for every multi-colour
Save3MF file. PrusaSlicer, OrcaSlicer and Bambu Studio all have them, under
the same names and with the same defaults; type "interlocking" into the
settings search to find them. The times below were measured with
PrusaSlicer 2.9.6 on an Original Prusa XL profile (0.20 mm layers, 0.4 mm
nozzle).

<a name="segmented"></a>

### Maximum width of a segmented region

How deep a painted colour goes into the model. The Original Prusa XL profiles
set 5 mm; PrusaSlicer's own default is 0, meaning all the way through.

- **5 mm:** each colour is a 5 mm shell around a core of a neighbouring
  colour. It looks the same from outside and saves filament changes.
- **0:** colours go all the way through. Use this if the model will be cut
  open to show solid chain colours inside.

*Interlocking depth of a segmented region* (greyed out while the width is 0)
varies the shell depth from layer to layer so that shell and core grip each
other.

<a name="interlocking"></a>

### Beam interlocking

Where two colours meet, this weaves them into each other with thin crossed
beams a few millimetres deep, hidden under the surface. It was made for
materials that don't stick to each other (PLA with PETG, rigid with TPU),
but on protein models it is needed even when all colours are the same
plastic. It works on painted colours as well as separate parts.

What to do:

- Turn it on for multi-colour protein models, even in a single material, and
  expect 17–42 % more printing time.
- Start with the defaults and print a small test piece – a single joint of
  the model is enough – before the whole model. If it doesn't hold, raise the
  depth first and leave *boundary avoidance* for last: that setting is what
  keeps the weave hidden under the surface.
- Keep boundary avoidance at 2 or more on visible models; below that the
  stripes can show on the surface.
- Give the weave room. Thin parts – ribbons, supports, narrow contacts
  between chains – are often thinner than the hidden zone, so the weave
  disappears or shows through there (reported as PrusaSlicer issue #15011).
  Thicker supports and ribbons, or a larger print, help. It works best on
  surface models with large contact areas.

| Variant | Print time | Tool changes |
|---|---|---|
| Interlocking off (two-part test block) | 26 m 02 s | 64 |
| On, defaults (0.8 mm, 22.5°, 2 layers, depth 2, avoidance 2) | 30 m 30 s (+17 %) | 64 |
| Painted object with horizontal colour bands, off → on | 40 m 07 s → 56 m 49 s (+42 %) | 32 → 44 |

> **Experience from a real print.** A 1ubq ribbon model in PLA on an Original
> Prusa XL showed both sides of it. Without interlocking, joints between two
> colours – a loop meeting a β-strand, say – held only briefly and then broke
> apart, because walls printed one after the other by different tools fuse
> only weakly. With interlocking at the defaults, PrusaSlicer often failed to
> connect the parts properly; settings strong enough to hold – depth 3,
> boundary avoidance 1 – pushed each colour into its neighbour where it
> showed on the surface. The parts of such a model are only a few
> millimetres thick, while the weave needs cells twice the beam width
> (1.6 mm by default). The feature is still experimental, and it shows here.

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

Tips are checked before they are added, and ChimeraX commands are run, so
everything on this page has worked at least once. Please add the source if
the tip comes from somewhere else.
