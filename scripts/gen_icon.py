"""Generate Vox app icon — ASCII V rendered at 4096px, downscaled for clarity."""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

ROOT = Path(__file__).parent.parent
ICONS_DIR = ROOT / "src-tauri" / "icons"
FONT_PATH = "C:/Windows/Fonts/consolab.ttf"

BG = (10, 10, 11, 255)
WHITE = (250, 250, 250, 255)

V_TEXT = (
    "██╗   ██╗\n"
    "██║   ██║\n"
    "██║   ██║\n"
    "╚██╗ ██╔╝\n"
    " ╚████╔╝\n"
    "  ╚═══╝"
)

MASTER = 4096


def render_master() -> Image.Image:
    size = MASTER
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    r = size // 6
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=BG)

    # Binary search for font size that fills ~70% width
    target_w = size * 0.70
    lo, hi = 10, size
    while lo < hi:
        mid = (lo + hi + 1) // 2
        font = ImageFont.truetype(FONT_PATH, mid)
        bbox = draw.textbbox((0, 0), V_TEXT, font=font)
        if (bbox[2] - bbox[0]) <= target_w:
            lo = mid
        else:
            hi = mid - 1

    font = ImageFont.truetype(FONT_PATH, lo)
    bbox = draw.textbbox((0, 0), V_TEXT, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) / 2 - bbox[0]
    y = (size - th) / 2 - bbox[1]
    draw.text((x, y), V_TEXT, font=font, fill=WHITE)

    return img


def main():
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    master = render_master()

    for name, s in [("icon.png", 512), ("32x32.png", 32)]:
        master.resize((s, s), Image.LANCZOS).save(ICONS_DIR / name, "PNG")
        print(f"Saved {name} ({s}x{s})")

    ico_sizes = [16, 32, 48, 256]
    imgs = [master.resize((s, s), Image.LANCZOS) for s in ico_sizes]
    imgs[0].save(ICONS_DIR / "icon.ico", format="ICO",
                 append_images=imgs[1:], sizes=[(s, s) for s in ico_sizes])
    print("Saved icon.ico")

    master.resize((16, 16), Image.LANCZOS).save(ICONS_DIR / "16x16_preview.png")
    print("Done!")


if __name__ == "__main__":
    main()
