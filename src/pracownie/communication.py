"""Compare recorded communication independently of price extraction versions.

Unknown legacy extracts can establish agreement of shared fragments, never a
campaign launch/removal. Only two captures of this contract establish changes.
"""

from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher

from .extract import MONEY, canonical_url, money_text, normalize
from .model import Change, Snapshot

CONTRACT = "communication-v1"
NOISE = re.compile(r"cookies|ciastecz|prywatno|danych osobowych|wyrażam zgod|przetwarzani.*danych|rodo\b|sales intelligence|digitree|^\[licznik\]$", re.I)
ROLES = {"heading": "Nagłówek", "banner": "Baner", "cta": "Wezwanie do działania", "text": "Treść", "image": "Źródło grafiki w zestawie banerów"}


def clean(value: str, patterns: list[str] | None = None) -> str:
    value = normalize(value, patterns)
    if MONEY.fullmatch(money_text(value)):
        return ""
    if NOISE.search(value) or not re.search(r"[a-ząćęłńóśźż]{3}", value, re.I):
        return ""
    if re.fullmatch(r"[\d\s.,%²m+−–-]+", value):
        return ""
    return value


def records(snapshot: Snapshot) -> list[dict]:
    doc = snapshot.document.get("communication", {})
    if doc.get("contract") != CONTRACT or doc.get("observed_at") != snapshot.observed_at:
        return []
    output, seen = [], set()
    for item in doc.get("items", []):
        value = clean(item.get("text", ""), snapshot.document.get("ignore_patterns"))
        identity = (item.get("role", "text"), value)
        if value and identity not in seen:
            output.append({**item, "text": value})
            seen.add(identity)
    return output


def text_fragments(snapshot: Snapshot) -> set[str]:
    # Legacy evidence remains scoped to texts actually saved on that day.
    return {text for key, field in snapshot.fields.items() if key.startswith("tekst:")
            and field.category not in {"ceny", "parametry"}
            and (field.observed_at or snapshot.observed_at) == snapshot.observed_at
            for line in field.value.splitlines() if (text := clean(line))}


def category(before: str, after: str) -> str:
    text = before + " " + after
    for name, pattern in [("promocje", r"promoc|rabat|przecen|wyprzeda|kod rabat"),
                          ("dodatki", r"gratis|bezpłat|za darmo|dodatk|kosztorys"),
                          ("pakiety", r"pakiet|w cenie|dokumentac"),
                          ("warunki", r"dostaw|wysył|termin|zwrot|gwaranc"),
                          ("funkcje", r"konfigur|kalkulator|personaliz")]:
        if re.search(pattern, text, re.I):
            return name
    return "komunikacja"


def measure(before: Snapshot | None, after: Snapshot) -> tuple[dict, list[Change]]:
    current = records(after)
    old_text, new_text = text_fragments(before) if before else set(), text_fragments(after)
    output = {
        "contract": CONTRACT, "status": "baseline", "comparable": False,
        "ready": bool(current) and after.quality in {"ok", "visual"} and not after.document.get("communication", {}).get("truncated"),
        "scope": "nagłówki, banery, CTA i treść; rotatory jako zestaw slajdów",
        "before_at": before.observed_at if before else None, "after_at": after.observed_at,
        "fragments_before": len(old_text), "fragments_after": len(current) or len(new_text),
        "shared_unchanged": len(old_text & new_text), "changes": 0,
        "same_visible_image": False,
        "reason": "Pierwszy zapis komunikacji; brak porównywalnej bazy z poprzedniego dnia.",
    }
    if before is None:
        return output, []
    old = records(before)
    same = (before.domain, before.page, before.scenario, canonical_url(before.url)) == (after.domain, after.page, after.scenario, canonical_url(after.url))
    same_browser = before.renderer.split("|extractor=")[0] == after.renderer.split("|extractor=")[0]
    # State image names are content-addressed and checked on restore. Equality
    # establishes only the captured, possibly masked viewport, never all slides.
    output["same_visible_image"] = bool(same and same_browser and before.quality in {"ok", "visual"} and after.quality in {"ok", "visual"} and re.fullmatch(r"images/[a-f0-9]{64}\.png", before.image) and before.image == after.image)
    old_adapter = before.document.get("communication", {}).get("adapter")
    new_adapter = after.document.get("communication", {}).get("adapter")
    same_adapter = bool(old_adapter) and old_adapter == new_adapter
    complete = old and current and same and same_browser and same_adapter and all(s.quality in {"ok", "visual"} for s in (before, after)) and not any(s.document.get("communication", {}).get("truncated") for s in (before, after))
    if not complete:
        output["status"] = "partial"
        if any(s.quality not in {"ok", "visual"} for s in (before, after)):
            output["reason"] = "Jeden z odczytów jest częściowy; nie ustalono zmian komunikacji."
        elif not old:
            output["reason"] = "Starszy skan zapisał wybrane teksty, bez pełnego zestawu nagłówków i banerów. Zgodne fragmenty nie oznaczają braku zmian na całej stronie."
        else:
            output["reason"] = "Niezgodny adres, zakres, przeglądarka lub niepełny zapis komunikacji; nie ustalono zmian."
        return output, []
    # Compare inventories first. Reordered sections and a different active slide
    # do not establish a campaign change if the same messages remain present.
    first = {(e["role"], e["text"]): e for e in old}
    second = {(e["role"], e["text"]): e for e in current}
    removed = [first[k] for k in sorted(first.keys() - second.keys())]
    added = [second[k] for k in sorted(second.keys() - first.keys())]
    pairs = []
    for a in list(removed):
        options = [b for b in added if a["role"] == b["role"]]
        b = next((b for b in options if a.get("key") and a["key"] == b.get("key")), None)
        if b is None and options:
            closest = max(options, key=lambda b: SequenceMatcher(None, a["text"], b["text"]).ratio())
            if SequenceMatcher(None, a["text"], closest["text"]).ratio() >= .65:
                b = closest
        if b is not None:
            removed.remove(a)
            added.remove(b)
            pairs.append((a, b))
    pairs += [(a, None) for a in removed] + [(None, b) for b in added]
    changes = []
    for a, b in pairs:
        old_value, new_value = a["text"] if a else "", b["text"] if b else ""
        # Pure price changes belong to the separate price module.
        if a and b and MONEY.sub("[kwota]", old_value) == MONEY.sub("[kwota]", new_value):
            continue
        item = b or a
        key = "communication:" + hashlib.sha256(repr((item["role"], old_value, new_value)).encode()).hexdigest()[:16]
        changes.append(Change("changed" if a and b else "added" if b else "removed", category(old_value, new_value), ROLES.get(item["role"], "Treść"), old_value or None, new_value or None, before.observed_at, after.observed_at, (b or {}).get("url") or after.url, after.scenario, field_key=key, details={"communication": True, "role": item["role"], "basis": "Dwa zapisy tego samego zakresu komunikacji; porównano zestaw komunikatów, nie aktywny slajd"}))
    output.update(status="changed" if changes else "unchanged", comparable=True, changes=len(changes), reason="", shared_unchanged=len(first.keys() & second.keys()), fragments_before=len(old))
    return output, changes
