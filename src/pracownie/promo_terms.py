"""Compare explicit campaign terms in dated quotations from one public page."""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urldefrag, urlsplit

from .commercial import document, expired_end, future_start, not_started
from .communication import COUNTDOWN
from .extract import page_identity
from .financial import codes
from .journal import capture_day
from .model import Snapshot, slug

MONEY = r"(?:\d{1,3}(?:[ \u00a0]\d{3})+|\d+)(?:[,.]\d{1,2})?\s*(?:zł|PLN)"
BENEFIT = rf"(?:do\s+)?[-−–]?\s*(?:\d+(?:[,.]\d+)?\s*%|{MONEY})"
VALUE = re.compile(rf"\b(?:rabat\w*|oszczędzasz|zniżk\w*|taniej\s+(?:nawet\s+)?o)\s*[:=–-]?\s*({BENEFIT})|({BENEFIT})\s*(?:rabatu|zniżki)", re.I)
CAMPAIGN = re.compile(r"\b(?:Black (?:Friday|Week(?:end)?)|Cyber Monday)\b", re.I)
SCOPE = re.compile(r"\b(?:na|dla|przy zakupie)\s+(?:(?:wszystki\w*|każd\w*|wybran\w*|gotow\w*|dowoln\w*|drug\w*)\s+)?(?:projekt\w*|garaż\w*|pakiet\w*|dodat\w*|klient\w*|subskrybent\w*|instalacj\w*|kosztorys\w*)(?:\s+(?:dom\w*|garaż\w*|instalacj\w*|sanitarn\w*|indywidualn\w*|newsletter\w*|budowlan\w*)){0,3}\b", re.I)
MINIMUM = re.compile(rf"\b(?:(?:minimaln\w*\s+(?:wartość|kwota)(?:\s+(?:zamówienia|koszyka|zakupów))?\s*:?\s*|(?:zamówieni\w*|zakup\w*|koszyk\w*)\s+(?:(?:o wartości|na kwotę)\s+)?(?:od|powyżej|minimum|co najmniej)\s+){MONEY})", re.I)
STACK = re.compile(r"\b(?:nie\s+(?:można|łączy się)|można\s+łączyć|łączy się|nie podlega łączeniu)(?:\s+łączyć)?\s+z\s+(?:(?:innymi|pozostałymi|aktywnymi)\s+)?(?:promocjami|rabatami|kodami|kodem rabatowym)\b[^.;!?]*", re.I)
DATE = r"(?:\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{4})"
EXPIRY = re.compile(rf"(?:\bdo(?:\s+dnia)?\s*:?\s*|\b(?:{DATE}|\d{{1,2}})\s*[-–—]\s*)({DATE})(?!\d)", re.I)
MONTH_END = re.compile(r"\bdo końca\s+(?:stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|września|października|listopada|grudnia)(?:\s+\d{4})?\b", re.I)
FINAL_PRICE = re.compile(rf"\b(?:cena (?:po rabacie|z kodem(?:\s+[A-Z0-9_-]+)?)|po rabacie zapłacisz)\s*:?\s*({MONEY})", re.I)
EXTRA_AMOUNT = re.compile(rf"\b(?:jeszcze|dodatkowo)\s+o\s+{BENEFIT}|\b(?:a|oraz|lub)\s+{MONEY}\s+(?:brutto\s+)?(?:przy zakupie|na\s)", re.I)
VALUE_FIELDS = ("value", "scope", "minimum", "stacking", "expiry", "effective_price")


def terms(text: str) -> dict | None:
    text = " ".join(text.split())
    if not text or len(text) > 1600:
        return None
    literals = codes(text)
    if len(literals) > 1:
        return None  # One sentence can offer different benefits for different codes.
    named = CAMPAIGN.search(text)
    stacking = list(STACK.finditer(text))
    discount = []
    for match in VALUE.finditer(text):
        if any(s.start() <= match.start() and match.end() <= s.end() for s in stacking):
            continue  # A non-stackable second discount is not this offer's benefit.
        value = " ".join((match[1] or match[2]).split())
        if "nawet o" in match[0].lower() and not value.lower().startswith("do "):
            value = "do " + value
        discount.append(value)
    if not discount and named:
        match = re.search(rf"(?<!\w)(?:do\s+)?[-−–]\s*(?:\d+(?:[,.]\d+)?\s*%|{MONEY})", text, re.I)
        if match:
            discount = [" ".join(match[0].split())]
    if not (literals or discount or stacking or named and (EXPIRY.search(text) or MONTH_END.search(text))):
        return None
    prices = list(dict.fromkeys(m[1] for m in FINAL_PRICE.finditer(text)))
    if len(set(discount)) > 1 or discount and EXTRA_AMOUNT.search(text):
        if not literals and not named:
            return None
        # A listed reduction and another reduction with a coupon do not
        # describe one guaranteed customer benefit. Preserve the full quote.
        discount = []
    expiry = EXPIRY.search(text)
    relative = MONTH_END.search(text)
    validity = expiry[1] if expiry else relative[0] if relative else ""
    unavailable = bool(re.search(r"aktualnie brak|promocja (?:zakończona|nie obowiązuje)|kod (?:[\w-]+ )?(?:wygasł|nieaktualny|nieaktywny|nie działa)", text, re.I))
    restrictions = [m[0] for m in SCOPE.finditer(text)]
    if not restrictions:
        restrictions = [m[0] for m in re.finditer(r"\b(?:wszystkie|wybrane) projekty(?: domów| garaży)?\b|\bten projekt\b", text, re.I)]
    restrictions.extend(m[0].strip() for m in re.finditer(
        r"\b(?:z wyjątkiem|z wyłączeniem|nie dotyczy|wyłącznie dla)\s+[^.;!?]{2,90}", text, re.I))
    return {"quote": text, "code": literals[0] if literals else "",
            "campaign": named[0] if named else "", "value": discount[0] if discount else "",
            "scope": " / ".join(dict.fromkeys(restrictions)),
            "minimum": " / ".join(dict.fromkeys(m[0] for m in MINIMUM.finditer(text))),
            "stacking": " / ".join(dict.fromkeys(m[0].strip() for m in stacking)),
            "expiry": validity, "effective_price": prices[0] if len(prices) == 1 and not unavailable else "",
            "unavailable": unavailable}


def campaign_key(item: dict) -> tuple[str, str]:
    if item["code"]:
        return "code", item["code"]
    if item["campaign"]:
        return "campaign", item["campaign"].casefold()
    # For unnamed offers the surrounding wording, including the object of
    # the offer, must remain identical. Never pair on a shared amount alone.
    text = item["quote"]
    for key in ("value", "expiry", "minimum", "effective_price"):
        if item[key]:
            text = text.replace(item[key], f"[{key}]")
    return "offer", " ".join(COUNTDOWN.sub("", text).replace("[licznik]", "").casefold().split())


def source_frame(doc: dict, page: str) -> dict | None:
    if doc.get("error") or not doc.get("observed_at") or not doc.get("url"):
        return None
    url = urldefrag(doc["url"])[0]
    if urlsplit(url).scheme not in {"http", "https"}:
        return None
    day = capture_day(doc["observed_at"])
    rows = []
    unstable = set(doc.get("unstable_claims", []))
    claims = dict.fromkeys([*doc.get("claims", []), *(
        line for line in doc.get("text", "").splitlines() if CAMPAIGN.search(line) or re.search(r"\bkod(?:em)?\b", line, re.I))])
    for claim in claims:
        if claim in unstable:
            continue
        item = terms(claim)
        if not item:
            continue
        if expired_end(claim, day) or future_start(claim, day) or not_started(claim):
            item["effective_price"] = ""
        anchor = doc.get("claim_urls", {}).get(claim, "")
        source = anchor if urldefrag(anchor)[0] == url else url
        rows.append({**item, "source": source, "observed_at": doc["observed_at"]})
    return {"url": url, "page": page, "day": day,
            "complete": bool(doc.get("complete")) and not unstable, "observed_at": doc["observed_at"], "offers": rows}


def grouped(frame: dict) -> dict:
    result = {}
    for item in frame.get("offers", []):
        result.setdefault(campaign_key(item), []).append(item)
    return result


def unambiguous(items: list[dict]) -> dict | None:
    # A full statement can subsume a shorter banner. Never combine fragments
    # or assign another campaign's threshold/expiry to the observed code.
    options = sorted(items, key=lambda i: (-sum(bool(i[k]) for k in VALUE_FIELDS), len(i["quote"])))
    if not options:
        return None
    selected = options[0]
    if any(i["unavailable"] != selected["unavailable"] or
           any(i[k] and i[k].casefold() != selected[k].casefold() for k in VALUE_FIELDS)
           for i in options):
        return None
    return selected


def compare_promo_terms(state: dict, view: dict, evidence_dir: Path | None = None) -> list[dict]:
    day = view["day"]
    yesterday = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    domains = {r["domain"]: r.get("url") for r in view["rows"]}
    past, current = {}, {}
    base_urls = {}

    def save(domain, frame):
        if not frame or frame["day"] not in {day, yesterday}:
            return
        target = current if frame["day"] == day else past
        key = domain, frame["page"], frame["url"]
        if key not in target or frame["observed_at"] >= target[key]["observed_at"]:
            target[key] = frame

    for section in ("anchor", "communication_anchor", "snapshots", "communication_snapshots"):
        for key, raw in state.get(section, {}).items():
            domain, page = raw["domain"], raw["page"]
            if domain not in domains or page not in {"glowna", "projekt"} or key != f"{domain}/{page}/podstawowy":
                continue
            if page == "projekt" and domains[domain] and page_identity(raw["url"]) != page_identity(domains[domain]):
                continue
            if capture_day(raw["observed_at"]) not in {day, yesterday}:
                continue
            base_urls.setdefault(domain, set()).add(urldefrag(raw["url"])[0])
            save(domain, source_frame(document(Snapshot.from_dict(raw)), page))

    for saved in state.get("promo_terms_frames", []):
        if saved["domain"] in domains:
            save(saved["domain"], saved["frame"])
    if evidence_dir:
        for domain in domains:
            path = evidence_dir / slug(domain) / "weryfikacja-oferty.json"
            if path.is_file():
                for doc in json.loads(path.read_text()).get("documents", []):
                    if doc.get("repeated") or urldefrag(doc.get("url", ""))[0] in base_urls.get(domain, set()):
                        continue
                    save(domain, source_frame(doc, "terms"))

    # Capture history for linked regulations is separate from the homepage and
    # the selected project, and remains available through same-day retries.
    state["promo_terms_frames"] = [{"domain": domain, "frame": frame}
                                   for frames in (past, current) for (domain, page, _), frame in sorted(frames.items())
                                   if page == "terms"]
    output = []
    for (domain, page, url), frame in sorted(current.items()):
        before_frame = past.get((domain, page, url), {})
        before, after = grouped(before_frame), grouped(frame)
        complete = frame["complete"] and before_frame.get("complete", False)
        for key in sorted(before.keys() | after.keys()):
            old, new = unambiguous(before.get(key, [])), unambiguous(after.get(key, []))
            if (not new and key in after) or (not old and key in before):
                continue
            if not new and not complete:
                continue
            status, changed = "observed", []
            if old and new and complete:
                changed = [k for k in VALUE_FIELDS if old[k] and new[k] and old[k].casefold() != new[k].casefold()]
                if not old["unavailable"] and new["unavailable"]:
                    changed.append("unavailable")
                known = all(bool(old[k]) == bool(new[k]) for k in VALUE_FIELDS)
                status = "changed" if changed else "unchanged" if known and old["unavailable"] == new["unavailable"] else "observed"
            elif complete and new:
                status = "appeared"
            elif old and not new:
                status = "missing"
            item = new or old
            output.append({"domain": domain, "page": page, "source": url, "code": item["code"],
                           "campaign": item["campaign"], "status": status, "changed_fields": changed,
                           "before": old, "after": new, "complete": bool(complete)})
    return output
