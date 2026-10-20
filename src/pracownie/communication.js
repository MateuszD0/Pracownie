// A separate, versioned measurement: price adapters never invalidate this copy.
(pageKind = 'glowna') => {
  const clean = s => (s || '').replace(/\s+/g,' ').trim();
  const omit = 'nav,footer,[role=navigation],script,style,noscript,.screen-reader-text,.sr-only,.visually-hidden,[id*=cookie i],[id*=consent i],[class*=cookie i],form[role=search],[class*=search-form],.related,.upsells,.cross-sells,[class*=related-products],[class*=similar-project],[class*=recommended-products]';
  const rotator = '.swiper,.swiper-container,.swiper-wrapper,.slick-slider,.owl-carousel,.carousel,[aria-roledescription=carousel],[class*=slider],[class*=rotator]';
  const slide = '.swiper-slide,.slick-slide,.owl-item,.carousel-item,[aria-roledescription=slide]';
  const shown = e => !!e.getClientRects().length && (!e.checkVisibility || e.checkVisibility({visibilityProperty:true,opacityProperty:true}));
  const related=[];
  if(pageKind==='projekt') {
    const headings=[...document.querySelectorAll('h2,h3,h4')];
    for(let i=0;i<headings.length;i++) {
      const h=headings[i];if(!/podobne projekty|polecane projekty|inne projekty|zobacz również|zobacz także|warianty projektu/i.test(h.textContent))continue;
      const range=document.createRange();range.setStartBefore(h);
      const next=headings.slice(i+1).find(n=>Number(n.tagName[1])<=Number(h.tagName[1]));
      if(next)range.setEndBefore(next);else range.setEndAfter(document.body.lastChild);related.push(range);
    }
  }
  const excluded = e => {
    for(let p=e;p&&p!==document.body&&p!==document.documentElement;p=p.parentElement)if(p.matches(omit))return true;
    return related.some(r=>r.intersectsNode(e));
  };
  const path = e => {
    const parts=[];
    for(let p=e;p&&p!==document.body;p=p.parentElement) {
      if(p.id && document.querySelectorAll('#'+CSS.escape(p.id)).length===1){parts.unshift('#'+CSS.escape(p.id));break;}
      const peers=[...p.parentElement?.children||[]].filter(x=>x.tagName===p.tagName);
      parts.unshift(p.tagName.toLowerCase()+':nth-of-type('+(peers.indexOf(p)+1)+')');
    }
    return parts.join(' > ');
  };
  const items=[], seen=new Set(); let truncated=false, characters=0;
  const put = (e,role,text) => {
    text=clean(text);if(!text||text.length<3)return;
    if(text.length>18000){truncated=true;return;}
    const identity=role+'\n'+text;if(seen.has(identity))return;
    if(items.length>=2200 || characters+text.length>500000){truncated=true;return;}seen.add(identity);characters+=text.length;
    const heading=e.closest('[id]');
    items.push({key:path(e),role,text,url:location.href.split('#')[0]+(heading?'#'+encodeURIComponent(heading.id):'')});
  };
  // Read all slides as a bounded DOM inventory. No marketing consent or
  // carousel clicks are needed, and hidden accordion content stays excluded.
  for(const e of document.querySelectorAll('h1,h2,h3,h4,p,li,dt,dd,td,summary,button,a,div,span')) {
    if(excluded(e))continue;
    const carousel=e.closest(rotator), inSlide=e.closest(slide);
    if(!shown(e) && !(carousel && shown(carousel) && inSlide))continue;
    if(carousel && e.closest('.slick-cloned,.swiper-slide-duplicate'))continue;
    if(e.closest('[role=dialog]') && /cookie|zgod|prywatno/i.test(e.closest('[role=dialog]').textContent))continue;
    const control=e.closest('a,button,summary');
    if(control && control!==e && !/^H[1-4]$/.test(e.tagName))continue;
    if(e.tagName==='A' && e.closest('h1,h2,h3,h4'))continue;
    if(/^(DIV|SPAN|LI|TD)$/.test(e.tagName)&&[...e.children].some(c=>clean(c.textContent)))continue;
    if(e.tagName==='A' && e.querySelector('p,h1,h2,h3,h4'))continue;
    const role=carousel?'banner':/^H[1-4]$/.test(e.tagName)?'heading':/^(A|BUTTON|SUMMARY)$/.test(e.tagName)?'cta':'text';
    put(e,role,carousel?e.textContent:e.innerText);
  }
  for(const e of document.images) {
    if(excluded(e) || !e.closest(rotator) || !shown(e.closest(rotator)) || e.closest('.slick-cloned,.swiper-slide-duplicate'))continue;
    // Assets retain source URL + accessible caption, including image-only ads.
    const src=e.getAttribute('data-src')||e.getAttribute('src');
    if(!src||src.startsWith('data:')||e.naturalWidth&&e.naturalWidth<80)continue;
    const asset=new URL(src,location.href).href;
    put(e,'image',(e.alt?e.alt+' · ':'')+asset);
    const item=items.find(i=>i.key===path(e)&&i.role==='image');if(item)item.asset=asset;
  }
  for(const e of [...document.querySelectorAll(rotator)].flatMap(r=>[r,...r.querySelectorAll('*')]).slice(0,3000)) {
    if(excluded(e) || !shown(e.closest(rotator)) || e.closest('.slick-cloned,.swiper-slide-duplicate'))continue;
    const background=getComputedStyle(e).backgroundImage;
    for(const match of background.matchAll(/url\(["']?([^"')]+)["']?\)/g)) {
      const asset=new URL(match[1],location.href).href;if(asset.startsWith('data:'))continue;
      put(e,'image',(e.getAttribute('aria-label')?e.getAttribute('aria-label')+' · ':'')+asset);
      const item=items.find(i=>i.key===path(e)&&i.role==='image');if(item)item.asset=asset;
    }
  }
  return {contract:'communication-v1',items,truncated,page:pageKind};
}
