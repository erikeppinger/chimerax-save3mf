"""Stress run: export the scenes users actually build and check every file.

The export tests build each scene from a few hand-picked commands. This run
instead applies every printable NIH 3D preset, plus scenes put together the
way a user would, and exports each one with the common options. It needs the
GUI, because the presets do, and is started by tests/run_scenes.ps1:

    ChimeraX.exe --script tests/test_scenes.py --exit

Every export must succeed, validate, come out closed where the scene is a
closed solid, and give a printability report whose numbers make sense.

For the whole run the exporter's unfilled arrays (numpy.empty) are filled
with garbage. Code that reads an entry it never wrote then fails every time
instead of once in a hundred exports, which is how the stray-vertex crash of
0.2.5 got past the tests.

Writes tests/out/scenes/results.json and a progress log, progress.txt, in the
same folder. The structures are fetched once and then come from ChimeraX's
download cache.
"""

import json
import math
import os
import time
import traceback

import numpy as np

from chimerax.core.commands import run

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out", "scenes").replace("\\", "/")
os.makedirs(OUT, exist_ok=True)
for name in os.listdir(OUT):
    if name.endswith((".3mf", ".json", ".txt")):
        os.remove(os.path.join(OUT, name))

import sys                                                   # noqa: E402
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from validate_3mf import validate                            # noqa: E402

SIZE = 80
PROGRESS = open(OUT + "/progress.txt", "w", encoding="utf-8")
RESULTS = []


def say(text):
    PROGRESS.write(text + "\n")
    PROGRESS.flush()


# ------------------------------------------------- garbage in empty arrays

def _garbage_empty(real_empty):
    def empty(shape, dtype=float, order="C", **kw):
        a = real_empty(shape, dtype=dtype, order=order, **kw)
        kind = a.dtype.kind
        if kind == "f":
            a.fill(np.nan)
        elif kind == "i":
            a.fill(np.iinfo(a.dtype).min)
        elif kind == "u":
            a.fill(np.iinfo(a.dtype).max)
        elif kind == "b":
            a.fill(True)
        return a
    return empty


def _poison_exporter():
    """Swap numpy.empty for the garbage version in every exporter module
    that uses it. Returns the modules patched."""
    import importlib
    patched = []
    for name in ("scene", "colors", "printcheck", "writer3mf", "smoothness",
                 "printcost"):
        try:
            mod = importlib.import_module("chimerax.save3mf." + name)
        except ImportError:
            continue
        if hasattr(mod, "empty"):
            mod.empty = _garbage_empty(np.empty)
            patched.append(name)
    return patched


# ---------------------------------------------------- reports and the log

REPORTS = []


def _record_reports():
    from chimerax.save3mf import printcheck
    real = printcheck.analyze

    def analyze(geometry, *a, **kw):
        report = real(geometry, *a, **kw)
        REPORTS.append(report)
        return report
    printcheck.analyze = analyze


class _Collector:
    """Catches warnings and errors the export writes to the log."""

    def __init__(self):
        from chimerax.core.logger import PlainTextLog

        class Log(PlainTextLog):
            excludes_other_logs = False

            def log(log_self, level, msg):
                if level >= log_self.LEVEL_ERROR:
                    self.messages.append(("error", msg.strip()))
                elif level >= log_self.LEVEL_WARNING:
                    self.messages.append(("warning", msg.strip()))
                return False
        self.messages = []
        self.log = Log()
        session.logger.add_log(self.log)                     # noqa: F821

    def take(self):
        out, self.messages = self.messages, []
        return out


# ---------------------------------------------------------------- scenes

# name, commands, closed, structure kind
#   closed: the exported mesh is expected to be a closed solid
#   kind:   which structures the scene is applied to
PRESETS_STRUCTURE = [
    "ribbon by secondary structure (printable)",
    "ribbon rainbow (printable)",
    "ribbon by chain (printable)",
    "ribbon by polymer (printable)",
    "ribbon monochrome (printable)",
    "surface monochrome (printable)",
    "surface coulombic (printable)",
    "surface hydrophobicity (printable)",
    "surface by chain (printable)",
    "surface by polymer (printable)",
    "sticks (printable)",
    "sticks monochrome (printable)",
    "CPK",
    "CPK monochrome",
    "ball and stick",
    "ball and stick monochrome",
]

PRESETS_ALPHAFOLD = [
    "ribbon monochrome [AlphaFold high confidence] (printable)",
    "ribbon AlphaFold/pLDDT [all residues] (printable)",
    "ribbon AlphaFold/PAE domains [all residues] (printable)",
    "ribbon AlphaFold/pLDDT [high confidence] (printable)",
    "ribbon AlphaFold/PAE domains [high confidence] (printable)",
    "ribbon rainbow [AlphaFold high confidence] (printable)",
    "ribbon by secondary structure [AlphaFold high confidence] (printable)",
    "surface AlphaFold/pLDDT [all residues] (printable)",
    "surface AlphaFold/PAE domains [all residues] (printable)",
    "surface AlphaFold/pLDDT [high confidence] (printable)",
    "surface AlphaFold/PAE domains [high confidence] (printable)",
    "surface monochrome [AlphaFold high confidence] (printable)",
    "surface coulombic [AlphaFold high confidence] (printable)",
    "surface hydrophobicity [AlphaFold high confidence] (printable)",
]

PRESETS_VOLUME = ["volume white", "volume radial", "volume monochrome"]

# structures the structure presets run on: a small protein, a tetramer with
# hemes, and a protein-DNA complex
STRUCTURES = {
    "1ubq": ["open 1ubq"],
    "1a3n": ["open 1a3n"],
    "1aay": ["open 1aay"],
}
# "alphafold pae #1" after opening finds no PAE data; fetching with it works
ALPHAFOLD = ["alphafold fetch P69905 pae true"]
VOLUME = ["open 1ubq", "molmap #1 4", "close #1"]

# scenes put together by hand, the way a user would
HAND_SCENES = [
    ("ribbon with ligand sticks",
     ["open 1a3n", "delete solvent", "hide atoms", "cartoon",
      "show ligand atoms", "style ligand stick"], True),
    ("surface by B-factor (continuous colour)",
     ["open 1a3n", "delete solvent", "hide atoms", "hide cartoons",
      "surface", "color bfactor palette bluered"], True),
    ("surface cut by a clipping plane",
     ["open 1ubq", "delete solvent", "hide atoms", "hide cartoons",
      "surface", "view", "clip near -2 position #1"], False),
    ("ribbon with dashed hydrogen bonds",
     ["open 1ubq", "delete solvent", "hide atoms", "cartoon", "hbonds"],
     True),
    ("ribbon with struts",
     ["open 1a3n", "delete solvent", "hide atoms", "cartoon",
      "struts @ca length 7 loop 30 radius 0.8 fattenRibbon true"], True),
    ("two chains hidden",
     ["open 1a3n", "delete solvent", "hide atoms", "cartoon",
      "hide /B,D cartoons", "color bychain"], True),
    ("two structures side by side",
     ["open 1ubq", "open 1a3n", "delete solvent", "hide atoms", "cartoon",
      "move x 40 models #1", "color bypolymer"], True),
    ("spheres with hydrogens",
     ["open 1ubq", "delete solvent", "addh", "hide cartoons",
      "show atoms", "style sphere", "color byelement"], True),
    ("DNA ladder and protein ribbon",
     ["open 1aay", "delete solvent", "hide atoms", "cartoon",
      "nucleotides ladder", "color bypolymer"], True),
    ("surface and ribbon together",
     ["open 1ubq", "delete solvent", "hide atoms", "cartoon", "surface",
      "transparency 50"], True),
    ("ligand surface only",
     ["open 1a3n", "delete solvent", "hide atoms", "hide cartoons",
      "surface ligand enclose ligand"], True),
    ("ball and stick with metal-coordination pseudobonds",
     ["open 1a3n", "delete solvent", "hide cartoons", "show :HEM :<4",
      "style ball", "color byelement"], True),
]

# every scene gets the first two exports; representative ones get all
BASIC_EXPORTS = ["", "parts chain flavor bambu"]
ALL_EXPORTS = BASIC_EXPORTS + ["flavor bambu", "flavor fullcolor",
                               "paint false", "maxColors 3"]
FULL_SCENES = {
    "1a3n: ribbon by chain (printable)",
    "1a3n: surface by chain (printable)",
    "1ubq: sticks (printable)",
    "1aay: ribbon by polymer (printable)",
    "AlphaFold: surface AlphaFold/pLDDT [all residues] (printable)",
    "surface by B-factor (continuous colour)",
    "two structures side by side",
}


def scene_list():
    out = []
    for key, opener in STRUCTURES.items():
        for preset in PRESETS_STRUCTURE:
            out.append(("%s: %s" % (key, preset),
                        opener + ['preset "nih3d" "%s"' % preset], True))
    for preset in PRESETS_ALPHAFOLD:
        out.append(("AlphaFold: %s" % preset,
                    ALPHAFOLD + ['preset "nih3d" "%s"' % preset], True))
    for preset in PRESETS_VOLUME:
        out.append(("map: %s" % preset,
                    VOLUME + ['preset "nih3d" "%s"' % preset], True))
    out.extend(HAND_SCENES)
    return out


# ---------------------------------------------------------------- checks

def _finite(x):
    return x is None or math.isfinite(float(x))


def _report_problems(report):
    """Numbers in the printability report that cannot be right."""
    p = []
    if report is None:
        return ["no printability report"]
    if not report.analysed:
        return p
    sizes = list(report.size_mm)
    if not all(math.isfinite(s) for s in sizes):
        p.append("size not finite: %s" % (sizes,))
    elif abs(max(sizes) - SIZE) > 0.5:
        p.append("longest edge %.2f mm, asked for %d" % (max(sizes), SIZE))
    for attr in ("shell_count", "cavity_count", "body_count", "loose_count",
                 "open_edges", "nonmanifold_edges", "open_shells",
                 "enclosed_shells", "enclosed_triangles"):
        v = getattr(report, attr)
        if not _finite(v) or v < 0:
            p.append("%s = %s" % (attr, v))
    if report.body_count < 1:
        p.append("no bodies")
    if report.body_count > report.shell_count:
        p.append("%d bodies from %d surfaces"
                 % (report.body_count, report.shell_count))
    if report.cavity_count > report.shell_count:
        p.append("%d cavities from %d surfaces"
                 % (report.cavity_count, report.shell_count))
    t = report.thinnest_body_mm
    if t is not None and (not math.isfinite(t) or t <= 0 or t > SIZE + 0.5):
        p.append("thinnest piece %s mm" % t)
    f = report.body_fractions
    if len(f) and (not all(math.isfinite(x) for x in f)
                   or abs(sum(f) - 1.0) > 1e-3):
        p.append("body volume shares sum to %s" % sum(f))
    if not (0.0 <= report.loose_fraction <= 1.0 + 1e-9):
        p.append("loose fraction %s" % report.loose_fraction)
    return p


MERGE_WARNING = "similar colors were merged into"


def export_and_check(scene_name, closed, args, collector):
    slug = "".join(c if c.isalnum() else "_" for c in scene_name)[:70]
    tag = "".join(c if c.isalnum() else "_" for c in args) or "default"
    path = "%s/%s__%s.3mf" % (OUT, slug, tag)
    entry = {"scene": scene_name, "export": args or "(default)",
             "file": os.path.basename(path), "problems": [], "warnings": []}
    del REPORTS[:]
    collector.take()
    start = time.time()
    try:
        run(session, "save %s size %d %s" % (path, SIZE, args))   # noqa: F821
    except Exception as e:
        entry["problems"].append("export failed: %s: %s"
                                 % (type(e).__name__, str(e).strip()))
        entry["traceback"] = traceback.format_exc()
    entry["seconds"] = round(time.time() - start, 1)
    for level, msg in collector.take():
        if level == "error":
            entry["problems"].append("logged error: %s" % msg[:300])
        else:
            entry["warnings"].append(msg[:300])

    # Past 15 colours a painted export merges similar colours into 15 and
    # says so. The model must still be closed; such files are listed.
    entry["merged"] = any(MERGE_WARNING in w for w in entry["warnings"])
    if not entry["problems"]:
        if not os.path.exists(path):
            entry["problems"].append("no file written")
        else:
            r = validate(path, require_closed=closed)
            entry["problems"].extend(r.problems)
            entry["facts"] = r.facts
            report = REPORTS[-1] if REPORTS else None
            entry["problems"].extend(_report_problems(report))
            if report is not None:
                entry["report"] = {
                    "shells": report.shell_count, "bodies": report.body_count,
                    "cavities": report.cavity_count,
                    "open_edges": report.open_edges,
                    "thinnest_mm": report.thinnest_body_mm,
                    "analysed": report.analysed}
    entry["passed"] = not entry["problems"]
    RESULTS.append(entry)
    say("  %-4s %-28s %5.1fs  %s" % ("FAIL" if not entry["passed"]
                                     else "mrg" if entry["merged"] else "ok",
                                     entry["export"], entry["seconds"],
                                     "; ".join(entry["problems"])[:400]))


def _save_results():
    with open(OUT + "/results.json", "w", encoding="utf-8") as f:
        json.dump(RESULTS, f, indent=1, default=str)


def build_scene(commands):
    run(session, "close session")                            # noqa: F821
    for c in commands:
        run(session, c)                                      # noqa: F821
    # presets and style commands take effect when the next frame is drawn
    run(session, "wait 1")                                   # noqa: F821


def main():
    patched = _poison_exporter()
    _record_reports()
    collector = _Collector()
    say("garbage-filled numpy.empty in: %s" % ", ".join(patched))
    scenes = scene_list()
    only = os.environ.get("SCENES_ONLY")
    if only:
        scenes = [s for s in scenes if only.lower() in s[0].lower()]
    say("%d scenes" % len(scenes))
    t0 = time.time()
    for name, commands, closed in scenes:
        say("\n%s" % name)
        try:
            build_scene(commands)
        except Exception as e:
            RESULTS.append({"scene": name, "export": "(scene)",
                            "passed": False, "warnings": [],
                            "problems": ["scene failed: %s: %s"
                                         % (type(e).__name__,
                                            str(e).strip()[:300])]})
            say("  FAIL scene: %s" % str(e).strip()[:300])
            continue
        exports = ALL_EXPORTS if name in FULL_SCENES else BASIC_EXPORTS
        for args in exports:
            export_and_check(name, closed, args, collector)
        _save_results()       # after every scene, so a killed run keeps them

    failed = [r for r in RESULTS if not r["passed"]]
    _save_results()
    say("\nSCENES: %d exports, %d passed, %d failed, %.0f s"
        % (len(RESULTS), len(RESULTS) - len(failed), len(failed),
           time.time() - t0))


try:
    main()
except Exception:
    say("CRASHED\n" + traceback.format_exc())
finally:
    PROGRESS.close()
