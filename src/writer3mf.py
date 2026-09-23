# vim: set expandtab shiftwidth=4 softtabstop=4:
"""Write a 3MF package.

3MF is an OPC (zip) container holding [Content_Types].xml, _rels/.rels and
3D/3dmodel.model.  Phase 1 writes a single object with one mesh; colour
regions and the slicer-specific part configs arrive in phase 2.
"""

import io
import zipfile

CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
MAT_NS = "http://schemas.microsoft.com/3dmanufacturing/material/2015/02"

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


def write_3mf(session, path, models=None, scale=None, size=None, check=True):
    from . import printcheck, scene

    geometry = scene.collect_geometry(session, models)
    if geometry.triangle_count == 0:
        from chimerax.core.errors import UserError
        raise UserError("Nothing to save as 3MF: no displayed surface geometry. "
                        "Show a molecular surface, cartoon or atoms first.")

    before = geometry.triangle_count
    geometry = scene.weld_vertices(geometry)
    geometry, used_scale = scene.place_for_printing(
        geometry, scale=1.0 if scale is None else scale, size=size)

    report = printcheck.analyze(geometry)

    model_xml = _model_xml(session, geometry)
    _write_package(path, model_xml)

    _report(session, path, geometry, used_scale, before)
    printcheck.log_report(session, report, quiet=not check)


def _write_package(path, model_xml, extra_files=None):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("3D/3dmodel.model", model_xml)
        for name, data in (extra_files or {}).items():
            z.writestr(name, data)


def _model_xml(session, geometry):
    from chimerax import app_dirs
    from time import strftime

    out = io.StringIO()
    out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    out.write('<model unit="millimeter" xml:lang="en-US" xmlns="%s" xmlns:m="%s">\n'
              % (CORE_NS, MAT_NS))
    out.write(' <metadata name="Application">%s %s</metadata>\n'
              % (app_dirs.appname, app_dirs.version))
    out.write(' <metadata name="CreationDate">%s</metadata>\n'
              % strftime("%Y-%m-%d"))
    out.write(' <resources>\n')
    out.write('  <object id="1" type="model" name="%s">\n' % _scene_name(session))
    out.write('   <mesh>\n')
    out.write('    <vertices>\n')
    _write_vertices(out, geometry.vertices)
    out.write('    </vertices>\n')
    out.write('    <triangles>\n')
    _write_triangles(out, geometry.triangles)
    out.write('    </triangles>\n')
    out.write('   </mesh>\n')
    out.write('  </object>\n')
    out.write(' </resources>\n')
    out.write(' <build>\n')
    out.write('  <item objectid="1" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>\n')
    out.write(' </build>\n')
    out.write('</model>\n')
    return out.getvalue()


def _write_vertices(out, vertices):
    from numpy import savetxt
    savetxt(out, vertices, fmt='     <vertex x="%.4f" y="%.4f" z="%.4f"/>')


def _write_triangles(out, triangles):
    from numpy import savetxt
    savetxt(out, triangles, fmt='     <triangle v1="%d" v2="%d" v3="%d"/>')


def _scene_name(session):
    names = [m.name for m in session.models.list() if getattr(m, 'display', True)]
    return _xml_escape(names[0] if names else "ChimeraX scene")


def _xml_escape(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


def _report(session, path, geometry, used_scale, triangles_before_weld):
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
