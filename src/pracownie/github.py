from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import re
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .model import digest, json_bytes, now_iso, slug
from .presentation import render_markdown
from .state import StateStore

OWNER_MARKER = "<!-- pracownie-monitor:v1 -->"


class GitHubStore:
    def __init__(self, repository: str, token: str, namespace: str = "monitor", client: httpx.Client | None = None):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("Niepoprawna nazwa repozytorium")
        if not token:
            raise ValueError("Brak GITHUB_TOKEN/GH_TOKEN; nie zapisano danych zdalnych")
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,30}", namespace):
            raise ValueError("Niepoprawny namespace")
        self.repo = repository
        self.namespace = namespace
        self.prefix = f"https://api.github.com/repos/{repository}"
        self.client = client or httpx.Client(
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
            timeout=90, follow_redirects=True,
        )
        self.owns_client = client is None

    def close(self):
        if self.owns_client:
            self.client.close()

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        for attempt in range(3):
            response = self.client.request(method, url, **kwargs)
            if method == "GET" and (response.status_code in {429, 502, 503, 504}) and attempt < 2:
                time.sleep(min(float(response.headers.get("retry-after", 2 ** attempt)), 10))
                continue
            if response.status_code >= 400:
                raise RuntimeError(f"GitHub HTTP {response.status_code}: {method} {urlsplit(url).path}; sprawdź dostęp i uprawnienia.")
            return response
        raise RuntimeError("Wyczerpano ponowienia GitHub")

    def preflight(self) -> dict:
        data = self.request("GET", self.prefix).json()
        if data.get("archived"):
            raise RuntimeError("Repozytorium jest zarchiwizowane")
        # Scoped installation/Actions tokens may report push:false despite contents:write.
        # Repository metadata does not prove or disprove permission to publish Releases.
        return {"repository": self.repo, "private": data.get("private"), "default_branch": data.get("default_branch"), "reported_git_push": data.get("permissions", {}).get("push")}

    def pages(self, url: str) -> list:
        output = []
        page = 1
        while True:
            records = self.request("GET", url, params={"per_page": 100, "page": page}).json()
            if not isinstance(records, list):
                raise ValueError("Niepoprawna odpowiedź listowania GitHub")
            output.extend(records)
            if len(records) < 100:
                return output
            page += 1

    def release(self, tag: str, create: bool = False) -> dict | None:
        response = self.client.get(f"{self.prefix}/releases/tags/{tag}")
        if response.status_code == 404 and create:
            return self.request("POST", f"{self.prefix}/releases", json={
                "tag_name": tag, "name": tag, "body": OWNER_MARKER, "draft": False,
                "prerelease": True, "make_latest": "false",
            }).json()
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise RuntimeError(f"GitHub HTTP {response.status_code} podczas odczytu wydania")
        data = response.json()
        if OWNER_MARKER not in (data.get("body") or ""):
            raise ValueError(f"Wydanie {tag} nie należy do monitora; nie zmieniono go")
        return data

    def assets(self, release: dict) -> list[dict]:
        return self.pages(f"{self.prefix}/releases/{release['id']}/assets")

    def download(self, asset: dict, destination: Path, expected_hash: str | None = None):
        destination.parent.mkdir(parents=True, exist_ok=True)
        url = f"{self.prefix}/releases/assets/{asset['id']}"
        total = 0
        with self.client.stream("GET", url, headers={"Accept": "application/octet-stream"}) as response:
            if response.status_code >= 400:
                raise RuntimeError(f"Nie udało się pobrać pliku GitHub: HTTP {response.status_code}")
            with destination.open("wb") as stream:
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > 1_500_000_000:
                        raise ValueError("Plik GitHub przekracza limit pobierania")
                    stream.write(chunk)
        if expected_hash and digest(destination) != expected_hash:
            destination.unlink(missing_ok=True)
            raise ValueError("Niepoprawna suma kontrolna pliku GitHub")

    def upload(self, release: dict, name: str, path: Path) -> dict:
        url = release["upload_url"].split("{")[0]
        if urlsplit(url).hostname != "uploads.github.com":
            raise ValueError("Nieoczekiwany host wysyłania GitHub; nie wysłano tokenu")
        if path.stat().st_size >= 2 * 1024**3:
            raise ValueError("Przekroczono limit 2 GiB pojedynczego pliku; wymagany podział archiwum")
        with path.open("rb") as stream:
            response = self.request("POST", url, params={"name": name}, content=stream,
                                    headers={"Content-Type": mimetypes.guess_type(path.name)[0] or "application/octet-stream", "Content-Length": str(path.stat().st_size)})
        asset = response.json()
        expected = digest(path)
        if asset.get("size") != path.stat().st_size:
            raise ValueError("Niepełny zapis pliku GitHub")
        if asset.get("digest"):
            if asset["digest"] != "sha256:" + expected:
                raise ValueError("Niepoprawna suma kontrolna zapisanego pliku GitHub")
        else:
            with tempfile.TemporaryDirectory() as temporary:
                self.download(asset, Path(temporary) / "verify", expected)
        return asset

    def pull(self, store: StateStore) -> dict | None:
        release = self.release(f"{self.namespace}-state-v1")
        if not release:
            return None
        assets = self.assets(release)
        commits = sorted((a for a in assets if a["name"].startswith("commit-") and a["name"].endswith(".json")), key=lambda a: a["name"], reverse=True)
        if not commits:
            return None
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.download(commits[0], root / "commit.json")
            record = json.loads((root / "commit.json").read_text())
            if record.get("owner") != "pracownie-monitor:v1":
                raise ValueError("Niepoprawny właściciel manifestu stanu")
            state_asset = next((a for a in assets if a["name"] == record["asset"]), None)
            if not state_asset:
                raise ValueError("Zatwierdzony stan nie ma archiwum; nie utworzono pustej historii")
            self.download(state_asset, root / "state.zip", record["sha256"])
            store.restore(root / "state.zip", record["sha256"])
        return record

    def publish(self, store: StateStore, output: Path, day: str, report_archive: Path, run_id: str) -> dict:
        stamp = slug(run_id)
        report_release = self.release(f"{self.namespace}-report-{day}", create=True)
        assert report_release is not None
        text_asset = self.upload(report_release, f"{day}-{stamp}.txt", output / f"{day}.txt")
        csv_asset = self.upload(report_release, f"{day}-{stamp}-oferty.csv", output / day / "oferty.csv")
        journal_asset = self.upload(report_release, f"{day}-{stamp}-dziennik-zmian.csv", output / day / "dziennik-zmian.csv")
        diagnostic_asset = self.upload(report_release, f"{day}-{stamp}-diagnostyka.txt", output / day / "diagnostyka.txt")
        from .web import export_standalone, prepare_web
        with tempfile.TemporaryDirectory() as temporary:
            web_root = Path(temporary)
            prepare_web(output, day, web_root / "web")
            import shutil
            web_archive = Path(shutil.make_archive(str(web_root / "widok"), "zip", web_root / "web"))
            html_asset = self.upload(report_release, f"{day}-{stamp}-widok.zip", web_archive)
            standalone = web_root / "web" / f"porownanie-{day}.html"
            export_standalone(web_root / "web" / day / "index.html", standalone, {
                f"{day}.txt": text_asset["browser_download_url"],
                "oferty.csv": csv_asset["browser_download_url"],
                "dziennik-zmian.csv": journal_asset["browser_download_url"],
                "diagnostyka.txt": diagnostic_asset["browser_download_url"],
            }, html_asset["browser_download_url"])
            standalone_asset = self.upload(report_release, f"{day}-{stamp}-porownanie.html", standalone)
        view = json.loads((output / day / "oferty.json").read_text())
        previews = {}
        preview_assets = []
        proof_candidates = [e for e in view.get("journal", []) if e["category"] == "obraz"] + [e for r in view["rows"] for e in r["events"]][:6]
        for event in proof_candidates:
            path = event["evidence"].get("zmieniony_obszar") or event["evidence"].get("roznice") or event["evidence"].get("po")
            if not path or path in previews:
                continue
            from .model import safe_path
            preview = self.upload(report_release, f"{day}-{stamp}-dowod-{len(previews)+1}.png", safe_path(output, path))
            previews[path] = preview["browser_download_url"]
            preview_assets.append(preview["id"])
        zip_asset = self.upload(report_release, f"{day}-{stamp}.zip", report_archive)
        state_release = self.release(f"{self.namespace}-state-v1", create=True)
        assert state_release is not None
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store.export(root / "state.zip")
            state_name = f"state-{stamp}.zip"
            state_asset = self.upload(state_release, state_name, root / "state.zip")
            record = {"schema": 1, "owner": "pracownie-monitor:v1", "day": day, "run_id": run_id,
                      "committed_at": now_iso(), "asset": state_name, "sha256": digest(root / "state.zip"),
                      "report_release_id": report_release["id"], "report_assets": [text_asset["id"], csv_asset["id"], journal_asset["id"], diagnostic_asset["id"], html_asset["id"], standalone_asset["id"], *preview_assets, zip_asset["id"]],
                      "report_files": {"txt": text_asset["id"], "csv": csv_asset["id"], "journal_csv": journal_asset["id"], "diagnostics": diagnostic_asset["id"], "html_zip": html_asset["id"], "html": standalone_asset["id"], "zip": zip_asset["id"]}}
            # Both report files and state have been verified. Make the daily report visible first.
            summary = render_markdown(view, previews)
            published_at = now_iso()
            self.request("PATCH", f"{self.prefix}/releases/{report_release['id']}", json={
                "name": f"Raport {day}", "prerelease": False, "make_latest": "false",
                "body": OWNER_MARKER + f"\n\n[Porównanie HTML — jeden plik]({standalone_asset['browser_download_url']}) · [Tabela zmian CSV]({journal_asset['browser_download_url']}) · [Raport TXT]({text_asset['browser_download_url']}) · [Ceny CSV]({csv_asset['browser_download_url']}) · [Raport HTML ze zrzutami]({html_asset['browser_download_url']}) · [Pełne archiwum ZIP]({zip_asset['browser_download_url']}) · [Diagnostyka]({diagnostic_asset['browser_download_url']})\n\n**Porównanie HTML — jeden plik** zawiera widoczne od razu teksty przed/po i wbudowane podglądy obrazów; działa bez skryptów i rozpakowywania archiwum. Pełne zrzuty są w **Raporcie HTML ze zrzutami**.\n\n" + summary + f"\n\nPublikacja: {published_at}.",
            })
            (root / "commit.json").write_bytes(json_bytes(record))
            self.upload(state_release, f"commit-{stamp}.json", root / "commit.json")
            # A commit manifest uploaded last is the only pointer used by subsequent runners.
            self._collect_state(state_release)
        keep_reports = set(record["report_assets"])
        for asset in self.assets(report_release):
            if asset["id"] not in keep_reports and asset["name"].startswith(day + "-"):
                self.request("DELETE", f"{self.prefix}/releases/assets/{asset['id']}")
        return {"report_url": report_release["html_url"], "state_asset_id": state_asset["id"], "published_at": published_at}

    def _collect_state(self, release: dict):
        assets = self.assets(release)
        commits = sorted((a for a in assets if a["name"].startswith("commit-") and a["name"].endswith(".json")), key=lambda a: a["name"], reverse=True)
        keep = set()
        with tempfile.TemporaryDirectory() as temporary:
            for index, commit in enumerate(commits[:2]):
                path = Path(temporary) / f"{index}.json"
                self.download(commit, path)
                record = json.loads(path.read_text())
                keep.update({commit["name"], record["asset"]})
        for asset in assets:
            if asset["name"].startswith(("commit-", "state-")) and asset["name"] not in keep:
                self.request("DELETE", f"{self.prefix}/releases/assets/{asset['id']}")

    def cleanup(self, day: str, retention_days: int = 180, dry_run: bool = True) -> list[str]:
        cutoff = (date.fromisoformat(day) - timedelta(days=retention_days)).isoformat()
        removed = []
        pattern = re.compile(re.escape(self.namespace) + r"-report-(\d{4}-\d{2}-\d{2})$")
        for release in self.pages(f"{self.prefix}/releases"):
            match = pattern.fullmatch(release["tag_name"])
            if not match or OWNER_MARKER not in (release.get("body") or ""):
                continue
            date.fromisoformat(match[1])
            if match[1] <= cutoff:
                removed.append(release["tag_name"])
                if not dry_run:
                    self.request("DELETE", f"{self.prefix}/releases/{release['id']}")
        return removed

    def update_index(self) -> str:
        """Publish useful daily navigation, also keeping repository activity current."""
        filename = "RAPORTY.md" if self.namespace == "monitor" else "RAPORTY-" + self.namespace.upper() + ".md"
        pattern = re.compile(re.escape(self.namespace) + r"-report-(\d{4}-\d{2}-\d{2})$")
        rows = []
        for release in self.pages(f"{self.prefix}/releases"):
            match = pattern.fullmatch(release["tag_name"])
            body = release.get("body") or ""
            if not match or OWNER_MARKER not in body:
                continue
            text = re.search(r"\[Raport TXT\]\((https://[^)]+)\)", body)
            archive = re.search(r"\[Pełne archiwum ZIP\]\((https://[^)]+)\)", body)
            csv_link = re.search(r"\[Tabela zmian CSV\]\((https://[^)]+)\)", body) or re.search(r"\[Ceny CSV\]\((https://[^)]+)\)", body)
            html_link = re.search(r"\[Raport HTML ze zrzutami\]\((https://[^)]+)\)", body)
            portable = re.search(r"\[Porównanie HTML — jeden plik\]\((https://[^)]+)\)", body)
            if not text or not archive:
                continue
            allowed = f"https://github.com/{self.repo}/releases/download/"
            if any(link and not link[1].startswith(allowed) for link in [text, archive, csv_link, html_link, portable]):
                raise ValueError("Nieoczekiwany adres plików w indeksie raportów")
            rows.append((match[1], text[1], archive[1], release["html_url"], csv_link[1] if csv_link else None, html_link[1] if html_link else archive[1], portable[1] if portable else None))
        lines = [OWNER_MARKER, "", "**Raporty monitoringu ofert**", "", "Raport zaczyna się od dziennej tabeli zmian cen, promocji, dodatków i wyglądu, z linkiem do źródła oraz dowodami przed/po. CSV zawiera tę samą listę zmian; w starszych raportach może zawierać tylko ceny. ZIP zachowuje pełne obrazy. Notatki przechowuj osobno.", "", "| Dzień | Czytelny raport | Tabela CSV | Opis TXT | HTML i zrzuty |", "| --- | --- | --- | --- | --- |"]
        lines.extend(f"| {day} | [Otwórz raport]({url}) | " + (f"[CSV]({csv_url})" if csv_url else "—") + f" | [TXT]({text}) | " + (f"[HTML]({portable}) · " if portable else "") + f"[ZIP]({html_url}) |" for day, text, archive, url, csv_url, html_url, portable in sorted(rows, reverse=True))
        content = ("\n".join(lines) + "\n").encode()
        endpoint = f"{self.prefix}/contents/{filename}"
        existing = self.client.get(endpoint)
        payload = {"message": "Update daily monitoring report index", "content": base64.b64encode(content).decode()}
        if existing.status_code == 200:
            data = existing.json()
            previous = base64.b64decode(data["content"])
            if OWNER_MARKER.encode() not in previous:
                raise ValueError(f"Plik {filename} nie należy do monitora; nie nadpisano go")
            if previous == content:
                return data["html_url"]
            payload["sha"] = data["sha"]
        elif existing.status_code != 404:
            raise RuntimeError(f"Nie można odczytać indeksu raportów: HTTP {existing.status_code}")
        result = self.request("PUT", endpoint, json=payload).json()
        return result["content"]["html_url"]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
