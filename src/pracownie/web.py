"""Build a small, standalone GitHub Pages view of a verified daily report."""

from __future__ import annotations

import argparse
import base64
import copy
import io
import json
import os
import shutil
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
    for node in soup.select('script, dialog, button, select, .filters, noscript'):
        node.decompose()
    cache = {}
    for picture in soup.select('img[src]'):
        relative = unquote(picture['src'])
        if relative not in cache:
            path = safe_path(document.parent, relative)
            with Image.open(path) as original:
                image = original.convert('RGB')
                image = image.crop((0, 0, image.width, min(image.height, 1800)))
                image.thumbnail((320, 450))
                stream = io.BytesIO()
                image.save(stream, format='JPEG', quality=40, optimize=True)
                cache[relative] = 'data:image/jpeg;base64,' + base64.b64encode(stream.getvalue()).decode('ascii')
        picture['src'] = cache[relative]
        if picture.parent.name == 'a':
            picture.parent.unwrap()
    for caption in soup.select('figcaption'):
        caption.append(' · Podgląd początku strony')
    for link in soup.select('a[href]'):
        href = link['href']
        if href.startswith(('#', 'https://', 'http://')):
            continue
        target = (downloads or {}).get(Path(href).name)
        if target:
            link['href'] = target
        else:
            link.unwrap()
    notice = soup.new_tag('p', attrs={'class': 'visual-note', 'id': 'standalone-notice'})
    notice.string = 'Wszystkie porównania tekstu są zapisane w tym pliku. Podglądy zrzutów są wbudowane; pełne obrazy są w archiwum raportu.'
    if archive_url:
        link = soup.new_tag('a', href=archive_url)
        link.string = ' Pobierz pełne zrzuty.'
        notice.append(link)
    soup.main.insert(0, notice)
    # The enhanced offers table is redundant with the fully rendered page
    # sections when scripts are disabled. Never show an empty table as data.
    empty_rows = soup.select_one('#rows')
    if empty_rows and not empty_rows.select('tr'):
        table_box = empty_rows.find_parent(class_='table-box')
        heading = table_box.find_previous_sibling(class_='section-head')
        if heading:
            heading.decompose()
        table_box.decompose()
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
                        if name not in {"przed", "po"}:
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
    for filename in ["oferty.csv", "diagnostyka.txt"]:
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
