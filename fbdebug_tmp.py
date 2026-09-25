from chimerax.core.commands import run
from chimerax.save3mf import scene as sc, printcheck as pc

run(session, "open 1ubq")
run(session, "hide ribbon")
run(session, "surface close")
run(session, "molmap protein 5")

g = sc.collect_geometry(session)
print("collected:", g.triangle_count, "triangles")
g = sc.weld_vertices(g)
print("welded:   ", g.triangle_count, "triangles,", g.vertex_count, "vertices")
g, _ = sc.place_for_printing(g, scale=1.0)

labels = pc._triangle_components(g.triangles)
n = int(labels.max()) + 1
print("printcheck shells:", n)
import numpy as np
vols = pc._shell_volumes(g.vertices, g.triangles, labels, n)
counts = np.bincount(labels, minlength=n)
for s in np.argsort(-vols):
    print("   shell %d: %d triangles, |volume| %.2f" % (s, counts[s], vols[s]))
