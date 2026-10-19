"""Read-only curation aid: verify candidates against HTTP-rendered structured data and headings."""
import argparse
import concurrent.futures
import json
from dataclasses import replace
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from inspect_sites import inspect

from pracownie.extract import page_identity, validate_payload
from pracownie.model import load_sites


def products_from(value):
    if isinstance(value, list):
        return [p for child in value for p in products_from(child)]
    if not isinstance(value, dict):
        return []
    output = [value] if "Product" in ([value.get("@type")] if isinstance(value.get("@type"), str) else value.get("@type", [])) else []
    for key in ["@graph", "mainEntity", "itemListElement", "item"]:
        if key in value:
            output.extend(products_from(value[key]))
    return output


def discover(site):
    row = {"domain": site.domain, "verified_candidate": None, "failures": []}
    home = inspect(site)
    candidates = []
    for ranking in list(dict.fromkeys(site.discovery_links + home.get("ranking_urls", [])))[:2]:
        listing = inspect(replace(site, home_url=ranking))
        for candidate in listing.get("candidates", []):
            candidate["basis"] = "Pierwszy poprawny projekt z sekcji: " + listing.get("title", ranking)
            candidates.append(candidate)
    candidates.extend(home.get("candidates", []))
    seen = set()
    with httpx.Client(follow_redirects=True, timeout=15) as client:
        for candidate in candidates:
            if candidate["url"] in seen:
                continue
            seen.add(candidate["url"])
            if len(seen) > 8:
                break
            try:
                response = client.get(candidate["url"])
                response.raise_for_status()
                if page_identity(str(response.url)) in {page_identity(site.home_url), page_identity(home.get("final_url", site.home_url))}:
                    raise ValueError("Adres przekierował na stronę główną")
                soup = BeautifulSoup(response.text, "html.parser")
                products = []
                for element in soup.select('script[type="application/ld+json"]'):
                    try:
                        products.extend(products_from(json.loads(element.get_text())))
                    except ValueError:
                        pass
                heading = soup.select_one('h1.product_title,h1[itemprop=name]') or soup.select_one('main h1') or soup.select_one('article h1') or soup.h1
                payload = {"title": soup.title.get_text(" ", strip=True) if soup.title else "", "h1": heading.get_text(" ", strip=True) if heading else "", "text": soup.get_text(" ", strip=True), "products": products}
                validate_payload(payload, product=True)
                candidate.update(name=payload["h1"] or payload["title"], verified_url=str(response.url), structured_products=len(products))
                row["verified_candidate"] = candidate
                return row
            except Exception as exc:
                row["failures"].append({"url": candidate["url"], "error": str(exc)[:250]})
    return row


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domains", required=True)
    parser.add_argument("--output", type=Path, default=Path(".monitor/discovery.json"))
    args = parser.parse_args()
    domains = set(args.domains.split(","))
    sites = [site for site in load_sites(Path("config/sites.json")) if site.domain in domains]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(discover, sites))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    for result in results:
        print(result["domain"], result["verified_candidate"] or "BRAK POTWIERDZONEJ KARTY")
