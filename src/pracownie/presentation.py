"""Business-facing views; raw browser traces live in the diagnostic report."""

from __future__ import annotations

import csv
import html
import io
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal
from difflib import SequenceMatcher
from importlib.resources import files
from urllib.parse import urlsplit

from .communication import COUNTDOWN
from .extract import MONEY, amount, money_text, normalize
from .journal import build_journal, render_journal_html
from .management import (
    brief,
    build_management,
    business_highlights,
    communication_summary,
    page_finding,
    render_availability,
    render_business_change,
    render_business_proofs,
    render_communication_table,
    render_management,
    render_quality_panel,
)
from .model import WARSAW, Result
from .offers import price_delta

SALES = {"ceny", "promocje", "dodatki", "pakiety", "warunki", "funkcje", "parametry", "komunikacja", "tresc"}
TITLES = {
    "ceny": "Cena",
    "promocje": "Promocja",
    "dodatki": "Dodatki",
    "pakiety": "Pakiet",
    "warunki": "Warunki zakupu",
    "funkcje": "Funkcjonalność",
    "komunikacja": "Komunikat",
    "parametry": "Parametry projektu",
    "tresc": "Treść strony",
}
NOISE = re.compile(
    r"cookies|ciastecz|danych osobowych|sales intelligence|digitree|zarządzaj zgod|^\[licznik\]$", re.I
)


def technical_reason(event: dict) -> str:
    if "reguły odczytu" in event.get("note", ""):
        return "method"
    if event.get("label") == "Termin ceny w metadanych":
        return "metadata"
    return ""


def assessment(view: dict) -> dict:
    """Business conclusions, bounded by genuinely comparable observations."""
    domains = set(view["comparison"]["price_domains"])
    prices = [r for r in view["rows"] if r["domain"] in domains]
    reasons = Counter(technical_reason(e) for r in view["rows"] for e in r["reviews"])
    total = view["counts"]["domains"]
    unchanged = sum(Decimal(r["delta"]) == 0 for r in prices)
    lines = [communication_summary(view)]
    lines.append("Ceny są miarą dodatkową i nie określają zakresu monitorowania komunikacji. Brak porównywalnego zapisu nie oznacza braku zmian.")
    if reasons["method"] or reasons["metadata"]:
        lines.append(f"Problemy danych: {reasons['method']} niejednoznacznych różnic po zmianie sposobu odczytu; {reasons['metadata']} różnic metadanych bez potwierdzenia w widocznej ofercie.")
        lines.append("Nie masz niczego potwierdzać. Te problemy wymagają naprawy po stronie monitora i nie są ustalonymi zmianami ofert.")
    limited = len(prices) < total or bool(sum(reasons.values())) or view["counts"]["missing"] > 0
    return {"title": "Zakres porównania komunikacji" if limited else "Wynik w sprawdzonym zakresie", "lines": lines, "prices": len(prices), "unchanged": unchanged, "uncompared": total - len(prices)}


def money(offer: dict) -> str:
    if not offer:
        return "—"

    def number(value):
        return f"{Decimal(value):,.2f}".replace(",", " ").replace(".", ",")

    currency = "zł" if offer.get("currency") == "PLN" else offer.get("currency", "")
    suffix = (" netto + VAT" if offer.get("tax") == "net" else " brutto" if offer.get("tax") == "gross" else "") + (" / lokal" if offer.get("unit") == "lokal" else "")
    if offer.get("quality") == "partial":
        suffix += " *"
    if offer.get("kind") == "range":
        return f"{number(offer['low'])}–{number(offer['high'])} {currency}{suffix}"
    return f"{number(offer['amount'])} {currency}{suffix}"


def when(value: str | None, short: bool = False) -> str:
    if not value:
        return "brak odczytu"
    return (
        datetime.fromisoformat(value)
        .astimezone(WARSAW)
        .strftime("%d.%m %H:%M" if short else "%d.%m.%Y %H:%M")
    )


def issue_text(value: str) -> str:
    if not value:
        return ""
    if "ERR_CONNECTION_REFUSED" in value:
        return "Serwer odmówił połączenia."
    if "ERR_CERT" in value or "SSL" in value:
        return "Witryna ma nieprawidłowy certyfikat dla tego adresu."
    if "403" in value:
        return "Witryna blokuje dostęp ze skanera (403)."
    if "429" in value:
        return "Witryna ogranicza liczbę odczytów (429)."
    if "Nie ustalono karty" in value:
        return "Nie ustalono poprawnej karty projektu."
    if "pust" in value.lower() or "dokumentu HTML" in value or "null" in value:
        return "Witryna nie zwróciła czytelnej treści strony."
    if "Wyczerpano czas skanu" in value:
        return "Nie ukończono odczytu domeny przed końcem skanu."
    if "czas domeny" in value and ("/podstawowy" in value or "odczyt strony" in value):
        return "Nie ukończono odczytu strony w limicie czasu domeny."
    if "czas domeny" in value or "Wyczerpano czas" in value:
        return "Nie ukończono dodatkowych interakcji w limicie czasu."
    if "Timeout" in value or "TIMED_OUT" in value:
        return "Strona lub kontrolka nie odpowiedziała w limicie czasu."
    return value.splitlines()[0][:180]


def _brief(value: str | None, limit: int = 260) -> str:
    if value is None:
        return "brak"
    value = normalize(value)
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _amount_key(value: str | None) -> str:
    if value:
        match = MONEY.search(money_text(value))
        if match:
            return str(amount(match[1])) + " " + match[2].casefold().replace("zł", "pln")
    return normalize(value or "")


def _event(change, result: Result) -> dict:
    old, new = change.before, change.after
    if old and new and "\n" in old + new:
        before_lines, after_lines = set(old.splitlines()), set(new.splitlines())
        old = " · ".join(sorted(before_lines - after_lines)) or None
        new = " · ".join(sorted(after_lines - before_lines)) or None
    role = (
        "regular"
        if "poprzednia" in change.label.lower()
        else "lowest30"
        if "najniższa" in change.label.lower()
        else "current"
    )
    label = TITLES.get(change.category, change.label)
    if change.details.get("communication"):
        label = change.label
    if change.category == "ceny":
        label = (
            "Cena regularna"
            if role == "regular"
            else "Najniższa cena z 30 dni"
            if role == "lowest30"
            else "Cena"
        )
    context = (
        result.scenario_label
        if result.scenario not in {"podstawowy"}
        else "Karta projektu"
        if result.page == "projekt"
        else "Strona główna"
    )
    if result.scenario != "podstawowy":
        context = ("Karta projektu" if result.page == "projekt" else "Strona główna") + " · " + context
    return {
        "category": change.category,
        "field_key": change.field_key,
        "label": label,
        "context": context,
        "variant": result.variant,
        "before": _brief(old),
        "after": _brief(new),
        "delta": change.delta,
        "percent": change.percent,
        "review": change.kind == "review",
        "kind": change.kind,
        "source": change.url,
        "before_at": change.before_at,
        "after_at": change.after_at,
        "evidence": change.evidence or result.evidence,
        "role": role,
        "page": result.page,
        "scenario": result.scenario,
        "note": "Zmieniono reguły odczytu lub przeglądarkę. Nie ustalono, czy różnica dotyczy oferty; problem wymaga naprawy po stronie monitora." if "reguły odczytu" in change.note else change.note.strip(),
        "before_full": old,
        "after_full": new,
        "basis": change.details.get("basis", ""),
        "communication_role": change.details.get("role", ""),
        "unmatched": change.details.get("unmatched", False),
        "supporting_reason": change.details.get("supporting_reason", ""),
        "commercial_check": change.details.get("commercial_check", {}),
    }


def page_comparison(day: str, page: str, base: Result | None, entries: list[Result], row: dict) -> dict:
    events = [e for e in row["events"] if e["page"] == page]
    reviews = [e for e in row["reviews"] if e["page"] == page]
    visuals = [v for v in row["visuals"] if v["page"] == page]
    migrations = sum("reguły odczytu" in c.note for r in entries if r.page == page for c in r.changes)
    before_at = base.compared_at if base else None
    gap = (date.fromisoformat(day) - datetime.fromisoformat(before_at).astimezone(WARSAW).date()).days if before_at else None
    current_read = bool(base and base.observed_at and datetime.fromisoformat(base.observed_at).astimezone(WARSAW).date().isoformat() == day)
    communication = dict(base.communication) if base else {}
    communication["daily"] = gap == 1 and current_read and bool(communication.get("comparable"))
    if not current_read:
        communication.update(status="missing", label="Brak odczytu", ready=False)
    elif gap is not None and gap > 1:
        communication.update(status="gap", label=f"Luka {gap} dni · brak porównania z wczoraj")
    elif communication.get("comparable") and gap == 1:
        communication["label"] = f"Zmiany komunikacji: {communication['changes']}" if communication["changes"] else "Bez zmian w zapisanej komunikacji"
    elif communication.get("same_visible_image") and gap == 1:
        communication["label"] = "Zrzut bez różnic · zakres częściowy"
    elif communication.get("status") == "partial" and communication.get("shared_unchanged"):
        communication["label"] = f"Częściowe · {communication['shared_unchanged']} zgodnych tekstów"
    elif communication.get("status") == "partial":
        communication["label"] = "Niepełny zakres porównania"
    else:
        communication["label"] = "Pierwszy zapis · brak porównywalnej bazy"
    if not current_read:
        status, label = "missing", "Brak bieżącego odczytu"
    elif events:
        status, label = "changed", f"Zmiany: {len(events)}"
    elif reviews:
        status, label = "review", f"Nie ustalono zmian: {len(reviews)} niejednoznacznych różnic odczytu"
    elif not before_at:
        status, label = "baseline", "Pierwszy odczyt — zapisano punkt odniesienia"
    elif migrations:
        status, label = "review", "Zmieniono reguły odczytu — porównanie ograniczone"
    elif base.data_quality != "ok":
        status, label = "review", "Odczyt częściowy — porównanie ograniczone"
    elif visuals:
        status, label = "visual", "Różnica obrazu do oceny"
    else:
        status, label = "unchanged", "Bez zmian w odczytanym zakresie"
    return {
        "page": page, "label": "Strona główna" if page == "glowna" else "Karta projektu",
        "url": base.url if base and (page != 'projekt' or row['project_selected']) else "", "status": status, "status_label": label,
        "observed_at": base.observed_at if base else None, "compared_at": before_at,
        "gap_days": gap, "daily": gap == 1 and current_read,
        "current_read": current_read, "data_quality": base.data_quality if base else "unknown",
        "error_text": issue_text(base.error) if base and base.error else issue_text(next((r.error for r in entries if r.page == "zakres" and r.error), "")) if not current_read else "",
        "quality_notes": [issue_text(w) for w in base.warnings] if base else [],
        "events": events, "reviews": reviews, "visuals": visuals,
        "evidence": base.evidence if base else {}, "extraction_changes": migrations,
        "communication": communication,
    }


def scan_comparison(day: str, rows: list[dict]) -> dict:
    yesterday = (date.fromisoformat(day) - timedelta(days=1)).isoformat()

    def observed_day(value):
        return datetime.fromisoformat(value).astimezone(WARSAW).date().isoformat() if value else None

    pairs = [p for r in rows for p in r["pages"] if observed_day(p["compared_at"]) == yesterday and observed_day(p["observed_at"]) == day]
    return {
        "before_day": yesterday, "after_day": day,
        "paired_home": sum(p["page"] == "glowna" for p in pairs),
        "paired_project": sum(p["page"] == "projekt" for p in pairs),
        "paired_pages": len(pairs),
        "screenshot_pairs": sum(all(p["evidence"].get(key) for key in ["przed", "po"]) for p in pairs),
        "price_domains": [r["domain"] for r in rows if r["delta"] is not None and observed_day(r["previous"].get("observed_at")) == yesterday and observed_day(r["current"].get("observed_at")) == day],
        "review_events": sum(len(r["reviews"]) for r in rows),
    }


def build_view(day: str, results: list[Result], metadata: dict, selections: dict, domains: list[str]) -> dict:
    rows = []
    for domain in domains:
        # Prefer the primary, verified observation when an interaction repeats
        # the same message. Alphabetical scenario order otherwise keeps cart
        # observations first and loses the verification attached to the page.
        entries = sorted((r for r in results if r.domain == domain), key=lambda r: r.scenario != 'podstawowy')
        home = next((r for r in entries if r.page == "glowna" and r.scenario == "podstawowy"), None)
        project = next((r for r in entries if r.page == "projekt" and r.scenario == "podstawowy"), None)
        selected = selections.get(domain, {})
        current = project.offer if project else {}
        previous = project.before_offer if project else {}
        delta, percent = price_delta(previous, current)
        if project and any(c.kind == "review" and c.field_key == current.get("field_key") for c in project.changes):
            delta, percent = None, None
        row = {
            "domain": domain,
            "name": selected.get("name") or domain,
            "url": selected.get("url") or (project.url if project else ""),
            "project_selected": bool(selected.get('url') or (project and project.observed_at)),
            "home_read": bool(home and home.observed_at and datetime.fromisoformat(home.observed_at).astimezone(WARSAW).date().isoformat() == day),
            "project_read": bool(project and project.observed_at and datetime.fromisoformat(project.observed_at).astimezone(WARSAW).date().isoformat() == day),
            "current": current,
            "previous": previous,
            "current_text": money(current),
            "previous_text": money(previous),
            "delta": delta,
            "percent": percent,
            "events": [],
            "reviews": [],
            "visuals": [],
            "issues": [],
            "observed_at": project.observed_at if project else None,
            "compared_at": project.compared_at if project else None,
            "migration": False,
            "evidence": project.evidence if project else {},
        }
        if delta is not None and Decimal(delta) != 0:
            row["events"].append(
                {
                    "category": "ceny",
                    "label": "Cena projektu",
                    "context": "Karta projektu",
                    "variant": "",
                    "before": money(previous),
                    "after": money(current),
                    "delta": delta,
                    "percent": percent,
                    "review": False,
                    "source": row["url"],
                    "before_at": previous.get("observed_at"),
                    "after_at": current.get("observed_at"),
                    "evidence": project.evidence,
                    "role": "current",
                    "page": "projekt",
                    "scenario": "podstawowy",
                    "note": "", "before_full": money(previous), "after_full": money(current),
                }
            )
        keys = set()
        for result in entries:
            if result.scenario == "podstawowy" and not result.observed_at and result.error:
                row["issues"].append(
                    ("Strona główna" if result.page == "glowna" else "Karta projektu")
                    + ": "
                    + issue_text(result.error)
                )
            for change in result.changes:
                if change.before and change.after and COUNTDOWN.sub("[licznik]", change.before) == COUNTDOWN.sub("[licznik]", change.after):
                    # Older categorized fields may still contain a timer even
                    # when no full communication inventory was recorded.
                    continue
                if result.communication.get("comparable") and change.field_key.startswith("tekst:"):
                    # Dedicated copy inventory replaces the older categorized
                    # blocks, avoiding duplicate or parser-version alerts.
                    continue
                if change.category == "obraz":
                    if change.details.get("communication_asset"):
                        # Asset URL inventory is retained in raw changes. It
                        # cannot replace a measured screenshot difference.
                        continue
                    if result.scenario == "podstawowy" and not any(
                        v["page"] == result.page for v in row["visuals"]
                    ):
                        row["visuals"].append(
                            {
                                "page": result.page,
                                "evidence": change.evidence or result.evidence,
                                "source": result.url,
                                "before_at": change.before_at or result.compared_at,
                                "after_at": change.after_at or result.observed_at,
                                "details": change.details,
                                "scenario": result.scenario,
                                "unreliable": change.details.get("unreliable",False) or result.data_quality not in {"ok", "visual"} or any(re.search(r"niezaładowane|widoczny panel cookies", warning, re.I) for warning in result.warnings) or bool(re.search(r"cookies|ciastecz|prywatno|consent",str(change.details.get("ocr",{})),re.I)),
                            }
                        )
                    continue
                if change.category not in SALES:
                    continue
                if change.category == "ceny" and "pierwotna cena" in change.label.casefold() and "aktualna cena" in change.label.casefold():
                    # A parent block repeats regular/current amounts and their
                    # accessible labels. Use individual prices and the quote.
                    continue
                if NOISE.search((change.before or "") + " " + (change.after or "")):
                    continue
                if "reguły odczytu" in change.note:
                    row["migration"] = True
                    # New/disappearing extraction keys cannot establish a site
                    # change. Matched before/after values remain inspectable.
                    if change.before is None or change.after is None:
                        continue
                if change.delta is not None and Decimal(change.delta) == 0:
                    continue
                event = _event(change, result)
                if change.field_key.endswith(":priceValidUntil"):
                    event["review"] = True
                    event["label"] = "Termin ceny w metadanych"
                    event["note"] = "Termin w metadanych może być aktualizowany automatycznie. Nie ustalono zmiany terminu w widocznej ofercie."
                if event["before"] == event["after"]:
                    continue
                if (
                    change.category == "ceny"
                    and not result.variant
                    and result.page == "projekt"
                    and event["role"] == "current"
                    and delta is not None
                    and change.delta == delta
                ):
                    continue
                key = (
                    result.page,
                    result.variant,
                    change.category,
                    event["role"],
                    _amount_key(change.before) if change.category == "ceny" else normalize(change.before or ""),
                    _amount_key(change.after) if change.category == "ceny" else normalize(change.after or ""),
                )
                if key in keys:
                    continue
                keys.add(key)
                event["technical"] = technical_reason(event)
                row["reviews" if event["review"] else "events"].append(event)
        for retry in [r for r in entries if r.scenario == "ponowienie-podstawowego" and r.error]:
            original = home if retry.page == "glowna" else project
            row["issues"].append(("Strona główna" if retry.page == "glowna" else "Karta projektu") + ": ponowienie nie powiodło się (" + issue_text(retry.error) + "). Zachowano " + ("częściowy" if original and original.data_quality != "ok" else "poprawny") + " odczyt z " + when(original.observed_at if original else None) + ".")
        failed_options = [r for r in entries if r.scenario not in {"podstawowy", "ponowienie-podstawowego"} and r.error]
        if failed_options:
            row["issues"].append(
                f"Dodatkowe interakcje: {len(failed_options)} nieukończonych prób; szczegóły w diagnostyce."
            )
        limited = [
            r
            for r in entries
            if r.page == "zakres" and r.error or r.scenario == "pokrycie-interakcji" and r.warnings
        ]
        if limited and not failed_options:
            row["issues"].append("Nie ukończono odczytów podstawowych w limicie domeny; zachowano dostępne materiały." if any("/podstawowy" in (r.error or "") for r in limited) else "Dodatkowe interakcje sprawdzone częściowo; szczegóły w diagnostyce.")
        if project and project.observed_at and project.data_quality == "partial":
            row["issues"].append("Karta odczytana częściowo; cena nie służy do ustalania zmiany oferty.")
        row["issues"] = list(dict.fromkeys(row["issues"]))
        row["pages"] = [page_comparison(day, page, base, entries, row) for page, base in [("glowna", home), ("projekt", project)]]
        if not row["home_read"] or not row["project_read"]:
            row["status"], row["status_label"] = "missing", "Brak pełnego odczytu stron"
        elif row["events"]:
            row["status"], row["status_label"] = "changed", "Zmiana oferty"
        elif row["reviews"]:
            row["status"], row["status_label"] = "review", "Nie ustalono zmian — odczyt niejednoznaczny"
        elif row["visuals"]:
            row["status"], row["status_label"] = "visual", "Obraz do oceny"
        elif any(p["status"] == "review" for p in row["pages"]):
            row["status"], row["status_label"] = "review", "Porównanie ograniczone"
        elif any(p["status"] == "baseline" for p in row["pages"]):
            row["status"], row["status_label"] = "baseline", "Pierwszy odczyt"
        else:
            row["status"], row["status_label"] = "unchanged", "Bez zmian w odczytanym zakresie"
        rows.append(row)
    journal = build_journal(day, rows)
    view = {
        "day": day,
        "metadata": metadata,
        "rows": rows,
        "comparison": scan_comparison(day, rows),
        "journal": journal,
        "counts": {
            "domains": len(rows),
            "home": sum(r["home_read"] for r in rows),
            "project": sum(r["project_read"] for r in rows),
            "prices": sum(bool(r["current"]) for r in rows),
            "price_pairs": sum(r["delta"] is not None for r in rows),
            "changed": sum(bool(r["events"]) for r in rows),
            "events": sum(len(r["events"]) for r in rows),
            "review": sum(bool(r["reviews"]) for r in rows),
            "visual": sum(bool(r["visuals"]) for r in rows),
            "missing": sum(not r["home_read"] or not r["project_read"] for r in rows),
            "daily_pages": sum(p["daily"] and bool(p["observed_at"]) for r in rows for p in r["pages"]),
            "journal": len(journal),
            "visual_changes": sum(e["category"] == "obraz" for e in journal),
        },
        "categories": dict(Counter(e["category"] for r in rows for e in r["events"])),
    }
    view["management"] = build_management(view)
    return view


def _delta_text(row: dict) -> str:
    if row["delta"] is None:
        return "brak porównywalnej ceny" if row["current"] else "brak ceny w odczycie"
    value = Decimal(row["delta"])
    if not value:
        return "bez zmiany ceny"
    return ("spadek " if value < 0 else "wzrost ") + f"{abs(value):.2f} ({row['percent'] or '—'}%)"


def render_text(view: dict) -> str:
    from .briefing import build_briefing, delivery_text

    c = view["counts"]
    pair = view["comparison"]
    briefing = build_briefing(view)
    brief_lines = [f"ODPRAWA DNIA — {pair['before_day']} → {pair['after_day']}",
                   f"Porównano obie strony: {len(briefing['complete_domains'])}/{briefing['total']} pracowni.",
                   delivery_text(view), ""]
    for tier, label in [('main', 'NAJWAŻNIEJSZE ZMIANY'), ('review', 'WAŻNE DO SPRAWDZENIA')]:
        brief_lines += [label]
        for event in briefing['events']:
            if event['tier'] == tier:
                brief_lines += [event['domain'] + ' | ' + event['sentence'] + ' | ' + event['confidence'], event['lead']['source']]
        brief_lines += ['']
    lines = brief_lines + [
        f"KOMUNIKACJA PRACOWNI — {view['day']}",
        assessment(view)["title"].upper(),
        *assessment(view)["lines"],
        "",
        f"Zakończenie odczytu: {when(view['metadata']['finished_at'])} (czas polski)",
        f"Podłączone skany: {pair['before_day']} → {pair['after_day']}. Pary odczytów: {pair['paired_home']} stron głównych + {pair['paired_project']} kart; pary zrzutów: {pair['screenshot_pairs']}.",
        "",
        f"Odczyt: {c['home']}/{c['domains']} stron głównych; {c['project']}/{c['domains']} kart projektów.",
        f"Ceny ustalone: {c['prices']}; porównywalne pary cen: {c['price_pairs']}. Potwierdzone zmiany ofert: {c['events']} w {c['changed']} domenach.",
        f"Brak pełnego odczytu stron: {c['missing']} domen. Obrazy do oceny: {c['visual']} domen.",
        "",
        "DIAGNOSTYKA I PEŁNE ZAPISY",
        "",
    ]
    management = build_management(view)
    journal = management["items"]
    table = ["DZIENNA TABELA ZMIAN", "Dzień | Pracownia | Strona | Kontekst / wariant | Rodzaj | Co się zmieniło | Było | Jest | Źródło"]
    for item in journal:
        table.append(" | ".join(str(item[k]).replace("\n", " · ") for k in ["day", "domain", "page", "context", "type", "description", "before", "after", "source"]))
    if not journal:
        table.append("Nie ustalono konkretnych zmian dzień do dnia w sprawdzonym zakresie. Zobacz kompletność danych powyżej.")
    lines.extend([communication_summary(view), ""])
    lines.extend(f"{b['label']}: {b['domains']} pracowni ze zmianą" for b in management['business_buckets'])
    lines.extend(["", "ZMIANY OFERTY I KOMUNIKACJI — SKRÓT", "Pracownia | Strona | Zmiana | Było | Jest | Źródło"])
    for item in business_highlights(journal):
        lines.append(" | ".join([item['domain'], 'Strona główna' if item['page'] == 'glowna' else 'Stała karta projektu', item['description'], brief(item['before'], 240), brief(item['after'], 240), item['source']]))
    lines.extend(["", "Pełne porównania, treści i powtórzenia zachowano poniżej.", "", *table, ""])
    lines.extend(["KOMUNIKACJA — WSZYSTKIE PRACOWNIE", "Pracownia | Strona główna | Karta projektu"])
    for row in view["rows"]:
        lines.append(" | ".join([row["domain"], *[p["communication"]["label"] + ("; nowa baza gotowa" if p["communication"].get("ready") and p["current_read"] else "") + "; " + p["url"] for p in row["pages"]]]))
    lines.append("")
    events = [(r, e) for r in view["rows"] for e in r["events"]]
    if not events:
        lines.append("Brak potwierdzonych zmian sprzedażowych w poprawnie porównanym zakresie.")
    for row, event in events:
        lines.extend(
            [
                f"{row['domain']} — {event['label']} ({event['context']})",
                f"  {event['before']} → {event['after']}",
                f"  Źródło: {event['source']}",
            ]
        )
    if management["secondary"]:
        lines.extend(["", "ARCHIWUM RÓŻNIC OBRAZU I PORÓWNAŃ PO LUCE", "Sam zmieniony zrzut nie ustala nowej promocji ani przebudowy witryny."])
        for item in management["secondary"]:
            lines.append(" | ".join(str(item[k]).replace("\n", " · ") for k in ["domain", "page", "description", "before_at", "after_at", "source"]))
    reviews = [(r, e) for r in view["rows"] for e in r["reviews"] if not technical_reason(e)]
    if reviews:
        lines.extend(["", "NIEZWERYFIKOWANE RÓŻNICE ODCZYTU", ""])
        for row, event in reviews[:15]:
            description = f"{event['before']} → {event['after']}"
            if event["delta"]:
                direction = "spadek" if Decimal(event["delta"]) < 0 else "wzrost"
                description += f"; {direction} o {abs(Decimal(event['delta'])):.2f}"
            lines.append(f"NIE USTALONO ZMIANY OFERTY: {row['domain']} — {event['label']}: {description}")
        if len(reviews) > 15:
            lines.append(f"Pozostałe {len(reviews) - 15} obserwacji: raport HTML i dane JSON.")
    lines.extend(["", "CENY PROJEKTÓW — POPRZEDNI ODCZYT → DZISIAJ", ""])
    for row in view["rows"]:
        lines.append(
            f"{row['domain']} | {row['name']} | {row['previous_text']} → {row['current_text']} | {_delta_text(row)}"
        )
    lines.extend(["", "SZCZEGÓŁY WEDŁUG DOMEN", ""])
    for row in view["rows"]:
        lines.append(f"{row['domain']} — {row['status_label']}")
        for page in row["pages"]:
            lines.append(f"  {page['label']}: {page['status_label']}")
            lines.append(f"    Porównanie: {when(page['compared_at'])} → {when(page['observed_at'])}")
            if page["gap_days"] and page["gap_days"] > 1:
                lines.append(f"    Luka {page['gap_days']} dni; to nie jest porównanie z wczoraj.")
            for event in page["events"] + page["reviews"]:
                lines.extend([
                    f"    {'NIEZWERYFIKOWANY ODCZYT: ' if event['review'] else ''}{event['label']} ({event['context']})",
                    f"      PRZED ({when(event['before_at'])}): {event.get('before_full') or event['before']}",
                    f"      PO ({when(event['after_at'])}): {event.get('after_full') or event['after']}",
                    f"      Źródło: {event['source']}",
                ])
                if event.get("note"):
                    lines.append("      Ocena: " + event["note"])
            if page["evidence"]:
                lines.append("    Zrzuty: " + "; ".join(f"{name}: {path}" for name, path in page["evidence"].items() if name in {"przed", "po"}))
        for issue in row["issues"]:
            lines.append("  " + issue)
        if row["migration"]:
            lines.append(
                "  Zmieniono reguły odczytu; nie ustalono zmian oferty. Niejednoznaczne zapisy zachowano do naprawy monitora."
            )
        for visual in row["visuals"]:
            lines.append(
                "  Obraz do oceny: " + ("strona główna" if visual["page"] == "glowna" else "karta projektu")
            )
        if row["evidence"]:
            lines.append(
                "  Dowody: "
                + "; ".join(
                    f"{name}: {path}"
                    for name, path in row["evidence"].items()
                    if name in {"przed", "po", "roznice"}
                )
            )
    lines.extend(
        [
            "",
            "JAK CZYTAĆ RAPORT",
            "Cena poprzednio pochodzi z ostatniego poprawnego odczytu sprzed dnia raportu. Brak danych nie oznacza ceny 0 zł ani braku zmian.",
            "* Cena z dokładnego pola projektu przy częściowym odczycie strony. Odczyt niepewny; nie wyliczamy z niego zmiany ceny.",
            "W ZIP otwórz folder dnia i index.html: tabela ma wyszukiwanie, filtry oraz zrzuty przed/po. oferty.csv zawiera ceny do arkusza.",
            "Surowe komunikaty przeglądarki i pełny zakres interakcji: diagnostyka.txt oraz pokrycie.json. Wszystkie obserwacje: zmiany.json.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_csv(view: dict) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=";")
    writer.writerow(
        [
            "Dzień",
            "Domena",
            "Projekt",
            "Cena poprzednio",
            "Cena dzisiaj",
            "Waluta",
            "Różnica",
            "Procent",
            "Strona główna odczytana",
            "Karta odczytana",
            "Status",
            "Adres projektu",
            "Cena od dzisiaj",
            "Cena do dzisiaj",
            "Podatek",
            "Jednostka ceny",
            "Poprzedni odczyt ceny",
            "Bieżący odczyt ceny",
            "Ocena odczytu ceny",
        ]
    )

    def safe(value):
        value = str(value or "")
        return "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r")) else value

    def number(value):
        return str(value).replace(".", ",") if value is not None else ""

    for r in view["rows"]:
        writer.writerow(
            [
                view["day"],
                r["domain"],
                safe(r["name"]),
                number(r["previous"].get("amount")),
                number(r["current"].get("amount")),
                r["current"].get("currency", ""),
                number(r["delta"]),
                number(r["percent"]),
                "tak" if r["home_read"] else "nie",
                "tak" if r["project_read"] else "nie",
                r["status_label"],
                safe(r["url"]),
                number(r["current"].get("low")),
                number(r["current"].get("high")),
                "netto + VAT" if r["current"].get("tax") == "net" else "brutto" if r["current"].get("tax") == "gross" else "nieoznaczony",
                r["current"].get("unit") or "projekt",
                r["previous"].get("observed_at", ""),
                r["current"].get("observed_at", ""),
                "odczyt niepewny" if r["current"].get("quality") == "partial" else "poprawny odczyt" if r["current"] else "brak ceny",
            ]
        )
    return "\ufeff" + stream.getvalue()


def render_markdown(view: dict, images: dict | None = None, item_limit: int | None = None) -> str:
    c = view["counts"]
    pair = view["comparison"]
    management = build_management(view)
    main_items = management['items'] if item_limit is None else management['items'][:item_limit]
    secondary_items = management['secondary'] if item_limit is None else management['secondary'][:item_limit]

    def esc(v):
        value = str(v).replace("\\", "\\\\").replace("\n", " ").replace("<", "&lt;").replace(">", "&gt;")
        return re.sub(r"([\[\]|*_`])", r"\\\1", value)

    paired = [r for r in view["rows"] if r["domain"] in pair["price_domains"]]
    price_lines = ["### Ceny, które udało się wiarygodnie porównać", "", "| Pracownia | Poprzedni dzień | Dzień raportu | Wynik |", "| --- | ---: | ---: | --- |"]
    price_lines.extend(f"| {esc(r['domain'])} | {r['previous_text']} | {r['current_text']} | {esc(_delta_text(r))} |" for r in paired)
    if not paired:
        price_lines = ["Brak wiarygodnych porównań cen z obu dni."]
    highlights = business_highlights(management['items'])
    business_lines = ["### Zmiany oferty i komunikacji — skrót", "", " · ".join(esc(b['label']) + ': **' + str(b['domains']) + '** pracowni' for b in management['business_buckets']), "", "| Pracownia / strona | Zmiana | Było | Jest | Źródło |", "| --- | --- | --- | --- | --- |"]
    for item in highlights:
        business_lines.append("| " + " | ".join([esc(item['domain']) + ' · ' + ('główna' if item['page'] == 'glowna' else 'stały projekt'), esc(item['description']), esc(brief(item['before'])), esc(brief(item['after'])), '[Źródło](' + item['source'] + ')']) + " |")
    if not highlights:
        business_lines.append("| Nie ustalono konkretnych różnic biznesowych dzień do dnia. | | | | |")
    business_lines.extend(["", f"Skrót: {len(highlights)} z {management['metrics']['communication']} pracowni ze zmianami. Każda pracownia: strona główna i ten sam zapamiętany projekt.", ""])
    lines = [
        f"## Komunikacja pracowni · {view['day']}",
        "",
        "### Wynik zarządczy",
        "",
        f"**Zmiany komunikacji: {management['metrics']['communication']} pracowni · strony główne: {management['metrics']['home_changes']} · karty projektów: {management['metrics']['project_changes']}.** Tylko konkretne zmiany dzień do dnia; każda pracownia jest liczona raz w danym wskaźniku.",
        "",
        communication_summary(view),
        "",
        *business_lines,
        "### Najważniejsze zmiany dzień do dnia",
        "",
        "Zmiany ofert oraz zmiany wyglądu mają osobne oznaczenia. Zmiana zrzutu nie potwierdza nowej ceny ani promocji. Błędy odczytu pozostają w diagnostyce.",
        "",
        "| Pracownia / strona | Rodzaj | Co się zmieniło | Było | Jest | Źródło / dowód |",
        "| --- | --- | --- | --- | --- | --- |",
        *["| " + " | ".join([esc(item['domain']) + ' · ' + ('główna' if item['page']=='glowna' else 'projekt') + (' · ' + esc(item['context']) if item.get('context') else ''), esc(item['type']), esc(item['description']), esc(str(item['before'])[:240] + ('…' if len(str(item['before']))>240 else '')), esc(str(item['after'])[:240] + ('…' if len(str(item['after']))>240 else '')), '[Strona]('+item['source']+')'+(' · [Zaznaczony fragment]('+images[item['evidence'].get('zmieniony_obszar')]+')' if images and item['evidence'].get('zmieniony_obszar') in images else '')]) + " |" for item in main_items],
        *([] if management['items'] else ["| Nie ustalono konkretnych zmian dzień do dnia w sprawdzonym zakresie. | | | | | |"]),
        *(["", f"Pokazano {len(main_items)} z {len(management['items'])} zmian komunikacji. Wszystkie wpisy, teksty przed/po i dowody są w pełnym raporcie HTML i dzienniku CSV."] if len(main_items) < len(management['items']) else []),
        "",
        f"### {assessment(view)['title']}",
        "",
        "\n\n".join(assessment(view)["lines"]),
        "",
        "### Dzienny przegląd wszystkich pracowni",
        "",
        "| Pracownia | Strona główna | Karta projektu | Źródła |",
        "| --- | --- | --- | --- |",
        *["| " + " | ".join([esc(r['domain']), *[esc(p['communication']['label']) + (' · nowa baza gotowa' if p['communication'].get('ready') and p['current_read'] else '') for p in r['pages']], ' · '.join('[' + ('Główna' if p['page']=='glowna' else 'Projekt') + '](' + p['url'] + ')' for p in r['pages'] if p['url'])]) + " |" for r in view['rows']],
        "",
        "<details><summary>Ceny projektów — informacje dodatkowe</summary>", "", *price_lines, "", "</details>",
        "",
        f"**Archiwum odczytów: {pair['before_day']} → {pair['after_day']}**. Zapisano {pair['paired_home']} par stron głównych i {pair['paired_project']} par kart projektów oraz {pair['screenshot_pairs']} par zrzutów. Są to zapisane materiały, nie liczba ustalonych zmian.",
        "",
        f"Odczytano **{c['home']}/{c['domains']} stron głównych** i **{c['project']}/{c['domains']} kart projektów**. Ustalono {c['prices']} cen; porównywalne pary cen: {c['price_pairs']}. **{c['events']} potwierdzonych zmian ofert** w {c['changed']} domenach.",
        "",
        "<details><summary>Dodatkowe zmiany ofert i ceny</summary>",
        "",
    ]
    events = [(r, e) for r in view["rows"] for e in r["events"]]
    if not events:
        lines.append("Brak potwierdzonych zmian sprzedażowych w poprawnie porównanym zakresie.")
    for row, e in events[:35]:
        lines.append(
            f"- **{esc(row['domain'])} · {esc(e['label'])}**: {esc(e['before'])} → **{esc(e['after'])}**. {esc(e['context'])}. [Źródło]({e['source']})"
        )
        proof = e["evidence"].get("roznice") or e["evidence"].get("po")
        if images and proof in images:
            lines.extend(["", f"![Zrzut porównawczy — {esc(row['domain'])}]({images[proof]})", ""])
    lines.extend(
        [
            "",
            "</details>",
            "",
            "<details><summary>Szczegóły odczytów, cen i ograniczeń monitora</summary>",
            "",
            "### Porównanie strony głównej i karty projektu",
            "",
            f"Porównania z poprzednim dniem: {c['daily_pages']} stron. Poniżej każda strona ma własny zakres dat. Luka w odczytach nie jest oznaczana jako porównanie z wczoraj.",
            "",
            "| Pracownia | Strona główna | Karta projektu |",
            "| --- | --- | --- |",
        ]
    )
    for row in view["rows"]:
        cells = [esc(row["domain"])]
        for page in row["pages"]:
            cells.append(esc(page["status_label"]) + " · " + when(page["compared_at"], True) + " → " + when(page["observed_at"], True))
        lines.append("| " + " | ".join(cells) + " |")
    reviews = [(r, e) for r in view["rows"] for e in r["reviews"] if not technical_reason(e)]
    if reviews:
        lines.extend(["", "### Niejednoznaczne różnice odczytu", "", "Nie ustalono, czy te różnice oznaczają zmianę oferty. Szczegóły zachowano do weryfikacji działania monitora.", ""])
        for row, event in reviews[:12]:
            lines.append(f"- **{esc(row['domain'])} · {esc(event['context'])} · {esc(event['label'])}**: {esc(event['before'])} → {esc(event['after'])}.")
    lines.extend(
        [
            "",
            "### Ceny wybranych projektów",
            "",
            "Cena poprzednio oznacza ostatni poprawny odczyt sprzed dnia raportu. „—” oznacza brak porównywalnej ceny, a nie zero.",
            "Gwiazdka przy cenie oznacza częściowy odczyt strony; kwota jest niepewna i nie służy do ustalania wzrostu lub spadku.",
            "",
            "| Pracownia / projekt | Poprzednio | Dzisiaj | Wynik |",
            "| --- | ---: | ---: | --- |",
        ]
    )
    for r in view["rows"]:
        name = f"{esc(r['domain'])} · {esc(r['name'])}"
        link = f"[{name}]({r['url']})" if r["url"] else name
        lines.append(
            f"| {link} | {r['previous_text']} | **{r['current_text']}** | {esc(_delta_text(r) if r['project_read'] else 'Nie odczytano karty')} |"
        )
    issues = [r for r in view["rows"] if not r["home_read"] or not r["project_read"]]
    if issues:
        lines.extend(["", "### Brakujące odczyty", ""])
        for r in issues:
            lines.append(f"- **{r['domain']}**: {esc(' '.join(r['issues'][:2]))}")
    lines.extend(
        [
            "",
            f"Obrazy do oceny: {c['visual']} domen. Dodatkowe konfiguratory i warianty mogą mieć częściowe pokrycie. Szczegóły, wyszukiwanie i zrzuty przed/po są w raporcie HTML w ZIP; techniczne komunikaty w diagnostyce.",
            "",
            f"Koniec odczytu: {when(view['metadata']['finished_at'])} czasu polskiego.",
            "",
            "</details>",
        ]
    )
    if management["secondary"]:
        lines.extend(["", "<details><summary>Archiwum różnic obrazu i porównań po luce (" + str(len(management["secondary"])) + ")</summary>", "", "Sama różnica zrzutu nie ustala nowej promocji ani przebudowy strony. Pełne wpisy, daty, źródła i dowody są w raporcie HTML oraz pełnym dzienniku CSV.", "", "| Pracownia / strona | Obserwacja | Daty odczytów | Źródło / dowód |", "| --- | --- | --- | --- |"])
        for item in secondary_items:
            link = "[Strona](" + item["source"] + ")"
            proof = item["evidence"].get("zmieniony_obszar")
            if images and proof in images:
                link += " · [Zaznaczony fragment](" + images[proof] + ")"
            lines.append("| " + esc(item["domain"] + " · " + item["page"]) + " | " + esc(item["description"]) + " | " + esc(when(item["before_at"], True) + " → " + when(item["after_at"], True)) + " | " + link + " |")
        if len(secondary_items) < len(management['secondary']):
            lines.extend(["", f"Pokazano {len(secondary_items)} z {len(management['secondary'])} dodatkowych obserwacji. Pełna lista jest w raporcie HTML i dzienniku CSV."])
        lines.extend(["", "</details>", ""])
    return "\n".join(lines) + "\n"


def render_html(view: dict) -> str:
    from .briefing import build_briefing, render_briefing, render_intelligence

    # Recompute after enrichment too; archived views can predate this schema.
    view = {**view, "management": build_management(view)}
    view["briefing"] = build_briefing(view, view["management"])
    template = files("pracownie").joinpath("_report_template.html").read_text()
    observed = sorted(p["observed_at"] for r in view["rows"] for p in r["pages"] if p["observed_at"])
    payload = (
        json.dumps(view, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    # Core content is rendered on the server too. Sandboxed previews and
    # browsers with scripts disabled must still display the complete report.
    source_ids = set(view["management"]["source_ids"])
    replacements = {
        "__REPORT_DATA__": payload,
        "__REPORT_DAY__": html.escape(view["day"]),
        "__STATIC_DAILY__": render_daily_html(view),
        "__STATIC_COMPARISON__": render_scan_html(view),
        "__STATIC_OBSERVATIONS__": render_observations_html(view),
        "__STATIC_STATS__": render_stats_html(view),
        "__STATIC_ASSESSMENT__": render_assessment_html(view),
        "__STATIC_JOURNAL__": render_journal_html(view, rows=[e for e in view['journal'] if e['id'] in source_ids]),
        "__STATIC_SECONDARY__": render_journal_html(view, rows=view["management"]["secondary"], secondary=True),
        "__STATIC_MANAGEMENT__": render_briefing(view, view["briefing"]) + render_intelligence(view) + '<details id="technical-summary"><summary>Wszystkie obserwacje — szczegóły techniczne</summary>' + render_management(view) + '</details>',
        "__STATIC_AVAILABILITY__": render_availability(view),
        "__STATIC_QUALITY__": render_quality_panel(view),
        "__STATIC_COMMUNICATION__": render_communication_table(view),
        "__SECONDARY_COUNT__": str(len(view["management"]["secondary"])),
        "__STATIC_EVENTS__": ''.join(render_event_html(view, row, event, i) for row in view["rows"] for i, event in enumerate(row["events"])) or '<p class="empty">Nie ustalono potwierdzonych zmian sprzedażowych. Niepełny zakres porównania jest opisany w wyniku powyżej.</p>',
        "__STATIC_TITLE__": "Zmiany na stronach · " + html.escape(view["day"]),
        "__STATIC_STAMP__": ("Dane z odczytów " + html.escape(when(observed[0])) + " – " + html.escape(when(observed[-1])) + " · czas polski") if observed else "Brak bieżących odczytów",
    }
    # One pass: source text containing a placeholder is data, never a template.
    return re.sub("|".join(re.escape(k) for k in replacements), lambda m: replacements[m[0]], template)


def render_stats_html(view: dict) -> str:
    result = assessment(view)
    stats = [("Potwierdzone zmiany ofert", view["counts"]["events"], "ceny, promocje, dodatki i treść"), ("Zmiany wyglądu", view["counts"].get("visual_changes",0), "osobne wpisy z porównaniem obrazów"), ("Cena bez zmian", result["unchanged"], "pracowni w porównanym zakresie"), ("Brak porównania ceny", result["uncompared"], "pracowni bez wiarygodnego porównania")]
    return ''.join('<div class="stat"><span>' + html.escape(name) + '</span><strong>' + str(value) + '</strong><span>' + html.escape(note) + '</span></div>' for name, value, note in stats)


def render_assessment_html(view: dict) -> str:
    result = assessment(view)
    return '<section class="box" id="assessment"><h2>' + html.escape(result["title"]) + '</h2>' + ''.join('<p>' + html.escape(line) + '</p>' for line in result["lines"]) + '</section>'


def proof_path(day: str, path: str) -> str:
    from pathlib import PurePosixPath
    from urllib.parse import quote
    parts = PurePosixPath(path).parts
    if not parts or parts[0] != day or ".." in parts:
        return ""
    return "/".join(quote(p, safe="") for p in parts[1:])


def highlighted_values(before: str, after: str) -> tuple[str, str]:
    first, second = re.findall(r"\s+|\S+", before), re.findall(r"\s+|\S+", after)
    old, new = [], []
    for op, a, b, c, d in SequenceMatcher(None, first, second, autojunk=False).get_opcodes():
        left, right = html.escape(''.join(first[a:b])), html.escape(''.join(second[c:d]))
        old.append('<del>' + left + '</del>' if op in {"delete", "replace"} else left)
        new.append('<ins>' + right + '</ins>' if op in {"insert", "replace"} else right)
    return ''.join(old), ''.join(new)


def render_event_html(view: dict, row: dict, event: dict, index: int, images: bool = False) -> str:
    esc = html.escape
    before, after = highlighted_values(event["before"], event["after"])
    tag = "review" if event["review"] else "event"
    output = '<article class="event" data-domain="' + esc(row["domain"], quote=True) + '" data-page="' + event["page"] + '" data-category="' + esc(event["category"], quote=True) + '"><header><h3>' + esc(row["domain"]) + '</h3><span class="badge ' + tag + '">' + esc(event["label"]) + (' · niezweryfikowany odczyt' if event["review"] else ' · potwierdzono') + '</span></header>'
    output += '<p class="context">' + esc(event["context"]) + '</p><div class="values"><div class="value"><small>Przed · ' + esc(when(event["before_at"])) + '</small>' + before + '</div><div class="value after"><small>Po · ' + esc(when(event["after_at"])) + '</small>' + after + '</div></div>'
    if event.get("note"):
        output += '<p class="small">' + esc(event["note"]) + '</p>'
    if images:
        output += '<div class="proofs">'
        for key, label, at in [("przed", "Przed", event["before_at"]), ("po", "Po", event["after_at"])]:
            path = proof_path(view["day"], event["evidence"].get(key, ""))
            if path:
                output += '<figure><a href="' + esc(path, quote=True) + '" target="_blank" rel="noopener"><img src="' + esc(path, quote=True) + '" loading="lazy" alt="' + label + ' — ' + esc(row["domain"], quote=True) + '"><figcaption>' + label + ' · ' + esc(when(at)) + '</figcaption></a></figure>'
        output += '</div>'
    output += '<footer><a href="' + esc(safe_url(event["source"]), quote=True) + '" target="_blank" rel="noopener">Strona źródłowa</a><button class="detail-button" data-open="' + esc(row["domain"], quote=True) + '" data-kind="' + tag + '" data-event="' + str(index) + '">Pełne szczegóły</button></footer></article>'
    return output


def render_observations_html(view: dict) -> str:
    examples = []
    for page in ["glowna", "projekt"]:
        candidates = [(row, event, i) for row in view["rows"] for i, event in enumerate(row["reviews"]) if event["page"] == page and not technical_reason(event)]
        candidates.sort(key=lambda item: not bool(item[1].get("before_full") and item[1].get("after_full")))
        examples.extend(candidates[:3])
    return ''.join(render_event_html(view, row, event, i, images=True) for row, event, i in examples) or '<p class="empty">Brak dodatkowych ustaleń. Niejednoznaczne zapisy techniczne zachowano w szczegółach odczytów; nie są zadaniami do potwierdzenia.</p>'


def render_scan_html(view: dict) -> str:
    esc = html.escape
    comparison = view["comparison"]
    before = date.fromisoformat(comparison["before_day"]).strftime("%d.%m.%Y")
    after = date.fromisoformat(comparison["after_day"]).strftime("%d.%m.%Y")
    content = '<section class="box scan-comparison" aria-labelledby="comparison-title"><p class="eyebrow">Archiwum odczytów</p>'
    content += f'<h2 id="comparison-title">{before} → {after}</h2>'
    content += f'<p>{comparison["paired_home"]} stron głównych i {comparison["paired_project"]} kart projektów ma odczyt z obu dni. Dla {comparison["screenshot_pairs"]} par są oba zrzuty ekranu.</p>'
    content += '<p class="small">Liczby dotyczą zapisanych materiałów. Nie oznaczają liczby ustalonych zmian. Zmiana sposobu odczytu ogranicza wnioski; jej naprawa jest zadaniem monitora.</p>'
    prices = [r for r in view["rows"] if r["domain"] in comparison["price_domains"]]
    if prices:
        content += '<h3>Ceny odczytane w obu dniach</h3><div class="table-box"><table class="paired-prices"><thead><tr><th>Pracownia</th><th>' + before + '</th><th>' + after + '</th><th>Wynik</th></tr></thead><tbody>'
        for row in prices:
            content += '<tr data-price-domain="' + esc(row["domain"], quote=True) + '"><td>' + esc(row["domain"]) + '</td><td>' + esc(row["previous_text"]) + '</td><td>' + esc(row["current_text"]) + '</td><td>' + esc(_delta_text(row)) + '</td></tr>'
        content += '</tbody></table></div>'
    else:
        content += '<p class="small">Brak porównywalnych cen z tych dwóch dni. Bieżące ceny są w sekcjach kart projektów.</p>'
    content += '<p class="small">Pełne porównanie i obrazy: <a href="#daily">przejdź do pracowni</a>.</p></section>'
    return content


def render_daily_html(view: dict) -> str:
    def esc(value):
        return html.escape(str(value or ""), quote=True)

    def proof(path):
        from pathlib import PurePosixPath
        from urllib.parse import quote
        parts = PurePosixPath(path).parts
        if not parts or parts[0] != view["day"] or ".." in parts:
            return ""
        return "/".join(quote(p, safe="") for p in parts[1:])

    def event_html(event):
        return (
            '<article class="daily-event"><strong>' + ("Niezweryfikowany odczyt · " if event["review"] else "") + esc(event["label"]) + '</strong>'
            + '<p class="small">' + esc(event["context"]) + '</p><div class="values"><div class="value"><small>Przed · '
            + esc(when(event["before_at"])) + '</small>' + esc(event.get("before_full") or event["before"])
            + '</div><div class="value after"><small>Po · ' + esc(when(event["after_at"])) + '</small>'
            + esc(event.get("after_full") or event["after"]) + '</div></div>'
            + ('<p class="small">' + esc(event.get("note")) + '</p>' if event.get("note") else "") + '</article>'
        )

    management = build_management(view)
    items = management['items']
    changed = {item['domain'] for item in items}
    blocks = []
    for row in sorted(view["rows"], key=lambda r: (r['domain'] not in changed, r['domain'])):
        pages = []
        domain_items = [item for item in items if item['domain'] == row['domain']]
        for page in row["pages"]:
            page_items = [item for item in domain_items if item['page'] == page['page']]
            link = safe_url(page["url"])
            title = '<a href="' + esc(link) + '" target="_blank" rel="noopener">' + esc(page["label"]) + '</a>' if link else esc(page["label"])
            part = '<section class="daily-page" data-page="' + page["page"] + '"><h3>' + title + '</h3>'
            supporting = [e for e in management['secondary'] if e['domain'] == row['domain'] and e['page'] == page['page'] and e['daily'] and e['category'] != 'ceny']
            copy_status = page_finding(page, page_items, supporting)
            part += '<span class="badge ' + page["status"] + '" data-change-label data-fallback="' + esc(page_finding(page, [], supporting)) + '">' + esc(copy_status) + '</span>'
            part += '<p class="small">' + esc(when(page["compared_at"])) + ' → ' + esc(when(page["observed_at"])) + ' · czas polski</p>'
            if page["page"] == "projekt":
                project_label = 'Ten sam projekt: ' + row['name'] if row.get('project_selected', True) else 'Stała karta projektu: jeszcze nie wybrana — brak poprawnego odczytu.'
                part += '<p class="fixed-project"><strong>' + esc(project_label) + '</strong></p>'
            if page["gap_days"] and page["gap_days"] > 1:
                part += '<p class="visual-note">Luka ' + str(page["gap_days"]) + ' dni. Porównanie z ostatnim poprawnym odczytem, starszym niż wczoraj.</p>'
            part += ''.join(render_business_change(item) for item in page_items[:3])
            if len(page_items) > 3:
                part += '<details class="more-changes"><summary>Pozostałe różnice tej strony (' + str(len(page_items) - 3) + ')</summary>' + ''.join(render_business_change(item) for item in page_items[3:]) + '</details>'
            if not page_items:
                part += '<p class="small">' + esc(page_finding(page, [], supporting)) + '</p>'
            if supporting:
                reasons = list(dict.fromkeys(e.get('supporting_reason', e.get('basis', 'Obserwacja pomocnicza')) for e in supporting))
                part += '<details class="supporting-observations"><summary>Obserwacje pomocnicze (' + str(len(supporting)) + ')</summary><ul>' + ''.join('<li>' + esc(reason) + '</li>' for reason in reasons) + '</ul><p class="small">Pełne teksty i dowody są w dodatkowym dzienniku obserwacji.</p></details>'
            part += render_business_proofs(view['day'], page_items)
            if page['page'] == 'projekt':
                price_events = [e for e in page['events'] if e['category'] == 'ceny']
                part += '<details class="project-prices"><summary>Ceny — informacje dodatkowe</summary><div class="values"><div class="value"><small>Cena poprzednio</small>' + esc(row['previous_text']) + '</div><div class="value after"><small>Cena dzisiaj</small>' + esc(row['current_text']) + '</div></div>' + ''.join(event_html(e) for e in price_events) + '</details>'
            if page["reviews"]:
                part += '<details class="reviews"><summary>Niejednoznaczne zapisy odczytu (' + str(len(page["reviews"])) + ')</summary><p class="small">Materiały do weryfikacji działania monitora. Nie są potwierdzonymi zmianami ofert ani zadaniami dla użytkownika.</p>' + ''.join(event_html(e) for e in page["reviews"]) + '</details>'
            images = []
            for key, label, at in [("przed", "Przed", page["compared_at"]), ("po", "Po", page["observed_at"])]:
                path = proof(page["evidence"].get(key, ""))
                if path:
                    images.append('<figure><a href="' + esc(path) + '" target="_blank" rel="noopener"><img loading="lazy" src="' + esc(path) + '" alt="' + label + ' — ' + esc(row["domain"] + ' · ' + page["label"]) + '"><figcaption>' + label + ' · ' + esc(when(at)) + '</figcaption></a></figure>')
            if images:
                part += '<details class="page-proofs"><summary>Zrzuty przed / po</summary><div class="proofs">' + ''.join(images) + '</div></details>'
            if page["extraction_changes"]:
                part += '<p class="small">Zmiana reguł odczytu: nowe lub niedopasowane pola pozostają w diagnostyce; nie potwierdzają zmiany na stronie.</p>'
            pages.append(part + '</section>')
        issues = '<ul class="small">' + ''.join('<li>' + esc(issue) + '</li>' for issue in row["issues"]) + '</ul>' if row["issues"] else ''
        summary = ('Strona główna: ' + str(sum(e['page'] == 'glowna' for e in domain_items)) + ' · stały projekt: ' + str(sum(e['page'] == 'projekt' for e in domain_items))) if domain_items else 'Bez zmian komunikacji' if all(p['communication'].get('daily') for p in row['pages']) else 'Porównanie częściowe lub brak odczytu'
        blocks.append('<details class="day-domain box" id="pracownia-' + esc(row['domain']) + '" data-domain="' + esc(row["domain"]) + '"><summary><strong>' + esc(row["domain"]) + '</strong><span class="small" data-company-counts>' + esc(summary) + '</span></summary><div><p class="small">Stała karta projektu: ' + esc(row["name"]) + '</p><div class="daily-pages">' + ''.join(pages) + '</div>' + issues + '</div></details>')
    return ''.join(blocks) or '<p class="empty">Brak odczytów w tym raporcie.</p>'


def safe_url(value: str) -> str:
    return value if urlsplit(value).scheme in {"http", "https"} else ""
