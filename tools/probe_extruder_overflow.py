"""Probe I: where do painted extruders above the printer's tool count go?

Eight stacked slabs, heights 2..16 mm, painted extruders 1..8.  Sliced on a
5-tool printer the two candidate behaviours are easy to tell apart by the
filament usage, since usage follows slab volume:

    surplus all to extruder 1   ->  slab mm [44, 4, 6, 8, 10]
    wrap around modulo 5        ->  slab mm [14, 18, 22, 8, 10]

Run with the ChimeraX python, then slice the result on a 5-tool profile.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import make_probes
from make_probes import (
    CORE_NS, SLIC3RPE_NS, box, triangle_xml, vertex_xml, write_package,
)

# index is the extruder number; 0 means unpainted
MMU_CODES = ["0", "4", "8", "0C", "1C", "2C", "3C", "4C", "5C", "6C", "7C",
             "8C", "9C", "AC", "BC", "CC"]

make_probes.OUT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "probes"))

HEIGHTS = [2, 4, 6, 8, 10, 12, 14, 16]


def main():
    verts, tris, owner = [], [], []
    z = 0.0
    for i, h in enumerate(HEIGHTS):
        v, t = box(0, 0, z, 30.0, 30.0, z + h)
        base = len(verts)
        verts.extend(v)
        tris.extend((a + base, b + base, c + base) for a, b, c in t)
        owner.extend([i] * len(t))
        z += h

    extra = ['slic3rpe:mmu_segmentation="%s"' % MMU_CODES[owner[i] + 1]
             for i in range(len(tris))]
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US" xmlns="%s"'
        ' xmlns:slic3rpe="%s">\n'
        " <resources>\n"
        '  <object id="1" type="model" name="probe I extruder overflow">\n'
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
        '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n'
        ' <object id="1">\n'
        '  <metadata type="object" key="name" value="probe I extruder overflow"/>\n'
        '  <volume firstid="0" lastid="%d">\n'
        '   <metadata type="volume" key="name" value="painted"/>\n'
        '   <mesh edges_fixed="0" degenerate_facets="0" facets_removed="0"'
        ' facets_reversed="0" backwards_edges="0"/>\n'
        "  </volume>\n"
        " </object>\n</config>\n" % (len(tris) - 1)
    )
    write_package("probe_I_extruder_overflow.3mf", xml,
                  {"Metadata/Slic3r_PE_model.config": config})
    print("slab heights (extruder 1..8):", HEIGHTS)


if __name__ == "__main__":
    main()
