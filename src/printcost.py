# vim: set expandtab shiftwidth=4 softtabstop=4:
"""What the colour regions will cost to print, as opposed to how they look.

A multi-material print spends most of its time changing tools, not extruding:
each change purges filament into a wipe tower.  A region that covers very
little of the model can still be expensive, because what matters is not its
area but how many print layers it appears in - it forces a tool change on
every one of them.

The estimate is "regions present in a layer, minus one, summed over layers".
Checked against PrusaSlicer on a real export (tools/check_cost_model.py): 805
estimated against 811 actual tool changes, within 1%.
"""

from numpy import add, arange, cumsum, floor, int32, maximum, minimum, zeros

DEFAULT_LAYER_HEIGHT = 0.2
# a region under this share of the model's area is "small"
SMALL_AREA_FRACTION = 0.02
# ...and costly if it also drives at least this share of the tool changes
COSTLY_CHANGE_FRACTION = 0.05


class PrintCost:

    def __init__(self, layer_height, n_layers, layers_touched, tool_changes,
                 savings, area_fractions):
        self.layer_height = layer_height
        self.n_layers = n_layers
        self.layers_touched = layers_touched      # per region
        self.tool_changes = tool_changes          # total estimate
        self.savings = savings                    # changes saved per region
        self.area_fractions = area_fractions      # per region, 0..1

    def costly_regions(self):
        """Regions that cost far more to print than they cover.

        Returns [(region index, area fraction, change fraction), ...].
        """
        out = []
        if self.tool_changes <= 0:
            return out
        for r in range(len(self.layers_touched)):
            change_share = self.savings[r] / float(self.tool_changes)
            if (self.area_fractions[r] < SMALL_AREA_FRACTION
                    and change_share >= COSTLY_CHANGE_FRACTION):
                out.append((r, float(self.area_fractions[r]), float(change_share)))
        return out


def layer_presence(geometry, index_per_triangle, n_groups,
                   layer_height=DEFAULT_LAYER_HEIGHT):
    """Which print layers each group of triangles appears in.

    Returns a (n_groups, n_layers) boolean array.  Computing this once per
    distinct colour lets any clustering of those colours be costed by simply
    OR-ing rows together, which is what makes the merge ladder affordable.
    """
    verts, tris = geometry.vertices, geometry.triangles
    if len(tris) == 0 or layer_height <= 0:
        return zeros((n_groups, 0), dtype=bool)

    z = verts[:, 2]
    tri_z = z[tris]
    low = floor(tri_z.min(axis=1) / layer_height).astype(int32)
    high = floor(tri_z.max(axis=1) / layer_height).astype(int32)
    n_layers = int(high.max()) + 1

    presence = zeros((n_groups, n_layers), dtype=bool)
    for g in range(n_groups):
        members = index_per_triangle == g
        if not members.any():
            continue
        diff = zeros(n_layers + 1, dtype=int32)
        add.at(diff, low[members], 1)
        add.at(diff, minimum(high[members] + 1, n_layers), -1)
        presence[g] = cumsum(diff)[:n_layers] > 0
    return presence


def changes_from_presence(presence):
    """Tool changes implied by which groups appear in which layers."""
    if presence.size == 0:
        return 0
    per_layer = presence.sum(axis=0)
    return int(maximum(per_layer - 1, 0).sum())


def regroup_presence(presence, group_of_row, n_groups):
    """Combine per-colour presence into per-cluster presence."""
    from numpy import logical_or
    out = zeros((n_groups, presence.shape[1]), dtype=bool)
    logical_or.at(out, group_of_row, presence)
    return out


def estimate(geometry, regions, layer_height=DEFAULT_LAYER_HEIGHT):
    """Estimate the tool changes the given colour regions would cause.

    The geometry must already be scaled to millimetres, since the layer count
    depends on how tall the print is.
    """
    verts, tris = geometry.vertices, geometry.triangles
    labels = regions.labels
    n_regions = regions.count

    if len(tris) == 0 or layer_height <= 0:
        return PrintCost(layer_height, 0, zeros(n_regions, int32), 0,
                         zeros(n_regions, int32), zeros(n_regions))

    z = verts[:, 2]
    tri_z = z[tris]
    low = floor(tri_z.min(axis=1) / layer_height).astype(int32)
    high = floor(tri_z.max(axis=1) / layer_height).astype(int32)
    n_layers = int(high.max()) + 1

    presence = zeros((n_regions, n_layers), dtype=bool)
    for r in range(n_regions):
        in_region = labels == r
        if not in_region.any():
            continue
        diff = zeros(n_layers + 1, dtype=int32)
        add.at(diff, low[in_region], 1)
        add.at(diff, minimum(high[in_region] + 1, n_layers), -1)
        presence[r] = cumsum(diff)[:n_layers] > 0

    per_layer = presence.sum(axis=0)
    tool_changes = int(maximum(per_layer - 1, 0).sum())

    # dropping a region saves a change in every layer where it shares the
    # layer with at least one other region
    shared = per_layer >= 2
    savings = (presence & shared).sum(axis=1).astype(int32)
    layers_touched = presence.sum(axis=1).astype(int32)

    total_area = float(regions.areas.sum()) or 1.0
    area_fractions = regions.areas / total_area

    return PrintCost(layer_height, n_layers, layers_touched, tool_changes,
                     savings, area_fractions)


def describe(cost):
    """One line summarising the whole print."""
    return ("%d layers at %.2f mm, roughly %d tool changes"
            % (cost.n_layers, cost.layer_height, cost.tool_changes))
