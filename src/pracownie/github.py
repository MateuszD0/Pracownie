from __future__ import annotations

import hashlib
import json
import re
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .model import digest, json_bytes, now_iso, slug
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
        if data.get("permissions", {}).get("push") is False:
            raise RuntimeError("Token ma odczyt repozytorium, ale brak uprawnienia zapisu")
        if data.get("archived"):
            raise RuntimeError("Repozytorium jest zarchiwizowane")
        return {"repository": self.repo, "private": data.get("private"), "default_branch": data.get("default_branch")}

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
                                    headers={"Content-Type": "application/octet-stream", "Content-Length": str(path.stat().st_size)})
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
                      "report_release_id": report_release["id"], "report_assets": [text_asset["id"], zip_asset["id"]]}
            # Both report files and state have been verified. Make the daily report visible first.
            excerpt = (output / f"{day}.txt").read_text().split("SZCZEGÓŁY WEDŁUG DOMEN")[0][:5000]
            published_at = now_iso()
            self.request("PATCH", f"{self.prefix}/releases/{report_release['id']}", json={
                "name": f"Raport {day}", "prerelease": False, "make_latest": "false",
                "body": OWNER_MARKER + f"\n\nAktualizacja: {published_at}\n\n[Raport TXT]({text_asset['browser_download_url']}) · [Pełne archiwum ZIP]({zip_asset['browser_download_url']})\n\n```text\n" + excerpt.replace("```", "'''") + "\n```",
            })
            (root / "commit.json").write_bytes(json_bytes(record))
            self.upload(state_release, f"commit-{stamp}.json", root / "commit.json")
            # A commit manifest uploaded last is the only pointer used by subsequent runners.
            self._collect_state(state_release)
        for asset in self.assets(report_release):
            if asset["id"] not in {text_asset["id"], zip_asset["id"]} and asset["name"].startswith(day + "-"):
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


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
