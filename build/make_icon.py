"""Generate build/icon.ico.

The icon is committed, so this only needs re-running when the mark changes.
Drawing it here rather than shipping a binary asset from a design tool keeps the
shape reviewable in the diff and reproducible on any machine.

    python build\\make_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

#: Sizes Windows asks for, largest first.
SIZES = (256, 128, 64, 48, 32, 16)

ACCENT = (37, 99, 235, 255)  # matches theme.LIGHT.accent
ACCENT_DEEP = (29, 78, 216, 255)
PAPER = (255, 255, 255, 255)
PAPER_SHADE = (219, 229, 250, 255)


def draw_icon(size: int) -> Image.Image:
    """Draw the mark at ``size`` px: a document sheet with a folded corner."""
    # Supersample, then downscale, so the diagonal fold and rounded corners stay
    # smooth at 16 px where direct drawing would alias badly.
    scale = 8 if size <= 64 else 4
    canvas = size * scale
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    radius = canvas * 0.22
    draw.rounded_rectangle([0, 0, canvas - 1, canvas - 1], radius=radius, fill=ACCENT)

    # Vertical gradient, applied per row rather than as a hard band: a two-tone
    # split reads as a rendering artifact at small sizes.
    for y in range(int(canvas)):
        blend = y / canvas
        colour = tuple(
            int(ACCENT[i] + (ACCENT_DEEP[i] - ACCENT[i]) * blend) for i in range(3)
        ) + (255,)
        draw.line([(0, y), (canvas, y)], fill=colour)
    # Re-cut the rounded silhouette, since the gradient painted over the corners.
    mask = Image.new("L", (int(canvas), int(canvas)), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, canvas - 1, canvas - 1], radius=radius, fill=255
    )
    image.putalpha(mask)
    draw = ImageDraw.Draw(image)

    # The sheet.
    left, top = canvas * 0.28, canvas * 0.20
    right, bottom = canvas * 0.72, canvas * 0.80
    fold = canvas * 0.14

    draw.polygon(
        [
            (left, top),
            (right - fold, top),
            (right, top + fold),
            (right, bottom),
            (left, bottom),
        ],
        fill=PAPER,
    )
    # Folded corner.
    draw.polygon([(right - fold, top), (right, top + fold), (right - fold, top + fold)],
                 fill=PAPER_SHADE)

    # Text lines, suggesting markup rather than prose.
    line_height = canvas * 0.035
    gap = canvas * 0.075
    for index, width_factor in enumerate((0.62, 0.80, 0.45)):
        y = top + fold + gap * (index + 0.9)
        x_start = left + canvas * 0.06
        x_end = x_start + (right - left - canvas * 0.12) * width_factor
        draw.rounded_rectangle(
            [x_start, y, x_end, y + line_height],
            radius=line_height / 2,
            fill=ACCENT,
        )

    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    target = Path(__file__).parent / "icon.ico"
    frames = [draw_icon(size) for size in SIZES]
    frames[0].save(target, format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"scritto {target} ({target.stat().st_size} byte)")


if __name__ == "__main__":
    main()
