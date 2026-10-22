"""Compare recorded communication independently of price extraction versions.

Unknown legacy extracts can establish agreement of shared fragments, never a
campaign launch/removal. Only two captures of this contract establish changes.
"""

from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from urllib.parse import urlsplit

from .extract import MONEY, canonical_url, money_text, normalize
from .model import Change, Snapshot

CONTRACT = "communication-v1"
NOISE = re.compile(r"cookies|ciastecz|polity[kc].{0,12}prywatno|ustawienia prywatno|privacy policy|privacy settings|danych osobowych|wyrażam zgod|przetwarzani.*danych|rodo\b|sales intelligence|digitree|^\[licznik\]$", re.I)
ROLES = {"heading": "Nagłówek", "banner": "Baner", "cta": "Wezwanie do działania", "text": "Treść", "image": "Źródło grafiki w zestawie banerów"}
COUNTDOWN = re.compile(r"(?:\d+\s*(?:dni|dzień|days?)\s*)?(?:\d+\s*(?:godz\.?|h)\s*\d+\s*min\.?\s*\d+\s*(?:sek\.?|s)(?!\w)|\d{1,2}\s*:\s*\d{1,2}\s*:\s*\d{1,2}(?!\d))", re.I)
# Some timers put each unit in a separate span. Match a whole fragment only:
# delivery promises such as "Wysyłka w 24 godz." remain meaningful copy.
TIMER_FRAGMENT = re.compile(r"^\d+\s*(?:godz\.?|min\.?|sek\.?)$", re.I)


def clean(value: str, patterns: list[str] | None = None) -> str:
    value = normalize(value, patterns)
    # DOM text often joins cells as "02 dni01 godz.53 min.14 sek.". Mask only
    # the ticking duration, keeping discounts, copy and absolute end dates.
    value = COUNTDOWN.sub("[licznik]", value)
    if TIMER_FRAGMENT.fullmatch(value):
        return ""
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
                          ("dodatki", r"gratis|bezpłat|za darmo|\bdodat(?:ek|ki|ków|ku|kiem|kami|kach|kowe|kowy|kowa|kową|kowych|kowego|kowej)\b|kosztorys"),
                          ("pakiety", r"pakiet|w cenie"),
                          ("warunki", r"dostaw|wysył|termin|zwrot|gwaranc"),
                          ("funkcje", r"konfigur|kalkulator|personaliz")]:
        if re.search(pattern, text, re.I):
            return name
    return "komunikacja"


def stable_element_key(key: str) -> bool:
    """A DOM position is a slot, not an identity for its current text."""
    return bool(key) and ":nth-" not in key and " > " not in key


def pair_candidate(item: dict, options: list[dict]) -> dict | None:
    matching = next((other for other in options if item.get("key") == other.get("key")), None)
    if matching is not None:
        if stable_element_key(item.get("key", "")) or SequenceMatcher(None, item["text"], matching["text"]).ratio() >= .65:
            return matching
    # For positional selectors, the content must corroborate a match. Otherwise
    # report separate inventory additions/removals rather than an invented edit.
    if options:
        closest = max(options, key=lambda other: SequenceMatcher(None, item["text"], other["text"]).ratio())
        if SequenceMatcher(None, item["text"], closest["text"]).ratio() >= .65:
            return closest
    return None


def supporting_reason(snapshot: Snapshot, item: dict | None) -> str:
    """Annotate only source-backed peripheral inventory, keeping the records."""
    if not item:
        return ""
    key = item.get("key", "").removeprefix("body > ")
    if key == "#similar-projects" or key.startswith("#similar-projects > "):
        return "Element sekcji podobnych projektów; nie dotyczy stałej karty projektu."
    if re.search(r"(?:^| > )project-list:nth-of-type\(\d+\) > ", key):
        return "Element zapisanej listy projektów; obserwacja katalogu."
    if snapshot.domain == "kreodom.pl" and re.match(r"#projects-tab\d+ > ", key):
        return "Element zakładki katalogu projektów; nie zmiana oferty stałego projektu."
    # This footer-like section has no <footer> tag. Its exact structure was
    # verified against the retained keys and the source HTML for this site.
    if (snapshot.domain == "dobredomy.pl" and snapshot.page == "projekt"
            and key.startswith("section:nth-of-type(8) > div:nth-of-type(2) > div:nth-of-type(1) > ")
            and item.get("role") == "cta"):
        return "Link w katalogowej stopce Dobrych Domów; nie zmiana oferty stałego projektu."
    for control in snapshot.document.get("payload", {}).get("controls", []):
        if control.get("selector", "").removeprefix("body > ") != key:
            continue
        href = control.get("href", "")
        target, current = urlsplit(href), urlsplit(snapshot.url)
        if (target.hostname and target.hostname.removeprefix("www.") == (current.hostname or "").removeprefix("www.")
                and canonical_url(href).rstrip("/") != canonical_url(snapshot.url).rstrip("/")
                and re.search(r"/(?:projekt/[^/]+|projekt-domu-[^/]+|projekty/[^/]+)", target.path)):
            return "Zapisany link prowadzi do innego projektu lub katalogu; nie do stałej karty."
    return ""


def ticking_activity(before: str, after: str) -> bool:
    activity = r"\b(?:odsłon(?:a|y)?(?: projektu)?|os(?:ób|oby|oba)\s+przegląda|przegląda(?:ją)?\s+(?:ten\s+)?projekt)"
    return bool(before and after and before != after and re.search(activity, before, re.I)
                and re.sub(r"\d+", "[liczba]", before) == re.sub(r"\d+", "[liczba]", after))


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
    output["same_visible_image"] = bool(same and same_browser and before.quality in {"ok", "visual"} and after.quality in {"ok", "visual"} and re.fullmatch(r"images/[a-f0-9]{64}\.(?:png|webp)", before.image) and before.image == after.image)
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
        b = pair_candidate(a, options)
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
        details = {
            "communication": True, "role": item["role"],
            "unmatched": not (a and b),
            "element_before": (a or {}).get("key", ""), "element_after": (b or {}).get("key", ""),
            "pairing": "identity" if a and b and a.get("key") == b.get("key") and stable_element_key(a.get("key", "")) else "similarity" if a and b else "inventory",
            "basis": "Dwa zapisy tego samego zakresu komunikacji; porównano zestaw komunikatów, nie aktywny slajd",
        }
        supporting = supporting_reason(before, a) or supporting_reason(after, b)
        if ticking_activity(old_value, new_value):
            supporting = "Zmieniła się wyłącznie liczba odsłon lub oglądających; treść komunikatu pozostała taka sama."
        if supporting:
            details["supporting_reason"] = supporting
        kind = "changed" if a and b else "added" if b else "removed"
        change_category = category(old_value, new_value)
        if item["role"] == "image":
            # A CDN deployment may change every URL while keeping all pixels.
            # Keep the observation, without inferring a new feature/campaign
            # from an accessible caption such as "Konfigurator domu".
            kind, change_category = "review", "obraz"
            details.update(
                communication_asset=True, specific=False,
                description="Zmiana adresu pliku grafiki; wygląd niepotwierdzony",
                basis="Zapisano różne adresy plików. Sam adres ani opis grafiki nie potwierdza zmiany wyglądu lub oferty.",
                asset_before=(a or {}).get("asset", ""), asset_after=(b or {}).get("asset", ""),
            )
        changes.append(Change(kind, change_category, ROLES.get(item["role"], "Treść"), old_value or None, new_value or None, before.observed_at, after.observed_at, (b or {}).get("url") or after.url, after.scenario, field_key=key, details=details))
    asset_reviews = sum(bool(change.details.get("communication_asset")) for change in changes)
    supporting_reviews = sum(bool(change.details.get("supporting_reason")) and not change.details.get("communication_asset") for change in changes)
    copy_changes = len(changes) - asset_reviews - supporting_reviews
    output.update(status="changed" if copy_changes else "unchanged", comparable=True, changes=copy_changes, asset_reviews=asset_reviews, supporting_reviews=supporting_reviews, reason="", shared_unchanged=len(first.keys() & second.keys()), fragments_before=len(old))
    return output, changes
