"""Read-only HTTP inventory. Candidates are evidence, not verified product selections."""
import concurrent.futures
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from pracownie.browser import project_candidates
from pracownie.model import load_sites


def inspect(site):
    result = {"domain": site.domain, "observed_at": datetime.now(UTC).isoformat(), "status": "unrun"}
    try:
        with httpx.Client(follow_redirects=True, timeout=20, headers={"User-Agent": "PracownieMonitor/0.1 (+daily public offer monitoring)"}) as client:
            response = client.get(site.home_url)
        result.update(status=response.status_code, final_url=str(response.url), bytes=len(response.content))
        if response.status_code != 200:
            return result
        soup = BeautifulSoup(response.text, "html.parser")
        result["title"] = soup.title.get_text(" ", strip=True) if soup.title else ""
        links = []
        for anchor in soup.select("a[href]"):
            if anchor.find_parent(["nav", "footer"]):
                continue
            context = anchor.find_parent(["article", "li"])
            if context is None:
                context = anchor.find_parent(class_=re.compile("card|product|projekt|offer|item", re.I))
            links.append({"url": urljoin(str(response.url), anchor.get("href", "")),
                          "text": anchor.get_text(" ", strip=True) or (anchor.find("img").get("alt", "") if anchor.find("img") else ""),
                          "context": context.get_text(" ", strip=True)[:500] if context else "", "image": bool(anchor.find("img"))})
        result["candidates"] = [item for _, item in project_candidates(site, {"links": links, "url": str(response.url)})][:20]
        result["ranking_urls"] = list(dict.fromkeys(link["url"] for link in links if re.search(r"bestseller|najpopular|najlepiej sprzed", link["text"], re.I)))[:5]
        result["resource_hosts"] = sorted({urlsplit(urljoin(str(response.url), e.get("src") or e.get("href", ""))).hostname for e in soup.select("script[src],link[rel=stylesheet],img[src]")} - {None})
    except Exception as exc:
        result.update(status="error", error=str(exc).splitlines()[0][:400])
    return result


def main():
    output = Path(sys.argv[1] if len(sys.argv) > 1 else ".monitor/inspection.json")
    sites = load_sites(Path("config/sites.json"))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(inspect, sites))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    for result in results:
        print(result["domain"], result["status"], "kandydaci:", len(result.get("candidates", [])), result.get("error", ""))


if __name__ == "__main__":
    main()
