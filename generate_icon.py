"""
Generate Lime Labs app icons from logo.png.

Produces:
  icon.icns  (macOS — via `iconutil` if available, else Pillow fallback)
  icon.ico   (Windows — via Pillow)

The brand mark is centered on a square canvas with a little padding so it reads
well as a rounded macOS app tile. Re-run any time logo.png changes.
"""

import os
import shutil
import subprocess
import sys
import tempfile

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required: pip install pillow")

# Prefer the pre-composed square brand tile (LIME over LABS on a rounded dark
# tile). Fall back to squaring the horizontal wordmark only if it's missing.
SQUARE_SRC = "app_icon.png"
SRC = "logo.png"
BG = (10, 12, 16, 255)   # #0a0c10 — matches the app window background
CANVAS = 1024
PAD_RATIO = 0.14         # margin used only for the wordmark fallback


def squared_logo():
    # Already-square brand tile: just normalise size, no extra padding/bg.
    if os.path.exists(SQUARE_SRC):
        tile = Image.open(SQUARE_SRC).convert("RGBA")
        if tile.size != (CANVAS, CANVAS):
            tile = tile.resize((CANVAS, CANVAS), Image.LANCZOS)
        return tile
    # Fallback: center the horizontal wordmark on a padded dark canvas.
    if not os.path.exists(SRC):
        sys.exit(f"Neither {SQUARE_SRC} nor {SRC} found next to generate_icon.py")
    logo = Image.open(SRC).convert("RGBA")
    canvas = Image.new("RGBA", (CANVAS, CANVAS), BG)
    inner = int(CANVAS * (1 - 2 * PAD_RATIO))
    w, h = logo.size
    scale = min(inner / w, inner / h)
    logo = logo.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    off = ((CANVAS - logo.size[0]) // 2, (CANVAS - logo.size[1]) // 2)
    canvas.paste(logo, off, logo)
    return canvas


def write_ico(img):
    sizes = [(s, s) for s in (16, 32, 48, 64, 128, 256)]
    img.save("icon.ico", sizes=sizes)
    print("  ✓ icon.ico")


def write_icns(img):
    # Preferred: macOS iconutil for a proper multi-resolution .icns
    if sys.platform == "darwin" and shutil.which("iconutil"):
        with tempfile.TemporaryDirectory() as tmp:
            iconset = os.path.join(tmp, "icon.iconset")
            os.makedirs(iconset)
            specs = [
                (16, "16x16"), (32, "16x16@2x"),
                (32, "32x32"), (64, "32x32@2x"),
                (128, "128x128"), (256, "128x128@2x"),
                (256, "256x256"), (512, "256x256@2x"),
                (512, "512x512"), (1024, "512x512@2x"),
            ]
            for px, label in specs:
                img.resize((px, px), Image.LANCZOS).save(
                    os.path.join(iconset, f"icon_{label}.png"))
            subprocess.run(["iconutil", "-c", "icns", iconset, "-o", "icon.icns"], check=True)
            print("  ✓ icon.icns (iconutil)")
            return
    # Fallback: Pillow can emit a basic .icns
    try:
        img.save("icon.icns")
        print("  ✓ icon.icns (Pillow fallback)")
    except Exception as e:
        print(f"  ⚠  couldn't write icon.icns: {e}")


def main():
    img = squared_logo()
    write_ico(img)
    write_icns(img)


if __name__ == "__main__":
    main()
