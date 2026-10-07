# vim: set expandtab shiftwidth=4 softtabstop=4:
"""Smoothness at print scale: how deep the flat facets are, and finer
tessellation for the export when they are deep enough to print.

ChimeraX tessellates for the screen. A 10-sided support cylinder is invisible
at screen size, but scaled to 200 mm it is a 3.5 mm-radius prism whose flats
sit 0.17 mm inside the true circle - nearly a whole 0.2 mm layer, and plainly
visible in the print.

The depth of a flat is measured from the mesh itself rather than predicted
from settings, so it holds for any geometry. For two triangles meeting at an
edge with a crease angle theta, a surface of width h across that edge sits at
most h * theta / 8 inside the smooth curve it approximates - the sagitta of a
polygon side. Sharp edges (above 60 degrees) are real corners, such as the
rim of a ribbon, and are not counted.

Depth falls with the square of the number of sides around a cylinder and in
proportion to the triangle count of a sphere, which gives the setting needed
to reach a target directly.

Only atoms, bonds, pseudobonds and ribbons can be re-tessellated from
ChimeraX's level-of-detail settings. Molecular surfaces and map surfaces are
fixed when they are computed, so for those the depth is reported together
with how to recompute them finer.
"""

from math import ceil, sqrt

DEFAULT_SMOOTHNESS = 0.05      # mm; well under one 0.1-0.2 mm print layer
MAX_CREASE_DEGREES = 60.0      # sharper than this is a corner, not a facet
PERCENTILE = 95                # ignore a handful of awkward triangles

# finer than this buys nothing a printer can show, and costs file size
MAX_CYLINDER_SIDES = 64
MAX_SPHERE_TRIANGLES = 5000
MAX_RIBBON_SIDES = 48
MAX_RIBBON_DIVISIONS = 40
TRIANGLE_BUDGET = 3000000      # beyond this, slicers become slow to load

ADJUSTABLE = ("pbonds", "bonds", "atoms", "ribbons")
LABELS = {
    "pbonds": "supports and other pseudobonds",
    "bonds": "bonds",
    "atoms": "atoms",
    "ribbons": "ribbons",
    "surfaces": "surfaces",
}


def kind_of(source_name):
    """Which tessellation setting governs a drawing, by its name."""
    if source_name in ADJUSTABLE:
        return source_name
    if "tether" in source_name:
        return None             # thin ribbon tethers; not worth smoothing
    return "surfaces"


# ---------------------------------------------------------------- measuring

class FlatDepths:
    """Depth of the flats, in mm, for each kind of geometry present."""

    def __init__(self, depth, triangles):
        self.depth = depth              # kind -> mm (95th percentile)
        self.triangles = triangles      # kind -> triangle count

    def worst(self, kinds=None):
        values = [d for k, d in self.depth.items()
                  if kinds is None or k in kinds]
        return max(values) if values else 0.0

    def above(self, target, kinds=None):
        return {k: d for k, d in self.depth.items()
                if d > target and (kinds is None or k in kinds)}


def measure(geometry):
    """FlatDepths for geometry already scaled to millimetres."""
    from numpy import (arccos, argsort, clip, concatenate, cross, einsum,
                       minimum, percentile, radians, sqrt as np_sqrt, tile,
                       arange, int64)

    v = geometry.vertices.astype(float)
    t = geometry.triangles
    if len(t) == 0 or geometry.triangle_sources is None:
        return FlatDepths({}, {})

    names = geometry.source_names
    kind_index = {}
    source_kind = []
    for name in names:
        k = kind_of(name)
        source_kind.append(-1 if k is None else
                           kind_index.setdefault(k, len(kind_index)))
    from numpy import array
    tri_kind = array(source_kind, dtype=int64)[geometry.triangle_sources]

    normal = cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]])
    twice_area = np_sqrt(einsum("ij,ij->i", normal, normal))
    ok = twice_area > 0
    normal[ok] /= twice_area[ok, None]

    # every edge of every triangle; an edge shared by two triangles appears
    # twice with the same sorted vertex pair
    edges = concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    owner = tile(arange(len(t)), 3)
    lo, hi = edges.min(axis=1).astype(int64), edges.max(axis=1).astype(int64)
    key = lo * len(v) + hi
    order = argsort(key, kind="stable")
    same = key[order[1:]] == key[order[:-1]]
    first, second = order[:-1][same], order[1:][same]
    t1, t2 = owner[first], owner[second]

    keep = (tri_kind[t1] == tri_kind[t2]) & (tri_kind[t1] >= 0) & ok[t1] & ok[t2]
    t1, t2 = t1[keep], t2[keep]
    a, b = lo[first][keep], hi[first][keep]

    crease = arccos(clip(einsum("ij,ij->i", normal[t1], normal[t2]), -1, 1))
    length = np_sqrt(((v[b] - v[a]) ** 2).sum(axis=1))
    curved = (crease > 1e-3) & (crease < radians(MAX_CREASE_DEGREES)) & (length > 0)
    t1, t2, crease, length = t1[curved], t2[curved], crease[curved], length[curved]
    width = minimum(twice_area[t1], twice_area[t2]) / length
    depth = width * crease / 8.0

    kinds = {i: k for k, i in kind_index.items()}
    edge_kind = tri_kind[t1]
    result, counts = {}, {}
    for i, k in kinds.items():
        counts[k] = int((tri_kind == i).sum())
        d = depth[edge_kind == i]
        if len(d):
            result[k] = float(percentile(d, PERCENTILE))
    return FlatDepths(result, counts)


# ----------------------------------------------------------------- settings

class Settings:
    """The tessellation settings that matter here, as currently in effect."""

    def __init__(self, session):
        from chimerax.atomic import structure_graphics_updater
        self.session = session
        self.gu = structure_graphics_updater(session)
        lod = self.gu.level_of_detail
        self.lod = lod

        self.atom_fixed = lod.atom_fixed_triangles
        self.bond_fixed = lod.bond_fixed_triangles
        self.pbond_sides = lod.pseudobond_sides
        self.ribbon_fixed = lod.ribbon_fixed_divisions

        # what is actually drawn now, which with automatic level of detail
        # depends on how many atoms are shown
        self.atom_triangles = _drawn_triangles(session, "atoms")
        bond_tris = _drawn_triangles(session, "bonds")
        self.bond_sides = bond_tris // 2 if bond_tris else None   # 2 per side

        self.ribbon_sides = {}
        self.ribbon_divisions = None
        for s in self.gu.structures:
            mgr = getattr(s, "ribbon_xs_mgr", None)
            if mgr is None:
                continue
            self.ribbon_sides[s] = mgr.params[mgr.STYLE_ROUND]["sides"]
            div = lod.ribbon_divisions(s.num_ribbon_residues)
            self.ribbon_divisions = max(div, self.ribbon_divisions or 0)


def _drawn_triangles(session, name):
    """Triangles per instance of the displayed drawings with this name."""
    best = 0
    for m in session.models.list():
        for d in m.all_drawings():
            if getattr(d, "name", None) == name and d.display \
                    and d.triangles is not None:
                best = max(best, len(d.triangles))
    return best


class Plan:
    """New settings for each kind of geometry whose flats are too deep."""

    def __init__(self, target, depths, settings):
        self.target = target
        self.depths = depths
        self.settings = settings
        self.changes = {}           # kind -> (old, new) description values
        self.limited = False        # caps or the triangle budget stopped short
        self.pbond_sides = None
        self.bond_sides = None
        self.atom_triangles = None
        self.ribbon_sides = None
        self.ribbon_divisions = None
        self.triangles_before = sum(depths.triangles.values())
        self.triangles_after = self.triangles_before

    @property
    def needed(self):
        return bool(self.changes)

    def unreachable(self):
        """Kinds above target that settings cannot change: surfaces."""
        return self.depths.above(self.target, kinds=("surfaces",))


def plan(session, depths, target):
    """Work out finer settings so that flats are at most `target` mm."""
    settings = Settings(session)
    p = Plan(target, depths, settings)
    too_deep = depths.above(target, kinds=ADJUSTABLE)
    if not too_deep:
        return p

    # Ask for a little more than the target so a rounding of sides down
    # does not leave the result just above it.
    def ratio(kind, relax=1.0):
        return depths.depth[kind] / (target * 0.9 * relax)

    relax = 1.0
    while True:
        changes, growth, limited = {}, {}, False
        if "pbonds" in too_deep:
            old = settings.pbond_sides
            new, capped = _sides(old, ratio("pbonds", relax), MAX_CYLINDER_SIDES)
            changes["pbonds"] = (old, new)
            growth["pbonds"] = new / old
            limited |= capped
        if "bonds" in too_deep and settings.bond_sides:
            old = settings.bond_sides
            new, capped = _sides(old, ratio("bonds", relax), MAX_CYLINDER_SIDES)
            changes["bonds"] = (old, new)
            growth["bonds"] = new / old
            limited |= capped
        if "atoms" in too_deep and settings.atom_triangles:
            old = settings.atom_triangles
            new = int(ceil(old * ratio("atoms", relax)))
            new += new % 2
            capped = new > MAX_SPHERE_TRIANGLES
            new = min(new, MAX_SPHERE_TRIANGLES)
            changes["atoms"] = (old, max(new, old))
            growth["atoms"] = max(new, old) / old
            limited |= capped
        if "ribbons" in too_deep and settings.ribbon_sides:
            old_sides = max(settings.ribbon_sides.values())
            old_div = settings.ribbon_divisions or 20
            factor = sqrt(ratio("ribbons", relax))
            new_sides = min(MAX_RIBBON_SIDES,
                            2 * int(ceil(old_sides * factor / 2)))
            new_div = min(MAX_RIBBON_DIVISIONS, int(ceil(old_div * factor)))
            new_sides, new_div = max(new_sides, old_sides), max(new_div, old_div)
            changes["ribbons"] = ((old_sides, old_div), (new_sides, new_div))
            growth["ribbons"] = (new_sides / old_sides) * (new_div / old_div)
            limited |= (new_sides == MAX_RIBBON_SIDES and
                        old_sides * factor > MAX_RIBBON_SIDES)

        after = sum(n * growth.get(k, 1.0) for k, n in depths.triangles.items())
        if after <= TRIANGLE_BUDGET or relax > 64:
            break
        relax *= 1.5            # aim coarser until the file stays manageable
        limited = True

    p.changes = {k: c for k, c in changes.items() if c[0] != c[1]}
    p.limited = limited
    p.triangles_after = int(after)
    if "pbonds" in p.changes:
        p.pbond_sides = p.changes["pbonds"][1]
    if "bonds" in p.changes:
        p.bond_sides = p.changes["bonds"][1]
    if "atoms" in p.changes:
        p.atom_triangles = p.changes["atoms"][1]
    if "ribbons" in p.changes:
        p.ribbon_sides, p.ribbon_divisions = p.changes["ribbons"][1]
    return p


def _sides(old, ratio, cap):
    """Cylinder sides that divide the flat depth by `ratio`."""
    want = int(ceil(old * sqrt(ratio)))
    return max(old, min(want, cap)), want > cap


class Applied:
    """Context manager: the plan's settings for the duration of the export,
    then exactly the previous ones again, so the display is left as it was."""

    def __init__(self, session, the_plan):
        self.session = session
        self.plan = the_plan

    def __enter__(self):
        p, s = self.plan, self.plan.settings
        _set(self.session, s,
             atom_fixed=p.atom_triangles if p.atom_triangles else s.atom_fixed,
             bond_fixed=4 * p.bond_sides if p.bond_sides else s.bond_fixed,
             pbond_sides=p.pbond_sides or s.pbond_sides,
             ribbon_fixed=p.ribbon_divisions or s.ribbon_fixed,
             ribbon_sides=(None if p.ribbon_sides is None else
                           {st: p.ribbon_sides for st in s.ribbon_sides}))
        return self

    def __exit__(self, *exc):
        s = self.plan.settings
        _set(self.session, s, atom_fixed=s.atom_fixed, bond_fixed=s.bond_fixed,
             pbond_sides=s.pbond_sides, ribbon_fixed=s.ribbon_fixed,
             ribbon_sides=s.ribbon_sides)
        from .scene import _flush_pending_graphics
        _flush_pending_graphics(self.session)
        return False


def _set(session, s, atom_fixed, bond_fixed, pbond_sides, ribbon_fixed,
         ribbon_sides):
    lod, gu = s.lod, s.gu
    lod.atom_fixed_triangles = atom_fixed
    lod.bond_fixed_triangles = bond_fixed
    if lod.pseudobond_sides != pbond_sides:
        lod.pseudobond_sides = pbond_sides
        from chimerax.atomic import all_pseudobond_groups
        for pbg in all_pseudobond_groups(session):
            pbg.update_cylinder_sides()
    if lod.ribbon_fixed_divisions != ribbon_fixed:
        gu.set_ribbon_divisions(ribbon_fixed)
    if ribbon_sides:
        # set directly rather than through 'cartoon style', which would add
        # an undo step for a change the user never made
        for st, sides in ribbon_sides.items():
            if not st.deleted:
                mgr = st.ribbon_xs_mgr
                mgr.set_params(mgr.STYLE_ROUND, sides=sides)
    gu.update_level_of_detail()


# ---------------------------------------------------------------- reporting

def describe_changes(p):
    """'supports 10 -> 24 sides, ribbons 12 -> 24 sides' and so on."""
    parts = []
    for kind in ADJUSTABLE:
        if kind not in p.changes:
            continue
        old, new = p.changes[kind]
        if kind in ("pbonds", "bonds"):
            parts.append("%s %d \N{RIGHTWARDS ARROW} %d sides"
                         % (_short(kind), old, new))
        elif kind == "atoms":
            parts.append("atoms %d \N{RIGHTWARDS ARROW} %d triangles"
                         % (old, new))
        else:
            (os_, od), (ns, nd) = old, new
            text = "ribbons %d \N{RIGHTWARDS ARROW} %d sides" % (os_, ns)
            if nd != od:
                text += ", %d \N{RIGHTWARDS ARROW} %d divisions" % (od, nd)
            parts.append(text)
    return ", ".join(parts)


def describe_depths(depths, kinds=None):
    """'supports 0.17 mm, ribbons 0.12 mm', deepest first."""
    items = sorted(((d, k) for k, d in depths.depth.items()
                    if kinds is None or k in kinds), reverse=True)
    return ", ".join("%s %.2f mm" % (_short(k), d) for d, k in items)


def _short(kind):
    return "supports" if kind == "pbonds" else LABELS[kind]


def surface_advice(kinds):
    if "surfaces" not in kinds:
        return ""
    return ("Surfaces keep the resolution they were computed at: recompute a "
            "molecular surface finer with 'surface gridSpacing 0.3' (or "
            "smaller), or show a map at full resolution with 'volume step 1'.")
