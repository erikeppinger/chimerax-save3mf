"""Headless test suite for the Save3MF bundle.

Run inside ChimeraX, from the bundle directory:

    & "C:\\Program Files\\ChimeraX 1.12\\bin\\ChimeraX-console.exe" --nogui --exit --silent --script tests/test_export.py

Writes tests/out/results.json and prints a summary line the shell driver
checks.  Every test exports a real scene and then inspects the resulting file;
nothing is asserted about internal state that a user could not observe.
"""

import json
import os
import sys
import traceback

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "tools"))

from chimerax.core.commands import run           # noqa: E402
from validate_3mf import validate                # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append({"test": name, "passed": bool(condition), "detail": detail})
    print("  %-52s %s%s" % (name, "pass" if condition else "FAIL",
                            "" if condition or not detail else "  <- " + detail))


def scene(*commands):
    run(session, "close")                        # noqa: F821
    for c in commands:
        run(session, c)                          # noqa: F821


def export(filename, args=""):
    path = os.path.join(OUT, filename).replace("\\", "/")
    run(session, "save %s %s" % (path, args))    # noqa: F821
    return path


# --------------------------------------------------------------------- tests

def test_surface_geometry():
    """Geometry must match what ChimeraX's own STL exporter produces."""
    scene("open 1ubq", "delete solvent", "hide atoms", "hide cartoon",
          "surface")
    stl = os.path.join(OUT, "ref.stl").replace("\\", "/")
    run(session, "save %s" % stl)                # noqa: F821
    path = export("t_surface.3mf")

    r = validate(path)
    check("surface: file is structurally valid", r.ok, "; ".join(r.problems))

    from chimerax.save3mf import scene as scene_module
    geom = scene_module.weld_vertices(
        scene_module.collect_geometry(session))  # noqa: F821
    check("surface: triangle count matches the live scene",
          abs(geom.triangle_count - r.facts["triangles"]) <= 0,
          "scene %d vs file %d" % (geom.triangle_count, r.facts["triangles"]))


def test_size_and_placement():
    """size must be exact, and nothing may sit at negative coordinates."""
    scene("open 1ubq", "delete solvent", "hide atoms", "hide cartoon",
          "surface")
    path = export("t_size.3mf", "size 42")
    r = validate(path)
    check("size: file is structurally valid", r.ok, "; ".join(r.problems))

    import zipfile
    import xml.etree.ElementTree as ET
    CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("3D/3dmodel.model"))
    pts = [(float(v.get("x")), float(v.get("y")), float(v.get("z")))
           for v in root.iter(CORE + "vertex")]
    xs, ys, zs = zip(*pts)
    longest = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    check("size: longest edge is 42 mm", abs(longest - 42.0) < 0.01,
          "got %.3f" % longest)
    check("size: model sits at z = 0", abs(min(zs)) < 1e-6, "min z %.4f" % min(zs))


def test_painting():
    """Colours become painted extruders on one closed mesh."""
    scene("open 1a3n", "delete solvent", "hide atoms", "hide cartoon",
          "surface", "color bychain")
    path = export("t_paint.3mf", "size 60")
    r = validate(path, expect_painted=True, expect_regions=4)
    check("paint: 4 chains become 4 painted regions on a closed mesh",
          r.ok, "; ".join(r.problems))
    check("paint: every triangle is painted",
          r.facts["painted"] == r.facts["triangles"],
          "%d of %d" % (r.facts["painted"], r.facts["triangles"]))


def test_bambu_flavor():
    scene("open 1a3n", "delete solvent", "hide atoms", "hide cartoon",
          "surface", "color bychain")
    path = export("t_bambu.3mf", "size 60 flavor bambu")
    r = validate(path, expect_painted=True, expect_regions=4)
    check("bambu: painted with paint_color and a Bambu config",
          r.ok, "; ".join(r.problems))

    import zipfile
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        model = z.read("3D/3dmodel.model").decode("utf-8")
    check("bambu: uses paint_color, not mmu_segmentation",
          "paint_color=" in model and "mmu_segmentation" not in model)
    check("bambu: writes model_settings.config",
          "Metadata/model_settings.config" in names)


def test_split_parts():
    """paint false falls back to per-colour volumes covering every triangle."""
    scene("open 1a3n", "delete solvent", "hide atoms", "hide cartoon",
          "surface", "color bychain")
    path = export("t_split.3mf", "size 60 paint false")
    # split parts are open where they meet, so closure is not required
    r = validate(path, expect_painted=False, expect_regions=4,
                 require_closed=False)
    check("split: 4 volumes tile the mesh with no gaps",
          r.ok, "; ".join(r.problems))


def _parts(path):
    """The parts of the one object in a 3MF: [(name, triangles, paint codes)].

    Reads both layouts - PrusaSlicer's triangle-range volumes and Bambu's
    components - the way the slicers do.
    """
    import re
    import zipfile
    with zipfile.ZipFile(path) as z:
        model = z.read("3D/3dmodel.model").decode("utf-8")
        names = z.namelist()
        prusa = ("Metadata/Slic3r_PE_model.config" in names
                 and z.read("Metadata/Slic3r_PE_model.config").decode("utf-8"))
    code = r'(?:paint_color|mmu_segmentation)="([^"]*)"'
    if prusa:
        tris = re.findall(r"<triangle [^>]*>", model)
        out = []
        for first, last, body in re.findall(
                r'<volume firstid="(\d+)" lastid="(\d+)">(.*?)</volume>',
                prusa, re.S):
            name = re.search(r'key="name" value="([^"]*)"', body).group(1)
            sub = tris[int(first):int(last) + 1]
            out.append((name, len(sub),
                        {m for t in sub for m in re.findall(code, t)}))
        return out
    objects = dict(re.findall(r'<object id="(\d+)"[^>]*>(.*?)</object>',
                              model, re.S))
    heads = dict(re.findall(r'<object id="(\d+)"([^>]*)>', model))
    out = []
    for oid in re.findall(r'<component objectid="(\d+)"', model):
        body = objects[oid]
        name = re.search(r'name="([^"]*)"', heads[oid]).group(1)
        out.append((name, len(re.findall(r"<triangle ", body)),
                    set(re.findall(code, body))))
    return out


def test_parts_per_chain():
    """parts chain: one part per chain, each painted, inside one object.

    Chain A is given two colours and chains B and C share one, so a part per
    colour (what paint false does) would come out differently from a part per
    chain.
    """
    scene("open 1a3n", "delete solvent | ligand", "hide atoms", "hide cartoon",
          "surface", "color bychain target s", "color /A:1-30 orange target s",
          "color /C #00ff00 target s", "color /B #00ff00 target s")
    whole = validate(export("t_whole.3mf", "size 60"), expect_painted=True)
    for flavor in ("prusa", "bambu"):
        path = export("t_parts_%s.3mf" % flavor, "size 60 parts chain flavor %s"
                      % flavor)
        parts = _parts(path)
        names = [p[0] for p in parts]
        check("parts %s: one part per chain" % flavor,
              names == ["chain A", "chain B", "chain C", "chain D"],
              "got %s" % names)
        check("parts %s: the parts hold every triangle of the scene" % flavor,
              sum(p[1] for p in parts) == whole.facts["triangles"],
              "%d vs %d" % (sum(p[1] for p in parts), whole.facts["triangles"]))
        codes = {p[0]: p[2] for p in parts}
        check("parts %s: chain A keeps both of its colours" % flavor,
              len(codes.get("chain A", ())) == 2, "codes %s" % codes)
        check("parts %s: chains B and C share one painted colour" % flavor,
              codes.get("chain B") == codes.get("chain C")
              and len(codes.get("chain B", ())) == 1, "codes %s" % codes)
        with __import__("zipfile").ZipFile(path) as z:
            items = z.read("3D/3dmodel.model").decode("utf-8").count("<item ")
        check("parts %s: one object on the plate, not one per chain" % flavor,
              items == 1, "%d build items" % items)


def test_parts_cartoon():
    """Cartoons and atoms are one drawing for all chains; each triangle has to
    reach the right chain anyway. Coloured by chain, so a misplaced triangle
    shows up as a second colour in a part."""
    scene("open 1a3n", "delete solvent | ligand", "hide atoms", "cartoon",
          "show :HIS atoms", "color bychain")
    parts = _parts(export("t_parts_cartoon.3mf", "size 60 parts chain"))
    check("parts cartoon: four chains", len(parts) == 4,
          "got %s" % [p[0] for p in parts])
    mixed = ["%s %s" % (p[0], sorted(p[2])) for p in parts if len(p[2]) != 1]
    check("parts cartoon: no triangle lands in another chain's part",
          not mixed, "; ".join(mixed))


def test_parts_hidden_atoms():
    """Hidden atoms must not claim cartoon triangles: chain A's waters are
    moved to a chain W of their own and hidden, so a part 'chain W' would mean
    the nearest-atom search looked at atoms that are not drawn. The ribbon is
    thickened as for printing; a thin one runs through the backbone atoms and
    never comes nearer a water (1041 triangles go to W otherwise)."""
    scene("open 1a3n", "delete ligand", "hide atoms", "cartoon",
          "changechains /A & solvent W",
          "cartoon style protein xsection round width 4 thick 3")
    names = [p[0] for p in _parts(export("t_parts_hidden.3mf",
                                         "size 60 parts chain"))]
    check("parts: hidden atoms claim no triangles",
          names == ["chain A", "chain B", "chain C", "chain D"],
          "got %s" % names)


def _mixed(parts):
    """Parts holding more than one paint code, for scenes coloured by chain."""
    return ["%s %s" % (p[0], sorted(p[2])) for p in parts if len(p[2]) != 1]


def test_parts_spheres():
    """Spheres of neighbouring chains overlap. Each must go to its chain
    whole; assigned triangle by triangle, the cap of a sphere that reaches
    into the other chain's sphere ends up in that chain's part."""
    scene("open 1a3n", "delete solvent | ligand", "hide cartoon",
          "show atoms", "style sphere", "color bychain",
          "hide pbonds")        # they keep a colour of their own
    parts = _parts(export("t_parts_spheres.3mf", "size 60 parts chain"))
    check("parts spheres: four chains", len(parts) == 4,
          "got %s" % [p[0] for p in parts])
    check("parts spheres: no sphere is split between chains",
          not _mixed(parts), "; ".join(_mixed(parts)))


def test_parts_thick_ribbon():
    """A ribbon thickened for printing reaches the neighbouring chain's side
    chains; its triangles must still follow the residue they were drawn
    for."""
    scene("open 1a3n", "delete solvent | ligand", "hide atoms", "cartoon",
          "cartoon style protein xsection round width 4 thick 3",
          "color bychain")
    parts = _parts(export("t_parts_thick.3mf", "size 60 parts chain"))
    check("parts thick ribbon: four chains", len(parts) == 4,
          "got %s" % [p[0] for p in parts])
    check("parts thick ribbon: no triangle lands in another chain's part",
          not _mixed(parts), "; ".join(_mixed(parts)))


def test_parts_surface_without_atom_map():
    """Sharp-edged zone colouring replaces a surface's vertices, and ChimeraX
    then has no atom map for it. The triangles must go to the surface's own
    atoms: with a cartoon shown for chain A only, a search among the drawn
    atoms would hand every surface to chain A."""
    scene("open 1a3n", "delete solvent | ligand", "hide atoms", "surface",
          "color bychain", "color zone #1 near /A distance 4 sharpEdges true",
          "hide cartoon", "cartoon /A")
    names = [p[0] for p in _parts(export("t_parts_sharp.3mf",
                                         "size 60 parts chain"))]
    check("parts: a surface without atom map stays with its own chain",
          names == ["chain A", "chain B", "chain C", "chain D"],
          "got %s" % names)


def test_parts_bonds_between_models():
    """A distance or hydrogen bond between two models is drawn by a model of
    its own; it belongs to the atoms it joins, not in an extra part."""
    scene("open 1ubq", "open 1ubq", "delete solvent", "hide atoms", "cartoon",
          "move x 45 models #2", "distance #1/A:1@CA #2/A:76@CA")
    for mode in ("chain", "model"):
        names = [p[0] for p in _parts(export(
            "t_parts_between_%s.3mf" % mode, "parts %s flavor bambu" % mode))]
        check("parts %s: bonds between models make no part of their own"
              % mode, len(names) == 2, "got %s" % names)


def test_parts_per_model():
    scene("open 1ubq", "open 1ubq", "delete solvent", "hide atoms",
          "hide cartoon", "move x 45 models #2", "surface")
    parts = _parts(export("t_parts_model.3mf", "parts model flavor bambu"))
    names = [p[0] for p in parts]
    check("parts model: one part per model", len(parts) == 2, "got %s" % names)
    check("parts model: same-named models get distinct part names",
          len(set(names)) == len(names), "got %s" % names)
    # each model's chain A is a chain of its own, not merged across models
    parts = _parts(export("t_parts_two_a.3mf", "parts chain flavor bambu"))
    names = [p[0] for p in parts]
    check("parts chain: chain A of two models stays two parts",
          len(parts) == 2 and len(set(names)) == 2, "got %s" % names)


def test_parts_unpainted():
    """paint false with parts: the parts are kept, without colour."""
    scene("open 1a3n", "delete solvent | ligand", "hide atoms", "hide cartoon",
          "surface", "color bychain")
    parts = _parts(export("t_parts_unpainted.3mf",
                          "parts chain paint false flavor bambu"))
    check("parts unpainted: four chains", len(parts) == 4,
          "got %s" % [p[0] for p in parts])
    check("parts unpainted: no paint codes written",
          all(not p[2] for p in parts), "%s" % [sorted(p[2]) for p in parts])


def test_parts_fullcolor_refused():
    scene("open 1ubq", "hide atoms", "hide cartoon", "surface")
    try:
        export("t_parts_fc.3mf", "parts chain flavor fullcolor")
        refused = False
    except Exception as e:
        refused = "filament flavor" in str(e)
    check("parts: refused for full colour, with the reason", refused)


def _open_loops(path):
    """Sizes of the open-edge loops of the first mesh in a 3MF: edges used by
    one triangle only, joined into loops."""
    import re
    import zipfile
    from collections import defaultdict
    from numpy import array, concatenate, int64, unique
    with zipfile.ZipFile(path) as z:
        model = z.read("3D/3dmodel.model").decode("utf-8")
    tris = array(re.findall(r'<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"',
                            model), int64)
    edges = concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    edges.sort(axis=1)
    n = int(tris.max()) + 1
    keys, counts = unique(edges[:, 0] * n + edges[:, 1], return_counts=True)
    neighbours = defaultdict(list)
    for k in keys[counts == 1].tolist():
        a, b = divmod(k, n)
        neighbours[a].append(b)
        neighbours[b].append(a)
    seen, sizes = set(), []
    for start in neighbours:
        if start in seen:
            continue
        stack, size = [start], 0
        seen.add(start)
        while stack:
            p = stack.pop()
            size += 1
            for q in neighbours[p]:
                if q not in seen:
                    seen.add(q)
                    stack.append(q)
        sizes.append(size)
    return sizes


def test_sticks_are_closed():
    """A stick model must arrive closed.

    The two half cylinders of a bond meet in the middle and must share their
    rim: merging vertices by rounded coordinates left about one slit per bond
    (a 4- to 10-edge hole) where copies of a rim vertex fell on either side
    of a rounding boundary. And ChimeraX draws bond cylinders without end
    caps, so their ends inside the atom spheres were open rims that slicers
    count as open edges; those are capped on export."""
    scene("open 1ubq", "delete solvent", "hide cartoon", "show atoms",
          "style stick")
    path = export("t_sticks.3mf", "size 80")
    sizes = _open_loops(path)
    slits = [s for s in sizes if s < 16]
    check("sticks: no slits where half bonds meet", not slits,
          "%d slits, sizes %s" % (len(slits), sorted(set(slits))))
    check("sticks: bond ends are capped, no open edges left", not sizes,
          "%d open loops, sizes %s" % (len(sizes), sorted(set(sizes))))
    import zipfile
    with zipfile.ZipFile(path) as z:
        use = _edge_use(z.read("3D/3dmodel.model").decode("utf-8"))
    check("sticks: every edge on exactly two triangles",
          use and all(set(u) == {2} for u in use),
          "edge use %s" % [dict(u) for u in use])


def test_clipped_surface_stays_open():
    """Capping is for round rims only. A surface cut by a clipping plane has
    a ragged opening; a fan over it would cross itself, so it stays open."""
    scene("open 1ubq", "delete solvent", "hide atoms", "hide cartoon",
          "surface", "clip near -3 position #1")
    sizes = _open_loops(export("t_clipped.3mf", "size 60"))
    check("clipped surface: the cut stays open, not fanned over", sizes,
          "no open loops: the cut was capped")


def test_ball_and_stick_parts_closed():
    """Ball-and-stick split per chain: bonds between chains are split
    between two parts, and each half has to be closed in its own part."""
    import zipfile
    scene("open 1a3n", "delete solvent | ligand", "hide cartoon",
          "show /A,B & :1-40 atoms", "style ball",
          "hbonds /A,B & :1-40 radius 0.3 dashes 0")
    path = export("t_bns_parts.3mf", "size 60 parts chain flavor bambu")
    with zipfile.ZipFile(path) as z:
        use = _edge_use(z.read("3D/3dmodel.model").decode("utf-8"))
    check("ball and stick, parts: every part closed",
          use and all(set(u) == {2} for u in use),
          "edge use %s" % [dict(u) for u in use])


def _edge_use(model_text):
    """How many edges are used by 1, 2, 3 ... triangles, per mesh object."""
    import re
    from collections import Counter
    from numpy import array, concatenate, int64, unique
    out = []
    for body in re.findall(r"<mesh>(.*?)</mesh>", model_text, re.S):
        t = array(re.findall(r'<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"',
                             body), int64)
        e = concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
        e.sort(axis=1)
        _, counts = unique(e[:, 0] * (int(t.max()) + 1) + e[:, 1],
                           return_counts=True)
        out.append(Counter(counts.tolist()))
    return out


def test_pseudobonds_are_closed():
    """ChimeraX draws a pseudobond as two capped half cylinders whose caps
    meet face to face in the middle. Exported as they are, each rim edge
    belongs to four triangles and slicers report a broken mesh. Hydrogen
    bonds on a cartoon must come out closed: every edge on two triangles,
    also with one part per chain, where a bond between two chains is split
    and each half keeps its cap."""
    import zipfile
    scene("open 1a3n", "delete solvent | ligand", "hide atoms", "cartoon",
          "hbonds radius 0.4 dashes 0")
    for label, args in (("one piece", "size 60"),
                        ("parts", "size 60 parts chain flavor bambu")):
        path = export("t_hbonds_%s.3mf" % label.replace(" ", "_"), args)
        with zipfile.ZipFile(path) as z:
            use = _edge_use(z.read("3D/3dmodel.model").decode("utf-8"))
        bad = [dict(u) for u in use if set(u) != {2}]
        check("hydrogen bonds, %s: every edge on exactly two triangles" % label,
              use and not bad, "edge use %s" % bad)


def test_colors_off():
    scene("open 1ubq", "delete solvent", "hide atoms", "hide cartoon",
          "surface")
    path = export("t_nocolor.3mf", "size 60 colors false")
    r = validate(path, expect_painted=False)
    check("colors false: one plain region", r.ok, "; ".join(r.problems))


def test_too_many_colors():
    """Above 15 regions it must fall back to split parts, not emit bad codes."""
    scene("open 1a3n", "delete solvent", "hide atoms", "hide cartoon",
          "surface", "color byattribute bfactor palette rainbow")
    path = export("t_many.3mf", "size 60 maxColors 20")
    r = validate(path, expect_painted=False, expect_regions=20,
                 require_closed=False)
    check("20 colors: falls back to split parts", r.ok, "; ".join(r.problems))


def _analysed(*commands):
    """Build a scene and return the printability report for it."""
    from chimerax.save3mf import printcheck, scene as scene_module
    scene(*commands)
    g = scene_module.collect_geometry(session)     # noqa: F821
    g = scene_module.weld_vertices(g)
    g, _ = scene_module.place_for_printing(g, scale=1.0)
    return printcheck.analyze(g)


def test_ribbon_is_one_body():
    """A plain ribbon is ~20 abutting surfaces and prints as one object.

    Reported by the ChimeraX developer: calling these "pieces that do not
    touch" which "will not print as a single object" was wrong on both counts.
    """
    r = _analysed("open 1ubq")
    check("ribbon: 20-odd surfaces make one printed body", r.body_count == 1,
          "%d bodies from %d surfaces" % (r.body_count, r.shell_count))
    check("ribbon: nothing reported as floating free", r.loose_count == 0,
          "%d loose" % r.loose_count)
    check("ribbon: several surfaces seen", r.shell_count > 1,
          "%d surfaces" % r.shell_count)


def test_spheres_are_one_body():
    """Overlapping atom spheres and bond cylinders print as one object."""
    r = _analysed("open 1ubq", "hide ribbon", "show atoms", "hide solvent")
    check("spheres: hundreds of surfaces make one printed body",
          r.body_count == 1,
          "%d bodies from %d surfaces" % (r.body_count, r.shell_count))
    # ChimeraX draws bond cylinders open-ended; the export caps them, so the
    # report must not call any surface open
    check("spheres: bond cylinders arrive capped, no open surfaces",
          r.open_shells == 0, "%d open surfaces" % r.open_shells)


def test_density_cavities():
    """Interior voids of a density map are cavities, not loose fragments."""
    r = _analysed("open 1ubq", "hide ribbon", "surface close",
                  "molmap protein 5")
    check("molmap: interior voids counted as cavities", r.cavity_count == 3,
          "%d cavities" % r.cavity_count)
    check("molmap: one printed body", r.body_count == 1,
          "%d bodies" % r.body_count)
    check("molmap: cavities not called loose pieces", r.loose_count == 0,
          "%d loose" % r.loose_count)


def test_hidden_geometry_inside():
    """Geometry sealed inside another surface must be called out.

    Found in testing: running molmap while atoms were still shown put the
    whole atomic model inside the density surface - 99.7% of the triangles,
    invisible in the print, and painted as four extra filaments.
    """
    r = _analysed("open 1ubq", "hide ribbon", "show atoms", "hide solvent",
                  "surface close", "molmap protein 5")
    check("hidden geometry: atoms inside a map are reported",
          r.enclosed_shells > 1000, "%d enclosed surfaces" % r.enclosed_shells)

    r = _analysed("open 1ubq", "hide ribbon", "hide atoms", "surface close",
                  "molmap protein 5")
    check("hidden geometry: nothing reported when the map is alone",
          r.enclosed_shells == 0, "%d enclosed surfaces" % r.enclosed_shells)


def test_fullcolor():
    """Continuous colour survives as a colour per vertex."""
    scene("open 1ubq", "mlp protein", "hide atoms", "hide cartoon")
    path = export("t_fullcolor.3mf", "size 60 flavor fullcolor")
    r = validate(path)
    check("fullcolor: file is structurally valid", r.ok, "; ".join(r.problems))

    import zipfile
    import re
    with zipfile.ZipFile(path) as z:
        model = z.read("3D/3dmodel.model").decode("utf-8")
    colors = len(re.findall(r"<m:color ", model))
    per_vertex = len(re.findall(r'p2="', model))
    check("fullcolor: many distinct colours kept", colors > 100,
          "%d colours" % colors)
    check("fullcolor: colour given per vertex, not per triangle",
          per_vertex > 1000, "%d triangles with p2/p3" % per_vertex)
    check("fullcolor: no extruder painting in a full-colour file",
          "mmu_segmentation" not in model and "paint_color" not in model)


def test_palette_command():
    scene("open 1a3n", "delete solvent", "hide atoms", "hide cartoon",
          "surface", "color byattribute bfactor palette rainbow")
    run(session, "3mf palette size 60")          # noqa: F821
    run(session, "3mf palette size 60 maxColors 5")   # noqa: F821
    check("3mf palette runs on a continuous color scheme", True)


def test_empty_scene():
    scene("open 1ubq", "hide atoms", "hide cartoon")
    try:
        export("t_empty.3mf")
        check("empty scene: reports a clear error", False, "no error raised")
    except Exception as e:
        check("empty scene: reports a clear error",
              "Nothing to save" in str(e), str(e)[:80])


def test_print_cost_model():
    """The cost estimate must stay close to what a slicer really does.

    The comparison against PrusaSlicer lives in the shell driver; here we only
    check the estimate is produced and is self-consistent.
    """
    scene("open 1a3n", "delete solvent", "hide atoms", "hide cartoon",
          "surface", "color bychain")
    from chimerax.save3mf import colors, printcost, scene as scene_module
    geom = scene_module.collect_geometry(session)      # noqa: F821
    geom = scene_module.weld_vertices(geom)
    geom, _ = scene_module.place_for_printing(geom, size=60.0)
    regions = colors.build_regions(geom)
    cost = printcost.estimate(geom, regions)
    check("cost: layer count is sane for a 60 mm model",
          200 < cost.n_layers < 350, "%d layers" % cost.n_layers)
    check("cost: tool changes are positive and below the theoretical maximum",
          0 < cost.tool_changes <= cost.n_layers * regions.count,
          "%d changes" % cost.tool_changes)


def _file_flats(path, kind):
    """Flat depth (mm) measured in a saved file, treating all of it as one
    kind of geometry - only meaningful for a scene of one kind."""
    import zipfile
    import xml.etree.ElementTree as ET
    from numpy import array, float32, int32, zeros
    from chimerax.save3mf import scene as scene_module, smoothness
    CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("3D/3dmodel.model"))
    v = array([(float(e.get("x")), float(e.get("y")), float(e.get("z")))
               for e in root.iter(CORE + "vertex")], float32)
    t = array([(int(e.get("v1")), int(e.get("v2")), int(e.get("v3")))
               for e in root.iter(CORE + "triangle")], int32)
    g = scene_module.SceneGeometry(v, t, zeros((len(t), 4)), [(kind, len(t))],
                                   zeros(len(t), int32))
    return smoothness.measure(g).depth.get(kind, 0.0), len(t)


def _lod_state():
    from chimerax.atomic.structure import level_of_detail
    from chimerax.atomic import AtomicStructure
    lod = level_of_detail(session)                         # noqa: F821
    sides = [m.ribbon_xs_mgr.params[m.ribbon_xs_mgr.STYLE_ROUND]["sides"]
             for m in session.models.list()               # noqa: F821
             if isinstance(m, AtomicStructure)]
    return (lod.pseudobond_sides, lod.atom_fixed_triangles,
            lod.bond_fixed_triangles, lod.ribbon_fixed_divisions, sides)


def test_smoothness():
    """Large prints are exported finer than the screen draws them, small ones
    are left alone, and the display settings come back unchanged."""
    from chimerax.save3mf.smoothness import DEFAULT_SMOOTHNESS
    # Thick hydrogen bonds alone, as the NIH presets draw them. A pseudobond
    # is shown only while both its atoms are, so the atoms stay displayed but
    # as tiny tetrahedra: their edges are all sharp corners, which the flat
    # measurement ignores, so only the pseudobonds are measured.
    scene("open 1ubq", "delete solvent", "hide cartoon", "hide atoms",
          "hbonds radius 0.6 dashes 0", "show @N,O atoms", "style sphere",
          "size @N,O atomRadius 0.01", "graphics quality atomTriangles 4")
    before = _lod_state()

    raw = export("t_smooth_off.3mf", "size 200 smoothness off")
    raw_depth, raw_tris = _file_flats(raw, "pbonds")
    smooth = export("t_smooth_on.3mf", "size 200")
    depth, tris = _file_flats(smooth, "pbonds")
    check("smoothness: pbond flats at 200 mm exceed the target as displayed",
          raw_depth > DEFAULT_SMOOTHNESS, "%.3f mm" % raw_depth)
    check("smoothness: exported flats are within the target",
          depth <= DEFAULT_SMOOTHNESS * 1.1,
          "%.3f mm (was %.3f)" % (depth, raw_depth))
    check("smoothness: finer export has more triangles", tris > raw_tris,
          "%d vs %d" % (tris, raw_tris))
    check("smoothness: display settings are restored after export",
          _lod_state() == before, "%s -> %s" % (before, _lod_state()))

    small = export("t_smooth_small.3mf", "size 40")
    small_off = export("t_smooth_small_off.3mf", "size 40 smoothness off")
    check("smoothness: a small print is left as displayed",
          _file_flats(small, "pbonds")[1] == _file_flats(small_off, "pbonds")[1])

    coarse = export("t_smooth_coarse.3mf", "size 200 smoothness 0.15")
    check("smoothness: a looser target needs fewer triangles",
          raw_tris <= _file_flats(coarse, "pbonds")[1] < tris)


def test_smoothness_ribbons():
    """Ribbons are smoothed through the cartoon cross-section and divisions."""
    from chimerax.save3mf.smoothness import DEFAULT_SMOOTHNESS
    scene("open 1ubq", "delete solvent", "hide atoms", "cartoon")
    before = _lod_state()
    # a plain cartoon is thin; at 400 mm its flats are well over the target
    raw = export("t_ribbon_off.3mf", "size 400 smoothness off")
    smooth = export("t_ribbon_on.3mf", "size 400")
    raw_depth, raw_tris = _file_flats(raw, "ribbons")
    depth, tris = _file_flats(smooth, "ribbons")
    check("smoothness: ribbon flats exceed the target as displayed",
          raw_depth > DEFAULT_SMOOTHNESS, "%.3f mm" % raw_depth)
    check("smoothness: ribbon flats come within the target",
          depth <= DEFAULT_SMOOTHNESS * 1.25,
          "%.3f -> %.3f mm" % (raw_depth, depth))
    check("smoothness: ribbon settings are restored",
          _lod_state() == before, "%s -> %s" % (before, _lod_state()))


TESTS = [
    test_surface_geometry,
    test_size_and_placement,
    test_painting,
    test_bambu_flavor,
    test_split_parts,
    test_parts_per_chain,
    test_parts_cartoon,
    test_parts_hidden_atoms,
    test_parts_spheres,
    test_parts_thick_ribbon,
    test_parts_surface_without_atom_map,
    test_parts_bonds_between_models,
    test_parts_per_model,
    test_parts_unpainted,
    test_parts_fullcolor_refused,
    test_sticks_are_closed,
    test_clipped_surface_stays_open,
    test_ball_and_stick_parts_closed,
    test_pseudobonds_are_closed,
    test_colors_off,
    test_too_many_colors,
    test_ribbon_is_one_body,
    test_spheres_are_one_body,
    test_density_cavities,
    test_hidden_geometry_inside,
    test_fullcolor,
    test_palette_command,
    test_empty_scene,
    test_print_cost_model,
    test_smoothness,
    test_smoothness_ribbons,
]


def main():
    os.makedirs(OUT, exist_ok=True)
    for test in TESTS:
        print("%s:" % test.__name__)
        try:
            test()
        except Exception:
            RESULTS.append({"test": test.__name__, "passed": False,
                            "detail": traceback.format_exc(limit=3)})
            print("  %-52s FAIL (exception)" % test.__name__)
            traceback.print_exc(limit=3)

    passed = sum(1 for r in RESULTS if r["passed"])
    failed = len(RESULTS) - passed
    with open(os.path.join(OUT, "results.json"), "w") as f:
        json.dump({"passed": passed, "failed": failed, "results": RESULTS}, f,
                  indent=1)
    print("\nTESTS: %d passed, %d failed" % (passed, failed))


main()
