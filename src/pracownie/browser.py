from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import Browser, Page, async_playwright
from playwright.async_api import Error as BrowserError

from .extract import (
    MONEY,
    amount,
    canonical_url,
    currency_code,
    extract_fields,
    money_text,
    page_identity,
    validate_payload,
)
from .model import Field, Scenario, Site, Snapshot, now_iso, slug
from .observations import CONTRACT

EXTRACT = files("pracownie").joinpath("extract.js").read_text()
VISUALS = files("pracownie").joinpath("visuals.js").read_text()
COOKIE_NAMES = re.compile(r"^(odmowa|odrzuć(?: wszystkie| wszystko| opcjonalne)?|(?:(?:zaakceptuj|akceptuj|zezwól na) )?tylko (?:niezbędne|konieczne)|nie zgadzam się|nie wyrażam zgody|nie akceptuję|reject all|reject|reject optional|necessary only|deny|continue without accepting)$", re.I)
UNSAFE_OPTIONS = re.compile(r"zgod(?![ayę]?\s+(?:autora\s+)?na\s+zmian)|sprzeciw|danych osobowych|consent|newsletter|prywatno|regulamin|rodo|quantity|ilość|ilosc|sort|limit|billing_|shipping_|address_|_country|\[country\]|\bkraj\b|\bcountry\b|kod pocztowy|województwo", re.I)


class TransientFetchError(RuntimeError):
    """A temporary origin failure that can be retried with backoff."""

    def __init__(self, message: str, retry_after: float = 0):
        super().__init__(message)
        self.retry_after = retry_after


def retry_after_seconds(value: str | None) -> float:
    try:
        return max(0, float(value or "0"))
    except ValueError:
        try:
            return max(0, (parsedate_to_datetime(value).astimezone(UTC) - datetime.now(UTC)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 0


class UnusableControl(ValueError):
    """An inferred control cannot currently be operated; never fabricate a read."""


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
    known_ids = set()
    cart_seen = False
    relevant = re.compile(r"ofert|promoc|rabat|gratis|pakiet|dodatk|dokument|kosztorys|instalac|wariant|wersj|lustrzan|rzuty|technicz|warunki|dostaw|płatno|opis|budow|energo", re.I)
    controls = payload.get("controls", [])
    for control in controls:
        kind, label, selector = control["kind"], control["label"], control["selector"]
        if control.get("scope", "offer") != "offer" or not label or UNSAFE_OPTIONS.search(label + " " + control.get("name", "")):
            continue
        if re.fullmatch(r"firma|osoba (?:prawna|fizyczna)|wyślij kopię do mnie|PayPal.*", label, re.I):
            continue
        if kind in {"checkbox", "radio"} and label.lower() in {"on", "off", "tak", "nie", "true", "false"}:
            warnings.append("Opcja bez jednoznacznej etykiety wymaga adaptera: " + label)
            continue
        # Homepage catalog/navigation tabs are not product offer interactions.
        if page == "glowna" and kind != "carousel" and not relevant.search(label):
            continue
        actions = []
        target = {"selector": selector, "label": label, "inferred": True}
        if control.get("label_selector"):
            target["label_selector"] = control["label_selector"]
        if kind in {"expand", "tab"}:
            if control.get("expanded") == "true":
                continue
            actions = [{"action": "click", **target}]
        elif kind == "select" and page == "projekt":
            for option in control.get("options", []):
                if option["value"] == control.get("value"):
                    continue
                identity = "opcja-" + hashlib.sha256(f"{control.get('name') or selector}:{option['value']}".encode()).hexdigest()[:12]
                if identity not in known_ids:
                    scenarios.append(Scenario(identity, f"{label}: {option['label']}", [{"action": "select", **target, "value": option["value"]}], page=page))
                    known_ids.add(identity)
        elif kind in {"radio", "checkbox"} and page == "projekt":
            if not control.get("checked"):
                actions = [{"action": "check", **target}]
        elif kind == "cart" and page == "projekt" and not cart_seen:
            cart_seen = True
            actions = [{"action": "click", **target, "cart": True}]
        elif kind == "carousel":
            if any(s.id.startswith("carousel-") for s in scenarios):
                continue
            warnings.append("Karuzela: sprawdzono pierwszy kolejny slajd; pełna lista wymaga adaptera.")
            actions = [{"action": "click", **target}]
        elif kind == "unknown" and re.search(r"konfigur|kalkulator|personaliz|dopasuj|pakiet|dodatk", label, re.I):
            warnings.append(f"Kontrolka wymagająca adaptera: {label[:100]}")
        if actions:
            stable_value = control.get("value", "") if kind in {"radio", "checkbox"} else ""
            identity = kind + "-" + hashlib.sha256(f"{control.get('name') or control.get('href') or selector.removeprefix('body > ')}:{stable_value}".encode()).hexdigest()[:12]
            if identity not in known_ids:
                scenarios.append(Scenario(identity, label, actions, page=page))
                known_ids.add(identity)
    effective_limit = min(limit, 3) if page == "glowna" else limit
    if len(scenarios) > effective_limit:
        warnings.append(f"Wykryto {len(scenarios)} interakcji; sprawdzono maksymalnie {effective_limit}. Pozostały zakres wymaga adaptera.")
        scenarios = scenarios[:effective_limit]
    if any(c["kind"] in {"select", "radio", "checkbox"} and c.get("scope", "offer") == "offer" and not UNSAFE_OPTIONS.search(c["label"] + " " + c.get("name", "")) for c in controls):
        warnings.append("Opcje sprawdzane pojedynczo; kombinacje zależnych wariantów wymagają adaptera.")
    # Inspect sale content/options before entering a cart.
    scenarios.sort(key=lambda s: any(a.get("cart") for a in s.actions))
    return scenarios, list(dict.fromkeys(warnings))


def project_candidates(site: Site, payload: dict) -> list[tuple[int, dict]]:
    candidates = []
    for position, link in enumerate(payload.get("links", [])):
        url = canonical_url(link["url"])
        if not allowed_url(site, url) or page_identity(url) in {page_identity(site.home_url), page_identity(payload.get("url", site.home_url))}:
            continue
        path = urlsplit(url).path.lower()
        if re.search(r"\.(pdf|zip|jpg|png|webp)$|/koszyk|/kontakt|/regulamin|/logowanie|/blog|/porady|/informacje|/aktualnosci|/dodatki/|/pakiet-dodatkow/|/kategoria-produktu/|/product-category/|/_cms/view/|/content/", path):
            continue
        if re.search(r"/(lista|nowosci|kategorie|ulubione|wszystkie-projekty|polecane_projekty|promocja|energo-plus)/?$", path):
            continue
        if re.search(r"^/(o-nas|onas|firma|biuro|pracownia|partnerzy|user|login|register|konto)(/|$)|-c\d+/?$", path):
            continue
        context = (link.get("text", "") + " " + link.get("context", "")).lower()
        detail = bool(re.search(r"projekt[^/]*[/_-].+|/dom[-/].+|/projekty/[^/]+", path))
        if site.product_url_pattern:
            if not re.search(site.product_url_pattern, url):
                continue
            detail = True
        price = bool(re.search(r"\d\s*(zł|pln)", context))
        surface = bool(re.search(r"\d[\d,.]*\s*m[²2]", context))
        named_link = bool(link.get("text")) and not re.match(r"^(projekty|domy|zobacz|więcej|szczegóły|czytaj|przejdź)\b", link["text"], re.I)
        strong_detail = bool(re.search(r"^/projekt/[^/]+/?$|^/projekt-domu-[^/]+/?$|^/produkt/[^/]+/?$|^/product/[^/]+/?$|^/projects/[^/]+/?$", path))
        named_image = link.get("image") and named_link
        if not (strong_detail or detail or (price or surface) and (link.get("image") or named_link) or named_image):
            continue
        if not strong_detail and not site.product_url_pattern:
            card_signal = bool(price or surface or re.search(r"powierzch", context))
            if not card_signal and not named_image:
                continue
        confidence_penalty = 0 if strong_detail else 1000 if price and link.get("image") else 3000
        rank = 4
        source = payload.get("url") or site.home_url
        basis = "Projekt wyróżniony na stronie głównej; brak potwierdzonych danych sprzedaży." if page_identity(source) == page_identity(site.home_url) else "Projekt z publicznego katalogu; brak potwierdzonego rankingu sprzedaży."
        if re.search(r"bestseller|najlepiej sprzed|najczęściej kupow|najchętniej wybier", context):
            rank, basis = 1, "Oznaczenie bestseller w kontekście karty/linku."
        elif re.search(r"najpopular|wybór klientów", context):
            rank, basis = 2, "Sekcja najpopularniejszych projektów."
        score = rank * 10000 + confidence_penalty + position
        candidates.append((score, {"url": url, "name": link.get("text") or urlsplit(url).path,
                                   "basis": basis, "source": source,
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
        self.next_read: dict[str, float] = {}
        self.rate_limited: dict[str, float] = {}

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
        self.extractor = hashlib.sha256((EXTRACT + files("pracownie").joinpath("extract.py").read_text()).encode()).hexdigest()[:16]
        return self

    async def __aexit__(self, *args):
        if self.browser:
            await self.browser.close()
        await self.manager.stop()

    async def settle(self, page: Page):
        for attempt in range(2):
            try:
                await self._settle(page)
                return
            except BrowserError as exc:
                if attempt or not re.search(r"context was destroyed|Cannot find context|frame was detached", str(exc), re.I):
                    raise

    async def _settle(self, page: Page):
        await page.wait_for_load_state("domcontentloaded", timeout=self.navigation_timeout)
        try:
            await page.locator("body").wait_for(state="attached", timeout=5000)
        except BrowserError as exc:
            raise ValueError("Witryna nie zwróciła dokumentu HTML z treścią") from exc
        await page.wait_for_timeout(self.settle_ms)
        try:
            await page.evaluate("() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 2500))])")
        except Exception:
            pass
        # Bounded scrolling: record a warning if the document exceeds the capture limit.
        for offset in range(0, min(await page.evaluate("document.body?.scrollHeight || 0"), 24000), 1000):
            await page.evaluate("y => window.scrollTo(0,y)", offset)
            await page.wait_for_timeout(35)
        await page.evaluate("window.scrollTo(0,0)")
        await page.wait_for_timeout(self.settle_ms)

    async def operate(self, page: Page, action: dict):
        selector = action.get("selector", "")
        locator = page.locator(selector)
        label = action.get("label", selector)
        if action["action"] in {"click", "select", "check", "fill"}:
            if await locator.count() != 1:
                raise UnusableControl(f"Kontrolka nie ma jednoznacznego celu: {label}")
            if not await locator.is_enabled():
                raise UnusableControl(f"Kontrolka jest nieaktywna: {label}")
        if action["action"] == "click":
            text = (await locator.inner_text()).strip() or await locator.get_attribute("value") or await locator.get_attribute("alt") or ""
            if re.search(r"zamawiam.*płac|potwierdź zamówienie|złóż zamówienie|place order|pay now|wyślij zapytanie", text, re.I):
                raise ValueError("Scenariusz próbuje wysłać zamówienie lub zapytanie; działanie poza zakresem")
            await locator.evaluate("e => e.scrollIntoView({block:'center',inline:'center',behavior:'instant'})")
            await locator.click(timeout=3500)
        elif action["action"] == "select":
            await locator.select_option(action["value"], timeout=3500)
        elif action["action"] == "check":
            if not await locator.is_checked():
                label_selector = action.get("label_selector")
                if label_selector and await page.locator(label_selector).is_visible():
                    target = page.locator(label_selector)
                    await target.evaluate("e => e.scrollIntoView({block:'center',inline:'center',behavior:'instant'})")
                    await target.click(timeout=3500)
                else:
                    await locator.check(timeout=3500)
                if not await locator.is_checked():
                    raise UnusableControl(f"Nie potwierdzono wyboru opcji: {label}")
        elif action["action"] == "fill":
            await locator.fill(str(action["value"]), timeout=3500)
        elif action["action"] == "wait_for":
            await locator.wait_for(state="visible")
        else:
            raise ValueError(f"Nieobsługiwane działanie: {action['action']}")

    async def cookies(self, page: Page):
        frames = [page.main_frame] + [frame for frame in page.frames if frame != page.main_frame and re.search(r"cookie|consent|privacy|cmp", frame.url, re.I)]
        for frame in frames:
            # Known CMP selectors avoid traversing the accessibility tree of advertisement frames.
            for selector in ("#CybotCookiebotDialogBodyButtonDecline", "#onetrust-reject-all-handler", "#didomi-notice-disagree-button", "#cn-close-notice"):
                button = frame.locator(selector).first
                if await button.count() and await button.is_visible():
                    try:
                        await button.click(timeout=2500)
                    except Exception:
                        # A recognized refusal control may be covered by the CMP's animation.
                        await button.evaluate("e => e.click()")
                    return
            # Some CMPs implement their refusal action as an anchor rather
            # than a button (e.g. the visible "Tylko niezbędne" control).
            buttons = frame.get_by_role("button", name=COOKIE_NAMES).or_(frame.get_by_role("link", name=COOKIE_NAMES))
            for index in range(min(await buttons.count(), 3)):
                button = buttons.nth(index)
                if await button.is_visible():
                    await button.click(timeout=1500)
                    return
        # WP exposes its refusal button only after opening the consent settings.
        wp_dialog = page.get_by_role("dialog", name="Plansza informacyjna WP")
        if await wp_dialog.count() and await wp_dialog.first.is_visible():
            settings = wp_dialog.get_by_text("Ustawienia zaawansowane", exact=True)
            if await settings.count():
                await settings.first.click(timeout=2500)
                # The settings can be rendered asynchronously. A fixed pause
                # can leave an empty panel and silently skip refusal.
                ready = page.get_by_role("button", name=COOKIE_NAMES).or_(
                    page.get_by_role("dialog").get_by_role("button", name=re.compile("^Zapisz$", re.I))
                )
                await ready.first.wait_for(state="visible", timeout=3500)
                refusal = page.get_by_role("button", name=COOKIE_NAMES)
                for index in range(min(await refusal.count(), 3)):
                    if await refusal.nth(index).is_visible():
                        await refusal.nth(index).click(timeout=2500)
                        return
                advanced = page.get_by_role("dialog").filter(has_text=re.compile("Ustawienia Zaawansowane", re.I)).first
                if await advanced.count():
                    await advanced.locator('input[type=checkbox],[role=switch]').nth(1).wait_for(state="attached", timeout=2500)
                    # This CMP has no reject-all button. Set the actual controls
                    # to refusal, including objection to legitimate interests.
                    await advanced.evaluate("""dialog => {
                      const controls=[...dialog.querySelectorAll('input[type=checkbox],[role=switch]')];
                      const label=e => e.labels?.[0]?.innerText || e.closest('label')?.innerText || e.getAttribute('aria-label') || '';
                      const target=e => /sprzeciw/i.test(label(e));
                      const checked=e => e.matches('input') ? e.checked : e.getAttribute('aria-checked') === 'true';
                      for (const e of controls.sort((a,b) => Number(target(b))-Number(target(a)))) {
                        if (/niezbęd|koniecz|necessary|essential/i.test(label(e))) continue;
                        if (checked(e)!==target(e)) e.click();
                      }
                    }""")
                    await page.wait_for_function("""dialog => {
                      const controls = [...dialog.querySelectorAll('input[type=checkbox],[role=switch]')];
                      return controls.length > 1 && controls.every(e => {
                      const label=e.labels?.[0]?.innerText || e.closest('label')?.innerText || e.getAttribute('aria-label') || '';
                      if (/niezbęd|koniecz|necessary|essential/i.test(label)) return true;
                      const checked=e.matches('input') ? e.checked : e.getAttribute('aria-checked') === 'true';
                      return checked === /sprzeciw/i.test(label);
                      });
                    }""", arg=await advanced.element_handle(), timeout=2500)
                    save = advanced.get_by_role("button", name=re.compile("^Zapisz$", re.I))
                    if await save.count():
                        await save.click(timeout=2500)
                        await advanced.wait_for(state="hidden", timeout=2500)

    async def disable_motion(self, page: Page, warnings: list[str]):
        try:
            await page.add_style_tag(content="html{scroll-behavior:auto!important}*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important} [data-monitor-ignore]{visibility:hidden!important}")
        except BrowserError:
            warnings.append("Nie udało się wyłączyć animacji; porównanie wizualne wymaga oceny.")

    async def capture(self, site: Site, page_kind: str, url: str, scenario: Scenario, destination: Path) -> Capture:
        if not allowed_url(site, url):
            raise ValueError("Adres poza skonfigurowanymi domenami; wymagany jawny allowed_hosts")
        assert self.browser is not None
        remaining = self.rate_limited.get(site.domain, 0) - time.monotonic()
        if remaining > 0:
            raise TransientFetchError(f"Witryna ogranicza odczyt (429); ponowienie najwcześniej za {remaining:.0f} s", remaining)
        # A domain is visited sequentially, but fresh contexts otherwise hit
        # homepage, card and variants immediately one after another.
        pause = self.next_read.get(site.domain, 0) - time.monotonic()
        if pause > 0:
            await asyncio.sleep(pause)
        self.next_read[site.domain] = time.monotonic() + 2
        proxy = None if urlsplit(url).hostname in {"localhost", "127.0.0.1", "::1"} else proxy_settings()
        context = await self.browser.new_context(viewport={"width": 1280, "height": 900}, locale="pl-PL", timezone_id="Europe/Warsaw", color_scheme="light", reduced_motion="reduce", proxy=proxy)
        page = await context.new_page()
        page.set_default_timeout(7000)
        failed_hosts = set()
        failed_styles = set()
        def failed_request(request):
            if request.resource_type in {"image", "stylesheet"}:
                host = urlsplit(request.url).hostname
                failed_hosts.add(host)
                if request.resource_type == "stylesheet":
                    failed_styles.add(host)
        page.on("requestfailed", failed_request)
        warnings = []
        data_ready = True
        response = None

        def navigation_response(received):
            nonlocal response
            if received.request.is_navigation_request() and received.request.frame == page.main_frame:
                response = received

        page.on("response", navigation_response)
        try:
            self.phases[site.domain] = f"{page_kind}/{scenario.id}: nawigacja"
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=self.navigation_timeout)
            except BrowserError:
                # Chromium can reject an empty HTTP error document before
                # goto returns. Its response headers still govern retries.
                if response is None or response.status < 400:
                    raise
            if response and (response.status == 429 or response.status >= 500):
                delay = retry_after_seconds(response.headers.get("retry-after"))
                if response.status == 429:
                    delay = max(5, delay)
                    self.rate_limited[site.domain] = time.monotonic() + delay
                raise TransientFetchError(f"Przejściowy błąd HTTP {response.status}", delay)
            if response is None or response.status >= 400:
                raise ValueError(f"Odpowiedź HTTP {response.status if response else 'brak'}")
            if not allowed_url(site, page.url):
                raise ValueError(f"Przekierowanie poza domenę: {urlsplit(page.url).hostname}; dodaj allowed_hosts po sprawdzeniu")
            await self.disable_motion(page, warnings)
            self.phases[site.domain] = f"{page_kind}/{scenario.id}: obsługa cookies"
            try:
                await self.cookies(page)
            except BrowserError:
                warnings.append("Panel cookies nie odpowiedział na próbę odmowy; sprawdź widoczność oferty.")
            self.phases[site.domain] = f"{page_kind}/{scenario.id}: przewijanie i oczekiwanie na zasoby"
            await self.settle(page)
            # Consent managers often appear asynchronously, after DOMContentLoaded.
            await page.wait_for_timeout(self.settle_ms)
            try:
                await self.cookies(page)
            except BrowserError:
                warnings.append("Panel cookies nie odpowiedział na próbę odmowy; sprawdź widoczność oferty.")
            await page.wait_for_timeout(250)
            cookie_dialog = page.locator('#onetrust-banner-sdk, #CybotCookiebotDialog, #CookiebotDialog, [role="dialog"]')
            for index in range(await cookie_dialog.count()):
                element = cookie_dialog.nth(index)
                # Playwright's is_visible also matches transparent/offscreen
                # preference panels. Only a rendered panel in the viewport
                # can obscure the offer at this point.
                rendered = await element.evaluate("e => {const r=e.getBoundingClientRect(),s=getComputedStyle(e);return Number(s.opacity)>0 && r.bottom>0 && r.top<innerHeight && r.right>0 && r.left<innerWidth}")
                if await element.is_visible() and rendered and re.search(r"cookies|ciastecz|plik.*cookie", await element.inner_text(), re.I):
                    warnings.append("Widoczny panel cookies może zasłaniać ofertę; potrzebna reguła adaptera.")
                    data_ready = False
            for action in scenario.actions:
                self.phases[site.domain] = f"{page_kind}/{scenario.id}: interakcja {action['action']}"
                if action["action"] == "goto":
                    target = action["url"]
                    if not allowed_url(site, target):
                        raise ValueError("Scenariusz prowadzi poza skonfigurowane domeny")
                    action_response = await page.goto(target, wait_until="domcontentloaded", timeout=self.navigation_timeout)
                    if not action_response or action_response.status >= 400:
                        raise ValueError("Nie udało się odczytać strony scenariusza")
                else:
                    try:
                        await self.operate(page, action)
                    except BrowserError as exc:
                        if action.get("inferred"):
                            raise UnusableControl(f"Nie udało się obsłużyć kontrolki: {action.get('label', action.get('selector', ''))}. {str(exc).splitlines()[0]}") from exc
                        raise
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
            await self.disable_motion(page, warnings)
            for selector in site.masks:
                await page.locator(selector).evaluate_all("es => es.forEach(e => e.style.visibility='hidden')")
            self.phases[site.domain] = f"{page_kind}/{scenario.id}: odczyt DOM"
            is_cart = any(a.get("cart") for a in scenario.actions)
            for rule in site.field_selectors:
                if rule.get("page", "projekt") != page_kind or rule.get("optional") or rule.get("attribute") or is_cart and not rule.get("include_cart"):
                    continue
                await page.locator(rule["selector"]).filter(visible=True).first.wait_for(state="visible", timeout=5000)
            payload = await page.evaluate(EXTRACT, page_kind)
            payload["scenario_label"] = scenario.label
            payload["variant"] = scenario.label if any(a.get("action") in {"select", "check"} for a in scenario.actions) else ""
            validate_payload(payload, product=page_kind == "projekt" and not any(a.get("cart") for a in scenario.actions))
            if payload.get("truncated"):
                warnings.append("Limit elementów DOM; odczyt częściowy.")
                data_ready = False
            if await page.evaluate("document.body?.scrollHeight || 0") > 24000:
                warnings.append("Strona dłuższa niż 24000 px; zrzut i przewijanie ograniczone.")
            relevant_failed = failed_hosts - set(site.ignore_resource_hosts)
            if failed_styles - set(site.ignore_resource_hosts):
                data_ready = False
            if relevant_failed:
                warnings.append("Niezaładowane obrazy/style z hostów: " + ", ".join(sorted(str(h) for h in relevant_failed)))
            if any(image["broken"] and image["rendered_width"] >= 80 and image["rendered_height"] >= 50 and urlsplit(image["src"]).hostname not in site.ignore_resource_hosts for image in payload.get("images", [])):
                warnings.append("Wykryto niezaładowane obrazy; porównanie wizualne może być niepełne.")
            timestamp = now_iso()
            fields, sections = extract_fields(payload, timestamp, site.ignore_patterns)
            visual_document = await page.evaluate(VISUALS)
            consent = await page.locator('#onetrust-banner-sdk, #CybotCookiebotDialog, #CookiebotDialog, [role="dialog"]').evaluate_all("""elements => elements.filter(e=>/cookies|ciastecz|plik.*cookie/i.test(e.innerText||'')).slice(0,6).map(e=>({id:e.id,role:e.getAttribute('role'),text:(e.innerText||'').slice(0,1600),opacity:getComputedStyle(e).opacity,rect:[e.getBoundingClientRect().x,e.getBoundingClientRect().y,e.getBoundingClientRect().width,e.getBoundingClientRect().height],controls:[...e.querySelectorAll('button,a,[role=button]')].slice(0,20).map(b=>({tag:b.tagName,id:b.id,classes:b.className,label:(b.innerText||b.getAttribute('aria-label')||'').slice(0,180),onclick:(b.getAttribute('onclick')||'').slice(0,300)}))}))""")
            visual_document["anchors"] = {slug(k): v for k, v in visual_document["anchors"].items()}
            for rule in site.field_selectors:
                if is_cart and not rule.get("include_cart", False):
                    continue
                if rule.get("page", "projekt") != page_kind:
                    continue
                candidates = page.locator(rule["selector"])
                element = candidates.first if rule.get("attribute") else candidates.filter(visible=True).first
                if not await element.count():
                    if rule.get("optional", False):
                        continue
                    raise ValueError(f"Brak wymaganego pola {rule['key']}; nie nadpisano punktu odniesienia")
                value = await element.get_attribute(rule["attribute"]) if rule.get("attribute") else await element.inner_text()
                value = (value or "").strip()
                if not value and not rule.get("optional", False):
                    raise ValueError(f"Puste wymagane pole: {rule['key']}")
                match = MONEY.search(money_text(value))
                currency = rule.get("currency")
                number = amount(match[1]) if match else amount(value) if currency else None
                if rule.get("pattern"):
                    selected = re.search(rule["pattern"], value)
                    number = amount(selected[1]) if selected else None
                    if number is None and not rule.get("optional", False):
                        raise ValueError(f"Pole {rule['key']} nie odpowiada wzorcowi ceny; nie nadpisano punktu odniesienia")
                if match:
                    currency = currency_code(match[2])
                section = rule.get("section", "oferta")
                sections.append(section)
                fields["adapter:" + rule["key"]] = Field(rule.get("label", rule["key"]), value, rule.get("category", "ceny"), section, number, currency, timestamp, source="adapter", role=rule.get("role", "current"), primary=rule.get("primary", rule.get("category", "ceny") == "ceny"), tax=rule.get("tax", ""), unit=rule.get("unit", ""))
            if not fields:
                warnings.append("Nie rozpoznano informacji sprzedażowych; adapter wymaga inspekcji.")
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.phases[site.domain] = f"{page_kind}/{scenario.id}: zrzut ekranu"
            height = min(await page.evaluate("document.documentElement.scrollHeight"), 24000)
            await page.screenshot(path=str(destination), animations="disabled", clip={"x": 0, "y": 0, "width": 1280, "height": max(900, height)}, timeout=15000)
            adapter = hashlib.sha256(json.dumps({"fields": site.field_selectors, "masks": site.masks, "ignore": site.ignore_patterns, "scenario": [asdict(s) for s in site.scenarios if s.id == scenario.id and s.page == page_kind]}, sort_keys=True).encode()).hexdigest()[:12]
            raw_payload = {key: payload.get(key) for key in ["version", "page", "url", "title", "h1", "blocks", "prices", "products", "meta_price", "controls", "sections"] if key in payload}
            document = {"raw_schema": "visible-v2", "observed_at": timestamp, "adapter": adapter, "ignore_patterns": site.ignore_patterns, "payload": raw_payload, "visual": visual_document, "consent": consent}
            if len(json.dumps(document).encode()) > 2_000_000:
                document = {"visual": visual_document}
                warnings.append("Dane źródłowe przekroczyły limit archiwum; zachowano pola i obraz bez możliwości ponownego przeliczenia tego odczytu.")
            snapshot = Snapshot(
                domain=site.domain, page=page_kind, scenario=scenario.id, url=canonical_url(page.url),
                observed_at=timestamp, title=payload.get("h1") or payload["title"], fields=fields,
                sections=sections, image="", renderer=self.renderer + "|extractor=" + self.extractor + "-" + adapter, warnings=warnings,
                quality="partial" if not data_ready else "ok" if fields else "visual",
                contract=CONTRACT + ":" + adapter, document=document,
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
            if len(seen) > 8:
                break
            try:
                capture = await self.capture(site, "projekt", selection["url"], Scenario("podstawowy", "Wariant podstawowy"), directory / "projekt.png")
                if page_identity(capture.snapshot.url) in {page_identity(site.home_url), page_identity(home.snapshot.url)}:
                    raise ValueError("Kandydat przekierował na stronę główną zamiast karty projektu")
                selection["name"] = capture.snapshot.title
                return selection, capture, warnings
            except Exception as exc:
                warnings.append(f"Kandydat niepotwierdzony: {selection['url']} ({type(exc).__name__})")
        return None, None, warnings + ["Nie wybrano poprawnej karty projektu; wymagane sprawdzenie domeny."]
