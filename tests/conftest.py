import json
import os
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest


@pytest.fixture
def sample_site():
    state = SimpleNamespace(price=4590, bonus="Kosztorys za 150 zł", unavailable=False, banner="Promocja jesienna", submitted=False, cookies=False, wp_cookies=False, wp_settings_delay=0, duplicate_cart=False, no_sales=False, background="white", requests=0)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            state.requests += 1
            if self.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if self.path.startswith("/projekt") and state.unavailable:
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b"Service unavailable")
                return
            structured = json.dumps({"@context": "https://schema.org", "@type": "Product", "name": "Dom Testowy", "sku": "test-1", "offers": {"@type": "Offer", "price": state.price, "priceCurrency": "PLN"}})
            if self.path.startswith("/projekt"):
                body = f'''<h1>Projekt domu Dom Testowy</h1><h2>Oferta projektu</h2>
                    <p>Cena projektu</p><span class="price">{state.price} zł</span>
                    <p>{state.bonus}</p><p>Dostawa dokumentacji w 3 dni. Zwrot w 14 dni.</p>
                    <label for="pakiet">Pakiet dokumentacji</label>
                    <select id="pakiet" name="pakiet" onchange="document.getElementById('dodatek').textContent='Dodatek '+this.value+' 200 zł'">
                    <option value="base">Podstawowy</option><option value="plus">Rozszerzony</option></select>
                    <p id="dodatek">Pakiet podstawowy w cenie</p>
                    <details><summary>Dokumentacja</summary><p>Instalacja fotowoltaiczna gratis</p>
                    <label for="wersja">Wersja dokumentacji</label><select id="wersja" name="wersja"><option value="pdf">PDF</option><option value="paper">Papier</option></select></details>
                    <button role="tab" id="tab" onclick="document.getElementById('warunki').hidden=false">Warunki zakupu</button>
                    <div id="warunki" hidden><p>Darmowa konsultacja i raty bez prowizji</p></div>
                    <a id="cart" class="btn" href="/cart">Dodaj do koszyka</a>
                    <script type="application/ld+json">{structured}</script>'''
            elif self.path == "/cart":
                body = f'''<h1>Koszyk</h1><h2>Oferta</h2><p>Projekt domu Dom Testowy</p><p class="price">{state.price} zł</p><p>Dostawa 0 zł. Dostępne płatności kartą i raty.</p><button id="order" onclick="fetch('/submitted')">Zamawiam i płacę</button>'''
            elif self.path == "/submitted":
                state.submitted = True
                body = "Nigdy nie wywołuj tego adresu podczas skanu"
            else:
                body = f'''<h1>Pracownia testowa</h1><h2>{state.banner}</h2><p>Bezpłatna dostawa projektów i nowa oferta promocyjna.</p>
                    <article><strong>Bestseller</strong><a href="/projekt-domu-testowy">Dom Testowy</a><span>4590 zł</span></article>
                    <p>Pomagamy wybrać projekt domu. Konsultacje dostępne przed zakupem.</p>'''
            if state.cookies:
                body += '''<div id="CybotCookiebotDialog" role="dialog">Pliki cookies<button onclick="document.getElementById('CybotCookiebotDialog').remove()">Odmowa</button><button role="tab">Szczegóły</button></div>'''
            if state.wp_cookies:
                body += '''<div role="dialog" aria-label="Plansza informacyjna WP" id="wp-dialog">Cenimy Twoją prywatność. Pliki cookies.
                <a href="#" onclick="document.getElementById('settings-wp').hidden=false;this.remove()">Ustawienia zaawansowane</a>
                <div id="settings-wp" hidden><h2>Ustawienia Zaawansowane</h2>
                <label><input type="checkbox" id="advertising-wp" checked>Spersonalizowane reklamy</label>
                <label><input type="checkbox" id="objection-wp">Wyrażam sprzeciw dla przetwarzania danych</label>
                <button onclick="if(document.getElementById('advertising-wp').checked || !document.getElementById('objection-wp').checked)fetch('/submitted');else document.getElementById('wp-dialog').remove()">Zapisz</button></div>
                <button onclick="fetch('/submitted')">Akceptuję i przechodzę do serwisu</button></div>'''
                if state.wp_settings_delay:
                    body += f'''<script>
                    const settingsWP = document.getElementById('settings-wp');
                    const delayedSettings = settingsWP.innerHTML;
                    settingsWP.innerHTML = '';
                    document.querySelector('#wp-dialog a').onclick = function () {{
                      setTimeout(() => {{ settingsWP.innerHTML = delayedSettings; settingsWP.hidden = false; }}, {state.wp_settings_delay});
                      this.remove();
                      return false;
                    }};
                    </script>'''
            if state.duplicate_cart:
                body += '<div><a id="cart" class="btn" href="/cart">Dodaj do koszyka</a></div>'
            if state.no_sales:
                body = '<h1>Pracownia testowa</h1><p>Witamy na naszej stronie internetowej. Zapraszamy do oglądania zdjęć i poznania naszej historii.</p>'
            html = f'''<!doctype html><html lang="pl"><head><meta charset="utf-8"><title>Oferta pracowni</title><style>body{{font:18px sans-serif;margin:30px;background:{state.background}}}h1{{color:#235}}summary,button{{margin:12px}}</style></head><body>{body}</body></html>'''
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.url = f"http://127.0.0.1:{server.server_port}"
    yield state
    server.shutdown()
    thread.join(timeout=5)
    server.server_close()


@pytest.fixture
def executable():
    return os.environ.get("MONITOR_BROWSER_EXECUTABLE") or shutil.which("chromium")
