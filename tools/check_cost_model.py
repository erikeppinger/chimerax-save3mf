"""Validate the tool-change estimate against a real sliced G-code.

Reads a painted 3MF, works out which print layers each painted extruder
appears in, and compares two candidate estimates with the tool-change count
actually produced by the slicer.

    python check_cost_model.py painted.3mf sliced.gcode [layer_height]
"""

import re
import sys
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
MMU_CODES = ["0", "4", "8", "0C", "1C", "2C", "3C", "4C", "5C", "6C", "7C",
             "8C", "9C", "AC", "BC", "CC"]

# how far the estimate may drift from the slicer before the test suite fails
TOLERANCE_PERCENT = 5.0


def read_painted(path):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("3D/3dmodel.model"))
    mesh = root.find(CORE + "resources").find(CORE + "object").find(CORE + "mesh")
    verts = np.array([[float(v.get("x")), float(v.get("y")), float(v.get("z"))]
                      for v in mesh.find(CORE + "vertices")], dtype=float)
    tris, codes = [], []
    for t in mesh.find(CORE + "triangles"):
        tris.append([int(t.get("v1")), int(t.get("v2")), int(t.get("v3"))])
        code = None
        for key, value in t.attrib.items():
            if key.endswith("mmu_segmentation") or key == "paint_color":
                code = value
        codes.append(MMU_CODES.index(code) if code else 0)
    return verts, np.array(tris), np.array(codes)


def layer_presence(verts, tris, labels, layer_height):
    z = verts[:, 2]
    lo = np.floor(z[tris].min(axis=1) / layer_height).astype(int)
    hi = np.floor(z[tris].max(axis=1) / layer_height).astype(int)
    n_layers = int(hi.max()) + 1
    regions = sorted(set(labels.tolist()))
    presence = np.zeros((len(regions), n_layers), dtype=bool)
    for i, r in enumerate(regions):
        m = labels == r
        diff = np.zeros(n_layers + 1, dtype=np.int32)
        np.add.at(diff, lo[m], 1)
        np.add.at(diff, np.minimum(hi[m] + 1, n_layers), -1)
        presence[i] = np.cumsum(diff)[:n_layers] > 0
    return regions, presence


def main():
    mf, gcode = sys.argv[1], sys.argv[2]
    layer_height = float(sys.argv[3]) if len(sys.argv) > 3 else 0.2

    verts, tris, labels = read_painted(mf)
    regions, presence = layer_presence(verts, tris, labels, layer_height)
    per_layer = presence.sum(axis=0)
    n_layers = presence.shape[1]

    measured = len(re.findall(r"(?m)^T\d", open(gcode, errors="ignore").read()))

    print("%d layers at %.2f mm, %d painted regions" %
          (n_layers, layer_height, len(regions)))
    for i, r in enumerate(regions):
        touched = int(presence[i].sum())
        share = 100.0 * (labels == r).sum() / len(labels)
        print("   extruder %-2d  %6.1f%% of triangles   appears in %4d/%d layers"
              % (r, share, touched, n_layers))

    est_sum = int(per_layer.sum())
    est_sum_minus_one = int(np.maximum(per_layer - 1, 0).sum())
    error = 100.0 * (est_sum_minus_one - measured) / measured
    print()
    print("measured tool changes in G-code : %d" % measured)
    print("estimate, regions per layer     : %d  (%+.0f%%)"
          % (est_sum, 100.0 * (est_sum - measured) / measured))
    print("estimate, regions per layer - 1 : %d  (%+.1f%%)  <- the one we use"
          % (est_sum_minus_one, error))

    if abs(error) > TOLERANCE_PERCENT:
        print("FAIL: estimate is off by more than %.0f%%" % TOLERANCE_PERCENT)
        sys.exit(1)
    print("OK: within %.0f%%" % TOLERANCE_PERCENT)


if __name__ == "__main__":
    main()
