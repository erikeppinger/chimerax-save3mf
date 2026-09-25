"""How far apart are the "separate" shells of a ChimeraX scene really?

Topological shells say nothing about printing: what matters is whether shells
overlap or touch, in which case a slicer fuses them into one solid. This
measures, for each shell, the distance to the nearest vertex of any other
shell, against the mesh's own triangle edge length as a yardstick.

    python measure_gaps.py file.3mf [file2.3mf ...]
"""

import sys

import numpy as np
from scipy.spatial import cKDTree

from analyze_shells import read_mesh, shells, signed_volume


def main():
    for path in sys.argv[1:]:
        verts, tris = read_mesh(path)
        n, labels = shells(tris)

        edge_len = np.linalg.norm(
            verts[tris[:, 0]] - verts[tris[:, 1]], axis=1)
        median_edge = float(np.median(edge_len))

        vertex_shell = np.empty(len(verts), dtype=np.int64)
        vertex_shell[tris.ravel()] = np.repeat(labels, 3)

        tree = cKDTree(verts)
        # nearest neighbour that belongs to a different shell
        gaps = []
        for s in range(n):
            pts = verts[vertex_shell == s]
            if len(pts) == 0:
                continue
            sample = pts[:: max(1, len(pts) // 400)]
            d, idx = tree.query(sample, k=24)
            other = vertex_shell[idx] != s
            if other.any():
                gaps.append(float(d[other].min()))
            else:
                gaps.append(np.inf)
        gaps = np.array(gaps)

        finite = gaps[np.isfinite(gaps)]
        print("\n=== %s" % path.split("\\")[-1].split("/")[-1])
        print("  %d triangles, %d shells, median triangle edge %.4f mm"
              % (len(tris), n, median_edge))
        if len(finite):
            print("  distance from a shell to the nearest other shell:")
            print("    min %.4f   median %.4f   max %.4f mm"
                  % (finite.min(), np.median(finite), finite.max()))
            print("    shells closer than one triangle edge: %d of %d"
                  % (int((gaps < median_edge).sum()), n))
            print("    shells closer than 0.05 mm:           %d of %d"
                  % (int((gaps < 0.05).sum()), n))
        isolated = int(np.isinf(gaps).sum())
        if isolated:
            print("  shells with no other shell within the search: %d" % isolated)

        vols = np.array([signed_volume(verts, tris[labels == s]) for s in range(n)])
        print("  inverted (cavity) shells: %d of %d"
              % (int((vols < 0).sum()), n))


if __name__ == "__main__":
    main()
