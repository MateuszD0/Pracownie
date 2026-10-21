() => {
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const selector = e => {
    if(e.id && document.querySelectorAll('#'+CSS.escape(e.id)).length===1)return '#'+e.id;
    const parts=[];
    for(let p=e;p && p!==document.body;p=p.parentElement){
      const siblings=[...p.parentElement.children].filter(x=>x.tagName===p.tagName);
      parts.unshift(p.tagName.toLowerCase()+':nth-of-type('+(siblings.indexOf(p)+1)+')');
    }
    return parts.join(' > ');
  };
  const anchors={},elements=[];
  for(const e of document.querySelectorAll('body,h1,h2,h3,header,main,img,[class*=hero],[class*=banner],button,[role=button],a[class*=btn],a[class*=button]')){
    const r=e.getBoundingClientRect(),style=getComputedStyle(e);
    if(!e.getClientRects().length || style.visibility==='hidden' || style.display==='none' || r.width<5 || r.height<5 || r.right<=0 || r.left>=document.documentElement.clientWidth)continue;
    const overlay=e.closest('[id*=cookie i],[id*=consent i],[class*=cookie i],[role=dialog],footer');
    // WordPress plugins also put cookie state classes on the whole body.
    // Those classes do not turn every page element into a consent overlay.
    if(overlay && overlay!==document.body && overlay!==document.documentElement)continue;
    const heading=/^H[1-3]$/.test(e.tagName),image=e.tagName==='IMG',control=e.matches('button,[role=button],a[class*=btn],a[class*=button]');
    if(image && (r.width<200 || r.height<100 || !e.complete || !e.naturalWidth))continue;
    const anchor=e.closest('[id]')?.id || '';
    if(heading && anchor)anchors[clean(e.innerText)]=anchor;
    const area=e.closest('[class*=hero],[class*=banner]')?'baner':e.closest('header')?'nagłówek strony':'treść strony';
    const label=clean(image?(e.alt || area):e.getAttribute('aria-label') || (heading||control?e.innerText:area)).slice(0,120);
    elements.push({key:selector(e),label,text:heading?clean(e.innerText):'',src:image?e.currentSrc:'',
      background:style.backgroundColor,background_image:style.backgroundImage==='none'?'':style.backgroundImage,color:!image?style.color:'',font:!image?style.fontFamily:'',
      font_size:!image?style.fontSize:'',font_weight:!image?style.fontWeight:'',border_radius:style.borderRadius,
      rect:[Math.round(r.x),Math.round(r.y+scrollY),Math.round(r.width),Math.round(r.height)],
      url:anchor?location.href.split('#')[0]+'#'+encodeURIComponent(anchor):location.href});
    if(elements.length>=100)break;
  }
  return {schema:1,elements,anchors};
}
