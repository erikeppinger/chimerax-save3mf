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
    abs as np_abs, arange, cross, einsum, repeat, sort, unique, zeros,
)

# a fragment smaller than this share of total volume is treated as debris
DEBRIS_VOLUME_FRACTION = 0.01
# if the biggest piece holds at least this much, the rest really are fragments;
# below it the model is not one body at all
COHERENT_VOLUME_FRACTION = 0.8
# thinnest feature a common 0.4 mm nozzle can hold up
THIN_FEATURE_MM = 1.0


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

    @property
    def watertight(self):
        return self.open_edges == 0 and self.nonmanifold_edges == 0

    def warnings(self):
        """Human-readable problems, worst first.  Empty means nothing to say."""
        out = []
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
    extents = _shell_extents(vertices, triangles, labels, n_shells)

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


def _shell_extents(vertices, triangles, labels, n_shells):
    """Smallest bounding-box dimension of each piece."""
    from numpy import empty, full, inf, maximum, minimum
    vertex_labels = empty(len(vertices), dtype=labels.dtype)
    vertex_labels[triangles.ravel()] = repeat(labels, 3)
    lows = full((n_shells, 3), inf)
    highs = full((n_shells, 3), -inf)
    minimum.at(lows, vertex_labels, vertices)
    maximum.at(highs, vertex_labels, vertices)
    return (highs - lows).min(axis=1)


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
