"""Sanity-check the generated probe files before handing them to a slicer.

Verifies for each package: required parts present, model XML well-formed,
triangle indices in range, and every mesh closed/manifold (each edge used
exactly twice, once in each direction).
"""

import glob
import os
import sys
import zipfile
import xml.etree.ElementTree as ET

CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
REQUIRED = ["[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"]


def check_mesh(obj):
    mesh = obj.find(CORE + "mesh")
    if mesh is None:
        return []  # component-only object
    verts = mesh.find(CORE + "vertices").findall(CORE + "vertex")
    tris = mesh.find(CORE + "triangles").findall(CORE + "triangle")
    problems = []
    nv = len(verts)
    edges = {}
    for t in tris:
        idx = [int(t.get(v)) for v in ("v1", "v2", "v3")]
        if any(i < 0 or i >= nv for i in idx):
            problems.append("triangle index out of range: %s (nv=%d)" % (idx, nv))
            continue
        if len(set(idx)) != 3:
            problems.append("degenerate triangle: %s" % idx)
        a, b, c = idx
        for e in ((a, b), (b, c), (c, a)):
            edges[e] = edges.get(e, 0) + 1
    for (a, b), n in edges.items():
        if n != 1:
            problems.append("edge (%d,%d) used %d times in same direction" % (a, b, n))
        if edges.get((b, a), 0) != 1:
            problems.append("edge (%d,%d) has no opposite twin -> not closed" % (a, b))
    return ["object %s [%d verts, %d tris]" % (obj.get("id"), nv, len(tris))] + problems


def check(path):
    print("\n== %s" % os.path.basename(path))
    ok = True
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        for req in REQUIRED:
            if req not in names:
                print("  MISSING part: %s" % req)
                ok = False
        extras = [n for n in names if n not in REQUIRED]
        if extras:
            print("  extra parts: %s" % ", ".join(extras))
        try:
            root = ET.fromstring(z.read("3D/3dmodel.model"))
        except ET.ParseError as e:
            print("  XML PARSE ERROR: %s" % e)
            return False
        for extra in extras:
            if extra.endswith(".config") or extra.endswith(".xml"):
                try:
                    ET.fromstring(z.read(extra))
                except ET.ParseError as e:
                    print("  XML PARSE ERROR in %s: %s" % (extra, e))
                    ok = False

    if root.get("unit") != "millimeter":
        print("  unit is %r, expected millimeter" % root.get("unit"))
        ok = False

    res = root.find(CORE + "resources")
    objects = res.findall(CORE + "object")
    obj_ids = {o.get("id") for o in objects}
    for o in objects:
        for line in check_mesh(o):
            marker = "  " if line.startswith("object") else "  !! "
            print(marker + line)
            if not line.startswith("object"):
                ok = False
        comps = o.find(CORE + "components")
        if comps is not None:
            refs = [c.get("objectid") for c in comps.findall(CORE + "component")]
            print("  object %s -> components %s" % (o.get("id"), refs))
            for r in refs:
                if r not in obj_ids:
                    print("  !! component references unknown object %s" % r)
                    ok = False

    items = root.find(CORE + "build").findall(CORE + "item")
    if not items:
        print("  !! build has no items")
        ok = False
    for it in items:
        if it.get("objectid") not in obj_ids:
            print("  !! build item references unknown object %s" % it.get("objectid"))
            ok = False
        else:
            print("  build item -> object %s" % it.get("objectid"))
    print("  %s" % ("OK" if ok else "PROBLEMS FOUND"))
    return ok


if __name__ == "__main__":
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "probes")
    files = sorted(glob.glob(os.path.join(d, "*.3mf")))
    if not files:
        sys.exit("no probe files found in %s" % d)
    sys.exit(0 if all([check(f) for f in files]) else 1)
