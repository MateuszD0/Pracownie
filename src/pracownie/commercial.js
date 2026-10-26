() => {
  // Supplementary offer context, including benefits outside the main product
  // description. It does not change the daily communication baseline.
  const words=/promoc|rabat|kupon|gratis|bezpłat|za darmo|pakiet|w cenie|dodatk/i;
  const excluded='script,style,noscript,[id*=cookie i],[class*=cookie i],[id*=consent i],.related,.upsells,.cross-sells,[data-related-products],[class*=similar-project],[class*=recommended-products]';
  const items=[], seen=new Set(); let truncated=false;
  for(const e of document.querySelectorAll('h1,h2,h3,h4,p,li,small,span,button,a,summary,div')) {
    if(e.closest(excluded) || e.querySelector('div,p,li,h1,h2,h3,h4'))continue;
    if(!e.getClientRects().length || !e.checkVisibility({visibilityProperty:true,opacityProperty:true}))continue;
    const text=(e.innerText||'').replace(/\s+/g,' ').trim();
    if(!text || !words.test(text) || seen.has(text))continue;
    if(text.length>1600){truncated=true;continue;}
    seen.add(text);
    if(items.length>=120){truncated=true;break;}
    const anchor=e.closest('[id]');
    items.push({text,url:location.href.split('#')[0]+(anchor?'#'+encodeURIComponent(anchor.id):'')});
  }
  const links=[];
  for(const e of document.querySelectorAll('a[href]')) {
    const text=(e.innerText||e.querySelector('img')?.alt||e.getAttribute('aria-label')||'').replace(/\s+/g,' ').trim();
    if(e.closest(excluded) || !e.checkVisibility({visibilityProperty:true,opacityProperty:true}) || !words.test(text+' '+e.href))continue;
    if(links.length>=100){truncated=true;break;}
    links.push({url:e.href,text:text.slice(0,300)});
  }
  return {contract:'commercial-v1',items,links,truncated};
}
