import hashlib
import json

import httpx
import pytest

from pracownie.github import OWNER_MARKER, GitHubStore
from pracownie.model import Change, Result
from pracownie.report import bundle_report, write_outputs
from pracownie.state import StateStore


class FakeGitHub:
    def __init__(self):
        self.releases = {}
        self.assets = {}
        self.contents = {}
        self.next_id = 1
        self.fail_commit = False
        self.deleted = []
        self.repo_files = {}
        self.git_head = "head-0"
        self.git_trees = {}
        self.git_commits = {}
        self.git_blobs = {}

    def request(self, request):
        path, method = request.url.path, request.method
        if '/git/' in path:
            import base64
            import copy
            prefix = '/repos/test/monitor/git/'
            part = path.removeprefix(prefix)
            if part == 'ref/heads/main':
                return httpx.Response(200, json={'object': {'sha': self.git_head}})
            if part.startswith('commits/'):
                return httpx.Response(200, json=self.git_commits.get(part.split('/')[-1], {'tree': {'sha': 'base-tree'}}))
            if part.startswith('trees/'):
                files = self.git_trees.get(part.split('/')[-1], self.repo_files)
                entries = []
                for name, data in files.items():
                    value = base64.b64decode(data['content'])
                    sha = hashlib.sha1(f'blob {len(value)}\0'.encode() + value, usedforsecurity=False).hexdigest()
                    self.git_blobs[sha] = data['content']
                    entries.append({'path': name, 'type': 'blob', 'mode': '100644', 'sha': sha})
                return httpx.Response(200, json={'tree': entries, 'truncated': False})
            if part.startswith('blobs/'):
                return httpx.Response(200, json={'content': self.git_blobs[part.split('/')[-1]]})
            if part == 'trees' and method == 'POST':
                payload = json.loads(request.content)
                files = copy.deepcopy(self.git_trees.get(payload['base_tree'], self.repo_files))
                for entry in payload['tree']:
                    files[entry['path']] = {'content': base64.b64encode(entry['content'].encode()).decode(), 'sha': 'example-sha', 'html_url': 'https://github.com/test/monitor/blob/main/' + entry['path']}
                sha = f'tree-{len(self.git_trees) + 1}'
                self.git_trees[sha] = files
                return httpx.Response(201, json={'sha': sha})
            if part == 'commits' and method == 'POST':
                payload = json.loads(request.content)
                sha = f'commit-{len(self.git_commits) + 1}'
                self.git_commits[sha] = {'sha': sha, 'tree': {'sha': payload['tree']}, 'parents': payload['parents']}
                return httpx.Response(201, json={'sha': sha})
            if part == 'refs/heads/main' and method == 'PATCH':
                payload = json.loads(request.content)
                assert payload['force'] is False
                self.git_head = payload['sha']
                self.repo_files = copy.deepcopy(self.git_trees[self.git_commits[self.git_head]['tree']['sha']])
                return httpx.Response(200, json={'object': {'sha': self.git_head}})
        if "/contents/" in path:
            name = path.split("/contents/", 1)[-1]
            if method == "GET":
                return httpx.Response(200 if name in self.repo_files else 404, json=self.repo_files.get(name, {}))
            payload = json.loads(request.content)
            self.repo_files[name] = {"content": payload["content"], "sha": "example-sha", "html_url": "https://github.com/test/monitor/blob/main/" + name}
            return httpx.Response(201, json={"content": self.repo_files[name]})
        if path == "/repos/test/monitor" and method == "GET":
            return httpx.Response(200, json={"private": True, "permissions": {"push": True}, "default_branch": "main"})
        if path.startswith("/repos/test/monitor/releases/tags/"):
            tag = path.rsplit("/", 1)[-1]
            release = next((r for r in self.releases.values() if r["tag_name"] == tag), None)
            return httpx.Response(200 if release else 404, json=release or {})
        if path == "/repos/test/monitor/releases":
            if method == "GET":
                return httpx.Response(200, json=list(self.releases.values()))
            data = json.loads(request.content)
            number = self.next_id
            self.next_id += 1
            release = dict(data, id=number, html_url=f"https://github.com/test/monitor/releases/tag/{data['tag_name']}", upload_url=f"https://uploads.github.com/repos/test/monitor/releases/{number}/assets{{?name}}")
            self.releases[number] = release
            return httpx.Response(201, json=release)
        if "/releases/assets/" in path:
            number = int(path.rsplit("/", 1)[-1])
            if method == "GET":
                return httpx.Response(200, content=self.contents[number])
            self.deleted.append(self.assets[number]["name"])
            del self.assets[number]
            del self.contents[number]
            return httpx.Response(204)
        if path.endswith("/assets"):
            release_id = int(path.split("/")[-2])
            if method == "GET":
                return httpx.Response(200, json=[a for a in self.assets.values() if a["release_id"] == release_id])
            name = request.url.params["name"]
            if self.fail_commit and name.startswith("commit-"):
                return httpx.Response(500, json={"message": "interrupted"})
            content = request.read()
            number = self.next_id
            self.next_id += 1
            tag = self.releases[release_id]["tag_name"]
            asset = {"id": number, "name": name, "release_id": release_id, "size": len(content), "digest": "sha256:" + hashlib.sha256(content).hexdigest(), "browser_download_url": f"https://github.com/test/monitor/releases/download/{tag}/{name}"}
            self.assets[number] = asset
            self.contents[number] = content
            return httpx.Response(201, json=asset)
        if "/releases/" in path:
            release_id = int(path.rsplit("/", 1)[-1])
            if method == "PATCH":
                payload = json.loads(request.content)
                if len(payload.get("body", "")) > 125_000:
                    return httpx.Response(422, json={"message": "Validation Failed", "errors": [{"resource": "Release", "field": "body", "code": "too_long", "message": "body is too long (maximum is 125000 characters)"}]})
                self.releases[release_id].update(payload)
                return httpx.Response(200, json=self.releases[release_id])
            if method == "DELETE":
                del self.releases[release_id]
                return httpx.Response(204)
        return httpx.Response(404, json={"path": path})


def prepare(store, output, day, run_id):
    data = store.begin(day)
    data["selections"]["test.pl"] = {"url": "https://test.pl/projekt", "name": run_id}
    store.commit(data)
    metadata = {"run_id": run_id, "started_at": day + "T05:00:00+00:00", "finished_at": day + "T05:01:00+00:00", "elapsed_seconds": 60}
    write_outputs(output, day, [], metadata, {}, [])
    archive = output / f"{day}.zip"
    bundle_report(output, day, archive)
    return archive


def test_persistence_and_interrupted_commit(tmp_path):
    fake = FakeGitHub()
    remote = GitHubStore("test/monitor", "not-a-real-token", client=httpx.Client(transport=httpx.MockTransport(fake.request)))
    store = StateStore(tmp_path / "local")
    output = tmp_path / "reports"
    output.mkdir()
    archive = prepare(store, output, "2026-10-19", "2026-10-19T060000-a")
    remote.publish(store, output, "2026-10-19", archive, "2026-10-19T060000-a")
    assert remote.published_report("2026-10-19")["day"] == "2026-10-19"
    assert remote.published_report("2026-10-20") is None
    fresh = StateStore(tmp_path / "fresh")
    remote.pull(fresh)
    assert fresh.read() == store.read()
    archive = prepare(store, output, "2026-10-20", "2026-10-20T060000-b")
    fake.fail_commit = True
    with pytest.raises(RuntimeError):
        remote.publish(store, output, "2026-10-20", archive, "2026-10-20T060000-b")
    # A release with all uploaded files but no final commit is not a daily success.
    assert remote.published_report("2026-10-20") is None
    another = StateStore(tmp_path / "another")
    remote.pull(another)
    assert another.read()["day"] == "2026-10-19"
    fake.fail_commit = False
    remote.publish(store, output, "2026-10-20", archive, "2026-10-20T070000-c")
    assert remote.published_report("2026-10-20")["run_id"] == "2026-10-20T070000-c"
    remote.pull(another)
    assert another.read()["day"] == "2026-10-20"
    assert len([a for a in fake.assets.values() if a["name"].startswith("commit-")]) == 2


def test_daily_publication_gate_checks_files_without_downloading_archives(tmp_path):
    fake = FakeGitHub()
    requests = []

    def respond(request):
        requests.append((request.method, request.url.path))
        return fake.request(request)

    remote = GitHubStore("test/monitor", "not-a-real-token", client=httpx.Client(transport=httpx.MockTransport(respond)))
    store = StateStore(tmp_path / "local")
    output = tmp_path / "reports"
    output.mkdir()
    assert remote.published_report("2026-10-21") is None
    archive = prepare(store, output, "2026-10-21", "2026-10-21T051700-a")
    remote.publish(store, output, "2026-10-21", archive, "2026-10-21T051700-a")
    requests.clear()
    record = remote.published_report("2026-10-21")
    assert record
    assert all(method == "GET" for method, _ in requests)
    downloads = [int(path.rsplit("/", 1)[-1]) for _, path in requests if "/releases/assets/" in path]
    assert len(downloads) == 1 and fake.assets[downloads[0]]["name"].startswith("commit-")
    # The commit alone cannot hide a missing user-facing HTML report.
    del fake.assets[record["report_files"]["html"]]
    assert remote.published_report("2026-10-21") is None
    with pytest.raises(ValueError, match="przyszłości"):
        remote.published_report("2026-10-20")


def test_retention_never_deletes_other_releases():
    fake = FakeGitHub()
    fake.releases = {
        1: {"id": 1, "tag_name": "monitor-report-2025-01-01", "body": OWNER_MARKER},
        2: {"id": 2, "tag_name": "v1.0.0", "body": "user release"},
        3: {"id": 3, "tag_name": "monitor-report-2025-01-02", "body": "not ours"},
        4: {"id": 4, "tag_name": "monitor-pilot-report-2025-01-03", "body": OWNER_MARKER},
    }
    remote = GitHubStore("test/monitor", "not-a-real-token", client=httpx.Client(transport=httpx.MockTransport(fake.request)))
    assert remote.cleanup("2026-10-19") == ["monitor-report-2025-01-01"]
    assert 1 in fake.releases
    remote.cleanup("2026-10-19", dry_run=False)
    assert set(fake.releases) == {2, 3, 4}


def test_ownership_collision_blocks_write():
    fake = FakeGitHub()
    fake.releases[1] = {"id": 1, "tag_name": "monitor-state-v1", "body": "user release"}
    remote = GitHubStore("test/monitor", "not-a-real-token", client=httpx.Client(transport=httpx.MockTransport(fake.request)))
    with pytest.raises(ValueError, match="nie należy"):
        remote.release("monitor-state-v1", create=True)


def test_unauthorized_upload_host_is_rejected(tmp_path):
    remote = GitHubStore("test/monitor", "not-a-real-token", client=httpx.Client())
    path = tmp_path / "data.txt"
    path.write_text("not secret")
    with pytest.raises(ValueError, match="host"):
        remote.upload({"upload_url": "https://outside.example/upload"}, "data.txt", path)


def test_git_push_metadata_does_not_block_contents_api():
    fake = FakeGitHub()
    original = fake.request
    def respond(request):
        if request.url.path == "/repos/test/monitor":
            return httpx.Response(200, json={"private": False, "permissions": {"push": False}, "default_branch": "main"})
        return original(request)
    remote = GitHubStore("test/monitor", "not-a-real-token", client=httpx.Client(transport=httpx.MockTransport(respond)))
    assert remote.preflight()["reported_git_push"] is False
    assert remote.release("monitor-state-v1", create=True)["id"] == 1


def test_daily_index_preserves_unrelated_user_file(tmp_path):
    import base64
    fake = FakeGitHub()
    remote = GitHubStore("test/monitor", "not-a-real-token", client=httpx.Client(transport=httpx.MockTransport(fake.request)))
    fake.repo_files["RAPORTY.md"] = {"content": base64.b64encode(b"User notes").decode(), "sha": "old"}
    with pytest.raises(ValueError, match="nie należy"):
        remote.update_index()
    del fake.repo_files["RAPORTY.md"]
    store = StateStore(tmp_path / "local")
    output = tmp_path / "reports"
    output.mkdir()
    archive = prepare(store, output, "2026-10-19", "2026-10-19T060000-a")
    remote.publish(store, output, "2026-10-19", archive, "2026-10-19T060000-a")
    remote.update_index()
    content = base64.b64decode(fake.repo_files["RAPORTY.md"]["content"]).decode()
    assert "2026-10-19" in content and "[TXT]" in content and "-widok.zip" in content


@pytest.mark.parametrize("failure", ["reset", "short"])
def test_interrupted_download_restarts_and_installs_only_verified_archive(tmp_path, monkeypatch, failure):
    monkeypatch.setattr("pracownie.github.time.sleep", lambda _: None)
    destination = tmp_path / "history.zip"
    destination.write_bytes(b"previous verified history")
    payload = b"complete new archive"
    attempts = 0

    class Interrupted(httpx.SyncByteStream):
        def __iter__(self):
            yield b"part"
            raise OSError(104, "Connection reset by peer")

    def respond(request):
        nonlocal attempts
        attempts += 1
        assert destination.read_bytes() == b"previous verified history"
        if attempts == 1:
            return httpx.Response(200, stream=Interrupted()) if failure == "reset" else httpx.Response(200, content=b"part")
        return httpx.Response(200, content=payload)

    remote = GitHubStore("test/monitor", "not-a-real-token", client=httpx.Client(transport=httpx.MockTransport(respond)))
    remote.download({"id": 1, "size": len(payload)}, destination, hashlib.sha256(payload).hexdigest())
    assert attempts == 2 and destination.read_bytes() == payload
    assert not list(tmp_path.glob('.github-download-*'))


def test_failed_transfer_or_checksum_cannot_replace_history(tmp_path, monkeypatch):
    monkeypatch.setattr("pracownie.github.time.sleep", lambda _: None)
    destination = tmp_path / "history.zip"
    destination.write_bytes(b"verified history")
    calls = 0

    def reset(request):
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("reset")

    remote = GitHubStore("test/monitor", "not-a-real-token", client=httpx.Client(transport=httpx.MockTransport(reset)))
    with pytest.raises(RuntimeError, match="po 3 próbach"):
        remote.download({"id": 1}, destination)
    assert calls == 3 and destination.read_bytes() == b"verified history"
    remote.client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"invalid")))
    with pytest.raises(ValueError, match="suma kontrolna"):
        remote.download({"id": 1, "size": 7}, destination, hashlib.sha256(b"valid").hexdigest())
    assert destination.read_bytes() == b"verified history" and not list(tmp_path.glob('.github-download-*'))


def test_only_get_is_retried_after_a_transport_failure(monkeypatch):
    monkeypatch.setattr("pracownie.github.time.sleep", lambda _: None)
    calls = []

    def respond(request):
        calls.append(request.method)
        if len(calls) < 3 or request.method != "GET":
            raise httpx.ConnectError("reset")
        return httpx.Response(200, json={})

    remote = GitHubStore("test/monitor", "not-a-real-token", client=httpx.Client(transport=httpx.MockTransport(respond)))
    assert remote.request("GET", remote.prefix).status_code == 200 and len(calls) == 3
    with pytest.raises(httpx.ConnectError):
        remote.request("POST", remote.prefix)
    assert calls == ["GET", "GET", "GET", "POST"]


def test_large_daily_report_publishes_bounded_summary_and_paired_previews(tmp_path):
    from PIL import Image

    from pracownie.github import RELEASE_BODY_BYTES, RELEASE_PREVIEW_PAIRS
    from pracownie.presentation import render_markdown

    fake = FakeGitHub()
    remote = GitHubStore("test/monitor", "not-a-real-token", client=httpx.Client(transport=httpx.MockTransport(fake.request)))
    store = StateStore(tmp_path / "local")
    output = tmp_path / "reports"
    day, run_id = "2026-10-21", "2026-10-21T051700-a"
    prepare(store, output, day, run_id)
    results, domains = [], []
    for index in range(65):
        domain = f"studio{index}.pl"
        domains.append(domain)
        proof = f"{day}/{domain}/po.png"
        path = output / proof
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (10, 10), "white").save(path)
        previous_proof = f"{day}/{domain}/przed.png"
        Image.new("RGB", (10, 10), "black").save(output / previous_proof)
        before, after = day.replace("21", "20") + "T05:20:00+00:00", day + "T05:20:00+00:00"
        changes = [Change("changed", "komunikacja", "Baner", f"{n} Stara oferta. " + "Żółć i źródło " * 30, f"{n} Nowa oferta. " + "Bezpłatne dodatki " * 30, before, after, "https://" + domain, "podstawowy") for n in range(16)]
        # Many observations on a page share one pair of source images.
        changes.append(Change("visual", "obraz", "Obraz", "Stara grafika", "Nowa grafika", before, after, "https://" + domain, "podstawowy"))
        results.append(Result(domain, "glowna", "podstawowy", "changed", "https://" + domain, changes, observed_at=after, compared_at=before, data_quality="ok", evidence={"przed": previous_proof, "po": proof}))
    write_outputs(output, day, results, {"run_id": run_id, "started_at": after, "finished_at": after, "elapsed_seconds": 60}, {}, domains)
    view = json.loads((output / day / "oferty.json").read_text())
    original = render_markdown(view)
    assert len(original) > 125_000  # The exact failure mode of scan #35.
    archive = output / "daily.zip"
    bundle_report(output, day, archive)
    remote.publish(store, output, day, archive, run_id)
    record = remote.published_report(day)
    assert record and record["run_id"] == run_id
    body = remote.release(f"monitor-report-{day}")["body"]
    assert len(body.encode()) <= RELEASE_BODY_BYTES
    assert "Pokazano 20 z 1040 zmian komunikacji" in body
    assert "Tabela zmian CSV" in body and "Porównanie HTML — jeden plik" in body
    assert all(domain in body for domain in domains)
    # Only the release landing page is shortened; files retain every event.
    assert (output / day / "podsumowanie.md").read_text() == original
    assert len(view["journal"]) == 65 * 17
    previews = [a for a in fake.assets.values() if "-dowod-" in a["name"]]
    assert len(previews) == 2 * RELEASE_PREVIEW_PAIRS
    assert sum(a["name"].endswith("-przed.jpg") for a in previews) == RELEASE_PREVIEW_PAIRS
    assert sum(a["name"].endswith("-po.jpg") for a in previews) == RELEASE_PREVIEW_PAIRS


def test_release_byte_budget_keeps_full_links_rows_and_balanced_disclosures(monkeypatch):
    from pracownie.github import RELEASE_BODY_BYTES, release_body

    # Deliberately exceed the byte budget with a single escaped/unicode field.
    source = "Nagłówek\n<details><summary>Rozwiń</summary>\n" + "| " + "Żółć" * 60_000 + " |\n</details>\n"
    monkeypatch.setattr("pracownie.github.render_markdown", lambda *args, **kwargs: source)
    body = release_body({}, {"Pełny raport": "https://example.test/report.html"}, {}, "2026-10-21T05:00:00+00:00")
    assert len(body.encode()) <= RELEASE_BODY_BYTES
    assert "[Pełny raport](https://example.test/report.html)" in body
    assert "Opis wydania został skrócony" in body
    assert body.count("<details>") == body.count("</details>") == 1
    assert "| Ż" not in body  # Never cut an individual row/link in half.


def test_github_validation_error_reports_body_limit_instead_of_permission_hint():
    requests = []

    def respond(request):
        requests.append(request.method)
        return httpx.Response(422, json={"message": "Validation Failed", "errors": [{"resource": "Release", "field": "body", "code": "too_long", "message": "body is too long (maximum is 125000 characters)"}]})

    remote = GitHubStore("test/monitor", "not-a-real-token", client=httpx.Client(transport=httpx.MockTransport(respond)))
    with pytest.raises(RuntimeError) as failure:
        remote.request("PATCH", remote.prefix + "/releases/1", json={"body": "data"})
    message = str(failure.value)
    assert "HTTP 422" in message and "Release body too_long" in message and "125000" in message
    assert "uprawnienia" not in message and requests == ["PATCH"]
