"""How deep do support ends reach into what they join?

Run inside ChimeraX on the current scene:

    runscript tools/measure_joints.py

For every displayed pseudobond (hydrogen-bond supports, struts) it takes the
two end points of the drawn cylinder and asks, against the displayed ribbon
mesh: is the end inside the ribbon, and how far from its surface? A support
whose end only just touches the ribbon is joined by little more than the
cylinder's cross-section; one that ends deep inside has its side wall in
contact too.

Distances are in Angstrom (scene units); multiply by the export scale
(mm per Angstrom) for millimetres in the print.
"""

import numpy as np

from chimerax.atomic import all_pseudobond_groups


def _ribbon_mesh(session):
    from chimerax.save3mf import scene
    g = scene.collect_geometry(session)
    names = g.source_names
    keep = np.array([names[i] == "ribbons" for i in g.triangle_sources])
    return g.vertices.astype(float), g.triangles[keep]


def _point_triangle_distance(p, a, b, c):
    """Distance from point p to each triangle (a, b, c), vectorised over
    triangles. Ericson, Real-Time Collision Detection, 5.1.5."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = p - b
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = p - c
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va = d3 * d6 - d5 * d4
    vb = d5 * d2 - d1 * d6
    vc = d1 * d4 - d3 * d2
    denom = va + vb + vc
    denom[denom == 0] = 1e-30
    v, w = vb / denom, vc / denom
    closest = a + ab * v[:, None] + ac * w[:, None]
    # vertex and edge regions
    m = (d1 <= 0) & (d2 <= 0); closest[m] = a[m]
    m = (d3 >= 0) & (d4 <= d3); closest[m] = b[m]
    m = (d6 >= 0) & (d5 <= d6); closest[m] = c[m]
    m = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
    t = d1 / np.where(d1 - d3 == 0, 1e-30, d1 - d3)
    closest[m] = (a + ab * t[:, None])[m]
    m = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
    t = d2 / np.where(d2 - d6 == 0, 1e-30, d2 - d6)
    closest[m] = (a + ac * t[:, None])[m]
    m = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
    t = (d4 - d3) / np.where((d4 - d3) + (d5 - d6) == 0, 1e-30,
                             (d4 - d3) + (d5 - d6))
    closest[m] = (b + (c - b) * t[:, None])[m]
    return np.sqrt(((p - closest) ** 2).sum(1))


def _inside(p, a, b, c):
    """Ray parity, majority over three directions."""
    votes = 0
    for d in (np.array([1.0, 0.31, 0.17]), np.array([-0.23, 1.0, 0.41]),
              np.array([0.37, -0.29, 1.0])):
        d = d / np.linalg.norm(d)
        e1, e2 = b - a, c - a
        h = np.cross(d, e2)
        det = (e1 * h).sum(1)
        ok = np.abs(det) > 1e-12
        f = np.where(ok, 1.0 / np.where(ok, det, 1), 0)
        s = p - a
        u = f * (s * h).sum(1)
        q = np.cross(s, e1)
        v = f * (q @ d)
        t = f * (e2 * q).sum(1)
        hits = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0)
        votes += int(hits.sum()) % 2
    return votes >= 2


def measure(session):
    """One row per support end: (group, atom, radius, depth, kind, stub).

    depth  > 0: the end is inside the ribbon by that much
    kind   embedded  end inside the ribbon
           pierces   end outside, but the support enters the ribbon nearer
                     its middle: the end sticks out past the ribbon surface
                     by `stub`
           touching  never enters the ribbon, side wall within reach of it
           gap       never comes within its own radius of the ribbon
    """
    v, t = _ribbon_mesh(session)
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    rows = []
    for g in all_pseudobond_groups(session):
        for pb in g.pseudobonds:
            if not pb.display or not pb.shown:
                continue
            # pseudobonds are drawn to effective coordinates: the ribbon
            # position for backbone atoms shown as ribbon, else the atom
            ends = [np.array(x.structure.scene_position * x.effective_coord,
                             dtype=float) for x in pb.atoms]
            for i, atom in enumerate(pb.atoms):
                p, q = ends[i], ends[1 - i]
                d = float(_point_triangle_distance(p, a, b, c).min())
                inside = _inside(p, a, b, c)
                depth = d if inside else -d
                kind, stub = "embedded", 0.0
                if not inside:
                    # walk from this end towards the middle of the support
                    length = np.linalg.norm(q - p)
                    entry, nearest = None, d
                    for f in np.linspace(0.0, 0.5, 26)[1:]:
                        x = p + (q - p) * f
                        if _inside(x, a, b, c):
                            entry = f * length
                            break
                        nearest = min(nearest, float(
                            _point_triangle_distance(x, a, b, c).min()))
                    if entry is not None:
                        kind, stub = "pierces", entry
                    elif nearest < pb.radius:
                        kind = "touching"
                    else:
                        kind = "gap"
                rows.append((g.name, str(atom), pb.radius, depth, kind, stub))
    return rows


rows = measure(session)                     # noqa: F821
from collections import Counter
print("JOINTS %d support ends, radius %.2f A" % (len(rows), rows[0][2]))
for kind, n in Counter(r[4] for r in rows).most_common():
    stubs = [r[5] for r in rows if r[4] == kind]
    extra = ""
    if kind == "pierces":
        extra = ", sticking out by median %.2f A, max %.2f A" % (
            np.median(stubs), max(stubs))
    print("JOINTS %-9s %3d%s" % (kind, n, extra))
emb = [r[3] for r in rows if r[4] == "embedded"]
if emb:
    print("JOINTS embedded ends: depth median %.2f A, max %.2f A"
          % (np.median(emb), max(emb)))
for r in rows:
    if r[4] in ("gap", "touching"):
        print("JOINTS %-8s %s" % (r[4], r[1]))
