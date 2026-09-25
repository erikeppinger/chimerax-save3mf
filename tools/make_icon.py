"""Draw the bundle icon: ".3mf" in a typewriter face, one colour per glyph.

Colours come from the Okabe-Ito palette, designed to stay distinguishable
under the common forms of colour vision deficiency - which is the point, given
the bundle is about assigning colours people have to tell apart.

    python make_icon.py [outdir]

Writes PNGs at several sizes plus an SVG.
"""

import os
import sys

# Okabe & Ito (2008), "Color Universal Design". Four chosen for contrast
# against white and against each other: blue, vermillion, bluish green,
# reddish purple. Yellow and sky blue are omitted as too light on white.
GLYPHS = [
    (".", "#0072B2"),   # blue
    ("3", "#D55E00"),   # vermillion
    ("m", "#009E73"),   # bluish green
    ("f", "#CC79A7"),   # reddish purple
]

SIZES = (512, 256, 128, 64)
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\consolab.ttf",     # Consolas Bold
    r"C:\Windows\Fonts\courbd.ttf",       # Courier New Bold
    r"C:\Windows\Fonts\lucon.ttf",        # Lucida Console
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
]


def find_font():
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    raise SystemExit("no monospace font found; add one to FONT_CANDIDATES")


def draw_png(path, size, font_path):
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    text = "".join(g for g, _ in GLYPHS)
    # ".3mf" is wide and short, so width is what limits the size; constraining
    # the height as well would leave the glyphs small in a mostly empty square
    target = size * 0.92

    # Size and position on the *ink* box, not the font metrics: ".3mf" in a
    # monospace face has a tall ascent nothing reaches and a wide advance for
    # the dot, so centring on metrics leaves the glyphs low and off to one
    # side.
    points = size
    while points > 4:
        font = ImageFont.truetype(font_path, points)
        box = draw.textbbox((0, 0), text, font=font)
        if (box[2] - box[0]) <= target:
            break
        points -= 2
    font = ImageFont.truetype(font_path, points)

    box = draw.textbbox((0, 0), text, font=font)
    origin_x = (size - (box[2] - box[0])) / 2.0 - box[0]
    origin_y = (size - (box[3] - box[1])) / 2.0 - box[1]

    x = origin_x
    for glyph, colour in GLYPHS:
        draw.text((x, origin_y), glyph, font=font, fill=colour)
        x += draw.textlength(glyph, font=font)

    img.save(path)
    return points


def crop_to_ink(src, dst, pad_fraction=0.08):
    """A wordmark version: the square icon trimmed to its glyphs.

    Useful anywhere the icon sits in running text or a page header, where the
    empty band above and below a wide, short wordmark looks like a mistake.
    """
    from PIL import Image
    img = Image.open(src)
    box = img.getbbox()
    if box is None:
        return
    pad = int(round((box[3] - box[1]) * pad_fraction))
    box = (max(box[0] - pad, 0), max(box[1] - pad, 0),
           min(box[2] + pad, img.width), min(box[3] + pad, img.height))
    img.crop(box).save(dst)
    return box


def write_svg(path, font_size=170):
    """Same design as a scalable file, for anywhere a PNG will not do."""
    glyphs = "".join(
        '<tspan fill="%s">%s</tspan>' % (colour, glyph)
        for glyph, colour in GLYPHS)
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512"
     viewBox="0 0 512 512">
  <title>.3mf</title>
  <text x="256" y="256" text-anchor="middle" dominant-baseline="central"
        font-family="Consolas, 'Courier New', monospace" font-weight="bold"
        font-size="%d" xml:space="preserve">%s</text>
</svg>
""" % (font_size, glyphs)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs",
        "icon")
    os.makedirs(outdir, exist_ok=True)
    font_path = find_font()
    print("font:", font_path)
    for size in SIZES:
        path = os.path.join(outdir, "save3mf-%d.png" % size)
        points = draw_png(path, size, font_path)
        print("wrote %s (%d pt)" % (path, points))
    wordmark = os.path.join(outdir, "save3mf-wordmark.png")
    crop_to_ink(os.path.join(outdir, "save3mf-512.png"), wordmark)
    print("wrote", wordmark)
    svg = os.path.join(outdir, "save3mf.svg")
    write_svg(svg)
    print("wrote", svg)


if __name__ == "__main__":
    main()
