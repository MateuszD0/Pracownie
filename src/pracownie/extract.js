(pageKind = 'glowna') => {
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const visible = e => {
    if (!e || !e.getClientRects().length) return false;
    if (e.checkVisibility && !e.checkVisibility({visibilityProperty:true,opacityProperty:true})) return false;
    const r=e.getBoundingClientRect();
    if (r.width<=1 || r.height<=1 || r.right<=0 || r.left>=document.documentElement.clientWidth || e.closest('.screen-reader-text,.sr-only,.visually-hidden')) return false;
    for (let p=e.parentElement; p; p=p.parentElement) {
      if (p.tagName==='DETAILS' && !p.open && !p.querySelector(':scope > summary')?.contains(e)) return false;
      const style=getComputedStyle(p);
      if (/hidden|clip/.test(style.overflowX)) {
        const pr=p.getBoundingClientRect();
        if (r.right<=pr.left || r.left>=pr.right) return false;
      }
    }
    return true;
  };
  const css = e => {
    if (e.id && document.querySelectorAll('#'+CSS.escape(e.id)).length===1) return '#'+CSS.escape(e.id);
    const parts=[];
    while(e && e!==document.body) {
      const siblings=e.parentElement?[...e.parentElement.children].filter(x=>x.tagName===e.tagName):[];
      parts.unshift(e.tagName.toLowerCase()+':nth-of-type('+(siblings.indexOf(e)+1)+')');
      e=e.parentElement;
      if(e?.id && document.querySelectorAll('#'+CSS.escape(e.id)).length===1) {parts.unshift('#'+CSS.escape(e.id));break;}
    }
    return (parts[0]?.startsWith('#')?'':'body > ')+parts.join(' > ');
  };
  const cookieSelector='#CybotCookiebotDialog,#onetrust-banner-sdk,#onetrust-pc-sdk,#CookiebotDialog,[id*=cookie i],[id*=consent i]:not(input):not(select):not(label):not(button),[class*=cookie-banner i],[class*=cookie-notice i],[class*=cookies-panel i]';
  const relatedSelector='.related,.upsells,.cross-sells,[data-related-products],[class*=related-products],[class*=similar-project],[class*=recommended-products],[class*=podobne-projekty]';
  const searchSelector='form[role=search],form[action*=szuk],form[action*=search],#ProjectSearch,#filter-form,[data-catalog-filter],[class*=search-form],[class*=search_form],[class*=filter-form],[class*=filters-form]';
  const relatedRanges=[];
  if(pageKind==='projekt') {
    const headings=[...document.querySelectorAll('h2,h3,h4')];
    for(let i=0;i<headings.length;i++) {
      const h=headings[i];
      if(!/podobne projekty|polecane projekty|inne projekty|zobacz również|zobacz także|warianty projektu/i.test(h.innerText))continue;
      const range=document.createRange();range.setStartBefore(h);
      const next=headings.slice(i+1).find(n=>Number(n.tagName[1])<=Number(h.tagName[1]));
      if(next)range.setEndBefore(next);else range.setEndAfter(document.body.lastChild);
      relatedRanges.push(range);
    }
  }
  const scope = e => {
    if(e.closest(cookieSelector) || e.closest('[role=dialog]') && /cookies|prywatno|ciastecz|zgod|consent/i.test(e.closest('[role=dialog]').innerText)) return 'privacy';
    if(e.closest(relatedSelector) || relatedRanges.some(r=>r.intersectsNode(e))) return 'related';
    if(e.closest(searchSelector)) return 'search';
    if(e.closest('nav,footer,[role=navigation],[role=banner],body > header,#main-header,#masthead,header.site-header')) return 'navigation';
    if(e.tagName==='SELECT' && [...e.options].some(o=>/^(https?:|\/)|\.(html|php)([?#]|$)/i.test(o.value))) return 'navigation';
    return 'offer';
  };
  const primaryTitle=document.querySelector('h1.product_title,h1[itemprop=name]') || document.querySelector('main h1') || document.querySelector('article h1') || document.querySelector('h1');
  const blocks=[], sections=new Set(['oferta']), headings=[];
  let heading='oferta',count=0;
  for(const e of document.body.querySelectorAll('h1,h2,h3,h4,p,li,dt,dd,td,label,summary,button,div,span,a')) {
    if(/^(DIV|SPAN)$/.test(e.tagName) && [...e.children].some(x=>clean(x.textContent))) continue;
    if(!visible(e) || e.closest('script,style,noscript') || ['privacy','navigation','related','search'].includes(scope(e))) continue;
    if(++count>7000) break;
    const text=clean(e.innerText);
    if(!text || text.length>1800) continue;
    if(/^H[1-4]$/.test(e.tagName)){heading=text;sections.add(heading);headings.push(text);}
    blocks.push({heading,text,tag:e.tagName});
  }
  const prices=[];
  for(const e of document.querySelectorAll('[itemprop=price],bdi,ins,del,s,[class*=price],[class*=Price],[class*=cena]')) {
    if(!visible(e) || scope(e)!=='offer') continue;
    const text=clean(e.innerText || e.getAttribute('content'));
    if(!text || text.length>220 || !/\d/.test(text)) continue;
    if([...e.children].some(c=>/\d[\d\s.,]*\s*(?:zł|PLN|EUR|€)/i.test(c.innerText || ''))) continue;
    const container=e.closest('label,li,dd,[class*=option],[class*=variant]');
    const context=clean(container?.innerText || e.parentElement?.innerText).slice(0,400);
    const name=clean(container?.querySelector('h2,h3,h4,[itemprop=name]')?.innerText || (pageKind==='projekt'?primaryTitle?.innerText:''));
    const primary=pageKind==='projekt' && !!e.closest('.summary,.product-summary,[class*=product-info],[itemprop=offers],.project-price,.product-price,.cena-projektu');
    prices.push({text,context,type:e.tagName+' '+String(e.className)+' '+getComputedStyle(e).textDecorationLine+(e.closest('del,s')?' previous':''),selector:css(e),primary,name});
  }
  const products=[];
  const walk=value=>{
    if(!value || typeof value!=='object')return;
    if(Array.isArray(value)){value.forEach(walk);return;}
    if([].concat(value['@type'] || []).some(t=>/Product$/i.test(t)))products.push(value);
    for(const key of ['@graph','mainEntity','itemListElement','item'])if(value[key])walk(value[key]);
  };
  for(const e of document.querySelectorAll('script[type="application/ld+json"]')){try{walk(JSON.parse(e.textContent));}catch{}}
  const identity=value=>{try{const u=new URL(value,location.href);return u.hostname.replace(/^www\./,'')+u.pathname.replace(/\/$/,'');}catch{return '';}};
  let selectedProducts=products;
  if(pageKind==='projekt') {
    const own=products.filter(p=>[p.url,p['@id'],...[].concat(p.offers || []).map(o=>o.url)].some(u=>u && identity(u)===identity(location.href)));
    selectedProducts=own.length?own:products.length===1 && (!products[0].url || identity(products[0].url)===identity(location.href))?products:[];
  }
  const links=[...document.querySelectorAll('a[href]')].filter(e=>visible(e) && scope(e)==='offer').slice(0,2000).map(e=>({
    url:e.href,text:clean(e.getAttribute('aria-label') || e.querySelector('img')?.alt || e.innerText || e.getAttribute('title')),
    context:clean(e.closest('article,li,[class*=card],[class*=product],[class*=projekt],[class*=offer],[class*=item]')?.innerText).slice(0,500),image:!!e.querySelector('img')
  }));
  const controls=[];
  // Catalogue links in navigation help select the first fixed project. They
  // stay separate from offer content and are never scanned after selection.
  const discoveryLinks=[...document.querySelectorAll('a[href]')]
    .filter(e=>visible(e) && scope(e)!=='privacy')
    .map(e=>({url:e.href,text:clean(e.innerText || e.getAttribute('aria-label'))}))
    .filter(e=>/bestseller|najpopular|najlepiej sprzed|^(?:(?:zobacz|nasze|wszystkie) )?projekty(?: domów| gotowe| gotowe domów)?$|^katalog(?: projektów)?$/i.test(e.text)).slice(0,40);
  for(const e of document.querySelectorAll('summary,[role=tab],button,a[data-toggle=tab],a[data-bs-toggle=tab],a[class*=button],a[class*=btn],a[href*=koszyk],a[href*=zamow],a[href*=cart],select,input[type=radio],input[type=checkbox],input[type=submit],input[type=button],input[type=image]')) {
    const associated=e.labels?.[0];
    const checkable=e.tagName==='INPUT' && /radio|checkbox/.test(e.type);
    const target=checkable && !visible(e) && visible(associated)?associated:e;
    if(!visible(target) || e.disabled || e.getAttribute('aria-disabled')==='true')continue;
    const s=scope(e);
    if(s!=='offer')continue;
    const label=clean(e.getAttribute('aria-label') || associated?.innerText || e.innerText || e.getAttribute('alt') || (e.tagName==='INPUT'?e.value:'') || e.getAttribute('title') || e.querySelector('img')?.alt || e.name);
    if(!label)continue;
    let kind=e.tagName==='SUMMARY' || e.hasAttribute('aria-expanded') && e.hasAttribute('aria-controls')?'expand':e.getAttribute('role')==='tab' || e.dataset.toggle==='tab' || e.dataset.bsToggle==='tab'?'tab':'unknown';
    if(e.tagName==='SELECT')kind='select';
    if(e.tagName==='INPUT')kind=e.type;
    if(/^(dodaj do koszyka|do koszyka|dodaj projekt do koszyka|add to cart|zamów (ten )?projekt|kup projekt|kup teraz)$/i.test(label))kind='cart';
    if(/następn.*slajd|next slide/i.test(label))kind='carousel';
    controls.push({selector:css(e),label_selector:associated && visible(associated)?css(associated):null,label,kind,name:e.name || '',checked:!!e.checked,scope:s,
      href:e.tagName==='A'?e.href:'',value:e.value || '',expanded:e.getAttribute('aria-expanded'),
      options:e.tagName==='SELECT'?[...e.options].filter(o=>!o.disabled && o.value).map(o=>({value:o.value,label:clean(o.text)})):[]});
  }
  const images=[...document.images].filter(e=>visible(e) && scope(e)!=='privacy').map(e=>({alt:clean(e.alt),src:e.currentSrc,width:e.naturalWidth,height:e.naturalHeight,rendered_width:e.getBoundingClientRect().width,rendered_height:e.getBoundingClientRect().height,broken:!e.complete || e.naturalWidth===0}));
  const metaAmount=document.querySelector('meta[property="product:sale_price:amount"]') || document.querySelector('meta[property="product:price:amount"]') || document.querySelector('meta[property="og:price:amount"]');
  const metaCurrency=document.querySelector('meta[property="product:price:currency"],meta[property="og:price:currency"]');
  const metaPrice=pageKind==='projekt' && metaAmount && metaCurrency?{amount:metaAmount.content,currency:metaCurrency.content}:null;
  return {version:2,page:pageKind,url:location.href,title:clean(document.title),h1:clean(primaryTitle?.innerText),text:clean(document.body.innerText),blocks,prices,products:selectedProducts,meta_price:metaPrice,links,discovery_links:discoveryLinks,controls,sections:[...sections],headings,images,truncated:count>7000};
}
