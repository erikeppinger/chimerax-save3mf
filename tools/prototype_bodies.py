"""Prototype: group shells into the bodies a printer will actually produce.

Two shells fuse in the print if their surfaces come within roughly an
extrusion width of each other, whether or not they share any vertices. This
uses a voxel grid at that scale rather than pairwise tests, so it stays linear
in the number of triangles.

    python prototype_bodies.py file.3mf [...]
"""

import sys

import numpy as np

from analyze_shells import read_mesh, shells, signed_volume

FUSE_MM = 0.4          # a 0.4 mm nozzle bridges gaps of about this size


def surface_points(verts, tris, labels):
    """Vertices plus triangle centroids, each tagged with its shell."""
    centroids = verts[tris].mean(axis=1)
    vertex_shell = np.empty(len(verts), dtype=np.int64)
    vertex_shell[tris.ravel()] = np.repeat(labels, 3)
    pts = np.vstack([verts, centroids])
    tags = np.concatenate([vertex_shell, labels])
    return pts, tags


def fuse_groups(pts, tags, n_shells, tau):
    """Group shells that occupy the same voxel, on two offset grids.

    Sorting by (voxel, shell) puts every shell sharing a voxel next to its
    neighbours, so linking consecutive differing shells is enough to connect
    the whole run - no pairwise work and no Python loop over voxels.
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    rows, cols = [], []
    for offset in (0.0, 0.5):
        keys = np.floor(pts / tau + offset).astype(np.int64)
        k = (keys[:, 0] * 1_000_003 + keys[:, 1]) * 1_000_003 + keys[:, 2]
        order = np.lexsort((tags, k))
        ks, ts = k[order], tags[order]
        link = (ks[1:] == ks[:-1]) & (ts[1:] != ts[:-1])
        rows.append(ts[:-1][link])
        cols.append(ts[1:][link])

    r = np.concatenate(rows)
    c = np.concatenate(cols)
    graph = coo_matrix((np.ones(len(r), dtype=np.int8), (r, c)),
                       shape=(n_shells, n_shells))
    _, bodies = connected_components(graph, directed=False)
    return bodies


def main():
    for path in sys.argv[1:]:
        verts, tris = read_mesh(path)
        n, labels = shells(tris)
        vols = np.array([signed_volume(verts, tris[labels == s]) for s in range(n)])
        cavities = vols < 0

        pts, tags = surface_points(verts, tris, labels)
        bodies = fuse_groups(pts, tags, n, FUSE_MM)

        solid = ~cavities
        body_ids = np.unique(bodies[solid])
        name = path.replace("\\", "/").split("/")[-1]
        print("\n=== %s" % name)
        print("  %d triangles, %d topological shells" % (len(tris), n))
        print("  %d interior cavities (inverted winding)" % int(cavities.sum()))
        print("  %d printed bod%s after fusing surfaces within %.1f mm"
              % (len(body_ids), "y" if len(body_ids) == 1 else "ies", FUSE_MM))
        for b in body_ids:
            members = np.flatnonzero(solid & (bodies == b))
            vol = vols[members].sum()
            print("     body %d: %d shells, volume %.1f mm^3 (%.1f%%)"
                  % (b, len(members), vol, 100 * vol / vols[solid].sum()))


if __name__ == "__main__":
    main()
