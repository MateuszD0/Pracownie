"""Build a small, standalone GitHub Pages view of a verified daily report."""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
from pathlib import Path

from PIL import Image

from .model import digest, safe_path
from .presentation import render_html
from .report import verify_outputs


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
