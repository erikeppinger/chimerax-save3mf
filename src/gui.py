# vim: set expandtab shiftwidth=4 softtabstop=4:
"""Options shown in ChimeraX's Save dialog when 3MF is the chosen format.

Only the options worth clicking are here.  Everything else stays available on
the save command itself.
"""

from Qt.QtCore import Qt
from Qt.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QPushButton, QRadioButton, QSpinBox, QVBoxLayout,
)

# label, flavor argument
SLICERS = [
    ("PrusaSlicer", "prusa"),
    ("Bambu Studio / OrcaSlicer", "bambu"),
    ("Other (geometry and colors only)", "generic"),
]

DEFAULT_SIZE_MM = 80.0
DEFAULT_MAX_COLORS = 5


class SaveOptionsWidget(QFrame):

    def __init__(self, session):
        super().__init__()
        self.session = session

        layout = QVBoxLayout()
        layout.setContentsMargins(2, 0, 0, 0)
        layout.setSpacing(6)
        self.setLayout(layout)

        layout.addLayout(self._size_section())
        layout.addLayout(self._color_section())
        layout.addLayout(self._slicer_section())

        self.check = QCheckBox("Report printability problems")
        self.check.setChecked(True)
        self.check.setToolTip("Warn about disconnected pieces, non-watertight "
                              "meshes and geometry sealed inside other geometry")
        layout.addWidget(self.check, alignment=Qt.AlignLeft)

        self._update_enabled()

    # ---------------------------------------------------------------- layout

    def _size_section(self):
        grid = QGridLayout()
        grid.setSpacing(4)
        grid.addWidget(QLabel("Size:"), 0, 0, alignment=Qt.AlignLeft)

        self.size_mode = QButtonGroup(self)
        self.longest_edge = QRadioButton("Longest edge")
        self.by_scale = QRadioButton("Scale")
        self.size_mode.addButton(self.longest_edge)
        self.size_mode.addButton(self.by_scale)
        self.longest_edge.setChecked(True)
        self.longest_edge.toggled.connect(self._update_enabled)

        self.size_value = QDoubleSpinBox()
        self.size_value.setRange(1.0, 10000.0)
        self.size_value.setValue(DEFAULT_SIZE_MM)
        self.size_value.setSuffix(" mm")

        self.scale_value = QDoubleSpinBox()
        self.scale_value.setRange(0.001, 1000.0)
        self.scale_value.setDecimals(3)
        self.scale_value.setValue(1.0)
        self.scale_value.setSuffix(" mm per \N{ANGSTROM SIGN}")

        grid.addWidget(self.longest_edge, 0, 1, alignment=Qt.AlignLeft)
        grid.addWidget(self.size_value, 0, 2, alignment=Qt.AlignLeft)
        grid.addWidget(self.by_scale, 1, 1, alignment=Qt.AlignLeft)
        grid.addWidget(self.scale_value, 1, 2, alignment=Qt.AlignLeft)
        grid.setColumnStretch(3, 1)
        return grid

    def _color_section(self):
        box = QVBoxLayout()
        box.setSpacing(3)

        self.colors = QCheckBox("Split colors into printable parts")
        self.colors.setChecked(True)
        self.colors.setToolTip("Each color becomes a part the slicer can "
                               "assign to its own filament")
        self.colors.toggled.connect(self._update_enabled)
        box.addWidget(self.colors, alignment=Qt.AlignLeft)

        merge_row = QHBoxLayout()
        merge_row.setSpacing(4)
        self.merge = QCheckBox("Merge to at most")
        self.merge.setToolTip("Continuous coloring (rainbow, by B-factor) can "
                              "produce hundreds of parts")
        self.merge.toggled.connect(self._update_enabled)
        self.merge_count = QSpinBox()
        self.merge_count.setRange(2, 999)
        self.merge_count.setValue(DEFAULT_MAX_COLORS)
        merge_row.addSpacing(18)
        merge_row.addWidget(self.merge)
        merge_row.addWidget(self.merge_count)
        merge_row.addWidget(QLabel("parts"))
        merge_row.addStretch(1)
        box.addLayout(merge_row)

        preview_row = QHBoxLayout()
        preview = QPushButton("Preview colors\N{HORIZONTAL ELLIPSIS}")
        preview.setToolTip("Show the colors in the log, and what merging "
                           "them would cost")
        preview.clicked.connect(self._preview)
        preview_row.addSpacing(18)
        preview_row.addWidget(preview)
        preview_row.addStretch(1)
        box.addLayout(preview_row)
        return box

    def _slicer_section(self):
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QLabel("Slicer:"), alignment=Qt.AlignLeft)
        self.slicer = QComboBox()
        for label, _ in SLICERS:
            self.slicer.addItem(label)
        self.slicer.setToolTip(
            "These slicers store multi-part models in incompatible ways, so "
            "the file has to be written for one of them")
        row.addWidget(self.slicer)
        row.addStretch(1)
        return row

    # --------------------------------------------------------------- behaviour

    def _update_enabled(self, *args):
        self.size_value.setEnabled(self.longest_edge.isChecked())
        self.scale_value.setEnabled(self.by_scale.isChecked())
        splitting = self.colors.isChecked()
        self.merge.setEnabled(splitting)
        self.merge_count.setEnabled(splitting and self.merge.isChecked())

    def _preview(self):
        from chimerax.core.commands import run
        command = "3mf palette"
        if self.colors.isChecked() and self.merge.isChecked():
            command += " maxColors %d" % self.merge_count.value()
        run(self.session, command)

    # ------------------------------------------------------------ the result

    def options_string(self):
        args = []
        if self.longest_edge.isChecked():
            args.append("size %g" % self.size_value.value())
        elif self.scale_value.value() != 1.0:
            args.append("scale %g" % self.scale_value.value())

        if not self.colors.isChecked():
            args.append("colors false")
        elif self.merge.isChecked():
            args.append("maxColors %d" % self.merge_count.value())

        flavor = SLICERS[self.slicer.currentIndex()][1]
        if flavor != "prusa":
            args.append("flavor %s" % flavor)

        if not self.check.isChecked():
            args.append("check false")

        return " ".join(args)
