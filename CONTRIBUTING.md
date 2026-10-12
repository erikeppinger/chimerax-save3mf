# Contributing

## Printing tips

The tutorial [Printing protein models](docs/printing-protein-models.md) is
meant to grow with what people find on real prints.

- **Easiest:** open a
  [printing tip issue](https://github.com/erikeppinger/chimerax-save3mf/issues/new?template=printing-tip.yml)
  and describe it. Someone will check it and add it to the page.
- **Or edit the page directly:** change
  [`docs/printing-protein-models.md`](docs/printing-protein-models.md) and open
  a pull request.

What makes a tip easy to accept:

- It has worked on a print you made. Say what you printed, on which printer and
  slicer, and what difference it made.
- ChimeraX commands go in a code block marked `chimerax`, one command per line.
  Each line becomes a clickable link in the ChimeraX help, so it must run as
  written.
- If it comes from somewhere else – a guide, paper, forum post – add it to
  *Sources*.
- It goes in the section it belongs to (all models, surface, cartoon,
  space-filling and ball-and-stick, materials, slicer settings).

Edit only the Markdown. The help page inside ChimeraX,
`docs/commands/3mf-printing.html`, is generated from it; the maintainer
regenerates it when merging:

```
& "C:\Program Files\ChimeraX 1.12\bin\python.exe" tools\build_tutorial.py
```

and the test run fails if the two disagree.

## Code

Read [CLAUDE.md](CLAUDE.md) for the architecture and for the facts established
by experiment rather than documentation, and [probes/RESULTS.md](probes/RESULTS.md)
before changing how colour is written. Run the full test suite before opening a
pull request:

```
.\tests\run_all.ps1
```

Tests assert on exported files rather than internal state; a new check should
fail when the bug it guards against is put back.

This project is developed with AI assistance (Claude); see the README.
Contributions written with or without it are equally welcome.
