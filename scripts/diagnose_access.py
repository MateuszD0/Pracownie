"""Inspect public redirects, TLS and control geometry on the production runner."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

from pracownie.github import GitHubStore
from pracownie.model import load_sites, now_iso

DETAIL = r"""() => ({
 title:document.title, url:location.href, canonical:document.querySelector('link[rel=canonical]')?.href,
 headings:[...document.querySelectorAll('h1,h2')].slice(0,12).map(e=>e.innerText),
 length:document.body?.innerText.length || 0,
 products:[...document.querySelectorAll('a[href]')].filter(e=>!e.closest('nav,header,footer') && !/kategoria-produktu/.test(e.href) && /produkt|project|projekt|,p\d|\d\.html/.test(e.href)).slice(0,150).map(e=>({url:e.href,text:(e.innerText||e.querySelector('img')?.alt||'').slice(0,120)})),
 prices:[...document.querySelectorAll('[itemprop=price],ins,del,[class*=price],[class*=Price],[class*=cena]')].slice(0,70).map(e=>({selector:e.id?'#'+e.id:e.tagName+'.'+String(e.className).replaceAll(' ','.'),text:(e.innerText||e.getAttribute('content')||'').slice(0,180),parent:e.parentElement?.outerHTML.slice(0,1200)})),
 controls:[...document.querySelectorAll('input[type=radio],input[type=checkbox],[role=tab],summary,a[href*=koszyk],a[href*=zamow],button[type=submit]')].slice(0,65).map(e=>({id:e.id,name:e.name,type:e.type,role:e.getAttribute('role'),text:(e.labels?.[0]?.innerText||e.innerText||e.getAttribute('aria-label')||'').slice(0,160),html:e.outerHTML.slice(0,500),visible:e.checkVisibility({visibilityProperty:true,opacityProperty:true}),rect:JSON.stringify(e.getBoundingClientRect()),label:e.labels?.[0]?.outerHTML.slice(0,600),parent:e.parentElement?.outerHTML.slice(0,900)}))
})"""


async def inspect(sites):
    output = {"observed_at": now_iso(), "sites": []}
    async with async_playwright() as manager:
        browser = await manager.chromium.launch()
        semaphore = asyncio.Semaphore(3)

        async def one(site):
            async with semaphore:
                context = await browser.new_context(locale="pl-PL", viewport={"width":1280,"height":900})
                row = {"domain": site.domain, "checks": []}
                urls = [site.home_url]
                if site.domain in {"archdesign.pl", "mtmstyl.com.pl", "nowoczesne-projektydomow.pl"}:
                    urls.append("http://" + urlsplit(site.home_url).netloc)
                if site.project_url:
                    urls.append(site.project_url)
                for url in urls:
                    page = await context.new_page()
                    check = {"requested_url": url}
                    try:
                        response = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                        check["status"] = response.status if response else None
                        await page.wait_for_timeout(1500)
                        check.update(await page.evaluate(DETAIL))
                    except Exception as exc:
                        check.update(error=str(exc).splitlines()[0], url=page.url)
                    row["checks"].append(check)
                    await page.close()
                output["sites"].append(row)
                await context.close()
                print("Diagnostyka " + site.domain, flush=True)

        await asyncio.gather(*(one(site) for site in sites))
        await browser.close()
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domains", default="archdesign.pl,mtmstyl.com.pl,nowoczesne-projektydomow.pl,archdom.pl,archido.pl,domdlaciebie.com.pl,dompp.pl,domydlanas.pl,lk-projekt.pl,hbstudio.pl,archipelag.pl,dompasja.pl,domenadom.pl,domywstylu.pl")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    selected = set(args.domains.split(","))
    sites = [s for s in load_sites(Path("config/sites.json")) if s.domain in selected]
    if selected != {s.domain for s in sites}:
        raise SystemExit("Nieznana domena diagnostyki")
    result = asyncio.run(inspect(sites))
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
