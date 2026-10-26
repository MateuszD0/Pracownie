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
from PIL import Image

from .dashboard import render_dashboard_documents
from .management import build_management
from .model import digest, json_bytes, now_iso, slug
from .presentation import render_markdown
from .state import StateStore

OWNER_MARKER = "<!-- pracownie-monitor:v1 -->"
# GitHub release bodies have a finite character limit. Use a smaller UTF-8 byte
# budget, including all links/markup, so Polish text and escaped fields also fit.
RELEASE_BODY_BYTES = 60_000
RELEASE_PREVIEW_PAIRS = 40


def proof_preview_pairs(items: list[dict], journal: list[dict], limit: int = RELEASE_PREVIEW_PAIRS) -> list[dict]:
    """One dated before/after pair per page, with business findings first."""
    pairs, seen = [], set()
    candidates = [*items, *(item for item in journal if item.get("category") == "obraz")]
    for item in candidates:
        if len(pairs) >= max(0, limit):
            break
        key = (item["domain"], item["page"])
        if key in seen or not item.get("daily"):
            continue
        evidence = item.get("evidence", {})
        fields = ("fragment_przed", "fragment_po") if all(evidence.get(k) for k in ("fragment_przed", "fragment_po")) else ("przed", "po")
        if not all(evidence.get(k) for k in fields):
            continue
        pairs.append({"domain": key[0], "page": key[1], "before": evidence[fields[0]], "after": evidence[fields[1]]})
        seen.add(key)
    return pairs


def write_proof_preview(source: Path, destination: Path) -> None:
    """A light public preview; the original archive retains full image pixels."""
    with Image.open(source) as original:
        image = original.convert("RGB")
        # Preserve the whole supplied frame and its aspect ratio. The height
        # bound is below JPEG's encoder limit, including very long pages.
        image.thumbnail((1000, 65000), Image.Resampling.LANCZOS)
        image.save(destination, format="JPEG", quality=65, optimize=True)


def release_body(view: dict, links: dict[str, str], images: dict, published_at: str, *, dashboard_url: str = "") -> str:
    header = OWNER_MARKER + "\n\n" + " · ".join(f"[{label}]({url})" for label, url in links.items())
    if dashboard_url:
        header += "\n\n[**Otwórz bieżący dashboard — czytaj w przeglądarce**](" + dashboard_url + ")"
    header += "\n\n**Porównanie HTML — jeden plik** zawiera teksty przed/po i podglądy obrazów; działa bez skryptów i rozpakowywania. Pełne zrzuty są w **Raporcie HTML ze zrzutami**.\n\n"
    footer = f"\n\nRozpoczęcie publikacji: {published_at}."
    summary = render_markdown(view, images, item_limit=20)
    if len((header + summary + footer).encode()) <= RELEASE_BODY_BYTES:
        return header + summary + footer
    notice = "\n\nOpis wydania został skrócony do limitu GitHuba. Pełne porównania wszystkich pracowni są w plikach HTML, TXT i CSV pod linkami powyżej.\n"
    # Keep whole Markdown rows/links and balance details when a pathological
    # field or long URL exceeds the budget even with a limited number of events.
    budget = RELEASE_BODY_BYTES - len((header + footer + notice).encode()) - 256
    if budget < 0:
        raise ValueError("Linki raportu przekraczają limit opisu wydania GitHub")
    kept, used, opened = [], 0, 0
    for line in summary.splitlines(keepends=True):
        size = len(line.encode())
        if used + size > budget:
            break
        kept.append(line)
        used += size
        opened += line.count("<details>") - line.count("</details>")
    body = header + "".join(kept) + "\n</details>" * max(opened, 0) + notice + footer
    if len(body.encode()) > RELEASE_BODY_BYTES:
        raise ValueError("Przekroczono budżet opisu wydania GitHub")
    return body


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

    def request(self, method: str, url: str, *, accepted_statuses: tuple[int, ...] = (), **kwargs) -> httpx.Response:
        for attempt in range(3):
            try:
                response = self.client.request(method, url, **kwargs)
            except (httpx.TransportError, OSError):
                # Only reads are safe to repeat after an uncertain response.
                if method != "GET" or attempt == 2:
                    raise
                time.sleep(2 ** attempt)
                continue
            if method == "GET" and (response.status_code in {429, 502, 503, 504}) and attempt < 2:
                time.sleep(min(float(response.headers.get("retry-after", 2 ** attempt)), 10))
                continue
            if response.status_code >= 400 and response.status_code not in accepted_statuses:
                try:
                    error = response.json()
                except ValueError:
                    error = {}
                details = [str(error.get("message", ""))[:300]] if isinstance(error, dict) else []
                errors = (error.get("errors") or []) if isinstance(error, dict) else []
                if not isinstance(errors, list):
                    errors = [errors]
                for item in errors[:3]:
                    if isinstance(item, dict):
                        details.append(" ".join(str(item.get(key, ""))[:300] for key in ["resource", "field", "code", "message"]).strip())
                    elif isinstance(item, str):
                        details.append(item[:300])
                if response.status_code in {401, 403}:
                    details.append("sprawdź dostęp i uprawnienia")
                explanation = "; ".join(" ".join(item.split()) for item in details if item)
                raise RuntimeError(f"GitHub HTTP {response.status_code}: {method} {urlsplit(url).path}" + ("; " + explanation if explanation else ""))
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
        response = self.request("GET", f"{self.prefix}/releases/tags/{tag}", accepted_statuses=(404,))
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
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".github-download-", delete=False) as temporary:
            partial = Path(temporary.name)
        try:
            for attempt in range(3):
                try:
                    total = 0
                    with self.client.stream("GET", url, headers={"Accept": "application/octet-stream"}) as response:
                        if response.status_code in {502, 503, 504}:
                            raise httpx.ReadError(f"Przejściowy błąd GitHub HTTP {response.status_code}")
                        if response.status_code >= 400:
                            raise RuntimeError(f"Nie udało się pobrać pliku GitHub: HTTP {response.status_code}")
                        with partial.open("wb") as stream:
                            for chunk in response.iter_bytes():
                                total += len(chunk)
                                if total > 1_500_000_000:
                                    raise ValueError("Plik GitHub przekracza limit pobierania")
                                stream.write(chunk)
                    if asset.get("size") is not None and total != asset["size"]:
                        raise httpx.ReadError("Niepełny transfer pliku GitHub")
                    if expected_hash and digest(partial) != expected_hash:
                        raise ValueError("Niepoprawna suma kontrolna pliku GitHub")
                    partial.replace(destination)
                    return
                except (httpx.TransportError, OSError) as exc:
                    if attempt == 2:
                        raise RuntimeError("Pobieranie pliku GitHub przerwano po 3 próbach; historia wymaga poprawnego archiwum.") from exc
                    time.sleep(2 ** attempt)
        finally:
            partial.unlink(missing_ok=True)

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

    def published_report(self, day: str) -> dict | None:
        """Check the committed daily publication without downloading state/screenshots.

        A release alone can be an interrupted upload. Only the commit uploaded last
        together with its existing report files is sufficient to skip a scheduled run.
        Callers must hold the same writer lock as publish/rebuild.
        """
        date.fromisoformat(day)
        release = self.release(f"{self.namespace}-state-v1")
        if not release:
            return None
        assets = self.assets(release)
        commits = sorted((a for a in assets if a["name"].startswith("commit-") and a["name"].endswith(".json")), key=lambda a: a["name"], reverse=True)
        if not commits:
            return None
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "commit.json"
            self.download(commits[0], path, (commits[0].get("digest") or "").removeprefix("sha256:") or None)
            record = json.loads(path.read_text())
        if record.get("schema") != 1 or record.get("owner") != "pracownie-monitor:v1":
            raise ValueError("Niepoprawny manifest zatwierdzenia raportu")
        recorded_day = record.get("day", "")
        date.fromisoformat(recorded_day)
        if recorded_day > day:
            raise ValueError("Zdalny raport ma datę z przyszłości; nie cofnięto historii")
        if recorded_day != day:
            return None
        state_asset = next((a for a in assets if a["name"] == record.get("asset")), None)
        if not state_asset or not re.fullmatch(r"[0-9a-f]{64}", record.get("sha256", "")):
            raise ValueError("Zatwierdzony raport nie ma poprawnego archiwum stanu")
        report = self.release(f"{self.namespace}-report-{day}")
        if not report or report["id"] != record.get("report_release_id"):
            return None
        files = record.get("report_files", {})
        required = {"txt", "csv", "journal_csv", "diagnostics", "html_zip", "html", "zip"}
        available = {a["id"] for a in self.assets(report) if a.get("size", 0) > 0}
        if not required <= files.keys() or not set(files.values()) <= available:
            return None
        # Asset creation is GitHub's confirmation of the final commit, not the
        # earlier scan finish or an upload-start timestamp. Preserve the first
        # confirmed publication across same-day repairs and format rebuilds.
        record['first_published_at'] = record.get('first_published_at') or commits[0].get('created_at')
        return record

    def publish(self, store: StateStore, output: Path, day: str, report_archive: Path, run_id: str) -> dict:
        previous_publication = self.published_report(day)
        from .delivery import annotate_report, delivery_status
        from .report import bundle_report

        delivery = delivery_status(self, day, previous_publication)
        from .intelligence import update_intelligence
        state = store.read()
        intelligence = update_intelligence(state, json.loads((output / day / 'oferty.json').read_text()))
        annotate_report(output, day, delivery, intelligence)
        store.commit(state)
        bundle_report(output, day, report_archive)
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
        pairs = proof_preview_pairs(build_management(view)["items"], view.get("journal", []))
        with tempfile.TemporaryDirectory() as temporary:
            for pair_index, pair in enumerate(pairs, start=1):
                for field, label in [("before", "przed"), ("after", "po")]:
                    path = pair[field]
                    if path in previews:
                        continue
                    from .model import safe_path
                    preview_path = Path(temporary) / f"{pair_index}-{label}.jpg"
                    write_proof_preview(safe_path(output, path), preview_path)
                    preview = self.upload(report_release, f"{day}-{stamp}-dowod-{pair_index}-{label}.jpg", preview_path)
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
            editions = [*delivery.get('editions', []), {
                'run_id': run_id, 'created_at': now_iso(), 'html': standalone_asset['browser_download_url'],
                'archive': zip_asset['browser_download_url']}]
            record = {"editions": editions, "schema": 1, "owner": "pracownie-monitor:v1", "day": day, "run_id": run_id,
                      "first_published_at": (previous_publication or {}).get('first_published_at'),
                      "publication_started_at": now_iso(), "asset": state_name, "sha256": digest(root / "state.zip"),
                      "report_release_id": report_release["id"], "report_assets": [text_asset["id"], csv_asset["id"], journal_asset["id"], diagnostic_asset["id"], html_asset["id"], standalone_asset["id"], *preview_assets, zip_asset["id"]],
                      "report_files": {"txt": text_asset["id"], "csv": csv_asset["id"], "journal_csv": journal_asset["id"], "diagnostics": diagnostic_asset["id"], "html_zip": html_asset["id"], "html": standalone_asset["id"], "zip": zip_asset["id"]}}
            from .readiness import base_readiness
            raw = json.loads((output / day / "zmiany.json").read_text())
            record["readiness"] = base_readiness(day, raw["results"], [row["domain"] for row in view["rows"]])
            if raw["metadata"].get("scan_phase") == "base-checkpoint":
                record["readiness"]["retry_domains"] = sorted({r["domain"] for r in raw["results"] if r["scenario"] == "checkpoint"}
                    | set(record["readiness"]["retry_domains"]))
                record["readiness"]["complete"] = False
            # Both report files and state have been verified. Make the daily report visible first.
            published_at = now_iso()
            body = release_body(view, {
                "Porównanie HTML — jeden plik": standalone_asset['browser_download_url'],
                "Tabela zmian CSV": journal_asset['browser_download_url'],
                "Raport TXT": text_asset['browser_download_url'],
                "Ceny CSV": csv_asset['browser_download_url'],
                "Raport HTML ze zrzutami": html_asset['browser_download_url'],
                "Pełne archiwum ZIP": zip_asset['browser_download_url'],
                "Diagnostyka": diagnostic_asset['browser_download_url'],
            }, previews, published_at, dashboard_url=f"https://github.com/{self.repo}/blob/main/" + self.dashboard_filename)
            self.request("PATCH", f"{self.prefix}/releases/{report_release['id']}", json={
                "name": f"Raport {day}", "prerelease": False, "make_latest": "false",
                "body": body,
            })
            (root / "commit.json").write_bytes(json_bytes(record))
            dashboard_url = self.update_dashboard(view, report_release["html_url"], {"html": standalone_asset["browser_download_url"]}, previews)
            confirmation = self.upload(state_release, f"commit-{stamp}.json", root / "commit.json")
            if not delivery.get('first_published_at') and confirmation.get('created_at'):
                delivery['first_published_at'] = confirmation['created_at']
                view['metadata']['delivery'] = delivery
                self.update_dashboard(view, report_release['html_url'], {'html': standalone_asset['browser_download_url']}, previews)
            published_at = now_iso()
            # A commit manifest uploaded last is the only pointer used by subsequent runners.
            self._collect_state(state_release)
        # Daily corrections are immutable. Existing links and morning evidence
        # survive subsequent rebuilds; day-level retention removes whole days.
        return {"report_url": report_release["html_url"], "dashboard_url": dashboard_url, "state_asset_id": state_asset["id"], "published_at": published_at}

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

    @property
    def dashboard_filename(self) -> str:
        return "DASHBOARD.md" if self.namespace == "monitor" else "DASHBOARD-" + self.namespace.upper() + ".md"

    def update_dashboard(self, view: dict, report_url: str, downloads: dict | None = None, previews: dict | None = None) -> str:
        documents = {path: (OWNER_MARKER + "\n\n" + text).encode() for path, text in render_dashboard_documents(view, report_url, downloads, previews, self.dashboard_filename).items()}
        self._update_dashboard_documents(documents)
        return f"https://github.com/{self.repo}/blob/main/{self.dashboard_filename}"

    def _update_dashboard_documents(self, documents: dict[str, bytes]) -> None:
        """Write the overview and company pages in one non-forced Git commit."""
        for _attempt in range(3):
            parent = self.request("GET", f"{self.prefix}/git/ref/heads/main").json()["object"]["sha"]
            commit = self.request("GET", f"{self.prefix}/git/commits/{parent}").json()
            tree = self.request("GET", f"{self.prefix}/git/trees/{commit['tree']['sha']}", params={"recursive": "1"}).json()
            if tree.get("truncated"):
                raise ValueError("Niepełne drzewo repozytorium; nie zaktualizowano dashboardu")
            entries = {item['path']: item for item in tree['tree']}
            changes = []
            for filename, content in documents.items():
                expected = hashlib.sha1(f"blob {len(content)}\0".encode() + content, usedforsecurity=False).hexdigest()
                existing = entries.get(filename)
                if existing and existing['sha'] == expected:
                    continue
                if existing:
                    if existing['type'] != 'blob':
                        raise ValueError(f"Plik {filename} nie należy do monitora")
                    blob = self.request("GET", f"{self.prefix}/git/blobs/{existing['sha']}").json()
                    if OWNER_MARKER.encode() not in base64.b64decode(blob['content']):
                        raise ValueError(f"Plik {filename} nie należy do monitora; nie nadpisano go")
                changes.append({"path": filename, "mode": "100644", "type": "blob", "content": content.decode()})
            if not changes:
                return
            created = self.request("POST", f"{self.prefix}/git/trees", json={"base_tree": commit['tree']['sha'], "tree": changes}).json()
            updated = self.request("POST", f"{self.prefix}/git/commits", json={"message": "Update daily monitoring dashboard", "tree": created['sha'], "parents": [parent]}).json()
            result = self.request("PATCH", f"{self.prefix}/git/refs/heads/main", json={"sha": updated['sha'], "force": False}, accepted_statuses=(409, 422))
            if result.status_code < 400:
                return
        raise RuntimeError("Gałąź main zmieniła się podczas publikacji dashboardu; ponów aktualizację")

    def _update_owned_document(self, filename: str, content: bytes, message: str) -> str:
        endpoint = f"{self.prefix}/contents/{filename}"
        for _attempt in range(3):
            existing = self.request("GET", endpoint, accepted_statuses=(404,))
            payload = {"message": message, "content": base64.b64encode(content).decode()}
            if existing.status_code == 200:
                data = existing.json()
                previous = base64.b64decode(data["content"])
                if OWNER_MARKER.encode() not in previous:
                    raise ValueError(f"Plik {filename} nie należy do monitora; nie nadpisano go")
                if previous == content:
                    return data["html_url"]
                payload["sha"] = data["sha"]
            result = self.request("PUT", endpoint, json=payload, accepted_statuses=(409,))
            if result.status_code != 409:
                return result.json()["content"]["html_url"]
        raise RuntimeError(f"Plik {filename} zmienił się podczas publikacji; ponów aktualizację")

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
        lines = [OWNER_MARKER, "", "**Raporty monitoringu ofert**", "", f"[Otwórz bieżący dashboard]({self.dashboard_filename}) — porównanie w przeglądarce, bez pobierania plików.", "", "Raport zaczyna się od podsumowania zarządczego, KPI i kompletności danych, a następnie pokazuje konkretne zmiany dzień do dnia z linkami i dowodami przed/po. Pełny dziennik CSV obejmuje również pomocnicze różnice obrazu i porównania po luce; w starszych raportach CSV może zawierać tylko ceny. ZIP zachowuje pełne obrazy i interaktywne filtry. Notatki przechowuj osobno.", "", "| Dzień | Czytelny raport | Pełny dziennik CSV | Opis TXT | HTML i zrzuty |", "| --- | --- | --- | --- | --- |"]
        lines.extend(f"| {day} | [Otwórz raport]({url}) | " + (f"[CSV]({csv_url})" if csv_url else "—") + f" | [TXT]({text}) | " + (f"[HTML]({portable}) · " if portable else "") + f"[ZIP]({html_url}) |" for day, text, archive, url, csv_url, html_url, portable in sorted(rows, reverse=True))
        content = ("\n".join(lines) + "\n").encode()
        return self._update_owned_document(filename, content, "Update daily monitoring report index")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
