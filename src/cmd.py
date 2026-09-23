# vim: set expandtab shiftwidth=4 softtabstop=4:
"""The '3mf palette' command: see what colour parts an export would produce,
and what merging them down would cost, before writing any file.
"""

from chimerax.core.commands import CmdDesc, ModelsArg, PositiveIntArg
from chimerax.core.errors import UserError

# part counts worth offering; filtered to those below the distinct count
LADDER = (2, 3, 4, 5, 6, 8, 12, 16, 24, 32)


def palette(session, models=None, max_colors=None):
    from . import colors as color_module, scene

    geometry = scene.collect_geometry(session, models)
    if geometry.triangle_count == 0:
        raise UserError("Nothing to inspect: no displayed surface geometry. "
                        "Show a molecular surface, cartoon or atoms first.")
    geometry = scene.weld_vertices(geometry)

    regions = color_module.build_regions(geometry, max_colors=max_colors)
    logger = session.logger

    if max_colors is not None:
        logger.info("%d distinct colors merged into %d parts "
                    "(mean color shift \N{GREEK CAPITAL LETTER DELTA}E %.1f, %s)"
                    % (regions.distinct, regions.count, regions.delta_e,
                       color_module.describe_delta_e(regions.delta_e)))
        color_module.log_palette(session, regions.names,
                                 regions.hex_colors(alpha=False),
                                 regions.counts, regions.areas)
        logger.info("Export it with:  save file.3mf maxColors %d" % max_colors)
        return

    logger.info("%d distinct color%s across %d triangles"
                % (regions.distinct, "" if regions.distinct == 1 else "s",
                   geometry.triangle_count))

    if regions.distinct <= max(LADDER):
        color_module.log_palette(session, regions.names,
                                 regions.hex_colors(alpha=False),
                                 regions.counts, regions.areas)
    if regions.distinct <= 2:
        return

    candidates = [k for k in LADDER if k < regions.distinct]
    _, merges = color_module.preview_merges(geometry, candidates)
    if not merges:
        return

    rows = []
    for k, delta_e, reps in merges:
        hex_colors = [_hex(c) for c in reps]
        rows.append(
            '<tr><td align="right">&nbsp;merge to %d&nbsp;</td>'
            '<td>%s</td>'
            '<td>&nbsp;\N{GREEK CAPITAL LETTER DELTA}E %.1f</td>'
            '<td>&nbsp;%s</td></tr>'
            % (k, color_module.swatch_strip(hex_colors), delta_e,
               color_module.describe_delta_e(delta_e)))
    rows.append(
        '<tr><td align="right">&nbsp;no merge&nbsp;</td><td></td>'
        '<td>&nbsp;\N{GREEK CAPITAL LETTER DELTA}E 0.0</td>'
        '<td>&nbsp;%d parts, exactly as colored</td></tr>' % regions.distinct)

    logger.info('<table style="border-spacing:0">%s</table>' % "".join(rows),
                is_html=True)
    logger.info("Export with:  save file.3mf maxColors N")


def _hex(rgb):
    return "#%02X%02X%02X" % (int(rgb[0]), int(rgb[1]), int(rgb[2]))


palette_desc = CmdDesc(
    keyword=[('models', ModelsArg), ('max_colors', PositiveIntArg)],
    synopsis="Preview the color parts a 3MF export would produce",
)


def register_command(command_name, logger):
    from chimerax.core.commands import register
    if command_name == "3mf palette":
        register(command_name, palette_desc, palette, logger=logger)
