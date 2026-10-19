from __future__ import annotations

import csv
import io
import shutil
import subprocess
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageOps


@dataclass
class VisualDiff:
    changed: bool
    ratio: float
    bbox: tuple | None


def image_difference(before: Path, after: Path, output: Path, threshold: float = 0.008) -> VisualDiff:
    with Image.open(before) as first, Image.open(after) as second:
        first, second = first.convert("RGB"), second.convert("RGB")
        width = min(800, max(first.width, second.width))
        first = first.resize((width, max(1, int(first.height * width / first.width))))
        second = second.resize((width, max(1, int(second.height * width / second.width))))
        height = max(first.height, second.height)
        a = Image.new("RGB", (width, height), "white")
        b = a.copy()
        a.paste(first)
        b.paste(second)
        red, green, blue = ImageChops.difference(a, b).split()
        difference = ImageChops.lighter(ImageChops.lighter(red, green), blue).point(lambda p: 255 if p > 35 else 0)
        histogram = difference.histogram()
        ratio = histogram[255] / (width * height)
        bbox = difference.getbbox()
        # A small coupon/date inside a banner must not disappear in a long page's average.
        regional_change = False
        if bbox and ratio < threshold:
            for top in range(0, height, 32):
                for left in range(0, width, 32):
                    tile = difference.crop((left, top, min(left + 32, width), min(top + 32, height)))
                    pixels = tile.histogram()[255]
                    if pixels >= 12 and pixels / (tile.width * tile.height) >= 0.015:
                        regional_change = True
                        break
                if regional_change:
                    break
        changed = (ratio >= threshold or regional_change) and bbox is not None
        if changed:
            canvas = Image.new("RGB", (width * 2 + 8, height + 32), "#eeeeee")
            canvas.paste(a, (0, 32))
            canvas.paste(b, (width + 8, 32))
            draw = ImageDraw.Draw(canvas)
            draw.text((8, 8), "PRZED", fill="black")
            draw.text((width + 16, 8), "PO", fill="black")
            for offset in (0, width + 8):
                x0, y0, x1, y1 = bbox
                draw.rectangle((x0 + offset, y0 + 32, x1 + offset, y1 + 32), outline="red", width=3)
            output.parent.mkdir(parents=True, exist_ok=True)
            canvas.save(output, optimize=True)
        return VisualDiff(changed, ratio, bbox)


@cache
def ocr_language() -> str | None:
    if not shutil.which("tesseract"):
        return None
    try:
        result = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    langs = result.stdout.splitlines()
    return "pol+eng" if "pol" in langs and "eng" in langs else "eng" if "eng" in langs else None


def ocr_context(image_path: Path, destination: Path, bbox: tuple | None = None) -> tuple[str, str]:
    """OCR is evidence only, never an authoritative monetary field."""
    language = ocr_language()
    if not language:
        return "", "OCR niedostępne; zmiana obrazu wymaga oceny."
    with Image.open(image_path) as source:
        image = source.convert("RGB")
        if bbox:
            scale = image.width / min(800, image.width)
            x0, y0, x1, y1 = bbox
            crop = (int(x0 * scale), int(y0 * scale), min(image.width, int(x1 * scale)), min(image.height, int(y1 * scale)))
            if crop[3] > crop[1]:
                image = image.crop(crop)
        image = ImageOps.contain(image, (1600, 4000))
        image.save(destination)
    try:
        result = subprocess.run(
            ["tesseract", str(destination), "stdout", "-l", language, "tsv"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode:
            return "", "OCR nie powiodło się; wymaga oceny."
        rows = [r for r in csv.DictReader(io.StringIO(result.stdout), delimiter="\t") if r.get("text", "").strip()]
        text = " ".join(row["text"] for row in rows)[:1500]
        confidence = sum(float(r["conf"]) for r in rows) / max(1, len(rows))
        return text, f"OCR: średnia pewność {confidence:.0f}/100; odczyt wymaga oceny."
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return "", "OCR niedostępne lub przekroczony czas; wymaga oceny."
