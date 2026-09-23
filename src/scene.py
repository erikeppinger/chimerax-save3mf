# vim: set expandtab shiftwidth=4 softtabstop=4:
"""Collect the displayed ChimeraX scene as one triangle soup with a colour per
triangle.

Follows the same traversal the STL and glTF exporters use: walk every drawing
below the requested models, keep the ones that are actually shown, honour the
triangle mask, and expand instanced drawings (atom spheres, bond cylinders)
into real triangles.
"""

from numpy import (
    array, concatenate, empty, float32, int32, uint8, uint32, zeros,
)


class SceneGeometry:
    """Triangles of the displayed scene, with a colour for each triangle.

    vertices         (nv, 3) float32, scene coordinates
    triangles        (nt, 3) int32, indices into vertices
    triangle_colors  (nt, 4) uint8 RGBA
    triangle_sources (nt,) int32, index into source_names
    sources          list of (drawing name, triangle count), for reporting
    """

    def __init__(self, vertices, triangles, triangle_colors, sources,
                 triangle_sources=None):
        self.vertices = vertices
        self.triangles = triangles
        self.triangle_colors = triangle_colors
        self.sources = sources
        self.triangle_sources = triangle_sources

    @property
    def source_names(self):
        return [name for name, _ in self.sources]

    @property
    def triangle_count(self):
        return len(self.triangles)

    @property
    def vertex_count(self):
        return len(self.vertices)

    def bounds(self):
        return self.vertices.min(axis=0), self.vertices.max(axis=0)


def collect_geometry(session, models=None):
    """Return a SceneGeometry for the displayed parts of the given models."""
    if models is None:
        models = session.models.list()

    drawings = []
    seen = set()
    for m in models:
        for d in m.all_drawings():
            if id(d) not in seen:
                seen.add(id(d))
                drawings.append(d)

    pieces = []
    sources = []
    for d in drawings:
        piece = _drawing_geometry(d)
        if piece is None:
            continue
        pieces.append(piece)
        sources.append((_drawing_name(d), len(piece[1])))

    if not pieces:
        return SceneGeometry(zeros((0, 3), float32), zeros((0, 3), int32),
                             zeros((0, 4), uint8), [])

    return _combine(pieces, sources)


def _drawing_name(d):
    name = getattr(d, 'name', None)
    return name if name else d.__class__.__name__


def _drawing_geometry(d):
    """Vertices, triangles and per-triangle colours for one drawing, with its
    instances expanded.  None if the drawing contributes nothing."""
    va, ta = d.vertices, d.masked_triangles
    if va is None or ta is None or len(ta) == 0:
        return None
    if not (d.display and d.parents_displayed):
        return None
    positions = d.get_scene_positions(displayed_only=True)
    if len(positions) == 0:
        return None

    vertex_colors = d.vertex_colors
    if vertex_colors is None:
        instance_colors = d.get_colors(displayed_only=True)
    else:
        instance_colors = None

    nv, nt = len(va), len(ta)
    ni = len(positions)

    out_v = empty((ni * nv, 3), float32)
    out_t = empty((ni * nt, 3), int32)
    out_c = empty((ni * nt, 4), uint8)

    ta32 = ta.astype(int32)
    for i, place in enumerate(positions):
        out_v[i * nv:(i + 1) * nv] = place.transform_points(va)
        out_t[i * nt:(i + 1) * nt] = ta32 + i * nv
        if vertex_colors is not None:
            out_c[i * nt:(i + 1) * nt] = _triangle_colors(vertex_colors, ta)
        else:
            out_c[i * nt:(i + 1) * nt] = instance_colors[i]

    return out_v, out_t, out_c


def _triangle_colors(vertex_colors, triangles):
    """Average the three vertex colours of each triangle."""
    vc = vertex_colors.astype(uint32)
    tc = (vc[triangles[:, 0]] + vc[triangles[:, 1]] + vc[triangles[:, 2]]) // 3
    return tc.astype(uint8)


def _combine(pieces, sources):
    from numpy import full
    vertex_arrays, triangle_arrays, color_arrays, source_arrays = [], [], [], []
    offset = 0
    for i, (va, ta, ca) in enumerate(pieces):
        vertex_arrays.append(va)
        triangle_arrays.append(ta + offset)
        color_arrays.append(ca)
        source_arrays.append(full(len(ta), i, dtype=int32))
        offset += len(va)
    return SceneGeometry(
        concatenate(vertex_arrays),
        concatenate(triangle_arrays),
        concatenate(color_arrays),
        sources,
        concatenate(source_arrays),
    )


def weld_vertices(geometry, tolerance=1e-4):
    """Merge vertices that land on the same point, so the mesh is connected.

    Instanced geometry and separate drawings produce many coincident vertices;
    slicers want them shared.  Triangle colours are untouched.
    """
    from numpy import round as np_round, unique
    v = geometry.vertices
    if len(v) == 0:
        return geometry
    decimals = max(0, int(round(-_log10(tolerance))))
    keys = np_round(v, decimals)
    # unique rows, keeping the mapping from old index to new
    _, first, inverse = unique(keys, axis=0, return_index=True,
                               return_inverse=True)
    new_vertices = v[first]
    new_triangles = inverse[geometry.triangles].astype(int32)
    # drop triangles that collapsed to a line or point
    keep = ((new_triangles[:, 0] != new_triangles[:, 1]) &
            (new_triangles[:, 1] != new_triangles[:, 2]) &
            (new_triangles[:, 0] != new_triangles[:, 2]))
    sources = geometry.triangle_sources
    return SceneGeometry(new_vertices.astype(float32), new_triangles[keep],
                         geometry.triangle_colors[keep], geometry.sources,
                         None if sources is None else sources[keep])


def _log10(x):
    from math import log10
    return log10(x)


def place_for_printing(geometry, scale=1.0, size=None):
    """Scale to millimetres and sit the model in the positive octant.

    Coordinates must not go negative: a slicer loading a 3MF without its own
    placement config takes them literally, and anything at negative x or y is
    off the build plate.  The model is moved so its bounding box starts at
    the origin, with its lowest point at z = 0.

    scale  millimetres per Angstrom (ChimeraX scene units)
    size   if given, scale so the longest edge of the bounding box is this
           many millimetres; overrides scale
    """
    v = geometry.vertices
    if len(v) == 0:
        return geometry, 1.0

    low, high = v.min(axis=0), v.max(axis=0)
    span = high - low
    if size is not None:
        longest = float(span.max())
        scale = (size / longest) if longest > 0 else 1.0

    v = (v - low) * scale            # bounding-box corner at the origin

    return SceneGeometry(v.astype(float32), geometry.triangles,
                         geometry.triangle_colors, geometry.sources,
                         geometry.triangle_sources), scale
