"""Measure what a tool change actually costs in print time.

Exports the same scene at several colour counts, slices each one, and fits
print time against tool changes.  The geometry is identical every time, so the
slope is the per-tool-change cost and the intercept is the time the print
would take with no colour at all.

    python calibrate_time.py [output.json]

Run with the ChimeraX python.  Takes a few minutes: it really does slice.
"""

import json
import os
import re
import subprocess
import sys

import numpy as np

CHIMERAX = r"C:\Program Files\ChimeraX 1.12\bin\ChimeraX-console.exe"
PRUSA = r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe"
BUNDLE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BUNDLE, "tests", "out")

SCENE = ("open 1a3n; delete solvent; hide atoms; hide cartoon; surface; "
         "color byattribute bfactor palette rainbow")
COLOR_COUNTS = [1, 2, 3, 4, 5, 6, 8, 10]
SIZE_MM = 60

PROFILE = ["--printer-profile", "Original Prusa XL - 5T Input Shaper 0.4 nozzle",
           "--print-profile", "0.20mm SPEED @XLIS 0.4",
           "--material-profile", "Generic PLA @XLIS"]


def export(k):
    path = os.path.join(OUT, "cal_%02d.3mf" % k)
    args = "size %d" % SIZE_MM
    args += " colors false" if k == 1 else " maxColors %d" % k
    cmd = "%s; save %s %s; exit" % (SCENE, path.replace("\\", "/"), args)
    subprocess.run([CHIMERAX, "--nogui", "--exit", "--silent", "--cmd", cmd],
                   capture_output=True)
    return path if os.path.exists(path) else None


def slice_it(path, k):
    gcode = os.path.join(OUT, "cal_%02d.gcode" % k)
    subprocess.run([PRUSA, "--slice", "--binary-gcode=0"] + PROFILE +
                   ["-o", gcode, path], capture_output=True)
    if not os.path.exists(gcode):
        return None
    with open(gcode, errors="ignore") as f:
        text = f.read()
    changes = len(re.findall(r"(?m)^T\d", text))
    match = re.search(r"estimated printing time \(normal mode\) = (.*)", text)
    return changes, _seconds(match.group(1)) if match else None


def _seconds(text):
    total = 0
    for value, unit in re.findall(r"(\d+)([dhms])", text):
        total += int(value) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit]
    return total


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for k in COLOR_COUNTS:
        path = export(k)
        if not path:
            print("  %2d colors: export failed" % k)
            continue
        result = slice_it(path, k)
        if not result:
            print("  %2d colors: slice failed" % k)
            continue
        changes, seconds = result
        rows.append({"colors": k, "changes": changes, "seconds": seconds})
        print("  %2d colors: %5d tool changes, %s"
              % (k, changes, _hhmm(seconds)))

    if len(rows) < 3:
        sys.exit("not enough data points to fit")

    changes = np.array([r["changes"] for r in rows], dtype=float)
    seconds = np.array([r["seconds"] for r in rows], dtype=float)
    slope, intercept = np.polyfit(changes, seconds, 1)
    predicted = slope * changes + intercept
    residual = np.abs(predicted - seconds)

    print()
    print("seconds per tool change : %.1f" % slope)
    print("print time with no color: %s" % _hhmm(intercept))
    print("worst fit error         : %s (%.1f%%)"
          % (_hhmm(residual.max()), 100.0 * (residual / seconds).max()))

    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(OUT, "time_fit.json")
    with open(out, "w") as f:
        json.dump({"rows": rows, "seconds_per_change": slope,
                   "base_seconds": intercept}, f, indent=1)
    print("wrote", out)


def _hhmm(seconds):
    seconds = int(round(seconds))
    return "%dh %02dm" % (seconds // 3600, (seconds % 3600) // 60)


if __name__ == "__main__":
    main()
