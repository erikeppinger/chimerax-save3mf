"""Capture the warning log as HTML, to check the help links render.

    ChimeraX-console.exe --nogui --exit --silent --script tests/capture_warnings.py
"""

import os

from chimerax.core.commands import run

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out",
                   "warnings.html")

SCENES = [
    ("Continuous colouring saved for a filament printer",
     ["close", "open 1ubq", "mlp protein", "hide atoms", "hide cartoon"],
     "save %s/noise3.3mf"),
    ("Atoms left inside a density map",
     ["close", "open 1ubq", "hide ribbon", "show atoms", "hide solvent",
      "surface close", "molmap protein 5"],
     "save %s/hidden.3mf"),
]

captured = []
logger = session.logger            # noqa: F821
orig_info, orig_warn = logger.info, logger.warning


def grab_info(msg, *a, **kw):
    captured.append((msg, kw.get("is_html", False), "info"))
    return orig_info(msg, *a, **kw)


def grab_warn(msg, *a, **kw):
    captured.append((msg, kw.get("is_html", False), "warning"))
    return orig_warn(msg, *a, **kw)


blocks = []
outdir = os.path.dirname(OUT).replace("\\", "/")
for title, commands, save in SCENES:
    for c in commands:
        run(session, c)            # noqa: F821
    captured = []
    logger.info, logger.warning = grab_info, grab_warn
    run(session, save % outdir)    # noqa: F821
    logger.info, logger.warning = orig_info, orig_warn
    body = []
    for msg, is_html, kind in captured:
        text = msg if is_html else "<p>%s</p>" % msg
        style = ("background:#fff6d6;border-left:3px solid #e0a800;"
                 "padding:0.4em 0.7em;margin:0.4em 0" if kind == "warning"
                 else "margin:0.4em 0")
        body.append('<div style="%s">%s</div>' % (style, text))
    blocks.append("<h2>%s</h2>%s" % (title, "".join(body)))

html = """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Save3MF log output</title></head>
<body style="font-family:system-ui,sans-serif;max-width:60em;margin:2em auto">
<h1>What Save3MF writes to the ChimeraX log</h1>%s</body></html>""" % "".join(blocks)

with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)
print("wrote", OUT)
