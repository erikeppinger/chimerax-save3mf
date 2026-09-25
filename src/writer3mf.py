# vim: set expandtab shiftwidth=4 softtabstop=4:
"""Write a 3MF package.

3MF is an OPC (zip) container holding [Content_Types].xml, _rels/.rels and
3D/3dmodel.model.

Colour regions have to be expressed differently for different slicers, and no
single layout satisfies all of them - see probes/RESULTS.md for the
experiments behind this:

  flavor "prusa"  one object holding one merged mesh, regions declared as
                  triangle ranges in Metadata/Slic3r_PE_model.config.  The
                  only thing PrusaSlicer honours.

  flavor "bambu"  one component object per region inside a wrapper object,
                  with parts declared in Metadata/model_settings.config.
                  What Bambu Studio and OrcaSlicer honour.

Both flavours also carry the standards-compliant colour tags (m:colorgroup and
basematerials).  Neither Prusa nor Bambu reads them on import, but generic 3MF
viewers do and they cost almost nothing.
"""

import io
import zipfile

CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
MAT_NS = "http://schemas.microsoft.com/3dmanufacturing/material/2015/02"
SLIC3RPE_NS = "http://schemas.slic3r.org/3mf/2017/06"

# Per-triangle extruder painting.  Splitting a mesh into one volume per colour
# leaves every patch edged with open boundaries, which slicers flag and then
# try to repair; painting keeps the mesh whole and assigns extruders per
# triangle instead.  Index N is extruder N; index 0 means unpainted.  The code
# for extruder N is MMU_CODES[N], verified by slicing probe H (see
# probes/RESULTS.md) - the published tables are off by one.
MMU_CODES = ["0", "4", "8", "0C", "1C", "2C", "3C", "4C", "5C", "6C", "7C",
             "8C", "9C", "AC", "BC", "CC"]
MAX_PAINTED_EXTRUDERS = len(MMU_CODES) - 1
# more tools than this and the printer is unusual; past it, warn that surplus
# colours are silently printed with filament 1
COMMON_TOOL_COUNT = 5

FLAVORS = ("prusa", "bambu", "fullcolor", "generic")

# "generic" was the 0.1.x name for what is really full-colour output
FLAVOR_ALIASES = {"generic": "fullcolor"}

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
 <Default Extension="config" ContentType="application/vnd.ms-printing.printticket+xml"/>
</Types>
"""

RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
"""

COLORGROUP_ID = 2
BASEMATERIALS_ID = 5
WRAPPER_OBJECT_ID = 1
FIRST_PART_OBJECT_ID = 10


def write_3mf(session, path, models=None, scale=None, size=None, check=True,
              colors=True, max_colors=None, flavor="prusa", paint=True):
    from chimerax.core.errors import UserError
    from . import colors as color_module, printcheck, scene

    flavor = flavor.lower()
    if flavor not in FLAVORS:
        raise UserError("Unknown 3MF flavor '%s'; use one of: %s"
                        % (flavor, ", ".join(FLAVORS)))
    flavor = FLAVOR_ALIASES.get(flavor, flavor)

    geometry = scene.collect_geometry(session, models)
    if geometry.triangle_count == 0:
        raise UserError("Nothing to save as 3MF: no displayed surface geometry. "
                        "Show a molecular surface, cartoon or atoms first.")

    before = geometry.triangle_count
    geometry = scene.weld_vertices(geometry)
    geometry, used_scale = scene.place_for_printing(
        geometry, scale=1.0 if scale is None else scale, size=size)

    report = printcheck.analyze(geometry)

    # Full colour is a different job from filament assignment: a full-colour
    # printer wants the colour of every vertex, not a handful of regions, so
    # none of the clustering or extruder machinery applies.
    if flavor == "fullcolor":
        model_xml, extra = _fullcolor_package(session, geometry, colors)
        _write_package(path, model_xml, extra)
        _report_fullcolor(session, path, geometry, used_scale, before, colors)
        printcheck.log_report(session, report, quiet=not check)
        return

    regions = None
    if colors:
        regions = color_module.build_regions(geometry, max_colors=max_colors)
        geometry = _sort_by_region(geometry, regions)

    painting = paint and flavor in ("prusa", "bambu") and regions is not None
    if painting and regions.count > MAX_PAINTED_EXTRUDERS:
        from . import log
        # A count this high almost always means continuous colouring, which a
        # filament printer cannot reproduce at all - so name the mode that can
        # before explaining the filament fallback.
        log.warn(
            session,
            "%d colors is far more than the %d a filament printer can paint. "
            "For a continuously coloured model &ndash; %s, hydrophobicity, "
            "B-factor &ndash; use %s, which keeps every colour for a "
            "full-colour printer. To print it on filament instead, reduce the "
            "colours with %s; the model has meanwhile been split into separate "
            "parts, which leaves open edges where they meet."
            % (regions.count, MAX_PAINTED_EXTRUDERS,
               log.cmd_link("help mlp", "mlp"),
               log.help_link("flavors", "flavor fullcolor"),
               log.help_link(text="maxColors %d" % MAX_PAINTED_EXTRUDERS)),
            html=True)
        painting = False

    if painting:
        model_xml, extra = _painted_package(session, geometry, regions, flavor)
    elif flavor == "bambu" and regions is not None and regions.count > 1:
        model_xml, extra = _bambu_package(session, geometry, regions)
    else:
        model_xml, extra = _prusa_package(session, geometry, regions,
                                          generic=(flavor == "generic"))

    _write_package(path, model_xml, extra)

    _report(session, path, geometry, used_scale, before, regions, flavor,
            painting)
    printcheck.log_report(session, report, quiet=not check)


# ------------------------------------------------------------------ helpers

def _sort_by_region(geometry, regions):
    """Reorder triangles so each region is one contiguous run.

    PrusaSlicer identifies parts by triangle ranges, so the runs have to be
    contiguous; it costs nothing for the other flavours.
    """
    from numpy import argsort
    from .scene import SceneGeometry
    order = argsort(regions.labels, kind='stable')
    regions.labels = regions.labels[order]
    sources = geometry.triangle_sources
    return SceneGeometry(
        geometry.vertices,
        geometry.triangles[order],
        geometry.triangle_colors[order],
        geometry.sources,
        None if sources is None else sources[order],
    )


def _region_ranges(regions):
    """(first triangle, last triangle) per region, after sorting."""
    ranges = []
    start = 0
    for count in regions.counts:
        ranges.append((start, start + int(count) - 1))
        start += int(count)
    return ranges


def _write_package(path, model_xml, extra_files=None):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("3D/3dmodel.model", model_xml)
        for name, data in (extra_files or {}).items():
            z.writestr(name, data)


def _model_header(session, out):
    from chimerax import app_dirs
    from time import strftime
    out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    out.write('<model unit="millimeter" xml:lang="en-US" xmlns="%s" xmlns:m="%s">\n'
              % (CORE_NS, MAT_NS))
    out.write(' <metadata name="Application">%s %s</metadata>\n'
              % (app_dirs.appname, app_dirs.version))
    out.write(' <metadata name="Title">%s</metadata>\n' % _scene_name(session))
    out.write(' <metadata name="CreationDate">%s</metadata>\n'
              % strftime("%Y-%m-%d"))


def _write_color_resources(out, regions):
    """basematerials and m:colorgroup, one entry per region."""
    if regions is None:
        return
    out.write('  <basematerials id="%d">\n' % BASEMATERIALS_ID)
    for name, hex_color in zip(regions.names, regions.hex_colors()):
        out.write('   <base name="%s" displaycolor="%s"/>\n'
                  % (_xml_escape(name), hex_color))
    out.write('  </basematerials>\n')
    out.write('  <m:colorgroup id="%d">\n' % COLORGROUP_ID)
    for hex_color in regions.hex_colors():
        out.write('   <m:color color="%s"/>\n' % hex_color)
    out.write('  </m:colorgroup>\n')


# ------------------------------------------------------- full-colour flavour

def _fullcolor_package(session, geometry, colors=True):
    """One mesh carrying a colour at every vertex.

    This is what a full-colour printer (inkjet, binder jet, PolyJet) and a 3MF
    viewer want: colour interpolated across each triangle rather than a few
    flat regions. Written with the Materials extension colorgroup, which is
    the standard place for vertex colour in 3MF.
    """
    from numpy import savetxt, column_stack, unique

    vertex_colors = geometry.vertex_colors if colors else None
    out = io.StringIO()
    _model_header(session, out)
    out.write(' <resources>\n')

    color_index = None
    if vertex_colors is not None and len(vertex_colors):
        palette, color_index = unique(vertex_colors[:, :3], axis=0,
                                      return_inverse=True)
        color_index = color_index.ravel()
        out.write('  <m:colorgroup id="%d">\n' % COLORGROUP_ID)
        for rgb in palette:
            out.write('   <m:color color="#%02X%02X%02XFF"/>\n'
                      % (int(rgb[0]), int(rgb[1]), int(rgb[2])))
        out.write('  </m:colorgroup>\n')
        # a default at object level as well: some readers only look there
        obj_attrs = ' pid="%d" pindex="0"' % COLORGROUP_ID
    else:
        obj_attrs = ''

    out.write('  <object id="%d" type="model" name="%s"%s>\n'
              % (WRAPPER_OBJECT_ID, _scene_name(session), obj_attrs))
    out.write('   <mesh>\n')
    out.write('    <vertices>\n')
    _write_vertices(out, geometry.vertices)
    out.write('    </vertices>\n')
    out.write('    <triangles>\n')
    if color_index is None:
        _write_triangles(out, geometry.triangles, None)
    else:
        rows = column_stack((geometry.triangles,
                             color_index[geometry.triangles]))
        savetxt(out, rows,
                fmt='     <triangle v1="%d" v2="%d" v3="%d" '
                    'pid="' + str(COLORGROUP_ID) + '" p1="%d" p2="%d" p3="%d"/>')
    out.write('    </triangles>\n')
    out.write('   </mesh>\n')
    out.write('  </object>\n')
    out.write(' </resources>\n')
    out.write(' <build>\n')
    out.write('  <item objectid="%d" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>\n'
              % WRAPPER_OBJECT_ID)
    out.write(' </build>\n')
    out.write('</model>\n')
    return out.getvalue(), {}


def _report_fullcolor(session, path, geometry, used_scale, before, colors):
    import os
    from numpy import unique
    low, high = geometry.bounds()
    span = high - low
    session.logger.info(
        "Saved %s: %d triangles, %d vertices, %.1f x %.1f x %.1f mm "
        "(scale %.4f mm/\N{ANGSTROM SIGN}), %.1f MB%s"
        % (os.path.basename(path), geometry.triangle_count,
           geometry.vertex_count, span[0], span[1], span[2], used_scale,
           os.path.getsize(path) / (1024.0 * 1024.0),
           "" if before == geometry.triangle_count
           else ", %d degenerate triangles removed"
                % (before - geometry.triangle_count)))
    if colors and geometry.vertex_colors is not None:
        distinct = len(unique(geometry.vertex_colors[:, :3], axis=0))
        session.logger.info(
            "Full colour: %d distinct vertex colours written, interpolated "
            "across each triangle. For full-colour printers (inkjet, binder "
            "jet, PolyJet) and 3MF viewers; filament printers ignore this and "
            "print one colour." % distinct)
    else:
        session.logger.info("Geometry only, no colour.")


# --------------------------------------------------------- painted flavour

def _painted_package(session, geometry, regions, flavor):
    """One watertight mesh with an extruder painted onto each triangle.

    This is what a slicer's own multi-material painting produces, so the mesh
    keeps its topology: no split parts, no open edges, nothing for the slicer
    to repair.
    """
    prusa = (flavor == "prusa")
    attribute = "slic3rpe:mmu_segmentation" if prusa else "paint_color"

    out = io.StringIO()
    from chimerax import app_dirs
    from time import strftime
    out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    extra_ns = ' xmlns:slic3rpe="%s"' % SLIC3RPE_NS if prusa else ""
    out.write('<model unit="millimeter" xml:lang="en-US" xmlns="%s" '
              'xmlns:m="%s"%s>\n' % (CORE_NS, MAT_NS, extra_ns))
    out.write(' <metadata name="Application">%s %s</metadata>\n'
              % (app_dirs.appname, app_dirs.version))
    out.write(' <metadata name="Title">%s</metadata>\n' % _scene_name(session))
    out.write(' <metadata name="CreationDate">%s</metadata>\n'
              % strftime("%Y-%m-%d"))
    out.write(' <resources>\n')
    _write_color_resources(out, regions)
    out.write('  <object id="%d" type="model" name="%s">\n'
              % (WRAPPER_OBJECT_ID, _scene_name(session)))
    out.write('   <mesh>\n')
    out.write('    <vertices>\n')
    _write_vertices(out, geometry.vertices)
    out.write('    </vertices>\n')
    out.write('    <triangles>\n')
    _write_painted_triangles(out, geometry.triangles, regions.labels, attribute)
    out.write('    </triangles>\n')
    out.write('   </mesh>\n')
    out.write('  </object>\n')
    out.write(' </resources>\n')
    out.write(' <build>\n')
    out.write('  <item objectid="%d" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>\n'
              % WRAPPER_OBJECT_ID)
    out.write(' </build>\n')
    out.write('</model>\n')

    name = _scene_name(session)
    if prusa:
        config = (
            '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n'
            ' <object id="%d">\n'
            '  <metadata type="object" key="name" value="%s"/>\n'
            '  <volume firstid="0" lastid="%d">\n'
            '   <metadata type="volume" key="name" value="%s"/>\n'
            '   <mesh edges_fixed="0" degenerate_facets="0" facets_removed="0"'
            ' facets_reversed="0" backwards_edges="0"/>\n'
            "  </volume>\n </object>\n</config>\n"
            % (WRAPPER_OBJECT_ID, name, len(geometry.triangles) - 1, name))
        extra = {"Metadata/Slic3r_PE_model.config": config}
    else:
        config = (
            '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n'
            '  <object id="%d">\n'
            '   <metadata key="name" value="%s"/>\n'
            '   <metadata key="extruder" value="1"/>\n'
            '    <part id="%d" subtype="normal_part">\n'
            '     <metadata key="name" value="%s"/>\n'
            '     <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
            "    </part>\n  </object>\n</config>\n"
            % (WRAPPER_OBJECT_ID, name, WRAPPER_OBJECT_ID, name))
        extra = {"Metadata/model_settings.config": config}
    return out.getvalue(), extra


def _write_painted_triangles(out, triangles, labels, attribute):
    """Triangles carrying a per-triangle extruder code."""
    from numpy import savetxt
    rows = triangles
    codes = [MMU_CODES[min(int(label) + 1, MAX_PAINTED_EXTRUDERS)]
             for label in labels]
    # savetxt cannot mix numbers and strings, so write one run per code;
    # triangles are already sorted by region, so this is one call per region
    start = 0
    n = len(rows)
    while start < n:
        end = start + 1
        while end < n and codes[end] == codes[start]:
            end += 1
        savetxt(out, rows[start:end],
                fmt='     <triangle v1="%d" v2="%d" v3="%d" '
                    + attribute + '="' + codes[start] + '"/>')
        start = end


# ------------------------------------------------------------ prusa flavour

def _prusa_package(session, geometry, regions, generic=False):
    """One object, one mesh, regions as triangle ranges in the Prusa config."""
    out = io.StringIO()
    _model_header(session, out)
    out.write(' <resources>\n')
    _write_color_resources(out, regions)
    out.write('  <object id="%d" type="model" name="%s">\n'
              % (WRAPPER_OBJECT_ID, _scene_name(session)))
    out.write('   <mesh>\n')
    out.write('    <vertices>\n')
    _write_vertices(out, geometry.vertices)
    out.write('    </vertices>\n')
    out.write('    <triangles>\n')
    _write_triangles(out, geometry.triangles,
                     None if regions is None else regions.labels)
    out.write('    </triangles>\n')
    out.write('   </mesh>\n')
    out.write('  </object>\n')
    out.write(' </resources>\n')
    out.write(' <build>\n')
    out.write('  <item objectid="%d" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>\n'
              % WRAPPER_OBJECT_ID)
    out.write(' </build>\n')
    out.write('</model>\n')

    extra = {}
    if regions is not None and regions.count > 1 and not generic:
        extra["Metadata/Slic3r_PE_model.config"] = _prusa_config(
            session, regions)
    return out.getvalue(), extra


def _prusa_config(session, regions):
    out = io.StringIO()
    out.write('<?xml version="1.0" encoding="UTF-8"?>\n<config>\n')
    out.write(' <object id="%d">\n' % WRAPPER_OBJECT_ID)
    out.write('  <metadata type="object" key="name" value="%s"/>\n'
              % _xml_escape(_scene_name(session)))
    for i, (first, last) in enumerate(_region_ranges(regions)):
        out.write('  <volume firstid="%d" lastid="%d">\n' % (first, last))
        out.write('   <metadata type="volume" key="name" value="%s"/>\n'
                  % _xml_escape(regions.names[i]))
        out.write('   <metadata type="volume" key="extruder" value="%d"/>\n'
                  % (i + 1))
        out.write('   <mesh edges_fixed="0" degenerate_facets="0"'
                  ' facets_removed="0" facets_reversed="0" backwards_edges="0"/>\n')
        out.write('  </volume>\n')
    out.write(' </object>\n</config>\n')
    return out.getvalue()


# ------------------------------------------------------------ bambu flavour

def _bambu_package(session, geometry, regions):
    """One component object per region, parts declared in the Bambu config."""
    out = io.StringIO()
    _model_header(session, out)
    out.write(' <resources>\n')
    _write_color_resources(out, regions)

    ranges = _region_ranges(regions)
    for i, (first, last) in enumerate(ranges):
        vertices, triangles = _submesh(geometry, first, last)
        out.write('  <object id="%d" type="model" name="%s" pid="%d" pindex="%d">\n'
                  % (FIRST_PART_OBJECT_ID + i, _xml_escape(regions.names[i]),
                     BASEMATERIALS_ID, i))
        out.write('   <mesh>\n')
        out.write('    <vertices>\n')
        _write_vertices(out, vertices)
        out.write('    </vertices>\n')
        out.write('    <triangles>\n')
        _write_triangles(out, triangles, None)
        out.write('    </triangles>\n')
        out.write('   </mesh>\n')
        out.write('  </object>\n')

    out.write('  <object id="%d" type="model" name="%s">\n'
              % (WRAPPER_OBJECT_ID, _scene_name(session)))
    out.write('   <components>\n')
    for i in range(len(ranges)):
        out.write('    <component objectid="%d"/>\n' % (FIRST_PART_OBJECT_ID + i))
    out.write('   </components>\n')
    out.write('  </object>\n')
    out.write(' </resources>\n')
    out.write(' <build>\n')
    out.write('  <item objectid="%d" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>\n'
              % WRAPPER_OBJECT_ID)
    out.write(' </build>\n')
    out.write('</model>\n')

    return out.getvalue(), {
        "Metadata/model_settings.config": _bambu_config(session, regions)
    }


def _bambu_config(session, regions):
    out = io.StringIO()
    out.write('<?xml version="1.0" encoding="UTF-8"?>\n<config>\n')
    out.write('  <object id="%d">\n' % WRAPPER_OBJECT_ID)
    out.write('   <metadata key="name" value="%s"/>\n'
              % _xml_escape(_scene_name(session)))
    out.write('   <metadata key="extruder" value="1"/>\n')
    for i, name in enumerate(regions.names):
        out.write('    <part id="%d" subtype="normal_part">\n'
                  % (FIRST_PART_OBJECT_ID + i))
        out.write('     <metadata key="name" value="%s"/>\n' % _xml_escape(name))
        out.write('     <metadata key="extruder" value="%d"/>\n' % (i + 1))
        out.write('     <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n')
        out.write('    </part>\n')
    out.write('  </object>\n</config>\n')
    return out.getvalue()


def _submesh(geometry, first, last):
    """Vertices and reindexed triangles for one contiguous triangle range."""
    from numpy import unique, zeros
    triangles = geometry.triangles[first:last + 1]
    used = unique(triangles)
    remap = zeros(len(geometry.vertices), dtype=triangles.dtype)
    remap[used] = range(len(used))
    return geometry.vertices[used], remap[triangles]


# ------------------------------------------------------------------ output

def _write_vertices(out, vertices):
    from numpy import savetxt
    savetxt(out, vertices, fmt='     <vertex x="%.4f" y="%.4f" z="%.4f"/>')


def _write_triangles(out, triangles, labels=None):
    from numpy import column_stack, savetxt
    if labels is None:
        savetxt(out, triangles, fmt='     <triangle v1="%d" v2="%d" v3="%d"/>')
    else:
        rows = column_stack((triangles, labels))
        savetxt(out, rows, fmt='     <triangle v1="%d" v2="%d" v3="%d" '
                               'pid="' + str(COLORGROUP_ID) + '" p1="%d"/>')


def _scene_name(session):
    names = [m.name for m in session.models.list() if getattr(m, 'display', True)]
    return _xml_escape(names[0] if names else "ChimeraX scene")


def _xml_escape(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
                     .replace(">", "&gt;").replace('"', "&quot;"))


def _report(session, path, geometry, used_scale, triangles_before_weld,
            regions, flavor, painting=False):
    import os
    low, high = geometry.bounds()
    span = high - low
    size_mb = os.path.getsize(path) / (1024.0 * 1024.0)
    welded = triangles_before_weld - geometry.triangle_count
    session.logger.info(
        "Saved %s: %d triangles, %d vertices, %.1f x %.1f x %.1f mm "
        "(scale %.4f mm/\N{ANGSTROM SIGN}), %.1f MB%s"
        % (os.path.basename(path), geometry.triangle_count, geometry.vertex_count,
           span[0], span[1], span[2], used_scale, size_mb,
           "" if welded == 0 else ", %d degenerate triangles removed" % welded))

    if regions is None:
        return

    if regions.merged:
        session.logger.info(
            "%d distinct colors merged into %d printable parts "
            "(mean color shift \N{GREEK CAPITAL LETTER DELTA}E %.1f), "
            "flavor %s" % (regions.distinct, regions.count, regions.delta_e, flavor))
    else:
        session.logger.info("%d color region%s, flavor %s"
                            % (regions.count, "" if regions.count == 1 else "s",
                               flavor))
    from .colors import MAX_REGIONS_BEFORE_WARNING, log_palette
    # the export report is a summary; '3mf palette' is where detail belongs
    log_palette(session, regions.names, regions.hex_colors(alpha=False),
                regions.counts, regions.areas, limit=12)

    from . import log
    warned = False
    if painting and regions.count > COMMON_TOOL_COUNT:
        log.warn(
            session,
            "Painted as extruders 1-%d. A printer with fewer tools prints "
            "every surplus colour with filament 1 and says nothing about it: "
            "on a %d-tool printer, colours %d-%d here would all come out as "
            "filament 1. Use %s to match your printer."
            % (regions.count, COMMON_TOOL_COUNT, COMMON_TOOL_COUNT + 1,
               regions.count, log.help_link(text="maxColors N")),
            html=True)
        warned = True

    if regions.count > MAX_REGIONS_BEFORE_WARNING:
        log.warn(
            session,
            "%d parts is a lot to assign by hand in a slicer. Run %s to see "
            "what merging them would cost, then export with %s."
            % (regions.count, log.cmd_link("3mf palette"),
               log.help_link(text="maxColors N")),
            html=True)
        warned = True

    if warned:
        log.help_hint(session)
