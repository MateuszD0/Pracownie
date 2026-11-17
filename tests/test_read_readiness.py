import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from pracownie.browser import BrowserScanner, TransientFetchError
from pracownie.model import Scenario, Site
from pracownie.pipeline import RunOptions, run_scan
from pracownie.state import StateStore


@pytest.fixture
def delayed_site():
    state = SimpleNamespace(blank=1)
    body = "<h1>Projekt domu Stabilny</h1><p>Opis projektu domu i powierzchnia 120 m2. Cena projektu 4500 zł.</p>"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            if self.path == "/retry" and state.blank:
                state.blank -= 1
                return
            if self.path == "/blank":
                return
            content = body
            if self.path == "/delayed":
                content = (
                    '<script>addEventListener("DOMContentLoaded",()=>setTimeout(()=>{document.body.innerHTML='
                    + repr(body)
                    + "},1200));</script>"
                )
            self.wfile.write(
                ("<html><head><title>Pracownia</title></head><body>" + content + "</body></html>").encode()
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join()


@pytest.mark.browser
async def test_waits_for_real_delayed_content_and_rejects_blank(delayed_site, tmp_path, executable):
    site = Site("127.0.0.1", delayed_site + "/delayed")
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        capture = await scanner.capture(
            site, "glowna", site.home_url, Scenario("podstawowy", ""), tmp_path / "ok.png"
        )
        assert capture.snapshot.fields and capture.snapshot.quality == "ok"
        with pytest.raises(TransientFetchError) as error:
            await scanner.capture(
                site, "glowna", delayed_site + "/blank", Scenario("podstawowy", ""), tmp_path / "blank.png"
            )
        assert error.value.diagnostics["text_length"] == 0
        assert not (tmp_path / "blank.png").exists()


@pytest.mark.browser
async def test_empty_200_is_retried_and_failure_evidence_survives(delayed_site, tmp_path, executable):
    import json

    site = Site("127.0.0.1", delayed_site + "/retry", project_url=delayed_site + "/project")
    result = await run_scan(
        [site],
        StateStore(tmp_path / "state"),
        tmp_path / "reports",
        RunOptions(browser_executable=executable, settle_ms=0, max_scenarios=0, retries=1, ocr=False),
    )
    rows = [r for r in result["results"] if r.scenario == "podstawowy"]
    assert len(rows) == 2 and all(r.observed_at and not r.error for r in rows)
    failures = list((tmp_path / "reports").rglob("bledy-odczytu.json"))
    assert len(failures) == 1
    data = json.loads(failures[0].read_text())
    assert data[0]["details"]["text_length"] == 0 and data[0]["attempt"] == 1
