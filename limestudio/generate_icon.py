"""
Generate the Lime Studio app icon.
Produces:  app_icon.png (1024)  ·  icon.icns (macOS)  ·  icon.ico (Windows)

Motif: the Lime Studio brand mark — the lemon wedge (from the Brandmark logo,
lime-tinted) glowing on a deep-stage tile. Same mark as #ls-mark in index.html
and brand/limestudio-mark.svg; bitmap source: brand/lemon-lime.png.

Run:  python3 generate_icon.py
"""

from PIL import Image, ImageDraw, ImageFilter

S = 1024
BG1 = (10, 12, 16)      # --bg
BG2 = (24, 28, 38)      # --bg-3
LIME = (182, 255, 58)


def rounded_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def vgradient(size, top, bottom):
    g = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / (size - 1)
        g.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return g.resize((size, size))


def main():
    base = vgradient(S, BG2, BG1)

    # lemon wedge, lime-tinted, trimmed — scale to ~72% of the tile
    mark = Image.open("brand/lemon-lime.png").convert("RGBA")
    span = int(S * 0.72)
    sc = span / max(mark.size)
    mark = mark.resize((int(mark.width * sc), int(mark.height * sc)), Image.LANCZOS)
    px = (S - mark.width) // 2
    py = (S - mark.height) // 2

    # glow pass: blurred copy of the mark's alpha as a lime halo
    glow_a = Image.new("L", (S, S), 0)
    glow_a.paste(mark.getchannel("A"), (px, py))
    glow_a = glow_a.filter(ImageFilter.GaussianBlur(46))
    base = Image.composite(Image.new("RGB", (S, S), LIME), base,
                           glow_a.point(lambda v: int(v * 0.55)))

    # crisp mark on top
    base = base.convert("RGBA")
    base.alpha_composite(mark, (px, py))

    base.putalpha(rounded_mask(S, int(S * 0.225)))
    base.save("app_icon.png")
    base.save("icon.icns")
    base.save("icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote app_icon.png, icon.icns, icon.ico")


if __name__ == "__main__":
    main()
