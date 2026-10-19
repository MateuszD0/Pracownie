from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import Browser, Page, async_playwright

from .extract import MONEY, amount, canonical_url, currency_code, extract_fields, validate_payload
from .model import Field, Scenario, Site, Snapshot, now_iso

EXTRACT = files("pracownie").joinpath("extract.js").read_text()
COOKIE_NAMES = re.compile(r"^(odmowa|odrzuć(?: wszystkie| opcjonalne)?|tylko niezbędne|tylko konieczne|nie zgadzam się|nie akceptuję|reject all|reject|reject optional|necessary only|deny|continue without accepting)$", re.I)
UNSAFE_OPTIONS = re.compile(r"zgod|consent|newsletter|prywatno|regulamin|rodo|quantity|ilość|ilosc|sort|limit", re.I)


class TransientFetchError(RuntimeError):
    """A temporary origin failure that can be retried with backoff."""


def allowed_url(site: Site, url: str) -> bool:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    home_host = urlsplit(site.home_url).hostname
    return parsed.scheme in {"http", "https"} and (
        host in {site.domain, home_host, *site.allowed_hosts} or host.endswith("." + site.domain)
    )


def proxy_settings() -> dict | None:
    value = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if not value:
        return None
    parsed = urlsplit(value)
    proxy = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 80}"}
    if parsed.username:
        proxy["username"] = parsed.username
        proxy["password"] = parsed.password or ""
    # Local fixtures must stay local even when an egress proxy is configured.
    proxy["bypass"] = "localhost,127.0.0.1,[::1]"
    return proxy


def infer_scenarios(payload: dict, page: str, limit: int = 30) -> tuple[list[Scenario], list[str]]:
    scenarios, warnings = [], []
    controls = payload.get("controls", [])
    known_ids = set()
    for control in controls:
        kind, label, selector = control["kind"], control["label"], control["selector"]
        if UNSAFE_OPTIONS.search(label + " " + control.get("name", "")):
            continue
        actions = []
        if kind in {"expand", "tab"}:
            actions = [{"action": "click", "selector": selector}]
        elif kind == "select" and page == "projekt":
            for option in control.get("options", []):
                if option["value"] == control.get("value"):
                    continue
                identity = "opcja-" + hashlib.sha256(f"{control.get('name') or selector}:{option['value']}".encode()).hexdigest()[:12]
                if identity not in known_ids:
                    scenarios.append(Scenario(identity, f"{label}: {option['label']}", [
                        {"action": "select", "selector": selector, "value": option["value"]}
                    ], page=page))
                    known_ids.add(identity)
        elif kind in {"radio", "checkbox"} and page == "projekt":
            if not control.get("checked"):
                actions = [{"action": "check", "selector": selector}]
        elif kind == "cart" and page == "projekt":
            actions = [{"action": "click", "selector": selector, "cart": True}]
        elif kind == "carousel":
            warnings.append("Wykryto karuzelę: automatycznie sprawdzono pierwszy kolejny slajd; pozostałe wymagają scenariuszy adaptera.")
            actions = [{"action": "click", "selector": selector}]
        elif kind == "unknown" and re.search(r"konfigur|kalkulator|personaliz|dopasuj|pakiet|dodatk", label, re.I):
            warnings.append(f"Niezweryfikowana kontrolka sprzedażowa: {label[:100]}")
        if actions:
            identity = kind + "-" + hashlib.sha256(f"{control.get('name') or selector}:{control.get('value', '')}".encode()).hexdigest()[:12]
            if identity not in known_ids:
                scenarios.append(Scenario(identity, label, actions, page=page))
                known_ids.add(identity)
    if len(scenarios) > limit:
        warnings.append(f"Wykryto {len(scenarios)} scenariuszy, limit wynosi {limit}; pokrycie częściowe.")
        scenarios = scenarios[:limit]
    if any(c["kind"] in {"select", "radio", "checkbox"} and not UNSAFE_OPTIONS.search(c["label"] + " " + c.get("name", "")) for c in controls):
        warnings.append("Sprawdzane opcje pojedynczo; kombinacje i zależności wymagają zatwierdzonego adaptera.")
    return scenarios, list(dict.fromkeys(warnings))


def project_candidates(site: Site, payload: dict) -> list[tuple[int, dict]]:
    candidates = []
    for position, link in enumerate(payload.get("links", [])):
        url = canonical_url(link["url"])
        if not allowed_url(site, url) or url.rstrip("/") == canonical_url(site.home_url).rstrip("/"):
            continue
        path = urlsplit(url).path.lower()
        if re.search(r"\.(pdf|zip|jpg|png|webp)$|/koszyk|/kontakt|/regulamin|/logowanie|/blog|/porady|/informacje|/aktualnosci|/dodatki/|/pakiet-dodatkow/", path):
            continue
        if re.search(r"/(lista|nowosci|kategorie|ulubione|wszystkie-projekty|polecane_projekty|promocja|energo-plus)/?$", path):
            continue
        context = (link.get("text", "") + " " + link.get("context", "")).lower()
        detail = bool(re.search(r"projekt[^/]*[/_-].+|/dom[-/].+|/projekty/[^/]+", path))
        if site.product_url_pattern:
            if not re.search(site.product_url_pattern, url):
                continue
            detail = True
        price = bool(re.search(r"\d\s*(zł|pln)", context))
        if not (detail or price and link.get("image")):
            continue
        strong_detail = bool(re.search(r"^/projekt/[^/]+/?$|^/projekt-domu-[^/]+/?$", path))
        if not strong_detail and not site.product_url_pattern:
            card_signal = bool(price or re.search(r"powierzch|\d\s*m[²2]", context))
            named_image = link.get("image") and bool(link.get("text")) and not re.match(r"^(projekty|domy)\b", link["text"], re.I)
            if not card_signal and not named_image:
                continue
        confidence_penalty = 0 if strong_detail else 1000 if price and link.get("image") else 3000
        rank = 4
        basis = "Projekt wyróżniony na stronie głównej; brak potwierdzonych danych sprzedaży."
        if "bestseller" in context or "najlepiej sprzed" in context:
            rank, basis = 1, "Oznaczenie bestseller w kontekście karty/linku."
        elif "najpopular" in context:
            rank, basis = 2, "Sekcja najpopularniejszych projektów."
        score = rank * 10000 + confidence_penalty + position
        candidates.append((score, {"url": url, "name": link.get("text") or urlsplit(url).path,
                                   "basis": basis, "source": site.home_url,
                                   "context": link.get("context", "")[:500], "selected_at": now_iso()}))
    seen = set()
    result = []
    for score, item in sorted(candidates, key=lambda item: item[0]):
        if item["url"] not in seen:
            result.append((score, item))
            seen.add(item["url"])
    return result


@dataclass
class Capture:
    snapshot: Snapshot
    payload: dict
    screenshot: Path
    controls: list[dict] = field(default_factory=list)


class BrowserScanner:
    def __init__(self, executable: str | None = None, navigation_timeout: int = 25000, settle_ms: int = 500):
        self.executable = executable or os.environ.get("MONITOR_BROWSER_EXECUTABLE")
        self.navigation_timeout = navigation_timeout
        self.settle_ms = settle_ms
        self.browser: Browser | None = None
        self.phases: dict[str, str] = {}

    async def __aenter__(self):
        self.manager = await async_playwright().start()
        try:
            self.browser = await self.manager.chromium.launch(
                headless=True, executable_path=self.executable,
            )
        except BaseException:
            await self.manager.stop()
            raise
        self.renderer = f"chromium-{self.browser.version}-playwright-1.56.0-v1-1280x900"
        return self

    async def __aexit__(self, *args):
        if self.browser:
            await self.browser.close()
        await self.manager.stop()

    async def settle(self, page: Page):
        await page.wait_for_timeout(self.settle_ms)
        try:
            await page.evaluate("() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 2500))])")
        except Exception:
            pass
        # Bounded scrolling: record a warning if the document exceeds the capture limit.
        for offset in range(0, min(await page.evaluate("document.body.scrollHeight"), 24000), 800):
            await page.evaluate("y => window.scrollTo(0,y)", offset)
            await page.wait_for_timeout(35)
        await page.evaluate("window.scrollTo(0,0)")
        await page.wait_for_timeout(self.settle_ms)

    async def cookies(self, page: Page):
        frames = [page.main_frame] + [frame for frame in page.frames if frame != page.main_frame and re.search(r"cookie|consent|privacy|cmp", frame.url, re.I)]
        for frame in frames:
            # Known CMP selectors avoid traversing the accessibility tree of advertisement frames.
            for selector in ("#CybotCookiebotDialogBodyButtonDecline", "#onetrust-reject-all-handler", "#didomi-notice-disagree-button"):
                button = frame.locator(selector).first
                if await button.count() and await button.is_visible():
                    try:
                        await button.click(timeout=2500)
                    except Exception:
                        # A recognized refusal control may be covered by the CMP's animation.
                        await button.evaluate("e => e.click()")
                    return
            buttons = frame.get_by_role("button", name=COOKIE_NAMES)
            for index in range(min(await buttons.count(), 3)):
                button = buttons.nth(index)
                if await button.is_visible():
                    await button.click(timeout=1500)
                    return

    async def capture(self, site: Site, page_kind: str, url: str, scenario: Scenario, destination: Path) -> Capture:
        if not allowed_url(site, url):
            raise ValueError("Adres poza skonfigurowanymi domenami; wymagany jawny allowed_hosts")
        assert self.browser is not None
        proxy = None if urlsplit(url).hostname in {"localhost", "127.0.0.1", "::1"} else proxy_settings()
        context = await self.browser.new_context(viewport={"width": 1280, "height": 900}, locale="pl-PL", timezone_id="Europe/Warsaw", color_scheme="light", reduced_motion="reduce", proxy=proxy)
        page = await context.new_page()
        page.set_default_timeout(7000)
        failed_hosts = set()
        page.on("requestfailed", lambda request: failed_hosts.add(urlsplit(request.url).hostname) if request.resource_type in {"image", "stylesheet"} else None)
        warnings = []
        try:
            self.phases[site.domain] = f"{page_kind}/{scenario.id}: nawigacja"
            response = await page.goto(url, wait_until="domcontentloaded", timeout=self.navigation_timeout)
            if response and (response.status == 429 or response.status >= 500):
                raise TransientFetchError(f"Przejściowy błąd HTTP {response.status}")
            if response is None or response.status >= 400:
                raise ValueError(f"Odpowiedź HTTP {response.status if response else 'brak'}")
            if not allowed_url(site, page.url):
                raise ValueError(f"Przekierowanie poza domenę: {urlsplit(page.url).hostname}; dodaj allowed_hosts po sprawdzeniu")
            await page.add_style_tag(content="html{scroll-behavior:auto!important}*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}")
            self.phases[site.domain] = f"{page_kind}/{scenario.id}: obsługa cookies"
            await self.cookies(page)
            self.phases[site.domain] = f"{page_kind}/{scenario.id}: przewijanie i oczekiwanie na zasoby"
            await self.settle(page)
            cookie_dialog = page.locator('#onetrust-banner-sdk, #CybotCookiebotDialog, #CookiebotDialog, [role="dialog"]')
            for index in range(await cookie_dialog.count()):
                element = cookie_dialog.nth(index)
                if await element.is_visible() and re.search(r"cookies|ciastecz|plik.*cookie", await element.inner_text(), re.I):
                    warnings.append("Widoczny panel cookies może zasłaniać ofertę; potrzebna reguła adaptera.")
            for action in scenario.actions:
                self.phases[site.domain] = f"{page_kind}/{scenario.id}: interakcja {action['action']}"
                selector = action.get("selector", "")
                locator = page.locator(selector)
                if action["action"] == "click":
                    text = (await locator.inner_text()).strip()
                    if re.search(r"zamawiam.*płac|potwierdź zamówienie|złóż zamówienie|place order|pay now|wyślij zapytanie", text, re.I):
                        raise ValueError("Scenariusz próbuje wysłać zamówienie lub zapytanie; działanie poza zakresem")
                    await locator.click()
                elif action["action"] == "select":
                    await locator.select_option(action["value"])
                elif action["action"] == "check":
                    await locator.check()
                elif action["action"] == "fill":
                    await locator.fill(str(action["value"]))
                elif action["action"] == "wait_for":
                    await locator.wait_for(state="visible")
                elif action["action"] == "goto":
                    target = action["url"]
                    if not allowed_url(site, target):
                        raise ValueError("Scenariusz prowadzi poza skonfigurowane domeny")
                    action_response = await page.goto(target, wait_until="domcontentloaded", timeout=self.navigation_timeout)
                    if not action_response or action_response.status >= 400:
                        raise ValueError("Nie udało się odczytać strony scenariusza")
                else:
                    raise ValueError(f"Nieobsługiwane działanie: {action['action']}")
                await self.settle(page)
                if not allowed_url(site, page.url):
                    raise ValueError("Interakcja przekierowała poza skonfigurowane domeny")
                if action.get("cart"):
                    warnings.append("Automatyczna próba koszyka; formularze i dalsze etapy wymagają scenariusza adaptera.")
            is_cart = any(a.get("cart") for a in scenario.actions)
            page_required = [] if is_cart else site.required.get(page_kind, [])
            for selector in [*page_required, *scenario.required]:
                if not await page.locator(selector).count() or not await page.locator(selector).first.is_visible():
                    raise ValueError(f"Nie odnaleziono wymaganego elementu: {selector}")
            await page.add_style_tag(content="*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important} [data-monitor-ignore]{visibility:hidden!important}")
            for selector in site.masks:
                await page.locator(selector).evaluate_all("es => es.forEach(e => e.style.visibility='hidden')")
            self.phases[site.domain] = f"{page_kind}/{scenario.id}: odczyt DOM"
            payload = await page.evaluate(EXTRACT)
            validate_payload(payload, product=page_kind == "projekt" and not any(a.get("cart") for a in scenario.actions))
            if payload.get("truncated"):
                warnings.append("Limit elementów DOM; odczyt częściowy.")
            if await page.evaluate("document.body.scrollHeight") > 24000:
                warnings.append("Strona dłuższa niż 24000 px; zrzut i przewijanie ograniczone.")
            relevant_failed = failed_hosts - set(site.ignore_resource_hosts)
            if relevant_failed:
                warnings.append("Niezaładowane obrazy/style z hostów: " + ", ".join(sorted(str(h) for h in relevant_failed)))
            if any(image["broken"] and image["rendered_width"] >= 80 and image["rendered_height"] >= 50 and urlsplit(image["src"]).hostname not in site.ignore_resource_hosts for image in payload.get("images", [])):
                warnings.append("Wykryto niezaładowane obrazy; porównanie wizualne może być niepełne.")
            timestamp = now_iso()
            fields, sections = extract_fields(payload, timestamp, site.ignore_patterns)
            for rule in site.field_selectors:
                if is_cart and not rule.get("include_cart", False):
                    continue
                if rule.get("page", "projekt") != page_kind:
                    continue
                element = page.locator(rule["selector"]).first
                if not await element.count():
                    if rule.get("optional", False):
                        continue
                    raise ValueError(f"Brak wymaganego pola {rule['key']}; nie nadpisano punktu odniesienia")
                value = await element.get_attribute(rule["attribute"]) if rule.get("attribute") else await element.inner_text()
                value = (value or "").strip()
                if not value and not rule.get("optional", False):
                    raise ValueError(f"Puste wymagane pole: {rule['key']}")
                match = MONEY.search(value)
                currency = rule.get("currency")
                number = amount(match[1]) if match else amount(value) if currency else None
                if match:
                    currency = currency_code(match[2])
                section = rule.get("section", "oferta")
                sections.append(section)
                fields["adapter:" + rule["key"]] = Field(rule.get("label", rule["key"]), value, rule.get("category", "ceny"), section, number, currency, timestamp)
            if not fields:
                warnings.append("Nie rozpoznano informacji sprzedażowych; adapter wymaga inspekcji.")
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.phases[site.domain] = f"{page_kind}/{scenario.id}: zrzut ekranu"
            height = min(await page.evaluate("document.documentElement.scrollHeight"), 24000)
            await page.screenshot(path=str(destination), animations="disabled", clip={"x": 0, "y": 0, "width": 1280, "height": max(900, height)}, timeout=15000)
            snapshot = Snapshot(
                domain=site.domain, page=page_kind, scenario=scenario.id, url=canonical_url(page.url),
                observed_at=timestamp, title=payload.get("h1") or payload["title"], fields=fields,
                sections=sections, image="", renderer=self.renderer, warnings=warnings,
                quality="partial" if warnings else "ok",
            )
            return Capture(snapshot, payload, destination, payload.get("controls", []))
        finally:
            await context.close()

    async def discover_project(self, site: Site, home: Capture, directory: Path) -> tuple[dict | None, Capture | None, list[str]]:
        candidates = project_candidates(site, home.payload)
        warnings = []
        # Inspect explicit bestseller/popular sections before choosing a merely promoted card.
        ranking_links = list(site.discovery_links)
        for link in home.payload.get("links", []):
            if re.search(r"bestseller|najpopular|najlepiej sprzed", link.get("text", ""), re.I) and allowed_url(site, link["url"]):
                ranking_links.append(link["url"])
        ranked_candidates = []
        for index, url in enumerate(list(dict.fromkeys(ranking_links))[:2]):
            try:
                listing = await self.capture(site, "glowna", url, Scenario("ranking", "Ranking"), directory / f"ranking-{index}.png")
                for _, candidate in project_candidates(site, listing.payload):
                    candidate.update(source=url, basis=f"Pierwszy poprawny projekt z sekcji: {listing.snapshot.title}. Ranking/ekspozycja nie potwierdza liczby sprzedaży.")
                    ranked_candidates.append((0, candidate))
            except Exception as exc:
                warnings.append("Nie udało się sprawdzić rankingu: " + type(exc).__name__)
        candidates = ranked_candidates + candidates
        seen = set()
        for _, selection in candidates:
            if selection["url"] in seen:
                continue
            seen.add(selection["url"])
            if len(seen) > 4:
                break
            try:
                capture = await self.capture(site, "projekt", selection["url"], Scenario("podstawowy", "Wariant podstawowy"), directory / "projekt.png")
                selection["name"] = capture.snapshot.title
                return selection, capture, warnings
            except Exception as exc:
                warnings.append(f"Kandydat niepotwierdzony: {selection['url']} ({type(exc).__name__})")
        return None, None, warnings + ["Nie wybrano poprawnej karty projektu; wymagane sprawdzenie domeny."]
