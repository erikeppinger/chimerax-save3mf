# Draft reply

Hi Tom,

Thank you — this was exactly the testing the bundle needed, and you were right
on every point. The diagnostics were built on an assumption about ChimeraX
geometry that simply isn't true, and everything wrong downstream followed from
it. I've rewritten that analysis and added the continuous-colour output you
were looking for. Version 0.2.0 is on GitHub:

  https://github.com/erikeppinger/chimerax-save3mf

## What was wrong

The old check counted *topologically* separate surfaces — pieces that don't
share vertices — and reported them as pieces that "do not touch" which "will
not print as a single object". Both claims were unfounded. As you say,
ChimeraX almost never stitches geometry: ribbons are a surface per helix,
strand and coil, atoms are separate spheres, bond cylinders are open tubes.
They abut or overlap, and a slicer fuses them. The mesh topology says nothing
about the print.

## What it measures now

**Printed bodies, not surfaces.** Surfaces whose points come within about an
extrusion width (0.4 mm) fuse into one body, whether or not they share
vertices, because that is what happens in the print. Coarse meshes that
interpenetrate without their vertices coming close are caught by a containment
test as well.

**Winding, to find cavities.** A closed surface wound inside-out bounds a
void, not a solid. Your `molmap` case has three of them, which is exactly why
the old code called them loose fragments.

**Isolation, for what really is loose.** Only geometry touching nothing else
is reported as printing separately.

Your four scenarios now log:

    open 1ubq; save test.3mf
    → One connected body, built from 20 separate surfaces that touch or
      overlap. ChimeraX draws ribbons, atoms and bonds as separate pieces;
      a slicer fuses anything closer than about 0.4 mm, so this prints as
      one object.

    hide ribbon; show atoms; hide solvent; save test.3mf
    → One connected body, built from 1210 separate surfaces that touch or
      overlap. [...]
      608 of 1210 surfaces are not closed. Bond cylinders have no end caps
      and clipped surfaces are cut open, which is normal in ChimeraX;
      slicers close them when slicing.

    surface close; molmap protein 5; save test.3mf
    → One connected body; it will print as one object.
      3 interior cavities (surfaces wound inside-out, such as voids in a
      density map). Slicers leave these hollow; they cost no filament.

No warnings on any of them — they are all printable as they stand, and the
report now says so rather than implying otherwise.

## Continuous colour

You had it right: the bundle only spoke filament. `flavor generic` was a
misnomer — it quantised the surface into flat per-triangle regions, so your
hydrophobicity colouring was destroyed before it reached the viewer, and the
3MF viewer showing one colour was probably ignoring the Materials-extension
colorgroup as well.

There is now an explicit mode for full-colour machines:

    save test.3mf flavor fullcolor

It keeps the colour of every vertex and interpolates across each triangle,
with no clustering, no extruder assignment and no colour limit. On your `mlp`
case that is 779 distinct vertex colours in a 3MF colorgroup, referenced per
vertex (`p1`/`p2`/`p3`) with a default at object level for readers that only
look there. `flavor generic` still works and means the same thing.

I verified this by rendering the exported file directly rather than trusting a
viewer — `tools/render_3mf.py` reads the colours back out and rasterises them,
and the hydrophobicity gradient comes out intact. If it still looks flat in
your inkjet workflow, I'd like to know what it reads; if those printers want a
texture rather than vertex colours, that is a straightforward addition.

## Scope, stated up front

The README and the help page now open with which printer each mode is for:

| Printer | flavor | What the file carries |
|---|---|---|
| Multi-filament (MMU, toolchanger, AMS) | `prusa` (default), `bambu` | extruder painted per triangle, at most 15 colours |
| Full colour (inkjet, binder jet, PolyJet) | `fullcolor` | a colour at every vertex |
| Single filament | any | geometry; colour ignored |

The 15-colour ceiling and the "more colours than tools" warning are filament
limits and no longer appear in full-colour mode.

## Tests

Your four scenarios are now regression tests, and the body-grouping rules are
tested against shapes whose answer is known by construction — boxes
overlapping, touching exactly, 0.2 mm apart, 2 mm apart, and one inside
another wound inside-out. That last set caught a real error while I was
writing it: my first threshold rule fused boxes that were 2 mm apart.

## Still open

- Whether a full-colour printer driver actually reads 3MF vertex colours, or
  expects a texture. I have no such machine to test against.
- I've only verified filament output through to G-code on PrusaSlicer; Bambu
  Studio and OrcaSlicer are checked as far as preserving the painting.
- Overlapping shells are still non-manifold in the union sense. Slicers repair
  them and the result prints, as you found, but I don't claim more than that.

Thanks again — the bundle is considerably more honest than it was on Monday.

Erik
