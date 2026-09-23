# vim: set expandtab shiftwidth=4 softtabstop=4:
"""Printability report for the geometry about to be written.

This does not repair anything.  Preparing a structure for printing - adding
struts between disjoint pieces, thickening ribbons, deleting solvent - is what
the NIH 3D print presets bundle is for:

    https://cxtoolshed.rbvi.ucsf.edu/apps/chimeraxnihpresets

The exporter's job is to measure what it is given and say plainly what a slicer
will make of it, before the file is written.
"""

from numpy import (
    abs as np_abs, arange, cross, einsum, repeat, sort, unique, where, zeros,
)

# a fragment smaller than this share of total volume is treated as debris
DEBRIS_VOLUME_FRACTION = 0.01
# if the biggest piece holds at least this much, the rest really are fragments;
# below it the model is not one body at all
COHERENT_VOLUME_FRACTION = 0.8
# thinnest feature a common 0.4 mm nozzle can hold up
THIN_FEATURE_MM = 1.0
# bigger than the build volume of all but the largest desktop printers
LARGE_PLATE_MM = 300.0
# below this the whole model is about as wide as a few extrusions
TINY_MODEL_MM = 5.0


class PrintReport:

    def __init__(self):
        self.shell_count = 0
        self.debris_count = 0
        self.debris_volume_fraction = 0.0
        self.largest_volume_fraction = 1.0
        self.open_edges = 0
        self.nonmanifold_edges = 0
        self.thinnest_shell_mm = None
        self.triangle_count = 0
        self.size_mm = (0.0, 0.0, 0.0)
        self.enclosed_count = 0
        self.enclosed_triangles = 0
        self.enclosed_checked = True     # False when skipped entirely
        self.enclosed_partial = False    # True when only the largest were tested

    @property
    def watertight(self):
        return self.open_edges == 0 and self.nonmanifold_edges == 0

    def warnings(self):
        """Human-readable problems, worst first.  Empty means nothing to say."""
        out = []
        longest = max(self.size_mm) if self.size_mm else 0.0
        if longest > LARGE_PLATE_MM:
            out.append(
                "Model is %.0f mm across, bigger than most build plates (a "
                "Prusa XL is 360 mm). Scale it down with 'size N', or split "
                "it up in the slicer." % longest)
        elif 0.0 < longest < TINY_MODEL_MM:
            out.append(
                "Model is only %.1f mm across - about the width of a few "
                "extrusions. Almost nothing will survive printing at this "
                "size; scale it up with 'size N'." % longest)
        if not self.watertight:
            bits = []
            if self.open_edges:
                bits.append("%d open edges" % self.open_edges)
            if self.nonmanifold_edges:
                bits.append("%d edges shared by more than two triangles"
                            % self.nonmanifold_edges)
            out.append(
                "Mesh is not watertight (%s). Slicers will try to repair it, "
                "with unpredictable results. Overlapping shells from ball-and-"
                "stick or sphere styles are the usual cause." % ", ".join(bits))
        if self.shell_count > 1 and self.largest_volume_fraction < COHERENT_VOLUME_FRACTION:
            out.append(
                "This is not one connected body: %d pieces that do not touch, "
                "the largest holding only %.1f%% of the volume. It will not "
                "print as a single object."
                % (self.shell_count, 100.0 * self.largest_volume_fraction))
        elif self.debris_count:
            out.append(
                "%d of %d pieces are loose fragments (%.1f%% of total volume "
                "between them) - typically waters, ions or ligands. They will "
                "print as separate bits."
                % (self.debris_count, self.shell_count,
                   100.0 * self.debris_volume_fraction))
        elif self.shell_count > 1:
            out.append(
                "Model is in %d separate pieces that do not touch. They will "
                "print separately unless connected." % self.shell_count)
        if self.enclosed_count:
            share = (100.0 * self.enclosed_triangles / self.triangle_count
                     if self.triangle_count else 0.0)
            out.append(
                "%d piece%s (%d triangles, %.0f%% of the model) %s sealed "
                "inside another piece and will never be visible, but still "
                "cost print time and filament. A cartoon left on underneath a "
                "surface is the usual cause - hide it before exporting.%s"
                % (self.enclosed_count, "" if self.enclosed_count == 1 else "s",
                   self.enclosed_triangles, share,
                   "is" if self.enclosed_count == 1 else "are",
                   " Only the largest pieces were checked, so there may be more."
                   if self.enclosed_partial else ""))
        if self.thinnest_shell_mm is not None and self.thinnest_shell_mm < THIN_FEATURE_MM:
            out.append(
                "Thinnest piece measures %.2f mm across, below the ~%.1f mm a "
                "0.4 mm nozzle can hold. Scale up or thicken it."
                % (self.thinnest_shell_mm, THIN_FEATURE_MM))
        return out

    def advice(self):
        if self.watertight and self.shell_count <= 1:
            return None
        return ("The NIH 3D print presets bundle adds struts between disjoint "
                "pieces, thickens ribbons and removes solvent: "
                "https://cxtoolshed.rbvi.ucsf.edu/apps/chimeraxnihpresets")


def analyze(geometry):
    """Measure the welded, millimetre-scaled geometry."""
    report = PrintReport()
    v, t = geometry.vertices, geometry.triangles
    report.triangle_count = len(t)
    if len(t) == 0:
        return report

    low, high = geometry.bounds()
    report.size_mm = tuple(float(x) for x in (high - low))

    _check_edges(t, report)
    _check_shells(v, t, report)
    return report


def _check_edges(triangles, report):
    """Count edges that are not shared by exactly two triangles."""
    edges = zeros((3 * len(triangles), 2), triangles.dtype)
    edges[0::3] = triangles[:, [0, 1]]
    edges[1::3] = triangles[:, [1, 2]]
    edges[2::3] = triangles[:, [2, 0]]
    edges = sort(edges, axis=1)            # undirected
    _, counts = unique(edges, axis=0, return_counts=True)
    report.open_edges = int((counts == 1).sum())
    report.nonmanifold_edges = int((counts > 2).sum())


def _check_shells(vertices, triangles, report):
    """Split into connected pieces and size each one.

    Pieces are connected through shared *edges*, not shared vertices: two
    shells meeting at a single point are separate as far as a printer is
    concerned, and this is also how slicers count parts.
    """
    labels = _triangle_components(triangles)
    if labels is None:
        return
    n_shells = int(labels.max()) + 1
    report.shell_count = n_shells
    if n_shells <= 1:
        report.thinnest_shell_mm = float(min(report.size_mm))
        return

    volumes = _shell_volumes(vertices, triangles, labels, n_shells)
    lows, highs = _shell_boxes(vertices, triangles, labels, n_shells)
    extents = (highs - lows).min(axis=1)
    _check_enclosed(vertices, triangles, labels, lows, highs, volumes, report)

    total = volumes.sum()
    if total <= 0:
        return
    fractions = volumes / total
    report.largest_volume_fraction = float(fractions.max())
    debris = fractions < DEBRIS_VOLUME_FRACTION
    report.debris_count = int(debris.sum())
    report.debris_volume_fraction = float(fractions[debris].sum())

    # thinness is only interesting for pieces that matter structurally
    keep = ~debris if debris.any() and not debris.all() else slice(None)
    structural = extents[keep]
    if len(structural):
        report.thinnest_shell_mm = float(structural.min())


def _triangle_components(triangles):
    """Label every triangle with its edge-connected piece."""
    try:
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
    except ImportError:
        return None

    nt = len(triangles)
    edges = zeros((3 * nt, 2), triangles.dtype)
    edges[0::3] = triangles[:, [0, 1]]
    edges[1::3] = triangles[:, [1, 2]]
    edges[2::3] = triangles[:, [2, 0]]
    edges = sort(edges, axis=1)
    _, edge_ids = unique(edges, axis=0, return_inverse=True)
    edge_ids = edge_ids.ravel()

    tri_of_edge = repeat(arange(nt), 3)
    order = edge_ids.argsort(kind='stable')
    e_sorted, t_sorted = edge_ids[order], tri_of_edge[order]
    shared = e_sorted[1:] == e_sorted[:-1]
    rows, cols = t_sorted[:-1][shared], t_sorted[1:][shared]

    data = zeros(len(rows), dtype='int8') + 1
    graph = coo_matrix((data, (rows, cols)), shape=(nt, nt))
    _, labels = connected_components(graph, directed=False)
    return labels


def _shell_volumes(vertices, triangles, labels, n_shells):
    """Enclosed volume of each piece, via the divergence theorem."""
    from numpy import bincount
    a = vertices[triangles[:, 0]]
    b = vertices[triangles[:, 1]]
    c = vertices[triangles[:, 2]]
    contrib = einsum('ij,ij->i', a, cross(b, c)) / 6.0
    return np_abs(bincount(labels, weights=contrib, minlength=n_shells))


def _shell_boxes(vertices, triangles, labels, n_shells):
    """Bounding box of each piece."""
    from numpy import empty, full, inf, maximum, minimum
    vertex_labels = empty(len(vertices), dtype=labels.dtype)
    vertex_labels[triangles.ravel()] = repeat(labels, 3)
    lows = full((n_shells, 3), inf)
    highs = full((n_shells, 3), -inf)
    minimum.at(lows, vertex_labels, vertices)
    maximum.at(highs, vertex_labels, vertices)
    return lows, highs


# ------------------------------------------------- enclosed (invisible) parts

# testing every pair is quadratic; stop well before that hurts
MAX_ENCLOSURE_TESTS = 64
# above this many pieces the pairwise box comparison itself gets expensive
MAX_SHELLS_FOR_ENCLOSURE = 2000
# how many points of a piece must be inside the other for it to count
ENCLOSURE_SAMPLES = 8


def _check_enclosed(vertices, triangles, labels, lows, highs, volumes, report):
    """Find pieces sealed inside another piece, which print but never show.

    A cartoon left displayed under a molecular surface is the common case: it
    is invisible in the print yet costs filament and time.
    """
    from numpy import bincount

    n = len(volumes)
    if n < 2:
        return
    if n > MAX_SHELLS_FOR_ENCLOSURE:
        report.enclosed_checked = False
        return

    # only pairs whose boxes nest can possibly be enclosed
    nested = (((lows[:, None, :] >= lows[None, :, :]).all(axis=2)) &
              ((highs[:, None, :] <= highs[None, :, :]).all(axis=2)) &
              (volumes[None, :] > volumes[:, None]))
    candidates = [(inner, int(nested[inner].argmax()))
                  for inner in range(n) if nested[inner].any()]

    if not candidates:
        return
    if len(candidates) > MAX_ENCLOSURE_TESTS:
        # biggest first: those are the ones worth telling the user about
        candidates.sort(key=lambda pair: -volumes[pair[0]])
        candidates = candidates[:MAX_ENCLOSURE_TESTS]
        report.enclosed_partial = True

    triangle_counts = bincount(labels, minlength=n)
    enclosed_triangles = 0
    enclosed_count = 0
    for inner, outer in candidates:
        if _shell_inside(vertices, triangles, labels, inner, outer):
            enclosed_count += 1
            enclosed_triangles += int(triangle_counts[inner])

    report.enclosed_count = enclosed_count
    report.enclosed_triangles = enclosed_triangles


def _shell_inside(vertices, triangles, labels, inner, outer):
    """True if every sampled point of the inner piece is inside the outer one."""
    from numpy import unique
    inner_tris = triangles[labels == inner]
    outer_tris = triangles[labels == outer]
    if len(inner_tris) == 0 or len(outer_tris) == 0:
        return False

    points = vertices[unique(inner_tris)]
    step = max(1, len(points) // ENCLOSURE_SAMPLES)
    points = points[::step][:ENCLOSURE_SAMPLES]

    a = vertices[outer_tris[:, 0]]
    b = vertices[outer_tris[:, 1]]
    c = vertices[outer_tris[:, 2]]
    box_low = __minimum3(a, b, c)
    box_high = __maximum3(a, b, c)

    for p in points:
        if not _point_inside(p, a, b, c, box_low, box_high):
            return False
    return True


def __minimum3(a, b, c):
    from numpy import minimum
    return minimum(minimum(a, b), c)


def __maximum3(a, b, c):
    from numpy import maximum
    return maximum(maximum(a, b), c)


def _point_inside(p, a, b, c, box_low, box_high):
    """Parity of a ray cast straight up from p through the triangles."""
    from numpy import abs as nabs
    candidates = ((box_low[:, 0] <= p[0]) & (box_high[:, 0] >= p[0]) &
                  (box_low[:, 1] <= p[1]) & (box_high[:, 1] >= p[1]) &
                  (box_high[:, 2] >= p[2]))
    if not candidates.any():
        return False
    A, B, C = a[candidates], b[candidates], c[candidates]

    v0 = C[:, :2] - A[:, :2]
    v1 = B[:, :2] - A[:, :2]
    v2 = p[:2] - A[:, :2]
    d00 = (v0 * v0).sum(axis=1)
    d01 = (v0 * v1).sum(axis=1)
    d11 = (v1 * v1).sum(axis=1)
    d20 = (v2 * v0).sum(axis=1)
    d21 = (v2 * v1).sum(axis=1)
    denom = d00 * d11 - d01 * d01
    usable = nabs(denom) > 1e-12
    if not usable.any():
        return False
    denom = where(usable, denom, 1.0)
    u = (d11 * d20 - d01 * d21) / denom
    v = (d00 * d21 - d01 * d20) / denom
    hit = usable & (u >= 0.0) & (v >= 0.0) & (u + v <= 1.0)
    if not hit.any():
        return False

    z = (A[hit, 2] + u[hit] * (C[hit, 2] - A[hit, 2])
         + v[hit] * (B[hit, 2] - A[hit, 2]))
    return bool((z > p[2]).sum() % 2 == 1)


def log_report(session, report, quiet=False):
    """Put the findings in the log; warnings use the log's warning channel."""
    logger = session.logger
    if quiet:
        return
    warnings = report.warnings()
    for w in warnings:
        logger.warning(w)
    advice = report.advice()
    if advice and warnings:
        logger.info(advice, is_html=False)
