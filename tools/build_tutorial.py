"""Build the in-ChimeraX help page from the printing tutorial's Markdown.

docs/printing-protein-models.md is the one source: GitHub renders it, and
contributions are made to it. This script turns it into
docs/commands/3mf-printing.html, which ships with the bundle:

  * ```chimerax code blocks become one cxcmd: link per line, so each command
    runs when clicked in the ChimeraX help viewer
  * links to repository files are rewritten to where they live in the help
    (or to GitHub); an unknown relative link is an error, so the page cannot
    quietly ship a dead link

Run with ChimeraX's Python (it has the markdown package):

    & "C:\\Program Files\\ChimeraX 1.12\\bin\\python.exe" tools\\build_tutorial.py
    & "C:\\Program Files\\ChimeraX 1.12\\bin\\python.exe" tools\\build_tutorial.py --check

--check rebuilds in memory and fails if the HTML in the repository differs,
which tests/run_all.ps1 uses to catch an edit to one without the other.
"""

import html
import os
import re
import sys

import markdown

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SOURCE = os.path.join(ROOT, "docs", "printing-protein-models.md")
TARGET = os.path.join(ROOT, "docs", "commands", "3mf-printing.html")
REPO = "https://github.com/erikeppinger/chimerax-save3mf/blob/main/"

# relative links in the Markdown, and where they point from the help page
LINKS = {
    "../README.md": "3mf.html",
    "../README.md#smoothness": "3mf.html#smoothness",
    "../examples/1ubq-print.cxc": REPO + "examples/1ubq-print.cxc",
    "../CONTRIBUTING.md": REPO + "CONTRIBUTING.md",
}

PAGE = """<html>
<head>
<title>%(title)s</title>
<!--
  GENERATED from docs/printing-protein-models.md by tools/build_tutorial.py.
  Edit the Markdown, then rerun the script; tests/run_all.ps1 fails if the
  two disagree. Styling is inline because a bundle's help page cannot reach
  the ChimeraX docs stylesheet.
-->
<style type="text/css">
body { font-family: Verdana, Arial, sans-serif; font-size: 90%%;
       line-height: 1.5; margin: 1.5em auto; padding: 0 2em;
       max-width: 62em; color: #222; }
h1 { font-size: 1.5em; margin-bottom: 0.2em; }
h2 { font-size: 1.15em; margin-top: 1.8em; margin-bottom: 0.4em;
     border-bottom: 1px solid #ddd; padding-bottom: 0.2em; }
h3 { font-size: 1em; margin-top: 1.3em; margin-bottom: 0.3em; }
code, pre { font-family: Consolas, "Courier New", monospace; }
pre { background: #f5f5f5; border: 1px solid #e0e0e0; padding: 0.6em 0.8em;
      overflow-x: auto; font-size: 95%%; }
table { border-collapse: collapse; margin: 0.8em 0; }
th { background: #eee; text-align: left; }
th, td { border: 1px solid #ccc; padding: 0.35em 0.6em; vertical-align: top; }
a { color: #0645ad; text-decoration: none; }
a:hover { text-decoration: underline; }
blockquote { background: #f7f7f7; border-left: 3px solid #ccc;
             margin: 0.6em 0; padding: 0.1em 0.9em; }
address { margin-top: 2.5em; font-size: 85%%; color: #666; font-style: normal; }
</style>
</head>
<body>

%(body)s

<hr>
<address>UCSF ChimeraX bundle: Save3MF &middot;
<a href="3mf.html">3MF export</a></address>
</body>
</html>
"""


def _command_block(match):
    """A ```chimerax block: each line a link that runs the command."""
    lines = []
    for line in match.group(1).rstrip("\n").split("\n"):
        command = html.unescape(line)
        lines.append('<a href="cxcmd:%s">%s</a>'
                     % (html.escape(command, quote=True), line))
    return "<pre>%s</pre>" % "\n".join(lines)


def _link(match):
    href = html.unescape(match.group(1))
    if re.match(r"^(https?:|mailto:|cxcmd:|#)", href):
        return match.group(0)
    if href not in LINKS:
        raise SystemExit("build_tutorial: no help-page target for link %r; "
                         "add it to LINKS" % href)
    return 'href="%s"' % html.escape(LINKS[href], quote=True)


def build():
    with open(SOURCE, encoding="utf-8") as f:
        text = f.read()
    body = markdown.markdown(text, extensions=["tables", "fenced_code"],
                             output_format="html")
    body = re.sub(r'<pre><code class="language-chimerax">(.*?)</code></pre>',
                  _command_block, body, flags=re.S)
    body = re.sub(r'href="([^"]*)"', _link, body)
    title = re.search(r"<h1>(.*?)</h1>", body).group(1)
    return PAGE % {"title": html.unescape(title), "body": body.strip()}


def main():
    page = build()
    if "--check" in sys.argv:
        with open(TARGET, encoding="utf-8") as f:
            current = f.read().replace("\r\n", "\n")
        if current != page:
            print("STALE: %s does not match %s; run tools/build_tutorial.py"
                  % (os.path.relpath(TARGET, ROOT), os.path.relpath(SOURCE, ROOT)))
            sys.exit(1)
        print("tutorial page up to date")
        return
    with open(TARGET, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    print("wrote", os.path.relpath(TARGET, ROOT))


main()
