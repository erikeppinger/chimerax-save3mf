# vim: set expandtab shiftwidth=4 softtabstop=4:
"""What a slicer will make of the geometry, described honestly.

ChimeraX scenes are almost never stitched together. A ribbon is a separate
surface per helix, strand and coil; atoms are separate spheres; bond cylinders
are open-ended tubes. These pieces abut or overlap rather than sharing
vertices, so *topological* connectivity says almost nothing about what will
print. Reporting it as if it did produces alarming nonsense - "20 pieces that
do not touch" for a plain ribbon, or "loose fragments" for the interior
cavities of a density map.

What actually decides the outcome:

  * **Winding.** A closed shell wound inside-out bounds a void, not a solid.
    Density-map surfaces routinely contain such cavities. Slicers fill the
    space inside an odd number of surfaces, so a cavity simply stays empty.

  * **Proximity.** Two shells whose surfaces come within about an extrusion
    width fuse into one printed body, whether or not they share vertices.
    That is why 600 overlapping atom spheres print as one object.

  * **Isolation.** Only a piece that touches nothing else prints separately -
    a water, an ion, a ligand sitting in space.

This module measures those three things and never modifies geometry.
Preparing a structure for printing - struts, thickened ribbons, solvent
removal - is the job of the NIH 3D print presets bundle.
"""

from numpy import (
    abs as np_abs, arange, argsort, bincount, concatenate, cross, einsum,
    empty, floor, int64, int8, lexsort, maximum, ones, repeat, sort, sqrt,
    unique, zeros,
)

# a 0.4 mm nozzle bridges gaps of roughly this size, so surfaces this close
# fuse in the print
FUSE_MM = 0.4
# a body holding less than this share of the total volume is "small"
SMALL_BODY_FRACTION = 0.01
# thinnest feature a common 0.4 mm nozzle can hold up
THIN_FEATURE_MM = 1.0
# bigger than the build volume of all but the largest desktop printers
LARGE_PLATE_MM = 300.0
# below this the whole model is about as wide as a few extrusions
TINY_MODEL_MM = 5.0
# above this many shells the fusion analysis is skipped
MAX_SHELLS = 200000


class PrintReport:
    """What the geometry is, in printing terms rather than mesh terms."""

    def __init__(self):
        self.triangle_count = 0
        self.size_mm = (0.0, 0.0, 0.0)
        self.shell_count = 0           # topological surfaces
        self.cavity_count = 0          # inside-out shells: interior voids
        self.body_count = 0            # what will actually print
        self.body_fractions = []       # volume share of each body, descending
        self.loose_count = 0           # bodies that touch nothing else
        self.loose_fraction = 0.0
        self.open_edges = 0
        self.nonmanifold_edges = 0
        self.open_shells = 0           # surfaces that are not closed
        self.thinnest_body_mm = None
        self.fuse_mm = FUSE_MM
        self.analysed = True           # False if the scene was too large
        self.enclosed_shells = 0       # surfaces sealed inside another
        self.enclosed_triangles = 0
        self.enclosed_partial = False  # True if only some pairs were tested

    @property
    def watertight(self):
        return self.open_edges == 0 and self.nonmanifold_edges == 0

    # ------------------------------------------------------------- reporting

    def notes(self):
        """Statements of fact about the scene. Not problems."""
        out = []
        if not self.analysed:
            return out

        solid_shells = self.shell_count - self.cavity_count
        if self.body_count == 1 and solid_shells > 1:
            out.append(
                "One connected body, built from %d separate surfaces that "
                "touch or overlap. ChimeraX draws ribbons, atoms and bonds as "
                "separate pieces; a slicer fuses anything closer than about "
                "%.1f mm, so this prints as one object."
                % (solid_shells, self.fuse_mm))
        elif self.body_count == 1 and self.cavity_count:
            out.append("One connected body; it will print as one object.")
        elif self.body_count > 1 and self.loose_count == 0:
            out.append(
                "%d connected bodies, none of them stray: each is a solid "
                "group of touching surfaces." % self.body_count)

        if self.cavity_count:
            out.append(
                "%d interior cavit%s (surfaces wound inside-out, such as voids "
                "in a density map). Slicers leave these hollow; they cost no "
                "filament."
                % (self.cavity_count, "y" if self.cavity_count == 1 else "ies"))

        if self.open_shells:
            out.append(
                "%d of %d surfaces are not closed. Bond cylinders have no end "
                "caps and clipped surfaces are cut open, which is normal in "
                "ChimeraX; slicers close them when slicing."
                % (self.open_shells, self.shell_count))
        return out

    def warnings(self):
        """Things that will genuinely go wrong, worst first."""
        out = []
        longest = max(self.size_mm) if self.size_mm else 0.0
        if longest > LARGE_PLATE_MM:
            out.append(
                "Model is %.0f mm across, bigger than most build plates (a "
                "Prusa XL is 360 mm). Scale it down with 'size N', or split it "
                "in the slicer." % longest)
        elif 0.0 < longest < TINY_MODEL_MM:
            out.append(
                "Model is only %.1f mm across - about the width of a few "
                "extrusions. Almost nothing will survive printing at this "
                "size; scale it up with 'size N'." % longest)

        if self.enclosed_shells:
            share = (100.0 * self.enclosed_triangles / self.triangle_count
                     if self.triangle_count else 0.0)
            # 99.7% must not be rounded to "100%": the container is not inside
            share_text = "%.1f%%" % share if share > 95.0 else "%.0f%%" % share
            out.append(
                "%d surface%s (%s of the triangles) lie completely inside "
                "another surface, so none of it can be seen in the print - "
                "atoms still shown inside a density map, or a cartoon left on "
                "under a molecular surface. It still costs filament and, if "
                "coloured differently, extra tool changes. Hide it before "
                "exporting unless you meant it to be there.%s"
                % (self.enclosed_shells,
                   "" if self.enclosed_shells == 1 else "s",
                   share_text,
                   " Only the largest surfaces were checked, so there may be "
                   "more." if self.enclosed_partial else ""))

        if self.loose_count:
            out.append(
                "%d piece%s float free of the main body (%.1f%% of the volume "
                "between them) - typically waters, ions or ligands. %s print "
                "as separate objects, and small ones may not survive removal "
                "from the plate."
                % (self.loose_count, "" if self.loose_count == 1 else "s",
                   100.0 * self.loose_fraction,
                   "It will" if self.loose_count == 1 else "They will"))

        if (self.thinnest_body_mm is not None
                and self.thinnest_body_mm < THIN_FEATURE_MM):
            out.append(
                "Thinnest separate piece measures %.2f mm across, below the "
                "~%.1f mm a 0.4 mm nozzle can hold."
                % (self.thinnest_body_mm, THIN_FEATURE_MM))
        return out

    def advice(self):
        if self.loose_count or (self.thinnest_body_mm is not None
                                and self.thinnest_body_mm < THIN_FEATURE_MM):
            return ("The NIH 3D print presets bundle adds struts between "
                    "disjoint pieces, thickens ribbons and removes solvent: "
                    "https://cxtoolshed.rbvi.ucsf.edu/apps/chimeraxnihpresets")
        return None


# ------------------------------------------------------------------ analysis

def analyze(geometry, fuse_mm=FUSE_MM):
    """Measure the millimetre-scaled geometry."""
    report = PrintReport()
    v, t = geometry.vertices, geometry.triangles
    report.triangle_count = len(t)
    report.fuse_mm = fuse_mm
    if len(t) == 0:
        return report

    low, high = geometry.bounds()
    report.size_mm = tuple(float(x) for x in (high - low))

    _check_edges(t, report)

    labels = _triangle_components(t)
    if labels is None:
        report.analysed = False
        return report
    n_shells = int(labels.max()) + 1
    report.shell_count = n_shells
    if n_shells > MAX_SHELLS:
        report.analysed = False
        return report

    report.open_shells = _count_open_shells(t, labels, n_shells)

    volumes = _shell_volumes(v, t, labels, n_shells)      # signed
    cavity = volumes < 0
    report.cavity_count = int(cavity.sum())

    bodies = _fuse_shells(v, t, labels, n_shells, fuse_mm)
    _describe_bodies(v, t, labels, bodies, volumes, cavity, report)
    _find_enclosed(v, t, labels, volumes, cavity, report)
    return report


# containment is only tested against the few biggest surfaces, which is where
# the case that matters lives: something hidden inside a surface or a map
MAX_CONTAINERS = 4
ENCLOSURE_SAMPLES = 8
# a containment test costs a handful of ray casts against one container mesh
# and stops at the first point that is outside, so this can be generous
MAX_ENCLOSURE_TESTS = 20000


def _find_enclosed(vertices, triangles, labels, volumes, cavity, report):
    """Find surfaces sealed inside another surface.

    Exporting what is displayed is right, but ChimeraX will happily leave an
    atomic model inside a density map or a cartoon inside a molecular surface,
    where it cannot be seen and still costs filament and tool changes.
    """
    n_shells = len(volumes)
    if n_shells < 2:
        return

    order = argsort(-np_abs(volumes))
    containers = [int(s) for s in order[:MAX_CONTAINERS] if not cavity[s]]
    if not containers:
        return

    lows, highs, tris = {}, {}, {}
    for s in range(n_shells):
        t = triangles[labels == s]
        if len(t) == 0:
            continue
        pts = vertices[unique(t)]
        lows[s], highs[s] = pts.min(axis=0), pts.max(axis=0)
        tris[s] = t

    counts = bincount(labels, minlength=n_shells)
    enclosed = 0
    enclosed_triangles = 0
    tested = 0
    for s in range(n_shells):
        if s in containers or s not in tris or cavity[s]:
            continue
        for big in containers:
            if big not in tris:
                continue
            if not ((lows[s] >= lows[big]).all() and (highs[s] <= highs[big]).all()):
                continue
            tested += 1
            if tested > MAX_ENCLOSURE_TESTS:
                report.enclosed_partial = True
                break
            if _all_points_inside(vertices, tris[s], tris[big]):
                enclosed += 1
                enclosed_triangles += int(counts[s])
            break
        if tested > MAX_ENCLOSURE_TESTS:
            break

    report.enclosed_shells = enclosed
    report.enclosed_triangles = enclosed_triangles


def _all_points_inside(vertices, tris_inner, tris_outer):
    """True only if every sampled point of the inner surface is inside."""
    from numpy import maximum as npmax, minimum as npmin
    pts = vertices[unique(tris_inner)]
    step = max(1, len(pts) // ENCLOSURE_SAMPLES)
    sample = pts[::step][:ENCLOSURE_SAMPLES]
    a = vertices[tris_outer[:, 0]]
    b = vertices[tris_outer[:, 1]]
    c = vertices[tris_outer[:, 2]]
    lo = npmin(npmin(a, b), c)
    hi = npmax(npmax(a, b), c)
    for p in sample:
        if not _point_inside(p, a, b, c, lo, hi):
            return False
    return True


def _describe_bodies(vertices, triangles, labels, bodies, volumes, cavity,
                     report):
    solid = ~cavity
    if not solid.any():
        return

    n_bodies = int(bodies.max()) + 1
    body_volume = bincount(bodies[solid], weights=volumes[solid],
                           minlength=n_bodies)
    present = body_volume > 0
    body_volume = body_volume[present]
    if len(body_volume) == 0:
        return

    total = float(body_volume.sum()) or 1.0
    fractions = sort(body_volume / total)[::-1]
    report.body_count = len(body_volume)
    report.body_fractions = [float(f) for f in fractions]

    if report.body_count > 1:
        # every body other than the largest is, by definition, not touching it
        report.loose_count = int(len(fractions) - 1)
        report.loose_fraction = float(fractions[1:].sum())
        report.thinnest_body_mm = _thinnest_body(
            vertices, triangles, labels, bodies, solid)
    return


def _thinnest_body(vertices, triangles, labels, bodies, solid):
    """Smallest bounding-box dimension over the separate bodies."""
    n_bodies = int(bodies.max()) + 1
    body_of_triangle = bodies[labels]
    thinnest = None
    for b in range(n_bodies):
        tris = triangles[body_of_triangle == b]
        if len(tris) == 0:
            continue
        pts = vertices[unique(tris)]
        extent = float((pts.max(axis=0) - pts.min(axis=0)).min())
        thinnest = extent if thinnest is None else min(thinnest, extent)
    return thinnest


# ------------------------------------------------------------- mesh topology

def _check_edges(triangles, report):
    edges = _edge_array(triangles)
    _, counts = unique(edges, axis=0, return_counts=True)
    report.open_edges = int((counts == 1).sum())
    report.nonmanifold_edges = int((counts > 2).sum())


def _edge_array(triangles):
    edges = empty((3 * len(triangles), 2), dtype=triangles.dtype)
    edges[0::3] = triangles[:, [0, 1]]
    edges[1::3] = triangles[:, [1, 2]]
    edges[2::3] = triangles[:, [2, 0]]
    return sort(edges, axis=1)


def _triangle_components(triangles):
    """Label every triangle with its edge-connected surface."""
    try:
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
    except ImportError:
        return None

    nt = len(triangles)
    edges = _edge_array(triangles)
    _, edge_ids = unique(edges, axis=0, return_inverse=True)
    edge_ids = edge_ids.ravel()

    tri_of_edge = repeat(arange(nt), 3)
    order = edge_ids.argsort(kind='stable')
    e, tri = edge_ids[order], tri_of_edge[order]
    shared = e[1:] == e[:-1]
    graph = coo_matrix((ones(int(shared.sum()), dtype=int8),
                        (tri[:-1][shared], tri[1:][shared])), shape=(nt, nt))
    _, labels = connected_components(graph, directed=False)
    return labels


def _count_open_shells(triangles, labels, n_shells):
    """How many surfaces have a boundary rather than being closed."""
    edges = _edge_array(triangles)
    shell_of_edge = repeat(labels, 3)
    key = edges[:, 0].astype(int64) * (edges.max() + 1) + edges[:, 1]
    order = lexsort((shell_of_edge, key))
    k = key[order]
    counts = bincount(unique(k, return_inverse=True)[1])
    boundary = counts == 1
    if not boundary.any():
        return 0
    _, inverse = unique(k, return_inverse=True)
    open_shells = unique(shell_of_edge[order][boundary[inverse]])
    return int(len(open_shells))


def _shell_volumes(vertices, triangles, labels, n_shells):
    """Signed volume of each surface. Negative means wound inside-out, which
    for a closed surface means it bounds a void rather than a solid."""
    a = vertices[triangles[:, 0]]
    b = vertices[triangles[:, 1]]
    c = vertices[triangles[:, 2]]
    contrib = einsum('ij,ij->i', a, cross(b, c)) / 6.0
    return bincount(labels, weights=contrib, minlength=n_shells)


# ---------------------------------------------------------- printed bodies

# never generate more surface samples than this, however coarse the mesh
SAMPLE_BUDGET = 3000000


def _surface_samples(vertices, triangles, labels, tau, budget=SAMPLE_BUDGET):
    """Points covering the surface no more coarsely than `tau`.

    Testing proximity on vertices alone fails on coarse meshes: two boxes can
    interpenetrate while their corners stay far apart. Rather than loosening
    the distance threshold - which would wrongly fuse things that really are
    apart - large triangles are sampled across their face.
    """
    from numpy import ceil, clip, stack, vstack

    vertex_shell = empty(len(vertices), dtype=int64)
    vertex_shell[triangles.ravel()] = repeat(labels, 3)
    point_sets = [vertices]
    tag_sets = [vertex_shell]

    a = vertices[triangles[:, 0]]
    b = vertices[triangles[:, 1]]
    c = vertices[triangles[:, 2]]
    longest = sqrt(maximum(maximum(((b - a) ** 2).sum(axis=1),
                                   ((c - b) ** 2).sum(axis=1)),
                           ((a - c) ** 2).sum(axis=1)))
    steps = clip(ceil(longest / max(tau, 1e-9)), 1, 16).astype(int64)

    # keep the total bounded: halve the sampling until it fits
    while True:
        total = int(((steps + 1) * (steps + 2) // 2).sum())
        if total <= budget or (steps <= 1).all():
            break
        steps = maximum(steps // 2, 1)

    for k in unique(steps):
        which = steps == k
        if not which.any():
            continue
        bary = _barycentric_grid(int(k))
        pa, pb, pc = a[which], b[which], c[which]
        # (triangles, samples, 3)
        pts = (pa[:, None, :] * bary[None, :, 0:1]
               + pb[:, None, :] * bary[None, :, 1:2]
               + pc[:, None, :] * bary[None, :, 2:3])
        point_sets.append(pts.reshape(-1, 3))
        tag_sets.append(repeat(labels[which], bary.shape[0]))

    return vstack(point_sets), concatenate(tag_sets)


def _barycentric_grid(k):
    """Barycentric coordinates of a k x k lattice over a triangle.

    For k = 1 the lattice is just the corners, which are already sampled as
    vertices, so the centroid is used instead - that is the common case on a
    molecular mesh and it keeps the point count down.
    """
    from numpy import array
    if k <= 1:
        return array([[1 / 3.0, 1 / 3.0, 1 / 3.0]], dtype=float)
    coords = []
    for i in range(k + 1):
        for j in range(k + 1 - i):
            coords.append(((k - i - j) / k, i / k, j / k))
    return array(coords, dtype=float)

def _fuse_shells(vertices, triangles, labels, n_shells, fuse_mm):
    """Group surfaces into the bodies a printer will produce.

    Surfaces fuse when they come within `fuse_mm`, which is what actually
    happens in a print, rather than when they share vertices, which is a
    modelling detail ChimeraX has no reason to arrange.

    Done on a voxel grid instead of pairwise tests: sorting points by
    (voxel, surface) puts everything sharing a voxel together, so linking
    consecutive differing surfaces connects the whole group. Two grids offset
    by half a voxel catch surfaces that straddle a boundary.
    """
    if n_shells <= 1:
        return zeros(max(n_shells, 1), dtype=int64)
    try:
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
    except ImportError:
        return arange(n_shells)

    tau = fuse_mm
    points, tags = _surface_samples(vertices, triangles, labels, tau)

    rows, cols = [], []
    for offset in (0.0, 0.5):
        cell = floor(points / tau + offset).astype(int64)
        key = (cell[:, 0] * 1000003 + cell[:, 1]) * 1000003 + cell[:, 2]
        order = lexsort((tags, key))
        k, s = key[order], tags[order]
        link = (k[1:] == k[:-1]) & (s[1:] != s[:-1])
        rows.append(s[:-1][link])
        cols.append(s[1:][link])

    r, c = concatenate(rows), concatenate(cols)
    graph = coo_matrix((ones(len(r), dtype=int8), (r, c)),
                       shape=(n_shells, n_shells))
    _, bodies = connected_components(graph, directed=False)
    return _fuse_interpenetrating(vertices, triangles, labels, bodies,
                                  n_shells)


# a shell pair is only tested for interpenetration if proximity left them
# apart; this caps the work when that still leaves many candidates
MAX_OVERLAP_TESTS = 400
OVERLAP_SAMPLES = 6


def _fuse_interpenetrating(vertices, triangles, labels, bodies, n_shells):
    """Also fuse shells that pass through each other.

    Proximity alone misses interpenetration on coarse meshes: two boxes can
    overlap by half their width while their vertices stay millimetres apart.
    Only pairs that proximity left in different bodies are tested, so on a
    normal molecular scene - where everything has already fused - this costs
    nothing.
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    if len(unique(bodies)) < 2:
        return bodies

    lows, highs, meshes = {}, {}, {}
    for s in range(n_shells):
        tris = triangles[labels == s]
        if len(tris) == 0:
            continue
        pts = vertices[unique(tris)]
        lows[s], highs[s] = pts.min(axis=0), pts.max(axis=0)
        meshes[s] = tris

    candidates = []
    shells_present = sorted(meshes)
    for i, a in enumerate(shells_present):
        for b in shells_present[i + 1:]:
            if bodies[a] == bodies[b]:
                continue
            if (lows[a] <= highs[b]).all() and (lows[b] <= highs[a]).all():
                candidates.append((a, b))
    if not candidates:
        return bodies
    if len(candidates) > MAX_OVERLAP_TESTS:
        candidates = candidates[:MAX_OVERLAP_TESTS]

    rows, cols = [], []
    for a, b in candidates:
        if _shells_interpenetrate(vertices, meshes[a], meshes[b]):
            rows.append(a)
            cols.append(b)
    if not rows:
        return bodies

    graph = coo_matrix((ones(len(rows), dtype=int8), (rows, cols)),
                       shape=(n_shells, n_shells))
    # keep what proximity already joined
    pr, pc = [], []
    for s in range(1, n_shells):
        if bodies[s] == bodies[s - 1]:
            pr.append(s - 1)
            pc.append(s)
    for body in unique(bodies):
        members = [s for s in range(n_shells) if bodies[s] == body]
        for x, y in zip(members, members[1:]):
            pr.append(x)
            pc.append(y)
    graph = graph + coo_matrix(
        (ones(len(pr), dtype=int8), (pr, pc)), shape=(n_shells, n_shells))
    _, merged = connected_components(graph, directed=False)
    return merged


def _shells_interpenetrate(vertices, tris_a, tris_b):
    """True if a sampled point of either shell lies inside the other."""
    return (_any_point_inside(vertices, tris_a, tris_b)
            or _any_point_inside(vertices, tris_b, tris_a))


def _any_point_inside(vertices, tris_inner, tris_outer):
    pts = vertices[unique(tris_inner)]
    step = max(1, len(pts) // OVERLAP_SAMPLES)
    sample = pts[::step][:OVERLAP_SAMPLES]
    a = vertices[tris_outer[:, 0]]
    b = vertices[tris_outer[:, 1]]
    c = vertices[tris_outer[:, 2]]
    from numpy import maximum as npmax, minimum as npmin
    lo = npmin(npmin(a, b), c)
    hi = npmax(npmax(a, b), c)
    for p in sample:
        if _point_inside(p, a, b, c, lo, hi):
            return True
    return False


def _point_inside(p, a, b, c, lo, hi):
    """Parity of a ray cast straight up from p through the triangles."""
    from numpy import abs as nabs, where
    hit_box = ((lo[:, 0] <= p[0]) & (hi[:, 0] >= p[0]) &
               (lo[:, 1] <= p[1]) & (hi[:, 1] >= p[1]) & (hi[:, 2] >= p[2]))
    if not hit_box.any():
        return False
    A, B, C = a[hit_box], b[hit_box], c[hit_box]
    v0 = C[:, :2] - A[:, :2]
    v1 = B[:, :2] - A[:, :2]
    v2 = p[:2] - A[:, :2]
    d00 = (v0 * v0).sum(axis=1)
    d01 = (v0 * v1).sum(axis=1)
    d11 = (v1 * v1).sum(axis=1)
    d20 = (v2 * v0).sum(axis=1)
    d21 = (v2 * v1).sum(axis=1)
    den = d00 * d11 - d01 * d01
    usable = nabs(den) > 1e-12
    if not usable.any():
        return False
    den = where(usable, den, 1.0)
    u = (d11 * d20 - d01 * d21) / den
    v = (d00 * d21 - d01 * d20) / den
    hit = usable & (u >= 0.0) & (v >= 0.0) & (u + v <= 1.0)
    if not hit.any():
        return False
    z = (A[hit, 2] + u[hit] * (C[hit, 2] - A[hit, 2])
         + v[hit] * (B[hit, 2] - A[hit, 2]))
    return bool((z > p[2]).sum() % 2 == 1)


# -------------------------------------------------------------------- output

def log_report(session, report, quiet=False):
    if quiet:
        return
    from . import log

    for note in report.notes():
        session.logger.info(note)
    warnings = report.warnings()
    for w in warnings:
        log.warn(session, w)
    advice = report.advice()
    if advice:
        session.logger.info(advice, is_html=False)
    if warnings:
        log.help_hint(session)
