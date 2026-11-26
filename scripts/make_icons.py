"""Draw the home-screen icons in icons/ (run once; needs Pillow).

Full-bleed square with the mountain inside the maskable safe zone, so the
same PNGs work as "any" and "maskable" icons and as the iOS touch icon.
"""
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "icons"
PEAKS = [(2, 28), (12, 8), (18, 18), (22, 12), (30, 28)]  # same path as the favicon
RACES = {"kepler": "#257de0", "grunt": "#0a7a1e"}
SIZES = [180, 192, 512]


def draw(bg, size):
    big = size * 4
    im = Image.new("RGB", (big, big), bg)
    # Mountain spans 28/32 of its box; scale so it sits within ~62% of the icon.
    scale = big * 0.62 / 28
    ox = (big - 28 * scale) / 2 - 2 * scale
    oy = (big - 20 * scale) / 2 - 8 * scale + big * 0.03
    pts = [(ox + x * scale, oy + y * scale) for x, y in PEAKS]
    ImageDraw.Draw(im).polygon(pts, fill="white")
    return im.resize((size, size), Image.LANCZOS)


OUT.mkdir(exist_ok=True)
for race, bg in RACES.items():
    for s in SIZES:
        draw(bg, s).save(OUT / f"{race}-{s}.png", optimize=True)
