() => {
  const visible = e => !!(e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden');
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const css = e => {
    if (e.id && document.querySelectorAll('#' + CSS.escape(e.id)).length === 1) return '#' + CSS.escape(e.id);
    const parts = [];
    while (e && e !== document.body) {
      const siblings = e.parentElement ? [...e.parentElement.children].filter(x => x.tagName === e.tagName) : [];
      parts.unshift(e.tagName.toLowerCase() + ':nth-of-type(' + (siblings.indexOf(e) + 1) + ')');
      e = e.parentElement;
      if (e && e.id && document.querySelectorAll('#' + CSS.escape(e.id)).length === 1) { parts.unshift('#' + CSS.escape(e.id)); break; }
    }
    return (parts[0]?.startsWith('#') ? '' : 'body > ') + parts.join(' > ');
  };
  const blocks = [], sections = new Set(['oferta']), headings = [];
  let heading = 'oferta', count = 0;
  const nodes = document.body.querySelectorAll('h1,h2,h3,h4,p,li,dt,dd,td,label,summary,button,div,span,a');
  for (const e of nodes) {
    if (/^(DIV|SPAN)$/.test(e.tagName) && [...e.children].some(x => clean(x.textContent))) continue;
    if (!visible(e) || e.closest('script,style,noscript,nav,[role=navigation]')) continue;
    if (++count > 7000) break;
    const text = clean(e.innerText);
    if (!text || text.length > 3000) continue;
    if (/^H[1-4]$/.test(e.tagName)) {
      heading = text; sections.add(heading); headings.push(text);
    }
    blocks.push({heading, text, tag:e.tagName});
  }
  const prices = [];
  for (const e of document.querySelectorAll('[itemprop=price],ins,del,s,[class*=price],[class*=Price],[class*=cena]')) {
    if (!visible(e)) continue;
    const text = clean(e.innerText || e.getAttribute('content'));
    if (!text || text.length > 220 || !/\d/.test(text)) continue;
    if ([...e.children].some(c => /(?:zł|PLN|EUR|€)/i.test(c.innerText || ''))) continue;
    const near = clean(e.closest('label,li,dd,article,[class*=option],[class*=variant]')?.innerText || e.parentElement?.innerText);
    prices.push({text, context:near.slice(0,400), type:e.tagName + ' ' + e.className + ' ' + getComputedStyle(e).textDecorationLine, selector:css(e)});
  }
  const products = [];
  const walk = value => {
    if (!value || typeof value !== 'object') return;
    if (Array.isArray(value)) return value.forEach(walk);
    const types = [].concat(value['@type'] || []);
    if (types.some(t => /Product$/i.test(t))) products.push(value);
    if (value['@graph']) walk(value['@graph']);
    if (value.mainEntity) walk(value.mainEntity);
    if (value.itemListElement) walk(value.itemListElement);
    if (value.item) walk(value.item);
  };
  for (const e of document.querySelectorAll('script[type="application/ld+json"]')) {
    try { walk(JSON.parse(e.textContent)); } catch { /* malformed structured data is optional */ }
  }
  const links = [...document.querySelectorAll('a[href]')].filter(e => visible(e) && !e.closest('nav,[role=navigation],footer')).slice(0,2000).map(e => ({
    url:e.href, text:clean(e.innerText || e.getAttribute('aria-label') || e.querySelector('img')?.alt),
    context:clean(e.closest('article,li,[class*=card],[class*=product],[class*=projekt]')?.innerText).slice(0,500),
    image:!!e.querySelector('img'),
  }));
  const controls = [];
  for (const e of document.querySelectorAll('summary,[role=tab],button,a[data-toggle=tab],a[data-bs-toggle=tab],a[class*=button],a[class*=btn],a[href*=koszyk],a[href*=zamow],a[href*=cart],select,input[type=radio],input[type=checkbox]')) {
    if (!visible(e) || e.closest('#CybotCookiebotDialog,#onetrust-banner-sdk,#onetrust-pc-sdk')) continue;
    const label = clean(e.getAttribute('aria-label') || e.labels?.[0]?.innerText || e.innerText || e.getAttribute('title') || e.name);
    let kind = e.tagName === 'SUMMARY' ? 'expand' : e.getAttribute('role') === 'tab' || e.dataset.toggle === 'tab' || e.dataset.bsToggle === 'tab' ? 'tab' : 'unknown';
    if (e.tagName === 'SELECT') kind = 'select';
    if (e.tagName === 'INPUT') kind = e.type;
    if (/^(dodaj do koszyka|do koszyka|dodaj projekt do koszyka|add to cart|zamów (ten )?projekt|kup projekt|kup teraz)$/i.test(label)) kind = 'cart';
    if (/następn.*slajd|next slide/i.test(label)) kind = 'carousel';
    controls.push({selector:css(e), label, kind, name:e.name || '', checked:!!e.checked,
      value:e.value || '', expanded:e.getAttribute('aria-expanded'),
      options:e.tagName === 'SELECT' ? [...e.options].filter(o => !o.disabled && o.value).map(o => ({value:o.value,label:clean(o.text)})) : []});
  }
  const images = [...document.images].filter(visible).map(e => ({
    alt:clean(e.alt), src:e.currentSrc, width:e.naturalWidth, height:e.naturalHeight,
    rendered_width:e.getBoundingClientRect().width, rendered_height:e.getBoundingClientRect().height,
    broken:!e.complete || e.naturalWidth === 0,
  }));
  return {title:clean(document.title), h1:clean(document.querySelector('h1')?.innerText),
    text:clean(document.body.innerText), blocks, prices, products, links, controls,
    sections:[...sections], headings, images, truncated:count>7000};
}
