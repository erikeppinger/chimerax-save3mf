"""Structural validation of a 3MF package.

Checks the things that have actually gone wrong in this project rather than
conformance to a schema: missing package parts, indices out of range, negative
coordinates (which put a model off the build plate), meshes that are not
closed, paint codes that no slicer would understand, and part configs that do
not line up with the geometry they describe.

    python validate_3mf.py file.3mf [file2.3mf ...]

Exits non-zero if any file has problems.
"""

import sys
import zipfile
import xml.etree.ElementTree as ET

import numpy as np

CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
MAT = "{http://schemas.microsoft.com/3dmanufacturing/material/2015/02}"
SLIC3RPE = "{http://schemas.slic3r.org/3mf/2017/06}"

REQUIRED_PARTS = ["[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"]
MMU_CODES = ["0", "4", "8", "0C", "1C", "2C", "3C", "4C", "5C", "6C", "7C",
             "8C", "9C", "AC", "BC", "CC"]


class Result:
    def __init__(self, path):
        self.path = path
        self.problems = []
        self.facts = {}

    def fail(self, message):
        self.problems.append(message)

    @property
    def ok(self):
        return not self.problems


def validate(path, expect_painted=None, expect_regions=None,
             require_closed=True):
    r = Result(path)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        for part in REQUIRED_PARTS:
            if part not in names:
                r.fail("missing package part: %s" % part)
        if not r.ok:
            return r
        model = z.read("3D/3dmodel.model")
        configs = {n: z.read(n).decode("utf-8") for n in names
                   if n.endswith(".config")}

    try:
        root = ET.fromstring(model)
    except ET.ParseError as e:
        r.fail("3dmodel.model is not well-formed XML: %s" % e)
        return r

    if root.get("unit") != "millimeter":
        r.fail("unit is %r, expected millimeter" % root.get("unit"))

    objects = root.find(CORE + "resources").findall(CORE + "object")
    if not objects:
        r.fail("no objects in resources")
        return r

    total_triangles = 0
    for obj in objects:
        mesh = obj.find(CORE + "mesh")
        if mesh is None:
            continue
        verts, tris, codes = _read_mesh(mesh)
        total_triangles += len(tris)
        _check_mesh(r, obj.get("id"), verts, tris, require_closed)
        _check_paint(r, obj.get("id"), codes, len(tris))

    r.facts["triangles"] = total_triangles
    r.facts["objects"] = len(objects)
    r.facts["painted"] = _painted_count(root)

    _check_build(r, root, objects)
    for name, text in configs.items():
        _check_config(r, name, text, total_triangles)

    if expect_painted is not None:
        if bool(r.facts["painted"]) != bool(expect_painted):
            r.fail("expected painted=%s but found %d painted triangles"
                   % (expect_painted, r.facts["painted"]))
    if expect_regions is not None:
        found = _region_count(root, configs)
        if found != expect_regions:
            r.fail("expected %d color regions, found %d"
                   % (expect_regions, found))
    return r


# --------------------------------------------------------------- mesh checks

def _read_mesh(mesh):
    verts = np.array([[float(v.get("x")), float(v.get("y")), float(v.get("z"))]
                      for v in mesh.find(CORE + "vertices")], dtype=float)
    tri_elements = list(mesh.find(CORE + "triangles"))
    tris = np.array([[int(t.get("v1")), int(t.get("v2")), int(t.get("v3"))]
                     for t in tri_elements], dtype=np.int64) \
        if tri_elements else np.zeros((0, 3), dtype=np.int64)
    codes = []
    for t in tri_elements:
        code = None
        for key, value in t.attrib.items():
            if key.endswith("mmu_segmentation") or key == "paint_color":
                code = value
        codes.append(code)
    return verts, tris, codes


def _check_mesh(r, object_id, verts, tris, require_closed):
    where = "object %s" % object_id
    if len(verts) == 0 or len(tris) == 0:
        r.fail("%s: empty mesh" % where)
        return
    if not np.isfinite(verts).all():
        r.fail("%s: non-finite vertex coordinates" % where)
    if (verts < -1e-6).any():
        r.fail("%s: negative coordinates (model would sit off the build plate)"
               % where)
    if tris.min() < 0 or tris.max() >= len(verts):
        r.fail("%s: triangle index out of range" % where)
        return
    degenerate = ((tris[:, 0] == tris[:, 1]) | (tris[:, 1] == tris[:, 2])
                  | (tris[:, 0] == tris[:, 2])).sum()
    if degenerate:
        r.fail("%s: %d degenerate triangles" % (where, degenerate))

    if require_closed:
        edges = np.sort(np.concatenate(
            [tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]), axis=1)
        _, counts = np.unique(edges, axis=0, return_counts=True)
        open_edges = int((counts == 1).sum())
        nonmanifold = int((counts > 2).sum())
        if open_edges or nonmanifold:
            r.fail("%s: not closed (%d open edges, %d non-manifold edges)"
                   % (where, open_edges, nonmanifold))


def _check_paint(r, object_id, codes, n_triangles):
    painted = [c for c in codes if c]
    if not painted:
        return
    if len(painted) != n_triangles:
        r.fail("object %s: %d of %d triangles painted; a slicer expects all "
               "or none" % (object_id, len(painted), n_triangles))
    bad = sorted({c for c in painted if c not in MMU_CODES})
    if bad:
        r.fail("object %s: unknown paint codes %s" % (object_id, bad))


def _painted_count(root):
    return sum(1 for _ in root.iter(CORE + "triangle")
               if any(k.endswith("mmu_segmentation") or k == "paint_color"
                      for k in _.attrib))


def _check_build(r, root, objects):
    build = root.find(CORE + "build")
    items = build.findall(CORE + "item") if build is not None else []
    if not items:
        r.fail("build section has no items")
        return
    ids = {o.get("id") for o in objects}
    for item in items:
        if item.get("objectid") not in ids:
            r.fail("build item references unknown object %s"
                   % item.get("objectid"))


# ------------------------------------------------------------- config checks

def _check_config(r, name, text, total_triangles):
    try:
        cfg = ET.fromstring(text)
    except ET.ParseError as e:
        r.fail("%s is not well-formed XML: %s" % (name, e))
        return

    if name.endswith("Slic3r_PE_model.config"):
        for obj in cfg.findall("object"):
            spans = []
            for vol in obj.findall("volume"):
                first, last = int(vol.get("firstid")), int(vol.get("lastid"))
                if first > last:
                    r.fail("%s: volume range %d..%d is inverted"
                           % (name, first, last))
                spans.append((first, last))
            _check_spans(r, name, spans, total_triangles)
    elif name.endswith("model_settings.config"):
        if not cfg.findall(".//part"):
            r.fail("%s: no parts declared" % name)


def _check_spans(r, name, spans, total_triangles):
    if not spans:
        return
    spans.sort()
    if spans[0][0] != 0:
        r.fail("%s: volumes start at triangle %d, not 0" % (name, spans[0][0]))
    for (a_first, a_last), (b_first, b_last) in zip(spans, spans[1:]):
        if b_first != a_last + 1:
            r.fail("%s: gap or overlap between triangle ranges %d..%d and "
                   "%d..%d" % (name, a_first, a_last, b_first, b_last))
    if spans[-1][1] != total_triangles - 1:
        r.fail("%s: volumes end at triangle %d but the mesh has %d"
               % (name, spans[-1][1], total_triangles))


def _region_count(root, configs):
    """How many colour regions the file declares, whichever way it does it."""
    painted_codes = set()
    for t in root.iter(CORE + "triangle"):
        for key, value in t.attrib.items():
            if key.endswith("mmu_segmentation") or key == "paint_color":
                painted_codes.add(value)
    if painted_codes:
        return len(painted_codes)
    for name, text in configs.items():
        cfg = ET.fromstring(text)
        volumes = cfg.findall(".//volume")
        if volumes:
            return len(volumes)
        parts = cfg.findall(".//part")
        if parts:
            return len(parts)
    return 1


def main():
    paths = sys.argv[1:]
    if not paths:
        sys.exit(__doc__)
    failed = 0
    for path in paths:
        r = validate(path)
        status = "OK" if r.ok else "PROBLEMS"
        print("%-40s %s  %s" % (path.split("\\")[-1], status, r.facts))
        for p in r.problems:
            print("    !! %s" % p)
        failed += 0 if r.ok else 1
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
