from datetime import datetime

import httpx
import pytest
from test_github import FakeGitHub, prepare
from test_recovery import NOW, Remote, published

from pracownie.browser import BrowserScanner, adapter_signature
from pracownie.github import GitHubStore
from pracownie.model import WARSAW, Scenario, Site
from pracownie.readiness import assess, base_readiness
from pracownie.recovery import recover
from pracownie.schedule import RECOVERY_CRON, daily_gate
from pracownie.state import StateStore


def test_partial_pages_are_retried_even_from_a_legacy_commit_without_retry_domains():
    record = published()
    record['readiness']['limited'] = ['partial.pl/glowna', 'partial.pl/projekt']
    record['readiness']['missing'] = ['blocked.pl/glowna']
    record['readiness']['blocked'] = ['blocked.pl/glowna']
    remote = Remote(record)
    result = recover(remote, NOW, False)
    assert result['repair_domains'] == ['partial.pl']
    assert remote.writes[0][1]['inputs']['rescan'] == 'false'
    assert daily_gate(RECOVERY_CRON, NOW, remote)['repair_domains'] == ['partial.pl']


def test_new_partial_capture_cannot_become_complete_and_keeps_its_repair_scope():
    rows = [{'domain': 'partial.pl', 'page': p, 'scenario': 'podstawowy',
             'observed_at': '2026-10-22T05:00:00+00:00', 'data_quality': 'partial'}
            for p in ['glowna', 'projekt']]
    quality = base_readiness('2026-10-22', rows, ['partial.pl'])
    assert quality['fresh'] == 2 and not quality['complete']
    assert quality['retry_domains'] == ['partial.pl']


def test_readiness_reports_availability_coverage_and_real_publication_time_separately():
    record = published()
    record['first_published_at'] = '2026-10-22T05:40:00+00:00'
    record['readiness'].update(missing=['blocked.pl/glowna'], limited=['partial.pl/projekt'])
    status = assess(record, NOW.replace(hour=12, minute=33), 'test/monitor')
    assert not status['ready'] and status['on_time'] is True
    assert 'Raport dostępny' in status['message']
    assert '12:33' in status['summary'] and '07:40' in status['timing']
    assert 'blocked.pl: strona główna' in status['summary']
    assert 'partial.pl: karta projektu' in status['summary']
    record['readiness'].update(expected=130, fresh=130, complete=True, limited=[], missing=[])
    record['first_published_at'] = '2026-10-22T06:00:01+00:00'
    status = assess(record, NOW, 'test/monitor')
    assert status['ready'] and status['on_time'] is False
    assert 'Termin 08:00 przekroczony' in status['timing']


def test_unknown_timestamp_is_not_misreported_as_meeting_the_deadline():
    status = assess(published(), NOW, 'test/monitor')
    assert status['on_time'] is None and 'nie potwierdzono' in status['timing']
    status = assess(None, NOW.replace(hour=7), 'test/monitor')
    assert 'termin upływa' in status['timing'] and not status['ready']
    status = assess(None, NOW, 'test/monitor')
    assert 'przekroczony' in status['timing'] and not status['ready']


@pytest.mark.parametrize('day,utc_hour', [('2026-10-24', 6), ('2026-10-25', 7)])
def test_readiness_deadline_uses_polish_dst(day, utc_hour):
    record = published()
    record['first_published_at'] = f'{day}T{utc_hour:02}:00:00+00:00'
    now = datetime.fromisoformat(day + 'T09:00:00').replace(tzinfo=WARSAW)
    assert assess(record, now, 'test/monitor')['on_time'] is True
    record['first_published_at'] = f'{day}T{utc_hour:02}:00:01+00:00'
    assert assess(record, now, 'test/monitor')['on_time'] is False


def test_same_day_rebuild_preserves_confirmed_publication_time_not_scan_finish(tmp_path):
    fake = FakeGitHub()
    remote = GitHubStore('test/monitor', 'fake', client=httpx.Client(transport=httpx.MockTransport(fake.request)))
    store, output = StateStore(tmp_path / 'state'), tmp_path / 'report'
    day = '2026-10-22'
    archive = prepare(store, output, day, 'a')
    remote.publish(store, output, day, archive, 'a')
    for asset in fake.assets.values():
        if asset['name'].startswith('commit-'):
            asset['created_at'] = day + 'T05:40:00Z'
    assert remote.published_report(day)['first_published_at'] == day + 'T05:40:00Z'
    prior_assets = set(remote.published_report(day)['report_assets'])
    archive = prepare(store, output, day, 'b')
    remote.publish(store, output, day, archive, 'b')
    for asset in fake.assets.values():
        if asset['name'] == 'commit-b.json':
            asset['created_at'] = day + 'T10:30:00Z'
    assert remote.published_report(day)['first_published_at'] == day + 'T05:40:00Z'
    assert prior_assets <= fake.assets.keys()
    assert len(remote.published_report(day)['editions']) == 2


@pytest.mark.browser
async def test_recovered_stylesheet_does_not_poison_capture_but_missing_styles_still_fail(executable):
    async with BrowserScanner(executable) as scanner:
        page = await scanner.browser.new_page()
        await page.route('https://fixture.test/**', lambda route: route.fulfill(
            status=200, content_type='text/css', body='body {color: rgb(1, 2, 3)}'))
        await page.set_content('<link rel="stylesheet" href="https://fixture.test/style.css"><h1>Oferta</h1>')
        await page.wait_for_function("getComputedStyle(document.body).color === 'rgb(1, 2, 3)'")
        assert await scanner.unresolved_styles(page, {'https://fixture.test/style.css'}, {'https://fixture.test/style.css'}) == []
        await page.route('https://fixture.test/missing.css', lambda route: route.abort())
        async with page.expect_event('requestfailed'):
            await page.evaluate("""() => {const e=document.createElement('link'); e.rel='stylesheet';
              e.href='https://fixture.test/missing.css'; document.head.append(e)}""")
        assert 'https://fixture.test/missing.css' in await scanner.unresolved_styles(
            page, {'https://fixture.test/missing.css'}, {'https://fixture.test/style.css'})
        await page.close()


@pytest.mark.browser
async def test_cookie_control_waits_for_delayed_handler_instead_of_accepting_a_noop(executable):
    async with BrowserScanner(executable) as scanner:
        page = await scanner.browser.new_page()
        await page.set_content('''<div role="dialog">Ta strona korzysta z cookies.
          <button id="cn-close-notice" aria-label="Nie wyrażam zgody">Zamknij</button></div>
          <script>setTimeout(() => document.querySelector('button').onclick = () => {
            document.querySelector('[role=dialog]').remove();
          }, 1000)</script>''')
        await scanner.cookies(page)
        assert await page.locator('[role=dialog]').count() == 0
        await page.close()


@pytest.mark.browser
async def test_normal_redirect_after_temporary_verification_is_captured(sample_site, executable, tmp_path, monkeypatch):
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        create_context = scanner.browser.new_context

        async def context(**kwargs):
            result = await create_context(**kwargs)
            await result.route('**/checking', lambda route: route.fulfill(status=403, content_type='text/html', body='''
              <title>Just a moment...</title><body>Weryfikacja
              <script>setTimeout(() => location.href='/', 500)</script></body>'''))
            return result

        monkeypatch.setattr(scanner.browser, 'new_context', context)
        site = Site('127.0.0.1', sample_site.url)
        captured = await scanner.capture(site, 'glowna', sample_site.url + '/checking',
                                         Scenario('podstawowy', 'Strona główna'), tmp_path / 'page.png')
        assert captured.snapshot.quality == 'ok'
        assert captured.snapshot.url == sample_site.url + '/'
        assert 'Just a moment' not in captured.snapshot.title


@pytest.mark.browser
async def test_site_can_identify_the_monitor_without_changing_other_sites(sample_site, executable, tmp_path, monkeypatch):
    site = Site('127.0.0.1', sample_site.url)
    sample_site.cookie_panel = '''<div id="cookie-notice" role="dialog">Informacja o cookies
      <button id="cn-accept-cookie" aria-label="Kontynuuj" onclick="this.parentElement.remove()">Kontynuuj</button></div>'''
    site.cookie_continue_selector = "#cookie-notice #cn-accept-cookie[aria-label='Kontynuuj']"
    scenario = Scenario('podstawowy', 'Strona główna')
    original = adapter_signature(site, scenario, 'glowna')
    site.user_agent = 'PracownieMonitor/1.0 (+https://github.com/MateuszD0/Pracownie)'
    assert adapter_signature(site, scenario, 'glowna') != original
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        create_context = scanner.browser.new_context
        received = []

        async def context(**kwargs):
            result = await create_context(**kwargs)
            result.on('request', lambda r: received.append(r.headers.get('user-agent')))
            return result

        monkeypatch.setattr(scanner.browser, 'new_context', context)
        captured = await scanner.capture(site, 'glowna', site.home_url, scenario, tmp_path / 'page.png')
        assert captured.snapshot.quality == 'ok'
        assert received and set(received) == {site.user_agent}


@pytest.mark.browser
async def test_cookie_animation_can_finish_before_motion_is_frozen(sample_site, executable, tmp_path):
    sample_site.cookie_panel = '''<style>@keyframes dismiss {to {opacity:0}}</style>
      <div id="cookie-notice" role="dialog" onanimationend="this.remove()">Informacja o cookies
      <button id="cn-close-notice" aria-label="Nie wyrażam zgody"
        onclick="this.parentElement.style.animation='dismiss .1s'">Zamknij</button></div>'''
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        site = Site('127.0.0.1', sample_site.url)
        captured = await scanner.capture(site, 'glowna', site.home_url,
                                         Scenario('podstawowy', 'Strona główna'), tmp_path / 'page.png')
        assert captured.snapshot.quality == 'ok'
        assert not captured.snapshot.document['consent']


@pytest.mark.browser
async def test_headed_access_is_scoped_to_one_site_and_has_separate_history(sample_site, executable, tmp_path, monkeypatch):
    import os
    import sys

    from playwright.async_api import Browser

    if sys.platform == 'linux' and not os.environ.get('DISPLAY'):
        pytest.skip('Uruchom test przez xvfb-run, jak w GitHub Actions.')
    create_context = Browser.new_context

    async def context(browser, **kwargs):
        result = await create_context(browser, **kwargs)

        async def protected(route):
            if 'HeadlessChrome' in route.request.headers.get('user-agent', ''):
                await route.fulfill(status=403, content_type='text/html', body='<title>Odmowa</title>')
            else:
                await route.fulfill(status=302, headers={'Location': sample_site.url + '/'})

        await result.route('**/window-required', protected)
        return result

    monkeypatch.setattr(Browser, 'new_context', context)
    site = Site('127.0.0.1', sample_site.url)
    scenario = Scenario('podstawowy', 'Strona główna')
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        with pytest.raises(ValueError, match='HTTP 403'):
            await scanner.capture(site, 'glowna', sample_site.url + '/window-required', scenario, tmp_path / 'denied.png')
        original_adapter = adapter_signature(site, scenario, 'glowna')
        site.browser_headed = True
        captured = await scanner.capture(site, 'glowna', sample_site.url + '/window-required', scenario, tmp_path / 'headed.png')
        assert captured.snapshot.quality == 'ok'
        assert '-headed|extractor=' in captured.snapshot.renderer
        assert original_adapter != adapter_signature(site, scenario, 'glowna')
        ordinary = await scanner.capture(Site('127.0.0.1', sample_site.url), 'glowna', sample_site.url, scenario, tmp_path / 'ordinary.png')
        assert '-headed' not in ordinary.snapshot.renderer
        assert scanner.headed_browser is not scanner.browser
        headed = scanner.headed_browser
    assert not headed.is_connected()
