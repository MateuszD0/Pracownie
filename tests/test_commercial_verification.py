from types import SimpleNamespace

import pytest

from pracownie.commercial import assess, document, linked_pages, verify_offers
from pracownie.communication import measure
from pracownie.dashboard import render_dashboard_documents
from pracownie.model import Change, Result, Site, Snapshot
from pracownie.presentation import build_view, render_html
from pracownie.rebuild import enrich_communication

DAY = '2026-10-26'
AT = DAY + 'T06:00:00+00:00'
BEFORE = '2026-10-25T06:00:00+00:00'
URL = 'https://test.pl/dom'


def shot(texts, url=URL, at=AT, quality='ok', links=None):
    return Snapshot('test.pl', 'projekt' if url == URL else 'glowna', 'podstawowy', url, at, 'Dom A', {}, [], '', 'test', quality=quality,
        document={'communication': {'contract': 'communication-v1', 'observed_at': at, 'adapter': 'stable',
            'items': [{'key': f'#text-{i}', 'role': 'text', 'text': t, 'url': url} for i, t in enumerate(texts)]},
            'payload': {'links': links or [], 'commercial_context': {'contract': 'commercial-v1', 'items': [], 'truncated': False}}})


def change(before='Promocja JESIEŃ -20%', after=None, category='promocje'):
    return Change('removed' if after is None else 'added' if before is None else 'changed', category, 'Baner', before, after, BEFORE, AT, URL, 'podstawowy', details={'communication': True})


def test_absence_requires_successful_repeat_and_complete_service_check():
    c = change()
    doc = document(shot(['Opis domu i technologia wykonania.']), repeated=True)
    assert assess(c, URL, [doc], complete=True)['status'] == 'probably_ended'
    assert assess(c, URL, [doc], complete=False)['status'] == 'unverified'
    doc['complete'] = False
    assert assess(c, URL, [doc], complete=True)['status'] == 'unverified'
    doc['complete'], doc['repeated'] = True, False
    assert assess(c, URL, [doc], complete=True)['status'] == 'unverified'


def test_repeat_can_recover_missing_banner_without_claiming_promotion_ended():
    c = change()
    doc = document(shot([c.before]), repeated=True)
    result = assess(c, URL, [doc], complete=True)
    assert result['status'] == 'still_present'
    assert result['sources'][0]['text'] == c.before


def test_other_campaign_does_not_prove_the_removed_campaign_is_still_active():
    c = change()
    docs = [document(shot(['Opis domu.']), repeated=True),
            document(shot(['Promocja garaż za 50% ceny przy zakupie domu.'], url='https://test.pl/promocje'))]
    result = assess(c, URL, docs, complete=True)
    assert result['status'] == 'other_offers'
    assert result['sources'][0]['url'].endswith('/promocje')
    assert 'nie potwierdzają' in result['note']


@pytest.mark.parametrize(('after', 'category', 'status', 'label'), [
    ('Promocja od 2026-10-27: rabat 20%', 'promocje', 'scheduled', 'Zapowiedź promocji od 2026-10-27'),
    ('Promocja jeszcze się nie rozpoczęła.', 'promocje', 'scheduled', 'Zapowiedź promocji — jeszcze nieaktywna'),
    ('Kod rabatowy JESIEN20 daje 20% rabatu do 31.10.2026', 'promocje', 'added', 'Nowy kod rabatowy'),
    ('Kosztorys gratis do każdego projektu', 'dodatki', 'added', 'Nowy dodatek lub pakiet'),
    ('Pakiet', 'pakiety', 'label_only', 'Zmiana etykiety'),
    ('Powiadom o promocji', 'promocje', 'label_only', 'Zmiana etykiety'),
    ('Promocja JESIEŃ zakończona', 'promocje', 'ended', 'Serwis informuje o zakończeniu promocji'),
    ('Kod rabatowy JESIEN20 ważny do 25.10.2026', 'promocje', 'expired', 'Komunikat z minionym terminem oferty (2026-10-25)'),
])
def test_new_offers_codes_extras_and_future_dates(after, category, status, label):
    c = change(None, after, category)
    result = assess(c, URL, [document(shot([after]), repeated=True)], complete=True)
    assert result['status'] == status
    assert label in result['summary']
    c.details['commercial_check'] = result
    row = Result('test.pl', 'projekt', 'podstawowy', 'changed', URL, [c], observed_at=AT, compared_at=BEFORE, data_quality='ok')
    view = build_view(DAY, [row], {'finished_at': AT}, {}, ['test.pl'])
    assert view['journal'][0]['commercial_check'] == result
    docs = render_dashboard_documents(view, 'https://example.org/report')
    assert label in docs['dashboard/testpl.md']
    assert label in render_html(view)
    if status not in {'label_only', 'expired'}:
        assert label in docs['DASHBOARD.md']
        assert 'Sprawdzone warunki' in docs['DASHBOARD.md']


def test_unstable_or_next_day_reads_do_not_confirm_todays_new_offer():
    c = change(None, 'Promocja JESIEN20')
    doc = document(shot(['Opis domu.']), repeated=True)
    assert assess(c, URL, [doc], complete=True)['status'] == 'unstable'
    later = document(shot([c.after], at='2026-10-27T06:00:00+00:00'), repeated=True)
    assert assess(c, URL, [later], complete=True)['status'] == 'unverified'


def test_missing_terms_link_is_not_a_probable_end_of_a_campaign():
    c = change('Regulamin promocji >>')
    result = assess(c, URL, [document(shot(['Opis domu.']), repeated=True)], complete=True)
    assert result['status'] == 'label_only'


def test_service_links_are_bounded_and_do_not_visit_carts_other_projects_or_foreign_sites():
    urls = ['https://test.pl/promocje', 'https://test.pl/warunki-promocji.pdf',
            'https://other.pl/promocje', 'https://test.pl/?add-to-cart=42',
            'https://test.pl/produkt/other', 'https://test.pl/dom#promocja']
    snapshot = shot(['Oferta'], links=[{'url': u, 'text': 'Promocja'} for u in urls])
    links, omitted = linked_pages(Site('test.pl', 'https://test.pl/'), [snapshot], {URL})
    assert links == ['https://test.pl/promocje']
    assert omitted == 1  # An unread PDF prevents a claim of complete absence.


async def test_verification_records_read_only_sources_and_propagates_failure(tmp_path):
    c = change()
    project = shot(['Opis domu.'], links=[{'url': 'https://test.pl/promocje', 'text': 'Promocje'}])
    home = shot(['Projekty domów.'], url='https://test.pl/')
    result = Result('test.pl', 'projekt', 'podstawowy', 'changed', URL, [c], observed_at=AT)
    calls = []

    class Scanner:
        async def capture(self, site, page, url, scenario, dest):
            calls.append((url, scenario.actions))
            if url.endswith('/promocje'):
                raise RuntimeError('Odpowiedź HTTP 403')
            return SimpleNamespace(snapshot=project)

    await verify_offers(Site('test.pl', home.url), [SimpleNamespace(snapshot=s) for s in [home, project]], [result], [], Scanner(), tmp_path, tmp_path / 'archive')
    assert calls == [(URL, []), ('https://test.pl/promocje', [])]
    assert c.details['commercial_check']['status'] == 'unverified'
    assert (tmp_path / 'archive/weryfikacja-oferty.json').is_file()


def test_rebuild_preserves_only_verification_of_identical_observations(tmp_path):
    old, new = shot(['Promocja JESIEN20'], at=BEFORE), shot(['Opis domu.'])
    new.document['communication']['items'][0]['key'] = '#description'
    _, changes = measure(old, new)
    removed = next(c for c in changes if c.kind == 'removed')
    removed.details['commercial_check'] = {'status': 'probably_ended', 'summary': 'Sprawdzono serwis.'}
    result = Result('test.pl', 'projekt', 'podstawowy', 'changed', URL, changes, observed_at=AT, compared_at=BEFORE)
    state = {'anchor': {old.key: old.to_dict()}, 'snapshots': {new.key: new.to_dict()}}
    enrich_communication([result], tmp_path, state)
    assert next(c for c in result.changes if c.kind == 'removed').details['commercial_check']['status'] == 'probably_ended'
    next(c for c in result.changes if c.kind == 'removed').before = 'Inna promocja'
    enrich_communication([result], tmp_path, state)
    assert not any(c.details.get('commercial_check') for c in result.changes)


@pytest.mark.browser
async def test_commercial_context_includes_footer_offers_but_excludes_hidden_and_related_projects(executable):
    from pracownie.browser import COMMERCIAL, BrowserScanner
    async with BrowserScanner(executable) as scanner:
        page = await scanner.browser.new_page()
        await page.set_content('''<h1>Projekt domu</h1><h2>Podobne projekty</h2>
            <section class="related"><p>Inny projekt z rabatem 99%</p></section>
            <section id="garage-offer"><h2>Projekt garażu za 50% ceny</h2>
              <p>Promocja: projekt garażu za 50% ceny przy zakupie projektu domu.</p></section>
            <footer><a href="https://test.pl/promocje">Warunki promocji</a></footer>
            <p hidden>Ukryty kod rabatowy FAKE99</p>
            <div id="cookie-notice"><p>Rabat tylko w niezatwierdzonej warstwie cookies</p></div>''')
        context = await page.evaluate(COMMERCIAL)
        texts = [item['text'] for item in context['items']]
        assert any('garażu za 50%' in text for text in texts)
        assert not any('FAKE99' in text or '99%' in text or 'cookies' in text for text in texts)
        assert context['links'] == [{'url': 'https://test.pl/promocje', 'text': 'Warunki promocji'}]
        assert not context['truncated']


def test_missing_supplementary_capture_cannot_establish_absence():
    snapshot = shot(['Opis domu.'])
    snapshot.document['payload'].pop('commercial_context')
    assert not document(snapshot, repeated=True)['complete']


def test_free_shipping_cannot_confirm_a_different_addon_became_free():
    from pracownie.model import Field
    c = change('50 zł', 'gratis', 'dodatki')
    c.details = {}
    c.field_key, c.label = 'addon:estimate', 'Kosztorys'
    snapshot = shot(['Dostawa gratis', 'Kosztorys za 50 zł'])
    snapshot.fields[c.field_key] = Field('Kosztorys', '50 zł', 'dodatki')
    result = assess(c, URL, [document(snapshot, repeated=True)], complete=True)
    assert result['status'] == 'unstable'
    snapshot.fields[c.field_key].value = 'gratis'
    snapshot.document['communication']['items'][1]['text'] = 'Kosztorys gratis'
    result = assess(c, URL, [document(snapshot, repeated=True)], complete=True)
    assert result['status'] == 'changed'
    assert 'Kosztorys' in result['summary']


@pytest.mark.parametrize('text', ['pomieszczenia dodatkowe,', 'wygodnie pomieszczenia dodatkowe i pomocnicze;', 'ADAPTACJA PROJEKTU Dodatkowo należy dostosować fundamenty budynku do warunków gruntowych.'])
def test_technical_descriptions_are_not_commercial_extras(text):
    from pracownie.commercial import concrete, relevant
    assert not concrete(text)
    assert not relevant(change(text, None, 'dodatki'))
