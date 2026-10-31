import copy
import json

import pytest

from pracownie.browser import BrowserScanner, project_candidates
from pracownie.communication import measure
from pracownie.model import Scenario, Site
from pracownie.pipeline import RunOptions, run_scan
from pracownie.quality import communication_usable, only_font_styles
from pracownie.readiness import base_readiness, repair_domains
from pracownie.state import StateStore


def test_named_house_cards_without_price_or_thumbnail_are_discoverable():
    site = Site('test.pl', 'https://test.pl/')
    links = [
        {'url': 'https://test.pl/duo-line.html', 'text': 'DUO-LINE', 'context': 'DUO-LINE projekt domu piętrowego'},
        {'url': 'https://test.pl/idea.html', 'text': 'Nasza idea', 'context': 'Nasza idea'},
        {'url': 'https://test.pl/blog/wybor.html', 'text': 'Jak wybrać projekt', 'context': 'projekt domu'},
        {'url': 'https://outside.pl/duo.html', 'text': 'DUO', 'context': 'projekt domu'},
    ]
    assert [p['url'] for _, p in project_candidates(site, {'links': links})] == ['https://test.pl/duo-line.html']


@pytest.mark.parametrize('urls', [[], ['https://test.pl/fonts.css'], ['https://fonts.googleapis.com.evil.test/css'],
                                  ['https://fonts.googleapis.com/css', 'https://test.pl/layout.css']])
def test_unknown_missing_styles_are_never_waived(urls):
    assert not only_font_styles(urls)


def test_partial_text_requires_recorded_capture_checks_not_just_a_font_url():
    from test_communication import AFTER, BEFORE, capture

    old = capture(BEFORE, [('hero', 'heading', 'Oferta jesienna')])
    new = capture(AFTER, [('hero', 'heading', 'Oferta zimowa')])
    new.quality = 'partial'
    new.document['unresolved_styles'] = ['https://fonts.googleapis.com/css?family=Bitter']
    assert not communication_usable(new)
    assert not measure(old, new)[0]['comparable']
    new.document['readability'] = {'text_complete': True}
    status, changes = measure(old, new)
    assert status['comparable'] and status['text_only'] and len(changes) == 1
    new.document['readability']['text_complete'] = False  # e.g. consent panel or DOM limit
    assert not measure(old, new)[0]['comparable']


def test_font_failure_stays_visible_without_repeated_same_day_full_scans():
    row = {'domain': 'test.pl', 'page': 'glowna', 'scenario': 'podstawowy',
           'observed_at': '2026-10-31T06:00:00+00:00', 'data_quality': 'partial',
           'communication': {'ready': True, 'text_only': True}}
    quality = base_readiness('2026-10-31', [row, dict(row, page='projekt')], ['test.pl'])
    assert not quality['complete'] and len(quality['limited']) == 2
    assert len(quality['manual_review']) == 2 and repair_domains(quality) == []
    broken = dict(row, page='projekt', communication={'ready': False})
    assert repair_domains(base_readiness('2026-10-31', [row, broken], ['test.pl'])) == ['test.pl']


@pytest.mark.browser
async def test_visible_complianz_refusal_is_used_instead_of_hidden_template(executable):
    async with BrowserScanner(executable) as scanner:
        page = await scanner.browser.new_page()
        await page.set_content('''<div class="cmplz-cookiebanner" hidden><button class="cmplz-deny">Odrzuć</button></div>
          <div class="cmplz-cookiebanner" role="dialog">Pliki cookies
          <button class="cmplz-deny" aria-label="Odrzuć opcjonalne pliki cookie">Odrzuć</button>
          <button onclick="window.accepted=true">Akceptuję</button></div>
          <script>setTimeout(() => document.querySelector('[role=dialog] .cmplz-deny').onclick = () => {
            document.querySelector('[role=dialog]').remove();
          }, 500)</script>''')
        await scanner.cookies(page)
        assert await page.locator('[role=dialog]').count() == 0
        assert not await page.evaluate('Boolean(window.accepted)')


@pytest.mark.browser
async def test_font_only_history_compares_text_preserves_price_baseline_and_survives_restore(sample_site, executable, tmp_path, monkeypatch):
    original_enter = BrowserScanner.__aenter__

    async def enter(self):
        await original_enter(self)
        original_context = self.browser.new_context

        async def context(**kwargs):
            ctx = await original_context(**kwargs)
            await ctx.route('https://fonts.googleapis.com/**', lambda route: route.abort())
            return ctx

        monkeypatch.setattr(self.browser, 'new_context', context)
        return self

    monkeypatch.setattr(BrowserScanner, '__aenter__', enter)
    site = Site('test.pl', sample_site.url, project_url=sample_site.url + '/projekt-domu-testowy', inspection='verified')
    store, output = StateStore(tmp_path / 'state'), tmp_path / 'reports'
    key = 'test.pl/projekt/podstawowy'

    async def scan(day):
        at = day + 'T06:00:00+00:00'
        monkeypatch.setattr('pracownie.browser.now_iso', lambda: at)
        return await run_scan([site], store, output, RunOptions(day=day, browser_executable=executable,
            settle_ms=0, retries=0, ocr=False, max_scenarios=0, budget_seconds=120))

    await scan('2026-10-28')
    trusted = copy.deepcopy(store.read()['snapshots'][key])
    sample_site.cookie_panel = '<link rel="stylesheet" href="https://fonts.googleapis.com/css?family=Bitter">'
    await scan('2026-10-29')
    assert store.read()['snapshots'][key] == trusted
    assert store.read()['communication_snapshots'][key]['quality'] == 'partial'
    # Archive/restore must preserve both histories and every referenced image.
    archive = tmp_path / 'state.zip'
    store.export(archive)
    store = StateStore(tmp_path / 'restored')
    store.restore(archive)
    sample_site.bonus = 'Kosztorys gratis'
    sample_site.price = 4200
    third = await scan('2026-10-30')
    project = next(r for r in third['results'] if r.page == 'projekt' and r.scenario == 'podstawowy')
    assert project.communication['comparable'] and project.communication['text_only']
    assert project.compared_at.startswith('2026-10-29')
    copies = [c for c in project.changes if c.details.get('communication')]
    assert any('gratis' in (c.after or '') for c in copies)
    assert all(c.before_at.startswith('2026-10-29') for c in copies)
    prices = [c for c in project.changes if c.delta]
    assert prices and all(c.before_at.startswith('2026-10-28') for c in prices)
    assert all(c.evidence['przed'].rsplit('/', 1)[-1].startswith('przed-oferta.') for c in prices)
    assert all((output / c.evidence['przed']).is_file() for c in project.changes if c.evidence.get('przed'))
    assert store.read()['snapshots'][key] == trusted
    view = json.loads((output / '2026-10-30/oferty.json').read_text())
    assert all(p['communication']['daily'] for p in view['rows'][0]['pages'])
    assert all('grafika ograniczona' in p['communication']['label'] for p in view['rows'][0]['pages'])
    # Same-day repeats still compare to yesterday, not to this morning.
    state = store.begin('2026-10-30')
    assert store.previous_communication(state, key).observed_at.startswith('2026-10-29')
    from pracownie.rebuild import enrich_communication
    enrich_communication(third['results'], output, store.read())
    assert project.communication['comparable'] and project.communication['text_only']
    sample_site.cookie_panel = ''
    await scan('2026-10-31')
    assert key not in store.read()['communication_snapshots']
    assert store.read()['snapshots'][key]['observed_at'].startswith('2026-10-31')
    assert not store.begin('2027-05-01')['communication_anchor']


@pytest.mark.browser
async def test_cookie_or_missing_layout_still_disqualifies_text(sample_site, executable, tmp_path):
    site = Site('test.pl', sample_site.url)
    sample_site.cookie_panel = '''<div role="dialog">Pliki cookies — ustawienia</div>
      <link rel="stylesheet" href="https://fonts.googleapis.com/css?family=Bitter">'''
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        original_context = scanner.browser.new_context

        async def context(**kwargs):
            ctx = await original_context(**kwargs)
            await ctx.route('https://fonts.googleapis.com/**', lambda route: route.abort())
            return ctx

        scanner.browser.new_context = context
        captured = await scanner.capture(site, 'glowna', site.home_url, Scenario('podstawowy', 'Strona główna'), tmp_path / 'page.png')
        assert captured.snapshot.quality == 'partial'
        assert not communication_usable(captured.snapshot)
