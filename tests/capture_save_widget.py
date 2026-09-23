"""Build the Save-dialog options widget offscreen, check the save-command
arguments it produces, and render it to a PNG.

Runs without a display and without opening the ChimeraX GUI:

    $env:QT_QPA_PLATFORM = "offscreen"
    & "C:\\Program Files\\ChimeraX 1.12\\bin\\ChimeraX-console.exe" --nogui --exit --silent --script tests/capture_save_widget.py
"""

import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")

from Qt.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from chimerax.save3mf.gui import SaveOptionsWidget

w = SaveOptionsWidget(session)          # noqa: F821 - provided by ChimeraX
w.adjustSize()

cases = []


def record(label):
    cases.append((label, w.options_string()))


record("defaults")

w.merge.setChecked(True)
w.merge_count.setValue(5)
record("merge to 5 parts")

w.slicer.setCurrentIndex(1)
record("+ Bambu/Orca flavor")

w.by_scale.setChecked(True)
w.scale_value.setValue(2.5)
record("+ scale instead of size")

w.colors.setChecked(False)
w.check.setChecked(False)
record("no colors, no check")

# back to something representative for the screenshot
w.colors.setChecked(True)
w.check.setChecked(True)
w.longest_edge.setChecked(True)
w.slicer.setCurrentIndex(0)
w.merge.setChecked(True)

print("\nsave command arguments produced by the widget")
print("-" * 60)
for label, args in cases:
    print("  %-26s save x.3mf %s" % (label + ":", args))
print("-" * 60)

os.makedirs(OUT, exist_ok=True)
png = os.path.join(OUT, "save_options.png")
w.grab().save(png)
print("wrote", png, os.path.getsize(png), "bytes")
