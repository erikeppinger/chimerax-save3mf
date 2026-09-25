"""Prototype: classify the shells of a 3MF the way a slicer would see them.

A ChimeraX scene is almost never stitched together. Ribbons are separate
surfaces per secondary-structure element, atoms are separate spheres, and they
abut or overlap rather than sharing vertices. Topological connectivity
therefore says almost nothing about what will print.

What matters:
  * signed volume  - a shell wound inside-out is an interior cavity, not a part
  * overlap        - shells that intersect or touch fuse into one printed body
  * isolation      - only a shell that touches nothing else prints separately

    python analyze_shells.py file.3mf
"""

import sys
import zipfile
import xml.etree.ElementTree as ET

import numpy as np

CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"


def read_mesh(path):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("3D/3dmodel.model"))
    obj = root.find(CORE + "resources").find(CORE + "object")
    mesh = obj.find(CORE + "mesh")
    verts = np.array([[float(v.get("x")), float(v.get("y")), float(v.get("z"))]
                      for v in mesh.find(CORE + "vertices")], dtype=float)
    tris = np.array([[int(t.get("v1")), int(t.get("v2")), int(t.get("v3"))]
                     for t in mesh.find(CORE + "triangles")], dtype=np.int64)
    return verts, tris


def shells(tris):
    """Label triangles by edge-connected piece."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    nt = len(tris)
    edges = np.empty((3 * nt, 2), dtype=tris.dtype)
    edges[0::3] = tris[:, [0, 1]]
    edges[1::3] = tris[:, [1, 2]]
    edges[2::3] = tris[:, [2, 0]]
    edges = np.sort(edges, axis=1)
    _, ids = np.unique(edges, axis=0, return_inverse=True)
    ids = ids.ravel()
    # edge 3i+k belongs to triangle i
    tri_of_edge = np.repeat(np.arange(nt), 3)
    order = ids.argsort(kind="stable")
    e, t = ids[order], tri_of_edge[order]
    same = e[1:] == e[:-1]
    graph = coo_matrix((np.ones(same.sum(), dtype=np.int8),
                        (t[:-1][same], t[1:][same])), shape=(nt, nt))
    n, labels = connected_components(graph, directed=False)
    return n, labels


def signed_volume(verts, tris):
    a, b, c = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def point_inside(p, a, b, c, lo, hi):
    m = ((lo[:, 0] <= p[0]) & (hi[:, 0] >= p[0]) &
         (lo[:, 1] <= p[1]) & (hi[:, 1] >= p[1]) & (hi[:, 2] >= p[2]))
    if not m.any():
        return False
    A, B, C = a[m], b[m], c[m]
    v0, v1 = C[:, :2] - A[:, :2], B[:, :2] - A[:, :2]
    v2 = p[:2] - A[:, :2]
    d00 = (v0 * v0).sum(1); d01 = (v0 * v1).sum(1); d11 = (v1 * v1).sum(1)
    d20 = (v2 * v0).sum(1); d21 = (v2 * v1).sum(1)
    den = d00 * d11 - d01 * d01
    ok = np.abs(den) > 1e-12
    den = np.where(ok, den, 1.0)
    u = (d11 * d20 - d01 * d21) / den
    v = (d00 * d21 - d01 * d20) / den
    hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1)
    if not hit.any():
        return False
    z = A[hit, 2] + u[hit] * (C[hit, 2] - A[hit, 2]) + v[hit] * (B[hit, 2] - A[hit, 2])
    return bool((z > p[2]).sum() % 2 == 1)


def main():
    verts, tris = read_mesh(sys.argv[1])
    n, labels = shells(tris)
    print("%d triangles, %d topological shells" % (len(tris), n))

    info = []
    for s in range(n):
        t = tris[labels == s]
        used = np.unique(t)
        pts = verts[used]
        info.append({
            "tris": t, "pts": pts,
            "vol": signed_volume(verts, t),
            "lo": pts.min(0), "hi": pts.max(0),
        })

    total = sum(abs(i["vol"]) for i in info) or 1.0
    order = sorted(range(n), key=lambda s: -abs(info[s]["vol"]))
    print("\n  shell  triangles  signed volume   %of total  orientation")
    for s in order[:12]:
        i = info[s]
        print("  %5d  %9d  %13.2f  %8.2f%%  %s"
              % (s, len(i["tris"]), i["vol"], 100 * abs(i["vol"]) / total,
                 "outward (solid)" if i["vol"] > 0 else "INVERTED (cavity)"))
    if n > 12:
        print("  ... %d more" % (n - 12))

    # is each small shell inside the largest one?
    big = order[0]
    A = verts[info[big]["tris"][:, 0]]
    B = verts[info[big]["tris"][:, 1]]
    C = verts[info[big]["tris"][:, 2]]
    lo = np.minimum(np.minimum(A, B), C)
    hi = np.maximum(np.maximum(A, B), C)
    print("\n  containment in the largest shell (%d):" % big)
    for s in order[1:min(n, 12)]:
        pts = info[s]["pts"]
        sample = pts[:: max(1, len(pts) // 6)][:6]
        inside = [point_inside(p, A, B, C, lo, hi) for p in sample]
        print("    shell %-5d %d/%d sampled points inside"
              % (s, sum(inside), len(inside)))


if __name__ == "__main__":
    main()
