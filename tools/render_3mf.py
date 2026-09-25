"""Render a 3MF to a PNG, using whatever colour the file actually carries.

Written to check full-colour output without depending on a third-party
viewer: if the colours are in the file, they appear here. Reads per-vertex
colour from the Materials-extension colorgroup (pid/p1/p2/p3) and interpolates
it across each triangle, with simple shading so the shape is legible.

    python render_3mf.py file.3mf [out.png] [--size 700]
"""

import sys
import zipfile
import xml.etree.ElementTree as ET

import numpy as np

CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
MAT = "{http://schemas.microsoft.com/3dmanufacturing/material/2015/02}"


def read(path):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("3D/3dmodel.model"))
    res = root.find(CORE + "resources")

    palettes = {}
    for cg in res.findall(MAT + "colorgroup"):
        cols = []
        for c in cg.findall(MAT + "color"):
            h = c.get("color").lstrip("#")
            cols.append([int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)])
        palettes[cg.get("id")] = np.array(cols, dtype=float) / 255.0
    for bm in res.findall(CORE + "basematerials"):
        cols = []
        for b in bm.findall(CORE + "base"):
            h = b.get("displaycolor").lstrip("#")
            cols.append([int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)])
        palettes[bm.get("id")] = np.array(cols, dtype=float) / 255.0

    obj = res.find(CORE + "object")
    mesh = obj.find(CORE + "mesh")
    verts = np.array([[float(v.get("x")), float(v.get("y")), float(v.get("z"))]
                      for v in mesh.find(CORE + "vertices")], dtype=float)

    tris, cols = [], []
    default = np.array([0.8, 0.8, 0.82])
    for t in mesh.find(CORE + "triangles"):
        tris.append([int(t.get("v1")), int(t.get("v2")), int(t.get("v3"))])
        pid = t.get("pid") or obj.get("pid")
        pal = palettes.get(pid)
        if pal is None:
            cols.append([default] * 3)
            continue
        p1 = t.get("p1")
        if p1 is None:
            cols.append([default] * 3)
            continue
        i1 = int(p1)
        i2 = int(t.get("p2", p1))
        i3 = int(t.get("p3", p1))
        cols.append([pal[i1], pal[i2], pal[i3]])
    return verts, np.array(tris, dtype=np.int64), np.array(cols, dtype=float)


def render(verts, tris, cols, size=700):
    # look down -z, y up, with a slight tilt so depth reads
    angle = np.radians(20.0)
    rot = np.array([[1, 0, 0],
                    [0, np.cos(angle), -np.sin(angle)],
                    [0, np.sin(angle), np.cos(angle)]])
    p = verts @ rot.T

    lo, hi = p.min(0), p.max(0)
    span = (hi - lo).max()
    scale = (size - 40) / span
    x = (p[:, 0] - lo[0]) * scale + 20
    y = (size - 20) - (p[:, 1] - lo[1]) * scale
    z = p[:, 2]

    img = np.ones((size, size, 3), dtype=float)
    zbuf = np.full((size, size), -np.inf)

    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    normals = np.cross(verts[b] - verts[a], verts[c] - verts[a])
    n = np.linalg.norm(normals, axis=1)
    normals = normals / np.where(n[:, None] == 0, 1, n[:, None])
    light = np.array([0.3, 0.5, 0.8])
    light = light / np.linalg.norm(light)
    shade = 0.45 + 0.55 * np.clip(normals @ light, 0, 1)

    # painter's order, far to near, with a z-buffer for safety
    order = np.argsort(z[tris].mean(axis=1))
    for t in order:
        i, j, k = tris[t]
        xs = np.array([x[i], x[j], x[k]])
        ys = np.array([y[i], y[j], y[k]])
        x0, x1 = int(max(xs.min(), 0)), int(min(xs.max() + 1, size))
        y0, y1 = int(max(ys.min(), 0)), int(min(ys.max() + 1, size))
        if x1 <= x0 or y1 <= y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5,
                             np.arange(y0, y1) + 0.5)
        d = ((ys[1] - ys[2]) * (xs[0] - xs[2])
             + (xs[2] - xs[1]) * (ys[0] - ys[2]))
        if abs(d) < 1e-12:
            continue
        w0 = ((ys[1] - ys[2]) * (gx - xs[2])
              + (xs[2] - xs[1]) * (gy - ys[2])) / d
        w1 = ((ys[2] - ys[0]) * (gx - xs[2])
              + (xs[0] - xs[2]) * (gy - ys[2])) / d
        w2 = 1.0 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            continue
        depth = w0 * z[i] + w1 * z[j] + w2 * z[k]
        sub = zbuf[y0:y1, x0:x1]
        win = inside & (depth > sub)
        if not win.any():
            continue
        colour = (w0[..., None] * cols[t, 0]
                  + w1[..., None] * cols[t, 1]
                  + w2[..., None] * cols[t, 2]) * shade[t]
        region = img[y0:y1, x0:x1]
        region[win] = np.clip(colour[win], 0, 1)
        sub[win] = depth[win]
    return (img * 255).astype(np.uint8)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    size = 700
    for a in sys.argv[1:]:
        if a.startswith("--size"):
            size = int(a.split("=")[-1])
    src = args[0]
    out = args[1] if len(args) > 1 else src.rsplit(".", 1)[0] + ".png"

    verts, tris, cols = read(src)
    print("%d triangles, %d distinct vertex colours"
          % (len(tris), len(np.unique(cols.reshape(-1, 3), axis=0))))
    img = render(verts, tris, cols, size)
    try:
        from PIL import Image
        Image.fromarray(img).save(out)
    except ImportError:
        out = out.rsplit(".", 1)[0] + ".ppm"
        with open(out, "wb") as f:
            f.write(b"P6\n%d %d\n255\n" % (img.shape[1], img.shape[0]))
            f.write(img.tobytes())
    print("wrote", out)


if __name__ == "__main__":
    main()
