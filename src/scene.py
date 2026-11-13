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
    triangle_colors  (nt, 4) uint8 RGBA, averaged over each triangle
    vertex_colors    (nv, 4) uint8 RGBA, kept unaveraged for full-colour
                     output, where smooth colour is the whole point
    triangle_sources (nt,) int32, index into source_names
    sources          list of (drawing name, triangle count), for reporting
    triangle_groups  (nt,) int32, index into group_names: the chain or model
                     each triangle belongs to, when collected with parts=
    group_names      list of str, one per group
    """

    def __init__(self, vertices, triangles, triangle_colors, sources,
                 triangle_sources=None, vertex_colors=None,
                 triangle_groups=None, group_names=None):
        self.vertices = vertices
        self.triangles = triangles
        self.triangle_colors = triangle_colors
        self.sources = sources
        self.triangle_sources = triangle_sources
        self.vertex_colors = vertex_colors
        self.triangle_groups = triangle_groups
        self.group_names = group_names

    def with_arrays(self, vertices, triangles, keep=None, vertex_colors=None):
        """A copy with new vertices and triangles. The per-triangle arrays are
        filtered or reordered by keep (a mask or an index array)."""
        def pick(a):
            return a if a is None or keep is None else a[keep]
        return SceneGeometry(
            vertices, triangles, pick(self.triangle_colors), self.sources,
            pick(self.triangle_sources),
            self.vertex_colors if vertex_colors is None else vertex_colors,
            pick(self.triangle_groups), self.group_names)

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


def collect_geometry(session, models=None, parts=None):
    """Return a SceneGeometry for the displayed parts of the given models.

    parts  None, "chain" or "model": also label every triangle with the chain
           or the top-level model it belongs to (triangle_groups).
    """
    _flush_pending_graphics(session)

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
    groups = _Groups(parts) if parts else None
    group_arrays = []
    for d in drawings:
        piece = _drawing_geometry(d)
        if piece is None:
            continue
        pieces.append(piece)
        sources.append((_drawing_name(d), len(piece[1])))
        if groups is not None:
            group_arrays.append(groups.label(d, piece[0], piece[1]))

    if not pieces:
        return SceneGeometry(zeros((0, 3), float32), zeros((0, 3), int32),
                             zeros((0, 4), uint8), [])

    geometry = _combine(pieces, sources)
    if groups is not None:
        geometry.triangle_groups, geometry.group_names = groups.finish(
            concatenate(group_arrays))
    return geometry


class _Groups:
    """Assigns each triangle to a chain or to a top-level model.

    A chain belongs to its structure, not to the top-level model: the models
    of an NMR ensemble or a set of predictions (#1.1, #1.2, ...) each have a
    chain A, and those stay separate parts.

    Wherever ChimeraX knows what a triangle was drawn for, that is used:

    molecular surface  the atom behind each vertex, so one surface enclosing
                       several chains is split exactly
    ribbon             the residue each stretch of the ribbon was drawn for
    atoms, bonds,      one sphere or cylinder per instance; each goes, whole,
    pseudobonds        to the chain of the nearest drawn atom, so nothing is
                       cut in two where chains meet

    Only what is left (tethers, surface caps, a surface whose atom map is
    gone) is assigned triangle by triangle to the nearest atom. Geometry not
    built from atoms (map surfaces, shapes) goes to its top-level model.
    """

    def __init__(self, mode):
        self.mode = mode
        self._keys = {}         # (owner model, chain id or None) -> index
        self._trees = {}        # cache key -> (KD-tree, group per atom)

    def label(self, d, vertices, triangles):
        from numpy import full, repeat
        instances = max(1, len(triangles) // max(1, len(d.masked_triangles)))
        per_instance = len(triangles) // instances

        def by_instance(key, atoms):
            centres = vertices.reshape(instances, -1, 3).mean(axis=1)
            return repeat(self._nearest(key, atoms, centres), per_instance)

        def by_triangle(key, atoms):
            return self._nearest(key, atoms, vertices[triangles].mean(axis=1))

        structure = _structure_of(d)
        if structure is None:
            # pseudobonds between structures (hydrogen bonds, distances) are
            # a model of their own, but belong to the atoms they join
            ends = _pseudobond_atoms(d)
            if ends is not None:
                return by_instance(("pseudobonds", id(d)), lambda: ends)
            return full(len(triangles), self._index(_top_model(d), None),
                        int32)
        if self.mode == "model":
            return full(len(triangles),
                        self._index(_top_model(structure), None), int32)

        def drawn():
            return _drawn_atoms(structure)

        from chimerax.atomic import MolecularSurface
        if isinstance(d, MolecularSurface):
            v2a = d.vertex_to_atom_map() if instances == 1 else None
            if v2a is not None and len(v2a) == len(vertices):
                per_atom = self._chain_groups(structure, d.atoms.chain_ids)
                return per_atom[v2a][triangles[:, 0]]
            # no atom map (recoloured with sharp edges): the surface's own
            # atoms, whether or not they are drawn
            return by_triangle(("surface", id(d)), lambda: d.atoms)

        if instances == 1:
            groups = self._ribbon_groups(d, structure, vertices, triangles)
            if groups is not None:
                unknown = groups < 0
                if unknown.any():
                    groups[unknown] = by_triangle(structure, drawn)[unknown]
                return groups

        if instances > 1 or type(d).__name__ in ("AtomsDrawing",
                                                 "BondsDrawing"):
            return by_instance(structure, drawn)
        return by_triangle(structure, drawn)

    def finish(self, triangle_groups):
        """Renumber the groups in model and chain order, and name them.

        Groups that received no triangle are dropped. Returns the renumbered
        per-triangle array and the names, which are unique: a repeated name
        gets its model number.
        """
        from collections import Counter
        from numpy import unique, zeros
        used = set(unique(triangle_groups).tolist())
        keys = sorted((k for k, i in self._keys.items() if i in used),
                      key=lambda k: (_model_id(k[0]), k[1] or ""))
        chain_owners = {owner for owner, chain in keys if chain is not None}
        plain = len(chain_owners) == 1 and all(c is not None for _, c in keys)
        names = []
        for owner, chain in keys:
            if chain is None:
                names.append(owner.name)
            elif plain:
                names.append("chain %s" % chain)
            else:
                names.append("%s chain %s" % (owner.name, chain))
        repeated = {n for n, count in Counter(names).items() if count > 1}
        for i, (owner, _) in enumerate(keys):
            if names[i] in repeated:
                names[i] = "%s #%s" % (names[i], ".".join(
                    str(n) for n in _model_id(owner)))
        renumber = zeros(len(self._keys), int32)
        for new, key in enumerate(keys):
            renumber[self._keys[key]] = new
        return renumber[triangle_groups], names

    def _index(self, owner, chain):
        key = (owner, chain)
        if key not in self._keys:
            self._keys[key] = len(self._keys)
        return self._keys[key]

    def _chain_groups(self, structure, chain_ids):
        """Group index for each of the given chain IDs of one structure."""
        from numpy import unique
        ids, inverse = unique(chain_ids, return_inverse=True)
        lookup = array([self._index(structure, str(c)) for c in ids], int32)
        return lookup[inverse.ravel()]

    def _atom_groups(self, atoms):
        """Coordinates and group index of atoms from any number of
        structures."""
        from numpy import full
        coords, groups = [], []
        for structure, some in atoms.by_structure:
            coords.append(some.scene_coords)
            if self.mode == "model":
                groups.append(full(len(some), self._index(
                    _top_model(structure), None), int32))
            else:
                groups.append(self._chain_groups(structure, some.chain_ids))
        return concatenate(coords), concatenate(groups)

    def _nearest(self, key, atoms, points):
        """Group of the atom nearest each point. atoms is a function, called
        once per key."""
        if key not in self._trees:
            from scipy.spatial import cKDTree
            coords, groups = self._atom_groups(atoms())
            self._trees[key] = (cKDTree(coords), groups)
        tree, groups = self._trees[key]
        return groups[tree.query(points)[1]]

    def _ribbon_groups(self, d, structure, vertices, triangles):
        """Group per triangle of a ribbon drawing, -1 where ChimeraX recorded
        no residue; None if d is not a ribbon or its records do not fit."""
        from numpy import full
        ranges = getattr(d, "_triangle_ranges", None)
        residues = getattr(d, "_residues", None)
        if ranges is None or residues is None or len(ranges) == 0:
            return None
        try:
            of_residue = self._chain_groups(structure, residues.chain_ids)
            per_vertex = full(len(vertices), -1, int32)
            for i, _, _, first, end in ranges:
                per_vertex[first:end] = of_residue[i]
        except (IndexError, TypeError, ValueError):
            return None
        return per_vertex[triangles[:, 0]]


def _drawn_atoms(structure):
    """The atoms of a structure that something is drawn for.

    Hidden waters or ions with a chain ID of their own would otherwise claim
    the triangles next to them. The cartoon command flags every residue as
    ribbon-displayed, waters and ions included, but only polymer residues
    get a ribbon.
    """
    from chimerax.atomic import Residue
    atoms = structure.atoms
    residues = atoms.residues
    in_ribbon = (residues.ribbon_displays
                 & (residues.polymer_types != Residue.PT_NONE))
    drawn = atoms.visibles | in_ribbon
    return atoms.filter(drawn) if drawn.any() else atoms


def _pseudobond_atoms(d):
    """The atoms joined by the pseudobond group d belongs to, or None."""
    from chimerax.atomic import Atoms, PseudobondGroup
    from chimerax.atomic import concatenate as join
    p = d
    while p is not None and not isinstance(p, PseudobondGroup):
        p = getattr(p, "parent", None)
    if p is None or p.num_pseudobonds == 0:
        return None
    return join(p.pseudobonds.atoms, Atoms)


def _model_id(model):
    return tuple(getattr(model, "id", None) or ())


def _structure_of(d):
    from chimerax.atomic import Structure
    p = d
    while p is not None and not isinstance(p, Structure):
        p = getattr(p, "parent", None)
    return p


def _top_model(d):
    """The top-level model (#1, #2, ...) a drawing belongs to."""
    from chimerax.core.models import Model
    top, p = None, d
    while p is not None:
        if isinstance(p, Model) and getattr(p, "id", None):
            top = p
        p = getattr(p, "parent", None)
    return top if top is not None else d


def _flush_pending_graphics(session):
    """Apply changes that have not reached the drawings yet.

    Commands like 'hide atoms' mark the scene as changed but the drawings are
    only rebuilt on the next frame.  Reading geometry before that gives the
    previous state - hidden atoms still present, recent recolouring missing.
    Nothing forces a frame in --nogui, so export what would be drawn next.
    """
    try:
        session.update_loop.update_graphics_now()
    except Exception:
        pass        # no update loop (or no graphics at all); use what we have


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
    out_vc = empty((ni * nv, 4), uint8)

    ta32 = ta.astype(int32)
    for i, place in enumerate(positions):
        out_v[i * nv:(i + 1) * nv] = place.transform_points(va)
        out_t[i * nt:(i + 1) * nt] = ta32 + i * nv
        if vertex_colors is not None:
            out_c[i * nt:(i + 1) * nt] = _triangle_colors(vertex_colors, ta)
            out_vc[i * nv:(i + 1) * nv] = vertex_colors
        else:
            out_c[i * nt:(i + 1) * nt] = instance_colors[i]
            out_vc[i * nv:(i + 1) * nv] = instance_colors[i]

    return out_v, out_t, out_c, out_vc


def _triangle_colors(vertex_colors, triangles):
    """Average the three vertex colours of each triangle."""
    vc = vertex_colors.astype(uint32)
    tc = (vc[triangles[:, 0]] + vc[triangles[:, 1]] + vc[triangles[:, 2]]) // 3
    return tc.astype(uint8)


def _combine(pieces, sources):
    from numpy import full
    vertex_arrays, triangle_arrays, color_arrays = [], [], []
    source_arrays, vcolor_arrays = [], []
    offset = 0
    for i, (va, ta, ca, vca) in enumerate(pieces):
        vertex_arrays.append(va)
        triangle_arrays.append(ta + offset)
        color_arrays.append(ca)
        vcolor_arrays.append(vca)
        source_arrays.append(full(len(ta), i, dtype=int32))
        offset += len(va)
    return SceneGeometry(
        concatenate(vertex_arrays),
        concatenate(triangle_arrays),
        concatenate(color_arrays),
        sources,
        concatenate(source_arrays),
        concatenate(vcolor_arrays),
    )


def weld_vertices(geometry, tolerance=1e-4):
    """Merge vertices that land on the same point, so the mesh is connected.

    Instanced geometry and separate drawings produce many coincident vertices;
    slicers want them shared.  Triangle colours are untouched.

    Vertices within tolerance (scene units, Angstrom) of each other are
    merged. Rounding coordinates and comparing them does not do this: two
    copies of one point that differ by a millionth fall on opposite sides of
    a rounding boundary often enough to leave a slit in about every bond of
    a stick model, where the two half cylinders meet.

    Then internal double walls are removed (_internal_walls) and round open
    rims capped (_cap_round_holes), so stick and strut models arrive closed.
    """
    from numpy import arange, ones, unique
    v = geometry.vertices
    if len(v) == 0:
        return geometry
    from scipy.spatial import cKDTree
    pairs = cKDTree(v).query_pairs(tolerance, output_type="ndarray")
    if len(pairs):
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        n = len(v)
        links = coo_matrix((ones(len(pairs), bool), (pairs[:, 0], pairs[:, 1])),
                           shape=(n, n))
        _, labels = connected_components(links, directed=False)
    else:
        labels = arange(len(v))
    # one vertex per group of coincident ones, keeping the mapping
    _, first, inverse = unique(labels, return_index=True, return_inverse=True)
    new_vertices = v[first]
    new_triangles = inverse.ravel()[geometry.triangles].astype(int32)
    # drop triangles that collapsed to a line or point
    keep = ((new_triangles[:, 0] != new_triangles[:, 1]) &
            (new_triangles[:, 1] != new_triangles[:, 2]) &
            (new_triangles[:, 0] != new_triangles[:, 2]))
    keep &= ~_internal_walls(new_triangles, keep)
    vcolors = geometry.vertex_colors
    welded = geometry.with_arrays(new_vertices.astype(float32),
                                  new_triangles[keep], keep,
                                  None if vcolors is None else vcolors[first])
    return _cap_round_holes(welded)


def _internal_walls(triangles, candidates):
    """Mask of triangles that lie on another triangle facing the other way.

    ChimeraX draws a pseudobond (hydrogen bond, distance, strut) as two
    capped half cylinders; their caps meet face to face in the middle. That
    double wall is inside the solid, and its rim edges belong to four
    triangles, which slicers report as a broken mesh. Removing each such pair
    leaves one closed cylinder. Pairs facing the same way are left alone: two
    copies of one surface are not inside anything. A strut whose halves went
    to two different parts loses its middle caps here too; _cap_round_holes
    then closes each half in its own part.
    """
    from numpy import (arange, argmin, bincount, column_stack, concatenate,
                       cumsum, diff, flatnonzero, lexsort, ones, split, zeros)
    mask = zeros(len(triangles), bool)
    idx = arange(len(triangles))[candidates]
    if len(idx) < 2:
        return mask
    t = triangles[idx].astype("int64")
    # rotate each triangle so its smallest vertex comes first; the order of
    # the other two then tells which way it faces
    r = argmin(t, axis=1)
    rows = arange(len(t))
    a, b, c = t[rows, r], t[rows, (r + 1) % 3], t[rows, (r + 2) % 3]
    lo, hi = (b < c).choose(c, b), (b < c).choose(b, c)
    facing = (b < c).astype("int64")
    keys = column_stack((a, lo, hi))
    order = lexsort((facing, hi, lo, a))
    keys, facing, idx = keys[order], facing[order], idx[order]
    same = (keys[1:] == keys[:-1]).all(axis=1)
    if not same.any():
        return mask
    # runs of equal keys are triangles lying on each other; within a run,
    # pair one of each facing. Only those runs are visited.
    run =cumsum(concatenate((ones(1, bool), ~same))) - 1
    shared = flatnonzero(bincount(run)[run] > 1)    # positions in such runs
    for pos in split(shared, flatnonzero(diff(run[shared])) + 1):
        down, up = idx[pos][facing[pos] == 0], idx[pos][facing[pos] == 1]
        pairs = min(len(down), len(up))
        mask[down[:pairs]] = True
        mask[up[:pairs]] = True
    return mask


def _cap_round_holes(geometry, roundness=0.02):
    """Close every open rim that is a flat circle, with a fan of triangles.

    ChimeraX draws bond cylinders without end caps: the open end sits inside
    the atom sphere, invisible, but a slicer counts every edge of it as open
    and reports the mesh as broken. Each such rim gets a cap here. A rim
    counts as round when all its vertices lie in one plane and at the same
    distance from its centre, within roundness of that distance; ragged
    openings, such as a surface cut by a clipping plane, are left as they
    are. Edges are counted within one part, so the rim of a half bond whose
    other half went to another chain's part is closed in its own part.

    Cap triangles take the colour, source drawing and part of the triangle
    whose rim they close, and face the way that keeps the mesh consistently
    oriented.
    """
    from numpy import (arange, array, concatenate, int64, unique, zeros)
    from numpy.linalg import svd
    t = geometry.triangles.astype(int64)
    if len(t) == 0:
        return geometry
    nv = len(geometry.vertices)
    groups = geometry.triangle_groups
    part = zeros(len(t), int64) if groups is None else groups.astype(int64)
    # directed edges a->b as they run in their triangles
    a = concatenate([t[:, 0], t[:, 1], t[:, 2]])
    b = concatenate([t[:, 1], t[:, 2], t[:, 0]])
    owner = concatenate([arange(len(t))] * 3)
    p = part[owner]
    lo, hi = (a < b).choose(b, a), (a < b).choose(a, b)
    key = (p * nv + lo) * nv + hi
    _, inverse, counts = unique(key, return_inverse=True, return_counts=True)
    open_ = counts[inverse.ravel()] == 1
    if not open_.any():
        return geometry

    # follow each loop through its directed open edges
    nxt = {}
    edge_owner = {}
    bad = set()
    for ea, eb, o, pp in zip(a[open_].tolist(), b[open_].tolist(),
                             owner[open_].tolist(), p[open_].tolist()):
        if (pp, ea) in nxt:
            bad.add((pp, ea))           # a vertex where two loops touch
        nxt[(pp, ea)] = eb
        edge_owner[(pp, ea)] = o
    v = geometry.vertices
    new_vertices, new_triangles, from_triangle = [], [], []
    rim_vertex = []                     # one rim vertex per cap, for colour
    done = set()
    for start in list(nxt):
        if start in done or start in bad:
            continue
        pp = start[0]
        loop, node, ok = [], start, True
        while node not in done:
            if node in bad or node not in nxt:
                ok = False
                break
            done.add(node)
            loop.append(node[1])
            node = (pp, nxt[node])
        if not ok or node != start or len(loop) < 3:
            continue
        pts = v[loop].astype(float)
        centre = pts.mean(axis=0)
        radius = ((pts - centre) ** 2).sum(axis=1) ** 0.5
        mean = radius.mean()
        if mean <= 0 or (radius.max() - radius.min()) > roundness * mean:
            continue
        normal = svd(pts - centre)[2][2]
        if abs((pts - centre) @ normal).max() > roundness * mean:
            continue
        c = nv + len(new_vertices)
        new_vertices.append(centre)
        rim_vertex.append(loop[0])
        for i, va in enumerate(loop):
            vb = loop[(i + 1) % len(loop)]
            # the rim edge runs va->vb in its triangle; the cap runs it back
            new_triangles.append((c, vb, va))
            from_triangle.append(edge_owner[(pp, va)])
    if not new_triangles:
        return geometry

    from numpy import float32, int32
    src = array(from_triangle, int64)
    vertices = concatenate([v, array(new_vertices, float32)])
    triangles = concatenate([geometry.triangles,
                             array(new_triangles, int32)])
    keep = concatenate([arange(len(t)), src])      # copy per-triangle data
    vcolors = geometry.vertex_colors
    if vcolors is not None:
        # a cap centre takes the colour of the rim it closes
        vcolors = concatenate([vcolors, vcolors[rim_vertex]])
    return geometry.with_arrays(vertices, triangles, keep, vcolors)

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

    return geometry.with_arrays(v.astype(float32), geometry.triangles), scale
