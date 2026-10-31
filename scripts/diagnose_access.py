"""Inspect public redirects, TLS and control geometry on the production runner."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup
from discover_projects import discover
from playwright.async_api import async_playwright

from pracownie.github import GitHubStore
from pracownie.model import load_sites, now_iso

DETAIL = r"""() => ({
 title:document.title, url:location.href, canonical:document.querySelector('link[rel=canonical]')?.href,
 headings:[...document.querySelectorAll('h1,h2')].filter(e=>e.checkVisibility({visibilityProperty:true,opacityProperty:true})).slice(0,12).map(e=>e.innerText),
 length:document.body?.innerText.length || 0,
 text:(document.body?.innerText || '').slice(0,20000),
 links:[...document.querySelectorAll('a[href]')].slice(0,250).map(e=>({url:e.href,text:(e.innerText||e.querySelector('img')?.alt||'').slice(0,140)})),
 products:[...document.querySelectorAll('a[href]')].filter(e=>!e.closest('nav,header,footer') && !/kategoria-produktu/.test(e.href) && /produkt|project|projekt|,p\d|\d\.html/.test(e.href)).slice(0,150).map(e=>({url:e.href,text:(e.innerText||e.querySelector('img')?.alt||'').slice(0,120)})),
 prices:[...document.querySelectorAll('[itemprop=price],ins,del,[class*=price],[class*=Price],[class*=cena]')].slice(0,70).map(e=>({selector:e.id?'#'+e.id:e.tagName+'.'+String(e.className).replaceAll(' ','.'),text:(e.innerText||e.getAttribute('content')||'').slice(0,180),parent:e.parentElement?.outerHTML.slice(0,1200)})),
 controls:[...document.querySelectorAll('input[type=radio],input[type=checkbox],[role=tab],summary,a[href*=koszyk],a[href*=zamow],button[type=submit]')].slice(0,65).map(e=>({id:e.id,name:e.name,type:e.type,role:e.getAttribute('role'),text:(e.labels?.[0]?.innerText||e.innerText||e.getAttribute('aria-label')||'').slice(0,160),html:e.outerHTML.slice(0,500),visible:e.checkVisibility({visibilityProperty:true,opacityProperty:true}),rect:JSON.stringify(e.getBoundingClientRect()),label:e.labels?.[0]?.outerHTML.slice(0,600),parent:e.parentElement?.outerHTML.slice(0,900)}))
})"""


async def inspect(sites, *, verification_wait=1.5, headed=False, discover_projects=False, disable_http2=False, extra_urls=None, probe_cookies=False):
    output = {"observed_at": now_iso(), "sites": []}
    async with async_playwright() as manager:
        browser = await manager.chromium.launch(headless=not headed, args=['--disable-http2'] if disable_http2 else [])
        semaphore = asyncio.Semaphore(3)

        async def one(site):
            async with semaphore:
                context = await browser.new_context(locale="pl-PL", viewport={"width":1280,"height":900}, user_agent=site.user_agent)
                row = {"domain": site.domain, "checks": []}
                urls = [site.home_url]
                if site.domain in {"archdesign.pl", "mtmstyl.com.pl", "nowoczesne-projektydomow.pl"}:
                    urls.append("http://" + urlsplit(site.home_url).netloc)
                if site.project_url:
                    urls.append(site.project_url)
                urls.extend(site.discovery_links)
                urls.extend((extra_urls or {}).get(site.domain, []))
                for url in dict.fromkeys(urls):
                    page = await context.new_page()
                    check = {"requested_url": url, "headed": headed, "navigation": []}
                    def navigation(response, page=page, check=check):
                        if response.request.is_navigation_request() and response.request.frame == page.main_frame:
                            check['navigation'].append({'status': response.status, 'url': response.url})
                    page.on('response', navigation)
                    try:
                        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
                            response = await client.get(url)
                            check['http'] = {'status': response.status_code, 'url': str(response.url)}
                            soup = BeautifulSoup(response.text, 'html.parser')
                            check['http']['title'] = soup.title.get_text(' ', strip=True) if soup.title else ''
                            check['http']['text'] = soup.get_text(' ', strip=True)[:20000]
                            check['http']['links'] = [{'url': a['href'], 'text': a.get_text(' ', strip=True)[:140]} for a in soup.select('a[href]')][:250]
                    except httpx.HTTPError as exc:
                        check['http'] = {'error': type(exc).__name__}
                    try:
                        response = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                        check["status"] = response.status if response else None
                        elapsed = 0
                        check['timeline'] = []
                        while elapsed < verification_wait:
                            pause = min(5, verification_wait - elapsed)
                            await page.wait_for_timeout(pause * 1000)
                            elapsed += pause
                            check['timeline'].append({'after_seconds': elapsed,
                                                      'title': await page.title(),
                                                      'text': (await page.locator('body').inner_text())[:700]})
                        if check['navigation']:
                            check['status'] = check['navigation'][-1]['status']
                        check.update(await page.evaluate(DETAIL))
                        if probe_cookies:
                            from pracownie.browser import BrowserScanner
                            scanner = BrowserScanner()
                            check['cookie_probes'] = []
                            for attempt in range(3):
                                probe = {'attempt': attempt + 1}
                                try:
                                    await scanner.cookies(page, site)
                                except Exception as exc:
                                    probe['error'] = str(exc)[:1600]
                                await page.wait_for_timeout(2000)
                                probe['consent_state'] = {c['name']: c['value'] for c in await context.cookies()
                                    if c['name'] in {'cmplz_marketing', 'cmplz_statistics', 'cmplz_preferences', 'cmplz_functional', 'cmplz_banner-status'}}
                                probe['panels'] = await page.locator('[role=dialog],#cn-close-notice,.cmplz-deny').evaluate_all("""es => es.map(e=>({
                                  html:e.outerHTML.slice(0,1800),visible:e.checkVisibility({visibilityProperty:true,opacityProperty:true}),
                                  rect:JSON.stringify(e.getBoundingClientRect()),
                                  controls:[...e.querySelectorAll('button,a')].map(b=>({html:b.outerHTML.slice(0,700),visible:b.checkVisibility({visibilityProperty:true,opacityProperty:true})}))
                                }))""")
                                check['cookie_probes'].append(probe)
                    except Exception as exc:
                        check.update(error=str(exc).splitlines()[0], url=page.url)
                    row["checks"].append(check)
                    await page.close()
                output["sites"].append(row)
                await context.close()
                if discover_projects:
                    row['curation'] = await asyncio.to_thread(discover, site)
                print("Diagnostyka " + site.domain, flush=True)

        await asyncio.gather(*(one(site) for site in sites))
        await browser.close()
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domains", default="archido.pl,domydlanas.pl,lk-projekt.pl,archi-projekt.com.pl,dompp.pl,housecollection.pl")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--verification-wait", type=float, default=1.5)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--disable-http2", action="store_true")
    parser.add_argument("--probe-cookies", action="store_true")
    parser.add_argument("--extra-urls", default="{}", help="Publiczne adresy do diagnostyki: obiekt domena → lista URL")
    args = parser.parse_args()
    if not 0 <= args.verification_wait <= 60:
        raise SystemExit('Czas diagnostyki musi być w zakresie 0–60 s')
    selected = set(args.domains.split(","))
    sites = [s for s in load_sites(Path("config/sites.json")) if s.domain in selected]
    if selected != {s.domain for s in sites}:
        raise SystemExit("Nieznana domena diagnostyki")
    extra_urls = json.loads(args.extra_urls)
    from pracownie.browser import allowed_url
    if not isinstance(extra_urls, dict) or set(extra_urls) - selected or any(not isinstance(extra_urls.get(site.domain, []), list) or len(extra_urls.get(site.domain, [])) > 4 or any(not isinstance(url, str) or not allowed_url(site, url) for url in extra_urls.get(site.domain, [])) for site in sites):
        raise SystemExit('Diagnostyka dopuszcza do czterech adresów na domenę z konfiguracji')
    result = asyncio.run(inspect(sites, verification_wait=args.verification_wait, headed=args.headed, discover_projects=args.discover, disable_http2=args.disable_http2, extra_urls=extra_urls, probe_cookies=args.probe_cookies))
    path = Path(".monitor/access-diagnostics.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if args.publish:
        remote = GitHubStore(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"])
        try:
            release = remote.release("monitor-access-diagnostics", create=True)
            remote.upload(release, f"access-{os.environ['GITHUB_RUN_ID']}.json", path)
        finally:
            remote.close()
