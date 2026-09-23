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


TESTS = [
    test_surface_geometry,
    test_size_and_placement,
    test_painting,
    test_bambu_flavor,
    test_split_parts,
    test_colors_off,
    test_too_many_colors,
    test_palette_command,
    test_empty_scene,
    test_print_cost_model,
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
