"""Generate small 3MF probe files to find out what PrusaSlicer (and other slicers)
actually honour when importing colour information.

Each probe is the same physical shape: three stacked 30x30x10 mm slabs
(red / green / blue, bottom to top), 36 triangles total.  Only the way the
colour is *expressed* differs between probes.

    A  one object, one mesh, Materials-extension <m:colorgroup>, per-triangle
    B  wrapper object with three <component> children, each a separate object
       carrying a core-spec <basematerials> colour
    C  PrusaSlicer-native: one object/one mesh plus Metadata/Slic3r_PE_model.config
       declaring three volumes by triangle range, each with an extruder number
    D  one object, one mesh, core-spec <basematerials> referenced per triangle

Run with the ChimeraX python (no third-party dependencies needed):
    & "C:\\Program Files\\ChimeraX 1.12\\bin\\python.exe" make_probes.py
"""

import os
import zipfile

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "probes")

# bottom, middle, top slab colours
COLORS = [("Red", "#FF3333FF"), ("Green", "#22CC55FF"), ("Blue", "#3366FFFF")]

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
 <Default Extension="config" ContentType="application/vnd.ms-printing.printticket+xml"/>
</Types>
"""

RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
"""

CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
MAT_NS = "http://schemas.microsoft.com/3dmanufacturing/material/2015/02"


def box(x0, y0, z0, x1, y1, z1):
    """Return (vertices, triangles) for an axis-aligned box, outward normals."""
    verts = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]
    tris = [
        (0, 2, 1), (0, 3, 2),        # bottom  -z
        (4, 5, 6), (4, 6, 7),        # top     +z
        (0, 1, 5), (0, 5, 4),        # front   -y
        (1, 2, 6), (1, 6, 5),        # right   +x
        (2, 3, 7), (2, 7, 6),        # back    +y
        (3, 0, 4), (3, 4, 7),        # left    -x
    ]
    return verts, tris


def slabs():
    """Three stacked slabs as one merged mesh; returns (verts, tris, slab_of_tri)."""
    verts, tris, owner = [], [], []
    for i in range(3):
        v, t = box(0, 0, i * 10.0, 30.0, 30.0, (i + 1) * 10.0)
        base = len(verts)
        verts.extend(v)
        tris.extend((a + base, b + base, c + base) for a, b, c in t)
        owner.extend([i] * len(t))
    return verts, tris, owner


def vertex_xml(verts, indent="    "):
    return "\n".join(
        '%s<vertex x="%g" y="%g" z="%g"/>' % (indent, x, y, z) for x, y, z in verts
    )


def triangle_xml(tris, extra=None, indent="    "):
    """extra: optional list of attribute strings, one per triangle."""
    out = []
    for i, (a, b, c) in enumerate(tris):
        att = "" if extra is None else " " + extra[i]
        out.append('%s<triangle v1="%d" v2="%d" v3="%d"%s/>' % (indent, a, b, c, att))
    return "\n".join(out)


def write_package(name, model_xml, extra_files=None):
    path = os.path.join(OUT_DIR, name)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("3D/3dmodel.model", model_xml)
        for fn, data in (extra_files or {}).items():
            z.writestr(fn, data)
    print("wrote %s (%d bytes)" % (path, os.path.getsize(path)))


def model_header(with_materials_ns=True):
    ns = ' xmlns:m="%s"' % MAT_NS if with_materials_ns else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US" xmlns="%s"%s>\n'
        ' <metadata name="Application">ChimeraX 3MF probe</metadata>\n'
        % (CORE_NS, ns)
    )


# ---------------------------------------------------------------- probe A
def probe_a():
    """Materials-extension colorgroup, referenced per triangle."""
    verts, tris, owner = slabs()
    colors = "\n".join('   <m:color color="%s"/>' % c for _, c in COLORS)
    extra = ['pid="2" p1="%d"' % owner[i] for i in range(len(tris))]
    xml = model_header() + (
        " <resources>\n"
        '  <m:colorgroup id="2">\n%s\n  </m:colorgroup>\n'
        '  <object id="1" type="model" name="probe A colorgroup">\n'
        "   <mesh>\n"
        "    <vertices>\n%s\n    </vertices>\n"
        "    <triangles>\n%s\n    </triangles>\n"
        "   </mesh>\n"
        "  </object>\n"
        " </resources>\n"
        " <build>\n"
        '  <item objectid="1"/>\n'
        " </build>\n"
        "</model>\n"
        % (colors, vertex_xml(verts, "     "), triangle_xml(tris, extra, "     "))
    )
    write_package("probe_A_colorgroup.3mf", xml)


# ---------------------------------------------------------------- probe B
def probe_b():
    """Three separate objects pulled together as components of one wrapper."""
    parts = []
    for i, (cname, chex) in enumerate(COLORS):
        verts, tris = box(0, 0, i * 10.0, 30.0, 30.0, (i + 1) * 10.0)
        oid = 10 + i
        parts.append(
            '  <basematerials id="%d">\n'
            '   <base name="%s" displaycolor="%s"/>\n'
            "  </basematerials>\n"
            '  <object id="%d" type="model" pid="%d" pindex="0" name="part %s">\n'
            "   <mesh>\n"
            "    <vertices>\n%s\n    </vertices>\n"
            "    <triangles>\n%s\n    </triangles>\n"
            "   </mesh>\n"
            "  </object>\n"
            % (100 + i, cname, chex, oid, 100 + i, cname,
               vertex_xml(verts, "     "), triangle_xml(tris, None, "     "))
        )
    components = "\n".join('    <component objectid="%d"/>' % (10 + i) for i in range(3))
    xml = model_header() + (
        " <resources>\n%s"
        '  <object id="1" type="model" name="probe B components">\n'
        "   <components>\n%s\n   </components>\n"
        "  </object>\n"
        " </resources>\n"
        " <build>\n"
        '  <item objectid="1"/>\n'
        " </build>\n"
        "</model>\n" % ("".join(parts), components)
    )
    write_package("probe_B_components.3mf", xml)


# ---------------------------------------------------------------- probe C
def probe_c():
    """PrusaSlicer-native: one mesh + model.config volumes with extruder numbers."""
    verts, tris, _ = slabs()
    xml = model_header(with_materials_ns=False) + (
        " <resources>\n"
        '  <object id="1" type="model" name="probe C prusa volumes">\n'
        "   <mesh>\n"
        "    <vertices>\n%s\n    </vertices>\n"
        "    <triangles>\n%s\n    </triangles>\n"
        "   </mesh>\n"
        "  </object>\n"
        " </resources>\n"
        " <build>\n"
        '  <item objectid="1"/>\n'
        " </build>\n"
        "</model>\n"
        % (vertex_xml(verts, "     "), triangle_xml(tris, None, "     "))
    )
    vols = []
    for i, (cname, _) in enumerate(COLORS):
        first, last = i * 12, i * 12 + 11
        vols.append(
            '  <volume firstid="%d" lastid="%d">\n'
            '   <metadata type="volume" key="name" value="%s"/>\n'
            '   <metadata type="volume" key="extruder" value="%d"/>\n'
            '   <mesh edges_fixed="0" degenerate_facets="0" facets_removed="0"'
            ' facets_reversed="0" backwards_edges="0"/>\n'
            "  </volume>\n" % (first, last, cname, i + 1)
        )
    config = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<config>\n"
        ' <object id="1">\n'
        '  <metadata type="object" key="name" value="probe C prusa volumes"/>\n'
        "%s"
        " </object>\n"
        "</config>\n" % "".join(vols)
    )
    write_package("probe_C_prusa_volumes.3mf", xml,
                  {"Metadata/Slic3r_PE_model.config": config})


# ---------------------------------------------------------------- probe D
def probe_d():
    """Core-spec basematerials referenced per triangle (no extension needed)."""
    verts, tris, owner = slabs()
    bases = "\n".join(
        '   <base name="%s" displaycolor="%s"/>' % (n, c) for n, c in COLORS
    )
    extra = ['pid="5" p1="%d"' % owner[i] for i in range(len(tris))]
    xml = model_header(with_materials_ns=False) + (
        " <resources>\n"
        '  <basematerials id="5">\n%s\n  </basematerials>\n'
        '  <object id="1" type="model" pid="5" pindex="0" name="probe D basematerials">\n'
        "   <mesh>\n"
        "    <vertices>\n%s\n    </vertices>\n"
        "    <triangles>\n%s\n    </triangles>\n"
        "   </mesh>\n"
        "  </object>\n"
        " </resources>\n"
        " <build>\n"
        '  <item objectid="1"/>\n'
        " </build>\n"
        "</model>\n"
        % (bases, vertex_xml(verts, "     "), triangle_xml(tris, extra, "     "))
    )
    write_package("probe_D_basematerials.3mf", xml)



# ---------------------------------------------------------------- probe E
def probe_e():
    """Combined: Prusa volumes + m:colorgroup + basematerials in one package.

    Checks that the colour tags other slicers read do not disturb the
    Slic3r_PE_model.config route that PrusaSlicer actually honours.
    """
    verts, tris, owner = slabs()
    colors = "\n".join('   <m:color color="%s"/>' % c for _, c in COLORS)
    bases = "\n".join(
        '   <base name="%s" displaycolor="%s"/>' % (n, c) for n, c in COLORS
    )
    extra = ['pid="2" p1="%d" p2="%d" p3="%d"' % (owner[i], owner[i], owner[i])
             for i in range(len(tris))]
    xml = model_header() + (
        " <resources>\n"
        '  <basematerials id="5">\n%s\n  </basematerials>\n'
        '  <m:colorgroup id="2">\n%s\n  </m:colorgroup>\n'
        '  <object id="1" type="model" name="probe E combined">\n'
        "   <mesh>\n"
        "    <vertices>\n%s\n    </vertices>\n"
        "    <triangles>\n%s\n    </triangles>\n"
        "   </mesh>\n"
        "  </object>\n"
        " </resources>\n"
        " <build>\n"
        '  <item objectid="1"/>\n'
        " </build>\n"
        "</model>\n"
        % (bases, colors, vertex_xml(verts, "     "),
           triangle_xml(tris, extra, "     "))
    )
    vols = []
    for i, (cname, _) in enumerate(COLORS):
        vols.append(
            '  <volume firstid="%d" lastid="%d">\n'
            '   <metadata type="volume" key="name" value="%s"/>\n'
            '   <metadata type="volume" key="extruder" value="%d"/>\n'
            '   <mesh edges_fixed="0" degenerate_facets="0" facets_removed="0"'
            ' facets_reversed="0" backwards_edges="0"/>\n'
            "  </volume>\n" % (i * 12, i * 12 + 11, cname, i + 1)
        )
    config = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<config>\n"
        ' <object id="1">\n'
        '  <metadata type="object" key="name" value="probe E combined"/>\n'
        "%s"
        " </object>\n"
        "</config>\n" % "".join(vols)
    )
    write_package("probe_E_combined.3mf", xml,
                  {"Metadata/Slic3r_PE_model.config": config})


# ---------------------------------------------------------------- probe F
def probe_f():
    """Bambu/Orca-native: component parts + Metadata/model_settings.config.

    Mirrors the layout Bambu Studio and OrcaSlicer write themselves: a wrapper
    object made of component children, with per-part extruder assignment in
    their own config file rather than in Slic3r_PE_model.config.
    """
    parts, comps, cfg_parts = [], [], []
    for i, (cname, chex) in enumerate(COLORS):
        verts, tris = box(0, 0, i * 10.0, 30.0, 30.0, (i + 1) * 10.0)
        oid = 10 + i
        parts.append(
            '  <object id="%d" type="model" name="%s">\n'
            "   <mesh>\n"
            "    <vertices>\n%s\n    </vertices>\n"
            "    <triangles>\n%s\n    </triangles>\n"
            "   </mesh>\n"
            "  </object>\n"
            % (oid, cname, vertex_xml(verts, "     "),
               triangle_xml(tris, None, "     "))
        )
        comps.append('    <component objectid="%d"/>' % oid)
        cfg_parts.append(
            '    <part id="%d" subtype="normal_part">\n'
            '     <metadata key="name" value="%s"/>\n'
            '     <metadata key="extruder" value="%d"/>\n'
            '     <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
            "    </part>\n" % (oid, cname, i + 1)
        )
    xml = model_header(with_materials_ns=False) + (
        " <resources>\n%s"
        '  <object id="1" type="model" name="probe F bambu parts">\n'
        "   <components>\n%s\n   </components>\n"
        "  </object>\n"
        " </resources>\n"
        " <build>\n"
        '  <item objectid="1" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>\n'
        " </build>\n"
        "</model>\n" % ("".join(parts), "\n".join(comps))
    )
    config = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<config>\n"
        '  <object id="1">\n'
        '   <metadata key="name" value="probe F bambu parts"/>\n'
        '   <metadata key="extruder" value="1"/>\n'
        "%s"
        "  </object>\n"
        "</config>\n" % "".join(cfg_parts)
    )
    write_package("probe_F_bambu_parts.3mf", xml,
                  {"Metadata/model_settings.config": config})


# ---------------------------------------------------------------- probe G
def probe_g():
    """Universal candidate: component parts carrying BOTH config flavours.

    Geometry as components (what Bambu/Orca need) plus Slic3r_PE_model.config
    volume ranges over the concatenated triangles (what PrusaSlicer needs),
    plus colorgroup/basematerials for generic viewers.
    """
    parts, comps, bambu_parts, prusa_vols = [], [], [], []
    colors = "\n".join('   <m:color color="%s"/>' % c for _, c in COLORS)
    bases = "\n".join(
        '   <base name="%s" displaycolor="%s"/>' % (n, c) for n, c in COLORS
    )
    for i, (cname, chex) in enumerate(COLORS):
        verts, tris = box(0, 0, i * 10.0, 30.0, 30.0, (i + 1) * 10.0)
        oid = 10 + i
        extra = ['pid="2" p1="%d" p2="%d" p3="%d"' % (i, i, i)] * len(tris)
        parts.append(
            '  <object id="%d" type="model" name="%s" pid="5" pindex="%d">\n'
            "   <mesh>\n"
            "    <vertices>\n%s\n    </vertices>\n"
            "    <triangles>\n%s\n    </triangles>\n"
            "   </mesh>\n"
            "  </object>\n"
            % (oid, cname, i, vertex_xml(verts, "     "),
               triangle_xml(tris, extra, "     "))
        )
        comps.append('    <component objectid="%d"/>' % oid)
        bambu_parts.append(
            '    <part id="%d" subtype="normal_part">\n'
            '     <metadata key="name" value="%s"/>\n'
            '     <metadata key="extruder" value="%d"/>\n'
            '     <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
            "    </part>\n" % (oid, cname, i + 1)
        )
        prusa_vols.append(
            '  <volume firstid="%d" lastid="%d">\n'
            '   <metadata type="volume" key="name" value="%s"/>\n'
            '   <metadata type="volume" key="extruder" value="%d"/>\n'
            '   <mesh edges_fixed="0" degenerate_facets="0" facets_removed="0"'
            ' facets_reversed="0" backwards_edges="0"/>\n'
            "  </volume>\n" % (i * 12, i * 12 + 11, cname, i + 1)
        )
    xml = model_header() + (
        " <resources>\n"
        '  <basematerials id="5">\n%s\n  </basematerials>\n'
        '  <m:colorgroup id="2">\n%s\n  </m:colorgroup>\n'
        "%s"
        '  <object id="1" type="model" name="probe G universal">\n'
        "   <components>\n%s\n   </components>\n"
        "  </object>\n"
        " </resources>\n"
        " <build>\n"
        '  <item objectid="1" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>\n'
        " </build>\n"
        "</model>\n" % (bases, colors, "".join(parts), "\n".join(comps))
    )
    bambu_cfg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<config>\n"
        '  <object id="1">\n'
        '   <metadata key="name" value="probe G universal"/>\n'
        '   <metadata key="extruder" value="1"/>\n'
        "%s"
        "  </object>\n"
        "</config>\n" % "".join(bambu_parts)
    )
    prusa_cfg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<config>\n"
        ' <object id="1">\n'
        '  <metadata type="object" key="name" value="probe G universal"/>\n'
        "%s"
        " </object>\n"
        "</config>\n" % "".join(prusa_vols)
    )
    write_package("probe_G_universal.3mf", xml,
                  {"Metadata/model_settings.config": bambu_cfg,
                   "Metadata/Slic3r_PE_model.config": prusa_cfg})


# ---------------------------------------------------------------- probe H
SLIC3RPE_NS = "http://schemas.slic3r.org/3mf/2017/06"

# per the community-documented encoding: colour index 0..2 -> (i << 2),
# colour index 3+ -> "C" preceded by the extension nibble.  Extruder N is
# said to be colour index N-1.  That offset is exactly what this probe tests.
MMU_CODES = ["0", "4", "8", "0C", "1C", "2C", "3C", "4C"]


def probe_h():
    """PrusaSlicer MMU painting: ONE mesh, per-triangle extruder, no volumes.

    Splitting a mesh into per-colour volumes leaves every patch with open
    edges.  Painting assigns extruders per triangle instead, so the mesh stays
    whole.  Slabs have deliberately different volumes (1:2:3) so the sliced
    filament usage says which extruder each code really means.
    """
    heights = [(0.0, 5.0), (5.0, 15.0), (15.0, 30.0)]
    verts, tris, owner = [], [], []
    for i, (z0, z1) in enumerate(heights):
        v, t = box(0, 0, z0, 30.0, 30.0, z1)
        base = len(verts)
        verts.extend(v)
        tris.extend((a + base, b + base, c + base) for a, b, c in t)
        owner.extend([i] * len(t))

    # slab 0 -> code for "extruder 2", slab 1 -> "3", slab 2 -> "4"
    extra = ['slic3rpe:mmu_segmentation="%s"' % MMU_CODES[owner[i] + 1]
             for i in range(len(tris))]

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US" xmlns="%s" xmlns:slic3rpe="%s">\n'
        ' <metadata name="Application">ChimeraX 3MF probe</metadata>\n'
        " <resources>\n"
        '  <object id="1" type="model" name="probe H mmu painting">\n'
        "   <mesh>\n"
        "    <vertices>\n%s\n    </vertices>\n"
        "    <triangles>\n%s\n    </triangles>\n"
        "   </mesh>\n"
        "  </object>\n"
        " </resources>\n"
        " <build>\n"
        '  <item objectid="1" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>\n'
        " </build>\n"
        "</model>\n"
        % (CORE_NS, SLIC3RPE_NS, vertex_xml(verts, "     "),
           triangle_xml(tris, extra, "     "))
    )
    config = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<config>\n"
        ' <object id="1">\n'
        '  <metadata type="object" key="name" value="probe H mmu painting"/>\n'
        '  <volume firstid="0" lastid="%d">\n'
        '   <metadata type="volume" key="name" value="painted"/>\n'
        '   <mesh edges_fixed="0" degenerate_facets="0" facets_removed="0"'
        ' facets_reversed="0" backwards_edges="0"/>\n'
        "  </volume>\n"
        " </object>\n"
        "</config>\n" % (len(tris) - 1)
    )
    write_package("probe_H_mmu_paint.3mf", xml,
                  {"Metadata/Slic3r_PE_model.config": config})


if __name__ == "__main__":
    OUT_DIR = os.path.abspath(OUT_DIR)
    os.makedirs(OUT_DIR, exist_ok=True)
    probe_a()
    probe_b()
    probe_c()
    probe_d()
    probe_e()
    probe_f()
    probe_g()
    probe_h()
