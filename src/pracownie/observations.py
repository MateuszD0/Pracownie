"""Stable measurement contracts and evidence-backed descriptions, without an AI API."""

from __future__ import annotations

import copy
import re
from difflib import SequenceMatcher
from urllib.parse import quote, urlsplit, urlunsplit

from .extract import extract_fields
from .model import Snapshot

# Reviewed diff e6517d8 -> d55a24c: only uncategorized text was added.
# Existing prices, promotions, extras, controls and their identities did not change.
LEGACY_SALES = {"72356a749d038e0b", "dba81208d46a4f37"}
CONTRACT = "sales-v2"
VISUAL_CONTRACT = "visual-v3"


def signature(snapshot: Snapshot, category: str) -> str:
    if snapshot.contract:
        return snapshot.contract
    _, marker, extractor = snapshot.renderer.partition("|extractor=")
    if marker:
        code, _, adapter = extractor.partition("-")
        if code in LEGACY_SALES and (category != "tresc" or code == "dba81208d46a4f37"):
            return CONTRACT + ":" + adapter
        return extractor
    return snapshot.renderer


def replay_pair(before: Snapshot, after: Snapshot) -> tuple[Snapshot, Snapshot]:
    """Reparse two actual stored captures together; never visit a historical URL."""
    a, b = before.document, after.document
    if not a or not b or a.get("raw_schema") != "visible-v2" or b.get("raw_schema") != "visible-v2":
        return before, after
    if a.get("observed_at") != before.observed_at or b.get("observed_at") != after.observed_at:
        return before, after
    # Masks, explicit selectors, ignore rules and scenario must retain identity.
    if not a.get("adapter") or a.get("adapter") != b.get("adapter"):
        return before, after
    if a.get("ignore_patterns") != b.get("ignore_patterns"):
        return before, after
    if before.contract == after.contract:
        return before, after
    output = []
    for original in (before, after):
        result = copy.deepcopy(original)
        result.fields, result.sections = extract_fields(
            original.document["payload"], original.observed_at, original.document.get("ignore_patterns")
        )
        result.fields.update(
            {
                k: v
                for k, v in original.fields.items()
                if k.startswith("adapter:")
                and (v.observed_at or original.observed_at) == original.observed_at
            }
        )
        result.contract = CONTRACT + ":" + original.document["adapter"]
        output.append(result)
    return tuple(output)


def location_url(snapshot: Snapshot, section: str, value: str | None) -> str:
    parts = urlsplit(snapshot.url)
    anchor = snapshot.document.get("visual", {}).get("anchors", {}).get(section)
    if anchor:
        return urlunsplit((*parts[:4], quote(anchor, safe="")))
    # Use visible text only. Structured prices can have a different currency
    # spelling on the page, so those fall back to the original project URL.
    payload = snapshot.document.get("payload", {})
    lines = (value or "").splitlines()
    visible = {block.get("text", "") for block in payload.get("blocks", [])}
    match = next((line for line in lines if line in visible and 4 <= len(line) <= 180), None)
    if match:
        return urlunsplit((*parts[:4], ":~:text=" + quote(match, safe="")))
    return snapshot.url


def style_value(prop: str, value: str) -> str:
    if prop in {"background", "color"}:
        channels = re.fullmatch(r"rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)", value)
        if channels:
            if channels[4] and float(channels[4]) == 0:
                return "przezroczysty"
            if not channels[4] or float(channels[4]) == 1:
                color = "#" + "".join(f"{int(n):02X}" for n in channels.group(1, 2, 3))
                name = {"#FFFFFF": "biały", "#000000": "czarny", "#FF0000": "czerwony"}.get(color)
                return f"{name} ({color})" if name else color
    if prop == "font_weight":
        return {"400": "normalny (400)", "700": "pogrubiony (700)"}.get(value, value)
    return value


def scope_complete(document: dict) -> bool:
    return not document.get("truncated", len(document.get("elements", [])) >= 100)


def visual_description(before: Snapshot, after: Snapshot, difference) -> dict:
    from .communication import stable_element_key

    old, new = before.document.get("visual", {}), after.document.get("visual", {})
    facts = []
    carousel_assets = []
    for snapshot in (before, after):
        carousel_assets.append({i.get("asset") for i in snapshot.document.get("communication", {}).get("items", []) if i.get("role") == "image" and i.get("asset")})
    # A positional CSS selector identifies a slot, not the project displayed in
    # it. Match an existing image by its actual asset before comparing styles.
    # This also works with older captures without a carousel inventory.
    visible_assets = [{e.get("src") for e in doc.get("elements", []) if e.get("src")} for doc in (old, new)]
    stable_assets = (carousel_assets[0] | visible_assets[0]) & (carousel_assets[1] | visible_assets[1])
    rotation = False
    if old.get("schema") == new.get("schema") == 1:
        first = {e["key"]: e for e in old.get("elements", [])}
        second = {e["key"]: e for e in new.get("elements", [])}
        # A CSS slot can be reused when a list or carousel reorders. If either
        # heading is still present elsewhere, the slot alone cannot establish
        # that one message was rewritten into the other.
        old_texts = {e.get("text") for e in first.values() if e.get("text")}
        new_texts = {e.get("text") for e in second.values() if e.get("text")}
        compared_assets = set()
        for key in sorted(first.keys() & second.keys()):
            a, b = first[key], second[key]
            fact_start = len(facts)
            moved_image = False
            if a.get("src") and a.get("src") != b.get("src"):
                matches = [e for e in second.values() if e.get("src") == a["src"]]
                old_matches = [e for e in first.values() if e.get("src") == a["src"]]
                if len(matches) == len(old_matches) == 1:
                    b = matches[0]
                    moved_image = rotation = True
            old_backgrounds = set(re.findall(r'url\(["\']?([^"\')]+)["\']?\)', a.get("background_image", "")))
            new_backgrounds = set(re.findall(r'url\(["\']?([^"\')]+)["\']?\)', b.get("background_image", "")))
            rotating_background = old_backgrounds and new_backgrounds and old_backgrounds != new_backgrounds and old_backgrounds | new_backgrounds <= stable_assets
            if (a.get("src") and b.get("src") and a["src"] != b["src"] and (a["src"] in stable_assets or b["src"] in stable_assets)) or rotating_background:
                rotation = True
                continue
            if bool(a.get("src")) != bool(b.get("src")):
                continue
            compared_assets.update(e["src"] for e in (a, b) if e.get("src"))
            label = b.get("label") or a.get("label") or "element strony"
            generic = {"", "baner", "treść strony", "nagłówek strony"}
            if a.get("src") and b.get("src") and all(e.get("label", "") not in generic for e in (a, b)) and a["label"] != b["label"]:
                facts.append({
                    "what": "Opis grafiki",
                    "before": a.get("label") or "brak opisu",
                    "after": b.get("label") or "brak opisu",
                    "url": b.get("url") or after.url,
                })
            for prop, description in [
                ("src", "Źródło grafiki"),
                ("background_image", "Grafika w tle"),
                ("background", "Kolor tła"),
                ("color", "Kolor tekstu"),
                ("font", "Krój pisma"),
                ("font_size", "Rozmiar tekstu"),
                ("font_weight", "Grubość tekstu"),
                ("border_radius", "Zaokrąglenie elementu"),
            ]:
                if a.get(prop) != b.get(prop) and a.get(prop) and b.get(prop):
                    facts.append(
                        {
                            "what": description + ": " + label,
                            "before": style_value(prop, a[prop]),
                            "after": style_value(prop, b[prop]),
                            "url": b.get("url") or after.url,
                        }
                    )
            if (
                a.get("rect")
                and b.get("rect")
                and any(abs(a["rect"][i] - b["rect"][i]) > 8 for i in ((2, 3) if moved_image else (0, 1, 2, 3)))
            ):
                resized = any(abs(a["rect"][i] - b["rect"][i]) > 8 for i in (2, 3))
                moved = not moved_image and any(abs(a["rect"][i] - b["rect"][i]) > 8 for i in (0, 1))
                layout_label = "Położenie i rozmiar" if resized and moved else "Rozmiar" if resized else "Przesunięcie"
                movements = []
                for i, positive, negative in [(0, "w prawo", "w lewo"), (1, "w dół", "w górę")]:
                    distance = b["rect"][i] - a["rect"][i]
                    if not moved_image and abs(distance) > 8:
                        movements.append(f"{abs(distance)} px {positive if distance > 0 else negative}")
                facts.append(
                    {
                        "what": layout_label + ": " + label + (" (" + ", ".join(movements) + ")" if movements else ""),
                        "before": f'{a["rect"][2]} × {a["rect"][3]} px; położenie: {a["rect"][0]} px od lewej, {a["rect"][1]} px od góry',
                        "after": f'{b["rect"][2]} × {b["rect"][3]} px; położenie: {b["rect"][0]} px od lewej, {b["rect"][1]} px od góry',
                        "url": b.get("url") or after.url,
                    }
                )
            if (a.get("text") != b.get("text") and a.get("text") and b.get("text")
                    and a["text"] not in new_texts and b["text"] not in old_texts
                    and (stable_element_key(key) or SequenceMatcher(None, a["text"], b["text"]).ratio() >= .65)):
                facts.append(
                    {
                        "what": "Widoczny nagłówek: " + label,
                        "before": a["text"],
                        "after": b["text"],
                        "url": b.get("url") or after.url,
                    }
                )
            for fact in facts[fact_start:]:
                fact["element"] = key
        # Insertions can reuse an old CSS slot and shift all following slots.
        # Detect missing/new assets independently of those positional keys.
        for mapping, other_assets, removed in [
            (second, visible_assets[0], False),
            (first, visible_assets[1], True),
        ]:
            for key in sorted(mapping):
                item = mapping[key]
                if (scope_complete(old) and scope_complete(new) and old.get("scope", "legacy") == new.get("scope", "legacy")
                    and item.get("src") and item["src"] not in stable_assets | other_assets | compared_assets):
                    compared_assets.add(item["src"])
                    facts.append(
                        {
                            "element": item["src"],
                            "what": ("Usunięta" if removed else "Dodana")
                            + " grafika: "
                            + item.get("label", ""),
                            "before": item["src"] if removed else "brak",
                            "after": "brak" if removed else item["src"],
                            "url": after.url if removed else item.get("url", after.url),
                        }
                    )
    # Prefer the changed visual assets and colors over repeated inherited
    # typography/layout facts, while retaining a bounded inspectable record.
    facts.sort(key=lambda f: not any(word in f["what"].lower() for word in ["grafik", "tła"]))
    bbox = list(difference.bbox or [])
    if bbox:
        top, bottom = bbox[1], bbox[3]
        area = (
            "górna część strony"
            if top < 560
            else "środkowa część strony"
            if top < 2400
            else "dolna część strony"
        )
        position = f"{area}; zaznaczony obszar y={top}–{bottom} px przy szerokości porównania 800 px"
    else:
        area = "obszar strony"
        position = "zaznaczony obszar strony"
    return {
        "measurement": VISUAL_CONTRACT,
        "facts": facts,
        "fact_count": len(facts),
        "scope_complete": scope_complete(old) and scope_complete(new),
        "scope_changed": old.get("scope", "legacy") != new.get("scope", "legacy"),
        "bbox": bbox,
        "ratio": difference.ratio,
        "position": position,
        "area": area,
        "description": "; ".join(f["what"] for f in facts[:3]) or ("Inna kolejność lub aktywny slajd istniejących grafik" if rotation else "Różnica zrzutów: " + area + " — przyczyna nieustalona"),
        "rotation": rotation,
        "basis": "Porównanie obrazu; nie oznacza samo w sobie zmiany ceny ani promocji.",
        "unreliable": any(s.quality not in {"ok", "visual"} or any(re.search(r"niezaładowane|widoczny panel cookies",w,re.I) for w in s.warnings) for s in (before,after)),
    }
