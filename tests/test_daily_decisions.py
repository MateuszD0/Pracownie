import re

from test_management_dashboard import management_view

from pracownie.dashboard import render_dashboard_documents

REPORT = 'https://github.com/test/monitor/releases/tag/day'


def test_compact_summary_selects_confirmed_code_wording_and_links_its_own_evidence():
    view = management_view()
    base = view['journal'][0]
    before = 'Projekty taniej o 600 zł, a z kodem BLACK500 jeszcze o 500 zł'
    after = 'Wszystkie projekty taniej nawet o 1100 zł z kodem BLACK500'
    view['journal'] = [
        dict(base, id='copy', category='komunikacja', description='Nagłówek', before=before, after=after,
             communication_check={'status': 'confirmed', 'summary': 'Potwierdzono ponownym odczytem.'}),
        dict(base, id='label', before='brak', after='% PROMOCJA',
             commercial_check={'status': 'added', 'summary': 'Dodano etykietę.'}),
        dict(base, id='unconfirmed', before='brak', after='Rabat 90% z kodem PROBA90',
             commercial_check={'status': 'unverified', 'summary': 'Do sprawdzenia.'}),
    ]
    docs = render_dashboard_documents(view, REPORT)
    summary = docs['DASHBOARD.md'].split('## Najważniejsze zmiany dnia')[1].split('<details>')[0]
    assert 'Obniżki **1**' in summary and 'podwyżki **0**' in summary
    assert '5 000,00 zł → **dziś 4 500,00 zł**' in summary
    assert f'Wczoraj — {before}<br>**Dziś** — {after}' in summary and 'Komunikat z kodem' in summary
    assert 'PROBA90' not in summary and '% PROMOCJA' not in summary
    target, anchor = re.search(r'\[Przed i po\]\(([^)#]+)#([^)]+)\)', summary).groups()
    assert '## Zdarzenie ' + anchor.removeprefix('zdarzenie-') in docs[target]


def test_inventory_and_incomparable_prices_do_not_enter_daily_summary():
    view = management_view()
    view['journal'] = []
    view['comparison']['price_domains'] = []
    view['metadata']['intelligence'] = {'offers': [{
        'domain': 'test.pl', 'text': 'Rabat 10% z kodem STALY10', 'status': 'Obecna w zapisie',
        'sources': [{'url': 'https://test.pl/promocja', 'observed_at': '2026-10-20T07:00:00+00:00'}],
    }]}
    docs = render_dashboard_documents(view, REPORT)
    summary = docs['DASHBOARD.md'].split('## Najważniejsze zmiany dnia')[1].split('<details>')[0]
    assert 'Brak porównywalnych cen' in summary and 'Obniżki **0**' not in summary
    assert 'STALY10' not in summary and 'STALY10' in docs['dashboard/ceny-i-rabaty.md']
    assert 'brak zweryfikowanej zmiany' in summary
