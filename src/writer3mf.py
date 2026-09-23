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

FLAVORS = ("prusa", "bambu", "generic")

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
              colors=True, max_colors=None, flavor="prusa"):
    from chimerax.core.errors import UserError
    from . import colors as color_module, printcheck, scene

    flavor = flavor.lower()
    if flavor not in FLAVORS:
        raise UserError("Unknown 3MF flavor '%s'; use one of: %s"
                        % (flavor, ", ".join(FLAVORS)))

    geometry = scene.collect_geometry(session, models)
    if geometry.triangle_count == 0:
        raise UserError("Nothing to save as 3MF: no displayed surface geometry. "
                        "Show a molecular surface, cartoon or atoms first.")

    before = geometry.triangle_count
    geometry = scene.weld_vertices(geometry)
    geometry, used_scale = scene.place_for_printing(
        geometry, scale=1.0 if scale is None else scale, size=size)

    report = printcheck.analyze(geometry)

    regions = None
    if colors:
        regions = color_module.build_regions(geometry, max_colors=max_colors)
        geometry = _sort_by_region(geometry, regions)

    if flavor == "bambu" and regions is not None and regions.count > 1:
        model_xml, extra = _bambu_package(session, geometry, regions)
    else:
        model_xml, extra = _prusa_package(session, geometry, regions,
                                          generic=(flavor == "generic"))

    _write_package(path, model_xml, extra)

    _report(session, path, geometry, used_scale, before, regions, flavor)
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
            regions, flavor):
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
    _log_palette(session, regions)

    from .colors import MAX_REGIONS_BEFORE_WARNING
    if regions.count > MAX_REGIONS_BEFORE_WARNING:
        session.logger.warning(
            "%d parts is a lot to assign by hand in a slicer. Use "
            "'maxColors N' to merge them down to N." % regions.count)


def _log_palette(session, regions):
    """Colour swatches in the ChimeraX log, which renders HTML."""
    rows = []
    total_area = float(regions.areas.sum()) or 1.0
    for i, (name, hex_color) in enumerate(zip(regions.names,
                                              regions.hex_colors(alpha=False))):
        rows.append(
            '<tr><td style="background:%s;width:2em">&nbsp;</td>'
            '<td>&nbsp;part %d</td><td>&nbsp;%s</td>'
            '<td align="right">&nbsp;%d triangles</td>'
            '<td align="right">&nbsp;%.1f%%</td></tr>'
            % (hex_color, i + 1, _xml_escape(name), regions.counts[i],
               100.0 * regions.areas[i] / total_area))
    session.logger.info(
        '<table style="border-spacing:0">%s</table>' % "".join(rows),
        is_html=True)
