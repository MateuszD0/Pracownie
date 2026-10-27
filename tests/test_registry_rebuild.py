import json
import sys

import httpx
import pytest
from PIL import Image
from test_github import FakeGitHub

from pracownie import rebuild
from pracownie.github import GitHubStore
from pracownie.model import Result, Site, json_bytes, slug
from pracownie.report import bundle_report, resume_data, verify_outputs, write_outputs
from pracownie.state import StateStore


@pytest.mark.parametrize(('keep_existing','include_new'), [(True,False),(False,False),(True,True)])
def test_registry_removal_updates_publication_preserves_history_and_allows_resume(tmp_path, monkeypatch, keep_existing, include_new):
    day = '2026-10-27'
    fake = FakeGitHub()
    def respond(request):
        if request.method == 'GET' and '/releases/assets/' in request.url.path and request.headers.get('accept') != 'application/octet-stream':
            return httpx.Response(200, json=fake.assets[int(request.url.path.rsplit('/', 1)[-1])])
        return fake.request(request)
    remote = GitHubStore('test/monitor', 'fake', client=httpx.Client(transport=httpx.MockTransport(respond)))
    store, output = StateStore(tmp_path/'state'), tmp_path/'source'
    state = store.begin(day)
    state['selections'] = {d:{'url':f'https://{d}/dom', 'name':'Stały projekt'} for d in ['test.pl', 'extradom.pl']}
    store.commit(state)
    rows = [Result(d, p, 'podstawowy', 'baseline', f'https://{d}/dom',
                   observed_at=day+'T05:00:00+00:00', data_quality='ok')
            for d in ['test.pl', 'extradom.pl'] for p in ['glowna', 'projekt']]
    removed_folder = output/day/slug('extradom.pl')/'projekt/podstawowy'
    removed_folder.mkdir(parents=True)
    Image.new('RGB', (20, 20), 'white').save(removed_folder/'po.png')
    metadata = {'run_id':'before-removal', 'started_at':day+'T05:00:00+00:00',
                'finished_at':day+'T05:01:00+00:00', 'elapsed_seconds':60,
                'domains':2, 'reused_domains':['test.pl','extradom.pl']}
    write_outputs(output, day, rows, metadata, state['selections'], ['test.pl','extradom.pl'])
    archive = tmp_path/'before.zip'
    bundle_report(output, day, archive)
    remote.publish(store, output, day, archive, 'before-removal')
    before = remote.published_report(day)
    original_archive = fake.contents[before['report_files']['zip']]
    config = tmp_path/'config'
    config.mkdir()
    domain = 'test.pl' if keep_existing else 'new.pl'
    configured = [{'domain':domain,'home_url':f'https://{domain}'}]
    if include_new:
        configured.append({'domain':'new.pl','home_url':'https://new.pl'})
    (config/'sites.json').write_bytes(json_bytes({'schema':1, 'sites':configured}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, 'argv', ['rebuild', '--repository','test/monitor','--root',str(tmp_path/'rebuilt'),'--publish'] + (['--include-new-sites'] if include_new else []))
    monkeypatch.setattr(rebuild, 'GitHubStore', lambda *a, **kw: remote)
    monkeypatch.setattr(remote, 'close', lambda: None)
    if not keep_existing:
        with pytest.raises(ValueError, match='pustego zakresu'):
            rebuild.main()
        assert remote.published_report(day)['run_id'] == before['run_id']
        return
    rebuild.main()
    reports = tmp_path/'rebuilt/raporty'
    raw = json.loads((reports/day/'zmiany.json').read_text())
    assert [r for r in raw['results'] if r['domain']=='test.pl'] == json.loads((output/day/'zmiany.json').read_text())['results'][:2]
    expected = ['new.pl','test.pl'] if include_new else ['test.pl']
    assert sorted(json.loads((reports/day/'pokrycie.json').read_text())) == expected
    assert list(json.loads((reports/day/'wybrane-projekty.json').read_text())) == ['test.pl']
    assert raw['metadata']['domains'] == len(expected) and raw['metadata']['readiness']['expected'] == len(expected)*2
    if include_new:
        pending = [r for r in raw['results'] if r['domain']=='new.pl']
        assert len(pending) == 2 and all(not r['observed_at'] and r['status']=='unavailable' for r in pending)
        assert raw['metadata']['new_domains'] == ['new.pl']
    assert not (reports/day/slug('extradom.pl')).exists()
    verify_outputs(reports, day)
    resume_data(reports, day, [Site(d,f'https://{d}') for d in expected], store.read(), ['test.pl'])
    dashboard = json.loads((reports/day/'oferty.json').read_text())
    assert sorted(row['domain'] for row in dashboard['rows']) == expected
    if include_new:
        new = next(r for r in dashboard['rows'] if r['domain']=='new.pl')
        assert new['scan_pending'] and all(p['communication']['label']=='Oczekuje na pierwszy skan' for p in new['pages'])
    assert fake.contents[before['report_files']['zip']] == original_archive
    assert 'extradom.pl' in StateStore(tmp_path/'rebuilt/state').read()['selections']
