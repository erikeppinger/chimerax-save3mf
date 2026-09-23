"""Dump what a 3MF package actually contains: objects, meshes, build items with
their transforms, colour resources, and PrusaSlicer's own volume/extruder config.

Used to read back what PrusaSlicer preserved after a --export-3mf round trip.

    python inspect_3mf.py file.3mf [file2.3mf ...]
"""

import os
import sys
import zipfile
import xml.etree.ElementTree as ET

CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
MAT = "{http://schemas.microsoft.com/3dmanufacturing/material/2015/02}"


def zrange(mesh):
    zs = [float(v.get("z")) for v in mesh.find(CORE + "vertices").findall(CORE + "vertex")]
    return (min(zs), max(zs)) if zs else (0.0, 0.0)


def dump(path):
    print("\n=== %s" % os.path.basename(path))
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        print("  parts: %s" % ", ".join(names))
        root = ET.fromstring(z.read("3D/3dmodel.model"))
        config = None
        for n in names:
            if n.endswith("Slic3r_PE_model.config"):
                config = ET.fromstring(z.read(n))

    res = root.find(CORE + "resources")

    for bm in res.findall(CORE + "basematerials"):
        cols = [(b.get("name"), b.get("displaycolor")) for b in bm.findall(CORE + "base")]
        print("  basematerials id=%s: %s" % (bm.get("id"), cols))
    for cg in res.findall(MAT + "colorgroup"):
        cols = [c.get("color") for c in cg.findall(MAT + "color")]
        print("  m:colorgroup id=%s: %s" % (cg.get("id"), cols))

    for o in res.findall(CORE + "object"):
        mesh = o.find(CORE + "mesh")
        desc = "  object id=%s name=%r pid=%s" % (o.get("id"), o.get("name"), o.get("pid"))
        if mesh is not None:
            tris = mesh.find(CORE + "triangles").findall(CORE + "triangle")
            painted = [t.get("pid") for t in tris if t.get("pid")]
            lo, hi = zrange(mesh)
            print("%s tris=%d z=[%.1f..%.1f] per-tri-pid=%d" %
                  (desc, len(tris), lo, hi, len(painted)))
            custom = {k for t in tris for k in t.attrib if k not in
                      ("v1", "v2", "v3", "pid", "p1", "p2", "p3")}
            if custom:
                print("       extra triangle attributes: %s" % sorted(custom))
        else:
            comps = o.find(CORE + "components")
            refs = [c.get("objectid") for c in comps.findall(CORE + "component")] if comps is not None else []
            print("%s components=%s" % (desc, refs))

    for it in root.find(CORE + "build").findall(CORE + "item"):
        print("  build item -> object %s transform=%r" % (it.get("objectid"), it.get("transform")))

    if config is not None:
        print("  -- Slic3r_PE_model.config --")
        for o in config.findall("object"):
            print("  config object id=%s" % o.get("id"))
            for md in o.findall("metadata"):
                print("     %s=%s" % (md.get("key"), md.get("value")))
            for v in o.findall("volume"):
                kv = {md.get("key"): md.get("value") for md in v.findall("metadata")}
                print("     volume tris %s..%s  %s" % (v.get("firstid"), v.get("lastid"), kv))


if __name__ == "__main__":
    for p in sys.argv[1:]:
        dump(p)
