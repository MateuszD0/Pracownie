"""Compare the placement of an identical offer in two measured page layouts."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from PIL import Image

from .model import Change, Snapshot, local_day, safe_path

ZONES = {"first": "Na pierwszym ekranie", "lower": "Poniżej pierwszego ekranu"}


def offer_text(text: str) -> bool:
    from .financial import meaningful_discount

    benefit = re.sub(r"\b(?:gratis\w*|bezpłat\w*|za darmo)\b", "", text, flags=re.I)
    return bool(
        meaningful_discount(text)
        or (benefit != text and re.search(r"\b[^\W\d_]{4,}\b", benefit))
        or re.search(r"(?:taniej|oszczęd).{0,25}\d+\s*(?:zł|pln|%)", text, re.I)
    )


def stable_placements(first: dict, second: dict) -> dict:
    """Require one unambiguous location on both passes of the same page."""
    from .communication import clean

    if (
        not first
        or not second
        or first.get("truncated")
        or second.get("truncated")
        or not second.get("viewport")
        or first.get("viewport") != second["viewport"]
    ):
        return {}

    def unique(sample):
        groups = defaultdict(list)
        for entry in sample["items"]:
            text = clean(entry["text"])
            if offer_text(text):
                groups[text].append(entry)
        return {t: items[0] for t, items in groups.items() if len(items) == 1 and items[0]["zone"] in ZONES}

    old, new = unique(first), unique(second)
    stable = {}
    for text in old.keys() & new.keys():
        a, b = old[text], new[text]
        if (
            a["zone"] == b["zone"]
            and a["key"] == b["key"]
            and max(abs(x - y) for x, y in zip(a["rect"], b["rect"], strict=True)) <= 8
        ):
            stable[text] = {"key": b["key"], "zone": b["zone"], "rect": b["rect"]}
    return {"version": 1, "viewport": second["viewport"], "offers": stable}


def placement_measured(snapshot: Snapshot) -> bool:
    inventory = snapshot.document.get("communication", {}).get("placement", {})
    return (
        snapshot.scenario == "podstawowy"
        and snapshot.quality in {"ok", "visual"}
        and inventory.get("version") == 1
        and bool(inventory.get("viewport"))
        and not any(
            re.search(r"niezaładowane|panel cookies|wyłączyć animacji", w, re.I) for w in snapshot.warnings
        )
    )


def compare_placements(
    before: Snapshot, after: Snapshot, old_items: list[dict], new_items: list[dict]
) -> tuple[bool, bool, list[Change]]:
    """Called after the copy comparator verifies both scopes, URLs and renderers."""
    if (
        not (placement_measured(before) and placement_measured(after))
        or (observed_day(after) - observed_day(before)).days != 1
    ):
        return False, False, []
    old_copy, new_copy = before.document["communication"], after.document["communication"]
    old, new = old_copy["placement"], new_copy["placement"]
    if old["viewport"] != new["viewport"] or old_copy.get("context_selectors") != new_copy.get(
        "context_selectors"
    ):
        return False, False, []
    old_texts = {entry["text"] for entry in old_items if not entry.get("unstable")}
    new_texts = {entry["text"]: entry for entry in new_items if not entry.get("unstable")}
    changes = []
    matched = old["offers"].keys() & new["offers"].keys() & old_texts & new_texts.keys()
    for text in sorted(matched):
        a, b = old["offers"][text], new["offers"][text]
        if a["zone"] == b["zone"]:
            continue
        key = hashlib.sha256(text.encode()).hexdigest()[:16]
        details = {
            "role": "placement",
            "element_before": a["key"],
            "element_after": b["key"],
            "offer_placement": {
                "text": text,
                "before": a["zone"],
                "after": b["zone"],
                "before_rect": a["rect"],
                "after_rect": b["rect"],
                "viewport": new["viewport"],
            },
            "basis": "Ten sam komunikat i rozmiar okna w obu dniach. Położenie powtórzyło się w dwóch pomiarach każdego dnia.",
        }
        changes.append(
            Change(
                "changed",
                "komunikacja",
                "Zmiana ekspozycji promocji",
                f"{ZONES[a['zone']]} · {text}",
                f"{ZONES[b['zone']]} · {text}",
                before.observed_at,
                after.observed_at,
                new_texts[text].get("url") or after.url,
                after.scenario,
                field_key="communication:placement:" + key,
                details=details,
            )
        )
    return True, bool(matched), changes


def observed_day(snapshot: Snapshot) -> date:
    return date.fromisoformat(local_day(datetime.fromisoformat(snapshot.observed_at)))


def placement_coverage(view: dict) -> dict:
    """Count measured pages, comparable pairs, and pairs with a shared offer."""
    counts = {"expected": len(view["rows"]) * 2, "measured": 0, "compared": 0, "matched": 0}
    for row in view["rows"]:
        for page in row.get("pages", []):
            if not page.get("current_read"):
                continue
            copy = page.get("communication", {})
            if copy.get("placement_measured"):
                counts["measured"] += 1
                if copy.get("daily") and copy.get("placement_compared"):
                    counts["compared"] += 1
                    if copy.get("placement_matched"):
                        counts["matched"] += 1
    return counts


def attach_placement_crops(change: Change, root: Path) -> None:
    """Keep per-day crops around the measured message, or use the whole image pair."""
    placement = change.details.get("offer_placement")
    if not placement:
        return
    evidence = change.evidence
    # The generic pixel-difference crops can highlight a different element.
    for key in ("fragment_przed", "fragment_po", "zmieniony_obszar"):
        evidence.pop(key, None)
    if not all(evidence.get(side) for side in ("przed", "po")):
        return
    try:
        crop_evidence(placement, evidence, root)
    except (OSError, ValueError, Image.DecompressionBombError):
        # A missing/corrupt optional image must not erase the recorded change.
        return


def crop_evidence(placement: dict, evidence: dict, root: Path) -> None:
    crops = []
    for side, rect in [("przed", placement["before_rect"]), ("po", placement["after_rect"])]:
        path = safe_path(root, evidence[side])
        if not path.is_file():
            return
        with Image.open(path) as image:
            x, y, width, height = rect
            if (
                image.width != placement["viewport"][0]
                or min(x, y) < 0
                or x + width > image.width + 1
                or y + height > image.height + 1
            ):
                return
            box = (
                max(0, x - 24),
                max(0, y - 45),
                min(image.width, x + width + 24),
                min(image.height, y + height + 45),
            )
            crop = image.crop(box)
            crop.thumbnail((1100, 540))
            crops.append((side, crop))
    dest = safe_path(root, evidence["po"]).parent
    token = hashlib.sha256(placement["text"].encode()).hexdigest()[:16]
    paths = {}
    for side, crop in crops:
        path = dest / f"ekspozycja-{token}-{side}.png"
        crop.save(path)
        paths["fragment_" + side] = path.relative_to(root).as_posix()
    evidence.update(paths)
