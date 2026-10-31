"""Keep readable offer text separate from an incomplete graphical rendering."""
from urllib.parse import urlsplit

from .extract import access_challenge
from .model import Snapshot


def only_font_styles(urls: list[str]) -> bool:
    # The public Google Fonts CSS endpoints serve font definitions, not page
    # visibility/layout rules. Never infer this from a filename like myfont.css.
    return bool(urls) and all(
        (p := urlsplit(url)).scheme in {'http', 'https'}
        and p.hostname == 'fonts.googleapis.com' and p.path in {'/css', '/css2'}
        for url in urls
    )


def captured_challenge(snapshot: Snapshot | dict) -> bool:
    # Recovery can have only observation metadata. Detect a challenge without
    # requiring unrelated fields/prices to deserialize a complete Snapshot.
    if isinstance(snapshot, dict):
        document, url, title = snapshot.get('document', {}), snapshot.get('url', ''), snapshot.get('title', '')
    else:
        document, url, title = snapshot.document, snapshot.url, snapshot.title
    payload = document.get('payload', {})
    return access_challenge({**payload, 'url': url, 'title': title + ' ' + payload.get('title', '')})


def communication_usable(snapshot: Snapshot) -> bool:
    if captured_challenge(snapshot):
        return False
    if snapshot.quality in {'ok', 'visual'}:
        return True
    # Older partial captures and arbitrary missing CSS remain untrusted. The
    # flag is written only after cookies, required elements and DOM limits pass.
    return (snapshot.quality == 'partial'
            and snapshot.document.get('readability', {}).get('text_complete') is True
            and only_font_styles(snapshot.document.get('unresolved_styles', [])))
