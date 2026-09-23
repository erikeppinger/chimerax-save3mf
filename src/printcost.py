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

# Measured, not guessed: tools/calibrate_time.py exports the same scene at
# several colour counts, slices each, and fits print time against tool
# changes.  On an Original Prusa XL with a 0.20 mm profile the slope was 18.4
# seconds per change, with the worst point 4.1% off the fit.  Other printers
# differ - an MMU rewinds and purges far more slowly than a toolchanger - so
# this is an order-of-magnitude figure for comparing choices, not a quote.
SECONDS_PER_TOOL_CHANGE = 18.4

# Colours beyond the printer's tool count do not add tool changes: they all
# print with filament 1 (see probes/RESULTS.md, probe I).
DEFAULT_TOOL_COUNT = 5
# a region under this share of the model's area is "small"
SMALL_AREA_FRACTION = 0.02
# ...and costly if it also drives at least this share of the tool changes
COSTLY_CHANGE_FRACTION = 0.05


def effective_extruders(labels, tools=DEFAULT_TOOL_COUNT):
    """Map colour regions to the extruders a printer will really use.

    Region r is painted as extruder r+1.  A printer with fewer tools prints
    everything above its tool count with filament 1, so those regions stop
    costing tool changes - which is why print time plateaus once there are
    more colours than tools.
    """
    from numpy import where
    extruder = labels + 1
    return where(extruder > tools, 1, extruder)


def seconds_to_text(seconds):
    seconds = int(round(seconds))
    if seconds < 60:
        return "%ds" % seconds
    if seconds < 3600:
        return "%dm" % (seconds // 60)
    return "%dh %02dm" % (seconds // 3600, (seconds % 3600) // 60)


class PrintCost:

    def __init__(self, layer_height, n_layers, layers_touched, tool_changes,
                 savings, area_fractions, tools=DEFAULT_TOOL_COUNT):
        self.layer_height = layer_height
        self.n_layers = n_layers
        self.layers_touched = layers_touched      # per region
        self.tool_changes = tool_changes          # total estimate
        self.savings = savings                    # changes saved per region
        self.area_fractions = area_fractions      # per region, 0..1
        self.tools = tools

    @property
    def seconds(self):
        """Print time spent changing tools, not the whole print."""
        return self.tool_changes * SECONDS_PER_TOOL_CHANGE

    def time_text(self):
        return seconds_to_text(self.seconds)

    def saving_text(self, region):
        return seconds_to_text(self.savings[region] * SECONDS_PER_TOOL_CHANGE)

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


def estimate(geometry, regions, layer_height=DEFAULT_LAYER_HEIGHT,
             tools=DEFAULT_TOOL_COUNT):
    """Estimate the tool changes the given colour regions would cause.

    The geometry must already be scaled to millimetres, since the layer count
    depends on how tall the print is.
    """
    labels = regions.labels
    n_regions = regions.count

    if len(geometry.triangles) == 0 or layer_height <= 0:
        return PrintCost(layer_height, 0, zeros(n_regions, int32), 0,
                         zeros(n_regions, int32), zeros(n_regions), tools)

    presence = layer_presence(geometry, labels, n_regions, layer_height)
    n_layers = presence.shape[1]
    layers_touched = presence.sum(axis=1).astype(int32)

    # what the printer really does: colours beyond the tool count share
    # filament 1, so they cost nothing extra
    extruder = effective_extruders(arange(n_regions), tools)
    n_extruders = int(extruder.max()) + 1
    by_extruder = regroup_presence(presence, extruder, n_extruders)
    per_layer = by_extruder.sum(axis=0)
    tool_changes = int(maximum(per_layer - 1, 0).sum())

    # dropping a region saves a change in each layer where its extruder is
    # present only because of that region, alongside at least one other
    savings = zeros(n_regions, dtype=int32)
    shared = per_layer >= 2
    for r in range(n_regions):
        siblings = (extruder == extruder[r]) & (arange(n_regions) != r)
        alone = presence[r] & ~presence[siblings].any(axis=0) \
            if siblings.any() else presence[r]
        savings[r] = int((alone & shared).sum())

    total_area = float(regions.areas.sum()) or 1.0
    area_fractions = regions.areas / total_area

    return PrintCost(layer_height, n_layers, layers_touched, tool_changes,
                     savings, area_fractions, tools)


def describe(cost):
    """One line summarising the whole print."""
    return ("%d layers at %.2f mm, about %s spent changing tools "
            "(%d changes on a %d-tool printer)"
            % (cost.n_layers, cost.layer_height, cost.time_text(),
               cost.tool_changes, cost.tools))
