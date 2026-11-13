"""Probes for writing one 3MF object (or part) per chain.

Question: can a file hold several painted pieces that stay where they were
relative to each other, so a two-chain complex can be handled per chain in the
slicer without losing its colours or its assembly?

Two boxes stand in for two chains in contact:

    A  30 x 30 x 20 mm at (0, 0, 0), sitting on the bed
       painted: top face extruder 2, everything else extruder 1
    B  20 x 20 x 20 mm at (32, 5, 8), floating 8 mm above the bed, 2 mm from A
       painted: top face extruder 3, everything else extruder 2

B floats on purpose: a chain of a complex rarely touches the bed, and a slicer
that drops every object onto the bed would take the assembly apart.

    J1  PrusaSlicer encoding, two objects, two build items
    J2  PrusaSlicer encoding, one object, two volumes (triangle ranges)
    K1  Bambu/Orca encoding, two objects, two build items
    K2  Bambu/Orca encoding, one object, two component parts

    & "C:\\Program Files\\ChimeraX 1.12\\bin\\python.exe" tools\\probe_objects.py [out_dir]
    & "C:\\Program Files\\ChimeraX 1.12\\bin\\python.exe" tools\\probe_objects.py --read file.3mf ...

--read reports, for any 3MF (including what a slicer saved), every mesh with
the lowest corner of its world-space bounding box and its paint codes, and
for the two largest pieces the distance between their centres and their
height difference. Those two numbers survive a slicer turning or moving the
whole model while arranging the plate; coordinates do not.
"""

import collections
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_probes import CONTENT_TYPES, RELS, CORE_NS, MAT_NS, box  # noqa: E402

SLIC3RPE_NS = "http://schemas.slic3r.org/3mf/2017/06"
CODES = ["", "4", "8", "0C"]                       # extruder N -> CODES[N]
TOP = {2, 3}                                       # indices of the +z triangles

PIECES = [  # name, box, extruder on top, extruder elsewhere
    ("chain A", (0, 0, 0, 30, 30, 20), 2, 1),
    ("chain B", (32, 5, 8, 52, 25, 28), 3, 2),
]
IDENTITY = "1 0 0 0 1 0 0 0 1 0 0 0"


def mesh_xml(verts, tris, codes, attribute, indent="   "):
    out = [indent + "<mesh>", indent + " <vertices>"]
    out += ['%s  <vertex x="%g" y="%g" z="%g"/>' % ((indent,) + v) for v in verts]
    out += [indent + " </vertices>", indent + " <triangles>"]
    out += ['%s  <triangle v1="%d" v2="%d" v3="%d" %s="%s"/>'
            % ((indent,) + t + (attribute, c)) for t, c in zip(tris, codes)]
    out += [indent + " </triangles>", indent + "</mesh>"]
    return "\n".join(out)


def pieces():
    for name, b, top, rest in PIECES:
        verts, tris = box(*b)
        codes = [CODES[top if i in TOP else rest] for i in range(len(tris))]
        yield name, verts, tris, codes


def header(prusa):
    ns = ' xmlns:slic3rpe="%s"' % SLIC3RPE_NS if prusa else ""
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<model unit="millimeter" xml:lang="en-US" xmlns="%s" xmlns:m="%s"%s>\n'
            % (CORE_NS, MAT_NS, ns))


def multi_object(prusa):
    attribute = "slic3rpe:mmu_segmentation" if prusa else "paint_color"
    model = [header(prusa), " <resources>"]
    config = ['<?xml version="1.0" encoding="UTF-8"?>', "<config>"]
    for i, (name, verts, tris, codes) in enumerate(pieces(), start=1):
        model.append('  <object id="%d" type="model" name="%s">' % (i, name))
        model.append(mesh_xml(verts, tris, codes, attribute))
        model.append("  </object>")
        if prusa:
            config += [' <object id="%d">' % i,
                       '  <metadata type="object" key="name" value="%s"/>' % name,
                       '  <volume firstid="0" lastid="%d">' % (len(tris) - 1),
                       '   <metadata type="volume" key="name" value="%s"/>' % name,
                       "  </volume>", " </object>"]
        else:
            config += ['  <object id="%d">' % i,
                       '   <metadata key="name" value="%s"/>' % name,
                       '   <metadata key="extruder" value="1"/>',
                       '    <part id="%d" subtype="normal_part">' % i,
                       '     <metadata key="name" value="%s"/>' % name,
                       '     <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>',
                       "    </part>", "  </object>"]
    model += [" </resources>", " <build>"]
    model += ['  <item objectid="%d" transform="%s"/>' % (i, IDENTITY)
              for i in (1, 2)]
    model += [" </build>", "</model>", ""]
    config += ["</config>", ""]
    name = "Slic3r_PE_model.config" if prusa else "model_settings.config"
    return "\n".join(model), {"Metadata/" + name: "\n".join(config)}


def prusa_volumes():
    model = [header(True), " <resources>",
             '  <object id="1" type="model" name="complex">']
    verts, tris, codes, ranges = [], [], [], []
    for name, v, t, c in pieces():
        offset = len(verts)
        ranges.append((name, len(tris), len(tris) + len(t) - 1))
        verts += v
        tris += [(a + offset, b + offset, d + offset) for a, b, d in t]
        codes += c
    model.append(mesh_xml(verts, tris, codes, "slic3rpe:mmu_segmentation"))
    model += ["  </object>", " </resources>", " <build>",
              '  <item objectid="1" transform="%s"/>' % IDENTITY,
              " </build>", "</model>", ""]
    config = ['<?xml version="1.0" encoding="UTF-8"?>', "<config>", ' <object id="1">',
              '  <metadata type="object" key="name" value="complex"/>']
    for name, first, last in ranges:
        config += ['  <volume firstid="%d" lastid="%d">' % (first, last),
                   '   <metadata type="volume" key="name" value="%s"/>' % name,
                   "  </volume>"]
    config += [" </object>", "</config>", ""]
    return "\n".join(model), {"Metadata/Slic3r_PE_model.config": "\n".join(config)}


def bambu_parts():
    model = [header(False), " <resources>"]
    config = ['<?xml version="1.0" encoding="UTF-8"?>', "<config>", '  <object id="1">',
              '   <metadata key="name" value="complex"/>',
              '   <metadata key="extruder" value="1"/>']
    for i, (name, verts, tris, codes) in enumerate(pieces(), start=10):
        model.append('  <object id="%d" type="model" name="%s">' % (i, name))
        model.append(mesh_xml(verts, tris, codes, "paint_color"))
        model.append("  </object>")
        config += ['    <part id="%d" subtype="normal_part">' % i,
                   '     <metadata key="name" value="%s"/>' % name,
                   '     <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>',
                   "    </part>"]
    model += ['  <object id="1" type="model" name="complex">', "   <components>",
              '    <component objectid="10"/>', '    <component objectid="11"/>',
              "   </components>", "  </object>", " </resources>", " <build>",
              '  <item objectid="1" transform="%s"/>' % IDENTITY,
              " </build>", "</model>", ""]
    config += ["  </object>", "</config>", ""]
    return "\n".join(model), {"Metadata/model_settings.config": "\n".join(config)}


def write(path, model, extra):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("3D/3dmodel.model", model)
        for name, data in extra.items():
            z.writestr(name, data)


# ------------------------------------------------------------------ reading

def _matrix(text):
    """3MF 'm00 m01 m02 m10 ... m32' -> function applying it to a point."""
    m = [float(x) for x in (text or IDENTITY).split()]

    def apply(p):
        x, y, z = p
        return (x * m[0] + y * m[3] + z * m[6] + m[9],
                x * m[1] + y * m[4] + z * m[7] + m[10],
                x * m[2] + y * m[5] + z * m[8] + m[11])
    return apply


def _attr(tag, name):
    m = re.search(r'(?:^|\s)(?:[\w]+:)?%s="([^"]*)"' % name, tag)
    return m.group(1) if m else None


def read(path):
    z = zipfile.ZipFile(path)
    files = {n: z.read(n).decode("utf-8") for n in z.namelist() if n.endswith(".model")}
    objects = {}                      # (file, id) -> body
    for name, text in files.items():
        for m in re.finditer(r'<object\s([^>]*)>(.*?)</object>', text, re.S):
            objects[("/" + name, _attr(m.group(1), "id"))] = (m.group(1), m.group(2))

    volumes = collections.defaultdict(list)   # Prusa: object id -> ranges
    if "Metadata/Slic3r_PE_model.config" in z.namelist():
        config = z.read("Metadata/Slic3r_PE_model.config").decode("utf-8")
        for o in re.finditer(r'<object id="(\d+)"[^>]*>(.*?)</object>', config, re.S):
            for v in re.finditer(r'<volume firstid="(\d+)" lastid="(\d+)">(.*?)</volume>',
                                 o.group(2), re.S):
                name = re.search(r'key="name" value="([^"]*)"', v.group(3))
                volumes[o.group(1)].append((int(v.group(1)), int(v.group(2)),
                                            name.group(1) if name else "volume"))
    meshes = []

    def walk(key, transforms, label):
        head, body = objects[key]
        label = label or _attr(head, "name") or key[1]
        if "<mesh" in body:
            verts = [tuple(float(v) for v in m.groups()) for m in re.finditer(
                r'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"', body)]
            for t in transforms:
                verts = [t(v) for v in verts]
            tris = re.findall(r"<triangle\s[^>]*>", body)
            ranges = ((volumes.get(key[1]) if key[0] == "/3D/3dmodel.model"
                       else None) or [(0, len(tris) - 1, label)])
            for first, last, part in ranges:
                sub = tris[first:last + 1]
                used = {int(i) for t in sub for i in re.findall(r'v\d="(\d+)"', t)}
                paint = collections.Counter(
                    _attr(t, "paint_color") or _attr(t, "mmu_segmentation") or "-"
                    for t in sub)
                low = [min(verts[j][i] for j in used) for i in range(3)]
                centre = [sum(verts[j][i] for j in used) / len(used)
                          for i in range(3)]
                meshes.append((part if len(ranges) > 1 else label, len(sub), low,
                               dict(paint), centre))
        for c in re.finditer(r"<component\s([^>]*)/>", body):
            target = (_attr(c.group(1), "path") or key[0], _attr(c.group(1), "objectid"))
            walk(target, [_matrix(_attr(c.group(1), "transform"))] + transforms, None)

    root = files["3D/3dmodel.model"]
    items = re.findall(r"<item\s([^>]*)/>", root)
    print("== %s: %d build item(s)" % (os.path.basename(path), len(items)))
    for item in items:
        before = len(meshes)
        walk(("/3D/3dmodel.model", _attr(item, "objectid")),
             [_matrix(_attr(item, "transform"))], None)
        for label, n, low, paint, _ in meshes[before:]:
            print("   item %-3s %-28s %3d tris  min=(%7.2f %7.2f %7.2f)  paint=%s"
                  % (_attr(item, "objectid"), label, n, low[0], low[1], low[2], paint))
    painted = sum(1 for m in meshes if "-" not in m[3])
    print("   summary: items=%d pieces=%d painted=%d"
          % (len(items), len(meshes), painted))     # parsed by run_all.ps1
    # A slicer may move and turn the whole model about z when it arranges the
    # plate, so compare what survives that: the distance between the two
    # largest pieces' centres, and their height difference.
    if len(meshes) >= 2:
        a, b = sorted(sorted(meshes, key=lambda m: -m[1])[:2],
                      key=lambda m: str(m[0]))
        d = [b[4][i] - a[4][i] for i in range(3)]
        print("   centres %s -> %s: distance %.2f mm, height difference %.2f mm"
              % (a[0], b[0], sum(x * x for x in d) ** 0.5, d[2]))


def main():
    if sys.argv[1:2] == ["--read"]:
        for path in sys.argv[2:]:
            read(path)
        return
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "probes")
    os.makedirs(out, exist_ok=True)
    for tag, (model, extra) in [("J1_prusa_objects", multi_object(True)),
                                ("J2_prusa_volumes", prusa_volumes()),
                                ("K1_bambu_objects", multi_object(False)),
                                ("K2_bambu_parts", bambu_parts())]:
        path = os.path.join(out, "probe_%s.3mf" % tag)
        write(path, model, extra)
        read(path)


if __name__ == "__main__":
    main()
