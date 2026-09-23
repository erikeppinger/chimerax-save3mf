"""Compare the print-time estimate with the measured calibration runs.

calibrate_time.py slices the same scene at several colour counts and records
the real tool-change count and print time.  This re-estimates each of those
cases from the exported 3MF alone and reports the error, so the model can be
checked without slicing again.

    python check_time_model.py [tests/out/time_fit.json]
"""

import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

import numpy as np

CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
MMU_CODES = ["0", "4", "8", "0C", "1C", "2C", "3C", "4C", "5C", "6C", "7C",
             "8C", "9C", "AC", "BC", "CC"]

SECONDS_PER_TOOL_CHANGE = 18.4
TOOLS = 5
LAYER_HEIGHT = 0.2
TOLERANCE_PERCENT = 15.0


def painted_labels(path):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("3D/3dmodel.model"))
    mesh = root.find(CORE + "resources").find(CORE + "object").find(CORE + "mesh")
    verts = np.array([[float(v.get("x")), float(v.get("y")), float(v.get("z"))]
                      for v in mesh.find(CORE + "vertices")], dtype=float)
    tris, labels = [], []
    for t in mesh.find(CORE + "triangles"):
        tris.append([int(t.get("v1")), int(t.get("v2")), int(t.get("v3"))])
        code = next((v for k, v in t.attrib.items()
                     if k.endswith("mmu_segmentation") or k == "paint_color"),
                    None)
        labels.append(MMU_CODES.index(code) if code else 1)
    return verts, np.array(tris), np.array(labels)


def estimate_changes(verts, tris, extruders):
    z = verts[:, 2]
    low = np.floor(z[tris].min(axis=1) / LAYER_HEIGHT).astype(int)
    high = np.floor(z[tris].max(axis=1) / LAYER_HEIGHT).astype(int)
    n_layers = int(high.max()) + 1
    groups = sorted(set(extruders.tolist()))
    presence = np.zeros((len(groups), n_layers), dtype=bool)
    for i, g in enumerate(groups):
        m = extruders == g
        diff = np.zeros(n_layers + 1, dtype=np.int32)
        np.add.at(diff, low[m], 1)
        np.add.at(diff, np.minimum(high[m] + 1, n_layers), -1)
        presence[i] = np.cumsum(diff)[:n_layers] > 0
    return int(np.maximum(presence.sum(axis=0) - 1, 0).sum()), n_layers


def main():
    fit_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tests", "out", "time_fit.json")
    with open(fit_path) as f:
        fit = json.load(f)
    out_dir = os.path.dirname(fit_path)

    print("%-8s %10s %10s %8s   %10s %10s %8s" %
          ("colors", "changes", "estimated", "error", "time", "estimated",
           "error"))
    worst = 0.0
    for row in fit["rows"]:
        k = row["colors"]
        path = os.path.join(out_dir, "cal_%02d.3mf" % k)
        if not os.path.exists(path):
            continue
        verts, tris, labels = painted_labels(path)
        extruders = np.where(labels > TOOLS, 1, labels)
        changes, _ = estimate_changes(verts, tris, extruders)
        seconds = changes * SECONDS_PER_TOOL_CHANGE
        # the model estimates only the tool-change part of the print
        measured_overhead = row["seconds"] - fit["base_seconds"]
        change_err = (100.0 * (changes - row["changes"]) / row["changes"]
                      if row["changes"] else 0.0)
        time_err = (100.0 * (seconds - measured_overhead) / measured_overhead
                    if measured_overhead > 60 else 0.0)
        worst = max(worst, abs(time_err))
        print("%-8d %10d %10d %7.1f%%   %10s %10s %7.1f%%" %
              (k, row["changes"], changes, change_err,
               _hhmm(measured_overhead), _hhmm(seconds), time_err))

    print("\nworst tool-change-time error: %.1f%%" % worst)
    if worst > TOLERANCE_PERCENT:
        print("FAIL: outside %.0f%%" % TOLERANCE_PERCENT)
        sys.exit(1)
    print("OK: within %.0f%%" % TOLERANCE_PERCENT)


def _hhmm(seconds):
    seconds = int(round(max(seconds, 0)))
    return "%dh %02dm" % (seconds // 3600, (seconds % 3600) // 60)


if __name__ == "__main__":
    main()
