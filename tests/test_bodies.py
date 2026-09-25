"""Body-grouping tests on geometry whose answer is known by construction.

The diagnostics claim things about printing that a user will act on, so the
rules behind them are checked against shapes where the correct answer is not a
matter of opinion: boxes that overlap, boxes with a measured gap, a box inside
a box, and a shell wound inside-out.

    python test_bodies.py        (with the ChimeraX python)
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from make_probes import box            # noqa: E402
import printcheck                      # noqa: E402


class Geom:
    """The bits of SceneGeometry that printcheck uses."""

    def __init__(self, vertices, triangles):
        self.vertices = vertices
        self.triangles = triangles

    def bounds(self):
        return self.vertices.min(axis=0), self.vertices.max(axis=0)


def build(boxes, invert=()):
    verts, tris = [], []
    for i, (x0, y0, z0, x1, y1, z1) in enumerate(boxes):
        v, t = box(x0, y0, z0, x1, y1, z1)
        base = len(verts)
        verts.extend(v)
        for a, b, c in t:
            # reversing the winding turns a solid into a void
            tris.append((a + base, c + base, b + base) if i in invert
                        else (a + base, b + base, c + base))
    return Geom(np.array(verts, dtype=float), np.array(tris, dtype=np.int64))


CASES = [
    # name, boxes, inverted shells, expected bodies, expected cavities
    ("two boxes overlapping",
     [(0, 0, 0, 10, 10, 10), (5, 0, 0, 15, 10, 10)], (), 1, 0),
    ("two boxes touching exactly",
     [(0, 0, 0, 10, 10, 10), (10, 0, 0, 20, 10, 10)], (), 1, 0),
    ("two boxes 0.2 mm apart (fuses when printed)",
     [(0, 0, 0, 10, 10, 10), (10.2, 0, 0, 20, 10, 10)], (), 1, 0),
    ("two boxes 2 mm apart (genuinely separate)",
     [(0, 0, 0, 10, 10, 10), (12, 0, 0, 22, 10, 10)], (), 2, 0),
    ("overlapping pair plus a distant box",
     [(0, 0, 0, 10, 10, 10), (5, 0, 0, 15, 10, 10), (30, 0, 0, 40, 10, 10)],
     (), 2, 0),
    ("box with an interior cavity",
     [(0, 0, 0, 20, 20, 20), (8, 8, 8, 12, 12, 12)], (1,), 1, 1),
    ("three boxes in a chain, each touching the next",
     [(0, 0, 0, 10, 10, 10), (10, 0, 0, 20, 10, 10), (20, 0, 0, 30, 10, 10)],
     (), 1, 0),
]


def main():
    failures = 0
    for name, boxes, invert, want_bodies, want_cavities in CASES:
        report = printcheck.analyze(build(boxes, invert))
        ok = (report.body_count == want_bodies
              and report.cavity_count == want_cavities)
        failures += 0 if ok else 1
        print("  %-46s bodies %d/%d  cavities %d/%d  %s"
              % (name, report.body_count, want_bodies,
                 report.cavity_count, want_cavities, "pass" if ok else "FAIL"))

    # a cavity must not be reported as a loose piece
    report = printcheck.analyze(build(CASES[5][1], CASES[5][2]))
    loose_ok = report.loose_count == 0
    failures += 0 if loose_ok else 1
    print("  %-46s loose %d/0  %s"
          % ("cavity is not called a loose piece", report.loose_count,
             "pass" if loose_ok else "FAIL"))

    print("\nBODY TESTS: %d passed, %d failed" % (len(CASES) + 1 - failures,
                                                  failures))
    return failures


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
