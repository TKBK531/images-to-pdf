"""Generate icon.ico (Windows) and icon.icns (macOS) for PyInstaller builds.

Pure-Pillow vector drawing, so this produces the same icon on every CI
runner with no external asset files or platform-specific tools required.
Run from the repo root: python scripts/make_icon.py
"""

import sys

from PIL import Image, ImageDraw

ACCENT = (79, 142, 247, 255)
FOLD_SHADE = (210, 224, 250, 255)
TEXT_LINE = (190, 205, 235, 255)
WHITE = (255, 255, 255, 255)
BADGE_BG = (62, 207, 142, 255)


def draw_icon(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    pad = size * 0.06
    d.rounded_rectangle(
        [pad, pad, size - pad, size - pad], radius=size * 0.22, fill=ACCENT
    )

    # Document with a folded top-right corner.
    doc_left, doc_top = size * 0.22, size * 0.16
    doc_right, doc_bottom = size * 0.66, size * 0.82
    fold = size * 0.12
    d.polygon(
        [
            (doc_left, doc_top),
            (doc_right - fold, doc_top),
            (doc_right, doc_top + fold),
            (doc_right, doc_bottom),
            (doc_left, doc_bottom),
        ],
        fill=WHITE,
    )
    d.polygon(
        [
            (doc_right - fold, doc_top),
            (doc_right, doc_top + fold),
            (doc_right - fold, doc_top + fold),
        ],
        fill=FOLD_SHADE,
    )

    # Lines of "text" on the document.
    for i in range(3):
        y = doc_top + fold + size * 0.10 + i * size * 0.09
        d.rectangle(
            [doc_left + size * 0.06, y, doc_right - size * 0.08, y + size * 0.035],
            fill=TEXT_LINE,
        )

    # Small "photo" badge overlapping the bottom-right of the document.
    b_left, b_top = size * 0.50, size * 0.52
    b_right, b_bottom = size * 0.88, size * 0.82
    d.rounded_rectangle(
        [b_left, b_top, b_right, b_bottom],
        radius=size * 0.03,
        fill=BADGE_BG,
        outline=ACCENT,
        width=max(1, int(size * 0.012)),
    )
    sun_r = size * 0.035
    d.ellipse(
        [b_left + size * 0.06, b_top + size * 0.06, b_left + size * 0.06 + sun_r * 2, b_top + size * 0.06 + sun_r * 2],
        fill=WHITE,
    )
    d.polygon(
        [
            (b_left + size * 0.04, b_bottom - size * 0.04),
            (b_left + size * 0.16, b_top + size * 0.12),
            (b_left + size * 0.28, b_bottom - size * 0.04),
        ],
        fill=WHITE,
    )

    return img


def main():
    base = draw_icon(256)

    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    base.save("icon.ico", sizes=[(s, s) for s in ico_sizes])
    print("Wrote icon.ico")

    try:
        base.save("icon.icns")
        print("Wrote icon.icns")
    except Exception as e:
        print(f"Skipping icon.icns (unsupported here): {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
