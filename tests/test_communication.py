import copy
import json

import pytest
from bs4 import BeautifulSoup

from pracownie.browser import COMMUNICATION, BrowserScanner
from pracownie.communication import CONTRACT, measure
from pracownie.model import Field, Result, Snapshot
from pracownie.observations import visual_description
from pracownie.presentation import build_view, render_html
from pracownie.rebuild import enrich_communication

BEFORE = '2026-10-20T06:00:00+00:00'
AFTER = '2026-10-21T06:00:00+00:00'


def capture(at, texts):
    items = [{'role': role, 'text': text, 'key': key, 'url': 'https://test.pl/#oferta'} for key, role, text in texts]
    return Snapshot('test.pl', 'glowna', 'podstawowy', 'https://test.pl/', at, 'Oferta', {}, [], '', 'chromium-1|extractor=any-price-parser', document={'communication': {'contract': CONTRACT, 'observed_at': at, 'adapter': 'copy-rules', 'items': items}})


def test_copy_changes_are_independent_of_price_adapters_and_have_source_excerpts():
    old = capture(BEFORE, [('hero', 'heading', 'Zbuduj dom swoich marzeń'), ('cta', 'cta', 'Sprawdź ofertę'), ('bonus', 'text', 'Kosztorys za 150 zł')])
    new = capture(AFTER, [('hero', 'heading', 'Projekty z pełnym wsparciem architekta'), ('cta', 'cta', 'Porozmawiaj z architektem'), ('bonus', 'text', 'Kosztorys gratis')])
    old.document['adapter'], new.document['adapter'] = 'old-price-selector', 'new-price-selector'
    new.renderer = 'chromium-1|extractor=new-price-parser'
    status, changes = measure(old, new)
    assert status['comparable'] and status['ready'] and status['changes'] == 3
    assert {c.label for c in changes} == {'Nagłówek', 'Wezwanie do działania', 'Treść'}
    assert all(c.before_at == BEFORE and c.after_at == AFTER and c.url == 'https://test.pl/#oferta' for c in changes)
    assert any(c.category == 'dodatki' and c.after == 'Kosztorys gratis' for c in changes)
    for c in changes:
        c.evidence = {'przed': '2026-10-21/przed.png', 'po': '2026-10-21/po.png'}
    result = Result('test.pl', 'glowna', 'podstawowy', 'changed', new.url, changes, observed_at=AFTER, compared_at=BEFORE, data_quality='ok', communication=status)
    view = build_view('2026-10-21', [result], {'finished_at': AFTER}, {}, ['test.pl'])
    assert view['management']['metrics']['communication'] == 1
    assert view['rows'][0]['pages'][0]['communication']['daily']
    assert not view['comparison']['price_domains']
    soup = BeautifulSoup(render_html(view), 'html.parser')
    assert '1/1' in soup.select_one('#quality-summary').text
    assert 'Kosztorys gratis' in soup.select_one('#journal').text
    assert all(soup.select_one(a['href']) for a in soup.select('[data-communication-change-page] a'))


def test_reordering_carousel_inventory_cookies_counters_and_price_alone_are_not_copy_changes():
    texts = [('slide1', 'banner', 'Rabat 20% na projekty'), ('slide2', 'banner', 'Kosztorys gratis'), ('price', 'text', 'Cena projektu 4500 zł'), ('privacy', 'text', 'Wyrażam zgodę na przetwarzanie danych osobowych')]
    old = capture(BEFORE, texts)
    new = capture(AFTER, list(reversed(texts[:-2])) + [('price', 'text', 'Cena projektu 4200 zł'), ('privacy', 'text', 'Cookies i prywatność')])
    status, changes = measure(old, new)
    assert status['comparable'] and status['status'] == 'unchanged' and changes == []
    new.document['communication']['items'].append({'role': 'banner', 'key': 'new', 'text': 'Bezpłatna konsultacja przy zamówieniu', 'url': 'https://test.pl/'})
    _, changes = measure(old, new)
    assert len(changes) == 1 and changes[0].kind == 'added'


def test_architectural_privacy_is_offer_copy_while_consent_is_noise():
    old = capture(BEFORE, [('description', 'text', 'Dom zapewnia prywatność i spokój'), ('privacy', 'text', 'Polityka prywatności')])
    new = capture(AFTER, [('description', 'text', 'Prywatność sypialni oraz wygodny salon'), ('privacy', 'text', 'Ustawienia prywatności')])
    status, changes = measure(old, new)
    assert status['comparable'] and len(changes) == 1
    assert changes[0].before == 'Dom zapewnia prywatność i spokój'
    assert changes[0].after == 'Prywatność sypialni oraz wygodny salon'


@pytest.mark.parametrize('problem', ['partial', 'different-url', 'different-copy-rules', 'truncated', 'wrong-time'])
def test_incompatible_or_incomplete_captures_never_claim_campaign_changes(problem):
    old = capture(BEFORE, [('hero', 'heading', 'Rabat 10%')])
    new = capture(AFTER, [('hero', 'heading', 'Rabat 20%')])
    if problem == 'partial':
        old.quality = 'partial'
    elif problem == 'different-url':
        old.url += 'inny-dom'
    elif problem == 'different-copy-rules':
        old.document['communication']['adapter'] = 'different'
    elif problem == 'truncated':
        old.document['communication']['truncated'] = True
    else:
        old.document['communication']['observed_at'] = AFTER
    status, changes = measure(old, new)
    assert not status['comparable'] and not changes
    assert status['status'] == 'partial'


def test_unknown_legacy_parser_can_establish_shared_texts_but_not_new_promotions():
    old = capture(BEFORE, [])
    old.renderer = 'chromium-1|extractor=9d9303a762451244-unknown'
    old.document = {}
    old.fields = {'tekst:oferta:komunikacja': Field('Opis', 'Pomagamy od projektu do budowy', 'komunikacja', observed_at=BEFORE)}
    new = capture(AFTER, [('hero', 'heading', 'Nowa promocja na projekty')])
    new.fields = {'tekst:oferta:komunikacja': Field('Opis', 'Pomagamy od projektu do budowy', 'komunikacja', observed_at=AFTER)}
    status, changes = measure(old, new)
    assert status['shared_unchanged'] == 1 and status['ready']
    assert status['status'] == 'partial' and not status['comparable'] and not changes


def test_identical_verified_legacy_images_establish_only_an_unchanged_captured_view():
    old = capture(BEFORE, [])
    new = capture(AFTER, [('hero', 'heading', 'Oferta')])
    old.document = {}
    old.image = new.image = 'images/' + 'a' * 64 + '.png'
    status, changes = measure(old, new)
    assert status['same_visible_image'] and not status['comparable'] and not changes
    result = Result('test.pl', 'glowna', 'podstawowy', 'review', new.url, observed_at=AFTER, compared_at=BEFORE, data_quality='ok', communication=status)
    page = build_view('2026-10-21', [result], {'finished_at': AFTER}, {}, ['test.pl'])['rows'][0]['pages'][0]
    assert page['communication']['label'] == 'Zrzut bez różnic · zakres częściowy'
    assert not page['communication']['daily']
    old.quality = 'partial'
    assert not measure(old, new)[0]['same_visible_image']
    old.quality = 'ok'
    new.image = 'images/' + 'b' * 64 + '.png'
    assert not measure(old, new)[0]['same_visible_image']


def test_format_rebuild_uses_original_sources_is_idempotent_and_rejects_other_dates(tmp_path):
    old = capture(BEFORE, [('hero', 'heading', 'Rabat 10%')])
    new = capture(AFTER, [('hero', 'heading', 'Rabat 20%')])
    folder = tmp_path / '2026-10-21/test.pl/glowna/podstawowy'
    folder.mkdir(parents=True)
    (folder / 'odczyt.json').write_text(json.dumps(new.to_dict()))
    result = Result('test.pl', 'glowna', 'podstawowy', 'changed', new.url, observed_at=AFTER, compared_at=BEFORE, data_quality='ok')
    state = {'anchor': {old.key: old.to_dict()}}
    enrich_communication([result], tmp_path, state)
    first = copy.deepcopy(result)
    enrich_communication([result], tmp_path, state)
    assert result == first and len(result.changes) == 1
    assert result.changes[0].before == 'Rabat 10%' and result.communication['comparable']
    result.observed_at = BEFORE
    result.communication = {}
    enrich_communication([result], tmp_path, state)
    assert not result.communication


@pytest.mark.browser
async def test_collector_captures_header_campaign_cta_hidden_slides_and_open_interactions(executable):
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        page = await scanner.browser.new_page()
        await page.set_content('''<body class="cookies-accepted"><header role="banner"><nav><a href="/">Kontakt nawigacja</a></nav><p>Weekend z bezpłatną konsultacją</p></header>
        <main><h1>Buduj na swoich zasadach</h1><a href="/oferta">Porozmawiaj z architektem</a>
        <div class="swiper"><div class="swiper-slide"><p>Rabat 20%</p></div><div class="swiper-slide" style="display:none"><p>Kosztorys gratis</p></div><div class="swiper-slide-duplicate"><p>Rabat 20%</p></div></div>
        <details><summary>Dodatki</summary><p>Projekt instalacji gratis</p></details></main>
        <footer>Promocja w stopce</footer><div id="cookie-notice">Cookies akceptuję</div>''')
        first = await page.evaluate(COMMUNICATION, 'glowna')
        texts = [i['text'] for i in first['items']]
        assert 'Weekend z bezpłatną konsultacją' in texts
        assert 'Porozmawiaj z architektem' in texts and 'Kosztorys gratis' in texts
        assert 'Kontakt nawigacja' not in texts and 'Promocja w stopce' not in texts
        assert 'Projekt instalacji gratis' not in texts
        await page.locator('summary').click()
        second = await page.evaluate(COMMUNICATION, 'glowna')
        assert any(i['text'] == 'Projekt instalacji gratis' for i in second['items'])
        await page.close()


@pytest.mark.parametrize('background', [False, True])
def test_rotation_of_existing_banner_assets_does_not_create_a_redesign_finding(background):
    from types import SimpleNamespace
    old = capture(BEFORE, [])
    new = capture(AFTER, [])
    for shot in (old, new):
        shot.document['communication']['items'] = [{'role': 'image', 'asset': 'https://test.pl/a.jpg'}, {'role': 'image', 'asset': 'https://test.pl/b.jpg'}]
    old.document['visual'] = {'schema': 1, 'elements': [{'key': '#hero', 'src': 'https://test.pl/a.jpg', 'label': 'Rabat'}]}
    new.document['visual'] = {'schema': 1, 'elements': [{'key': '#hero', 'src': 'https://test.pl/b.jpg', 'label': 'Gratis'}]}
    if background:
        for snapshot in (old, new):
            item = snapshot.document['visual']['elements'][0]
            item['background_image'] = 'url("' + item.pop('src') + '")'
    details = visual_description(old, new, SimpleNamespace(bbox=[0,0,800,200], ratio=.1))
    assert not details['facts']


@pytest.mark.browser
async def test_search_heading_is_not_allowed_to_hide_the_project_offer(executable):
    # Source structure observed in Praktyczne Projekty: a search H2 contains
    # "Inne projekty", preceding the main H1 and the entire project description.
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        page = await scanner.browser.new_page()
        await page.set_content('''<header><div id="imHeader_imHTMLObject_04"><h2>Szukaj projektu B01 B11 Inne projekty</h2></div></header>
        <main><header><h1>B11 Projekt czworaków</h1></header><p>Komfort i prywatność czterech rodzin</p><p>Kosztorys w cenie projektu</p><a href="/kontakt">Zapytaj architekta</a></main>''')
        broken = await page.evaluate(COMMUNICATION, 'projekt')
        assert not broken['items']
        fixed = await page.evaluate(COMMUNICATION, {'page': 'projekt', 'ignore_selectors': ['#imHeader_imHTMLObject_04']})
        assert {'B11 Projekt czworaków', 'Komfort i prywatność czterech rodzin', 'Kosztorys w cenie projektu', 'Zapytaj architekta'} <= {i['text'] for i in fixed['items']}
        assert not any('Szukaj projektu' in i['text'] for i in fixed['items'])
        await page.close()
