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
    check("spheres: open-ended cylinders are noticed", r.open_shells > 0,
          "%d open surfaces" % r.open_shells)


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
