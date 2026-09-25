# vim: set expandtab shiftwidth=4 softtabstop=4:
"""The '3mf palette' command: see what colour parts an export would produce,
and what merging them down would cost, before writing any file.
"""

from chimerax.core.commands import CmdDesc, FloatArg, ModelsArg, PositiveIntArg
from chimerax.core.errors import UserError

# part counts worth offering; filtered to those below the distinct count
LADDER = (2, 3, 4, 5, 6, 8, 12, 16, 24, 32)


def palette(session, models=None, max_colors=None, size=None, scale=None,
            layer_height=None, tools=None):
    from . import colors as color_module, printcost, scene

    geometry = scene.collect_geometry(session, models)
    if geometry.triangle_count == 0:
        raise UserError("Nothing to inspect: no displayed surface geometry. "
                        "Show a molecular surface, cartoon or atoms first.")
    geometry = scene.weld_vertices(geometry)
    # print cost depends on how tall the print is, so scale it the way the
    # export would
    geometry, _ = scene.place_for_printing(
        geometry, scale=1.0 if scale is None else scale, size=size)

    regions = color_module.build_regions(geometry, max_colors=max_colors)
    logger = session.logger
    tool_count = printcost.DEFAULT_TOOL_COUNT if tools is None else tools
    cost = printcost.estimate(
        geometry, regions,
        layer_height=(printcost.DEFAULT_LAYER_HEIGHT if layer_height is None
                      else layer_height),
        tools=tool_count)

    if max_colors is not None:
        logger.info("%d distinct colors merged into %d parts "
                    "(mean color shift \N{GREEK CAPITAL LETTER DELTA}E %.1f, %s)"
                    % (regions.distinct, regions.count, regions.delta_e,
                       color_module.describe_delta_e(regions.delta_e)))
        logger.info(printcost.describe(cost))
        _log_palette_with_cost(session, regions, cost)
        _warn_costly(session, regions, cost)
        logger.info("Export it with:  save file.3mf maxColors %d" % max_colors)
        return

    logger.info("%d distinct color%s across %d triangles; %s"
                % (regions.distinct, "" if regions.distinct == 1 else "s",
                   geometry.triangle_count, printcost.describe(cost)))

    if regions.distinct <= max(LADDER):
        _log_palette_with_cost(session, regions, cost)
        _warn_costly(session, regions, cost)
    if regions.distinct <= 2:
        return

    candidates = [k for k in LADDER if k < regions.distinct]
    _, merges = color_module.preview_merges(geometry, candidates)
    if not merges:
        return

    # cost every candidate from one pass over the distinct colours
    unique_colors, color_of_triangle = color_module.color_index(geometry)
    presence = printcost.layer_presence(
        geometry, color_of_triangle, len(unique_colors), cost.layer_height)

    rows = []
    for k, delta_e, reps, cluster_of_color in merges:
        hex_colors = [_hex(c) for c in reps]
        extruder = printcost.effective_extruders(cluster_of_color, tool_count)
        changes = printcost.changes_from_presence(
            printcost.regroup_presence(presence, extruder,
                                       int(extruder.max()) + 1))
        rows.append(
            '<tr><td align="right">&nbsp;merge to %d&nbsp;</td>'
            '<td>%s</td>'
            '<td>&nbsp;\N{GREEK CAPITAL LETTER DELTA}E %.1f</td>'
            '<td>&nbsp;%s</td>'
            '<td align="right">&nbsp;+%s changing tools</td></tr>'
            % (k, color_module.swatch_strip(hex_colors), delta_e,
               color_module.describe_delta_e(delta_e),
               printcost.seconds_to_text(
                   changes * printcost.SECONDS_PER_TOOL_CHANGE)))
    rows.append(
        '<tr><td align="right">&nbsp;no merge&nbsp;</td><td></td>'
        '<td>&nbsp;\N{GREEK CAPITAL LETTER DELTA}E 0.0</td>'
        '<td>&nbsp;%d parts, exactly as colored</td>'
        '<td align="right">&nbsp;+%s changing tools</td></tr>'
        % (regions.distinct, cost.time_text()))

    logger.info('<table style="border-spacing:0">%s</table>' % "".join(rows),
                is_html=True)
    logger.info("Export with:  save file.3mf maxColors N")


def _log_palette_with_cost(session, regions, cost):
    """The palette table, with what each part costs in tool changes."""
    from .colors import _escape
    total_area = float(regions.areas.sum()) or 1.0
    rows = []
    for i, (name, hex_color) in enumerate(zip(regions.names,
                                              regions.hex_colors(alpha=False))):
        share = 100.0 * regions.areas[i] / total_area
        change_share = (100.0 * cost.savings[i] / cost.tool_changes
                        if cost.tool_changes else 0.0)
        note = ""
        if (share < 100 * 2e-2 and change_share >= 5.0):
            note = ('<td>&nbsp;<b>costly</b>: %s of tool changes for %.1f%% '
                    'of the model</td>' % (cost.saving_text(i), share))
        rows.append(
            '<tr><td style="background:%s;width:2em">&nbsp;</td>'
            '<td>&nbsp;part %d</td><td>&nbsp;%s</td>'
            '<td align="right">&nbsp;%.1f%%</td>'
            '<td align="right">&nbsp;%d layers</td>'
            '<td align="right">&nbsp;+%s</td>%s</tr>'
            % (hex_color, i + 1, _escape(name), share,
               cost.layers_touched[i], cost.saving_text(i), note))
    session.logger.info('<table style="border-spacing:0">%s</table>'
                        % "".join(rows), is_html=True)


def _warn_costly(session, regions, cost):
    """Say plainly when a part buys very little for a lot of print time."""
    from . import log
    for r, area_fraction, change_share in cost.costly_regions():
        log.warn(
            session,
            "Part %d (%s) is %.1f%% of the model but costs about %s of tool "
            "changes, because it appears in %d of %d layers. Dropping it with "
            "%s would get that time back."
            % (r + 1, log.escape(regions.names[r]), 100.0 * area_fraction,
               cost.saving_text(r), cost.layers_touched[r], cost.n_layers,
               log.help_link(text="maxColors %d"
                             % max(1, regions.count - 1))),
            html=True)


def _hex(rgb):
    return "#%02X%02X%02X" % (int(rgb[0]), int(rgb[1]), int(rgb[2]))


palette_desc = CmdDesc(
    keyword=[('models', ModelsArg), ('max_colors', PositiveIntArg),
             ('size', FloatArg), ('scale', FloatArg),
             ('layer_height', FloatArg), ('tools', PositiveIntArg)],
    synopsis="Preview the color parts a 3MF export would produce",
)


def register_command(command_name, logger):
    from chimerax.core.commands import register
    if command_name == "3mf palette":
        register(command_name, palette_desc, palette, logger=logger)
