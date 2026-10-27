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


@pytest.mark.parametrize('keep_existing', [True, False])
def test_registry_removal_updates_publication_preserves_history_and_allows_resume(tmp_path, monkeypatch, keep_existing):
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
    (config/'sites.json').write_bytes(json_bytes({'schema':1, 'sites':[{'domain':domain,'home_url':f'https://{domain}'}]}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, 'argv', ['rebuild', '--repository','test/monitor','--root',str(tmp_path/'rebuilt'),'--publish'])
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
    assert raw['results'] == json.loads((output/day/'zmiany.json').read_text())['results'][:2]
    assert list(json.loads((reports/day/'pokrycie.json').read_text())) == ['test.pl']
    assert list(json.loads((reports/day/'wybrane-projekty.json').read_text())) == ['test.pl']
    assert raw['metadata']['domains'] == 1 and raw['metadata']['readiness']['expected'] == 2
    assert not (reports/day/slug('extradom.pl')).exists()
    verify_outputs(reports, day)
    resume_data(reports, day, [Site('test.pl','https://test.pl')], store.read(), ['test.pl'])
    dashboard = json.loads((reports/day/'oferty.json').read_text())
    assert [row['domain'] for row in dashboard['rows']] == ['test.pl']
    assert fake.contents[before['report_files']['zip']] == original_archive
    assert 'extradom.pl' in StateStore(tmp_path/'rebuilt/state').read()['selections']
