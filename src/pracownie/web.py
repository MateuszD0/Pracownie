"""Build a small, standalone GitHub Pages view of a verified daily report."""

from __future__ import annotations

import argparse
import base64
import copy
import io
import json
import os
import shutil
from importlib.resources import files
from pathlib import Path
from urllib.parse import unquote

from bs4 import BeautifulSoup
from PIL import Image

from .model import digest, safe_path
from .presentation import render_html
from .report import verify_outputs


def export_standalone(document: Path, destination: Path, downloads: dict | None = None, archive_url: str = "") -> None:
    """A portable comparison: real HTML content and embedded screenshot previews."""
    soup = BeautifulSoup(document.read_text(), "html.parser")
    dates = soup.select_one('#comparison-title')
    if dates:
        soup.title.string = 'Porównanie skanów · ' + dates.get_text()
        soup.select_one('#title').string = 'Porównanie skanów · ' + dates.get_text()
    soup.body['data-portable'] = 'true'
    full = json.loads(soup.select_one('#data').string)
    compact = {'rows': [{'domain': r['domain'], 'name': r['name'],
                        'complete': len(r['pages']) == 2 and all(p['communication'].get('daily') for p in r['pages']),
                        'missing': any(not p['current_read'] for p in r['pages'])} for r in full['rows']],
               'events': [{'id': e['id'], 'domain': e['domain'], 'tier': e['tier'],
                           'items': [{'page': i['page'], 'category': i['category'], 'bucket': i['business_bucket']} for i in e['items']]}
                          for e in full['briefing']['events'] if e['tier'] != 'technical']}
    for node in soup.select('script, dialog, #technical-summary, #all-prices, #export-visible, [data-watch], [data-open]'):
        node.decompose()
    watch = soup.select_one('#watch-only')
    if watch:
        watch.find_parent('label').decompose()
    payload = soup.new_tag('script', type='application/json', id='data')
    payload.string = json.dumps(compact, ensure_ascii=False).replace('<', '\\u003c')
    soup.body.append(payload)
    script = soup.new_tag('script')
    script.string = files('pracownie').joinpath('portable.js').read_text()
    soup.body.append(script)
    status = soup.new_tag('p', id='portable-status', attrs={'class': 'small', 'role': 'status'})
    soup.select_one('.quick-filters').insert_after(status)
    cache = {}
    for picture in soup.select('img[src]'):
        relative = unquote(picture['src'])
        important = picture.find_parent(id='brief-proofs') is not None
        cache_key = (relative, important)
        if cache_key not in cache:
            path = safe_path(document.parent, relative)
            with Image.open(path) as original:
                image = original.convert('RGB')
                image = image.crop((0, 0, image.width, min(image.height, 1800)))
                image.thumbnail((640, 900) if important else (320, 450))
                stream = io.BytesIO()
                image.save(stream, format='JPEG', quality=65 if important else 40, optimize=True)
                cache[cache_key] = 'data:image/jpeg;base64,' + base64.b64encode(stream.getvalue()).decode('ascii')
        picture['data-proof'] = picture['src']
        picture['src'] = cache[cache_key]
        if picture.parent.name == 'a':
            picture.parent.unwrap()
    for caption in soup.select('figcaption'):
        caption.append(' · Podgląd zapisanego zrzutu')
    for link in soup.select('a[href]'):
        href = link['href']
        if href.startswith(('#', 'https://', 'http://')):
            continue
        target = (downloads or {}).get(Path(href).name)
        if target:
            link['href'] = target
        elif link.find_parent('nav'):
            link.decompose()
        else:
            link.unwrap()
    notice = soup.new_tag('p', attrs={'class': 'visual-note standalone-note', 'id': 'standalone-notice'})
    notice.string = 'Wszystkie porównania tekstu są zapisane w tym pliku. Podglądy zrzutów są wbudowane; pełne obrazy są w archiwum raportu.'
    if archive_url:
        link = soup.new_tag('a', href=archive_url)
        link.string = ' Pobierz pełne zrzuty.'
        notice.append(link)
    soup.main.append(notice)
    destination.write_text(str(soup))


def prepare_web(source: Path, day: str, destination: Path) -> dict:
    verify_outputs(source, day)
    manifest = json.loads((source / day / "manifest.json").read_text())
    if manifest.get("owner") != "pracownie-monitor:v1":
        raise ValueError("Raport nie należy do monitora")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Katalog publikacji musi być pusty")
    directory = destination / day
    images = directory / "screenshots"
    images.mkdir(parents=True)
    view = copy.deepcopy(json.loads((source / day / "oferty.json").read_text()))
    converted = {}

    def visit(value):
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                if key == "evidence":
                    for name, path in list(item.items()):
                        if name not in {"przed", "po", "fragment_przed", "fragment_po", "zmieniony_obszar"}:
                            del item[name]
                            continue
                        if path not in manifest["files"] or not path.startswith(day + "/"):
                            raise ValueError("Zrzut spoza zweryfikowanego raportu")
                        if path not in converted:
                            original = safe_path(source, path)
                            filename = digest(original) + ".jpg"
                            target = images / filename
                            if not target.exists():
                                with Image.open(original) as image:
                                    rgb = image.convert("RGB")
                                    if rgb.width > 1280:
                                        rgb = rgb.resize((1280, round(rgb.height * 1280 / rgb.width)))
                                    rgb.save(target, quality=75, optimize=True, progressive=True)
                            converted[path] = f"{day}/screenshots/{filename}"
                        item[name] = converted[path]
                else:
                    visit(item)

    visit(view)
    (directory / "index.html").write_text(render_html(view))
    export_standalone(directory / "index.html", destination / f"porownanie-{day}.html")
    for filename in ["oferty.csv", "diagnostyka.txt", "dziennik-zmian.csv"]:
        shutil.copy2(source / day / filename, directory / filename)
    shutil.copy2(source / f"{day}.txt", destination / f"{day}.txt")
    (destination / ".nojekyll").touch()
    (destination / "index.html").write_text(
        '<!doctype html><html lang="pl"><meta charset="utf-8">'
        f'<meta http-equiv="refresh" content="0;url={day}/">'
        f'<title>Monitoring pracowni · {day}</title><p><a href="{day}/">Otwórz raport z {day}</a></p></html>'
    )
    return {"day": day, "images": len(set(converted.values())), "bytes": sum(p.stat().st_size for p in destination.rglob("*") if p.is_file())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("raporty"))
    parser.add_argument("--destination", type=Path, default=Path(".monitor/pages"))
    parser.add_argument("--check-pages", action="store_true")
    args = parser.parse_args()
    if args.check_pages:
        from .github import GitHubStore
        remote = GitHubStore(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"])
        try:
            response = remote.client.get(remote.prefix + "/pages")
            enabled = response.status_code == 200 and response.json().get("build_type") == "workflow"
            with Path(os.environ["GITHUB_OUTPUT"]).open("a") as stream:
                stream.write("enabled=" + str(enabled).lower() + "\n")
            print("GitHub Pages gotowe." if enabled else "Widok HTML jest w wydaniu. Adres WWW wymaga Settings → Pages → Source: GitHub Actions.")
        finally:
            remote.close()
        return
    days = sorted(p.parent.name for p in args.source.glob("????-??-??/manifest.json"))
    if not days:
        raise ValueError("Brak raportu do publikacji")
    print(json.dumps(prepare_web(args.source, days[-1], args.destination)))


if __name__ == "__main__":
    main()
