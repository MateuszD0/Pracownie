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


def visual_evidence(before: Path, after: Path, directory: Path, difference: VisualDiff) -> dict[str, Path]:
    """Crop the measured changed area, keeping the actual captures unchanged."""
    if not difference.bbox:
        return {}
    x0, y0, x1, y1 = difference.bbox
    # A tall layout change needs a readable first changed region, not a tiny
    # thumbnail of the entire document. Full screenshots remain available.
    y0 = max(0, y0 - 32)
    y1 = min(y1 + 32, y0 + 1000)
    paths = {}
    crops = []
    with Image.open(before) as first, Image.open(after) as second:
        comparison_width = min(800, max(first.width, second.width))
    for label, source in [("fragment_przed", before), ("fragment_po", after)]:
        with Image.open(source) as original:
            scale = original.width / comparison_width
            box = (max(0, int((x0 - 24) * scale)), int(y0 * scale), min(original.width, int((x1 + 24) * scale)), min(original.height, int(y1 * scale)))
            if box[3] <= box[1]:
                # A removed lower section has no corresponding current area.
                crop = Image.new("RGB", (max(1, box[2] - box[0]), 100), "white")
            else:
                crop = original.convert("RGB").crop(box)
            crop.thumbnail((800, 1000))
            path = directory / (label + ".png")
            crop.save(path)
            paths[label] = path
            crops.append(crop)
    canvas = Image.new("RGB", (sum(c.width for c in crops) + 12, max(c.height for c in crops) + 28), "#eeeeee")
    offset = 0
    draw = ImageDraw.Draw(canvas)
    for label, crop in zip(["PRZED", "PO"], crops, strict=True):
        draw.text((offset + 6, 6), label, fill="black")
        canvas.paste(crop, (offset, 28))
        draw.rectangle((offset, 28, offset + crop.width - 1, 27 + crop.height), outline="red", width=3)
        offset += crop.width + 12
    proof = directory / "zmieniony-obszar.png"
    canvas.save(proof)
    paths["zmieniony_obszar"] = proof
    return paths


def visual_text(paths: dict[str, Path]) -> dict:
    """Optional bounded OCR context; never creates a price/promotion signal."""
    language = ocr_language()
    if not language:
        return {}
    texts = []
    for key in ("fragment_przed", "fragment_po"):
        try:
            result = subprocess.run(["tesseract", str(paths[key]), "stdout", "-l", language, "tsv"], capture_output=True, text=True, timeout=3)
            rows = [r for r in csv.DictReader(io.StringIO(result.stdout), delimiter="\t", quoting=csv.QUOTE_NONE) if r.get("text", "").strip()]
            confidence = sum(float(r["conf"]) for r in rows) / max(1, len(rows))
            if result.returncode or len(rows) < 3 or confidence < 85:
                return {}
            texts.append(" ".join(r["text"] for r in rows)[:500])
        except (OSError, subprocess.TimeoutExpired, KeyError, ValueError):
            return {}
    if texts[0] == texts[1]:
        return {}
    return {"before": texts[0], "after": texts[1], "basis": "Pomocniczy odczyt tekstu z obrazu (OCR); miarodajnym dowodem jest załączony fragment zrzutu."}


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
        rows = [r for r in csv.DictReader(io.StringIO(result.stdout), delimiter="\t", quoting=csv.QUOTE_NONE) if r.get("text", "").strip()]
        text = " ".join(row["text"] for row in rows)[:1500]
        confidence = sum(float(r["conf"]) for r in rows) / max(1, len(rows))
        return text, f"OCR: średnia pewność {confidence:.0f}/100; odczyt wymaga oceny."
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return "", "OCR niedostępne lub przekroczony czas; wymaga oceny."


def lossless_image(source: Path) -> tuple[bytes, str]:
    """Use WebP only when smaller; never resize or introduce lossy pixels."""
    original = source.read_bytes()
    with Image.open(source) as image:
        extension = '.webp' if image.format == 'WEBP' else '.png'
        if image.format == 'WEBP' or max(image.size) > 16383:
            return original, extension
        stream = io.BytesIO()
        image.save(stream, format='WEBP', lossless=True, method=3, exact=True)
        compressed = stream.getvalue()
    return (compressed, '.webp') if len(compressed) < len(original) else (original, extension)


def compact_evidence(root: Path, day: str, results: list) -> dict:
    """Keep page-local paths for safe domain resume; reuse identical local images."""
    from .model import safe_path
    from .state import atomic_write

    root = root.resolve()
    references = [r.evidence for r in results] + [c.evidence for r in results for c in r.changes]
    paths = {p for refs in references for p in refs.values()}
    replacements, originals, saved = {}, 0, 0
    encoded, local_assets = {}, {}
    for relative in sorted(paths):
        path = safe_path(root, relative)
        if not relative.startswith(day + '/') or path.suffix not in {'.png', '.webp'}:
            continue
        from .model import digest
        fingerprint = digest(path)
        if fingerprint in encoded:
            cached = encoded[fingerprint]
            content, extension = cached.read_bytes(), cached.suffix
        else:
            content, extension = lossless_image(path)
        target = path.with_suffix(extension)
        originals += path.stat().st_size
        saved += path.stat().st_size - len(content)
        if target != path:
            atomic_write(target, content)
            path.unlink()
        encoded[fingerprint] = target
        import hashlib
        local_key = (target.parent, hashlib.sha256(content).hexdigest())
        if local_key in local_assets and local_assets[local_key] != target:
            saved += target.stat().st_size
            target.unlink()
            target = local_assets[local_key]
            encoded[fingerprint] = target
        else:
            local_assets[local_key] = target
        replacements[relative] = target.relative_to(root).as_posix()
    for refs in references:
        for name, relative in refs.items():
            refs[name] = replacements.get(relative, relative)
    return {'input_bytes': originals, 'saved_bytes': saved, 'format': 'lossless-webp-or-png'}
