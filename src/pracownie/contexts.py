"""Source-backed context for copy; peripheral observations stay inspectable."""
from __future__ import annotations

import re

# Reviewed against archived DOM keys from the 2026-11-09 report. These annotate
# existing observations as well as new captures; they never remove source text.
ARCHIVED_SECTIONS = {
    'artinex-projekt.pl': [('#project-list', 'catalogue')],
    'ecodomy.pl': [('#sppb-addon-1613120340836', 'editorial')],
    'hexagreen.pl': [('#swiper-wrapper-7f790fc2a6ddd222', 'testimonials')],
    'planujdom.pl': [('#content > div:nth-of-type(1) > div:nth-of-type(1) > div:nth-of-type(6) > div:nth-of-type(1) > div:nth-of-type(2)', 'testimonials')],
}
REASONS = {
    'testimonials': 'Treść opinii klienta; nie jest deklaracją warunków oferty pracowni.',
    'editorial': 'Artykuł lub poradnik; obserwacja treści redakcyjnej, nie zmiana warunków oferty.',
    'catalogue': 'Element listy lub polecanych projektów; nie potwierdza nowej kampanii ani zmiany stałej karty.',
    'dynamic': 'Animowany lub niestabilny tekst; nie potwierdzono zmiany komunikatu.',
}


def concrete_offer(text: str) -> bool:
    return bool(re.search(r'rabat|kupon|kod rabatowy|promocj|gratis|bezpłat|za darmo|w cenie|dostaw|wysył|zwrot|gwaranc', text, re.I))


def item_context(domain: str, item: dict) -> str:
    if item.get('unstable'):
        return 'dynamic'
    if item.get('context') in REASONS:
        return item['context']
    key = item.get('key', '').removeprefix('body > ')
    for prefix, context in ARCHIVED_SECTIONS.get(domain, []):
        if key == prefix or key.startswith(prefix + ' > '):
            return context
    if re.match(r'#(?:reviews?|testimonials?|opinie)(?:\b|[-_])', key, re.I):
        return 'testimonials'
    # Only the inspected site's typewriter phrases; arbitrary short edits,
    # codes and promotion headlines are not dismissed by text similarity.
    text = item.get('text', '')
    if domain == 'kowalscypracownia.pl' and (
        re.fullmatch(r'PROJEKTUJEMY MIEJSCA DO [A-ZĄĆĘŁŃÓŚŹŻ]*\|?', text)
        or key.endswith('p:nth-of-type(1) > span:nth-of-type(1)')
        and re.fullmatch(r'(?:R(?:E(?:L(?:A(?:K(?:S(?:U)?)?)?)?)?)?|P(?:R(?:A(?:C(?:Y)?)?)?)?)', text)
    ):
        return 'dynamic'
    return ''


def context_reason(domain: str, before: dict | None, after: dict | None, *, page: str = '') -> str:
    items = [i for i in (before, after) if i]
    contexts = [item_context(domain, i) for i in items]
    for kind in ('dynamic', 'testimonials', 'editorial', 'catalogue'):
        if kind not in contexts:
            continue
        if kind == 'catalogue' and page == 'glowna' and any(concrete_offer(i.get('text', '')) for i in items):
            continue
        return REASONS[kind]
    return ''


def observation_reason(item: dict) -> str:
    return context_reason(item.get('domain', ''),
                          {'key': item.get('element_before', ''), 'text': str(item.get('before') or ''),
                           'context': item.get('context_before', '')},
                          {'key': item.get('element_after', ''), 'text': str(item.get('after') or ''),
                           'context': item.get('context_after', '')}, page=item.get('page', ''))
