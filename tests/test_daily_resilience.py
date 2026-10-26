import asyncio
import json

import pytest

from pracownie.model import Field, Result, Site, Snapshot
from pracownie.offers import primary_offer
from pracownie.pipeline import RunOptions, preserve_same_day_reads, run_scan
from pracownie.presentation import build_view
from pracownie.rebuild import repair_archived_quotes
from pracownie.report import resume_data, write_outputs
from pracownie.state import StateStore

DAY = "2026-10-20"
AFTER = "2026-10-20T06:00:00+00:00"


def test_targeted_addition_preserves_existing_observations_and_errors(tmp_path):
    existing = Site('old.pl', 'https://old.pl')
    added = Site('new.pl', 'https://new.pl')
    results = [
        Result(existing.domain, 'glowna', 'podstawowy', 'unchanged', existing.home_url,
               observed_at=AFTER, compared_at='2026-10-19T06:00:00+00:00', data_quality='ok'),
        Result(existing.domain, 'projekt', 'podstawowy', 'error', existing.home_url,
               error='Odpowiedź HTTP 403'),
    ]
    metadata = {'run_id': 'old', 'started_at': AFTER, 'finished_at': AFTER, 'elapsed_seconds': 0}
    write_outputs(tmp_path, DAY, results, metadata, {}, [existing.domain])
    reused, retained, original = resume_data(tmp_path, DAY, [existing, added], {'day': DAY}, [added.domain])
    assert reused == {existing.domain}
    assert retained == results
    assert original['run_id'] == 'old'
    # An added studio still needs its first real capture; no earlier baseline is invented.
    view = build_view(DAY, retained, original, {}, [existing.domain, added.domain])
    assert len(view['rows']) == 2
    for sites, repair in [([existing, added], None), ([existing, added], [existing.domain]),
                          ([added], [added.domain])]:
        with pytest.raises(ValueError, match='inny zakres domen'):
            resume_data(tmp_path, DAY, sites, {'day': DAY}, repair)


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


def test_reviewed_price_correction_uses_actual_archived_text_and_cannot_create_a_fake_cut(tmp_path):
    from pracownie.offers import price_delta

    field = Field('Cena brutto', 'DOM—B55 pow. użytkowa 121,30 m2 \n4899 zł\nZAMAWIAM\n(w tym 23% VAT)', 'ceny', amount='24899.00', currency='PLN', source='adapter', primary=True, role='current', tax='gross')
    shot = Snapshot('projektyszkieletowe.pl', 'projekt', 'podstawowy', 'https://www.projektyszkieletowe.pl/projekt-dom-b55-63.html', AFTER, 'DOM—B55', {'adapter:cena-projektu': field}, ['oferta'], '', 'test')
    quote = primary_offer(shot)
    assert quote['amount'] == '4899.00' and field.amount == '24899.00'
    assert quote['observed_at'] == AFTER and quote['tax'] == 'gross'
    folder = tmp_path / DAY / shot.domain / 'projekt' / 'podstawowy'
    folder.mkdir(parents=True)
    (folder / 'odczyt.json').write_text(json.dumps(shot.to_dict()))
    result = Result(shot.domain, shot.page, shot.scenario, 'baseline', shot.url, observed_at=AFTER, data_quality='ok', offer={**quote, 'amount': '24899.00'})
    corrections = repair_archived_quotes([result], tmp_path, DAY)
    assert len(corrections) == 1 and corrections[0]['before'] == '24899.00' and corrections[0]['after'] == '4899.00'
    assert result.offer['amount'] == '4899.00' and result.observed_at == AFTER
    assert price_delta(primary_offer(shot), result.offer) == ('0.00', '0.00')
    (folder / 'odczyt.json').unlink()
    repair_archived_quotes([result], tmp_path, DAY)
    assert result.offer == {}
