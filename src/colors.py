# vim: set expandtab shiftwidth=4 softtabstop=4:
"""Turn per-triangle colours into a small set of printable regions.

Most ChimeraX colouring is discrete - by chain, by hetero, by secondary
structure - so the distinct colours usually number a handful and nothing is
merged.  Continuous schemes (rainbow, by B-factor) produce thousands, which
would become thousands of slicer parts, so those are clustered down to a
requested maximum.

Clustering happens in CIELAB rather than RGB: RGB distance does not match what
the eye calls "close", and would happily merge a red with a brown while
splitting two near-identical blues.  Clusters are weighted by triangle area so
a large surface is not merged away in favour of a few tiny ligand triangles.

The colour representing a region is the largest real colour in it, never an
averaged centroid, so every part in the slicer is a colour that actually
appears in the ChimeraX scene.
"""

from numpy import (
    argsort, array, bincount, cbrt, cross, dot, empty, float64, sqrt, unique,
    where, zeros,
)

MAX_REGIONS_BEFORE_WARNING = 32


class ColorRegions:
    """Triangles grouped by colour.

    labels   (nt,) int, region index per triangle
    colors   (nr, 3) uint8, the colour of each region
    counts   (nr,) triangles per region
    areas    (nr,) mm^2 per region
    names    list of region names for the slicer's part list
    merged   True if clustering reduced the colour count
    distinct number of distinct colours before any merging
    delta_e  mean perceptual error introduced by merging (0.0 if none)
    """

    def __init__(self, labels, colors, counts, areas, names,
                 merged=False, distinct=0, delta_e=0.0):
        self.labels = labels
        self.colors = colors
        self.counts = counts
        self.areas = areas
        self.names = names
        self.merged = merged
        self.distinct = distinct
        self.delta_e = delta_e

    @property
    def count(self):
        return len(self.colors)

    def hex_colors(self, alpha=True):
        return [_hex(c, alpha) for c in self.colors]


def build_regions(geometry, max_colors=None):
    """Group the geometry's triangles into colour regions."""
    tri_colors = geometry.triangle_colors[:, :3]
    areas = triangle_areas(geometry)

    unique_colors, inverse = unique(tri_colors, axis=0, return_inverse=True)
    inverse = inverse.ravel()
    distinct = len(unique_colors)

    color_areas = bincount(inverse, weights=areas, minlength=distinct)

    delta_e = 0.0
    merged = False
    if max_colors is not None and 0 < max_colors < distinct:
        cluster_of_color, delta_e = _cluster_colors(
            unique_colors, color_areas, max_colors)
        merged = True
    else:
        cluster_of_color = _order_by_area(color_areas)

    labels = cluster_of_color[inverse]
    n = int(labels.max()) + 1

    region_colors = _representative_colors(unique_colors, color_areas,
                                           cluster_of_color, n)
    counts = bincount(labels, minlength=n)
    region_areas = bincount(labels, weights=areas, minlength=n)
    names = _region_names(geometry, labels, region_colors, n, areas)

    return ColorRegions(labels, region_colors, counts, region_areas, names,
                        merged=merged, distinct=distinct, delta_e=delta_e)


def preview_merges(geometry, candidates):
    """What merging to each candidate part count would cost.

    Returns (distinct colour count, [(k, mean delta E, representative
    colours), ...]) without touching the geometry, so the choice can be made
    before exporting anything.
    """
    tri_colors = geometry.triangle_colors[:, :3]
    areas = triangle_areas(geometry)
    unique_colors, inverse = unique(tri_colors, axis=0, return_inverse=True)
    distinct = len(unique_colors)
    color_areas = bincount(inverse.ravel(), weights=areas, minlength=distinct)

    results = []
    for k in candidates:
        if k >= distinct:
            continue
        cluster_of_color, delta_e = _cluster_colors(unique_colors, color_areas, k)
        reps = _representative_colors(unique_colors, color_areas,
                                      cluster_of_color, k)
        results.append((k, delta_e, reps, cluster_of_color))
    return distinct, results


def color_index(geometry):
    """Distinct colours in the scene and which one each triangle has."""
    tri_colors = geometry.triangle_colors[:, :3]
    unique_colors, inverse = unique(tri_colors, axis=0, return_inverse=True)
    return unique_colors, inverse.ravel()


def describe_delta_e(delta_e):
    """Plain words for a CIELAB distance."""
    if delta_e < 1.0:
        return "identical to the eye"
    if delta_e < 2.0:
        return "barely visible"
    if delta_e < 5.0:
        return "slight shift"
    if delta_e < 10.0:
        return "clearly different"
    return "strong shift"


def log_palette(session, names, hex_colors, counts=None, areas=None,
                limit=MAX_REGIONS_BEFORE_WARNING):
    """Colour swatches in the ChimeraX log, which renders HTML.

    Continuous colouring can produce thousands of regions, and a table with a
    row for each of them buries everything else in the log, so only the
    largest are listed.
    """
    total = float(areas.sum()) if areas is not None and len(areas) else 0.0
    shown = len(names) if limit is None else min(len(names), limit)
    rows = []
    for i, (name, hex_color) in enumerate(zip(names[:shown],
                                              hex_colors[:shown])):
        extra = ""
        if counts is not None:
            extra += '<td align="right">&nbsp;%d triangles</td>' % counts[i]
        if total > 0:
            extra += '<td align="right">&nbsp;%.1f%%</td>' % (100.0 * areas[i] / total)
        rows.append(
            '<tr><td style="background:%s;width:2em">&nbsp;</td>'
            '<td>&nbsp;part %d</td><td>&nbsp;%s</td>%s</tr>'
            % (hex_color, i + 1, _escape(name), extra))
    if shown < len(names):
        rows.append('<tr><td></td><td colspan="4">&nbsp;&hellip; and %d more'
                    '</td></tr>' % (len(names) - shown))
    session.logger.info('<table style="border-spacing:0">%s</table>'
                        % "".join(rows), is_html=True)


def swatch_strip(hex_colors, width="1.2em"):
    """A row of colour chips as an inline HTML table."""
    cells = "".join('<td style="background:%s;width:%s">&nbsp;</td>' % (c, width)
                    for c in hex_colors)
    return '<table style="border-spacing:0;display:inline-table"><tr>%s</tr></table>' % cells


def _escape(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
                     .replace(">", "&gt;").replace('"', "&quot;"))


def triangle_areas(geometry):
    """Area of each triangle in the geometry's own units."""
    v, t = geometry.vertices, geometry.triangles
    if len(t) == 0:
        return zeros(0)
    e1 = v[t[:, 1]] - v[t[:, 0]]
    e2 = v[t[:, 2]] - v[t[:, 0]]
    return sqrt((cross(e1, e2) ** 2).sum(axis=1)) / 2.0


def _order_by_area(color_areas):
    """Region order: biggest first, so part 1 is the dominant colour."""
    order = argsort(-color_areas)
    rank = empty(len(color_areas), dtype='int64')
    rank[order] = range(len(color_areas))
    return rank


def _representative_colors(unique_colors, color_areas, cluster_of_color, n):
    """Pick the largest real colour in each cluster."""
    best_area = zeros(n)
    best = zeros((n, 3), dtype=unique_colors.dtype)
    for i, cluster in enumerate(cluster_of_color):
        if color_areas[i] >= best_area[cluster]:
            best_area[cluster] = color_areas[i]
            best[cluster] = unique_colors[i]
    return best


def _region_names(geometry, labels, region_colors, n, areas=None):
    """Name each region after the drawing that contributes most of it, plus
    the colour - a slicer shows these in its part list, so they have to say
    which bit of the molecule this is.

    Dominance is by *area*, not triangle count.  Cartoon ribbons are made of
    many tiny triangles, so counting them would name a region after a ribbon
    hidden inside a surface that covers a hundred times the area.
    """
    sources = getattr(geometry, 'triangle_sources', None)
    source_names = getattr(geometry, 'source_names', None)
    color_names = _builtin_color_names()
    names = []
    for r in range(n):
        rgb = region_colors[r]
        color_label = color_names.get(tuple(int(x) for x in rgb),
                                      _hex(rgb, alpha=False))
        label = None
        if sources is not None and source_names:
            in_region = labels == r
            region_sources = sources[in_region]
            if len(region_sources):
                weights = None if areas is None else areas[in_region]
                dominant = bincount(region_sources, weights=weights,
                                    minlength=len(source_names)).argmax()
                label = _tidy(source_names[dominant])
        names.append("%s %s" % (label, color_label) if label else color_label)
    return names


def _tidy(name, limit=40):
    """Drawing names can be long; keep them readable in a slicer's part list."""
    name = str(name).strip()
    return name if len(name) <= limit else name[:limit - 1] + "\N{HORIZONTAL ELLIPSIS}"


def _builtin_color_names():
    """Map exact RGB to ChimeraX's own colour names, so a part reads
    'cornflowerblue' rather than '#6495ED'."""
    try:
        from chimerax.core.colors import BuiltinColors
    except ImportError:
        return {}
    mapping = {}
    for name, color in BuiltinColors.items():
        rgba8 = tuple(int(x) for x in color.uint8x4()[:3])
        # first name wins; ChimeraX has aliases for the same value
        mapping.setdefault(rgba8, name)
    return mapping


# ---------------------------------------------------------------- clustering

def _cluster_colors(colors, weights, k, iterations=25):
    """Weighted k-means in CIELAB.  Returns (cluster per colour, mean dE)."""
    lab = srgb_to_lab(colors)
    centers = _kmeans_plusplus(lab, weights, k)

    assignment = zeros(len(lab), dtype='int64')
    for _ in range(iterations):
        distances = _squared_distances(lab, centers)
        new_assignment = distances.argmin(axis=1)
        if (new_assignment == assignment).all():
            break
        assignment = new_assignment
        for c in range(k):
            members = assignment == c
            w = weights[members]
            if w.sum() > 0:
                centers[c] = (lab[members] * w[:, None]).sum(axis=0) / w.sum()

    distances = _squared_distances(lab, centers)
    errors = sqrt(distances[range(len(lab)), assignment])
    total = weights.sum()
    mean_error = float((errors * weights).sum() / total) if total > 0 else 0.0

    # renumber so region 0 is the largest by area
    area_per_cluster = bincount(assignment, weights=weights, minlength=k)
    return _order_by_area(area_per_cluster)[assignment], mean_error


def _kmeans_plusplus(points, weights, k):
    """Deterministic weighted k-means++ seeding: first the heaviest point,
    then repeatedly the point furthest from what is already chosen."""
    centers = empty((k, points.shape[1]), dtype=float64)
    centers[0] = points[weights.argmax()]
    closest = ((points - centers[0]) ** 2).sum(axis=1)
    for i in range(1, k):
        centers[i] = points[(closest * weights).argmax()]
        d = ((points - centers[i]) ** 2).sum(axis=1)
        closest = where(d < closest, d, closest)
    return centers


def _squared_distances(points, centers):
    d = empty((len(points), len(centers)))
    for i, c in enumerate(centers):
        d[:, i] = ((points - c) ** 2).sum(axis=1)
    return d


# ------------------------------------------------------------ colour spaces

_XYZ_FROM_LINEAR_RGB = [
    [0.4124564, 0.3575761, 0.1804375],
    [0.2126729, 0.7151522, 0.0721750],
    [0.0193339, 0.1191920, 0.9503041],
]
_D65_WHITE = [0.95047, 1.0, 1.08883]


def srgb_to_lab(rgb):
    """(n, 3) uint8 sRGB to (n, 3) float CIELAB."""
    c = rgb[:, :3].astype(float64) / 255.0
    linear = where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = dot(linear, array(_XYZ_FROM_LINEAR_RGB).T) / array(_D65_WHITE)
    f = where(xyz > 0.008856, cbrt(xyz), 7.787 * xyz + 16.0 / 116.0)
    lab = empty(xyz.shape, dtype=float64)
    lab[:, 0] = 116.0 * f[:, 1] - 16.0
    lab[:, 1] = 500.0 * (f[:, 0] - f[:, 1])
    lab[:, 2] = 200.0 * (f[:, 1] - f[:, 2])
    return lab


def _hex(rgb, alpha=True):
    if alpha:
        return "#%02X%02X%02XFF" % (int(rgb[0]), int(rgb[1]), int(rgb[2]))
    return "#%02X%02X%02X" % (int(rgb[0]), int(rgb[1]), int(rgb[2]))
