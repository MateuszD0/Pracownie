"""Dated homepage campaigns beside their terms and the same selected project.

Co-occurrence is evidence of publication, never proof of coupon eligibility,
redemption, or the cause of a price change. All calculations use listed prices.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from .commercial import expired_end, future_start, not_started
from .communication import COUNTDOWN, records
from .contexts import item_context
from .extract import page_identity
from .financial import codes
from .journal import capture_day, safe_source
from .model import Snapshot
from .offers import price_delta


def _day(value: str | None) -> str:
    try:
        return capture_day(value)
    except (TypeError, ValueError):
        return ""


def _same_page(first: str, second: str) -> bool:
    return bool(first and second and page_identity(first) == page_identity(second))


def _own_source(domain: str, source: str) -> bool:
    return bool(safe_source(source) and (urlsplit(source).hostname or "").removeprefix("www.") == domain.removeprefix("www."))


def _snapshot(state: dict, row: dict, page: str, day: str, *, anchor: bool = False) -> Snapshot | None:
    if page == "projekt" and not row.get("project_selected", True):
        return None
    raw = state.get("anchor" if anchor else "snapshots", {}).get(row["domain"] + "/" + page + "/podstawowy")
    if not raw or _day(raw.get("observed_at")) != day:
        return None
    if raw.get("domain") != row["domain"] or raw.get("page") != page or raw.get("scenario") != "podstawowy":
        return None
    if page == "projekt" and not _same_page(raw.get("url", ""), row.get("url", "")):
        return None
    if raw.get("quality") not in {"ok", "visual"}:
        return None
    try:
        return Snapshot.from_dict(raw)
    except (TypeError, ValueError, KeyError):
        return None


def _concrete_offer(text: str) -> bool:
    if re.search(r"maksymalna ilość produktów|w porównywarce|w ulubionych", text, re.I):
        return False
    if codes(text):
        return True
    amount = r"[-–−]?\s*\d+(?:[,.]\d+)?\s*(?:%|zł|PLN)"
    benefit = (r"(?:rabat\w*|taniej|oszczędz\w*|promocj\w*|minus)\s*(?:nawet\s*)?(?:do|o|w wysokości)?\s*" + amount
               + "|" + amount + r"\s*(?:rabatu|taniej|na (?:zakup|projekty))"
               + r"|(?:odbierz|otrzym\w*|dostajesz|zyskaj)\s*(?:od nas\s*)?" + amount)
    if re.search(benefit, text, re.I):
        return True
    named_extra = r"kosztorys|konsultacj|doradztw|zgod\w*\s+na\s+zmian|projekt\s+instalacji|dostaw|wysyłk|analiz\w*\s+działki|dziennik\s+budowy|zestaw\w*\s+(?:dodatk|materiał)|pakiet\w*\s+(?:dodatk|gratis)|pozwoleni\w*\s+na\s+budowę"
    return bool(re.search(named_extra, text, re.I) and re.search(r"gratis|bezpłat|darmow|za darmo|w cenie(?:\s+(?:projektu|obsługi|umowy))?", text, re.I))


def _campaign_key(text: str) -> str:
    text = COUNTDOWN.sub("", text).replace("[licznik]", "")
    text = re.sub(r"(?:do końca promocji(?: pozostało)?|zobacz\s*>)[\s:!>]*", "", text, flags=re.I)
    text = re.sub(r"^w cenie projektu\s+", "", text, flags=re.I)
    return " ".join(re.sub(r"[^\w%]+", " ", text).casefold().split())


def _article_source(source: str) -> bool:
    parts = urlsplit(source or "")
    return bool(re.search(r"/(?:aktualnosci|aktualności|artykul|artykuly|blog|porady)/", parts.path, re.I)
                or re.search(r"(?:^|[-_])(?:article|articles|news|blog|aktualnosci)(?:$|[-_])", parts.fragment, re.I))


def _editorial_keys(snapshot: Snapshot, items: list[dict]) -> tuple[set[str], set[str]]:
    payload = snapshot.document.get("payload", {})
    links = payload.get("links", []) + payload.get("commercial_context", {}).get("links", [])
    titles = {" ".join(link.get("text", "").casefold().split()) for link in links if _article_source(link.get("url", ""))}
    keys, roots = set(), set()
    for item in items:
        key = item.get("key", "")
        if key and " ".join(item.get("text", "").casefold().split()) in titles:
            keys.add(key)
            # An ID root identifies the recorded slide; a positional body root
            # could encompass unrelated homepage content, so never widen it.
            root = key.split(" > ")[0]
            if root.startswith("#"):
                roots.add(root)
    return keys, roots


def _other_period(claims: list[dict], day: str) -> str:
    months = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia", "września", "października", "listopada", "grudnia"]
    current = date.fromisoformat(day).month
    for claim in claims:
        for index, month in enumerate(months, 1):
            if index != current and re.search(r"(?:projekt(?:\s+miesiąca)?|do\s+końca)\s+" + month + r"\b", claim["quote"], re.I):
                return month
    return ""


def _claims(snapshot: Snapshot | None) -> list[dict]:
    if snapshot is None:
        return []
    items = records(snapshot) + snapshot.document.get("payload", {}).get("commercial_context", {}).get("items", [])
    editorial_keys, editorial_roots = _editorial_keys(snapshot, items)
    result, seen = [], set()
    for item in items:
        quote = item.get("text", "")
        key = item.get("key", "")
        if key in editorial_keys or any(key == root or key.startswith(root + " > ") for root in editorial_roots):
            continue
        if item.get("role") == "image" or item_context(snapshot.domain, item) in {"editorial", "testimonials", "dynamic"} or not _concrete_offer(quote):
            continue
        source = item.get("url") or snapshot.url
        if _article_source(source) or "#" + urlsplit(source).fragment in editorial_roots:
            continue
        identity = (quote, source)
        if _own_source(snapshot.domain, source) and _same_page(source, snapshot.url) and identity not in seen:
            result.append({"quote": quote, "source": source, "observed_at": snapshot.observed_at,
                           "page": snapshot.page, "codes": codes(quote)})
            seen.add(identity)
    return result


def _matches(home: list[dict], record: dict) -> bool:
    home_codes = {code for claim in home for code in claim["codes"]}
    record_codes = set(codes(record.get("quote", "")))
    if record.get("code"):
        record_codes.add(record["code"])
    if home_codes and record_codes:
        return bool(home_codes & record_codes)
    # A general campaign title or a shared percentage does not identify a
    # campaign. Without a code, require the complete recorded wording.
    text = " ".join(record.get("quote", "").casefold().split())
    return bool(text and any(text == " ".join(claim["quote"].casefold().split()) for claim in home))


def _project_name_pattern(name: str) -> str:
    name = re.sub(r"^projekt(?:y)?\s+dom(?:u|ów)?\s*[-:–]?\s*", "", name, flags=re.I).strip()
    if len(name) < 3:
        return ""
    # Jantar must not match Jantar VII, Jantar 2, or Jantar G2.
    return r"(?<!\w)" + re.escape(name) + r"(?!\w|\s+(?:[IVX]+|\d+|[A-Z]{1,3}\d+)\b)"


def _scope(name: str, terms: list[dict], project_claims: list[dict], project_available: bool, day: str, project_url: str) -> dict:
    evidence = terms + project_claims
    pattern = _project_name_pattern(name)
    included, excluded, expired, scheduled = [], [], [], []
    for record in evidence:
        quote = record["quote"]
        if expired_end(quote, day):
            expired.append(record)
            continue
        if future_start(quote, day) or not_started(quote):
            scheduled.append(record)
            continue
        if (record.get("page") == "projekt" and _same_page(record.get("source", ""), project_url)
                and re.search(r"(?:kup|zamów)\s+ten\s+projekt|(?:rabat|promocj\w*)\s+(?:na|obejmuje|dotyczy)\s+(?:ten projekt|tego projektu)", quote, re.I)):
            included.append(record)
            continue
        if not pattern or not re.search(pattern, quote, re.I):
            continue
        product = r"(?:projekt(?:u|y|ów)?\s+(?:domu\s+)?)?" + pattern
        if re.search(r"(?:nie\s+(?:obejmuje|dotyczy|obowiązuje(?:\s+na)?)|wyłącza|z wyjątkiem|oprócz)\s+" + product, quote, re.I):
            excluded.append(record)
        elif re.search(r"(?:obejmuje|dotyczy|obowiązuje(?:\s+na)?|rabat\s+na|promocja\s+na)\s+" + product, quote, re.I):
            included.append(record)
    if included and (excluded or expired or scheduled):
        return {"status": "conflicting", "label": "Sprzeczne zapisy zakresu lub terminu — wymaga sprawdzenia", "evidence": included + excluded + expired + scheduled}
    if excluded:
        return {"status": "explicitly_excluded", "label": "Stały projekt wymieniony w wyłączeniach promocji", "evidence": excluded}
    if included:
        return {"status": "explicitly_included", "label": "Stały projekt wymieniony w zakresie; realizacja kodu niesprawdzona", "evidence": included}
    if expired and not scheduled:
        return {"status": "expired", "label": "Zapisane warunki podają miniony termin; aktualne zastosowanie niepotwierdzone", "evidence": expired}
    if scheduled and not expired:
        return {"status": "scheduled", "label": "Zapisane warunki zapowiadają przyszłą promocję; nie potwierdzają rabatu dzisiaj", "evidence": scheduled}
    if expired and scheduled:
        return {"status": "conflicting", "label": "Różne terminy kampanii w źródłach — wymaga sprawdzenia", "evidence": expired + scheduled}
    all_projects = [record for record in evidence if re.search(r"(?:wszystki(?:e|ch)\s+projekt(?:y|ów)|cał[ąa]\s+ofert[ęa]\s+projektów)", record["quote"], re.I)]
    if all_projects:
        restricted = [record for record in evidence if record.get("minimum") or re.search(r"z wyjątkiem|oprócz|nie dotyczy|nie obejmuje|wybran|minimaln|powyżej|przy zakupie|tylko", record["quote"], re.I)]
        if restricted:
            return {"status": "conditional", "label": "Podano ograniczenia promocji; spełnienie warunków przez stały projekt niepotwierdzone", "evidence": all_projects + [r for r in restricted if r not in all_projects]}
        return {"status": "declared_all", "label": "Deklaracja wszystkich projektów; zastosowanie do tej karty niesprawdzone", "evidence": all_projects}
    if project_claims:
        return {"status": "mentioned_on_card", "label": "Ten sam kod lub komunikat jest na karcie; zakres niepotwierdzony", "evidence": project_claims}
    if not project_available:
        return {"status": "missing_project", "label": "Brak wiarygodnego odczytu stałej karty z tego dnia", "evidence": []}
    return {"status": "unconfirmed", "label": "Nie ustalono, czy kampania obejmuje stały projekt", "evidence": terms}


def daily_price_fact(state: dict, view: dict, row: dict) -> dict:
    """Price facts concern the selected card, independently of any campaign."""
    day = view["day"]
    previous_day = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    current, previous = row.get("current", {}), row.get("previous", {})
    fact = {"status": "missing", "before": None, "after": None, "delta": None, "percent": None,
            "source": safe_source(row.get("url", "")),
            "note": "Cena zapisana na karcie. Równoczesny baner nie dowodzi zastosowania rabatu ani przyczyny zmiany ceny."}
    if not row.get("project_selected", True) or not fact["source"]:
        return _price_display(fact)
    retained = bool(state.get("snapshots") or state.get("anchor"))
    before = _snapshot(state, row, "projekt", previous_day, anchor=True) if retained else None
    after = _snapshot(state, row, "projekt", day) if retained else None
    for value, target_day, target in [(previous, previous_day, "before"), (current, day, "after")]:
        saved = before if target == "before" else after
        if retained and (saved is None or value.get("observed_at") != saved.observed_at):
            continue
        if value.get("kind") == "price" and value.get("quality") == "ok" and _day(value.get("observed_at")) == target_day:
            fact[target] = {**value, "source_url": fact["source"]}
    if fact["after"] is None:
        return _price_display(fact)
    fact["status"] = "unpaired"
    paired = row["domain"] in view.get("comparison", {}).get("price_domains", [])
    # A report's paired-price flag is necessary but not sufficient when the
    # retained snapshots show a different project or dated capture.
    if retained:
        paired = paired and before is not None and after is not None
        if before and after:
            paired = paired and previous.get("observed_at") == before.observed_at and current.get("observed_at") == after.observed_at
    if not paired or fact["before"] is None:
        return _price_display(fact)
    try:
        delta, percent = price_delta(previous, current)
    except (InvalidOperation, KeyError, TypeError, ValueError):
        return _price_display(fact)
    if delta is not None:
        fact.update(status="unchanged" if Decimal(delta) == 0 else "changed", delta=delta, percent=percent)
    return _price_display(fact)


def _price_display(fact: dict) -> dict:
    from .presentation import money

    fact["before_text"] = money(fact["before"]) if fact["before"] else "Brak porównywalnej ceny z wczoraj"
    fact["after_text"] = money(fact["after"]) if fact["after"] else "Brak wiarygodnej ceny z dnia raportu"
    fact["delta_text"] = "Brak porównania dzień do dnia"
    if fact["delta"] is not None:
        currency = fact["after"].get("currency", "")
        delta = f'{Decimal(fact["delta"]):+,.2f}'.replace(",", " ").replace(".", ",")
        fact["delta_text"] = delta + " " + ("zł" if currency == "PLN" else currency)
        if fact["percent"] is not None:
            fact["delta_text"] += " / " + f'{Decimal(fact["percent"]):+.2f}'.replace(".", ",") + "%"
    fact["text"] = (fact["before_text"] + " → " + fact["after_text"] + " (" + fact["delta_text"] + ")"
                    if fact["status"] == "changed" else "Cena bez zmian: " + fact["after_text"]
                    if fact["status"] == "unchanged" else fact["after_text"] + "; " + fact["delta_text"]
                    if fact["status"] == "unpaired" else fact["after_text"])
    return fact


def build_campaign_cards(state: dict, view: dict, terms_rows: list[dict] | tuple = ()) -> list[dict]:
    """One card per observed homepage campaign; no inferred launches or scopes.

    ``terms_rows`` is the result of ``promo_terms.compare_promo_terms``. Only
    its same-day ``after`` evidence is joined, by literal code or whole quote.
    Absence of a campaign card does not establish absence of a promotion.
    """
    result = []
    day = view["day"]
    for row in view["rows"]:
        home = _claims(_snapshot(state, row, "glowna", day))
        project_snapshot = _snapshot(state, row, "projekt", day)
        project = _claims(project_snapshot)
        grouped = {}
        for claim in home:
            fragment = urlsplit(claim["source"]).fragment
            slide = fragment if re.fullmatch(r"slick-slide\d+", fragment) else ""
            identity = tuple(claim["codes"]) or (("slide", slide) if slide else (_campaign_key(claim["quote"]),))
            grouped.setdefault(identity, []).append(claim)
        for identity, claims in grouped.items():
            terms = []
            for term in terms_rows:
                current = term.get("after")
                if term.get("domain") != row["domain"] or not current or _day(current.get("observed_at")) != day:
                    continue
                source = current.get("source") or term.get("source", "")
                evidence = {**current, "source": source, "page": term.get("page", "terms"), "code": term.get("code", "")}
                if _own_source(row["domain"], source) and _matches(claims, evidence):
                    terms.append(evidence)
            project_matches = [claim for claim in project if _matches(claims, claim)]
            scope = _scope(row["name"], terms, project_matches, project_snapshot is not None, day, row["url"])
            period = _other_period(claims, day)
            if period:
                scope = {"status": "unverified_period", "label": "Komunikat odnosi się do miesiąca „" + period + "”; nie potwierdzono aktualnej ważności", "evidence": claims}
            if not row.get("project_selected", True):
                scope = {"status": "missing_project", "label": "Nie wybrano stałego projektu; brak oceny zastosowania kampanii", "evidence": []}
            scope["text"] = scope["label"]
            effective = []
            name_pattern = _project_name_pattern(row["name"])
            for term in terms:
                if not term.get("effective_price") or scope["status"] in {"conflicting", "explicitly_excluded", "expired", "scheduled", "unverified_period"}:
                    continue
                named = bool(name_pattern and re.search(name_pattern, term["quote"], re.I))
                if named or scope["status"] == "explicitly_included" and _same_page(term["source"], row["url"]):
                    effective.append({"value": term["effective_price"], "quote": term["quote"], "source": term["source"], "observed_at": term["observed_at"]})
            result.append({
                "id": "campaign-" + hashlib.sha256(repr((day, row["domain"], identity)).encode()).hexdigest()[:16],
                "day": day, "domain": row["domain"], "project_name": row["name"] if row.get("project_selected", True) else "Brak stałego projektu",
                "project_url": safe_source(row["url"]) if row.get("project_selected", True) else "",
                "home": claims, "terms": terms, "project": project_matches, "scope": scope,
                "price": daily_price_fact(state, view, row), "effective_price": effective,
                "note": "Komunikaty odczytano tego samego dnia. Kod nie był realizowany w koszyku; cena po kodzie jest pokazywana tylko jako dosłowna deklaracja źródła.",
            })
    return sorted(result, key=lambda card: (card["scope"]["status"] in {"unverified_period", "expired", "scheduled"},
                                           not any(claim["codes"] for claim in card["home"]),
                                           card["scope"]["status"] not in {"explicitly_included", "explicitly_excluded"},
                                           card["domain"], card["id"]))
