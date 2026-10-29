"""Cut the app's images out of the branding sheets in branding/.

The sheets are presentation boards: the boxes below locate each piece on
them, so re-measure them if the layout of a sheet changes.

Usage: python scripts/export_brand_images.py [preview dir]
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = Path(sys.argv[1]) if len(sys.argv) > 1 else None
APP = Image.open(ROOT / "branding/app-icon@2x.png").convert("RGBA")
SHEET = Image.open(ROOT / "branding/variants@2x.png").convert("RGBA")

# Measured on the sheets (pixel boxes at @2x)
APP_TILE = (208, 208, 1232, 1232)
SMALL_TILES = {  # designed size -> box
    128: (3276, 456, 3532, 712),
    64: (3568, 584, 3696, 712),
    32: (3732, 648, 3796, 712),
    16: (3832, 680, 3864, 712),
}
CORNER = 0.215  # corner radius as a share of the tile's width


def rounded(tile):
    """Make the page background outside the tile's rounded corners transparent."""
    w, h = tile.size
    k = 4
    mask = Image.new("L", (w * k, h * k), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w * k - 1, h * k - 1), radius=int(w * k * CORNER), fill=255)
    out = tile.copy()
    out.putalpha(mask.resize((w, h), Image.LANCZOS))
    return out


def resized(img, size):
    return img.resize((size, size), Image.LANCZOS)


big = rounded(APP.crop(APP_TILE))
small = {s: rounded(SHEET.crop(box)) for s, box in SMALL_TILES.items()}


def save(img, rel):
    img.save(ROOT / rel)
    print("wrote", rel, img.size, img.mode)


# Icon file: the full design at 256, the designer's simplified tiles below it
ico_sources = {256: big, 128: small[128], 64: small[64], 48: small[64], 32: small[32], 24: small[32], 16: small[16]}
ico = [resized(src, s) for s, src in ico_sources.items()]
for rel in ("assets/icon.ico", "vendor/PenguLoader-1.1.6/loader/Resources/icon.ico"):
    ico[0].save(ROOT / rel, format="ICO", sizes=[(s, s) for s in ico_sources], append_images=ico[1:])
    print("wrote", rel, list(ico_sources))

save(resized(big, 512), "assets/icon.png")
save(resized(big, 300), "Pengu Loader/plugins/VEIL-Jade/assets/logo.png")

# Tray: the simplified tile reads best at tray size; dimmed while starting
tray = small[128]
save(tray, "assets/tray_ready.png")
dim = ImageEnhance.Brightness(ImageEnhance.Color(tray).enhance(0.25)).enhance(0.55)
dim.putalpha(tray.getchannel("A"))
save(dim, "assets/tray_starting.png")

# Sidebar item: a CSS mask shown at about 24px, so white with the mark of the
# 32px design (strokes drawn for small sizes) as alpha, centred in a square
lum = SHEET.crop(SMALL_TILES[32]).convert("L")
lum = lum.point(lambda v: max(0, min(255, (v - 60) * 255 // 150)))  # drop the dark tile
lum = lum.crop(lum.getbbox())
mark = lum.resize((lum.width * 8, lum.height * 8), Image.LANCZOS)
side = 512
pad = 0.08
scale = side * (1 - 2 * pad) / max(mark.size)
mark = mark.resize((round(mark.width * scale), round(mark.height * scale)), Image.LANCZOS)
alpha = Image.new("L", (side, side), 0)
alpha.paste(mark, ((side - mark.width) // 2, (side - mark.height) // 2))
nav = Image.new("RGBA", (side, side), (255, 255, 255, 0))
nav.putalpha(alpha)
save(nav, "assets/veil_nav.png")

if PREVIEW:
    # Preview: each output on a light and a dark strip
    PREVIEW.mkdir(parents=True, exist_ok=True)
    sheet = Image.new("RGBA", (1100, 560), (32, 32, 36, 255))
    sheet.paste(Image.new("RGBA", (1100, 280), (236, 236, 240, 255)), (0, 280))
    for row, y in ((0, 20), (1, 300)):
        x = 20
        for img in [resized(big, 160)] + ico[1:] + [resized(tray, 64), resized(dim, 64)]:
            sheet.alpha_composite(img, (x, y))
            x += img.width + 24
        nav_tint = Image.new("RGBA", (160, 160), (205, 190, 145, 255) if row == 0 else (60, 50, 90, 255))
        nav_tint.putalpha(resized(nav, 160).getchannel("A"))
        sheet.alpha_composite(nav_tint, (900, y))
    sheet.save(PREVIEW / "brand_export_preview.png")
    print("preview", PREVIEW / "brand_export_preview.png")
