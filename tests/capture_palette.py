"""Capture what '3mf palette' puts in the ChimeraX log as standalone HTML, so
the swatch rendering can be checked without opening the GUI.

    & "C:\\Program Files\\ChimeraX 1.12\\bin\\ChimeraX-console.exe" --nogui --exit --silent --script tests/capture_palette.py
"""

import os

from chimerax.core.commands import run

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out",
                   "palette.html")

SCENES = [
    ("Colored by chain (4 chains)",
     ["open 1a3n", "delete solvent", "hide atoms", "surface", "color bychain"]),
    ("Rainbow by B-factor (continuous)",
     ["close", "open 1a3n", "delete solvent", "hide atoms", "surface",
      "color byattribute bfactor palette rainbow"]),
    ("Rainbow merged to 5 parts",
     []),   # same scene, different command
]

blocks = []
logger = session.logger            # noqa: F821 - provided by ChimeraX
original_info = logger.info


def capture(msg, *args, **kw):
    captured.append((msg, kw.get("is_html", False)))
    return original_info(msg, *args, **kw)


for title, commands in SCENES:
    for c in commands:
        run(session, c)            # noqa: F821
    captured = []
    logger.info = capture
    run(session, "3mf palette maxColors 5" if "merged" in title
        else "3mf palette")        # noqa: F821
    logger.info = original_info
    body = "\n".join(m if is_html else "<p>%s</p>" % m for m, is_html in captured)
    blocks.append("<h2>%s</h2>\n%s" % (title, body))

html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>3mf palette output</title></head>
<body style="font-family:system-ui,sans-serif;max-width:60em;margin:2em auto">
<h1>What '3mf palette' writes to the ChimeraX log</h1>
%s
</body></html>""" % "\n<hr>\n".join(blocks)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)
print("wrote", OUT)
