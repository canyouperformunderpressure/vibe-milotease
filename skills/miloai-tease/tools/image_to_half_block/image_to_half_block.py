from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

from PIL import Image


WHITE = (255, 255, 255)


def distance_sq(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return sum((a[index] - b[index]) ** 2 for index in range(3))


def average_rgb(colors: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    if not colors:
        return WHITE
    return tuple(
        round(sum(color[channel] for color in colors) / len(colors))
        for channel in range(3)
    )


def corner_background(image: Image.Image) -> tuple[int, int, int]:
    width, height = image.size
    side = max(1, min(width, height) // 24)
    colors: list[tuple[int, int, int]] = []
    for box in (
        (0, 0, side, side),
        (width - side, 0, width, side),
        (0, height - side, side, height),
        (width - side, height - side, width, height),
    ):
        colors.extend(image.crop(box).getdata())
    return average_rgb(colors)


def auto_crop(image: Image.Image, *, threshold: int = 18, margin: float = 0.05) -> Image.Image:
    background = corner_background(image)
    limit = threshold * threshold * 3
    pixels = image.load()
    xs: list[int] = []
    ys: list[int] = []
    for y in range(image.height):
        for x in range(image.width):
            if distance_sq(pixels[x, y], background) > limit:
                xs.append(x)
                ys.append(y)
    if not xs:
        return image
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    margin_x = round((right - left + 1) * margin)
    margin_y = round((bottom - top + 1) * margin)
    return image.crop(
        (
            max(0, left - margin_x),
            max(0, top - margin_y),
            min(image.width, right + 1 + margin_x),
            min(image.height, bottom + 1 + margin_y),
        )
    )


def normalize_background(
    color: tuple[int, int, int],
    background: tuple[int, int, int],
    *,
    tolerance: int = 12,
) -> tuple[int, int, int]:
    if distance_sq(color, background) <= tolerance * tolerance * 3:
        return background
    return color


def make_palette(image: Image.Image, *, colors: int) -> list[tuple[int, int, int]]:
    quantized = image.quantize(colors=colors, method=Image.Quantize.MEDIANCUT).convert("RGB")
    counts = Counter(quantized.getdata())
    background = corner_background(image)
    palette: list[tuple[int, int, int]] = [background]
    for color, _count in counts.most_common():
        normalized = normalize_background(color, background)
        if normalized not in palette:
            palette.append(normalized)
    return palette


def nearest_palette_index(
    color: tuple[int, int, int],
    palette: list[tuple[int, int, int]],
) -> int:
    return min(range(len(palette)), key=lambda index: distance_sq(color, palette[index]))


def encode_half_block(
    image: Image.Image,
    *,
    columns: int,
    colors: int,
) -> tuple[list[tuple[int, int, int]], str, int]:
    cropped = auto_crop(image)
    target_height = round(cropped.height * columns / cropped.width)
    if target_height % 2:
        target_height += 1
    resized = cropped.resize((columns, target_height), Image.Resampling.LANCZOS)
    palette = make_palette(resized, colors=colors)
    background = palette[0]
    pixels = resized.load()

    rows: list[str] = []
    for y in range(0, target_height, 2):
        runs: list[str] = []
        run_index: int | None = None
        run_text = ""
        for x in range(columns):
            top = normalize_background(pixels[x, y], background)
            bottom = normalize_background(pixels[x, y + 1], background)
            top_index = nearest_palette_index(top, palette)
            bottom_index = nearest_palette_index(bottom, palette)

            if top_index == bottom_index:
                character = "█"
                color_index = top_index
            elif top_index == 0:
                character = "▄"
                color_index = bottom_index
            elif bottom_index == 0:
                character = "▀"
                color_index = top_index
            else:
                top_contrast = distance_sq(palette[top_index], background)
                bottom_contrast = distance_sq(palette[bottom_index], background)
                if top_contrast >= bottom_contrast:
                    character = "▀"
                    color_index = top_index
                else:
                    character = "▄"
                    color_index = bottom_index

            if color_index != run_index:
                if run_text:
                    runs.append(f"{run_index:x}{run_text}")
                run_index = color_index
                run_text = character
            else:
                run_text += character

        if run_text:
            runs.append(f"{run_index:x}{run_text}")
        rows.append("~".join(runs))

    return palette, "|".join(rows), target_height // 2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert an image to compact precomputed static half-block data for Milo Say."
    )
    parser.add_argument("image", type=Path)
    parser.add_argument("--columns", type=int, default=80)
    parser.add_argument("--colors", type=int, default=12)
    args = parser.parse_args()
    if args.columns < 4:
        parser.error("--columns must be at least 4")
    if not 2 <= args.colors <= 16:
        parser.error("--colors must be between 2 and 16")

    image = Image.open(args.image).convert("RGB")
    palette, data, rows = encode_half_block(
        image,
        columns=args.columns,
        colors=args.colors,
    )
    print(
        json.dumps(
            {
                "columns": args.columns,
                "rows": rows,
                "palette": ["#%02x%02x%02x" % color for color in palette],
                "data": data,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
