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


def captured_challenge(snapshot: Snapshot) -> bool:
    return access_challenge({**snapshot.document.get('payload', {}), 'url': snapshot.url, 'title': snapshot.title})


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
