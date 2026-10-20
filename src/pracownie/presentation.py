"""Business-facing views; raw browser traces live in the diagnostic report."""

from __future__ import annotations

import csv
import html
import io
import json
import re
from collections import Counter
from datetime import datetime
from decimal import Decimal
from importlib.resources import files
from urllib.parse import urlsplit

from .extract import MONEY, amount, money_text, normalize
from .model import WARSAW, Result
from .offers import price_delta

SALES = {"ceny", "promocje", "dodatki", "pakiety", "warunki", "funkcje", "komunikacja"}
TITLES = {
    "ceny": "Cena",
    "promocje": "Promocja",
    "dodatki": "Dodatki",
    "pakiety": "Pakiet",
    "warunki": "Warunki zakupu",
    "funkcje": "Funkcjonalność",
    "komunikacja": "Komunikat",
}
NOISE = re.compile(
    r"cookies|ciastecz|danych osobowych|sales intelligence|digitree|zarządzaj zgod|^\[licznik\]$", re.I
)


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
    return {
        "category": change.category,
        "label": label,
        "context": context,
        "variant": result.variant,
        "before": _brief(old),
        "after": _brief(new),
        "delta": change.delta,
        "percent": change.percent,
        "review": change.kind == "review",
        "source": change.url,
        "before_at": change.before_at,
        "after_at": change.after_at,
        "evidence": change.evidence or result.evidence,
        "role": role,
        "page": result.page,
    }


def build_view(day: str, results: list[Result], metadata: dict, selections: dict, domains: list[str]) -> dict:
    rows = []
    for domain in domains:
        entries = [r for r in results if r.domain == domain]
        home = next((r for r in entries if r.page == "glowna" and r.scenario == "podstawowy"), None)
        project = next((r for r in entries if r.page == "projekt" and r.scenario == "podstawowy"), None)
        selected = selections.get(domain, {})
        current = project.offer if project else {}
        previous = project.before_offer if project else {}
        delta, percent = price_delta(previous, current)
        row = {
            "domain": domain,
            "name": selected.get("name") or domain,
            "url": selected.get("url") or (project.url if project else ""),
            "home_read": bool(home and home.observed_at),
            "project_read": bool(project and project.observed_at),
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
                if change.category == "obraz":
                    if result.scenario == "podstawowy" and not any(
                        v["page"] == result.page for v in row["visuals"]
                    ):
                        row["visuals"].append(
                            {
                                "page": result.page,
                                "evidence": change.evidence or result.evidence,
                                "source": result.url,
                            }
                        )
                    continue
                if change.category not in SALES or change.field_key.endswith(":priceValidUntil"):
                    continue
                if NOISE.search((change.before or "") + " " + (change.after or "")):
                    continue
                if "reguły odczytu" in change.note:
                    row["migration"] = True
                    # Extraction changes are not changes in an architect's offer.
                    continue
                if change.delta is not None and Decimal(change.delta) == 0:
                    continue
                event = _event(change, result)
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
                    _amount_key(change.before),
                    _amount_key(change.after),
                )
                if key in keys:
                    continue
                keys.add(key)
                row["reviews" if event["review"] else "events"].append(event)
        failed_options = [r for r in entries if r.scenario != "podstawowy" and r.error]
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
            row["issues"].append("Dodatkowe interakcje sprawdzone częściowo; szczegóły w diagnostyce.")
        if project and project.observed_at and project.data_quality == "partial":
            row["issues"].append("Karta odczytana częściowo; cena wymaga potwierdzenia.")
        row["issues"] = list(dict.fromkeys(row["issues"]))
        if not row["home_read"] or not row["project_read"]:
            row["status"], row["status_label"] = "missing", "Brak pełnego odczytu stron"
        elif row["events"]:
            row["status"], row["status_label"] = "changed", "Zmiana oferty"
        elif row["reviews"]:
            row["status"], row["status_label"] = "review", "Porównanie wymaga oceny"
        elif row["visuals"]:
            row["status"], row["status_label"] = "visual", "Obraz do oceny"
        elif not project.compared_at or row["migration"] and delta is None:
            row["status"], row["status_label"] = "baseline", "Pierwszy odczyt"
        else:
            row["status"], row["status_label"] = "unchanged", "Bez zmian w odczytanym zakresie"
        rows.append(row)
    return {
        "day": day,
        "metadata": metadata,
        "rows": rows,
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
        },
        "categories": dict(Counter(e["category"] for r in rows for e in r["events"])),
    }


def _delta_text(row: dict) -> str:
    if row["delta"] is None:
        return "brak porównywalnej ceny" if row["current"] else "brak ceny w odczycie"
    value = Decimal(row["delta"])
    if not value:
        return "bez zmiany ceny"
    return ("spadek " if value < 0 else "wzrost ") + f"{abs(value):.2f} ({row['percent'] or '—'}%)"


def render_text(view: dict) -> str:
    c = view["counts"]
    lines = [
        f"OFERTY PRACOWNI — {view['day']}",
        f"Raport gotowy: {when(view['metadata']['finished_at'])} (czas polski)",
        "",
        f"Odczyt: {c['home']}/{c['domains']} stron głównych; {c['project']}/{c['domains']} kart projektów.",
        f"Ceny ustalone: {c['prices']}; porównywalne pary cen: {c['price_pairs']}. Potwierdzone zmiany ofert: {c['events']} w {c['changed']} domenach.",
        f"Brak pełnego odczytu stron: {c['missing']} domen. Obrazy do oceny: {c['visual']} domen.",
        "",
        "NAJWAŻNIEJSZE ZMIANY",
        "",
    ]
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
    reviews = [(r, e) for r in view["rows"] for e in r["reviews"]]
    if reviews:
        lines.extend(["", "OBSERWACJE DO POTWIERDZENIA", ""])
        for row, event in reviews[:15]:
            description = f"{event['before']} → {event['after']}"
            if event["delta"]:
                direction = "spadek" if Decimal(event["delta"]) < 0 else "wzrost"
                description += f"; {direction} o {abs(Decimal(event['delta'])):.2f}"
            lines.append(f"DO OCENY: {row['domain']} — {event['label']}: {description}")
        if len(reviews) > 15:
            lines.append(f"Pozostałe {len(reviews) - 15} obserwacji: raport HTML i dane JSON.")
    lines.extend(["", "CENY PROJEKTÓW — POPRZEDNI ODCZYT → DZISIAJ", ""])
    for row in view["rows"]:
        lines.append(
            f"{row['domain']} | {row['name']} | {row['previous_text']} → {row['current_text']} | {_delta_text(row)}"
        )
    lines.extend(["", "SZCZEGÓŁY WEDŁUG DOMEN", ""])
    for row in view["rows"]:
        if not row["events"] and not row["reviews"] and not row["issues"] and not row["visuals"]:
            continue
        lines.append(f"{row['domain']} — {row['status_label']}")
        for issue in row["issues"]:
            lines.append("  " + issue)
        if row["migration"]:
            lines.append(
                "  Zmieniono reguły odczytu; różnice wynikające z tej zmiany nie są liczone jako zmiany oferty."
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
            "* Cena z dokładnego pola projektu przy częściowym odczycie strony; wymaga potwierdzenia. Nie wyliczamy z niej zmiany ceny.",
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
            ]
        )
    return "\ufeff" + stream.getvalue()


def render_markdown(view: dict, images: dict | None = None) -> str:
    c = view["counts"]

    def esc(v):
        value = str(v).replace("\\", "\\\\").replace("\n", " ").replace("<", "&lt;").replace(">", "&gt;")
        return re.sub(r"([\[\]|*_`])", r"\\\1", value)

    lines = [
        f"## Oferty pracowni · {view['day']}",
        "",
        f"Odczytano **{c['home']}/{c['domains']} stron głównych** i **{c['project']}/{c['domains']} kart projektów**. Ustalono {c['prices']} cen; porównywalne pary cen: {c['price_pairs']}. **{c['events']} potwierdzonych zmian ofert** w {c['changed']} domenach.",
        "",
        "### Zmiany ofert",
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
            "### Ceny wybranych projektów",
            "",
            "Cena poprzednio oznacza ostatni poprawny odczyt sprzed dnia raportu. „—” oznacza brak porównywalnej ceny, a nie zero.",
            "Gwiazdka przy cenie oznacza częściowy odczyt strony; kwota wymaga potwierdzenia i nie służy do potwierdzania wzrostu lub spadku.",
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
        ]
    )
    return "\n".join(lines) + "\n"


def render_html(view: dict) -> str:
    template = files("pracownie").joinpath("report.html").read_text()
    payload = (
        json.dumps(view, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    return template.replace("__REPORT_DATA__", payload).replace("__REPORT_DAY__", html.escape(view["day"]))


def safe_url(value: str) -> str:
    return value if urlsplit(value).scheme in {"http", "https"} else ""
