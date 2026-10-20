"""Stable measurement contracts and evidence-backed descriptions, without an AI API."""

from __future__ import annotations

import copy
import re
from urllib.parse import quote, urlsplit, urlunsplit

from .extract import extract_fields
from .model import Snapshot

# Reviewed diff e6517d8 -> d55a24c: only uncategorized text was added.
# Existing prices, promotions, extras, controls and their identities did not change.
LEGACY_SALES = {"72356a749d038e0b", "dba81208d46a4f37"}
CONTRACT = "sales-v2"


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


def visual_description(before: Snapshot, after: Snapshot, difference) -> dict:
    old, new = before.document.get("visual", {}), after.document.get("visual", {})
    facts = []
    if old.get("schema") == new.get("schema") == 1:
        first = {e["key"]: e for e in old.get("elements", [])}
        second = {e["key"]: e for e in new.get("elements", [])}
        for key in sorted(first.keys() & second.keys()):
            a, b = first[key], second[key]
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
            ]:
                if a.get(prop) != b.get(prop) and a.get(prop) and b.get(prop):
                    facts.append(
                        {
                            "what": description + ": " + label,
                            "before": a[prop],
                            "after": b[prop],
                            "url": b.get("url") or after.url,
                        }
                    )
            if (
                a.get("rect")
                and b.get("rect")
                and any(abs(x - y) > 8 for x, y in zip(a["rect"], b["rect"], strict=True))
            ):
                facts.append(
                    {
                        "what": "Układ lub rozmiar: " + label,
                        "before": str(a["rect"]) + " px (x, y, szerokość, wysokość)",
                        "after": str(b["rect"]) + " px (x, y, szerokość, wysokość)",
                        "url": b.get("url") or after.url,
                    }
                )
            if a.get("text") != b.get("text") and a.get("text") and b.get("text"):
                facts.append(
                    {
                        "what": "Widoczny nagłówek: " + label,
                        "before": a["text"],
                        "after": b["text"],
                        "url": b.get("url") or after.url,
                    }
                )
        # New/removed large images are concrete observations too.
        for keys, mapping, removed in [
            (second.keys() - first.keys(), second, False),
            (first.keys() - second.keys(), first, True),
        ]:
            for key in sorted(keys):
                item = mapping[key]
                other = first if not removed else second
                if item.get("src") and item["src"] not in {e.get("src") for e in other.values()}:
                    facts.append(
                        {
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
        "facts": facts[:20],
        "bbox": bbox,
        "ratio": difference.ratio,
        "position": position,
        "area": area,
        "description": "; ".join(f["what"] for f in facts[:3]) or "Zmienił się obraz strony: " + area,
        "basis": "Porównanie obrazu; nie oznacza samo w sobie zmiany ceny ani promocji.",
        "unreliable": any(s.quality not in {"ok", "visual"} or any(re.search(r"niezaładowane|widoczny panel cookies",w,re.I) for w in s.warnings) for s in (before,after)),
    }
