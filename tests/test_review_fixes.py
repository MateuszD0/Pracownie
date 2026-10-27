import copy
import io
from datetime import datetime

import httpx
import pytest
from PIL import Image, ImageDraw
from test_github import FakeGitHub, prepare

from pracownie.github import GitHubStore
from pracownie.images import VisualDiff, compact_evidence, image_difference, lossless_image
from pracownie.journal import build_journal
from pracownie.management import highlight_eligible
from pracownie.model import WARSAW, Result, Snapshot, digest
from pracownie.observations import visual_description
from pracownie.readiness import base_readiness, check_ready
from pracownie.report import bundle_report, write_outputs
from pracownie.schedule import RECOVERY_CRON, daily_gate
from pracownie.state import StateStore, atomic_write

DAY = '2026-10-21'
OLD = '2026-10-20T06:00:00+00:00'
NEW = '2026-10-21T06:00:00+00:00'


def shot(elements, when=OLD, **scope):
    return Snapshot('test.pl', 'projekt', 'podstawowy', 'https://test.pl/dom', when,
                    'Dom', {}, [], '', 'test', document={'visual': {'schema': 1, 'elements': elements, **scope}})


def test_reordered_images_still_report_resizing_without_fabricating_movement():
    a = {'key': 'a', 'src': 'a.jpg', 'label': 'Dom A', 'rect': [0, 0, 300, 200]}
    b = {'key': 'b', 'src': 'b.jpg', 'label': 'Dom B', 'rect': [300, 0, 300, 200]}
    before = shot([a, b])
    after = shot([{**b, 'key': 'a', 'rect': [0, 0, 600, 400]},
                  {**a, 'key': 'b', 'rect': [600, 0, 600, 400]}], NEW)
    details = visual_description(before, after, VisualDiff(True, .3, None))
    assert len(details['facts']) == 2
    assert all(f['what'].startswith('Rozmiar:') and '600 × 400' in f['after'] for f in details['facts'])


def test_reordered_headlines_are_not_claimed_as_rewritten_messages():
    a = {'key': '#slot-1', 'text': 'Koszt budowy domu w 2026', 'label': 'Koszt budowy domu w 2026'}
    b = {'key': '#slot-2', 'text': 'Kierownik budowy i jego obowiązki', 'label': 'Kierownik budowy i jego obowiązki'}
    before = shot([a, b])
    after = shot([{**b, 'key': '#slot-1'}, {**a, 'key': '#slot-2'}], NEW)
    facts = visual_description(before, after, VisualDiff(True, .3, None))['facts']
    assert not any(f['what'].startswith('Widoczny nagłówek:') for f in facts)
    after = shot([{**a, 'text': 'Nowy przekaz o domach', 'label': 'Nowy przekaz o domach'}, b], NEW)
    facts = visual_description(before, after, VisualDiff(True, .3, None))['facts']
    assert any(f['before'] == a['text'] and f['after'] == 'Nowy przekaz o domach' for f in facts)


def test_different_unrelated_headlines_in_positional_slot_are_not_an_edit():
    key = '#articles > h2:nth-of-type(1)'
    before = shot([{'key': key, 'text': 'Kierownik budowy i jego obowiązki'}])
    after = shot([{'key': key, 'text': 'Powierzchnia zabudowy i jak ją liczyć'}], NEW)
    facts = visual_description(before, after, VisualDiff(True, .3, None))['facts']
    assert not any(f['what'].startswith('Widoczny nagłówek:') for f in facts)


def test_all_style_facts_survive_and_journal_has_distinct_element_ids():
    elements = [{'key': str(i), 'label': 'treść strony', 'color': 'black'} for i in range(25)]
    before = shot(elements)
    after = shot([{**e, 'color': 'red'} for e in elements], NEW)
    details = visual_description(before, after, VisualDiff(True, .5, None))
    assert details['fact_count'] == len(details['facts']) == 25
    row = {'domain': 'test.pl', 'name': 'Dom', 'events': [], 'visuals': [{
        'page': 'projekt', 'scenario': 'podstawowy', 'before_at': OLD, 'after_at': NEW,
        'evidence': {}, 'details': details}]}
    row['visuals'].append(copy.deepcopy(row['visuals'][0]))
    journal = build_journal(DAY, [row])
    assert len(journal) == len({r['id'] for r in journal}) == 25
    row['visuals'][1]['scenario'] = 'wariant'
    assert len(build_journal(DAY, [row])) == 50


@pytest.mark.parametrize('scope', [{'truncated': True}, {'scope': 'different'}])
def test_scope_change_cannot_invent_removed_images(scope):
    before = shot([{'key': 'a', 'src': 'a.jpg'}], scope='visible-sales-v2')
    after = shot([], NEW, **scope)
    assert not visual_description(before, after, VisualDiff(True, .5, None))['facts']


def test_recovery_retries_transient_base_failures_but_keeps_permanent_blocks(tmp_path):
    fake = FakeGitHub()
    remote = GitHubStore('test/monitor', 'fake', client=httpx.Client(transport=httpx.MockTransport(fake.request)))
    store, output = StateStore(tmp_path / 'state'), tmp_path / 'report'
    prepare(store, output, DAY, 'initial')
    results = [Result('test.pl', p, 'podstawowy', 'error', 'https://test.pl', error='HTTP 503') for p in ['glowna', 'projekt']]
    metadata = {'run_id': 'failed', 'started_at': NEW, 'finished_at': NEW, 'elapsed_seconds': 1}
    write_outputs(output, DAY, results, metadata, {}, ['test.pl'])
    archive = tmp_path / 'report.zip'
    bundle_report(output, DAY, archive)
    remote.publish(store, output, DAY, archive, 'failed')
    record = remote.published_report(DAY)
    assert record['readiness']['fresh'] == 0 and not check_ready(record)[0]
    decision = daily_gate(RECOVERY_CRON, datetime(2026, 10, 21, 6, 7, tzinfo=WARSAW), remote)
    assert decision['run_scan'] and decision['repair_domains'] == ['test.pl']
    raw = [{'domain': 'test.pl', 'page': p, 'scenario': 'podstawowy', 'error': 'HTTP 403'} for p in ['glowna', 'projekt']]
    blocked = base_readiness(DAY, raw, ['test.pl'])
    assert not blocked['retry_domains'] and len(blocked['blocked']) == 2
    assert not check_ready({'readiness': blocked})[0]


def test_readiness_rejects_stale_and_unknown_quality_and_accepts_fresh_reads():
    rows = [{'domain': 'test.pl', 'page': p, 'scenario': 'podstawowy', 'observed_at': NEW, 'data_quality': 'ok'} for p in ['glowna', 'projekt']]
    assert check_ready({'readiness': base_readiness(DAY, rows, ['test.pl'])})[0]
    rows[0]['observed_at'] = OLD
    rows[1]['data_quality'] = 'unknown'
    assert base_readiness(DAY, rows, ['test.pl'])['fresh'] == 0


def test_publication_deadline_timestamp_is_taken_after_commit_manifest(tmp_path, monkeypatch):
    fake = FakeGitHub()
    remote = GitHubStore('test/monitor', 'fake', client=httpx.Client(transport=httpx.MockTransport(fake.request)))
    store, output = StateStore(tmp_path / 'state'), tmp_path / 'report'
    archive = prepare(store, output, DAY, 'a')
    def clock():
        committed = any(a['name'].startswith('commit-') for a in fake.assets.values())
        return DAY + ('T06:00:01+00:00' if committed else 'T05:59:59+00:00')
    monkeypatch.setattr('pracownie.github.now_iso', clock)
    result = remote.publish(store, output, DAY, archive, 'a')
    assert result['published_at'] == DAY + 'T06:00:01+00:00'


@pytest.mark.parametrize("relative_root", [False, True])
def test_lossless_compression_dedup_and_mixed_history_restore(tmp_path, monkeypatch, relative_root):
    image = Image.new('RGB', (1000, 2000), 'white')
    ImageDraw.Draw(image).rectangle((50, 50, 800, 1000), fill='red')
    folder = tmp_path / 'report' / DAY / 'test.pl' / 'projekt' / 'podstawowy'
    folder.mkdir(parents=True)
    before, after = folder / 'przed.png', folder / 'po.png'
    image.save(before)
    image.save(after)
    compressed, extension = lossless_image(before)
    assert extension == '.webp' and len(compressed) < before.stat().st_size
    assert Image.open(io.BytesIO(compressed)).convert('RGB').tobytes() == image.tobytes()
    result = Result('test.pl', 'projekt', 'podstawowy', 'unchanged', 'https://test.pl', evidence={
        'przed': before.relative_to(tmp_path / 'report').as_posix(), 'po': after.relative_to(tmp_path / 'report').as_posix()})
    from pathlib import Path
    monkeypatch.chdir(tmp_path)
    stats = compact_evidence(Path("report") if relative_root else tmp_path / "report", DAY, [result])
    assert stats['saved_bytes'] > 0 and result.evidence['przed'] == result.evidence['po']
    stored = tmp_path / 'report' / result.evidence['po']
    source = tmp_path / 'original.png'
    image.save(source)
    assert not image_difference(source, stored, tmp_path / 'diff.png').changed
    store = StateStore(tmp_path / 'state')
    data = store.begin(DAY)
    legacy = f'images/{digest(source)}.png'
    atomic_write(store.root / legacy, source.read_bytes())
    old, new = shot([]), shot([], NEW)
    old.image, new.image = legacy, store.image(source)
    data['anchor'][old.key], data['snapshots'][new.key] = old.to_dict(), new.to_dict()
    store.commit(data)
    store.export(tmp_path / 'state.zip')
    restored = StateStore(tmp_path / 'restored')
    restored.restore(tmp_path / 'state.zip')
    assert restored.read() == data
    restored.collect(data)
    assert (restored.root / old.image).exists() and (restored.root / new.image).exists()


def test_very_tall_screenshot_falls_back_to_png_without_cropping(tmp_path):
    path = tmp_path / 'tall.png'
    Image.new('RGB', (10, 17000), 'white').save(path)
    data, extension = lossless_image(path)
    assert extension == '.png' and data == path.read_bytes()


def test_minor_calendar_and_layout_changes_remain_outside_highlights():
    assert not highlight_eligible({'category': 'warunki', 'before': 'Wyślemy projekt jutro kurierem', 'after': 'Wyślemy projekt dzisiaj kurierem'})
    assert not highlight_eligible({'category': 'obraz', 'description': 'Przesunięcie: dom (28 px w dół)', 'before': 'a', 'after': 'b'})
    assert highlight_eligible({'category': 'promocje', 'before': 'Rabat 10%', 'after': 'Rabat 20%'})


@pytest.mark.parametrize("changed_adapter", [False, True])
async def test_base_checkpoint_survives_failure_and_resume_does_not_revisit_good_pages(tmp_path, monkeypatch, changed_adapter):
    import json

    from pracownie.browser import Capture, adapter_signature
    from pracownie.model import Field, Site
    from pracownie.pipeline import RunOptions, run_scan
    from pracownie.report import verify_outputs

    store, output = StateStore(tmp_path / 'state'), tmp_path / 'report'
    calls = []
    class Scanner:
        renderer = 'test'
        fail = True

        def __init__(self, *args):
            self.phases = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            verify_outputs(output, DAY)
            assert json.loads((output / DAY / 'zmiany.json').read_text())['metadata']['scan_phase'] == 'base-checkpoint'
            assert len(store.read()['snapshots']) == 2
            if self.fail:
                raise RuntimeError('interrupted after base checkpoint')

        async def capture(self, site, kind, url, scenario, dest):
            calls.append(kind)
            dest.parent.mkdir(parents=True, exist_ok=True)
            Image.new('RGB', (100, 100), 'white').save(dest)
            snapshot = Snapshot(site.domain, kind, scenario.id, url, NEW, 'Dom',
                {'promo': Field('Promocja', 'Kosztorys gratis', 'promocje')},
                ['oferta'], '', self.renderer, document={'payload': {'controls': []}, 'adapter': adapter_signature(site, scenario, kind)})
            return Capture(snapshot, {'controls': []}, dest)

    # The synthetic scanner exercises persistence without external websites.
    monkeypatch.setattr('pracownie.pipeline.BrowserScanner', Scanner)
    site = Site('test.pl', 'https://test.pl', 'https://test.pl/dom', inspection='verified')
    options = RunOptions(day=DAY, ocr=False)
    with pytest.raises(RuntimeError, match='checkpoint'):
        await run_scan([site], store, output, options)
    assert calls == ['glowna', 'projekt']
    Scanner.fail = False
    options.resume = True
    if changed_adapter:
        site.masks = ["#clock"]
    result = await run_scan([site], store, output, options)
    assert calls == ['glowna', 'projekt'] * (2 if changed_adapter else 1)
    assert result['metadata']['scan_phase'] == 'complete'
    assert len([r for r in result['results'] if r.scenario == 'podstawowy']) == 2
    verify_outputs(output, DAY)


@pytest.mark.browser
async def test_visual_collector_reports_limit_and_counts_all_eligible_elements(executable):
    from pracownie.browser import VISUALS, BrowserScanner

    async with BrowserScanner(executable) as scanner:
        page = await scanner.browser.new_page()
        await page.set_content('<body>' + ''.join(f'<h2 id="h{i}">Nagłówek {i}</h2>' for i in range(1005)) + '</body>')
        result = await page.evaluate(VISUALS)
        assert result['scope'] == 'visible-sales-v2'
        assert len(result['elements']) == result['limit'] == 1000
        assert result['eligible'] == 1006 and result['truncated']
        await page.close()


def test_partial_capture_is_fresh_but_cannot_make_readiness_green():
    rows = [{'domain': 'test.pl', 'page': p, 'scenario': 'podstawowy', 'observed_at': NEW, 'data_quality': 'partial'} for p in ['glowna', 'projekt']]
    result = base_readiness(DAY, rows, ['test.pl'])
    assert result['fresh'] == 2 and len(result['limited']) == 2
    assert not check_ready({'readiness': result})[0]


def test_readiness_workflow_is_read_only_and_does_not_wait_for_scan_lock():
    from pathlib import Path

    import yaml

    workflow = yaml.load(Path('.github/workflows/readiness.yml').read_text(), Loader=yaml.BaseLoader)
    assert workflow['permissions'] == {'contents': 'read'}
    assert workflow['on']['schedule'] == [{'cron': '50 5,6 * * *'}]
    assert 'concurrency' not in workflow['jobs']['readiness']
