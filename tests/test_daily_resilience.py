import asyncio
import json

import pytest

from pracownie.model import Field, Result, Site, Snapshot
from pracownie.offers import primary_offer
from pracownie.pipeline import RunOptions, preserve_same_day_reads, run_scan
from pracownie.presentation import build_view
from pracownie.report import write_outputs
from pracownie.state import StateStore

DAY = "2026-10-20"
AFTER = "2026-10-20T06:00:00+00:00"


@pytest.mark.parametrize("matching", [True, False])
def test_failed_retry_keeps_documented_partial_read_without_promoting_it_to_a_baseline(tmp_path, matching):
    source, staging = tmp_path / 'source', tmp_path / 'staging'
    site = Site('test.pl', 'https://test.pl', 'https://test.pl/dom')
    shot = Snapshot('test.pl', 'projekt', 'podstawowy', site.project_url, AFTER, 'Dom', {'adapter:cena': Field('Cena', '5000 zł', 'ceny', amount='5000.00', currency='PLN', source='adapter', primary=True, role='current')}, ['oferta'], '', 'test', quality='partial')
    old = Result('test.pl', 'projekt', 'podstawowy', 'partial', site.project_url, observed_at=AFTER, data_quality='partial', offer=primary_offer(shot))
    folder = source / DAY / site.domain / 'projekt' / 'podstawowy'
    folder.mkdir(parents=True)
    raw = shot.to_dict()
    if not matching:
        raw['observed_at'] = '2026-10-19T06:00:00+00:00'
    (folder / 'odczyt.json').write_text(json.dumps(raw))
    write_outputs(source, DAY, [old], {'run_id': 'old', 'started_at': AFTER, 'finished_at': AFTER, 'elapsed_seconds': 0}, {}, [site.domain])
    failed = Result(site.domain, 'projekt', 'podstawowy', 'error', site.project_url, error='Przekroczono czas domeny (projekt/podstawowy); odczyt strony nieukończony.')
    results, state = [failed], {'snapshots': {}}
    retained = preserve_same_day_reads(results, [old], state, [site], source, staging, DAY)
    assert bool(retained) is matching
    assert state['snapshots'] == {}
    if matching:
        view = build_view(DAY, results, {'finished_at': AFTER}, {}, [site.domain])
        assert view['counts']['project'] == 1 and view['counts']['price_pairs'] == view['counts']['events'] == 0
        assert view['rows'][0]['current']['quality'] == 'partial'
        assert view['rows'][0]['observed_at'] == AFTER
        assert 'częściowy odczyt' in ' '.join(view['rows'][0]['issues'])


async def test_domain_timeout_records_each_missing_base_page_and_its_real_reason(tmp_path, monkeypatch):
    class SlowScanner:
        renderer = 'test'

        def __init__(self, *args):
            self.phases = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def capture(self, site, page, *args):
            self.phases[site.domain] = page + '/podstawowy: nawigacja'
            await asyncio.sleep(2)

    monkeypatch.setattr('pracownie.pipeline.BrowserScanner', SlowScanner)
    site = Site('test.pl', 'https://test.pl', 'https://test.pl/dom')
    outcome = await run_scan([site], StateStore(tmp_path / 'state'), tmp_path / 'report', RunOptions(day=DAY, domain_timeout=0.01, budget_seconds=2, ocr=False))
    base = [r for r in outcome['results'] if r.scenario == 'podstawowy']
    assert {r.page for r in base} == {'glowna', 'projekt'}
    assert all(r.error and not r.observed_at for r in base)
    view = build_view(DAY, outcome['results'], outcome['metadata'], {}, [site.domain])
    assert all('odczytu strony' in p['error_text'] for p in view['rows'][0]['pages'])
    assert view['management']['metrics']['sales'] == 0


def test_legacy_timeout_without_page_row_has_an_explanation_in_dashboard():
    result = Result('test.pl', 'zakres', 'limit-czasu', 'partial', 'https://test.pl', error='Przekroczono czas domeny (projekt/podstawowy: przewijanie); pozostały zakres nie został sprawdzony.')
    view = build_view(DAY, [result], {'finished_at': AFTER}, {}, ['test.pl'])
    assert all('odczytu strony' in p['error_text'] for p in view['rows'][0]['pages'])
    assert all('interakcji' not in p['error_text'] for p in view['rows'][0]['pages'])
