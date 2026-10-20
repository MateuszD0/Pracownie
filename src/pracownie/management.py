"""Executive decisions use confirmed daily facts, with explicit coverage."""

from __future__ import annotations

import html
from collections import Counter
from datetime import datetime
from decimal import Decimal

from .journal import capture_day
from .model import WARSAW


def build_management(view: dict) -> dict:
    journal = view["journal"]
    # A changed screenshot alone cannot explain a redesign. Keep the material
    # available for inspection, without promoting it into an executive finding.
    meaningful = [e for e in journal if e["daily"] and e.get("specific", e["category"] != "obraz")]
    priority = {"ceny": 0, "promocje": 1, "dodatki": 2, "pakiety": 2, "warunki": 3,
                "funkcje": 3, "parametry": 4, "komunikacja": 5, "tresc": 5, "obraz": 6}
    meaningful.sort(key=lambda e: (priority.get(e["category"], 5), -abs(Decimal(e.get("delta") or "0")), e["domain"], e["id"]))
    domains = []
    for row in view["rows"]:
        pages = row["pages"]
        problems = []
        for page in pages:
            prefix = page["label"] + ": "
            if not page.get("current_read", bool(page["observed_at"]) and capture_day(page["observed_at"]) == view["day"]):
                reason = page.get("error_text") or ("brak odczytu z dnia raportu" if page["observed_at"] else "brak odczytu")
                problems.append(prefix + reason)
            elif page.get("data_quality", "ok") not in {"ok", "visual"}:
                problems.append(prefix + "odczyt częściowy" + (" — " + "; ".join(page.get("quality_notes", [])) if page.get("quality_notes") else ""))
            elif page["reviews"] or page["extraction_changes"]:
                problems.append(prefix + "niezgodne lub niejednoznaczne odczyty z obu dni")
            elif not page["compared_at"]:
                problems.append(prefix + "pierwszy odczyt; brak wcześniejszej bazy")
            elif not page["daily"]:
                problems.append(prefix + f"brak porównania z wczoraj (luka {page['gap_days']} dni)")
        if row["domain"] not in view["comparison"]["price_domains"]:
            if not row["current"]:
                reason = "nie rozpoznano jednoznacznej ceny" if row["project_read"] else "brak bieżącego odczytu karty"
            elif row["current"].get("quality") != "ok":
                reason = "bieżąca kwota jest niepewna lub obejmuje warianty"
            elif not row["previous"]:
                reason = "brak wcześniejszej ceny tego samego pola i wariantu"
            elif capture_day(row["previous"].get("observed_at")) != view["comparison"]["before_day"]:
                reason = "brak ceny z wczoraj"
            else:
                reason = "ceny mają różne pola, warianty lub jakość odczytu"
            problems.append("Cena: " + reason)
        domains.append({"domain": row["domain"], "problems": problems,
                        "interaction_issues": [i for i in row["issues"] if i.startswith("Dodatkowe interakcje")],
                        "price_pair": row["domain"] in view["comparison"]["price_domains"]})
    sales = [e for e in meaningful if e["category"] != "obraz"]
    return {
        "items": meaningful,
        "secondary": [e for e in journal if e not in meaningful],
        "domains": domains,
        "metrics": {
            "price_cuts": len({e["domain"] for e in meaningful if e.get("selected_price") and Decimal(e.get("delta") or "0") < 0}),
            "promotions": len({e["domain"] for e in meaningful if e["category"] == "promocje"}),
            "extras": len({e["domain"] for e in meaningful if e["category"] in {"dodatki", "pakiety"}}),
            "sales": len(sales), "changed_domains": len({e["domain"] for e in sales}),
            "visual_facts": sum(e["category"] == "obraz" for e in meaningful),
        },
    }


def render_management(view: dict) -> str:
    esc = html.escape
    data = build_management(view)
    metrics = data["metrics"]
    total = len(view["rows"])
    pairs = len(view["comparison"]["price_domains"])
    notes = (
        f"Ustalono {metrics['sales']} zmian ofert w {metrics['changed_domains']} pracowniach. "
        f"Ceny wybranych projektów porównano dla {pairs}/{total} pracowni. "
        + (f"Dla {total - pairs} pracowni dzienna zmiana ceny pozostaje nieustalona." if pairs < total else "Wszystkie wybrane projekty mają porównywalną parę cen.")
    )
    content = '<section class="box executive" id="executive" aria-labelledby="summary-title"><p class="eyebrow">Wynik dnia</p><h2 id="summary-title">' + ("Wynik częściowy" if pairs < total else "Porównanie dzienne") + '</h2><p id="management-summary" aria-live="polite">' + esc(notes) + '</p>'
    content += '<p class="small" id="management-scope">Zakres: wszystkie pracownie · ' + esc(view["comparison"]["before_day"]) + ' → ' + esc(view["day"]) + '. Liczymy tylko zmiany dzień do dnia; starsze porównania są w archiwum poniżej.</p></section>'
    content += '<div class="stats management-stats" id="management-stats">'
    for key, label, note in [("price_cuts", "Obniżki cen projektów", "pracowni · ten sam wybrany projekt i wariant"), ("promotions", "Zmiany promocji", "pracowni · nowe, zmienione lub zakończone promocje"), ("extras", "Zmiany dodatków i pakietów", "pracowni · gratisy, wyposażenie i dokumentacja")]:
        content += '<div class="stat"><span>' + label + '</span><strong id="metric-' + key + '">' + str(metrics[key]) + '</strong><span>' + note + '</span></div>'
    content += '</div><section class="box quality-overview" aria-labelledby="quality-title"><h2 id="quality-title">Na ile pełny jest ten wynik?</h2><div id="quality-summary">' + render_quality_summary(view) + '</div><p class="small">Odczyt strony i porównywalna cena to różne miary. „0” w KPI dotyczy wyłącznie potwierdzonych zmian w sprawdzonym zakresie. <a href="#availability">Sprawdź przyczyny braków i zakres każdej pracowni</a>.</p></section>'
    return content


def render_quality_summary(view: dict) -> str:
    total = len(view["rows"])
    pages = [p for row in view["rows"] for p in row["pages"]]
    fresh = [p for p in pages if p.get("current_read", bool(p["observed_at"]) and capture_day(p["observed_at"]) == view["day"])]
    partial = sum(p.get("data_quality", "ok") not in {"ok", "visual"} for p in fresh)
    return (
        '<div class="quality-grid">'
        f'<p><strong>{sum(p["page"] == "glowna" for p in fresh)}/{total}</strong> Strony główne odczytane</p>'
        f'<p><strong>{sum(p["page"] == "projekt" for p in fresh)}/{total}</strong> Karty projektów odczytane</p>'
        f'<p><strong>{len(view["comparison"]["price_domains"])}/{total}</strong> Ceny porównane z wczoraj</p>'
        '</div><p class="small">'
        f'Odczyty częściowe: {partial} stron. Pary odczytów z obu dni: {view["comparison"]["paired_pages"]}/{total * 2} stron — ich treść może wymagać zgodnych reguł odczytu.</p>'
    )


def render_availability(view: dict) -> str:
    esc = html.escape
    rows = {row["domain"]: row for row in view["rows"]}
    data = build_management(view)
    counts = Counter("missing" if not rows[d["domain"]]["home_read"] or not rows[d["domain"]]["project_read"] else "limited" if d["problems"] else "ready" for d in data["domains"])
    content = '<details class="box disclosure" id="availability"><summary><strong>Dostępność danych i przyczyny braków</strong><span class="small">Brak odczytu: ' + str(counts["missing"]) + ' pracowni · pozostałe ograniczenia: ' + str(counts["limited"]) + '</span></summary><p class="small">Każda pracownia pozostaje na liście, także gdy blokuje skaner. Odmowa 403 wymaga dostępnego publicznego źródła lub uzgodnienia dostępu z witryną; kolejne dni nie są oznaczane jako „bez zmian”. Interakcje mogą mieć dodatkowe ograniczenia.</p><div class="table-box"><table class="availability-table"><thead><tr><th>Pracownia / projekt</th><th>Strona główna</th><th>Karta projektu</th><th>Cena dzień do dnia</th><th>Przyczyna / dalszy odczyt</th></tr></thead><tbody>'
    for domain in sorted(data["domains"], key=lambda d: (not bool(d["problems"]), d["domain"])):
        row = rows[domain["domain"]]
        content += '<tr data-availability-domain="' + esc(row["domain"], quote=True) + '"><td><strong>' + esc(row["domain"]) + '</strong><br><span class="small">' + esc(row["name"]) + '</span><br><button class="watch-button" data-watch="' + esc(row["domain"], quote=True) + '" aria-pressed="false" aria-label="Obserwuj ' + esc(row["domain"], quote=True) + '">☆ Obserwuj</button></td>'
        for p in row["pages"]:
            fresh = p.get("current_read", bool(p["observed_at"]) and capture_day(p["observed_at"]) == view["day"])
            label = "Brak odczytu" if not fresh else "Odczyt częściowy" if p.get("data_quality", "ok") not in {"ok", "visual"} else "Odczytano"
            stamp = datetime.fromisoformat(p["observed_at"]).astimezone(WARSAW).strftime("%d.%m %H:%M") if p["observed_at"] else "—"
            content += '<td>' + label + '<br><span class="small">' + stamp + '</span></td>'
        content += '<td>' + ("Porównano" if domain["price_pair"] else "Nie ustalono") + '</td><td><ul class="quality-reasons">' + ''.join('<li>' + esc(p) + '</li>' for p in domain["problems"] + domain["interaction_issues"]) + '</ul><a href="#pracownia-' + esc(row["domain"], quote=True) + '">Szczegóły i zapisane dowody</a></td></tr>'
    return content + '</tbody></table></div></details>'
