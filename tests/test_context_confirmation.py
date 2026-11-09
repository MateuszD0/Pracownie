from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup
from test_communication import AFTER, BEFORE, capture
from test_management_dashboard import management_view

from pracownie.briefing import build_briefing
from pracownie.browser import COMMUNICATION, BrowserScanner
from pracownie.communication import mark_unstable, measure
from pracownie.contexts import context_reason
from pracownie.model import Result, Site
from pracownie.presentation import build_view, render_html
from pracownie.verification import assess_copy, verify_copy


def snapshots(text='Projekty z pełnym wsparciem architekta'):
    a = capture(BEFORE, [('hero', 'heading', 'Zbuduj dom swoich marzeń')])
    b = capture(AFTER, [('hero', 'heading', text)])
    return a, b, measure(a, b)[1][0]


def test_confirmation_requires_later_complete_same_page_same_day_capture():
    _, current, change = snapshots()
    assert assess_copy(change, current, current.url)['status'] == 'unverified'
    current.observed_at = (datetime.fromisoformat(AFTER) + timedelta(seconds=15)).isoformat()
    current.document['communication']['observed_at'] = current.observed_at
    assert assess_copy(change, current, current.url)['status'] == 'confirmed'
    current.document['communication']['items'][0]['text'] = change.before
    assert assess_copy(change, current, current.url)['status'] == 'unstable'
    current.document['communication']['items'][0]['text'] = change.after
    current.url += 'inna-strona'
    assert assess_copy(change, current, 'https://test.pl/')['status'] == 'unverified'
    current.url = 'https://test.pl/'
    current.document['communication']['truncated'] = True
    assert assess_copy(change, current, current.url)['status'] == 'unverified'


async def test_failed_confirmation_retains_observation_and_records_reason(tmp_path):
    _, current, change = snapshots()
    row = Result('test.pl', 'glowna', 'podstawowy', 'changed', current.url, [change], observed_at=AFTER)
    calls = []
    class Scanner:
        async def capture(self, *args):
            calls.append(args[2])
            raise ValueError('HTTP 403')
    await verify_copy(Site('test.pl', current.url), [row], Scanner(), tmp_path, tmp_path/'archive')
    assert calls == [current.url] and row.changes == [change]
    assert change.details['communication_check']['status'] == 'unverified'
    assert change.details['communication_check']['error'] == 'HTTP 403'
    assert row.observed_at == AFTER
    assert (tmp_path/'archive/weryfikacja-komunikacji.json').exists()


async def test_one_repeat_per_changed_page_and_no_repeat_for_testimonials(tmp_path):
    a, current, change = snapshots()
    current.observed_at = (datetime.fromisoformat(AFTER) + timedelta(seconds=10)).isoformat()
    current.document['communication']['observed_at'] = current.observed_at
    noise = measure(a, current)[1][0]
    noise.details['supporting_reason'] = 'Treść opinii klienta'
    row = Result('test.pl', 'glowna', 'podstawowy', 'changed', current.url, [change, noise], observed_at=AFTER)
    calls = []
    class Scanner:
        async def capture(self, *args):
            calls.append(args[2])
            return SimpleNamespace(snapshot=current)
    await verify_copy(Site('test.pl', current.url), [row], Scanner(), tmp_path, tmp_path/'archive')
    assert calls == [current.url]
    assert change.details['communication_check']['status'] == 'confirmed'
    assert 'communication_check' not in noise.details


def test_context_keeps_catalogue_promotions_but_not_testimonial_extras():
    quoted = {'context': 'testimonials', 'text': 'Dodatkowo dostaliśmy kosztorys gratis. Polecam!'}
    assert context_reason('test.pl', None, quoted, page='glowna')
    promo = {'context': 'catalogue', 'text': 'Projekt A — rabat 20% z kodem DOM'}
    assert not context_reason('test.pl', None, promo, page='glowna')
    assert context_reason('test.pl', None, promo, page='projekt')
    assert not context_reason('test.pl', None, {'key':'#hero','text':'Kosztorys gratis'}, page='glowna')


def test_dynamic_samples_keep_raw_values_and_do_not_mask_changed_discount():
    before = {'items':[{'key':'#typed', 'role':'heading', 'text':'REL|'}, {'key':'#promo', 'role':'banner', 'text':'Rabat 20%'}]}
    after = {'items':[{'key':'#typed', 'role':'heading', 'text':'RELAKSU|'}, {'key':'#promo', 'role':'banner', 'text':'Rabat 20%'}]}
    result = mark_unstable(before, after, 350)
    assert result['items'][0]['unstable'] and not result['items'][1].get('unstable')
    assert result['stability']['changed'][0]['before'] == ['REL|']
    a = capture(BEFORE, [('promo','banner','Rabat 10%')])
    b = capture(AFTER, [('promo','banner','Rabat 20%')])
    assert measure(a,b)[1][0].after == 'Rabat 20%'


def test_heading_alone_is_not_high_priority_and_failed_repeat_is_separate():
    view = management_view()
    item = dict(view['journal'][0], category='komunikacja', description='Dodano: Nagłówek',
                before='Dom dla każdego', after='Dom z pełnym wsparciem architekta', commercial_check={})
    view['journal'] = [item]
    event = build_briefing(view)['events'][0]
    assert event['priority'] == 'Standardowy'
    item['communication_check'] = {'status':'unverified','summary':'HTTP 503'}
    event = build_briefing(view)['events'][0]
    assert event['tier'] == 'review' and event['confidence'] == 'Do sprawdzenia'
    item['communication_check'] = {'status':'confirmed','summary':'Potwierdzono'}
    event = build_briefing(view)['events'][0]
    assert event['tier'] == 'main' and event['confidence'] == 'Potwierdzono ponownym odczytem'
    item['communication_check'] = {'status':'unstable'}
    assert not build_briefing(view)['events']


@pytest.mark.browser
async def test_dom_context_and_actual_changes_survive_to_executive_view(executable):
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        page = await scanner.browser.new_page()
        await page.set_content('''<section class="testimonials"><h2>Dodatkowo dostaliśmy garaż gratis</h2></section>
          <section id="project-list"><h2>Rabat 20% na projekt A</h2></section>
          <section id="hero"><h1>Projekty z pełnym wsparciem</h1></section>''')
        new = await page.evaluate(COMMUNICATION, 'glowna')
        assert next(i for i in new['items'] if 'garaż' in i['text'])['context'] == 'testimonials'
        a = capture(BEFORE, [('hero','heading','Zbuduj swój dom')])
        b = capture(AFTER, [])
        b.document['communication']['items'] = new['items']
        status, changes = measure(a, b)
        row = Result('test.pl','glowna','podstawowy','changed',a.url,changes,observed_at=AFTER,
                     compared_at=BEFORE,data_quality='ok',communication=status)
        view = build_view('2026-10-21',[row],{}, {},['test.pl'])
        events = build_briefing(view)['events']
        assert any(e['bucket']=='promotions' for e in events)
        assert not any('garaż' in e['sentence'] for e in events)
        assert any('garaż' in e['after'] for e in view['journal'])
        soup = BeautifulSoup(render_html(view),'html.parser')
        assert [x.text for x in soup.select('#brief-main thead th')] == ['Pracownia / miejsce','Było','Jest','Ważność / weryfikacja','Dowód']
