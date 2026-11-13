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
PRUSA_CONFIG = "Metadata/Slic3r_PE_model.config"
BAMBU_CONFIG = "Metadata/model_settings.config"


def write_3mf(session, path, models=None, scale=None, size=None, check=True,
              colors=True, max_colors=None, flavor="prusa", paint=True,
              smoothness=None, parts=None):
    from chimerax.core.errors import UserError
    from . import colors as color_module, printcheck, scene

    flavor = flavor.lower()
    if flavor not in FLAVORS:
        raise UserError("Unknown 3MF flavor '%s'; use one of: %s"
                        % (flavor, ", ".join(FLAVORS)))
    flavor = FLAVOR_ALIASES.get(flavor, flavor)
    if parts not in (None, "chain", "model"):
        raise UserError("parts is 'chain' or 'model', not '%s'" % parts)
    if parts and flavor == "fullcolor":
        raise UserError("parts %s needs a filament flavor (prusa or bambu); "
                        "full-colour output is one mesh" % parts)
    target = smoothness_target(smoothness)

    geometry = scene.collect_geometry(session, models, parts=parts)
    if geometry.triangle_count == 0:
        raise UserError("Nothing to save as 3MF: no displayed surface geometry. "
                        "Show a molecular surface, cartoon or atoms first.")

    before = geometry.triangle_count
    geometry = scene.weld_vertices(geometry)
    geometry, used_scale = scene.place_for_printing(
        geometry, scale=1.0 if scale is None else scale, size=size)

    depths = None
    if target is not None:
        geometry, before, depths = _smooth(session, models, geometry, before,
                                           used_scale, target, parts)

    report = printcheck.analyze(geometry)

    # Full colour is a different job from filament assignment: a full-colour
    # printer wants the colour of every vertex, not a handful of regions, so
    # none of the clustering or extruder machinery applies.
    if flavor == "fullcolor":
        model_xml, extra = _fullcolor_package(session, geometry, colors)
        _write_package(path, model_xml, extra)
        _report_fullcolor(session, path, geometry, used_scale, before, colors)
        _report_smoothness(session, depths, target)
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
        fallback = (
            "the parts per %s have meanwhile been written without colour" % parts
            if parts else
            "the model has meanwhile been split into separate parts, which "
            "leaves open edges where they meet")
        log.warn(
            session,
            "%d colors is far more than the %d a filament printer can paint. "
            "For a continuously coloured model &ndash; %s, hydrophobicity, "
            "B-factor &ndash; use %s, which keeps every colour for a "
            "full-colour printer. To print it on filament instead, reduce the "
            "colours with %s; %s."
            % (regions.count, MAX_PAINTED_EXTRUDERS,
               log.cmd_link("help mlp", "mlp"),
               log.help_link("flavors", "flavor fullcolor"),
               log.help_link(text="maxColors %d" % MAX_PAINTED_EXTRUDERS),
               fallback),
            html=True)
        painting = False
    elif parts and not paint and regions is not None:
        # parts carry colour only as painting; there is no per-colour split
        # inside a part to fall back on
        from . import log
        log.warn(session, "paint false with parts %s: the parts are written "
                          "without colour. Leave paint on to keep the colours "
                          "inside each part." % parts)

    if parts:
        model_xml, extra = _parts_package(session, geometry, regions, flavor,
                                          painting)
    elif painting:
        model_xml, extra = _painted_package(session, geometry, regions, flavor)
    elif flavor == "bambu" and regions is not None and regions.count > 1:
        model_xml, extra = _bambu_package(session, geometry, regions)
    else:
        model_xml, extra = _prusa_package(session, geometry, regions,
                                          generic=(flavor == "generic"))

    _write_package(path, model_xml, extra)

    # unpainted parts carry no colour, so there is no palette to report
    written_regions = None if parts and not painting else regions
    _report(session, path, geometry, used_scale, before, written_regions,
            flavor, painting)
    if parts:
        _report_parts(session, geometry, parts)
    _report_smoothness(session, depths, target)
    printcheck.log_report(session, report, quiet=not check)


# --------------------------------------------------------------- smoothness

def smoothness_target(smoothness):
    """Target flat depth in mm, or None when smoothing is switched off."""
    from .smoothness import DEFAULT_SMOOTHNESS
    if smoothness is None:
        return DEFAULT_SMOOTHNESS
    if isinstance(smoothness, str):
        return None                 # 'off'
    if smoothness <= 0:
        from chimerax.core.errors import UserError
        raise UserError("smoothness is the deepest flat allowed, in mm; "
                        "give a positive number, or 'off'")
    return float(smoothness)


def _smooth(session, models, geometry, before, used_scale, target, parts=None):
    """Re-collect the scene finer when its flats would show in the print.

    Says what it is about to change before doing it, since it makes the file
    larger than what is on screen would suggest.
    """
    from . import log, scene, smoothness
    depths = smoothness.measure(geometry)
    p = smoothness.plan(session, depths, target)
    if not p.needed:
        return geometry, before, depths

    log.warn(
        session,
        "<b>Smoothing for print.</b> At %.3g mm/\N{ANGSTROM SIGN} the flat "
        "facets ChimeraX draws would be up to %.2f mm deep (%s), more than "
        "the %.2g mm target. Exporting with %s (about %s \N{RIGHTWARDS ARROW} "
        "%s triangles). The display is left as it is; %s exports exactly what "
        "is on screen."
        % (used_scale, depths.worst(kinds=p.changes),
           log.escape(smoothness.describe_depths(depths, kinds=p.changes)),
           target, log.escape(smoothness.describe_changes(p)),
           _thousands(p.triangles_before), _thousands(p.triangles_after),
           log.help_link("smoothness", "smoothness off")),
        html=True)

    with smoothness.Applied(session, p):
        finer = scene.collect_geometry(session, models, parts=parts)
    before = finer.triangle_count
    geometry = scene.weld_vertices(finer)
    geometry, _ = scene.place_for_printing(geometry, scale=used_scale)
    return geometry, before, smoothness.measure(geometry)


def _report_smoothness(session, depths, target):
    if depths is None or not depths.depth:
        return
    from . import log, smoothness
    adjustable = depths.worst(kinds=smoothness.ADJUSTABLE)
    if adjustable:
        session.logger.info("Flats up to %.2f mm deep on %s (target %.2g mm)"
                            % (adjustable, ", ".join(
                                smoothness.LABELS[k] for k in depths.depth
                                if k in smoothness.ADJUSTABLE), target))
    rough = depths.above(target * 1.25)
    if not rough:
        return
    fixed = [k for k in rough if k == "surfaces"]
    capped = [k for k in rough if k != "surfaces"]
    text = ("Still above the %.2g mm smoothness target: %s."
            % (target, smoothness.describe_depths(depths, kinds=rough)))
    if capped:
        text += (" Finer tessellation stopped at the limit that keeps the "
                 "file manageable; a smaller model needs less.")
    if fixed:
        text += " " + smoothness.surface_advice(fixed)
    log.warn(session, text)


def _thousands(n):
    return "{:,}".format(int(n))


# ------------------------------------------------------------------ helpers

def _sort_by_region(geometry, regions):
    """Reorder triangles so each part, and each region within a part, is one
    contiguous run.

    PrusaSlicer identifies parts by triangle ranges, so the runs have to be
    contiguous; it costs nothing for the other flavours. Parts (chains or
    models) come first when the geometry has them, colour regions second.
    """
    from numpy import argsort, lexsort
    groups = geometry.triangle_groups
    if regions is None and groups is None:
        return geometry
    if groups is None:
        order = argsort(regions.labels, kind='stable')
    elif regions is None:
        order = argsort(groups, kind='stable')
    else:
        order = lexsort((regions.labels, groups))     # last key sorts first
    if regions is not None:
        regions.labels = regions.labels[order]
    return geometry.with_arrays(geometry.vertices, geometry.triangles[order],
                                order)


def _group_ranges(geometry):
    """(first triangle, last triangle) per part, after sorting."""
    from numpy import bincount
    counts = bincount(geometry.triangle_groups,
                      minlength=len(geometry.group_names))
    ranges, start = [], 0
    for count in counts:
        ranges.append((start, start + int(count) - 1))
        start += int(count)
    return ranges


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


def _model_header(session, out, prusa_painting=False):
    from chimerax import app_dirs
    from time import strftime
    extra_ns = ' xmlns:slic3rpe="%s"' % SLIC3RPE_NS if prusa_painting else ""
    out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    out.write('<model unit="millimeter" xml:lang="en-US" xmlns="%s" '
              'xmlns:m="%s"%s>\n' % (CORE_NS, MAT_NS, extra_ns))
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
    _close_mesh_object(out)
    _write_build(out)
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
           else ", %d degenerate or doubled triangles removed"
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

    name = _scene_name(session)
    out = io.StringIO()
    _model_header(session, out, prusa_painting=prusa)
    out.write(' <resources>\n')
    _write_color_resources(out, regions)
    _open_mesh_object(out, WRAPPER_OBJECT_ID, name, geometry.vertices)
    _write_painted_triangles(out, geometry.triangles, regions.labels, attribute)
    _close_mesh_object(out)
    _write_build(out)

    if prusa:
        extra = {PRUSA_CONFIG: _prusa_volumes_config(
            name, [(0, len(geometry.triangles) - 1, name, None)])}
    else:
        extra = {BAMBU_CONFIG: _bambu_parts_config(
            name, [(WRAPPER_OBJECT_ID, name, None)])}
    return out.getvalue(), extra


# ------------------------------------------------------ one part per chain

def _parts_package(session, geometry, regions, flavor, painting):
    """One object holding one part per chain (or model), painted inside.

    Separate objects would be simpler, but every slicer drops each object
    onto the bed and Bambu/Orca also rearrange them, which takes a complex
    apart. Parts of one object keep their places (probes J and K, see
    probes/RESULTS.md). Each slicer family reads only its own layout, as with
    the colour parts: triangle-range volumes for PrusaSlicer, components for
    Bambu Studio and OrcaSlicer.
    """
    prusa = (flavor == "prusa")
    attribute = "slic3rpe:mmu_segmentation" if prusa else "paint_color"
    labels = regions.labels if painting else None
    ranges = [(i, first, last)
              for i, (first, last) in enumerate(_group_ranges(geometry))
              if last >= first]
    names = [_xml_escape(n) for n in geometry.group_names]
    name = _scene_name(session)

    out = io.StringIO()
    _model_header(session, out, prusa_painting=prusa and painting)
    out.write(' <resources>\n')
    _write_color_resources(out, regions if painting else None)

    def triangles(rows, first, last):
        if labels is None:
            _write_triangles(out, rows, None)
        else:
            _write_painted_triangles(out, rows, labels[first:last + 1],
                                     attribute)

    if prusa:
        _open_mesh_object(out, WRAPPER_OBJECT_ID, name, geometry.vertices)
        for _, first, last in ranges:
            triangles(geometry.triangles[first:last + 1], first, last)
        _close_mesh_object(out)
        extra = {PRUSA_CONFIG: _prusa_volumes_config(
            name, [(first, last, names[i], None) for i, first, last in ranges])}
    else:
        ids = [FIRST_PART_OBJECT_ID + i for i, _, _ in ranges]
        for object_id, (i, first, last) in zip(ids, ranges):
            vertices, rows = _submesh(geometry, first, last)
            _open_mesh_object(out, object_id, names[i], vertices)
            triangles(rows, first, last)
            _close_mesh_object(out)
        _write_components_object(out, name, ids)
        extra = {BAMBU_CONFIG: _bambu_parts_config(
            name, [(object_id, names[i], None)
                   for object_id, (i, _, _) in zip(ids, ranges)])}
    _write_build(out)
    return out.getvalue(), extra


def _report_parts(session, geometry, parts):
    from numpy import bincount
    counts = bincount(geometry.triangle_groups,
                      minlength=len(geometry.group_names))
    listed = ["%s (%s triangles)" % (n, _thousands(c))
              for n, c in zip(geometry.group_names, counts) if c]
    session.logger.info("%d part%s, one per %s, kept in place: %s"
                        % (len(listed), "" if len(listed) == 1 else "s",
                           parts, ", ".join(listed)))


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
    name = _scene_name(session)
    out = io.StringIO()
    _model_header(session, out)
    out.write(' <resources>\n')
    _write_color_resources(out, regions)
    _open_mesh_object(out, WRAPPER_OBJECT_ID, name, geometry.vertices)
    _write_triangles(out, geometry.triangles,
                     None if regions is None else regions.labels)
    _close_mesh_object(out)
    _write_build(out)

    extra = {}
    if regions is not None and regions.count > 1 and not generic:
        extra[PRUSA_CONFIG] = _prusa_volumes_config(
            name, [(first, last, _xml_escape(regions.names[i]), i + 1)
                   for i, (first, last) in enumerate(_region_ranges(regions))])
    return out.getvalue(), extra


def _prusa_volumes_config(object_name, volumes):
    """PrusaSlicer's model config: the volumes of the one object, each a
    triangle range. volumes holds (first triangle, last triangle, name,
    extruder or None); names are already XML-escaped."""
    out = io.StringIO()
    out.write('<?xml version="1.0" encoding="UTF-8"?>\n<config>\n')
    out.write(' <object id="%d">\n' % WRAPPER_OBJECT_ID)
    out.write('  <metadata type="object" key="name" value="%s"/>\n'
              % object_name)
    for first, last, name, extruder in volumes:
        out.write('  <volume firstid="%d" lastid="%d">\n' % (first, last))
        out.write('   <metadata type="volume" key="name" value="%s"/>\n' % name)
        if extruder is not None:
            out.write('   <metadata type="volume" key="extruder" value="%d"/>\n'
                      % extruder)
        out.write('   <mesh edges_fixed="0" degenerate_facets="0"'
                  ' facets_removed="0" facets_reversed="0" backwards_edges="0"/>\n')
        out.write('  </volume>\n')
    out.write(' </object>\n</config>\n')
    return out.getvalue()


# ------------------------------------------------------------ bambu flavour

def _bambu_package(session, geometry, regions):
    """One component object per region, parts declared in the Bambu config."""
    name = _scene_name(session)
    out = io.StringIO()
    _model_header(session, out)
    out.write(' <resources>\n')
    _write_color_resources(out, regions)

    ranges = _region_ranges(regions)
    ids = [FIRST_PART_OBJECT_ID + i for i in range(len(ranges))]
    names = [_xml_escape(n) for n in regions.names]
    for i, (first, last) in enumerate(ranges):
        vertices, triangles = _submesh(geometry, first, last)
        _open_mesh_object(out, ids[i], names[i], vertices,
                          ' pid="%d" pindex="%d"' % (BASEMATERIALS_ID, i))
        _write_triangles(out, triangles, None)
        _close_mesh_object(out)
    _write_components_object(out, name, ids)
    _write_build(out)

    return out.getvalue(), {BAMBU_CONFIG: _bambu_parts_config(
        name, [(ids[i], names[i], i + 1) for i in range(len(ranges))])}


def _bambu_parts_config(object_name, parts):
    """Bambu Studio's and OrcaSlicer's model config: the parts of the one
    object. parts holds (object id, name, extruder or None); names are
    already XML-escaped."""
    out = io.StringIO()
    out.write('<?xml version="1.0" encoding="UTF-8"?>\n<config>\n')
    out.write('  <object id="%d">\n' % WRAPPER_OBJECT_ID)
    out.write('   <metadata key="name" value="%s"/>\n' % object_name)
    out.write('   <metadata key="extruder" value="1"/>\n')
    for object_id, name, extruder in parts:
        out.write('    <part id="%d" subtype="normal_part">\n' % object_id)
        out.write('     <metadata key="name" value="%s"/>\n' % name)
        if extruder is not None:
            out.write('     <metadata key="extruder" value="%d"/>\n' % extruder)
        out.write('     <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n')
        out.write('    </part>\n')
    out.write('  </object>\n</config>\n')
    return out.getvalue()


# ------------------------------------------------------- shared XML pieces

def _open_mesh_object(out, object_id, name, vertices, attributes=""):
    """Start an object holding a mesh; the caller writes the triangles."""
    out.write('  <object id="%d" type="model" name="%s"%s>\n'
              % (object_id, name, attributes))
    out.write('   <mesh>\n')
    out.write('    <vertices>\n')
    _write_vertices(out, vertices)
    out.write('    </vertices>\n')
    out.write('    <triangles>\n')


def _close_mesh_object(out):
    out.write('    </triangles>\n')
    out.write('   </mesh>\n')
    out.write('  </object>\n')


def _write_components_object(out, name, object_ids):
    """The one object of the build, assembled from other objects in place."""
    out.write('  <object id="%d" type="model" name="%s">\n'
              % (WRAPPER_OBJECT_ID, name))
    out.write('   <components>\n')
    for object_id in object_ids:
        out.write('    <component objectid="%d"/>\n' % object_id)
    out.write('   </components>\n')
    out.write('  </object>\n')


def _write_build(out):
    """Close the resources and put the one object on the plate, unmoved."""
    out.write(' </resources>\n')
    out.write(' <build>\n')
    out.write('  <item objectid="%d" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>\n'
              % WRAPPER_OBJECT_ID)
    out.write(' </build>\n')
    out.write('</model>\n')


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
           "" if welded == 0 else
           ", %d degenerate or doubled triangles removed" % welded))

    if regions is None:
        return

    if regions.merged:
        session.logger.info(
            "%d distinct colors merged into %d printable colors "
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
            "%d colors is a lot to assign by hand in a slicer. Run %s to see "
            "what merging them would cost, then export with %s."
            % (regions.count, log.cmd_link("3mf palette"),
               log.help_link(text="maxColors N")),
            html=True)
        warned = True

    if warned:
        log.help_hint(session)
